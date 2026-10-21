from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]

from PyFLASH import utils
import numpy as np
import pytest

FIXTURE=(ROOT/'reproducibility/reference-sources/scientific-utilities/polyline-extreme-native-before-20261006-v2/frozen-before.json')
ROWS=json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['case']['key'])
@pytest.mark.parametrize('carrier',['list','tuple','array'])
def test_complete_native_extreme_arrays_and_output_refusals(row,carrier):
    case=row['case'];points=np.asarray(case['points']);line=np.asarray(case['line'])
    values=[points[:,0],points[:,1],line[:,0],line[:,1]]
    values=[v.tolist() if carrier=='list' else tuple(v) if carrier=='tuple' else v for v in values]
    with np.errstate(all='raise'):
        if row['domain']=='refuse-unrepresentable-output':
            with pytest.raises(ValueError,match='floating-point range'):
                utils.points_to_polyline_distance(*values)
        else:
            result=utils.points_to_polyline_distance(*values)
    if row['domain']=='finite-output':
        assert isinstance(result,tuple) and len(result)==2
        distance,closest=result
        if case['key']=='polyline-extreme.minimum-subnormal':
            np.testing.assert_array_equal(distance,row['expected_distances'])
            np.testing.assert_array_equal(closest,row['expected_closest_points'])
        else:
            np.testing.assert_allclose(distance,row['expected_distances'],rtol=1e-12,atol=0.)
            np.testing.assert_allclose(closest,row['expected_closest_points'],rtol=1e-12,atol=0.)
        assert distance.shape==(len(points),) and closest.shape==(len(points),2)
        assert distance.dtype==closest.dtype==np.float64


@pytest.mark.parametrize('values',[
    ([1],[1,2],[0,1],[0,1]),([1],[1],[0,1],[0]),
    ([[1]],[1],[0,1],[0,1]),([1],[[1]],[0,1],[0,1]),
    ([1],[1],[[0,1]],[0,1]),([1],[1],[0,1],[[0,1]]),
    ([np.nan],[1],[0,1],[0,1]),([1],[np.inf],[0,1],[0,1]),
    ([1],[1],[0,np.inf],[0,1]),([1],[1],[0,1],[0,np.nan]),
    ([1],[1],[0],[0]),([1],[1],[],[]),
])
def test_invalid_coordinate_arrays_refuse(values):
    with pytest.raises(ValueError):utils.points_to_polyline_distance(*values)


def test_empty_points_keep_complete_float_shapes():
    distances,closest=utils.points_to_polyline_distance([],[],[0,1],[0,1])
    assert distances.shape==(0,) and closest.shape==(0,2)
    assert distances.dtype==closest.dtype==np.float64


@pytest.mark.parametrize('scale',[1.,1e-200,1e200])
def test_readonly_arrays_and_first_segment_ties_are_preserved(scale):
    values=[np.array(v)*scale for v in ([0],[0],[-1,-1,1,1],[-2,2,2,-2])]
    before=[v.copy() for v in values]
    for value in values:value.flags.writeable=False
    distance,closest=utils.points_to_polyline_distance(*values)
    np.testing.assert_allclose(distance,[scale],rtol=1e-12,atol=0.)
    # Both side segments are equally near; preserve the first original segment.
    np.testing.assert_allclose(closest,[[-scale,0]],rtol=1e-12,atol=0.)
    for old,new in zip(before,values):np.testing.assert_array_equal(old,new)
