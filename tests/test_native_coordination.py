import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.native_coordination import NativeCoordinator
from corel_operator.native_tracking import tracked_mutation
from corel_operator.results import success_result
from corel_operator.worker_state import failure_recovery_reason
from jsonschema import Draft202012Validator
from test_worker_recovery import probe


class NativeCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.coordinator = NativeCoordinator(self.root)

    def uncertain(self):
        with self.assertRaises(RuntimeError):
            with self.coordinator.operation('edit_text_range'):
                self.coordinator.mark_write()
                raise RuntimeError('private content')
        return self.coordinator.snapshot()['fingerprint']

    def child(self, source):
        return subprocess.run([sys.executable, '-c', source, str(self.root)],
                              capture_output=True, text=True, timeout=10)

    def test_independent_process_is_refused_until_operation_returns(self):
        source = ('import sys; from corel_operator.native_coordination import NativeCoordinator; '
                  'c=NativeCoordinator(sys.argv[1]);\n'
                  'try:\n with c.operation("child"): pass\n'
                  'except Exception as e: print(e.code.value)\n')
        with self.coordinator.operation('parent'):
            blocked = self.child(source)
            self.assertEqual(blocked.returncode, 0, blocked.stderr)
            self.assertEqual(blocked.stdout.strip(), 'WORKER_BUSY')
        ready = self.child(source)
        self.assertEqual(ready.returncode, 0, ready.stderr)
        self.assertEqual(ready.stdout, '')

    def test_abrupt_process_exit_keeps_durable_uncertainty(self):
        result = self.child('import sys,os; from corel_operator.native_coordination import NativeCoordinator; '
                            'c=NativeCoordinator(sys.argv[1]); g=c.operation("crashed"); '
                            'g.__enter__(); os._exit(0)')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.coordinator.snapshot()['recovery_required'])
        with self.assertRaises(CorelBridgeError) as caught:
            with self.coordinator.operation('edit'): self.fail('must not enter')
        self.assertEqual(caught.exception.code, ErrorCode.RECOVERY_REQUIRED)

    def test_partial_failure_blocks_an_independent_client(self):
        self.uncertain()
        other = NativeCoordinator(self.root)
        with self.assertRaises(CorelBridgeError):
            with other.operation('edit'): self.fail('must not enter')
        self.assertNotIn('private', json.dumps(other.snapshot()))

    def test_failure_before_write_does_not_quarantine(self):
        with self.assertRaises(RuntimeError):
            with self.coordinator.operation('preflight'): raise RuntimeError()
        self.assertFalse(self.coordinator.snapshot()['recovery_required'])

    def test_verified_rollback_does_not_quarantine(self):
        with self.assertRaises(CorelBridgeError):
            with self.coordinator.operation('edit'):
                self.coordinator.mark_write()
                raise CorelBridgeError('rolled back', details={'rollback_verified': True})
        self.assertFalse(self.coordinator.snapshot()['recovery_required'])

    def test_reentrant_commands_share_one_lease(self):
        with self.coordinator.operation('outer'):
            before = self.coordinator.snapshot()
            with self.coordinator.operation('nested'):
                self.assertEqual(self.coordinator.snapshot(), before)
                with self.assertRaises(CorelBridgeError):
                    with NativeCoordinator(self.root).operation('other'): pass
        self.assertFalse(self.coordinator.snapshot()['recovery_required'])

    def test_other_thread_cannot_reenter(self):
        observed = []
        def run():
            try:
                with self.coordinator.operation('other'): pass
            except CorelBridgeError as error:
                observed.append(error.code)
        with self.coordinator.operation('outer'):
            thread = threading.Thread(target=run)
            thread.start(); thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(observed, [ErrorCode.WORKER_BUSY])

    def test_pure_read_preserves_recovery_and_temporary_setter_is_refused(self):
        token = self.uncertain()
        with self.coordinator.operation('inspect', allow_recovery=True):
            with self.assertRaises(CorelBridgeError): self.coordinator.mark_write()
        self.assertEqual(self.coordinator.snapshot()['fingerprint'], token)

    def test_reconciliation_requires_exact_fingerprint(self):
        token = self.uncertain()
        with self.coordinator.operation('reconcile', allow_recovery=True):
            with self.assertRaises(CorelBridgeError): self.coordinator.resolve('0' * 64)
        self.assertEqual(self.coordinator.snapshot()['fingerprint'], token)

    def test_reconciliation_requires_ack_and_bound_probe(self):
        token = self.uncertain()
        bridge = CorelBridge(native_coordinator=self.coordinator)
        with patch.object(bridge, 'reconcile_document_state', return_value=probe()):
            with self.assertRaises(CorelBridgeError): bridge.reconcile_native_coordination(token)
            result = bridge.reconcile_native_coordination(token, True)
        self.assertTrue(result['reconciled'])
        self.assertFalse(self.coordinator.snapshot()['recovery_required'])

    def test_unbound_or_invalid_probe_does_not_clear_marker(self):
        token = self.uncertain()
        bridge = CorelBridge(native_coordinator=self.coordinator)
        for value in ({}, dict(probe(), connected=False)):
            with patch.object(bridge, 'reconcile_document_state', return_value=value):
                with self.assertRaises(CorelBridgeError): bridge.reconcile_native_coordination(token, True)
            self.assertEqual(self.coordinator.snapshot()['fingerprint'], token)

    def test_reconciliation_refused_while_other_process_is_running(self):
        with self.coordinator.operation('parent'):
            result = self.child('import sys; from corel_operator.corel_bridge import CorelBridge; '
                                'from corel_operator.native_coordination import NativeCoordinator; '
                                'b=CorelBridge(native_coordinator=NativeCoordinator(sys.argv[1]));\n'
                                'try: b.reconcile_native_coordination("0"*64,True)\n'
                                'except Exception as e: print(e.code.value)')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'WORKER_BUSY')

    def test_malformed_or_oversized_state_is_preserved(self):
        for content in ('{}', 'x' * 4097):
            (self.root / 'state.json').write_text(content)
            with self.assertRaises(CorelBridgeError):
                with self.coordinator.operation('edit'): pass
            self.assertEqual((self.root / 'state.json').read_text(), content)

    def test_late_persistence_failure_leaves_running_marker(self):
        from corel_operator.native_coordination import os as native_os
        original = native_os.replace
        calls = []
        def replace(*args):
            calls.append(args)
            if len(calls) == 2:
                raise OSError('private path')
            return original(*args)
        with self.assertRaises(CorelBridgeError):
            with patch('corel_operator.native_coordination.os.replace', side_effect=replace):
                with self.coordinator.operation('edit'):
                    self.coordinator.mark_write()
        self.assertTrue(self.coordinator.snapshot()['recovery_required'])
        self.assertEqual(self.coordinator.snapshot()['state']['phase'], 'running')
        with self.coordinator.operation('inspect', allow_recovery=True): pass

    def test_embedded_commands_cannot_bypass_shared_lease(self):
        bridge = CorelBridge(native_coordinator=NativeCoordinator(self.root))
        with self.coordinator.operation('other'):
            with patch.object(bridge, '_require_app') as connect:
                with self.assertRaises(CorelBridgeError) as caught: bridge.create_document()
                connect.assert_not_called()
        self.assertEqual(caught.exception.code, ErrorCode.WORKER_BUSY)
        self.assertIsNone(failure_recovery_reason(caught.exception, True, bridge._operation_mutation_started))

    def test_snapshot_can_be_read_without_waiting_for_lease(self):
        bridge = CorelBridge(native_coordinator=NativeCoordinator(self.root))
        with self.coordinator.operation('running'):
            self.assertEqual(bridge.get_native_coordination_state()['state']['phase'], 'running')

    def test_subclass_mutation_preserves_outer_write_marker(self):
        class Embedded(CorelBridge):
            @tracked_mutation
            def custom_edit(self):
                self._note_mutation()
                self.set_text_content('')  # Nested preflight refusal after a write.
        bridge = Embedded(native_coordinator=self.coordinator)
        bridge.configure_editing_mode('exclusive', True)
        with self.assertRaises(CorelBridgeError): bridge.custom_edit()
        self.assertTrue(bridge._operation_mutation_started)
        self.assertTrue(self.coordinator.snapshot()['recovery_required'])

    def test_actual_results_match_catalog_schemas(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text())
        bridge = CorelBridge(native_coordinator=self.coordinator)
        snapshot = bridge.get_native_coordination_state()
        token = self.uncertain()
        with patch.object(bridge, 'reconcile_document_state', return_value=probe()):
            reconciled = bridge.reconcile_native_coordination(token, True)
        for name, data in [('get_native_coordination_state', snapshot), ('reconcile_native_coordination', reconciled)]:
            tool = next(t for t in registry['tools'] if t['name'] == name)
            schema = dict(tool['output_schema'], schema_definitions=registry['schema_definitions'])
            Draft202012Validator(schema).validate(success_result(name, data, 0))
