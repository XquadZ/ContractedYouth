# -*- coding: utf-8 -*-
import os, re, json, time, urllib.parse, urllib.request, winreg
from pathlib import Path

def oc():
    v=os.environ.get('LAW_OC','').strip()
    if v: return v
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Environment') as k:
        v,_=winreg.QueryValueEx(k,'LAW_OC'); return str(v).strip()

def get(base, params):
    q=urllib.parse.urlencode(params)
    req=urllib.request.Request(f'{base}?{q}', headers={'User-Agent':'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw=r.read()
        for enc in ('utf-8','euc-kr','cp949'):
            try: t=raw.decode(enc); break
            except: t=raw.decode('utf-8','replace')
        time.sleep(0.55)
        return t
    except Exception as e:
        return f'ERR:{e!r}'

def classify(t):
    if t.startswith('ERR:'): return 'err', t[:200]
    if '<html' in t[:200].lower() or '<!DOCTYPE' in t[:50]:
        text=re.sub(r'<[^>]+>',' ',t)
        text=re.sub(r'\s+',' ',text).strip()
        return 'html', text[:300]
    try:
        j=json.loads(t)
        return 'json', list(j.keys())[:8]
    except:
        if t.strip().startswith('<'):
            return 'xml', t[:120]
        return 'other', t[:120]

OC=oc()
SEARCH='http://www.law.go.kr/DRF/lawSearch.do'
SERVICE='http://www.law.go.kr/DRF/lawService.do'
tests=[
 ('expc JSON', SEARCH, {'OC':OC,'target':'expc','type':'JSON','query':'근로계약','display':5}),
 ('expc XML', SEARCH, {'OC':OC,'target':'expc','type':'XML','query':'근로계약','display':5}),
 ('ftc XML', SEARCH, {'OC':OC,'target':'ftc','type':'XML','query':'임대차','display':5}),
 ('ftc JSON', SEARCH, {'OC':OC,'target':'ftc','type':'JSON','query':'임대차','display':5}),
 ('lstrm JSON q=근로', SEARCH, {'OC':OC,'target':'lstrm','type':'JSON','query':'근로','display':5}),
 ('lstrm XML', SEARCH, {'OC':OC,'target':'lstrm','type':'XML','query':'근로','display':5}),
 ('lawhist?', SEARCH, {'OC':OC,'target':'lawhist','type':'JSON','query':'근로기준법','display':5}),
 ('lsHst', SEARCH, {'OC':OC,'target':'lsHst','type':'JSON','query':'근로기준법','display':5}),
 ('eflaw', SEARCH, {'OC':OC,'target':'eflaw','type':'JSON','query':'근로기준법','display':5}),
 ('elaw', SEARCH, {'OC':OC,'target':'elaw','type':'JSON','query':'근로기준법','display':5}),
 ('law efYd', SEARCH, {'OC':OC,'target':'law','type':'JSON','query':'근로기준법','efYd':'20220101~20301231','display':5}),
]
# ministry targets guess from open API
for tgt in ['moel','molit','moj','moleg','els','drf','expc']:
    tests.append((f'{tgt}', SEARCH, {'OC':OC,'target':tgt,'type':'JSON','query':'근로','display':3}))

out=[]
for name,base,params in tests:
    t=get(base, params)
    kind,info=classify(t)
    out.append({'name':name,'kind':kind,'info':info if not isinstance(info,str) else info})
    print(name, kind, info if isinstance(info,(list,tuple)) else str(info)[:200])

Path(r'C:\Users\DMLAB\Desktop\학부-AI서비스 개발\data_contract\api_probe.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
