"""Retain installed indexing descriptors without connecting to CorelDRAW."""
import json
from pathlib import Path

import pythoncom

ROOT = Path(__file__).resolve().parents[1]
TYPELIB = r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'


def main():
    library = pythoncom.LoadTypeLib(TYPELIB)
    evidence = dict(typelib_path=TYPELIB, application_connected=False,
                    browser_used=False, members=[], enums={})
    seen = set()
    for index in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(index)
        attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0))
            attr = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if name in seen:
            continue
        seen.add(name)
        if name == 'cdrTextIndexingType':
            evidence['enums'][name] = {info.GetNames(info.GetVarDesc(i)[0])[0]:
                                      info.GetVarDesc(i)[1] for i in range(attr.cVars)}
        if name not in ('IVGText', 'IVGTextRange', 'IVGTextCharacters'):
            continue
        for member in range(attr.cFuncs):
            desc = info.GetFuncDesc(member)
            names = info.GetNames(desc[0])
            if names[0] in ('Range', 'Characters', 'Count', 'Item', 'Text', 'Start', 'End',
                             'IndexingType', 'Selection', 'Selected', 'CharSpacing', 'WordSpacing'):
                record = dict(interface=name, names=names, descriptor=repr(tuple(desc)),
                              invkind=desc[4], documentation=info.GetDocumentation(desc[0])[1])
                evidence['members'].append(record)
                print(name, names, record['documentation'])
    evidence['unicode_conclusion'] = (
        'Descriptors do not prove UTF-16/code-point/grapheme indexing. Enumerate '
        'Characters.Item(i,1), concatenate exact native Text, and derive boundaries '
        'from readback per story. Refuse ambiguous, partial or changed mappings.')
    evidence['native_verification'] = 'not_run'
    (ROOT / 'docs/x7_selected_text_evidence.json').write_text(
        json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(evidence['enums'])


if __name__ == '__main__':
    main()
