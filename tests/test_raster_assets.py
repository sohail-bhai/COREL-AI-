from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin
from jsonschema import Draft202012Validator, ValidationError

from corel_operator import raster_assets as raster
from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.operation_records import OperationJournal


class RasterAssetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / 'source.png'
        self.output = self.root / 'output.png'
        self.image = Image.new('RGB', (4, 3))
        self.image.putdata([(i * 17, i * 11, i * 7) for i in range(12)])
        self.addCleanup(self.image.close)
        self.image.save(self.source)
        self.original = self.source.read_bytes()

    def inspect(self, path=None):
        return raster.inspect_raster_asset(str(path or self.source))['asset']

    def prepare(self, **kwargs):
        source = kwargs.pop('source_path', str(self.source))
        destination = kwargs.pop('destination_path', str(self.output))
        fingerprint = kwargs.pop('expected_source_fingerprint', self.inspect(Path(source))['fingerprint'])
        return raster.prepare_raster_asset(source, destination, fingerprint, **kwargs)

    def assertPixels(self, expected):
        with Image.open(self.output) as actual:
            self.assertEqual(actual.mode, expected.mode)
            self.assertEqual(actual.size, expected.size)
            self.assertEqual(actual.tobytes(), expected.tobytes())

    def assertRefused(self, code=ErrorCode.INVALID_ARGUMENT, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            self.prepare(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.original)
        return caught.exception

    def test_snapshot_and_pixel_fingerprints(self):
        asset = self.inspect()
        self.assertEqual(asset['source_sha256'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(asset['size_pixels'], {'width': 4, 'height': 3})
        self.assertEqual(asset['fingerprint'], self.inspect()['fingerprint'])
        self.assertTrue(asset['preparation_supported'])
        result = self.prepare()
        self.assertPixels(self.image)
        self.assertEqual(result['source_preservation'], {'source_written': False, 'byte_hash_verified': True})
        self.assertTrue(result['pixel_readback_verified'])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_crop_rotation_flip_order_exact(self):
        crop = {'left': 1, 'top': 0, 'right': 4, 'bottom': 2}
        result = self.prepare(crop_box=crop, rotation_degrees=90, flip_horizontal=True, flip_vertical=True)
        with self.image.crop((1, 0, 4, 2)) as first:
            with first.transpose(Image.Transpose.ROTATE_90) as second:
                with second.transpose(Image.Transpose.FLIP_LEFT_RIGHT) as third:
                    with third.transpose(Image.Transpose.FLIP_TOP_BOTTOM) as expected:
                        self.assertPixels(expected)
        self.assertEqual(result['operations']['crop_box'], crop)

    def test_all_quarter_rotations_exact(self):
        for degrees, method in [(0, None), (90, Image.Transpose.ROTATE_90), (180, Image.Transpose.ROTATE_180), (270, Image.Transpose.ROTATE_270)]:
            with self.subTest(degrees=degrees):
                self.prepare(rotation_degrees=degrees)
                with self.image.copy() if method is None else self.image.transpose(method) as expected:
                    self.assertPixels(expected)
                self.output.unlink()

    def test_all_exif_orientations_pixels_and_dpi(self):
        methods = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
                   4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                   6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE, 8: Image.Transpose.ROTATE_90}
        for orientation in range(1, 9):
            with self.subTest(orientation=orientation):
                exif = Image.Exif(); exif[274] = orientation
                self.image.save(self.source, exif=exif, dpi=(100, 200))
                asset = self.inspect()
                self.assertEqual(asset['exif_orientation'], orientation)
                dpi = asset['metadata_dpi']
                self.assertAlmostEqual(dpi['x'], 200 if orientation >= 5 else 100, delta=.02)
                self.assertAlmostEqual(dpi['y'], 100 if orientation >= 5 else 200, delta=.02)
                result = self.prepare()
                with self.image.copy() if orientation == 1 else self.image.transpose(methods[orientation]) as expected:
                    self.assertPixels(expected)
                self.assertEqual(result['output']['exif_orientation'], 1)
                self.output.unlink()

    def test_contain_has_no_padding(self):
        result = self.prepare(target_size={'width': 3, 'height': 3}, resampling='nearest')
        self.assertEqual(result['output']['size_pixels'], {'width': 3, 'height': 2})
        with self.image.resize((3, 2), Image.Resampling.NEAREST) as expected:
            self.assertPixels(expected)

    def test_cover_center_crop_exact(self):
        result = self.prepare(target_size={'width': 2, 'height': 3}, resize_mode='cover', resampling='nearest')
        self.assertEqual(result['operations']['fitting_crop_box'], {'left': 1, 'top': 0, 'right': 3, 'bottom': 3})
        with self.image.crop((1, 0, 3, 3)) as expected:
            self.assertPixels(expected)

    def test_stretch_explicit(self):
        self.prepare(target_size={'width': 2, 'height': 3}, resize_mode='stretch', resampling='nearest')
        with self.image.resize((2, 3), Image.Resampling.NEAREST) as expected:
            self.assertPixels(expected)

    def test_upscale_refused_and_explicit_upscale_reported(self):
        self.assertRefused(target_size={'width': 8, 'height': 6})
        result = self.prepare(target_size={'width': 8, 'height': 6}, allow_upscale=True)
        self.assertTrue(result['operations']['upscaled'])
        self.assertTrue(any('additional source detail' in item for item in result['warnings']))

    def test_cover_upscale_refused_after_fit(self):
        self.assertRefused(target_size={'width': 4, 'height': 3}, crop_box={'left': 0, 'top': 0, 'right': 2, 'bottom': 3}, resize_mode='cover')

    def test_modes_roundtrip_png_tiff(self):
        for mode in ('RGB', 'RGBA', 'L', 'LA', 'CMYK'):
            for extension in ('.png', '.tiff'):
                if mode == 'CMYK' and extension == '.png': continue
                with self.subTest(mode=mode, extension=extension):
                    source = self.root / 'mode.tiff'
                    output = self.root / ('mode-output' + extension)
                    with self.image.convert(mode) as expected:
                        expected.save(source)
                        result = self.prepare(source_path=str(source), destination_path=str(output))
                        self.assertEqual(result['output']['mode'], mode)
                        with Image.open(output) as actual:
                            self.assertEqual(actual.tobytes(), expected.tobytes())
                    output.unlink()

    def test_cmyk_png_refused(self):
        source = self.root / 'cmyk.tiff'
        with self.image.convert('CMYK') as image: image.save(source)
        self.assertRefused(source_path=str(source))

    def test_palette_transparency_normalized(self):
        with self.image.convert('P') as source:
            source.save(self.source, transparency=0)
        self.assertEqual(self.inspect()['mode'], 'RGBA')
        result = self.prepare()
        self.assertTrue(result['output']['alpha']['present'])
        self.assertEqual(result['output']['alpha']['minimum'], 0)

    def test_bitonal_normalized(self):
        with self.image.convert('1') as source: source.save(self.source)
        self.assertEqual(self.inspect()['mode'], 'L')
        self.assertEqual(self.prepare()['output']['mode'], 'L')

    def test_grayscale_transparency_retains_grayscale_channels(self):
        with Image.new('L', (2, 1)) as image:
            image.putdata([0, 255]); image.save(self.source, transparency=0, icc_profile=b'opaque gray profile')
        result = self.prepare()
        self.assertEqual(result['output']['mode'], 'LA')
        self.assertEqual(result['output']['alpha'], {'present': True, 'minimum': 0, 'maximum': 255})
        self.assertEqual(result['source']['icc_profile'], result['output']['icc_profile'])
        with Image.open(self.output) as image: self.assertEqual(image.tobytes(), bytes([0, 0, 255, 255]))

    def test_bitonal_transparency_preserved(self):
        with Image.new('1', (2, 1)) as image:
            image.putdata([0, 1]); image.save(self.source, transparency=0)
        result = self.prepare()
        self.assertEqual(result['output']['mode'], 'LA')
        self.assertEqual(result['output']['alpha'], {'present': True, 'minimum': 0, 'maximum': 255})

    def test_supported_encoded_formats(self):
        for extension, image_format in (('.jpg', 'JPEG'), ('.bmp', 'BMP'), ('.gif', 'GIF')):
            with self.subTest(image_format=image_format):
                source = self.root / ('other' + extension); self.image.save(source)
                self.assertEqual(self.inspect(source)['format'], image_format)
                result = self.prepare(source_path=str(source))
                self.assertTrue(result['pixel_readback_verified']); self.output.unlink()

    def test_disguised_unsupported_decoder_refused(self):
        self.image.save(self.source, format='PPM')
        with self.assertRaises(CorelBridgeError): self.inspect()

    def test_icc_dpi_preserved_exif_and_text_stripped(self):
        exif = Image.Exif(); exif[315] = 'Private author'; exif[274] = 1
        metadata = PngImagePlugin.PngInfo(); metadata.add_text('Private', 'Private content')
        self.image.save(self.source, icc_profile=b'opaque profile bytes', dpi=(100, 200), exif=exif, pnginfo=metadata)
        result = self.prepare(rotation_degrees=90)
        self.assertEqual(result['source']['icc_profile'], result['output']['icc_profile'])
        self.assertAlmostEqual(result['output']['metadata_dpi']['x'], 200, delta=.02)
        self.assertAlmostEqual(result['output']['metadata_dpi']['y'], 100, delta=.02)
        with Image.open(self.output) as actual:
            self.assertEqual(dict(actual.getexif()), {})
            self.assertNotIn('Private', actual.info)

    def test_explicit_dpi_no_pixel_change(self):
        result = self.prepare(output_dpi=300.125)
        self.assertAlmostEqual(result['output']['metadata_dpi']['x'], 300.125, delta=.02)
        self.assertPixels(self.image)

    def test_tiff_without_resolution_tags_has_no_dpi(self):
        self.output = self.root / 'output.tif'
        result = self.prepare()
        self.assertIsNone(result['output']['metadata_dpi'])

    def test_multiframe_inspectable_preparation_refused(self):
        source = self.root / 'animated.gif'
        with self.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT) as other:
            self.image.save(source, save_all=True, append_images=[other])
        self.assertTrue(self.inspect(source)['has_multiple_frames'])
        self.assertRefused(ErrorCode.UNSUPPORTED_IN_PROFILE, source_path=str(source))

    def test_precision_inspectable_preparation_refused(self):
        source = self.root / 'precision.tiff'
        with Image.new('I;16', (2, 2), 1234) as image: image.save(source)
        self.assertFalse(self.inspect(source)['preparation_supported'])
        self.assertRefused(ErrorCode.UNSUPPORTED_IN_PROFILE, source_path=str(source))

    def test_malformed_arguments_refused(self):
        cases = [{'rotation_degrees': True}, {'rotation_degrees': 45}, {'flip_horizontal': 1},
                 {'flip_vertical': 'true'}, {'allow_upscale': 1}, {'resize_mode': []}, {'resampling': {}},
                 {'output_dpi': float('nan')}, {'output_dpi': True}, {'output_dpi': 2401},
                 {'crop_box': []}, {'crop_box': {'left': 0, 'top': 0, 'right': 5, 'bottom': 3}},
                 {'crop_box': {'left': False, 'top': 0, 'right': 2, 'bottom': 3}},
                 {'target_size': []}, {'target_size': {'width': 2}}, {'target_size': {'width': 0, 'height': 1}},
                 {'target_size': {'width': True, 'height': 1}}, {'target_size': {'width': 65535, 'height': 65535}},
                 {'expected_source_fingerprint': 'bad'}, {'expected_source_fingerprint': '0' * 64}]
        for arguments in cases:
            with self.subTest(arguments=arguments): self.assertRefused(**arguments)

    def test_stale_source_fingerprint(self):
        fingerprint = self.inspect()['fingerprint']
        self.image.save(self.source, dpi=(300, 300))
        with self.assertRaises(CorelBridgeError): self.prepare(expected_source_fingerprint=fingerprint)
        self.assertFalse(self.output.exists())

    def test_path_validation(self):
        for value in ('relative.png', '//server/share/image.png', '\\\\server\\share\\image.png', 'C:/image.png\x00', '', 3):
            with self.subTest(path=value), self.assertRaises(CorelBridgeError): raster.raster_path(value)
        if os.name == 'nt':
            for value in ('C:/CON.png', 'C:/image:stream.png'):
                with self.subTest(path=value), self.assertRaises(CorelBridgeError): raster.raster_path(value)

    def test_missing_and_corrupt_source_redacted(self):
        for path in (self.root / 'missing.png', self.source):
            if path == self.source: path.write_bytes(b'corrupt')
            with self.assertRaises(CorelBridgeError) as caught: self.inspect(path)
            self.assertNotIn(str(self.root), str(caught.exception))

    def test_capacity_limits(self):
        with patch.object(raster, 'MAX_RASTER_BYTES', 10):
            with self.assertRaises(CorelBridgeError): self.inspect()
        with patch.object(raster, 'MAX_RASTER_PIXELS', 10):
            with self.assertRaises(CorelBridgeError): self.inspect()
        self.image.save(self.source, icc_profile=b'123456')
        with patch.object(raster, 'MAX_ICC_BYTES', 3):
            with self.assertRaises(CorelBridgeError): self.inspect()

    def test_existing_destination_preserved(self):
        self.output.write_bytes(b'client data')
        with self.assertRaises(CorelBridgeError) as caught: self.prepare()
        self.assertEqual(caught.exception.code, ErrorCode.OUTPUT_EXISTS)
        self.assertEqual(self.output.read_bytes(), b'client data')

    def test_destination_race_preserved(self):
        publish = raster._publish
        def race(stage, destination, state):
            destination.write_bytes(b'client race')
            return publish(stage, destination, state)
        with patch.object(raster, '_publish', side_effect=race):
            with self.assertRaises(CorelBridgeError) as caught: self.prepare()
        self.assertEqual(caught.exception.code, ErrorCode.OUTPUT_EXISTS)
        self.assertEqual(self.output.read_bytes(), b'client race')

    def test_exclusive_copy_fallback(self):
        with patch.object(raster.os, 'link', side_effect=OSError('unsupported filesystem')):
            self.assertTrue(self.prepare()['pixel_readback_verified'])
        self.assertPixels(self.image)

    def test_source_change_before_publication(self):
        def changed(*args):
            self.source.write_bytes(b'changed externally')
            return False
        with patch.object(raster, '_source_matches', side_effect=changed):
            with self.assertRaises(CorelBridgeError): self.prepare()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), b'changed externally')

    def test_source_change_after_publication_owned_output_removed(self):
        publish = raster._publish
        def changed(stage, destination, state):
            publish(stage, destination, state)
            self.source.write_bytes(b'changed externally')
        with patch.object(raster, '_publish', side_effect=changed):
            with self.assertRaises(CorelBridgeError) as caught: self.prepare()
        self.assertFalse(self.output.exists())
        self.assertTrue(caught.exception.details['output_cleanup']['verified'])

    def test_source_alias_retarget_detected(self):
        alias = self.root / 'alias.png'
        second = self.root / 'second.png'; second.write_bytes(self.original)
        snapshot = raster._snapshot
        mapping = [self.source]
        def aliased_snapshot(path):
            return snapshot(mapping[0] if path == alias else path)
        publish = raster._publish
        def retarget(stage, destination, state):
            publish(stage, destination, state); mapping[0] = second
        with patch.object(raster, '_snapshot', side_effect=aliased_snapshot):
            fingerprint = self.inspect(alias)['fingerprint']
            with patch.object(raster, '_publish', side_effect=retarget):
                with self.assertRaises(CorelBridgeError):
                    self.prepare(source_path=str(alias), expected_source_fingerprint=fingerprint)
        self.assertFalse(self.output.exists())
        self.assertEqual(second.read_bytes(), self.original)

    def test_output_replacement_preserved_on_readback_failure(self):
        publish = raster._publish
        def replaced(stage, destination, state):
            publish(stage, destination, state)
            destination.rename(self.root / 'owned-moved.png')
            destination.write_bytes(b'unrelated replacement')
        with patch.object(raster, '_publish', side_effect=replaced):
            with self.assertRaises(CorelBridgeError) as caught: self.prepare()
        self.assertEqual(self.output.read_bytes(), b'unrelated replacement')
        self.assertFalse(caught.exception.details['output_cleanup']['verified'])

    def test_unknown_output_receipt_preserved(self):
        def lost_receipt(stage, destination, state):
            state['publication_attempted'] = True
            destination.write_bytes(b'unknown output')
            raise OSError('Private filesystem detail')
        with patch.object(raster, '_publish', side_effect=lost_receipt):
            with self.assertRaises(CorelBridgeError) as caught: self.prepare()
        self.assertEqual(self.output.read_bytes(), b'unknown output')
        self.assertEqual(caught.exception.details['output_cleanup']['reason'], 'output_ownership_unavailable')
        self.assertNotIn('Private', str(caught.exception))

    def test_cleanup_stat_error_is_explicit(self):
        with patch.object(Path, 'lstat', side_effect=PermissionError('private')):
            result = raster._discard_owned(self.output, {'output_identity': (1, 2)})
        self.assertFalse(result['verified'])
        self.assertEqual(result['error_type'], 'PermissionError')

    def test_cleanup_delete_error_is_explicit(self):
        self.output.write_bytes(b'owned')
        state = {'output_identity': raster._identity(self.output.stat())}
        with patch.object(Path, 'unlink', side_effect=PermissionError('private')):
            result = raster._discard_owned(self.output, state)
        self.assertFalse(result['verified'])
        self.assertEqual(self.output.read_bytes(), b'owned')

    def test_staging_directory_removed(self):
        self.prepare()
        self.assertEqual(list(self.root.glob('corel-raster-*')), [])

    def test_missing_source_after_publication_not_reported_verified(self):
        publish = raster._publish
        def removed(stage, destination, state):
            publish(stage, destination, state); self.source.unlink()
        with patch.object(raster, '_publish', side_effect=removed):
            with self.assertRaises(CorelBridgeError) as caught: self.prepare()
        self.assertFalse(caught.exception.details['source_byte_hash_verified'])
        self.assertFalse(self.output.exists())

    def test_identical_output_replacement_detected_and_preserved(self):
        publish = raster._publish
        def replaced(stage, destination, state):
            publish(stage, destination, state)
            raw = destination.read_bytes()
            destination.rename(self.root / 'owned-moved.png')
            destination.write_bytes(raw)
        with patch.object(raster, '_publish', side_effect=replaced):
            with self.assertRaises(CorelBridgeError) as caught: self.prepare()
        self.assertTrue(self.output.exists())
        self.assertEqual(caught.exception.details['output_cleanup']['reason'], 'output_identity_changed')

    def test_staging_pixel_readback_mismatch_refused(self):
        load = raster._load
        def mismatched(path):
            asset, image, icc = load(path)
            if path.name.startswith('derivative'):
                asset['pixels_sha256'] = '0' * 64
            return asset, image, icc
        with patch.object(raster, '_load', side_effect=mismatched): self.assertRefused(ErrorCode.INTERNAL_ERROR)
        self.assertEqual(list(self.root.glob('corel-raster-*')), [])

    def test_staging_dpi_readback_mismatch_refused(self):
        load = raster._load
        def mismatched(path):
            asset, image, icc = load(path)
            if path.name.startswith('derivative'):
                asset['metadata_dpi'] = {'x': 1., 'y': 1.}
            return asset, image, icc
        with patch.object(raster, '_load', side_effect=mismatched): self.assertRefused(ErrorCode.INTERNAL_ERROR, output_dpi=300)

    def test_copy_fallback_destination_race_preserved(self):
        def race(*args):
            self.output.write_bytes(b'client race')
            raise OSError('unsupported')
        with patch.object(raster.os, 'link', side_effect=race):
            with self.assertRaises(CorelBridgeError) as caught: self.prepare()
        self.assertEqual(caught.exception.code, ErrorCode.OUTPUT_EXISTS)
        self.assertEqual(self.output.read_bytes(), b'client race')

    def test_tiff_exif_not_carried(self):
        source = self.root / 'tagged.tif'; self.output = self.root / 'output.tif'
        exif = Image.Exif(); exif[315] = 'Private author'
        self.image.save(source, exif=exif, dpi=(300, 300))
        self.prepare(source_path=str(source))
        with Image.open(self.output) as image:
            self.assertNotIn(315, image.getexif())

    def validator(self, name, direction):
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool = next(tool for tool in registry['tools'] if tool['name'] == name)
        return Draft202012Validator({**tool[direction + '_schema'], 'schema_definitions': registry['schema_definitions']})

    def test_direct_server_envelopes_without_dispatcher(self):
        with patch.object(server, 'dispatcher') as dispatcher:
            inspected = server.inspect_raster_asset(str(self.source))
            result = server.prepare_raster_asset(str(self.source), str(self.output), inspected['data']['asset']['fingerprint'])
            refused = server.prepare_raster_asset(str(self.source), str(self.output), inspected['data']['asset']['fingerprint'])
        self.assertTrue(inspected['ok']); self.assertTrue(result['ok'])
        self.assertFalse(refused['ok']); self.assertEqual(refused['error']['code'], 'OUTPUT_EXISTS')
        self.assertIsNone(result['target_document'])
        dispatcher.assert_not_called(); self.assertEqual(dispatcher.mock_calls, [])
        for name, value in [('inspect_raster_asset', inspected), ('prepare_raster_asset', result), ('prepare_raster_asset', refused)]:
            self.validator(name, 'output').validate(value)

    def test_strict_schema_rejects_bad_nested_request(self):
        validator = self.validator('prepare_raster_asset', 'input')
        request = {'source_path': str(self.source), 'destination_path': str(self.output), 'expected_source_fingerprint': self.inspect()['fingerprint']}
        validator.validate(request)
        for key, value in [('crop_box', {'left': 0, 'top': 0, 'right': 2, 'bottom': 3, 'extra': 1}),
                           ('target_size', {'width': True, 'height': 1}), ('rotation_degrees', 45), ('output_dpi', 2401), ('unknown', True)]:
            with self.subTest(key=key), self.assertRaises(ValidationError): validator.validate({**request, key: value})

    def test_strict_schema_rejects_false_preservation_success(self):
        result = server.prepare_raster_asset(str(self.source), str(self.output), self.inspect()['fingerprint'])
        result['data']['source_preservation']['byte_hash_verified'] = False
        with self.assertRaises(ValidationError): self.validator('prepare_raster_asset', 'output').validate(result)

    def test_local_failure_does_not_enter_native_recovery(self):
        before = server.dispatcher.snapshot()
        with patch.object(raster.Image.Image, 'save', side_effect=OSError('Private filesystem detail')):
            result = server.prepare_raster_asset(str(self.source), str(self.output), self.inspect()['fingerprint'])
        self.assertFalse(result['ok']); self.assertNotIn('Private', json.dumps(result))
        self.assertEqual(server.dispatcher.snapshot(), before)
        self.assertFalse(self.output.exists())

    def test_operation_records_do_not_store_paths_pixels_or_fingerprint(self):
        directory = self.root / 'records'
        journal = OperationJournal(directory); self.addCleanup(journal.close)
        with patch.object(server, 'operation_journal', journal):
            inspected = server.inspect_raster_asset(str(self.source))
            prepared = server.prepare_raster_asset(str(self.source), str(self.output), inspected['data']['asset']['fingerprint'])
        lines = [line for path in directory.glob('*.jsonl') for line in path.read_text(encoding='utf-8').splitlines()]
        records = [json.loads(line) for line in lines]
        self.assertEqual([record['event'] for record in records], ['requested', 'returned', 'requested', 'returned'])
        self.assertEqual(records[0]['operation_id'], inspected['operation_id'])
        self.assertEqual(records[2]['operation_id'], prepared['operation_id'])
        serialized = '\n'.join(lines)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn(inspected['data']['asset']['fingerprint'], serialized)
        self.assertNotIn('pixels_sha256', serialized)


if __name__ == '__main__': unittest.main()
