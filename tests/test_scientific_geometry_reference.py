import hashlib
import shutil
from pathlib import Path
import pytest
from reproducibility import scientific_geometry_contract as contract

def test_retained_native_outputs_and_tie_differences(tmp_path):
    rows=contract.validate(tmp_path)
    assert len(rows)==233 and all(row['status']=='agree' for row in rows)
    paired=contract.read('polyline-native-comparison-v2/paired.json')
    assert sum(row['canonical_nearest_points_agree'] is False for row in paired)==6

def test_changed_native_answers_fail_before_production(tmp_path,monkeypatch):
    from PyFLASH import utils
    archive=tmp_path/'changed-reference'
    shutil.copytree(contract.ARCHIVE,archive)
    path=archive/'polyline-native-frozen-v1/shapely-answers.json'
    path.write_text(path.read_text()+'\n')
    monkeypatch.setattr(contract,'ARCHIVE',archive)
    monkeypatch.setattr(utils,'points_to_polyline_distance',lambda *_: pytest.fail('Changed evidence reached production'))
    with pytest.raises(ValueError,match='Retained native evidence changed'):
        contract.validate(tmp_path)

def test_wrong_nearest_point_fails_with_correct_distance(tmp_path,monkeypatch):
    from PyFLASH import utils
    original=utils.points_to_polyline_distance
    calls=[]
    def altered(*args):
        result=original(*args)
        calls.append(True)
        if len(calls)==1:
            return result[0],result[1]+100
        return result
    monkeypatch.setattr(utils,'points_to_polyline_distance',altered)
    rows=contract.validate(tmp_path)
    assert len(calls)==183 and len(rows)==233
    assert rows[0]['status']=='disagree'
    assert all(row['status']=='agree' for row in rows[1:])

def test_first_failure_keeps_later_comparisons_and_error(tmp_path,monkeypatch):
    from PyFLASH import utils
    import json
    original=utils.points_to_polyline_distance
    calls=[]
    def interrupted(*args):
        calls.append(True)
        if len(calls)==1: raise RuntimeError('retained-original-geometry-error')
        return original(*args)
    monkeypatch.setattr(utils,'points_to_polyline_distance',interrupted)
    rows=contract.validate(tmp_path)
    assert len(rows)==233 and rows[0]['status']=='disagree'
    assert all(row['status']=='agree' for row in rows[1:])
    saved=json.loads((tmp_path/'scientific-geometry-paired.json').read_text())['rows']
    assert len(saved)==233 and 'retained-original-geometry-error' in saved[0]['error']

def test_default_configuration_restored_after_conversion_failure(tmp_path,monkeypatch):
    from PyFLASH import utils
    from PyFLASH.config import Config
    prior=Config.PIXEL_SIZE
    def failing(*_,**__): raise ValueError('retained-original-conversion-error')
    monkeypatch.setattr(utils,'convert_microns_to_pixels',failing)
    rows=contract.validate(tmp_path)
    assert len(rows)==233 and sum(row['status']=='disagree' for row in rows)==25
    assert Config.PIXEL_SIZE==prior
