from pathlib import Path
import json
import sys
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]

from PyFLASH import utils
REF=json.loads((ROOT/'reproducibility/reference-sources/scientific-utilities/polyline-integer-native-before-20261006-v3/frozen-before.json').read_text())['rows']
@pytest.mark.parametrize('row',REF,ids=lambda row:row['case']['key'])
@pytest.mark.parametrize('carrier',['list','tuple','array'])
def test_original_integer_geometry_uses_native_exact_points(row,carrier):
    case=row['case'];raw=[[point[axis] for point in case[name]] for name in ('points','line') for axis in (0,1)]
    if carrier=='tuple': values=list(map(tuple,raw))
    elif carrier=='array':
        dtype=np.uint64 if case['base']>np.iinfo(np.int64).max else np.int64
        values=[np.asarray(v,dtype=dtype) for v in raw]
        for value in values:value.flags.writeable=False
    else:values=raw
    snapshots=[list(v) for v in values]
    with np.errstate(all='raise'):distance,closest=utils.points_to_polyline_distance(*values)
    np.testing.assert_allclose(distance,row['expected_distances'],rtol=1e-12,atol=0.)
    np.testing.assert_array_equal(closest,row['expected_closest_points'])
    assert distance.dtype==closest.dtype==np.float64
    assert [list(v) for v in values]==snapshots
