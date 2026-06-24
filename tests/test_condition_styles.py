"""Tests for the condition ``style`` channel and bar-style collision resolution.

``style`` is the second visual channel for bars (alongside ``color``):
``"fill"`` (default solid), ``"hollow"`` (outline only), or a matplotlib hatch
pattern. In a crossed design colour collapses onto the primary factor, so style
is what keeps the secondary factor (e.g. sex) distinguishable — either authored
explicitly or resolved automatically at plot time.
"""

import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

import PyFLASH.plotting as plotting
from PyFLASH.batch import Batch
from PyFLASH.conditions import (
    ConditionBuilder,
    condition,
    conditionList,
    zipConditionLists,
    zipConditions,
    DEFAULT_STYLE,
)
from PyFLASH.experiment import MiniExperiment
from PyFLASH.iteration import Context
from PyFLASH.plotting import (
    _apply_bar_style,
    _apply_pie_wedge_style,
    _bar_style_cycle,
    _condition_style_handles,
    _condition_style_map,
    _factor_style_map,
    _resolve_group_styles,
    _resolved_condition_style,
    _style_patch,
    _style_render,
    plot_condition_key,
)
from PyFLASH.ui.project_io import build_condition_list


def _crossed_conditions():
    diagnosis = conditionList([
        condition("AD", "AD", "#9f1c1f", "Diagnosis"),
        condition("Control", "Control", "#787a7c", "Diagnosis"),
    ])
    Male, Female = zipConditions(["Male", "Female"], ["Male", "Female"], [None, None], "Sex")
    return conditionList(list(zipConditionLists(diagnosis, conditionList([Male, Female]))))


# ── model: conditions carry a style, default "fill" ────────────────────────


def test_single_condition_defaults_to_fill():
    assert condition("WT", "WT", "#1f77b4", "Genotype").style == DEFAULT_STYLE
    assert condition("WT", "WT", "#1f77b4", "Genotype", style=None).style == "fill"


def test_builder_add_records_style():
    cl = (
        ConditionBuilder("Sex")
        .add("Male", "M")
        .add("Female", "F", style="hollow")
        .build()
    )
    styles = {c.name: c.style for c in cl}
    assert styles == {"M": "fill", "F": "hollow"}


def test_crossed_condition_takes_colour_from_primary_and_style_from_secondary():
    diagnosis = (
        ConditionBuilder("Diagnosis")
        .add("AD", "AD", color="red")
        .add("Control", "Ctrl", color="blue")
        .build()
    )
    sex = (
        ConditionBuilder("Sex")
        .add("Male", "M")
        .add("Female", "F", style="hollow")
        .build()
    )
    crossed = ConditionBuilder.cross(diagnosis, sex).build()

    # Colour mirrors the primary factor; style mirrors the secondary factor.
    by_name = {c.name: (c.color, c.style) for c in crossed}
    assert by_name["ADM"][1] == "fill"
    assert by_name["ADF"][1] == "hollow"
    assert by_name["ADM"][0] == by_name["ADF"][0]  # same colour (AD)
    assert by_name["CtrlM"][1] == "fill"
    assert by_name["CtrlF"][1] == "hollow"


def test_context_style_falls_back_to_fill_without_condition():
    styled = condition("F", "F", "#000000", "Sex", style="hollow")
    assert Context(experiment=None, condition_obj=styled).style == "hollow"
    assert Context(experiment=None, condition_obj=None).style == "fill"


# ── serialization: style round-trips through the project JSON spec ─────────


def test_style_round_trips_through_project_spec():
    spec = {
        "factor": "Sex",
        "entries": [
            {"label": "Male", "short": "M"},                    # no style -> fill
            {"label": "Female", "short": "F", "style": "hollow"},
        ],
    }
    cl = build_condition_list(spec)
    assert {c.name: c.style for c in cl} == {"M": "fill", "F": "hollow"}


# ── collision resolution: vary only true (colour, style) collisions ────────


def test_no_collision_design_stays_all_fill():
    order = ["AD", "Ctrl"]
    colors = {"AD": "#ff0000", "Ctrl": "#0000ff"}
    styles = {"AD": "fill", "Ctrl": "fill"}
    assert _resolve_group_styles(order, colors, styles) == {"AD": "fill", "Ctrl": "fill"}


def test_shared_colour_auto_varies_keeping_first_solid():
    # Crossed diagnosis x sex with no authored styles: each colour bucket holds
    # two bars; the first stays solid, the second becomes hollow (fill->hollow).
    order = ["ADM", "ADF", "CtrlM", "CtrlF"]
    colors = {"ADM": "#ff0000", "ADF": "#ff0000", "CtrlM": "#0000ff", "CtrlF": "#0000ff"}
    styles = {k: "fill" for k in order}
    resolved = _resolve_group_styles(order, colors, styles)
    assert resolved == {"ADM": "fill", "ADF": "hollow", "CtrlM": "fill", "CtrlF": "hollow"}


def test_explicit_style_is_honoured_and_not_reused_by_auto_vary():
    # One member authored hollow; the colliding default takes the next free
    # cycle slot (fill), never duplicating the authored hollow.
    order = ["ADM", "ADF"]
    colors = {"ADM": "#ff0000", "ADF": "#ff0000"}
    styles = {"ADM": "fill", "ADF": "hollow"}
    resolved = _resolve_group_styles(order, colors, styles)
    assert resolved == {"ADM": "fill", "ADF": "hollow"}


def test_three_level_secondary_factor_uses_hatch_after_hollow():
    order = ["a", "b", "c"]
    colors = {k: "#ff0000" for k in order}
    styles = {k: "fill" for k in order}
    resolved = _resolve_group_styles(order, colors, styles)
    assert resolved == {"a": "fill", "b": "hollow", "c": "///"}


def test_style_cycle_override_changes_auto_assignment():
    order = ["a", "b"]
    colors = {k: "#ff0000" for k in order}
    styles = {k: "fill" for k in order}
    resolved = _resolve_group_styles(order, colors, styles, style_cycle=["fill", "xxx"])
    assert resolved == {"a": "fill", "b": "xxx"}


def test_default_cycle_is_fill_then_hollow_then_hatch():
    assert _bar_style_cycle()[:3] == ["fill", "hollow", "///"]


# ── rendering: style tokens map to the right matplotlib patch properties ───


def test_apply_bar_style_hollow_clears_fill_and_outlines_in_colour():
    fig, ax = plt.subplots()
    try:
        bars = ax.bar([0], [1], color="#ff0000")
        _apply_bar_style(list(bars), "hollow", "#ff0000")
        patch = bars[0]
        assert patch.get_facecolor()[3] == 0.0          # transparent fill
        assert matplotlib.colors.to_hex(patch.get_edgecolor()) == "#ff0000"
        assert patch.get_hatch() is None
    finally:
        plt.close(fig)


def test_apply_bar_style_hatch_sets_pattern_over_colour_fill():
    fig, ax = plt.subplots()
    try:
        bars = ax.bar([0], [1], color="#ff0000")
        _apply_bar_style(list(bars), "///", "#ff0000")
        patch = bars[0]
        assert matplotlib.colors.to_hex(patch.get_facecolor()) == "#ff0000"
        assert patch.get_hatch() == "///"
    finally:
        plt.close(fig)


# ── integration: the crossed diagnosis x sex bug, end to end ───────────────


def _crossed_human_batch(tmp_path):
    """A diagnosis x sex batch with both sexes of two diagnoses present.

    Each diagnosis colour therefore appears twice (once per sex) — exactly the
    duplicate-colour case the style channel exists to disambiguate.
    """
    csv = "\n".join([
        "ID,Diagnosis,Sex,Period (h),Amplitude,Phase",
        "1,Dementia-AD,Female,24.2,1.1,6.0",
        "2,Dementia-AD,Male,23.9,1.4,6.4",
        "3,Healthy control,Female,23.8,0.9,7.1",
        "4,Healthy control,Male,22.7,1.7,7.8",
        ",,,,,",
    ])
    data_path = tmp_path / "Data.csv"
    data_path.write_text(csv, encoding="utf-8")

    diagnosis = conditionList([
        condition("AD", "AD", "#9f1c1f", "Diagnosis"),
        condition("MCI", "MCI", "#4369b2", "Diagnosis"),
        condition("Control", "Control", "#787a7c", "Diagnosis"),
    ])
    Male, Female = zipConditions(["Male", "Female"], ["Male", "Female"], [None, None], "Sex")
    crossed = conditionList(list(zipConditionLists(diagnosis, conditionList([Male, Female]))))

    exp = MiniExperiment(
        "Human", str(tmp_path), animal_column="ID",
        factor_mappings={
            "Diagnosis": {"Dementia-AD": "AD", "MCI-AD": "MCI", "Healthy control": "Control"},
            "Sex": {"male": "Male", "female": "Female", "Male": "Male", "Female": "Female"},
        },
    )
    batch = Batch("human", [exp], crossed, str(tmp_path))
    batch.processData(import_images=False, progress=False)
    return batch


def test_plot_mean_bars_auto_styles_only_the_colliding_sex(tmp_path, monkeypatch):
    batch = _crossed_human_batch(tmp_path)
    assert batch.summary["Condition"].tolist() == [
        "ADFemale", "ADMale", "ControlFemale", "ControlMale",
    ]

    calls = []
    original = plotting._apply_bar_style

    def spy(patches, style, color, line_width=2.5):
        calls.append((style, color))
        return original(patches, style, color, line_width)

    monkeypatch.setattr(plotting, "_apply_bar_style", spy)
    plotting.plot_mean_bars(
        batch, filtered_columns=["Period(h)"], points=False, save=False,
    )

    # The second bar of each diagnosis colour (the Females) is restyled hollow;
    # the first (Males) stays solid and never triggers a restyle.
    assert calls == [("hollow", "#9f1c1f"), ("hollow", "#787a7c")]


def test_plot_mean_bars_auto_style_off_keeps_every_bar_solid(tmp_path, monkeypatch):
    batch = _crossed_human_batch(tmp_path)

    calls = []
    monkeypatch.setattr(
        plotting, "_apply_bar_style",
        lambda *a, **k: calls.append(a),
    )
    plotting.plot_mean_bars(
        batch, filtered_columns=["Period(h)"], points=False, save=False,
        auto_style=False,
    )
    assert calls == []


# ── follow-up #2: the style channel reaches radar / pie / regression ───────


def test_plot_mean_bars_save_false_does_not_write_svg(tmp_path):
    batch = _crossed_human_batch(tmp_path)

    plotting.plot_mean_bars(
        batch, filtered_columns=["Period(h)"], points=False, save=False,
    )

    written_svgs = [
        filename
        for _root, _dirs, files in os.walk(batch.fig_path)
        for filename in files
        if filename.endswith(".svg")
    ]
    assert written_svgs == []


class _Exp:
    """Minimal stand-in carrying a condition_list (+ fig_path for the key)."""

    def __init__(self, condition_list, fig_path="."):
        self.condition_list = condition_list
        self.fig_path = fig_path


def test_style_render_maps_each_token_family():
    assert _style_render("fill") == {
        "filled": True, "hatch": None, "linestyle": "-", "marker_filled": True}
    hollow = _style_render("hollow")
    assert hollow["filled"] is False and hollow["linestyle"] == "--"
    assert hollow["marker_filled"] is False and hollow["hatch"] is None
    hatch = _style_render("///")
    assert hatch == {
        "filled": True, "hatch": "///", "linestyle": ":", "marker_filled": True}


def test_condition_style_map_varies_crossed_collisions():
    exp = _Exp(_crossed_conditions())
    assert _condition_style_map(exp) == {
        "ADMale": "fill", "ADFemale": "hollow",
        "ControlMale": "fill", "ControlFemale": "hollow",
    }
    # auto_style off collapses everything back to solid.
    assert set(_condition_style_map(exp, auto_style=False).values()) == {"fill"}


def test_resolved_condition_style_caches_and_handles_factor_mode():
    exp = _Exp(_crossed_conditions())
    state = {}
    ctx = Context(experiment=exp, condition="ADFemale")
    assert _resolved_condition_style(ctx, state) == "hollow"
    assert "__condition_style_map__" in state  # design-wide map cached once

    # Factor mode resolves over the factor's own levels (factorDict). Here the
    # two Sex levels share a colour, so the second varies to hollow.
    factor_state = {}
    fctx_female = Context(experiment=exp, factor="Sex", factor_value="Female")
    assert _resolved_condition_style(fctx_female, factor_state) == "hollow"
    assert "__factor_style_map__" in factor_state
    fctx_male = Context(experiment=exp, factor="Sex", factor_value="Male")
    assert _resolved_condition_style(fctx_male, {}) == "fill"


def test_factor_style_map_honours_authored_level_styles():
    diagnosis = (ConditionBuilder("Diagnosis")
                 .add("AD", "AD", color="red").add("Control", "Ctrl", color="blue").build())
    sex = (ConditionBuilder("Sex")
           .add("Male", "M", color="green")
           .add("Female", "F", color="orange", style="///").build())
    exp = _Exp(ConditionBuilder.cross(diagnosis, sex).build())
    # Distinct level colours -> no auto-vary; the authored hatch is honoured.
    assert _factor_style_map(exp, "Sex") == {"M": "fill", "F": "///"}
    # auto_style off collapses the authored style back to solid.
    assert _factor_style_map(exp, "Sex", auto_style=False) == {"M": "fill", "F": "fill"}


def test_present_subset_does_not_style_a_lone_colour_survivor():
    exp = _Exp(_crossed_conditions())
    # ControlMale absent from the data: ControlFemale is then alone in its
    # colour bucket and must stay solid, while the AD pair still collides.
    present = {"ADMale", "ADFemale", "ControlFemale"}
    m = _condition_style_map(exp, present=present)
    assert m["ControlFemale"] == "fill"
    assert m["ADMale"] == "fill"
    assert m["ADFemale"] == "hollow"
    assert "ControlMale" not in m


def test_auto_style_off_suppresses_even_authored_styles():
    sex = (ConditionBuilder("Sex").add("Male", "M")
           .add("Female", "F", style="hollow").build())
    diagnosis = ConditionBuilder("Diagnosis").add("AD", "AD", color="red").build()
    exp = _Exp(ConditionBuilder.cross(diagnosis, sex).build())
    # With auto_style on, the authored hollow survives; off, everything is fill.
    on = _condition_style_map(exp, auto_style=True)
    assert "hollow" in on.values()
    off = _condition_style_map(exp, auto_style=False)
    assert set(off.values()) == {"fill"}


def test_style_patch_reflects_fill_hollow_and_hatch():
    solid = _style_patch("#ff0000", "fill", "AD")
    assert matplotlib.colors.to_hex(solid.get_facecolor()) == "#ff0000"
    hollow = _style_patch("#ff0000", "hollow", "ADf")
    assert hollow.get_facecolor()[3] == 0.0
    assert matplotlib.colors.to_hex(hollow.get_edgecolor()) == "#ff0000"
    hatch = _style_patch("#ff0000", "///", "ADh")
    assert hatch.get_hatch() == "///"


def test_condition_style_handles_one_swatch_per_condition():
    handles, labels = _condition_style_handles(_Exp(_crossed_conditions()))
    assert len(handles) == 4 == len(labels)
    # Order follows condition_list: ADMale (solid), ADFemale (hollow), ...
    assert handles[0].get_facecolor()[3] == 1.0
    assert handles[1].get_facecolor()[3] == 0.0


def test_apply_pie_wedge_style_hatches_non_fill_only():
    fig, ax = plt.subplots()
    try:
        hollow_wedges = ax.pie([1, 1, 1])[0]
        _apply_pie_wedge_style(hollow_wedges, "hollow", "#ff0000")
        assert all(w.get_hatch() == "oo" for w in hollow_wedges)  # default for hollow

        fill_wedges = ax.pie([1, 1])[0]
        _apply_pie_wedge_style(fill_wedges, "fill", "#00ff00")
        assert all(not w.get_hatch() for w in fill_wedges)
    finally:
        plt.close(fig)


def test_apply_pie_wedge_style_keeps_hollow_and_slash_distinct():
    # 2nd ("hollow") and 3rd ("///") default cycle levels must not collapse to
    # the same hatch when 3+ same-colour levels land on pies.
    fig, ax = plt.subplots()
    try:
        hollow = ax.pie([1, 1])[0]
        _apply_pie_wedge_style(hollow, "hollow", "#ff0000")
        slash = ax.pie([1, 1])[0]
        _apply_pie_wedge_style(slash, "///", "#ff0000")
        assert hollow[0].get_hatch() != slash[0].get_hatch()
        assert hollow[0].get_hatch() == "oo" and slash[0].get_hatch() == "///"
    finally:
        plt.close(fig)


def test_plot_regressions_opens_markers_for_the_colliding_sex(tmp_path, monkeypatch):
    batch = _crossed_human_batch(tmp_path)
    seen = {}
    original = plotting._resolved_condition_style

    def spy(ctx, state, auto_style=True, style_cycle=None):
        style = original(ctx, state, auto_style, style_cycle)
        seen[ctx.condition] = style
        return style

    monkeypatch.setattr(plotting, "_resolved_condition_style", spy)
    plotting.plot_regressions(
        batch, x="Period(h)", y="Amplitude", combine=True, save=False)
    assert seen.get("ADFemale") == "hollow"
    assert seen.get("ADMale") == "fill"


def test_plot_radar_styles_the_colliding_sex(tmp_path, monkeypatch):
    batch = _crossed_human_batch(tmp_path)
    seen = {}
    original = plotting._resolved_condition_style

    def spy(ctx, state, auto_style=True, style_cycle=None):
        style = original(ctx, state, auto_style, style_cycle)
        seen[ctx.condition] = style
        return style

    monkeypatch.setattr(plotting, "_resolved_condition_style", spy)
    plotting.plot_radar(
        batch, filtered_columns=["Period(h)", "Amplitude", "Phase"],
        combine=True, save=False)
    assert seen.get("ADFemale") == "hollow"
    assert seen.get("ControlFemale") == "hollow"


def test_queue_branch_propagates_auto_style_false(tmp_path, monkeypatch):
    # A queued y input exercises the x/y-queue recursive branch; auto_style must
    # survive the recursion (else it silently reverts to the default-on styling).
    batch = _crossed_human_batch(tmp_path)
    seen = {}
    original = plotting._resolved_condition_style

    def spy(ctx, state, auto_style=True, style_cycle=None):
        style = original(ctx, state, auto_style, style_cycle)
        seen[ctx.condition] = style
        return style

    monkeypatch.setattr(plotting, "_resolved_condition_style", spy)
    plotting.plot_regressions(
        batch, x="Period(h)", y=["Amplitude", "Phase"],
        combine=True, save=False, auto_style=False)
    assert seen  # the recursive branch actually ran
    assert set(seen.values()) == {"fill"}  # auto_style=False reached the leaf call


def test_non_bar_plot_does_not_style_lone_colour_survivor(tmp_path, monkeypatch):
    # A cohort missing ControlMale: ControlFemale is alone in its colour bucket
    # among the *rendered* groups, so a regression must keep it solid even though
    # ControlMale still exists in the design's condition_list.
    csv = "\n".join([
        "ID,Diagnosis,Sex,Period (h),Amplitude,Phase",
        "1,Dementia-AD,Female,24.2,1.1,6.0",
        "2,Dementia-AD,Male,23.9,1.4,6.4",
        "3,Healthy control,Female,23.8,0.9,7.1",
        ",,,,,",
    ])
    (tmp_path / "Data.csv").write_text(csv, encoding="utf-8")
    exp = MiniExperiment(
        "Human", str(tmp_path), animal_column="ID",
        factor_mappings={
            "Diagnosis": {"Dementia-AD": "AD", "Healthy control": "Control"},
            "Sex": {"male": "Male", "female": "Female", "Male": "Male", "Female": "Female"},
        },
    )
    batch = Batch("human", [exp], _crossed_conditions(), str(tmp_path))
    batch.processData(import_images=False, progress=False)
    assert "ControlMale" not in batch.summary["Condition"].tolist()

    seen = {}
    original = plotting._resolved_condition_style

    def spy(ctx, state, auto_style=True, style_cycle=None):
        style = original(ctx, state, auto_style, style_cycle)
        seen[ctx.condition] = style
        return style

    monkeypatch.setattr(plotting, "_resolved_condition_style", spy)
    plotting.plot_regressions(batch, x="Period(h)", y="Amplitude", combine=True, save=False)
    assert seen.get("ControlFemale") == "fill"  # partner absent -> no collision
    assert seen.get("ADFemale") == "hollow"      # AD pair present -> collides


def test_pie_bar_mode_styles_colliding_groups(tmp_path, monkeypatch):
    # plot_format="bar" renders one stacked bar per condition; same-colour
    # crossed groups must get a hatch on their stack (matching the pie wedges).
    rows = ["ID,Diagnosis,Sex,Period (h),Region"]
    i = 0
    for diag in ("Dementia-AD", "Healthy control"):
        for sex in ("Female", "Male"):
            for region in ("CA1", "CA1", "DG"):
                i += 1
                rows.append(f"{i},{diag},{sex},{23 + i * 0.1:.1f},{region}")
    rows.append(",,,,")
    (tmp_path / "Data.csv").write_text("\n".join(rows), encoding="utf-8")
    exp = MiniExperiment(
        "Human", str(tmp_path), animal_column="ID",
        factor_mappings={
            "Diagnosis": {"Dementia-AD": "AD", "Healthy control": "Control"},
            "Sex": {"Male": "Male", "Female": "Female"},
        },
    )
    batch = Batch("human", [exp], _crossed_conditions(), str(tmp_path))
    batch.processData(import_images=False, progress=False)

    calls = []
    original = plotting._apply_pie_wedge_style

    def spy(wedges, style, color):
        calls.append((style, color))
        return original(wedges, style, color)

    monkeypatch.setattr(plotting, "_apply_pie_wedge_style", spy)
    plotting.plot_pie_charts(
        batch, marker="Data", x_attr="Region", plot_format="bar", save=False)

    # Only the second of each colour pair (the Females) is hatched; Males stay solid.
    assert calls, "stacked-bar mode never applied the style channel"
    assert {style for style, _ in calls} == {"hollow"}


# ── follow-up #3: standalone colour+style key ──────────────────────────────


def test_plot_condition_key_saves_a_swatch_figure(tmp_path):
    exp = _Exp(_crossed_conditions(), fig_path=str(tmp_path))
    path = plot_condition_key(exp, save=True)
    assert os.path.exists(path)
    assert path.endswith("condition_key.png")


def test_plot_mean_bars_can_fill_points_with_group_colour(tmp_path, monkeypatch):
    batch = _crossed_human_batch(tmp_path)

    calls = []
    original = plotting.sns.swarmplot

    def spy(*args, **kwargs):
        calls.append(kwargs.copy())
        return original(*args, **kwargs)

    monkeypatch.setattr(plotting.sns, "swarmplot", spy)
    plotting.plot_mean_bars(
        batch, filtered_columns=["Period(h)"], points=True, save=False,
        point_fill="group", point_edge="none", point_size=4,
        point_linewidth=0,
    )

    assert calls
    assert {call["color"] for call in calls}.issubset({"#9f1c1f", "#787a7c"})
    assert {call["edgecolor"] for call in calls} == {"none"}
    assert {call["size"] for call in calls} == {4}
    assert {call["linewidth"] for call in calls} == {0}


def test_plot_mean_bars_factor_mode_uses_condition_labels(tmp_path, monkeypatch):
    batch = _crossed_human_batch(tmp_path)

    tick_labels = []

    def spy_save(fig, *args, **kwargs):
        tick_labels.append([tick.get_text() for tick in fig.axes[0].get_xticklabels()])

    monkeypatch.setattr(plotting, "save_fig", spy_save)
    plotting.plot_mean_bars(
        batch, filtered_columns=["Period(h)"], factor="Diagnosis",
        points=False, bottom_ticks=True, bottom_tick_labels=True,
    )

    assert tick_labels
    assert tick_labels[-1] == ["AD", "Control"]
