"""Read installed X7 template-copy/document signatures without application access."""
import json
import pythoncom


def main():
    path=r"C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb"
    library=pythoncom.LoadTypeLib(path)
    wanted={"IVGApplication":{"CreateDocument","ActiveDocument","Documents"},
            "IVGDocument":{"AddPagesEx","Close","Dirty","Activate","BeginCommandGroup","EndCommandGroup"},
            "IVGPage":{"Activate","SetSize","CreateLayer","ActiveLayer"},
            "IVGLayer":{"Paste","Activate","Shapes"},
            "IVGShape":{"Copy","Duplicate","Shapes","Name","Type"}}
    evidence={"path":path,"connection_attempted":False,"members":[]}
    for index in range(library.GetTypeInfoCount()):
        info=library.GetTypeInfo(index); attr=info.GetTypeAttr()
        if attr.typekind==pythoncom.TKIND_COCLASS:
            info=info.GetRefTypeInfo(info.GetRefTypeOfImplType(0)); attr=info.GetTypeAttr()
        name=info.GetDocumentation(-1)[0]
        if name not in wanted: continue
        for function_index in range(attr.cFuncs):
            desc=info.GetFuncDesc(function_index); names=info.GetNames(desc[0])
            if names[0] in wanted[name]:
                evidence["members"].append({"interface":name,"names":names,"invkind":desc[4],"descriptor":repr(tuple(desc))})
    print(json.dumps(evidence,indent=2))


if __name__=="__main__": main()
