import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from types import SimpleNamespace

from PyFLASH import plotting
from PyFLASH.conditions import condition, conditionList
from PyFLASH.iteration import Context


def _build_regression_experiment():
    summary = pd.DataFrame(
        [
            {"AnimalName": "S1", "Condition": "Syn", "Genotype": "Syn", "x": 0.0, "y": 1.0},
            {"AnimalName": "S2", "Condition": "Syn", "Genotype": "Syn", "x": 1.0, "y": 3.0},
            {"AnimalName": "S3", "Condition": "Syn", "Genotype": "Syn", "x": 2.0, "y": 5.0},
            {"AnimalName": "S4", "Condition": "Syn", "Genotype": "Syn", "x": 3.0, "y": 7.0},
            {"AnimalName": "S5", "Condition": "Syn", "Genotype": "Syn", "x": 4.0, "y": 9.0},
            {"AnimalName": "A1", "Condition": "APP", "Genotype": "APP", "x": 0.0, "y": 2.0},
            {"AnimalName": "A2", "Condition": "APP", "Genotype": "APP", "x": 1.0, "y": 4.0},
            {"AnimalName": "A3", "Condition": "APP", "Genotype": "APP", "x": 2.0, "y": 6.0},
            {"AnimalName": "A4", "Condition": "APP", "Genotype": "APP", "x": 3.0, "y": 8.0},
        ]
    )

    conds = conditionList(
        [
            condition("Syn", "Syn", "#111111", "Genotype"),
            condition("APP", "APP", "#222222", "Genotype"),
        ]
    )

    return SimpleNamespace(
        summary=summary.copy(),
        summaries={"SCN": summary.copy()},
        condition_list=conds,
        factorDict=conds.factorDict,
        fig_path=".",
    )


def test_plot_regressions_merges_explicit_axis_bounds(monkeypatch):
    experiment = _build_regression_experiment()
    seen = []

    def _recording_regression_action(ctx, state, **kwargs):
        seen.append(
            (
                kwargs.get("x_range"),
                kwargs.get("y_range"),
                kwargs.get("clip_fit_line"),
            )
        )
        return {"group": ctx.factor_value or ctx.condition}

    monkeypatch.setattr(plotting, "regression_action", _recording_regression_action)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        save=False,
        x_range=(0.0, 4.0),
        y_range=(0.0, 10.0),
        xmin=1.0,
        ymax=5.0,
    )

    assert len(seen) == 2
    assert all(x_range == (1.0, 4.0) for x_range, _, _ in seen)
    assert all(y_range == (0.0, 5.0) for _, y_range, _ in seen)
    assert all(clip_fit_line is True for _, _, clip_fit_line in seen)


def test_regression_action_clip_fit_line_trims_to_axis_limits():
    experiment = _build_regression_experiment()
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig, ax = plt.subplots()
    plotting.regression_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        normalize_x=False,
        normalize_y=False,
        y_range=(0.0, 5.0),
        clip_fit_line=False,
    )
    unclipped_line = ax.lines[-1]
    assert float(np.nanmax(unclipped_line.get_ydata())) > 5.0
    plt.close(fig)

    fig, ax = plt.subplots()
    plotting.regression_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        normalize_x=False,
        normalize_y=False,
        y_range=(0.0, 5.0),
        clip_fit_line=True,
    )
    clipped_line = ax.lines[-1]
    assert float(np.nanmax(clipped_line.get_ydata())) <= 5.0 + 1e-9
    assert float(np.nanmax(clipped_line.get_xdata())) <= 2.0 + 1e-9
    plt.close(fig)


def test_regression_action_true_normalizes_to_unit_interval():
    experiment = _build_regression_experiment()
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig, ax = plt.subplots()
    plotting.regression_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        normalize_x=True,
        normalize_y=True,
        clip_fit_line=False,
    )
    offsets = np.asarray(ax.collections[0].get_offsets(), dtype=float)
    assert np.isclose(float(np.min(offsets[:, 0])), 0.0)
    assert np.isclose(float(np.max(offsets[:, 0])), 1.0)
    assert np.isclose(float(np.min(offsets[:, 1])), 0.0)
    assert np.isclose(float(np.max(offsets[:, 1])), 1.0)
    plt.close(fig)


def test_regression_action_range_and_zscore_normalize_scatter_data():
    experiment = _build_regression_experiment()
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig, ax = plt.subplots()
    plotting.regression_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        normalize_x=(10.0, 20.0),
        normalize_y=(-1.0, 1.0),
        clip_fit_line=False,
    )
    offsets = np.asarray(ax.collections[0].get_offsets(), dtype=float)
    assert np.isclose(float(np.min(offsets[:, 0])), 10.0)
    assert np.isclose(float(np.max(offsets[:, 0])), 20.0)
    assert np.isclose(float(np.min(offsets[:, 1])), -1.0)
    assert np.isclose(float(np.max(offsets[:, 1])), 1.0)
    plt.close(fig)

    fig, ax = plt.subplots()
    plotting.regression_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        normalize_x="Z-score",
        normalize_y="zscore",
        clip_fit_line=False,
    )
    offsets = np.asarray(ax.collections[0].get_offsets(), dtype=float)
    assert np.isclose(float(np.mean(offsets[:, 0])), 0.0)
    assert np.isclose(float(np.std(offsets[:, 0], ddof=0)), 1.0)
    assert np.isclose(float(np.mean(offsets[:, 1])), 0.0)
    assert np.isclose(float(np.std(offsets[:, 1], ddof=0)), 1.0)
    plt.close(fig)


def test_plot_regressions_queue_share_respects_specificity_filter(monkeypatch):
    """Queue-share must honor the active specificity filter when computing the
    shared data span, or rows that never get plotted will widen the axis."""
    experiment = _build_regression_experiment()
    experiment.summary["Time"] = "WeekFour"
    experiment.summary["y2"] = experiment.summary["y"] * 10.0
    # Add rows outside the filter with much lower x — those must not leak.
    extra = pd.DataFrame(
        [
            {"AnimalName": "Z1", "Condition": "Syn", "Genotype": "Syn",
             "Time": "WeekTwo", "x": -5.0, "y": 50.0, "y2": 500.0},
            {"AnimalName": "Z2", "Condition": "APP", "Genotype": "APP",
             "Time": "WeekTwo", "x": -3.0, "y": 60.0, "y2": 600.0},
        ]
    )
    experiment.summary = pd.concat([experiment.summary, extra], ignore_index=True)

    seen = []

    def _recording_regression_action(ctx, state, **kwargs):
        seen.append((kwargs.get("x"), kwargs.get("x_range")))
        return {"group": ctx.factor_value or ctx.condition}

    monkeypatch.setattr(plotting, "regression_action", _recording_regression_action)

    plotting.plot_regressions(
        experiment,
        x="x",
        y=["y", "y2"],
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        normalize_x=False,
        normalize_y=False,
        save=False,
        margin=0.1,
    )
    # In-filter x range: 0..4. Out-of-filter x=-5..-3 must not leak.
    x_ranges = {s[1] for s in seen}
    assert len(x_ranges) == 1
    shared = x_ranges.pop()
    # 10% simultaneous pad on (0, 4): new_span = 4/0.8 = 5, pad = 0.5.
    assert shared[0] == pytest.approx(-0.5)
    assert shared[1] == pytest.approx(4.5)


def test_plot_regressions_queue_share_carries_margin_into_sub_calls(monkeypatch):
    experiment = _build_regression_experiment()
    experiment.summary["y2"] = experiment.summary["y"] * 10.0
    seen = []

    def _recording_regression_action(ctx, state, **kwargs):
        seen.append(
            (kwargs.get("x"), kwargs.get("y"), kwargs.get("x_range"), kwargs.get("y_range"))
        )
        return {"group": ctx.factor_value or ctx.condition}

    monkeypatch.setattr(plotting, "regression_action", _recording_regression_action)

    plotting.plot_regressions(
        experiment,
        x="x",
        y=["y", "y2"],
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=False,
        margin=0.2,
    )

    # x is the reused column -> queue shares its range and pre-pads both
    # sides so the data extremes sit at 20% of the final axis span from
    # each spine (simultaneous pad).
    x_ranges = {s[2] for s in seen}
    assert len(x_ranges) == 1
    shared_x = x_ranges.pop()
    # data span = 4; new_span = 4 / (1 - 2*0.2) = 6.667; pad = 1.333
    assert shared_x[0] == pytest.approx(-4.0 / 3.0)
    assert shared_x[1] == pytest.approx(4.0 + 4.0 / 3.0)
    span = shared_x[1] - shared_x[0]
    assert (0.0 - shared_x[0]) / span == pytest.approx(0.2)
    assert (shared_x[1] - 4.0) / span == pytest.approx(0.2)


def test_plot_regressions_margin_ignores_extrapolated_fit_line(monkeypatch):
    """Regression lines drawn by sns.regplot can extrapolate well past the
    scatter range. The margin calculation must key off scatter data, not the
    fit line — otherwise the padded axis balloons out to accommodate the
    line's extrapolated endpoint."""
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        for ax in figure.axes:
            y_scatter = []
            for coll in ax.collections:
                offs = coll.get_offsets()
                if offs.size:
                    y_scatter.extend(offs[:, 1].tolist())
            y_scatter_min = min(y_scatter) if y_scatter else None
            captured.append((image_name, ax.get_ylim(), y_scatter_min))
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=True,
        combine=True,
        margin=0.1,
    )

    for _, ylim, y_scatter_min in captured:
        # Scatter min should sit at ~10% from the bottom. If the margin were
        # computed from the extrapolated fit line, the axis bottom would be
        # well below this expectation.
        span = ylim[1] - ylim[0]
        frac = (y_scatter_min - ylim[0]) / span
        assert 0.09 < frac < 0.11, (
            f"scatter min at {frac*100:.1f}% of span — fit line leakage into margin"
        )


def test_plot_regressions_pads_all_four_sides(monkeypatch):
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        for ax in figure.axes:
            x_scatter = []
            y_scatter = []
            for coll in ax.collections:
                offs = coll.get_offsets()
                if offs.size:
                    x_scatter.extend(offs[:, 0].tolist())
                    y_scatter.extend(offs[:, 1].tolist())
            captured.append(
                (
                    image_name,
                    ax.get_xlim(),
                    ax.get_ylim(),
                    (min(x_scatter), max(x_scatter)) if x_scatter else None,
                    (min(y_scatter), max(y_scatter)) if y_scatter else None,
                )
            )
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=True,
        combine=True,
        margin=0.1,
    )
    assert captured
    for _, xlim, ylim, x_scat, y_scat in captured:
        span_x = xlim[1] - xlim[0]
        span_y = ylim[1] - ylim[0]
        # All four fractions should sit at 10% (both spines, both axes).
        assert (x_scat[0] - xlim[0]) / span_x == pytest.approx(0.1, abs=0.005)
        assert (xlim[1] - x_scat[1]) / span_x == pytest.approx(0.1, abs=0.005)
        assert (y_scat[0] - ylim[0]) / span_y == pytest.approx(0.1, abs=0.005)
        assert (ylim[1] - y_scat[1]) / span_y == pytest.approx(0.1, abs=0.005)


def test_plot_regressions_margin_respects_pinned_upper_bound(monkeypatch):
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        for ax in figure.axes:
            captured.append((image_name, ax.get_xlim(), ax.get_ylim()))
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=True,
        combine=True,
        xmax=4.0,  # pin upper -> no pad on right spine
        margin=0.1,
    )
    for _, xlim, _ in captured:
        assert xlim[1] == pytest.approx(4.0)
        # Left side still padded below data min (=0)
        assert xlim[0] < 0.0


def test_plot_regressions_pads_lower_bounds_under_default_normalization(monkeypatch):
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        for ax in figure.axes:
            captured.append((image_name, ax.get_xlim(), ax.get_ylim()))
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    # Default normalize_x=True / normalize_y=True must still receive the
    # bottom/left breathing room.
    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        save=True,
        combine=False,
    )

    assert captured, "save_fig was not invoked"
    for _, xlim, ylim in captured:
        assert xlim[0] < 0.0
        assert ylim[0] < 0.0


def test_plot_regressions_pads_lower_bounds_by_margin(monkeypatch):
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        for ax in figure.axes:
            captured.append((image_name, ax.get_xlim(), ax.get_ylim()))
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=True,
        combine=False,
        margin=0.1,
    )

    assert len(captured) == 2
    # Syn data: x in [0, 4], y in [1, 9]. Margin extends lower bound by 10% of span.
    # Without margin the auto lims should start at ~0 / ~1; with 10% pad they shift left/down.
    syn_entry = next(c for c in captured if "(Syn)" in c[0])
    assert syn_entry[1][0] < 0.0
    assert syn_entry[2][0] < 1.0


def test_plot_regressions_margin_zero_leaves_bounds_tight(monkeypatch):
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        for ax in figure.axes:
            captured.append((ax.get_xlim(), ax.get_ylim()))
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=True,
        combine=False,
        margin=0,
    )

    # With margin=0, the auto-scale pad from seaborn is ~5%; the lower bound
    # should be above what we'd get with 10% margin.
    first = captured[0]
    assert first[0][0] > -0.5
    assert first[1][0] > 0.0


def test_plot_regressions_margin_skipped_when_lower_bound_pinned(monkeypatch):
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        for ax in figure.axes:
            captured.append((image_name, ax.get_xlim(), ax.get_ylim()))
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=True,
        combine=False,
        xmin=0.0,
        margin=0.1,
    )

    # Explicit xmin=0 must stay at 0 even with margin on.
    data_min_by_group = {"Syn": 1.0, "APP": 2.0}
    for name, xlim, ylim in captured:
        assert xlim[0] == 0.0
        group_name = next(g for g in data_min_by_group if f"({g})" in name)
        # Y side is not pinned -> lower bound must sit below the group's data min.
        assert ylim[0] < data_min_by_group[group_name]


def test_plot_regressions_writes_side_stats_summary_per_panel(monkeypatch):
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        texts = [text.get_text() for ax in figure.axes for text in ax.texts]
        captured.append((image_name, texts))
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        test="pearsonr",
        normalize_x=False,
        normalize_y=False,
        save=True,
        combine=False,
    )

    assert len(captured) == 2

    captured_map = {name: "\n".join(texts) for name, texts in captured}
    syn_text = next(text for name, text in captured_map.items() if "(Syn)" in name)
    app_text = next(text for name, text in captured_map.items() if "(APP)" in name)

    assert "Test: Pearson" in syn_text
    assert "Syn: p=" in syn_text
    assert "r = 1.00" in syn_text

    assert "Test: Pearson" in app_text
    assert "APP: p=" in app_text
    assert "r = 1.00" in app_text


def test_regression_action_falls_back_to_axis_registry():
    experiment = _build_regression_experiment()
    plotting.set_axis_limits(experiment, {"x": (-2.0, 10.0), "y": (-1.0, 25.0)})
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig, ax = plt.subplots()
    plotting.regression_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        normalize_x=False,
        normalize_y=False,
        clip_fit_line=False,
    )
    assert ax.get_xlim() == (-2.0, 10.0)
    assert ax.get_ylim() == (-1.0, 25.0)
    plt.close(fig)


def test_regression_action_explicit_range_beats_registry():
    experiment = _build_regression_experiment()
    plotting.set_axis_limits(experiment, {"x": (-2.0, 10.0)})
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig, ax = plt.subplots()
    plotting.regression_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        normalize_x=False,
        normalize_y=False,
        x_range=(0.5, 3.5),
        clip_fit_line=False,
    )
    assert ax.get_xlim() == (0.5, 3.5)
    plt.close(fig)


def test_regression_action_skips_registry_when_normalized():
    experiment = _build_regression_experiment()
    plotting.set_axis_limits(experiment, {"x": (-100.0, 100.0)})
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig, ax = plt.subplots()
    plotting.regression_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        normalize_x=True,
        normalize_y=False,
        clip_fit_line=False,
    )
    # Normalized data sits in [0, 1]; registry (-100, 100) must be ignored.
    low, high = ax.get_xlim()
    assert low > -10.0 and high < 10.0
    plt.close(fig)


def test_plot_regressions_queue_shares_reused_column_ranges(monkeypatch):
    experiment = _build_regression_experiment()
    experiment.summary["y2"] = experiment.summary["y"] * 10.0
    seen = []

    def _recording_regression_action(ctx, state, **kwargs):
        seen.append(
            (kwargs.get("x"), kwargs.get("y"), kwargs.get("x_range"), kwargs.get("y_range"))
        )
        return {"group": ctx.factor_value or ctx.condition}

    monkeypatch.setattr(plotting, "regression_action", _recording_regression_action)

    plotting.plot_regressions(
        experiment,
        x="x",
        y=["y", "y2"],
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=False,
        margin=0,
    )

    # Two columns in y -> two combinations, two conditions each -> 4 actions.
    assert len(seen) == 4
    # x appears in two combinations, so its range is shared across all panels
    # (unpadded here because margin=0).
    x_ranges = {s[2] for s in seen}
    assert x_ranges == {(0.0, 4.0)}
    # Each y column appears in only one combination, so queue sharing leaves
    # y_range untouched (matplotlib auto-scales per panel).
    assert all(s[3] is None for s in seen)


def test_plot_regressions_queue_share_folds_margin_into_shared_range(monkeypatch):
    experiment = _build_regression_experiment()
    experiment.summary["y2"] = experiment.summary["y"] * 10.0
    seen = []

    def _recording_regression_action(ctx, state, **kwargs):
        seen.append((kwargs.get("x"), kwargs.get("x_range")))
        return {"group": ctx.factor_value or ctx.condition}

    monkeypatch.setattr(plotting, "regression_action", _recording_regression_action)

    plotting.plot_regressions(
        experiment,
        x="x",
        y=["y", "y2"],
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=False,
        margin=0.1,
    )
    # Data x: min=0, max=4. Simultaneous pad: new_span = 4/0.8 = 5, pad=0.5
    x_ranges = {s[1] for s in seen}
    assert len(x_ranges) == 1
    shared = x_ranges.pop()
    assert shared[0] == pytest.approx(-0.5)
    assert shared[1] == pytest.approx(4.5)
    span = shared[1] - shared[0]
    assert (0.0 - shared[0]) / span == pytest.approx(0.1)
    assert (shared[1] - 4.0) / span == pytest.approx(0.1)


def test_plot_regressions_queue_shares_when_both_axes_reused(monkeypatch):
    experiment = _build_regression_experiment()
    experiment.summary["x2"] = experiment.summary["x"] + 10.0
    experiment.summary["y2"] = experiment.summary["y"] * 10.0
    seen = []

    def _recording_regression_action(ctx, state, **kwargs):
        seen.append(
            (kwargs.get("x"), kwargs.get("y"), kwargs.get("x_range"), kwargs.get("y_range"))
        )
        return {"group": ctx.factor_value or ctx.condition}

    monkeypatch.setattr(plotting, "regression_action", _recording_regression_action)

    plotting.plot_regressions(
        experiment,
        x=["x", "x2"],
        y=["y", "y2"],
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=False,
        margin=0,
    )

    # 2*2 combos * 2 conditions = 8 actions.
    assert len(seen) == 8
    x_range_by_col = {}
    y_range_by_col = {}
    for x_col, y_col, x_range, y_range in seen:
        x_range_by_col.setdefault(x_col, set()).add(x_range)
        y_range_by_col.setdefault(y_col, set()).add(y_range)
    assert x_range_by_col["x"] == {(0.0, 4.0)}
    assert x_range_by_col["x2"] == {(10.0, 14.0)}
    assert y_range_by_col["y"] == {(1.0, 9.0)}
    assert y_range_by_col["y2"] == {(10.0, 90.0)}


def test_plot_regressions_queue_share_disabled(monkeypatch):
    experiment = _build_regression_experiment()
    seen = []

    def _recording_regression_action(ctx, state, **kwargs):
        seen.append((kwargs.get("x_range"), kwargs.get("y_range")))
        return {"group": ctx.factor_value or ctx.condition}

    monkeypatch.setattr(plotting, "regression_action", _recording_regression_action)

    plotting.plot_regressions(
        experiment,
        x=["x"],
        y=["y"],
        factor="Genotype",
        normalize_x=False,
        normalize_y=False,
        save=False,
        share_axes=False,
    )
    assert all(x_range is None and y_range is None for x_range, y_range in seen)


def test_plot_regressions_combined_summary_lists_each_condition(monkeypatch):
    experiment = _build_regression_experiment()
    captured = []

    def _capture_save_fig(figure, save_path, image_name, **kwargs):
        texts = [text.get_text() for ax in figure.axes for text in ax.texts]
        captured.append((image_name, texts))
        return image_name

    monkeypatch.setattr(plotting, "save_fig", _capture_save_fig)

    plotting.plot_regressions(
        experiment,
        x="x",
        y="y",
        factor="Genotype",
        test="spearmanr",
        normalize_x=False,
        normalize_y=False,
        save=True,
        combine=True,
    )

    assert len(captured) == 1

    image_name, texts = captured[0]
    summary_text = "\n".join(texts)

    assert "(Combined)" in image_name
    assert "Test: Spearman" in summary_text
    assert "Syn: p=" in summary_text
    assert "APP: p=" in summary_text
    assert "Syn: r = 1.00" in summary_text
    assert "APP: r = 1.00" in summary_text
