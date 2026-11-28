from pathlib import Path
import re, json, csv, unicodedata, urllib.request, argparse
from collections import Counter
ROOT=Path(__file__).resolve().parent
ORDER=['Paraguay','Más popular','Desde Internet','Cine y series','Deportes','Full HD','HD+ (H.265)','Cultura','Infantil','Noticias','Música','Religioso','Vivo gratis','Entretenimiento','NFL Pass','MLB Pass','NBA Pass','Argentina','Bolivia','Brasil','Chile','Colombia','Ecuador','Perú','Uruguay','Venezuela','México','Estados Unidos','España','Costa Rica','Panamá','República Dominicana','Honduras','El Salvador','Puerto Rico','Centroamérica','Adultos (+18)']
MAP={'deportes':'Deportes','sports':'Deportes','espn+':'Deportes','peliculas':'Cine y series','entretenimiento':'Entretenimiento','documentales':'Cultura','infantiles':'Infantil','musica':'Música','religion':'Religioso','noticias':'Noticias','general':'Desde Internet','latinoamerica':'Desde Internet','latino':'Desde Internet','europa':'Desde Internet','-':'Desde Internet'}
SOURCES=['https://iptv-org.github.io/iptv/countries/py.m3u','https://www.m3u.cl/lista/PY.m3u','https://nexonic-technologies.github.io/nexonic-iptv/playlists/countries/py.m3u']
def norm(s): return ''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if not unicodedata.combining(c)).strip()
def attr(s,k):
 m=re.search(r'\b'+re.escape(k)+r'="([^"]*)"',s); return m.group(1) if m else ''
def split(s):
 quoted=False
 for i,c in enumerate(s):
  if c=='"': quoted=not quoted
  if c==',' and not quoted: return s[:i],s[i+1:].strip()
 return s,''
def parse(text):
 h=None; opts=[]
 for raw in text.splitlines():
  s=raw.strip()
  if s.startswith('#EXTINF:'): h=s; opts=[]
  elif h and s.startswith(('https://','http://')): yield h,s,opts; h=None; opts=[]
  elif h and s.startswith('#') and not s.startswith(('# PENDIENTE','#EXTGRP:')): opts.append(s)
def name(h): return re.sub(r'\s*\(alternativa \d+\)$','',re.sub(r'^\d+\s*-\s*','',attr(h,'tvg-name') or split(h)[1]),flags=re.I).strip()
def set_attr(h,k,v):
 v=v.replace('"',"'"); pat=r'\b'+re.escape(k)+r'="[^"]*"'
 return re.sub(pat,lambda _:k+'="'+v+'"',h) if re.search(pat,h) else h+' '+k+'="'+v+'"'
def group(h,force=None):
 if force:return force
 g=attr(h,'group-title'); n=norm(name(h)); k=norm(g)
 if g=='Paraguay':return g
 if g in ORDER:return g
 if re.search(r'\b(es[pt]n|espn|fox sports|tigo sports|tyc sports|dsports|tnt sports|bein sports)\b',n): return 'Deportes'
 if g in ORDER:return g
 if 'espa' in k:return 'España'
 return MAP.get(k,'Desde Internet')
def merge(base,extras):
 seen=set(); items=[]; pending=[l for l in base.splitlines() if l.startswith('# PENDIENTE')]; stats=Counter()
 for text,force in [(base,None)]+extras:
  for h,u,opts in parse(text):
   n=name(h); g=group(h,force)
   if norm(attr(h,'group-title'))=='fuentes online' or '(playlist)' in n.casefold(): stats['listas_anidadas']+=1; continue
   if u in seen:stats['duplicados']+=1; continue
   seen.add(u); items.append((g,n,h,u,opts))
 items.sort(key=lambda x:(ORDER.index(x[0]),norm(x[1]),x[3]))
 out=['#EXTM3U','# Catalogo Paraguay: consultar Catalogo_Paraguay_154.csv para registros historicos.']; counts=Counter(); names=Counter()
 for i,(g,n,h,u,opts) in enumerate(items,1):
  k=(g,norm(n)); names[k]+=1; label=n if names[k]==1 else f'{n} (alternativa {names[k]-1})'
  h=split(h)[0]; h=set_attr(h,'group-title',g); h=set_attr(h,'tvg-name',label); h=set_attr(h,'tvg-chno',str(i)); out.extend([f'{h},{i:03d} - {label}',*opts,u]); counts[g]+=1
 out.extend(pending); print('Grupos:',dict(counts),'Total:',len(seen),'Pendientes historicos:',len(pending),'Omitidos:',dict(stats))
 return '\n'.join(out)+'\n',counts
def buscar():
 base=(ROOT/'Paraguay.m3u').read_text(encoding='utf-8-sig'); existing={u for _,u,_ in parse(base)}; rows=[]; seen=set(existing)
 for src in SOURCES:
  try:
   with urllib.request.urlopen(urllib.request.Request(src,headers={'User-Agent':'Mi-IPTV-catalogo/1.0'}),timeout=25) as resp: raw=resp.read(5_000_000).decode('utf-8-sig','replace')
   for h,u,_ in parse(raw):
    if u not in seen:seen.add(u); rows.append([name(h),u,src,'PENDIENTE'])
   print('Fuente consultada:',src)
  except Exception as e:print('Fuente no disponible:',src,type(e).__name__)
 with (ROOT/'Candidatos_Paraguay_Nuevos.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f); w.writerow(['Canal','URL','Fuente','Revision']);w.writerows(rows)
 print('Candidatos nuevos:',len(rows),'No se publican automaticamente.')
def main():
 p=argparse.ArgumentParser();p.add_argument('--buscar',action='store_true');a=p.parse_args(); base=ROOT/'Paraguay.m3u'
 if a.buscar:buscar();return
 text=base.read_text(encoding='utf-8-sig'); extras=[]
 for filename,g in [('Paraguay_Alternativas_Aprobadas.m3u','Paraguay'),('Canales_Adicionales.m3u',None),('Enlaces_Aprobados.m3u',None)]:
  f=ROOT/filename
  if f.exists():extras.append((f.read_text(encoding='utf-8-sig'),g))
 new,_=merge(text,extras);tmp=base.with_suffix('.tmp');tmp.write_text(new,encoding='utf-8');tmp.replace(base)
if __name__=='__main__':main()
