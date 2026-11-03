"""Inspect installed page/layer descriptors without connecting to CorelDRAW."""
import json
from pathlib import Path

import pythoncom


def main():
    path = r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'
    library = pythoncom.LoadTypeLib(path)
    wanted = {
        'IVGDocument': {'Pages', 'ActivePage', 'MasterPage', 'AddPages', 'InsertPages', 'BeginCommandGroup', 'EndCommandGroup'},
        'IVGPage': {'Name', 'Index', 'SizeWidth', 'SizeHeight', 'Layers', 'AllLayers', 'ActiveLayer', 'Activate', 'CreateLayer', 'Delete', 'MoveTo', 'SetSize'},
        'IVGLayer': {'Name', 'Index', 'AbsoluteIndex', 'Page', 'Visible', 'Editable', 'Printable', 'Master', 'IsSpecialLayer', 'Shapes', 'Activate', 'Delete'},
        'IVGShape': {'MoveToLayer', 'Layer', 'Page'},
        'IVGPages': {'Count', 'Item'}, 'IVGLayers': {'Count', 'Item'},
    }
    seen = set()
    evidence = {'path': path, 'connection_attempted': False, 'members': []}
    for i in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(i)
        attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0))
            attr = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if name in seen or name not in wanted:
            continue
        seen.add(name)
        for j in range(attr.cFuncs):
            descriptor = info.GetFuncDesc(j)
            names = info.GetNames(descriptor[0])
            if names[0] in wanted[name]:
                evidence['members'].append({'interface': name, 'names': names, 'invkind': descriptor[4],
                    'descriptor': repr(tuple(descriptor)), 'documentation': info.GetDocumentation(descriptor[0])[1]})
    output = Path(__file__).resolve().parents[1] / 'docs/x7_organization_api_evidence.json'
    output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(f'Retained {len(evidence["members"])} organization descriptors; no application connection.')


if __name__ == '__main__':
    main()
