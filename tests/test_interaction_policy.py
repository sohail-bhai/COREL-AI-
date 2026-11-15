import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.worker_state import failure_recovery_reason
from fake_documents import attach_open_document, OpenDocuments
import test_typography as fixtures


class InteractionPolicyTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.TypographyTests()
        fixture.setUp()
        self.bridge, self.document = fixture.bridge, fixture.document
        self.bridge.configure_editing_mode('paused')
        self.other = SimpleNamespace(Name='My work.cdr')
        self.bridge.app.Documents = OpenDocuments(self.document, self.other)
        self.bridge.app.ActiveDocument = self.other
        self.bridge._native_pause_event = threading.Event()

    def test_default_paused_refusal_does_not_quarantine(self):
        with self.assertRaises(CorelBridgeError) as caught:
            self.bridge._prepare_interaction_operation('add_text', True)
        self.assertEqual(caught.exception.code, ErrorCode.CONFIRMATION_REQUIRED)
        self.assertIsNone(failure_recovery_reason(caught.exception, True, self.bridge._operation_mutation_started))

    def test_read_and_bind_allowed_while_paused(self):
        for method, mutation in [('inspect_text_range', False), ('use_active_document', True)]:
            self.bridge._prepare_interaction_operation(method, mutation)
            self.assertEqual(self.bridge._interaction_operation, method if not mutation else None)

    def test_read_only_temporary_context_writes_are_also_guarded(self):
        self.bridge._prepare_interaction_operation('get_object_bounds', False)
        with self.assertRaises(CorelBridgeError): self.bridge._note_mutation()
        self.bridge.configure_editing_mode('background_document')
        self.bridge._prepare_interaction_operation('get_document_structure', False)
        with self.assertRaises(CorelBridgeError): self.bridge._note_mutation()

    def test_direct_embedded_bridge_cannot_bypass_paused_policy(self):
        with self.assertRaises(CorelBridgeError):
            self.bridge.set_text_style(bold=True, object_name='Title')
        self.assertFalse(self.bridge._operation_mutation_started)
        self.bridge._interaction_operation = None
        with self.assertRaises(CorelBridgeError): self.bridge._note_mutation()

    def test_fresh_direct_bridge_refuses_before_connecting_or_creating(self):
        bridge = CorelBridge()
        with patch.object(bridge, '_require_app') as require_app:
            with self.assertRaises(CorelBridgeError): bridge.create_document()
            require_app.assert_not_called()
        self.assertIsNone(bridge._interaction_operation)

    def test_exclusive_requires_explicit_confirmation(self):
        with self.assertRaises(CorelBridgeError): self.bridge.configure_editing_mode('exclusive')
        self.bridge.configure_editing_mode('exclusive', True)
        self.bridge._prepare_interaction_operation('add_text', True)
        self.bridge._note_mutation()

    def test_background_only_on_separate_inactive_document(self):
        result = self.bridge.configure_editing_mode('background_document')
        self.assertTrue(result['requires_separate_document'])
        self.bridge._prepare_interaction_operation('edit_text_range', True)
        self.bridge._note_mutation()
        self.bridge.app.ActiveDocument = self.document
        with self.assertRaises(CorelBridgeError): self.bridge._note_mutation()

    def test_background_rejects_global_and_legacy_selection_commands(self):
        self.bridge.configure_editing_mode('background_document')
        for method in ('create_document', 'set_text_style', 'set_text_spacing', 'fit_paragraph_text',
                       'export_pdf', 'activate_page', 'undo', 'save_document', 'execute_design_plan'):
            with self.assertRaises(CorelBridgeError): self.bridge._prepare_interaction_operation(method, True)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_document_switch_rebind_and_close_are_refused(self):
        for change in ('active', 'rebind', 'closed'):
            self.setUp()
            self.bridge.configure_editing_mode('background_document')
            self.bridge._prepare_interaction_operation('edit_text_range', True)
            if change == 'active': self.bridge.app.ActiveDocument = self.document
            if change == 'rebind': self.bridge._bind_target_document(self.other)
            if change == 'closed': self.bridge.app.Documents = OpenDocuments(self.other)
            with self.assertRaises(CorelBridgeError): self.bridge._note_mutation()

    def test_missing_foreground_refused(self):
        self.bridge.app.ActiveDocument = None
        with self.assertRaises(CorelBridgeError): self.bridge.configure_editing_mode('background_document')

    def test_pause_event_stops_remaining_writes_and_retains_partial_state(self):
        self.bridge.configure_editing_mode('background_document')
        self.bridge._prepare_interaction_operation('edit_text_range', True)
        self.bridge._mutation_depth = 1
        self.bridge._note_mutation()
        self.bridge._native_pause_event.set()
        with self.assertRaises(CorelBridgeError) as caught: self.bridge._note_mutation()
        self.assertEqual(failure_recovery_reason(caught.exception, True, self.bridge._operation_mutation_started), 'mutation_failed')

    def test_invalid_modes_refused(self):
        for mode, confirm in [('other', False), (True, False), ('exclusive', 1)]:
            with self.assertRaises(CorelBridgeError): self.bridge.configure_editing_mode(mode, confirm)

    def test_dispatcher_starts_paused_and_refusal_leaves_worker_usable(self):
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = server.CorelDispatcher(call_timeout_seconds=1)
        try:
            self.assertFalse(dispatcher.snapshot()['accepting_mutations'])
            with self.assertRaises(CorelBridgeError):
                dispatcher.call('set_text_style', bold=True, object_name='Title')
            self.assertFalse(dispatcher.snapshot()['recovery_required'])
            dispatcher.call('configure_editing_mode', 'exclusive', True)
            self.assertTrue(dispatcher.snapshot()['accepting_mutations'])
            dispatcher.call('set_text_style', bold=True, object_name='Title')
            dispatcher.pause_native_editing()
            self.assertFalse(dispatcher.snapshot()['accepting_mutations'])
            with self.assertRaises(CorelBridgeError):
                dispatcher.call('set_text_style', italic=True, object_name='Title')
        finally:
            dispatcher.close()

    def test_pause_wins_over_a_configuration_already_in_progress(self):
        original = self.bridge.configure_editing_mode
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = server.CorelDispatcher(call_timeout_seconds=1)
        def configure(*args):
            result = original(*args)
            dispatcher.pause_native_editing()
            return result
        self.bridge.configure_editing_mode = configure
        try:
            result = dispatcher.call('configure_editing_mode', 'exclusive', True)
            self.assertTrue(result['native_writes_paused'])
            self.assertFalse(dispatcher.snapshot()['accepting_mutations'])
        finally:
            dispatcher.close()

    def test_immediate_pause_during_running_native_call_stops_second_write(self):
        from corel_operator.native_tracking import tracked_mutation
        entered, release = threading.Event(), threading.Event()
        writes, errors = [], []
        @tracked_mutation
        def slow(bridge):
            bridge._note_mutation()
            writes.append('first')
            entered.set()
            if not release.wait(1): raise AssertionError('Test release timed out')
            bridge._note_mutation()
            writes.append('second')
        self.bridge.slow = lambda: slow(self.bridge)
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = server.CorelDispatcher(call_timeout_seconds=1)
        def execute():
            try: dispatcher.call('slow')
            except CorelBridgeError as exc: errors.append(exc)
        try:
            dispatcher.call('configure_editing_mode', 'exclusive', True)
            caller = threading.Thread(target=execute)
            caller.start()
            self.assertTrue(entered.wait(.5))
            result = dispatcher.pause_native_editing()
            self.assertFalse(result['in_flight_native_call_cancellable'])
            release.set()
            caller.join(1)
            self.assertEqual(writes, ['first'])
            self.assertEqual(len(errors), 1)
            self.assertTrue(dispatcher.snapshot()['recovery_required'])
        finally:
            release.set()
            dispatcher.close()
