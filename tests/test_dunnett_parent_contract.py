"""Preserve legacy ordered posthoc outputs when sharing the complete control test."""
from pathlib import Path
import json
import math
import pytest
from PyFLASH import stats
from reproducibility.dunnett_contract import clean

SOURCE=Path(__file__).resolve().parents[1]/'reproducibility/reference-sources/dunnett/parent-frozen-before.json'
CASES=json.loads(SOURCE.read_text(encoding='utf-8'))['rows']

@pytest.mark.parametrize('case',CASES,ids=lambda row:row['key'])
def test_legacy_ordered_posthoc_fields_against_native_control_reports(case):
    actual=clean(stats._run_dunnett(case['groups'],case['comparisons']))
    assert len(actual)==len(case['expected'])
    for index,(a,b) in enumerate(zip(actual,case['expected'])):
        assert len(a)==len(b)
        assert all(x==y if isinstance(x,str) or isinstance(y,str) else
                   math.isclose(x,y,rel_tol=1e-9,abs_tol=0. if index==1 else 1e-12)
                   for x,y in zip(a,b))

def test_legacy_posthoc_calls_the_shared_control_report(monkeypatch):
    from PyFLASH import stats_extra
    original=stats_extra.dunnett_vs_control
    calls=[]
    def recorded(groups,**options):
        calls.append(options['control'])
        return original(groups,**options)
    monkeypatch.setattr(stats_extra,'dunnett_vs_control',recorded)
    stats._run_dunnett([[1,2,3],[2,4,6],[3,5,8]],['1-2','1-3'])
    assert calls==[0]
