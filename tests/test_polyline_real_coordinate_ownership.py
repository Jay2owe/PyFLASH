"""Retained native eligibility answers and complete nearest-point arrays."""
from pathlib import Path
import importlib.util
import json
import shutil
import warnings
import numpy as np
import pytest
from PyFLASH import utils
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'reproducibility/reference-sources/scientific-utilities'
REFERENCE=json.loads((ARCHIVE/'polyline-complex-coordinate-before-20261006-v2/frozen-before.json').read_text())['rows']

@pytest.mark.parametrize('row',REFERENCE,ids=lambda row:row['key'])
def test_native_real_plane_eligibility_and_owned_carriers(row):
    case=row['case']
    values=[[complex(v['real'],v['imaginary']) for v in array] for array in case['inputs']]
    carrier=case['carrier']
    if carrier=='tuple':values=list(map(tuple,values))
    elif carrier not in ('list','tuple'):
        values=[np.array(v,dtype=object if 'object' in carrier else getattr(np,carrier)) for v in values]
        if carrier=='readonly-object':
            for value in values:value.flags.writeable=False
    snapshots=[np.array(v,dtype=object,copy=True) for v in values]
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        if case['imaginary']:
            assert row['native_error']
            with pytest.raises(ValueError,match='must be real'):utils.points_to_polyline_distance(*values)
        else:
            assert row['native_error'] is None
            distances,closest=utils.points_to_polyline_distance(*values)
            np.testing.assert_array_equal(distances,row['expected']['distances'])
            np.testing.assert_array_equal(closest,row['expected']['closest_points'])
            assert distances.shape==(3,) and closest.shape==(3,2)
            assert distances.dtype==closest.dtype==np.float64
    for value,snapshot in zip(values,snapshots):np.testing.assert_array_equal(value,snapshot)

@pytest.mark.parametrize('name',['coordinate-amendment-manifest.json','polyline-complex-coordinate-before-20261006-v2/native-point.py'])
def test_changed_coordinate_evidence_refuses_before_geometry(tmp_path,monkeypatch,name):
    from reproducibility import scientific_utility_contract
    spec=importlib.util.spec_from_file_location('isolated_coordinate_contract',scientific_utility_contract.__file__)
    contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
    archive=tmp_path/'archive';shutil.copytree(ARCHIVE,archive)
    target=archive/name;target.write_bytes(target.read_bytes()+b'\n')
    contract.ARCHIVE=archive
    monkeypatch.setattr(utils,'points_to_polyline_distance',lambda *_:pytest.fail('Changed evidence reached geometry'))
    with pytest.raises(ValueError,match='evidence'):contract.validate(tmp_path/'output')
