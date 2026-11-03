"""Native source-preserving text-template batches on explicitly owned outputs."""
from __future__ import annotations

from .errors import CorelBridgeError,ErrorCode
from .native_tracking import tracked_mutation
from .template_jobs import MAX_NODES,seal,validate_template,validate_template_plan
from .typography import STYLE_ATTRIBUTES,UNDERLINES,ALIGNMENTS,style_readback,layout_readback


def breaks(value): return value.replace("\r\n","\r").replace("\n","\r")


def inside(bounds,region,tolerance=.001):
    return (bounds["x"]>=region["x"]-tolerance and bounds["y"]>=region["y"]-tolerance
            and bounds["x"]+bounds["width"]<=region["x"]+region["width"]+tolerance
            and bounds["y"]+bounds["height"]<=region["y"]+region["height"]+tolerance)


def appearance(node):
    fill=node["fill"]; color=fill.get("color") or {}
    outline=node["outline"]; outline_color=outline.get("color") or {}
    return (fill.get("type_code"),color.get("type_code"),color.get("value"),
            outline.get("type_code"),outline.get("width_raw"),outline_color.get("type_code"),outline_color.get("value"))


class TemplateBridgeMixin:
    def _template_nodes(self,document,root):
        if self._reference_for_shape(document,root) is None:
            raise CorelBridgeError("Template root ownership cannot be established in the expected document.",ErrorCode.COREL_COM_ERROR)
        nodes,handles=[],[]
        stack=[([],root,None)]
        seen=set()
        while stack:
            path,shape,parent=stack.pop()
            if len(nodes)>=MAX_NODES or len(path)>16:
                raise CorelBridgeError("The template exceeds 1000 nodes or 16 group levels.",ErrorCode.UNSUPPORTED_IN_PROFILE)
            identity=self._reference_identity(shape)
            if identity in seen: raise CorelBridgeError("Template native membership is ambiguous.",ErrorCode.COREL_COM_ERROR)
            seen.add(identity)
            if parent is not None and (not self._same_com_object(shape.ParentGroup,parent,strict=True)
                    or not self._same_com_object(shape.Page,root.Page,strict=True)
                    or not self._same_com_object(shape.Layer,root.Layer,strict=True)):
                raise CorelBridgeError("Template child ownership differs from its group.",ErrorCode.COREL_COM_ERROR)
            name=shape.Name; code=shape.Type
            if type(name) is not str or len(name)>256 or type(code) is not int:
                raise CorelBridgeError("Template names/types are unavailable or too long.",ErrorCode.UNSUPPORTED_IN_PROFILE)
            transform=self._layout_snapshot(document,shape)
            text=None
            if code==self.adapter.CDR_TEXT_SHAPE:
                story=shape.Text.Story; content=story.Text
                if type(content) is not str or len(content)>10000:
                    raise CorelBridgeError("Template text fields exceed the 10000-character inspection limit.",ErrorCode.UNSUPPORTED_IN_PROFILE)
                text={"content":content,"style":style_readback(story),"layout":layout_readback(shape.Text,story)}
            nodes.append({"path":path,"name":name,"type_code":code,"identity":identity,"static_id":getattr(shape,"StaticID",None),
                          "bounds_inches":{k:round(v,8) for k,v in transform["bounds_inches"].items()},
                          "matrix":[round(v,8) for v in transform["matrix"]],"text":text,
                          "fill":self._fill_readback(shape),"outline":self._outline_readback(shape)})
            handles.append(shape)
            if code==self.adapter.CDR_GROUP_SHAPE:
                count=shape.Shapes.Count
                if type(count) is not int or not 0<=count<=MAX_NODES:
                    raise CorelBridgeError("The template group count is unavailable or exceeds its limit.",ErrorCode.UNSUPPORTED_IN_PROFILE)
                for index in range(count,0,-1): stack.append((path+[index],self._collection_item(shape.Shapes,index),shape))
        return nodes,handles

    def inspect_text_template(self,object_name: str="",shape_index: int=0,object_reference: dict | None=None):
        document,shape,identity=self._inspection_target(object_name,shape_index,object_reference)
        if identity["shape_type_code"]!=self.adapter.CDR_GROUP_SHAPE or identity["object_reference"] is None:
            raise CorelBridgeError("A text template requires a group with complete session identity.",ErrorCode.UNSUPPORTED_IN_PROFILE)
        try:
            nodes,_=self._template_nodes(document,shape)
            manifest=seal({"schema":"text-template-v1","template_reference":identity["object_reference"],"bounds_inches":nodes[0]["bounds_inches"],"nodes":nodes})
            validate_template(manifest)
            return {"template":manifest,"text_object_names":[n["name"] for n in nodes if n["text"] is not None],
                    "preservation_scope":"identity_structure_geometry_text_basic_appearance"}
        except CorelBridgeError: raise
        except Exception as exc: raise CorelBridgeError("Could not inspect the native template safely.",ErrorCode.COREL_COM_ERROR) from exc

    def _template_copy_nodes(self,document,page,layer,group,template,used_identities,root_name=None):
        if not self._same_com_object(group.Page,page,strict=True) or not self._same_com_object(group.Layer,layer,strict=True):
            raise CorelBridgeError("A template copy belongs to a different output page or layer.",ErrorCode.COREL_COM_ERROR)
        nodes,handles=self._template_nodes(document,group)
        source=template["nodes"]
        expected_name=source[0]["name"] if root_name is None else root_name
        if len(nodes)!=len(source) or nodes[0]["name"]!=expected_name or any((a["path"],a["type_code"])!=(b["path"],b["type_code"]) or (i>0 and a["name"]!=b["name"]) for i,(a,b) in enumerate(zip(nodes,source))):
            raise CorelBridgeError("The copied template structure differs from its source.",ErrorCode.COREL_COM_ERROR)
        identities={n["identity"] for n in nodes}
        if identities.intersection(used_identities):
            raise CorelBridgeError("A template copy shares native objects with another copy or the source.",ErrorCode.COREL_COM_ERROR)
        for node in nodes:
            if node["text"] is not None and (node["text"]["layout"]["text_type_code"] not in (0,1) or node["text"]["layout"]["frame_count"]!=1):
                raise CorelBridgeError("The copied template contains shared/fitted text frames.",ErrorCode.COREL_COM_ERROR)
        used_identities.update(identities)
        return nodes,handles

    def _template_replace_field(self,shape,value,expected_style):
        story=shape.Text.Story
        self._note_mutation(); story.Text=value
        # Explicit whole-field aggregate style prevents inherited defaults after
        # replacement. Per-run text formatting is outside this contract.
        for field,attr in STYLE_ATTRIBUTES.items():
            setting=expected_style[field]
            if field=="underline": setting=UNDERLINES[setting]
            if field=="alignment": setting=ALIGNMENTS[setting]
            setattr(story,attr,setting)
        if breaks(story.Text)!=breaks(value):
            raise CorelBridgeError("Native template text readback differs from its record.",ErrorCode.COREL_COM_ERROR)
        self._verify_text_style({k:expected_style[k] for k in STYLE_ATTRIBUTES},style_readback(story))

    @tracked_mutation
    def execute_template_batch(self,plan: dict,approved_fingerprint: str):
        plan=validate_template_plan(plan,approved_fingerprint)
        request=plan["request"]; template=request["template"]; source_reference=template["template_reference"]
        source_document=self._selector_document("",0,source_reference)
        source,_=self._resolve_object_reference(source_document,source_reference)
        fresh=self.inspect_text_template(object_reference=source_reference)["template"]
        if fresh["fingerprint"]!=template["fingerprint"]:
            raise CorelBridgeError("The source template changed after planning; inspect and approve a new plan.",ErrorCode.INVALID_ARGUMENT)
        mapping=request["field_mapping"]
        source_nodes=template["nodes"]
        field_indices={column:next(i for i,n in enumerate(source_nodes) if n["name"]==name) for column,name in mapping.items()}
        for font in {source_nodes[i]["text"]["style"]["font"] for i in field_indices.values()}: self._require_font(font)
        self._layout_method(source,"Copy")
        source_page=source_document.ActivePage; source_layer=source_page.ActiveLayer
        copy_page=source.Page
        previous_active=self.app.ActiveDocument
        baseline={self._reference_identity(doc) for doc in self._open_document_proxies(self.app)}
        output=None; owned=False; command_open=False; clipboard_modified=False
        items=[]; fit_issues=[]; group_records=[]; page_records=[]
        try:
            self._note_mutation(); output=self.app.CreateDocument()
            if output is None or self._reference_identity(output) in baseline:
                raise CorelBridgeError("CorelDRAW did not return an independently owned output document.",ErrorCode.COREL_COM_ERROR)
            owned=True
            if {self._reference_identity(doc) for doc in self._open_document_proxies(self.app)}!=baseline|{self._reference_identity(output)}:
                raise CorelBridgeError("Document membership changed unexpectedly during template output creation.",ErrorCode.COREL_COM_ERROR)
            if output.Pages.Count!=1: raise CorelBridgeError("A new template output must start with one page.",ErrorCode.COREL_COM_ERROR)
            output.BeginCommandGroup("AI Template Batch"); command_open=True
            used={n["identity"] for n in source_nodes}
            with self._in_inches(output,strict_restore=True),self._reference_point(output,strict_restore=True):
                for page_index in range(1,plan["summary"]["sheet_count"]+1):
                    if page_index>1:
                        output.AddPagesEx(1,request["sheet_width_inches"],request["sheet_height_inches"])
                        if output.Pages.Count!=page_index: raise CorelBridgeError("The output page count differs from the plan.",ErrorCode.COREL_COM_ERROR)
                    page=self._collection_item(output.Pages,page_index)
                    page.Activate(); page.SetSize(request["sheet_width_inches"],request["sheet_height_inches"])
                    layer=page.CreateLayer("Template Batch")
                    if abs(page.SizeWidth-request["sheet_width_inches"])>.001 or abs(page.SizeHeight-request["sheet_height_inches"])>.001:
                        raise CorelBridgeError("Native output page dimensions differ from the plan.",ErrorCode.COREL_COM_ERROR)
                    page_records.append((page,layer))
                    copy_page.Activate(); clipboard_modified=True; source.Copy()
                    page.Activate(); layer.Activate()
                    blueprint=layer.Paste()
                    if layer.Shapes.Count!=1: raise CorelBridgeError("Paste did not create exactly one independent template group.",ErrorCode.COREL_COM_ERROR)
                    if blueprint is None: blueprint=self._collection_item(layer.Shapes,1)
                    placements=[p for p in plan["placements"] if p["page_index"]==page_index]
                    copies=[blueprint]
                    for _ in placements[1:]: copies.append(blueprint.Duplicate(0.,0.))
                    if layer.Shapes.Count!=len(placements): raise CorelBridgeError("The native copy count differs from the plan.",ErrorCode.COREL_COM_ERROR)
                    # Duplicate every pristine group on the page before editing data.
                    for placement,group in zip(placements,copies):
                        _,handles=self._template_copy_nodes(output,page,layer,group,template,used)
                        group.Name=placement["label"]; group.SetPosition(placement["x"],placement["y"])
                        values=request["records"][placement["record_index"]-1]
                        for column,index in field_indices.items():
                            self._template_replace_field(handles[index],values[column],source_nodes[index]["text"]["style"])
                        group_records.append((page,layer,group,placement))
            # Verify every row again after all edits to expose shared text/ranges.
            final_identities={n["identity"] for n in source_nodes}
            for page,layer,group,placement in group_records:
                nodes,handles=self._template_copy_nodes(output,page,layer,group,template,final_identities,placement["label"])
                if len(nodes)!=len(source_nodes): raise CorelBridgeError("Template output structure changed while merging data.",ErrorCode.COREL_COM_ERROR)
                if group.Name!=placement["label"]:
                    raise CorelBridgeError("A final template copy lost its planned identity label.",ErrorCode.COREL_COM_ERROR)
                values=request["records"][placement["record_index"]-1]
                region={k:placement[k] for k in ("x","y","width","height")}
                issues=[]; field_reports=[]
                for index,(node,original) in enumerate(zip(nodes,source_nodes)):
                    if (node["path"],node["type_code"])!=(original["path"],original["type_code"]) or (index>0 and node["name"]!=original["name"]) or appearance(node)!=appearance(original):
                        raise CorelBridgeError("Template structure or basic appearance changed unexpectedly.",ErrorCode.COREL_COM_ERROR)
                    columns=[column for column,field_index in field_indices.items() if field_index==index]
                    if node["text"] is not None:
                        expected=values[columns[0]] if columns else original["text"]["content"]
                        if breaks(node["text"]["content"])!=breaks(expected): raise CorelBridgeError("A final template record or static text changed unexpectedly.",ErrorCode.COREL_COM_ERROR)
                        if node["text"]["style"]!=original["text"]["style"]:
                            raise CorelBridgeError("Final template text formatting differs from the source.",ErrorCode.COREL_COM_ERROR)
                    if index>0 and not columns:
                        before=original["bounds_inches"]; actual=node["bounds_inches"]
                        expected={**before,"x":before["x"]+placement["x"]-template["bounds_inches"]["x"],
                                  "y":before["y"]+placement["y"]-template["bounds_inches"]["y"]}
                        if any(abs(actual[k]-expected[k])>.001 for k in expected) or any(abs(node["matrix"][k]-original["matrix"][k])>1e-6 for k in range(4)):
                            raise CorelBridgeError("Static template geometry changed during copying or personalization.",ErrorCode.COREL_COM_ERROR)
                    for column in columns:
                        self._verify_text_style({k:original["text"]["style"][k] for k in STYLE_ATTRIBUTES},node["text"]["style"])
                        layout=node["text"]["layout"]
                        if layout["text_type_code"]==1 and layout["overflow"] is None:
                            raise CorelBridgeError("Paragraph overflow could not be established.",ErrorCode.COREL_COM_ERROR)
                        field_region=request["field_regions"].get(column)
                        if field_region is None and layout["text_type_code"]==1:
                            b=original["bounds_inches"]; root=template["bounds_inches"]
                            field_region={"x":b["x"]-root["x"],"y":b["y"]-root["y"],"width":b["width"],"height":b["height"]}
                        box=region if field_region is None else {"x":placement["x"]+field_region["x"],"y":placement["y"]+field_region["y"],"width":field_region["width"],"height":field_region["height"]}
                        fits=inside(node["bounds_inches"],box) and layout["overflow"] is not True
                        if not fits: issues.append(column)
                        if len(field_reports)<8:
                            field_reports.append({"column":column,"content_matches":True,"style_matches":True,"overflow":layout["overflow"],
                                                  "fits_region":fits,"bounds_inches":node["bounds_inches"],"region_inches":box})
                if not inside(nodes[0]["bounds_inches"],region): issues.append("__item_bounds__")
                if issues:
                    fit_issues.append({"record_index":placement["record_index"],"copy_index":placement["copy_index"],"columns":issues})
                if len(items)<100:
                    items.append({"record_index":placement["record_index"],"copy_index":placement["copy_index"],"page_index":placement["page_index"],
                                  "object_name":placement["label"],"object_reference":None,"fields":field_reports,"fields_truncated":len(field_indices)>8})
            if len(group_records)!=plan["summary"]["item_count"] or output.Pages.Count!=plan["summary"]["sheet_count"]:
                raise CorelBridgeError("Final template counts differ from the complete plan.",ErrorCode.COREL_COM_ERROR)
            for page_index,(page,layer) in enumerate(page_records,1):
                expected_count=sum(p["page_index"]==page_index for p in plan["placements"])
                if layer.Shapes.Count!=expected_count:
                    raise CorelBridgeError("Final output layer membership differs from the complete plan.",ErrorCode.COREL_COM_ERROR)
            if fit_issues and request["overflow_policy"]=="reject":
                raise CorelBridgeError("Template output exceeded a field/item region or paragraph frame.",ErrorCode.INVALID_ARGUMENT,{"fit_issue_count":len(fit_issues)})
            source_page.Activate(); source_layer.Activate()
            if self.inspect_text_template(object_reference=source_reference)["template"]["fingerprint"]!=template["fingerprint"]:
                raise CorelBridgeError("Measured source template state changed during copying.",ErrorCode.COREL_COM_ERROR)
            output.EndCommandGroup(); command_open=False
            output.Activate(); self._collection_item(output.Pages,1).Activate()
            self._bind_target_document(output,new_document=True)
            for item,(_,_,group,_) in zip(items,group_records): item["object_reference"]=self._reference_for_shape(output,group)
            return {"created":True,"record_count":plan["summary"]["record_count"],"item_count":len(group_records),"sheet_count":output.Pages.Count,
                    "output_document":{"name":str(output.Name),"document_session_id":self._document_session_id(output)},
                    "source_preservation":{"verified":True,"scope":"identity_structure_geometry_text_basic_appearance"},
                    "fit_checks_passed":not fit_issues,"fit_issue_count":len(fit_issues),"fit_issues":fit_issues[:100],"fit_issues_truncated":len(fit_issues)>100,
                    "items":items,"items_truncated":len(group_records)>100,"clipboard_modified":clipboard_modified,
                    "verification_status":"implemented_unverified",
                    "warnings":["System clipboard contents were replaced by the template copy.","Glyph, visual and print readiness remain unverified."]}
        except Exception as exc:
            rollback={"attempted":True,"verified":False,"output_closed":False,"source_observations_restored":False}
            try:
                if owned and output is not None:
                    if self._reference_identity(output) in baseline: raise RuntimeError("Refusing discard of a pre-existing document")
                    if command_open: output.EndCommandGroup(); command_open=False
                    output.Dirty=False; output.Close(); rollback["output_closed"]=True
                self._bind_target_document(source_document)
                source_page.Activate(); source_layer.Activate()
                rollback["source_observations_restored"]=self.inspect_text_template(object_reference=source_reference)["template"]["fingerprint"]==template["fingerprint"]
                membership={self._reference_identity(doc) for doc in self._open_document_proxies(self.app)}
                if previous_active is not None and self._reference_identity(previous_active) in membership: previous_active.Activate()
                rollback["verified"]=membership==baseline and rollback["source_observations_restored"]
            except Exception as cleanup_error: rollback["error_type"]=type(cleanup_error).__name__
            code=exc.code if isinstance(exc,CorelBridgeError) else ErrorCode.COREL_COM_ERROR
            details={"rollback":rollback,"clipboard_modified":clipboard_modified}
            if isinstance(exc,CorelBridgeError): details.update(exc.details)
            raise CorelBridgeError("Template batch could not complete safely. "+("Owned output was discarded and measured source state verified." if rollback["verified"] else "Inspect the source and remaining owned output before reconciliation."),code,details) from exc
