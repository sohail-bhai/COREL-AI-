from __future__ import annotations

import unittest

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode


class _FakePage:
    def __init__(self) -> None:
        self.size = (8.27, 11.69)

    def SetSize(self, width: float, height: float) -> None:
        self.size = (width, height)

    def GetSize(self):
        return self.size


class _FakePages:
    Count = 1


class _FakeDocument:
    def __init__(self, name: str) -> None:
        self.Name = name
        self.Unit = 3
        self.ReferencePoint = 9
        self.ActivePage = _FakePage()
        self.Pages = _FakePages()
        self.activated = False

    def Activate(self) -> None:
        self.activated = True


class _FakeApplication:
    Version = "Version 17.0.0.491"
    VersionMajor = 17
    VersionMinor = 0
    VersionBuild = 491
    Visible = True

    def __init__(self, active_document: _FakeDocument | None = None) -> None:
        self.ActiveDocument = active_document
        self.created: list[_FakeDocument] = []

    def CreateDocument(self) -> _FakeDocument:
        document = _FakeDocument(f"Graphic{len(self.created) + 1}")
        self.created.append(document)
        return document


class DocumentTargetingTests(unittest.TestCase):
    def test_status_inspects_active_document_without_binding_it(self) -> None:
        existing = _FakeDocument("Client.cdr")
        bridge = CorelBridge()
        bridge.app = _FakeApplication(existing)

        status = bridge.status()

        self.assertEqual(status["active_document_name"], "Client.cdr")
        self.assertFalse(status["target_document_bound"])
        with self.assertRaises(CorelBridgeError) as context:
            bridge._target_document()
        self.assertEqual(context.exception.code, ErrorCode.NO_TARGET_DOCUMENT)

    def test_create_document_binds_only_the_new_document(self) -> None:
        existing = _FakeDocument("Client.cdr")
        application = _FakeApplication(existing)
        bridge = CorelBridge()
        bridge.app = application

        result = bridge.create_document(8.5, 11)

        self.assertIs(bridge.target_doc, application.created[0])
        self.assertIsNot(bridge.target_doc, existing)
        self.assertEqual(bridge.target_doc.ActivePage.size, (8.5, 11.0))
        self.assertEqual(bridge.target_doc.Unit, 1)
        self.assertEqual(bridge.target_doc.ReferencePoint, 5)
        self.assertTrue(bridge.target_doc.activated)
        self.assertEqual(result["target_document_name"], "Graphic1")
        self.assertEqual(result["actual_page_size_inches"], {"width": 8.5, "height": 11.0})
        self.assertEqual(result["unit_code_actual"], 1)
        self.assertEqual(result["reference_point_actual"], 5)

    def test_active_document_binding_requires_exact_true(self) -> None:
        bridge = CorelBridge()
        bridge.app = _FakeApplication(_FakeDocument("Approved.cdr"))

        with self.assertRaises(CorelBridgeError) as context:
            bridge.use_active_document(False)
        self.assertEqual(context.exception.code, ErrorCode.CONFIRMATION_REQUIRED)

        result = bridge.use_active_document(True)
        self.assertEqual(result["target_document_name"], "Approved.cdr")
        self.assertEqual(bridge._target_document().Name, "Approved.cdr")

    def test_bound_target_does_not_follow_application_focus(self) -> None:
        first = _FakeDocument("First.cdr")
        second = _FakeDocument("Second.cdr")
        application = _FakeApplication(first)
        bridge = CorelBridge()
        bridge.app = application
        bridge.use_active_document(True)

        application.ActiveDocument = second

        self.assertIs(bridge._target_document(), first)
        status = bridge.status()
        self.assertEqual(status["active_document_name"], "Second.cdr")
        self.assertEqual(status["target_document_name"], "First.cdr")


if __name__ == "__main__":
    unittest.main()
