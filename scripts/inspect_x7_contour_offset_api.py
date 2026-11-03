"""Retain installed native contour descriptors without application access."""
import json
from pathlib import Path

import pythoncom


def main():
    path = r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'
    library = pythoncom.LoadTypeLib(path)
    wanted = {
        'IVGShape': {'CreateContour', 'Effects', 'Ungroup', 'UngroupAll', 'ConvertToCurves', 'Type'},
        'IVGEffect': {'Type', 'Contour', 'Separate', 'Delete'}, 'IVGEffectContour': None,
        'IVGEffects': {'Count', 'Item'},
    }
    enum_names = {'cdrContourDirection', 'cdrContourEndCapType', 'cdrContourCornerType', 'cdrEffectType', 'cdrShapeType'}
    seen = set()
    evidence = {'path': path, 'connection_attempted': False, 'members': [], 'enums': {}}
    for i in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(i)
        attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0))
            attr = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if name in seen:
            continue
        seen.add(name)
        if attr.typekind == pythoncom.TKIND_ENUM and name in enum_names:
            values = {}
            for j in range(attr.cVars):
                descriptor = info.GetVarDesc(j)
                values[info.GetDocumentation(descriptor[0])[0]] = descriptor[1]
            evidence['enums'][name] = values
        if name not in wanted:
            continue
        for j in range(attr.cFuncs):
            descriptor = info.GetFuncDesc(j)
            names = info.GetNames(descriptor[0])
            if wanted[name] is None or names[0] in wanted[name]:
                evidence['members'].append({'interface': name, 'names': names, 'invkind': descriptor[4],
                                             'descriptor': repr(tuple(descriptor)),
                                             'documentation': info.GetDocumentation(descriptor[0])[1]})
    output = Path(__file__).resolve().parents[1] / 'docs/x7_contour_offset_api_evidence.json'
    output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(f'Retained {len(evidence["members"])} contour descriptors and {len(evidence["enums"])} enum groups; no application connection.')


if __name__ == '__main__':
    main()
