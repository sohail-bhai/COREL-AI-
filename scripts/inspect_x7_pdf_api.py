"""Retain X7 PDF signatures/enums without connecting to CorelDRAW."""
import json
from pathlib import Path
import pythoncom


def main():
    path=r"C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb"
    library=pythoncom.LoadTypeLib(path)
    evidence={"path":path,"connection_attempted":False,"members":[],"enums":{}}
    seen=set()
    for index in range(library.GetTypeInfoCount()):
        info=library.GetTypeInfo(index); attr=info.GetTypeAttr()
        if attr.typekind==pythoncom.TKIND_COCLASS:
            info=info.GetRefTypeInfo(info.GetRefTypeOfImplType(0)); attr=info.GetTypeAttr()
        name=info.GetDocumentation(-1)[0]
        if name in seen: continue
        seen.add(name)
        if attr.typekind==pythoncom.TKIND_ENUM and 'pdf' in name.lower():
            values={}
            for variable_index in range(attr.cVars):
                desc=info.GetVarDesc(variable_index)
                values[info.GetDocumentation(desc[0])[0]]=desc[1]
            evidence['enums'][name]=values
        if name not in ('IVGDocument','IPDFVBASettings'): continue
        for function_index in range(attr.cFuncs):
            desc=info.GetFuncDesc(function_index); names=info.GetNames(desc[0])
            if name=='IPDFVBASettings' or names[0] in ('PDFSettings','PublishToPDF'):
                evidence['members'].append({'interface':name,'names':names,'invkind':desc[4],'descriptor':repr(tuple(desc))})
    output=Path(__file__).resolve().parents[1]/'docs/x7_pdf_api_evidence.json'
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(f"Retained {len(evidence['members'])} PDF descriptors and {len(evidence['enums'])} enum groups; no application connection.")


if __name__=='__main__': main()
