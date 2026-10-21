"""Bound retained analysis caches by entry count and estimated Python memory."""
from collections import OrderedDict, namedtuple
from collections.abc import MutableMapping
from functools import wraps
from fractions import Fraction as _Fraction
from threading import RLock
import sys
import types

DEFAULT_MAX_BYTES = 64*1024**2


def retained_size(value, *, stop_after):
    """Size a retained object graph once; exclude shared interpreter globals.

    This measures Python objects and owned scientific buffers, not process
    allocator overhead or temporary memory used to calculate a result.
    """
    pending,seen,total = [value],set(),0
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        total += sys.getsizeof(item)
        if total>stop_after:
            return total
        if isinstance(item,dict):
            pending.extend(item.keys()); pending.extend(item.values())
        elif isinstance(item,_Fraction):
            pending.extend((item.numerator,item.denominator))
        elif isinstance(item,(list,tuple,set,frozenset)):
            pending.extend(item)
        elif isinstance(item,memoryview):
            pending.append(item.obj)
        elif hasattr(item,'__array_interface__'):
            base = getattr(item,'base',None)
            if base is not None:
                pending.append(base)
            if getattr(getattr(item,'dtype',None),'hasobject',False):
                pending.extend(item.flat)
        elif type(item).__module__.startswith('pandas.'):
            # pandas.__sizeof__ already includes deep measurement/index bytes.
            continue
        elif isinstance(item,types.FunctionType):
            pending.extend(cell.cell_contents for cell in item.__closure__ or ())
            pending.append(item.__defaults__)
        if not isinstance(item,(type,types.ModuleType)) and hasattr(item,'__dict__'):
            pending.append(vars(item))
    return total


class BoundedCache(MutableMapping):
    """Least-recently-used retained answers; oversized results are never cached."""
    def __init__(self,max_entries=128,max_bytes=DEFAULT_MAX_BYTES):
        self.max_entries,self.max_bytes = max_entries,max_bytes
        self._entries = OrderedDict()
        self._sizes = {}
        self._bytes = 0
        self._lock = RLock()

    @property
    def retained_bytes(self):
        with self._lock:
            return self._bytes

    def __getitem__(self,key):
        with self._lock:
            answer = self._entries[key]
            self._entries.move_to_end(key)
            return answer

    def __setitem__(self,key,value):
        try:
            size = retained_size((key,value),stop_after=self.max_bytes)
        except Exception:
            # A result with unsupported memory introspection remains usable;
            # omitting its cache entry must not break a completed analysis.
            size = self.max_bytes+1
        with self._lock:
            if key in self._entries:
                self.__delitem__(key)
            if size>self.max_bytes or self.max_entries<=0:
                return
            while self._entries and (len(self._entries)>=self.max_entries or self._bytes+size>self.max_bytes):
                self.__delitem__(next(iter(self._entries)))
            self._entries[key] = value
            self._sizes[key] = size
            self._bytes += size

    def __delitem__(self,key):
        with self._lock:
            del self._entries[key]
            self._bytes -= self._sizes.pop(key)

    def __iter__(self):
        with self._lock:
            return iter(tuple(self._entries))

    def __len__(self):
        with self._lock:
            return len(self._entries)

    def clear(self):
        with self._lock:
            self._entries.clear(); self._sizes.clear(); self._bytes=0


def bounded_lru_cache(*,maxsize=64,max_bytes=DEFAULT_MAX_BYTES):
    """Memoize pure analysis functions with the usual cache_info/clear surface."""
    def decorate(function):
        cache = BoundedCache(maxsize,max_bytes)
        lock = RLock()
        hits=misses=generation=0
        info = namedtuple('CacheInfo','hits misses maxsize currsize')
        @wraps(function)
        def run(*args,**kwargs):
            nonlocal hits,misses
            key = (args,tuple(sorted(kwargs.items())))
            with lock:
                try:
                    result = cache[key]
                except KeyError:
                    misses+=1
                    started_generation=generation
                else:
                    hits+=1
                    return result
            result = function(*args,**kwargs)
            with lock:
                if generation==started_generation:
                    cache[key] = result
            return result
        def clear():
            nonlocal hits,misses,generation
            with lock:
                cache.clear(); hits=misses=0; generation+=1
        def cache_info():
            with lock:
                return info(hits,misses,maxsize,len(cache))
        run.cache_clear = clear
        run.cache_info = cache_info
        run.cache_bytes = lambda:cache.retained_bytes
        return run
    return decorate
