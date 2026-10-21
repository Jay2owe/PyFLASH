"""Public option regressions on authenticated original CSVs and acquired values."""
from copy import deepcopy
from pathlib import Path
import shutil
import pytest
from reproducibility import marker_threshold_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def evidence_is_unchanged():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=[row['key'] for row in CASES])
def test_actual_constructor_import_and_nearest_controls(item):
    contract.production(item, {})


@pytest.mark.parametrize('resource', ['source-manifest.json', 'marker-threshold-before-20261007-v2/frozen-before.json', 'marker-import-threshold-before-20261007-v1/inputs/global-30.requested-50.Vol/Objects/A.csv'])
def test_changed_native_evidence_is_rejected(resource, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    target = copied / resource
    target.write_bytes(target.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['flag', 'measurement', 'column-order'])
def test_wrong_flags_changed_measurements_or_reordered_table_are_rejected(damage):
    item = next(row for row in CASES if row['kind'] == 'constructor' and row['reference']['case']['key'] == 'global-30.requested-50.Vol')
    observation = {}
    actual, _, _, _ = contract.production(item, observation)
    broken = deepcopy(actual)
    if damage == 'flag':
        broken['actual'][0] = 1
    elif damage == 'measurement':
        column = broken['table']['columns'].index('A_Volume')
        broken['table']['values'][0][column] = 99
    else:
        broken['table']['columns'] = list(reversed(broken['table']['columns']))
    with pytest.raises(AssertionError):
        contract.check_result(item, broken)


def test_changed_nearest_consumer_count_is_rejected():
    item = next(row for row in CASES if row['kind'] == 'nearest')
    actual, _, _, _ = contract.production(item, {})
    broken = deepcopy(actual)
    broken['actual']['closest_counts'][0] = 0
    with pytest.raises(AssertionError):
        contract.check_result(item, broken)


def test_legacy_marker_without_own_threshold_retains_global_fallback(monkeypatch):
    from types import SimpleNamespace
    from PyFLASH import markers
    from PyFLASH.config import Config
    import pandas as pd
    obj = object.__new__(markers.objectMarker)
    obj.name = 'A'
    obj.experiment = SimpleNamespace(data={})
    obj.df = pd.DataFrame({'Region': ['SCN1'] * 3, 'Animal Name': ['Subject1'] * 3,
                          'Volume (micron^3)': [2.] * 3, 'Surface': [4.] * 3,
                          'XM': [0., 1., 2.], 'YM': [1.] * 3, 'ZM': [1.] * 3,
                          'A_VolColoc_B': [10., 50., 70.]})
    monkeypatch.setattr(Config, 'THRESHOLD', 50)
    with pytest.warns(UserWarning, match='No Area Data'):
        obj.clean_df()
    assert obj.df['A_VolColocCountB'].tolist() == [0, 0, 1]
