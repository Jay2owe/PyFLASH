"""Identical scientific inputs must retain the same uncertainty on replay."""
import numpy as np
import pandas as pd
from PyFLASH import stats_extra
from PyFLASH.config import Config


def test_bootstrap_defaults_and_explicit_seed_reproduce_subject_uncertainty(monkeypatch):
    a = [1.2,2.4,2.9,3.8,5.1,6.3]
    b = [2.0,4.2,5.7,6.8,7.0,8.1]
    monkeypatch.setattr(Config,"EFFECT_CI_RANDOM_STATE",41)
    implicit = stats_extra.effect_ci(a,b,n_resamples=300)
    explicit = stats_extra.effect_ci(a,b,n_resamples=300,random_state=41)
    assert implicit == explicit == stats_extra.effect_ci(a,b,n_resamples=300)
    different = stats_extra.effect_ci(a,b,n_resamples=300,random_state=42)
    assert different != explicit
    assert np.isfinite(explicit).all()


def test_dunnett_reference_wrapper_reproduces_probability_integration():
    groups = [[1,2,3,4,5],[2,3,4,6,8],[3,4,5,7,9]]
    first = stats_extra.dunnett_vs_control(groups,random_state=17)
    second = stats_extra.dunnett_vs_control(groups,random_state=17)
    pd.testing.assert_frame_equal(first,second,check_exact=True)


def test_uncertainty_settings_invalidate_plot_statistics_cache(monkeypatch):
    from PyFLASH.stats import stats_cache_key
    original = stats_cache_key('Signal',['A','B'],None)
    monkeypatch.setattr(Config,'EFFECT_CI_RANDOM_STATE',901)
    changed_seed = stats_cache_key('Signal',['A','B'],None)
    assert changed_seed != original
    monkeypatch.setattr(Config,'EFFECT_CI_RESAMPLES',777)
    assert stats_cache_key('Signal',['A','B'],None) != changed_seed
