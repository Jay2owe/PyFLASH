import pickle
import sys
import types

import pandas as pd

from PyFLASH.batch import Batch
from PyFLASH.serialization import _remap_legacy_module, load_state


def _make_legacy_batch_pickle(path, module_name="IF_analysis.batch"):
    package = types.ModuleType("IF_analysis")
    module = types.ModuleType(module_name)
    legacy_batch = type("Batch", (), {})
    legacy_batch.__module__ = module_name
    module.Batch = legacy_batch

    previous_package = sys.modules.get("IF_analysis")
    previous_module = sys.modules.get(module_name)
    sys.modules["IF_analysis"] = package
    sys.modules[module_name] = module
    try:
        obj = legacy_batch()
        obj.name = "legacy"
        obj.data = {}
        obj.summary = pd.DataFrame()
        obj.experiment_list = []
        obj.filePath = None
        with open(path, "wb") as f:
            pickle.dump(obj, f)
    finally:
        if previous_package is None:
            sys.modules.pop("IF_analysis", None)
        else:
            sys.modules["IF_analysis"] = previous_package

        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module


def test_load_state_remaps_legacy_if_analysis_batch_pickle(tmp_path):
    pickle_path = tmp_path / "legacy.pkl"
    _make_legacy_batch_pickle(pickle_path)

    loaded = load_state(pickle_path, normalize_paths=False, verbose=False)

    assert isinstance(loaded, Batch)
    assert loaded.name == "legacy"
    assert loaded._state_path == pickle_path


def test_legacy_module_remapping_handles_nested_pyflash_package_names():
    assert _remap_legacy_module("IF_analysis") == "PyFLASH"
    assert _remap_legacy_module("IF_analysis.batch") == "PyFLASH.batch"
    assert _remap_legacy_module("IF_analysis.PyFLASH.batch") == "PyFLASH.batch"
    assert _remap_legacy_module("pandas.core.frame") == "pandas.core.frame"
