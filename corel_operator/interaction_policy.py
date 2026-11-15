"""Cooperative editing policy; checked on the STA at native write boundaries.

CorelDRAW provides no atomic lock against human input. Background mode reserves
an inactive AI document and only permits audited explicit-object text edits.
It never promises cancellation of a COM call that has already entered CorelDRAW.
"""
from .errors import CorelBridgeError, ErrorCode

MODES = ('paused', 'exclusive', 'background_document')
BACKGROUND_WRITES = frozenset({'edit_text_range'})
CONTROL_METHODS = frozenset({'configure_editing_mode', 'use_active_document'})


class InteractionPolicyMixin:
    def configure_editing_mode(self, mode, confirm_exclusive=False):
        if type(mode) is not str or mode not in MODES or type(confirm_exclusive) is not bool:
            raise CorelBridgeError('Choose paused, exclusive or background_document.', ErrorCode.INVALID_ARGUMENT)
        if mode == 'exclusive' and not confirm_exclusive:
            raise CorelBridgeError('Exclusive editing requires confirming that you have stopped editing in CorelDRAW.',
                                   ErrorCode.CONFIRMATION_REQUIRED)
        reserved = None
        if mode == 'background_document':
            document = self._target_document()
            self._require_inactive_document(document)
            reserved = self._com_identity(document, strict=True)
        self._editing_mode = mode
        self._reserved_document_key = reserved
        return {'mode': mode, 'native_writes_paused': mode == 'paused',
                'document_session_id': self._document_session_id(self.target_doc) if self.target_doc is not None else None,
                'background_methods': sorted(BACKGROUND_WRITES),
                'requires_separate_document': mode == 'background_document',
                'in_flight_native_call_cancellable': False}

    def _require_inactive_document(self, document):
        active = self._active_document()
        if active is None or self._same_com_object(active, document, strict=True):
            raise CorelBridgeError('Keep the reserved AI document inactive and work in a different document.',
                                   ErrorCode.CONFIRMATION_REQUIRED)
        # Both documents must still belong to the bound application.
        if not any(self._same_com_object(active, item, strict=True)
                   for item in self._open_document_proxies(self.app)):
            raise CorelBridgeError('Could not verify the foreground document.', ErrorCode.NO_TARGET_DOCUMENT)

    def _prepare_interaction_operation(self, method, mutation):
        self._interaction_operation = None
        if method in CONTROL_METHODS:
            return
        if not mutation:
            # Read tools sometimes enter temporary unit/reference contexts.
            # Their write markers must obey the same paused/background policy.
            self._interaction_operation = method
            return
        self._operation_mutation_started = False
        self._interaction_operation = method
        self._check_interaction_write()

    def _check_interaction_write(self):
        method = getattr(self, '_interaction_operation', None) or 'embedded_native_operation'
        if self._native_pause_event is not None and self._native_pause_event.is_set():
            raise CorelBridgeError('Native editing was paused; remaining writes stopped.', ErrorCode.CONFIRMATION_REQUIRED)
        mode = self._editing_mode
        if mode == 'paused':
            raise CorelBridgeError('Native editing is paused. Configure an editing mode before applying changes.',
                                   ErrorCode.CONFIRMATION_REQUIRED)
        if mode == 'background_document':
            if method not in BACKGROUND_WRITES:
                raise CorelBridgeError('This command requires exclusive editing; background mode permits only reserved-document text-range edits.',
                                       ErrorCode.UNSUPPORTED_IN_PROFILE)
            document = self._target_document()
            if self._com_identity(document, strict=True) != self._reserved_document_key:
                raise CorelBridgeError('The reserved AI document changed; configure background mode again.',
                                       ErrorCode.NO_TARGET_DOCUMENT)
            self._require_inactive_document(document)
