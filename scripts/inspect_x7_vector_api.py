"""Retain native X7 vector/node/shaping signatures without application access."""
import json
from pathlib import Path
import pythoncom


def main():
    path=r"C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb"
    library=pythoncom.LoadTypeLib(path)
    wanted={
        'IVGApplication':{'CreateCurve','CreateShapeRange'},
        'IVGLayer':{'CreateCurve','CreateLineSegment'},
        'IVGShape':{'Curve','DisplayCurve','ConvertToCurves','Combine','BreakApartEx','Weld','Trim','Intersect','Delete','Duplicate','Layer','Page'},
        'IVGCurve':None,'IVGSubPath':None,'IVGNode':None,'IVGSegment':None,
        'IVGShapeRange':{'Add','Combine','BreakApartEx','Count','Item','Delete'},
    }
    evidence={'path':path,'connection_attempted':False,'members':[],'enums':{}}; seen=set()
    for index in range(library.GetTypeInfoCount()):
        info=library.GetTypeInfo(index); attr=info.GetTypeAttr()
        if attr.typekind==pythoncom.TKIND_COCLASS:
            info=info.GetRefTypeInfo(info.GetRefTypeOfImplType(0)); attr=info.GetTypeAttr()
        name=info.GetDocumentation(-1)[0]
        if name in seen: continue
        seen.add(name)
        if attr.typekind==pythoncom.TKIND_ENUM and name in ('cdrShapeType','cdrSegmentType','cdrNodeType'):
            values={}
            for variable_index in range(attr.cVars):
                desc=info.GetVarDesc(variable_index); values[info.GetDocumentation(desc[0])[0]]=desc[1]
            evidence['enums'][name]=values
        if name not in wanted: continue
        for function_index in range(attr.cFuncs):
            desc=info.GetFuncDesc(function_index); names=info.GetNames(desc[0])
            if wanted[name] is None or names[0] in wanted[name]:
                evidence['members'].append({'interface':name,'names':names,'invkind':desc[4],
                    'descriptor':repr(tuple(desc)),'documentation':info.GetDocumentation(desc[0])[1]})
    output=Path(__file__).resolve().parents[1]/'docs/x7_vector_api_evidence.json'
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(f"Retained {len(evidence['members'])} vector descriptors and {len(evidence['enums'])} enums; no application connection.")


if __name__=='__main__': main()
