"""Retain installed bitmap inspection descriptors without application access."""
import json
from pathlib import Path

import pythoncom


def main():
    path = r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'
    library = pythoncom.LoadTypeLib(path)
    wanted = {
        'IVGBitmap': {'SizeWidth', 'SizeHeight', 'ResolutionX', 'ResolutionY', 'Mode',
            'ExternallyLinked', 'Embedded', 'Cropped', 'CropEnvelopeModified', 'CropEnvelope', 'BoundingBoxPath'},
        'IVGShape': {'Bitmap', 'GetMatrix', 'DisplayCurve', 'SizeWidth', 'SizeHeight', 'PowerClip', 'Effects'},
        'IVGCurve': {'Nodes', 'Segments', 'SubPaths', 'GetBoundingBox'},
        'IVGNode': {'PositionX', 'PositionY'}, 'IVGSegment': {'Type', 'StartNode', 'EndNode'},
    }
    seen = set(); result = {'path': path, 'connection_attempted': False, 'members': []}
    for i in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(i); attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0)); attr = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if name in seen or name not in wanted:
            continue
        seen.add(name)
        for j in range(attr.cFuncs):
            descriptor = info.GetFuncDesc(j); names = info.GetNames(descriptor[0])
            if names[0] in wanted[name]:
                result['members'].append({'interface': name, 'names': names, 'invkind': descriptor[4],
                    'descriptor': repr(tuple(descriptor)), 'documentation': info.GetDocumentation(descriptor[0])[1]})
    output = Path(__file__).resolve().parents[1] / 'docs/x7_bitmap_api_evidence.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Retained {len(result["members"])} bitmap inspection descriptors; no application connection.')


if __name__ == '__main__': main()
