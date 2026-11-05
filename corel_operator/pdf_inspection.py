"""Local bounded PDF structure checks; no rendering, font decoding or native calls."""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import DictionaryObject,StreamObject,IndirectObject

from .errors import CorelBridgeError,ErrorCode
from .typography import finite_number

MAX_PDF_BYTES=50*1024*1024
MAX_PAGES=500
MAX_RESOURCES=10000


def invalid(message): raise CorelBridgeError(message,ErrorCode.INVALID_ARGUMENT)


def pdf_path(value):
    if type(value) is not str or not value or len(value)>32767 or '\x00' in value:
        invalid('path must be an absolute .pdf file path.')
    path=Path(value).expanduser()
    if not path.is_absolute() or path.suffix.lower()!='.pdf': invalid('path must be an absolute .pdf file path.')
    return path


def validate_expectations(expected_page_count,expected_page_sizes,require_embedded_fonts,tolerance_inches):
    if expected_page_count is not None and (type(expected_page_count) is not int or not 1<=expected_page_count<=MAX_PAGES):
        invalid('expected_page_count must be 1-500 or null.')
    if expected_page_sizes is not None:
        if type(expected_page_sizes) is not list or not 1<=len(expected_page_sizes)<=MAX_PAGES:
            invalid('expected_page_sizes must contain 1-500 width/height dictionaries or be null.')
        for size in expected_page_sizes:
            if type(size) is not dict or set(size)!={'width','height'}: invalid('Each expected page size needs width and height in inches.')
            for field,value in size.items(): finite_number(value,field,.001,200)
        if expected_page_count is not None and expected_page_count!=len(expected_page_sizes): invalid('Expected page count and size list disagree.')
    if type(require_embedded_fonts) is not bool: invalid('require_embedded_fonts must be a boolean.')
    finite_number(tolerance_inches,'tolerance_inches',.0001,.1)


def resolve(value): return value.get_object() if isinstance(value,IndirectObject) else value


def box(value,required=False):
    value=resolve(value)
    if value is None and not required: return None
    if not isinstance(value,(list,tuple)) or len(value)!=4: invalid('A PDF page box is missing or malformed.')
    try: coordinates=[float(v) for v in value]
    except (TypeError,ValueError,OverflowError) as exc: raise CorelBridgeError('PDF page coordinates are invalid.',ErrorCode.INVALID_ARGUMENT) from exc
    if any(not math.isfinite(v) or abs(v)>1000000 for v in coordinates) or coordinates[2]<=coordinates[0] or coordinates[3]<=coordinates[1]:
        invalid('PDF page coordinates are nonfinite, reversed or outside the inspection limit.')
    return {'x':coordinates[0]/72,'y':coordinates[1]/72,'width':(coordinates[2]-coordinates[0])/72,'height':(coordinates[3]-coordinates[1])/72}


def read_pdf_snapshot(path):
    path=pdf_path(path)
    try:
        with path.open('rb') as stream: raw=stream.read(MAX_PDF_BYTES+1)
    except OSError as exc: raise CorelBridgeError('The PDF file could not be read.',ErrorCode.INVALID_ARGUMENT) from exc
    if not raw or len(raw)>MAX_PDF_BYTES: invalid('PDF input must be nonempty and at most 50 MiB.')
    if not raw.startswith(b'%PDF-'): invalid('The input has no PDF header.')
    return path,raw


def inspect_pdf(path: str,expected_page_count: int | None=None,expected_page_sizes: list[dict] | None=None,
                require_embedded_fonts: bool=False,tolerance_inches: float=.01):
    validate_expectations(expected_page_count,expected_page_sizes,require_embedded_fonts,tolerance_inches)
    path,raw=read_pdf_snapshot(path)
    return inspect_pdf_snapshot(path,raw,expected_page_count,expected_page_sizes,require_embedded_fonts,tolerance_inches)


def inspect_pdf_snapshot(path,raw,expected_page_count=None,expected_page_sizes=None,
                         require_embedded_fonts=False,tolerance_inches=.01):
    """Internal entry point for a validated immutable encoded-byte snapshot."""
    try:
        reader=PdfReader(io.BytesIO(raw),strict=True,root_object_recovery_limit=MAX_RESOURCES,xref_stream_maximum_entries=MAX_RESOURCES*2)
        if reader.is_encrypted: invalid('Encrypted PDFs are outside this inspection contract.')
        tree=reader.root_object['/Pages']
        count=tree.get('/Count')
        if type(count) is bool or not isinstance(count,int) or not 1<=count<=MAX_PAGES: invalid('PDF inspection requires 1-500 declared pages.')
        if len(reader.pages)!=count: invalid('PDF page tree count differs from its actual page membership.')
        pages=[]; fonts=[]; font_keys=set(); resource_keys=set(); visited=0; unembedded=0
        def resource_key(value):
            return ('indirect',value.idnum,value.generation) if isinstance(value,IndirectObject) else ('direct',id(value))
        def resources(value,depth=0):
            nonlocal visited,unembedded
            if value is None: return
            if depth>16: invalid('PDF form resources exceed 16 nesting levels.')
            key=resource_key(value)
            if key in resource_keys: return
            resource_keys.add(key); value=resolve(value)
            if not isinstance(value,DictionaryObject): invalid('PDF resources must be dictionaries.')
            visited+=1
            if visited>MAX_RESOURCES: invalid('PDF resources exceed the 10000-object inspection budget.')
            font_map=resolve(value.get('/Font',DictionaryObject()))
            forms=resolve(value.get('/XObject',DictionaryObject()))
            if not isinstance(font_map,DictionaryObject) or not isinstance(forms,DictionaryObject): invalid('PDF font/form resources are malformed.')
            if len(font_map)+len(forms)+visited>MAX_RESOURCES: invalid('PDF resources exceed the 10000-object inspection budget.')
            for font_reference in font_map.values():
                key=resource_key(font_reference)
                if key in font_keys: continue
                font_keys.add(key); visited+=1
                font=resolve(font_reference)
                if not isinstance(font,DictionaryObject): invalid('A PDF font resource is malformed.')
                subtype=str(font.get('/Subtype',''))[:256]; name=str(font.get('/BaseFont',''))[:256]
                descendants=resolve(font.get('/DescendantFonts',[]))
                if not isinstance(descendants,list) or len(descendants)>32: invalid('PDF descendant font resources are malformed or excessive.')
                native_fonts=[resolve(f) for f in descendants] if subtype=='/Type0' else [font]
                visited+=len(native_fonts)
                if visited>MAX_RESOURCES: invalid('PDF font resources exceed the 10000-object inspection budget.')
                embedded=bool(native_fonts)
                for native in native_fonts:
                    if not isinstance(native,DictionaryObject): invalid('PDF descendant font resources are malformed.')
                    descriptor=resolve(native.get('/FontDescriptor'))
                    files=[] if not isinstance(descriptor,DictionaryObject) else [resolve(descriptor.get(k)) for k in ('/FontFile','/FontFile2','/FontFile3')]
                    embedded=embedded and any(isinstance(f,StreamObject) and bool(getattr(f,'_data',None)) for f in files)
                if not embedded: unembedded+=1
                if len(fonts)<100: fonts.append({'name':name,'subtype':subtype,'embedded_program_present':embedded})
            for form_reference in forms.values():
                visited+=1
                if visited>MAX_RESOURCES: invalid('PDF resources exceed the 10000-object inspection budget.')
                form=resolve(form_reference)
                if not isinstance(form,DictionaryObject): invalid('A PDF XObject resource is malformed.')
                if form.get('/Subtype')=='/Form': resources(form.get('/Resources'),depth+1)
        dimension_matches=True if expected_page_sizes is not None else None
        for index,page in enumerate(reader.pages):
            user_unit=float(page.get('/UserUnit',1))
            if not math.isfinite(user_unit) or user_unit!=1: invalid('Nondefault PDF UserUnit values need a separate units contract.')
            rotation=page.get('/Rotate',0)
            if type(rotation) is bool or not isinstance(rotation,int) or rotation%90: invalid('PDF page rotation is malformed.')
            media=box(page.get('/MediaBox'),required=True)
            crop=box(page.get('/CropBox')) or media
            width,height=media['width'],media['height']
            if rotation%180: width,height=height,width
            trim=box(page.get('/TrimBox')); bleed=box(page.get('/BleedBox'))
            matches=None
            if expected_page_sizes is not None:
                matches=index<len(expected_page_sizes) and abs(width-expected_page_sizes[index]['width'])<=tolerance_inches and abs(height-expected_page_sizes[index]['height'])<=tolerance_inches
                dimension_matches=dimension_matches and matches
            resources(page.get('/Resources'))
            if len(pages)<100: pages.append({'page_index':index+1,'rotation_degrees':rotation%360,'media_box_inches':media,
                'crop_box_inches':crop,'trim_box_inches':trim,'bleed_box_inches':bleed,
                'effective_width_inches':width,'effective_height_inches':height,'expected_size_matches':matches})
        if expected_page_sizes is not None and len(expected_page_sizes)!=count: dimension_matches=False
        checks={'page_count_matches':None if expected_page_count is None else count==expected_page_count,
                'page_sizes_match':dimension_matches,'embedded_fonts_passed':unembedded==0 if require_embedded_fonts else None}
        return {'path':str(path),'bytes':len(raw),'source_sha256':hashlib.sha256(raw).hexdigest(),'pdf_header':reader.pdf_header,
            'page_count':count,'pages':pages,'pages_truncated':count>100,'font_resource_count':len(font_keys),'fonts':fonts,
            'fonts_truncated':len(font_keys)>100,'unembedded_font_count':unembedded,'checks':checks,
            'checks_passed':all(value is not False for value in checks.values()),'production_ready':False,
            'warnings':['Structure checks do not establish visual fidelity, valid font programs, ICC/PDF-X compliance or printer readiness.']}
    except CorelBridgeError: raise
    except Exception as exc: raise CorelBridgeError('The PDF could not be parsed within the inspection contract.',ErrorCode.INVALID_ARGUMENT) from exc
