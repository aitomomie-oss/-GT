"""Conservative process-wide budget shared across screens and client instances."""
import hashlib
import threading
import time
from collections import deque
from src.market_data.base import MarketDataError


class RequestBudget:
    def __init__(self,clock=time.monotonic,limit=5,window=60):
        self.clock=clock;self.limit=limit;self.window=window;self.lock=threading.Lock();self.states={}

    def _identity(self,key): return hashlib.sha256(key.encode('utf-8')).digest()

    def acquire(self,key):
        ident=self._identity(key)
        with self.lock:
            now=self.clock()
            # Bound memory if many keys are replaced in a long running process.
            for old,state in list(self.states.items()):
                if state['blocked']<=now and (not state['times'] or now-state['times'][-1]>=self.window): self.states.pop(old)
            state=self.states.setdefault(ident,{'times':deque(),'blocked':0})
            while state['times'] and now-state['times'][0]>=self.window: state['times'].popleft()
            if now<state['blocked'] or len(state['times'])>=self.limit: raise MarketDataError('rate_limit')
            state['times'].append(now)

    def defer(self,key,seconds=60):
        try: seconds=max(60,min(3600,int(seconds)))
        except (ValueError,TypeError): seconds=60
        with self.lock:
            state=self.states.setdefault(self._identity(key),{'times':deque(),'blocked':0})
            state['blocked']=max(state['blocked'],self.clock()+seconds)


BUDGET=RequestBudget()
