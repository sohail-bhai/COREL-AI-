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

    def import_artwork(self, file_path: str, object_name: str = "AI_Artwork") -> dict[str, Any]:
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
