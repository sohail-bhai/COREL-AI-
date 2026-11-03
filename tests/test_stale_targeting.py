from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from fake_documents import OpenDocuments


class _Ole:
    def __init__(self, key):
        self.key = key

    def GetIUnknown(self):
        return self.key


class _BrokenCollection:
    @property
    def Count(self):
        raise RuntimeError("C:/private/client.cdr token=secret")


class _NativeUnknown:
    __hash__ = None

    def __init__(self, key):
        self.key = key

    def __repr__(self):
        return f"<PyIUnknown at 0x{id(self):X} with obj at 0x{self.key:X}>"

    def __eq__(self, other):
        return isinstance(other, _NativeUnknown) and self.key == other.key


class _NativeOle:
    def __init__(self, key):
        self.key = key

    def QueryInterface(self, iid):
        return _NativeUnknown(self.key)


class StaleTargetingTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(sys.modules, {"pythoncom": SimpleNamespace(IID_IUnknown="IUnknown")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.document = SimpleNamespace(Name="Target.cdr")
        self.other = SimpleNamespace(Name="Client.cdr")
        self.application = SimpleNamespace(
            Documents=OpenDocuments(self.document, self.other), ActiveDocument=self.other,
        )
        self.bridge = CorelBridge()
        self.bridge.app = self.application
        self.bridge._bind_target_document(self.document)

    def assert_error(self, code, operation):
        with self.assertRaises(CorelBridgeError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        return caught.exception

    def test_bound_document_does_not_follow_user_focus(self):
        self.assertIs(self.bridge._target_document(), self.document)
        self.assertIs(self.application.ActiveDocument, self.other)

    def test_closed_target_is_cleared_without_binding_active_document(self):
        self.application.Documents.items.remove(self.document)
        self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)
        self.assertIsNone(self.bridge.target_doc)
        self.assertIs(self.application.ActiveDocument, self.other)

    def test_closed_target_blocks_mutation_before_shape_access(self):
        self.application.Documents.items.remove(self.document)
        with patch.object(self.bridge, "_find_shape", side_effect=AssertionError("Unexpected shape access")):
            self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, lambda: self.bridge.move_object(
                1, 2, object_name="headline",
            ))

    def test_same_name_reopened_file_does_not_reuse_the_binding(self):
        replacement = SimpleNamespace(Name="Target.cdr")
        self.application.Documents.items = [replacement, self.other]
        self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)
        self.assertIsNone(self.bridge.target_doc)

    def test_rename_or_save_as_keeps_the_live_document_identity(self):
        session = self.bridge._document_session_id(self.document)
        self.document.Name = "Renamed.cdr"
        self.document.FullFileName = "C:/jobs/Renamed.cdr"
        self.assertIs(self.bridge._target_document(), self.document)
        self.assertEqual(self.bridge._document_session_id(self.document), session)

    def test_collection_proxy_churn_uses_iunknown_identity(self):
        self.document._oleobj_ = _Ole(101)
        self.bridge._bind_target_document(self.document)
        proxy = SimpleNamespace(Name="Target.cdr", _oleobj_=_Ole(101))
        self.application.Documents.items = [proxy, self.other]
        self.assertIs(self.bridge._target_document(), self.document)

    def test_same_name_different_iunknown_is_rejected(self):
        self.document._oleobj_ = _Ole(101)
        self.bridge._bind_target_document(self.document)
        proxy = SimpleNamespace(Name="Target.cdr", _oleobj_=_Ole(102))
        self.application.Documents.items = [proxy]
        self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)

    def test_native_iunknown_identity_does_not_require_getter_or_hash(self):
        self.document._oleobj_ = _NativeOle(101)
        self.bridge._bind_target_document(self.document)
        proxy = SimpleNamespace(Name="Target.cdr", _oleobj_=_NativeOle(101))
        self.application.Documents.items = [proxy, self.other]
        self.assertEqual(self.bridge._com_identity(self.document), "iunknown:101")
        self.assertEqual(self.bridge._com_identity(proxy), "iunknown:101")
        self.assertIs(self.bridge._target_document(), self.document)

    def test_native_iunknown_equality_distinguishes_different_objects(self):
        first = SimpleNamespace(_oleobj_=_NativeOle(101))
        second = SimpleNamespace(_oleobj_=_NativeOle(102))
        self.assertFalse(self.bridge._same_com_object(first, second, strict=True))

    def test_failed_native_identity_is_unknown_and_preserves_binding(self):
        class Broken:
            def QueryInterface(inner, iid):
                raise RuntimeError("token=secret")

        self.document._oleobj_ = Broken()
        self.assert_error(ErrorCode.COREL_COM_ERROR, self.bridge._target_document)
        self.assertIs(self.bridge.target_doc, self.document)

    def test_unsupported_native_identity_format_blocks_binding(self):
        class Unsupported:
            def QueryInterface(inner, iid):
                return object()

        document = SimpleNamespace(Name="New.cdr", _oleobj_=Unsupported())
        self.application.Documents.items.append(document)
        self.assert_error(ErrorCode.COREL_COM_ERROR, lambda: self.bridge._bind_target_document(document))
        self.assertIsNone(self.bridge.target_doc)

    def test_failed_native_identity_comparison_is_not_reported_as_closed(self):
        class BrokenUnknown(_NativeUnknown):
            def __eq__(inner, other):
                raise RuntimeError("token=secret")

        class Broken(_NativeOle):
            def QueryInterface(inner, iid):
                return BrokenUnknown(inner.key)

        self.document._oleobj_ = Broken(101)
        self.bridge._bind_target_document(self.document)
        self.application.Documents.items = [SimpleNamespace(_oleobj_=Broken(101))]
        self.assert_error(ErrorCode.COREL_COM_ERROR, self.bridge._target_document)
        self.assertIs(self.bridge.target_doc, self.document)

    def test_application_replacement_invalidates_the_binding(self):
        self.bridge.app = SimpleNamespace(Documents=OpenDocuments(self.document), ActiveDocument=self.document)
        self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)
        self.assertIsNone(self.bridge.target_doc)

    def test_lost_application_clears_target_without_reconnecting(self):
        self.bridge.app = None
        with patch.object(self.bridge, "connect", side_effect=AssertionError("Unexpected reconnect")):
            self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)
        self.assertIsNone(self.bridge.target_doc)

    def test_direct_document_replacement_requires_explicit_rebind(self):
        self.bridge.target_doc = self.other
        self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)
        self.assertIsNone(self.bridge.target_doc)

    def test_unreadable_document_collection_blocks_use_without_losing_binding(self):
        self.application.Documents = _BrokenCollection()
        self.assert_error(ErrorCode.COREL_COM_ERROR, self.bridge._target_document)
        self.assertIs(self.bridge.target_doc, self.document)
        self.application.Documents = OpenDocuments(self.document, self.other)
        self.assertIs(self.bridge._target_document(), self.document)

    def test_unreadable_collection_blocks_mutation_without_shape_access(self):
        self.application.Documents = _BrokenCollection()
        with patch.object(self.bridge, "_find_shape", side_effect=AssertionError("Unexpected shape access")):
            self.assert_error(ErrorCode.COREL_COM_ERROR, lambda: self.bridge.move_object(
                1, 2, object_name="headline",
            ))

    def test_document_scan_limit_fails_before_any_collection_item_read(self):
        class Collection:
            Count = 1001

            def Item(inner, index):
                raise AssertionError("Unbounded traversal")

        self.application.Documents = Collection()
        self.assert_error(ErrorCode.COREL_COM_ERROR, self.bridge._target_document)
        self.assertIs(self.bridge.target_doc, self.document)

    def test_empty_document_collection_clears_target(self):
        self.application.Documents = OpenDocuments()
        self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)
        self.assertIsNone(self.bridge.target_doc)

    def test_stale_document_session_is_retired(self):
        session = self.bridge._document_session_id(self.document)
        self.application.Documents.items.remove(self.document)
        self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)
        self.application.Documents.items.append(self.document)
        self.application.ActiveDocument = self.document
        self.bridge.use_active_document(True)
        self.assertNotEqual(self.bridge._document_session_id(self.document), session)

    def test_status_clears_stale_target_and_reports_current_active_document(self):
        self.application.Documents.items.remove(self.document)
        result = self.bridge.status()
        self.assertFalse(result["target_document_bound"])
        self.assertIsNone(result["target_document_name"])
        self.assertEqual(result["active_document_name"], "Client.cdr")
        self.assertIsNone(self.bridge.target_doc)

    def test_open_document_listing_clears_stale_binding_and_sessions(self):
        session = self.bridge._document_session_id(self.document)
        self.application.Documents.items.remove(self.document)
        result = self.bridge.list_open_documents()
        self.assertEqual(len(result["documents"]), 1)
        self.assertFalse(result["documents"][0]["is_bound_target"])
        self.assertNotIn(session, self.bridge._document_sessions.values())
        self.assertIsNone(self.bridge.target_doc)

    def test_unbound_target_guard_does_not_enumerate_or_connect(self):
        self.bridge._invalidate_target_document()
        self.application.Documents = _BrokenCollection()
        with patch.object(self.bridge, "connect", side_effect=AssertionError("Unexpected connect")):
            self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)

    def test_explicit_binding_uses_open_document_identity_not_name(self):
        self.application.ActiveDocument = self.other
        result = self.bridge.use_active_document(True)
        self.assertTrue(result["bound"])
        self.assertIs(self.bridge._target_document(), self.other)


if __name__ == "__main__":
    unittest.main()
