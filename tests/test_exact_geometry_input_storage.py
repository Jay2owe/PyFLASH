"""Original exact-input arithmetic controls, separate from native engine votes."""
import copy
import json

import numpy as np
import pytest

from PyFLASH import utils
from reproducibility.roi_analysis_contract import ARCHIVE

ROWS = json.loads((ARCHIVE / 'utility/before.json').read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row', ROWS, ids=lambda row: row['key'])
def test_original_mixed_storage_and_unbounded_integer_answers(row):
    original = copy.deepcopy(row)
    if row['operation'] == 'trace':
        carrier = row['key'].split('.')[1]; x, y = row['x'], row['y']
        if carrier == 'tuple': x, y = tuple(x), tuple(y)
        elif carrier == 'object': x, y = np.asarray(x, dtype=object), np.asarray(y, dtype=object)
        actual_x, actual_y, indices = utils.trace_downward_nearest(x, y)
        assert indices.tolist() == row['expected']
        # Convert only for comparison storage, keeping the original integer cells.
        np.testing.assert_array_equal(actual_x, np.asarray(row['x'], dtype=object)[indices])
        np.testing.assert_array_equal(actual_y, np.asarray(row['y'], dtype=object)[indices])
    else:
        values = np.asarray(row['values'], dtype=object)
        before = values.copy()
        actual = utils.moving_average(values, row['width'])
        assert actual.dtype == object and actual.tolist() == row['expected']
        np.testing.assert_array_equal(values, before)
    assert row == original
