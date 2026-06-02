"""Unit tests for the Stage 04 conditions builder.

Exercises the Streamlit-free layers only — ``PyFLASH.ui.project_io`` and
``PyFLASH.ui.services`` — so they run with no UI dependency installed
(house rule 2). Conditions are pure Python, so no data files are needed.

These tests assert that a JSON *spec* replays through ``ConditionBuilder`` to an
equivalent ``conditionList``, that every comparison mode resolves exactly like
``conditions._resolve_comparisons``, that a bad comparison name raises the
builder's difflib ``ValueError``, that crossing two factors produces the
expected ``multiCondition`` set with working ``within=`` / ``order_by``, and
that ``Project`` JSON round-trips and rebuilds an equivalent list.
"""

import ast
import os
import sys

import pytest

from PyFLASH.conditions import _resolve_comparisons, condition, multiCondition
from PyFLASH.ui import services
from PyFLASH.ui.project_io import (
    Project,
    build_condition_list,
    build_factor_list,
    load_project,
    save_project,
)


# ── Streamlit-free guarantee ────────────────────────────────────────────────


def test_conditions_layers_do_not_import_streamlit():
    # project_io + services must be usable with no Streamlit installed.
    assert "streamlit" not in sys.modules


# ── Single-factor build + comparison resolution ─────────────────────────────


def _genotype_spec(mode="pairs"):
    spec = {
        "factor": "Genotype",
        "entries": [
            {"label": "WT", "short": "WT", "color": "blue"},
            {"label": "KO", "short": "KO", "color": "red"},
        ],
    }
    if mode == "pairs":
        spec["comparisons"] = {"mode": "pairs", "pairs": [["WT", "KO"]]}
    return spec


def test_two_condition_design_yields_comparison_1_2():
    cl = build_condition_list(_genotype_spec())
    # Exit gate 1: a single comparison on a 2-condition design -> ['1-2'].
    assert cl.comparisons == ["1-2"]
    assert [c.name for c in cl.condition_list] == ["WT", "KO"]
    assert cl.factor == ["Genotype"]


def test_colors_resolve_palette_key_to_hex():
    cl = build_condition_list(_genotype_spec())
    # 'blue'/'red' are Config.COLORS keys -> resolved to those hex values.
    from PyFLASH.config import Config

    assert cl.condition_list[0].color == Config.COLORS["blue"]
    assert cl.condition_list[1].color == Config.COLORS["red"]


def test_blank_color_auto_assigns_from_palette():
    spec = {
        "factor": "F",
        "entries": [{"label": "A", "short": "A", "color": ""},
                    {"label": "B", "short": "B", "color": ""}],
    }
    cl = build_condition_list(spec)
    # Blank -> auto Okabe-Ito palette (first two entries).
    from PyFLASH.conditions import _AUTO_PALETTE

    assert cl.condition_list[0].color == _AUTO_PALETTE[0]
    assert cl.condition_list[1].color == _AUTO_PALETTE[1]


@pytest.mark.parametrize(
    "mode,extra,sentinel",
    [
        ("all_pairs", {}, [("__ALL_PAIRS__",)]),
        ("vs_control", {"control": "A"}, [("__VS_CONTROL__", "A")]),
        ("sequential", {}, [("__SEQUENTIAL__",)]),
    ],
)
def test_each_mode_matches_resolve_comparisons(mode, extra, sentinel):
    names = ["A", "B", "C"]
    spec = {
        "factor": "F",
        "entries": [{"label": n, "short": n} for n in names],
        "comparisons": {"mode": mode, **extra},
    }
    cl = build_condition_list(spec)
    expected = _resolve_comparisons(sentinel, names)
    # Exit gate 2: every mode resolves exactly like _resolve_comparisons.
    assert cl.comparisons == expected


def test_explicit_pairs_resolve_like_resolve_comparisons():
    names = ["A", "B", "C"]
    spec = {
        "factor": "F",
        "entries": [{"label": n, "short": n} for n in names],
        "comparisons": {"mode": "pairs", "pairs": [["A", "C"], ["B", "C"]]},
    }
    cl = build_condition_list(spec)
    expected = _resolve_comparisons(
        [("__PAIR__", "A", "C"), ("__PAIR__", "B", "C")], names)
    assert cl.comparisons == expected == ["1-3", "2-3"]


def test_explanation_template_expands_per_condition():
    spec = {
        "factor": "Genotype",
        "entries": [{"label": "WT", "short": "WT"},
                    {"label": "KO", "short": "KO"}],
        "explanation": "Mice of type <>",
    }
    cl = build_condition_list(spec)
    assert cl.condition_list[0].factor_explanation == "Mice of type WT"
    assert cl.condition_list[1].factor_explanation == "Mice of type KO"


# ── Bad comparison name -> difflib ValueError ───────────────────────────────


def test_bad_comparison_name_raises_difflib_suggestion():
    spec = {
        "factor": "Genotype",
        "entries": [{"label": "WT", "short": "WT"},
                    {"label": "KO", "short": "KO"}],
        # 'KOO' is within difflib's 0.5 cutoff of 'KO' -> a suggestion appears.
        "comparisons": {"mode": "pairs", "pairs": [["WT", "KOO"]]},
    }
    # Exit gate 3: surfaces the builder's ValueError with a difflib suggestion.
    with pytest.raises(ValueError) as exc:
        build_condition_list(spec)
    msg = str(exc.value)
    assert "not found" in msg
    assert "Did you mean 'KO'" in msg


def test_vs_control_bad_control_raises():
    spec = {
        "factor": "F",
        "entries": [{"label": "A", "short": "A"}, {"label": "B", "short": "B"}],
        "comparisons": {"mode": "vs_control", "control": "Aa"},
    }
    with pytest.raises(ValueError):
        build_condition_list(spec)


# ── Crossing two factor lists ───────────────────────────────────────────────


def _cross_specs():
    f1 = {"factor": "Genotype",
          "entries": [{"label": "WT", "short": "WT"},
                      {"label": "KO", "short": "KO"}]}
    f2 = {"factor": "Time",
          "entries": [{"label": "WeekOne", "short": "W1"},
                      {"label": "WeekTwo", "short": "W2"}]}
    return f1, f2


def test_crossing_produces_expected_multicondition_set():
    f1, f2 = _cross_specs()
    spec = {"crossed": True, "factors": [f1, f2]}
    cl = build_condition_list(spec)
    # Exit gate 4: factorial product, grouped by the first factor by default.
    assert [c.name for c in cl.condition_list] == ["WTW1", "WTW2", "KOW1", "KOW2"]
    assert all(isinstance(c, multiCondition) for c in cl.condition_list)
    assert cl.factor == ["Genotype", "Time"]
    # Flattened single conditions (2 genotypes x 2 timepoints unique).
    assert all(isinstance(c, condition) for c in cl.conditions)


def test_crossed_within_pair_disambiguates_by_index():
    f1, f2 = _cross_specs()
    spec = {
        "crossed": True,
        "factors": [f1, f2],
        "comparisons": {"mode": "pairs", "pairs": [["WT", "KO", "W2"]]},
    }
    cl = build_condition_list(spec)
    # WTW2 is position 2, KOW2 is position 4 -> '2-4'.
    assert cl.comparisons == ["2-4"]


def test_crossed_all_pairs_within_factor():
    f1, f2 = _cross_specs()
    spec = {
        "crossed": True,
        "factors": [f1, f2],
        "comparisons": {"mode": "all_pairs", "within_factor": "Time"},
    }
    cl = build_condition_list(spec)
    # Compare genotypes within each timepoint: (WTW1,KOW1)=1-3, (WTW2,KOW2)=2-4.
    assert cl.comparisons == ["1-3", "2-4"]


def test_crossed_order_by_regroups_and_reindexes():
    f1, f2 = _cross_specs()
    spec = {
        "crossed": True,
        "factors": [f1, f2],
        "order_by": "Time",
        "comparisons": {"mode": "all_pairs", "within_factor": "Time"},
    }
    cl = build_condition_list(spec)
    # order_by('Time') regroups so each timepoint is contiguous...
    assert [c.name for c in cl.condition_list] == ["WTW1", "KOW1", "WTW2", "KOW2"]
    # ...and the resolved indices follow the new ordering.
    assert cl.comparisons == ["1-2", "3-4"]


def test_crossed_vs_control_within_factor():
    f1, f2 = _cross_specs()
    spec = {
        "crossed": True,
        "factors": [f1, f2],
        "comparisons": {"mode": "vs_control", "control": "WT",
                        "within_factor": "Time"},
    }
    cl = build_condition_list(spec)
    # WT control vs KO within each timepoint: W1 -> 1-3, W2 -> 2-4.
    assert cl.comparisons == ["1-3", "2-4"]


def test_crossed_bad_within_name_raises():
    f1, f2 = _cross_specs()
    spec = {
        "crossed": True,
        "factors": [f1, f2],
        "comparisons": {"mode": "pairs", "pairs": [["WT", "KO", "WeekNine"]]},
    }
    with pytest.raises(ValueError):
        build_condition_list(spec)


def test_crossed_requires_two_factors():
    f1, _ = _cross_specs()
    with pytest.raises(ValueError):
        build_condition_list({"crossed": True, "factors": [f1]})


def test_build_factor_list_matches_simple_build():
    spec = _genotype_spec()
    a = build_factor_list(spec)
    b = build_condition_list(spec)
    assert [c.name for c in a.condition_list] == [c.name for c in b.condition_list]
    assert a.comparisons == b.comparisons


# ── services wrappers ───────────────────────────────────────────────────────


def test_build_conditions_service_matches_project_io():
    spec = _genotype_spec()
    cl = services.build_conditions(spec)
    assert cl.comparisons == ["1-2"]


def test_preview_conditions_reports_names_colors_comparisons():
    cl = services.build_conditions(_genotype_spec())
    preview = services.preview_conditions(cl)
    assert preview["factor"] == ["Genotype"]
    assert [c["name"] for c in preview["conditions"]] == ["WT", "KO"]
    # Resolved '1-2' style strings, plus a human-readable echo.
    assert preview["comparisons"] == ["1-2"]
    assert preview["labelled_comparisons"] == ["WT vs KO"]
    # Colors are resolved hex (palette keys -> hex).
    assert all(c["color"].startswith("#") for c in preview["conditions"])


def test_preview_conditions_handles_none():
    preview = services.preview_conditions(None)
    assert preview["conditions"] == []
    assert preview["comparisons"] is None


def test_resolve_color_palette_key_wins_over_css():
    from PyFLASH.config import Config

    # 'blue' is a Config.COLORS key; it must win over the CSS 'blue'.
    assert services.resolve_color("blue") == Config.COLORS["blue"]
    # A bare hex passes through; None auto-assigns from the palette.
    assert services.resolve_color("#123456") == "#123456"
    assert services.resolve_color(None, 0).startswith("#")


# ── Project JSON round-trip + rebuild ───────────────────────────────────────


def test_project_to_json_from_json_round_trips_conditions():
    spec = {
        "factor": "Genotype",
        "entries": [{"label": "WT", "short": "WT", "color": "blue"},
                    {"label": "KO", "short": "KO", "color": "red"}],
        "comparisons": {"mode": "all_pairs"},
        "explanation": "Mice of type <>",
    }
    proj = Project(name="design", conditions=spec)

    restored = Project.from_json(proj.to_json())
    # Exit gate 5: spec survives the JSON round-trip verbatim.
    assert restored.conditions == spec

    original = build_condition_list(proj.conditions)
    rebuilt = build_condition_list(restored.conditions)
    # ...and rebuilds an equivalent conditionList.
    assert [c.name for c in original.condition_list] == \
        [c.name for c in rebuilt.condition_list]
    assert original.comparisons == rebuilt.comparisons
    assert [c.color for c in original.condition_list] == \
        [c.color for c in rebuilt.condition_list]
    assert restored.condition_list().comparisons == original.comparisons


def test_project_file_round_trips_crossed_design(tmp_path):
    f1, f2 = _cross_specs()
    spec = {
        "crossed": True,
        "factors": [f1, f2],
        "order_by": "Time",
        "comparisons": {"mode": "all_pairs", "within_factor": "Time"},
        "explanation": "Crossed <>",
    }
    proj = Project(name="crossed", conditions=spec)
    out = tmp_path / "proj.json"
    save_project(proj, str(out))
    loaded = load_project(str(out))

    assert loaded.conditions == spec
    cl = build_condition_list(loaded.conditions)
    assert [c.name for c in cl.condition_list] == ["WTW1", "KOW1", "WTW2", "KOW2"]
    assert cl.comparisons == ["1-2", "3-4"]


def test_empty_conditions_build_returns_none():
    assert build_condition_list({}) is None
    assert Project().condition_list() is None


# ── Page is importable as source (no Streamlit needed to parse) ─────────────


def test_conditions_page_parses_as_python():
    here = os.path.dirname(os.path.dirname(os.path.abspath(services.__file__)))
    page = os.path.join(here, "ui", "pages", "3_conditions.py")
    with open(page, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    # Sanity: the page does import streamlit (pages may; services must not).
    assert any(
        isinstance(n, ast.Import) and any(a.name == "streamlit" for a in n.names)
        for n in ast.walk(tree)
    )
