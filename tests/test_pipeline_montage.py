"""Tests for the pipeline overview-montage layer.

Two jobs:

1. **Forcing function.** Every public pipeline (``pipeline.__all__``) must wear the
   ``@montage_pipeline`` decorator (or be listed in ``pipeline.MONTAGE_EXEMPT``), so
   a newly-added pipeline cannot silently ship without an overview montage. This
   mirrors the describe-layer coverage test (``tests/test_describe_coverage.py``).

2. **Behaviour.** The capture collector + ``save_fig`` observer record the right
   panels, ``build_montage`` writes one grid PNG, and each pipeline drops a
   ``! Overview Montage.png`` (``Config.MONTAGE_FILENAME``) into its run folder
   (honouring the ``montage`` / ``save`` toggles, resolving the config override /
   legacy name, and letting specificity-queue *children* each build their own).
"""

import inspect
import os
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from PyFLASH import pipeline
from PyFLASH import pipeline_montage as pm
from PyFLASH import utils
from PyFLASH.config import Config


# ── fixtures ─────────────────────────────────────────────────────────────────
def _dataset(tmp_path, n=24):
    rng = np.random.default_rng(11)
    a = rng.normal(10.0, 2.0, n)
    b = 1.7 * a + rng.normal(0, 0.3, n)   # correlates with A
    c = rng.normal(5.0, 1.0, n)
    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "Condition": (["WT"] * (n // 2)) + (["KO"] * (n - n // 2)),
        "Diagnosis": (["Control"] * (n // 2)) + (["AD"] * (n - n // 2)),
        "A": a, "B": b, "C": c,
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    return SimpleNamespace(
        summary=summary, summaries={"SCN": summary},
        fig_path=fig_path, data_path=data_path,
        condition_list=[SimpleNamespace(name="WT"), SimpleNamespace(name="KO")],
    )


def _png(label):
    fig = plt.figure(figsize=(2, 2))
    fig.gca().text(0.5, 0.5, label, ha="center", va="center")
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


_DATA_OVERVIEW_MONTAGE_SMOKE = {
    "include_inventory": False,
    "include_group_counts": True,
    "include_descriptives": False,
    "include_normality": False,
    "include_outliers": False,
    "include_covariation": False,
    "include_condition_distributions": False,
    "include_effect_sizes": False,
    "include_significance_audit": False,
    "include_scorecard": False,
    "include_readiness": False,
    "plot_missingness": False,
    "plot_covariation": False,
    "plot_group_counts": True,
    "plot_availability": False,
    "plot_descriptives": False,
    "plot_normality": False,
    "plot_outliers": False,
    "plot_covariation_pairs": False,
    "plot_condition_distributions": False,
    "plot_condition_distribution_zscores": False,
    "plot_condition_fingerprint": False,
    "plot_condition_variability": False,
    "plot_effect_sizes": False,
    "plot_significance_audit": False,
    "plot_scorecard": False,
    "plot_readiness": False,
}


def _data_overview_montage_smoke(exp, **kwargs):
    params = dict(_DATA_OVERVIEW_MONTAGE_SMOKE)
    params.update(kwargs)
    return pipeline.data_overview(exp, **params)


# ── 1. forcing function ──────────────────────────────────────────────────────
def test_every_pipeline_is_montage_enforced():
    for name in pipeline.__all__:
        if name in pipeline.MONTAGE_EXEMPT:
            continue
        func = getattr(pipeline, name)
        assert getattr(func, "__montage_pipeline__", False), (
            f"pipeline.{name} is not montage-enforced. Decorate it with "
            "@pipeline_montage.montage_pipeline(...) so every run emits an overview "
            "montage of its key graphs, or add it to pipeline.MONTAGE_EXEMPT with a "
            "reason. See PyFLASH/pipeline_montage.py and CLAUDE.md."
        )
    stray = set(pipeline.MONTAGE_EXEMPT) - set(pipeline.__all__)
    assert not stray, (
        f"MONTAGE_EXEMPT name(s) {sorted(stray)} are not in pipeline.__all__ — "
        "remove them or fix the name."
    )


def test_enforced_pipelines_expose_montage_and_save_params():
    # The decorator must preserve the wrapped signature (so the spec runner and
    # validate_spec still see every parameter, including the montage toggle).
    for name in pipeline.__all__:
        if name in pipeline.MONTAGE_EXEMPT:
            continue
        params = inspect.signature(getattr(pipeline, name)).parameters
        assert "montage" in params, f"{name} is missing a montage= parameter"
        assert "save" in params, f"{name} is missing a save= parameter"


# ── 2a. capture collector + save_fig observer ────────────────────────────────
def test_capture_session_records_key_and_secondary_only(tmp_path):
    with pm.capture_session() as state:
        f1 = plt.figure(); f1.gca().plot([0, 1], [0, 1])
        utils.save_fig(f1, str(tmp_path), "Headline Matrix", montage=True, verbose=False)
        plt.close(f1)

        # non-key, outside any secondary block -> ignored (e.g. a p-value matrix)
        f2 = plt.figure(); f2.gca().plot([0, 1], [1, 0])
        utils.save_fig(f2, str(tmp_path), "PValue Matrix", verbose=False)
        plt.close(f2)

        # non-key, inside a secondary block -> captured (e.g. a regression)
        with pm.capture_secondary("regression"):
            f3 = plt.figure(); f3.gca().plot([0, 1], [0, 1])
            utils.save_fig(f3, str(tmp_path), "X vs Y", verbose=False)
            plt.close(f3)

        captured = [(p["name"], p["key"]) for p in state["panels"]]

    assert ("Headline Matrix", True) in captured
    assert ("X vs Y", False) in captured
    assert all(name != "PValue Matrix" for name, _ in captured)
    # the observer is removed and the collector disarmed once the session closes
    assert not pm.is_active()
    assert pm._observer not in utils._FIG_SAVE_OBSERVERS


def test_observer_inert_without_session(tmp_path):
    # No armed session: save_fig must not capture anything anywhere.
    assert not pm.is_active()
    f = plt.figure(); f.gca().plot([0, 1], [0, 1])
    utils.save_fig(f, str(tmp_path), "Lonely", montage=True, verbose=False)
    plt.close(f)
    assert not pm._STATE["panels"]


def test_capture_secondary_inert_without_session():
    # A pipeline run with montage=False / save=False still enters the
    # capture_secondary block; with no armed session it must not touch _STATE.
    assert not pm.is_active()
    snapshot = dict(pm._STATE)
    with pm.capture_secondary("regression"):
        assert pm._STATE["capture_secondary"] is False  # left untouched
        assert pm._STATE["secondary_label"] is None
    assert pm._STATE == snapshot


def test_secondary_capture_respects_cap(tmp_path):
    limit = pm.MAX_NONKEY_CAPTURE
    with pm.capture_session() as state:
        with pm.capture_secondary("regression"):
            for i in range(limit + 5):
                f = plt.figure(); f.gca().plot([0, 1], [0, 1])
                utils.save_fig(f, str(tmp_path), f"reg {i}", verbose=False)
                plt.close(f)
        n_secondary = sum(1 for p in state["panels"] if not p["key"])
        omitted = state["n_nonkey_omitted"]
    assert n_secondary == limit
    assert omitted == 5


# ── 2b. build_montage ────────────────────────────────────────────────────────
def test_build_montage_writes_png(tmp_path):
    panels = [
        {"name": "K1", "subfolder": None, "key": True, "png": _png("K1")},
        {"name": "K2", "subfolder": "AD/Matrices", "key": True, "png": _png("K2")},
        {"name": "X vs Y", "subfolder": "Regressions", "key": False, "png": _png("R1")},
    ]
    out = pm.build_montage(panels, str(tmp_path), title="Demo")
    assert out and os.path.isfile(out)
    assert os.path.basename(out) == f"{pm.DEFAULT_MONTAGE_FILENAME}.png"


def test_build_montage_empty_returns_none(tmp_path):
    assert pm.build_montage([], str(tmp_path), title="Demo") is None
    assert pm.build_montage([{"name": "x", "png": None, "key": True}],
                            str(tmp_path), title="Demo") is None


# ── 2b-bis. montage filename resolution + legacy fallback ─────────────────────
def test_montage_filename_resolution():
    # explicit wins; else Config.MONTAGE_FILENAME; else the module default.
    assert pm._montage_filename("Custom Name") == "Custom Name"
    assert pm._montage_filename() == pm.DEFAULT_MONTAGE_FILENAME
    prev = Config.MONTAGE_FILENAME
    Config.MONTAGE_FILENAME = "00 - Overview Montage"
    try:
        assert pm._montage_filename() == "00 - Overview Montage"
        # explicit still overrides a config value
        assert pm._montage_filename("Forced") == "Forced"
    finally:
        Config.MONTAGE_FILENAME = prev


def test_existing_montage_finds_legacy_name(tmp_path):
    # A run reused after the montage rename still resolves a montage the original
    # run wrote under the historical "00 - Overview Montage.png" name.
    fig_dir = str(tmp_path)
    legacy = os.path.join(fig_dir, "00 - Overview Montage.png")
    with open(legacy, "wb") as fh:
        fh.write(b"\x89PNG\r\n")
    result = {"reused": True, "fig_dir": fig_dir}
    assert pm._existing_montage(result, pm.DEFAULT_MONTAGE_FILENAME) == legacy
    # a non-reused run yields nothing even if a montage file exists
    assert pm._existing_montage({"reused": False, "fig_dir": fig_dir},
                                pm.DEFAULT_MONTAGE_FILENAME) is None


# ── 2c. end-to-end through the pipelines ─────────────────────────────────────
def _montage_path(res):
    return res.get("montage")


def test_data_overview_writes_montage_into_run_folder(tmp_path):
    exp = _dataset(tmp_path)
    res = _data_overview_montage_smoke(exp, run_label="ovw", save=True)
    montage = _montage_path(res)
    assert montage and os.path.isfile(montage)
    assert os.path.basename(montage) == f"{pm.DEFAULT_MONTAGE_FILENAME}.png"
    assert os.path.dirname(montage) == res["fig_dir"]


def test_correlation_writes_montage(tmp_path):
    exp = _dataset(tmp_path)
    res = pipeline.correlation(
        exp, filtered_columns=["A", "B", "C"], run_label="corr",
        tests=("pearsonr", "spearmanr"), gate="p", save=True)
    montage = _montage_path(res)
    assert montage and os.path.isfile(montage)


def test_adjusted_correlation_writes_montage(tmp_path):
    exp = _dataset(tmp_path)
    res = pipeline.adjusted_correlation(
        exp, endpoints=["A", "B", "C"], run_label="adj",
        tests=("pearsonr",), gate="p", save=True)
    montage = _montage_path(res)
    assert montage and os.path.isfile(montage)


def test_montage_toggle_off_skips(tmp_path):
    exp = _dataset(tmp_path)
    res = _data_overview_montage_smoke(
        exp, run_label="ovw_off", save=True, montage=False)
    assert "montage" not in res
    assert not os.path.isfile(
        os.path.join(res["fig_dir"], f"{pm.DEFAULT_MONTAGE_FILENAME}.png"))


def test_save_false_skips_montage(tmp_path):
    exp = _dataset(tmp_path)
    res = _data_overview_montage_smoke(exp, run_label="ovw_nosave", save=False)
    assert "montage" not in res


def test_global_save_mode_false_skips_montage(tmp_path):
    exp = _dataset(tmp_path)
    prev = Config.SAVE_MODE
    Config.SAVE_MODE = False
    try:
        res = _data_overview_montage_smoke(
            exp, run_label="ovw_global_nosave", save=True)
    finally:
        Config.SAVE_MODE = prev

    assert "montage" not in res
    assert not os.path.isfile(
        os.path.join(res["fig_dir"], f"{pm.DEFAULT_MONTAGE_FILENAME}.png"))


def test_reused_run_points_at_existing_montage(tmp_path):
    exp = _dataset(tmp_path)
    first = _data_overview_montage_smoke(exp, run_label="ovw_reuse", save=True)
    assert first.get("montage") and os.path.isfile(first["montage"])
    # if_exists='skip' returns the cached manifest without recomputing, but the
    # returned montage path should still resolve to the original run's montage.
    second = _data_overview_montage_smoke(
        exp, run_label="ovw_reuse", save=True, if_exists="skip")
    assert second.get("reused") is True
    assert second.get("montage") == first["montage"]
    assert os.path.isfile(second["montage"])


def test_data_overview_montage_config_override(tmp_path):
    # Setting Config.MONTAGE_FILENAME restores the historical name without a code
    # edit; the decorator resolves it at run time.
    exp = _dataset(tmp_path)
    prev = Config.MONTAGE_FILENAME
    Config.MONTAGE_FILENAME = "00 - Overview Montage"
    try:
        res = _data_overview_montage_smoke(
            exp, run_label="ovw_legacy", save=True)
    finally:
        Config.MONTAGE_FILENAME = prev
    montage = _montage_path(res)
    assert montage and os.path.isfile(montage)
    assert os.path.basename(montage) == "00 - Overview Montage.png"


def test_specificity_queue_builds_one_combined_montage(tmp_path):
    exp = _dataset(tmp_path)
    res = _data_overview_montage_smoke(
        exp, specificity=[("Diagnosis", "Control"), ("Diagnosis", "AD")],
        run_label="ovw_queue", save=True)
    # A specificity queue is now one merged run in a single folder, so it gets a
    # single combined overview montage spanning every condition (not one per child).
    assert res.get("queued") is not True
    montage = _montage_path(res)
    assert montage and os.path.isfile(montage)
    assert os.path.dirname(montage) == res["fig_dir"]
