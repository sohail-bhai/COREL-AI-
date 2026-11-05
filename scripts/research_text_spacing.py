"""Retain X7 spacing evidence without application or browser access."""
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import urllib.request

import pythoncom

ROOT = Path(__file__).resolve().parents[1]
TYPELIB = r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'
MEMBERS = {'CharSpacing', 'WordSpacing', 'LineSpacing', 'LineSpacingType'}


def main():
    evidence = {'typelib_path': TYPELIB, 'application_connected': False,
                'browser_used': False, 'members': [], 'enums': {}, 'sources': []}
    library = pythoncom.LoadTypeLib(TYPELIB)
    visited = set()
    for index in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(index)
        attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0))
            attr = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if name in visited:
            continue
        visited.add(name)
        if name == 'IVGTextRange':
            for member in range(attr.cFuncs):
                desc = info.GetFuncDesc(member)
                names = info.GetNames(desc[0])
                if 'Spacing' in names[0]:
                    evidence['members'].append({'interface': name, 'names': names,
                        'invkind': desc[4], 'descriptor': repr(tuple(desc)),
                        'documentation': info.GetDocumentation(desc[0])[1]})
        if attr.typekind == pythoncom.TKIND_ENUM and 'spac' in name.lower():
            evidence['enums'][name] = {info.GetNames(info.GetVarDesc(i)[0])[0]:
                                      info.GetVarDesc(i)[1] for i in range(attr.cVars)}
    sources = [('https://community.coreldraw.com/sdk/api/draw/17/p/textrange.' + member.lower(), member)
               for member in sorted(MEMBERS)]
    sources.extend([
        ('https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Adjusting-character-and-word-spacing.html', 'spacing'),
        ('https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Adjusting-character-spacing-and-word-spacing.html', 'spacing'),
        ('https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Adjusting-line-and-paragraph-spacing.html', 'spacing'),
    ])
    for url, member in sources:
        record = {'url': url, 'accessed_utc': datetime.now(timezone.utc).isoformat()}
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'CorelOperator-Research/1.0'})
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read(1_000_001)
                record.update(status=response.status, final_url=response.url,
                              response_truncated=len(raw) > 1_000_000)
            content = raw[:1_000_000].decode('utf-8', errors='replace')
            record['related_spacing_links'] = re.findall(r'href=[\"\x27]([^\"\x27]*[Ss]pacing[^\"\x27]*)', content)[:20]
            content = re.sub(r'<(script|style)\b.*?</\1>', '', content, flags=re.S | re.I)
            content = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', content)))
            matches = list(re.finditer(re.escape(member), content, re.I))
            unit_matches = list(re.finditer(r'percent|point|character height|space character', content, re.I))
            record['excerpts'] = [content[max(0, m.start()-100):m.start()+600] for m in (matches[:2] + unit_matches[:8])]
            record['member_text_found'] = bool(matches)
        except Exception as exc:
            record['error_type'] = type(exc).__name__
        evidence['sources'].append(record)
        print(member, record.get('status', record.get('error_type')), record.get('member_text_found', False))
    path = ROOT / 'docs/x7_text_spacing_evidence.json'
    path.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    for entry in evidence['members']:
        if entry['invkind'] in (pythoncom.INVOKE_PROPERTYGET, pythoncom.INVOKE_FUNC):
            print(entry['names'][0] + ': ' + str(entry['documentation']))
    print(evidence['enums'])


if __name__ == '__main__':
    main()
