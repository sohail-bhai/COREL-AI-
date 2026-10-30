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


if __name__ == "__main__":
    mcp.run(transport="stdio")
