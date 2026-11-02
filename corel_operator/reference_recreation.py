"""Reference-image preflight and perspective calibration for vector recreation.

This module is deliberately independent of CorelDRAW.  It prepares a bounded,
reference-only raster workspace and records the transforms needed to convert
measured photo pixels into physical page coordinates.  The rectified image is
analysis material; callers must not treat it as printable artwork.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


A4_LANDSCAPE_WIDTH_MM = 297.0
A4_LANDSCAPE_HEIGHT_MM = 210.0
MM_PER_INCH = 25.4
MAX_REFERENCE_BYTES = 250 * 1024 * 1024
MAX_REFERENCE_PIXELS = 500_000_000
MAX_RECTIFIED_PIXELS = 100_000_000
SUPPORTED_REFERENCE_EXTENSIONS = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
CORNER_NAMES = ("top_left", "top_right", "bottom_right", "bottom_left")
ROTATIONS = {
    "none": None,
    "clockwise_90": "ROTATE_270",
    "counterclockwise_90": "ROTATE_90",
    "180": "ROTATE_180",
}


class ReferencePreparationError(ValueError):
    """Raised when reference material cannot be prepared deterministically."""


def _pillow() -> tuple[Any, Any, type[BaseException]]:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - installation diagnostics cover this
        raise ReferencePreparationError(
            "Reference preparation requires Pillow. Install the project requirements."
        ) from exc
    return Image, ImageOps, UnidentifiedImageError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_path(file_path: str | Path) -> Path:
    if not isinstance(file_path, (str, Path)):
        raise ReferencePreparationError("file_path must be a string or Path.")
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise ReferencePreparationError(f"Reference image does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_REFERENCE_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_REFERENCE_EXTENSIONS))
        raise ReferencePreparationError(
            f"Unsupported reference-image extension {path.suffix!r}; expected one of {supported}."
        )
    if path.stat().st_size > MAX_REFERENCE_BYTES:
        raise ReferencePreparationError("Reference image exceeds the 250 MB safety limit.")
    return path


def inspect_reference_image(file_path: str | Path) -> dict[str, Any]:
    """Return bounded metadata and a content hash without changing the source."""
    path = _reference_path(file_path)
    Image, ImageOps, UnidentifiedImageError = _pillow()
    try:
        with Image.open(path) as source:
            frame_count = int(getattr(source, "n_frames", 1))
            raw_width, raw_height = source.size
            exif_orientation = None
            try:
                exif_orientation = source.getexif().get(274)
            except Exception:
                pass
            normalized = ImageOps.exif_transpose(source)
            width, height = normalized.size
            bands = tuple(str(band) for band in normalized.getbands())
            dpi = source.info.get("dpi")
            metadata_dpi = None
            if isinstance(dpi, (tuple, list)) and len(dpi) >= 2:
                try:
                    dpi_x, dpi_y = float(dpi[0]), float(dpi[1])
                    if all(math.isfinite(value) and value > 0 for value in (dpi_x, dpi_y)):
                        metadata_dpi = {"x": round(dpi_x, 3), "y": round(dpi_y, 3)}
                except (TypeError, ValueError, OverflowError):
                    pass
            image_format = str(source.format or path.suffix.lstrip(".")).upper()
            mode = str(normalized.mode)
            has_icc_profile = bool(source.info.get("icc_profile"))
            has_transparency = "A" in bands or "transparency" in source.info
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ReferencePreparationError("Reference file is not a readable supported image.") from exc

    pixel_count = int(width) * int(height)
    if width <= 0 or height <= 0 or pixel_count > MAX_REFERENCE_PIXELS:
        raise ReferencePreparationError(
            "Reference dimensions are empty or exceed the 500-megapixel safety limit."
        )

    warnings: list[str] = []
    blocking_issues: list[str] = []
    if frame_count != 1:
        blocking_issues.append("Animated or multi-page reference images are not accepted.")
    if not has_icc_profile:
        warnings.append("The reference has no embedded ICC profile; sampled colors are uncalibrated.")
    if metadata_dpi is None:
        warnings.append("The reference has no reliable DPI metadata; A4 calibration uses page corners.")
    if image_format in {"JPEG", "JPG"}:
        warnings.append("JPEG compression may make fine edges and color samples uncertain.")
    if has_transparency:
        warnings.append("Transparency will be composited over white in the analysis copy.")

    return {
        "schema_version": "reference-preflight-v1",
        "file_path": str(path),
        "file_name": path.name,
        "file_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "format": image_format,
        "raw_width_pixels": int(raw_width),
        "raw_height_pixels": int(raw_height),
        "width_pixels_after_exif": int(width),
        "height_pixels_after_exif": int(height),
        "pixel_count_after_exif": pixel_count,
        "mode_after_exif": mode,
        "frame_count": frame_count,
        "exif_orientation": exif_orientation,
        "metadata_dpi": metadata_dpi,
        "has_icc_profile": has_icc_profile,
        "warnings": warnings,
        "blocking_issues": blocking_issues,
        "ready_for_calibration": not blocking_issues,
    }


def normalize_rotation(rotation: str) -> str:
    aliases = {
        "ccw": "counterclockwise_90",
        "counterclockwise": "counterclockwise_90",
        "counter-clockwise": "counterclockwise_90",
        "90_ccw": "counterclockwise_90",
        "cw": "clockwise_90",
        "clockwise": "clockwise_90",
        "90_cw": "clockwise_90",
        "rotate_180": "180",
        "0": "none",
    }
    if not isinstance(rotation, str):
        raise ReferencePreparationError("rotation must be a string.")
    normalized = aliases.get(rotation.strip().lower(), rotation.strip().lower())
    if normalized not in ROTATIONS:
        raise ReferencePreparationError(
            "rotation must be none, clockwise_90, counterclockwise_90, or 180."
        )
    return normalized


def rotated_size(width: int, height: int, rotation: str) -> tuple[int, int]:
    normalized = normalize_rotation(rotation)
    if normalized in {"clockwise_90", "counterclockwise_90"}:
        return int(height), int(width)
    return int(width), int(height)


def _finite_coordinate(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReferencePreparationError(f"{name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ReferencePreparationError(f"{name} must be a finite number.")
    return number


def _coerce_point(name: str, value: Any) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ReferencePreparationError(f"{name} must contain exactly [x, y].")
    return (
        _finite_coordinate(f"{name}[0]", value[0]),
        _finite_coordinate(f"{name}[1]", value[1]),
    )


def _cross(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> float:
    return (
        (second[0] - first[0]) * (third[1] - second[1])
        - (second[1] - first[1]) * (third[0] - second[0])
    )


def _polygon_area(points: Sequence[tuple[float, float]]) -> float:
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2.0


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def validate_page_corners(
    corners: Mapping[str, Any],
    image_width: int,
    image_height: int,
    *,
    allow_extrapolated: bool = False,
    max_extrapolation_fraction: float = 0.25,
) -> dict[str, tuple[float, float]]:
    """Validate named page corners in top-left-origin image-edge coordinates."""
    if not isinstance(corners, Mapping):
        raise ReferencePreparationError("page_corners_pixels must be an object.")
    missing = [name for name in CORNER_NAMES if name not in corners]
    extras = [str(name) for name in corners if name not in CORNER_NAMES]
    if missing or extras:
        raise ReferencePreparationError(
            f"Page corners must contain exactly {list(CORNER_NAMES)}; missing={missing}, extra={extras}."
        )
    if image_width <= 0 or image_height <= 0:
        raise ReferencePreparationError("Image dimensions must be positive.")

    normalized = {name: _coerce_point(name, corners[name]) for name in CORNER_NAMES}
    points = [normalized[name] for name in CORNER_NAMES]
    if not isinstance(allow_extrapolated, bool):
        raise ReferencePreparationError("allow_extrapolated must be Boolean.")
    if (
        isinstance(max_extrapolation_fraction, bool)
        or not isinstance(max_extrapolation_fraction, (int, float))
        or not math.isfinite(float(max_extrapolation_fraction))
        or not 0 <= float(max_extrapolation_fraction) <= 0.5
    ):
        raise ReferencePreparationError("max_extrapolation_fraction must be between 0 and 0.5.")
    x_allowance = image_width * float(max_extrapolation_fraction) if allow_extrapolated else 0.0
    y_allowance = image_height * float(max_extrapolation_fraction) if allow_extrapolated else 0.0
    for name, (x, y) in normalized.items():
        if (
            x < -x_allowance
            or x > image_width + x_allowance
            or y < -y_allowance
            or y > image_height + y_allowance
        ):
            raise ReferencePreparationError(
                f"{name} lies outside the permitted rotated-image calibration bounds."
            )
    if len(set(points)) != 4:
        raise ReferencePreparationError("The four page corners must be distinct.")

    crosses = [_cross(points[index], points[(index + 1) % 4], points[(index + 2) % 4]) for index in range(4)]
    epsilon = max(image_width, image_height) * 1e-6
    if not all(value > epsilon for value in crosses):
        raise ReferencePreparationError(
            "Corners must form a non-self-intersecting convex quadrilateral in "
            "top-left, top-right, bottom-right, bottom-left order."
        )

    top_mid_y = (points[0][1] + points[1][1]) / 2.0
    bottom_mid_y = (points[2][1] + points[3][1]) / 2.0
    left_mid_x = (points[0][0] + points[3][0]) / 2.0
    right_mid_x = (points[1][0] + points[2][0]) / 2.0
    if top_mid_y >= bottom_mid_y or left_mid_x >= right_mid_x:
        raise ReferencePreparationError("Corner names do not describe an upright page after rotation.")

    area = _polygon_area(points)
    if area < image_width * image_height * 0.01:
        raise ReferencePreparationError("Measured page area is below 1% of the image and is unreliable.")
    minimum_side = max(5.0, min(image_width, image_height) * 0.01)
    if any(_distance(points[index], points[(index + 1) % 4]) < minimum_side for index in range(4)):
        raise ReferencePreparationError("At least one measured page edge is too short to calibrate.")
    return normalized


def _solve_linear_system(matrix: list[list[float]], values: list[float]) -> list[float]:
    """Solve a small square system with partial-pivot Gaussian elimination."""
    size = len(values)
    augmented = [list(row) + [float(value)] for row, value in zip(matrix, values)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ReferencePreparationError("Corner geometry produces a singular perspective transform.")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [
                    current - factor * pivot_value
                    for current, pivot_value in zip(augmented[row], augmented[column])
                ]
    return [augmented[row][-1] for row in range(size)]


def projective_coefficients(
    source_points: Sequence[tuple[float, float]],
    target_points: Sequence[tuple[float, float]],
) -> tuple[float, float, float, float, float, float, float, float]:
    """Return coefficients mapping source (x, y) to target (u, v)."""
    if len(source_points) != 4 or len(target_points) != 4:
        raise ReferencePreparationError("A projective transform requires four source and target points.")
    matrix: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(source_points, target_points):
        matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        values.append(u)
        matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        values.append(v)
    solved = _solve_linear_system(matrix, values)
    return tuple(float(value) for value in solved)  # type: ignore[return-value]


def apply_projective_transform(
    coefficients: Sequence[float],
    point: Sequence[float],
) -> tuple[float, float]:
    if len(coefficients) != 8:
        raise ReferencePreparationError("Projective coefficients must contain eight values.")
    x, y = _coerce_point("point", point)
    a, b, c, d, e, f, g, h = (float(value) for value in coefficients)
    denominator = g * x + h * y + 1.0
    if abs(denominator) < 1e-12:
        raise ReferencePreparationError("Point projects to infinity under this transform.")
    return (
        (a * x + b * y + c) / denominator,
        (d * x + e * y + f) / denominator,
    )


def _matrix(coefficients: Sequence[float]) -> list[list[float]]:
    a, b, c, d, e, f, g, h = coefficients
    return [[a, b, c], [d, e, f], [g, h, 1.0]]


def _output_dimensions(area_pixels: float) -> tuple[int, int]:
    # 297:210 reduces to 99:70. Multiples preserve the exact A4 ratio.
    units = max(4, round(math.sqrt(area_pixels / (99.0 * 70.0))))
    max_units = min(10000 // 99, int(math.sqrt(MAX_RECTIFIED_PIXELS / (99 * 70))))
    units = min(units, max_units)
    return 99 * units, 70 * units


def calibrate_a4_landscape(
    image_width: int,
    image_height: int,
    page_corners_pixels: Mapping[str, Any],
    *,
    output_width_pixels: int | None = None,
    allow_extrapolated_corners: bool = False,
) -> dict[str, Any]:
    """Build deterministic photo↔A4 transforms from measured page corners."""
    corners = validate_page_corners(
        page_corners_pixels,
        image_width,
        image_height,
        allow_extrapolated=allow_extrapolated_corners,
    )
    source_points = [corners[name] for name in CORNER_NAMES]
    area = _polygon_area(source_points)
    if output_width_pixels is None:
        output_width, output_height = _output_dimensions(area)
    else:
        if isinstance(output_width_pixels, bool) or not isinstance(output_width_pixels, int):
            raise ReferencePreparationError("output_width_pixels must be an integer.")
        if output_width_pixels < 396 or output_width_pixels > 10000:
            raise ReferencePreparationError("output_width_pixels must be between 396 and 10000.")
        units = max(4, round(output_width_pixels / 99))
        output_width, output_height = 99 * units, 70 * units
        if output_width * output_height > MAX_RECTIFIED_PIXELS:
            raise ReferencePreparationError("Requested rectified image exceeds 100 megapixels.")

    rectified_points = [
        (0.0, 0.0),
        (float(output_width), 0.0),
        (float(output_width), float(output_height)),
        (0.0, float(output_height)),
    ]
    page_mm_points = [
        (0.0, A4_LANDSCAPE_HEIGHT_MM),
        (A4_LANDSCAPE_WIDTH_MM, A4_LANDSCAPE_HEIGHT_MM),
        (A4_LANDSCAPE_WIDTH_MM, 0.0),
        (0.0, 0.0),
    ]
    rectified_to_source = projective_coefficients(rectified_points, source_points)
    source_to_page_mm = projective_coefficients(source_points, page_mm_points)
    page_mm_to_source = projective_coefficients(page_mm_points, source_points)
    rectified_to_page_mm = (
        A4_LANDSCAPE_WIDTH_MM / output_width,
        0.0,
        0.0,
        0.0,
        -A4_LANDSCAPE_HEIGHT_MM / output_height,
        A4_LANDSCAPE_HEIGHT_MM,
        0.0,
        0.0,
    )
    # Dividing g/h would alter the projective denominator. Recompute instead.
    page_inches_points = [
        (x / MM_PER_INCH, y / MM_PER_INCH) for x, y in page_mm_points
    ]
    source_to_page_inches = projective_coefficients(source_points, page_inches_points)

    corners_outside_image = [
        name
        for name, (x, y) in corners.items()
        if x < 0 or x > image_width or y < 0 or y > image_height
    ]
    return {
        "schema_version": "reference-calibration-v1",
        "coordinate_contract": {
            "measured_source": "rotated image edge coordinates; origin top-left; x right; y down",
            "rectified_image": "image edge coordinates; origin top-left; x right; y down",
            "corel_page": "physical coordinates; origin bottom-left; x right; y up",
        },
        "page": {
            "standard": "A4 landscape",
            "width_mm": A4_LANDSCAPE_WIDTH_MM,
            "height_mm": A4_LANDSCAPE_HEIGHT_MM,
            "width_inches": A4_LANDSCAPE_WIDTH_MM / MM_PER_INCH,
            "height_inches": A4_LANDSCAPE_HEIGHT_MM / MM_PER_INCH,
        },
        "rotated_source_size_pixels": {"width": image_width, "height": image_height},
        "page_corners_pixels": {
            name: [round(corners[name][0], 6), round(corners[name][1], 6)]
            for name in CORNER_NAMES
        },
        "page_quadrilateral": {
            "area_pixels_squared": round(area, 3),
            "image_coverage_percent": round(area / (image_width * image_height) * 100.0, 3),
            "edge_lengths_pixels": {
                "top": round(_distance(source_points[0], source_points[1]), 3),
                "right": round(_distance(source_points[1], source_points[2]), 3),
                "bottom": round(_distance(source_points[2], source_points[3]), 3),
                "left": round(_distance(source_points[3], source_points[0]), 3),
            },
            "corners_outside_image": corners_outside_image,
            "uses_explicit_extrapolation": bool(corners_outside_image),
        },
        "rectified_image": {
            "width_pixels": output_width,
            "height_pixels": output_height,
            "aspect_ratio": output_width / output_height,
            "exact_integer_ratio": "99:70",
            "nominal_dpi": round(output_width / (A4_LANDSCAPE_WIDTH_MM / MM_PER_INCH), 3),
        },
        "transforms": {
            "rectified_pixel_to_rotated_source_pixel": {
                "coefficients": list(rectified_to_source),
                "matrix": _matrix(rectified_to_source),
                "consumer": "Pillow perspective transform (output to input)",
            },
            "rotated_source_pixel_to_corel_mm": {
                "coefficients": list(source_to_page_mm),
                "matrix": _matrix(source_to_page_mm),
            },
            "corel_mm_to_rotated_source_pixel": {
                "coefficients": list(page_mm_to_source),
                "matrix": _matrix(page_mm_to_source),
            },
            "rotated_source_pixel_to_corel_inches": {
                "coefficients": list(source_to_page_inches),
                "matrix": _matrix(source_to_page_inches),
            },
            "rectified_pixel_to_corel_mm": {
                "coefficients": list(rectified_to_page_mm),
                "matrix": _matrix(rectified_to_page_mm),
            },
        },
    }


def measure_inner_printed_field(
    calibration: Mapping[str, Any],
    inner_corners_pixels: Mapping[str, Any],
    *,
    allow_extrapolated_corners: bool = False,
) -> dict[str, Any]:
    """Map measured inner-field corners to Corel millimetres and margin widths."""
    source_size = calibration.get("rotated_source_size_pixels")
    transforms = calibration.get("transforms")
    if not isinstance(source_size, Mapping) or not isinstance(transforms, Mapping):
        raise ReferencePreparationError("Calibration data is missing source size or transforms.")
    source_to_mm = transforms.get("rotated_source_pixel_to_corel_mm")
    if not isinstance(source_to_mm, Mapping) or not isinstance(source_to_mm.get("coefficients"), list):
        raise ReferencePreparationError("Calibration data is missing the source-to-Corel transform.")
    width = int(source_size.get("width", 0))
    height = int(source_size.get("height", 0))
    corners = validate_page_corners(
        inner_corners_pixels,
        width,
        height,
        allow_extrapolated=allow_extrapolated_corners,
    )
    mapped = {
        name: apply_projective_transform(source_to_mm["coefficients"], corners[name])
        for name in CORNER_NAMES
    }
    top_left = mapped["top_left"]
    top_right = mapped["top_right"]
    bottom_right = mapped["bottom_right"]
    bottom_left = mapped["bottom_left"]
    left = (top_left[0] + bottom_left[0]) / 2.0
    right = (top_right[0] + bottom_right[0]) / 2.0
    top = (top_left[1] + top_right[1]) / 2.0
    bottom = (bottom_left[1] + bottom_right[1]) / 2.0
    margins = {
        "left": left,
        "top": A4_LANDSCAPE_HEIGHT_MM - top,
        "right": A4_LANDSCAPE_WIDTH_MM - right,
        "bottom": bottom,
    }
    tolerance = 0.5
    if any(value < -tolerance for value in margins.values()):
        raise ReferencePreparationError("Inner printed-field corners project outside the measured page.")
    return {
        "source_corners_pixels": {
            name: [round(corners[name][0], 6), round(corners[name][1], 6)]
            for name in CORNER_NAMES
        },
        "corel_corners_mm": {
            name: [round(mapped[name][0], 6), round(mapped[name][1], 6)]
            for name in CORNER_NAMES
        },
        "average_bounds_mm": {
            "left": round(left, 6),
            "bottom": round(bottom, 6),
            "right": round(right, 6),
            "top": round(top, 6),
            "width": round(right - left, 6),
            "height": round(top - bottom, 6),
        },
        "margin_widths_mm": {name: round(max(0.0, value), 6) for name, value in margins.items()},
        "corners_outside_image": [
            name
            for name, (x, y) in corners.items()
            if x < 0 or x > width or y < 0 or y > height
        ],
        "measurement_note": (
            "Bounds and margins average opposing measured edges; retain individual Corel corners "
            "when the photographed print field is not perfectly rectangular."
        ),
    }


def _open_normalized_rgb(source_path: Path, rotation: str) -> Any:
    Image, ImageOps, _ = _pillow()
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source)
        transpose_name = ROTATIONS[normalize_rotation(rotation)]
        if transpose_name is not None:
            image = image.transpose(getattr(Image.Transpose, transpose_name))
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            image = background.convert("RGB")
        else:
            image = image.convert("RGB")
        return image.copy()


def save_rotated_reference(
    source_path: str | Path,
    output_path: str | Path,
    *,
    rotation: str = "counterclockwise_90",
) -> dict[str, Any]:
    """Write a normalized reference-only PNG for manual corner measurement."""
    source = _reference_path(source_path)
    destination = Path(output_path).expanduser().resolve()
    if destination.suffix.lower() != ".png":
        raise ReferencePreparationError("The normalized analysis copy must use a .png path.")
    if destination.exists():
        raise ReferencePreparationError(f"Refusing to overwrite existing analysis file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image = _open_normalized_rgb(source, rotation)
    image.save(destination, format="PNG")
    return {
        "path": str(destination),
        "width_pixels": image.width,
        "height_pixels": image.height,
        "rotation_after_exif": normalize_rotation(rotation),
        "sha256": _sha256(destination),
    }


def rectify_a4_reference(
    source_path: str | Path,
    output_path: str | Path,
    page_corners_pixels: Mapping[str, Any],
    *,
    rotation: str = "counterclockwise_90",
    output_width_pixels: int | None = None,
    allow_extrapolated_corners: bool = False,
) -> dict[str, Any]:
    """Write a perspective-corrected A4 analysis PNG and return calibration data."""
    source = _reference_path(source_path)
    preflight = inspect_reference_image(source)
    if not preflight["ready_for_calibration"]:
        raise ReferencePreparationError(
            "Reference preflight has blocking issues: " + "; ".join(preflight["blocking_issues"])
        )
    destination = Path(output_path).expanduser().resolve()
    if destination.suffix.lower() != ".png":
        raise ReferencePreparationError("The rectified analysis copy must use a .png path.")
    if destination.exists():
        raise ReferencePreparationError(f"Refusing to overwrite existing analysis file: {destination}")

    Image, _, _ = _pillow()
    image = _open_normalized_rgb(source, rotation)
    calibration = calibrate_a4_landscape(
        image.width,
        image.height,
        page_corners_pixels,
        output_width_pixels=output_width_pixels,
        allow_extrapolated_corners=allow_extrapolated_corners,
    )
    output = calibration["rectified_image"]
    coefficients = calibration["transforms"]["rectified_pixel_to_rotated_source_pixel"]["coefficients"]
    rectified = image.transform(
        (output["width_pixels"], output["height_pixels"]),
        Image.Transform.PERSPECTIVE,
        tuple(coefficients),
        resample=Image.Resampling.BICUBIC,
        fillcolor="white",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    dpi = float(output["nominal_dpi"])
    rectified.save(destination, format="PNG", dpi=(dpi, dpi))
    calibration["source_preflight"] = preflight
    calibration["rotation_after_exif"] = normalize_rotation(rotation)
    calibration["rectified_analysis_file"] = {
        "path": str(destination),
        "sha256": _sha256(destination),
        "role": "reference-only; never printable artwork",
    }
    return calibration


def _load_corner_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReferencePreparationError(f"Corner measurement JSON is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ReferencePreparationError("Corner measurement JSON must contain an object.")
    return value


def _replace_string_prefix(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return new + value[len(old):] if value.startswith(old) else value
    if isinstance(value, list):
        return [_replace_string_prefix(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: _replace_string_prefix(item, old, new) for key, item in value.items()}
    return value


def prepare_a4_reference_workspace(
    source_path: str | Path,
    output_directory: str | Path,
    *,
    rotation: str = "counterclockwise_90",
    corner_measurements_path: str | Path | None = None,
    project_name: str = "reference-vector-recreation-v2",
) -> dict[str, Any]:
    """Create a new, non-overwriting reference workspace for A4 reconstruction."""
    source = _reference_path(source_path)
    preflight = inspect_reference_image(source)
    if not preflight["ready_for_calibration"]:
        raise ReferencePreparationError(
            "Reference preflight has blocking issues: " + "; ".join(preflight["blocking_issues"])
        )
    output = Path(output_directory).expanduser().resolve()
    if output.exists():
        raise ReferencePreparationError(f"Refusing to overwrite existing V2 workspace: {output}")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{output.name}.preparing"
    if staging.exists():
        raise ReferencePreparationError(f"Stale preparation directory must be reviewed first: {staging}")

    normalized_rotation = normalize_rotation(rotation)
    try:
        reference_dir = staging / "00_reference_nonprinting"
        reference_dir.mkdir(parents=True)
        source_copy = reference_dir / f"source_original{source.suffix.lower()}"
        shutil.copy2(source, source_copy)
        rotated_path = reference_dir / "reference_rotated_for_corner_marking.png"
        rotated = save_rotated_reference(source_copy, rotated_path, rotation=normalized_rotation)

        template = {
            "schema_version": "a4-corner-measurements-v1",
            "project_name": project_name,
            "coordinate_space": {
                "file": rotated_path.name,
                "origin": "top-left image edge",
                "x_axis": "right",
                "y_axis": "down",
                "width_pixels": rotated["width_pixels"],
                "height_pixels": rotated["height_pixels"],
            },
            "rotation_after_exif": normalized_rotation,
            "allow_extrapolated_page_corners": False,
            "allow_extrapolated_inner_field_corners": False,
            "page_corners_pixels": {name: None for name in CORNER_NAMES},
            "inner_printed_field_corners_pixels": {name: None for name in CORNER_NAMES},
            "uncertain_regions": [],
            "measurement_method": {
                "page_corners": "direct observation",
                "inner_printed_field_corners": "direct observation",
            },
            "instructions": (
                "Measure the four outer paper corners in the rotated PNG. Use pixel-edge coordinates "
                "and preserve top_left, top_right, bottom_right, bottom_left order."
            ),
        }
        template_path = reference_dir / "corner_measurements.template.json"
        template_path.write_text(json.dumps(template, indent=2), encoding="utf-8")

        calibration = None
        measurements_source = None
        status = "AWAITING_MEASURED_PAGE_CORNERS"
        if corner_measurements_path is not None:
            measurements_source = Path(corner_measurements_path).expanduser().resolve()
            measurements = _load_corner_document(measurements_source)
            measured_rotation = normalize_rotation(
                str(measurements.get("rotation_after_exif", normalized_rotation))
            )
            if measured_rotation != normalized_rotation:
                raise ReferencePreparationError(
                    "Corner JSON rotation_after_exif does not match the requested workspace rotation."
                )
            corners = measurements.get("page_corners_pixels")
            if not isinstance(corners, Mapping):
                raise ReferencePreparationError(
                    "Corner JSON must contain page_corners_pixels with four measured points."
                )
            allow_page_extrapolation = measurements.get(
                "allow_extrapolated_page_corners", False
            )
            allow_inner_extrapolation = measurements.get(
                "allow_extrapolated_inner_field_corners", False
            )
            if not isinstance(allow_page_extrapolation, bool) or not isinstance(
                allow_inner_extrapolation, bool
            ):
                raise ReferencePreparationError(
                    "Corner extrapolation flags must be JSON Booleans."
                )
            rectified_path = reference_dir / "reference_rectified_a4.png"
            calibration = rectify_a4_reference(
                source_copy,
                rectified_path,
                corners,
                rotation=normalized_rotation,
                allow_extrapolated_corners=allow_page_extrapolation,
            )
            inner_corners = measurements.get("inner_printed_field_corners_pixels")
            if isinstance(inner_corners, Mapping) and all(
                inner_corners.get(name) is not None for name in CORNER_NAMES
            ):
                calibration["inner_printed_field"] = measure_inner_printed_field(
                    calibration,
                    inner_corners,
                    allow_extrapolated_corners=allow_inner_extrapolation,
                )
            else:
                calibration["inner_printed_field"] = None
            calibration["uncertain_regions"] = measurements.get("uncertain_regions", [])
            calibration["measurement_method"] = measurements.get("measurement_method", {})
            calibration["measurement_source_file"] = str(measurements_source)
            measurements_path = staging / "v2_measurements.json"
            measurements_path.write_text(
                json.dumps(calibration, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            status = "PHASE_1_RECTIFIED_AND_CALIBRATED"

        manifest = {
            "schema_version": "vector-recreation-workspace-v1",
            "project_name": project_name,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "source_preflight": preflight,
            "source_copy": {
                "path": str(source_copy),
                "sha256": _sha256(source_copy),
                "matches_original": _sha256(source_copy) == preflight["sha256"],
            },
            "reference_policy": {
                "directory_role": "analysis only",
                "may_be_imported_only_to": "00 - Reference - NONPRINTING",
                "printable": False,
                "final_vector_audit_requires_bitmap_shapes": 0,
            },
            "artifacts": {
                "rotated_corner_marking_image": str(rotated_path),
                "corner_measurement_template": str(template_path),
                "rectified_reference": (
                    str(reference_dir / "reference_rectified_a4.png") if calibration else None
                ),
                "measurement_json": str(staging / "v2_measurements.json") if calibration else None,
            },
            "next_gate": (
                "Trace structural geometry from the measured transform."
                if calibration
                else "Fill the corner template from the rotated image and rerun into a new V2 workspace."
            ),
        }
        manifest_path = staging / "V2_WORKSPACE_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        staging.replace(output)

        # Paths were written while the directory had its staging name. Rewrite them to
        # final durable paths after the atomic rename.
        manifest_path = output / "V2_WORKSPACE_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = _replace_string_prefix(manifest, str(staging), str(output))
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        measurement_path = output / "v2_measurements.json"
        if measurement_path.exists():
            measurement = json.loads(measurement_path.read_text(encoding="utf-8"))
            measurement = _replace_string_prefix(
                measurement, str(staging), str(output)
            )
            measurement_path.write_text(
                json.dumps(measurement, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
