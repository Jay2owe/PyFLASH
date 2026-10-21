"""Numerical helpers defer optional engine loading and retain patch ownership."""
from pathlib import Path
import subprocess,sys

def test_numeric_stats_import_defers_model_and_posthoc_engines():
    root=Path(__file__).resolve().parents[1]
    code='''import sys
from PyFLASH import stats
assert not {'matplotlib.pyplot','statsmodels.api','statsmodels.formula.api','scikit_posthocs','seaborn'} & set(sys.modules)
assert stats.cauchy_combination_test([.5]) == .5
assert not {'matplotlib.pyplot','statsmodels.api','statsmodels.formula.api','scikit_posthocs','seaborn'} & set(sys.modules)
'''
    result=subprocess.run([sys.executable,str(root/'reproducibility/check_bootstrap.py'),'-c',code],
                          cwd=root,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr

def test_external_dependency_access_and_monkeypatches_share_the_same_object(monkeypatch):
    from PyFLASH import stats
    from statsmodels.formula.api import ols
    assert stats.ols is ols
    sentinel=object()
    monkeypatch.setattr(stats,'ols',sentinel)
    assert stats._dependency('ols') is sentinel

def test_unknown_statistics_attribute_remains_an_attribute_error():
    from PyFLASH import stats
    import pytest
    with pytest.raises(AttributeError):getattr(stats,'unregistered_engine')
