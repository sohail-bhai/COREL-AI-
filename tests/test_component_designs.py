import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from corel_operator import component_designs as components
from corel_operator.errors import CorelBridgeError, ErrorCode


class ComponentDesignTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.base = self.root / 'base.json'
        self.next = self.root / 'next.json'
        self.plan = {'version': '1.0', 'name': 'Card', 'canvas': {'width_inches': 4., 'height_inches': 2.},
            'elements': [{'id': 'background', 'type': 'rectangle', 'x_inches': 0., 'y_inches': 0.,
                          'width_inches': 4., 'height_inches': 2., 'fill': {'red': 20, 'green': 30, 'blue': 40}},
                         {'id': 'name', 'type': 'text', 'x_inches': 1., 'y_inches': 1., 'text': 'First',
                          'font_size_points': 24., 'font': 'Arial'}]}

    def create(self):
        return components.create_component_design(self.plan, str(self.base))

    def revise(self, created=None, **kwargs):
        created = created or self.create()
        kwargs.setdefault('component_id', 'name')
        kwargs.setdefault('replacement_element', dict(self.plan['elements'][1], text='Second'))
        return components.revise_component_design(str(self.base), str(self.next), created['fingerprint'], **kwargs)

    def add_asset(self, pixels=100):
        path = self.root / 'portrait.png'
        with Image.new('RGB', (pixels, pixels), 'red') as image:
            image.save(path)
        self.plan['elements'].append({'id': 'portrait', 'type': 'artwork', 'file_path': str(path),
            'x_inches': 2., 'y_inches': 0., 'width_inches': 1., 'height_inches': 1.})
        return path

    def test_create_and_inspect_persist_exact_editable_component_plan(self):
        created = self.create()
        self.assertEqual(created['plan'], self.plan)
        inspected = components.inspect_component_design(str(self.base))
        self.assertEqual(inspected['fingerprint'], created['fingerprint'])
        self.assertEqual(inspected['history'][0]['action'], 'create')
        self.assertEqual(inspected['history_count'], 1)

    def test_one_component_replacement_preserves_source_and_other_parts(self):
        created = self.create()
        raw = self.base.read_bytes()
        result = self.revise(created)
        self.assertEqual(self.base.read_bytes(), raw)
        self.assertEqual(result['plan']['elements'][0], self.plan['elements'][0])
        self.assertEqual(result['plan']['elements'][1]['text'], 'Second')
        self.assertEqual(result['changed_component_ids'], ['name'])
        self.assertEqual(result['revision'], 1)

    def test_restore_creates_a_new_revision_and_preserves_all_older_files(self):
        created = self.create()
        revised = self.revise(created)
        raw = self.next.read_bytes()
        restored = components.revise_component_design(str(self.next), str(self.root / 'restored.json'),
            revised['fingerprint'], restore_revision=0)
        self.assertEqual(restored['plan'], self.plan)
        self.assertEqual(restored['revision'], 2)
        self.assertEqual(self.next.read_bytes(), raw)

    def test_stale_fingerprint_refused_without_output(self):
        self.create()
        with self.assertRaises(CorelBridgeError): self.revise({'fingerprint': 'a' * 64})
        self.assertFalse(self.next.exists())

    def test_missing_component_and_mismatched_replacement_ids_refused(self):
        created = self.create()
        for key, replacement in [('missing', {'id': 'missing', 'type': 'text', 'text': 'New', 'x_inches': 1, 'y_inches': 1}),
                                 ('name', dict(self.plan['elements'][1], id='different'))]:
            with self.assertRaises(CorelBridgeError): self.revise(created, component_id=key, replacement_element=replacement)
        self.assertFalse(self.next.exists())

    def test_unknown_or_nonfinite_plan_data_refused(self):
        for field, value in [('unknown', 'x'), ('width_inches', float('nan'))]:
            plan = copy.deepcopy(self.plan)
            plan['canvas'][field] = value
            with self.assertRaises(CorelBridgeError): components.create_component_design(plan, str(self.base))
        self.assertFalse(self.base.exists())

    def test_existing_output_is_never_overwritten(self):
        self.base.write_bytes(b'User work')
        with self.assertRaises(CorelBridgeError) as caught: self.create()
        self.assertEqual(caught.exception.code, ErrorCode.OUTPUT_EXISTS)
        self.assertEqual(self.base.read_bytes(), b'User work')

    def test_malformed_or_forged_history_refused(self):
        self.create()
        value = json.loads(self.base.read_text())
        value['history'][0]['plan']['elements'][1]['text'] = 'Forged'
        self.base.write_text(json.dumps(value))
        with self.assertRaises(CorelBridgeError): components.inspect_component_design(str(self.base))

    def test_raster_receipts_detect_changed_source(self):
        asset = self.add_asset()
        self.create()
        with Image.new('RGB', (100, 100), 'blue') as image: image.save(asset)
        with self.assertRaises(CorelBridgeError): components.inspect_component_design(str(self.base))

    def test_native_vector_import_is_not_claimed_as_inspected_raster(self):
        asset = self.root / 'art.svg'
        asset.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.plan['elements'].append({'id': 'logo', 'type': 'artwork', 'file_path': str(asset)})
        with self.assertRaises(CorelBridgeError) as caught: self.create()
        self.assertEqual(caught.exception.code, ErrorCode.UNSUPPORTED_IN_PROFILE)

    def test_resize_preserves_aspect_ratio_and_centers_layout(self):
        self.plan['elements'][0]['outline'] = {'width_points': 2.}
        created = self.create()
        result = components.resize_component_design(str(self.base), str(self.next), created['fingerprint'], 8., 8.)
        background, text = result['plan']['elements']
        self.assertEqual((background['width_inches'], background['height_inches'], background['y_inches']), (8., 4., 2.))
        self.assertEqual(background['outline']['width_points'], 4.)
        self.assertEqual((text['x_inches'], text['y_inches'], text['font_size_points']), (2., 4., 48.))
        self.assertEqual(self.plan['elements'][1]['font_size_points'], 24.)

    def test_resize_rejects_unreadable_font_before_publication(self):
        created = self.create()
        with self.assertRaises(CorelBridgeError):
            components.resize_component_design(str(self.base), str(self.next), created['fingerprint'], 1., .5, minimum_font_size_points=8.)
        self.assertFalse(self.next.exists())

    def test_resize_identifies_only_images_needing_more_pixels(self):
        self.add_asset(100)
        created = self.create()
        result = components.resize_component_design(str(self.base), str(self.next), created['fingerprint'], 8., 4., minimum_image_dpi=300.)
        self.assertEqual(result['requires_higher_resolution_components'], ['portrait'])
        self.assertIn('native_composition', result['unchecked_checks'])

    def test_resize_refuses_unknown_artwork_placement(self):
        self.add_asset()
        del self.plan['elements'][-1]['width_inches']
        created = self.create()
        with self.assertRaises(CorelBridgeError):
            components.resize_component_design(str(self.base), str(self.next), created['fingerprint'], 8., 4.)

    def test_generation_request_is_local_literal_and_targets_one_component(self):
        created = self.create()
        prompt = 'Portrait; $(do not execute) and preserve other components'
        result = components.prepare_component_generation(str(self.base), 'name', created['fingerprint'], prompt, str(self.next))
        self.assertFalse(result['network_request_sent'])
        self.assertFalse(result['generated'])
        self.assertFalse(result['provider_connected'])
        request = json.loads(self.next.read_text())
        self.assertEqual(request['component_id'], 'name')
        self.assertEqual(request['prompt'], prompt)
        self.assertEqual(request['source_design_fingerprint'], created['fingerprint'])

    def test_generation_request_rejects_invalid_bounds_and_unknown_component(self):
        created = self.create()
        for key, width in [('unknown', 1024), ('name', True), ('name', 0), ('name', 16385)]:
            with self.assertRaises(CorelBridgeError): components.prepare_component_generation(
                str(self.base), key, created['fingerprint'], 'Prompt', str(self.next), width_pixels=width)
        self.assertFalse(self.next.exists())

    def test_source_change_before_publication_preserved(self):
        created = self.create()
        original = components._source_unchanged
        def changed(source):
            self.base.write_bytes(b'Concurrent user edit')
            original(source)
        with patch.object(components, '_source_unchanged', changed):
            with self.assertRaises(CorelBridgeError): self.revise(created)
        self.assertEqual(self.base.read_bytes(), b'Concurrent user edit')
        self.assertFalse(self.next.exists())

    def test_output_creation_race_preserves_foreign_file(self):
        original = components.os.link
        def race(stage, destination):
            destination.write_bytes(b'User output')
            return original(stage, destination)
        with patch.object(components.os, 'link', race):
            with self.assertRaises(CorelBridgeError) as caught: self.create()
        self.assertEqual(caught.exception.code, ErrorCode.OUTPUT_EXISTS)
        self.assertEqual(self.base.read_bytes(), b'User output')

    def test_late_source_failure_cleans_only_exact_owned_output(self):
        created = self.create()
        original, count = components._source_unchanged, 0
        def changed(source):
            nonlocal count
            count += 1
            if count == 2: self.base.write_bytes(b'Concurrent edit')
            original(source)
        with patch.object(components, '_source_unchanged', changed):
            with self.assertRaises(CorelBridgeError) as caught: self.revise(created)
        self.assertTrue(caught.exception.details['cleanup_verified'])
        self.assertFalse(self.next.exists())
        self.assertEqual(self.base.read_bytes(), b'Concurrent edit')

    def test_late_output_edit_is_preserved_and_cleanup_is_uncertain(self):
        created = self.create()
        original, count = components._source_unchanged, 0
        def changed(source):
            nonlocal count
            count += 1
            if count == 2:
                self.next.write_bytes(b'Concurrent output edit')
                raise CorelBridgeError('Synthetic late failure')
            original(source)
        with patch.object(components, '_source_unchanged', changed):
            with self.assertRaises(CorelBridgeError) as caught: self.revise(created)
        self.assertFalse(caught.exception.details['cleanup_verified'])
        self.assertEqual(self.next.read_bytes(), b'Concurrent output edit')

    def test_historical_asset_change_blocks_restore(self):
        asset = self.add_asset()
        created = self.create()
        replacement = self.root / 'other.png'
        with Image.new('RGB', (100, 100), 'green') as image: image.save(replacement)
        element = dict(self.plan['elements'][-1], file_path=str(replacement))
        revised = self.revise(created, component_id='portrait', replacement_element=element)
        with Image.new('RGB', (100, 100), 'blue') as image: image.save(asset)
        with self.assertRaises(CorelBridgeError): components.revise_component_design(
            str(self.next), str(self.root / 'restore.json'), revised['fingerprint'], restore_revision=0)

    def test_relative_network_and_non_json_paths_refused(self):
        for path in ('relative.json', '//host/share/test.json', str(self.root / 'file.txt')):
            with self.assertRaises(CorelBridgeError): components.create_component_design(self.plan, path)

    def test_history_and_byte_limits_refuse_before_new_output(self):
        created = self.create()
        with patch.object(components, 'MAX_REVISIONS', 1):
            with self.assertRaises(CorelBridgeError): self.revise(created)
        with patch.object(components, 'MAX_JSON_BYTES', 100):
            with self.assertRaises(CorelBridgeError): components.create_component_design(self.plan, str(self.next))
        self.assertFalse(self.next.exists())

    def test_network_asset_refused_before_general_file_preflight(self):
        self.plan['elements'].append({'id': 'foreign', 'type': 'artwork', 'file_path': '//host/share/image.png'})
        with patch.object(components, 'validate_design_plan') as general_preflight:
            with self.assertRaises(CorelBridgeError): self.create()
            general_preflight.assert_not_called()

    def test_ambiguous_duplicate_json_keys_are_refused(self):
        self.create()
        raw = self.base.read_text()
        self.base.write_text(raw.replace('{', '{"schema":"ambiguous",', 1))
        with self.assertRaises(CorelBridgeError): components.inspect_component_design(str(self.base))

    def test_actual_success_outputs_and_request_schemas(self):
        from jsonschema import Draft202012Validator, ValidationError
        from corel_operator import server
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text())
        tools = {tool['name']: tool for tool in registry['tools']}
        created = server.create_component_design(self.plan, str(self.base))
        inspected = server.inspect_component_design(str(self.base))
        revised = server.revise_component_design(str(self.base), str(self.next), created['data']['fingerprint'],
            component_id='name', replacement_element=dict(self.plan['elements'][1], text='New'))
        resized = server.resize_component_design(str(self.base), str(self.root / 'large.json'),
            created['data']['fingerprint'], 8., 4.)
        prepared = server.prepare_component_generation(str(self.base), 'name', created['data']['fingerprint'],
            'Prompt', str(self.root / 'request.json'))
        for result in (created, inspected, revised, resized, prepared):
            self.assertTrue(result['ok'])
            schema = dict(schema_definitions=registry['schema_definitions'], allOf=[tools[result['tool']]['output_schema']])
            Draft202012Validator(schema).validate(result)
            broken = copy.deepcopy(result)
            broken['data']['extra'] = True
            with self.assertRaises(ValidationError): Draft202012Validator(schema).validate(broken)
        schema = dict(schema_definitions=registry['schema_definitions'], allOf=[tools['revise_component_design']['input_schema']])
        request = registry['tool_examples']['revise_component_design']['request']
        Draft202012Validator(schema).validate(request)
        with self.assertRaises(ValidationError): Draft202012Validator(schema).validate(dict(request, restore_revision=0))
