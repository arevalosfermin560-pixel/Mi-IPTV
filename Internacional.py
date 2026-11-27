"""Selección de señales públicas internacionales; no retransmite ni elude accesos."""
import json,re,unicodedata,urllib.request,urllib.parse,ipaddress,os
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'Internacional.json'
BASE='https://nexonic-technologies.github.io/nexonic-iptv/playlists/'
RAW='https://raw.githubusercontent.com/nexonic-technologies/nexonic-iptv/main/playlists/'
LIMIT=1000
COUNTRIES=dict(zip('AR BR UY BO CL PE CO EC VE MX US CA ES PY CR PA DO HN GT SV NI PR CU HT JM BZ GY SR GB FR DE IT PT NL JP KR IN AU NZ'.split(),'Argentina|Brasil|Uruguay|Bolivia|Chile|Perú|Colombia|Ecuador|Venezuela|México|Estados Unidos|Canadá|España|Paraguay|Costa Rica|Panamá|República Dominicana|Honduras|Guatemala|El Salvador|Nicaragua|Puerto Rico|Cuba|Haití|Jamaica|Belice|Guyana|Surinam|Reino Unido|Francia|Alemania|Italia|Portugal|Países Bajos|Japón|Corea del Sur|India|Australia|Nueva Zelanda'.split('|')))
THEMES={'sports':'Deportes','movies':'Cine y series','series':'Cine y series','news':'Noticias','documentary':'Cultura','culture':'Cultura','education':'Cultura','science':'Cultura','music':'Música','kids':'Infantil','religious':'Religioso','entertainment':'Entretenimiento','lifestyle':'Entretenimiento'}
ORDER=['Deportes','Cine y series','Noticias','Cultura','Infantil','Música','Religioso','Entretenimiento']+list(COUNTRIES.values())
# Objetivos orientativos; el resto se reparte por grupo, sin duplicar canales.
QUOTAS={'Deportes':65,'Cine y series':85,'Noticias':50,'Cultura':45,'Infantil':25,'Música':30,'Religioso':15,'Entretenimiento':35,'Argentina':65,'Brasil':65,'México':70,'Estados Unidos':70,'España':50,'Colombia':45,'Chile':40,'Perú':35,'Ecuador':30,'Bolivia':25,'Uruguay':20,'Venezuela':20,'Canadá':20}
def norm(s): return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
def safe(s): return str(s).replace('"',"'").replace('\r',' ').replace('\n',' ').strip()
def url_ok(u):
    try:
        p=urllib.parse.urlsplit(u)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or any(c.isspace() for c in u): return False
        try: ipaddress.ip_address(p.hostname); return False # evita servidores IP de origen incierto en la importación internacional
        except ValueError: pass
        return '.' in p.hostname and not p.hostname.endswith(('.local','.internal','.localhost'))
    except ValueError: return False
def parse(text):
    entries=[]; meta=None
    for line in text.splitlines():
        line=line.strip()
        if line.startswith('#EXTINF:'):
            # La coma delimitadora está fuera de los atributos entre comillas.
            pieces=re.split(r',(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)',line,maxsplit=1)
            a=dict(re.findall(r'([\w-]+)="([^"\r\n]*)"',pieces[0])); name=a.get('tvg-name') or (pieces[1] if len(pieces)>1 else '')
            meta={'name':safe(name),'id':safe(a.get('tvg-id','')),'country':safe(a.get('tvg-country','')).upper(),'group':safe(a.get('group-title','')),'logo':safe(a.get('tvg-logo','')),'language':safe(a.get('tvg-language',''))}
        elif not line.startswith('#') and line:
            if meta and meta['name'] and url_ok(line): entries.append(dict(meta,url=line))
            meta=None
    return entries
def country(e):
    c=re.split(r'[,; ]',e['country'])[0]
    if len(c)==2: return c
    m=re.search(r'\.([a-z]{2})(?:@.*)?$',e['id'],re.I)
    return m.group(1).upper() if m else ''
def group(e,cat):
    tags=re.split(r'[;,|/]',cat.get(e['id'], '')+';'+e['group'])
    for t in tags:
        if t.strip().lower() in THEMES: return THEMES[t.strip().lower()]
    c=country(e)
    return COUNTRIES.get(c,c or 'Otros países')
def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mi-IPTV/2.0'}),timeout=25) as r:
        data=r.read(12_000_001)
    if len(data)>12_000_000: raise ValueError('lista demasiado grande')
    text=data.decode('utf-8-sig','replace')
    if not text.startswith('#EXTM3U'): raise ValueError('no es M3U')
    return text
def select(entries,cat,preferred=()):
    bins=defaultdict(list); ids=set(); urls=set(); prefs=set(preferred)
    def rank(e):
        c=country(e); return (norm(e['name']) not in prefs,c not in COUNTRIES,not e['url'].startswith('https:'),e['name'].casefold(),e['url'])
    for e in sorted(entries,key=rank):
        if country(e)=='PY' or e['group'].casefold()=='paraguay': continue
        key=(country(e),norm(e['name']))
        if key in ids or e['url'] in urls: continue
        ids.add(key); urls.add(e['url']); g=group(e,cat); bins[g].append(dict(e,group=g))
    out=[]; groups=sorted(bins,key=lambda g:(ORDER.index(g) if g in ORDER else len(ORDER),g))
    for g in groups:
        n=min(QUOTAS.get(g,5),len(bins[g]),LIMIT-len(out)); out+=bins[g][:n]; bins[g]=bins[g][n:]
    while len(out)<LIMIT and any(bins.values()):
        for g in groups:
            if bins[g] and len(out)<LIMIT: out.append(bins[g].pop(0))
    return sorted(out,key=lambda e:(ORDER.index(e['group']) if e['group'] in ORDER else len(ORDER),e['group'],e['name'].casefold()))
def refresh():
    entries=[]
    for base in (BASE,RAW):
        try:
            entries=parse(fetch(base+'verified.m3u'))
            if len(entries)>=100: break
        except Exception as ex: print('Fuente internacional:',type(ex).__name__)
    if len(entries)<100: print('Se conserva el catálogo internacional anterior'); return
    cat={}
    try:
        cat={e['id']:e['group'] for e in parse(fetch('https://iptv-org.github.io/iptv/index.category.m3u')) if e['id']}
    except Exception: print('Sin metadatos complementarios; se usan grupos de la fuente')
    pref=ROOT/'Preferencias_Xuper.json'
    preferred=json.loads(pref.read_text()) if pref.exists() else []
    selected=select(entries,cat,preferred)
    old=load()
    if len(selected)<min(800,len(old)*0.8): print('Reducción anormal; se conserva lista anterior'); return
    CACHE.write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Internacional:',len(selected),dict(Counter(e['group'] for e in selected)))
def load(): return json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else []
def append(text):
    lines=[text.rstrip()]; seen=set(x.strip() for x in text.splitlines() if x.startswith(('http://','https://')))
    n=154
    for e in load():
        if not url_ok(e['url']) or e['url'] in seen or country(e)=='PY': continue
        seen.add(e['url']); n+=1; name=safe(e['name']); groupname=safe(e['group']); logo=safe(e['logo']); ident=safe(e['id']); c=safe(country(e))
        lines += [f'#EXTINF:-1 tvg-id="{ident}" tvg-name="{name}" tvg-logo="{logo}" tvg-country="{c}" tvg-chno="{n}" group-title="{groupname}",{n:03d} - {name}',e['url']]
    return '\n'.join(lines)+'\n'
