"""Track entry into native edit stages across nested bridge operations."""
from functools import wraps


def tracked_mutation(function):
    @wraps(function)
    def wrapper(self,*args,**kwargs):
        outermost=self._mutation_depth==0
        if outermost: self._operation_mutation_started=False
        previous_operation = getattr(self, '_interaction_operation', None)
        if outermost and previous_operation is None and hasattr(self, '_prepare_interaction_operation'):
            try:
                self._prepare_interaction_operation(function.__name__, True)
            except BaseException:
                self._interaction_operation = previous_operation
                raise
        try:
            # Also cover new embedded/subclass mutations that are not inherited
            # public commands. Nested calls preserve the outer write marker.
            with self._native_coordinator.operation(function.__name__,
                    allow_recovery=function.__name__ == 'use_active_document'):
                self._mutation_depth+=1
                try:
                    return function(self,*args,**kwargs)
                finally:
                    self._mutation_depth-=1
        finally:
            if outermost and hasattr(self, '_interaction_operation'):
                self._interaction_operation = previous_operation
    return wrapper
