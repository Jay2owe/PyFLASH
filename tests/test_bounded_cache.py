"""Retained cache budgets, sharing, eviction, and concurrent clear boundaries."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import sys
import numpy as np
from PyFLASH._cache import BoundedCache,bounded_lru_cache,retained_size


def test_reads_refresh_lru_order_and_replacements_release_old_size():
    cache = BoundedCache(max_entries=2,max_bytes=4096)
    cache['first']={'value':1}
    cache['second']={'value':2}
    assert cache['first']=={'value':1}
    cache['third']={'value':3}
    assert list(cache)==['first','third'] and cache.get('second') is None
    cache['first']=1
    assert cache.retained_bytes==sum(retained_size((k,cache[k]),stop_after=4096) for k in list(cache))
    cache.clear()
    assert cache.retained_bytes==0 and len(cache)==0


def test_memory_limit_evicts_a_small_cache_before_the_entry_limit():
    cache = BoundedCache(max_entries=100,max_bytes=4096)
    for i in range(20):
        cache[i]=np.full(64,i,dtype=float)
    assert 1<len(cache)<20
    assert cache.retained_bytes<=4096
    assert cache.get(0) is None and (cache[19]==19).all()
    cache[19]=np.zeros(4096)
    assert cache.get(19) is None and cache.retained_bytes<=4096


def test_size_follows_array_owners_and_counts_cycles_and_aliases_once():
    owner = np.arange(1024,dtype=float)
    view = owner[:1]
    assert retained_size(view,stop_after=100000)>=owner.nbytes
    repeated = [owner,owner]
    repeated.append(repeated)
    expected = sys.getsizeof(repeated)+sys.getsizeof(owner)
    assert retained_size(repeated,stop_after=100000)==expected


def test_uncacheable_result_remains_returned_and_recomputes():
    class CannotSize:
        def __sizeof__(self):
            raise ValueError('No retained-memory protocol')
    calls=[]
    @bounded_lru_cache(maxsize=2,max_bytes=1024)
    def calculate(key):
        calls.append(key)
        return CannotSize()
    assert isinstance(calculate(1),CannotSize) and isinstance(calculate(1),CannotSize)
    assert calls==[1,1] and calculate.cache_info().currsize==0


def test_clear_during_calculation_does_not_restore_an_old_entry():
    entered,finish = Event(),Event()
    @bounded_lru_cache(maxsize=2)
    def calculate(key):
        entered.set()
        assert finish.wait(10)
        return key*2
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(calculate,3)
        assert entered.wait(10)
        calculate.cache_clear()
        finish.set()
        assert pending.result(timeout=10)==6
    assert calculate.cache_info().currsize==0 and calculate.cache_bytes()==0


def test_repeated_hits_keep_results_and_have_bounded_cache_info():
    calls=[]
    @bounded_lru_cache(maxsize=2,max_bytes=4096)
    def calculate(key):
        calls.append(key)
        return np.array([key,key+1])
    assert (calculate(1)==[1,2]).all()
    assert (calculate(1)==[1,2]).all()
    calculate(2); calculate(3)
    assert calls==[1,2,3]
    assert calculate.cache_info().hits==1 and calculate.cache_info().misses==3
    assert calculate.cache_info().currsize==2 and calculate.cache_bytes()<=4096
