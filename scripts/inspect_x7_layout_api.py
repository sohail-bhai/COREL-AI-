"""Inspect X7 transform/order signatures and enums without application access."""
import json
import pythoncom


def main():
    path = r"C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb"
    library = pythoncom.LoadTypeLib(path)
    wanted = {
        "IVGShape": {"Rotate", "RotateEx", "RotationAngle", "Flip", "HFlip", "VFlip",
                     "AbsoluteHScale", "AbsoluteVScale", "GetMatrix", "OrderToFront", "OrderToBack",
                     "OrderForwardOne", "OrderBackOne", "OrderIsInFrontOf", "ParentGroup", "ZOrder", "SetPosition", "GetPosition"},
        "IVGShapeRange": {"AlignAndDistribute", "Distribute", "OrderToFront", "OrderToBack"},
    }
    enums = {"cdrFlipAxes", "cdrAlignDistributeH", "cdrAlignDistributeV", "cdrAlignShapesTo"}
    evidence = {"path": path, "connection_attempted": False, "members": [], "enums": {}}
    for index in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(index)
        name = info.GetDocumentation(-1)[0]
        attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0))
            name = info.GetDocumentation(-1)[0]
            attr = info.GetTypeAttr()
        if name in wanted:
            for function_index in range(attr.cFuncs):
                desc = info.GetFuncDesc(function_index)
                names = info.GetNames(desc[0])
                if names[0] in wanted[name]:
                    evidence["members"].append({"interface": name, "names": names,
                                                "invkind": desc[4], "descriptor": repr(tuple(desc))})
        if name in enums:
            values = {}
            for variable_index in range(attr.cVars):
                desc = info.GetVarDesc(variable_index)
                values[info.GetNames(desc[0])[0]] = desc[1]
            evidence["enums"][name] = values
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
