"""Open-document collection fixtures for tests of the real targeting guard."""
from __future__ import annotations

from types import SimpleNamespace


class OpenDocuments:
    def __init__(self, *documents):
        self.items = list(documents)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]


def attach_open_document(bridge, document, app=None):
    if app is not None:
        bridge.app = app
    if bridge.app is None:
        bridge.app = SimpleNamespace(ActiveDocument=document)
    bridge.app.Documents = OpenDocuments(document)
    bridge._bind_target_document(document)
    return bridge.app
