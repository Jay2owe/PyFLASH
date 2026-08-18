"""Unit tests for the Stage 07 plotting preset launcher.

These tests must run with **no Streamlit installed and without importing the
heavy plotting module at services-import time** (house rule 2). They therefore:

* assert ``available_plots()`` mirrors ``PLOT_REGISTRY``,
* exercise ``services._build_plot_kwargs`` against a *real* plot function's
  signature (so the columns→filtered_columns remap, specificity→tuple
  conversion, and unknown-key dropping are verified) **without calling the
  plot** (no ImageJ data required),
* drive ``services.run_plot_spec`` / ``validate_spec`` with JSON / dict specs
  (no PyYAML dependency) to confirm errors block and bad columns warn,
* check the ``figures.locate_saved_figures`` helper finds a saved .svg.

``ast.parse`` is used to confirm the Streamlit page is syntactically valid
without launching Streamlit.
"""

import ast
import importlib.util
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from PyFLASH.spec import (
    PLOT_REGISTRY,
    _convert_specificity,
    _resolve_func,
)
from PyFLASH.ui import figures, services


def _load_local_pyflash_runner(module_name):
    runner_path = (
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "pyflash" / "scripts" / "pyflash_runner.py"
    )
    if not runner_path.exists():
        pytest.skip("pyflash runner lives in gitignored .claude/; skip on public clones")
    spec = importlib.util.spec_from_file_location(module_name, runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def _patch_runner_for_fake_plot(monkeypatch, runner, tmp_path):
    import PyFLASH

    pkl_path = tmp_path / "human.pkl"
    pkl_path.write_text("fake pickle placeholder", encoding="utf-8")
    fig_root = tmp_path / "Results" / "Python Figures"
    fig_root.mkdir(parents=True)
    batch = types.SimpleNamespace(fig_path=str(fig_root), experiment_list=[])

    monkeypatch.setattr(runner, "resolve_pickle", lambda _batch: str(pkl_path))
    monkeypatch.setattr(PyFLASH, "load_state", lambda _path: batch)
    monkeypatch.setattr(runner, "_install_save_fig_hook", lambda: None)

    def fake_plot(_target, **_kwargs):
        (fig_root / "plot.png").write_bytes(b"fake png")
        return None

    monkeypatch.setattr(
        runner,
        "_resolve_function_target",
        lambda _name: (fake_plot, "PyFLASH.plotting", "plot_fake"),
    )
    return pkl_path, fig_root, batch


# ── available_plots ─────────────────────────────────────────────────────────


def test_available_plots_matches_registry():
    plots = services.available_plots()
    assert plots == sorted(PLOT_REGISTRY)
    # Spot-check a few expected keys are present.
    for key in ("mean_bars", "matrices", "radar", "regressions", "volcano",
                "histograms", "scatter_3d", "adjusted_correlation_pipeline",
                "iterative_model_sweep"):
        assert key in plots


def test_available_plots_does_not_eagerly_import_plotting():
    # Calling available_plots() only touches PLOT_REGISTRY's string refs; it
    # must not drag in the heavy plotting module.
    sys.modules.pop("PyFLASH.plotting", None)
    sys.modules.pop("PyFLASH.pipeline", None)
    services.available_plots()
    assert "PyFLASH.plotting" not in sys.modules
    assert "PyFLASH.pipeline" not in sys.modules


# ── _build_plot_kwargs (no plot call) ───────────────────────────────────────


def test_build_plot_kwargs_maps_columns_to_filtered_columns():
    # plot_mean_bars takes `filtered_columns`, not `columns`; the helper must
    # remap so a UI form using "columns" reaches the right parameter.
    func = _resolve_func(PLOT_REGISTRY["mean_bars"])
    kwargs = services._build_plot_kwargs(func, {"columns": ["A", "B"]})
    assert "filtered_columns" in kwargs
    assert kwargs["filtered_columns"] == ["A", "B"]
    assert "columns" not in kwargs


def test_build_plot_kwargs_maps_data_cols_to_filtered_columns_when_needed():
    def filtered_only(_batch, filtered_columns=None):
        return filtered_columns

    kwargs = services._build_plot_kwargs(filtered_only, {"data_cols": ["A", "B"]})
    assert kwargs == {"filtered_columns": ["A", "B"]}


def test_build_plot_kwargs_rejects_conflicting_column_aliases():
    def filtered_only(_batch, filtered_columns=None):
        return filtered_columns

    with pytest.raises(ValueError, match="data_cols|columns"):
        services._build_plot_kwargs(
            filtered_only,
            {"columns": ["A"], "data_cols": ["B"]},
        )


def test_build_plot_kwargs_allows_equivalent_column_aliases():
    def filtered_only(_batch, filtered_columns=None):
        return filtered_columns

    kwargs = services._build_plot_kwargs(
        filtered_only,
        {"columns": ["A"], "data_cols": ["A"]},
    )
    assert kwargs == {"filtered_columns": ["A"]}


def test_build_plot_kwargs_maps_filter_by_to_specificity_when_needed():
    def specificity_only(_batch, specificity=None):
        return specificity

    kwargs = services._build_plot_kwargs(
        specificity_only, {"filter_by": {"Sex": "Female", "Region": "SCN"}}
    )
    assert kwargs == {"specificity": {"Sex": "Female", "Region": "SCN"}}


def test_build_plot_kwargs_converts_direct_filter_by_to_tuple():
    def filter_by_func(_batch, filter_by=None):
        return filter_by

    kwargs = services._build_plot_kwargs(
        filter_by_func, {"filter_by": ["Time", "WeekEight"]}
    )
    assert kwargs == {"filter_by": ("Time", "WeekEight")}


def test_resolve_func_supports_pipeline_module_targets():
    func = _resolve_func(PLOT_REGISTRY["correlation_pipeline"])
    assert func.__module__ == "PyFLASH.plotting"
    assert func.__name__ == "plot_correlation_pipeline"
    adjusted = _resolve_func(PLOT_REGISTRY["adjusted_correlation_pipeline"])
    assert adjusted.__module__ == "PyFLASH.pipeline"
    assert adjusted.__name__ == "adjusted_correlation"
    model_sweep = _resolve_func(PLOT_REGISTRY["iterative_model_sweep"])
    assert model_sweep.__module__ == "PyFLASH.modelling"
    assert model_sweep.__name__ == "iterative_model_sweep"
    scatter = _resolve_func(PLOT_REGISTRY["scatter_3d"])
    assert scatter.__module__ == "PyFLASH.plotting"
    assert scatter.__name__ == "plot_scatter_3d"


def test_pyflash_runner_resolves_pipeline_registry_aliases():
    runner_path = (
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "pyflash" / "scripts" / "pyflash_runner.py"
    )
    if not runner_path.exists():
        pytest.skip("pyflash runner lives in gitignored .claude/; skip on public clones")
    spec = importlib.util.spec_from_file_location("pyflash_runner_test", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    req = {
        "batch": "human",
        "func": "adjusted_correlation_pipeline",
        "kwargs": {"endpoints": ["A", "B"], "save": False},
    }
    script = runner.build_equivalent_script(req, "human.pkl")
    assert "from PyFLASH.pipeline import adjusted_correlation as _pyflash_func" in script
    assert "_pyflash_func(batch, endpoints=['A', 'B'], save=False)" in script


def test_pyflash_runner_safe_run_id_cannot_escape_store():
    runner_path = (
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "pyflash" / "scripts" / "pyflash_runner.py"
    )
    if not runner_path.exists():
        pytest.skip("pyflash runner lives in gitignored .claude/; skip on public clones")
    spec = importlib.util.spec_from_file_location("pyflash_runner_safeid", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    # Path-traversal / absolute / separator ids must collapse to a bare slug that
    # stays inside RESULTS_STORE (no separators, no leading '..').
    for bad in ("..\\outside", "../../etc/passwd", "C:\\tmp\\x", "a/b\\c"):
        safe = runner._safe_run_id(bad)
        assert "/" not in safe and "\\" not in safe and ":" not in safe
        assert not safe.startswith(".")
        joined = (runner.RESULTS_STORE / f"{safe}.results.json").resolve()
        assert str(runner.RESULTS_STORE.resolve()) in str(joined)
    # Empty / all-junk ids fall back to a random slug, not an empty filename.
    assert runner._safe_run_id("") and runner._safe_run_id("..")
    # A normal id is preserved unchanged.
    assert runner._safe_run_id("abc123") == "abc123"
    # Distinct ids that sanitise to the same base must NOT collide onto one slug.
    assert runner._safe_run_id("a/b") != runner._safe_run_id("a:b")
    assert runner._safe_run_id("../abc") != runner._safe_run_id("abc")
    # Long clean ids sharing a 64-char prefix must not fold together under [:64].
    assert runner._safe_run_id("a" * 65) != runner._safe_run_id("a" * 64 + "b")
    assert all(len(runner._safe_run_id("z" * n)) <= 64 for n in (63, 64, 65, 200))


def test_pyflash_runner_appends_reproducibility_notebook(tmp_path):
    runner_path = (
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "pyflash" / "scripts" / "pyflash_runner.py"
    )
    if not runner_path.exists():
        pytest.skip("pyflash runner lives in gitignored .claude/; skip on public clones")
    spec = importlib.util.spec_from_file_location("pyflash_runner_notebook", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    fig_root = tmp_path / "Results" / "Python Figures"
    fig_root.mkdir(parents=True)
    batch = types.SimpleNamespace(fig_path=str(fig_root))
    req = {
        "batch": "human",
        "func": "plot_mean_bars",
        "kwargs": {"factor": "Diagnosis", "save": True},
        "project": "Human Amyloid",
        "user_request": "Make human diagnosis bars",
    }
    result = {
        "ok": True,
        "func": "plot_mean_bars",
        "outputs": [str(fig_root / "bars.svg")],
        "previews": [str(tmp_path / "preview.png")],
        "equivalent_script": "from PyFLASH import load_state\nplotting.plot_mean_bars(batch)",
        "results_summary": {"run_id": "run_1"},
        "results_json": str(tmp_path / "run_1.results.json"),
        "results_md": str(tmp_path / "run_1.results.md"),
        "digest": "deterministic digest text",
    }

    notebook, notebook_run_id = runner._append_reproducibility_notebook(
        req, tmp_path / "human.pkl", result, batch, batch
    )

    assert notebook == tmp_path / "Results" / "PyFLASH Notebooks" / "human_amyloid.ipynb"
    assert notebook_run_id == "run_1"
    data = json.loads(notebook.read_text(encoding="utf-8"))
    sources = "\n".join(str(cell["source"]) for cell in data["cells"])
    assert data["nbformat"] == 4
    assert "Make human diagnosis bars" in sources
    assert "PyFLASH source:" in sources
    assert "plotting.plot_mean_bars(batch)" in sources
    assert "preview.png" in sources
    assert "run_1" in sources
    assert "deterministic digest text" in sources

    second = dict(result)
    second["results_summary"] = {"run_id": "run_2"}
    runner._append_reproducibility_notebook(req, tmp_path / "human.pkl", second, batch, batch)
    updated = json.loads(notebook.read_text(encoding="utf-8"))
    updated_sources = "\n".join(str(cell["source"]) for cell in updated["cells"])
    assert len(updated["cells"]) > len(data["cells"])
    assert "run_1" in updated_sources
    assert "run_2" in updated_sources


def test_pyflash_runner_notebook_path_override(tmp_path):
    runner = _load_local_pyflash_runner("pyflash_runner_notebook_override")

    fig_root = tmp_path / "Results" / "Python Figures"
    fig_root.mkdir(parents=True)
    batch = types.SimpleNamespace(fig_path=str(fig_root))
    result = {
        "ok": True,
        "func": "plot_mean_bars",
        "outputs": [],
        "previews": [],
        "equivalent_script": "plotting.plot_mean_bars(batch)",
        "results_summary": {"run_id": "run_explicit"},
    }

    explicit_file = tmp_path / "custom_project.ipynb"
    req = {
        "batch": "human",
        "func": "plot_mean_bars",
        "notebook_path": str(explicit_file),
    }
    notebook, notebook_run_id = runner._append_reproducibility_notebook(
        req, tmp_path / "human.pkl", result, batch, batch
    )
    assert notebook == explicit_file
    assert notebook_run_id == "run_explicit"

    req_dir = {
        "batch": "human",
        "func": "plot_mean_bars",
        "project": "Custom Folder Project",
        "notebook_path": str(tmp_path / "notebooks"),
    }
    notebook_dir, _ = runner._append_reproducibility_notebook(
        req_dir, tmp_path / "human.pkl", result, batch, batch
    )
    assert notebook_dir == tmp_path / "notebooks" / "custom_folder_project.ipynb"


def test_pyflash_runner_run_request_reports_notebook_fields(tmp_path, monkeypatch):
    runner = _load_local_pyflash_runner("pyflash_runner_run_request_notebook")
    _pkl_path, fig_root, _batch = _patch_runner_for_fake_plot(
        monkeypatch, runner, tmp_path
    )

    result = runner.run_request(
        {
            "id": "runreq1",
            "batch": "human",
            "func": "plot_fake",
            "kwargs": {"save": True},
            "project": "Run Request",
            "user_request": "make a fake plot",
            "describe": False,
        },
        cache=None,
    )

    assert result["ok"] is True
    assert result["notebook"] == str(
        tmp_path / "Results" / "PyFLASH Notebooks" / "run_request.ipynb"
    )
    assert result["notebook_run_id"] == "runreq1"
    assert result["notebook_project"] == "run_request"
    assert str(fig_root / "plot.png") in result["outputs"]

    notebook = json.loads(Path(result["notebook"]).read_text(encoding="utf-8"))
    sources = "\n".join(str(cell["source"]) for cell in notebook["cells"])
    assert "make a fake plot" in sources
    assert "plotting.plot_fake(batch, save=True)" in sources


def test_pyflash_runner_run_request_fails_on_notebook_error(tmp_path, monkeypatch):
    runner = _load_local_pyflash_runner("pyflash_runner_notebook_failure")
    _patch_runner_for_fake_plot(monkeypatch, runner, tmp_path)

    def fail_notebook(*_args, **_kwargs):
        raise RuntimeError("notebook disk full")

    monkeypatch.setattr(runner, "_append_reproducibility_notebook", fail_notebook)

    result = runner.run_request(
        {
            "id": "runreq2",
            "batch": "human",
            "func": "plot_fake",
            "kwargs": {"save": True},
            "project": "Run Request",
            "describe": False,
        },
        cache=None,
    )

    assert result["ok"] is False
    assert result["notebook_error"] == "RuntimeError: notebook disk full"
    assert "RuntimeError" in result["notebook_traceback"]


def test_pyflash_runner_describe_status_for_func():
    runner_path = (
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "pyflash" / "scripts" / "pyflash_runner.py"
    )
    if not runner_path.exists():
        pytest.skip("pyflash runner lives in gitignored .claude/; skip on public clones")
    spec_mod = importlib.util.spec_from_file_location("pyflash_runner_dsf", runner_path)
    runner = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(runner)

    # Resolves describe status from a registry short-name, a plot_* name, or a
    # module-qualified pipeline target — used to decide whether to flag a 0-record run.
    assert runner._describe_status_for_func("mean_bars") == "covered"
    assert runner._describe_status_for_func("plot_mean_bars") == "covered"
    assert runner._describe_status_for_func("volcano") == "unreviewed"
    assert runner._describe_status_for_func("plot_images") == "exempt"
    assert runner._describe_status_for_func("correlation_pipeline") == "covered"
    assert runner._describe_status_for_func("PyFLASH.pipeline.correlation") == "covered"
    assert runner._describe_status_for_func("linear_model_pipeline") == "covered"
    assert runner._describe_status_for_func("PyFLASH.pipeline.linear_model") == "covered"
    assert runner._describe_status_for_func("iterative_model_sweep") == "covered"
    assert runner._describe_status_for_func("PyFLASH.modelling.iterative_model_sweep") == "covered"
    assert runner._describe_status_for_func("scatter_3d") == "exempt"
    assert runner._describe_status_for_func("plot_scatter_3d") == "exempt"
    assert runner._describe_status_for_func("not_a_real_plot") == "unclassified"


def test_pyflash_runner_discover_includes_registered_pipeline_signatures():
    runner_path = (
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "pyflash" / "scripts" / "pyflash_runner.py"
    )
    if not runner_path.exists():
        pytest.skip("pyflash runner lives in gitignored .claude/; skip on public clones")
    spec_mod = importlib.util.spec_from_file_location("pyflash_runner_discover", runner_path)
    runner = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(runner)

    discovered = runner.discover()
    corr = discovered["registered_callables"]["correlation_pipeline"]
    adjusted = discovered["registered_callables"]["adjusted_correlation_pipeline"]
    linear = discovered["registered_callables"]["linear_model_pipeline"]
    sweep = discovered["registered_callables"]["iterative_model_sweep"]
    scatter = discovered["registered_callables"]["scatter_3d"]

    assert corr["target"] == "PyFLASH.plotting.plot_correlation_pipeline"
    assert "gate='p'" in corr["signature"]
    assert "value_matrices='p'" in corr["signature"]
    assert adjusted["target"] == "PyFLASH.pipeline.adjusted_correlation"
    assert "value_matrices='p'" in adjusted["signature"]
    assert linear["target"] == "PyFLASH.pipeline.linear_model"
    assert "dependent_variables=None" in linear["signature"]
    assert "group=None" in linear["signature"]
    assert sweep["target"] == "PyFLASH.modelling.iterative_model_sweep"
    assert "target:" in sweep["signature"]
    assert "model_preset:" in sweep["signature"]
    assert "'ultra_compact'" in sweep["signature"]
    assert scatter["target"] == "PyFLASH.plotting.plot_scatter_3d"
    assert "x, y, z" in scatter["signature"]
    assert "correlation_pipeline" not in discovered["undocumented"]
    assert "adjusted_correlation_pipeline" not in discovered["undocumented"]
    assert "linear_model_pipeline" not in discovered["undocumented"]
    assert "iterative_model_sweep" not in discovered["undocumented"]
    assert "scatter_3d" not in discovered["undocumented"]


def test_pyflash_reference_updater_is_current():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "update_pyflash_references.py"
    if not (root / ".claude" / "skills" / "pyflash" / "reference" / "plot-functions.md").exists():
        pytest.skip("pyflash skill references are local to this project")

    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cheat_sheet_accepts_pipeline_module_targets(capsys):
    from PyFLASH.plotting import cheat_sheet

    cheat_sheet(PLOT_REGISTRY["correlation_pipeline"])
    out = capsys.readouterr().out
    assert "plot_correlation_pipeline" in out
    assert "max_regressions" in out


def test_build_plot_kwargs_converts_specificity_to_tuple():
    func = _resolve_func(PLOT_REGISTRY["mean_bars"])
    kwargs = services._build_plot_kwargs(
        func, {"specificity": ["Time", "WeekEight"]}
    )
    assert kwargs["specificity"] == ("Time", "WeekEight")
    # And matches what core's converter produces.
    assert kwargs["specificity"] == _convert_specificity(["Time", "WeekEight"])


def test_build_plot_kwargs_converts_specificity_queue():
    func = _resolve_func(PLOT_REGISTRY["mean_bars"])
    kwargs = services._build_plot_kwargs(
        func, {"specificity": [["Time", "WeekEight"], ["Region", "CA1"]]}
    )
    assert kwargs["specificity"] == [("Time", "WeekEight"), ("Region", "CA1")]


def test_build_plot_kwargs_preserves_specificity_mapping_as_and_filter():
    func = _resolve_func(PLOT_REGISTRY["mean_bars"])
    kwargs = services._build_plot_kwargs(
        func, {"specificity": {"Sex": "Female", "Region": "SCN"}}
    )
    assert kwargs["specificity"] == {"Sex": "Female", "Region": "SCN"}


def test_build_plot_kwargs_drops_unknown_keys():
    func = _resolve_func(PLOT_REGISTRY["mean_bars"])
    kwargs = services._build_plot_kwargs(
        func, {"factor": "Genotype", "not_a_real_param": 123}
    )
    assert kwargs == {"factor": "Genotype"}
    assert "not_a_real_param" not in kwargs


def test_build_plot_kwargs_keeps_known_keys_verbatim():
    func = _resolve_func(PLOT_REGISTRY["mean_bars"])
    kwargs = services._build_plot_kwargs(
        func, {"points": False, "normalize": True}
    )
    assert kwargs == {"points": False, "normalize": True}


# ── run_plot_spec / validate_spec wiring (JSON, no PyYAML) ───────────────────


class _FakeExperiment:
    """Minimal stand-in for validate_spec's column check (needs .summary)."""

    def __init__(self, columns):
        self.summary = types.SimpleNamespace(columns=list(columns))


def _write_json_spec(tmp_path, spec):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return str(path)


def test_run_plot_spec_blocks_on_unknown_plot_type(tmp_path):
    spec = {"plots": [{"type": "not_a_plot"}]}
    path = _write_json_spec(tmp_path, spec)
    exp = _FakeExperiment(["A", "B"])

    out = services.run_plot_spec(exp, path)

    assert out["ok"] is False
    assert out["errors"]
    assert any("unknown plot type" in e for e in out["errors"])
    # Nothing ran: no "results" key on a blocked spec.
    assert "results" not in out


def test_run_plot_spec_warns_on_bad_column(tmp_path):
    # A valid plot type but a column absent from the experiment summary -> a
    # validate_spec warning (spec.py column check), not a blocking error.
    spec = {"plots": [{"type": "mean_bars", "columns": ["DoesNotExist"]}]}
    path = _write_json_spec(tmp_path, spec)
    exp = _FakeExperiment(["RealColumn"])

    # Validate directly (mirrors spec.py's own tests) — bad column -> warning.
    from PyFLASH.spec import validate_spec

    errors, warnings = validate_spec(spec, exp)
    assert errors == []
    assert any("DoesNotExist" in w for w in warnings)


def test_run_plot_spec_reports_per_entry_results(tmp_path, monkeypatch):
    # With validation passing, run_plot_spec should map run_spec's per-entry
    # outputs (object vs None) to "ok"/"failed". Stub run_spec so no real plot
    # or data is needed.
    spec = {"plots": [{"type": "mean_bars"}, {"type": "volcano"}]}
    path = _write_json_spec(tmp_path, spec)
    exp = _FakeExperiment(["A"])

    import PyFLASH.spec as spec_mod

    monkeypatch.setattr(spec_mod, "run_spec", lambda b, p: [object(), None])
    # run_plot_spec imports run_spec from PyFLASH.spec at call time.
    out = services.run_plot_spec(exp, path)

    assert out["ok"] is True
    assert out["results"] == ["ok", "failed"]


# ── figures.locate_saved_figures ────────────────────────────────────────────


def test_locate_saved_figures_finds_svg(tmp_path):
    fig_root = tmp_path / "Python Figures"
    sub = fig_root / "Bars"
    sub.mkdir(parents=True)
    svg = sub / "MyPlot.svg"
    svg.write_text("<svg></svg>", encoding="utf-8")

    found = figures.locate_saved_figures(str(fig_root))
    assert str(svg) in found


def test_locate_saved_figures_respects_since(tmp_path):
    fig_root = tmp_path / "Python Figures"
    fig_root.mkdir()
    old = fig_root / "old.svg"
    old.write_text("<svg></svg>", encoding="utf-8")
    # Backdate the old file well before the cutoff.
    old_time = time.time() - 1000
    os.utime(str(old), (old_time, old_time))

    cutoff = time.time()
    new = fig_root / "new.svg"
    new.write_text("<svg></svg>", encoding="utf-8")

    found = figures.locate_saved_figures(str(fig_root), since=cutoff)
    assert str(new) in found
    assert str(old) not in found


def test_locate_saved_figures_missing_dir_returns_empty(tmp_path):
    assert figures.locate_saved_figures(str(tmp_path / "nope")) == []
    assert figures.locate_saved_figures(None) == []


def test_locate_saved_figures_newest_first(tmp_path):
    fig_root = tmp_path / "figs"
    fig_root.mkdir()
    a = fig_root / "a.svg"
    b = fig_root / "b.svg"
    a.write_text("<svg></svg>", encoding="utf-8")
    b.write_text("<svg></svg>", encoding="utf-8")
    os.utime(str(a), (time.time() - 100, time.time() - 100))
    os.utime(str(b), (time.time(), time.time()))

    found = figures.locate_saved_figures(str(fig_root))
    assert found[0] == str(b)  # newest first


def test_is_figure_duck_types():
    assert figures.is_figure(None) is False
    assert figures.is_figure(object()) is False

    class _Fig:
        def savefig(self):
            pass

        def get_axes(self):
            return []

    assert figures.is_figure(_Fig()) is True


# ── Import-cleanliness + page parse ─────────────────────────────────────────


def test_importing_services_is_streamlit_and_plotting_free():
    # Stage 07 must not regress the import contract.
    assert "streamlit" not in sys.modules
    assert not hasattr(services, "st")


def test_plots_page_parses_as_valid_python():
    page = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "PyFLASH", "ui", "pages", "6_plots.py",
    )
    with open(page, encoding="utf-8") as fh:
        ast.parse(fh.read())
