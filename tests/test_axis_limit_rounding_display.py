from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]

from PyFLASH import utils
import numpy as np
import pytest

FIXTURE=(ROOT/'reproducibility/reference-sources/scientific-utilities/axis-limit-rounding-display-qualified-before-20261006-v2/frozen-before.json')
ROWS=json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['case']['key'])
def test_qualified_display_grid_and_unrepresentable_output_refusal(row):
    value=np.nan if row['case']['value']=='NaN' else row['case']['value']
    with np.errstate(all='raise'):
        if row['domain']=='refuse-unrepresentable-output':
            with pytest.raises(ValueError,match='floating-point range'):
                utils.round_up_to_nearest_5(value)
        else:
            actual=utils.round_up_to_nearest_5(value)
            assert actual==row['expected']
            if not np.isnan(value):assert actual>=value


@pytest.mark.parametrize('value',[np.inf,-np.inf,10**400])
def test_unrepresentable_input_refuses(value):
    with pytest.raises(ValueError):utils.round_up_to_nearest_5(value)


@pytest.mark.parametrize('value',['1.0',1+2j])
def test_nonnumeric_or_complex_axis_values_refuse(value):
    with pytest.raises(TypeError):utils.round_up_to_nearest_5(value)


@pytest.mark.parametrize('value',[0.,-0.,np.nan,None])
def test_legacy_zero_and_missing_bound_is_integer_zero(value):
    result=utils.round_up_to_nearest_5(value)
    assert type(result) is int and result==0


@pytest.mark.parametrize('carrier',[int,np.int32,np.int64,np.uint64,np.float32,np.float64])
def test_numeric_scalar_carriers_do_not_change_the_bound(carrier):
    assert utils.round_up_to_nearest_5(carrier(42))==45.


def test_float_decimal_boundary_does_not_expand_the_axis_unnecessarily():
    assert utils.round_up_to_nearest_5(.4)==.4
    assert utils.round_up_to_nearest_5(np.nextafter(.4,np.inf))==.45
