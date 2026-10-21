from pathlib import Path
import importlib.util
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
from PyFLASH import utils
from PyFLASH.config import Config
import pytest

MODULE=ROOT/'reproducibility/scientific_utility_contract.py'


@pytest.fixture
def contract():
    spec=importlib.util.spec_from_file_location('isolated_utility_contract_guards',MODULE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_all_native_and_declared_policy_envelopes(contract,tmp_path):
    rows=contract.validate(tmp_path)
    assert len(rows)==451 and all(row['status']=='agree' for row in rows)
    assert len({row['contract'] for row in rows})==451
    assert 'PyFLASH.utils.trace_downward_nearest' not in contract.COMPLETE_CAPABILITIES
    assert 'PyFLASH.utils.round_up_to_nearest_5' not in contract.COMPLETE_CAPABILITIES
    assert 'PyFLASH.utils.moving_average' not in contract.COMPLETE_CAPABILITIES


@pytest.mark.parametrize('manifest',[True,False])
def test_changed_native_evidence_refuses_before_calculating(contract,tmp_path,monkeypatch,manifest):
    archive=tmp_path/'changed';shutil.copytree(contract.ARCHIVE,archive)
    target=archive/('source-manifest.json' if manifest else 'moving-average-window-means-before-20261006-v1/frozen-before.json')
    target.write_text(target.read_text()+'\n')
    monkeypatch.setattr(contract,'ARCHIVE',archive)
    monkeypatch.setattr(utils,'add_coloc_percentages',lambda *_:pytest.fail('Changed evidence reached production'))
    with pytest.raises(ValueError,match='evidence'):contract.validate(tmp_path/'output')


def test_correct_percentage_numbers_with_wrong_object_ownership_fail(contract,tmp_path,monkeypatch):
    original=utils.add_coloc_percentages
    monkeypatch.setattr(utils,'add_coloc_percentages',lambda frame:original(frame).copy(deep=True))
    rows=contract.validate(tmp_path)
    assert rows[0]['status']=='disagree'
    paired=json.loads((tmp_path/'scientific-utility-paired.json').read_text())['rows']
    assert paired[0]['production']['returned_original'] is False
    assert paired[0]['reference']['returned_original'] is True


def test_first_runtime_error_keeps_later_native_comparisons(contract,tmp_path,monkeypatch):
    original=utils.add_coloc_percentages;calls=[]
    def failed_once(frame):
        calls.append(True)
        if len(calls)==1:raise RuntimeError('retained-first-utility-error')
        return original(frame)
    monkeypatch.setattr(utils,'add_coloc_percentages',failed_once)
    rows=contract.validate(tmp_path)
    assert len(rows)==451 and rows[0]['status']=='disagree'
    assert all(row['status']=='agree' for row in rows[1:])
    paired=json.loads((tmp_path/'scientific-utility-paired.json').read_text())['rows']
    assert 'retained-first-utility-error' in paired[0]['error'] and len(paired)==451


def test_wrong_boundary_point_fails_with_unchanged_distances(contract,tmp_path,monkeypatch):
    original=utils.points_to_polyline_distance
    def wrong(*args):
        distance,closest=original(*args)
        return distance,closest+1
    monkeypatch.setattr(utils,'points_to_polyline_distance',wrong)
    rows=contract.validate(tmp_path)
    first=next(row for row in rows if row['contract'].startswith('scientific-utility.points_to_polyline_distance.'))
    assert first['status']=='disagree'
    paired=json.loads((tmp_path/'scientific-utility-paired.json').read_text())['rows']
    item=next(row for row in paired if row['key']==first['contract'])
    assert item['production'] is not None and item['reference'] is not None


@pytest.mark.parametrize('name,attribute',[('convert_microns_to_pixels','PIXEL_SIZE'),('adjust_for_volumemm','SECTION_THICKNESS_UM')])
def test_native_failure_restores_caller_calibration(contract,tmp_path,monkeypatch,name,attribute):
    previous=getattr(Config,attribute)
    def fail(*_,**__):raise RuntimeError('retained-calibration-call-error')
    monkeypatch.setattr(utils,name,fail)
    rows=contract.validate(tmp_path)
    assert len(rows)==451 and any(row['status']=='disagree' for row in rows)
    assert getattr(Config,attribute)==previous
