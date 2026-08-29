# -*- coding: utf-8 -*-
# regenera data.json a partir da base e monta painel + index
from openpyxl import load_workbook
import json
COLETA="2026-08-29 11:20"; HOJE="2026-08-29"
wb=load_workbook("base_atual.xlsx", data_only=True)
ws=wb["Posts"]
posts=[]
for r in range(2, ws.max_row+1):
    a=ws.cell(row=r,column=1).value
    if not a: continue
    posts.append({"a":a,"p":ws.cell(row=r,column=2).value,
        "d":str(ws.cell(row=r,column=3).value)[:10],"h":str(ws.cell(row=r,column=4).value)[:5],
        "t":ws.cell(row=r,column=5).value,"id":ws.cell(row=r,column=6).value,
        "ti":ws.cell(row=r,column=7).value or "","u":ws.cell(row=r,column=8).value or "",
        "v":ws.cell(row=r,column=9).value or 0,"l":ws.cell(row=r,column=10).value or 0,
        "c":ws.cell(row=r,column=11).value or 0,
        "cb":1 if ws.cell(row=r,column=12).value=="Sim" else 0,
        "fx":1 if ws.cell(row=r,column=13).value=="Sim" else 0})
ws=wb["Contadores"]
# ultimo snapshot por (artista, plataforma, handle)
snap={}
for r in range(2, ws.max_row+1):
    d=str(ws.cell(row=r,column=1).value)[:10]
    if not d or d=="None": continue
    k=(ws.cell(row=r,column=2).value,ws.cell(row=r,column=3).value,ws.cell(row=r,column=4).value)
    if k not in snap or d>=snap[k][0]:
        snap[k]=(d,ws.cell(row=r,column=5).value,ws.cell(row=r,column=6).value,ws.cell(row=r,column=7).value)
cont=[{"a":k[0],"p":k[1],"h":k[2],"seg":v[1],"tot":v[2],"lk":v[3]} for k,v in snap.items() if v[1]]
data=json.dumps({"coleta":COLETA,"posts":posts,"contadores":cont},ensure_ascii=False)
tpl=open("painel_template.html").read()
html=tpl.replace("__DATA__",data)
import re
html=re.sub(r'const HOJE = "[0-9-]+";', f'const HOJE = "{HOJE}";', html)
open("painel_casa_saturno.html","w").write(html)
open("index.html","w").write(html)
print("posts:",len(posts),"| contadores:",len(cont),"| bytes:",len(html))
