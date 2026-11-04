"""CorelDRAW X7-oriented COM bridge for the CorelDRAW AI Operator prototype.

Operations target a document created by this bridge. Editing an already-open document requires
an explicit `use_active_document` call so a client design isn't modified by accident.
"""
from __future__ import annotations

import math
import os
import platform
import re
import secrets
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
from .object_search import validate_search_inputs
from .object_inspection import (
    DEFAULT_TEXT_CHARS, MAX_NAME_CHARS, MAX_NAME_SCAN,
    validate_inspection_selector, validate_text_limit,
)
from .typography import (
    ALIGNMENTS, UNDERLINES, STYLE_ATTRIBUTES, MAX_FONT_SCAN, MAX_FONT_CHARS,
    validate_font, validate_style, validate_paragraph,
    read_property, style_readback, layout_readback,
)
from .layout import (
    FLIP_AXES, ORDER_METHODS, MAX_LAYOUT_OBJECTS, POSITION_TOLERANCE,
    choice, validate_rotation, plan_distribution, matrix_determinant, circular_difference,
)
from .native_tracking import tracked_mutation
from .template_bridge import TemplateBridgeMixin
from .pdf_bridge import PdfBridgeMixin
from .vector_bridge import VectorBridgeMixin
from .appearance_bridge import AppearanceBridgeMixin
from .transparency_bridge import TransparencyBridgeMixin
from .powerclip_bridge import PowerClipBridgeMixin
from .gradient_bridge import GradientBridgeMixin
from .contour_offset_bridge import ContourOffsetBridgeMixin
from .organization_bridge import OrganizationBridgeMixin
from .bitmap_bridge import BitmapBridgeMixin
from .object_references import (
    MAX_REFERENCE_DEPTH, MAX_REFERENCE_SCAN, authenticate_reference,
    identity_token, reference_signature, validate_reference,
    validate_reference_selector,
)
from .print_jobs import materialize_placement_artwork, plan_print_job
from .contour_nesting import (
    classify_imposition_job,
    contours_have_conflicts,
    imposition_plan_fingerprint,
    plan_contour_nesting,
    plan_imposition_layout,
)


class CorelBridge(TemplateBridgeMixin,PdfBridgeMixin,VectorBridgeMixin,AppearanceBridgeMixin,TransparencyBridgeMixin,PowerClipBridgeMixin,GradientBridgeMixin,ContourOffsetBridgeMixin,OrganizationBridgeMixin,BitmapBridgeMixin):
    CDR_INCH = CorelX7Adapter.CDR_INCH
    CDR_BOTTOM_LEFT = CorelX7Adapter.CDR_BOTTOM_LEFT
    MAX_IMPORT_BYTES = 250 * 1024 * 1024
    MAX_OPEN_DOCUMENTS = 1000
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
        self._target_application_key: str | None = None
        self._target_document_key: str | None = None
        self._bridge_session_id = secrets.token_hex(16)
        self._reference_secret = secrets.token_bytes(32)
        self._mutation_depth = 0
        self._operation_mutation_started: bool | None = None

    def _note_mutation(self) -> None:
        if self._mutation_depth:
            self._operation_mutation_started = True

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
                if self.app is not None and not self._same_com_object(self.app, candidate):
                    self._invalidate_target_document()
                    self._document_sessions.clear()
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
        """Verify the bound document is still open in the same application before use."""
        if self.target_doc is None:
            raise CorelBridgeError(
                "No target document is bound. Call create_document for a new file, or explicitly call "
                "use_active_document(confirm_existing_document=True) to allow editing the current file.",
                ErrorCode.NO_TARGET_DOCUMENT,
            )
        if self.app is None:
            self._invalidate_target_document()
            raise CorelBridgeError("The bound application is no longer available.", ErrorCode.NO_TARGET_DOCUMENT)
        application_key = self._com_identity(self.app, strict=True)
        if self._target_application_key not in (None, application_key):
            self._invalidate_target_document()
            raise CorelBridgeError(
                "The application changed; explicitly bind a new target document.", ErrorCode.NO_TARGET_DOCUMENT,
            )
        document_key = self._com_identity(self.target_doc, strict=True)
        if self._target_document_key not in (None, document_key):
            self._invalidate_target_document()
            raise CorelBridgeError(
                "The document binding changed without an explicit bind operation.", ErrorCode.NO_TARGET_DOCUMENT,
            )
        documents = self._open_document_proxies(self.app)
        if not any(self._same_com_object(self.target_doc, document, strict=True) for document in documents):
            self._invalidate_target_document()
            raise CorelBridgeError(
                "The bound document was closed or replaced; explicitly bind a new target document.",
                ErrorCode.NO_TARGET_DOCUMENT,
            )
        self._target_application_key = application_key
        self._target_document_key = document_key
        return self.target_doc

    def reconcile_document_state(self) -> dict[str, Any]:
        """Read finite current target state without reconnecting or choosing another document."""
        result = {
            "connected": self.app is not None, "target_bound": False,
            "document_session_id": None, "open_document_count": 0,
            "page_index": None, "page_object_count": None,
            "unit_code": None, "reference_point_code": None, "dirty": None,
        }
        if self.app is None:
            if self.target_doc is not None:
                self._invalidate_target_document()
            return result
        try:
            result["open_document_count"] = len(self._open_document_proxies(self.app))
            if self.target_doc is None:
                return result
            try:
                document = self._target_document()
            except CorelBridgeError as exc:
                if exc.code == ErrorCode.NO_TARGET_DOCUMENT:
                    return result
                raise
            page = document.ActivePage
            page_count = document.Pages.Count
            if type(page_count) is not int or not 1 <= page_count <= 2147483647:
                raise ValueError("Unavailable page count")
            for field, value, minimum in (
                ("page_index", page.Index, 1), ("page_object_count", page.Shapes.Count, 0),
                ("unit_code", document.Unit, 0), ("reference_point_code", document.ReferencePoint, 0),
            ):
                if type(value) is not int or not minimum <= value <= 2147483647:
                    raise ValueError("Unavailable target metadata")
                result[field] = value
            actual_page = self._page_at(document, result["page_index"])
            if not self._same_com_object(page, actual_page, strict=True):
                raise ValueError("Unverifiable active page")
            dirty = document.Dirty
            if type(dirty) is bool:
                result["dirty"] = dirty
            elif type(dirty) is int and dirty in (-1, 0):
                result["dirty"] = bool(dirty)
            else:
                raise ValueError("Unavailable dirty state")
            result["target_bound"] = True
            result["document_session_id"] = self._document_session_id(document)
            return result
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("Could not reconcile finite bound-document state.", ErrorCode.COREL_COM_ERROR) from exc

    def _invalidate_target_document(self) -> None:
        if self.target_doc is not None:
            key = self._target_document_key or self._com_identity(self.target_doc)
            self._document_sessions.pop(key, None)
        self.target_doc = None
        self._target_application_key = None
        self._target_document_key = None

    def _bind_target_document(self, document: Any, new_document: bool = False) -> None:
        try:
            application_key = self._com_identity(self.app, strict=True)
            document_key = self._com_identity(document, strict=True)
        except CorelBridgeError:
            self._invalidate_target_document()
            raise
        self.target_doc = document
        self._target_application_key = application_key
        self._target_document_key = document_key
        if new_document:
            self._document_sessions.pop(self._target_document_key, None)
        self._target_document()
        self._document_session_id(document)

    def _open_document_proxies(self, app: Any) -> list[Any]:
        try:
            collection = app.Documents
            count = int(collection.Count)
            if not 0 <= count <= self.MAX_OPEN_DOCUMENTS:
                raise ValueError("Document enumeration limit")
            return [self._collection_item(collection, index) for index in range(1, count + 1)]
        except Exception as exc:
            raise CorelBridgeError(
                "Could not verify open documents; the bound target has not been used. "
                "Document inspection is limited to 1000 open documents.",
                ErrorCode.COREL_COM_ERROR,
            ) from exc

    @tracked_mutation
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
        self._bind_target_document(doc)
        return {
            "bound": True,
            "target_document_name": _safe_attr(doc, "Name"),
            "warning": "Subsequent editing operations will modify this document. Save a backup first."
        }

    @contextmanager
    def _in_inches(self, doc: Any, strict_restore: bool = False) -> Iterator[None]:
        self._note_mutation()
        previous = None
        changed = False
        try:
            previous = int(doc.Unit)
            if previous != self.CDR_INCH:
                changed = True
                doc.Unit = self.CDR_INCH
            yield
        finally:
            if changed and previous is not None:
                try:
                    doc.Unit = previous
                except Exception as exc:
                    raise CorelBridgeError(
                        "Could not restore the document unit after the operation.",
                        ErrorCode.COREL_COM_ERROR,
                    ) from exc

    @contextmanager
    def _reference_point(
        self, doc: Any, point: int = CDR_BOTTOM_LEFT, strict_restore: bool = False,
    ) -> Iterator[None]:
        self._note_mutation()
        previous = None
        changed = False
        try:
            previous = int(doc.ReferencePoint)
            if previous != point:
                changed = True
                doc.ReferencePoint = point
            yield
        finally:
            if changed and previous is not None:
                try:
                    doc.ReferencePoint = previous
                except Exception as exc:
                    raise CorelBridgeError(
                        "Could not restore the document reference point after the operation.",
                        ErrorCode.COREL_COM_ERROR,
                    ) from exc

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

    def _shape_bounds_inches(
        self, doc: Any, shape: Any, strict_context: bool = False,
    ) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        with self._in_inches(doc, strict_restore=strict_context), self._reference_point(
            doc, self.CDR_BOTTOM_LEFT, strict_restore=strict_context,
        ):
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
            "bold": {self.adapter.CDR_TRUE: True, self.adapter.CDR_FALSE: False}.get(bold_code),
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
        if self.target_doc is not None:
            try:
                self._target_document()
            except CorelBridgeError as exc:
                if exc.code != ErrorCode.NO_TARGET_DOCUMENT:
                    raise
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
    def _com_identity(value: Any, strict: bool = False) -> str:
        """Return a process-local identity key without changing COM selection or focus."""
        ole = _safe_attr(value, "_oleobj_")
        if ole is not None:
            query_interface = _safe_attr(ole, "QueryInterface")
            if callable(query_interface):
                try:
                    import pythoncom  # type: ignore

                    unknown = query_interface(pythoncom.IID_IUnknown)
                    # pywin32 documents repr as wrapper address plus attached IUnknown
                    # address. PyIUnknown is unhashable and has no GetIUnknown method.
                    match = re.search(r"with obj at (0x[0-9a-fA-F]+)>", repr(unknown))
                    if match is None:
                        raise ValueError("Unsupported IUnknown representation")
                    return f"iunknown:{int(match.group(1), 16)}"
                except Exception as exc:
                    if strict:
                        raise CorelBridgeError(
                            "Could not verify COM object identity.", ErrorCode.COREL_COM_ERROR,
                        ) from exc
            try:
                return f"iunknown:{int(ole.GetIUnknown())}"
            except Exception as exc:
                if strict:
                    raise CorelBridgeError(
                        "Could not verify COM object identity.", ErrorCode.COREL_COM_ERROR,
                    ) from exc
        return f"python:{id(value)}"

    def _same_com_object(self, left: Any, right: Any, strict: bool = False) -> bool:
        if left is None or right is None:
            return False
        if left is right:
            return True
        left_ole, right_ole = _safe_attr(left, "_oleobj_"), _safe_attr(right, "_oleobj_")
        if callable(_safe_attr(left_ole, "QueryInterface")) and callable(_safe_attr(right_ole, "QueryInterface")):
            try:
                import pythoncom  # type: ignore

                return bool(left_ole.QueryInterface(pythoncom.IID_IUnknown) == right_ole.QueryInterface(pythoncom.IID_IUnknown))
            except Exception as exc:
                if strict:
                    raise CorelBridgeError(
                        "Could not compare COM object identity.", ErrorCode.COREL_COM_ERROR,
                    ) from exc
                return False
        return self._com_identity(left, strict=strict) == self._com_identity(right, strict=strict)

    def _document_session_id(self, document: Any) -> str:
        key = self._com_identity(document, strict=True)
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
        documents = self._open_document_proxies(app)
        open_keys = {self._com_identity(document, strict=True) for document in documents}
        if self.target_doc is not None and (
            self._com_identity(self.target_doc) not in open_keys
            or self._target_application_key not in (None, self._com_identity(app))
        ):
            self._invalidate_target_document()
        for key in set(self._document_sessions) - open_keys:
            self._document_sessions.pop(key, None)
        active = self._active_document()
        result = []
        for index, document in enumerate(documents, start=1):
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

    def _reference_identity(self, value: Any) -> str:
        return identity_token(self._reference_secret, self._com_identity(value, strict=True))

    def _make_object_reference(
        self, document: Any, page: Any, layer: Any, shape: Any,
        page_index: int, layer_index: int, path: tuple[int, ...],
        ancestors: tuple[str, ...],
    ) -> dict[str, Any] | None:
        """Issue only complete identities. Missing native identity metadata is explicit null."""
        try:
            reference = {
                "version": 1, "bridge_session_id": self._bridge_session_id,
                "document_session_id": self._document_session_id(document),
                "page_identity": self._reference_identity(page),
                "layer_identity": self._reference_identity(layer),
                "ancestor_identities": list(ancestors),
                "shape_identity": self._reference_identity(shape),
                "static_id": shape.StaticID, "object_name": shape.Name or "",
                "shape_type_code": shape.Type,
                "page_index": page_index, "layer_index": layer_index,
                "shape_path": list(path),
            }
            reference["signature"] = reference_signature(self._reference_secret, reference)
            validate_reference(reference)
            return reference
        except Exception:
            return None

    @staticmethod
    def _reference_budget():
        remaining = MAX_REFERENCE_SCAN

        def consume(count: int = 1) -> None:
            nonlocal remaining
            if count < 0:
                raise CorelBridgeError("Invalid collection count during reference resolution.", ErrorCode.COREL_COM_ERROR)
            if count > remaining:
                raise CorelBridgeError(
                    "Object reference resolution exceeds the 10000-entry limit; narrow the document and inspect again.",
                    ErrorCode.AMBIGUOUS_SELECTOR,
                )
            remaining -= count
        return consume

    @staticmethod
    def _reference_count(collection: Any) -> int:
        count = collection.Count
        if type(count) is not int or count < 0:
            raise CorelBridgeError("Invalid collection count during reference resolution.", ErrorCode.COREL_COM_ERROR)
        return count

    def _reference_collection(self, collection: Any, consume):
        count = self._reference_count(collection)
        consume(count)
        for index in range(1, count + 1):
            yield index, self._collection_item(collection, index)

    def _reference_scope(self, document: Any, page_key: str, layer_key: str, consume):
        pages = [
            (index, page) for index, page in self._reference_collection(document.Pages, consume)
            if self._reference_identity(page) == page_key
        ]
        if len(pages) > 1:
            raise CorelBridgeError("Object reference page is ambiguous.", ErrorCode.AMBIGUOUS_SELECTOR)
        if not pages:
            raise CorelBridgeError("Object reference page no longer exists.", ErrorCode.OBJECT_NOT_FOUND)
        page_index, page = pages[0]
        layers = _safe_attr(page, "AllLayers")
        if layers is None:
            layers = page.Layers
        matches = [
            (index, layer) for index, layer in self._reference_collection(layers, consume)
            if self._reference_identity(layer) == layer_key
        ]
        if len(matches) > 1:
            raise CorelBridgeError("Object reference layer is ambiguous.", ErrorCode.AMBIGUOUS_SELECTOR)
        if not matches:
            raise CorelBridgeError("Object reference layer no longer exists on its page.", ErrorCode.OBJECT_NOT_FOUND)
        layer_index, layer = matches[0]
        return page_index, page, layer_index, layer

    def _walk_reference_shapes(self, collection: Any, consume, path=(), ancestors=()):
        for index, shape in self._reference_collection(collection, consume):
            key = self._reference_identity(shape)
            if key in ancestors:
                raise CorelBridgeError("A group cycle prevents unique reference resolution.", ErrorCode.AMBIGUOUS_SELECTOR)
            shape_path = (*path, index)
            yield shape, shape_path, ancestors
            type_code = shape.Type
            if type(type_code) is not int or type_code < 0:
                raise CorelBridgeError("Could not verify shape type during reference traversal.", ErrorCode.COREL_COM_ERROR)
            if type_code == self.adapter.CDR_GROUP_SHAPE:
                children = shape.Shapes
                if self._reference_count(children) > 0:
                    if len(ancestors) >= MAX_REFERENCE_DEPTH:
                        raise CorelBridgeError("Reference traversal exceeds 32 group levels.", ErrorCode.AMBIGUOUS_SELECTOR)
                    yield from self._walk_reference_shapes(children, consume, shape_path, (*ancestors, key))

    def _selector_document(self, object_name: str, shape_index: int, object_reference: dict | None):
        validate_reference_selector(object_name, shape_index, object_reference)
        if object_reference is not None:
            authenticate_reference(self._reference_secret, self._bridge_session_id, object_reference)
        return self._target_document()

    def _resolve_object_reference(self, document: Any, reference: dict, mutation: bool = False):
        """Rescan the recorded scope completely; never fall back to stored names/indices."""
        validate_reference(reference)
        authenticate_reference(self._reference_secret, self._bridge_session_id, reference)
        if reference["document_session_id"] != self._document_session_id(document):
            raise CorelBridgeError("Object reference belongs to another document session.", ErrorCode.OBJECT_NOT_FOUND)
        try:
            consume = self._reference_budget()
            page_index, page, layer_index, layer = self._reference_scope(
                document, reference["page_identity"], reference["layer_identity"], consume,
            )
            matches = []
            static_matches = 0
            for shape, path, ancestors in self._walk_reference_shapes(layer.Shapes, consume):
                # Identity checks must fail on unreadable native metadata, never interpret it as absence.
                static_id = shape.StaticID
                if type(static_id) is not int or static_id < 0:
                    raise ValueError("Unavailable StaticID")
                if static_id == reference["static_id"]:
                    static_matches += 1
                if self._reference_identity(shape) == reference["shape_identity"]:
                    matches.append((shape, path, ancestors))
            if len(matches) > 1 or static_matches > 1:
                raise CorelBridgeError("Object reference identity is ambiguous within its layer.", ErrorCode.AMBIGUOUS_SELECTOR)
            if not matches:
                raise CorelBridgeError("Referenced object was deleted or replaced.", ErrorCode.OBJECT_NOT_FOUND)
            shape, path, ancestors = matches[0]
            name = shape.Name
            if name is not None and type(name) is not str:
                raise ValueError("Unavailable name")
            if (shape.StaticID != reference["static_id"] or (name or "") != reference["object_name"]
                    or shape.Type != reference["shape_type_code"] or list(ancestors) != reference["ancestor_identities"]):
                raise CorelBridgeError("Referenced object identity or group membership changed; inspect it again.", ErrorCode.OBJECT_NOT_FOUND)
            if mutation and not self._same_com_object(page, document.ActivePage, strict=True):
                raise CorelBridgeError(
                    "Activate the referenced page explicitly before editing its objects.", ErrorCode.INVALID_ARGUMENT,
                )
            fresh = self._make_object_reference(document, page, layer, shape, page_index, layer_index, path, ancestors)
            if fresh is None:
                raise ValueError("Unavailable reference metadata")
            return shape, fresh
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("Could not verify object reference identity and scope.", ErrorCode.COREL_COM_ERROR) from exc

    def _reference_for_shape(self, document: Any, shape: Any) -> dict | None:
        """Best-effort issuance for legacy results; failure never creates a fabricated reference."""
        try:
            consume = self._reference_budget()
            page_index, page, layer_index, layer = self._reference_scope(
                document, self._reference_identity(shape.Page), self._reference_identity(shape.Layer), consume,
            )
            matches = [
                (candidate, path, ancestors)
                for candidate, path, ancestors in self._walk_reference_shapes(layer.Shapes, consume)
                if self._same_com_object(candidate, shape, strict=True)
            ]
            if len(matches) != 1:
                return None
            candidate, path, ancestors = matches[0]
            return self._make_object_reference(document, page, layer, candidate, page_index, layer_index, path, ancestors)
        except Exception:
            return None

    def get_object_info(self, object_name: str = "", shape_index: int = 0,
                        object_reference: dict | None = None) -> dict[str, Any]:
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        identity["bounds_inches"] = self._shape_bounds_inches(document, shape)
        identity["text"] = self._text_readback(shape)
        identity["fill"] = self._fill_readback(shape)
        identity["outline"] = self._outline_readback(shape)
        return {"document_name": _safe_string_attr(document, "Name"), "object": identity}

    def _inspection_target(self, object_name: str, shape_index: int,
                           object_reference: dict | None = None) -> tuple[Any, Any, dict[str, Any]]:
        """Resolve a legacy active-page selector or an exact scoped reference."""
        if object_reference is None:
            validate_inspection_selector(object_name, shape_index)
        document = self._selector_document(object_name, shape_index, object_reference)
        try:
            fresh_reference = None
            if object_reference is not None:
                shape, fresh_reference = self._resolve_object_reference(document, object_reference)
                shape_index = None
                if (not fresh_reference["ancestor_identities"]
                        and fresh_reference["page_identity"] == self._reference_identity(document.ActivePage)):
                    shape_index = self._index_for_shape(document, shape)
            else:
                shapes = self._shapes(document)
                count = int(shapes.Count)
            if object_reference is not None:
                pass
            elif object_name:
                if count > MAX_NAME_SCAN:
                    raise CorelBridgeError(
                        "The active page exceeds the 10000-object name lookup limit; "
                        "supply an explicit shape_index.", ErrorCode.AMBIGUOUS_SELECTOR,
                    )
                matches = []
                for index in range(1, count + 1):
                    candidate = self._collection_item(shapes, index)
                    if str(candidate.Name or "") == object_name:
                        matches.append((index, candidate))
                if not matches:
                    raise CorelBridgeError(
                        "No object with the requested name exists on the bound document's active page.",
                        ErrorCode.OBJECT_NOT_FOUND,
                    )
                if len(matches) != 1:
                    raise CorelBridgeError(
                        "The requested name is not unique on the bound document's active page.",
                        ErrorCode.AMBIGUOUS_SELECTOR,
                    )
                shape_index, shape = matches[0]
            else:
                if shape_index > count:
                    raise CorelBridgeError(
                        "shape_index does not exist on the bound document's active page.",
                        ErrorCode.OBJECT_NOT_FOUND,
                    )
                shape = self._collection_item(shapes, shape_index)
            identity = self._shape_identity(shape)
            if fresh_reference is not None:
                identity["page_index"] = fresh_reference["page_index"]
            for field in ("object_name", "layer_name"):
                value = identity[field]
                identity[field + "_truncated"] = value is not None and len(value) > MAX_NAME_CHARS
                if value is not None:
                    identity[field] = value[:MAX_NAME_CHARS]
            session_id = self._document_session_id(document)
            static_id = identity["static_id"]
            identity.update(
                document_session_id=session_id,
                object_id=f"{session_id}:shape:{static_id}" if static_id is not None else None,
                shape_index=shape_index,
                object_reference=fresh_reference if fresh_reference is not None else self._reference_for_shape(document, shape),
            )
            return document, shape, identity
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError(
                "Could not resolve the requested object on the bound document.",
                ErrorCode.COREL_COM_ERROR,
            ) from exc

    def get_object_bounds(self, object_name: str = "", shape_index: int = 0,
                          object_reference: dict | None = None) -> dict[str, Any]:
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        try:
            values = self._shape_bounds_inches(document, shape, strict_context=True)
            if any(value is None or not math.isfinite(value) for value in values.values()):
                raise ValueError("Unavailable bounds")
            x, y, width, height = (values[field] for field in ("x", "y", "width", "height"))
            if width < 0 or height < 0:
                raise ValueError("Invalid dimensions")
            if not all(math.isfinite(value) for value in (x + width, y + height)):
                raise ValueError("Unrepresentable bounds")
            return {
                "document_name": _safe_string_attr(document, "Name"), "object": identity,
                "bounds": {
                    "lower_left": {"x": x, "y": y},
                    "upper_right": {"x": round(x + width, 4), "y": round(y + height, 4)},
                    "center": {"x": round(x + width / 2, 4), "y": round(y + height / 2, 4)},
                    "width": width, "height": height,
                    "coordinate_space": "document_ruler_bottom_left_reference",
                },
                "unit": "inch",
            }
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError(
                "Could not read finite object bounds in inches.", ErrorCode.COREL_COM_ERROR,
            ) from exc

    def get_text_properties(
        self, object_name: str = "", shape_index: int = 0,
        max_text_chars: int = DEFAULT_TEXT_CHARS,
        object_reference: dict | None = None,
    ) -> dict[str, Any]:
        validate_text_limit(max_text_chars)
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        if identity["shape_type_code"] is None:
            raise CorelBridgeError("Could not read the object's type.", ErrorCode.COREL_COM_ERROR)
        if identity["shape_type_code"] != self.adapter.CDR_TEXT_SHAPE:
            raise CorelBridgeError("The selected object is not a text shape.", ErrorCode.INVALID_ARGUMENT)
        try:
            story = shape.Text.Story
            content = story.Text
            if not isinstance(content, str):
                raise ValueError("Unavailable text")
        except Exception as exc:
            raise CorelBridgeError(
                "Could not read the selected text object's story.", ErrorCode.COREL_COM_ERROR,
            ) from exc
        unavailable: list[str] = []
        indeterminate: list[str] = []
        truncated: list[str] = []
        text: dict[str, Any] = {
            "content": content[:max_text_chars], "content_length": len(content),
            "content_truncated": len(content) > max_text_chars,
            "formatting_scope": "whole_story_aggregate",
        }
        for field, attr, reader in (
            ("font", "Font", _safe_string_attr),
            ("size_points", "Size", _safe_float_attr),
            ("bold_code", "Bold", _safe_int_attr),
            ("italic_code", "Italic", _safe_int_attr),
            ("underline_code", "Underline", _safe_int_attr),
            ("alignment_code", "Alignment", _safe_int_attr),
        ):
            value = reader(story, attr)
            if value is None or (isinstance(value, float) and not math.isfinite(value)):
                unavailable.append(field)
                value = None
            elif (field == "font" and not value) or (field == "size_points" and value <= 0):
                indeterminate.append(field)
                value = None
            elif field.endswith("_code") and value < 0:
                if field not in ("bold_code", "italic_code") or value != self.adapter.CDR_TRUE:
                    indeterminate.append(field)
            if field == "font" and value is not None and len(value) > MAX_NAME_CHARS:
                value = value[:MAX_NAME_CHARS]
                truncated.append(field)
            text[field] = value
        for field in ("bold", "italic"):
            code = text[field + "_code"]
            text[field] = {self.adapter.CDR_TRUE: True, self.adapter.CDR_FALSE: False}.get(code)
            if code is not None and text[field] is None and field + "_code" not in indeterminate:
                indeterminate.append(field + "_code")
        text["unavailable_properties"] = unavailable
        text["indeterminate_properties"] = indeterminate
        text["truncated_properties"] = truncated
        text["layout"] = layout_readback(shape.Text, story)
        return {"document_name": _safe_string_attr(document, "Name"), "object": identity, "text": text}

    def get_fill(self, object_name: str = "", shape_index: int = 0,
                 object_reference: dict | None = None) -> dict[str, Any]:
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        fill = self._fill_readback(shape)
        if fill["type_code"] is None:
            raise CorelBridgeError("Could not read the object's fill type.", ErrorCode.COREL_COM_ERROR)
        unavailable: list[str] = []
        truncated: list[str] = []
        color = fill["color"]
        if fill["type"] == "uniform":
            if color is None:
                unavailable.append("color")
            else:
                if color["type_code"] is None:
                    unavailable.append("color.type_code")
                if isinstance(color["value"], dict):
                    unavailable.extend(
                        "color.value." + key for key, value in color["value"].items() if value is None
                    )
                for key in ("name", "hex_value"):
                    value = color[key]
                    if value is not None and len(value) > MAX_NAME_CHARS:
                        color[key] = value[:MAX_NAME_CHARS]
                        truncated.append("color." + key)
                if isinstance(color["value"], dict):
                    value = color["value"].get("spot_name")
                    if value is not None and len(value) > MAX_NAME_CHARS:
                        color["value"]["spot_name"] = value[:MAX_NAME_CHARS]
                        truncated.append("color.value.spot_name")
        fill["detail_scope"] = "type_and_uniform_color"
        fill["unavailable_properties"] = unavailable
        fill["truncated_properties"] = truncated
        return {"document_name": _safe_string_attr(document, "Name"), "object": identity, "fill": fill}

    def find_objects(
        self, name_contains: str = "", shape_type_code: int | None = None,
        text_contains: str = "", page_index: int | None = None,
        layer_name: str = "", max_results: int = 100, include_nested: bool = True,
        case_sensitive: bool = False, max_depth: int = 8, max_scan: int = 5000,
    ) -> dict[str, Any]:
        """Inspect a bounded, deterministic page/layer/group traversal without selection."""
        validate_search_inputs(
            name_contains, shape_type_code, text_contains, page_index, layer_name,
            max_results, include_nested, case_sensitive, max_depth, max_scan,
        )
        document = self._target_document()
        session_id = self._document_session_id(document)
        matches: list[dict[str, Any]] = []
        reasons: set[str] = set()
        scanned_entries = 0
        scanned_objects = 0
        stop = False
        normalize = (lambda value: value) if case_sensitive else str.casefold
        name_filter = normalize(name_contains)
        text_filter = normalize(text_contains)
        layer_filter = normalize(layer_name)

        def consume() -> bool:
            nonlocal scanned_entries, stop
            if scanned_entries >= max_scan:
                reasons.add("max_scan")
                stop = True
                return False
            scanned_entries += 1
            return True

        def walk(collection: Any, path: tuple[int, ...], ancestors: tuple[str, ...]):
            nonlocal scanned_objects
            count = int(collection.Count)
            for index in range(1, count + 1):
                if stop or not consume():
                    return
                shape = self._collection_item(collection, index)
                scanned_objects += 1
                key = self._com_identity(shape)
                if key in ancestors:
                    reasons.add("cycle")
                    continue
                shape_path = (*path, index)
                yield shape, shape_path, ancestors
                if stop:
                    return
                if include_nested and int(shape.Type) == self.adapter.CDR_GROUP_SHAPE:
                    children = shape.Shapes
                    if int(children.Count) > 0:
                        if len(shape_path) - 1 >= max_depth:
                            reasons.add("max_depth")
                        else:
                            yield from walk(children, shape_path, (*ancestors, key))

        try:
            if page_index is not None:
                # Check existence before enumeration, including when a layer filter has no hits.
                self._page_at(document, page_index)
                page_indices = (page_index,)
            else:
                page_indices = range(1, int(document.Pages.Count) + 1)
            for current_page_index in page_indices:
                if stop or not consume():
                    break
                page = self._collection_item(document.Pages, current_page_index)
                layers = _safe_attr(page, "AllLayers")
                if layers is None:
                    layers = page.Layers
                for layer_index in range(1, int(layers.Count) + 1):
                    if stop or not consume():
                        break
                    layer = self._collection_item(layers, layer_index)
                    current_layer_name = str(layer.Name or "")
                    if layer_filter and normalize(current_layer_name) != layer_filter:
                        continue
                    for shape, shape_path, ancestors in walk(layer.Shapes, (), ()):
                        name = str(shape.Name or "")
                        type_code = int(shape.Type)
                        if name_filter and name_filter not in normalize(name):
                            continue
                        if shape_type_code is not None and type_code != shape_type_code:
                            continue
                        text = None
                        if type_code == self.adapter.CDR_TEXT_SHAPE:
                            text = str(shape.Text.Story.Text or "")
                        if text_filter and (text is None or text_filter not in normalize(text)):
                            continue
                        # One additional matching object proves result truncation. Reaching
                        # the limit alone does not falsely mark an exact-size search incomplete.
                        if len(matches) >= max_results:
                            reasons.add("max_results")
                            stop = True
                            break
                        static_id = _safe_int_attr(shape, "StaticID")
                        matches.append({
                            "object_name": name[:256],
                            "name_truncated": len(name) > 256,
                            "static_id": static_id,
                            "object_id": f"{session_id}:shape:{static_id}" if static_id is not None else None,
                            "object_reference": self._make_object_reference(
                                document, page, layer, shape, current_page_index, layer_index,
                                shape_path, tuple(identity_token(self._reference_secret, key) for key in ancestors),
                            ),
                            "shape_type_code": type_code,
                            "page_index": current_page_index,
                            "layer_index": layer_index,
                            "layer_name": current_layer_name[:256],
                            "layer_name_truncated": len(current_layer_name) > 256,
                            "group_depth": len(shape_path) - 1,
                            "shape_path": list(shape_path),
                            "text_preview": text[:160] if text is not None else None,
                            "text_truncated": text is not None and len(text) > 160,
                        })
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError(
                "Could not complete object inspection on the bound document.",
                ErrorCode.COREL_COM_ERROR,
            ) from exc
        return {
            "document_name": _safe_string_attr(document, "Name"),
            "document_session_id": session_id,
            "matches": matches,
            "truncated": bool(reasons),
            "incomplete_reasons": sorted(reasons),
            "scanned_objects": scanned_objects,
            "scanned_entries": scanned_entries,
        }

    @tracked_mutation
    def create_document(self, width_in: float = 8.27, height_in: float = 11.69) -> dict[str, Any]:
        if not (0 < width_in <= 200 and 0 < height_in <= 200):
            raise CorelBridgeError(
                "Page dimensions must be greater than 0 and at most 200 inches.",
                ErrorCode.INVALID_ARGUMENT,
            )
        app = self._require_app()
        try:
            self._note_mutation()
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
            self._bind_target_document(doc, new_document=True)
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

    def _find_shape(self, doc: Any, object_name: str = "", shape_index: int = 0,
                    object_reference: dict | None = None) -> Any:
        if object_reference is not None:
            validate_reference_selector(object_name, shape_index, object_reference)
            return self._resolve_object_reference(doc, object_reference, mutation=True)[0]
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

    def _named_descendants(self, shape: Any, object_name: str) -> list[Any]:
        """Find named children recursively while keeping repeat groups independent."""
        matches: list[Any] = []
        children = _safe_attr(shape, "Shapes")
        count = _safe_int_attr(children, "Count") if children is not None else None
        if not count:
            return matches
        for index in range(1, count + 1):
            child = self._collection_item(children, index)
            if _safe_string_attr(child, "Name") == object_name:
                matches.append(child)
            matches.extend(self._named_descendants(child, object_name))
        return matches

    def _curve_polygon_points_inches(self, doc: Any, shape: Any, curve_precision: int) -> list[list[float]]:
        """Flatten one closed X7 subpath with Corel's native GetPolyline API."""
        curve = _safe_attr(shape, "Curve")
        subpaths = _safe_attr(curve, "SubPaths") if curve is not None else None
        count = _safe_int_attr(subpaths, "Count") if subpaths is not None else None
        if count != 1:
            raise CorelBridgeError(
                "The dieline must contain exactly one closed subpath.",
                ErrorCode.INVALID_ARGUMENT,
                {"subpath_count": count},
            )
        subpath = self._collection_item(subpaths, 1)
        closed = _safe_attr(subpath, "Closed")
        if closed in (False, 0, None):
            raise CorelBridgeError("The dieline subpath must be closed.", ErrorCode.INVALID_ARGUMENT)
        try:
            polyline = subpath.GetPolyline(int(curve_precision))
            nodes = polyline.Nodes
            node_count = int(nodes.Count)
        except Exception as exc:
            raise CorelBridgeError(
                "Could not flatten the dieline with CorelDRAW's GetPolyline API.",
                ErrorCode.COREL_COM_ERROR,
            ) from exc
        if not 3 <= node_count <= 5001:
            raise CorelBridgeError(
                "The flattened dieline must contain 3 to 5,000 points.",
                ErrorCode.INVALID_ARGUMENT,
                {"node_count": node_count},
            )
        points: list[list[float]] = []
        with self._in_inches(doc):
            for index in range(1, node_count + 1):
                node = self._collection_item(nodes, index)
                try:
                    x, y = float(node.PositionX), float(node.PositionY)
                except Exception:
                    try:
                        position = node.GetPosition()
                        x, y = float(position[0]), float(position[1])
                    except Exception as exc:
                        raise CorelBridgeError(
                            "Could not read a flattened dieline node position.",
                            ErrorCode.COREL_COM_ERROR,
                        ) from exc
                if not points or abs(points[-1][0] - x) > 1e-9 or abs(points[-1][1] - y) > 1e-9:
                    points.append([x, y])
        if len(points) > 3 and abs(points[0][0] - points[-1][0]) <= 1e-9 and abs(points[0][1] - points[-1][1]) <= 1e-9:
            points.pop()
        return points

    def _descendant_identity_summary(self, shape: Any, limit: int = 5000) -> list[dict[str, Any]]:
        """Return a bounded structural signature for approval-time source identity."""
        result: list[dict[str, Any]] = []

        def children_of(parent: Any) -> list[Any]:
            children = _safe_attr(parent, "Shapes")
            count = _safe_int_attr(children, "Count") if children is not None else None
            return [self._collection_item(children, index) for index in range(1, (count or 0) + 1)]

        stack = list(reversed(children_of(shape)))
        while stack:
            if len(result) >= limit:
                raise CorelBridgeError(
                    "The repeat unit exceeds the supported 5,000-descendant inspection limit.",
                    ErrorCode.INVALID_ARGUMENT,
                )
            child = stack.pop()
            result.append({
                "object_name": _safe_string_attr(child, "Name") or "",
                "static_id": _safe_int_attr(child, "StaticID"),
                "shape_type_code": _safe_int_attr(child, "Type"),
            })
            stack.extend(reversed(children_of(child)))
        return result

    def _repeat_source_signature(
        self,
        doc: Any,
        source: Any,
        dieline_name: str,
        curve_precision: int,
    ) -> dict[str, Any]:
        """Capture document/page/group/contour identity without changing page focus."""
        matches = self._named_descendants(source, dieline_name)
        if len(matches) != 1:
            raise CorelBridgeError(
                "The source group must contain exactly one uniquely named dieline.",
                ErrorCode.AMBIGUOUS_SELECTOR if matches else ErrorCode.OBJECT_NOT_FOUND,
                {"dieline_name": dieline_name, "matches": len(matches)},
            )
        absolute_points = self._curve_polygon_points_inches(doc, matches[0], curve_precision)
        minimum_x = min(point[0] for point in absolute_points)
        minimum_y = min(point[1] for point in absolute_points)
        maximum_x = max(point[0] for point in absolute_points)
        maximum_y = max(point[1] for point in absolute_points)
        source_page = _safe_attr(source, "Page")
        if source_page is None:
            source_page = _safe_attr(doc, "ActivePage")
        source_identity = self._shape_identity(source)
        source_identity["page_index"] = source_identity.get("page_index") or _safe_int_attr(source_page, "Index")
        return {
            "document_session_id": self._document_session_id(doc),
            "document_name": _safe_string_attr(doc, "Name"),
            "document_full_path": _safe_string_attr(doc, "FullFileName") or None,
            "page_index": _safe_int_attr(source_page, "Index"),
            "page_name": _safe_string_attr(source_page, "Name"),
            "source_group": source_identity,
            "source_group_bounds_inches": self._shape_bounds_inches(doc, source),
            "source_rotation_degrees": round(float(_safe_float_attr(source, "RotationAngle") or 0.0) % 360.0, 6),
            "descendants": self._descendant_identity_summary(source),
            "dieline": self._shape_identity(matches[0]),
            "dieline_name": dieline_name,
            "contour_bounds_inches": {
                "x": round(minimum_x, 6),
                "y": round(minimum_y, 6),
                "width": round(maximum_x - minimum_x, 6),
                "height": round(maximum_y - minimum_y, 6),
            },
            "contour_points_inches": [
                [round(x - minimum_x, 6), round(y - minimum_y, 6)]
                for x, y in absolute_points
            ],
        }

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

    def _font_collection(self):
        try:
            collection = self._require_app().FontList
            count = collection.Count
            if type(count) is not int or count < 0 or count > 100000:
                raise ValueError("Invalid font count")
            return collection, count
        except Exception as exc:
            raise CorelBridgeError("Could not read the X7 font catalog.", ErrorCode.COREL_COM_ERROR) from exc

    def _font_at(self, collection, index):
        value = self._collection_item(collection, index)
        if type(value) is not str or not value.strip() or len(value) > MAX_FONT_CHARS:
            raise ValueError("Unavailable font name")
        return value

    def list_fonts(self, name_contains: str = "", max_results: int = 100, max_scan: int = 5000):
        if type(name_contains) is not str or len(name_contains) > MAX_FONT_CHARS:
            raise CorelBridgeError("name_contains must be a string of at most 200 characters.", ErrorCode.INVALID_ARGUMENT)
        if type(max_results) is not int or not 1 <= max_results <= 1000:
            raise CorelBridgeError("max_results must be an integer between 1 and 1000.", ErrorCode.INVALID_ARGUMENT)
        if type(max_scan) is not int or not 1 <= max_scan <= MAX_FONT_SCAN:
            raise CorelBridgeError("max_scan must be an integer between 1 and 10000.", ErrorCode.INVALID_ARGUMENT)
        collection, count = self._font_collection()
        fonts, reasons, scanned = [], set(), 0
        for index in range(1, min(count, max_scan) + 1):
            scanned += 1
            try:
                name = self._font_at(collection, index)
            except Exception:
                reasons.add("unavailable_font_entry")
                continue
            if name_contains.casefold() not in name.casefold():
                continue
            if len(fonts) == max_results:
                reasons.add("max_results")
                break
            fonts.append(name)
        if count > max_scan and "max_results" not in reasons:
            reasons.add("max_scan")
        return {"fonts": fonts, "returned_count": len(fonts), "total_count": count,
                "scanned_count": scanned, "truncated": bool(reasons),
                "incomplete_reasons": sorted(reasons), "availability_scope": "coreldraw_font_catalog"}

    def _require_font(self, font):
        validate_font(font)
        # Inspect the complete catalog with a literal filter. A missing font may
        # only be concluded when no entry or scan limit is unavailable.
        catalog = self.list_fonts(name_contains=font, max_results=1000, max_scan=MAX_FONT_SCAN)
        if catalog["total_count"] > MAX_FONT_SCAN:
            raise CorelBridgeError("The font catalog exceeds the 10000-entry verification limit.", ErrorCode.UNSUPPORTED_IN_PROFILE)
        if catalog["truncated"]:
            raise CorelBridgeError("Could not establish complete font availability before editing.", ErrorCode.UNSUPPORTED_IN_PROFILE)
        matches = [name for name in catalog["fonts"] if name.casefold() == font.casefold()]
        if not matches:
            raise CorelBridgeError("The requested font is absent from CorelDRAW's font catalog.", ErrorCode.INVALID_ARGUMENT)
        return matches[0]

    def _typography_bounds(self, document, shape):
        bounds = self._shape_bounds_inches(document, shape, strict_context=True)
        if any(value is None or not math.isfinite(value) for value in bounds.values()):
            raise CorelBridgeError("Could not read actual text bounds after editing.", ErrorCode.COREL_COM_ERROR)
        return bounds

    @tracked_mutation
    def add_paragraph_text(
        self, text: str, x_inches: float, y_inches: float, width_inches: float, height_inches: float,
        size_points: float = 12, font: str = "Arial", bold: bool = False, italic: bool = False,
        underline: str = "none", alignment: str = "left", object_name: str = "",
    ):
        validate_paragraph(text, x_inches, y_inches, width_inches, height_inches, object_name)
        requested = validate_style(font, size_points, bold, italic, underline, alignment)
        document = self._target_document()
        requested["font"] = self._require_font(font)
        if int(self._shapes(document).Count) > MAX_NAME_SCAN:
            raise CorelBridgeError("The page exceeds the 10000-object naming limit.", ErrorCode.UNSUPPORTED_IN_PROFILE)
        name = self._unique_name(document, object_name, "AI_Paragraph")
        layer = self._get_layer(document)
        try:
            self._note_mutation()
            with self._in_inches(document, strict_restore=True):
                shape = layer.CreateParagraphText(
                    float(x_inches), float(y_inches + height_inches),
                    float(x_inches + width_inches), float(y_inches), text,
                    self.adapter.CDR_LANGUAGE_NONE, self.adapter.CDR_CHARSET_MIXED,
                    requested["font"], float(size_points),
                    self.adapter.CDR_TRUE if bold else self.adapter.CDR_FALSE,
                    self.adapter.CDR_TRUE if italic else self.adapter.CDR_FALSE,
                    UNDERLINES[underline], ALIGNMENTS[alignment],
                )
                shape.Name = name
            story = shape.Text.Story
            actual_content = story.Text
            normalize_breaks = lambda value: value.replace("\r\n", "\r").replace("\n", "\r")
            if not isinstance(actual_content, str) or normalize_breaks(actual_content) != normalize_breaks(text):
                raise CorelBridgeError("Paragraph text content readback differs from the request.", ErrorCode.COREL_COM_ERROR)
            actual_style = style_readback(story)
            self._verify_text_style(requested, actual_style)
            layout = layout_readback(shape.Text, story)
            if layout["text_type_code"] != 1:
                raise CorelBridgeError("CorelDRAW did not return an editable paragraph text object.", ErrorCode.COREL_COM_ERROR)
            identity = self._shape_identity(shape)
            identity["object_reference"] = self._reference_for_shape(document, shape)
            return {"created": True, "object_name": name, "object": identity,
                    "requested_style": requested, "actual_style": actual_style,
                    "line_breaks_normalized": actual_content != text,
                    "actual_bounds_inches": self._typography_bounds(document, shape), "layout": layout}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW could not create or inspect paragraph text.", ErrorCode.COREL_COM_ERROR) from exc

    @staticmethod
    def _verify_text_style(requested, actual):
        for field, expected in requested.items():
            observed = actual[field]
            matches = observed == expected
            if field == "size_points":
                matches = observed is not None and math.isclose(observed, expected, abs_tol=0.01, rel_tol=0)
            elif field == "font":
                matches = observed is not None and observed.casefold() == expected.casefold()
            if not matches:
                raise CorelBridgeError("Native text formatting readback differs from the request.",
                                       ErrorCode.COREL_COM_ERROR, {"property": field})

    @tracked_mutation
    def set_text_style(
        self, font: str | None = None, size_points: float | None = None,
        bold: bool | None = None, italic: bool | None = None,
        underline: str | None = None, alignment: str | None = None,
        object_name: str = "", shape_index: int = 0, object_reference: dict | None = None,
    ):
        requested = validate_style(font, size_points, bold, italic, underline, alignment)
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        if object_reference is not None:
            shape, _ = self._resolve_object_reference(document, object_reference, mutation=True)
        if identity["shape_type_code"] != self.adapter.CDR_TEXT_SHAPE:
            raise CorelBridgeError("The selected object is not a text shape.", ErrorCode.INVALID_ARGUMENT)
        try:
            text = shape.Text
            story = text.Story
            layout = layout_readback(text, story)
            if layout["text_type_code"] not in (0, 1) or layout["frame_count"] != 1:
                raise CorelBridgeError("Style editing requires one unfitted, unlinked text frame.", ErrorCode.UNSUPPORTED_IN_PROFILE)
            before = style_readback(story)
            # Verify property access before the first write. Mixed formatting is
            # permitted: this operation explicitly applies to the entire story.
            for field in requested:
                getattr(story, STYLE_ATTRIBUTES[field])
            if font is not None:
                requested["font"] = self._require_font(font)
            for field, value in requested.items():
                native = UNDERLINES[value] if field == "underline" else ALIGNMENTS[value] if field == "alignment" else value
                self._note_mutation()
                setattr(story, STYLE_ATTRIBUTES[field], native)
            actual = style_readback(story)
            self._verify_text_style(requested, actual)
            identity["object_reference"] = self._reference_for_shape(document, shape)
            return {"updated": True, "object": identity, "formatting_scope": "whole_story",
                    "requested_style": requested, "before_style": before, "actual_style": actual,
                    "actual_bounds_inches": self._typography_bounds(document, shape),
                    "layout": layout_readback(text, story)}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW could not apply or inspect text formatting.", ErrorCode.COREL_COM_ERROR) from exc

    @tracked_mutation
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
                    "object": self._shape_identity(shape),
                    "font": font, "size_points": size_pt, "bold": bold,
                    "actual_text": actual_text,
                    "actual_bounds_inches": actual_bounds,
                    "note": "Editable artistic-text object created."}
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 rejected CreateArtisticText or naming. Full COM error: " + str(exc)) from exc

    @tracked_mutation
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
                    "object": self._shape_identity(shape),
                    "x_inches": x_in, "y_inches": y_in,
                    "width_inches": width_in, "height_inches": height_in,
                    "actual_bounds_inches": actual_bounds}
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 rejected CreateRectangle2 or naming. Full COM error: " + str(exc)) from exc

    @tracked_mutation
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
                    "object": self._shape_identity(shape),
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

    @tracked_mutation
    def set_fill_color(self, red: int, green: int, blue: int,
                       object_name: str = "", shape_index: int = 0,
                       object_reference: dict | None = None) -> dict[str, Any]:
        self._validate_rgb(red, green, blue)
        doc = self._selector_document(object_name, shape_index, object_reference)
        shape = self._find_shape(doc, object_name, shape_index, object_reference)
        try:
            color = self._require_app().CreateRGBColor(red, green, blue)
            self._note_mutation()
            shape.Fill.ApplyUniformFill(color)
            name = str(_safe_attr(shape, "Name") or "")
            return {"updated": True, "object_name": name, "shape_index": self._index_for_shape(doc, shape),
                    "fill_rgb": [red, green, blue],
                    "actual_fill": self._fill_readback(shape)}
        except Exception as exc:
            raise CorelBridgeError("Could not set fill color in CorelDRAW X7. Full COM error: " + str(exc)) from exc

    @tracked_mutation
    def set_outline(self, red: int, green: int, blue: int, width_points: float = 1.0,
                    object_name: str = "", shape_index: int = 0,
                    object_reference: dict | None = None) -> dict[str, Any]:
        self._validate_rgb(red, green, blue)
        if not (0 <= width_points <= 72):
            raise CorelBridgeError(
                "Outline width must be between 0 and 72 points; use 0 to remove it.",
                ErrorCode.INVALID_ARGUMENT,
            )
        doc = self._selector_document(object_name, shape_index, object_reference)
        shape = self._find_shape(doc, object_name, shape_index, object_reference)
        try:
            if width_points == 0:
                self._note_mutation()
                shape.Outline.SetNoOutline()
                return {"updated": True, "object_name": str(_safe_attr(shape, "Name") or ""),
                        "outline_removed": True,
                        "actual_outline": self._outline_readback(shape)}
            color = self._require_app().CreateRGBColor(red, green, blue)
            self._note_mutation()
            shape.Outline.Color = color
            with self._in_inches(doc):
                shape.Outline.Width = float(width_points) / 72.0
            return {"updated": True, "object_name": str(_safe_attr(shape, "Name") or ""),
                    "outline_rgb": [red, green, blue], "width_points": width_points,
                    "actual_outline": self._outline_readback(shape)}
        except Exception as exc:
            raise CorelBridgeError("Could not set outline in CorelDRAW X7. Full COM error: " + str(exc)) from exc

    @tracked_mutation
    def move_object(self, x_inches: float, y_inches: float,
                    object_name: str = "", shape_index: int = 0,
                    object_reference: dict | None = None) -> dict[str, Any]:
        doc = self._selector_document(object_name, shape_index, object_reference)
        shape = self._find_shape(doc, object_name, shape_index, object_reference)
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

    @tracked_mutation
    def resize_object(self, width_inches: float = 0, height_inches: float = 0,
                      keep_aspect_ratio: bool = False,
                      object_name: str = "", shape_index: int = 0,
                      object_reference: dict | None = None) -> dict[str, Any]:
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
        doc = self._selector_document(object_name, shape_index, object_reference)
        shape = self._find_shape(doc, object_name, shape_index, object_reference)
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

    def _layout_target(self, object_name="", shape_index=0, object_reference=None, mutation=False):
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        if mutation and object_reference is not None:
            shape, _ = self._resolve_object_reference(document, object_reference, mutation=True)
        return document, shape, identity

    @staticmethod
    def _layout_method(shape, name):
        try:
            method = getattr(shape, name)
            if callable(method):
                return method
        except Exception:
            pass
        raise CorelBridgeError("The selected object's required layout API is unavailable.", ErrorCode.UNSUPPORTED_IN_PROFILE)

    def _layout_snapshot(self, document, shape):
        try:
            method = self._layout_method(shape, "GetMatrix")
            with self._in_inches(document, strict_restore=True), self._reference_point(document, strict_restore=True):
                bounds = {field: getattr(shape, attr) for field,attr in
                          (("x", "PositionX"), ("y", "PositionY"), ("width", "SizeWidth"), ("height", "SizeHeight"))}
                matrix = method()
                angle = shape.RotationAngle
            if not isinstance(matrix, (tuple, list)) or len(matrix)!=6 or any(type(v) not in (int,float) for v in matrix):
                raise ValueError("Incomplete matrix")
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in (*bounds.values(), *matrix, angle)) or bounds["width"]<0 or bounds["height"]<0:
                raise ValueError("Nonfinite transform")
            return {"bounds_inches": {key:float(value) for key,value in bounds.items()}, "matrix": [float(v) for v in matrix],
                    "rotation_degrees": angle % 360, "native_z_order": _safe_int_attr(shape, "ZOrder"),
                    "matrix_coordinate_space": "native_affine_in_document_inches"}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("Could not read the object's finite native transform and bounds.", ErrorCode.COREL_COM_ERROR) from exc

    def get_object_transform(self, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None):
        document, shape, identity = self._layout_target(object_name, shape_index, object_reference)
        return {"object": identity, "transform": self._layout_snapshot(document, shape)}

    @tracked_mutation
    def rotate_object(
        self, angle_degrees: float, relative: bool = True,
        center_x_inches: float | None = None, center_y_inches: float | None = None,
        object_name: str = "", shape_index: int = 0, object_reference: dict | None = None,
    ):
        validate_rotation(angle_degrees, relative, center_x_inches, center_y_inches)
        document, shape, identity = self._layout_target(object_name, shape_index, object_reference, mutation=True)
        method = self._layout_method(shape, "RotateEx")
        before = self._layout_snapshot(document, shape)
        bounds = before["bounds_inches"]
        center = (bounds["x"]+bounds["width"]/2, bounds["y"]+bounds["height"]/2) if center_x_inches is None else (center_x_inches,center_y_inches)
        delta = angle_degrees if relative else angle_degrees % 360-before["rotation_degrees"]
        expected = (before["rotation_degrees"]+delta) % 360
        try:
            self._note_mutation()
            with self._in_inches(document, strict_restore=True):
                method(float(delta), float(center[0]), float(center[1]))
            actual = self._layout_snapshot(document, shape)
            if circular_difference(actual["rotation_degrees"], expected)>0.001:
                raise CorelBridgeError("Native rotation readback differs from the requested angle.", ErrorCode.COREL_COM_ERROR)
            return {"rotated": True, "object": identity, "relative": relative,
                    "applied_angle_degrees": delta, "center_inches": {"x": center[0], "y": center[1]},
                    "before_transform": before, "actual_transform": actual}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW could not rotate or inspect the selected object.", ErrorCode.COREL_COM_ERROR) from exc

    @tracked_mutation
    def flip_object(self, axis: str, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None):
        choice(axis, "axis", FLIP_AXES)
        document, shape, identity = self._layout_target(object_name, shape_index, object_reference, mutation=True)
        method = self._layout_method(shape, "Flip")
        before = self._layout_snapshot(document, shape)
        old_determinant = matrix_determinant(before["matrix"])
        if not math.isfinite(old_determinant) or abs(old_determinant)<1e-12:
            raise CorelBridgeError("A degenerate native matrix cannot establish mirror orientation.", ErrorCode.UNSUPPORTED_IN_PROFILE)
        try:
            self._note_mutation()
            method(FLIP_AXES[axis])
            actual = self._layout_snapshot(document, shape)
            expected = old_determinant if axis=="both" else -old_determinant
            actual_determinant = matrix_determinant(actual["matrix"])
            if (actual_determinant==0 or math.copysign(1,actual_determinant)!=math.copysign(1,expected)
                    or not math.isclose(actual_determinant, expected, rel_tol=1e-6, abs_tol=1e-9)):
                raise CorelBridgeError("Native mirror orientation readback differs from the request.", ErrorCode.COREL_COM_ERROR)
            if axis=="both" and any(not math.isclose(actual["matrix"][i], -before["matrix"][i], rel_tol=1e-6, abs_tol=1e-9) for i in range(4)):
                raise CorelBridgeError("Native two-axis mirror matrix did not change as requested.", ErrorCode.COREL_COM_ERROR)
            return {"flipped": True, "object": identity, "axis": axis,
                    "before_transform": before, "actual_transform": actual,
                    "orientation_check": "native_matrix_parity"}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW could not mirror or inspect the selected object.", ErrorCode.COREL_COM_ERROR) from exc

    def _stacking_snapshot(self, shape):
        try:
            parent = shape.ParentGroup
            collection = shape.Layer.Shapes if parent is None else parent.Shapes
            count = collection.Count
            if type(count) is not int or not 1 <= count <= MAX_REFERENCE_SCAN:
                raise CorelBridgeError("The sibling stacking scope exceeds the 10000-object limit.", ErrorCode.UNSUPPORTED_IN_PROFILE)
            compare = self._layout_method(shape, "OrderIsInFrontOf")
            members, above, found = set(), 0, 0
            for index in range(1,count+1):
                candidate = self._collection_item(collection,index)
                key = self._reference_identity(candidate)
                if key in members:
                    raise ValueError("Ambiguous sibling membership")
                members.add(key)
                if self._same_com_object(candidate,shape,strict=True):
                    found += 1
                    continue
                in_front = compare(candidate)
                if type(in_front) is bool:
                    pass
                elif type(in_front) is int and in_front in (-1,0):
                    in_front = bool(in_front)
                else:
                    raise ValueError("Unavailable native stacking relation")
                if not in_front:
                    above += 1
            if found != 1:
                raise ValueError("Selected shape is absent from its sibling scope")
            scope = self._reference_identity(parent if parent is not None else shape.Layer)
            return {"rank_from_front": above+1, "sibling_count": count,
                    "native_z_order": _safe_int_attr(shape,"ZOrder")}, members, scope
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("Could not establish complete native sibling stacking order.", ErrorCode.COREL_COM_ERROR) from exc

    @tracked_mutation
    def order_object(self, position: str, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None):
        choice(position,"position",ORDER_METHODS)
        document, shape, identity = self._layout_target(object_name,shape_index,object_reference,mutation=True)
        method = self._layout_method(shape,ORDER_METHODS[position])
        before,members,scope = self._stacking_snapshot(shape)
        expected = {"front": 1, "back": before["sibling_count"],
                    "forward_one": max(1,before["rank_from_front"]-1),
                    "back_one": min(before["sibling_count"],before["rank_from_front"]+1)}[position]
        try:
            self._note_mutation()
            method()
            actual,new_members,new_scope = self._stacking_snapshot(shape)
            if members!=new_members or scope!=new_scope or actual["rank_from_front"]!=expected:
                raise CorelBridgeError("Native sibling order readback differs from the request.",ErrorCode.COREL_COM_ERROR)
            return {"ordered": True,"object": identity,"position": position,
                    "scope": "immediate_siblings","before_order": before,"actual_order": actual}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW could not reorder or inspect the selected object.",ErrorCode.COREL_COM_ERROR) from exc

    @tracked_mutation
    def distribute_objects(
        self, axis: str, object_names: list[str] | None = None, object_references: list[dict] | None = None,
        mode: str = "equal_gaps", spacing_inches: float | None = None, allow_overlap: bool = False,
    ):
        choice(axis,"axis",("horizontal","vertical"))
        choice(mode,"mode",("equal_gaps","equal_centers"))
        if type(allow_overlap) is not bool:
            raise CorelBridgeError("allow_overlap must be a boolean.",ErrorCode.INVALID_ARGUMENT)
        # Validate spacing before any native context changes.
        if spacing_inches is not None:
            from .typography import finite_number
            finite_number(spacing_inches,"spacing_inches",-200,200)
            if mode!="equal_gaps":
                raise CorelBridgeError("Explicit spacing requires equal_gaps mode.",ErrorCode.INVALID_ARGUMENT)
        if (object_names is None)==(object_references is None):
            raise CorelBridgeError("Supply exactly one object_names or object_references list.",ErrorCode.AMBIGUOUS_SELECTOR)
        selectors = object_names if object_names is not None else object_references
        if type(selectors) is not list or not 3<=len(selectors)<=MAX_LAYOUT_OBJECTS:
            raise CorelBridgeError("Distribution requires a list of 3-100 objects.",ErrorCode.INVALID_ARGUMENT)
        if object_names is not None and (any(type(name) is not str or not name.strip() or len(name)>MAX_NAME_CHARS for name in selectors) or len(set(selectors))!=len(selectors)):
            raise CorelBridgeError("object_names must contain unique nonblank names of at most 256 characters.",ErrorCode.INVALID_ARGUMENT)
        targets,keys = [],set()
        for selector in selectors:
            document,shape,identity = self._layout_target(object_name=selector if object_names is not None else "",
                object_reference=selector if object_references is not None else None,mutation=True)
            reference = identity["object_reference"]
            if reference is None:
                raise CorelBridgeError("Distribution requires complete session object identity for every target.",ErrorCode.UNSUPPORTED_IN_PROFILE)
            key = reference["shape_identity"]
            if key in keys:
                raise CorelBridgeError("Distribution targets must be distinct objects.",ErrorCode.INVALID_ARGUMENT)
            keys.add(key)
            self._layout_method(shape,"SetPosition")
            targets.append((document,shape,identity,reference))
        if any(keys.intersection(reference["ancestor_identities"]) for _,_,_,reference in targets):
            raise CorelBridgeError("A group and its descendant cannot be distributed together.",ErrorCode.INVALID_ARGUMENT)
        before = [self._layout_snapshot(doc,shape) for doc,shape,_,_ in targets]
        plan = plan_distribution([value["bounds_inches"] for value in before],axis,mode,spacing_inches,allow_overlap)
        try:
            document = targets[0][0]
            for doc,_,_,reference in targets:
                self._resolve_object_reference(doc,reference,mutation=True)
            self._note_mutation()
            with self._in_inches(document,strict_restore=True), self._reference_point(document,strict_restore=True):
                for item in plan["targets"]:
                    _,shape,_,reference = targets[item["input_index"]]
                    # Recheck each exact identity immediately before moving it.
                    shape,_ = self._resolve_object_reference(document,reference,mutation=True)
                    bounds = item["bounds"]
                    shape.SetPosition(bounds["x"],bounds["y"])
            result = []
            for item in plan["targets"]:
                index = item["input_index"]
                doc,shape,identity,_ = targets[index]
                actual = self._layout_snapshot(doc,shape)
                if any(not math.isclose(actual["bounds_inches"][key],value,abs_tol=POSITION_TOLERANCE,rel_tol=0)
                       for key,value in item["bounds"].items()):
                    raise CorelBridgeError("Native distributed bounds differ from the geometry plan.",ErrorCode.COREL_COM_ERROR)
                result.append({"object": identity,"before_transform": before[index],"actual_transform": actual,
                               "planned_bounds_inches": item["bounds"]})
            return {"distributed": True,"axis": axis,"mode": mode,"spacing_inches": plan["spacing_inches"],
                    "has_axis_overlap": plan["has_overlap"],"overlap_allowed": allow_overlap,"objects": result}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW could not distribute or inspect the selected objects.",ErrorCode.COREL_COM_ERROR) from exc

    @tracked_mutation
    def set_text_content(self, new_text: str, object_name: str = "", shape_index: int = 0,
                         object_reference: dict | None = None) -> dict[str, Any]:
        if not new_text.strip():
            raise CorelBridgeError("Text cannot be empty.", ErrorCode.INVALID_ARGUMENT)
        doc = self._selector_document(object_name, shape_index, object_reference)
        shape = self._find_shape(doc, object_name, shape_index, object_reference)
        try:
            story = shape.Text.Story
            old_text = str(story.Text)
            self._note_mutation()
            story.Text = str(new_text)
            return {"updated": True, "object_name": str(_safe_attr(shape, "Name") or ""),
                    "old_text": old_text[:200], "new_text": new_text}
        except Exception as exc:
            raise CorelBridgeError("Could not edit text; target may not be a text object. Full COM error: " + str(exc)) from exc

    @tracked_mutation
    def rename_object(self, new_name: str, object_name: str = "", shape_index: int = 0,
                      object_reference: dict | None = None) -> dict[str, Any]:
        if not new_name.strip():
            raise CorelBridgeError("new_name cannot be blank.", ErrorCode.INVALID_ARGUMENT)
        doc = self._selector_document(object_name, shape_index, object_reference)
        shape = self._find_shape(doc, object_name, shape_index, object_reference)
        unique = self._unique_name(doc, new_name, "AI_Object")
        # If we're renaming the selected object to its current name, preserve it.
        if unique != new_name and str(_safe_attr(shape, "Name") or "") == new_name:
            unique = new_name
        try:
            old = str(_safe_attr(shape, "Name") or "")
            self._note_mutation()
            shape.Name = unique
            identity = self._shape_identity(shape)
            identity["object_reference"] = self._reference_for_shape(doc, shape)
            return {"renamed": True, "old_name": old, "object_name": unique,
                    "object": identity}
        except Exception as exc:
            raise CorelBridgeError("Could not rename the object. Full COM error: " + str(exc)) from exc

    @tracked_mutation
    def duplicate_object(self, offset_x_inches: float = 0.25, offset_y_inches: float = -0.25,
                         object_name: str = "", shape_index: int = 0,
                         new_name: str = "", object_reference: dict | None = None) -> dict[str, Any]:
        doc = self._selector_document(object_name, shape_index, object_reference)
        shape = self._find_shape(doc, object_name, shape_index, object_reference)
        try:
            with self._in_inches(doc):
                new_shape = shape.Duplicate(float(offset_x_inches), float(offset_y_inches))
                name = self._name_shape(doc, new_shape, new_name, "AI_Copy")
            identity = self._shape_identity(new_shape)
            identity["object_reference"] = self._reference_for_shape(doc, new_shape)
            return {"duplicated": True, "source_name": str(_safe_attr(shape, "Name") or ""),
                    "object_name": name, "offset_inches": [offset_x_inches, offset_y_inches],
                    "shape_index": self._index_for_shape(doc, new_shape),
                    "object": identity}
        except Exception as exc:
            raise CorelBridgeError("Could not duplicate object. Full COM error: " + str(exc)) from exc

    @tracked_mutation
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

    @tracked_mutation
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

    @tracked_mutation
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

    @tracked_mutation
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

    @tracked_mutation
    def import_artwork(self, file_path: str, object_name: str = "AI_Artwork") -> dict[str, Any]:
        path = self._validate_artwork_path(file_path)
        doc = self._target_document()
        layer = self._get_layer(doc)
        before = int(self._shapes(doc).Count)
        try:
            try:
                self._note_mutation()
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
        count = int(shapes.Count)
        if count > MAX_NAME_SCAN:
            return None
        for i in range(1, count + 1):
            shape = self._collection_item(shapes, i)
            if self._same_com_object(shape, target, strict=True):
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

    @tracked_mutation
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

    @tracked_mutation
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
            self._note_mutation()
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
                            with self._in_inches(doc):
                                created_shape.Outline.Width = ow / 72.0

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

    def inspect_repeat_unit(
        self,
        source_group_name: str,
        dieline_name: str,
        cutting_method: str = "unknown",
        allow_180_rotation: bool | None = None,
        curve_precision: int = 5,
    ) -> dict[str, Any]:
        """Inspect one grouped repeat and route rectangular or contour imposition."""
        if not isinstance(source_group_name, str) or not source_group_name.strip():
            raise CorelBridgeError("source_group_name must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)
        if not isinstance(dieline_name, str) or not dieline_name.strip():
            raise CorelBridgeError("dieline_name must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)
        if isinstance(curve_precision, bool) or not isinstance(curve_precision, int) or not 1 <= curve_precision <= 10:
            raise CorelBridgeError("curve_precision must be an integer from 1 to 10.", ErrorCode.INVALID_ARGUMENT)
        doc = self._target_document()
        source = self._find_shape(doc, object_name=source_group_name)
        if _safe_int_attr(source, "Type") != self.adapter.CDR_GROUP_SHAPE:
            raise CorelBridgeError(
                "The source repeat must be one top-level group containing its artwork and dieline.",
                ErrorCode.INVALID_ARGUMENT,
            )
        source_signature = self._repeat_source_signature(doc, source, dieline_name, curve_precision)
        normalized = source_signature["contour_points_inches"]
        contour_width = float(source_signature["contour_bounds_inches"]["width"])
        contour_height = float(source_signature["contour_bounds_inches"]["height"])
        contour_area = abs(sum(
            normalized[index][0] * normalized[(index + 1) % len(normalized)][1]
            - normalized[(index + 1) % len(normalized)][0] * normalized[index][1]
            for index in range(len(normalized))
        )) / 2.0
        rectangularity = contour_area / (contour_width * contour_height) if contour_width > 0 and contour_height > 0 else 0.0
        footprint_kind = "rectangular" if rectangularity >= 0.995 else "contour"
        group_bounds = source_signature["source_group_bounds_inches"]
        group_width = float(group_bounds.get("width") or 0.0)
        group_height = float(group_bounds.get("height") or 0.0)
        possible_combined = (
            contour_width > 0 and group_width > contour_width * 1.5
        ) or (
            contour_height > 0 and group_height > contour_height * 1.5
        )
        rotation = float(source_signature["source_rotation_degrees"])
        classification = classify_imposition_job(
            footprint_kind,
            True,
            cutting_method,
            allow_180_rotation,
            possible_combined,
        )
        if abs(rotation % 360.0) > 0.001:
            classification["blocking_issues"].append({
                "code": "SOURCE_ALREADY_ROTATED",
                "message": "Reset the source repeat group to 0 degrees before deterministic nesting.",
            })
            classification["ready"] = False
        return {
            "source_group_name": source_group_name,
            "dieline_name": dieline_name,
            "source_group": source_signature["source_group"],
            "source_identity": source_signature,
            "source_group_bounds_inches": group_bounds,
            "footprint_kind": footprint_kind,
            "rectangularity": round(rectangularity, 6),
            "possible_combined_source": possible_combined,
            "contour_width_inches": round(contour_width, 6),
            "contour_height_inches": round(contour_height, 6),
            "contour_points_inches": normalized,
            "curve_precision": curve_precision,
            **classification,
        }

    def _execute_vector_imposition_plan(
        self,
        source: Any,
        dieline_name: str,
        plan: dict[str, Any],
        copies: int,
        curve_precision: int,
        object_name_prefix: str,
        output_layer_name: str,
    ) -> dict[str, Any]:
        """Copy one repeat to a new page, place independent groups, and verify source preservation."""
        doc = self._target_document()
        if not isinstance(object_name_prefix, str) or not object_name_prefix.strip():
            raise CorelBridgeError("object_name_prefix must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)
        if not isinstance(output_layer_name, str) or not output_layer_name.strip():
            raise CorelBridgeError("output_layer_name must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)
        placements = list(plan.get("placements", []))[:copies]
        if len(placements) != copies:
            raise CorelBridgeError(
                "The approved plan does not contain every requested placement coordinate.",
                ErrorCode.INVALID_ARGUMENT,
                {"requested_copies": copies, "available_placements": len(placements)},
            )
        if int(plan.get("sheets_required", 0)) != 1:
            raise CorelBridgeError(
                "This execution slice supports one output sheet; multi-sheet execution is not implemented yet.",
                ErrorCode.INVALID_ARGUMENT,
                {"sheets_required": plan.get("sheets_required")},
            )

        source_page = _safe_attr(source, "Page")
        if source_page is None:
            source_page = _safe_attr(doc, "ActivePage")
        source_before = self._repeat_source_signature(doc, source, dieline_name, curve_precision)
        pages = _safe_attr(doc, "Pages")
        baseline_page_count = _safe_int_attr(pages, "Count") if pages is not None else None
        if baseline_page_count is None:
            raise CorelBridgeError("Could not read the target document page count.", ErrorCode.COREL_COM_ERROR)

        output_page: Any | None = None
        output_layer: Any | None = None
        command_group_open = False
        clipboard_modified = False
        created: list[dict[str, Any]] = []
        actual_contours: list[list[list[float]]] = []
        try:
            self._note_mutation()
            doc.BeginCommandGroup("AI Prepare Imposition Job")
            command_group_open = True
            with self._in_inches(doc), self._reference_point(doc, self.CDR_BOTTOM_LEFT):
                doc.AddPagesEx(
                    1,
                    float(plan["sheet_width_inches"]),
                    float(plan["sheet_height_inches"]),
                )
                actual_page_count = int(doc.Pages.Count)
                if actual_page_count != baseline_page_count + 1:
                    raise CorelBridgeError(
                        "CorelDRAW did not create exactly one output page.",
                        ErrorCode.COREL_COM_ERROR,
                        {"before": baseline_page_count, "after": actual_page_count},
                    )
                output_page = self._page_at(doc, actual_page_count)
                output_page.Activate()
                output_page.SetSize(float(plan["sheet_width_inches"]), float(plan["sheet_height_inches"]))
                output_layer = output_page.CreateLayer(output_layer_name.strip())
                source_page.Activate()
                source.Copy()
                clipboard_modified = True
                output_page.Activate()
                output_layer.Activate()
                copied_source = output_layer.Paste()
                if copied_source is None:
                    layer_shapes = _safe_attr(output_layer, "Shapes")
                    layer_count = _safe_int_attr(layer_shapes, "Count") if layer_shapes is not None else None
                    if not layer_count:
                        raise CorelBridgeError(
                            "CorelDRAW did not return or expose the copied source group.",
                            ErrorCode.COREL_COM_ERROR,
                        )
                    copied_source = self._collection_item(layer_shapes, layer_count)
                if _safe_int_attr(copied_source, "Type") != self.adapter.CDR_GROUP_SHAPE:
                    raise CorelBridgeError(
                        "The output copy is not an independent top-level group.",
                        ErrorCode.COREL_COM_ERROR,
                    )

                groups = [copied_source]
                for _ in range(2, copies + 1):
                    groups.append(copied_source.Duplicate(0.0, 0.0))
                for index, group in enumerate(groups, start=1):
                    group.Name = f"{object_name_prefix.strip()}_{index:03d}"

                for index, (group, placement) in enumerate(zip(groups, placements), start=1):
                    rotation = int(placement["rotation_degrees"])
                    if rotation:
                        group.Rotate(float(rotation))
                    contours = self._named_descendants(group, dieline_name)
                    if len(contours) != 1:
                        raise CorelBridgeError(
                            "A copied repeat group did not retain exactly one dieline.",
                            ErrorCode.COREL_COM_ERROR,
                        )
                    before = self._curve_polygon_points_inches(doc, contours[0], curve_precision)
                    minimum_x = min(point[0] for point in before)
                    minimum_y = min(point[1] for point in before)
                    offset_x = float(placement["x_inches"]) - minimum_x
                    offset_y = float(placement["y_inches"]) - minimum_y
                    group.SetPosition(float(group.PositionX) + offset_x, float(group.PositionY) + offset_y)
                    after = self._curve_polygon_points_inches(doc, contours[0], curve_precision)
                    actual_contours.append(after)
                    actual_rotation = float(_safe_float_attr(group, "RotationAngle") or 0.0) % 360.0
                    if abs(actual_rotation - rotation) > 0.001:
                        raise CorelBridgeError(
                            "CorelDRAW rotation readback differs from the imposition plan.",
                            ErrorCode.COREL_COM_ERROR,
                            {"planned_rotation": rotation, "actual_rotation": actual_rotation},
                        )
                    contour_bounds = {
                        "x": round(min(point[0] for point in after), 6),
                        "y": round(min(point[1] for point in after), 6),
                        "width": round(max(point[0] for point in after) - min(point[0] for point in after), 6),
                        "height": round(max(point[1] for point in after) - min(point[1] for point in after), 6),
                    }
                    expected_width = float(placement.get("width_inches", plan["footprint_width_inches"]))
                    expected_height = float(placement.get("height_inches", plan["footprint_height_inches"]))
                    if (
                        abs(contour_bounds["x"] - float(placement["x_inches"])) > 0.001
                        or abs(contour_bounds["y"] - float(placement["y_inches"])) > 0.001
                        or abs(contour_bounds["width"] - expected_width) > 0.001
                        or abs(contour_bounds["height"] - expected_height) > 0.001
                    ):
                        raise CorelBridgeError(
                            "CorelDRAW contour readback differs from the planned placement.",
                            ErrorCode.COREL_COM_ERROR,
                            {"planned": placement, "actual_contour_bounds": contour_bounds},
                        )
                    edge_allowance = float(plan["margin_inches"]) + float(plan["bleed_inches"])
                    if (
                        contour_bounds["x"] < edge_allowance - 0.001
                        or contour_bounds["y"] < edge_allowance - 0.001
                        or contour_bounds["x"] + contour_bounds["width"] > float(plan["sheet_width_inches"]) - edge_allowance + 0.001
                        or contour_bounds["y"] + contour_bounds["height"] > float(plan["sheet_height_inches"]) - edge_allowance + 0.001
                    ):
                        raise CorelBridgeError(
                            "A placed dieline falls outside the planned printable contour area.",
                            ErrorCode.COREL_COM_ERROR,
                            {"actual_contour_bounds": contour_bounds, "edge_allowance_inches": edge_allowance},
                        )
                    created.append({
                        "copy": placement.get("copy", placement.get("index", index)),
                        "object_name": str(group.Name),
                        "object": self._shape_identity(group),
                        "rotation_degrees": rotation,
                        "actual_rotation_degrees": round(actual_rotation, 6),
                        "group_bounds_inches": self._shape_bounds_inches(doc, group),
                        "contour_bounds_inches": contour_bounds,
                    })

                if contours_have_conflicts(actual_contours, float(plan["effective_contour_clearance_inches"])):
                    raise CorelBridgeError(
                        "Post-placement contour verification detected an overlap or insufficient clearance.",
                        ErrorCode.COREL_COM_ERROR,
                    )
                if int(self._shapes(doc).Count) != copies:
                    raise CorelBridgeError(
                        "The number of independent top-level repeat groups differs from the plan.",
                        ErrorCode.COREL_COM_ERROR,
                    )
                source_after = self._repeat_source_signature(doc, source, dieline_name, curve_precision)
                if source_after != source_before:
                    raise CorelBridgeError(
                        "The approved source changed during imposition execution.",
                        ErrorCode.COREL_COM_ERROR,
                    )
                output_dimensions = self._page_dimensions(output_page)
            doc.EndCommandGroup()
            command_group_open = False
        except Exception as exc:
            if command_group_open:
                try:
                    doc.EndCommandGroup()
                except Exception:
                    pass
            rollback_attempted = output_page is not None or int(doc.Pages.Count) > baseline_page_count
            if output_page is None and int(doc.Pages.Count) > baseline_page_count:
                try:
                    output_page = self._page_at(doc, baseline_page_count + 1)
                except Exception:
                    output_page = None
            if output_page is not None:
                try:
                    output_page.Delete()
                except Exception:
                    try:
                        doc.DeletePages(baseline_page_count + 1, 1)
                    except Exception:
                        pass
            try:
                source_page.Activate()
            except Exception:
                pass
            try:
                source_unchanged = self._repeat_source_signature(doc, source, dieline_name, curve_precision) == source_before
            except Exception:
                source_unchanged = False
            rollback_verified = int(doc.Pages.Count) == baseline_page_count and source_unchanged
            raise CorelBridgeError(
                "Imposition execution failed. "
                + ("The new output page was removed and the source was preserved." if rollback_verified else "Rollback could not be verified."),
                exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                {
                    "rollback_attempted": rollback_attempted,
                    "rollback_verified": rollback_verified,
                    "source_unchanged": source_unchanged,
                    "clipboard_modified": clipboard_modified,
                    "exception_type": type(exc).__name__,
                },
            ) from exc

        return {
            "prepared": True,
            "workflow": plan["workflow"],
            "created_count": len(created),
            "independent_repeat_groups": True,
            "objects": created,
            "output": {
                "mode": "new_page_same_document",
                "page_index": _safe_int_attr(output_page, "Index"),
                "page_name": _safe_string_attr(output_page, "Name"),
                "layer_name": _safe_string_attr(output_layer, "Name") or output_layer_name.strip(),
                "width_inches": output_dimensions.get("width_document_units"),
                "height_inches": output_dimensions.get("height_document_units"),
            },
            "source_identity": source_before,
            "source_preserved": True,
            "source_copy_method": "clipboard_copy_paste",
            "clipboard_modified": clipboard_modified,
            "warnings": ["CorelDRAW X7 cross-page copying replaced the current system clipboard contents."],
            "rollback_policy": "delete_new_output_page_only",
            "post_execution_verification": True,
        }

    @tracked_mutation
    def prepare_contour_nesting(
        self,
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
    ) -> dict[str, Any]:
        """Execute one source-preserving contour sheet for expert/low-level use."""
        inspection = self.inspect_repeat_unit(
            source_group_name, dieline_name, cutting_method, allow_180_rotation, curve_precision,
        )
        if not inspection["ready"] or inspection["workflow"] != "contour_nesting":
            raise CorelBridgeError(
                "The repeat unit is not ready for contour nesting.",
                ErrorCode.INVALID_ARGUMENT,
                {
                    "questions": inspection["questions"],
                    "blocking_issues": inspection["blocking_issues"],
                    "recommended_workflow": inspection["workflow"],
                },
            )
        plan = plan_contour_nesting(
            inspection["contour_points_inches"],
            sheet_width_inches,
            sheet_height_inches,
            quantity=copies,
            margin_inches=margin_inches,
            gutter_inches=gutter_inches,
            bleed_inches=bleed_inches,
            cutting_method=cutting_method,
            allow_180_rotation=allow_180_rotation,
            sheet_orientation=sheet_orientation,
        )
        if not plan["ready"] or plan["copies_per_sheet"] < copies:
            raise CorelBridgeError(
                "The requested repeat count does not fit one nested sheet.",
                ErrorCode.INVALID_ARGUMENT,
                {
                    "copies": copies,
                    "copies_per_sheet": plan.get("copies_per_sheet", 0),
                    "sheets_required": plan.get("sheets_required", 0),
                },
            )
        doc = self._target_document()
        source = self._find_shape(doc, object_name=source_group_name)
        result = self._execute_vector_imposition_plan(
            source,
            dieline_name,
            plan,
            copies,
            curve_precision,
            object_name_prefix,
            output_layer_name,
        )
        result["plan"] = plan
        return result

    @tracked_mutation
    def prepare_imposition_job(
        self,
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
    ) -> dict[str, Any]:
        """Inspect, route, plan, approve, and optionally execute one vector imposition sheet."""
        if not isinstance(confirm_execution, bool):
            raise CorelBridgeError("confirm_execution must be a boolean.", ErrorCode.INVALID_ARGUMENT)
        if not isinstance(approved_plan_fingerprint, str):
            raise CorelBridgeError("approved_plan_fingerprint must be a string.", ErrorCode.INVALID_ARGUMENT)
        if not isinstance(object_name_prefix, str) or not object_name_prefix.strip():
            raise CorelBridgeError("object_name_prefix must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)
        if not isinstance(output_layer_name, str) or not output_layer_name.strip():
            raise CorelBridgeError("output_layer_name must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)
        object_name_prefix = object_name_prefix.strip()
        output_layer_name = output_layer_name.strip()

        inspection_rotation = allow_180_rotation
        if allow_180_rotation is None and cutting_method in {"digital_cutter", "die_cut"}:
            inspection_rotation = False
        inspection = self.inspect_repeat_unit(
            source_group_name,
            dieline_name,
            cutting_method,
            inspection_rotation,
            curve_precision,
        )
        questions = list(inspection["questions"])
        blocking_issues = list(inspection["blocking_issues"])
        warnings: list[str] = []
        common = {
            "workflow": inspection["workflow"],
            "questions": questions,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "plan_fingerprint": "",
            "ready_for_execution": False,
            "source_identity": inspection["source_identity"],
            "source_preservation": {
                "output_mode": "new_page_same_document",
                "source_will_be_moved_or_renamed": False,
                "source_copy_method": "clipboard_copy_paste",
                "clipboard_will_be_modified": True,
                "rollback_policy": "delete_new_output_page_only",
            },
            "print_ready": False,
        }
        if questions:
            return {"status": "needs_input", **common}
        if blocking_issues:
            return {"status": "failed", **common}

        effective_rotation = bool(allow_180_rotation)
        if inspection["workflow"] == "contour_nesting" and allow_180_rotation is None:
            upright = plan_imposition_layout(
                inspection["contour_points_inches"],
                inspection["footprint_kind"],
                inspection["workflow"],
                sheet_width_inches,
                sheet_height_inches,
                quantity,
                margin_inches,
                gutter_inches,
                bleed_inches,
                cutting_method,
                False,
                sheet_orientation,
            )
            rotated = plan_imposition_layout(
                inspection["contour_points_inches"],
                inspection["footprint_kind"],
                inspection["workflow"],
                sheet_width_inches,
                sheet_height_inches,
                quantity,
                margin_inches,
                gutter_inches,
                bleed_inches,
                cutting_method,
                True,
                sheet_orientation,
            )
            if int(rotated["copies_per_sheet"]) > int(upright["copies_per_sheet"]):
                common["questions"] = [{
                    "id": "allow_180_rotation",
                    "question": "May complete repeat units rotate 180 degrees, considering grain and design direction?",
                    "options": [True, False],
                    "required": True,
                    "impact": {
                        "upright_copies_per_sheet": upright["copies_per_sheet"],
                        "rotated_copies_per_sheet": rotated["copies_per_sheet"],
                    },
                }]
                return {"status": "needs_input", **common}
            plan = upright
            warnings.append("A 180-degree rotation decision was not requested because it does not improve sheet capacity.")
        else:
            plan = plan_imposition_layout(
                inspection["contour_points_inches"],
                inspection["footprint_kind"],
                inspection["workflow"],
                sheet_width_inches,
                sheet_height_inches,
                quantity,
                margin_inches,
                gutter_inches,
                bleed_inches,
                cutting_method,
                effective_rotation,
                sheet_orientation,
            )

        if not plan["ready"]:
            blocking_issues.append({
                "code": "NO_LAYOUT_FITS",
                "message": "The repeat contour does not fit within the requested sheet and allowances.",
            })
        if int(plan.get("sheets_required", 0)) > 1:
            blocking_issues.append({
                "code": "MULTI_SHEET_EXECUTION_NOT_IMPLEMENTED",
                "message": "The layout is valid, but this slice executes only jobs that fit one output sheet.",
            })
        if quantity > len(plan.get("placements", [])):
            blocking_issues.append({
                "code": "PLACEMENT_COORDINATES_UNAVAILABLE",
                "message": "The bounded planner did not materialize every requested placement coordinate.",
            })
        warnings.append("Production marks, controlled export, and output-profile checks are not implemented; print_ready remains false.")
        warnings.append("Execution will replace current system clipboard contents during the X7 cross-page copy.")

        fingerprint_payload = {
            "schema": "imposition-plan-v1",
            "source_identity": inspection["source_identity"],
            "production": {
                "quantity": quantity,
                "cutting_method": cutting_method,
                "allow_180_rotation": effective_rotation,
                "curve_precision": curve_precision,
            },
            "output_policy": {
                "mode": "new_page_same_document",
                "object_name_prefix": object_name_prefix,
                "output_layer_name": output_layer_name,
                "source_copy_method": "clipboard_copy_paste",
                "clipboard_modified": True,
            },
            "layout": plan,
        }
        fingerprint = imposition_plan_fingerprint(fingerprint_payload)
        common.update({
            "workflow": plan["workflow"],
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "plan_fingerprint": fingerprint,
            "ready_for_execution": bool(plan["ready"] and not blocking_issues),
            "plan": plan,
        })
        if not confirm_execution:
            return {"status": "planned" if plan["ready"] else "failed", **common}
        if blocking_issues or not plan["ready"]:
            raise CorelBridgeError(
                "The imposition plan has blocking issues and cannot be executed.",
                ErrorCode.INVALID_ARGUMENT,
                {"blocking_issues": blocking_issues},
            )
        if not approved_plan_fingerprint or approved_plan_fingerprint != fingerprint:
            raise CorelBridgeError(
                "Execution requires the exact fingerprint returned by the current approved plan.",
                ErrorCode.CONFIRMATION_REQUIRED,
                {
                    "approved_plan_fingerprint": approved_plan_fingerprint or None,
                    "current_plan_fingerprint": fingerprint,
                },
            )

        doc = self._target_document()
        source = self._find_shape(doc, object_name=source_group_name)
        execution = self._execute_vector_imposition_plan(
            source,
            dieline_name,
            plan,
            quantity,
            curve_precision,
            object_name_prefix,
            output_layer_name,
        )
        if execution["clipboard_modified"]:
            common["warnings"] = [
                warning for warning in common["warnings"]
                if not warning.startswith("Execution will replace current system clipboard")
            ]
            for warning in execution["warnings"]:
                if warning not in common["warnings"]:
                    common["warnings"].append(warning)
        return {
            "status": "completed",
            **common,
            "ready_for_execution": False,
            "execution": execution,
            "source_preserved": execution["source_preserved"],
        }

    @tracked_mutation
    def prepare_print_job(
        self,
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
    ) -> dict[str, Any]:
        """Create a new one-sheet document and place validated raster copies."""
        plan = plan_print_job(
            file_path,
            finished_width_inches,
            finished_height_inches,
            sheet_width_inches,
            sheet_height_inches,
            copies=copies,
            bleed_inches=bleed_inches,
            safe_margin_inches=safe_margin_inches,
            margin_inches=margin_inches,
            gutter_inches=gutter_inches,
            minimum_dpi=minimum_dpi,
            artwork_includes_bleed=artwork_includes_bleed,
            fit_mode=fit_mode,
            allow_low_resolution=allow_low_resolution,
            rotation_policy=rotation_policy,
            sheet_orientation=sheet_orientation,
            margin_left_inches=margin_left_inches,
            margin_top_inches=margin_top_inches,
            margin_right_inches=margin_right_inches,
            margin_bottom_inches=margin_bottom_inches,
            gripper_inches=gripper_inches,
            gripper_edge=gripper_edge,
            mark_clearance_inches=mark_clearance_inches,
        )
        if not plan["ready_for_execution"]:
            raise CorelBridgeError(
                "Print job failed preflight; no CorelDRAW document was created.",
                ErrorCode.INVALID_ARGUMENT,
                {"blocking_issues": plan["preflight"]["blocking_issues"]},
            )
        if not isinstance(object_name_prefix, str) or not object_name_prefix.strip():
            raise CorelBridgeError("object_name_prefix must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)

        job = plan["job"]
        document_result = self.create_document(
            width_in=float(job["sheet_size_inches"]["width"]),
            height_in=float(job["sheet_size_inches"]["height"]),
        )
        doc = self._target_document()
        baseline_count = int(self._shapes(doc).Count)
        command_group_open = False
        created_objects: list[dict[str, Any]] = []
        try:
            self._note_mutation()
            doc.BeginCommandGroup("AI Prepare Print Job")
            command_group_open = True
            first_name = f"{object_name_prefix.strip()}_001"
            with materialize_placement_artwork(file_path, plan) as placement_file:
                imported = self.import_artwork(placement_file, first_name)
                if imported["object_count"] != 1:
                    raise CorelBridgeError(
                        "The general print-job workflow requires artwork that imports as exactly one object.",
                        ErrorCode.INVALID_ARGUMENT,
                        {"imported_object_count": imported["object_count"]},
                    )
                source = self._find_shape(doc, object_name=imported["object_names"][0])

                with self._in_inches(doc), self._reference_point(doc, self.CDR_BOTTOM_LEFT):
                    # Duplicate the pristine import before rotating any copy. Otherwise an
                    # all-rotated layout would duplicate an already-rotated source.
                    shapes = [source]
                    for index in range(2, len(plan["placements"]) + 1):
                        shape = source.Duplicate(0.0, 0.0)
                        self._name_shape(doc, shape, f"{object_name_prefix.strip()}_{index:03d}", "Print_Artwork")
                        shapes.append(shape)
                    for index, (shape, placement) in enumerate(zip(shapes, plan["placements"]), start=1):
                        box = placement["artwork_box"]
                        rotation = int(placement.get("rotation_degrees", 0))
                        if rotation:
                            shape.SizeWidth = float(box["height_inches"])
                            shape.SizeHeight = float(box["width_inches"])
                            shape.Rotate(float(rotation))
                        else:
                            shape.SizeWidth = float(box["width_inches"])
                            shape.SizeHeight = float(box["height_inches"])
                        shape.SetPosition(float(box["x_inches"]), float(box["y_inches"]))
                        created_objects.append({
                            "copy": index,
                            "object_name": str(_safe_attr(shape, "Name") or ""),
                            "object": self._shape_identity(shape),
                            "actual_bounds_inches": self._shape_bounds_inches(doc, shape),
                            "placement_box": placement["placement_box"],
                            "trim_box": placement["trim_box"],
                            "safe_box": placement["safe_box"],
                            "rotation_degrees": rotation,
                        })

            doc.EndCommandGroup()
            command_group_open = False
        except Exception as exc:
            if command_group_open:
                try:
                    doc.EndCommandGroup()
                except Exception:
                    pass
            rollback_verified = False
            try:
                doc.Undo()
                rollback_verified = int(self._shapes(doc).Count) == baseline_count
            except Exception:
                rollback_verified = False
            raise CorelBridgeError(
                "Print-job placement failed. "
                + ("Created objects were rolled back." if rollback_verified else "Rollback could not be verified."),
                exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                {"rollback_verified": rollback_verified, "exception_type": type(exc).__name__},
            ) from exc

        discrepancies: list[str] = []
        actual_page_size = document_result["actual_page_size_inches"]
        for axis in ("width", "height"):
            actual = actual_page_size.get(axis)
            expected = float(job["sheet_size_inches"][axis])
            if actual is None or abs(float(actual) - expected) > 0.001:
                discrepancies.append(f"Actual page {axis} {actual!r} differs from planned {expected:.6f} inches.")
        for created, placement in zip(created_objects, plan["placements"]):
            actual_bounds = created["actual_bounds_inches"]
            expected_box = placement["artwork_box"]
            for actual_key, expected_key in (
                ("x", "x_inches"),
                ("y", "y_inches"),
                ("width", "width_inches"),
                ("height", "height_inches"),
            ):
                actual = actual_bounds.get(actual_key)
                expected = float(expected_box[expected_key])
                if actual is None or abs(float(actual) - expected) > 0.001:
                    discrepancies.append(
                        f"{created['object_name']!r} {actual_key} {actual!r} differs from planned {expected:.6f} inches."
                    )

        return {
            "prepared": True,
            "print_ready": False,
            "document_name": self._safe_target_name(),
            "actual_page_size_inches": actual_page_size,
            "created_count": len(created_objects),
            "objects": created_objects,
            "plan": plan,
            "discrepancies": discrepancies,
            "post_execution_verification": len(created_objects) == copies and not discrepancies,
            "next_steps": [
                "Inspect the placed objects and trim boxes visually before saving or exporting.",
                "Use a unique CDR path to preserve the editable production file.",
                "Current PDF export settings are not yet controlled by this workflow; do not label the PDF print-ready without external verification.",
            ],
        }

    @tracked_mutation
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
            self._note_mutation()
            doc.SaveAs(path, options)
            if not os.path.isfile(path):
                raise CorelBridgeError("CorelDRAW returned from SaveAs, but the file was not created: " + path)
            return {"saved": True, "path": path, "bytes": os.path.getsize(path),
                    "document_name": self._safe_target_name()}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError("CorelDRAW X7 could not save the target document. Full COM error: " + str(exc)) from exc

    @tracked_mutation
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
            self._note_mutation()
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
