"""Project adapters for existing PyFLASH controls and embedded theme rules."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _engine():
    spec = importlib.util.spec_from_file_location(
        "pyflash_development_contract", ROOT / "scripts/project_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_controls_cannot_bypass_registered_builder():
    """A new page must retain stable keys, help and the shared icon route."""
    tree = ast.parse((ROOT / "PyFLASH/ui/controls.py").read_text(encoding="utf-8"))
    kinds = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "CONTROL_ICONS"
                         for target in node.targets))
    forbidden = set(kinds) | {"expander"}
    failures = []
    for path in (ROOT / "PyFLASH/ui").rglob("*.py"):
        if path.name == "controls.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden):
                failures.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.func.attr}")
    assert not failures, "Use controls.widget or controls.fold: " + ", ".join(failures)


def test_discovered_component_options_match_production_signatures():
    contract = json.loads((ROOT / "architecture.yaml").read_text(encoding="utf-8"))
    for component in contract["components"]:
        tree = ast.parse((ROOT / component["path"]).read_text(encoding="utf-8"))
        node = next(node for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == component["symbol"])
        parameters = {arg.arg for arg in
                      [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]}
        if node.args.kwarg is None:
            assert set(component["options"]) <= parameters, component["id"]


def test_new_scientific_module_cannot_import_browser_by_relative_path(tmp_path):
    contract = json.loads((ROOT / "architecture.yaml").read_text(encoding="utf-8"))
    rule = next(rule for rule in contract["boundaries"]
                if rule["id"] == "science-without-browser-adapters")
    package = tmp_path / "PyFLASH"
    package.mkdir()
    (package / "future_statistic.py").write_text(
        "from .ui import workspace\n", encoding="utf-8")
    checked = {"source_root": contract["source_root"],
               "boundaries": [{**rule, "exceptions": []}]}
    issues = _engine().check_boundaries(tmp_path, checked)
    assert any("imports forbidden PyFLASH.ui" in issue for issue in issues), issues


def test_saved_condition_colour_names_keep_existing_frozen_values():
    """Use the existing fixture without importing its optional private-kit tests."""
    from PyFLASH import palette
    tree = ast.parse((ROOT / "tests/test_style_conformance.py").read_text(encoding="utf-8"))
    expected = next(ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name)
                            and target.id == "PICKLED_CONDITION_COLOURS"
                            for target in node.targets))
    assert palette.PIPELINE == expected
    for name, colour in expected.items():
        assert palette.condition_colour(name) == colour, name


def _card_theme(tmp_path):
    """Read the actual Python-owned CSS; do not maintain a second stylesheet."""
    tree = ast.parse((ROOT / "PyFLASH/ui/theme.py").read_text(encoding="utf-8"))
    css = next(ast.literal_eval(node.value) for node in tree.body
               if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == "FUNCTION_CARDS_CSS"
                       for target in node.targets))
    destination = tmp_path / "cards.css"
    destination.write_text(css, encoding="utf-8")
    theme = {
        "files": ["cards.css"],
        "required_tokens": [],
        "runtime_tokens": [
            {"name": name, "reason": "Streamlit supplies this native interface theme token."}
            for name in ("--st-border-color", "--st-text-color", "--st-background-color",
                         "--st-primary-color", "--st-secondary-background-color")
        ],
        "rules": [{
            "path": "cards.css",
            "selectors": [".pf-function-grid", ".pf-function-card", ".pf-function-actions",
                          ".pf-function-actions button", ".pf-picture-card > button",
                          ".pf-picture-card svg"],
            "forbid_raw_colours": True,
            "forbid_fixed_layout": True,
        }],
    }
    return destination, {"theme": theme}


def test_embedded_card_theme_uses_native_colours_and_relative_layout(tmp_path):
    _, contract = _card_theme(tmp_path)
    assert _engine().check_theme(tmp_path, contract) == []


@pytest.mark.parametrize("declaration, expected", [
    ("color: #123456;", "raw colour"),
    ("padding: 48px;", "fixed layout pixels"),
])
def test_embedded_theme_adapter_detects_regressions(tmp_path, declaration, expected):
    stylesheet, contract = _card_theme(tmp_path)
    with stylesheet.open("a", encoding="utf-8") as stream:
        stream.write("\n.pf-function-card {" + declaration + "}\n")
    issues = _engine().check_theme(tmp_path, contract)
    assert any(expected in issue for issue in issues), issues
