from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator

from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.operation_records import (
    OperationJournal, current_operation, input_summary, result_metadata, target_ids,
)


class FakeBridge:
    def __init__(self):
        self._bridge_session_id = '1'*32
        self._target_document_key = 'private native pointer key'
        self._document_sessions = {self._target_document_key: 'doc-0001'}

    def add_text(self, *args):
        return {'created': True, 'text': args[0], 'object': {'static_id': 101, 'object_name': 'private client title'}}

    def set_text_content(self, *args):
        raise CorelBridgeError('private path token=secret', ErrorCode.COREL_COM_ERROR,
                               {'rollback_attempted': True, 'rollback_verified': False, 'private': 'secret'})


class OperationRecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='corel-record-tests-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.journal = OperationJournal(self.path)
        self.addCleanup(self.journal.close)

    def records(self):
        return [json.loads(line) for p in sorted(self.path.glob('*.jsonl')) for line in p.read_text(encoding='utf-8').splitlines()]

    def test_disabled_journal_performs_no_filesystem_io(self):
        journal = OperationJournal()
        with patch.object(Path, 'open', side_effect=AssertionError('must not open')):
            self.assertFalse(journal.write('1'*32, 'add_text', 'requested'))
        self.assertFalse(journal.enabled)

    def test_invalid_or_repository_directory_is_refused_without_creation(self):
        for location in (Path('relative-records'), self.path / 'repository' / 'logs'):
            journal = OperationJournal(location, repository_root=self.path / 'repository')
            self.addCleanup(journal.close)
            self.assertFalse(journal.available)
            self.assertFalse(journal.write('1'*32, 'add_text', 'requested'))
            self.assertFalse(location.exists())

    def test_canonical_repository_path_is_refused(self):
        repository = self.path / 'repo'
        journal = OperationJournal(repository / '..' / 'repo' / 'records', repository_root=repository)
        self.assertFalse(journal.available)

    def test_environment_is_opt_in_and_empty_value_is_disabled(self):
        with patch.dict('os.environ', {'COREL_OPERATION_LOG_DIR': ''}):
            self.assertFalse(OperationJournal.from_environment().enabled)
        with patch.dict('os.environ', {'COREL_OPERATION_LOG_DIR': str(self.path)}):
            journal = OperationJournal.from_environment()
            self.addCleanup(journal.close)
            self.assertTrue(journal.enabled)
            self.assertTrue(journal.available)

    def test_type_summary_omits_parameter_names_values_and_nested_content(self):
        summary = input_summary(('secret text', 123, True, None), {'private_client_name': {'api_key': 'secret'}, 'file': ['C:/private/client.cdr']})
        self.assertEqual(summary['parameter_count'], 6)
        self.assertEqual(summary['type_counts']['object'], 1)
        self.assertNotIn('private', json.dumps(summary))
        self.assertNotIn('123', json.dumps(summary))

    def test_result_summary_omits_text_paths_names_warnings_and_exception_details(self):
        payload = {'created': True, 'path': 'C:/private/client.cdr', 'text': 'secret', 'warning': 'private',
                   'objects': [{'static_id': 101, 'object_name': 'secret'}, {'object_id': 'doc-0001:shape:102'}],
                   'rollback_attempted': True, 'rollback_verified': False}
        metadata = result_metadata(payload)
        self.assertEqual(metadata['created_object_ids'], [{'object_id': 'doc-0001:shape:102'}, {'static_id': 101}])
        self.assertTrue(metadata['created_ids_available'])
        self.assertNotIn('private', json.dumps(metadata))
        self.assertNotIn('secret', json.dumps(metadata))
        error = CorelBridgeError('secret', ErrorCode.COREL_COM_ERROR, {'rollback_verified': False, 'path': 'private'})
        metadata = result_metadata(error=error)
        self.assertEqual(metadata['rollback'], {'rollback_verified': False})
        self.assertEqual(metadata['result_code'], 'COREL_COM_ERROR')
        error = CorelBridgeError('secret', ErrorCode.COREL_COM_ERROR, {'rollback': {'attempted': True, 'verified': False, 'undo_succeeded': True, 'private': 'secret'}})
        metadata = result_metadata(error=error)
        self.assertEqual(metadata['rollback'], {'rollback_attempted': True, 'rollback_verified': False, 'rollback_succeeded': True})
        self.assertNotIn('secret', json.dumps(metadata))

    def test_result_id_scan_is_bounded_and_does_not_invent_unavailable_ids(self):
        cyclic = {'created': True, 'objects': []}
        cyclic['objects'].append(cyclic)
        self.assertFalse(result_metadata(cyclic)['created_ids_available'])
        result = result_metadata({'created': True, 'objects': [{'static_id': i} for i in range(5000)]})
        self.assertTrue(result['created_ids_scan_limited'])
        self.assertLessEqual(len(result['created_object_ids']), 256)
        self.assertFalse(result_metadata({'created': True, 'object_name': 'private'})['created_ids_available'])
        self.assertTrue(result_metadata({'prepared': True, 'objects': [{'static_id': 101}]})['created_ids_available'])

    def test_target_snapshot_never_reads_native_properties_or_raw_keys(self):
        class Bridge(FakeBridge):
            @property
            def target_doc(self):
                raise AssertionError('COM access is forbidden')
        targets = target_ids(Bridge())
        self.assertEqual(targets, {'bridge_session_id': '1'*32, 'document_session_id': 'doc-0001'})
        self.assertNotIn('private', json.dumps(targets))

    def test_final_disk_boundary_rejects_injected_content_and_unknown_fields(self):
        self.assertTrue(self.journal.write('1'*32, 'add_text', 'returned',
            input_summary={'private': 'secret', 'type_counts': {'string': 1, 'private': 'secret'}},
            target_ids={'document_name': 'secret', 'bridge_session_id': 'private', 'document_session_id': 'doc-0001'},
            result_code='secret', created_object_ids=[{'static_id': 101, 'name': 'secret'}, {'object_id': 'private'}],
            rollback={'rollback_verified': True, 'private': 'secret'}, private='secret'))
        text = json.dumps(self.records())
        self.assertNotIn('private', text)
        self.assertNotIn('secret', text)
        self.assertEqual(self.records()[0]['target_ids'], {'document_session_id': 'doc-0001'})

    def test_exclusive_segments_preserve_existing_files_and_prior_process_logs(self):
        existing = self.path / 'client.jsonl'; existing.write_text('Do not overwrite', encoding='utf-8')
        self.journal.write('1'*32, 'add_text', 'requested')
        another = OperationJournal(self.path); self.addCleanup(another.close)
        another.write('2'*32, 'add_text', 'requested')
        self.assertEqual(existing.read_text(encoding='utf-8'), 'Do not overwrite')
        self.assertEqual(len(list(self.path.glob('operations-*.jsonl'))), 2)

    def test_rotation_and_session_capacity_are_bounded_without_deleting_old_logs(self):
        with patch('corel_operator.operation_records.MAX_SEGMENT_BYTES', 600), patch('corel_operator.operation_records.MAX_SEGMENTS', 2):
            for i in range(20):
                self.journal.write(f'{i:032x}', 'add_text', 'requested')
        paths = list(self.path.glob('operations-*.jsonl'))
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(p.stat().st_size <= 600 for p in paths))
        self.assertFalse(self.journal.available)

    def test_disk_failure_never_prints_content_or_raises_to_caller(self):
        with patch.object(Path, 'open', side_effect=OSError('private path token=secret')), contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertFalse(self.journal.write('1'*32, 'add_text', 'requested'))
        self.assertFalse(self.journal.available)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(stderr.getvalue(), '')

    def test_concurrent_events_remain_individual_valid_json_lines(self):
        threads = [threading.Thread(target=lambda i=i: self.journal.write(f'{i:032x}', 'add_text', 'requested')) for i in range(20)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(self.records()), 20)
        self.assertEqual(len({r['operation_id'] for r in self.records()}), 20)

    def test_correlated_mcp_and_worker_success_failure_events_are_redacted(self):
        with patch.object(server, 'CorelBridge', FakeBridge):
            dispatcher = server.CorelDispatcher()
        self.addCleanup(dispatcher.close)
        with patch.object(server, 'dispatcher', dispatcher), patch.object(server, 'operation_journal', self.journal):
            success = server.add_text('secret client text', 1, 2, object_name='private client')
            failure = server.set_text_content('secret new text', object_name='private')
        self.assertTrue(success['ok'])
        self.assertFalse(failure['ok'])
        records = self.records()
        first = [r for r in records if r['operation_id'] == success['operation_id']]
        second = [r for r in records if r['operation_id'] == failure['operation_id']]
        self.assertEqual([r['event'] for r in first], ['requested', 'worker_started', 'worker_completed', 'returned'])
        self.assertEqual([r['event'] for r in second], ['requested', 'worker_started', 'worker_failed', 'returned'])
        self.assertEqual(first[1]['target_ids']['document_session_id'], 'doc-0001')
        self.assertEqual(first[2]['created_object_ids'], [{'static_id': 101}])
        self.assertFalse(second[2]['rollback']['rollback_verified'])
        self.assertNotIn('private', json.dumps(records))
        self.assertNotIn('secret', json.dumps(records))
        self.assertIsNone(current_operation.get())

    def test_pure_tool_success_and_failure_are_recorded_without_dispatcher(self):
        with patch.object(server, 'operation_journal', self.journal):
            success = server.plan_chest_number_batch(1, 3)
            failure = server.plan_chest_number_batch(3, 1)
        self.assertTrue(success['ok'])
        self.assertFalse(failure['ok'])
        self.assertEqual([r['event'] for r in self.records()], ['requested', 'returned', 'requested', 'returned'])

    def test_late_worker_completion_is_distinct_from_mcp_timeout(self):
        entered = threading.Event()
        release = threading.Event()
        class BlockingBridge(FakeBridge):
            def add_text(self, *args):
                entered.set()
                if not release.wait(timeout=2):
                    raise AssertionError('test failed to release worker')
                return super().add_text(*args)
        class ShortWaitFuture(Future):
            def result(self, timeout=None):
                return super().result(timeout=0.05)
        with patch.object(server, 'CorelBridge', BlockingBridge):
            dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher), patch.object(server, 'operation_journal', self.journal), patch.object(server, 'Future', ShortWaitFuture):
                result = server.add_text('secret', 1, 2)
            self.assertTrue(entered.is_set())
            self.assertEqual(result['error']['code'], 'OPERATION_TIMEOUT')
            self.assertEqual([r['event'] for r in self.records()], ['requested', 'worker_started', 'returned'])
        finally:
            release.set()
            dispatcher.close()
        records = self.records()
        self.assertEqual(records[-1]['event'], 'worker_completed')
        self.assertEqual(records[-1]['operation_id'], result['operation_id'])
        self.assertEqual(records[-1]['result_code'], 'OK')

    def test_unhandled_wrapper_exception_is_logged_without_raw_message(self):
        @server.recorded_operation
        def test_operation():
            raise ValueError('private token=secret')
        with patch.object(server, 'operation_journal', self.journal):
            with self.assertRaises(ValueError):test_operation()
        self.assertEqual([r['event'] for r in self.records()], ['requested', 'returned'])
        self.assertEqual(self.records()[-1]['result_code'], 'INTERNAL_ERROR')
        self.assertNotIn('secret', json.dumps(self.records()))
        self.assertIsNone(current_operation.get())

    def test_unavailable_recording_warns_but_does_not_prevent_the_operation(self):
        self.journal.available = False
        with patch.object(server, 'operation_journal', self.journal):
            result = server.plan_chest_number_batch(1, 3)
        self.assertTrue(result['ok'])
        self.assertEqual(result['warnings'], ['Operation recording could not persist all events.'])
        self.assertRegex(result['operation_id'], r'^[0-9a-f]{32}$')

    def test_default_disabled_keeps_result_envelope_compatibility(self):
        with patch.object(server, 'operation_journal', OperationJournal()):
            result = server.plan_chest_number_batch(1, 3)
        self.assertNotIn('operation_id', result)

    def test_recording_preserves_fastmcp_parameter_schema_and_catalog_envelope(self):
        registry = json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool = next(t for t in registry['tools'] if t['name'] == 'plan_chest_number_batch')
        validator = Draft202012Validator({'schema_definitions':registry['schema_definitions'],'allOf':[tool['output_schema']]})
        with patch.object(server, 'operation_journal', self.journal):
            result = server.plan_chest_number_batch(1, 3)
        validator.validate(result)
        registered = server.mcp._tool_manager.get_tool('add_text')
        self.assertIn('text', registered.parameters['properties'])
        self.assertNotIn('args', registered.parameters['properties'])


if __name__ == '__main__':
    unittest.main()
