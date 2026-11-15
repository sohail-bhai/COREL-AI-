"""Opt fake-COM fault tests into an exclusive apply window under tool schema v2."""
from corel_operator import server
from corel_operator.corel_bridge import CorelBridge


def exclusive_bridge(*args, **kwargs):
    bridge = CorelBridge(*args, **kwargs)
    bridge.configure_editing_mode('exclusive', True)
    return bridge


def exclusive_dispatcher(**kwargs):
    dispatcher = server.CorelDispatcher(**kwargs)
    if hasattr(dispatcher._bridge, 'configure_editing_mode'):
        dispatcher.call('configure_editing_mode', 'exclusive', True)
    return dispatcher
