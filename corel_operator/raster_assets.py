"""Local immutable raster snapshots and verified non-overwriting derivatives."""
from __future__ import annotations

import hashlib
import io
import math
import os
import re
import stat
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from .errors import CorelBridgeError, ErrorCode
from .vector_geometry import fingerprint

MAX_RASTER_BYTES = 128 * 1024 * 1024
MAX_RASTER_PIXELS = 64_000_000
MAX_RASTER_SIDE = 65535
MAX_ICC_BYTES = 8 * 1024 * 1024
SOURCE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif'}
OUTPUT_FORMATS = {'.png': 'PNG', '.tif': 'TIFF', '.tiff': 'TIFF'}
WORKING_MODES = {'RGB', 'RGBA', 'L', 'LA', 'CMYK'}
RESAMPLING = {'nearest': Image.Resampling.NEAREST, 'bicubic': Image.Resampling.BICUBIC, 'lanczos': Image.Resampling.LANCZOS}


def invalid(message):
    raise CorelBridgeError(message, ErrorCode.INVALID_ARGUMENT)


def raster_path(value, output=False):
    if type(value) is not str or not value or len(value) > 32767 or any(ord(c) < 32 for c in value) or value.startswith(('\\\\', '//')):
        invalid('Raster paths must be absolute local file paths without control characters.')
    path = Path(value).expanduser()
    if not path.is_absolute() or path.suffix.lower() not in (OUTPUT_FORMATS if output else SOURCE_EXTENSIONS):
        invalid('Choose an absolute supported raster path; derivatives must use PNG or TIFF.')
    if os.name == 'nt' and (path.is_reserved() or ':' in path.name):
        invalid('Raster device names and alternate streams are unsupported.')
    return path


def _identity(value):
    return value.st_dev, value.st_ino


def _snapshot(path):
    try:
        path = path.resolve(strict=True)
        raster_path(str(path))
        if not stat.S_ISREG(path.stat().st_mode):
            raise CorelBridgeError('Raster sources must be ordinary files.', ErrorCode.UNSAFE_PATH)
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_RASTER_BYTES:
                invalid('Raster sources must contain 1 byte to 128 MiB of bounded file data.')
            raw = stream.read(MAX_RASTER_BYTES + 1); after = os.fstat(stream.fileno())
        if len(raw) != before.st_size or len(raw) > MAX_RASTER_BYTES or _identity(before) != _identity(after) or before.st_mtime_ns != after.st_mtime_ns:
            invalid('Raster source changed while being read; inspect it again.')
        return path, raw, hashlib.sha256(raw).hexdigest()
    except CorelBridgeError:
        raise
    except Exception as exc:
        raise CorelBridgeError('Raster source could not be read safely.', ErrorCode.UNSAFE_PATH) from exc


def _pixel_hash(image):
    digest = hashlib.sha256(f'{image.mode}:{image.width}:{image.height}:'.encode('ascii'))
    rows = max(1, min(64, 1_000_000 // max(1, image.width * len(image.getbands()))))
    for top in range(0, image.height, rows):
        with image.crop((0, top, image.width, min(image.height, top + rows))) as tile:
            digest.update(tile.tobytes())
    return digest.hexdigest()


def _dpi(image):
    # TIFF decoders expose (1, 1) when resolution tags are absent. It is not DPI.
    if image.format == 'TIFF':
        tags = image.tag_v2
        if 282 not in tags or 283 not in tags or tags.get(296, 2) not in (2, 3):
            return None
    value = image.info.get('dpi')
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) < 2:
        invalid('Raster DPI metadata is unreadable.')
    result = [float(component) for component in value[:2]]
    if any(not math.isfinite(component) or not 0 < component <= 1_000_000 for component in result):
        invalid('Raster DPI metadata is invalid.')
    return {'x': result[0], 'y': result[1]}


def _load(path):
    resolved, raw, digest = _snapshot(path)
    normalized = None
    try:
        with Image.open(io.BytesIO(raw)) as header:
            if header.format not in {'PNG', 'JPEG', 'TIFF', 'BMP', 'GIF'}:
                invalid('The decoded source format is unsupported for this raster workflow.')
            width, height = header.size
            if not 1 <= width <= MAX_RASTER_SIDE or not 1 <= height <= MAX_RASTER_SIDE or width * height > MAX_RASTER_PIXELS:
                invalid('Raster dimensions exceed 65535 pixels per side or 64 million total pixels.')
            header.verify()
        with Image.open(io.BytesIO(raw)) as source:
            original_mode = source.mode; original_size = source.size; image_format = source.format
            orientation = source.getexif().get(274, 1)
            if type(orientation) is not int or orientation not in range(1, 9):
                invalid('Raster EXIF orientation is invalid.')
            dpi = _dpi(source)
            if dpi is not None and orientation in (5, 6, 7, 8):
                dpi = {'x': dpi['y'], 'y': dpi['x']}
            icc = source.info.get('icc_profile') or b''
            if type(icc) is not bytes or len(icc) > MAX_ICC_BYTES:
                invalid('ICC metadata must be bounded binary data of at most 8 MiB.')
            try:
                source.seek(1); multiple_frames = True
            except EOFError:
                multiple_frames = False
            source.seek(0); source.load()
            normalized = ImageOps.exif_transpose(source)
            mode = normalized.mode
            if mode == '1':
                converted = normalized.convert('L'); normalized.close(); normalized = converted
                mode = 'L'
            if mode == 'P':
                alpha = 'transparency' in normalized.info or getattr(normalized.palette, 'mode', None) == 'RGBA'
                converted = normalized.convert('RGBA' if alpha else 'RGB'); normalized.close(); normalized = converted
            elif mode in ('RGB', 'L') and 'transparency' in normalized.info:
                converted = normalized.convert('LA' if mode == 'L' else 'RGBA'); normalized.close(); normalized = converted
        alpha = None
        if 'A' in normalized.getbands():
            with normalized.getchannel('A') as channel:
                alpha = channel.getextrema()
        unsupported = []
        if multiple_frames: unsupported.append('multi_frame_source_requires_explicit_frame_workflow')
        if normalized.mode not in WORKING_MODES: unsupported.append('source_mode_requires_precision_or_color_workflow')
        data = {'schema': 'raster-asset-v1', 'path': str(resolved), 'bytes': len(raw), 'source_sha256': digest,
            'format': image_format, 'native_mode': original_mode, 'mode': normalized.mode,
            'native_size_pixels': {'width': original_size[0], 'height': original_size[1]},
            'size_pixels': {'width': normalized.width, 'height': normalized.height},
            'pixels_sha256': _pixel_hash(normalized), 'exif_orientation': orientation,
            'exif_orientation_applied': orientation != 1, 'has_multiple_frames': multiple_frames,
            'metadata_dpi': dpi, 'icc_profile': {'present': bool(icc), 'bytes': len(icc), 'sha256': hashlib.sha256(icc).hexdigest() if icc else None},
            'alpha': {'present': alpha is not None, 'minimum': alpha[0] if alpha else None, 'maximum': alpha[1] if alpha else None},
            'preparation_supported': not unsupported, 'unsupported_reasons': unsupported}
        data['fingerprint'] = fingerprint(data)
        return data, normalized, icc
    except CorelBridgeError:
        if normalized is not None: normalized.close()
        raise
    except Exception as exc:
        if normalized is not None: normalized.close()
        raise CorelBridgeError('Raster source could not be decoded completely.', ErrorCode.INVALID_ARGUMENT) from exc


def inspect_raster_asset(source_path):
    data, image, _ = _load(raster_path(source_path))
    image.close()
    return {'asset': data, 'verification_status': 'implemented_unverified',
        'warnings': ['Pixel hashes describe the decoded EXIF-normalized first frame; multi-frame/precision modes require separate preparation workflows. ICC/DPI metadata is not color or print approval.']}


def _source_matches(path, expected_sha, expected_path):
    resolved, _, current = _snapshot(path)
    return str(resolved) == expected_path and current == expected_sha


def _publish(stage, destination, state):
    expected_identity = _identity(stage.stat())
    state['publication_attempted'] = True
    try:
        os.link(stage, destination)
        state['output_identity'] = expected_identity
        if _identity(destination.stat()) != expected_identity:
            raise CorelBridgeError('Published raster ownership changed.', ErrorCode.INTERNAL_ERROR)
        return
    except FileExistsError as exc:
        raise CorelBridgeError('Raster output appeared during preparation and was preserved.', ErrorCode.OUTPUT_EXISTS) from exc
    except OSError:
        pass  # Some local filesystems do not support hard links; retain exclusive creation.
    with stage.open('rb') as source:
        if _identity(os.fstat(source.fileno())) != expected_identity:
            raise CorelBridgeError('Raster staging identity changed.', ErrorCode.INTERNAL_ERROR)
        try:
            with destination.open('xb') as target:
                state['output_identity'] = _identity(os.fstat(target.fileno()))
                copied = 0
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > MAX_RASTER_BYTES:
                        raise CorelBridgeError('Raster staging grew beyond the publication limit.', ErrorCode.INTERNAL_ERROR)
                    target.write(chunk)
        except FileExistsError as exc:
            raise CorelBridgeError('Raster output appeared during preparation and was preserved.', ErrorCode.OUTPUT_EXISTS) from exc


def _discard_owned(destination, state):
    identity = state.get('output_identity')
    if identity is None:
        if state.get('publication_attempted') and (destination.exists() or destination.is_symlink()):
            return {'attempted': False, 'verified': False, 'reason': 'output_ownership_unavailable'}
        return {'attempted': False, 'verified': True}
    try:
        current = destination.lstat()
    except FileNotFoundError:
        return {'attempted': False, 'verified': True}
    except Exception as exc:
        return {'attempted': False, 'verified': False, 'error_type': type(exc).__name__}
    if not stat.S_ISREG(current.st_mode) or _identity(current) != identity:
        return {'attempted': False, 'verified': False, 'reason': 'output_identity_changed'}
    try:
        destination.unlink()
        return {'attempted': True, 'verified': not destination.exists() and not destination.is_symlink()}
    except Exception as exc:
        return {'attempted': True, 'verified': False, 'error_type': type(exc).__name__}


def prepare_raster_asset(source_path, destination_path, expected_source_fingerprint, crop_box=None,
                         rotation_degrees=0, flip_horizontal=False, flip_vertical=False, target_size=None,
                         resize_mode='contain', allow_upscale=False, resampling='lanczos', output_dpi=None):
    source = raster_path(source_path); destination = raster_path(destination_path, output=True)
    if type(expected_source_fingerprint) is not str or re.fullmatch(r'[0-9a-f]{64}', expected_source_fingerprint) is None:
        invalid('Supply the current inspect_raster_asset source fingerprint.')
    if type(rotation_degrees) is not int or rotation_degrees not in (0, 90, 180, 270):
        invalid('rotation_degrees must be 0, 90, 180 or 270 counterclockwise.')
    if any(type(v) is not bool for v in (flip_horizontal, flip_vertical, allow_upscale)):
        invalid('Raster flip/upscale controls must be booleans.')
    if type(resize_mode) is not str or resize_mode not in ('contain', 'cover', 'stretch') or type(resampling) is not str or resampling not in RESAMPLING:
        invalid('Choose contain/cover/stretch and nearest/bicubic/lanczos resampling.')
    if output_dpi is not None and (type(output_dpi) not in (int, float) or not math.isfinite(output_dpi) or not 1 <= output_dpi <= 2400):
        invalid('output_dpi must be finite in [1, 2400] or null to preserve recognized metadata.')
    if destination.exists() or destination.is_symlink():
        raise CorelBridgeError('The raster output already exists and was preserved.', ErrorCode.OUTPUT_EXISTS)
    asset, image, icc = _load(source); stage_directory = None; state = {}; source_verified = False
    try:
        if asset['fingerprint'] != expected_source_fingerprint:
            invalid('Raster source changed; inspect it again before preparing a derivative.')
        if not asset['preparation_supported']:
            raise CorelBridgeError('This raster source needs a separate frame/precision workflow.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if OUTPUT_FORMATS[destination.suffix.lower()] == 'PNG' and image.mode == 'CMYK':
            invalid('Use TIFF to preserve CMYK; PNG conversion requires a separate explicit color workflow.')
        requested_crop = None
        if crop_box is not None:
            if type(crop_box) is not dict:
                invalid('crop_box requires integer left/top/right/bottom in EXIF-normalized pixels.')
            crop_box = dict(crop_box)
            if set(crop_box) != {'left', 'top', 'right', 'bottom'} or any(type(v) is not int for v in crop_box.values()):
                invalid('crop_box requires integer left/top/right/bottom in EXIF-normalized pixels.')
            if not 0 <= crop_box['left'] < crop_box['right'] <= image.width or not 0 <= crop_box['top'] < crop_box['bottom'] <= image.height:
                invalid('crop_box must be a nonempty region inside the normalized source.')
            requested_crop = dict(crop_box)
            cropped = image.crop(tuple(crop_box[k] for k in ('left', 'top', 'right', 'bottom'))); image.close(); image = cropped
        if rotation_degrees:
            rotated = image.transpose({90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_270}[rotation_degrees])
            image.close(); image = rotated
        for selected, method in ((flip_horizontal, Image.Transpose.FLIP_LEFT_RIGHT), (flip_vertical, Image.Transpose.FLIP_TOP_BOTTOM)):
            if selected:
                flipped = image.transpose(method); image.close(); image = flipped
        fitting_crop = None; upscaled = False
        before_resize = {'width': image.width, 'height': image.height}
        if target_size is not None:
            if type(target_size) is not dict:
                invalid('target_size needs 1-65535 integer width/height and at most 64 million pixels.')
            target_size = dict(target_size)
            if set(target_size) != {'width', 'height'} or any(type(v) is not int or not 1 <= v <= MAX_RASTER_SIDE for v in target_size.values()) or target_size['width'] * target_size['height'] > MAX_RASTER_PIXELS:
                invalid('target_size needs 1-65535 integer width/height and at most 64 million pixels.')
            tw, th = target_size['width'], target_size['height']
            if resize_mode == 'contain':
                scale = min(tw / image.width, th / image.height)
                tw, th = max(1, min(tw, round(image.width * scale))), max(1, min(th, round(image.height * scale)))
            elif resize_mode == 'cover':
                if image.width * th > image.height * tw:
                    cw = max(1, min(image.width, round(image.height * tw / th))); ch = image.height
                else:
                    cw = image.width; ch = max(1, min(image.height, round(image.width * th / tw)))
                left, top = (image.width - cw) // 2, (image.height - ch) // 2
                fitting_crop = {'left': left, 'top': top, 'right': left + cw, 'bottom': top + ch}
                cropped = image.crop((left, top, left + cw, top + ch)); image.close(); image = cropped
            upscaled = tw > image.width or th > image.height
            if upscaled and not allow_upscale:
                invalid('The requested fit upsamples pixels; allow_upscale must be explicit.')
            if (tw, th) != image.size:
                resized = image.resize((tw, th), RESAMPLING[resampling]); image.close(); image = resized
        dpi = asset['metadata_dpi']
        if dpi is not None and rotation_degrees in (90, 270): dpi = {'x': dpi['y'], 'y': dpi['x']}
        if output_dpi is not None: dpi = {'x': float(output_dpi), 'y': float(output_dpi)}
        pixels_hash = _pixel_hash(image)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = destination.parent.resolve(strict=True) / destination.name
        raster_path(str(destination), output=True)
        if destination.exists() or destination.is_symlink():
            raise CorelBridgeError('Raster output appeared during preparation and was preserved.', ErrorCode.OUTPUT_EXISTS)
        stage_directory = tempfile.TemporaryDirectory(prefix='corel-raster-', dir=destination.parent)
        stage = Path(stage_directory.name) / ('derivative' + destination.suffix.lower())
        options = {'icc_profile': icc} if icc else {}
        if dpi is not None: options['dpi'] = (dpi['x'], dpi['y'])
        if OUTPUT_FORMATS[destination.suffix.lower()] == 'TIFF': options['compression'] = 'tiff_lzw'
        image.info = {}  # Carry only the explicitly captured ICC/DPI fields.
        image.save(stage, format=OUTPUT_FORMATS[destination.suffix.lower()], **options)
        prepared, decoded, _ = _load(stage); decoded.close()
        def verify(result):
            if result['pixels_sha256'] != pixels_hash or result['mode'] != image.mode or result['size_pixels'] != {'width': image.width, 'height': image.height} or result['has_multiple_frames'] or result['exif_orientation'] != 1 or result['icc_profile'] != asset['icc_profile']:
                raise CorelBridgeError('Raster derivative pixel/mode/profile readback differs from the request.', ErrorCode.INTERNAL_ERROR)
            actual_dpi = result['metadata_dpi']
            if (dpi is None) != (actual_dpi is None) or dpi is not None and any(not math.isclose(actual_dpi[k], dpi[k], abs_tol=.02, rel_tol=0.) for k in ('x', 'y')):
                raise CorelBridgeError('Raster derivative DPI metadata did not reconcile.', ErrorCode.INTERNAL_ERROR)
        verify(prepared)
        source_verified = _source_matches(source, asset['source_sha256'], asset['path'])
        if not source_verified: invalid('Raster source changed before publication; inspect it again.')
        source_verified = False
        _publish(stage, destination, state)
        actual, decoded, _ = _load(destination); decoded.close(); verify(actual)
        if actual['source_sha256'] != prepared['source_sha256']:
            raise CorelBridgeError('Raster derivative changed during publication.', ErrorCode.INTERNAL_ERROR)
        current_output = destination.lstat()
        if not stat.S_ISREG(current_output.st_mode) or _identity(current_output) != state.get('output_identity'):
            raise CorelBridgeError('Raster output identity changed during readback.', ErrorCode.INTERNAL_ERROR)
        source_verified = _source_matches(source, asset['source_sha256'], asset['path'])
        if not source_verified: invalid('Raster source changed during publication; inspect it again.')
        stage_directory.cleanup(); stage_directory = None
        return {'prepared': True, 'source': asset, 'output': actual,
            'operations': {'crop_box': requested_crop, 'rotation_degrees': rotation_degrees, 'flip_horizontal': flip_horizontal,
                'flip_vertical': flip_vertical, 'before_resize_pixels': before_resize, 'target_size': target_size,
                'resize_mode': resize_mode, 'fitting_crop_box': fitting_crop, 'resampling': resampling, 'upscaled': upscaled},
            'source_preservation': {'source_written': False, 'byte_hash_verified': source_verified},
            'pixel_readback_verified': True, 'verification_status': 'implemented_unverified',
            'warnings': ['Derivatives retain recognized DPI and opaque ICC bytes; EXIF and other ancillary metadata are not copied. No ICC conversion or print approval is performed.'] +
                (['Upsampling creates pixels without establishing additional source detail.'] if upscaled else [])}
    except Exception as exc:
        cleanup = _discard_owned(destination, state)
        if stage_directory is not None:
            try: stage_directory.cleanup()
            except Exception as cleanup_error: cleanup['staging_error_type'] = type(cleanup_error).__name__; cleanup['verified'] = False
        raise CorelBridgeError(str(exc) if isinstance(exc, CorelBridgeError) else 'Raster preparation could not complete with verified pixel/source readback.',
            exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.UNSAFE_PATH,
            {'output_cleanup': cleanup, 'source_written': False, 'source_byte_hash_verified': source_verified}) from exc
    finally:
        image.close()
