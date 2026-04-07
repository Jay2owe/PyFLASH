import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from types import SimpleNamespace

from IF_analysis import plotting
from IF_analysis.conditions import condition, conditionList
from IF_analysis.iteration import Context


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
