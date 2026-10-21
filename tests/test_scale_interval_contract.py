"""Bootstrap intervals preserve exact measurement differences and binary unit scales."""
from copy import deepcopy
import json
import pytest
from reproducibility import scale_interval_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_scale_and_close_measurement_interval(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_original_interval_requests_draws_answers_and_failures_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==86
    assert sum(row['original_failure'] for row in fixture['rows'])==58


def test_complete_interval_gate_requires_every_old_and_new_case():
    from reproducibility.run import inventory, _inventory_metadata, _inventory_execution_status
    from reproducibility.bootstrap_options_contract import cases as option_cases
    from reproducibility.finite_scale_contract import cases as unit_cases
    from reproducibility.scalar_input_contract import cases as shape_cases
    fixture=json.loads((contract.FIXTURE.parent/'bootstrap_reference.json').read_text(encoding='utf-8'))
    old={f"bootstrap.{row['kind']}.{row['case']}.{row['confidence']}" for row in fixture['rows']}
    old.update(row['key'] for row in option_cases());new={row['key'] for row in contract.cases()}
    old.update(row['key'] for row in unit_cases() if row['method']=='effect_ci')
    old.update(row['key'] for row in shape_cases() if row['method']=='effect_ci')
    owner='PyFLASH.stats_extra.effect_ci'
    metadata=_inventory_metadata()
    frozen=deepcopy(metadata)
    def status(keys):return _inventory_execution_status(metadata,keys)
    assert inventory(old|new)==status(old|new)
    assert next(row for row in status(old) if row['capability']==owner)['status']!='validated-complete-contract'
    rows={row['capability']:row for row in status(old|new)}
    assert rows[owner]['status']=='validated-complete-contract'
    for key in ('scale-interval.0','scale-interval.84','scale-interval.85'):
        partial={row['capability']:row for row in status((old|new)-{key})}
        assert partial[owner]['status']!='validated-complete-contract'
    assert metadata==frozen


def test_positive_interval_endpoint_cannot_be_accepted_as_zero():
    assert not contract.equal([0.,1.],[1e-200,1.])


def test_replacing_interval_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));payload['rows'][0]['expected']=[0.,0.]
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
