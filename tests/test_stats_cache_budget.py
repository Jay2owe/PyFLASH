"""Repeated analyses must not retain an unbounded session cache."""
import numpy as np
import pytest
from PyFLASH import stats


def test_stats_result_cache_has_entry_and_memory_bounds():
    stats.clear_stats_cache()
    try:
        # These are complete stored results for the cache boundary; no
        # numerical algorithm is substituted or validated by this test.
        for index in range(160):
            stats._stats_cache[index]={'estimate':float(index)}
        assert len(stats._stats_cache)<=128
        stats._stats_cache['oversized']={'measurements':np.zeros(9*1024*1024,dtype=float)}
        assert stats._stats_cache.get('oversized') is None
        assert stats._stats_cache.retained_bytes<=64*1024**2
    finally:
        stats.clear_stats_cache()


@pytest.mark.slow
def test_actual_rank_caches_remain_within_both_memory_budgets():
    from PyFLASH import stats_extra
    stats_extra._mean_rank_null_cached.cache_clear()
    stats_extra._permutation_null_cached.cache_clear()
    try:
        for seed in range(10):
            answer = stats_extra.permutation_null([2]*20,n_resamples=5000,exact_max=0,seed=seed)
            assert answer['p'].shape==(5000,190)
            assert np.isfinite(answer['p']).all()
        assert stats_extra._permutation_null_cached.cache_bytes()<=64*1024**2
        assert stats_extra._mean_rank_null_cached.cache_bytes()<=64*1024**2
        assert stats_extra._permutation_null_cached.cache_info().currsize<10
    finally:
        stats_extra._mean_rank_null_cached.cache_clear()
        stats_extra._permutation_null_cached.cache_clear()
