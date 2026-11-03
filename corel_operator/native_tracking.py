"""Track entry into native edit stages across nested bridge operations."""
from functools import wraps


def tracked_mutation(function):
    @wraps(function)
    def wrapper(self,*args,**kwargs):
        outermost=self._mutation_depth==0
        if outermost: self._operation_mutation_started=False
        self._mutation_depth+=1
        try: return function(self,*args,**kwargs)
        finally: self._mutation_depth-=1
    return wrapper
