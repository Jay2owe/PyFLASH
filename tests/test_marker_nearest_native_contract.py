"""Whole nearest-marker tables retain independent geometry and input ownership."""
from copy import deepcopy
import json
import pytest
from reproducibility import marker_nearest_contract as contract


def test_completion_requires_every_native_and_published_corroborating_output():
    keys=contract.required_keys(contract.CAPABILITY)
    native={item['key'] for item in contract.cases()}
    corroborating={key for key in keys if key.endswith('.sklearn')}
    assert len(native)==268
    assert len(corroborating)==216
    assert keys==native|corroborating
    assert contract.required_keys('PyFLASH.experiment.Experiment.processData')==set()
    assert contract.COMPLETE_CAPABILITIES=={contract.CAPABILITY}


@pytest.mark.parametrize('item',contract.cases(),ids=lambda row:row['key'])
def test_complete_nearest_marker_tables_match_native_r(item):
    original=deepcopy(item)
    actual,expected=contract.production(item)
    contract.equal(actual,expected)
    assert item==original


def test_native_reference_source_and_original_inputs_are_pinned():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==54


def test_changed_native_frozen_answer_is_refused(monkeypatch,tmp_path):
    payload=json.loads(contract.FROZEN.read_text(encoding='utf-8'))
    payload['rows'][0]['expected']['distances'][0]=999.
    changed=tmp_path/'frozen.json';changed.write_text(json.dumps(payload),encoding='utf-8')
    monkeypatch.setattr(contract,'FROZEN',changed)
    # The archive manifest authenticates its own original path; a substituted
    # fixture must also match the directly pinned frozen bytes.
    with pytest.raises(ValueError,match='frozen answers'):
        contract.check_identity()


@pytest.mark.parametrize('backend',['tree','fallback'])
def test_unrepresentable_nearest_distance_refuses_before_mutating_tables(backend):
    from PyFLASH import markers
    import pandas as pd
    item=deepcopy(contract.cases()[0]);item['backend']=backend
    case=item['case'];case['left']=[case['left'][0]];case['right']=[case['right'][0]]
    case['left'][0]['point']=[-1e308,0.,1.];case['right'][0]['point']=[1e308,0.,1.]
    left=object.__new__(markers.Antibody);left.name='L';left.df=contract.frame(case,'left','L')
    right=object.__new__(markers.Antibody);right.name='R';right.df=contract.frame(case,'right','R')
    originals=[obj.df.copy(deep=True) for obj in (left,right)]
    with contract.configuration(item),pytest.raises(ValueError,match='finite coordinate range'):
        left.find_closest_distances_between_markers(right)
    for obj,original in zip((left,right),originals,strict=True):
        pd.testing.assert_frame_equal(obj.df,original,check_exact=True)


@pytest.mark.parametrize('field',['coloc_counts','closest_counts','closest_flags','contains'])
def test_native_count_and_attribution_changes_are_refused_exactly(field):
    item=deepcopy(contract.cases()[0]);item['expected'][field][0]+=1e-10
    # Integer counts and attribution are exact contracts; a small mutation
    # must never be concealed by the distance comparison's relative tolerance.
    with pytest.raises(AssertionError):
        actual,expected=contract.production(item)
        contract.equal(actual,expected)
