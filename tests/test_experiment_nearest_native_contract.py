"""Actual experiment orchestration must retain every native ordered-pair array."""
import copy
import shutil
import pytest
from reproducibility import experiment_nearest_contract as contract

CASES=contract.cases()


def test_completion_requires_every_full_experiment_configuration():
    keys=contract.required_keys(contract.CAPABILITY)
    assert len(keys)==576
    assert keys=={item['key'] for item in CASES}
    assert contract.COMPLETE_CAPABILITIES=={contract.CAPABILITY}
    assert contract.required_keys('PyFLASH.experiment.Experiment.processData')==set()
    assert contract.required_keys('PyFLASH.experiment.Experiment.createSummary')==set()


@pytest.fixture(scope='module',autouse=True)
def original_native_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_whole_public_experiment_matches_all_native_pair_tables(item):
    contract.production(item)


@pytest.mark.parametrize('resource',['source-manifest.json','native-v1/frozen.json',
                                   'native-v1/native-r/experiment-nearest-ordered-pairs-queries.json'])
def test_changed_original_experiment_evidence_cannot_pass(resource,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    path=archive/resource;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(contract,'ARCHIVE',archive)
    with pytest.raises(ValueError,match='evidence'):contract.check_identity()


@pytest.mark.parametrize('field',['closest_flags','coloc_counts','contains','closest_counts'])
def test_noninteger_native_attribution_cannot_be_silently_cast(field):
    item=next(item for item in CASES if item['pairs'] and item['pairs'][0]['expected'][field])
    expected=copy.deepcopy(item['pairs'][0]['expected']);expected[field][0]=.5
    import pandas as pd
    with pytest.raises(ValueError,match='integers'):
        contract.add_reference_arrays(pd.DataFrame(),pd.DataFrame(),'L','R',expected)
