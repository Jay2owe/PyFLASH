"""Model records and plotted observations retain the supplied source identifiers."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_parent_record_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_all_model_report_fields_and_source_rows_match_independent_reference(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_original_model_rows_and_full_answers_are_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==1048
    assert sum(row['original_failure'] for row in fixture['rows'])==797
    assert fixture['scientific_parent_complete'] is False


def test_record_round_leaves_other_combined_parent_options_open():
    from reproducibility.run import inventory
    keys={r['key'] for r in contract.cases()}
    row=next(r for r in inventory(keys) if r['capability']=='PyFLASH.stats.multipleComparisons')
    assert row['status']=='partially-validated-contract'
    assert set(row['executed_subcontracts'].split(';'))==keys


def test_replacing_source_observation_id_fails_identity(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));fixture['rows'][0]['expected']['plotted_data'][0]['observation_id']='Unknown source'
    path=tmp_path/'altered.json';path.write_text(json.dumps(fixture),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
