"""Unit tests for the Stage 08 image / representative / location tools.

These must run with **no Streamlit installed and without importing the heavy
plotting module at services-import time** (house rule 2). They therefore use
fakes/monkeypatching and never touch real images or data:

* ``image_table`` returns a non-empty image table and ``None`` for missing /
  empty tables,
* ``run_image_grid`` / ``run_representative_panels`` / ``run_locations`` forward
  markers/objects + kwargs and pass ``save=True`` (patched on the *plotting*
  module so the wrappers' lazy ``import PyFLASH.plotting`` resolves to the fake),
* ``get_representative_selections`` / ``set_representative_selections`` round-trip
  a DataFrame on a fake object's ``representative_images`` attribute.

Importing *plotting* inside a test to patch it is fine; the point of the
import-cleanliness test is that importing *services* alone must not pull it in.
``ast.parse`` confirms the Streamlit page is valid without launching Streamlit.
"""

import ast
import os
import sys
import types

import pandas as pd
import pytest

from PyFLASH.ui import services


# ── image_table ─────────────────────────────────────────────────────────────


def test_image_table_returns_non_empty_table():
    df = pd.DataFrame({"AnimalName": ["a1"], "Marker": ["DAPI"]})
    batch = types.SimpleNamespace(images=df)
    out = services.image_table(batch)
    assert out is df
    assert not out.empty


def test_image_table_none_when_images_missing():
    batch = types.SimpleNamespace(images=None)
    assert services.image_table(batch) is None
    # Also when the attribute is absent entirely.
    assert services.image_table(types.SimpleNamespace()) is None


def test_image_table_none_when_images_empty():
    batch = types.SimpleNamespace(images=pd.DataFrame())
    assert services.image_table(batch) is None


# ── plot wrapper forwarding (patched on the plotting module) ─────────────────


class _Recorder:
    """Records the positional args + kwargs of each call, returns a sentinel."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "RESULT"


@pytest.fixture
def patched_plotting(monkeypatch):
    """Patch the three plot functions on PyFLASH.plotting with recorders.

    Importing plotting *here* (in the test) is fine — the contract is only that
    importing ``services`` must not. The wrappers do a lazy
    ``import PyFLASH.plotting`` inside their bodies, so they resolve to these
    patched attributes.
    """
    import PyFLASH.plotting as plotting

    recorders = {
        "plot_images": _Recorder(),
        "plot_representative_images": _Recorder(),
        "plot_locations": _Recorder(),
    }
    for name, rec in recorders.items():
        monkeypatch.setattr(plotting, name, rec)
    return recorders


def test_run_image_grid_forwards_markers_and_save(patched_plotting):
    batch = object()
    result = services.run_image_grid(
        batch, ["DAPI", "mCherry"], animal_filter="a1", tile_size=5.0,
    )
    assert result == "RESULT"
    (args, kwargs), = patched_plotting["plot_images"].calls
    assert args == (batch,)
    assert kwargs["markers"] == ["DAPI", "mCherry"]
    assert kwargs["save"] is True
    assert kwargs["show"] is False
    assert kwargs["animal_filter"] == "a1"
    assert kwargs["tile_size"] == 5.0


def test_run_representative_panels_forwards_markers_and_save(patched_plotting):
    batch = object()
    result = services.run_representative_panels(
        batch, ["DAPI"], animal_filter="a2", fast_loading=True,
    )
    assert result == "RESULT"
    (args, kwargs), = patched_plotting["plot_representative_images"].calls
    assert args == (batch,)
    assert kwargs["markers"] == ["DAPI"]
    # Wrapper defaults save=True (plan: render saved panels).
    assert kwargs["save"] is True
    assert kwargs["animal_filter"] == "a2"
    assert kwargs["fast_loading"] is True


def test_run_representative_panels_save_override(patched_plotting):
    # setdefault means an explicit save=... is respected, not clobbered.
    services.run_representative_panels(object(), ["DAPI"], save=False)
    (_args, kwargs), = patched_plotting["plot_representative_images"].calls
    assert kwargs["save"] is False


def test_run_locations_forwards_objects_and_save(patched_plotting):
    exp = object()
    result = services.run_locations(
        exp, ["CK1d"], separate_by="animals", colocalise=False,
    )
    assert result == "RESULT"
    (args, kwargs), = patched_plotting["plot_locations"].calls
    # objects is passed positionally (matches plot_locations(experiment, objects)).
    assert args == (exp, ["CK1d"])
    assert kwargs["save"] is True
    assert kwargs["separate_by"] == "animals"
    assert kwargs["colocalise"] is False


# ── representative-selection round-trip ──────────────────────────────────────


def test_representative_selection_round_trip():
    batch = types.SimpleNamespace()
    # Absent attribute -> None.
    assert services.get_representative_selections(batch) is None

    df = pd.DataFrame({
        "AnimalName": ["a1", "a2"],
        "Marker": ["DAPI", "mCherry"],
        "ImageName": ["img1", "img2"],
    })
    returned = services.set_representative_selections(batch, df)
    assert returned is df
    assert batch.representative_images is df

    fetched = services.get_representative_selections(batch)
    pd.testing.assert_frame_equal(fetched, df)


def test_set_representative_selections_overwrites():
    batch = types.SimpleNamespace(representative_images=pd.DataFrame({"x": [1]}))
    new = pd.DataFrame({"AnimalName": ["a1"], "Marker": ["DAPI"]})
    services.set_representative_selections(batch, new)
    pd.testing.assert_frame_equal(
        services.get_representative_selections(batch), new
    )


# ── import-cleanliness + page parse ──────────────────────────────────────────


def test_importing_services_is_streamlit_and_plotting_free():
    # Stage 08 must not regress the import contract: importing services alone
    # must not load streamlit OR PyFLASH.plotting (the wrappers import plotting
    # lazily inside their bodies).
    sys.modules.pop("PyFLASH.plotting", None)
    sys.modules.pop("streamlit", None)
    import importlib

    importlib.reload(services)
    assert "streamlit" not in sys.modules
    assert "PyFLASH.plotting" not in sys.modules
    assert not hasattr(services, "st")
    assert not hasattr(services, "plotting")


def test_images_page_parses_as_valid_python():
    page = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "PyFLASH", "ui", "pages", "7_images.py",
    )
    with open(page, encoding="utf-8") as fh:
        ast.parse(fh.read())
