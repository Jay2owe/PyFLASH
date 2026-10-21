"""Real input, replay, portability and interruption checks for the workflow."""
import json
import os
from pathlib import Path
import subprocess

import pandas as pd
import pytest

from PyFLASH.ui import services, workspace
from PyFLASH.ui.project_io import Project, load_project, save_project
from PyFLASH.ui.workflow import HELP, STAGES
from reproducibility.run import python_command


def test_packaged_example_is_frozen_demo():
    root = Path(__file__).resolve().parents[1]
    assert workspace.DEMO_PATH.read_bytes() == (root / "demo/data/summary.csv").read_bytes()
    experiment = workspace.load_table(workspace.DEMO_PATH, demo=True)
    table = services.summary_table(experiment, display=False)
    expected = json.loads((root / "demo/expected_result.json").read_text())
    assert table.groupby("Condition")["Signal_MeanIntensity"].mean().to_dict() == pytest.approx(expected["group_means"], rel=1e-9)
    assert workspace.numeric_columns(table) == ["DAPI_MeanIntensity", "Signal_MeanIntensity"]


def test_input_refuses_missing_identity(tmp_path):
    path = tmp_path / "table.csv"
    path.write_text("AnimalName,Condition,Signal\nA,,1\n")
    with pytest.raises(ValueError, match="missing identities"):
        workspace.load_table(path)


def test_point_selection_and_clear_share_subject_identity():
    assert workspace.selected_subject({"selection": {"picked_subject": [{"_subject": "B01"}]}}) == "B01"
    assert workspace.selected_subject({"selection": {"picked_subject": {"_subject": ["B01"]}}}) == "B01"
    assert workspace.selected_subject({"selection": {"picked_subject": []}}) == "All subjects"


def test_legacy_measurements_preserve_source_and_missing_tags(monkeypatch):
    raw = pd.DataFrame({
        "AnimalName": ["001", "002", "003", "004"],
        "Condition": ["Control"] * 4,
        "Area(um^2)Mean.exp1": [1.25, "NOT_INCLUDED_IN_EXPERIMENT", "EXCLUDED_9", "2.5"],
        "unrecognised": [1, "review needed", 2, 3],
        "coordinates": [[1, 2], 3, None, [4]],
    })
    before = raw.copy(deep=True)
    monkeypatch.setattr(services, "summary_table", lambda *a, **k: raw)
    table = workspace.measurement_table(object())
    assert workspace.numeric_columns(table) == ["Area(um^2)Mean.exp1"]
    assert table["Area(um^2)Mean.exp1"].dropna().tolist() == [1.25, 2.5]
    assert table["Area(um^2)Mean.exp1"].isna().tolist() == [False, True, True, False]
    assert table["AnimalName"].tolist() == ["001", "002", "003", "004"]
    pd.testing.assert_frame_equal(raw, before)
    data, aliases = workspace.exploration_data(table, ["Area(um^2)Mean.exp1"] * 2)
    assert aliases == {"Area(um^2)Mean.exp1": "_measurement_0"}
    assert data.columns.tolist() == ["AnimalName", "Condition", "_measurement_0"]
    assert data["_measurement_0"].dropna().tolist() == [1.25, 2.5]
    arrow = pytest.importorskip("pyarrow")
    arrow.Table.from_pandas(workspace.display_table(raw))
    pd.testing.assert_frame_equal(raw, before)


def test_measurement_cache_changes_with_batch_and_region(monkeypatch):
    calls = []
    def summary(batch, **kwargs):
        calls.append((batch, kwargs["roi_base"]))
        return pd.DataFrame({"Signal": [1, "NOT_INCLUDED_IN_EXPERIMENT"]})
    monkeypatch.setattr(services, "summary_table", summary)
    first, second = object(), object()
    cache = {}
    table = workspace.measurement_table(first, "SCN", cache)
    assert workspace.measurement_table(first, "SCN", cache) is table
    workspace.measurement_table(first, "other", cache)
    workspace.measurement_table(second, "other", cache)
    assert calls == [(first, "SCN"), (first, "other"), (second, "other")]


def test_opening_completed_or_new_data_clears_all_previous_results():
    state = {"_ui_dataset_token": "previous", "_ui_measurement_cache": {"table": "old"},
             "ui_last_plot": "old", "ui_image_result": "old", "ui_location_result": "old",
             "ui_image_representatives": "old", "ui_export_log": "old", "ui_csv_result": "old",
             "ui_save_analysis": "old", "ui_saved_analysis_result": "old", "ui_project_name": "keep"}
    batch = object()
    workspace.activate_dataset(state, batch, {"kind": "pickle", "path": "new.pkl"})
    assert state["batch"] is batch and state["pickle_path"] == "new.pkl"
    assert state["_ui_dataset_token"] != "previous"
    assert state["ui_project_name"] == "keep"
    assert not any(key.endswith("result") or key == "_ui_measurement_cache" for key in state)


def test_presentation_keeps_exact_large_integers_and_nonfinite_values(monkeypatch):
    import numpy as np
    raw = pd.DataFrame({"AnimalName": ["A", "B", "C"],
        "large": pd.Series([2**63+1, 2**63+2, 2**63+3], dtype=object),
        "nonfinite": pd.Series([1.5, np.inf, "NOT_INCLUDED_IN_EXPERIMENT"], dtype=object),
        "empty": pd.Series([None, "EXCLUDED_3", "NOT_INCLUDED_IN_EXPERIMENT"], dtype=object)})
    monkeypatch.setattr(services, "summary_table", lambda *a, **k: raw)
    table, metrics, labels = workspace.measurement_catalogue(object())
    assert table["large"].tolist() == [2**63+1, 2**63+2, 2**63+3]
    assert np.isinf(table.loc[1, "nonfinite"])
    assert metrics == ["large", "nonfinite"]
    assert labels["large"] == "large"
    assert raw.loc[2, "nonfinite"] == "NOT_INCLUDED_IN_EXPERIMENT"


def test_catalogue_cache_does_not_copy_or_relabel_measurements_on_interaction(monkeypatch):
    from PyFLASH import export
    calls = []
    original = export._display_label_for_summary_column
    def label(column):
        calls.append(column)
        return original(column)
    monkeypatch.setattr(export, "_display_label_for_summary_column", label)
    monkeypatch.setattr(services, "summary_table", lambda *a, **k: pd.DataFrame({"Signal_MeanIntensity": [1.0, 2.0]}))
    batch, cache = object(), {}
    first = workspace.measurement_catalogue(batch, "SCN", cache)
    second = workspace.measurement_catalogue(batch, "SCN", cache)
    assert first[0] is second[0] and first[1] is second[1] and first[2] is second[2]
    assert not calls
    assert first[2]['Signal_MeanIntensity'] == second[2]['Signal_MeanIntensity']
    assert calls == ['Signal_MeanIntensity']


def test_float_block_preserves_integer_precision_nested_metadata_and_labels(monkeypatch):
    import numpy as np
    raw = pd.DataFrame({'AnimalName':['001','002','003'],
        'huge':pd.Series([2**63+1,2**63+2,2**63+3],dtype=object),
        'integers':pd.Series(['1','2','3'],dtype=object),
        'floating':pd.Series([1.125,'NOT_INCLUDED_IN_EXPERIMENT',2.75],dtype=object),
        'other_float':pd.Series([9.5,np.inf,6.25],dtype=object),
        'unknown':pd.Series([1.25,'needs review',3.25],dtype=object),
        'nested':pd.Series([[1,2],None,3.5],dtype=object)})
    monkeypatch.setattr(services,'summary_table',lambda *a,**k:raw)
    table,metrics,labels = workspace.measurement_catalogue(object())
    assert table['huge'].dtype == np.dtype('uint64')
    assert table['huge'].tolist() == [2**63+1,2**63+2,2**63+3]
    assert table['integers'].dtype == np.dtype('int64')
    assert table['floating'].tolist()[0] == 1.125 and np.isnan(table['floating'].iloc[1])
    pd.testing.assert_series_equal(table['unknown'],raw['unknown'])
    pd.testing.assert_series_equal(table['nested'],raw['nested'])
    assert metrics == ['huge','integers','floating','other_float']
    assert list(labels)==raw.columns.tolist()
    assert not labels._resolved
    assert dict(labels)==dict(zip(raw.columns,services.format_summary_for_display(raw.iloc[:0]).columns))


def test_opening_legacy_analysis_migrates_in_memory_without_replacing_source(tmp_path):
    import pickle
    from types import SimpleNamespace
    legacy = SimpleNamespace(name='legacy',experiment_list=[],
        summary=pd.DataFrame({'Signal_exp1':[2.5]}),
        images=pd.DataFrame({'ImageArray':[[1,2,3]],'AnimalName':['a']}))
    source = tmp_path/'old.pkl'
    source.write_bytes(pickle.dumps(legacy))
    original = source.read_bytes()
    loaded = services.open_pickle(str(source))
    assert loaded.summary.columns.tolist()==['Signal.exp1']
    assert loaded.images.columns.tolist()==['AnimalName']
    assert loaded._state_schema_version==2
    assert source.read_bytes()==original


def test_large_source_opening_reuses_catalogue_and_rejects_changed_bytes(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from PyFLASH.ui import loading
    source = tmp_path/'large.pkl'
    source.write_bytes(b'0'*(9*1024**2))
    template = SimpleNamespace(summary=pd.DataFrame({'AnimalName':['a'],'Signal':[1.25]}))
    loading._source.clear()
    monkeypatch.setattr(services,'open_pickle',lambda path, **kwargs:template)
    original_identity = workspace.source_version
    calls = []
    reads = []
    def identity(path):
        result = original_identity(path)
        reads.append(result)
        return result
    def catalogue(batch,region):
        calls.append(region)
        return template.summary,['Signal'],{'Signal':'Signal'}
    monkeypatch.setattr(workspace,'source_version',identity)
    monkeypatch.setattr(workspace,'measurement_catalogue',catalogue)
    first = loading.open_source({'kind':'pickle','path':str(source)})
    second = loading.open_source({'kind':'pickle','path':str(source)})
    assert first is not second and len(calls)==1
    assert first._ui_source_version == second._ui_source_version == original_identity(source)
    assert len(reads) == 4 and all(item == first._ui_source_version for item in reads)
    pd.testing.assert_frame_equal(first.summary,template.summary,check_exact=True)
    pd.testing.assert_frame_equal(second.summary,template.summary,check_exact=True)
    template.__dict__.pop('_ui_initial_catalogue')
    loading._source.clear()
    def changed(path, **kwargs):
        with source.open('r+b') as handle:
            handle.seek(-1,2)
            handle.write(b'1')
        return template
    monkeypatch.setattr(services,'open_pickle',changed)
    with pytest.raises(ValueError,match='source file changed'):
        loading.open_source({'kind':'pickle','path':str(source)})
    loading._source.clear()


def test_source_cache_seed_preserves_catalogue_and_region_ownership(monkeypatch):
    from types import SimpleNamespace
    table = pd.DataFrame({"Signal": [1, 2]})
    seed = (table, ["Signal"], {"Signal": "Signal"})
    batch = SimpleNamespace(_ui_initial_catalogue=("SCN", seed))
    monkeypatch.setattr(services, "summary_table", lambda *a, **k: pd.DataFrame({"Other": [3]}))
    cache = {}
    result = workspace.measurement_catalogue(batch, "SCN", cache)
    assert result[0] is table and cache["batch"] is batch
    other = workspace.measurement_catalogue(batch, "other-region", cache)
    assert other[1] == ["Other"] and other[0] is not table


def test_source_resource_cache_reuses_reads_but_isolates_edits(tmp_path):
    source = tmp_path / "fixture.pkl"
    source.write_bytes(b"first version")
    script = f"""
from types import SimpleNamespace
import os
import pandas as pd
from PyFLASH.ui import loading, services, workspace
reads = []
template = SimpleNamespace(summary=pd.DataFrame({{'AnimalName':['001'], 'Signal':[1.2345678901234567]}}), representative_images=pd.DataFrame({{'AnimalName':['001'], 'Representative':[True]}}))
def read(path, **kwargs):
    reads.append(path)
    return template
services.open_pickle = read
source = {{'kind':'pickle', 'path':{str(source)!r}}}
loading._source.clear()
first = loading.open_source(source)
second = loading.open_source(source)
assert len(reads) == 1 and first is not second and first is not template
first.representative_images.loc[0, 'AnimalName'] = 'changed'
first._state_path = 'changed-path'
assert second.representative_images.loc[0, 'AnimalName'] == '001'
assert template.representative_images.loc[0, 'AnimalName'] == '001'
assert not hasattr(second, '_state_path')
assert workspace.measurement_catalogue(first, 'SCN')[0] is workspace.measurement_catalogue(second, 'SCN')[0]
assert second.summary.loc[0,'Signal'] == 1.2345678901234567
stat = os.stat(source['path'])
open(source['path'],'wb').write(b'other version')
os.utime(source['path'], ns=(stat.st_atime_ns, stat.st_mtime_ns))
third = loading.open_source(source)
assert len(reads) == 2
assert third._ui_source_version != first._ui_source_version
loading._code_version = lambda: ('edited-code-version',)
fourth = loading.open_source(source)
assert len(reads) == 3
loading._source.clear()
"""
    result = subprocess.run(python_command()+["-c", script], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_identity_follows_contents_not_file_metadata(tmp_path):
    source = tmp_path / 'summary.csv'
    source.write_bytes(b'original')
    first = workspace.source_version(source)
    stat = source.stat()
    source.write_bytes(b'modified')
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert source.stat().st_size == stat.st_size
    assert workspace.source_version(source) != first
    changed = workspace.source_version(source)
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000))
    assert workspace.source_version(source) == changed


@pytest.mark.parametrize('dependency', ['dataframe.py', 'conditions.py', 'aliases.py',
                                       'palette.py', 'utils.py', 'ui/loading.py'])
def test_source_cache_identity_tracks_import_and_catalogue_dependencies(monkeypatch, dependency):
    from PyFLASH.ui import loading
    root = Path(workspace.__file__).resolve().parents[1]
    edited = root / dependency
    revision = ['original']
    original = workspace.content_hash
    monkeypatch.setattr(workspace, 'content_hash',
        lambda path: revision[0] if Path(path) == edited else original(path))
    first = loading._code_version()
    revision[0] = 'different-code-with-identical-file-metadata'
    assert loading._code_version() != first


def test_fragment_and_full_page_share_the_complete_checkpoint(tmp_path):
    state = {'ui_explore_subject': 'A01', 'ui_explore_x': 'Signal',
             'ui_function_drafts': {'example': {'style': {'font.size': 20}}},
             'ui_fn_transient': 'skip', 'ui_source': {'kind': 'demo', 'path': str(workspace.DEMO_PATH)},
             'project': Project(name='Edited project'), 'ui_image_representatives': pd.DataFrame({'x': [1]})}
    path = tmp_path / 'recovery.json'
    workspace.checkpoint_session(state, path)
    saved = workspace.read_recovery(path)
    assert saved['preferences']['ui_explore_subject'] == 'A01'
    assert saved['preferences']['ui_function_drafts']['example']['style'] == {'font.size': 20}
    assert saved['project']['name'] == 'Edited project'
    assert 'ui_fn_transient' not in saved['preferences']
    assert 'ui_image_representatives' not in saved['preferences']
    state['ui_explore_subject'] = 'B01'
    workspace.checkpoint_session(state, path)
    assert workspace.read_recovery(path)['preferences']['ui_explore_subject'] == 'B01'


def test_distinct_edits_persist_when_the_system_clock_returns_the_same_revision(tmp_path,monkeypatch):
    import time
    monkeypatch.setattr(time,'time_ns',lambda:123456789)
    state = {'ui_explore_subject':'A01'}
    path = tmp_path/'same-clock.json'
    first = workspace.checkpoint_session(state,path)
    state['ui_explore_subject'] = 'B01'
    second = workspace.checkpoint_session(state,path)
    assert second['saved_at_ns'] == first['saved_at_ns']+1
    assert workspace.read_recovery(path)['preferences']['ui_explore_subject'] == 'B01'
    assert workspace.write_json(path, first, revision_key='saved_at_ns') is False
    assert workspace.read_recovery(path)['preferences']['ui_explore_subject'] == 'B01'


def test_large_measurement_menus_preserve_selections_and_reach_every_column():
    metrics = [f"Signal_{i}" for i in range(1000)]
    labels = {c: c.replace("_", " ") for c in metrics}
    choices, count = workspace.measurement_choices(metrics, labels, selected=[metrics[-1], metrics[0]])
    assert choices[:2] == [metrics[-1], metrics[0]] and len(choices) <= 202 and count == 1000
    choices, count = workspace.measurement_choices(metrics, labels, "signal 999", selected=[metrics[0]])
    assert choices == [metrics[0], metrics[-1]] and count == 1
    choices, count = workspace.measurement_choices(metrics, labels, "absent", selected=[metrics[-1]])
    assert choices == [metrics[-1]] and count == 0


def test_saved_subject_analysis_reopens_without_changing_measurements(tmp_path):
    experiment = workspace.load_table(workspace.DEMO_PATH, demo=True)
    path = str(tmp_path / "analysis.pkl")
    services.save_batch(experiment, path)
    restored = services.open_pickle(path)
    pd.testing.assert_frame_equal(restored.summary, experiment.summary)


def test_recipe_rejects_typos_and_missing_required_parameters():
    with pytest.raises(ValueError, match="Unknown parameters: pionts"):
        workspace.plot_contract("mean_bars", {"pionts": False})
    with pytest.raises(TypeError, match="missing a required argument"):
        workspace.plot_contract("scatter_3d", {})
    _, params = workspace.plot_contract("mean_bars", {"data_cols": ["Signal_MeanIntensity"]})
    assert params.get("data_cols", params.get("filtered_columns")) == ["Signal_MeanIntensity"]


def test_plot_reference_uses_canonical_source_and_does_not_load_plotting():
    command = "from PyFLASH.ui import workspace; import sys; from PyFLASH.spec import PLOT_REGISTRY; " \
              "refs = {p: workspace.plot_reference(p) for p in PLOT_REGISTRY}; " \
              "assert 'PyFLASH.plotting' not in sys.modules; " \
              "assert 'plot_mean_bars(' in refs['mean_bars']['signature']; " \
              "assert 'objects' in refs['locations']['signature']; " \
              "assert 'adjusted_correlation(' in refs['adjusted_correlation_pipeline']['signature']"
    result = subprocess.run(python_command()+["-c", command], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_help_parses_only_declaration_and_literal_docstring(tmp_path):
    filename = tmp_path / "reference.py"
    filename.write_text('''def plot_test(value=lambda x: x + 1, options={"label": "):"}, *, flag=True):
    "First " "second"
    raise RuntimeError("Body must not execute")
''', encoding="utf-8")
    reference = workspace._source_reference(str(filename), filename.stat().st_mtime_ns, "plot_test")
    assert reference["documentation"] == "First second"
    assert "lambda x: x + 1" in reference["signature"] and "flag=True" in reference["signature"]


def test_recovery_failed_replace_preserves_previous_copy(tmp_path, monkeypatch):
    path = tmp_path / "workspace.json"
    before = {"schema_version": 1, "preferences": {"ui_explore_subject": "A01"}}
    workspace.write_json(path, before)
    def fail(*args):
        raise OSError("interrupted replace")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="interrupted"):
        workspace.write_json(path, {"schema_version": 1})
    assert json.loads(path.read_text()) == before
    restored = workspace.read_recovery(path)
    assert restored['schema_version'] == workspace.SCHEMA_VERSION
    assert restored['preferences'] == before['preferences']
    assert list(tmp_path.iterdir()) == [path]


def test_project_moves_and_old_absolute_project_loads(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    project = Project(batch_path=str(original / "inputs"), experiments={"one": str(original / "inputs/one")})
    save_project(project, str(original / "project.json"))
    assert json.loads((original / "project.json").read_text())["batch_path"] == "inputs"
    moved = tmp_path / "moved"
    original.rename(moved)
    restored = load_project(str(moved / "project.json"))
    assert restored.batch_path == str(moved / "inputs")
    assert restored.experiments == {"one": str(moved / "inputs/one")}
    legacy = moved / "legacy.json"
    legacy.write_text(project.to_json())
    assert load_project(str(legacy)).batch_path == project.batch_path


def test_legacy_project_migrates_and_future_schema_is_rejected():
    assert Project.from_dict({"name":"Legacy"}).schema_version == 1
    assert Project.from_dict({"schema_version":0}).schema_version == 1
    with pytest.raises(ValueError,match="Unsupported project schema"):
        Project.from_dict({"schema_version":2})


def test_replay_exports_effective_scientific_configuration(monkeypatch):
    from PyFLASH.config import Config
    monkeypatch.setattr(Config,"EFFECT_CI_RANDOM_STATE",83)
    monkeypatch.setattr(Config,"EFFECT_CI_RESAMPLES",701)
    script = workspace.equivalent_script(workspace.DEMO_PATH,"mean_bars",{},source_kind="csv")
    assert "'EFFECT_CI_RANDOM_STATE': 83" in script
    assert "'EFFECT_CI_RESAMPLES': 701" in script


def test_replay_script_reproduces_input_and_refuses_changed_source(tmp_path, monkeypatch):
    source = tmp_path / "input.csv"
    source.write_bytes(workspace.DEMO_PATH.read_bytes())
    monkeypatch.chdir(tmp_path)
    script = workspace.equivalent_script(source, "mean_bars",
        {"data_cols": ["Signal_MeanIntensity"], "save": False, "save_normality": False}, source_kind="csv")
    script += "print('TABLE=' + batch.summary.to_json(orient='split'))\n"
    producer = tmp_path / "replay.py"
    producer.write_text(script, encoding="utf-8")
    source_root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, MPLBACKEND='Agg',
               PYTHONPATH=os.pathsep.join(filter(None, (source_root, os.environ.get('PYTHONPATH')))))
    result = subprocess.run(python_command()+[str(producer)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = next(line.removeprefix("TABLE=") for line in result.stdout.splitlines() if line.startswith("TABLE="))
    import io
    actual = pd.read_json(io.StringIO(payload), orient="split")
    expected = workspace.load_table(source).summary
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-9)
    source.write_text("AnimalName,Condition,Signal_MeanIntensity\nX,A,1\n")
    result = subprocess.run(python_command()+[str(producer)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode != 0
    assert "Input content changed" in result.stderr


def test_every_stage_has_a_page_and_help():
    root = Path(__file__).resolve().parents[1] / "PyFLASH/ui/pages"
    assert len({s.key for s in STAGES}) == len(STAGES)
    for stage in STAGES:
        assert (root / stage.file).is_file()
        assert HELP[stage.key]
