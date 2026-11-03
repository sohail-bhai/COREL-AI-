"""Retain installed appearance/clipping descriptors; never access the application."""
import json
from pathlib import Path
import pythoncom


def main():
    path=r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'
    library=pythoncom.LoadTypeLib(path); seen=set()
    wanted={'IVGApplication':{'CreateRGBColor','CreateCMYKColor','ConvertUnits'},
            'IVGColor':None,'IVGFill':None,'IVGOutline':None,'IVGTransparency':None,
            'IVGShape':{'AddToPowerClip','PowerClip','Transparency','Fill','Outline'},'IVGPowerClip':None}
    evidence={'path':path,'connection_attempted':False,'members':[],'enums':{}}
    for i in range(library.GetTypeInfoCount()):
        info=library.GetTypeInfo(i); attr=info.GetTypeAttr()
        if attr.typekind==pythoncom.TKIND_COCLASS:
            info=info.GetRefTypeInfo(info.GetRefTypeOfImplType(0)); attr=info.GetTypeAttr()
        name=info.GetDocumentation(-1)[0]
        if name in seen: continue
        seen.add(name)
        if attr.typekind==pythoncom.TKIND_ENUM and name in ('cdrColorType','cdrFillType','cdrOutlineType','cdrTransparencyType','cdrMergeMode'):
            values={}
            for j in range(attr.cVars):
                descriptor=info.GetVarDesc(j); values[info.GetDocumentation(descriptor[0])[0]]=descriptor[1]
            evidence['enums'][name]=values
        if name not in wanted: continue
        for j in range(attr.cFuncs):
            descriptor=info.GetFuncDesc(j); names=info.GetNames(descriptor[0])
            if wanted[name] is None or names[0] in wanted[name]:
                evidence['members'].append({'interface':name,'names':names,'invkind':descriptor[4],
                    'descriptor':repr(tuple(descriptor)),'documentation':info.GetDocumentation(descriptor[0])[1]})
    output=Path(__file__).resolve().parents[1]/'docs/x7_appearance_api_evidence.json'
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(f'Retained {len(evidence["members"])} appearance descriptors and {len(evidence["enums"])} enums; no application connection.')


if __name__=='__main__': main()
