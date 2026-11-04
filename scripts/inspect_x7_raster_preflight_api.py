"""Retain preflight/link/ownership descriptors without an application connection."""
import json
from pathlib import Path
import pythoncom


def main():
    path = r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'
    library = pythoncom.LoadTypeLib(path)
    wanted = {'IVGBitmap': {'LinkFileName', 'OPILinked', 'IsEPS', 'ExternallyLinked', 'Embedded'},
        'IVGShape': {'ParentGroup', 'PowerClipParent', 'PowerClip', 'Shapes', 'Effects', 'Page', 'Layer'},
        'IVGPowerClip': {'Parent', 'Shapes'}, 'IVGPage': {'AllLayers', 'Layers'},
        'IVGLayer': {'Printable', 'Master', 'Page', 'Shapes'}}
    result = {'path': path, 'connection_attempted': False, 'members': []}; seen = set()
    for index in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(index); attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0)); attr = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if name in seen or name not in wanted: continue
        seen.add(name)
        for member in range(attr.cFuncs):
            descriptor = info.GetFuncDesc(member); names = info.GetNames(descriptor[0])
            if names[0] in wanted[name]:
                record = {'interface': name, 'names': names, 'invkind': descriptor[4],
                    'descriptor': repr(tuple(descriptor)), 'documentation': info.GetDocumentation(descriptor[0])[1]}
                if name == 'IVGShape' and names[0] == 'PowerClipParent':
                    record['return_interface'] = info.GetRefTypeInfo(descriptor[8][0][1][1]).GetDocumentation(-1)[0]
                result['members'].append(record)
    output = Path(__file__).resolve().parents[1] / 'docs/x7_raster_preflight_api_evidence.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Retained {len(result["members"])} raster preflight descriptors; no application connection.')


if __name__ == '__main__': main()
