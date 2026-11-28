"""Registro persistente, verificacion rotativa y descubrimiento revisable."""
import argparse, csv, json, subprocess, time, concurrent.futures, urllib.request
from pathlib import Path
from Integrar import parse, name, group, norm, merge, attr, SOURCES
R=Path(__file__).resolve().parent
DB=R/'Registro_Senales.json'; BASE=R/'Paraguay.m3u'
def load(): return json.loads(DB.read_text()) if DB.exists() else {}
def save(db):
 t=DB.with_suffix('.tmp'); t.write_text(json.dumps(db,ensure_ascii=False,indent=2,sort_keys=True)+'\n'); t.replace(DB)
def absorb(db,path,force=None):
 if not path.exists():return
 for h,u,opts in parse(path.read_text(encoding='utf-8-sig')):
  if not u in db:db[u]={'nombre':name(h),'grupo':group(h,force),'cabecera':h,'opciones':opts,'ultimo':0,'fallos':0,'estado':'pendiente'}
def snapshot(db):
 absorb(db,BASE);save(db)
def probe(u):
 try:
  p=subprocess.run(['ffprobe','-v','error','-rw_timeout','7000000','-analyzeduration','2000000','-probesize','500000','-show_entries','stream=codec_type','-of','json',u],capture_output=True,timeout=12)
  streams=json.loads(p.stdout).get('streams',[])
  return 'video_detectado' if p.returncode==0 and any(x.get('codec_type')=='video' for x in streams) else 'no_confirmado'
 except Exception:return 'no_confirmado'
def maintain(db):
 for f,g in [('Paraguay.m3u',None),('Paraguay_Alternativas_Aprobadas.m3u','Paraguay'),('Canales_Adicionales.m3u',None),('Enlaces_Aprobados.m3u',None)]:absorb(db,R/f,g)
 # Priorizar Paraguay sin impedir la rotacion internacional.
 key=lambda u:db[u].get('ultimo',0)
 py=sorted((u for u in db if db[u]['grupo']=='Paraguay'),key=key)
 other=sorted((u for u in db if db[u]['grupo']!='Paraguay'),key=key)
 batch=py[:80]+other[:240]; now=int(time.time())
 with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
  for u,state in zip(batch,ex.map(probe,batch)):
   row=db[u];row.update(ultimo=now,estado=state,fallos=0 if state=='video_detectado' else row.get('fallos',0)+1)
 save(db)
 # No borrar canales ante fallos temporales, ni publicar candidatos sin revision.
 from Integrar import set_attr,split
 lines=['#EXTM3U']
 for u,r in db.items():
  h=set_attr(split(r['cabecera'])[0],'group-title',r['grupo']);lines.extend([h+','+r['nombre'],*r['opciones'],u])
 text,counts=merge(BASE.read_text(encoding='utf-8-sig'),[('\n'.join(lines),None)])
 tmp=BASE.with_suffix('.tmp');tmp.write_text(text);tmp.replace(BASE)
 print('Verificadas:',len(batch),'Registro:',len(db),'Paraguay:',counts['Paraguay'])
def discover(db):
 historical=R/'Catalogo_Paraguay_Respaldo.json'; known={(r['grupo'],norm(r['nombre'])) for r in db.values()}
 if historical.exists():known.update(('Paraguay',norm(r['nombre'])) for r in json.loads(historical.read_text()))
 sources=[(s,'Paraguay') for s in SOURCES[:2]]+ [('https://iptv-org.github.io/iptv/index.m3u',None)]
 rows=[];seen=set(db)
 for url,force in sources:
  try:
   with urllib.request.urlopen(url,timeout=30) as resp: raw=resp.read(30_000_000).decode('utf-8-sig','replace')
   for h,u,_ in parse(raw):
    g=group(h,force);n=name(h)
    if u in seen:continue
    if force or (g,norm(n)) in known:
     seen.add(u);rows.append([n,g,u,url,'REVISAR'])
  except Exception as e:print('Fuente no disponible:',url,type(e).__name__)
 with (R/'Candidatos_Individuales.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(['Canal','Grupo','URL','Fuente','Revision']);w.writerows(rows)
 print('Candidatos para revision:',len(rows))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('modo',choices=['guardar','verificar','buscar']);a=p.parse_args();db=load();absorb(db,BASE)
 if a.modo=='guardar':snapshot(db)
 elif a.modo=='verificar':maintain(db)
 else:discover(db)
