"""Whole public region-label state, original failures and coverage boundaries."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import region_assignment_contract as reference


@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_whole_region_assignment_matches_all_predeclared_state_and_tables(row,tmp_path):
    reference.production(row,tmp_path)


@pytest.mark.parametrize('name',['literal-reference.py','table-transport.py','original-v1/run.json',
    'original-v2/reasoned-declaration-amendment.json','original-v3/declared-before.json',
    'first-private/run.json','qualified-private/run.json','qualified-private/paired.json'])
def test_changed_region_evidence_is_refused(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ARCHIVE,archive)
    target=archive/name;target.write_bytes(target.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError):reference.check_identity()


def test_changed_answer_is_refused_before_the_public_call(tmp_path,monkeypatch):
    row=deepcopy(reference.cases()[0]);row['expected']['aliases']='forged'
    helper=reference._helper(str((reference.ARCHIVE/'literal-reference.py').resolve()))
    def forbidden(*args,**kwargs):raise RuntimeError('public call must not execute')
    monkeypatch.setattr(helper,'production',forbidden)
    with pytest.raises(AssertionError,match='Declared whole region-assignment'):reference.production(row,tmp_path)
    assert not list(tmp_path.iterdir())


def test_whole_region_assignment_requires_every_declared_branch_in_both_classes():
    reference.assert_parameter_inventory()
    for name in reference.CAPABILITIES:
        keys=reference.required_keys(name)
        assert len(keys)==156
        assert any('.assign_scn_number.' in key for key in keys)
        assert any('.refuse-' in key for key in keys)
        assert any(key.endswith('.3') for key in keys)
        assert any('.named-column-axis.' in key for key in keys)
    assert reference.required_keys('PyFLASH.experiment.Experiment.processData')==set()
    assert reference.required_keys('PyFLASH.experiment.Experiment.createSummary')==set()


def test_region_assignment_inventory_closes_only_executed_functional_contracts():
    from reproducibility import run
    from reproducibility.validation_registry import FAMILIES
    assert FAMILIES['whole-region-assignment']=='reproducibility.region_assignment_contract'
    keys={row['key'] for row in reference.cases()}
    complete={row['capability']:row for row in run.inventory(keys) if row['capability'] in reference.CAPABILITIES}
    assert set(complete)==reference.CAPABILITIES
    assert all(row['status']=='validated-complete-contract' and row['kind']=='functional-whole-region-assignment' for row in complete.values())
    absent={row['capability']:row for row in run.inventory(keys-{min(reference.required_keys(next(iter(reference.CAPABILITIES))))}) if row['capability'] in reference.CAPABILITIES}
    assert sum(row['status']=='validated-complete-contract' for row in absent.values())==1
    assert all(row['status']!='validated-complete-contract' for row in run.inventory(keys) if row['capability'] not in reference.CAPABILITIES)
