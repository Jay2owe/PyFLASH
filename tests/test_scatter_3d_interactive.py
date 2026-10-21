"""Browser views preserve native scatter data, group ranges and saved evidence."""
import builtins
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from PyFLASH import ConditionBuilder, from_dataframe
from PyFLASH import plotting as P


@pytest.fixture
def experiment(tmp_path):
    frame = pd.DataFrame(dict(AnimalName=['a', 'b', 'c', 'd', 'e', 'f', 'missing', 'excluded'],
        Group=['A'] * 3 + ['B'] * 3 + ['A', 'B'],
        x=[1, 2, 3, 101, 102, 103, np.nan, 'NOT_INCLUDED_IN_EXPERIMENT'],
        y=[2, 4, 6, 40, 50, 60, 7, 80], z=[3, 4, 5, 80, 90, 100, 8, 110]))
    return from_dataframe(frame, conditions=ConditionBuilder('Group').add('A').add('B').build(),
        condition_col='Group', animal_col='AnimalName', name='browser-scatter',
        fig_path=tmp_path / 'figures', data_path=tmp_path / 'data')


@pytest.mark.parametrize('combine', [False, True])
def test_interactive_preserves_points_subjects_and_native_group_ranges(experiment, combine):
    result = P.plot_scatter_3d(experiment, x='x', y='y', z='z', factor='Group',
        combine=combine, share_axes=False, interactive=True, save=False,
        column_labels={'x': 'Measured x', 'y': 'Measured y', 'z': 'Measured z'})
    figures = result['interactive']
    assert len(figures) == (1 if combine else 2)
    for figure, axis in zip(figures, result['scatter']):
        assert figure.layout.scene.xaxis.title.text == 'Measured x'
        assert tuple(figure.layout.scene.xaxis.range) == axis.get_xlim()
        assert tuple(figure.layout.scene.yaxis.range) == axis.get_ylim()
        assert tuple(figure.layout.scene.zaxis.range) == axis.get_zlim()
        for trace, collection in zip(figure.data, axis.collections):
            np.testing.assert_array_equal(np.column_stack([trace.x, trace.y, trace.z]),
                                         np.column_stack(collection._offsets3d))
            assert list(trace.customdata) == collection._pyflash_subjects
    assert sorted(subject for f in figures for t in f.data for subject in t.customdata) == list('abcdef')
    if not combine:
        assert figures[0].layout.scene.xaxis.range[1] < figures[1].layout.scene.xaxis.range[0]
    assert result['interactive_outputs'] == []
    assert not list(Path(experiment.fig_path).glob('**/*.html'))


def test_interactive_save_is_offline_and_embeds_the_actual_points(experiment):
    from PyFLASH.publication import extract_record, validate_artifact
    result = P.plot_scatter_3d(experiment, x='x', y='y', z='z', factor='Group',
                              interactive=True, save=True)
    assert len(result['interactive_outputs']) == 2
    for filename in result['interactive_outputs']:
        path = Path(filename)
        text = path.read_text(encoding='utf-8')
        assert path.suffix == '.html'
        assert 'Plotly.newPlot' in text
        assert '<script src="https://cdn.plot.ly' not in text
        assert validate_artifact(path).valid
        assert any(table.row_count == 3 for table in extract_record(path).data_tables)


def test_queued_interactive_calls_keep_filters_labels_and_explicit_ranges(experiment):
    result = P.plot_scatter_3d(experiment, x=['x', 'y'], y='y', z='z', factor='Group',
        filter_by=[('Group', 'A'), ('Group', 'B')], interactive=True, share_axes=False,
        save=False, x_range=(0, 200), column_labels={'x': 'X axis', 'y': 'Y axis'})
    for queued in result.values():
        assert len(queued) == 2
        for child in queued.values():
            assert len(child['interactive']) == 1
            assert tuple(child['interactive'][0].layout.scene.xaxis.range) == (0, 200)


def test_static_default_needs_no_plotly_and_interactive_missing_dependency_is_clear(experiment, monkeypatch):
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith('plotly'):
            raise ImportError('deliberately unavailable')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    result = P.plot_scatter_3d(experiment, x='x', y='y', z='z', save=False)
    assert 'interactive' not in result
    with pytest.raises(ImportError, match=r'PyFLASH-analysis\[interactive\]'):
        P.plot_scatter_3d(experiment, x='x', y='y', z='z', interactive=True, save=False)
    with pytest.raises(TypeError, match='interactive must be'):
        P.plot_scatter_3d(experiment, x='x', y='y', z='z', interactive='yes', save=False)


def test_normalization_sized_points_and_shared_queue_ranges_survive_native_save(experiment):
    result = P.plot_scatter_3d(experiment, x='x', y='y', z='z', factor='Group',
        size_by='y', normalize_z=True, interactive=True, save=True)
    for figure, axis in zip(result['interactive'], result['scatter']):
        trace, collection = figure.data[0], axis.collections[0]
        np.testing.assert_array_equal(trace.z, collection._offsets3d[2])
        np.testing.assert_allclose(trace.marker.size, np.sqrt(collection._sizes3d) * 96 / 72)
    queued = P.plot_scatter_3d(experiment, x=['x', 'y'], y='y', z='z',
                              combine=True, share_axes=True, interactive=True, save=False)
    assert queued[('x', 'y', 'z')]['interactive'][0].layout.scene.yaxis.range == queued[('y', 'y', 'z')]['interactive'][0].layout.scene.yaxis.range


def test_interactive_roi_queue_uses_the_selected_summary_and_labels(experiment, tmp_path):
    frame = experiment.summary.copy()
    other = frame.copy()
    other['y'] = pd.to_numeric(other['y']) + 500
    with_regions = from_dataframe(frame,
        conditions=ConditionBuilder('Group').add('A').add('B').build(),
        condition_col='Group', animal_col='AnimalName',
        summaries={'SCN': frame, 'OC': other},
        fig_path=tmp_path / 'regions', data_path=tmp_path / 'data')
    result = P.plot_scatter_3d(with_regions, x='x', y='y', z='z', roi=['SCN', 'OC'],
        interactive=True, combine=True, save=False, column_labels={'y': 'Y measurement'})
    assert set(result) == {'SCN', 'OC'}
    assert result['OC']['interactive'][0].layout.scene.yaxis.title.text == 'Y measurement'
    assert min(result['OC']['interactive'][0].data[0].y) >= 500
