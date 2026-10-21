"""User-facing analysis tasks and supporting tools have separate homes."""
import pytest

from PyFLASH.ui import function_contracts as fc, workspace


def test_main_list_uses_analysis_registry_and_every_helper_has_another_home():
    from PyFLASH.spec import PLOT_REGISTRY
    main = fc.catalogue_contracts()
    assert {c.entry.action for c in main} == set(PLOT_REGISTRY)
    assert all(c.access == "form" for c in main)
    assert not fc.search(main, "export_all_excel")
    assert not fc.search(main, "set_pyflash_style")
    assert not fc.search(main, "bonferroni_correction")
    assert fc.catalogue_home(fc.find("PyFLASH.batch.Batch.export_all_excel")) == "export"
    assert fc.catalogue_home(fc.find("PyFLASH.aesthetics.set_pyflash_style")) == "appearance"
    placed = [c.entry.key for home in ("functions", "export", "appearance", "workspace") for c in fc.catalogue_contracts(home)]
    assert len(set(placed)) == len(placed) == len(fc.contracts())


def test_old_utility_selection_cannot_reappear_in_main_workbench(monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_cards
    seen = []
    monkeypatch.setattr(function_cards, "render", lambda items, **kwargs: seen.append(items))
    app = AppTest.from_file(str(fc.catalogue.ROOT / "ui/pages/9_functions.py"), default_timeout=20)
    app.session_state["ui_function_selection"] = "PyFLASH.aesthetics.set_pyflash_style"
    app.session_state["ui_functions_task"] = "Package helpers"
    app.session_state["ui_functions_access"] = "Python reference"
    app.run()
    assert not app.exception
    assert app.session_state["ui_function_selection"] == "action:mean_bars"
    assert app.selectbox(key="ui_functions_task").value == "All"
    assert all(c.entry.action for c in seen[-1])
    assert "Access" not in [c.label for c in app.selectbox]


def test_supporting_helpers_open_in_their_own_section():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string("from PyFLASH.ui.function_tools import render\nrender('appearance', 'Appearance package reference')", default_timeout=20)
    app.run()
    assert not app.exception
    selector = app.selectbox(key="ui_appearance_function_selection")
    assert "set_pyflash_style" in selector.options
    assert all(c.entry.module in {"PyFLASH.aesthetics", "PyFLASH.palette"} for c in fc.catalogue_contracts("appearance"))
    selector.set_value("PyFLASH.aesthetics.set_pyflash_style").run()
    assert not app.exception
    assert any("set_pyflash_style(" in code.value for code in app.code)


def test_house_defaults_are_saved_and_sent_to_new_runs_without_global_changes(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from PyFLASH.aesthetics import get_pyflash_style
    from PyFLASH.ui import function_workbench as fw, job_status, jobs
    package = get_pyflash_style()
    submitted = []
    monkeypatch.setattr(jobs, "latest_job", lambda: None)
    monkeypatch.setattr(job_status, "submit", lambda *a, **k: submitted.append(a))
    app = AppTest.from_string("from PyFLASH.ui import appearance, function_contracts as fc, function_workbench\nappearance.render()\nfunction_workbench.render(fc.find('action:mean_bars'))", default_timeout=20)
    app.session_state["batch"] = workspace.load_table(workspace.DEMO_PATH, demo=True)
    app.run()
    app.number_input(key="ui_house_dpi").set_value(300)
    app.number_input(key="ui_house_point_size").set_value(12.0)
    next(b for b in app.button if b.label == "Save house aesthetic").click().run()
    assert not app.exception
    assert app.session_state["ui_house_style"]["save_dpi"] == 300
    assert get_pyflash_style() == package
    contract = fc.find("action:mean_bars")
    measurement = workspace.measurement_catalogue(app.session_state["batch"], "SCN")[1][0]
    app.multiselect(key=fw._key(contract.entry, "data_cols")).set_value([measurement]).run()
    app.button(key=fw._key(contract.entry, "run")).click().run()
    assert not app.error, {"messages": [message.value for message in app.error], "draft": app.session_state["ui_function_drafts"][contract.entry.key], "issues": app.session_state[fw._key(contract.entry, "errors")]}
    assert submitted[-1][1]["style"] == {"save_dpi": 300, "point_size": 12.0}
    # A restored result's appearance takes priority over later house changes.
    draft = app.session_state["ui_function_drafts"][contract.entry.key]
    draft["style"] = {"point_size": 15.0}
    app.session_state["ui_function_drafts"] = {contract.entry.key: draft}
    app.run()
    app.button(key=fw._key(contract.entry, "run")).click().run()
    assert submitted[-1][1]["style"] == {"save_dpi": 300, "point_size": 15.0}
    app.button(key="_function_event_house_reset").click().run()
    assert not app.exception
    assert "ui_house_style" not in app.session_state
    assert get_pyflash_style() == package


def test_reopened_house_dimensions_remain_inherited_when_appearance_is_opened(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_workbench as fw, jobs
    monkeypatch.setattr(jobs, "latest_job", lambda: None)
    app = AppTest.from_string("from PyFLASH.ui import function_contracts as fc, function_workbench\nfunction_workbench.render(fc.find('action:mean_bars'))", default_timeout=20)
    app.session_state["batch"] = workspace.load_table(workspace.DEMO_PATH, demo=True)
    # JSON recovery changes a tuple into a list; opening the appearance editor
    # must not turn this inherited value into a per-function override.
    app.session_state["ui_house_style"] = {"figure_size": [9.0, 6.0]}
    contract = fc.find("action:mean_bars")
    app.run()
    app.checkbox(key=fw._key(contract.entry, "appearance_open")).set_value(True).run()
    assert not app.exception
    assert "figure_size" not in app.session_state["ui_function_drafts"][contract.entry.key]["style"]


def test_inherited_appearance_updates_but_explicit_plot_overrides_stay(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_workbench as fw, jobs
    monkeypatch.setattr(jobs, "latest_job", lambda: None)
    app = AppTest.from_string("from PyFLASH.ui import function_contracts as fc, function_workbench\nfunction_workbench.render(fc.find('action:mean_bars'))", default_timeout=20)
    app.session_state["batch"] = workspace.load_table(workspace.DEMO_PATH, demo=True)
    app.session_state["ui_house_style"] = {"point_size": 12.0}
    contract = fc.find("action:mean_bars")
    app.run()
    app.checkbox(key=fw._key(contract.entry, "appearance_open")).set_value(True).run()
    point = fw._key(contract.entry, "style_point_size")
    assert app.number_input(key=point).value == 12.0
    app.session_state["ui_house_style"] = {"point_size": 18.0}
    app.run()
    assert app.number_input(key=point).value == 18.0
    assert "point_size" not in app.session_state["ui_function_drafts"][contract.entry.key]["style"]
    app.number_input(key=point).set_value(15.0).run()
    app.session_state["ui_house_style"] = {"point_size": 20.0}
    app.run()
    assert app.number_input(key=point).value == 15.0
    assert app.session_state["ui_function_drafts"][contract.entry.key]["style"]["point_size"] == 15.0
