#!/usr/bin/env python3
"""Monitor de señales públicas; no elude restricciones ni retransmite video."""
import argparse, concurrent.futures as cf, csv, datetime as dt, json, os, re, subprocess, threading, time, unicodedata, urllib.request, urllib.error, urllib.parse
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parent
CAT=ROOT/'Canales.json'; STATE=ROOT/'Estado.json'; REPORT=ROOT/'Estado.csv'; CAND=ROOT/'Candidatos.json'; LOG=ROOT/'Historial.csv'
HEADERS={'User-Agent':'Mi-IPTV-monitor/1.0 (public stream health check)','Accept':'*/*'}
LOCK=threading.Lock(); HOSTS={}
SOURCES=['https://iptv-org.github.io/iptv/countries/py.m3u','https://nexonic-technologies.github.io/nexonic-iptv/playlists/countries/py.m3u']
def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
def valid(u):
    try:
        p=urllib.parse.urlsplit(u); return p.scheme in ('http','https') and bool(p.hostname) and not p.username and not p.password and not any(x in u for x in '\r\n')
    except ValueError: return False
def hostlock(u):
    h=urllib.parse.urlsplit(u).hostname or ''
    # Agrupa subdominios de un mismo proveedor.
    h='.'.join(h.split('.')[-2:]) if not re.fullmatch(r'[\d.]+',h) else h
    with LOCK: return HOSTS.setdefault(h,threading.BoundedSemaphore(2))
def fetch(u,limit=262144,timeout=8):
    if not valid(u): raise ValueError('URL no admitida')
    with urllib.request.urlopen(urllib.request.Request(u,headers=HEADERS),timeout=timeout) as r:
        if not valid(r.geturl()): raise ValueError('Redireccion no admitida')
        return r.read(limit),r.geturl()
def quick(u):
    try:
        body,final=fetch(u)
        if b'#EXTM3U' not in body[:1024]: return 'no_hls'
        if b'#EXT-X-STREAM-INF' in body: return 'hls_master'
        if b'#EXTINF' in body: return 'hls_media'
        return 'hls_sin_segmentos'
    except urllib.error.HTTPError as e: return 'http_'+str(e.code)
    except (OSError,ValueError) as e: return 'error_red_'+type(e).__name__
def deep(u):
    # No se usan cookies, tokens nuevos, cabeceras de suplantación ni DRM.
    common=['-v','error','-rw_timeout','6000000','-protocol_whitelist','http,https,tcp,tls,crypto']
    try:
        p=subprocess.run(['ffprobe',*common,'-analyzeduration','3000000','-probesize','1000000','-show_entries','stream=codec_type,codec_name,width,height','-of','json',u],capture_output=True,text=True,timeout=18)
        streams=json.loads(p.stdout or '{}').get('streams',[])
        v=next((s for s in streams if s.get('codec_type')=='video'),{})
        a=next((s for s in streams if s.get('codec_type')=='audio'),{})
        info={'video':v.get('codec_name',''),'audio':a.get('codec_name',''),'resolucion':f"{v.get('width','')}x{v.get('height','')}" if v else ''}
        if p.returncode or not v or not a: return {'estado':'sin_audio_video_confirmado',**info}
        # Decodifica brevemente ambas pistas; no guarda ni distribuye contenido.
        q=subprocess.run(['ffmpeg','-nostdin',*common,'-xerror','-i',u,'-t','3','-map','0:v:0','-map','0:a:0','-f','null','-'],capture_output=True,timeout=22)
        return {'estado':'decodifica' if q.returncode==0 else 'error_decodificacion',**info}
    except (subprocess.TimeoutExpired,OSError,ValueError): return {'estado':'timeout_o_error'}
def check(u,do_deep):
    with hostlock(u):
        result={'rapida':quick(u)}
        if do_deep and result['rapida'] in ('hls_master','hls_media'): result['multimedia']=deep(u)
        return result

def norm(s):
    s=re.sub(r'^\s*\d+\s*[-.]\s*','',s)
    s=re.sub(r'\s*[\[(](?:alternativa|opci[oó]n|respaldo)[^\])]*[\])]','',s,flags=re.I)
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
def discover(channels):
    # Solo sugerencias: una coincidencia de nombre no prueba identidad ni autorización.
    candidates=load(CAND,{}); idx=defaultdict(list)
    for c in channels: idx[norm(c['nombre'])].append(c)
    for src in SOURCES:
        try: raw,_=fetch(src,limit=4_000_000,timeout=20); name=None
        except (OSError,ValueError): continue
        for line in raw.decode('utf-8-sig','replace').splitlines():
            line=line.strip()
            if line.startswith('#EXTINF:'):
                m=re.search(r'tvg-name="([^"]+)"',line); name=m.group(1) if m else line.rsplit(',',1)[-1]
            elif valid(line) and name:
                for c in idx.get(norm(name),[]):
                    if line!=c['principal'] and line not in [a['url'] for a in c['alternativas']]:
                        arr=candidates.setdefault(c['id'],[])
                        if not any(x['url']==line for x in arr): arr.append({'url':line,'fuente':src,'nombre':name,'aprobada':False})
                name=None
    save(CAND,candidates)
def render(channels):
    lines=['#EXTM3U','# Catalogo permanente Paraguay. Sin enlace: comentario no reproducible.']
    for c in sorted(channels,key=lambda c:c['numero']):
        n=c['numero']; name=c['nombre'].replace('"',"'").replace('\n',' '); u=c['principal']
        if valid(u): lines += [f'#EXTINF:-1 tvg-id="{c["id"]}" tvg-name="{name}" tvg-chno="{n}" group-title="Paraguay",{n:03d} - {name}',u]
        else: lines.append(f'# PENDIENTE {n:03d} - {name} (sin enlace directo)')
    return '\n'.join(lines)+'\n'
def run(mode):
    channels=load(CAT,[]); assert len(channels)==154 and len({c['id'] for c in channels})==154, 'Catalogo incompleto o ID repetido'
    old=load(STATE,{}); state={}; do_deep=mode in ('profunda','completa'); do_search=mode=='completa'
    urls=set()
    for c in channels:
        if valid(c['principal']): urls.add(c['principal'])
        urls.update(a['url'] for a in c['alternativas'] if a.get('aprobada') is True and valid(a['url']))
    results={}
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        jobs={pool.submit(check,u,do_deep):u for u in sorted(urls)}
        for f in cf.as_completed(jobs):
            try: results[jobs[f]]=f.result()
            except Exception: results[jobs[f]]={'rapida':'error_interno'}
    changes=[]; timestamp=now(); modified=False
    for c in channels:
        cid=c['id']; prev=old.get(cid,{}); u=c['principal']; r=results.get(u,{'rapida':'sin_enlace'}); previous_urls=prev.get('urls',{}); records={}
        for candidate in [u]+[a['url'] for a in c['alternativas'] if a.get('aprobada') is True]:
            if not valid(candidate): continue
            rr=results.get(candidate,{'rapida':'sin_prueba'}); pp=previous_urls.get(candidate,{})
            ok=rr['rapida'] in ('hls_master','hls_media'); mm=rr.get('multimedia')
            rec={'rapida':rr['rapida'],'fallos_rapidos':0 if ok else min(3,pp.get('fallos_rapidos',0)+1),'multimedia':mm or pp.get('multimedia',{}),'exitos_multimedia':pp.get('exitos_multimedia',0),'fallos_multimedia':pp.get('fallos_multimedia',0)}
            if mm:
                good=mm['estado']=='decodifica'; rec['exitos_multimedia']=min(2,rec['exitos_multimedia']+1) if good else 0; rec['fallos_multimedia']=0 if good else min(3,rec['fallos_multimedia']+1)
            elif not ok: rec['exitos_multimedia']=0
            records[candidate]=rec
        current=records.get(u,{})
        # Solo sustituye por una alternativa expresamente aprobada y confirmada dos veces.
        if do_deep and (not u or current.get('fallos_rapidos',0)>=2 or current.get('fallos_multimedia',0)>=2):
            for a in c['alternativas']:
                alt=a['url']; ar=records.get(alt,{})
                if a.get('aprobada') is True and alt!=u and ar.get('exitos_multimedia',0)>=2 and ar.get('multimedia',{}).get('video')=='h264' and ar.get('multimedia',{}).get('audio')=='aac':
                    if u: c['alternativas'].append({'url':u,'aprobada':False,'fuente':'principal anterior'})
                    c['alternativas']=[x for x in c['alternativas'] if x['url']!=alt]; c['principal']=alt; modified=True; u=alt; break
        status=records.get(u,{}).get('rapida','sin_enlace')
        media=records.get(u,{}).get('multimedia',{}).get('estado','pendiente')
        item={'principal':u,'rapida':status,'multimedia':media,'urls':records}
        state[cid]=item
        if (prev.get('principal'),prev.get('rapida'),prev.get('multimedia'))!=(u,status,media): changes.append([timestamp,cid,c['nombre'],status,media,'principal cambiado' if prev.get('principal') not in (None,u) else 'estado'])
    save(STATE,state)
    if modified: save(CAT,channels)
    # Nunca elimina una entrada por fallo ni introduce páginas HTML como señales.
    text=render(channels); playlist=ROOT/'Paraguay.m3u'
    if not playlist.exists() or playlist.read_text(encoding='utf-8-sig')!=text: playlist.write_text(text,encoding='utf-8')
    with REPORT.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['numero','id','canal','prueba_cielo_2026-11-26','checker_2026-11-26','rapida','multimedia','video','audio','resolucion'])
        for c in channels:
            s=state[c['id']]; m=s['urls'].get(s['principal'],{}).get('multimedia',{}); w.writerow([c['numero'],c['id'],c['nombre'],c['prueba_cielo'],c['checker'],s['rapida'],s['multimedia'],m.get('video',''),m.get('audio',''),m.get('resolucion','')])
    if changes:
        exists=LOG.exists()
        with LOG.open('a',encoding='utf-8',newline='') as f:
            w=csv.writer(f)
            if not exists: w.writerow(['utc','id','canal','rapida','multimedia','evento'])
            w.writerows(changes)
    if do_search: discover(channels)
    from collections import Counter
    summary=f'### IPTV Paraguay — {timestamp}\n\nModo: {mode}. Registros: {len(channels)}. URLs comprobadas: {len(urls)}. Cambios de estado: {len(changes)}.\n\n{dict(Counter(s["rapida"] for s in state.values()))}\n\nMultimedia: {dict(Counter(s["multimedia"] for s in state.values()))}\n\nLas pruebas son desde GitHub, no desde Samsung.\n'
    print(summary)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f: f.write(summary)
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--modo',choices=['rapida','profunda','completa'],default='completa'); run(ap.parse_args().modo)
