"""Literal CSV data and deterministic source-bound template batch plans."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from .errors import CorelBridgeError, ErrorCode
from .object_references import validate_reference
from .typography import finite_number,validate_style,STYLE_ATTRIBUTES

MAX_ROWS=1000
MAX_ITEMS=2000
MAX_NODES=1000
MAX_BYTES=2*1024*1024


def invalid(message,details=None):
    raise CorelBridgeError(message,ErrorCode.INVALID_ARGUMENT,details)


def canonical(value):
    try:
        data=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (ValueError,TypeError,OverflowError,RecursionError) as exc:
        raise CorelBridgeError("Template data must be finite ordinary JSON.",ErrorCode.INVALID_ARGUMENT) from exc
    if len(data)>MAX_BYTES: invalid("Template/plan data exceeds the 2 MiB limit.")
    return data


def digest(value): return hashlib.sha256(canonical(value)).hexdigest()


def seal(value):
    result=copy.deepcopy(value)
    result["fingerprint"]=digest(value)
    return result


def validate_template(template):
    if type(template) is not dict or set(template)!={"schema","template_reference","bounds_inches","nodes","fingerprint"}:
        invalid("Invalid text-template manifest.")
    if template["schema"]!="text-template-v1": invalid("Unsupported template schema.")
    validate_reference(template["template_reference"])
    nodes=template["nodes"]
    if type(nodes) is not list or not 2<=len(nodes)<=MAX_NODES: invalid("Templates require 2-1000 nodes including the root group.")
    seen=set()
    for node in nodes:
        if type(node) is not dict or set(node)!={"path","name","type_code","identity","static_id","bounds_inches","matrix","text","fill","outline"}:
            invalid("Invalid template node.")
        path=node["path"]
        if type(path) is not list or len(path)>16 or any(type(v) is not int or v<1 for v in path) or tuple(path) in seen:
            invalid("Template paths must be unique bounded diagnostic paths.")
        if path and tuple(path[:-1]) not in seen: invalid("Template node order does not include its parent.")
        seen.add(tuple(path))
        if type(node["name"]) is not str or len(node["name"])>256 or type(node["type_code"]) is not int:
            invalid("Template node names/types are unavailable.")
        if type(node["identity"]) is not str or len(node["identity"])!=64: invalid("Template native identity is unavailable.")
        bounds=node["bounds_inches"]
        if type(bounds) is not dict or set(bounds)!={"x","y","width","height"}: invalid("Invalid template bounds.")
        for field,value in bounds.items():
            finite_number(value,field,0 if field in ("width","height") else -10000,10000)
        if type(node["matrix"]) is not list or len(node["matrix"])!=6: invalid("Invalid template matrix.")
        for value in node["matrix"]: finite_number(value,"template matrix",-1000000,1000000)
        if node["text"] is not None:
            text=node["text"]
            if type(text) is not dict or set(text)!={"content","style","layout"} or type(text["content"]) is not str or len(text["content"])>10000:
                invalid("Invalid template text metadata.")
            layout=text["layout"]
            if type(layout) is not dict or layout.get("text_type_code") not in (0,1) or layout.get("frame_count")!=1:
                raise CorelBridgeError("Template copying requires unfitted, unlinked text throughout the group.",ErrorCode.UNSUPPORTED_IN_PROFILE)
    if nodes[0]["path"]!=[] or nodes[0]["type_code"]!=7 or nodes[0]["bounds_inches"]!=template["bounds_inches"]:
        invalid("Template root must be the measured group.")
    unsigned={k:v for k,v in template.items() if k!="fingerprint"}
    if template["fingerprint"]!=digest(unsigned): invalid("Template manifest fingerprint does not match its content.")


def read_template_csv(csv_path: str,delimiter: str=","):
    if type(csv_path) is not str: invalid("csv_path must be an absolute .csv file path.")
    path=Path(csv_path).expanduser()
    if not path.is_absolute() or path.suffix.lower()!=".csv": invalid("csv_path must be an absolute .csv file path.")
    if delimiter not in (",",";","\t") or type(delimiter) is not str: invalid("delimiter must be comma, semicolon or tab.")
    try:
        with path.open("rb") as handle: raw=handle.read(MAX_BYTES+1)
    except OSError as exc:
        raise CorelBridgeError("The CSV file could not be read.",ErrorCode.INVALID_ARGUMENT) from exc
    if len(raw)>MAX_BYTES: invalid("CSV input exceeds 2 MiB.")
    try:
        content=raw.decode("utf-8-sig")
        if "\x00" in content: invalid("CSV text cannot contain NUL.")
        reader=csv.reader(io.StringIO(content,newline=""),delimiter=delimiter,strict=True)
        headers=next(reader)
        if not 1<=len(headers)<=128 or any(not h.strip() or h!=h.strip() or len(h)>128 or any(ord(c)<32 for c in h) for h in headers):
            invalid("CSV headers must be nonblank unpadded names of at most 128 characters.")
        if len(set(headers))!=len(headers): invalid("CSV headers must be unique.")
        records,lines=[],[]
        while True:
            start=reader.line_num+1
            try: row=next(reader)
            except StopIteration: break
            if len(records)>=MAX_ROWS: invalid("CSV input exceeds 1000 records.")
            if len(row)!=len(headers): invalid("A CSV row has missing or extra cells.",{"source_line":start})
            if any(len(cell)>10000 for cell in row): invalid("CSV cells are limited to 10000 characters.",{"source_line":start})
            records.append(dict(zip(headers,row))); lines.append(start)
    except (UnicodeError,csv.Error,StopIteration) as exc:
        raise CorelBridgeError("CSV input must be valid UTF-8 with a header and complete rows.",ErrorCode.INVALID_ARGUMENT) from exc
    if not records: invalid("CSV input has no data rows.")
    return {"columns":headers,"records":records,"row_count":len(records),"source_lines":lines,"source_sha256":hashlib.sha256(raw).hexdigest()}


def plan_template_batch(
    template: dict,field_mapping: dict,records: list[dict],field_regions: dict | None=None,
    sheet_width_inches: float=8.5,sheet_height_inches: float=11,margin_inches: float=.25,gutter_inches: float=.125,
    copies_per_record: int=1,record_key: str | None=None,duplicate_policy: str="reject",overflow_policy: str="reject",
):
    validate_template(template)
    if type(field_mapping) is not dict or not 1<=len(field_mapping)<=128: invalid("field_mapping must bind 1-128 columns to unique text object names.")
    if any(type(k) is not str or not k.strip() or len(k)>128 or type(v) is not str or not v.strip() or len(v)>256 for k,v in field_mapping.items()): invalid("Invalid field mapping names.")
    if len(set(field_mapping.values()))!=len(field_mapping): invalid("Two columns cannot write the same template object.")
    fields={}
    for column,name in field_mapping.items():
        matches=[n for n in template["nodes"] if n["name"]==name]
        if len(matches)!=1 or matches[0]["text"] is None: invalid("Each mapped object name must identify one text node inside the template.")
        style=matches[0]["text"]["style"]
        if type(style) is not dict or any(style.get(k) is None for k in ("font","size_points","bold","italic","underline","alignment")):
            raise CorelBridgeError("Mapped fields require readable whole-story aggregate formatting.",ErrorCode.UNSUPPORTED_IN_PROFILE)
        validate_style(**{k:style[k] for k in STYLE_ATTRIBUTES})
        fields[column]=matches[0]
    if type(records) is not list or not 1<=len(records)<=MAX_ROWS: invalid("records must contain 1-1000 dictionaries of literal strings.")
    if duplicate_policy not in ("reject","allow") or overflow_policy not in ("reject","report"): invalid("Unknown duplicate/overflow policy.")
    if record_key is not None and (type(record_key) is not str or not record_key.strip()): invalid("record_key must be a column name or null.")
    seen,duplicates,all_columns={},[],set()
    for index,record in enumerate(records,1):
        if type(record) is not dict or len(record)>128 or any(type(k) is not str or not k.strip() or len(k)>128 or type(v) is not str or len(v)>10000 or "\x00" in v for k,v in record.items()):
            invalid("Record cells must be literal strings of at most 10000 characters.",{"record_index":index})
        missing=set(field_mapping)-set(record)
        if record_key is not None and (record_key not in record or not record[record_key].strip()): missing.add(record_key)
        if missing: invalid("Record columns are missing or the record key is blank.",{"record_index":index,"missing_columns":sorted(missing)})
        key=record[record_key] if record_key else tuple(record[k] for k in sorted(field_mapping))
        if key in seen:
            duplicates.append({"record_index":index,"first_record_index":seen[key]})
            if duplicate_policy=="reject": invalid("Duplicate records require an explicit allow policy or copies_per_record.",{"record_index":index,"first_record_index":seen[key]})
        else: seen[key]=index
        all_columns.update(record)
    if type(copies_per_record) is not int or not 1<=copies_per_record<=100 or len(records)*copies_per_record>MAX_ITEMS: invalid("copies_per_record must be 1-100 and the job may contain at most 2000 copies.")
    width=finite_number(sheet_width_inches,"sheet_width_inches",.001,200)
    height=finite_number(sheet_height_inches,"sheet_height_inches",.001,200)
    margin=finite_number(margin_inches,"margin_inches",0,50)
    gutter=finite_number(gutter_inches,"gutter_inches",0,50)
    item=template["bounds_inches"]
    iw=finite_number(item["width"],"template width",.001,200); ih=finite_number(item["height"],"template height",.001,200)
    columns=math.floor((width-2*margin+gutter+1e-9)/(iw+gutter))
    rows=math.floor((height-2*margin+gutter+1e-9)/(ih+gutter))
    if columns<1 or rows<1: invalid("The template does not fit the requested sheet and margins.")
    capacity=min(columns*rows,100,max(1,9000//len(template["nodes"])))
    count=len(records)*copies_per_record; sheets=math.ceil(count/capacity)
    if sheets>500: invalid("The job exceeds the 500-page output limit; split the data into smaller jobs.")
    regions={} if field_regions is None else field_regions
    if type(regions) is not dict or set(regions)-set(field_mapping): invalid("field_regions may only name mapped columns.")
    for column,region in regions.items():
        if type(region) is not dict or set(region)!={"x","y","width","height"}: invalid("Field regions require x/y/width/height in template-relative inches.")
        for name,value in region.items(): finite_number(value,name,0 if name in ("x","y") else .001,200)
        if region["x"]+region["width"]>iw+.001 or region["y"]+region["height"]>ih+.001: invalid("A field region extends beyond the template.")
    options=dict(sheet_width_inches=width,sheet_height_inches=height,margin_inches=margin,gutter_inches=gutter,
                 copies_per_record=copies_per_record,record_key=record_key,duplicate_policy=duplicate_policy,overflow_policy=overflow_policy)
    placements=[]
    for index in range(count):
        slot=index%capacity; page=index//capacity+1
        placements.append({"record_index":index//copies_per_record+1,"copy_index":index%copies_per_record+1,"page_index":page,
            "x":margin+(slot%columns)*(iw+gutter),"y":height-margin-ih-(slot//columns)*(ih+gutter),"width":iw,"height":ih,
            "label":f"Batch_R{index//copies_per_record+1:04d}_C{index%copies_per_record+1:03d}"})
    request={"template":copy.deepcopy(template),"field_mapping":dict(field_mapping),"records":copy.deepcopy(records),"field_regions":copy.deepcopy(regions),**options}
    return seal({"schema":"template-batch-plan-v1","request":request,"summary":{"record_count":len(records),"item_count":count,"sheet_count":sheets,
        "columns":columns,"rows":rows,"items_per_sheet":capacity,"unused_columns":sorted(all_columns-set(field_mapping)),"duplicate_rows":duplicates},"placements":placements})


def validate_template_plan(plan,approved_fingerprint):
    if type(plan) is not dict or set(plan)!={"schema","request","summary","placements","fingerprint"} or plan["schema"]!="template-batch-plan-v1": invalid("Invalid template batch plan.")
    if type(approved_fingerprint) is not str or approved_fingerprint!=plan["fingerprint"]: invalid("approved_fingerprint must match the complete plan.")
    try: rebuilt=plan_template_batch(**plan["request"])
    except TypeError as exc: raise CorelBridgeError("Invalid template batch request.",ErrorCode.INVALID_ARGUMENT) from exc
    if plan!=rebuilt: invalid("Template plan contents or fingerprint have changed; prepare and approve it again.")
    return rebuilt
