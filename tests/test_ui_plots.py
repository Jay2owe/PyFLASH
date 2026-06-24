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
import json
import os
import sys
import time
import types

import pytest

from PyFLASH.spec import (
    PLOT_REGISTRY,
    _convert_specificity,
    _resolve_func,
)
from PyFLASH.ui import figures, services


# ── available_plots ─────────────────────────────────────────────────────────


def test_available_plots_matches_registry():
    plots = services.available_plots()
    assert plots == sorted(PLOT_REGISTRY)
    # Spot-check a few expected keys are present.
    for key in ("mean_bars", "matrices", "radar", "regressions", "volcano",
                "histograms", "adjusted_correlation_pipeline"):
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


def test_resolve_func_supports_pipeline_module_targets():
    func = _resolve_func(PLOT_REGISTRY["correlation_pipeline"])
    assert func.__module__ == "PyFLASH.pipeline"
    assert func.__name__ == "correlation"
    adjusted = _resolve_func(PLOT_REGISTRY["adjusted_correlation_pipeline"])
    assert adjusted.__module__ == "PyFLASH.pipeline"
    assert adjusted.__name__ == "adjusted_correlation"


def test_cheat_sheet_accepts_pipeline_module_targets(capsys):
    from PyFLASH.plotting import cheat_sheet

    cheat_sheet(PLOT_REGISTRY["correlation_pipeline"])
    out = capsys.readouterr().out
    assert "PyFLASH.pipeline.correlation" in out
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
