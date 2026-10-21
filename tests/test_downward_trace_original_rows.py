from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]

from PyFLASH import utils
import numpy as np
import pytest

FIXTURE = (ROOT/'reproducibility/reference-sources/scientific-utilities/downward-trace-original-native-20261006-v1/frozen-before.json')
ROWS = json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row',ROWS,ids=lambda row: row['case']['key'])
@pytest.mark.parametrize('carrier',[list,tuple,np.array],ids=['list','tuple','array'])
def test_returned_path_selects_the_original_input_rows(row, carrier):
    points=np.asarray(row['case']['points'])
    x,y=carrier(points[:,0]),carrier(points[:,1])
    if not row['expected']:
        with pytest.raises(ValueError,match='downward path'):
            utils.trace_downward_nearest(x,y)
    else:
        result=utils.trace_downward_nearest(x,y)
        assert isinstance(result,tuple) and len(result)==3
        assert all(isinstance(item,np.ndarray) and item.ndim==1 for item in result)
        assert np.column_stack(result).tolist()==row['expected']
        np.testing.assert_array_equal(points[result[2]],np.column_stack(result[:2]))
    np.testing.assert_array_equal(x,points[:,0])
    np.testing.assert_array_equal(y,points[:,1])


@pytest.mark.parametrize('x,y',[([],[]),([1],[1]),([1,2],[1]),([[1,2]],[[1,2]]),([1,np.nan],[1,2]),([1,2],[1,np.inf])])
def test_invalid_coordinates_refuse_before_tracing(x,y):
    with pytest.raises(ValueError,match='paired finite'):
        utils.trace_downward_nearest(x,y)


def test_many_isolated_starts_refuse_without_recursive_stack_failure():
    x=np.arange(1200)
    y=np.zeros(1200)
    with pytest.raises(ValueError,match='downward path'):
        utils.trace_downward_nearest(x,y)
