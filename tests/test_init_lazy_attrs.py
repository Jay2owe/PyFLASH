"""Lazy attribute / submodule access on the PyFLASH package (PEP 562 __getattr__).

These guard the ergonomics added so that ``PyFLASH.plotting`` (and friends)
resolve without an explicit ``import PyFLASH.plotting`` first, while keeping a
bare ``import PyFLASH`` free of the heavy plotting stack.
"""

import importlib
import subprocess
import sys

import pytest

import PyFLASH


@pytest.mark.parametrize("name", ["plotting", "pipeline", "modelling", "stats"])
def test_heavy_submodules_resolve_as_attributes(name):
    mod = getattr(PyFLASH, name)
    assert mod is importlib.import_module(f"PyFLASH.{name}")


def test_plotting_attribute_exposes_plot_functions():
    assert hasattr(PyFLASH.plotting, "plot_mean_bars")
    assert callable(PyFLASH.cheat_sheet)


def test_modelling_attribute_exposes_linear_model_pipeline():
    assert callable(PyFLASH.run_linear_model_pipeline)


def test_pipeline_attribute_exposes_adjusted_correlation():
    assert callable(PyFLASH.adjusted_correlation)


def test_unknown_attribute_still_raises_attributeerror():
    with pytest.raises(AttributeError):
        PyFLASH.definitely_not_a_real_attribute


def test_dir_advertises_lazy_submodules():
    listed = dir(PyFLASH)
    for name in ("plotting", "pipeline", "modelling", "stats"):
        assert name in listed


def test_bare_import_stays_lightweight():
    """`import PyFLASH` must not drag in matplotlib (only touching plotting does)."""
    code = (
        "import sys, PyFLASH; "
        "assert 'matplotlib' not in sys.modules, 'matplotlib imported eagerly'; "
        "PyFLASH.plotting; "
        "assert 'matplotlib' in sys.modules, 'plotting did not load matplotlib'; "
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
