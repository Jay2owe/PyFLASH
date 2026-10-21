import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

def bundle():
    path = Path(__file__).with_name("actions.py")
    spec = importlib.util.spec_from_file_location("reviewed_shortcut", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_requires_live_binding():
    with pytest.raises(RuntimeError):
        bundle().workspace_overview()

def test_real_backend_readback(tmp_path):
    from fastapi import FastAPI
    from PyFLASH.control import describe
    from PyFLASH.ui.ai_assistant import overview
    path = tmp_path / "subjects.csv"
    path.write_text("AnimalName,Condition,Value\na,Control,2\n", encoding="utf-8")
    sessions = {"live": {"source": {"path": str(path), "kind": "csv"}}}
    app = FastAPI()
    app.state.aiify_overview = lambda: overview(sessions, "live")
    module = bundle()
    module.bind(app)
    result = module.workspace_overview()
    assert result["actions"] == describe()
    assert result["source"]["path"] == str(path)
    assert path.read_text() == "AnimalName,Condition,Value\na,Control,2\n"
