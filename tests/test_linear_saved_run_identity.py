"""Different scientific requests must never silently reuse one saved run."""
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from PyFLASH import from_dataframe
from PyFLASH.pipeline import linear_model
from reproducibility import linear_parent_contract as contract


@pytest.fixture
def native_request(tmp_path):
    fixture = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    row = next(row for row in fixture['covariance_rows']
               if row['case']['key'] == 'linear-parent.HAC.lag-0.correction-false')
    case = deepcopy(row['case'])
    frame = pd.DataFrame(case['data'])
    for name, levels in case['factor_levels'].items():
        frame[name] = pd.Categorical(frame[name], categories=levels)
    experiment = from_dataframe(frame, group_col=case['group'], fig_path=str(tmp_path))
    parameters = dict(dependent_variables=case['endpoints'], predictors=case['predictors'],
        group=case['group'], categorical=case['categorical'], reference_levels=case['reference_levels'],
        cov_type=case['cov_type'], cov_kwds=case['cov_kwds'], alpha=case['alpha'],
        fdr_method=case['fdr_method'], fdr_family=case['fdr_family'],
        covariate_profile=case['profile'], adjusted_mean_weights=case['weights'],
        adjusted_mean_p_adjust=case['adjusted_mean_p_adjust'],
        adjusted_mean_p_family=case['adjusted_mean_p_family'],
        save=True, if_exists='skip', montage=False, plot_coefficients=False,
        plot_adjusted_means=False, verbose=False)
    return experiment, parameters, fixture


def test_new_covariance_request_saves_distinct_independently_qualified_tables(native_request):
    experiment, parameters, fixture = native_request
    assert fixture == contract.check_identity()
    first = linear_model(experiment, **parameters)
    parameters['cov_kwds'] = dict(maxlags=5, use_correction=False)
    second = linear_model(experiment, **parameters)
    assert first['run_label'] != second['run_label'] and not second['reused']
    assert second['cov_kwds'] == parameters['cov_kwds']
    expected = next(row['expected'] for row in fixture['covariance_rows']
                    if row['case']['key'] == 'linear-parent.HAC.lag-5.correction-false')
    saved = pd.read_csv(Path(second['data_dir'])/'linear_model_coefficients.csv', float_precision='round_trip')
    for _, actual in saved.iterrows():
        gold = expected[actual['dependent_variable']]['coefficients'][contract._term_name(actual['term'])]
        for field in ('estimate', 'std_error', 'p_value', 'ci_low', 'ci_high'):
            assert contract.equal({field: float(actual[field])}, {field: gold[field]})


def test_identical_request_reuses_unchanged_saved_tables(native_request):
    experiment, parameters, _ = native_request
    first = linear_model(experiment, run_label='same', **parameters)
    files = {path: path.read_bytes() for path in Path(first['data_dir']).rglob('*') if path.is_file()}
    second = linear_model(experiment, run_label='same', **parameters)
    assert second['reused'] is True
    assert all(path.read_bytes() == original for path, original in files.items())


@pytest.mark.parametrize('change', ['covariance', 'correction', 'input', 'levels', 'profile',
                                   'software', 'damaged_output', 'extra_output', 'missing_manifest', 'legacy_manifest'])
def test_explicit_label_cannot_hide_changed_or_unverified_request(native_request, monkeypatch, change):
    experiment, parameters, _ = native_request
    first = linear_model(experiment, run_label='same', **parameters)
    folder = Path(first['data_dir'])
    manifest = folder/'manifest.json'
    if change == 'covariance':
        parameters['cov_kwds'] = dict(maxlags=5, use_correction=False)
    elif change == 'correction':
        parameters['fdr_method'] = 'holm'
    elif change == 'input':
        experiment.summary.loc[0, 'y'] += 1
    elif change == 'levels':
        experiment.summary['g'] = experiment.summary['g'].cat.reorder_categories(['C', 'B', 'A'])
    elif change == 'profile':
        parameters['covariate_profile'] = {'x': 0.125}
    elif change == 'software':
        monkeypatch.setattr('PyFLASH._cache_identity.version', lambda name: 'changed-version')
    elif change == 'damaged_output':
        path = folder/'linear_model_coefficients.csv'
        path.write_text(path.read_text()+'changed\n')
    elif change == 'extra_output':
        (folder/'unrecorded.csv').write_text('unverified\n')
    elif change == 'missing_manifest':
        manifest.unlink()
    elif change == 'legacy_manifest':
        payload = json.loads(manifest.read_text(encoding='utf-8'))
        payload.pop('request_identity')
        manifest.write_text(json.dumps(payload), encoding='utf-8')
    held = {path: path.read_bytes() for path in folder.rglob('*') if path.is_file()}
    with pytest.raises(ValueError, match='Cannot reuse'):
        linear_model(experiment, run_label='same', **parameters)
    assert all(path.read_bytes() == original for path, original in held.items())


def test_truncated_array_display_cannot_hide_cluster_membership():
    from PyFLASH._cache_identity import analysis_value
    first = np.zeros(2000, dtype=int)
    second = first.copy(); second[1000] = 1
    assert str(first) == str(second)
    assert analysis_value(first) != analysis_value(second)


def test_atomic_manifest_failure_preserves_previous_complete_record(tmp_path, monkeypatch):
    from PyFLASH import pipeline_io
    path = tmp_path/'manifest.json'
    pipeline_io.write_json({'first': 1}, str(path))
    before = path.read_bytes()
    def fail(*args):
        raise OSError('Injected publication failure')
    monkeypatch.setattr('PyFLASH._persistence.atomic_replace', fail)
    with pytest.raises(OSError, match='Injected publication failure'):
        pipeline_io.write_json({'second': 2}, str(path))
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_editing_loaded_software_cannot_stamp_old_calculations_as_current(native_request, monkeypatch):
    experiment, parameters, _ = native_request
    first = linear_model(experiment, run_label='same', **parameters)
    folder = Path(first['data_dir'])
    held = {path: path.read_bytes() for path in folder.rglob('*') if path.is_file()}
    monkeypatch.setattr('PyFLASH._persistence.code_identity', lambda: {'changed.py': 'changed'})
    with pytest.raises(RuntimeError, match='restart Python'):
        linear_model(experiment, run_label='same', **parameters)
    assert all(path.read_bytes() == original for path, original in held.items())


def test_outer_montage_publishes_final_files_before_identical_reuse(native_request, monkeypatch):
    from PyFLASH import pipeline_montage
    experiment, parameters, _ = native_request
    parameters['montage'] = True
    # Exercise the actual outer call boundary without manufacturing a chart.
    # The separately retained native figure run covers real save_fig observers.
    def collector(panels, directory, **kwargs):
        folder = Path(directory)
        (folder/'figures.json').write_text('{"finished": true}')
        (folder/'collector.txt').write_text('Finished outer collector')
        return str(folder/'collector.txt')
    monkeypatch.setattr(pipeline_montage, 'build_montage', collector)
    first = linear_model(experiment, run_label='same', **parameters)
    original = {path: path.read_bytes() for path in Path(first['data_dir']).rglob('*') if path.is_file()}
    def forbidden(*args, **kwargs):
        raise AssertionError('Reuse rebuilt the outer collector')
    monkeypatch.setattr(pipeline_montage, 'build_montage', forbidden)
    second = linear_model(experiment, run_label='same', **parameters)
    assert second['reused'] is True
    assert all(path.read_bytes() == content for path, content in original.items())


def test_unverifiable_covariance_callable_keeps_fresh_requests_distinct(native_request):
    from statsmodels.stats.sandwich_covariance import weights_bartlett
    experiment, parameters, _ = native_request
    parameters['cov_kwds'] = dict(maxlags=0, use_correction=False, weights_func=weights_bartlett)
    first = linear_model(experiment, **parameters)
    held = {path: path.read_bytes() for path in Path(first['data_dir']).rglob('*') if path.is_file()}
    parameters['cov_kwds'] = dict(maxlags=5, use_correction=False, weights_func=weights_bartlett)
    second = linear_model(experiment, **parameters)
    assert first['run_label'] != second['run_label'] and not second['reused']
    assert not first['request_identity']['reusable'] and not second['request_identity']['reusable']
    assert not first['coefficients']['std_error'].equals(second['coefficients']['std_error'])
    assert all(path.read_bytes() == content for path, content in held.items())


def test_run_is_not_reusable_while_outer_figure_collector_is_running(native_request, monkeypatch):
    from PyFLASH import pipeline_montage
    experiment, parameters, _ = native_request
    parameters['montage'] = True
    observed = {}
    def collector(panels, directory, **kwargs):
        try:
            early = linear_model(experiment, run_label='same', **parameters)
            observed['early_reused'] = early.get('reused', False)
        except ValueError as error:
            observed['early_error'] = str(error)
        return None
    monkeypatch.setattr(pipeline_montage, 'build_montage', collector)
    first = linear_model(experiment, run_label='same', **parameters)
    assert observed.get('early_reused') is not True
    assert 'not complete' in observed['early_error']
    assert first['completion_status'] == 'complete'
    assert linear_model(experiment, run_label='same', **parameters)['reused'] is True


def test_failed_outer_figure_collector_cannot_publish_a_complete_run(native_request, monkeypatch):
    from PyFLASH import pipeline_montage
    experiment, parameters, _ = native_request
    parameters['montage'] = True
    def broken(*args, **kwargs):
        raise RuntimeError('Injected overview failure')
    monkeypatch.setattr(pipeline_montage, 'build_montage', broken)
    first = linear_model(experiment, run_label='same', **parameters)
    assert first['completion_status'] == 'partial'
    assert 'Injected overview failure' in first['montage_error']
    with pytest.raises(ValueError, match='not complete'):
        linear_model(experiment, run_label='same', **parameters)


def test_moved_saved_run_resolves_its_verified_files_at_the_new_location(native_request):
    import shutil
    experiment, parameters, _ = native_request
    first = linear_model(experiment, run_label='same', **parameters)
    owner = Path(experiment.fig_path).resolve()
    old = Path(first['data_dir']).resolve()
    new_root = owner/'moved'
    target = new_root/'Linear Model Pipeline'/old.name
    assert old.is_relative_to(owner) and target.resolve().is_relative_to(owner)
    target.parent.mkdir(parents=True)
    shutil.move(str(old), str(target))
    experiment.fig_path = str(new_root)
    cached = linear_model(experiment, run_label='same', **parameters)
    assert cached['reused'] is True
    assert Path(cached['data_dir']).resolve() == target.resolve()
    assert Path(cached['fig_dir']).resolve() == target.resolve()
    assert Path(cached['adjusted_means_dir']).resolve() == target.resolve()
    assert (Path(cached['data_dir'])/'linear_model_coefficients.csv').is_file()
