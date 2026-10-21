"""The scientific observer must retain table values and native pandas metadata."""
from copy import deepcopy
from decimal import Decimal
import numpy as np
import pandas as pd
import pytest

from reproducibility import dataframe_table_protocol as transport


def frames():
    base = pd.DataFrame({'AnimalName': ['one', 'two', 'three'],
                         'Condition': ['B', 'A', 'B']})
    columns = {
        'int64': pd.Series([1, 7, 11], dtype='int64'),
        'float32': pd.Series([1.25, np.nan, 17.75], dtype='float32'),
        'nullable-integer': pd.Series([1, pd.NA, 11], dtype='Int64'),
        'nullable-float': pd.Series([1.25, pd.NA, 17.75], dtype='Float64'),
        'nullable-boolean': pd.Series([True, pd.NA, False], dtype='boolean'),
        'nullable-string': pd.Series(['one', pd.NA, 'three'], dtype='string'),
        'ordered-category': pd.Series(pd.Categorical(['high', None, 'low'],
            categories=['unused', 'low', 'high'], ordered=True)),
        'float32-category': pd.Series(pd.Categorical([1.25, None, 7.5],
            categories=pd.Index(np.array([1.25, 7.5, 99.], dtype='float32')))),
        'datetime': pd.Series(pd.to_datetime(['2024-01-02', None, '2024-02-03'])),
        'timezone': pd.Series(pd.to_datetime(['2024-01-02', None, '2024-02-03'], utc=True)),
        'duration': pd.Series(pd.to_timedelta([1, None, 17], unit='ns')),
        'decimal': pd.Series([Decimal('1.250'), None, Decimal('17.750')], dtype=object),
        'nested': pd.Series([[1, {'cells': [2, 7]}], {'@': 'native-data', 'pair': (3, 5)}, None], dtype=object),
        'array': pd.Series([np.array([1, 2], dtype='int16'), np.zeros((0, 2)),
                            np.array([[1.25, np.nan]])], dtype=object),
    }
    for name, column in columns.items():
        frame = base.copy(); frame['Measurement'] = column
        frame.attrs = {'units': 'declared', 'nested': {'values': np.array([1.25, np.nan])}}
        yield name, frame
    indexes = {
        'range': pd.RangeIndex(1, 7, 2, name='row'),
        'integer': pd.Index([17, 2, 11], name='row', dtype='int32'),
        'string': pd.Index(['third', 'first', 'second'], name='row', dtype='string'),
        'boolean': pd.Index([True, False, True], name='row'),
        'datetime-index': pd.date_range('2024-01-01', periods=3, tz='Europe/London', name='row'),
        'duration-index': pd.timedelta_range('1h', periods=3, freq='2h', name='row'),
        'category-index': pd.CategoricalIndex(['B', 'A', 'B'],
            categories=['unused', 'B', 'A'], ordered=True, name='row'),
        'multiple-index': pd.MultiIndex.from_tuples([('B', 17), ('A', 2), ('B', 11)],
            names=['group', 'row']),
    }
    for name, index in indexes.items():
        frame = base.copy(); frame.index = index; frame['Measurement'] = [1.25, 9.5, 17.75]
        yield name, frame
    empty = pd.DataFrame({'AnimalName': pd.Series([], dtype='string'),
                          'Condition': pd.Series([], dtype='category'),
                          'Measurement': pd.Series([], dtype='Float64')})
    yield 'empty-extension', empty
    yield 'no-columns', pd.DataFrame(index=pd.Index(['a', 'b'], name='row'))
    renamed = base.copy(); renamed.columns = pd.Index(renamed.columns, name='measurement-columns')
    yield 'named-columns', renamed


CASES = list(frames())


@pytest.mark.parametrize('frame', [frame for _, frame in CASES], ids=[name for name, _ in CASES])
def test_transport_preserves_native_table_and_index_metadata(frame):
    original = deepcopy(frame)
    packet = transport.table(frame)
    actual = transport.restore(packet)
    pd.testing.assert_frame_equal(actual, original, check_exact=True,
                                  check_index_type=True, check_column_type=True)
    assert transport.table(actual) == packet
    assert transport.table(frame) == transport.table(original)


def test_reserved_transport_keys_in_client_metadata_remain_literal():
    value = {'@': 'timestamp', 'iso': 'ordinary client metadata', 7: (pd.NA, Decimal('1.00'))}
    restored = transport.decode(transport.encode(value))
    assert restored['@'] == 'timestamp'
    assert restored['iso'] == 'ordinary client metadata'
    assert restored[7][0] is pd.NA
    assert restored[7][1].as_tuple() == Decimal('1.00').as_tuple()
