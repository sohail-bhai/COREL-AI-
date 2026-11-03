"""Retain primary clipping API access results via bounded foreground HTTP requests."""
import datetime
import html
import json
import re
import urllib.request
from pathlib import Path


def main():
    records=[]
    for url in [
        'https://community.coreldraw.com/sdk/api/draw/17/m/shape.addtopowerclip?lang=cli',
        'https://community.coreldraw.com/sdk/api/draw/17/p/shape.powerclip?lang=cli',
        'https://community.coreldraw.com/sdk/api/draw/17/m/powerclip.extractshapes?lang=cli',
    ]:
        record={'url':url,'accessed':datetime.date.today().isoformat()}
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'CorelAI-CapabilityResearch/1.0'})
            with urllib.request.urlopen(request,timeout=20) as response:
                raw=response.read(2_000_000).decode('utf-8',errors='replace')
                record.update(status=response.status,resolved_url=response.geturl())
            raw=re.sub(r'<(script|style)\b.*?</\1>','',raw,flags=re.S|re.I)
            content=html.unescape(re.sub(r'<[^>]+>',' ',raw)); content=re.sub(r'\s+',' ',content)
            needle=url.rsplit('/',1)[-1].split('?')[0].split('.')[-1]
            indices=[m.start() for m in re.finditer(re.escape(needle),content,re.I)]
            record['excerpts']=[content[max(0,i-100):i+850] for i in indices[:5]]
            record['api_name_found']=bool(indices)
        except Exception as exc: record['error_type']=type(exc).__name__
        records.append(record)
        print(url.rsplit('/',1)[-1],record.get('status',record.get('error_type')),record.get('api_name_found',False))
    path=Path(__file__).resolve().parents[1]/'docs/powerclip_online_evidence.json'
    path.write_text(json.dumps({'browser_used':False,'sources':records},indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
