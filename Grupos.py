"""Normalización final de grupos; no modifica enlaces ni catálogo paraguayo."""
from pathlib import Path
import re
from collections import Counter

ALLOWED = {'Paraguay','Más popular','Desde Internet','Cine y series','Deportes','Full HD','HD+ (H.265)','Cultura','Infantil','Noticias','Música','Religioso','Vivo gratis','NFL Pass','MLB Pass','NBA Pass','Argentina','Brasil','Bolivia','Chile','Colombia','Ecuador','Perú','Uruguay','Venezuela','México','Estados Unidos','España','Costa Rica','Panamá','República Dominicana','Honduras','El Salvador','Puerto Rico','Centroamérica'}
MAP = {'PY':'Paraguay','AR':'Argentina','BR':'Brasil','BO':'Bolivia','CL':'Chile','CO':'Colombia','EC':'Ecuador','PE':'Perú','UY':'Uruguay','VE':'Venezuela','MX':'México','US':'Estados Unidos','ES':'España','CR':'Costa Rica','PA':'Panamá','DO':'República Dominicana','HN':'Honduras','SV':'El Salvador','PR':'Puerto Rico','GT':'Centroamérica','NI':'Centroamérica','BZ':'Centroamérica','Guatemala':'Centroamérica','Nicaragua':'Centroamérica','Belice':'Centroamérica'}
def normalize(group):
    group=MAP.get(group,group)
    return group if group in ALLOWED else 'Desde Internet'
def fix(text):
    counts=Counter()
    def linefix(line):
        if not line.startswith('#EXTINF:'): return line
        m=re.search(r'group-title="([^"]*)"',line)
        if not m: raise ValueError('Entrada sin group-title')
        g=normalize(m.group(1)); counts[g]+=1
        return line[:m.start(1)]+g+line[m.end(1):]
    result='\n'.join(linefix(l) for l in text.splitlines())+'\n'
    assert set(counts)<=ALLOWED
    print('Grupos:',len(counts),'Entradas:',sum(counts.values()),dict(counts))
    return result
if __name__=='__main__':
    p=Path(__file__).resolve().parent/'Paraguay.m3u'
    old=p.read_text(encoding='utf-8-sig'); new=fix(old)
    if old!=new: p.write_text(new,encoding='utf-8')
