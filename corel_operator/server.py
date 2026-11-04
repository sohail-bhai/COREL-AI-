"""MCP stdio server for CorelDRAW X7; COM actions run on one dedicated thread."""
from __future__ import annotations
import copy
import math
import queue
import threading
import uuid
from concurrent.futures import Future
from collections import OrderedDict
from datetime import datetime, timezone
from functools import wraps
from time import perf_counter
from typing import Any
from mcp.server.fastmcp import FastMCP
from .corel_bridge import CorelBridge
from .errors import CorelBridgeError, ErrorCode
from .results import error_result, success_result
from .operation_records import (
    OperationJournal, RecordedOperation, current_operation, input_summary,
    exception_code, result_metadata, target_ids,
)
from .worker_state import (
    DispatchJob, MAX_OPERATION_HISTORY, READ_ONLY_METHODS, failure_recovery_reason,
    native_busy, validate_operation_id, validate_recovery_probe,
)
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
operation_journal = OperationJournal.from_environment()


def recorded_operation(function):
    """Preserve MCP signatures and correlate caller/worker events without content."""
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not operation_journal.enabled:
            return function(*args, **kwargs)
        operation = RecordedOperation(uuid.uuid4().hex, function.__name__, operation_journal)
        token = current_operation.set(operation)
        started = perf_counter()
        try:
            operation.journal.write(operation.operation_id, operation.tool, "requested", input_summary=input_summary(args, kwargs))
            result = function(*args, **kwargs)
            metadata = result_metadata(result.get("data")) if result.get("ok") else {"result_code": (result.get("error") or {}).get("code")}
            operation.journal.write(operation.operation_id, operation.tool, "returned", duration_ms=(perf_counter() - started) * 1000, **metadata)
            result["operation_id"] = operation.operation_id
            if not operation.journal.available:
                result["warnings"].append("Operation recording could not persist all events.")
            return result
        except BaseException as exc:
            operation.journal.write(operation.operation_id, operation.tool, "returned", duration_ms=(perf_counter() - started) * 1000, **result_metadata(error=exc))
            raise
        finally:
            current_operation.reset(token)
    return wrapper


class CorelDispatcher:
    def __init__(self, call_timeout_seconds: float = 120.0) -> None:
        if type(call_timeout_seconds) not in (int, float) or not math.isfinite(call_timeout_seconds) or not 0 < call_timeout_seconds <= 120:
            raise CorelBridgeError("Worker timeout must be positive and at most 120 seconds.", ErrorCode.INVALID_ARGUMENT)
        self.call_timeout_seconds = float(call_timeout_seconds)
        self._jobs: queue.Queue[Any] = queue.Queue(maxsize=32)
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._startup_error: str | None = None
        self._closing = False
        self._stop_requested = False
        self._active_job: DispatchJob | None = None
        self._recovery: dict | None = None
        self._history: OrderedDict[str, dict] = OrderedDict()
        self._thread = threading.Thread(target=self._worker, name="CorelDRAW-COM-STA", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise RuntimeError("CorelDRAW COM worker did not initialize within 15 seconds.")
        if self._startup_error:
            raise RuntimeError(self._startup_error)

    @staticmethod
    def _job_metadata(job: DispatchJob, status: str, summary: dict | None = None) -> dict:
        return {
            "operation_id": job.operation_id, "method": job.method, "status": status,
            "mutation": job.mutation, "timed_out": job.timed_out,
            "submitted_at_utc": job.submitted_utc,
            "duration_ms": round(max(0., (perf_counter() - job.submitted) * 1000), 3),
            "reconciliation": job.reconciliation,
            "recovery_operation_id": job.recovery_operation_id, "summary": summary,
        }

    def _remember(self, job: DispatchJob, status: str, summary: dict):
        self._history[job.operation_id] = self._job_metadata(job, status, summary)
        while len(self._history) > MAX_OPERATION_HISTORY:
            pinned = self._recovery["operation_id"] if self._recovery is not None else None
            oldest = next(key for key in self._history if key != pinned)
            self._history.pop(oldest)

    def snapshot(self) -> dict:
        """Return bounded Python metadata immediately, including while native work is blocked."""
        with self._lock:
            alive = self._thread.is_alive() and self._startup_error is None
            job = self._active_job
            state = "unavailable" if not alive or self._closing else (
                "timed_out_but_running" if job is not None and job.timed_out else
                "running" if job is not None else "idle"
            )
            active = None if job is None else self._job_metadata(job, "timed_out_but_running" if job.timed_out else "running" if job.started else "pending")
            return copy.deepcopy({
                "state": state, "worker_alive": alive, "closing": self._closing,
                "accepting_mutations": state == "idle" and self._recovery is None and not self._jobs.full(),
                "recovery_required": self._recovery is not None, "recovery": self._recovery,
                "active_operation": active,
                "last_operation": next(reversed(self._history.values()), None),
                "retained_operations": len(self._history), "call_timeout_seconds": self.call_timeout_seconds,
            })

    def operation_status(self, operation_id: str) -> dict:
        validate_operation_id(operation_id)
        with self._lock:
            if self._active_job is not None and self._active_job.operation_id == operation_id:
                return self.snapshot()["active_operation"]
            result = self._history.get(operation_id)
            if result is None:
                raise CorelBridgeError("No current or retained operation matches this ID.", ErrorCode.OBJECT_NOT_FOUND)
            return copy.deepcopy(result)

    def _check_available(self):
        if self._closing or not self._thread.is_alive() or self._startup_error:
            raise CorelBridgeError("CorelDRAW COM worker is not running or is closing.", ErrorCode.WORKER_UNAVAILABLE)
        if self._active_job is not None:
            raise CorelBridgeError(
                "CorelDRAW is executing another operation. Inspect get_operator_state before retrying.",
                ErrorCode.WORKER_BUSY,
                {"active_operation_id": self._active_job.operation_id,
                 "timed_out": self._active_job.timed_out},
            )

    def _submit(self, method_name: str, args: tuple, kwargs: dict, reconciliation=False,
                recovery_operation_id=None, acknowledge_partial_changes=False):
        mutation = method_name not in READ_ONLY_METHODS and not reconciliation
        with self._lock:
            self._check_available()
            if reconciliation:
                if self._recovery is None or self._recovery["operation_id"] != recovery_operation_id:
                    raise CorelBridgeError("Recovery operation ID no longer matches the blocked state.", ErrorCode.RECOVERY_REQUIRED)
            elif mutation and self._recovery is not None:
                raise CorelBridgeError(
                    "Mutation is blocked until the completed operation is reconciled.", ErrorCode.RECOVERY_REQUIRED,
                    {"recovery_operation_id": self._recovery["operation_id"], "reason": self._recovery["reason"]},
                )
            record = current_operation.get()
            job = DispatchJob(
                record.operation_id if record is not None else uuid.uuid4().hex,
                method_name, args, kwargs, Future(), record, mutation, perf_counter(),
                datetime.now(timezone.utc).isoformat(), reconciliation=reconciliation,
                recovery_operation_id=recovery_operation_id,
                acknowledge_partial_changes=acknowledge_partial_changes,
            )
            self._active_job = job
            try:
                self._jobs.put_nowait(job)
            except queue.Full as exc:
                self._active_job = None
                raise CorelBridgeError("Worker queue capacity is exhausted.", ErrorCode.WORKER_BUSY) from exc
        try:
            return job.future.result(timeout=self.call_timeout_seconds)
        except TimeoutError:
            with self._lock:
                if job.future.done():
                    # A native TimeoutError is an actual completed exception, not a wait timeout.
                    return job.future.result(timeout=0)
                job.timed_out = True
                cancelled = job.future.cancel()
                if cancelled:
                    self._remember(job, "cancelled", {"result_code": ErrorCode.OPERATION_TIMEOUT.value})
                    if self._active_job is job:
                        self._active_job = None
                elif mutation and self._recovery is None:
                    self._recovery = {"operation_id": job.operation_id, "reason": "mutation_timed_out", "requires_partial_ack": False}
                raise CorelBridgeError(
                    "The caller timed out; inspect get_operator_state before continuing. Running COM work is not cancelled.",
                    ErrorCode.OPERATION_TIMEOUT,
                    {"operation_id": job.operation_id, "cancelled_before_execution": cancelled,
                     "mutation": mutation, "recovery_required": self._recovery is not None},
                ) from None

    def call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        return self._submit(method_name, args, kwargs)

    def reconcile(self, operation_id: str, acknowledge_partial_changes: bool = False) -> dict:
        validate_operation_id(operation_id)
        if type(acknowledge_partial_changes) is not bool:
            raise CorelBridgeError("acknowledge_partial_changes must be a boolean.", ErrorCode.INVALID_ARGUMENT)
        return self._submit("reconcile_document_state", (), {}, reconciliation=True,
                            recovery_operation_id=operation_id, acknowledge_partial_changes=acknowledge_partial_changes)

    def _reconcile_on_worker(self, job: DispatchJob) -> dict:
        probe = self._bridge.reconcile_document_state()
        validate_recovery_probe(probe)
        with self._lock:
            if self._recovery is None or self._recovery["operation_id"] != job.recovery_operation_id:
                raise CorelBridgeError("Recovery state changed; inspect get_operator_state again.", ErrorCode.RECOVERY_REQUIRED)
            if self._recovery["requires_partial_ack"] and not job.acknowledge_partial_changes:
                raise CorelBridgeError(
                    "Partial changes may remain. Inspect the target and explicitly acknowledge them before recovery.",
                    ErrorCode.CONFIRMATION_REQUIRED,
                    {"recovery_operation_id": job.recovery_operation_id, "document_state": probe},
                )
            previous = copy.deepcopy(self._history.get(job.recovery_operation_id))
            self._recovery = None
            return {"reconciled": True, "recovery_operation_id": job.recovery_operation_id,
                    "document_state": probe, "previous_operation": previous}

    def _complete(self, job: DispatchJob, result=None, error=None):
        with self._lock:
            summary = result_metadata(result, error)
            summary["native_busy"] = error is not None and native_busy(error)
            if error is not None and not job.reconciliation:
                mutation_started = getattr(self._bridge, "_operation_mutation_started", None)
                reason = failure_recovery_reason(error, job.mutation, mutation_started)
                if reason is not None and (self._recovery is None or self._recovery["operation_id"] == job.operation_id):
                    self._recovery = {"operation_id": job.operation_id, "reason": reason,
                                      "requires_partial_ack": job.mutation and mutation_started is not False}
            if job.timed_out and job.mutation and self._recovery is None:
                self._recovery = {"operation_id": job.operation_id, "reason": "mutation_timed_out", "requires_partial_ack": False}
            self._remember(job, "failed" if error is not None else "completed", summary)
            if error is None:
                job.future.set_result(result)
            else:
                try:
                    error.operator_operation_id = job.operation_id
                except Exception:
                    pass
                job.future.set_exception(error)
            if self._active_job is job:
                self._active_job = None

    def _worker(self) -> None:
        pythoncom = None
        try:
            import pythoncom as _pythoncom  # type: ignore
            pythoncom = _pythoncom
            pythoncom.CoInitialize()
            self._bridge = CorelBridge()
        except Exception:
            self._startup_error = "Could not initialize the dedicated Windows COM worker. Check pywin32."
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    break
                with self._lock:
                    running = job.future.set_running_or_notify_cancel()
                    if running:
                        job.started = True
                if not running:
                    if job.record is not None:
                        job.record.journal.write(job.operation_id, job.record.tool, "worker_cancelled")
                    continue
                started = perf_counter()
                self._bridge._operation_mutation_started = None
                if job.record is not None:
                    job.record.journal.write(job.operation_id, job.record.tool, "worker_started", target_ids=target_ids(self._bridge))
                try:
                    result = self._reconcile_on_worker(job) if job.reconciliation else getattr(self._bridge, job.method)(*job.args, **job.kwargs)
                    if job.record is not None:
                        job.record.journal.write(job.operation_id, job.record.tool, "worker_completed", target_ids=target_ids(self._bridge), duration_ms=(perf_counter() - started) * 1000, **result_metadata(result))
                except BaseException as exc:
                    if job.record is not None:
                        job.record.journal.write(job.operation_id, job.record.tool, "worker_failed", target_ids=target_ids(self._bridge), duration_ms=(perf_counter() - started) * 1000, **result_metadata(error=exc))
                    self._complete(job, error=exc)
                else:
                    self._complete(job, result=result)
        finally:
            # Native proxies belong to this STA and must be released before uninitializing it.
            self._bridge = None
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def close(self, timeout: float = 5.0) -> None:
        with self._lock:
            if not self._thread.is_alive():
                self._closing = True
                return
            self._closing = True
            if not self._stop_requested:
                try:
                    self._jobs.put_nowait(None)
                except queue.Full as exc:
                    raise RuntimeError("CorelDRAW worker stop queue is full; retry shutdown after native work finishes.") from exc
                self._stop_requested = True
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise RuntimeError("CorelDRAW COM worker did not stop within the timeout; native work may continue.")


dispatcher = CorelDispatcher()


def _tool(tool_name: str, method: str, *args: Any, **kwargs: Any) -> dict:
    started = perf_counter()
    try:
        data = dispatcher.call(method, *args, **kwargs)
        return success_result(tool_name, data, (perf_counter() - started) * 1000)
    except Exception as exc:
        return _operator_error(tool_name, exc, started)


def _operator_error(tool_name: str, exc: BaseException, started: float) -> dict:
    result = error_result(tool_name, exc, (perf_counter() - started) * 1000)
    operation_id = getattr(exc, "operator_operation_id", None)
    if operation_id is None and isinstance(exc, CorelBridgeError):
        operation_id = exc.details.get("operation_id")
    if operation_id is not None:
        try:
            validate_operation_id(operation_id)
            result["operation_id"] = operation_id
        except CorelBridgeError:
            pass
    snapshot = getattr(dispatcher, "snapshot", None)
    if callable(snapshot):
        state = snapshot()
        result["error"]["details"]["worker_state"] = state["state"]
        result["error"]["details"]["recovery_required"] = state["recovery_required"]
        if state["recovery"] is not None:
            result["error"]["details"]["recovery_operation_id"] = state["recovery"]["operation_id"]
    return result


@mcp.tool()
@recorded_operation
def get_operator_state() -> dict:
    """Read worker/recovery state immediately without connecting to or calling CorelDRAW."""
    started = perf_counter()
    try:
        return success_result("get_operator_state", dispatcher.snapshot(), (perf_counter() - started) * 1000)
    except Exception as exc:
        return error_result("get_operator_state", exc, (perf_counter() - started) * 1000)


@mcp.tool()
@recorded_operation
def get_operation_status(operation_id: str) -> dict:
    """Read a current or retained operation's bounded outcome; never retry it or access artwork."""
    started = perf_counter()
    try:
        return success_result("get_operation_status", dispatcher.operation_status(operation_id), (perf_counter() - started) * 1000)
    except Exception as exc:
        return error_result("get_operation_status", exc, (perf_counter() - started) * 1000)


@mcp.tool()
@recorded_operation
def reconcile_operator_state(operation_id: str, acknowledge_partial_changes: bool = False) -> dict:
    """Recheck finite target state after native work stops, using the exact recovery operation ID.

    Failed mutations require inspecting and explicitly acknowledging any partial
    changes. This does not undo or repeat the operation, rebind, or reconnect.
    """
    started = perf_counter()
    try:
        return success_result("reconcile_operator_state", dispatcher.reconcile(operation_id, acknowledge_partial_changes), (perf_counter() - started) * 1000)
    except Exception as exc:
        return _operator_error("reconcile_operator_state", exc, started)


@mcp.tool()
@recorded_operation
def corel_status() -> dict:
    """Report CorelDRAW version, active document and protected target document. This does not edit anything."""
    return _tool("corel_status", "status")


@mcp.tool()
@recorded_operation
def list_open_documents() -> dict:
    """List open CorelDRAW documents without activating, selecting, or binding any of them."""
    return _tool("list_open_documents", "list_open_documents")


@mcp.tool()
@recorded_operation
def get_document_info() -> dict:
    """Inspect identity, path, dirty state, units, and active page for the bound target document."""
    return _tool("get_document_info", "get_document_info")


@mcp.tool()
@recorded_operation
def list_pages() -> dict:
    """List pages and their actual dimensions for the bound target document without changing the active page."""
    return _tool("list_pages", "list_pages")


@mcp.tool()
@recorded_operation
def get_page_bounds(page_index: int) -> dict:
    """Return page-local bottom-left bounds in inches for one page of the bound target document."""
    return _tool("get_page_bounds", "get_page_bounds", page_index)


@mcp.tool()
@recorded_operation
def list_layers(page_index: int) -> dict:
    """List page and master layers with state and object counts without changing the active layer."""
    return _tool("list_layers", "list_layers", page_index)


@mcp.tool()
@recorded_operation
def get_object_info(object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Inspect one object selected unambiguously by name, index, or issued object_reference."""
    return _tool("get_object_info", "get_object_info", object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def get_object_bounds(object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Read object bounds in inches relative to the document ruler's bottom-left reference.

    Supply one unique active-page name, index, or object_reference. References also inspect nested objects on other pages.
    Targets the explicitly bound document and restores units/reference point.
    """
    return _tool("get_object_bounds", "get_object_bounds", object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def get_object_transform(object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Read actual native affine matrix, rotation, bounds in inches and raw stacking index.

    Supply one unique active-page name, index, or signed object_reference. Reference
    inspection can read other pages without activation. Units/reference point are restored.
    """
    return _tool("get_object_transform", "get_object_transform", object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def rotate_object(
    angle_degrees: float, relative: bool = True,
    center_x_inches: float | None = None, center_y_inches: float | None = None,
    object_name: str = "", shape_index: int = 0, object_reference: dict | None = None,
) -> dict:
    """Rotate one object by a relative angle or to an absolute orientation.

    Default pivot is its measured bounds center; supply both center coordinates
    to rotate around another point in document ruler inches. Returns actual
    transform/bounds. Signed reference edits require the referenced page active.
    """
    return _tool("rotate_object", "rotate_object", angle_degrees, relative, center_x_inches,
                 center_y_inches, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def flip_object(axis: str, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Mirror one object horizontally, vertically or on both axes; return its actual matrix and bounds.

    axis: horizontal/vertical/both. Degenerate matrices are refused. Select by
    unique active-page name, index, or signed object_reference on the active page.
    """
    return _tool("flip_object", "flip_object", axis, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def order_object(position: str, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Move one object to front/back or forward_one/back_one within its immediate sibling stack.

    Verify native sibling relations and membership after editing. Select by unique
    active-page name, index, or signed object_reference on the active page.
    """
    return _tool("order_object", "order_object", position, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def distribute_objects(
    axis: str, object_names: list[str] | None = None, object_references: list[dict] | None = None,
    mode: str = "equal_gaps", spacing_inches: float | None = None, allow_overlap: bool = False,
) -> dict:
    """Distribute 3-100 independent objects along horizontal/vertical using measured geometry.

    Supply one list of unique names or signed references on the active page.
    equal_gaps preserves the outer extent unless spacing_inches is supplied;
    equal_centers preserves the first/last centers. Objects sort by current
    position. Orthogonal positions/sizes stay fixed. Overlaps require explicit
    allow_overlap. Partial native failures require worker reconciliation.
    """
    return _tool("distribute_objects", "distribute_objects", axis, object_names,
                 object_references, mode, spacing_inches, allow_overlap)


@mcp.tool()
@recorded_operation
def inspect_text_template(object_name: str="",shape_index: int=0,object_reference: dict | None=None) -> dict:
    """Capture a bounded grouped template and its named editable text fields.

    Supply one name/index/signed reference. Returns a source fingerprint and
    ordinary JSON; linked/fitted stories are refused. Native verification is pending.
    """
    return _tool("inspect_text_template","inspect_text_template",object_name,shape_index,object_reference)


@mcp.tool()
@recorded_operation
def get_bitmap_properties(minimum_dpi: float = 150., object_name: str = "", shape_index: int = 0,
                          object_reference: dict | None = None) -> dict:
    """Inspect native bitmap metadata and calculate its placed affine pixel DPI.

    Reconcile the uncropped pixel-grid box with bounds and native affine axes,
    including rotation/skew. Report worst directional resolution against a
    requested minimum. Unknown/effect/crop geometry stays indeterminate; metadata
    or calculated DPI alone never establishes source detail or print readiness.
    """
    return _tool("get_bitmap_properties", "get_bitmap_properties", minimum_dpi, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def get_document_structure() -> dict:
    """Inspect bounded page/local/master-layer structure and root membership.

    Return session identities, inches, native flags, active context and a current
    fingerprint. Use that fingerprint for every page/layer organization change.
    """
    return _tool("get_document_structure", "get_document_structure")


@mcp.tool()
@recorded_operation
def activate_page(page_identity: str, expected_fingerprint: str) -> dict:
    """Activate an exact inspected page and verify all other recorded structure."""
    return _tool("activate_page", "activate_page", page_identity, expected_fingerprint)


@mcp.tool()
@recorded_operation
def activate_layer(page_identity: str, layer_identity: str, expected_fingerprint: str) -> dict:
    """Activate an exact visible/editable ordinary local layer for later creation."""
    return _tool("activate_layer", "activate_layer", page_identity, layer_identity, expected_fingerprint)


@mcp.tool()
@recorded_operation
def rename_page(page_identity: str, name: str, expected_fingerprint: str) -> dict:
    """Rename an inspected page with a current structure fingerprint."""
    return _tool("rename_page", "rename_page", page_identity, name, expected_fingerprint)


@mcp.tool()
@recorded_operation
def create_page(name: str, width_inches: float, height_inches: float, expected_fingerprint: str) -> dict:
    """Append one named page with explicit size and restore the active context.

    Verify existing structure and root membership. Failed creation discards only
    an owned empty new page; unknown or populated receipts require recovery.
    """
    return _tool("create_page", "create_page", name, width_inches, height_inches, expected_fingerprint)


@mcp.tool()
@recorded_operation
def create_layer(page_identity: str, name: str, expected_fingerprint: str) -> dict:
    """Create one ordinary local layer and restore the prior page/layer context."""
    return _tool("create_layer", "create_layer", page_identity, name, expected_fingerprint)


@mcp.tool()
@recorded_operation
def set_layer_properties(page_identity: str, layer_identity: str, properties: dict, expected_fingerprint: str) -> dict:
    """Change an ordinary local layer's name/visible/editable/printable fields.

    Use exact inspected identities and a current fingerprint. Master/special
    layers are deferred; failed or partial writes require explicit recovery.
    """
    return _tool("set_layer_properties", "set_layer_properties", page_identity, layer_identity, properties, expected_fingerprint)


@mcp.tool()
@recorded_operation
def create_contour_offsets(object_reference: dict, offset_inches: float, direction: str = "outside", steps: int = 1,
                           color: dict | None = None, corner_type: str = "round", miter_limit: float = 0.,
                           result_name_prefix: str = "AI_Contour") -> dict:
    """Create independent editable inside/outside contours from a closed vector.

    Copy the source, apply 1-32 native steps, reconcile distance/corner controls and
    separate into owned ordinary curves. Output is an opaque process fill without
    an outline. Return measured curves and signed refs; cutting accuracy remains
    unverified. Known empty inside results are explicit. Cleanup refuses foreign trees.
    """
    return _tool("create_contour_offsets", "create_contour_offsets", object_reference, offset_inches, direction,
                 steps, color, corner_type, miter_limit, result_name_prefix)


@mcp.tool()
@recorded_operation
def get_gradient_fill(object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Inspect up to 32 native gradient stops, parameters and coordinates.

    Report missing metadata explicitly. Complete inspection returns a current-session
    fingerprint for revisions. Native opacity values are raw; rendering is unverified.
    """
    return _tool("get_gradient_fill", "get_gradient_fill", object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def set_gradient_fill(stops: list[dict], gradient_type: str = "linear", angle_degrees: float = 0., steps: int = 0,
                      edge_padding_percent: int = 0, center_offset_x_percent: float = 0., center_offset_y_percent: float = 0.,
                      replace_existing: bool = False, expected_fingerprint: str = "",
                      object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Apply opaque direct gradients to individual vector/text objects.

    Supply 2-32 strictly ordered integer-percent RGB or CMYK stops including 0/100.
    Choose linear/radial/conical/square, angle, steps, padding and center offsets.
    Existing gradient revisions require the current fingerprint. Replacing other
    non-uniform fills is explicit. Verify native state/geometry and quarantine failures.
    """
    return _tool("set_gradient_fill", "set_gradient_fill", stops, gradient_type, angle_degrees, steps,
                 edge_padding_percent, center_offset_x_percent, center_offset_y_percent, replace_existing,
                 expected_fingerprint, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def get_powerclip(object_name: str="",shape_index: int=0,object_reference: dict | None=None) -> dict:
    """Inspect bounded native PowerClip/group trees and a source-bound fingerprint.

    Includes measured geometry, editable text/body hashes and native bitmap metadata.
    Clipped descendants use identity metadata; extract copies for ordinary edit refs.
    Limits: 1000 shapes/32 levels; visual/pixel/effect fidelity remains unverified.
    """
    return _tool("get_powerclip","get_powerclip",object_name,shape_index,object_reference)


@mcp.tool()
@recorded_operation
def create_powerclip(frame_reference: dict,content_references: list[dict],fit_kind: str="none",padding_inches: float=0.,
    contents_locked: bool=True,replace_existing_contents: bool=False,result_name: str="") -> dict:
    """Create an independent editable PowerClip from exact same-layer root inputs.

    Preserve source frame and 1-64 content objects. Group copied content in source
    stacking order; choose none/contain/cover fitting, padding and lock behavior.
    Replacing copied old contents is explicit. Verify full measured geometry/tree
    ownership and discard only owned outputs on failure. No rasterization or clipboard.
    """
    return _tool("create_powerclip","create_powerclip",frame_reference,content_references,fit_kind,padding_inches,
        contents_locked,replace_existing_contents,result_name)


@mcp.tool()
@recorded_operation
def extract_powerclip_contents(frame_reference: dict,expected_fingerprint: str,result_name_prefix: str="AI_Extracted") -> dict:
    """Extract copied PowerClip content into independently editable root objects.

    Require current frame/content fingerprint, preserve complete measured source,
    reconcile native extraction identities/geometry and return signed editing refs.
    Native rendering/pixel/complex-effect fidelity remains deferred.
    """
    return _tool("extract_powerclip_contents","extract_powerclip_contents",frame_reference,expected_fingerprint,result_name_prefix)


@mcp.tool()
@recorded_operation
def get_transparency(object_name: str="",shape_index: int=0,object_reference: dict | None=None) -> dict:
    """Inspect native transparency type, uniform percent, affected channel and merge mode.

    Unavailable properties are explicit. Non-uniform transparency internals and
    rendered appearance require separate inspection/manual review.
    """
    return _tool("get_transparency","get_transparency",object_name,shape_index,object_reference)


@mcp.tool()
@recorded_operation
def set_uniform_transparency(percent: int,applied_to: str="fill",replace_existing: bool=False,
    object_name: str="",shape_index: int=0,object_reference: dict | None=None) -> dict:
    """Set normal-mode uniform transparency 1-100 or remove the effect with 0.

    applied_to is fill, outline or both. Non-uniform replacement is explicit.
    Verify actual native state and measured geometry/base appearance. Partial
    failures quarantine. Bitmap pixel/visual fidelity remains deferred.
    """
    return _tool("set_uniform_transparency","set_uniform_transparency",percent,applied_to,replace_existing,
        object_name,shape_index,object_reference)


@mcp.tool()
@recorded_operation
def set_process_color(color: dict,channel: str="fill",replace_non_uniform: bool=False,
    object_name: str="",shape_index: int=0,object_reference: dict | None=None) -> dict:
    """Set exact native RGB/CMYK process fill or an existing ordinary outline color.

    color uses model=rgb and red/green/blue 0-255, or model=cmyk and cyan/magenta/
    yellow/black 0-100. Gradient/pattern replacement is explicit. Full component,
    other-channel and measured geometry/text readback gate success. No ICC/PDF-X proof.
    """
    return _tool("set_process_color","set_process_color",color,channel,replace_non_uniform,
        object_name,shape_index,object_reference)


@mcp.tool()
@recorded_operation
def create_vector_path(paths: list[dict],object_name: str="") -> dict:
    """Create editable inch-based line/cubic subpaths with complete native readback.

    Each path needs start{x,y}, segments, closed. Cubics include control1/control2;
    a missing closing line is explicit in normalized readback. Limits: 64 paths,
    1000 segments. Native appearance inherits defaults and remains unverified.
    """
    return _tool("create_vector_path","create_vector_path",paths,object_name)


@mcp.tool()
@recorded_operation
def revise_curve_topology(object_reference: dict,expected_fingerprint: str,insertions: list[dict] | None=None,
    deletions: list[dict] | None=None,result_name: str="") -> dict:
    """Insert/delete nodes on an independent source-preserving curve revision.

    Insertions use inspected subpath_index/segment_index and curve parameter t.
    Deletions use nonadjacent interior node_index and explicit line/cubic replacement
    controls. Indices refer to the fingerprinted source; revised nodes are cusp.
    Returns the full actual curve and retained/inserted node mapping. Limits: 200 edits.
    """
    return _tool("revise_curve_topology","revise_curve_topology",object_reference,expected_fingerprint,
        insertions,deletions,result_name)


@mcp.tool()
@recorded_operation
def get_curve_geometry(object_name: str="",shape_index: int=0,object_reference: dict | None=None) -> dict:
    """Inspect exact bounded nodes and line/cubic handles with a curve fingerprint.

    Native curves are editable; rectangles/ellipses/polygons use read-only display
    geometry. Returns all supported subpaths, native node types and inch coordinates.
    """
    return _tool("get_curve_geometry","get_curve_geometry",object_name,shape_index,object_reference)


@mcp.tool()
@recorded_operation
def edit_curve_geometry(expected_fingerprint: str,node_edits: list[dict] | None=None,handle_edits: list[dict] | None=None,
    convert_edited_nodes_to_cusp: bool=False,object_name: str="",shape_index: int=0,object_reference: dict | None=None) -> dict:
    """Move nodes and change cubic handles after complete fingerprinted preflight.

    Node edits use subpath_index/node_index/position and optional translate_handles.
    Handle edits use subpath_index/segment_index/control1/control2. Smooth constraints
    require compatible geometry or explicit cusp conversion. Partial failures quarantine.
    """
    return _tool("edit_curve_geometry","edit_curve_geometry",expected_fingerprint,node_edits,handle_edits,
        convert_edited_nodes_to_cusp,object_name,shape_index,object_reference)


@mcp.tool()
@recorded_operation
def boolean_shapes(operation: str,source_reference: dict,target_reference: dict,result_name: str="") -> dict:
    """Create source-preserving weld/trim/intersect derivatives from exact vector targets.

    Inputs must be closed supported geometry on the same page/layer. Trim subtracts
    source from target. Empty trim/intersection is explicit; owned copies are cleaned.
    """
    return _tool("boolean_shapes","boolean_shapes",operation,source_reference,target_reference,result_name)


@mcp.tool()
@recorded_operation
def combine_vector_shapes(object_references: list[dict],result_name: str="") -> dict:
    """Combine 2-64 exact vector inputs into one independent editable compound curve.

    Preserve sources, verify copied/combined subpath geometry and original order,
    clean owned temporary inputs and return actual signed output references.
    """
    return _tool("combine_vector_shapes","combine_vector_shapes",object_references,result_name)


@mcp.tool()
@recorded_operation
def break_apart_curve(object_reference: dict,result_name_prefix: str="AI_Subpath") -> dict:
    """Split a copied native compound curve into independent source-preserving outputs.

    Match actual native outputs to the original subpath geometry, reconcile counts,
    use deterministic names and discard only established owned copies on failure.
    """
    return _tool("break_apart_curve","break_apart_curve",object_reference,result_name_prefix)


@mcp.tool()
@recorded_operation
def inspect_raster_asset(source_path: str) -> dict:
    """Inspect a bounded local raster snapshot with EXIF-normalized pixel hashes.

    Return dimensions, mode, alpha, ICC/DPI metadata and a source fingerprint.
    Multi-frame and precision sources remain inspectable; preparation is refused.
    """
    from .raster_assets import inspect_raster_asset as inspect_file
    started = perf_counter()
    try:
        return success_result("inspect_raster_asset", inspect_file(source_path), (perf_counter()-started)*1000)
    except Exception as exc:
        return error_result("inspect_raster_asset", exc, (perf_counter()-started)*1000)


@mcp.tool()
@recorded_operation
def prepare_raster_asset(source_path: str, destination_path: str, expected_source_fingerprint: str,
                         crop_box: dict | None = None, rotation_degrees: int = 0,
                         flip_horizontal: bool = False, flip_vertical: bool = False,
                         target_size: dict | None = None, resize_mode: str = "contain",
                         allow_upscale: bool = False, resampling: str = "lanczos",
                         output_dpi: float | None = None) -> dict:
    """Create a new PNG/TIFF derivative with exact pixel and source readback.

    Normalize EXIF, crop, rotate counterclockwise, flip, then fit/resize. Preserve
    source bytes and recognized ICC/DPI; require explicit upscale, never overwrite.
    """
    from .raster_assets import prepare_raster_asset as prepare_file
    started = perf_counter()
    try:
        result = prepare_file(source_path, destination_path, expected_source_fingerprint, crop_box,
            rotation_degrees, flip_horizontal, flip_vertical, target_size, resize_mode, allow_upscale,
            resampling, output_dpi)
        return success_result("prepare_raster_asset", result, (perf_counter()-started)*1000)
    except Exception as exc:
        return error_result("prepare_raster_asset", exc, (perf_counter()-started)*1000)


@mcp.tool()
@recorded_operation
def inspect_pdf(path: str,expected_page_count: int | None=None,expected_page_sizes: list[dict] | None=None,
                require_embedded_fonts: bool=False,tolerance_inches: float=.01) -> dict:
    """Parse a local PDF and check all page sizes/counts and font program presence.

    Require an absolute .pdf path, at most 50 MiB, 500 pages and 10000 resource
    objects. Summaries cap at 100 pages/fonts. No rendering or print-ready claim.
    """
    from .pdf_inspection import inspect_pdf as inspect_file
    started=perf_counter()
    try:
        return success_result("inspect_pdf",inspect_file(path,expected_page_count,expected_page_sizes,
            require_embedded_fonts,tolerance_inches),(perf_counter()-started)*1000)
    except Exception as exc: return error_result("inspect_pdf",exc,(perf_counter()-started)*1000)


@mcp.tool()
@recorded_operation
def export_pdf_controlled(path: str,color_mode: str="native",pdf_version: str="1.4",text_as_curves: bool=False,
                          require_embedded_fonts: bool=True) -> dict:
    """Export all bound-document pages with explicit zero-bleed/font/color controls.

    Restore native PDF settings, inspect every page and font resource, then
    publish exclusively to a new path. X7 and manual review remain pending;
    ICC conversion, nonzero bleed and PDF/X are outside this contract.
    """
    result=_tool("export_pdf_controlled","export_pdf_controlled",path,color_mode,pdf_version,text_as_curves,require_embedded_fonts)
    if result.get("ok"): result["warnings"].extend(result["data"]["warnings"])
    return result


@mcp.tool()
@recorded_operation
def read_template_csv(csv_path: str,delimiter: str=",") -> dict:
    """Read literal UTF-8 CSV rows for templates; preserve leading zeros and quoted text.

    Require an absolute .csv path, unique headers and complete rows. Limits:
    2 MiB, 1000 records, 128 columns, 10000 characters per cell. No native call.
    """
    from .template_jobs import read_template_csv as read_csv
    started=perf_counter()
    try: return success_result("read_template_csv",read_csv(csv_path,delimiter),(perf_counter()-started)*1000)
    except Exception as exc: return error_result("read_template_csv",exc,(perf_counter()-started)*1000)


@mcp.tool()
@recorded_operation
def plan_template_batch(
    template: dict,field_mapping: dict,records: list[dict],field_regions: dict | None=None,
    sheet_width_inches: float=8.5,sheet_height_inches: float=11,margin_inches: float=.25,gutter_inches: float=.125,
    copies_per_record: int=1,record_key: str | None=None,duplicate_policy: str="reject",overflow_policy: str="reject",
) -> dict:
    """Validate data and plan independent template copies across full/partial output sheets.

    field_mapping maps data columns to unique template text names. Optional field
    regions are template-relative inch boxes. Duplicates require allow policy;
    overflow policy is reject/report. Return a complete fingerprinted plan without COM.
    """
    from .template_jobs import plan_template_batch as plan_batch
    started=perf_counter()
    try:
        data=plan_batch(template,field_mapping,records,field_regions,sheet_width_inches,sheet_height_inches,
                        margin_inches,gutter_inches,copies_per_record,record_key,duplicate_policy,overflow_policy)
        return success_result("plan_template_batch",data,(perf_counter()-started)*1000)
    except Exception as exc: return error_result("plan_template_batch",exc,(perf_counter()-started)*1000)


@mcp.tool()
@recorded_operation
def execute_template_batch(plan: dict,approved_fingerprint: str) -> dict:
    """Revalidate an approved template/data plan and create a separately owned editable document.

    Verify every row after all edits, measured source preservation, counts and
    field/item bounds. Failures discard only the owned output with verified
    cleanup; uncertain cleanup requires worker reconciliation. Replaces clipboard.
    """
    result=_tool("execute_template_batch","execute_template_batch",plan,approved_fingerprint)
    if result.get("ok"): result["warnings"].extend(result["data"]["warnings"])
    return result


@mcp.tool()
@recorded_operation
def get_text_properties(object_name: str = "", shape_index: int = 0, max_text_chars: int = 2000, object_reference: dict | None = None) -> dict:
    """Read bounded story content and aggregate formatting for one text shape.

    Supply one unique active-page name, index, or object_reference. References also inspect nested objects on other pages.
    max_text_chars is 0-10000; truncation and unavailable/indeterminate properties
    are explicit. Aggregate formatting does not describe individual text runs.
    """
    return _tool("get_text_properties", "get_text_properties", object_name, shape_index, max_text_chars, object_reference)


@mcp.tool()
@recorded_operation
def get_fill(object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Read fill type and uniform color in its original model without conversion.

    Supply one unique active-page name, index, or object_reference. References also inspect nested objects on other pages.
    Nonuniform fill internals are outside this inspection's detail scope.
    """
    return _tool("get_fill", "get_fill", object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def find_objects(
    name_contains: str = "", shape_type_code: int | None = None,
    text_contains: str = "", page_index: int | None = None,
    layer_name: str = "", max_results: int = 100, include_nested: bool = True,
    case_sensitive: bool = False, max_depth: int = 8, max_scan: int = 5000,
) -> dict:
    """Search the bound document by literal name/text, type, page, or layer; never select or edit.

    A null page_index searches all pages. Filters combine with AND. Layer names
    match exactly; name/text filters match substrings. Results retain duplicates
    and include group paths. Check truncated/incomplete_reasons before treating
    a search as complete. Returned IDs/paths are inspection data, not edit selectors.
    """
    return _tool(
        "find_objects", "find_objects", name_contains, shape_type_code,
        text_contains, page_index, layer_name, max_results, include_nested,
        case_sensitive, max_depth, max_scan,
    )


@mcp.tool()
@recorded_operation
def create_document(width_inches: float = 8.27, height_inches: float = 11.69) -> dict:
    """Create and bind a new target document. Subsequent edits/save target this document even if another window is activated."""
    return _tool("create_document", "create_document", width_inches, height_inches)


@mcp.tool()
@recorded_operation
def use_active_document(confirm_existing_document: bool = False) -> dict:
    """Explicitly bind the currently active document for editing. Set confirm_existing_document=True only after backing up client work."""
    return _tool("use_active_document", "use_active_document", confirm_existing_document)


@mcp.tool()
@recorded_operation
def list_fonts(name_contains: str = "", max_results: int = 100, max_scan: int = 5000) -> dict:
    """Inspect X7's font catalog using a case-insensitive literal filter.

    Limits: 1-1000 results, 1-10000 scanned entries. Check incomplete_reasons
    before concluding a font is absent. Catalog presence does not prove glyph coverage.
    """
    return _tool("list_fonts", "list_fonts", name_contains, max_results, max_scan)


@mcp.tool()
@recorded_operation
def add_paragraph_text(
    text: str, x_inches: float, y_inches: float, width_inches: float, height_inches: float,
    size_points: float = 12, font: str = "Arial", bold: bool = False, italic: bool = False,
    underline: str = "none", alignment: str = "left", object_name: str = "",
) -> dict:
    """Create editable paragraph text in an explicit frame in the bound document.

    x/y locate the frame's lower-left in document ruler inches; width/height are
    positive. Verify the font catalog before creating; return actual formatting,
    bounds, and native linked-story overflow. Text is limited to 100000 characters.
    """
    return _tool("add_paragraph_text", "add_paragraph_text", text, x_inches, y_inches,
                 width_inches, height_inches, size_points, font, bold, italic,
                 underline, alignment, object_name)


@mcp.tool()
@recorded_operation
def set_text_style(
    font: str | None = None, size_points: float | None = None,
    bold: bool | None = None, italic: bool | None = None,
    underline: str | None = None, alignment: str | None = None,
    object_name: str = "", shape_index: int = 0, object_reference: dict | None = None,
) -> dict:
    """Apply supplied formatting to one entire, unfitted, unlinked text story.

    Null properties are preserved. Select by unique active-page name, index, or
    signed object_reference on the active page. Underline: none/single; alignment:
    left/right/center/justify/force_justify. Returns before/actual styles and bounds.
    """
    return _tool("set_text_style", "set_text_style", font, size_points, bold, italic,
                 underline, alignment, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def add_text(text: str, x_inches: float, y_inches: float, size_points: float = 24,
             font: str = "Arial", bold: bool = False, object_name: str = "") -> dict:
    """Create editable artistic text in the target document. Names are used to edit objects later."""
    return _tool("add_text", "add_text", text, x_inches, y_inches, size_points, font, bold, object_name)


@mcp.tool()
@recorded_operation
def draw_rectangle(x_inches: float, y_inches: float, width_inches: float, height_inches: float,
                   object_name: str = "") -> dict:
    """Draw a rectangle in the target document; optionally assign a useful unique object_name."""
    return _tool("draw_rectangle", "draw_rectangle", x_inches, y_inches, width_inches, height_inches, object_name)


@mcp.tool()
@recorded_operation
def draw_ellipse(x_inches: float, y_inches: float, width_inches: float, height_inches: float,
                 object_name: str = "") -> dict:
    """Draw an ellipse in the target document; optionally assign a useful unique object_name."""
    return _tool("draw_ellipse", "draw_ellipse", x_inches, y_inches, width_inches, height_inches, object_name)


@mcp.tool()
@recorded_operation
def list_objects(max_objects: int = 200) -> dict:
    """List objects on the target page including object names, indexes, positions, sizes and text where available."""
    return _tool("list_objects", "list_objects", max_objects)


@mcp.tool()
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
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
@recorded_operation
def execute_design_plan(plan: dict, create_new_document: bool = False,
                        rollback_on_failure: bool = True) -> dict:
    """Execute a structured multi-element design plan transactionally with atomic rollback on failure."""
    return _tool(
        "execute_design_plan", "execute_design_plan",
        plan, create_new_document, rollback_on_failure,
    )


@mcp.tool()
@recorded_operation
def set_fill_color(red: int, green: int, blue: int, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Set an object's solid fill using RGB 0-255. Specify one selector: name, index, or object_reference. Reference edits require its page to be active."""
    return _tool("set_fill_color", "set_fill_color", red, green, blue, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def set_outline(red: int, green: int, blue: int, width_points: float = 1.0,
                object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Set an object's outline color/width in points. Use width_points=0 to remove outline. Reference edits require its page to be active."""
    return _tool("set_outline", "set_outline", red, green, blue, width_points, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def move_object(x_inches: float, y_inches: float, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Move an object so its bottom-left reference point is at x/y inches on the page. Reference edits require its page to be active."""
    return _tool("move_object", "move_object", x_inches, y_inches, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def resize_object(width_inches: float = 0, height_inches: float = 0, keep_aspect_ratio: bool = False,
                  object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Resize an object in inches. For proportional resizing, provide only one dimension and set keep_aspect_ratio=True. Reference edits require its page to be active."""
    return _tool("resize_object", "resize_object", width_inches, height_inches, keep_aspect_ratio, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def set_text_content(new_text: str, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Replace the text of an existing text object. Target must be artistic/paragraph text. Reference edits require its page to be active."""
    return _tool("set_text_content", "set_text_content", new_text, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def rename_object(new_name: str, object_name: str = "", shape_index: int = 0, object_reference: dict | None = None) -> dict:
    """Rename an object to make later natural-language edits more reliable. Supply exactly one current selector. Reference edits require its page to be active."""
    return _tool("rename_object", "rename_object", new_name, object_name, shape_index, object_reference)


@mcp.tool()
@recorded_operation
def duplicate_object(offset_x_inches: float = 0.25, offset_y_inches: float = -0.25,
                     object_name: str = "", shape_index: int = 0, new_name: str = "", object_reference: dict | None = None) -> dict:
    """Duplicate an object with an offset in inches. Supply exactly one source selector. Reference edits require its page to be active."""
    return _tool("duplicate_object", "duplicate_object", offset_x_inches, offset_y_inches, object_name, shape_index, new_name, object_reference)


@mcp.tool()
@recorded_operation
def import_artwork(file_path: str, object_name: str = "AI_Artwork") -> dict:
    """Import local PNG/JPG/BMP/TIFF/SVG/PDF/EPS/AI/WMF/EMF/CMX artwork. Then inspect and position it with list_objects/move_object/resize_object."""
    return _tool("import_artwork", "import_artwork", file_path, object_name)


@mcp.tool()
@recorded_operation
def save_document(path: str) -> dict:
    """Save the bound target document as a new CDR file. Refuses to overwrite existing files."""
    return _tool("save_document", "save_document", path)


@mcp.tool()
@recorded_operation
def export_pdf(path: str) -> dict:
    """Export the bound target document to a new PDF. Print settings need separate verification."""
    return _tool("export_pdf", "export_pdf", path)


@mcp.tool()
@recorded_operation
def align_objects(
    object_names: list[str],
    horizontal: str = "none",
    vertical: str = "none",
    align_to: str = "last_selected",
) -> dict:
    """Align two or more shapes relative to a reference target (last_selected or first_selected)."""
    return _tool("align_objects", "align_objects", object_names, horizontal, vertical, align_to)


@mcp.tool()
@recorded_operation
def align_to_page(
    object_names: list[str],
    horizontal: str = "none",
    vertical: str = "none",
    align_as_group: bool = False,
) -> dict:
    """Align one or more shapes to page edges or page center, individually or collectively as a group."""
    return _tool("align_to_page", "align_to_page", object_names, horizontal, vertical, align_as_group)


@mcp.tool()
@recorded_operation
def group_shapes(object_names: list[str], group_name: str = "") -> dict:
    """Group two or more shapes on the active page into a single named group shape."""
    return _tool("group_shapes", "group_shapes", object_names, group_name)


@mcp.tool()
@recorded_operation
def ungroup_shapes(
    object_name: str = "",
    shape_index: int = 0,
    ungroup_all: bool = False,
) -> dict:
    """Ungroup a group shape into individual shapes. Use ungroup_all=True to ungroup nested groups recursively."""
    return _tool("ungroup_shapes", "ungroup_shapes", object_name, shape_index, ungroup_all)


if __name__ == "__main__":
    mcp.run(transport="stdio")
