from __future__ import annotations

import threading
import unittest

from corel_operator import server


class _FakeBridge:
    def thread_id(self) -> int:
        return threading.get_ident()

    def echo(self, value):
        return value

    def fail(self):
        raise ValueError("expected test failure")


class DispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_bridge_class = server.CorelBridge
        server.CorelBridge = _FakeBridge
        self.dispatcher = server.CorelDispatcher()

    def tearDown(self) -> None:
        self.dispatcher.close()
        server.CorelBridge = self.original_bridge_class

    def test_calls_execute_on_dedicated_worker_thread(self) -> None:
        calling_thread = threading.get_ident()
        worker_thread = self.dispatcher.call("thread_id")

        self.assertNotEqual(worker_thread, calling_thread)
        self.assertEqual(worker_thread, self.dispatcher._thread.ident)

    def test_arguments_and_results_are_dispatched(self) -> None:
        value = {"safe": True}
        self.assertIs(self.dispatcher.call("echo", value), value)

    def test_worker_exceptions_propagate_to_caller(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected test failure"):
            self.dispatcher.call("fail")

    def test_close_is_idempotent_and_prevents_new_calls(self) -> None:
        self.dispatcher.close()
        self.dispatcher.close()

        with self.assertRaisesRegex(RuntimeError, "worker is not running"):
            self.dispatcher.call("echo", "value")


if __name__ == "__main__":
    unittest.main()
