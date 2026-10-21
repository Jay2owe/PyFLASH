"""Borrowed collector ownership on complete parent reports and failure."""
from copy import deepcopy
import pytest
from PyFLASH import report
from reproducibility import comparison_parent_record_adapter as adapter,comparison_parent_record_contract as contract

@pytest.mark.parametrize('case',contract.cases()[:3],ids=lambda row:row['key'])
def test_complete_parent_report_preserves_exact_borrowed_collector(case,monkeypatch):
    caller={'active':True,'records':[{'sentinel':i} for i in range(20)],'origins':[None]*20,'metadata':{'preserved':True}}
    before=deepcopy(caller);monkeypatch.setattr(report,'_STATE',caller)
    assert contract.equal(adapter.production(case),case['expected'])
    assert report._STATE is caller and caller==before

def test_parent_failure_preserves_every_borrowed_object(monkeypatch):
    caller={'active':True,'records':[{'sentinel':object()}],'origins':[None]}
    records=caller['records'];sentinel=records[0]['sentinel'];monkeypatch.setattr(report,'_STATE',caller)
    def fail(case):raise RuntimeError('owned failure')
    monkeypatch.setattr(adapter.parent,'production',fail)
    with pytest.raises(RuntimeError,match='owned failure'):adapter.production(contract.cases()[0])
    assert report._STATE is caller and caller['records'] is records and records[0]['sentinel'] is sentinel
