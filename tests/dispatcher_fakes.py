"""Opt fake-COM fault tests into an exclusive apply window under tool schema v2."""
from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from contextlib import nullcontext


class FakeCoordinator:
    """Existing COM fixtures isolate native failures from durable process tests."""
    _depth = 1
    def operation(self, *args, **kwargs):
        return nullcontext()
    def mark_write(self):
        pass


def exclusive_bridge(*args, **kwargs):
    kwargs.setdefault('native_coordinator', FakeCoordinator())
    bridge = CorelBridge(*args, **kwargs)
    bridge.configure_editing_mode('exclusive', True)
    return bridge


def exclusive_dispatcher(**kwargs):
    dispatcher = server.CorelDispatcher(**kwargs)
    if hasattr(dispatcher._bridge, 'configure_editing_mode'):
        dispatcher.call('configure_editing_mode', 'exclusive', True)
    return dispatcher
