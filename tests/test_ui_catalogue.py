"""Public coverage, source fidelity and safe navigation for the functions page."""
import ast
import sys

import pytest


from PyFLASH.spec import PLOT_REGISTRY
from PyFLASH.ui import catalogue, workspace, function_cards


def test_every_registered_action_has_exact_help_and_canonical_setup():
    actions = {item.action: item for item in catalogue.functions() if item.action}
    assert actions.keys() == PLOT_REGISTRY.keys()
    for alias, item in actions.items():
        reference = workspace.plot_reference(alias)
        assert item.signature == reference["signature"]
        assert item.documentation == reference["documentation"]
        page, preferences = catalogue.setup(item)
        assert page in {"6_plots.py", "7_images.py"}
        assert preferences
    assert catalogue.setup(actions["locations"])[1] == {"ui_image_open_location": True}
    assert catalogue.setup(actions["representative_images"])[1] == {"ui_image_mode": "Representative images"}


def test_catalogue_covers_source_definitions_without_private_or_ui_helpers():
    items = catalogue.functions()
    keys = {f"{i.module}.{i.name}" for i in items}
    assert len({i.key for i in items}) == len(items)
    expected = set()
    for path in catalogue.ROOT.glob("*.py"):
        if path.stem.startswith("_") and path.stem not in {"__init__", "_logging"}:
            continue
        module = "PyFLASH" if path.stem == "__init__" else f"PyFLASH.{path.stem}"
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                expected.add(f"{module}.{node.name}")
                if isinstance(node, ast.ClassDef):
                    for method in node.body:
                        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and not method.name.startswith("_"):
                            if not any(ast.unparse(d) in {"property", f"{method.name}.setter"} for d in method.decorator_list):
                                expected.add(f"{module}.{node.name}.{method.name}")
    assert keys == expected
    assert all(".ui." not in i.module for i in items)
    assert all(not part.startswith("_") for i in items for part in i.name.split("."))


def test_aliases_search_defaults_required_arguments_and_call_templates():
    items = catalogue.functions()
    builder = next(i for i in items if i.key == "PyFLASH.conditions.ConditionBuilder")
    assert "PyFLASH.GroupBuilder" in builder.aliases
    assert catalogue.search(items, "PyFLASH.GroupBuilder")[0] == builder
    build = next(i for i in items if i.key == "PyFLASH.conditions.ConditionBuilder.build")
    assert "PyFLASH.GroupBuilder.build" in build.aliases
    assert catalogue.search(items, "PyFLASH.GroupBuilder.build")[0] == build
    save = next(i for i in items if i.key == "PyFLASH.utils.save_fig")
    assert catalogue.search(items, "save_fig", module="PyFLASH.utils")[0] == save
    assert any(p.name == "figure_formats" for p in save.parameters)
    assert catalogue.search(items, "impossible_function_name") == ()
    assert all(i.action for i in catalogue.search(items, kind="Registered figure"))
    for item in items:
        ast.parse(catalogue.call_template(item))
        if not item.action:
            assert catalogue.setup(item) == (None, {})
    bars = next(i for i in items if i.action == "mean_bars")
    required = [p.name for p in bars.parameters if p.required]
    assert required == ["experiment"]
    assert next(p for p in bars.parameters if p.name == "points").default == "True"
    assert next(p for p in bars.parameters if p.name == "data_cols").description


def test_source_changes_invalidate_cache_without_importing_analysis(tmp_path, monkeypatch):
    package = tmp_path / "PyFLASH"
    package.mkdir()
    source = package / "toy.py"
    source.write_text('def public(x, /, *, threshold=0.05, **options):\n    """Help."""\n    raise RuntimeError("must never run")\n\ndef _private():\n    pass\n', encoding="utf-8")
    monkeypatch.setattr(catalogue, "ROOT", package)
    monkeypatch.setattr("PyFLASH.spec.PLOT_REGISTRY", {})
    modules = set(sys.modules)
    item, = catalogue.functions()
    assert item.signature == "public(x, /, *, threshold=0.05, **options)"
    assert [(p.name, p.required) for p in item.parameters] == [("x", True), ("threshold", False), ("options", False)]
    source.write_text('def public(x, /, *, threshold=0.01):\n    """New help."""\n    pass\n', encoding="utf-8")
    revised, = catalogue.functions()
    assert "0.01" in revised.signature and revised.documentation == "New help."
    assert not (set(sys.modules) - modules) & {"streamlit", "PyFLASH.plotting", "PyFLASH.pipeline", "matplotlib", "statsmodels"}


def test_multiline_header_literal_help_and_binding_are_read_without_bodies():
    source = '''class Example:
    """Example help."""
    def __init__(self, x):
        self.x = x
    @classmethod
    def make(cls, x: int = 3):
        """Create an example."""
        return cls(x)
    @property
    def value(self):
        return self.x

def public(
    x: str = "a:b",
    *, settings={"label": ")"},
):
    """First """ """second."""
    raise RuntimeError("must never run")
'''
    tree = catalogue._interface_tree(source)
    assert [n.name for n in tree.body] == ["Example", "public"]
    node = tree.body[-1]
    assert ast.get_docstring(node) == "First second."
    assert ast.unparse(node.args) == "x: str='a:b', *, settings={'label': ')'}"
    method = tree.body[0].body[2]
    assert ast.unparse(method.decorator_list[0]) == "classmethod"


def test_functions_page_shows_every_match_together_without_a_dataset(monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    rendered = []
    events = []
    def render(items, selected=None, **kwargs):
        rendered.append(items)
        return events.pop(0) if events else None
    monkeypatch.setattr(function_cards, "render", render)
    app = AppTest.from_file(str(catalogue.ROOT / "ui/pages/9_functions.py"), default_timeout=20)
    app.session_state["ui_functions_page"] = 37
    app.run()
    assert not app.exception
    from PyFLASH.ui import function_contracts as fc
    items = tuple(c.entry for c in fc.catalogue_contracts())
    assert tuple(c.entry for c in rendered[-1]) == items
    assert all(select.label != "Page" for select in app.selectbox)
    assert "ui_functions_page" not in app.session_state
    selected_before_search = app.session_state["ui_function_selection"]
    app.text_input(key="ui_functions_search").set_value("mean_bars").run()
    assert not app.exception
    assert {c.entry.key for c in rendered[-1]} == {i.key for i in catalogue.search(items, "mean_bars")}
    app.text_input(key="ui_functions_search").set_value("no_such_function_12345").run()
    assert not app.exception
    assert rendered[-1] == ()
    assert app.session_state["ui_function_selection"] == selected_before_search
    app.text_input(key="ui_functions_search").set_value("").run()
    assert not app.exception
    assert tuple(c.entry for c in rendered[-1]) == items
    events.append({"key":items[0].key, "operation":"details"})
    app.run()
    assert not app.exception
    assert app.session_state["ui_function_selection"] == items[0].key
    assert not any(button.label == "Run" and not button.disabled for button in app.button)


def test_continuous_cards_cover_all_entries_escape_help_and_validate_clicks():
    from dataclasses import replace
    items = catalogue.functions()
    html = function_cards.markup(items)
    assert html.count('<article ') == len(items)
    assert html.count('data-operation="details"') == len(items)
    assert html.count('data-operation="setup"') == len(PLOT_REGISTRY)
    assert f'data-function-key="{items[-1].key}"' in html
    unsafe = replace(items[0], documentation='<img src=x onerror="alert(1)">', name='"bad<name>')
    safe_html = function_cards.markup([unsafe])
    assert '<img' not in safe_html and '&lt;img' in safe_html
    assert function_cards.selection(items, {"key":items[0].key,"operation":"details"}) == (items[0], "details")
    assert function_cards.selection(items, {"key":"unknown","operation":"details"}) is None
    assert function_cards.selection(items, {"key":items[0].key,"operation":"execute"}) is None
    python_only = next(i for i in items if not i.action)
    assert function_cards.selection(items, {"key":python_only.key,"operation":"setup"}) is None
