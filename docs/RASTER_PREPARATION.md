# Source-preserving raster preparation

Status: `implemented_unverified`. These two local tools do not access CorelDRAW
or change native worker/recovery state. Consolidated MCP client verification,
Corel import and visual/artifact review remain deferred by the user.

`inspect_raster_asset(source_path)` reads a bounded immutable byte snapshot and
reports encoded source SHA-256, EXIF-normalized decoded pixel SHA-256, canonical
path, dimensions, mode, alpha range, first-frame status and opaque ICC/DPI
metadata. Its fingerprint binds the full summary to the observed source.

`prepare_raster_asset(source_path, destination_path,
expected_source_fingerprint, ...)` requires the current inspection fingerprint.
It creates a distinct PNG/TIFF output, refuses an existing destination, and
never writes source pixels or metadata. It applies operations in this order:

1. EXIF orientation normalization.
2. Explicit integer crop in normalized pixel coordinates. `left`/`top` are
   inclusive; `right`/`bottom` are exclusive. The crop must remain inside the image.
3. Counterclockwise quarter rotation: 0, 90, 180 or 270 degrees.
4. Horizontal and/or vertical flips.
5. Optional fit and resize with nearest, bicubic or default Lanczos resampling.

`target_size` takes integer pixel `width` and `height`. `contain` fits inside those
dimensions without padding; the returned size can be smaller on one axis.
`cover` center-crops to the requested aspect before resizing. `stretch` explicitly
changes aspect. Increasing either pixel dimension requires `allow_upscale=true`;
the result reports upsampling without claiming added source detail.

Sources are PNG, JPEG, TIFF, BMP and GIF. Preparation accepts single-frame
RGB/RGBA/L/LA/CMYK; bitonal sources normalize to L and palettes normalize to
RGB/RGBA. Multiple frames and precision modes remain inspectable but preparation
is refused. CMYK uses TIFF; PNG does not trigger an implicit color conversion.
Encoded files are capped at 128 MiB, dimensions at 65535 per side and 64 million
pixels total, and ICC metadata at 8 MiB. Paths must be absolute supported local
paths; UNC/device/control/alternate-stream paths are refused.

Recognized DPI and opaque ICC bytes are retained. EXIF and other ancillary
metadata are stripped. EXIF transposes and quarter rotations swap DPI axes when
appropriate. Optional finite `output_dpi` in [1, 2400] sets metadata on both axes;
it does not resample or approve resolution. TIFF without physical resolution tags
has absent DPI even though Pillow supplies a decoder default of `(1, 1)`.
PNG stores quantized physical resolution, so DPI readback permits 0.02 DPI error.

Publication starts in an owned temporary directory under the resolved output
parent. Staged readback must match decoded pixels, mode, size, single-frame state,
orientation, ICC bytes and expected DPI. Publication uses an exclusive hard link
or bounded exclusive-copy fallback, then reconciles output bytes/pixels/identity.
Source path and byte hash must match before and after publication. Known owned
outputs are removed on failure; replaced or unowned outputs are preserved with
an explicit cleanup failure. Temporary cleanup and filesystem errors remain
redacted. These are bounded observations, not atomic locks against external edits.

Example local flow:

```python
asset = inspect_raster_asset("C:/jobs/source.png")["asset"]
result = prepare_raster_asset(
    "C:/jobs/source.png", "C:/jobs/prepared.png", asset["fingerprint"],
    crop_box={"left": 10, "top": 20, "right": 610, "bottom": 420},
    target_size={"width": 300, "height": 200}, resize_mode="contain",
)
```

Direct module calls return the data above; MCP wrappers place it under the
standard envelope's `data`. Every success includes source/output summaries,
operations, source byte preservation and pixel readback evidence. Strict catalog
schemas reject malformed nested requests and false preservation-success fields.
Local operations use the existing redacted operation recording wrapper.

The [primary Pillow evidence](raster_preparation_online_evidence.json) retains
bounded excerpts from [EXIF transforms](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html),
[resize/resampling](https://pillow.readthedocs.io/en/stable/reference/Image.html)
and [image format metadata](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html).
All three returned readable HTTP 200 content; actual access dates are retained.
Tests use the installed Pillow runtime and generated synthetic images.

Background removal, cleanup, AI enhancement, tracing, color conversion and
document-wide raster preflight remain separate work. Deferred artifact review
should import prepared transparent PNG and CMYK TIFF fixtures into an owned X7
document, compare placement/pixels/alpha/color behavior, save CDR/PDF and inspect
the results. The existing native bitmap/import campaign provides the handoff;
these local tools have no additional X7 API requirement or native readiness claim.
