"""Retain bounded primary prepress evidence, without Corel or browser access."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URLS = [
    'https://community.coreldraw.com/sdk/api/draw/17.4/p/pdfvbasettings.bleed',
    'https://community.coreldraw.com/sdk/api/draw/17.4/p/pdfvbasettings.cropmarks',
    'https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Specifying-prepress-settings-for-PDF-files.html',
    'https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Specifying-prepress-options-for-PDF-files.html',
    'https://help.coreldraw.com/CorelDRAW/540111192/Documentation-Windows/CorelDRAW-en/CorelDRAW-PDF-preflight-summaries.html',
    'https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf',
]


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(' '.join(data.split()))


def main():
    records = []
    for url in URLS:
        record = {'url': url, 'accessed_utc': datetime.now(timezone.utc).isoformat()}
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'CorelOperator-DocumentationResearch/1.0'})
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                record.update(status=response.status, final_url=response.url,
                              content_type=response.headers.get('Content-Type', ''), bytes_read=len(raw))
            if raw.startswith(b'%PDF-'):
                record['readable_html'] = False
                record['note'] = 'PDF reference only; bounded download not retained or parsed.'
            else:
                parser = PlainText()
                parser.feed(raw.decode('utf-8', errors='replace'))
                text = '\n'.join(parser.parts)
                record.update(readable_html=len(text) > 200, excerpt=text[:24000])
        except (OSError, urllib.error.URLError) as exc:
            record.update(readable_html=False, error=str(exc)[:500])
        records.append(record)
        # Ordinary file checkpoint after every sequential request.
        output = ROOT / 'docs/pdf_prepress_online_evidence.json'
        output.write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
        print(f"{record.get('status', 'unavailable')} readable={record['readable_html']} {url}", flush=True)


if __name__ == '__main__':
    main()
