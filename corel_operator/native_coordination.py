"""Nonblocking, per-user exclusion and durable uncertainty across native clients.

This coordinates cooperating bridge processes, not CorelDRAW's human interface.
The byte-range lease is held until the native operation actually returns.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from .errors import CorelBridgeError, ErrorCode
from .worker_state import READ_ONLY_METHODS, failure_recovery_reason


def fingerprint(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class NativeCoordinator:
    def __init__(self, directory=None):
        if directory is None:
            base = os.environ.get('LOCALAPPDATA') if os.name == 'nt' else os.environ.get('XDG_STATE_HOME')
            base = Path(base) if base else Path.home() / '.local' / 'state'
            directory = base / 'CorelDRAW-AI-Operator' / 'native-v1'
        self.directory = Path(directory)
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._state = None
        self._write_started = False
        self._recovery = None

    def _read(self):
        path = self.directory / 'state.json'
        try:
            with path.open('rb') as source:
                raw = source.read(4097)
            if len(raw) > 4096:
                raise ValueError()
            state = json.loads(raw)
            if (type(state) is not dict or set(state) != {'schema', 'phase', 'operation_id', 'method', 'pid'}
                    or state['schema'] != 1 or state['phase'] not in ('idle', 'running', 'recovery_required')
                    or type(state['operation_id']) is not str or len(state['operation_id']) != 32
                    or any(c not in '0123456789abcdef' for c in state['operation_id'])
                    or type(state['method']) is not str or not 1 <= len(state['method']) <= 100
                    or type(state['pid']) is not int or state['pid'] <= 0):
                raise ValueError()
            return state
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, UnicodeError):
            raise CorelBridgeError('Shared native state cannot be verified. Preserve it for recovery.',
                                   ErrorCode.RECOVERY_REQUIRED) from None

    def _persist(self, state):
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix='state-', suffix='.tmp', dir=self.directory)
            with os.fdopen(fd, 'w', encoding='utf-8') as target:
                json.dump(state, target, sort_keys=True)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.directory / 'state.json')
        except OSError:
            raise CorelBridgeError('Shared native state could not be saved; keep native editing paused for recovery.',
                                   ErrorCode.RECOVERY_REQUIRED) from None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def snapshot(self):
        state = self._read()
        return {'state': state, 'fingerprint': fingerprint(state),
                'recovery_required': state is not None and state['phase'] != 'idle',
                'human_input_locked': False}

    def mark_write(self):
        if self._depth:
            if self._recovery is not None:
                raise CorelBridgeError('Native writes are blocked by unresolved shared recovery.', ErrorCode.RECOVERY_REQUIRED)
            self._write_started = True

    def resolve(self, expected_fingerprint):
        if not self._depth or self._recovery is None:
            raise CorelBridgeError('There is no shared recovery marker to acknowledge.', ErrorCode.INVALID_ARGUMENT)
        if fingerprint(self._recovery) != expected_fingerprint:
            raise CorelBridgeError('Shared recovery state changed; inspect it again.', ErrorCode.RECOVERY_REQUIRED)
        self._recovery = None

    @contextmanager
    def operation(self, method, allow_recovery=False):
        if not self._thread_lock.acquire(blocking=False):
            raise CorelBridgeError('Another native operation is running in this client.', ErrorCode.WORKER_BUSY)
        lease = None
        acquired = False
        entered = False
        error = None
        try:
            if self._depth:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            lease = (self.directory / 'lease.lock').open('a+b')
            lease.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                raise CorelBridgeError('Another CorelDRAW bridge client is using native operations. Try after it finishes.',
                                       ErrorCode.WORKER_BUSY) from None
            if os.fstat(lease.fileno()).st_size == 0:
                lease.write(b'0')
                lease.flush()
            prior = self._read()
            self._recovery = prior if prior is not None and prior['phase'] != 'idle' else None
            if self._recovery is not None and not allow_recovery:
                raise CorelBridgeError('A previous native operation is uncertain. Inspect and reconcile shared native state.',
                                       ErrorCode.RECOVERY_REQUIRED)
            self._state = {'schema': 1, 'phase': 'running', 'operation_id': uuid.uuid4().hex,
                           'method': method, 'pid': os.getpid()}
            if self._recovery is None:
                self._persist(self._state)
            self._depth = 1
            self._write_started = False
            entered = True
            try:
                yield
            except BaseException as exc:
                error = exc
                raise
        except CorelBridgeError:
            raise
        except OSError:
            raise CorelBridgeError('Shared native coordination failed; inspect local recovery state.',
                                   ErrorCode.RECOVERY_REQUIRED) from None
        finally:
            try:
                if entered:
                    self._depth = 0
                    state = self._recovery or dict(self._state, phase=(
                        'recovery_required' if error is not None and self._write_started
                        and failure_recovery_reason(error, True, True) is not None else 'idle'))
                    self._persist(state)
            finally:
                if lease is not None:
                    if acquired:
                        lease.seek(0)
                        if os.name == 'nt':
                            import msvcrt
                            msvcrt.locking(lease.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(lease.fileno(), fcntl.LOCK_UN)
                    lease.close()
                self._thread_lock.release()


def coordinated_operation(function):
    @wraps(function)
    def wrapper(self, *args, **kwargs):
        if not self._native_coordinator._depth and not self._mutation_depth:
            self._operation_mutation_started = False
        with self._native_coordinator.operation(function.__name__, allow_recovery=(
                function.__name__ in READ_ONLY_METHODS or function.__name__ in
                ('use_active_document', 'reconcile_document_state'))):
            return function(self, *args, **kwargs)
    return wrapper
