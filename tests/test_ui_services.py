"""Unit tests for PyFLASH.ui.services.

The services adapter must be importable and usable with **no Streamlit
installed** (house rule 2). These tests therefore:

* import ``PyFLASH.ui.services`` and assert ``streamlit`` was not pulled in,
* check ``package_info()`` reports a clean core import,
* check ``open_pickle`` is wired to ``serialization.load_state`` (verified via
  a real round-tripped pickle, with no streamlit dependency).
"""

import sys

import pandas as pd

from PyFLASH.batch import Batch
from PyFLASH.serialization import save_state
from PyFLASH.ui import services


def test_importing_services_does_not_import_streamlit():
    # Importing the adapter must not drag in the UI dependency.
    assert "streamlit" not in sys.modules


def test_package_info_reports_clean_import():
    info = services.package_info()
    assert info["import_ok"] is True
    assert info["has_create_batch"] is True
    assert info["has_load_state"] is True


def test_services_module_has_no_streamlit_attribute():
    # services.py must not import streamlit at module top.
    assert not hasattr(services, "streamlit")
    assert not hasattr(services, "st")


def _make_minimal_batch():
    batch = Batch.__new__(Batch)
    batch.name = "ui_test_batch"
    batch.data = {}
    batch.summary = pd.DataFrame()
    batch.experiment_list = []
    batch.filePath = None
    return batch


def test_open_pickle_round_trips_via_load_state(tmp_path):
    batch = _make_minimal_batch()
    pickle_path = tmp_path / "ui_batch.pkl"
    save_state(batch, str(pickle_path), verbose=False)

    loaded = services.open_pickle(str(pickle_path))

    assert isinstance(loaded, Batch)
    assert loaded.name == "ui_test_batch"
    # open_pickle records the load path on the object (load_state behaviour).
    assert loaded._state_path == str(pickle_path)


def test_open_pickle_is_backed_by_load_state():
    # Wiring check: the symbol services calls is serialization.load_state.
    from PyFLASH import serialization

    assert services.load_state is serialization.load_state
