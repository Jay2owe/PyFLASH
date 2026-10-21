"""Exact rank arithmetic follows the shared cache memory budget."""
from fractions import Fraction
import sys
from PyFLASH._cache import retained_size,bounded_lru_cache,DEFAULT_MAX_BYTES

def test_owned_fraction_integers_are_part_of_retained_size():
    value=Fraction(2**4096+1,2**4096-1)
    expected=sys.getsizeof(value)+sys.getsizeof(value.numerator)+sys.getsizeof(value.denominator)
    assert retained_size(value,stop_after=10000)==expected

def test_large_fraction_results_are_returned_without_retaining_them():
    calls=[]
    @bounded_lru_cache(maxsize=2,max_bytes=1024)
    def calculate(key):
        calls.append(key);return Fraction(2**4096+1,2**4096-1)
    assert calculate(1)==calculate(1)
    assert calls==[1,1]
    assert calculate.cache_info().currsize==0 and calculate.cache_bytes()==0

def test_exact_rank_strengths_use_the_shared_memory_owner():
    from PyFLASH import stats
    cache=stats._exact_rank_null_strengths
    assert callable(getattr(cache,'cache_bytes',None))
    cache.cache_clear()
    first=stats.runKW([[1,2],[3,4],[5,6]],['1-3','1-2'],{},posthoc_correction='Westfall-Young')[0]
    second=stats.runKW([[1,2],[3,4],[5,6]],['1-3','1-2'],{},posthoc_correction='Westfall-Young')[0]
    assert first==second==[4/90,10/90]
    assert 0<cache.cache_bytes()<=DEFAULT_MAX_BYTES
    assert cache.cache_info().maxsize==4
