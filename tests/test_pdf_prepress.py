from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError
from pypdf import PdfWriter
from pypdf.generic import (ArrayObject, BooleanObject, DecodedStreamObject,
                           DictionaryObject, FloatObject, NameObject, NumberObject, TextStringObject)

from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.pdf_bridge import BLEED_UNITS_PER_INCH, bleed_units
from corel_operator.pdf_prepress import preflight_pdf
from corel_operator.results import success_result
import test_pdf_production as pdf_fixture

write_pdf = pdf_fixture.write_pdf


def dictionary(**values):
    return DictionaryObject({NameObject('/' + key): value for key, value in values.items()})


def rectangle(x, y, width, height):
    return ArrayObject([FloatObject(v * 72) for v in (x, y, x + width, y + height)])


def production_pdf(path, sizes=((8.5, 11),), bleed=.125, last_bad=False, resources=None, rotation=0):
    writer = PdfWriter()
    for index, (width, height) in enumerate(sizes):
        page = writer.add_blank_page((width + 2) * 72, (height + 2) * 72)
        page[NameObject('/TrimBox')] = rectangle(1, 1, width, height)
        b = bleed if not last_bad or index < len(sizes) - 1 else 0
        page[NameObject('/BleedBox')] = rectangle(1 - b, 1 - b, width + 2 * b, height + 2 * b)
        if resources is not None:
            page[NameObject('/Resources')] = resources
        if rotation:
            page.rotate(rotation)
    writer.write(path)
    return writer


class PdfPrepressTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'output.pdf'

    def error(self, **options):
        with self.assertRaises(CorelBridgeError) as caught:
            preflight_pdf(str(self.path), **options)
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_all_four_bleed_edges_and_trim_dimensions(self):
        production_pdf(self.path)
        before = self.path.read_bytes()
        result = preflight_pdf(str(self.path), [{'width': 8.5, 'height': 11}], .125)
        self.assertTrue(result['checks_passed'])
        self.assertEqual(result['pages'][0]['bleed_margins_inches'], {edge: .125 for edge in ('left', 'bottom', 'right', 'top')})
        self.assertEqual(result['source_sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(result['production_ready'])
        self.assertFalse(preflight_pdf(str(self.path), [{'width': 8.4, 'height': 11}], .125)['checks_passed'])

    def test_missing_explicit_trim_or_bleed_is_not_proof(self):
        write_pdf(self.path)
        result = preflight_pdf(str(self.path), [{'width': 8.5, 'height': 11}], .125)
        self.assertFalse(result['checks']['trim_sizes_match'])
        self.assertFalse(result['checks']['bleed_margins_match'])

    def test_last_page_mismatch_blocks_even_when_summaries_truncate(self):
        production_pdf(self.path, [(1, 2)] * 101, last_bad=True)
        result = preflight_pdf(str(self.path), [{'width': 1, 'height': 2}] * 101, .125)
        self.assertTrue(result['pages_truncated'])
        self.assertEqual(len(result['pages']), 100)
        self.assertFalse(result['checks_passed'])

    def test_nonzero_origins_and_rotation(self):
        production_pdf(self.path, [(2, 3)], rotation=90)
        result = preflight_pdf(str(self.path), [{'width': 3, 'height': 2}], .125)
        self.assertTrue(result['checks_passed'])
        self.assertEqual(len(result['pages'][0]['bleed_margins_inches']), 4)

    def test_containment_and_asymmetric_bleed_fail_checks(self):
        writer = production_pdf(self.path)
        page = writer.pages[0]
        page[NameObject('/BleedBox')] = rectangle(.9, .875, 8.725, 11.25)
        writer.write(self.path)
        self.assertFalse(preflight_pdf(str(self.path), expected_bleed_inches=.125)['checks_passed'])
        page[NameObject('/TrimBox')] = rectangle(-1, 0, 8.5, 11)
        writer.write(self.path)
        self.assertFalse(preflight_pdf(str(self.path))['checks']['box_relationships_passed'])

    def test_crop_clipping_and_zero_margin_cannot_pass_positive_bleed(self):
        writer = production_pdf(self.path)
        writer.pages[0][NameObject('/CropBox')] = rectangle(1, 1, 8.5, 11)
        writer.write(self.path)
        self.assertFalse(preflight_pdf(str(self.path))['checks_passed'])
        production_pdf(self.path, bleed=0)
        self.assertFalse(preflight_pdf(str(self.path), expected_bleed_inches=1/2540)['checks_passed'])

    def test_nested_spots_images_patterns_groups_and_overprint_defaults(self):
        tint = dictionary(FunctionType=NumberObject(2))
        spot = ArrayObject([NameObject('/Separation'), NameObject('/CutContour'), NameObject('/DeviceCMYK'), tint])
        image = DecodedStreamObject()
        image.set_data(b'synthetic pixels')
        image.update(dictionary(Subtype=NameObject('/Image'), Width=NumberObject(600), Height=NumberObject(300),
                                ColorSpace=NameObject('/DeviceRGB')))
        local = dictionary(ColorSpace=dictionary(Spot=spot), XObject=dictionary(Im=image),
                           ExtGState=dictionary(GS=dictionary(OP=BooleanObject(True), OPM=NumberObject(1))),
                           Pattern=dictionary(P=dictionary(Shading=dictionary(ColorSpace=NameObject('/DeviceGray')))))
        form = DecodedStreamObject()
        form.set_data(b'')
        form.update(dictionary(Subtype=NameObject('/Form'), Resources=local,
                               Group=dictionary(S=NameObject('/Transparency'), CS=NameObject('/DeviceCMYK'))))
        production_pdf(self.path, resources=dictionary(XObject=dictionary(Form=form)))
        result = preflight_pdf(str(self.path))['resource_inventory']
        self.assertEqual(result['color_space_families'], ['DeviceCMYK', 'DeviceGray', 'DeviceRGB', 'Separation'])
        self.assertEqual(result['spot_colorants'], ['/CutContour'])
        self.assertEqual(result['images'][0], {'width_pixels': 600, 'height_pixels': 300, 'image_mask': False})
        self.assertEqual(result['graphics_states'][0], {'stroke_overprint': True, 'fill_overprint': True, 'overprint_mode': 1})
        self.assertTrue(result['complete_for_supported_resources'])

    def test_shared_image_aliases_are_resolved_in_each_parent_scope(self):
        writer = PdfWriter()
        image = DecodedStreamObject()
        image.set_data(b'')
        image.update(dictionary(Subtype=NameObject('/Image'), Width=NumberObject(2), Height=NumberObject(2), ColorSpace=NameObject('/C')))
        reference = writer._add_object(image)
        for space in ('/DeviceRGB', '/DeviceCMYK'):
            page = writer.add_blank_page(72, 72)
            page[NameObject('/Resources')] = dictionary(ColorSpace=dictionary(C=NameObject(space)), XObject=dictionary(Im=reference))
        writer.write(self.path)
        result = preflight_pdf(str(self.path))['resource_inventory']
        self.assertEqual(result['color_space_families'], ['DeviceCMYK', 'DeviceRGB'])

    def test_device_n_process_and_icc_alternate_resources(self):
        profile = DecodedStreamObject()
        profile.set_data(b'synthetic ICC bytes')
        profile.update(dictionary(N=NumberObject(4), Alternate=NameObject('/DeviceCMYK')))
        tint = dictionary(FunctionType=NumberObject(2))
        attributes = dictionary(Process=dictionary(ColorSpace=NameObject('/DeviceRGB')))
        device_n = ArrayObject([NameObject('/DeviceN'), ArrayObject([NameObject('/Orange'), NameObject('/Violet')]),
                               ArrayObject([NameObject('/ICCBased'), profile]), tint, attributes])
        production_pdf(self.path, resources=dictionary(ColorSpace=dictionary(N=device_n)))
        inventory = preflight_pdf(str(self.path))['resource_inventory']
        self.assertEqual(inventory['color_space_families'], ['DeviceCMYK', 'DeviceN', 'DeviceRGB', 'ICCBased'])
        self.assertEqual(inventory['spot_colorants'], ['/Orange', '/Violet'])

    def test_soft_mask_resources_are_inspected(self):
        image = DecodedStreamObject()
        image.set_data(b'')
        image.update(dictionary(Subtype=NameObject('/Image'), Width=NumberObject(100), Height=NumberObject(100),
                                ImageMask=BooleanObject(True)))
        form = DecodedStreamObject()
        form.set_data(b'')
        form.update(dictionary(Subtype=NameObject('/Form'), Resources=dictionary(XObject=dictionary(Mask=image))))
        resources = dictionary(ExtGState=dictionary(GS=dictionary(SMask=dictionary(G=form))))
        production_pdf(self.path, resources=resources)
        inventory = preflight_pdf(str(self.path))['resource_inventory']
        self.assertEqual(inventory['image_resource_count'], 1)
        self.assertTrue(inventory['images'][0]['image_mask'])

    def test_output_intent_is_presence_only_and_declarations_are_informational(self):
        writer = production_pdf(self.path)
        profile = DecodedStreamObject()
        profile.set_data(b'not a valid ICC program')
        intent = dictionary(S=NameObject('/GTS_PDFX'), OutputConditionIdentifier=TextStringObject('Synthetic'),
                            DestOutputProfile=writer._add_object(profile))
        writer.root_object[NameObject('/OutputIntents')] = ArrayObject([intent])
        writer.add_metadata({'/GTS_PDFXVersion': 'PDF/X-4'})
        writer.write(self.path)
        result = preflight_pdf(str(self.path), require_output_intent=True)
        self.assertTrue(result['checks']['output_intent_present'])
        self.assertEqual(result['pdfx_declarations']['GTS_PDFXVersion'], 'PDF/X-4')
        self.assertFalse(result['production_ready'])
        del intent['/DestOutputProfile']
        writer.write(self.path)
        self.assertFalse(preflight_pdf(str(self.path), require_output_intent=True)['checks_passed'])

    def test_unknown_spaces_and_annotations_report_incomplete_scope(self):
        writer = production_pdf(self.path, resources=dictionary(ColorSpace=dictionary(C=NameObject('/Unrecognized'))))
        writer.pages[0][NameObject('/Annots')] = ArrayObject([dictionary(Subtype=NameObject('/Widget'))])
        writer.write(self.path)
        inventory = preflight_pdf(str(self.path))['resource_inventory']
        self.assertFalse(inventory['complete_for_supported_resources'])
        self.assertIn('annotation_appearances_not_scanned', inventory['unsupported_reasons'])

    def test_malformed_native_flags_are_refused_without_boolean_coercion(self):
        for key, value in (('OP', NameObject('/true')), ('op', NumberObject(1)), ('OPM', FloatObject(.5))):
            production_pdf(self.path, resources=dictionary(ExtGState=dictionary(GS=dictionary(**{key: value}))))
            self.error()

    def test_alias_cycles_and_resource_work_bounds_are_refused(self):
        production_pdf(self.path, resources=dictionary(ColorSpace=dictionary(A=NameObject('/B'), B=NameObject('/A'))))
        self.error()
        production_pdf(self.path, resources=dictionary(ColorSpace=dictionary(C=NameObject('/DeviceCMYK'))))
        with patch('corel_operator.pdf_prepress.MAX_RESOURCES', 2):
            self.error()

    def test_validation_precedes_file_access(self):
        for options in ({'expected_bleed_inches': True}, {'expected_bleed_inches': float('nan')},
                        {'expected_bleed_inches': -1}, {'expected_trim_sizes': []}, {'require_output_intent': 1}):
            self.error(**options)

    def test_summaries_truncate_after_every_resource_is_inspected(self):
        states = DictionaryObject({NameObject('/S' + str(i)): dictionary(OP=BooleanObject(i == 100)) for i in range(101)})
        production_pdf(self.path, resources=dictionary(ExtGState=states))
        inventory = preflight_pdf(str(self.path))['resource_inventory']
        self.assertTrue(inventory['graphics_states_truncated'])
        self.assertEqual(inventory['graphics_state_count'], 101)
        self.assertEqual(inventory['overprint_enabled_state_count'], 1)
        self.assertEqual(len(inventory['graphics_states']), 100)

    def test_local_wrapper_and_strict_result_schema(self):
        production_pdf(self.path)
        with patch.object(server, 'dispatcher', None):
            envelope = server.preflight_pdf(str(self.path), expected_bleed_inches=.125)
        self.assertTrue(envelope['ok'])
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool = next(t for t in registry['tools'] if t['name'] == 'preflight_pdf')
        validator = Draft202012Validator({'schema_definitions': registry['schema_definitions'], **tool['output_schema']})
        validator.validate(envelope)
        bad = copy.deepcopy(envelope)
        bad['data']['resource_inventory']['unexpected'] = True
        with self.assertRaises(ValidationError):
            validator.validate(bad)


class PdfBleedExportTests(unittest.TestCase):
    def setUp(self):
        # Reuse the established bridge/source fixture without inheriting its tests.
        self.fixture = pdf_fixture.PdfProductionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.bridge, self.path = self.fixture.bridge, self.fixture.path

    def test_unit_conversion_has_physical_anchor_and_quantization(self):
        self.assertEqual(BLEED_UNITS_PER_INCH, 2540)
        self.assertEqual(bleed_units(1 / 25.4), 100)  # 1 mm = 100 ten-micron units.
        self.assertEqual(bleed_units(.125), 318)
        for value in (True, -.1, 1.1, float('inf'), .00001):
            with self.assertRaises(CorelBridgeError):
                bleed_units(value)

    def test_nonzero_bleed_marks_and_overprint_controls_restore(self):
        snapshots = []
        def publish(path):
            snapshots.append(dict(self.fixture.settings.values))
            production_pdf(path, bleed=self.fixture.settings.Bleed / 2540)
        self.fixture.document.PublishToPDF = publish
        result = self.bridge.export_pdf_controlled(str(self.path), bleed_inches=.125, crop_marks=True,
                                                   registration_marks=True, preserve_overprints=False)
        self.assertEqual(snapshots[0]['Bleed'], 318)
        self.assertTrue(snapshots[0]['IncludeBleed'])
        self.assertTrue(snapshots[0]['CropMarks'])
        self.assertFalse(snapshots[0]['Overprints'])
        self.assertEqual(self.fixture.settings.values, self.fixture.settings.original)
        self.assertEqual(result['controls']['native_bleed_units'], 318)
        self.assertTrue(result['prepress']['checks_passed'])

    def test_wrong_or_missing_bleed_boxes_discard_staging_and_restore(self):
        for publish in (lambda p: production_pdf(p, bleed=0), lambda p: write_pdf(p)):
            self.fixture.document.PublishToPDF = publish
            error = self.fixture.error(ErrorCode.COREL_COM_ERROR, self.bridge.export_pdf_controlled, str(self.path), bleed_inches=.125)
            self.assertTrue(error.details['rollback']['verified'])
            self.assertEqual(self.fixture.settings.values, self.fixture.settings.original)
            self.assertFalse(self.path.exists())

    def test_production_controls_validate_before_settings_write(self):
        for options in ({'bleed_inches': float('nan')}, {'crop_marks': 1}, {'registration_marks': None}, {'preserve_overprints': 1}):
            self.fixture.error(ErrorCode.INVALID_ARGUMENT, self.bridge.export_pdf_controlled, str(self.path), **options)
        self.assertFalse(self.fixture.settings.writes)

    def test_ignored_bleed_control_refuses_publish(self):
        self.fixture.settings.ignore = 'Bleed'
        self.fixture.error(ErrorCode.COREL_COM_ERROR, self.bridge.export_pdf_controlled, str(self.path), bleed_inches=.125)
        self.assertFalse(self.fixture.published)

    def test_post_preflight_staging_change_is_refused_and_owned_output_removed(self):
        def changed(path, **options):
            result = preflight_pdf(path, **options)
            Path(path).write_bytes(b'%PDF-1.4\nchanged')
            return result
        with patch('corel_operator.pdf_bridge.preflight_pdf', changed):
            error = self.fixture.error(ErrorCode.COREL_COM_ERROR, self.bridge.export_pdf_controlled, str(self.path))
        self.assertTrue(error.details['rollback']['verified'])
        self.assertFalse(self.path.exists())

    def test_late_staging_cleanup_failure_removes_only_unchanged_owned_pdf(self):
        original = tempfile.TemporaryDirectory.cleanup
        calls = []
        def fail_once(directory):
            calls.append(1)
            if len(calls) == 1:
                raise OSError('synthetic cleanup failure')
            original(directory)
        with patch('corel_operator.pdf_bridge.tempfile.TemporaryDirectory.cleanup', fail_once):
            error = self.fixture.error(ErrorCode.COREL_COM_ERROR, self.bridge.export_pdf_controlled, str(self.path))
        self.assertTrue(error.details['rollback']['verified'])
        self.assertFalse(self.path.exists())

    def test_concurrent_output_content_edit_is_preserved_after_late_failure(self):
        original = tempfile.TemporaryDirectory.cleanup
        calls = []
        def fail_once(directory):
            calls.append(1)
            if len(calls) == 1:
                self.path.write_bytes(b'USER EDIT')
                raise OSError('synthetic cleanup failure')
            original(directory)
        with patch('corel_operator.pdf_bridge.tempfile.TemporaryDirectory.cleanup', fail_once):
            error = self.fixture.error(ErrorCode.COREL_COM_ERROR, self.bridge.export_pdf_controlled, str(self.path))
        self.assertEqual(self.path.read_bytes(), b'USER EDIT')
        self.assertFalse(error.details['rollback']['verified'])
        self.assertEqual(error.details['rollback']['output_cleanup']['reason'], 'output_content_changed')

    def test_final_output_readback_rejects_and_preserves_user_replacement_bytes(self):
        original = tempfile.TemporaryDirectory.cleanup
        def replace_after_cleanup(directory):
            original(directory)
            self.path.write_bytes(b'USER FINAL EDIT')
        with patch('corel_operator.pdf_bridge.tempfile.TemporaryDirectory.cleanup', replace_after_cleanup):
            error = self.fixture.error(ErrorCode.COREL_COM_ERROR, self.bridge.export_pdf_controlled, str(self.path))
        self.assertEqual(self.path.read_bytes(), b'USER FINAL EDIT')
        self.assertFalse(error.details['rollback']['verified'])


if __name__ == '__main__':
    unittest.main()
