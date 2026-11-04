"""Retain bounded primary Corel preflight and linked-raster references."""
import datetime
import html
import json
import re
import urllib.request
from pathlib import Path


def main():
    sources = [('https://help.coreldraw.com/CorelDRAW/540111192/Documentation-Windows/CorelDRAW-en/CorelDRAW-PDF-preflight-summaries.html', 'preflight'),
        ('https://community.coreldraw.com/sdk/api/draw/17/p/bitmap.linkfilename', 'linked'),
        ('https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Changing-the-dimensions-and-resolution-of-bitmaps.html', 'resolution')]
    records = []
    for url, needle in sources:
        record = {'url': url, 'accessed': datetime.date.today().isoformat()}
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'CorelAI-CapabilityResearch/1.0'})
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read(2_000_000).decode('utf-8', errors='replace')
                record.update(status=response.status, resolved_url=response.geturl())
            raw = re.sub(r'<(script|style)\b.*?</\1>', '', raw, flags=re.S | re.I)
            content = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', raw)))
            indices = [match.start() for match in re.finditer(re.escape(needle), content, re.I)]
            record['excerpts'] = [content[max(0, i-100):i+850] for i in indices[:4]]
            record['relevant_text_found'] = bool(indices)
        except Exception as exc: record['error_type'] = type(exc).__name__
        records.append(record)
        print(url.rsplit('/', 1)[-1], record.get('status', record.get('error_type')), record.get('relevant_text_found', False))
    output = Path(__file__).resolve().parents[1] / 'docs/raster_preflight_online_evidence.json'
    output.write_text(json.dumps({'browser_used': False, 'sources': records}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__': main()
