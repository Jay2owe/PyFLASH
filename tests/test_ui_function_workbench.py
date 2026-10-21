"""Function use, argument fidelity, drafts and complete background results."""
from pathlib import Path
import json

import pytest

from PyFLASH.ui import function_contracts as fc, function_workbench as fw, workspace


@pytest.fixture
def batch(tmp_path):
    import pandas as pd
    from PyFLASH import from_dataframe
    frame = pd.DataFrame({"AnimalName": ["a", "b", "c", "d", "e", "f"],
                          "Condition": ["Control"] * 3 + ["Treated"] * 3,
                          "Signal": [1., 2., 3., 4., 6., 7.], "Volume": [4., 6., 5., 9., 8., 10.]})
    objects = frame.rename(columns={"Signal": "Cells_Intensity", "Volume": "Cells_Volume"})
    return from_dataframe(frame, group_col="Condition", subject_col="AnimalName", data={"Cells": objects},
                          file_path=str(tmp_path), source_paths=[])


def test_complete_coverage_keeps_owner_defaults_and_explains_reference_access():
    from PyFLASH.spec import PLOT_REGISTRY
    contracts = fc.contracts()
    assert {c.entry.key for c in contracts} == {i.key for i in fc.catalogue.functions()}
    assert {c.entry.action for c in contracts if c.entry.action} == set(PLOT_REGISTRY)
    for contract in contracts:
        fields = {f.name: f for f in contract.fields}
        assert contract.task and contract.title and contract.output
        if contract.access == "reference":
            assert contract.reason and not contract.entry.action
        for parameter in contract.entry.parameters:
            assert fields[parameter.name].parameter == parameter
            assert fields[parameter.name].role
    histogram = fc.find("action:histograms")
    assert {f.name:f.role for f in histogram.fields}["marker"] == "marker"
    assert {f.name:f.role for f in histogram.fields}["x_attr"] == "object_measurement"
    representative = fc.find("action:representative_images")
    assert "tile_size" in {f.name for f in representative.fields}


def test_search_task_titles_and_preserve_all_entries():
    assert any(c.entry.action == "mean_bars" for c in fc.search(fc.contracts(), "compare group means"))
    assert len(fc.search(fc.contracts())) == len(fc.catalogue.functions())
    assert all(c.task == "Fit models" for c in fc.search(fc.contracts(), task="Fit models"))


def test_shared_appearance_edits_restore_in_a_fresh_browser_session(batch, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_cards, jobs
    monkeypatch.setattr(function_cards,'render',lambda *a,**k:None)
    monkeypatch.setattr(jobs,'latest_job',lambda:None)
    contract = fc.find('action:mean_bars')
    app = AppTest.from_file('PyFLASH/ui/pages/9_functions.py',default_timeout=20)
    app.session_state['batch'] = batch
    app.session_state['ui_function_selection'] = contract.entry.key
    app.run()
    app.checkbox(key=fw._key(contract.entry,'appearance_open')).set_value(True).run()
    prefix = fw._key(contract.entry,'presentation')
    app.checkbox(key=prefix+'_xlim_enabled').set_value(True).run()
    app.number_input(key=prefix+'_xlim_first').set_value(-2.)
    app.number_input(key=prefix+'_xlim_second').set_value(12.)
    app.selectbox(key=prefix+'_legend').set_value('hide').run()
    assert not app.exception
    drafts = json.loads(json.dumps(app.session_state['ui_function_drafts']))
    assert drafts[contract.entry.key]['style']['presentation'] == {'xlim':[-2.,12.],'legend':'hide'}
    fresh = AppTest.from_file('PyFLASH/ui/pages/9_functions.py',default_timeout=20)
    fresh.session_state['batch'] = batch
    fresh.session_state['ui_function_selection'] = contract.entry.key
    fresh.session_state['ui_function_drafts'] = drafts
    fresh.run()
    assert not fresh.exception
    assert fresh.checkbox(key=prefix+'_xlim_enabled').value
    assert fresh.number_input(key=prefix+'_xlim_first').value == -2.
    assert fresh.number_input(key=prefix+'_xlim_second').value == 12.
    assert fresh.selectbox(key=prefix+'_legend').value == 'hide'


def test_inputs_validate_against_real_data_without_silent_selections(batch):
    context = fc.input_context(batch)
    assert "data_cols" in fc.validate(fc.find("action:mean_bars"), {}, context)
    assert not fc.validate(fc.find("action:mean_bars"), {"data_cols": ["Signal"]}, context)
    assert "x" in fc.validate(fc.find("action:regressions"), {"x":"wrong", "y":"Volume"}, context)
    histogram = fc.find("action:histograms")
    assert not fc.validate(histogram, {"marker":"Cells", "x_attr":"Cells_Volume"}, context)
    assert "x_attr" in fc.validate(histogram, {"marker":"Cells", "x_attr":"missing"}, context)
    assert "path" in fc.validate(fc.find("action:model_result_matrix"), {}, context)
    assert "markers" in fc.validate(fc.find("action:images"), {}, context)


def test_value_modes_preserve_none_empty_omission_and_sequences():
    contract = fc.find("action:mean_bars")
    assert fc.prepared_values(contract, {}) == {}
    assert fc.prepared_values(contract, {"data_col_exclude": ""}) == {"data_col_exclude": ""}
    assert fc.prepared_values(contract, {"data_col_exclude": None}) == {"data_col_exclude": None}
    assert fc.prepared_values(contract, {"y_range": [0, 10]}) == {"y_range": (0, 10)}
    with pytest.raises(ValueError):
        fc.prepared_values(contract, {"invented": 1})
    with pytest.raises(ValueError):
        fc.prepared_values(contract, {"experiment": "arbitrary_object"})


def test_cache_cannot_reuse_another_dataset(batch, tmp_path):
    cache = {}
    original = fc.input_context(batch, cache=cache)
    another = workspace.load_table(workspace.DEMO_PATH, demo=True)
    changed = fc.input_context(another, cache=cache)
    assert original["table"] is not changed["table"]
    assert "Cells" not in changed["markers"]


def test_registered_forms_render_without_json_and_never_execute_on_selection(batch, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_cards, job_status, jobs
    monkeypatch.setattr(function_cards, "render", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "latest_job", lambda: None)
    submitted = []
    monkeypatch.setattr(job_status, "submit", lambda *a, **k: submitted.append((a,k)))
    app = AppTest.from_file(str(Path("PyFLASH/ui/pages/9_functions.py")), default_timeout=20)
    app.session_state["batch"] = batch
    for contract in fc.contracts():
        if not contract.entry.action:
            continue
        app.session_state["ui_function_selection"] = contract.entry.key
        app.run()
        assert not app.exception, (contract.entry.action, [e.message for e in app.exception])
        assert not app.text_area
    assert not submitted


def test_complete_forms_submit_exact_inputs_and_restore_drafts(batch, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_cards, job_status, jobs
    monkeypatch.setattr(function_cards, "render", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "latest_job", lambda: None)
    submitted = []
    monkeypatch.setattr(job_status, "submit", lambda *args: submitted.append(args))
    app = AppTest.from_file("PyFLASH/ui/pages/9_functions.py", default_timeout=20)
    app.session_state["batch"] = batch
    app.session_state["ui_function_selection"] = "action:mean_bars"
    app.run()
    bars = fc.find("action:mean_bars")
    app.multiselect(key=fw._key(bars.entry,"data_cols")).set_value(["Signal"]).run()
    app.button(key=fw._key(bars.entry,"run")).click().run()
    assert submitted[-1][1]["kwargs"] == {"data_cols": ["Signal"]}
    app.session_state["ui_function_selection"] = "action:regressions"
    app.run()
    relation = fc.find("action:regressions")
    app.selectbox(key=fw._key(relation.entry,"x")).set_value("Signal")
    app.selectbox(key=fw._key(relation.entry,"y")).set_value("Volume").run()
    app.button(key=fw._key(relation.entry,"run")).click().run()
    assert submitted[-1][1]["kwargs"] == {"x":"Signal", "y":"Volume"}
    app.session_state["ui_function_selection"] = "action:histograms"
    app.run()
    histogram = fc.find("action:histograms")
    app.selectbox(key=fw._key(histogram.entry,"marker")).set_value("Cells").run()
    app.selectbox(key=fw._key(histogram.entry,"x_attr")).set_value("Cells_Volume").run()
    app.button(key=fw._key(histogram.entry,"run")).click().run()
    assert submitted[-1][1]["kwargs"] == {"marker":"Cells", "x_attr":"Cells_Volume"}
    drafts = json.loads(json.dumps(app.session_state["ui_function_drafts"]))
    fresh = AppTest.from_file("PyFLASH/ui/pages/9_functions.py", default_timeout=20)
    fresh.session_state["batch"] = batch
    fresh.session_state["ui_function_drafts"] = drafts
    fresh.session_state["ui_function_selection"] = "action:mean_bars"
    fresh.run()
    assert fresh.multiselect(key=fw._key(bars.entry,"data_cols")).value == ["Signal"]


def test_public_helpers_execute_real_owner_and_reject_arbitrary_call(batch):
    contract = fc.find("PyFLASH.stats.bonferroni_correction")
    func, kwargs = fc.public_call(contract, batch, {"p_value":0.01, "n_tests":3})
    assert func(**kwargs) == pytest.approx(0.03)
    with pytest.raises(ValueError):
        fc.public_call(fc.find("PyFLASH.stats.clear_stats_cache"), batch, {})


def test_returned_tables_are_complete_and_separate_from_browser_preview(tmp_path):
    import pandas as pd
    from PyFLASH.ui.jobs import _result_tables
    frame = pd.DataFrame({"Value": range(250)})
    result = _result_tables({"fitted":frame, "count":250}, tmp_path)
    assert len(pd.read_csv(result["tables"][0]["path"])) == 250
    assert result["value"]["count"] == 250


def test_legacy_recipes_migrate_without_discarding_invalid_text():
    contract = fc.find("action:mean_bars")
    state = {"ui_fig_params_mean_bars": '{"filtered_columns": ["Signal"], "normalize": false}'}
    assert fw.migrate_legacy_draft(state, contract) is None
    assert state["ui_function_drafts"][contract.entry.key]["values"] == {"data_cols":["Signal"], "normalize":False}
    invalid = {"ui_fig_params_mean_bars": "unfinished JSON"}
    assert "retained" in fw.migrate_legacy_draft(invalid, contract)
    assert invalid["ui_fig_params_mean_bars"] == "unfinished JSON"


def test_full_application_reopens_forms_without_restoring_button_triggers(batch, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_cards, job_status, jobs, loading, workflow
    monkeypatch.setattr(function_cards, "render", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "latest_job", lambda: None)
    monkeypatch.setattr(job_status, "show_status", lambda: None)
    monkeypatch.setattr(job_status, "consume_completed", lambda: None)
    monkeypatch.setattr(loading, "open_source", lambda source, **kwargs: batch)
    function_stage = next(stage for stage in workflow.STAGES if stage.key == "functions")
    monkeypatch.setattr(workflow, "STAGES", (function_stage,))
    contract = fc.find("action:mean_bars")
    legacy_button = "ui_fn_" + fw._key(contract.entry, "data_cols").split("_")[2] + "_reset"
    monkeypatch.setattr(workspace, "read_recovery", lambda path: {"preferences": {legacy_button: False}})
    checkpoints = []
    monkeypatch.setattr(workspace, "write_json", lambda path, value, **kwargs: checkpoints.append(value) or True)
    app = AppTest.from_file(str(Path("PyFLASH/ui/app.py").resolve()), default_timeout=20).run()
    assert not app.exception
    assert app.session_state["batch"] is batch
    assert "ui_recovery_error" not in app.session_state
    app.multiselect(key=fw._key(contract.entry,"data_cols")).set_value(["Signal"]).run()
    app.run()
    assert not app.exception
    app.button(key=fw._key(contract.entry,"reset")).click().run()
    assert not app.exception
    assert app.multiselect(key=fw._key(contract.entry,"data_cols")).value == []
    assert all(legacy_button not in c["preferences"] for c in checkpoints)


def test_background_public_result_and_executable_replay_match_owner(batch, tmp_path):
    from PyFLASH.ui import jobs
    from PyFLASH.stats import bonferroni_correction
    source = tmp_path / "subjects.csv"
    from PyFLASH.ui.services import summary_table
    summary_table(batch, display=False).to_csv(source, index=False)
    parameters = {"function_key":"PyFLASH.stats.bonferroni_correction", "kwargs":{"p_value":0.01, "n_tests":3}}
    request = {"id":"a" * 32, "source":{"kind":"csv", "path":str(source)}, "kind":"function", "parameters":parameters}
    result = jobs._run_operation(request, tmp_path)
    assert result["value"] == bonferroni_correction(**parameters["kwargs"])
    namespace = {}
    exec(compile(result["script"], "downloaded_replay.py", "exec"), namespace)
    assert namespace["result"] == result["value"]


def test_svg_result_is_an_image_and_keeps_original_audit_record(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import sys
    from PyFLASH.ui import figures
    path = tmp_path / "audited.svg"
    original = '<svg xmlns="http://www.w3.org/2000/svg"><metadata>saved audit record</metadata><text>Signal</text></svg>'
    path.write_text(original, encoding="utf-8")
    shown, downloaded = [], []
    fake = SimpleNamespace(image=lambda *a, **k: shown.append(a[0]), download_button=lambda *a, **k: downloaded.append(k["data"]))
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    figures.embed_figure(None, None, paths=[str(path)])
    assert shown == [str(path)]
    assert downloaded == [original.encode()]


def test_large_measurement_picker_keeps_selection_across_filtered_reruns(tmp_path, monkeypatch):
    import pandas as pd
    from PyFLASH import from_dataframe
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_cards, jobs
    table = pd.DataFrame({"AnimalName":["a","b"], "Condition":["Control","Treated"],
                          **{f"Metric{i}":[1.,2.] for i in range(250)}})
    large = from_dataframe(table, file_path=str(tmp_path))
    monkeypatch.setattr(function_cards, "render", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "latest_job", lambda: None)
    app = AppTest.from_file("PyFLASH/ui/pages/9_functions.py", default_timeout=20)
    app.session_state["batch"] = large
    app.session_state["ui_function_selection"] = "action:regressions"
    contract = fc.find("action:regressions")
    app.run()
    key = fw._key(contract.entry, "x")
    app.text_input(key=key + "_search").set_value("Metric220").run()
    app.selectbox(key=key).set_value("Metric220").run()
    assert app.selectbox(key=key).value == "Metric220"
    app.run()
    assert app.session_state["ui_function_drafts"][contract.entry.key]["values"]["x"] == "Metric220"
