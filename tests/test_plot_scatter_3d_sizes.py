import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from types import SimpleNamespace

from IF_analysis import plotting
from IF_analysis.conditions import condition, conditionList
from IF_analysis.iteration import Context


def _build_scatter_experiment():
    summary = pd.DataFrame(
        [
            {"AnimalName": "S1", "Condition": "Syn", "Genotype": "Syn", "x": 1.0, "y": 2.0, "z": 3.0, "size_metric": 1.0},
            {"AnimalName": "S2", "Condition": "Syn", "Genotype": "Syn", "x": 2.0, "y": 3.0, "z": 4.0, "size_metric": 2.0},
            {"AnimalName": "A1", "Condition": "APP", "Genotype": "APP", "x": 3.0, "y": 4.0, "z": 5.0, "size_metric": 10.0},
            {"AnimalName": "A2", "Condition": "APP", "Genotype": "APP", "x": 4.0, "y": 5.0, "z": 6.0, "size_metric": 20.0},
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


def test_scatter_3d_action_applies_size_factor_without_size_by():
    experiment = _build_scatter_experiment()
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    plotting.scatter_3d_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        z="z",
        point_size=30,
        size_factor=1.5,
    )

    sizes = np.asarray(ax.collections[0].get_sizes(), dtype=float)
    assert np.allclose(sizes, np.array([45.0, 45.0]))
    plt.close(fig)


def test_scatter_3d_action_uses_global_size_norm_for_size_by():
    experiment = _build_scatter_experiment()
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    state = {
        "ax": ax,
        "size_norm": plotting._scatter_size_norm(experiment.summary, "size_metric"),
    }
    plotting.scatter_3d_action(
        ctx,
        state,
        x="x",
        y="y",
        z="z",
        size_by="size_metric",
        point_size=40,
        size_factor=2.0,
    )

    sizes = np.asarray(ax.collections[0].get_sizes(), dtype=float)
    expected = plotting._scatter_point_sizes(
        ctx.factor_df[["x", "y", "z", "size_metric"]],
        size_by="size_metric",
        point_size=40,
        size_factor=2.0,
        size_norm=state["size_norm"],
    )
    local_norm = plotting._scatter_point_sizes(
        ctx.factor_df[["x", "y", "z", "size_metric"]],
        size_by="size_metric",
        point_size=40,
        size_factor=2.0,
        size_norm=None,
    )

    assert np.allclose(sizes, expected)
    assert not np.allclose(sizes, local_norm)
    plt.close(fig)


def test_scatter_3d_action_true_normalizes_axes_to_unit_interval():
    experiment = _build_scatter_experiment()
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    plotting.scatter_3d_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        z="z",
        normalize_x=True,
        normalize_y=True,
        normalize_z=True,
    )

    xs, ys, zs = ax.collections[0]._offsets3d
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    zs = np.asarray(zs, dtype=float)
    assert np.isclose(float(np.min(xs)), 0.0)
    assert np.isclose(float(np.max(xs)), 1.0)
    assert np.isclose(float(np.min(ys)), 0.0)
    assert np.isclose(float(np.max(ys)), 1.0)
    assert np.isclose(float(np.min(zs)), 0.0)
    assert np.isclose(float(np.max(zs)), 1.0)
    plt.close(fig)


def test_scatter_3d_action_range_and_zscore_normalize_axes():
    experiment = _build_scatter_experiment()
    ctx = Context(experiment=experiment, factor="Genotype", factor_value="Syn", factor_index=0)

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    plotting.scatter_3d_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        z="z",
        normalize_x=(10.0, 20.0),
        normalize_y=(-1.0, 1.0),
        normalize_z=(100.0, 200.0),
    )

    xs, ys, zs = ax.collections[0]._offsets3d
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    zs = np.asarray(zs, dtype=float)
    assert np.isclose(float(np.min(xs)), 10.0)
    assert np.isclose(float(np.max(xs)), 20.0)
    assert np.isclose(float(np.min(ys)), -1.0)
    assert np.isclose(float(np.max(ys)), 1.0)
    assert np.isclose(float(np.min(zs)), 100.0)
    assert np.isclose(float(np.max(zs)), 200.0)
    plt.close(fig)

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    plotting.scatter_3d_action(
        ctx,
        {"ax": ax},
        x="x",
        y="y",
        z="z",
        normalize_x="Z-score",
        normalize_y="zscore",
        normalize_z="Z_SCORE",
    )

    xs, ys, zs = ax.collections[0]._offsets3d
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    zs = np.asarray(zs, dtype=float)
    assert np.isclose(float(np.mean(xs)), 0.0)
    assert np.isclose(float(np.std(xs, ddof=0)), 1.0)
    assert np.isclose(float(np.mean(ys)), 0.0)
    assert np.isclose(float(np.std(ys, ddof=0)), 1.0)
    assert np.isclose(float(np.mean(zs)), 0.0)
    assert np.isclose(float(np.std(zs, ddof=0)), 1.0)
    plt.close(fig)
