"""CorelDRAW X7-oriented COM bridge for the CorelDRAW AI Operator prototype.

Operations target a document created by this bridge. Editing an already-open document requires
an explicit `use_active_document` call so a client design isn't modified by accident.
"""
from __future__ import annotations

import os
import platform
import struct
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path
from typing import Any, Iterator

from .adapters import CorelX7Adapter
from .errors import CorelBridgeError, ErrorCode
from .version import BRIDGE_VERSION, CAPABILITY_PROFILE_ID, TOOL_SCHEMA_VERSION
from .workflows import build_chest_number_sequence
from .design_plans import validate_design_plan


class CorelBridge:
    CDR_INCH = CorelX7Adapter.CDR_INCH
    CDR_BOTTOM_LEFT = CorelX7Adapter.CDR_BOTTOM_LEFT
    MAX_IMPORT_BYTES = 250 * 1024 * 1024
    ALLOWED_IMPORT_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif",
        ".svg", ".pdf", ".eps", ".ai", ".wmf", ".emf", ".cmx"
    }

    def __init__(self, adapter: CorelX7Adapter | None = None) -> None:
        self.adapter = adapter or CorelX7Adapter()
        self.app: Any | None = None
        self.target_doc: Any | None = None
        self.prog_id_used: str | None = None
        self.connection_mode: str | None = None
        self.application_info: dict[str, Any] | None = None
        self._document_sessions: dict[str, str] = {}
        self._next_document_session = 1

    def connect(self) -> dict[str, Any]:
        if os.name != "nt":
            raise CorelBridgeError(
                "CorelDRAW COM automation is available only on Windows.",
                ErrorCode.UNSUPPORTED_IN_PROFILE,
            )
        try:
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise CorelBridgeError(
                "pywin32 is missing. Run: python -m pip install -r requirements.txt",
                ErrorCode.COREL_COM_ERROR,
            ) from exc

        errors: list[str] = []
        unsupported: list[CorelBridgeError] = []
        for mode, prog_id in self.adapter.CONNECTION_CANDIDATES:
            try:
                candidate = (
                    win32com.client.GetActiveObject(prog_id)
                    if mode == "GetActiveObject"
                    else win32com.client.Dispatch(prog_id)
                )
                application_info = self.adapter.validate_application(candidate, prog_id)
                self.app = candidate
                self.prog_id_used = prog_id
                self.connection_mode = mode
                self.application_info = application_info
                break
            except CorelBridgeError as exc:
                unsupported.append(exc)
                errors.append(f"{mode}({prog_id}): {exc}")
            except Exception as exc:
                errors.append(f"{mode}({prog_id}): {exc}")
        if self.app is None:
            if unsupported:
                raise unsupported[-1]
            raise CorelBridgeError(
                "Could not connect to CorelDRAW. Open CorelDRAW and retry. Details: "
                + " | ".join(errors),
                ErrorCode.COREL_COM_ERROR,
            )
        return self.status()

    def _require_app(self) -> Any:
        if self.app is None:
            self.connect()
        return self.app

    def _active_document(self) -> Any | None:
        try:
            return self._require_app().ActiveDocument
        except Exception:
            return None

    def _target_document(self) -> Any:
        """Return the bridge's bound target, never silently fall back to another active file."""
        if self.target_doc is not None:
            return self.target_doc
        raise CorelBridgeError(
            "No target document is bound. Call create_document for a new file, or explicitly call "
            "use_active_document(confirm_existing_document=True) to allow editing the current file.",
            ErrorCode.NO_TARGET_DOCUMENT,
        )

    def use_active_document(self, confirm_existing_document: bool) -> dict[str, Any]:
        if confirm_existing_document is not True:
            raise CorelBridgeError(
                "To protect client work, this operation requires confirm_existing_document=True.",
                ErrorCode.CONFIRMATION_REQUIRED,
            )
        doc = self._active_document()
        if doc is None:
            raise CorelBridgeError(
                "CorelDRAW has no active document to bind.",
                ErrorCode.NO_TARGET_DOCUMENT,
            )
        self.target_doc = doc
        return {
            "bound": True,
            "target_document_name": _safe_attr(doc, "Name"),
            "warning": "Subsequent editing operations will modify this document. Save a backup first."
        }

    @contextmanager
    def _in_inches(self, doc: Any) -> Iterator[None]:
        previous = None
        changed = False
        try:
            previous = int(doc.Unit)
            if previous != self.CDR_INCH:
                doc.Unit = self.CDR_INCH
                changed = True
            yield
        finally:
            if changed and previous is not None:
                try:
                    doc.Unit = previous
                except Exception:
                    pass

    @contextmanager
    def _reference_point(self, doc: Any, point: int = CDR_BOTTOM_LEFT) -> Iterator[None]:
        previous = None
        changed = False
        try:
            previous = int(doc.ReferencePoint)
            if previous != point:
                doc.ReferencePoint = point
                changed = True
            yield
        finally:
            if changed and previous is not None:
                try:
                    doc.ReferencePoint = previous
                except Exception:
                    pass

    @staticmethod
    def _page_dimensions(page: Any) -> dict[str, Any]:
        try:
            result = page.GetSize()
            if isinstance(result, (tuple, list)) and len(result) >= 2:
                return {"width_document_units": float(result[0]),
                        "height_document_units": float(result[1])}
        except Exception:
            pass
        result: dict[str, Any] = {}
        for key, attr in (("width_document_units", "SizeWidth"),
                          ("height_document_units", "SizeHeight")):
            try:
                result[key] = float(getattr(page, attr))
            except Exception:
                result[key] = None
        return result

    def _shape_bounds_inches(self, doc: Any, shape: Any) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        with self._in_inches(doc), self._reference_point(doc, self.CDR_BOTTOM_LEFT):
            for key, attr in (
                ("x", "PositionX"),
                ("y", "PositionY"),
                ("width", "SizeWidth"),
                ("height", "SizeHeight"),
            ):
                try:
                    result[key] = round(float(getattr(shape, attr)), 4)
                except Exception:
                    result[key] = None
        return result

    def _text_readback(self, shape: Any) -> dict[str, Any]:
        try:
            story = shape.Text.Story
        except Exception:
            return {
                "text": None,
                "font": None,
                "size_points": None,
                "bold": None,
                "bold_code": None,
            }
        text = _safe_attr(story, "Text")
        font = _safe_attr(story, "Font")
        size = _safe_attr(story, "Size")
        bold_code = _safe_attr(story, "Bold")
        try:
            size = float(size)
        except (TypeError, ValueError):
            size = None
        try:
            bold_code = int(bold_code)
        except (TypeError, ValueError):
            bold_code = None
        return {
            "text": str(text) if text is not None else None,
            "font": str(font) if font is not None else None,
            "size_points": size,
            "bold": bold_code == self.adapter.CDR_TRUE if bold_code is not None else None,
            "bold_code": bold_code,
        }

    def _color_readback(self, color: Any) -> dict[str, Any] | None:
        if color is None:
            return None
        type_code = _safe_int_attr(color, "Type")
        model = self.adapter.COLOR_TYPE_NAMES.get(type_code, "unknown")
        result: dict[str, Any] = {
            "type_code": type_code,
            "model": model,
            "hex_value": _safe_string_attr(color, "HexValue"),
            "name": _safe_string_attr(color, "Name"),
        }
        if model == "rgb":
            result["value"] = {
                "red": _safe_int_attr(color, "RGBRed"),
                "green": _safe_int_attr(color, "RGBGreen"),
                "blue": _safe_int_attr(color, "RGBBlue"),
            }
        elif model == "cmyk":
            result["value"] = {
                "cyan": _safe_int_attr(color, "CMYKCyan"),
                "magenta": _safe_int_attr(color, "CMYKMagenta"),
                "yellow": _safe_int_attr(color, "CMYKYellow"),
                "black": _safe_int_attr(color, "CMYKBlack"),
            }
        elif model == "gray":
            result["value"] = {"gray": _safe_int_attr(color, "Gray")}
        elif model in {"spot", "pantone", "pantone_hex"}:
            result["value"] = {
                "spot_name": _safe_string_attr(color, "SpotColorName"),
                "tint": _safe_int_attr(color, "Tint"),
            }
        else:
            result["value"] = None
        return result

    def _fill_readback(self, shape: Any) -> dict[str, Any]:
        fill = _safe_attr(shape, "Fill")
        type_code = _safe_int_attr(fill, "Type") if fill is not None else None
        type_name = self.adapter.FILL_TYPE_NAMES.get(type_code, "unknown")
        color = None
        if type_name == "uniform":
            color = self._color_readback(_safe_attr(fill, "UniformColor"))
        return {
            "type_code": type_code,
            "type": type_name,
            "color": color,
        }

    def _outline_readback(self, shape: Any) -> dict[str, Any]:
        outline = _safe_attr(shape, "Outline")
        type_code = _safe_int_attr(outline, "Type") if outline is not None else None
        type_name = self.adapter.OUTLINE_TYPE_NAMES.get(type_code, "unknown")
        present = type_code not in (None, 0)
        return {
            "type_code": type_code,
            "type": type_name,
            "present": present,
            "width_raw": _safe_float_attr(outline, "Width") if present else None,
            "width_units": "coreldraw_outline_width_unverified" if present else None,
            "color": self._color_readback(_safe_attr(outline, "Color")) if present else None,
        }

    @staticmethod
    def _shape_identity(shape: Any) -> dict[str, Any]:
        layer = _safe_attr(shape, "Layer")
        page = _safe_attr(shape, "Page")
        return {
            "object_name": str(_safe_attr(shape, "Name") or ""),
            "static_id": _safe_int_attr(shape, "StaticID"),
            "shape_type_code": _safe_int_attr(shape, "Type"),
            "layer_name": _safe_string_attr(layer, "Name"),
            "page_index": _safe_int_attr(page, "Index"),
        }

    def status(self) -> dict[str, Any]:
        app = self._require_app()
        info: dict[str, Any] = {
            "connected": True,
            "bridge_version": BRIDGE_VERSION,
            "tool_schema_version": TOOL_SCHEMA_VERSION,
            "capability_profile_id": CAPABILITY_PROFILE_ID,
            "capability_profile": self.adapter.profile_summary(),
            "prog_id_used": self.prog_id_used,
            "connection_mode": self.connection_mode,
            "runtime": {
                "python_version": platform.python_version(),
                "python_bitness": struct.calcsize("P") * 8,
                "platform": platform.platform(),
                "mcp_sdk_version": _distribution_version("mcp"),
                "pywin32_version": _distribution_version("pywin32"),
            },
        }
        for key, attr in (
            ("version", "Version"),
            ("version_major", "VersionMajor"),
            ("version_minor", "VersionMinor"),
            ("version_build", "VersionBuild"),
            ("visible", "Visible"),
        ):
            try:
                info[key] = getattr(app, attr)
            except Exception:
                info[key] = None
        active = self._active_document()
        info["active_document_name"] = _safe_attr(active, "Name") if active is not None else None
        info["active_document_open"] = active is not None
        info["target_document_name"] = _safe_attr(self.target_doc, "Name") if self.target_doc is not None else None
        info["target_document_bound"] = self.target_doc is not None
        inspected = self.target_doc if self.target_doc is not None else active
        if inspected is not None:
            info["document_name"] = _safe_attr(inspected, "Name")
            try:
                info["page_count"] = int(inspected.Pages.Count)
            except Exception:
                info["page_count"] = None
            try:
                info["unit_code"] = int(inspected.Unit)
                info["unit_name"] = self.adapter.unit_name(info["unit_code"])
            except Exception:
                info["unit_code"] = None
                info["unit_name"] = None
            try:
                info["page_size"] = self._page_dimensions(inspected.ActivePage)
            except Exception:
                info["page_size"] = None
        return info

    @staticmethod
    def _com_identity(value: Any) -> str:
        """Return a process-local identity key without changing COM selection or focus."""
        ole = _safe_attr(value, "_oleobj_")
        if ole is not None:
            try:
                return f"iunknown:{int(ole.GetIUnknown())}"
            except Exception:
                pass
        return f"python:{id(value)}"

    def _same_com_object(self, left: Any, right: Any) -> bool:
        return left is not None and right is not None and self._com_identity(left) == self._com_identity(right)

    def _document_session_id(self, document: Any) -> str:
        key = self._com_identity(document)
        session_id = self._document_sessions.get(key)
        if session_id is None:
            session_id = f"doc-{self._next_document_session:04d}"
            self._next_document_session += 1
            self._document_sessions[key] = session_id
        return session_id

    @staticmethod
    def _collection_item(collection: Any, index: int) -> Any:
        try:
            return collection.Item(index)
        except Exception:
            return collection(index)

    def _page_at(self, document: Any, page_index: int) -> Any:
        if type(page_index) is not int or page_index < 1:
            raise CorelBridgeError("page_index must be a positive integer.", ErrorCode.INVALID_ARGUMENT)
        pages = document.Pages
        count = int(pages.Count)
        if page_index > count:
            raise CorelBridgeError(
                f"Page {page_index} was not found; the target document has {count} page(s).",
                ErrorCode.OBJECT_NOT_FOUND,
                {"page_index": page_index, "page_count": count},
            )
        return self._collection_item(pages, page_index)

    def _document_summary(self, document: Any, active: Any, target: Any) -> dict[str, Any]:
        pages = _safe_attr(document, "Pages")
        page_count = _safe_int_attr(pages, "Count") if pages is not None else None
        full_path = _safe_string_attr(document, "FullFileName")
        return {
            "session_id": self._document_session_id(document),
            "name": _safe_string_attr(document, "Name"),
            "full_path": full_path or None,
            "saved": bool(full_path),
            "dirty": _safe_bool_attr(document, "Dirty"),
            "page_count": page_count,
            "unit_code": _safe_int_attr(document, "Unit"),
            "unit_name": self.adapter.unit_name(_safe_int_attr(document, "Unit")),
            "is_active": self._same_com_object(document, active),
            "is_bound_target": self._same_com_object(document, target),
        }

    def list_open_documents(self) -> dict[str, Any]:
        app = self._require_app()
        documents = app.Documents
        active = self._active_document()
        result = []
        for index in range(1, int(documents.Count) + 1):
            document = self._collection_item(documents, index)
            summary = self._document_summary(document, active, self.target_doc)
            summary["collection_index"] = index
            result.append(summary)
        return {"documents": result}

    def get_document_info(self) -> dict[str, Any]:
        document = self._target_document()
        summary = self._document_summary(document, self._active_document(), document)
        active_page = _safe_attr(document, "ActivePage")
        summary["active_page_index"] = _safe_int_attr(active_page, "Index")
        summary["active_page_name"] = _safe_string_attr(active_page, "Name")
        return {"document_name": _safe_string_attr(document, "Name"), "document": summary}

    def list_pages(self) -> dict[str, Any]:
        document = self._target_document()
        active_page = _safe_attr(document, "ActivePage")
        pages = document.Pages
        result = []
        with self._in_inches(document):
            for index in range(1, int(pages.Count) + 1):
                page = self._collection_item(pages, index)
                dimensions = self._page_dimensions(page)
                result.append({
                    "page_index": _safe_int_attr(page, "Index") or index,
                    "name": _safe_string_attr(page, "Name"),
                    "orientation_code": _safe_int_attr(page, "Orientation"),
                    "width_inches": dimensions.get("width_document_units"),
                    "height_inches": dimensions.get("height_document_units"),
                    "is_active": self._same_com_object(page, active_page),
                })
        return {"document_name": _safe_string_attr(document, "Name"), "pages": result}

    def get_page_bounds(self, page_index: int) -> dict[str, Any]:
        document = self._target_document()
        page = self._page_at(document, page_index)
        with self._in_inches(document):
            dimensions = self._page_dimensions(page)
        width = dimensions.get("width_document_units")
        height = dimensions.get("height_document_units")
        if width is None or height is None:
            raise CorelBridgeError("Could not read the requested page dimensions.", ErrorCode.COREL_COM_ERROR)
        return {
            "document_name": _safe_string_attr(document, "Name"),
            "page_index": page_index,
            "bounds": {
                "lower_left": {"x": 0.0, "y": 0.0},
                "upper_right": {"x": width, "y": height},
                "center": {"x": width / 2.0, "y": height / 2.0},
                "width": width,
                "height": height,
                "coordinate_space": "page_local_bottom_left",
            },
            "unit": "inch",
        }

    def list_layers(self, page_index: int) -> dict[str, Any]:
        document = self._target_document()
        page = self._page_at(document, page_index)
        active_layer = _safe_attr(page, "ActiveLayer")
        layers = _safe_attr(page, "AllLayers")
        if layers is None:
            layers = page.Layers
        result = []
        for index in range(1, int(layers.Count) + 1):
            layer = self._collection_item(layers, index)
            shapes = _safe_attr(layer, "Shapes")
            result.append({
                "collection_index": index,
                "index": _safe_int_attr(layer, "Index"),
                "absolute_index": _safe_int_attr(layer, "AbsoluteIndex"),
                "name": _safe_string_attr(layer, "Name"),
                "visible": _safe_bool_attr(layer, "Visible"),
                "editable": _safe_bool_attr(layer, "Editable"),
                "printable": _safe_bool_attr(layer, "Printable"),
                "master": _safe_bool_attr(layer, "Master"),
                "is_special": _safe_bool_attr(layer, "IsSpecialLayer"),
                "object_count": _safe_int_attr(shapes, "Count") if shapes is not None else None,
                "is_active": self._same_com_object(layer, active_layer),
            })
        return {
            "document_name": _safe_string_attr(document, "Name"),
            "page_index": page_index,
            "layers": result,
        }

    def get_object_info(self, object_name: str = "", shape_index: int = 0) -> dict[str, Any]:
        document = self._target_document()
        shape = self._find_shape(document, object_name, shape_index)
        identity = self._shape_identity(shape)
        static_id = identity.get("static_id")
        document_session_id = self._document_session_id(document)
        identity["document_session_id"] = document_session_id
        identity["object_id"] = (
            f"{document_session_id}:shape:{static_id}" if static_id is not None else None
        )
        identity["shape_index"] = self._index_for_shape(document, shape)
        identity["bounds_inches"] = self._shape_bounds_inches(document, shape)
        identity["text"] = self._text_readback(shape)
        identity["fill"] = self._fill_readback(shape)
        identity["outline"] = self._outline_readback(shape)
        return {"document_name": _safe_string_attr(document, "Name"), "object": identity}

    def create_document(self, width_in: float = 8.27, height_in: float = 11.69) -> dict[str, Any]:
        if not (0 < width_in <= 200 and 0 < height_in <= 200):
            raise CorelBridgeError(
                "Page dimensions must be greater than 0 and at most 200 inches.",
                ErrorCode.INVALID_ARGUMENT,
            )
        app = self._require_app()
        try:
            doc = app.CreateDocument()
            doc.Unit = self.CDR_INCH
            doc.ActivePage.SetSize(float(width_in), float(height_in))
            try:
                doc.ReferencePoint = self.CDR_BOTTOM_LEFT
            except Exception:
                pass
            try:
                doc.Activate()
            except Exception:
                pass
            self.target_doc = doc
        except Exception as exc:
            raise CorelBridgeError(
                "CorelDRAW X7 could not create/size/bind the document. Full COM error: " + str(exc)
            ) from exc
        actual_page_size = self._page_dimensions(doc.ActivePage)
        return {
            "created": True,
            "target_document_name": self._safe_target_name(),
            "width_inches_requested": width_in,
            "height_inches_requested": height_in,
            "actual_page_size_inches": {
                "width": actual_page_size.get("width_document_units"),
                "height": actual_page_size.get("height_document_units"),
            },
            "unit_code_actual": _safe_int_attr(doc, "Unit"),
            "reference_point_actual": _safe_int_attr(doc, "ReferencePoint"),
            "target_bound": True
        }

    def _safe_target_name(self) -> str | None:
        return _safe_attr(self.target_doc, "Name") if self.target_doc is not None else None

    @staticmethod
    def _get_layer(doc: Any) -> Any:
        try:
            return doc.ActivePage.ActiveLayer
        except Exception:
            try:
                return doc.ActiveLayer
            except Exception as exc:
                raise CorelBridgeError("Could not locate the active CorelDRAW layer.") from exc

    @staticmethod
    def _shapes(doc: Any) -> Any:
        try:
            return doc.ActivePage.Shapes
        except Exception as exc:
            raise CorelBridgeError("Could not read shapes from the target document's active page.") from exc

    @staticmethod
    def _shape_at(doc: Any, shape_index: int) -> Any:
        if shape_index < 1:
            raise CorelBridgeError(
                "shape_index is 1-based and must be at least 1.",
                ErrorCode.INVALID_ARGUMENT,
            )
        shapes = CorelBridge._shapes(doc)
        try:
            count = int(shapes.Count)
        except Exception as exc:
            raise CorelBridgeError("Could not read the page's shape count.") from exc
        if shape_index > count:
            raise CorelBridgeError(
                f"shape_index {shape_index} is outside the current range 1..{count}.",
                ErrorCode.OBJECT_NOT_FOUND,
            )
        try:
            return shapes.Item(shape_index)
        except Exception:
            try:
                return shapes[shape_index]
            except Exception as exc:
                raise CorelBridgeError(f"Could not access shape index {shape_index}.") from exc

    def _find_shape(self, doc: Any, object_name: str = "", shape_index: int = 0) -> Any:
        has_name = bool(object_name.strip())
        has_index = int(shape_index) > 0
        if has_name == has_index:
            raise CorelBridgeError(
                "Specify exactly one selector: object_name OR shape_index.",
                ErrorCode.AMBIGUOUS_SELECTOR,
            )
        if has_name:
            shapes = self._shapes(doc)
            matches = []
            for i in range(1, int(shapes.Count) + 1):
                shape = self._shape_at(doc, i)
                if str(_safe_attr(shape, "Name") or "") == object_name:
                    matches.append(shape)
            if not matches:
                raise CorelBridgeError(
                    f"No shape named {object_name!r} exists on the active page.",
                    ErrorCode.OBJECT_NOT_FOUND,
                )
            if len(matches) > 1:
                raise CorelBridgeError(
                    f"Shape name {object_name!r} is not unique; rename objects first.",
                    ErrorCode.AMBIGUOUS_SELECTOR,
                )
            return matches[0]
        return self._shape_at(doc, int(shape_index))

    def _unique_name(self, doc: Any, requested: str, prefix: str) -> str:
        clean = requested.strip() if requested and requested.strip() else ""
        existing = set()
        shapes = self._shapes(doc)
        for i in range(1, int(shapes.Count) + 1):
            existing.add(str(_safe_attr(self._shape_at(doc, i), "Name") or ""))
        if not clean:
            n = 1
            while f"{prefix}_{n:03d}" in existing:
                n += 1
            return f"{prefix}_{n:03d}"
        base = clean[:120]
        candidate = base
        n = 2
        while candidate in existing:
            candidate = f"{base}_{n}"
            n += 1
        return candidate

    def _name_shape(self, doc: Any, shape: Any, requested: str, prefix: str) -> str:
        name = self._unique_name(doc, requested, prefix)
        try:
            shape.Name = name
        except Exception as exc:
            raise CorelBridgeError("Object was created but could not be named for later edits: " + str(exc)) from exc
        return name

    def add_text(self, text: str, x_in: float, y_in: float, size_pt: float = 24,
                 font: str = "Arial", bold: bool = False,
                 object_name: str = "") -> dict[str, Any]:
        if not text.strip():
            raise CorelBridgeError("Text cannot be empty.", ErrorCode.INVALID_ARGUMENT)
        if not (1 <= size_pt <= 500):
            raise CorelBridgeError(
                "Font size must be between 1 and 500 points.",
                ErrorCode.INVALID_ARGUMENT,
            )
        doc = self._target_document()
        layer = self._get_layer(doc)
        try:
            with self._in_inches(doc):
                shape = layer.CreateArtisticText(
                    float(x_in), float(y_in), str(text),
                    self.adapter.CDR_LANGUAGE_NONE,
                    self.adapter.CDR_CHARSET_ANSI,
                    str(font), float(size_pt),
                    self.adapter.CDR_TRUE if bold else self.adapter.CDR_FALSE,
                )
                name = self._name_shape(doc, shape, object_name, "AI_Text")
            actual_text = self._text_readback(shape)
            actual_bounds = self._shape_bounds_inches(doc, shape)
            return {"created": True, "type": "text", "object_name": name, "text": text,
                    "font": font, "size_points": size_pt, "bold": bold,
                    "actual_text": actual_text,
                    "actual_bounds_inches": actual_bounds,
                    "note": "Editable artistic-text object created."}
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 rejected CreateArtisticText or naming. Full COM error: " + str(exc)) from exc

    def draw_rectangle(self, x_in: float, y_in: float, width_in: float, height_in: float,
                       object_name: str = "") -> dict[str, Any]:
        if width_in <= 0 or height_in <= 0:
            raise CorelBridgeError(
                "Rectangle width and height must be positive.",
                ErrorCode.INVALID_ARGUMENT,
            )
        doc = self._target_document()
        try:
            with self._in_inches(doc):
                shape = self._get_layer(doc).CreateRectangle2(
                    float(x_in), float(y_in), float(width_in), float(height_in)
                )
                name = self._name_shape(doc, shape, object_name, "AI_Rectangle")
            actual_bounds = self._shape_bounds_inches(doc, shape)
            return {"created": True, "type": "rectangle", "object_name": name,
                    "x_inches": x_in, "y_inches": y_in,
                    "width_inches": width_in, "height_inches": height_in,
                    "actual_bounds_inches": actual_bounds}
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 rejected CreateRectangle2 or naming. Full COM error: " + str(exc)) from exc

    def draw_ellipse(self, x_in: float, y_in: float, width_in: float, height_in: float,
                     object_name: str = "") -> dict[str, Any]:
        if width_in <= 0 or height_in <= 0:
            raise CorelBridgeError(
                "Ellipse width and height must be positive.",
                ErrorCode.INVALID_ARGUMENT,
            )
        doc = self._target_document()
        try:
            with self._in_inches(doc):
                shape = self._get_layer(doc).CreateEllipse2(
                    float(x_in + width_in / 2), float(y_in + height_in / 2),
                    float(width_in / 2), float(height_in / 2)
                )
                name = self._name_shape(doc, shape, object_name, "AI_Ellipse")
            actual_bounds = self._shape_bounds_inches(doc, shape)
            return {"created": True, "type": "ellipse", "object_name": name,
                    "x_inches": x_in, "y_inches": y_in,
                    "width_inches": width_in, "height_inches": height_in,
                    "actual_bounds_inches": actual_bounds}
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 rejected CreateEllipse2 or naming. Full COM error: " + str(exc)) from exc

    def list_objects(self, max_objects: int = 200) -> dict[str, Any]:
        if not (1 <= max_objects <= 1000):
            raise CorelBridgeError(
                "max_objects must be between 1 and 1000.",
                ErrorCode.INVALID_ARGUMENT,
            )
        doc = self._target_document()
        result = []
        with self._in_inches(doc), self._reference_point(doc, self.CDR_BOTTOM_LEFT):
            shapes = self._shapes(doc)
            count = int(shapes.Count)
            for i in range(1, min(count, max_objects) + 1):
                shape = self._shape_at(doc, i)
                summary: dict[str, Any] = {
                    "shape_index": i,
                    "object_name": str(_safe_attr(shape, "Name") or ""),
                    "static_id": _safe_int_attr(shape, "StaticID"),
                    "shape_type_code": _safe_attr(shape, "Type"),
                    "layer_name": _safe_string_attr(_safe_attr(shape, "Layer"), "Name"),
                    "page_index": _safe_int_attr(_safe_attr(shape, "Page"), "Index"),
                }
                for key, attr in (("x_inches", "PositionX"), ("y_inches", "PositionY"),
                                  ("width_inches", "SizeWidth"), ("height_inches", "SizeHeight")):
                    try:
                        summary[key] = round(float(getattr(shape, attr)), 4)
                    except Exception:
                        summary[key] = None
                try:
                    summary["text"] = str(shape.Text.Story.Text)[:500]
                except Exception:
                    summary["text"] = None
                try:
                    summary["outline_width_points"] = float(shape.Outline.Width)
                except Exception:
                    summary["outline_width_points"] = None
                summary["fill"] = self._fill_readback(shape)
                summary["outline"] = self._outline_readback(shape)
                result.append(summary)
        return {"document_name": self._safe_target_name(), "object_count": len(result),
                "total_on_page": count, "truncated": count > len(result),
                "coordinate_reference": "object reference point is bottom-left; measurements are inches",
                "warning": "outline_width_points is a legacy field with unverified COM units; use outline.width_raw and outline.width_units.",
                "objects": result}

    @staticmethod
    def _validate_rgb(red: int, green: int, blue: int) -> None:
        if not all(type(v) is int and 0 <= v <= 255 for v in (red, green, blue)):
            raise CorelBridgeError(
                "RGB values must be integers from 0 to 255.",
                ErrorCode.INVALID_ARGUMENT,
            )

    def set_fill_color(self, red: int, green: int, blue: int,
                       object_name: str = "", shape_index: int = 0) -> dict[str, Any]:
        self._validate_rgb(red, green, blue)
        doc = self._target_document()
        shape = self._find_shape(doc, object_name, shape_index)
        try:
            color = self._require_app().CreateRGBColor(red, green, blue)
            shape.Fill.ApplyUniformFill(color)
            name = str(_safe_attr(shape, "Name") or "")
            return {"updated": True, "object_name": name, "shape_index": self._index_for_shape(doc, shape),
                    "fill_rgb": [red, green, blue],
                    "actual_fill": self._fill_readback(shape)}
        except Exception as exc:
            raise CorelBridgeError("Could not set fill color in CorelDRAW X7. Full COM error: " + str(exc)) from exc

    def set_outline(self, red: int, green: int, blue: int, width_points: float = 1.0,
                    object_name: str = "", shape_index: int = 0) -> dict[str, Any]:
        self._validate_rgb(red, green, blue)
        if not (0 <= width_points <= 72):
            raise CorelBridgeError(
                "Outline width must be between 0 and 72 points; use 0 to remove it.",
                ErrorCode.INVALID_ARGUMENT,
            )
        doc = self._target_document()
        shape = self._find_shape(doc, object_name, shape_index)
        try:
            if width_points == 0:
                shape.Outline.SetNoOutline()
                return {"updated": True, "object_name": str(_safe_attr(shape, "Name") or ""),
                        "outline_removed": True,
                        "actual_outline": self._outline_readback(shape)}
            color = self._require_app().CreateRGBColor(red, green, blue)
            shape.Outline.Color = color
            shape.Outline.Width = float(width_points)
            return {"updated": True, "object_name": str(_safe_attr(shape, "Name") or ""),
                    "outline_rgb": [red, green, blue], "width_points": width_points,
                    "actual_outline": self._outline_readback(shape)}
        except Exception as exc:
            raise CorelBridgeError("Could not set outline in CorelDRAW X7. Full COM error: " + str(exc)) from exc

    def move_object(self, x_inches: float, y_inches: float,
                    object_name: str = "", shape_index: int = 0) -> dict[str, Any]:
        doc = self._target_document()
        shape = self._find_shape(doc, object_name, shape_index)
        try:
            with self._in_inches(doc), self._reference_point(doc, self.CDR_BOTTOM_LEFT):
                shape.SetPosition(float(x_inches), float(y_inches))
                actual_x = float(shape.PositionX)
                actual_y = float(shape.PositionY)
            return {"moved": True, "object_name": str(_safe_attr(shape, "Name") or ""),
                    "x_inches": round(actual_x, 4), "y_inches": round(actual_y, 4),
                    "reference_point": "bottom-left"}
        except Exception as exc:
            raise CorelBridgeError("Could not move object in CorelDRAW X7. Full COM error: " + str(exc)) from exc

    def resize_object(self, width_inches: float = 0, height_inches: float = 0,
                      keep_aspect_ratio: bool = False,
                      object_name: str = "", shape_index: int = 0) -> dict[str, Any]:
        if width_inches <= 0 and height_inches <= 0:
            raise CorelBridgeError(
                "Provide a positive width or height in inches.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (width_inches <= 0 or height_inches <= 0) and not keep_aspect_ratio:
            raise CorelBridgeError(
                "Provide both width and height, or set keep_aspect_ratio=True.",
                ErrorCode.INVALID_ARGUMENT,
            )
        doc = self._target_document()
        shape = self._find_shape(doc, object_name, shape_index)
        try:
            with self._in_inches(doc):
                old_w, old_h = float(shape.SizeWidth), float(shape.SizeHeight)
                if keep_aspect_ratio:
                    if old_w <= 0 or old_h <= 0:
                        raise CorelBridgeError(
                            "Cannot preserve aspect ratio for a zero-size object.",
                            ErrorCode.INVALID_ARGUMENT,
                        )
                    if width_inches > 0 and height_inches <= 0:
                        height_inches = width_inches * old_h / old_w
                    elif height_inches > 0 and width_inches <= 0:
                        width_inches = height_inches * old_w / old_h
                shape.SizeWidth = float(width_inches)
                shape.SizeHeight = float(height_inches)
                new_w, new_h = float(shape.SizeWidth), float(shape.SizeHeight)
            return {"resized": True, "object_name": str(_safe_attr(shape, "Name") or ""),
                    "old_size_inches": [round(old_w, 4), round(old_h, 4)],
                    "new_size_inches": [round(new_w, 4), round(new_h, 4)],
                    "warning": "Resizing text objects by bounding box may stretch glyphs; changing font size is preferable for typography."}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("Could not resize object in CorelDRAW X7. Full COM error: " + str(exc)) from exc

    def set_text_content(self, new_text: str, object_name: str = "", shape_index: int = 0) -> dict[str, Any]:
        if not new_text.strip():
            raise CorelBridgeError("Text cannot be empty.", ErrorCode.INVALID_ARGUMENT)
        doc = self._target_document()
        shape = self._find_shape(doc, object_name, shape_index)
        try:
            story = shape.Text.Story
            old_text = str(story.Text)
            story.Text = str(new_text)
            return {"updated": True, "object_name": str(_safe_attr(shape, "Name") or ""),
                    "old_text": old_text[:200], "new_text": new_text}
        except Exception as exc:
            raise CorelBridgeError("Could not edit text; target may not be a text object. Full COM error: " + str(exc)) from exc

    def rename_object(self, new_name: str, object_name: str = "", shape_index: int = 0) -> dict[str, Any]:
        if not new_name.strip():
            raise CorelBridgeError("new_name cannot be blank.", ErrorCode.INVALID_ARGUMENT)
        doc = self._target_document()
        shape = self._find_shape(doc, object_name, shape_index)
        unique = self._unique_name(doc, new_name, "AI_Object")
        # If we're renaming the selected object to its current name, preserve it.
        if unique != new_name and str(_safe_attr(shape, "Name") or "") == new_name:
            unique = new_name
        try:
            old = str(_safe_attr(shape, "Name") or "")
            shape.Name = unique
            return {"renamed": True, "old_name": old, "object_name": unique,
                    "object": self._shape_identity(shape)}
        except Exception as exc:
            raise CorelBridgeError("Could not rename the object. Full COM error: " + str(exc)) from exc

    def duplicate_object(self, offset_x_inches: float = 0.25, offset_y_inches: float = -0.25,
                         object_name: str = "", shape_index: int = 0,
                         new_name: str = "") -> dict[str, Any]:
        doc = self._target_document()
        shape = self._find_shape(doc, object_name, shape_index)
        try:
            with self._in_inches(doc):
                new_shape = shape.Duplicate(float(offset_x_inches), float(offset_y_inches))
                name = self._name_shape(doc, new_shape, new_name, "AI_Copy")
            return {"duplicated": True, "source_name": str(_safe_attr(shape, "Name") or ""),
                    "object_name": name, "offset_inches": [offset_x_inches, offset_y_inches],
                    "shape_index": self._index_for_shape(doc, new_shape),
                    "object": self._shape_identity(new_shape)}
        except Exception as exc:
            raise CorelBridgeError("Could not duplicate object. Full COM error: " + str(exc)) from exc

    def align_objects(
        self,
        object_names: list[str],
        horizontal: str = "none",
        vertical: str = "none",
        align_to: str = "last_selected",
    ) -> dict[str, Any]:
        """Align two or more shapes relative to the reference object (last_selected or first_selected)."""
        if not isinstance(object_names, list) or len(object_names) < 2:
            raise CorelBridgeError(
                "align_objects requires at least two object names.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if len(set(object_names)) != len(object_names):
            raise CorelBridgeError(
                "Duplicate object names are not allowed in align_objects.",
                ErrorCode.INVALID_ARGUMENT,
            )
        h_norm = str(horizontal).lower().strip()
        v_norm = str(vertical).lower().strip()
        target_norm = str(align_to).lower().strip()

        h_map = {
            "none": self.adapter.CDR_ALIGN_DISTRIBUTE_H_NONE,
            "right": self.adapter.CDR_ALIGN_DISTRIBUTE_H_ALIGN_RIGHT,
            "left": self.adapter.CDR_ALIGN_DISTRIBUTE_H_ALIGN_LEFT,
            "center": self.adapter.CDR_ALIGN_DISTRIBUTE_H_ALIGN_CENTER,
        }
        v_map = {
            "none": self.adapter.CDR_ALIGN_DISTRIBUTE_V_NONE,
            "top": self.adapter.CDR_ALIGN_DISTRIBUTE_V_ALIGN_TOP,
            "bottom": self.adapter.CDR_ALIGN_DISTRIBUTE_V_ALIGN_BOTTOM,
            "center": self.adapter.CDR_ALIGN_DISTRIBUTE_V_ALIGN_CENTER,
        }

        if h_norm not in h_map:
            raise CorelBridgeError(
                f"Invalid horizontal alignment {horizontal!r}; must be one of {sorted(h_map.keys())}.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if v_norm not in v_map:
            raise CorelBridgeError(
                f"Invalid vertical alignment {vertical!r}; must be one of {sorted(v_map.keys())}.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if h_norm == "none" and v_norm == "none":
            raise CorelBridgeError(
                "Specify at least one horizontal or vertical alignment option other than 'none'.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if target_norm not in ("last_selected", "first_selected"):
            raise CorelBridgeError(
                f"Invalid align_to {align_to!r}; must be 'last_selected' or 'first_selected'.",
                ErrorCode.INVALID_ARGUMENT,
            )

        doc = self._target_document()
        app = self._require_app()

        shapes: list[Any] = []
        for name in object_names:
            shape = self._find_shape(doc, object_name=name)
            shapes.append(shape)

        if target_norm == "last_selected":
            ordered_shapes = [shapes[-1]] + shapes[:-1]
        else:
            ordered_shapes = [shapes[0]] + shapes[1:]

        with self._in_inches(doc):
            sr = app.CreateShapeRange()
            for s in ordered_shapes:
                sr.Add(s)

            method_h = h_map[h_norm]
            method_v = v_map[v_norm]

            sr.AlignAndDistribute(
                method_h,
                method_v,
                self.adapter.CDR_ALIGN_SHAPES_TO_LAST_SELECTED,
                0,
                False,
                2,
                0.0,
                0.0,
                None,
            )

        results = []
        for name, shape in zip(object_names, shapes):
            bounds = self._shape_bounds_inches(doc, shape)
            results.append({
                "object_name": name,
                "bounds_inches": bounds,
            })

        return {
            "aligned": True,
            "align_to": target_norm,
            "horizontal": h_norm,
            "vertical": v_norm,
            "object_count": len(object_names),
            "objects": results,
        }

    def align_to_page(
        self,
        object_names: list[str],
        horizontal: str = "none",
        vertical: str = "none",
        align_as_group: bool = False,
    ) -> dict[str, Any]:
        """Align one or more shapes to the page edges or center."""
        if not isinstance(object_names, list) or len(object_names) < 1:
            raise CorelBridgeError(
                "align_to_page requires at least one object name.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if len(set(object_names)) != len(object_names):
            raise CorelBridgeError(
                "Duplicate object names are not allowed in align_to_page.",
                ErrorCode.INVALID_ARGUMENT,
            )
        h_norm = str(horizontal).lower().strip()
        v_norm = str(vertical).lower().strip()

        valid_h = ("none", "left", "center", "right")
        valid_v = ("none", "top", "center", "bottom")

        if h_norm not in valid_h:
            raise CorelBridgeError(
                f"Invalid horizontal alignment {horizontal!r}; must be one of {list(valid_h)}.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if v_norm not in valid_v:
            raise CorelBridgeError(
                f"Invalid vertical alignment {vertical!r}; must be one of {list(valid_v)}.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if h_norm == "none" and v_norm == "none":
            raise CorelBridgeError(
                "Specify at least one horizontal or vertical alignment option other than 'none'.",
                ErrorCode.INVALID_ARGUMENT,
            )

        doc = self._target_document()
        app = self._require_app()

        shapes: list[Any] = []
        for name in object_names:
            shape = self._find_shape(doc, object_name=name)
            shapes.append(shape)

        with self._in_inches(doc):
            sr = app.CreateShapeRange()
            for s in shapes:
                sr.Add(s)

            if align_as_group and len(shapes) > 1:
                if h_norm == "center" and v_norm == "center":
                    sr.AlignRangeToPageCenter(self.adapter.CDR_ALIGN_H_CENTER | self.adapter.CDR_ALIGN_V_CENTER)
                else:
                    if h_norm == "center":
                        sr.AlignRangeToPageCenter(self.adapter.CDR_ALIGN_H_CENTER)
                    elif h_norm == "left":
                        sr.AlignRangeToPage(self.adapter.CDR_ALIGN_LEFT)
                    elif h_norm == "right":
                        sr.AlignRangeToPage(self.adapter.CDR_ALIGN_RIGHT)

                    if v_norm == "center":
                        sr.AlignRangeToPageCenter(self.adapter.CDR_ALIGN_V_CENTER)
                    elif v_norm == "top":
                        sr.AlignRangeToPage(self.adapter.CDR_ALIGN_TOP)
                    elif v_norm == "bottom":
                        sr.AlignRangeToPage(self.adapter.CDR_ALIGN_BOTTOM)
            else:
                h_map = {
                    "none": self.adapter.CDR_ALIGN_DISTRIBUTE_H_NONE,
                    "right": self.adapter.CDR_ALIGN_DISTRIBUTE_H_ALIGN_RIGHT,
                    "left": self.adapter.CDR_ALIGN_DISTRIBUTE_H_ALIGN_LEFT,
                    "center": self.adapter.CDR_ALIGN_DISTRIBUTE_H_ALIGN_CENTER,
                }
                v_map = {
                    "none": self.adapter.CDR_ALIGN_DISTRIBUTE_V_NONE,
                    "top": self.adapter.CDR_ALIGN_DISTRIBUTE_V_ALIGN_TOP,
                    "bottom": self.adapter.CDR_ALIGN_DISTRIBUTE_V_ALIGN_BOTTOM,
                    "center": self.adapter.CDR_ALIGN_DISTRIBUTE_V_ALIGN_CENTER,
                }

                if h_norm == "center" and v_norm == "center":
                    sr.AlignAndDistribute(
                        h_map["center"], v_map["center"],
                        self.adapter.CDR_ALIGN_SHAPES_TO_CENTER_OF_PAGE,
                        0, False, 2, 0.0, 0.0, None,
                    )
                else:
                    if h_norm == "center":
                        sr.AlignAndDistribute(
                            h_map["center"], self.adapter.CDR_ALIGN_DISTRIBUTE_V_NONE,
                            self.adapter.CDR_ALIGN_SHAPES_TO_CENTER_OF_PAGE,
                            0, False, 2, 0.0, 0.0, None,
                        )
                    elif h_norm != "none":
                        sr.AlignAndDistribute(
                            h_map[h_norm], self.adapter.CDR_ALIGN_DISTRIBUTE_V_NONE,
                            self.adapter.CDR_ALIGN_SHAPES_TO_EDGE_OF_PAGE,
                            0, False, 2, 0.0, 0.0, None,
                        )
                    if v_norm == "center":
                        sr.AlignAndDistribute(
                            self.adapter.CDR_ALIGN_DISTRIBUTE_H_NONE, v_map["center"],
                            self.adapter.CDR_ALIGN_SHAPES_TO_CENTER_OF_PAGE,
                            0, False, 2, 0.0, 0.0, None,
                        )
                    elif v_norm != "none":
                        sr.AlignAndDistribute(
                            self.adapter.CDR_ALIGN_DISTRIBUTE_H_NONE, v_map[v_norm],
                            self.adapter.CDR_ALIGN_SHAPES_TO_EDGE_OF_PAGE,
                            0, False, 2, 0.0, 0.0, None,
                        )

        results = []
        for name, shape in zip(object_names, shapes):
            bounds = self._shape_bounds_inches(doc, shape)
            results.append({
                "object_name": name,
                "bounds_inches": bounds,
            })

        return {
            "aligned": True,
            "align_to": "page",
            "horizontal": h_norm,
            "vertical": v_norm,
            "align_as_group": align_as_group,
            "object_count": len(object_names),
            "objects": results,
        }

    def group_shapes(self, object_names: list[str], group_name: str = "") -> dict[str, Any]:
        """Group multiple shapes on the active page into a single named group shape."""
        if not isinstance(object_names, list) or len(object_names) < 2:
            raise CorelBridgeError(
                "group_shapes requires at least two object names.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if len(set(object_names)) != len(object_names):
            raise CorelBridgeError(
                "Duplicate object names are not allowed in group_shapes.",
                ErrorCode.INVALID_ARGUMENT,
            )

        doc = self._target_document()
        app = self._require_app()

        shapes: list[Any] = []
        for name in object_names:
            shape = self._find_shape(doc, object_name=name)
            shapes.append(shape)

        try:
            with self._in_inches(doc):
                sr = app.CreateShapeRange()
                for s in shapes:
                    sr.Add(s)
                group_shape = sr.Group()
                name = self._name_shape(doc, group_shape, group_name, "AI_Group")

            child_names = []
            try:
                child_count = int(group_shape.Shapes.Count)
                for i in range(1, child_count + 1):
                    c = group_shape.Shapes.Item(i)
                    child_names.append(str(_safe_attr(c, "Name") or ""))
            except Exception:
                child_names = list(object_names)

            actual_bounds = self._shape_bounds_inches(doc, group_shape)
            return {
                "grouped": True,
                "group_name": name,
                "shape_count": len(child_names),
                "child_names": child_names,
                "bounds_inches": actual_bounds,
            }
        except Exception as exc:
            raise CorelBridgeError(f"Could not group shapes in CorelDRAW X7: {exc}") from exc

    def ungroup_shapes(
        self,
        object_name: str = "",
        shape_index: int = 0,
        ungroup_all: bool = False,
    ) -> dict[str, Any]:
        """Ungroup a group shape into individual shapes."""
        doc = self._target_document()
        shape = self._find_shape(doc, object_name, shape_index)

        shape_type = _safe_attr(shape, "Type")
        if shape_type != self.adapter.CDR_GROUP_SHAPE:
            raise CorelBridgeError(
                f"Target shape {object_name or shape_index!r} is of type {shape_type}, not a group shape.",
                ErrorCode.INVALID_ARGUMENT,
            )

        resolved_name = str(_safe_attr(shape, "Name") or "")
        child_count = 0
        try:
            child_count = int(shape.Shapes.Count)
        except Exception:
            child_count = 0

        try:
            with self._in_inches(doc):
                if ungroup_all:
                    shape.UngroupAll()
                else:
                    shape.Ungroup()

            return {
                "ungrouped": True,
                "object_name": resolved_name,
                "ungroup_all": ungroup_all,
                "shapes_released": child_count,
            }
        except Exception as exc:
            raise CorelBridgeError(f"Could not ungroup shape {resolved_name!r}: {exc}") from exc

    def _validate_artwork_path(self, file_path: str) -> Path:
        path = Path(os.path.abspath(os.path.expanduser(file_path)))
        if not path.is_file():
            raise CorelBridgeError(
                f"Artwork file does not exist: {path}",
                ErrorCode.UNSAFE_PATH,
            )
        if path.suffix.lower() not in self.ALLOWED_IMPORT_EXTENSIONS:
            raise CorelBridgeError(
                f"Unsupported artwork extension {path.suffix!r}.",
                ErrorCode.INVALID_ARGUMENT,
            )
        if path.stat().st_size > self.MAX_IMPORT_BYTES:
            raise CorelBridgeError(
                "Artwork is larger than the 250 MB prototype limit.",
                ErrorCode.INVALID_ARGUMENT,
            )
        return path

    def import_artwork(self, file_path: str, object_name: str = "AI_Artwork") -> dict[str, Any]:
        path = self._validate_artwork_path(file_path)
        doc = self._target_document()
        layer = self._get_layer(doc)
        before = int(self._shapes(doc).Count)
        try:
            try:
                doc.ClearSelection()
            except Exception:
                pass
            app = self._require_app()
            import_options = None
            try:
                import_options = app.CreateStructImportOptions()
            except Exception:
                import_options = None
            with self._in_inches(doc):
                if import_options is not None:
                    try:
                        layer.Import(str(path), 0, import_options)
                    except TypeError:
                        layer.Import(str(path))
                else:
                    layer.Import(str(path))
            imported = []
            # CorelDRAW normally selects imported shapes. Prefer that collection.
            try:
                selected = doc.SelectionRange
                for i in range(1, int(selected.Count) + 1):
                    imported.append(selected.Item(i))
            except Exception:
                imported = []
            # Fallback: report shapes appended to the page if import didn't expose a selection.
            if not imported:
                shapes = self._shapes(doc)
                count = int(shapes.Count)
                for i in range(before + 1, count + 1):
                    imported.append(self._shape_at(doc, i))
            if not imported:
                raise CorelBridgeError("Import returned but no new/selected objects could be identified.")
            assigned = []
            identities = []
            for i, shape in enumerate(imported, start=1):
                requested = object_name if len(imported) == 1 else f"{object_name}_{i:02d}"
                assigned.append(self._name_shape(doc, shape, requested, "AI_Artwork"))
                identities.append(self._shape_identity(shape))
            return {"imported": True, "file_path": str(path), "object_count": len(imported),
                    "object_names": assigned, "objects": identities,
                    "note": "Imported objects may need move/resize operations. Inspect list_objects before printing."}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 artwork import failed. Full COM error: " + str(exc)) from exc

    def _index_for_shape(self, doc: Any, target: Any) -> int | None:
        shapes = self._shapes(doc)
        for i in range(1, int(shapes.Count) + 1):
            shape = self._shape_at(doc, i)
            if str(_safe_attr(shape, "Name") or "") == str(_safe_attr(target, "Name") or ""):
                # Names are unique for all shapes created by this bridge. If imported art has
                # duplicate names we don't depend on this lookup for its primary identity.
                return i
        return None

    def _design_plan_shape_snapshot(self, doc: Any) -> dict[str, Any]:
        shapes = self._shapes(doc)
        tokens: list[str] = []
        names: list[str] = []
        for index in range(1, int(shapes.Count) + 1):
            shape = self._shape_at(doc, index)
            name = str(_safe_attr(shape, "Name") or "")
            names.append(name)
            static_id = _safe_int_attr(shape, "StaticID")
            shape_type = _safe_int_attr(shape, "Type")
            if static_id is not None:
                tokens.append(f"static_id:{static_id}")
            else:
                tokens.append(f"name:{name}|type:{shape_type}")
        tokens.sort()
        return {
            "count": int(shapes.Count),
            "tokens": tokens,
            "names": names,
        }

    def _verify_design_plan_rollback(
        self,
        doc: Any,
        baseline: dict[str, Any],
        created_names: list[str],
    ) -> dict[str, Any]:
        try:
            current = self._design_plan_shape_snapshot(doc)
        except Exception as exc:
            return {
                "verified": False,
                "verification_error_type": type(exc).__name__,
            }

        created_name_set = set(created_names)
        remaining = sorted(name for name in current["names"] if name in created_name_set)
        identity_restored = current["tokens"] == baseline["tokens"]
        count_restored = current["count"] == baseline["count"]
        return {
            "verified": count_restored and identity_restored and not remaining,
            "before_count": baseline["count"],
            "after_count": current["count"],
            "identity_restored": identity_restored,
            "created_objects_remaining": remaining,
        }

    def create_chest_number_batch(
        self,
        start: int,
        end: int,
        item_width_inches: float,
        item_height_inches: float,
        font: str = "Arial",
        font_size_points: float = 72.0,
        zero_pad_width: int = 0,
        sheet_width_inches: float | None = None,
        sheet_height_inches: float | None = None,
        margin_inches: float = 0.0,
        gutter_inches: float = 0.0,
        bold: bool = True,
        draw_border: bool = True,
        header_text: str = "",
        footer_text: str = "",
        allow_rotate: bool = False,
    ) -> dict[str, Any]:
        """Generate a validated sequence of editable chest-number designs on the bound target document."""
        doc = self._target_document()

        # Determine sheet dimensions: explicitly provided or read from bound target document active page
        if sheet_width_inches is None or sheet_height_inches is None:
            with self._in_inches(doc):
                dims = self._page_dimensions(doc.ActivePage)
            sheet_w = dims.get("width_document_units")
            sheet_h = dims.get("height_document_units")
            if sheet_w is None or sheet_h is None or sheet_w <= 0 or sheet_h <= 0:
                raise CorelBridgeError("Could not determine page dimensions for batch layout.", ErrorCode.COREL_COM_ERROR)
            sheet_width_inches = sheet_w if sheet_width_inches is None else sheet_width_inches
            sheet_height_inches = sheet_h if sheet_height_inches is None else sheet_height_inches

        # Build and validate sequence and layout plan using workflows helper
        plan = build_chest_number_sequence(
            start=start,
            end=end,
            zero_pad_width=zero_pad_width,
            item_width_inches=item_width_inches,
            item_height_inches=item_height_inches,
            sheet_width_inches=sheet_width_inches,
            sheet_height_inches=sheet_height_inches,
            margin_inches=margin_inches,
            gutter_inches=gutter_inches,
            allow_rotate=allow_rotate,
        )

        layout = plan["layout"]
        if layout is None or not plan["fits_sheet"]:
            capacity = layout["capacity"] if layout else 0
            raise CorelBridgeError(
                f"Requested {plan['count']} chest numbers, but sheet capacity is {capacity}. "
                "Adjust item size, margins, or sheet dimensions to fit.",
                ErrorCode.INVALID_ARGUMENT,
                {"requested_count": plan["count"], "capacity": capacity, "layout": layout},
            )

        if not (1 <= font_size_points <= 500):
            raise CorelBridgeError("font_size_points must be between 1 and 500.", ErrorCode.INVALID_ARGUMENT)
        if not font or not font.strip():
            raise CorelBridgeError("font cannot be empty.", ErrorCode.INVALID_ARGUMENT)

        layer = self._get_layer(doc)
        created_names: list[str] = []
        created_items: list[dict[str, Any]] = []

        with self._in_inches(doc), self._reference_point(doc, self.CDR_BOTTOM_LEFT):
            for item in plan["items"]:
                placement = item["placement"]
                px = float(placement["x_inches"])
                py = float(placement["y_inches"])
                pw = float(placement["width_inches"])
                ph = float(placement["height_inches"])
                num_label = str(item["label"])
                prefix = str(item["object_name"])

                item_record: dict[str, Any] = {
                    "value": item["value"],
                    "label": num_label,
                    "placement": placement,
                    "shapes": {},
                }

                # 1. Draw border rectangle if requested
                if draw_border:
                    box = layer.CreateRectangle2(px, py, pw, ph)
                    box_name = self._name_shape(doc, box, f"{prefix}_box", "AI_Box")
                    created_names.append(box_name)
                    item_record["shapes"]["box"] = box_name

                # 2. Header text if provided
                if header_text.strip():
                    h_size = max(6.0, min(font_size_points * 0.28, 24.0))
                    h_shape = layer.CreateArtisticText(
                        px, py, str(header_text.strip()),
                        self.adapter.CDR_LANGUAGE_NONE,
                        self.adapter.CDR_CHARSET_ANSI,
                        str(font), float(h_size),
                        self.adapter.CDR_TRUE if bold else self.adapter.CDR_FALSE,
                    )
                    h_name = self._name_shape(doc, h_shape, f"{prefix}_header", "AI_Text")
                    hw = float(h_shape.SizeWidth)
                    hh = float(h_shape.SizeHeight)
                    hx = round(px + max(0.0, (pw - hw) / 2.0), 4)
                    hy = round(py + max(0.0, ph - hh - max(0.1, ph * 0.08)), 4)
                    h_shape.SetPosition(hx, hy)
                    created_names.append(h_name)
                    item_record["shapes"]["header"] = h_name

                # 3. Main number text
                n_shape = layer.CreateArtisticText(
                    px, py, num_label,
                    self.adapter.CDR_LANGUAGE_NONE,
                    self.adapter.CDR_CHARSET_ANSI,
                    str(font), float(font_size_points),
                    self.adapter.CDR_TRUE if bold else self.adapter.CDR_FALSE,
                )
                n_name = self._name_shape(doc, n_shape, f"{prefix}_number", "AI_Text")
                nw = float(n_shape.SizeWidth)
                nh = float(n_shape.SizeHeight)
                nx = round(px + max(0.0, (pw - nw) / 2.0), 4)
                ny = round(py + max(0.0, (ph - nh) / 2.0), 4)
                n_shape.SetPosition(nx, ny)
                created_names.append(n_name)
                item_record["shapes"]["number"] = n_name

                # 4. Footer text if provided
                if footer_text.strip():
                    f_size = max(6.0, min(font_size_points * 0.22, 18.0))
                    f_shape = layer.CreateArtisticText(
                        px, py, str(footer_text.strip()),
                        self.adapter.CDR_LANGUAGE_NONE,
                        self.adapter.CDR_CHARSET_ANSI,
                        str(font), float(f_size),
                        self.adapter.CDR_FALSE,
                    )
                    f_name = self._name_shape(doc, f_shape, f"{prefix}_footer", "AI_Text")
                    fw = float(f_shape.SizeWidth)
                    fh = float(f_shape.SizeHeight)
                    fx = round(px + max(0.0, (pw - fw) / 2.0), 4)
                    fy = round(py + max(0.05, ph * 0.08), 4)
                    f_shape.SetPosition(fx, fy)
                    created_names.append(f_name)
                    item_record["shapes"]["footer"] = f_name

                created_items.append(item_record)

        return {
            "created": True,
            "created_count": len(created_items),
            "batch_type": "chest_numbers",
            "document_name": self._safe_target_name(),
            "start": start,
            "end": end,
            "count": plan["count"],
            "zero_pad_width": zero_pad_width,
            "sequence_validation": plan["sequence_validation"],
            "object_names": created_names,
            "item_dimensions_inches": {"width": item_width_inches, "height": item_height_inches},
            "sheet_dimensions_inches": {"width": sheet_width_inches, "height": sheet_height_inches},
            "layout": {
                "columns": layout["columns"],
                "rows": layout["rows"],
                "capacity": layout["capacity"],
                "rotated": layout["rotated"],
                "items_placed": len(created_items),
            },
            "items": created_items,
        }

    def execute_design_plan(
        self,
        plan: dict[str, Any],
        create_new_document: bool = False,
        rollback_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Execute a validated multi-element design plan transactionally with atomic rollback."""
        validation = validate_design_plan(plan)
        if not validation["ready_for_execution"]:
            raise CorelBridgeError(
                "Design plan failed execution preflight.",
                ErrorCode.INVALID_ARGUMENT,
                {"blocking_issues": validation["blocking_issues"]},
            )

        # Validate every local asset before document creation or any CorelDRAW mutation.
        # import_artwork validates again immediately before import to reduce TOCTOU risk.
        for elem in plan["elements"]:
            if elem["type"] == "artwork":
                self._validate_artwork_path(elem["file_path"])

        if create_new_document:
            cw = float(plan["canvas"]["width_inches"])
            ch = float(plan["canvas"]["height_inches"])
            self.create_document(width_in=cw, height_in=ch)

        doc = self._target_document()
        layer = self._get_layer(doc)

        rollback_baseline: dict[str, Any] | None = None
        if rollback_on_failure:
            try:
                rollback_baseline = self._design_plan_shape_snapshot(doc)
            except Exception as exc:
                raise CorelBridgeError(
                    "Could not establish a pre-execution state for rollback verification; no plan elements were created.",
                    ErrorCode.COREL_COM_ERROR,
                    {"exception_type": type(exc).__name__},
                ) from exc

        has_command_group = False
        try:
            doc.BeginCommandGroup(f"AI Plan: {plan.get('name', 'Design Plan')}")
            has_command_group = True
        except Exception as exc:
            has_command_group = False
            if rollback_on_failure:
                raise CorelBridgeError(
                    "Could not start a CorelDRAW command group; no plan elements were created.",
                    ErrorCode.COREL_COM_ERROR,
                    {"exception_type": type(exc).__name__},
                ) from exc

        executed_elements: list[dict[str, Any]] = []
        created_shape_names: list[str] = []

        with self._in_inches(doc), self._reference_point(doc, self.CDR_BOTTOM_LEFT):
            try:
                for elem in plan["elements"]:
                    elem_id = str(elem["id"])
                    elem_type = str(elem["type"])
                    created_shape = None
                    created_names_before = len(created_shape_names)

                    if elem_type == "rectangle":
                        x = float(elem["x_inches"])
                        y = float(elem["y_inches"])
                        w = float(elem["width_inches"])
                        h = float(elem["height_inches"])
                        created_shape = layer.CreateRectangle2(x, y, w, h)
                        name = self._name_shape(doc, created_shape, elem_id, "AI_Rect")
                        created_shape_names.append(name)

                    elif elem_type == "ellipse":
                        x = float(elem["x_inches"])
                        y = float(elem["y_inches"])
                        w = float(elem["width_inches"])
                        h = float(elem["height_inches"])
                        created_shape = layer.CreateEllipse2(
                            float(x + w / 2.0), float(y + h / 2.0),
                            float(w / 2.0), float(h / 2.0)
                        )
                        name = self._name_shape(doc, created_shape, elem_id, "AI_Ellipse")
                        created_shape_names.append(name)

                    elif elem_type == "text":
                        x = float(elem["x_inches"])
                        y = float(elem["y_inches"])
                        text_str = str(elem["text"])
                        font = str(elem.get("font", "Arial"))
                        font_size = float(elem.get("font_size_points", 24.0))
                        bold = bool(elem.get("bold", False))
                        created_shape = layer.CreateArtisticText(
                            x, y, text_str,
                            self.adapter.CDR_LANGUAGE_NONE,
                            self.adapter.CDR_CHARSET_ANSI,
                            font, font_size,
                            self.adapter.CDR_TRUE if bold else self.adapter.CDR_FALSE,
                        )
                        name = self._name_shape(doc, created_shape, elem_id, "AI_Text")
                        created_shape_names.append(name)

                    elif elem_type == "artwork":
                        art_result = self.import_artwork(elem["file_path"], elem_id)
                        created_shape_names.extend(art_result.get("object_names", []))
                        if "x_inches" in elem and "y_inches" in elem:
                            self.move_object(elem["x_inches"], elem["y_inches"], object_name=elem_id)
                        if "width_inches" in elem or "height_inches" in elem:
                            self.resize_object(
                                elem.get("width_inches", 0.0), elem.get("height_inches", 0.0),
                                keep_aspect_ratio=True, object_name=elem_id
                            )

                    # Apply fill styling
                    if created_shape is not None and elem.get("fill"):
                        fill = elem["fill"]
                        color = self._require_app().CreateRGBColor(
                            int(fill["red"]), int(fill["green"]), int(fill["blue"])
                        )
                        created_shape.Fill.ApplyUniformFill(color)

                    # Apply outline styling
                    if created_shape is not None and elem.get("outline"):
                        outline = elem["outline"]
                        ow = float(outline.get("width_points", 1.0))
                        if ow <= 0:
                            created_shape.Outline.SetNoOutline()
                        else:
                            color = self._require_app().CreateRGBColor(
                                int(outline.get("red", 0)), int(outline.get("green", 0)), int(outline.get("blue", 0))
                            )
                            created_shape.Outline.Color = color
                            created_shape.Outline.Width = ow

                    element_object_names = created_shape_names[created_names_before:]
                    executed_elements.append({
                        "id": elem_id,
                        "type": elem_type,
                        "object_name": element_object_names[0] if len(element_object_names) == 1 else None,
                        "object_names": element_object_names,
                        "status": "created",
                    })

                if has_command_group:
                    doc.EndCommandGroup()
                    has_command_group = False

            except Exception as step_exc:
                command_group_closed = False
                if has_command_group:
                    try:
                        doc.EndCommandGroup()
                        command_group_closed = True
                    except Exception:
                        pass

                rollback_result: dict[str, Any] = {
                    "requested": rollback_on_failure,
                    "attempted": False,
                    "undo_succeeded": False,
                    "verified": False,
                    "command_group_closed": command_group_closed,
                }
                if has_command_group and rollback_on_failure:
                    rollback_result["attempted"] = True
                    try:
                        doc.Undo()
                        rollback_result["undo_succeeded"] = True
                    except Exception as rollback_exc:
                        rollback_result["undo_error_type"] = type(rollback_exc).__name__

                    if rollback_result["undo_succeeded"] and rollback_baseline is not None:
                        rollback_result.update(
                            self._verify_design_plan_rollback(
                                doc,
                                rollback_baseline,
                                created_shape_names,
                            )
                        )

                if rollback_result["verified"]:
                    rollback_message = "Changes were rolled back and the prior page state was verified."
                elif rollback_on_failure:
                    rollback_message = "Rollback could not be verified; review the target document before further mutation."
                else:
                    rollback_message = "Rollback was not requested; partial changes may remain."
                error_details: dict[str, Any] = {
                    "failed_element": elem.get("id"),
                    "executed_count": len(executed_elements),
                    "rollback": rollback_result,
                    "exception_type": type(step_exc).__name__,
                }
                if isinstance(step_exc, CorelBridgeError):
                    error_details["cause_code"] = step_exc.code.value
                raise CorelBridgeError(
                    f"Plan execution failed on element {elem.get('id', 'unknown')!r}. "
                    + rollback_message,
                    step_exc.code if isinstance(step_exc, CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                    error_details,
                ) from step_exc

        # Post-execution verification & discrepancy reporting
        objects_summary = self.list_objects(max_objects=1000)
        page_objects = {obj["object_name"]: obj for obj in objects_summary.get("objects", [])}
        discrepancies: list[str] = []
        for executed in executed_elements:
            actual_objects = [
                page_objects[name]
                for name in executed["object_names"]
                if name in page_objects
            ]
            executed["actual_objects"] = actual_objects
            missing_names = [
                name for name in executed["object_names"] if name not in page_objects
            ]
            if missing_names:
                discrepancies.append(
                    f"Element {executed['id']!r} objects were not found after execution: "
                    + ", ".join(repr(name) for name in missing_names)
                    + "."
                )

        return {
            "executed": True,
            "name": plan["name"],
            "document_name": self._safe_target_name(),
            "elements_planned": len(plan["elements"]),
            "elements_executed": len(executed_elements),
            "object_names": created_shape_names,
            "elements": executed_elements,
            "discrepancies": discrepancies,
            "post_execution_verification": len(discrepancies) == 0,
            "total_page_objects": objects_summary.get("total_on_page", len(created_shape_names)),
        }

    def save_document(self, path: str) -> dict[str, Any]:
        doc = self._target_document()
        path = os.path.abspath(os.path.expanduser(path))
        if not path.lower().endswith(".cdr"):
            raise CorelBridgeError("Save path must end in .cdr.", ErrorCode.INVALID_ARGUMENT)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            raise CorelBridgeError(
                f"Refusing to overwrite existing file: {path}",
                ErrorCode.OUTPUT_EXISTS,
            )
        try:
            app = self._require_app()
            options = app.CreateStructSaveAsOptions()
            options.Filter = self.adapter.CDR_FILTER_CDR
            options.Version = self.adapter.CDR_CURRENT_VERSION
            options.Range = self.adapter.CDR_ALL_PAGES
            options.EmbedICCProfile = False
            options.EmbedVBAProject = False
            options.IncludeCMXData = False
            options.Overwrite = False
            doc.SaveAs(path, options)
            if not os.path.isfile(path):
                raise CorelBridgeError("CorelDRAW returned from SaveAs, but the file was not created: " + path)
            return {"saved": True, "path": path, "bytes": os.path.getsize(path),
                    "document_name": self._safe_target_name()}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 could not save the target document. Full COM error: " + str(exc)) from exc

    def export_pdf(self, path: str) -> dict[str, Any]:
        doc = self._target_document()
        path = os.path.abspath(os.path.expanduser(path))
        if not path.lower().endswith(".pdf"):
            raise CorelBridgeError("Export path must end in .pdf.", ErrorCode.INVALID_ARGUMENT)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            raise CorelBridgeError(
                f"Refusing to overwrite existing file: {path}",
                ErrorCode.OUTPUT_EXISTS,
            )
        try:
            doc.PublishToPDF(path)
            if not os.path.isfile(path):
                raise CorelBridgeError(
                    "CorelDRAW returned from PublishToPDF, but the file was not created: " + path,
                    ErrorCode.COREL_COM_ERROR,
                )
            size = os.path.getsize(path)
            if size <= 0:
                raise CorelBridgeError(
                    "CorelDRAW created an empty PDF file: " + path,
                    ErrorCode.COREL_COM_ERROR,
                )
            return {"exported": True, "path": path, "bytes": size,
                    "warning": "PDF settings inherit CorelDRAW preferences; verify page size, fonts, color profile, bleed and output settings."}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 PDF export failed. Full COM error: " + str(exc)) from exc


def _safe_attr(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None


def _safe_int_attr(obj: Any, attr: str) -> int | None:
    value = _safe_attr(obj, attr)
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_bool_attr(obj: Any, attr: str) -> bool | None:
    value = _safe_attr(obj, attr)
    if value is None:
        return None
    try:
        return bool(value)
    except Exception:
        return None


def _safe_float_attr(obj: Any, attr: str) -> float | None:
    value = _safe_attr(obj, attr)
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_string_attr(obj: Any, attr: str) -> str | None:
    value = _safe_attr(obj, attr)
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def _distribution_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None
