from __future__ import annotations

import copy
import json
import threading
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge, tracked_mutation
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.worker_state import MAX_OPERATION_HISTORY, READ_ONLY_METHODS, native_busy
from fake_documents import attach_open_document


def probe(count=0):
    return {'connected': True, 'target_bound': True, 'document_session_id': 'doc-0001',
            'open_document_count': 1, 'page_index': 1, 'page_object_count': count,
            'unit_code': 1, 'reference_point_code': 5, 'dirty': bool(count)}


class ControlledBridge:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.read_block = False
        self.probe_block = False
        self.error = None
        self.read_error = None
        self.probe_error = None
        self.probe_value = None
        self.preflight_refusal = False
        self.writes = 0
        self.reads = 0
        self.probes = 0
        self.native_threads = []

    def _wait(self, block):
        self.native_threads.append(threading.get_ident())
        if block:
            self.entered.set()
            if not self.release.wait(timeout=2):
                raise AssertionError('Controlled worker was not released')

    def add_text(self, *args):
        self._wait(self.block)
        if self.preflight_refusal and self.error is not None:
            self._operation_mutation_started = False
            raise self.error
        self._operation_mutation_started = True
        self.writes += 1
        if self.error is not None:
            raise self.error
        return {'created': True, 'object': {'static_id': self.writes}, 'text': 'private client secret'}

    def get_document_info(self):
        self._wait(self.read_block)
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        return {'document_name': 'private client', 'object_count': self.writes}

    def reconcile_document_state(self):
        self._wait(self.probe_block)
        self.probes += 1
        if self.probe_error is not None:
            raise self.probe_error
        return self.probe_value if self.probe_value is not None else probe(self.writes)


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.bridge = ControlledBridge()
        self.patcher = patch.object(server, 'CorelBridge', side_effect=lambda: self.bridge)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.dispatcher = server.CorelDispatcher(call_timeout_seconds=0.05)
        self.addCleanup(self.dispatcher.close)
        self.addCleanup(self.bridge.release.set)

    def wait_terminal(self):
        deadline = time.monotonic() + 2
        while self.dispatcher.snapshot()['active_operation'] is not None:
            if time.monotonic() >= deadline:
                self.fail('Worker did not reach a terminal state')
            time.sleep(0.002)
        return self.dispatcher.snapshot()

    def assert_error(self, code, callback):
        with self.assertRaises(CorelBridgeError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def fail_mutation(self, error=None):
        self.bridge.error = error or CorelBridgeError('private path token=secret', ErrorCode.COREL_COM_ERROR)
        self.assert_error(self.bridge.error.code, lambda: self.dispatcher.call('add_text', 'secret'))
        return self.dispatcher.snapshot()['recovery']['operation_id'] if self.dispatcher.snapshot()['recovery'] else None

    def timeout_mutation(self):
        self.bridge.block = True
        error = self.assert_error(ErrorCode.OPERATION_TIMEOUT, lambda: self.dispatcher.call('add_text', 'secret'))
        self.assertTrue(self.bridge.entered.is_set())
        return error.details['operation_id']

    def test_initial_and_closed_states_are_available_without_native_calls(self):
        state = self.dispatcher.snapshot()
        self.assertEqual(state['state'], 'idle')
        self.assertTrue(state['accepting_mutations'])
        self.assertEqual(self.bridge.native_threads, [])
        self.dispatcher.close()
        state = self.dispatcher.snapshot()
        self.assertEqual(state['state'], 'unavailable')
        self.assertFalse(state['accepting_mutations'])
        self.assert_error(ErrorCode.WORKER_UNAVAILABLE, lambda: self.dispatcher.call('add_text', 'secret'))

    def test_active_call_refuses_all_followup_com_calls_before_enqueue(self):
        self.dispatcher.call_timeout_seconds = 1.0
        self.bridge.block = True
        result = []
        caller = threading.Thread(target=lambda: result.append(self.dispatcher.call('add_text', 'secret')))
        caller.start()
        self.assertTrue(self.bridge.entered.wait(timeout=1))
        try:
            self.assertEqual(self.dispatcher.snapshot()['state'], 'running')
            self.assert_error(ErrorCode.WORKER_BUSY, lambda: self.dispatcher.call('add_text', 'another'))
            self.assert_error(ErrorCode.WORKER_BUSY, lambda: self.dispatcher.call('get_document_info'))
        finally:
            self.bridge.release.set()
            caller.join(timeout=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(self.bridge.writes, 1)
        self.assertEqual(self.bridge.reads, 0)

    def test_timeout_keeps_native_work_running_and_never_replays_it(self):
        operation_id = self.timeout_mutation()
        state = self.dispatcher.snapshot()
        self.assertEqual(state['state'], 'timed_out_but_running')
        self.assertTrue(state['worker_alive'])
        self.assertTrue(state['recovery_required'])
        self.assertEqual(state['active_operation']['operation_id'], operation_id)
        self.assertEqual(self.bridge.writes, 0)
        self.assert_error(ErrorCode.WORKER_BUSY, lambda: self.dispatcher.reconcile(operation_id))
        self.bridge.release.set()
        state = self.wait_terminal()
        self.assertEqual(state['state'], 'idle')
        self.assertTrue(state['recovery_required'])
        self.assertFalse(state['accepting_mutations'])
        self.assertEqual(self.bridge.writes, 1)
        self.assert_error(ErrorCode.RECOVERY_REQUIRED, lambda: self.dispatcher.call('add_text', 'duplicate'))
        self.assertEqual(self.bridge.writes, 1)

    def test_late_success_is_inspectable_and_reconciles_on_the_worker(self):
        operation_id = self.timeout_mutation()
        self.bridge.release.set(); self.wait_terminal()
        result = self.dispatcher.operation_status(operation_id)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['timed_out'])
        self.assertEqual(result['summary']['result_code'], 'OK')
        self.assertEqual(result['summary']['created_object_ids'], [{'static_id': 1}])
        self.assertNotIn('private', json.dumps(result))
        self.assertEqual(self.dispatcher.call('get_document_info')['object_count'], 1)
        reconciled = self.dispatcher.reconcile(operation_id)
        self.assertTrue(reconciled['reconciled'])
        self.assertEqual(reconciled['previous_operation']['operation_id'], operation_id)
        self.assertTrue(self.dispatcher.snapshot()['accepting_mutations'])
        self.assertNotIn(threading.get_ident(), self.bridge.native_threads)
        self.bridge.block = False
        self.dispatcher.call('add_text', 'next deliberate operation')
        self.assertEqual(self.bridge.writes, 2)

    def test_failed_mutation_requires_probe_and_explicit_partial_acknowledgement(self):
        operation_id = self.fail_mutation()
        state = self.dispatcher.snapshot()
        self.assertEqual(state['recovery']['reason'], 'mutation_failed')
        self.assertTrue(state['recovery']['requires_partial_ack'])
        self.assert_error(ErrorCode.CONFIRMATION_REQUIRED, lambda: self.dispatcher.reconcile(operation_id))
        self.assertTrue(self.dispatcher.snapshot()['recovery_required'])
        self.assertEqual(self.bridge.probes, 1)
        result = self.dispatcher.reconcile(operation_id, acknowledge_partial_changes=True)
        self.assertEqual(result['document_state']['page_object_count'], 1)
        self.assertFalse(self.dispatcher.snapshot()['recovery_required'])

    def test_late_failure_retains_partial_change_requirement(self):
        self.bridge.error = CorelBridgeError('private', ErrorCode.COREL_COM_ERROR)
        operation_id = self.timeout_mutation()
        self.bridge.release.set(); self.wait_terminal()
        self.assertEqual(self.dispatcher.operation_status(operation_id)['status'], 'failed')
        self.assertTrue(self.dispatcher.snapshot()['recovery']['requires_partial_ack'])
        self.assert_error(ErrorCode.CONFIRMATION_REQUIRED, lambda: self.dispatcher.reconcile(operation_id))

    def test_unverified_rollback_blocks_even_when_failure_code_is_a_validation_code(self):
        for details in ({'rollback_verified': False}, {'rollback': {'requested': True, 'attempted': True, 'verified': False}}):
            operation_id = self.fail_mutation(CorelBridgeError('private', ErrorCode.INVALID_ARGUMENT, details))
            self.assertEqual(self.dispatcher.snapshot()['recovery']['reason'], 'rollback_unverified')
            self.dispatcher.reconcile(operation_id, acknowledge_partial_changes=True)

    def test_verified_rollback_leaves_known_state_without_quarantine(self):
        for details in ({'rollback_verified': True}, {'rollback': {'attempted': True, 'verified': True}}):
            self.assertIsNone(self.fail_mutation(CorelBridgeError('failure safely undone', ErrorCode.COREL_COM_ERROR, details)))
            self.assertTrue(self.dispatcher.snapshot()['accepting_mutations'])

    def test_preflight_refusal_codes_do_not_require_partial_ack(self):
        self.bridge.preflight_refusal = True
        for code in (ErrorCode.INVALID_ARGUMENT, ErrorCode.OBJECT_NOT_FOUND, ErrorCode.AMBIGUOUS_SELECTOR,
                     ErrorCode.NO_TARGET_DOCUMENT, ErrorCode.CONFIRMATION_REQUIRED, ErrorCode.UNSAFE_PATH, ErrorCode.OUTPUT_EXISTS):
            self.assertIsNone(self.fail_mutation(CorelBridgeError('safe refusal', code)))

    def test_validation_code_after_native_mutation_is_not_mistaken_for_preflight(self):
        operation_id = self.fail_mutation(CorelBridgeError('failed after native edit', ErrorCode.INVALID_ARGUMENT))
        self.assertIsNotNone(operation_id)
        self.assertTrue(self.dispatcher.snapshot()['recovery']['requires_partial_ack'])
        self.assert_error(ErrorCode.RECOVERY_REQUIRED, lambda: self.dispatcher.call('add_text', 'duplicate'))

    def test_unknown_bridge_methods_are_conservatively_mutating(self):
        self.assert_error(ErrorCode.RECOVERY_REQUIRED, lambda: self._unknown_after_failure())
        self.assertTrue(self.dispatcher.snapshot()['recovery_required'])

    def _unknown_after_failure(self):
        self.fail_mutation()
        return self.dispatcher.call('unclassified_new_tool')

    def test_read_timeout_resolves_without_a_partial_mutation_quarantine(self):
        self.bridge.read_block = True
        error = self.assert_error(ErrorCode.OPERATION_TIMEOUT, lambda: self.dispatcher.call('get_document_info'))
        self.assertFalse(error.details['mutation'])
        self.assertEqual(self.dispatcher.snapshot()['state'], 'timed_out_but_running')
        self.assert_error(ErrorCode.WORKER_BUSY, lambda: self.dispatcher.call('add_text', 'secret'))
        self.bridge.release.set(); state = self.wait_terminal()
        self.assertFalse(state['recovery_required'])
        self.assertTrue(state['accepting_mutations'])
        self.assertEqual(self.bridge.writes, 0)

    def test_native_read_failure_requires_successful_probe_but_no_partial_ack(self):
        self.bridge.read_error = CorelBridgeError('private read detail', ErrorCode.COREL_COM_ERROR)
        self.assert_error(ErrorCode.COREL_COM_ERROR, lambda: self.dispatcher.call('get_document_info'))
        recovery = self.dispatcher.snapshot()['recovery']
        self.assertEqual(recovery['reason'], 'read_failed')
        self.assertFalse(recovery['requires_partial_ack'])
        self.dispatcher.reconcile(recovery['operation_id'])
        self.assertTrue(self.dispatcher.snapshot()['accepting_mutations'])

    def test_read_failures_during_recovery_do_not_replace_the_original_operation(self):
        operation_id = self.fail_mutation()
        self.bridge.read_error = CorelBridgeError('private', ErrorCode.COREL_COM_ERROR)
        self.assert_error(ErrorCode.COREL_COM_ERROR, lambda: self.dispatcher.call('get_document_info'))
        self.assertEqual(self.dispatcher.snapshot()['recovery']['operation_id'], operation_id)

    def test_failed_or_malformed_probe_cannot_clear_recovery_even_with_ack(self):
        operation_id = self.fail_mutation()
        self.bridge.probe_error = CorelBridgeError('private probe failure', ErrorCode.COREL_COM_ERROR)
        self.assert_error(ErrorCode.COREL_COM_ERROR, lambda: self.dispatcher.reconcile(operation_id, True))
        self.bridge.probe_error = None
        for bad in ({}, {'target_bound': True}, {**probe(), 'page_index': True}, {**probe(), 'dirty': None}, {**probe(), 'open_document_count': 1001}):
            self.bridge.probe_value = bad
            self.assert_error(ErrorCode.COREL_COM_ERROR, lambda: self.dispatcher.reconcile(operation_id, True))
            self.assertEqual(self.dispatcher.snapshot()['recovery']['operation_id'], operation_id)

    def test_stale_recovery_id_and_invalid_ack_fail_before_native_probe(self):
        operation_id = self.fail_mutation()
        self.assert_error(ErrorCode.RECOVERY_REQUIRED, lambda: self.dispatcher.reconcile('f'*32, True))
        self.assert_error(ErrorCode.INVALID_ARGUMENT, lambda: self.dispatcher.reconcile(operation_id, 'yes'))
        self.assert_error(ErrorCode.INVALID_ARGUMENT, lambda: self.dispatcher.reconcile('bad', True))
        self.assertEqual(self.bridge.probes, 0)
        self.dispatcher.reconcile(operation_id, True)
        self.assert_error(ErrorCode.RECOVERY_REQUIRED, lambda: self.dispatcher.reconcile(operation_id, True))

    def test_recovery_history_is_bounded_and_pins_the_unresolved_operation(self):
        operation_id = self.fail_mutation()
        first_read = None
        for _ in range(MAX_OPERATION_HISTORY + 5):
            self.dispatcher.call('get_document_info')
            if first_read is None:first_read = self.dispatcher.snapshot()['last_operation']['operation_id']
        self.assertEqual(self.dispatcher.snapshot()['retained_operations'], MAX_OPERATION_HISTORY)
        self.assertEqual(self.dispatcher.operation_status(operation_id)['status'], 'failed')
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND, lambda: self.dispatcher.operation_status(first_read))
        result = self.dispatcher.reconcile(operation_id, True)
        self.assertIsNotNone(result['previous_operation'])

    def test_operation_history_and_snapshots_are_copies_and_contain_no_client_content(self):
        self.dispatcher.call('add_text', 'private secret data')
        state = self.dispatcher.snapshot()
        operation_id = state['last_operation']['operation_id']
        self.assertNotIn('private', json.dumps(state))
        self.assertNotIn('secret', json.dumps(state))
        state['last_operation']['summary']['result_code'] = 'private'
        status = self.dispatcher.operation_status(operation_id)
        self.assertEqual(status['summary']['result_code'], 'OK')
        status['summary']['created_object_ids'].clear()
        self.assertTrue(self.dispatcher.operation_status(operation_id)['summary']['created_object_ids'])

    def test_native_busy_hresult_is_recognized_without_retry_or_raw_messages(self):
        class BusyError(Exception):
            hresult = -2147417846  # 0x8001010A
        native = BusyError('private HRESULT details')
        error = CorelBridgeError('sanitized', ErrorCode.COREL_COM_ERROR)
        error.__cause__ = native
        operation_id = self.fail_mutation(error)
        self.assertEqual(self.bridge.writes, 1)
        self.assertEqual(self.dispatcher.snapshot()['recovery']['reason'], 'application_busy')
        self.assertTrue(self.dispatcher.operation_status(operation_id)['summary']['native_busy'])
        self.assertNotIn('private', json.dumps(self.dispatcher.snapshot()))
        native.__cause__ = error
        self.assertTrue(native_busy(error))

    def test_operator_tools_and_pure_planning_remain_responsive_during_timeout(self):
        operation_id = self.timeout_mutation()
        with patch.object(server, 'dispatcher', self.dispatcher):
            state = server.get_operator_state()
            status = server.get_operation_status(operation_id)
            plan = server.plan_chest_number_batch(1, 3)
            rejected = server.add_text('duplicate', 1, 2)
        self.assertEqual(state['data']['state'], 'timed_out_but_running')
        self.assertEqual(status['data']['status'], 'timed_out_but_running')
        self.assertTrue(plan['ok'])
        self.assertEqual(rejected['error']['code'], 'WORKER_BUSY')
        self.assertEqual(self.bridge.writes, 0)

    def test_timeout_result_carries_a_correlation_id_even_with_recording_disabled(self):
        self.bridge.block = True
        with patch.object(server, 'dispatcher', self.dispatcher):
            result = server.add_text('private', 1, 2)
        self.assertEqual(result['error']['code'], 'OPERATION_TIMEOUT')
        self.assertEqual(result['operation_id'], self.dispatcher.snapshot()['active_operation']['operation_id'])
        self.assertTrue(result['error']['details']['recovery_required'])

    def test_shutdown_blocks_new_work_and_never_force_terminates_the_native_call(self):
        self.timeout_mutation()
        with self.assertRaisesRegex(RuntimeError, 'native work may continue'):
            self.dispatcher.close(timeout=0.01)
        state = self.dispatcher.snapshot()
        self.assertEqual(state['state'], 'unavailable')
        self.assertTrue(state['worker_alive'])
        self.assertTrue(state['closing'])
        self.assert_error(ErrorCode.WORKER_UNAVAILABLE, lambda: self.dispatcher.call('add_text', 'secret'))
        self.bridge.release.set()
        self.dispatcher.close(timeout=1)
        self.assertEqual(self.bridge.writes, 1)

    def test_pending_timeout_is_cancelled_before_execution(self):
        self.dispatcher.close()
        processing = threading.Event()
        class DelayedDispatcher(server.CorelDispatcher):
            def _worker(inner):
                inner._ready.set()
                if not processing.wait(timeout=2):return
                super(DelayedDispatcher, inner)._worker()
        delayed = DelayedDispatcher(call_timeout_seconds=0.02)
        try:
            error = self.assert_error(ErrorCode.OPERATION_TIMEOUT, lambda: delayed.call('add_text', 'secret'))
            self.assertTrue(error.details['cancelled_before_execution'])
            self.assertFalse(delayed.snapshot()['recovery_required'])
            self.assertEqual(delayed.operation_status(error.details['operation_id'])['status'], 'cancelled')
            processing.set()
            delayed.call_timeout_seconds = 1.0
            delayed.call('get_document_info')
            self.assertEqual(self.bridge.writes, 0)
        finally:
            processing.set(); delayed.close()

    def test_reconciliation_timeout_keeps_original_recovery_and_eventual_probe_can_finish(self):
        operation_id = self.fail_mutation()
        self.bridge.probe_block = True
        self.assert_error(ErrorCode.OPERATION_TIMEOUT, lambda: self.dispatcher.reconcile(operation_id, True))
        self.assertEqual(self.dispatcher.snapshot()['recovery']['operation_id'], operation_id)
        self.assert_error(ErrorCode.WORKER_BUSY, lambda: self.dispatcher.call('add_text', 'secret'))
        self.bridge.release.set(); state = self.wait_terminal()
        self.assertFalse(state['recovery_required'])
        self.assertTrue(state['last_operation']['reconciliation'])

    def test_invalid_timeout_configuration_is_rejected_before_starting_a_worker(self):
        for value in (0, -1, 121, True, float('nan'), float('inf'), '120'):
            self.assert_error(ErrorCode.INVALID_ARGUMENT, lambda: server.CorelDispatcher(value))

    def test_completed_native_timeout_exception_is_not_a_wait_timeout(self):
        self.bridge.error = TimeoutError('native operation failure')
        with self.assertRaises(TimeoutError):self.dispatcher.call('add_text','secret')
        state = self.dispatcher.snapshot()
        self.assertEqual(state['state'],'idle')
        self.assertEqual(state['last_operation']['status'],'failed')
        self.assertFalse(state['last_operation']['timed_out'])
        self.assertTrue(state['recovery']['requires_partial_ack'])

    def test_completion_at_wait_deadline_returns_actual_result_without_false_quarantine(self):
        class DeadlineFuture(Future):
            def result(inner,timeout=None):
                result = super(DeadlineFuture,inner).result(timeout=timeout)
                if timeout != 0:raise TimeoutError('simulated deadline race after completion')
                return result
        with patch.object(server,'Future',DeadlineFuture):
            result = self.dispatcher.call('add_text','secret')
        self.assertTrue(result['created'])
        self.assertEqual(self.bridge.writes,1)
        self.assertFalse(self.dispatcher.snapshot()['recovery_required'])

    def test_cancelled_queue_capacity_and_shutdown_remain_bounded(self):
        self.dispatcher.close()
        processing = threading.Event()
        class DelayedDispatcher(server.CorelDispatcher):
            def _worker(inner):
                inner._ready.set()
                if processing.wait(timeout=2):super(DelayedDispatcher,inner)._worker()
        delayed = DelayedDispatcher(call_timeout_seconds=0.001)
        try:
            for _ in range(32):self.assert_error(ErrorCode.OPERATION_TIMEOUT,lambda:delayed.call('add_text','secret'))
            self.assert_error(ErrorCode.WORKER_BUSY,lambda:delayed.call('add_text','secret'))
            self.assertFalse(delayed.snapshot()['accepting_mutations'])
            with self.assertRaisesRegex(RuntimeError,'stop queue is full'):delayed.close(timeout=0.01)
            self.assertTrue(delayed.snapshot()['closing'])
            processing.set()
            deadline = time.monotonic()+1
            while delayed._jobs.full() and time.monotonic()<deadline:time.sleep(0.002)
            delayed.close(timeout=1)
            self.assertEqual(self.bridge.writes,0)
        finally:
            processing.set();delayed.close()

    def test_read_only_method_classification_matches_current_com_registry_permissions(self):
        registry = json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        for tool in registry['tools']:
            method = tool['implementation'].get('bridge_method', '')
            if tool['implementation']['state'] != 'registered' or not method.startswith('CorelBridge.'):continue
            method = method.split('.')[-1]
            self.assertEqual(method in READ_ONLY_METHODS, tool['permission'] == 'read_only', tool['name'])

    def test_new_operator_request_and_actual_result_schemas(self):
        registry = json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        operation_id = self.fail_mutation()
        with patch.object(server, 'dispatcher', self.dispatcher):
            for name, request in (('get_operator_state', {}), ('get_operation_status', {'operation_id':operation_id}),
                                  ('reconcile_operator_state', {'operation_id':operation_id,'acknowledge_partial_changes':True})):
                tool = next(t for t in registry['tools'] if t['name'] == name)
                for key, value in (('input_schema', request), ('output_schema', getattr(server,name)(**request))):
                    Draft202012Validator({'schema_definitions':registry['schema_definitions'],'allOf':[tool[key]]}).validate(value)


class NativeReconciliationProbeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = CorelBridge()
        self.page = SimpleNamespace(Index=1, Shapes=SimpleNamespace(Count=3))
        pages = SimpleNamespace(Count=1, Item=lambda index:self.page)
        self.document = SimpleNamespace(Name='private client', ActivePage=self.page, Pages=pages,
                                        Unit=1, ReferencePoint=5, Dirty=False)
        attach_open_document(self.bridge, self.document)

    def test_probe_reads_complete_native_target_state_without_mutating_it(self):
        before = vars(self.document).copy()
        result = self.bridge.reconcile_document_state()
        self.assertEqual(result, {**probe(3), 'dirty':False})
        self.assertEqual(before, vars(self.document))
        self.assertNotIn('private', json.dumps(result))

    def test_closed_or_replaced_target_returns_known_unbound_state(self):
        self.bridge.app.Documents.items[:] = [SimpleNamespace(Name='same name replacement')]
        result = self.bridge.reconcile_document_state()
        self.assertFalse(result['target_bound'])
        self.assertIsNone(self.bridge.target_doc)
        self.assertIsNone(result['document_session_id'])

    def test_disconnected_probe_never_reconnects_or_chooses_active_document(self):
        self.bridge.app = None
        with patch.object(self.bridge, 'connect', side_effect=AssertionError('must not reconnect')):
            result = self.bridge.reconcile_document_state()
        self.assertFalse(result['connected'])
        self.assertFalse(result['target_bound'])

    def test_unreadable_or_invalid_state_is_sanitized_and_not_claimed_reconciled(self):
        for field, value in (('Unit', None), ('ReferencePoint', True), ('Dirty', 'unknown')):
            old = getattr(self.document, field);setattr(self.document,field,value)
            with self.assertRaises(CorelBridgeError) as caught:self.bridge.reconcile_document_state()
            self.assertEqual(caught.exception.code, ErrorCode.COREL_COM_ERROR)
            self.assertNotIn('private', str(caught.exception))
            setattr(self.document,field,old)
        self.page.Shapes.Count = -1
        with self.assertRaises(CorelBridgeError):self.bridge.reconcile_document_state()

    def test_unreadable_document_collection_cannot_reconcile(self):
        class Broken:
            @property
            def Count(self):raise RuntimeError('private token=secret')
        self.bridge.app.Documents = Broken()
        with self.assertRaises(CorelBridgeError) as caught:self.bridge.reconcile_document_state()
        self.assertEqual(caught.exception.code, ErrorCode.COREL_COM_ERROR)
        self.assertNotIn('secret',str(caught.exception))

    def test_replaced_active_page_is_refused(self):
        self.document.Pages.Item = lambda index:SimpleNamespace(Index=1)
        with self.assertRaises(CorelBridgeError):self.bridge.reconcile_document_state()

    def test_real_preflight_refusal_has_no_native_mutation_stage(self):
        with patch.object(server, 'CorelBridge', side_effect=lambda:self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with self.assertRaises(CorelBridgeError):dispatcher.call('set_text_content', '', shape_index=1)
            self.assertFalse(dispatcher.snapshot()['recovery_required'])
            self.assertFalse(self.bridge._operation_mutation_started)
        finally:
            dispatcher.close()

    def test_real_native_setter_failure_requires_recovery_and_partial_ack(self):
        class Story:
            value = 'Before'
            @property
            def Text(self):return self.value
            @Text.setter
            def Text(self, value):
                self.value = value
                raise CorelBridgeError('native setter failed after updating', ErrorCode.INVALID_ARGUMENT)
        story = Story()
        shape = SimpleNamespace(Name='Title', Text=SimpleNamespace(Story=story))
        self.page.Shapes.Item = lambda index:shape
        with patch.object(server, 'CorelBridge', side_effect=lambda:self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with self.assertRaises(CorelBridgeError):dispatcher.call('set_text_content', 'After', shape_index=1)
            self.assertEqual(story.value, 'After')
            self.assertTrue(self.bridge._operation_mutation_started)
            recovery = dispatcher.snapshot()['recovery']
            self.assertTrue(recovery['requires_partial_ack'])
            with self.assertRaises(CorelBridgeError) as caught:dispatcher.call('set_text_content','Another',shape_index=1)
            self.assertEqual(caught.exception.code, ErrorCode.RECOVERY_REQUIRED)
            self.assertEqual(story.value,'After')
        finally:
            dispatcher.close()

    def test_nested_preflight_failure_cannot_erase_an_outer_native_edit_stage(self):
        class NestedBridge(CorelBridge):
            @tracked_mutation
            def nested_job(self):
                self._note_mutation()
                self.target_doc.Dirty = True
                return self.set_text_content('')
        bridge = NestedBridge()
        attach_open_document(bridge,self.document)
        with patch.object(server, 'CorelBridge', side_effect=lambda:bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with self.assertRaises(CorelBridgeError):dispatcher.call('nested_job')
            self.assertTrue(self.document.Dirty)
            self.assertTrue(dispatcher.snapshot()['recovery']['requires_partial_ack'])
            self.assertEqual(bridge._mutation_depth,0)
        finally:
            dispatcher.close()

    def test_native_context_restoration_failure_after_edit_is_not_silent_success(self):
        class Document:
            _unit = 3
            @property
            def Unit(self):return self._unit
            @Unit.setter
            def Unit(self,value):
                if value == 3:raise RuntimeError('unit restoration failed')
                self._unit = value
        document = Document()
        document.Name = 'Fixture'
        document.ActivePage = self.page
        document.Pages = self.document.Pages
        document.ReferencePoint = 5
        document.Dirty = False
        shape = SimpleNamespace(Name='Shape',PositionX=1.,PositionY=2.)
        def set_position(x,y):
            shape.PositionX,shape.PositionY = x,y
            document.Dirty = True
        shape.SetPosition = set_position
        self.page.Shapes.Item = lambda index:shape
        attach_open_document(self.bridge,document)
        with patch.object(server,'CorelBridge',side_effect=lambda:self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with self.assertRaises(CorelBridgeError):dispatcher.call('move_object',8,9,shape_index=1)
            self.assertEqual((shape.PositionX,shape.PositionY),(8.,9.))
            self.assertEqual(document.Unit,1)
            self.assertTrue(dispatcher.snapshot()['recovery']['requires_partial_ack'])
        finally:
            dispatcher.close()

    def test_read_only_context_restoration_failure_requires_probe_without_artwork_ack(self):
        class Document:
            _unit = 3
            @property
            def Unit(self):return self._unit
            @Unit.setter
            def Unit(self,value):
                if value == 3:raise RuntimeError('unit restoration failed')
                self._unit = value
        document = Document()
        document.Name = 'Fixture'
        document.ActivePage = self.page
        document.Pages = self.document.Pages
        document.ReferencePoint = 5
        document.Dirty = False
        shape = SimpleNamespace(Name='Shape',StaticID=1,Type=1,PositionX=1.,PositionY=2.,SizeWidth=3.,SizeHeight=4.)
        self.page.Shapes.Item = lambda index:shape
        attach_open_document(self.bridge,document)
        with patch.object(server,'CorelBridge',side_effect=lambda:self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with self.assertRaises(CorelBridgeError):dispatcher.call('get_object_info',shape_index=1)
            recovery = dispatcher.snapshot()['recovery']
            self.assertIsNotNone(recovery)
            self.assertFalse(recovery['requires_partial_ack'])
            self.assertEqual(document.Unit,1)
            self.assertFalse(document.Dirty)
        finally:
            dispatcher.close()


if __name__ == '__main__':
    unittest.main()
