"""Bounded PDF box/resource preflight, without decoding artwork or ICC programs."""
from __future__ import annotations

import hashlib
import io

from pypdf import PdfReader
from pypdf.generic import BooleanObject, DictionaryObject, IndirectObject, StreamObject

from .errors import CorelBridgeError, ErrorCode
from .pdf_inspection import (MAX_RESOURCES, box, inspect_pdf_snapshot, invalid,
                             read_pdf_snapshot, resolve, validate_expectations)
from .typography import finite_number

MAX_DEPTH = 16
MAX_SUMMARIES = 100


def _boolean(value):
    if not isinstance(value, (bool, BooleanObject)):
        invalid('A PDF boolean resource flag is malformed.')
    # pypdf BooleanObject instances are truthy even when their stored value is false.
    return value.value if isinstance(value, BooleanObject) else value


def _contains(outer, inner, tolerance):
    return (inner['x'] >= outer['x'] - tolerance and inner['y'] >= outer['y'] - tolerance
            and inner['x'] + inner['width'] <= outer['x'] + outer['width'] + tolerance
            and inner['y'] + inner['height'] <= outer['y'] + outer['height'] + tolerance)


class ResourceInventory:
    """Visit every resource edge; cap recursion and work even for alias graphs."""
    def __init__(self):
        self.work = 0
        self.seen = set()
        self.families = set()
        self.spots = set()
        self.images = []
        self.image_count = 0
        self.states = []
        self.state_count = 0
        self.overprint_count = 0
        self.unknown = set()

    def tick(self, depth):
        self.work += 1
        if depth > MAX_DEPTH or self.work > MAX_RESOURCES:
            invalid('PDF prepress resources exceed 16 levels or 10000 visits.')

    def once(self, value, kind, depth):
        self.tick(depth)
        key = (kind, value.idnum, value.generation) if isinstance(value, IndirectObject) else (kind, id(value))
        if key in self.seen:
            return False
        self.seen.add(key)
        return True

    def color(self, value, resources, depth=0):
        self.tick(depth)
        value = resolve(value)
        if isinstance(value, str):
            if value in ('/DeviceRGB', '/DeviceCMYK', '/DeviceGray', '/Pattern'):
                self.families.add(value[1:])
                return
            aliases = resolve(resources.get('/ColorSpace', DictionaryObject()))
            if not isinstance(aliases, DictionaryObject):
                invalid('PDF color aliases must be a dictionary.')
            if value in aliases:
                self.color(aliases[value], resources, depth + 1)
            else:
                self.unknown.add('unknown_or_unresolved_color_space')
            return
        if not isinstance(value, list) or not value:
            invalid('A PDF color space is malformed.')
        kind = str(resolve(value[0]))
        if kind in ('/CalGray', '/CalRGB', '/Lab'):
            if len(value) != 2 or not isinstance(resolve(value[1]), DictionaryObject):
                invalid('A calibrated PDF color space is malformed.')
            self.families.add(kind[1:])
        elif kind == '/ICCBased':
            if len(value) != 2:
                invalid('A PDF ICCBased color space is malformed.')
            profile = resolve(value[1])
            if (not isinstance(profile, StreamObject) or not isinstance(profile.get('/N'), int)
                    or isinstance(profile.get('/N'), bool) or profile.get('/N') not in (1, 3, 4)):
                invalid('A PDF ICC color-space profile is malformed.')
            self.families.add('ICCBased')
            if not getattr(profile, '_data', b''):
                self.unknown.add('empty_icc_color_space_profile')
            if '/Alternate' in profile:
                self.color(profile['/Alternate'], resources, depth + 1)
        elif kind in ('/Separation', '/DeviceN'):
            if len(value) not in ((4,) if kind == '/Separation' else (4, 5)):
                invalid('A PDF spot color space is malformed.')
            names = [resolve(value[1])] if kind == '/Separation' else resolve(value[1])
            if not isinstance(names, list) or not 1 <= len(names) <= 32:
                invalid('PDF DeviceN colorant names are malformed or excessive.')
            for name in names:
                self.tick(depth)
                if not isinstance(name, str) or not name.startswith('/') or len(name) > 256:
                    invalid('A PDF colorant name is malformed or excessive.')
                self.spots.add(str(name))
            self.families.add(kind[1:])
            self.color(value[2], resources, depth + 1)
            # Tint transforms and DeviceN attributes are opaque, never evaluated.
            if not isinstance(resolve(value[3]), (DictionaryObject, list)):
                invalid('A PDF tint transform is malformed.')
            if kind == '/DeviceN' and len(value) == 5:
                attributes = resolve(value[4])
                if not isinstance(attributes, DictionaryObject):
                    invalid('PDF DeviceN attributes are malformed.')
                colorants = resolve(attributes.get('/Colorants', DictionaryObject()))
                if not isinstance(colorants, DictionaryObject):
                    invalid('PDF DeviceN colorant resources are malformed.')
                for colorant in colorants.values():
                    self.color(colorant, resources, depth + 1)
                process = resolve(attributes.get('/Process'))
                if process is not None:
                    if not isinstance(process, DictionaryObject) or '/ColorSpace' not in process:
                        invalid('PDF DeviceN process attributes are malformed.')
                    self.color(process['/ColorSpace'], resources, depth + 1)
        elif kind == '/Indexed':
            if len(value) != 4:
                invalid('A PDF Indexed color space is malformed.')
            self.families.add('Indexed')
            self.color(value[1], resources, depth + 1)
        elif kind == '/Pattern':
            if len(value) not in (1, 2):
                invalid('A PDF Pattern color space is malformed.')
            self.families.add('Pattern')
            if len(value) == 2:
                self.color(value[1], resources, depth + 1)
        else:
            self.unknown.add('unknown_color_space_family')

    def group(self, value, resources, depth):
        if value is None:
            return
        self.tick(depth)
        value = resolve(value)
        if not isinstance(value, DictionaryObject):
            invalid('A PDF transparency group is malformed.')
        if '/CS' in value:
            self.color(value['/CS'], resources, depth + 1)

    def xobject(self, reference, resources, depth):
        if not self.once(reference, ('xobject', id(resources)), depth):
            return
        value = resolve(reference)
        if not isinstance(value, StreamObject):
            invalid('A PDF prepress XObject is not a stream.')
        kind = value.get('/Subtype')
        if kind == '/Form':
            if '/Ref' in value or '/OPI' in value:
                self.unknown.add('external_or_opi_form')
            local = resolve(value.get('/Resources', resources))
            self.resources(local, depth + 1)
            self.group(value.get('/Group'), local, depth + 1)
        elif kind == '/Image':
            width, height = value.get('/Width'), value.get('/Height')
            if any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 1000000 for v in (width, height)):
                invalid('PDF image dimensions are malformed or excessive.')
            mask = _boolean(value.get('/ImageMask', False))
            if '/ColorSpace' in value:
                self.color(value['/ColorSpace'], resources, depth + 1)
            elif not mask:
                self.unknown.add('image_without_color_space')
            self.image_count += 1
            if len(self.images) < MAX_SUMMARIES:
                self.images.append({'width_pixels': int(width), 'height_pixels': int(height), 'image_mask': mask})
            for field in ('/SMask', '/Mask'):
                nested = value.get(field)
                if isinstance(resolve(nested), StreamObject):
                    self.xobject(nested, resources, depth + 1)
            if '/OPI' in value:
                self.unknown.add('opi_image')
        else:
            self.unknown.add('unknown_or_postscript_xobject')

    def resources(self, reference, depth=0):
        if not self.once(reference, 'resources', depth):
            return
        value = resolve(reference)
        if not isinstance(value, DictionaryObject):
            invalid('PDF prepress resources must be dictionaries.')
        known = {'/ColorSpace', '/XObject', '/ExtGState', '/Shading', '/Pattern', '/Font', '/ProcSet', '/Properties'}
        if set(value) - known:
            self.unknown.add('unknown_resource_category')
        for category in ('/ColorSpace', '/XObject', '/ExtGState', '/Shading', '/Pattern', '/Font'):
            mapping = resolve(value.get(category, DictionaryObject()))
            if not isinstance(mapping, DictionaryObject):
                invalid('A PDF prepress resource category is malformed.')
            for resource in mapping.values():
                self.tick(depth)
                if category == '/ColorSpace':
                    self.color(resource, value, depth + 1)
                elif category == '/XObject':
                    self.xobject(resource, value, depth + 1)
                else:
                    if not self.once(resource, (category, id(value)), depth + 1):
                        continue
                    resource = resolve(resource)
                    if not isinstance(resource, DictionaryObject):
                        invalid('A PDF prepress resource is malformed.')
                    if category == '/ExtGState':
                        stroke = _boolean(resource.get('/OP', False))
                        fill = _boolean(resource.get('/op', stroke))
                        mode = resource.get('/OPM', 0)
                        if isinstance(mode, bool) or not isinstance(mode, int) or mode not in (0, 1):
                            invalid('PDF overprint flags or mode are malformed.')
                        self.state_count += 1
                        self.overprint_count += int(stroke or fill)
                        if len(self.states) < MAX_SUMMARIES:
                            self.states.append({'stroke_overprint': stroke, 'fill_overprint': fill, 'overprint_mode': int(mode)})
                        softmask = resolve(resource.get('/SMask'))
                        if isinstance(softmask, DictionaryObject) and '/G' in softmask:
                            self.xobject(softmask['/G'], value, depth + 1)
                    elif category in ('/Shading', '/Pattern'):
                        if '/ColorSpace' in resource:
                            self.color(resource['/ColorSpace'], value, depth + 1)
                        shading = resolve(resource.get('/Shading'))
                        if isinstance(shading, DictionaryObject) and '/ColorSpace' in shading:
                            self.color(shading['/ColorSpace'], value, depth + 1)
                        if '/Resources' in resource:
                            self.resources(resource['/Resources'], depth + 1)
                    elif category == '/Font' and resource.get('/Subtype') == '/Type3':
                        self.unknown.add('type3_glyph_content_not_scanned')
                        if '/Resources' in resource:
                            self.resources(resource['/Resources'], depth + 1)
        if '/Properties' in value:
            self.unknown.add('marked_content_properties_not_scanned')


def preflight_pdf(path: str, expected_trim_sizes: list[dict] | None = None,
                  expected_bleed_inches: float | None = None, require_embedded_fonts: bool = False,
                  require_output_intent: bool = False, tolerance_inches: float = .001):
    validate_expectations(None, expected_trim_sizes, require_embedded_fonts, tolerance_inches)
    if expected_bleed_inches is not None:
        finite_number(expected_bleed_inches, 'expected_bleed_inches', 0, 1)
    if type(require_output_intent) is not bool:
        invalid('require_output_intent must be a boolean.')
    path, raw = read_pdf_snapshot(path)
    structural = inspect_pdf_snapshot(path, raw, require_embedded_fonts=require_embedded_fonts)
    try:
        reader = PdfReader(io.BytesIO(raw), strict=True, root_object_recovery_limit=MAX_RESOURCES,
                           xref_stream_maximum_entries=MAX_RESOURCES * 2)
        inventory = ResourceInventory()
        pages = []
        relationships = True
        trim_matches = None if expected_trim_sizes is None else len(expected_trim_sizes) == structural['page_count']
        bleed_matches = None if expected_bleed_inches is None else True
        for index, page in enumerate(reader.pages):
            media = box(page.get('/MediaBox'), required=True)
            crop = box(page.get('/CropBox')) or media
            trim = box(page.get('/TrimBox'))
            bleed = box(page.get('/BleedBox'))
            related = _contains(media, crop, tolerance_inches)
            related = related and all(_contains(media, b, tolerance_inches) for b in (trim, bleed) if b is not None)
            related = related and all(_contains(crop, b, tolerance_inches) for b in (trim, bleed) if b is not None)
            if trim is not None and bleed is not None:
                related = related and _contains(bleed, trim, tolerance_inches)
            relationships = relationships and related
            matches = None
            if expected_trim_sizes is not None:
                matches = False
                if trim is not None and index < len(expected_trim_sizes):
                    width, height = trim['width'], trim['height']
                    if int(page.get('/Rotate', 0)) % 180:
                        width, height = height, width
                    expected = expected_trim_sizes[index]
                    matches = abs(width - expected['width']) <= tolerance_inches and abs(height - expected['height']) <= tolerance_inches
                trim_matches = trim_matches and matches
            margins = None
            bleed_match = None
            if trim is not None and bleed is not None:
                margins = {'left': trim['x'] - bleed['x'], 'bottom': trim['y'] - bleed['y'],
                           'right': bleed['x'] + bleed['width'] - trim['x'] - trim['width'],
                           'top': bleed['y'] + bleed['height'] - trim['y'] - trim['height']}
            if expected_bleed_inches is not None:
                bleed_match = margins is not None and all(abs(v - expected_bleed_inches) <= tolerance_inches for v in margins.values())
                if expected_bleed_inches > 0 and margins is not None:
                    bleed_match = bleed_match and all(v > 0 for v in margins.values())
                if expected_bleed_inches == 0 and trim is not None and bleed is None:
                    bleed_match = True
                bleed_matches = bleed_matches and bleed_match
            resources = resolve(page.get('/Resources', DictionaryObject()))
            inventory.resources(resources)
            inventory.group(page.get('/Group'), resources, 0)
            if page.get('/Annots'):
                inventory.unknown.add('annotation_appearances_not_scanned')
            if len(pages) < MAX_SUMMARIES:
                pages.append({'page_index': index + 1, 'box_relationships_passed': related,
                              'trim_size_matches': matches, 'bleed_margins_inches': margins, 'bleed_matches': bleed_match})
        intents = resolve(reader.root_object.get('/OutputIntents', []))
        if not isinstance(intents, list) or len(intents) > 32:
            invalid('PDF output intents are malformed or exceed 32 entries.')
        output_intents = []
        for reference in intents:
            inventory.tick(0)
            intent = resolve(reference)
            if not isinstance(intent, DictionaryObject):
                invalid('A PDF output intent is malformed.')
            profile = resolve(intent.get('/DestOutputProfile'))
            present = isinstance(profile, StreamObject) and bool(getattr(profile, '_data', b''))
            encoded = getattr(profile, '_data', b'') if present else b''
            output_intents.append({'subtype': str(intent.get('/S', ''))[:256],
                'identifier': str(intent.get('/OutputConditionIdentifier', ''))[:256],
                'embedded_profile_present': present, 'encoded_profile_bytes': len(encoded),
                'encoded_profile_sha256': hashlib.sha256(encoded).hexdigest() if present else None})
        metadata = reader.metadata
        declarations = {key[1:]: str(metadata.get(key))[:256] if metadata and metadata.get(key) is not None else None
                        for key in ('/GTS_PDFXVersion', '/GTS_PDFXConformance')}
        checks = {'box_relationships_passed': relationships, 'trim_sizes_match': trim_matches,
                  'bleed_margins_match': bleed_matches, 'embedded_fonts_passed': structural['checks']['embedded_fonts_passed'],
                  'output_intent_present': any(item['embedded_profile_present'] for item in output_intents) if require_output_intent else None}
        return {'path': str(path), 'bytes': len(raw), 'source_sha256': structural['source_sha256'],
            'page_count': structural['page_count'], 'pages': pages, 'pages_truncated': structural['page_count'] > MAX_SUMMARIES,
            'checks': checks, 'checks_passed': all(value is not False for value in checks.values()),
            'resource_inventory': {'color_space_families': sorted(inventory.families), 'spot_colorant_count': len(inventory.spots),
                'spot_colorants': sorted(inventory.spots)[:MAX_SUMMARIES], 'spot_colorants_truncated': len(inventory.spots) > MAX_SUMMARIES,
                'image_resource_count': inventory.image_count, 'images': inventory.images,
                'images_truncated': inventory.image_count > MAX_SUMMARIES, 'graphics_state_count': inventory.state_count,
                'overprint_enabled_state_count': inventory.overprint_count,
                'graphics_states': inventory.states, 'graphics_states_truncated': inventory.state_count > MAX_SUMMARIES,
                'visits': inventory.work, 'complete_for_supported_resources': not inventory.unknown,
                'unsupported_reasons': sorted(inventory.unknown)},
            'output_intents': output_intents, 'pdfx_declarations': declarations,
            'font_resource_count': structural['font_resource_count'], 'unembedded_font_count': structural['unembedded_font_count'],
            'verification_status': 'implemented_unverified', 'production_ready': False,
            'warnings': ['Resource presence does not prove content usage, correct color conversion, spot separations or overprint appearance.',
                'ICC programs, tint transforms, artwork streams, inline images and XMP are not decoded; effective raster DPI is unmeasured.',
                'Page boxes do not prove artwork reaches bleed edges or that crop/registration marks are drawn correctly.',
                'Output intents and PDF/X declarations do not establish conformance, visual fidelity or printer readiness.']}
    except CorelBridgeError:
        raise
    except Exception as exc:
        raise CorelBridgeError('PDF prepress inspection could not complete within its bounded contract.', ErrorCode.INVALID_ARGUMENT) from exc
