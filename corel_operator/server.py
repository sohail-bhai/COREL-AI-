"""MCP stdio server for CorelDRAW X7; COM actions run on one dedicated thread."""
from __future__ import annotations
import queue
import threading
from concurrent.futures import Future
from time import perf_counter
from typing import Any
from mcp.server.fastmcp import FastMCP
from .corel_bridge import CorelBridge
from .results import error_result, success_result
from .workflows import (
    build_chest_number_sequence as _build_chest_number_sequence,
    calculate_sheet_layout as _calculate_sheet_layout,
)
from .design_plans import (
    validate_design_plan as _validate_design_plan,
    preview_design_plan as _preview_design_plan,
)
from .print_jobs import plan_print_job as _plan_print_job
from .contour_nesting import (
    classify_imposition_job as _classify_imposition_job,
    plan_contour_nesting as _plan_contour_nesting,
)

mcp = FastMCP("coreldraw-ai-operator")


class CorelDispatcher:
    def __init__(self) -> None:
        self._jobs: queue.Queue[Any] = queue.Queue()
        self._ready = threading.Event()
        self._startup_error: str | None = None
        self._thread = threading.Thread(target=self._worker, name="CorelDRAW-COM-STA", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise RuntimeError("CorelDRAW COM worker did not initialize within 15 seconds.")
        if self._startup_error:
            raise RuntimeError(self._startup_error)

    def _worker(self) -> None:
        pythoncom = None
        try:
            import pythoncom as _pythoncom  # type: ignore
            pythoncom = _pythoncom
            pythoncom.CoInitialize()
            self._bridge = CorelBridge()
        except Exception as exc:
            self._startup_error = "Could not initialize the dedicated Windows COM thread. Check pywin32. Details: " + str(exc)
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    break
                method_name, args, kwargs, future = job
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    future.set_result(getattr(self._bridge, method_name)(*args, **kwargs))
                except BaseException as exc:
                    future.set_exception(exc)
        finally:
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        if not self._thread.is_alive():
            raise RuntimeError("CorelDRAW COM worker is not running.")
        future: Future[Any] = Future()
        self._jobs.put((method_name, args, kwargs, future))
        return future.result(timeout=120)

    def close(self, timeout: float = 5.0) -> None:
        """Stop the worker after queued work; primarily used by controlled shutdown/tests."""
        if not self._thread.is_alive():
            return
        self._jobs.put(None)
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise RuntimeError("CorelDRAW COM worker did not stop within the timeout.")


dispatcher = CorelDispatcher()


def _tool(tool_name: str, method: str, *args: Any, **kwargs: Any) -> dict:
    started = perf_counter()
    try:
        data = dispatcher.call(method, *args, **kwargs)
        return success_result(tool_name, data, (perf_counter() - started) * 1000)
    except Exception as exc:
        return error_result(tool_name, exc, (perf_counter() - started) * 1000)


@mcp.tool()
def corel_status() -> dict:
    """Report CorelDRAW version, active document and protected target document. This does not edit anything."""
    return _tool("corel_status", "status")


@mcp.tool()
def list_open_documents() -> dict:
    """List open CorelDRAW documents without activating, selecting, or binding any of them."""
    return _tool("list_open_documents", "list_open_documents")


@mcp.tool()
def get_document_info() -> dict:
    """Inspect identity, path, dirty state, units, and active page for the bound target document."""
    return _tool("get_document_info", "get_document_info")


@mcp.tool()
def list_pages() -> dict:
    """List pages and their actual dimensions for the bound target document without changing the active page."""
    return _tool("list_pages", "list_pages")


@mcp.tool()
def get_page_bounds(page_index: int) -> dict:
    """Return page-local bottom-left bounds in inches for one page of the bound target document."""
    return _tool("get_page_bounds", "get_page_bounds", page_index)


@mcp.tool()
def list_layers(page_index: int) -> dict:
    """List page and master layers with state and object counts without changing the active layer."""
    return _tool("list_layers", "list_layers", page_index)


@mcp.tool()
def get_object_info(object_name: str = "", shape_index: int = 0) -> dict:
    """Inspect one object selected unambiguously by bridge name or 1-based active-page shape index."""
    return _tool("get_object_info", "get_object_info", object_name, shape_index)


@mcp.tool()
def create_document(width_inches: float = 8.27, height_inches: float = 11.69) -> dict:
    """Create and bind a new target document. Subsequent edits/save target this document even if another window is activated."""
    return _tool("create_document", "create_document", width_inches, height_inches)


@mcp.tool()
def use_active_document(confirm_existing_document: bool = False) -> dict:
    """Explicitly bind the currently active document for editing. Set confirm_existing_document=True only after backing up client work."""
    return _tool("use_active_document", "use_active_document", confirm_existing_document)


@mcp.tool()
def add_text(text: str, x_inches: float, y_inches: float, size_points: float = 24,
             font: str = "Arial", bold: bool = False, object_name: str = "") -> dict:
    """Create editable artistic text in the target document. Names are used to edit objects later."""
    return _tool("add_text", "add_text", text, x_inches, y_inches, size_points, font, bold, object_name)


@mcp.tool()
def draw_rectangle(x_inches: float, y_inches: float, width_inches: float, height_inches: float,
                   object_name: str = "") -> dict:
    """Draw a rectangle in the target document; optionally assign a useful unique object_name."""
    return _tool("draw_rectangle", "draw_rectangle", x_inches, y_inches, width_inches, height_inches, object_name)


@mcp.tool()
def draw_ellipse(x_inches: float, y_inches: float, width_inches: float, height_inches: float,
                 object_name: str = "") -> dict:
    """Draw an ellipse in the target document; optionally assign a useful unique object_name."""
    return _tool("draw_ellipse", "draw_ellipse", x_inches, y_inches, width_inches, height_inches, object_name)


@mcp.tool()
def list_objects(max_objects: int = 200) -> dict:
    """List objects on the target page including object names, indexes, positions, sizes and text where available."""
    return _tool("list_objects", "list_objects", max_objects)


@mcp.tool()
def calculate_sheet_layout(item_width_inches: float, item_height_inches: float,
                           sheet_width_inches: float, sheet_height_inches: float,
                           margin_inches: float = 0.0, gutter_inches: float = 0.0,
                           allow_rotate: bool = True,
                           rotation_policy: str | None = None,
                           sheet_orientation: str = "fixed",
                           margin_left_inches: float | None = None,
                           margin_top_inches: float | None = None,
                           margin_right_inches: float | None = None,
                           margin_bottom_inches: float | None = None,
                           gripper_inches: float = 0.0,
                           gripper_edge: str = "bottom",
                           mark_clearance_inches: float = 0.0,
                           requested_quantity: int | None = None) -> dict:
    """Optimize upright, rotated, or mixed-strip N-up layouts without editing CorelDRAW."""
    started = perf_counter()
    try:
        data = _calculate_sheet_layout(
            item_width_inches, item_height_inches, sheet_width_inches,
            sheet_height_inches, margin_inches, gutter_inches, allow_rotate,
            rotation_policy, sheet_orientation, margin_left_inches,
            margin_top_inches, margin_right_inches, margin_bottom_inches,
            gripper_inches, gripper_edge, mark_clearance_inches,
            requested_quantity,
        )
        warnings = []
        if data.get("placements_truncated"):
            warnings.append("Placement coordinates were capped at 2000; capacity remains exact.")
        return success_result("calculate_sheet_layout", data, (perf_counter() - started) * 1000, warnings)
    except Exception as exc:
        return error_result("calculate_sheet_layout", exc, (perf_counter() - started) * 1000)


@mcp.tool()
def classify_imposition_job(
    footprint_kind: str = "auto",
    has_explicit_cut_contour: bool = False,
    cutting_method: str = "unknown",
    allow_180_rotation: bool | None = None,
    source_is_combined: bool = False,
) -> dict:
    """Choose rectangular N-up or contour nesting, asking cutter questions only for non-rectangular work."""
    started = perf_counter()
    try:
        data = _classify_imposition_job(
            footprint_kind, has_explicit_cut_contour, cutting_method,
            allow_180_rotation, source_is_combined,
        )
        return success_result("classify_imposition_job", data, (perf_counter() - started) * 1000)
    except Exception as exc:
        return error_result("classify_imposition_job", exc, (perf_counter() - started) * 1000)


@mcp.tool()
def plan_contour_nesting(
    contour_points_inches: list[list[float]],
    sheet_width_inches: float,
    sheet_height_inches: float,
    quantity: int = 1,
    margin_inches: float = 0.25,
    gutter_inches: float = 0.0,
    bleed_inches: float = 0.0,
    cutting_method: str = "unknown",
    allow_180_rotation: bool | None = None,
    sheet_orientation: str = "fixed",
    geometry_tolerance_inches: float = 0.0005,
) -> dict:
    """Plan deterministic 0/180-degree paired rows from an explicit closed cut contour."""
    started = perf_counter()
    try:
        data = _plan_contour_nesting(
            contour_points_inches, sheet_width_inches, sheet_height_inches,
            quantity, margin_inches, gutter_inches, bleed_inches,
            cutting_method, allow_180_rotation, sheet_orientation,
            geometry_tolerance_inches,
        )
        return success_result("plan_contour_nesting", data, (perf_counter() - started) * 1000)
    except Exception as exc:
        return error_result("plan_contour_nesting", exc, (perf_counter() - started) * 1000)


@mcp.tool()
def inspect_repeat_unit(
    source_group_name: str,
    dieline_name: str,
    cutting_method: str = "unknown",
    allow_180_rotation: bool | None = None,
    curve_precision: int = 5,
) -> dict:
    """Inspect one vector repeat group and its named dieline, then return workflow questions or readiness."""
    return _tool(
        "inspect_repeat_unit", "inspect_repeat_unit", source_group_name,
        dieline_name, cutting_method, allow_180_rotation, curve_precision,
    )


@mcp.tool()
def prepare_contour_nesting(
    source_group_name: str,
    dieline_name: str,
    sheet_width_inches: float,
    sheet_height_inches: float,
    copies: int = 1,
    margin_inches: float = 0.25,
    gutter_inches: float = 0.0,
    bleed_inches: float = 0.0,
    cutting_method: str = "unknown",
    allow_180_rotation: bool | None = None,
    sheet_orientation: str = "fixed",
    curve_precision: int = 5,
    object_name_prefix: str = "Nested_Copy",
    output_layer_name: str = "Imposition_Repeats",
) -> dict:
    """Create separately grouped vector repeats on a new page using a verified contour-nesting plan."""
    return _tool(
        "prepare_contour_nesting", "prepare_contour_nesting", source_group_name,
        dieline_name, sheet_width_inches, sheet_height_inches, copies,
        margin_inches, gutter_inches, bleed_inches, cutting_method,
        allow_180_rotation, sheet_orientation, curve_precision,
        object_name_prefix, output_layer_name,
    )


@mcp.tool()
def prepare_imposition_job(
    source_group_name: str,
    dieline_name: str,
    sheet_width_inches: float,
    sheet_height_inches: float,
    quantity: int = 1,
    margin_inches: float = 0.25,
    gutter_inches: float = 0.0,
    bleed_inches: float = 0.0,
    cutting_method: str = "unknown",
    allow_180_rotation: bool | None = None,
    sheet_orientation: str = "fixed",
    curve_precision: int = 5,
    object_name_prefix: str = "Imposed_Copy",
    output_layer_name: str = "Imposition_Repeats",
    confirm_execution: bool = False,
    approved_plan_fingerprint: str = "",
) -> dict:
    """Plan first, then fingerprint-gate source-preserving vector imposition execution."""
    return _tool(
        "prepare_imposition_job", "prepare_imposition_job", source_group_name,
        dieline_name, sheet_width_inches, sheet_height_inches, quantity,
        margin_inches, gutter_inches, bleed_inches, cutting_method,
        allow_180_rotation, sheet_orientation, curve_precision,
        object_name_prefix, output_layer_name, confirm_execution,
        approved_plan_fingerprint,
    )


@mcp.tool()
def plan_chest_number_batch(start: int, end: int, zero_pad_width: int = 0,
                            item_width_inches: float | None = None,
                            item_height_inches: float | None = None,
                            sheet_width_inches: float | None = None,
                            sheet_height_inches: float | None = None,
                            margin_inches: float = 0.0, gutter_inches: float = 0.0,
                            allow_rotate: bool = True) -> dict:
    """Preview a validated chest-number sequence and optional sheet placement without editing CorelDRAW."""
    started = perf_counter()
    try:
        data = _build_chest_number_sequence(
            start, end, zero_pad_width, item_width_inches, item_height_inches,
            sheet_width_inches, sheet_height_inches, margin_inches, gutter_inches,
            allow_rotate,
        )
        return success_result("plan_chest_number_batch", data, (perf_counter() - started) * 1000)
    except Exception as exc:
        return error_result("plan_chest_number_batch", exc, (perf_counter() - started) * 1000)


@mcp.tool()
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
) -> dict:
    """Preflight raster artwork and deterministic best-fit N-up imposition without opening CorelDRAW."""
    started = perf_counter()
    try:
        data = _plan_print_job(
            file_path, finished_width_inches, finished_height_inches,
            sheet_width_inches, sheet_height_inches, copies=copies,
            bleed_inches=bleed_inches, safe_margin_inches=safe_margin_inches,
            margin_inches=margin_inches, gutter_inches=gutter_inches,
            minimum_dpi=minimum_dpi, artwork_includes_bleed=artwork_includes_bleed,
            fit_mode=fit_mode, allow_low_resolution=allow_low_resolution,
            rotation_policy=rotation_policy, sheet_orientation=sheet_orientation,
            margin_left_inches=margin_left_inches, margin_top_inches=margin_top_inches,
            margin_right_inches=margin_right_inches, margin_bottom_inches=margin_bottom_inches,
            gripper_inches=gripper_inches, gripper_edge=gripper_edge,
            mark_clearance_inches=mark_clearance_inches,
        )
        return success_result("plan_print_job", data, (perf_counter() - started) * 1000, data["preflight"]["warnings"])
    except Exception as exc:
        return error_result("plan_print_job", exc, (perf_counter() - started) * 1000)


@mcp.tool()
def prepare_print_job(
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
    object_name_prefix: str = "Print_Artwork",
    rotation_policy: str = "never",
    sheet_orientation: str = "fixed",
    margin_left_inches: float | None = None,
    margin_top_inches: float | None = None,
    margin_right_inches: float | None = None,
    margin_bottom_inches: float | None = None,
    gripper_inches: float = 0.0,
    gripper_edge: str = "bottom",
    mark_clearance_inches: float = 0.0,
) -> dict:
    """Create a new print sheet and place fitted/cropped raster copies after production preflight."""
    return _tool(
        "prepare_print_job", "prepare_print_job", file_path,
        finished_width_inches, finished_height_inches, sheet_width_inches,
        sheet_height_inches, copies, bleed_inches, safe_margin_inches,
        margin_inches, gutter_inches, minimum_dpi, artwork_includes_bleed,
        fit_mode, allow_low_resolution, object_name_prefix,
        rotation_policy, sheet_orientation, margin_left_inches,
        margin_top_inches, margin_right_inches, margin_bottom_inches,
        gripper_inches, gripper_edge, mark_clearance_inches,
    )


@mcp.tool()
def create_chest_number_batch(start: int, end: int,
                              item_width_inches: float, item_height_inches: float,
                              font: str = "Arial", font_size_points: float = 72.0,
                              zero_pad_width: int = 0,
                              sheet_width_inches: float | None = None,
                              sheet_height_inches: float | None = None,
                              margin_inches: float = 0.0, gutter_inches: float = 0.0,
                              bold: bool = True, draw_border: bool = True,
                              header_text: str = "", footer_text: str = "",
                              allow_rotate: bool = False) -> dict:
    """Generate a validated sequence of editable chest-number designs on the bound target document."""
    return _tool(
        "create_chest_number_batch", "create_chest_number_batch",
        start, end, item_width_inches, item_height_inches,
        font, font_size_points, zero_pad_width,
        sheet_width_inches, sheet_height_inches, margin_inches, gutter_inches,
        bold, draw_border, header_text, footer_text, allow_rotate,
    )


@mcp.tool()
def validate_design_plan(plan: dict) -> dict:
    """Validate a multi-element design plan against schema and domain rules without modifying CorelDRAW."""
    started = perf_counter()
    try:
        data = _validate_design_plan(plan)
        warnings = data.get("warnings", [])
        return success_result("validate_design_plan", data, (perf_counter() - started) * 1000, warnings)
    except Exception as exc:
        return error_result("validate_design_plan", exc, (perf_counter() - started) * 1000)


@mcp.tool()
def preview_design_plan(plan: dict) -> dict:
    """Preview layout statistics, palette, typography, and bounding box of a design plan without modifying CorelDRAW."""
    started = perf_counter()
    try:
        data = _preview_design_plan(plan)
        warnings = data.get("warnings", [])
        return success_result("preview_design_plan", data, (perf_counter() - started) * 1000, warnings)
    except Exception as exc:
        return error_result("preview_design_plan", exc, (perf_counter() - started) * 1000)


@mcp.tool()
def execute_design_plan(plan: dict, create_new_document: bool = False,
                        rollback_on_failure: bool = True) -> dict:
    """Execute a structured multi-element design plan transactionally with atomic rollback on failure."""
    return _tool(
        "execute_design_plan", "execute_design_plan",
        plan, create_new_document, rollback_on_failure,
    )


@mcp.tool()
def set_fill_color(red: int, green: int, blue: int, object_name: str = "", shape_index: int = 0) -> dict:
    """Set an object's solid fill using RGB 0-255. Specify exactly one selector: object_name or 1-based shape_index."""
    return _tool("set_fill_color", "set_fill_color", red, green, blue, object_name, shape_index)


@mcp.tool()
def set_outline(red: int, green: int, blue: int, width_points: float = 1.0,
                object_name: str = "", shape_index: int = 0) -> dict:
    """Set an object's outline color/width in points. Use width_points=0 to remove outline."""
    return _tool("set_outline", "set_outline", red, green, blue, width_points, object_name, shape_index)


@mcp.tool()
def move_object(x_inches: float, y_inches: float, object_name: str = "", shape_index: int = 0) -> dict:
    """Move an object so its bottom-left reference point is at x/y inches on the page."""
    return _tool("move_object", "move_object", x_inches, y_inches, object_name, shape_index)


@mcp.tool()
def resize_object(width_inches: float = 0, height_inches: float = 0, keep_aspect_ratio: bool = False,
                  object_name: str = "", shape_index: int = 0) -> dict:
    """Resize an object in inches. For proportional resizing, provide only one dimension and set keep_aspect_ratio=True."""
    return _tool("resize_object", "resize_object", width_inches, height_inches, keep_aspect_ratio, object_name, shape_index)


@mcp.tool()
def set_text_content(new_text: str, object_name: str = "", shape_index: int = 0) -> dict:
    """Replace the text of an existing text object. Target must be artistic/paragraph text."""
    return _tool("set_text_content", "set_text_content", new_text, object_name, shape_index)


@mcp.tool()
def rename_object(new_name: str, object_name: str = "", shape_index: int = 0) -> dict:
    """Rename an object to make later natural-language edits more reliable. Supply exactly one current selector."""
    return _tool("rename_object", "rename_object", new_name, object_name, shape_index)


@mcp.tool()
def duplicate_object(offset_x_inches: float = 0.25, offset_y_inches: float = -0.25,
                     object_name: str = "", shape_index: int = 0, new_name: str = "") -> dict:
    """Duplicate an object with an offset in inches. Supply exactly one source selector."""
    return _tool("duplicate_object", "duplicate_object", offset_x_inches, offset_y_inches, object_name, shape_index, new_name)


@mcp.tool()
def import_artwork(file_path: str, object_name: str = "AI_Artwork") -> dict:
    """Import local PNG/JPG/BMP/TIFF/SVG/PDF/EPS/AI/WMF/EMF/CMX artwork. Then inspect and position it with list_objects/move_object/resize_object."""
    return _tool("import_artwork", "import_artwork", file_path, object_name)


@mcp.tool()
def save_document(path: str) -> dict:
    """Save the bound target document as a new CDR file. Refuses to overwrite existing files."""
    return _tool("save_document", "save_document", path)


@mcp.tool()
def export_pdf(path: str) -> dict:
    """Export the bound target document to a new PDF. Print settings need separate verification."""
    return _tool("export_pdf", "export_pdf", path)


@mcp.tool()
def align_objects(
    object_names: list[str],
    horizontal: str = "none",
    vertical: str = "none",
    align_to: str = "last_selected",
) -> dict:
    """Align two or more shapes relative to a reference target (last_selected or first_selected)."""
    return _tool("align_objects", "align_objects", object_names, horizontal, vertical, align_to)


@mcp.tool()
def align_to_page(
    object_names: list[str],
    horizontal: str = "none",
    vertical: str = "none",
    align_as_group: bool = False,
) -> dict:
    """Align one or more shapes to page edges or page center, individually or collectively as a group."""
    return _tool("align_to_page", "align_to_page", object_names, horizontal, vertical, align_as_group)


@mcp.tool()
def group_shapes(object_names: list[str], group_name: str = "") -> dict:
    """Group two or more shapes on the active page into a single named group shape."""
    return _tool("group_shapes", "group_shapes", object_names, group_name)


@mcp.tool()
def ungroup_shapes(
    object_name: str = "",
    shape_index: int = 0,
    ungroup_all: bool = False,
) -> dict:
    """Ungroup a group shape into individual shapes. Use ungroup_all=True to ungroup nested groups recursively."""
    return _tool("ungroup_shapes", "ungroup_shapes", object_name, shape_index, ungroup_all)


if __name__ == "__main__":
    mcp.run(transport="stdio")
