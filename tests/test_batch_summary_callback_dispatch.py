"""Choose legacy/current callback syntax without replaying internal failures."""
from types import SimpleNamespace

import pandas as pd
import pytest

from PyFLASH.batch import Batch


def owner(callback):
    batch = object.__new__(Batch)
    batch.name = 'callback fixture'
    batch.summaries = {}
    batch.experiment_list = [SimpleNamespace(summaries={}, summary=None, createSummary=callback)]
    return batch


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('method', ['export_excel', 'export_all_excel', 'export_IF_summary_excel'])
def test_public_export_preserves_internal_type_error_after_one_call(tmp_path, legacy, method):
    calls = []
    def modern(progress=False):
        calls.append(progress)
        raise TypeError('declared callback failure')
    def old():
        calls.append('legacy')
        raise TypeError('declared callback failure')
    batch = owner(old if legacy else modern)
    output = tmp_path / 'unwritten'
    options = (dict(behaviour=False, if_extended=False, if_summary=True,
                    unregistered_summary=False) if method != 'export_IF_summary_excel' else {})
    with pytest.raises(TypeError, match='declared callback failure'):
        getattr(batch, method)(save_path=output, **options)
    assert calls == ['legacy' if legacy else False]
    # The direct summary exporter may admit its destination before rebuilding;
    # no partial workbook or sidecar may be emitted by any failing route.
    assert not list(output.glob('*'))


@pytest.mark.parametrize('legacy', [False, True])
def test_successful_legacy_and_required_progress_callbacks_execute_once(legacy):
    calls = []
    expected = pd.DataFrame({'AnimalName': ['one'], 'Condition': ['Control'], 'CustomScore': [1.]})
    original = expected.copy(deep=True)
    def modern(*, progress):
        calls.append(progress)
        batch.experiment_list[0].summaries = {'SCN': expected}
    def old():
        calls.append('legacy')
        batch.experiment_list[0].summaries = {'SCN': expected}
    batch = owner(old if legacy else modern)
    summaries = batch._ensure_batch_summaries_for_export()
    assert calls == ['legacy' if legacy else False]
    assert summaries
    # Batch merges reserve object metrics for missing-experiment text sentinels.
    # Check that exact declared output dtype and preserve the original input.
    pd.testing.assert_frame_equal(batch.summary, original.astype({'CustomScore': object}))
    pd.testing.assert_frame_equal(expected, original)
