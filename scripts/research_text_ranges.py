"""Inspect installed X7 text ranges/fitting, with bounded primary-source research."""
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import urllib.request

import pythoncom

ROOT = Path(__file__).resolve().parents[1]
TYPELIB = r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'


def referenced_types(info, value):
    if not isinstance(value, tuple):
        return []
    if len(value) >= 2 and value[0] == pythoncom.VT_USERDEFINED:
        return [info.GetRefTypeInfo(value[1]).GetDocumentation(-1)[0]]
    return [name for child in value for name in referenced_types(info, child)]


def main():
    library = pythoncom.LoadTypeLib(TYPELIB)
    evidence = {'application_connected': False, 'browser_used': False,
                'typelib_path': TYPELIB, 'members': [], 'sources': []}
    visited = set()
    for index in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(index)
        attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0))
            attr = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if name in visited or not name.startswith('IVGText') or name.startswith('IVGTexture'):
            continue
        visited.add(name)
        for i in range(attr.cFuncs):
            desc = info.GetFuncDesc(i)
            names = info.GetNames(desc[0])
            if desc[0] >= 1610743800 or desc[0] == 0:
                evidence['members'].append({'interface': name, 'names': names, 'invkind': desc[4],
                    'descriptor': repr(tuple(desc)), 'documentation': info.GetDocumentation(desc[0])[1],
                    'return_referenced_types': referenced_types(info, desc[8][0])})
    urls = [
        ('https://community.coreldraw.com/sdk/api/draw/17/m/textrange.range', 'Range'),
        ('https://community.coreldraw.com/sdk/api/draw/17/p/textrange.characters', 'Characters'),
        ('https://community.coreldraw.com/sdk/api/draw/17/m/text.fittexttoframe', 'FitTextToFrame'),
        ('https://community.coreldraw.com/sdk/api/draw/17/p/textcharacters.item', 'Item'),
        ('https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Fitting-text-to-the-paragraph-text-frame.html', 'fit'),
        ('https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Fitting-text-to-a-frame.html', 'fit'),
        ('https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Adding-paragraph-text.html', 'fit'),
    ]
    for url, needle in urls:
        record = {'url': url, 'accessed_utc': datetime.now(timezone.utc).isoformat()}
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'CorelOperator-Research/1.0'})
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read(1_000_001)
                record.update(status=response.status, final_url=response.url, response_truncated=len(raw) > 1_000_000)
            content = raw[:1_000_000].decode('utf-8', errors='replace')
            content = re.sub(r'<(script|style)\b.*?</\1>', '', content, flags=re.S | re.I)
            content = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', content)))
            matches = list(re.finditer(re.escape(needle), content, re.I))
            record['excerpts'] = [content[max(0, m.start()-100):m.start()+800] for m in matches[:5]]
            record['member_text_found'] = bool(matches)
        except Exception as exc:
            record['error_type'] = type(exc).__name__
        evidence['sources'].append(record)
        print(url.rsplit('/', 1)[-1], record.get('status', record.get('error_type')), record.get('member_text_found', False))
    (ROOT / 'docs/x7_text_range_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    for member in evidence['members']:
        if member['interface'] == 'IVGTextFrame' or member['names'][0] in ('FitTextToFrame', 'Range', 'Characters', 'Overflow'):
            print(member['interface'], member['names'], member['documentation'], member['return_referenced_types'])


if __name__ == '__main__':
    main()
