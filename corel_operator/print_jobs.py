"""Pure raster-artwork inspection and general print-sheet planning."""
from __future__ import annotations

import math
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .errors import CorelBridgeError, ErrorCode
from .workflows import calculate_sheet_layout


MAX_ARTWORK_BYTES = 250 * 1024 * 1024
MAX_ARTWORK_PIXELS = 500_000_000
MAX_PRINT_COPIES = 500
RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif"}
ASPECT_FIT_MODES = {"contain", "cover", "stretch"}


def _finite_number(name: str, value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CorelBridgeError(f"{name} must be a finite number.", ErrorCode.INVALID_ARGUMENT)
    number = float(value)
    if not math.isfinite(number):
        raise CorelBridgeError(f"{name} must be a finite number.", ErrorCode.INVALID_ARGUMENT)
    if positive and number <= 0:
        raise CorelBridgeError(f"{name} must be greater than zero.", ErrorCode.INVALID_ARGUMENT)
    if not positive and number < 0:
        raise CorelBridgeError(f"{name} cannot be negative.", ErrorCode.INVALID_ARGUMENT)
    return number


def _aspect_geometry(
    width_pixels: int,
    height_pixels: int,
    target_width: float,
    target_height: float,
    fit_mode: str,
) -> dict[str, Any]:
    """Calculate deterministic display and source-crop geometry."""
    source_ratio = width_pixels / height_pixels
    target_ratio = target_width / target_height
    difference_percent = abs(source_ratio - target_ratio) / target_ratio * 100
    crop = {
        "left": 0,
        "top": 0,
        "right": width_pixels,
        "bottom": height_pixels,
        "width": width_pixels,
        "height": height_pixels,
    }

    if fit_mode == "contain":
        scale = min(target_width / width_pixels, target_height / height_pixels)
        display_width = width_pixels * scale
        display_height = height_pixels * scale
    elif fit_mode == "cover":
        if source_ratio > target_ratio:
            crop_width = min(width_pixels, max(1, round(height_pixels * target_ratio)))
            left = (width_pixels - crop_width) // 2
            crop.update(left=left, right=left + crop_width, width=crop_width)
        elif source_ratio < target_ratio:
            crop_height = min(height_pixels, max(1, round(width_pixels / target_ratio)))
            top = (height_pixels - crop_height) // 2
            crop.update(top=top, bottom=top + crop_height, height=crop_height)
        display_width = target_width
        display_height = target_height
    else:  # stretch is an explicit request to fill without preserving aspect ratio
        display_width = target_width
        display_height = target_height

    return {
        "fit_mode": fit_mode,
        "source_aspect_ratio": round(source_ratio, 8),
        "target_aspect_ratio": round(target_ratio, 8),
        "difference_percent": round(difference_percent, 3),
        "display_width_inches": round(display_width, 6),
        "display_height_inches": round(display_height, 6),
        "source_crop_pixels": crop,
        "cropped": crop["width"] != width_pixels or crop["height"] != height_pixels,
        "distorted": fit_mode == "stretch" and difference_percent > 0.01,
    }


def inspect_raster_artwork(file_path: str) -> dict[str, Any]:
    """Read bounded raster metadata without connecting to CorelDRAW."""
    if not isinstance(file_path, str) or not file_path.strip():
        raise CorelBridgeError("file_path must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise CorelBridgeError(f"Artwork file does not exist: {path}", ErrorCode.UNSAFE_PATH)
    if path.suffix.lower() not in RASTER_EXTENSIONS:
        raise CorelBridgeError(
            "The general print-job workflow currently accepts PNG, JPEG, BMP, TIFF, or GIF raster artwork.",
            ErrorCode.INVALID_ARGUMENT,
        )
    file_bytes = path.stat().st_size
    if file_bytes > MAX_ARTWORK_BYTES:
        raise CorelBridgeError("Artwork exceeds the 250 MB print-job limit.", ErrorCode.INVALID_ARGUMENT)

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - dependency diagnostics cover installation
        raise CorelBridgeError(
            "Raster inspection requires Pillow. Install the project requirements.",
            ErrorCode.INTERNAL_ERROR,
        ) from exc

    try:
        with Image.open(path) as image:
            width_px, height_px = image.size
            exif_orientation = None
            try:
                exif_orientation = image.getexif().get(274)
            except Exception:
                pass
            if exif_orientation in (5, 6, 7, 8):
                width_px, height_px = height_px, width_px
            if width_px <= 0 or height_px <= 0 or width_px * height_px > MAX_ARTWORK_PIXELS:
                raise CorelBridgeError(
                    "Artwork pixel dimensions are empty or exceed the 500-megapixel planning limit.",
                    ErrorCode.INVALID_ARGUMENT,
                )
            bands = tuple(str(band) for band in image.getbands())
            dpi_value = image.info.get("dpi")
            metadata_dpi = None
            if isinstance(dpi_value, (tuple, list)) and len(dpi_value) >= 2:
                try:
                    dx, dy = float(dpi_value[0]), float(dpi_value[1])
                    if math.isfinite(dx) and math.isfinite(dy) and dx > 0 and dy > 0:
                        metadata_dpi = {"x": round(dx, 2), "y": round(dy, 2)}
                except (TypeError, ValueError, OverflowError):
                    pass
            mode = str(image.mode)
            color_space = {
                "1": "monochrome",
                "L": "grayscale",
                "LA": "grayscale_alpha",
                "P": "indexed",
                "RGB": "rgb",
                "RGBA": "rgb_alpha",
                "CMYK": "cmyk",
            }.get(mode, "unknown")
            return {
                "file_path": str(path),
                "file_name": path.name,
                "file_bytes": file_bytes,
                "format": str(image.format or path.suffix.lstrip(".")).upper(),
                "width_pixels": int(width_px),
                "height_pixels": int(height_px),
                "aspect_ratio": round(width_px / height_px, 8),
                "mode": mode,
                "color_space": color_space,
                "has_alpha": "A" in bands or "transparency" in image.info,
                "has_icc_profile": bool(image.info.get("icc_profile")),
                "metadata_dpi": metadata_dpi,
                "frame_count": int(getattr(image, "n_frames", 1)),
                "exif_orientation": exif_orientation,
            }
    except CorelBridgeError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise CorelBridgeError(
            "Artwork could not be decoded as a supported raster image.",
            ErrorCode.INVALID_ARGUMENT,
            {"exception_type": type(exc).__name__},
        ) from exc


@contextmanager
def materialize_placement_artwork(file_path: str, plan: dict[str, Any]) -> Iterator[str]:
    """Yield original artwork or a temporary lossless center crop for cover mode."""
    aspect = plan.get("aspect_fit", {})
    if aspect.get("fit_mode") != "cover" or not aspect.get("cropped"):
        yield file_path
        return

    crop = aspect["source_crop_pixels"]
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - dependency diagnostics cover installation
        raise CorelBridgeError(
            "Cover placement requires Pillow. Install the project requirements.",
            ErrorCode.INTERNAL_ERROR,
        ) from exc

    with tempfile.TemporaryDirectory(prefix="corel-print-") as temp_dir:
        output_path = Path(temp_dir) / "cover-crop.tif"
        try:
            with Image.open(Path(file_path).expanduser().resolve()) as source:
                source.seek(0)
                oriented = ImageOps.exif_transpose(source)
                if oriented.mode == "P" and "transparency" in oriented.info:
                    oriented = oriented.convert("RGBA")
                cropped = oriented.crop((crop["left"], crop["top"], crop["right"], crop["bottom"]))
                save_options: dict[str, Any] = {"compression": "tiff_lzw"}
                icc_profile = source.info.get("icc_profile")
                if icc_profile:
                    save_options["icc_profile"] = icc_profile
                metadata_dpi = plan.get("artwork", {}).get("metadata_dpi")
                if metadata_dpi:
                    save_options["dpi"] = (metadata_dpi["x"], metadata_dpi["y"])
                cropped.save(output_path, format="TIFF", **save_options)
        except (Image.DecompressionBombError, OSError, ValueError, KeyError) as exc:
            raise CorelBridgeError(
                "Could not create the lossless cover-crop derivative.",
                ErrorCode.INVALID_ARGUMENT,
                {"exception_type": type(exc).__name__},
            ) from exc
        yield str(output_path)


def plan_print_job(
    file_path: str,
    finished_width_inches: float,
    finished_height_inches: float,
    sheet_width_inches: float,
    sheet_height_inches: float,
    copies: int = 1,
    bleed_inches: float = 0.0,
    safe_margin_inches: float = 0.125,
    margin_inches: float = 0.25,
    gutter_inches: float = 0.125,
    minimum_dpi: float = 150.0,
    artwork_includes_bleed: bool = False,
    fit_mode: str = "contain",
    allow_low_resolution: bool = False,
    rotation_policy: str = "never",
    sheet_orientation: str = "fixed",
    margin_left_inches: float | None = None,
    margin_top_inches: float | None = None,
    margin_right_inches: float | None = None,
    margin_bottom_inches: float | None = None,
    gripper_inches: float = 0.0,
    gripper_edge: str = "bottom",
    mark_clearance_inches: float = 0.0,
) -> dict[str, Any]:
    """Preflight raster artwork and exact best-fit sheet geometry before mutation."""
    finished_width = _finite_number("finished_width_inches", finished_width_inches, positive=True)
    finished_height = _finite_number("finished_height_inches", finished_height_inches, positive=True)
    sheet_width = _finite_number("sheet_width_inches", sheet_width_inches, positive=True)
    sheet_height = _finite_number("sheet_height_inches", sheet_height_inches, positive=True)
    bleed = _finite_number("bleed_inches", bleed_inches)
    safe_margin = _finite_number("safe_margin_inches", safe_margin_inches)
    margin = _finite_number("margin_inches", margin_inches)
    gutter = _finite_number("gutter_inches", gutter_inches)
    gripper = _finite_number("gripper_inches", gripper_inches)
    mark_clearance = _finite_number("mark_clearance_inches", mark_clearance_inches)
    edge_margins = {
        "left": margin_left_inches,
        "top": margin_top_inches,
        "right": margin_right_inches,
        "bottom": margin_bottom_inches,
    }
    for edge, value in edge_margins.items():
        if value is not None:
            edge_margins[edge] = _finite_number(f"margin_{edge}_inches", value)
    min_dpi = _finite_number("minimum_dpi", minimum_dpi, positive=True)
    if any(value > 200 for value in (finished_width, finished_height, sheet_width, sheet_height)):
        raise CorelBridgeError("Finished and sheet dimensions cannot exceed 200 inches.", ErrorCode.INVALID_ARGUMENT)
    allowances = [margin, gutter, gripper, mark_clearance] + [
        float(value) for value in edge_margins.values() if value is not None
    ]
    if bleed > 2 or safe_margin > 20 or any(value > 20 for value in allowances) or min_dpi > 2400:
        raise CorelBridgeError(
            "Bleed, safe margin, sheet allowance, gutter, or minimum DPI exceeds the supported planning range.",
            ErrorCode.INVALID_ARGUMENT,
        )
    if safe_margin * 2 >= min(finished_width, finished_height):
        raise CorelBridgeError(
            "safe_margin_inches must leave a positive safe-area width and height.",
            ErrorCode.INVALID_ARGUMENT,
        )
    if isinstance(copies, bool) or not isinstance(copies, int) or not 1 <= copies <= MAX_PRINT_COPIES:
        raise CorelBridgeError(f"copies must be an integer from 1 to {MAX_PRINT_COPIES}.", ErrorCode.INVALID_ARGUMENT)
    for name, value in (("artwork_includes_bleed", artwork_includes_bleed), ("allow_low_resolution", allow_low_resolution)):
        if not isinstance(value, bool):
            raise CorelBridgeError(f"{name} must be a boolean.", ErrorCode.INVALID_ARGUMENT)
    if not isinstance(fit_mode, str) or fit_mode not in ASPECT_FIT_MODES:
        raise CorelBridgeError(
            "fit_mode must be one of: contain, cover, stretch.",
            ErrorCode.INVALID_ARGUMENT,
        )

    artwork = inspect_raster_artwork(file_path)
    placed_width = finished_width + bleed * 2
    placed_height = finished_height + bleed * 2
    layout = calculate_sheet_layout(
        placed_width,
        placed_height,
        sheet_width,
        sheet_height,
        margin,
        gutter,
        rotation_policy != "never",
        rotation_policy,
        sheet_orientation,
        edge_margins["left"],
        edge_margins["top"],
        edge_margins["right"],
        edge_margins["bottom"],
        gripper,
        gripper_edge,
        mark_clearance,
        copies,
    )
    aspect = _aspect_geometry(
        int(artwork["width_pixels"]),
        int(artwork["height_pixels"]),
        placed_width,
        placed_height,
        fit_mode,
    )
    crop = aspect["source_crop_pixels"]
    effective_dpi_x = crop["width"] / aspect["display_width_inches"]
    effective_dpi_y = crop["height"] / aspect["display_height_inches"]
    effective_dpi = min(effective_dpi_x, effective_dpi_y)

    blocking_issues: list[dict[str, Any]] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    capacity_passed = layout["capacity"] >= copies
    checks.append({
        "check": "sheet_capacity",
        "status": "passed" if capacity_passed else "failed",
        "capacity": layout["capacity"],
        "copies": copies,
        "sheets_required": layout["sheets_required"],
    })
    if not capacity_passed:
        blocking_issues.append({
            "code": "COPY_COUNT_EXCEEDS_SHEET",
            "message": (
                f"The optimized sheet fits {layout['capacity']} copies; {copies} copies require "
                f"{layout['sheets_required']} sheets. This execution workflow prepares one sheet at a time."
            ),
        })
    checks.append({
        "check": "production_quantity",
        "status": "passed" if layout["capacity"] else "failed",
        "requested_quantity": copies,
        "copies_per_sheet": layout["capacity"],
        "sheets_required": layout["sheets_required"],
        "total_produced": layout["total_produced"],
        "overage": layout["overage"],
    })

    aspect_status = "passed"
    if aspect["difference_percent"] > 0.01:
        aspect_status = "warning"
        if fit_mode == "contain":
            message = "Contain mode preserves all artwork but leaves part of the bleed-inclusive placement box uncovered."
        elif fit_mode == "cover":
            message = "Cover mode preserves aspect ratio and center-crops the artwork to fill the bleed-inclusive placement box."
        else:
            message = "Stretch mode fills the placement box by distorting the artwork aspect ratio."
        warnings.append(message)
    checks.append({
        "check": "aspect_fit",
        "status": aspect_status,
        "fit_mode": fit_mode,
        "difference_percent": aspect["difference_percent"],
        "cropped": aspect["cropped"],
        "distorted": aspect["distorted"],
    })

    resolution_passed = effective_dpi >= min_dpi
    resolution_status = "passed" if resolution_passed else ("warning" if allow_low_resolution else "failed")
    checks.append({"check": "effective_resolution", "status": resolution_status, "effective_dpi": round(effective_dpi, 2), "minimum_dpi": min_dpi, "override_applied": not resolution_passed and allow_low_resolution})
    if effective_dpi < min_dpi:
        message = f"Effective resolution is {effective_dpi:.1f} DPI, below the requested {min_dpi:.1f} DPI."
        warnings.append(message)
        if not allow_low_resolution:
            blocking_issues.append({"code": "LOW_EFFECTIVE_RESOLUTION", "message": message})

    bleed_passed = bleed == 0 or artwork_includes_bleed
    checks.append({"check": "bleed_content", "status": "passed" if bleed_passed else "failed", "bleed_inches": bleed})
    if bleed > 0 and not artwork_includes_bleed:
        blocking_issues.append({"code": "BLEED_NOT_CONFIRMED", "message": "Bleed was requested, but the artwork was not confirmed to include bleed content."})
    if bleed > 0 and fit_mode == "contain" and aspect["difference_percent"] > 0.01:
        message = "Contain mode does not cover the full bleed box; use matching artwork or cover mode."
        blocking_issues.append({"code": "BLEED_COVERAGE_INCOMPLETE", "message": message})
        warnings.append(message)
    if bleed == 0:
        warnings.append("No bleed is planned; confirm that the selected print process does not require it.")
    checks.append({
        "check": "safe_area_geometry",
        "status": "passed",
        "safe_margin_inches": safe_margin,
        "safe_width_inches": round(finished_width - safe_margin * 2, 6),
        "safe_height_inches": round(finished_height - safe_margin * 2, 6),
    })
    checks.append({
        "check": "safe_area_content",
        "status": "not_checked",
        "message": "This geometry-only slice cannot determine whether important visual content stays inside the safe area.",
    })
    if artwork["color_space"] not in ("cmyk", "grayscale", "monochrome"):
        message = f"Artwork color space is {artwork['color_space']}; the output color profile has not been converted or verified."
        warnings.append(message)
        checks.append({"check": "color_mode", "status": "warning", "color_space": artwork["color_space"]})
    else:
        checks.append({"check": "color_mode", "status": "passed", "color_space": artwork["color_space"]})
    if not artwork["has_icc_profile"]:
        warnings.append("Artwork has no embedded ICC profile.")
        checks.append({"check": "icc_profile", "status": "warning", "embedded": False})
    else:
        checks.append({"check": "icc_profile", "status": "passed", "embedded": True})
    if artwork["has_alpha"]:
        warnings.append("Artwork contains transparency; flattening and print-engine behavior have not been verified.")
        checks.append({"check": "transparency", "status": "warning", "present": True})
    else:
        checks.append({"check": "transparency", "status": "passed", "present": False})
    if artwork["frame_count"] > 1:
        warnings.append("Artwork has multiple frames; only the CorelDRAW importer's selected/default frame is expected.")
        checks.append({"check": "multiple_frames", "status": "warning", "frame_count": artwork["frame_count"]})
    else:
        checks.append({"check": "multiple_frames", "status": "passed", "frame_count": 1})
    checks.extend([
        {"check": "print_marks", "status": "not_checked", "message": "Print marks are not created in this slice."},
        {"check": "output_profile", "status": "not_checked", "message": "No output color profile or conversion policy is applied."},
        {"check": "pdf_export", "status": "not_checked", "message": "No controlled PDF preset or exported-file validation is performed."},
    ])

    selected_layout_placements = [dict(item) for item in layout["placements"][:copies]]
    if rotation_policy == "best_fit" and selected_layout_placements and len(selected_layout_placements) < layout["capacity"]:
        last_strip = selected_layout_placements[-1]["strip"]
        strip_items = [item for item in selected_layout_placements if item["strip"] == last_strip]
        sample = strip_items[0]
        strategy = layout["layout_strategy"]
        if strategy == "mixed_rotated_columns":
            full_count = math.floor(
                (layout["usable_height_inches"] + gutter) / (sample["height_inches"] + gutter) + 1e-12
            )
            if len(strip_items) < full_count:
                span = len(strip_items) * sample["height_inches"] + (len(strip_items) - 1) * gutter
                cursor_top = (
                    layout["sheet_height_inches"] - layout["margins_inches"]["top"]
                    - (layout["usable_height_inches"] - span) / 2
                )
                for index, item in enumerate(strip_items):
                    item["y_inches"] = round(cursor_top - sample["height_inches"] - index * (sample["height_inches"] + gutter), 6)
        else:
            full_count = math.floor(
                (layout["usable_width_inches"] + gutter) / (sample["width_inches"] + gutter) + 1e-12
            )
            if len(strip_items) < full_count:
                span = len(strip_items) * sample["width_inches"] + (len(strip_items) - 1) * gutter
                cursor_left = layout["margins_inches"]["left"] + (layout["usable_width_inches"] - span) / 2
                for index, item in enumerate(strip_items):
                    item["x_inches"] = round(cursor_left + index * (sample["width_inches"] + gutter), 6)

    placements = []
    for placement in selected_layout_placements:
        x = float(placement["x_inches"])
        y = float(placement["y_inches"])
        rotated = bool(placement["rotated"])
        placement_width = float(placement["width_inches"])
        placement_height = float(placement["height_inches"])
        unrotated_artwork_width = float(aspect["display_width_inches"])
        unrotated_artwork_height = float(aspect["display_height_inches"])
        artwork_width, artwork_height = (
            (unrotated_artwork_height, unrotated_artwork_width)
            if rotated else (unrotated_artwork_width, unrotated_artwork_height)
        )
        trim_width, trim_height = (finished_height, finished_width) if rotated else (finished_width, finished_height)
        safe_width = trim_width - safe_margin * 2
        safe_height = trim_height - safe_margin * 2
        artwork_x = x + (placement_width - artwork_width) / 2
        artwork_y = y + (placement_height - artwork_height) / 2
        placements.append({
            "copy": len(placements) + 1,
            "fit_mode": fit_mode,
            "rotation_degrees": 90 if rotated else 0,
            "rotated": rotated,
            "placement_box": {"x_inches": x, "y_inches": y, "width_inches": placement_width, "height_inches": placement_height},
            "artwork_box": {
                "x_inches": round(artwork_x, 6),
                "y_inches": round(artwork_y, 6),
                "width_inches": artwork_width,
                "height_inches": artwork_height,
            },
            "trim_box": {"x_inches": x + bleed, "y_inches": y + bleed, "width_inches": trim_width, "height_inches": trim_height},
            "safe_box": {
                "x_inches": round(x + bleed + safe_margin, 6),
                "y_inches": round(y + bleed + safe_margin, 6),
                "width_inches": round(safe_width, 6),
                "height_inches": round(safe_height, 6),
            },
            "source_crop_pixels": dict(crop),
        })

    has_cautions = bool(warnings) or any(item["status"] in ("warning", "not_checked") for item in checks)
    status = "failed" if blocking_issues else ("warning" if has_cautions else "passed")
    return {
        "ready_for_execution": not blocking_issues,
        "print_ready": False,
        "artwork": artwork,
        "job": {
            "finished_size_inches": {"width": finished_width, "height": finished_height},
            "placed_size_inches": {"width": placed_width, "height": placed_height},
            "sheet_size_inches": {"width": layout["sheet_width_inches"], "height": layout["sheet_height_inches"]},
            "supplied_sheet_size_inches": {"width": sheet_width, "height": sheet_height},
            "copies": copies,
            "bleed_inches": bleed,
            "safe_margin_inches": safe_margin,
            "margin_inches": margin,
            "gutter_inches": gutter,
            "minimum_dpi": min_dpi,
            "fit_mode": fit_mode,
            "rotation_policy": rotation_policy,
            "sheet_orientation": sheet_orientation,
            "margin_left_inches": edge_margins["left"],
            "margin_top_inches": edge_margins["top"],
            "margin_right_inches": edge_margins["right"],
            "margin_bottom_inches": edge_margins["bottom"],
            "gripper_inches": gripper,
            "gripper_edge": gripper_edge,
            "mark_clearance_inches": mark_clearance,
        },
        "requested_quantity": copies,
        "copies_per_sheet": layout["capacity"],
        "sheets_required": layout["sheets_required"],
        "total_produced": layout["total_produced"],
        "overage": layout["overage"],
        "layout": {key: value for key, value in layout.items() if key != "placements"},
        "aspect_fit": aspect,
        "placements": placements,
        "effective_dpi": {"x": round(effective_dpi_x, 2), "y": round(effective_dpi_y, 2), "minimum": round(effective_dpi, 2)},
        "preflight": {"status": status, "checks": checks, "blocking_issues": blocking_issues, "warnings": warnings},
        "limitations": [
            "This workflow handles one raster artwork file and prepares one imposed sheet document at a time.",
            "Safe-area geometry is calculated, but artwork content inside that area is not semantically inspected.",
            "It does not yet create crop/registration marks, cut paths, spot colors, or a controlled PDF preset.",
            "A successful plan is a production preflight candidate, not a claim that the exported file is print-ready.",
        ],
    }
