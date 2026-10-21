"""Optional absence is distinct from an actual behavior-table read failure."""
import pytest
from PyFLASH.batch import Batch


METHODS = ['export_behavior_summary_excel', 'export_excel', 'export_all_excel']


def options(method):
    return dict(if_summary=False, if_extended=False, unregistered_summary=False) if method != 'export_behavior_summary_excel' else {}


@pytest.mark.parametrize('method', METHODS)
@pytest.mark.parametrize('error_type', [RuntimeError, OSError, KeyboardInterrupt, KeyError, AttributeError])
def test_real_behavior_read_failure_propagates_without_partial_outputs(tmp_path, method, error_type):
    error = error_type('declared behavior table read failure')
    class FailedTable:
        @property
        def df(self):
            raise error
    batch = object.__new__(Batch)
    batch.data = {'Behaviour': FailedTable()}
    output = tmp_path / 'unwritten'
    with pytest.raises(error_type) as caught:
        getattr(batch, method)(save_path=output, **options(method))
    assert caught.value is error
    assert not list(output.glob('*'))


@pytest.mark.parametrize('method', METHODS)
def test_optional_absent_behavior_remains_an_empty_result(tmp_path, method):
    batch = object.__new__(Batch)
    batch.data = {}
    result = getattr(batch, method)(save_path=tmp_path, **options(method))
    assert result == (None if method == 'export_behavior_summary_excel' else [])
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('method', METHODS)
def test_optional_absent_dataframe_attribute_remains_an_empty_result(tmp_path, method):
    batch = object.__new__(Batch)
    batch.data = {'Behaviour': object()}
    result = getattr(batch, method)(save_path=tmp_path, **options(method))
    assert result == (None if method == 'export_behavior_summary_excel' else [])
    assert not list(tmp_path.iterdir())
