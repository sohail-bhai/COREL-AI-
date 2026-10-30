from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from corel_operator.adapters import CorelX7Adapter
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode


class _FakeApplication:
    Visible = True
    ActiveDocument = None

    def __init__(self, major: int = 17) -> None:
        self.Version = f"Version {major}.0.0.491"
        self.VersionMajor = major
        self.VersionMinor = 0
        self.VersionBuild = 491


class _FakeClient:
    def __init__(self, get_results=None, dispatch_results=None) -> None:
        self.get_results = dict(get_results or {})
        self.dispatch_results = dict(dispatch_results or {})
        self.calls: list[tuple[str, str]] = []

    def GetActiveObject(self, prog_id: str):
        self.calls.append(("GetActiveObject", prog_id))
        result = self.get_results.get(prog_id, RuntimeError("not active"))
        if isinstance(result, BaseException):
            raise result
        return result

    def Dispatch(self, prog_id: str):
        self.calls.append(("Dispatch", prog_id))
        result = self.dispatch_results.get(prog_id, RuntimeError("not registered"))
        if isinstance(result, BaseException):
            raise result
        return result


def _fake_win32_modules(client: _FakeClient) -> dict[str, types.ModuleType]:
    package = types.ModuleType("win32com")
    client_module = types.ModuleType("win32com.client")
    client_module.GetActiveObject = client.GetActiveObject
    client_module.Dispatch = client.Dispatch
    package.client = client_module
    return {"win32com": package, "win32com.client": client_module}


class ConnectionStrategyTests(unittest.TestCase):
    def test_attaches_with_explicit_x7_prog_id_first(self) -> None:
        application = _FakeApplication()
        client = _FakeClient(
            get_results={CorelX7Adapter.EXPLICIT_PROG_ID: application}
        )
        with patch.dict(sys.modules, _fake_win32_modules(client)):
            bridge = CorelBridge()
            status = bridge.connect()

        self.assertEqual(
            client.calls,
            [("GetActiveObject", CorelX7Adapter.EXPLICIT_PROG_ID)],
        )
        self.assertEqual(status["prog_id_used"], CorelX7Adapter.EXPLICIT_PROG_ID)
        self.assertEqual(status["connection_mode"], "GetActiveObject")

    def test_dispatches_explicit_x7_after_active_lookup_fails(self) -> None:
        application = _FakeApplication()
        client = _FakeClient(
            dispatch_results={CorelX7Adapter.EXPLICIT_PROG_ID: application}
        )
        with patch.dict(sys.modules, _fake_win32_modules(client)):
            bridge = CorelBridge()
            status = bridge.connect()

        self.assertEqual(
            client.calls,
            [
                ("GetActiveObject", CorelX7Adapter.EXPLICIT_PROG_ID),
                ("GetActiveObject", CorelX7Adapter.GENERIC_PROG_ID),
                ("Dispatch", CorelX7Adapter.EXPLICIT_PROG_ID),
            ],
        )
        self.assertEqual(status["prog_id_used"], CorelX7Adapter.EXPLICIT_PROG_ID)
        self.assertEqual(status["connection_mode"], "Dispatch")

    def test_rejects_non_x7_application_from_all_candidates(self) -> None:
        wrong_application = _FakeApplication(major=18)
        client = _FakeClient(
            get_results={
                CorelX7Adapter.EXPLICIT_PROG_ID: wrong_application,
                CorelX7Adapter.GENERIC_PROG_ID: wrong_application,
            },
            dispatch_results={
                CorelX7Adapter.EXPLICIT_PROG_ID: wrong_application,
                CorelX7Adapter.GENERIC_PROG_ID: wrong_application,
            },
        )
        with patch.dict(sys.modules, _fake_win32_modules(client)):
            with self.assertRaises(CorelBridgeError) as context:
                CorelBridge().connect()

        self.assertEqual(context.exception.code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(context.exception.details["detected_major"], 18)


if __name__ == "__main__":
    unittest.main()
