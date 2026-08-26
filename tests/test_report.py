"""Tests for the PyFLASH structured-results ("describe") layer.

These cover ``PyFLASH.report`` in isolation (no pickled batch needed) plus one
end-to-end check that ``stats.multipleComparisons`` emits a record when the
collector is armed.
"""

import math
import types

import numpy as np
import pandas as pd
import pytest

from PyFLASH import report


@pytest.fixture(autouse=True)
def _clean_collector():
    """Ensure every test starts/ends with a disarmed, empty collector."""
    report.collect()  # disarm + clear whatever a prior test left
    yield
    report.collect()


# ── coerce ────────────────────────────────────────────────────────────────────
def test_coerce_numpy_scalars_and_arrays():
    out = report.coerce({"i": np.int64(3), "f": np.float64(1.5),
                         "arr": np.array([1, 2, 3])})
    assert out == {"i": 3, "f": 1.5, "arr": [1, 2, 3]}
    assert isinstance(out["i"], int) and isinstance(out["f"], float)


def test_coerce_nan_and_inf_become_none():
    out = report.coerce({"a": float("nan"), "b": np.float64("inf"), "c": 2.0})
    assert out["a"] is None and out["b"] is None and out["c"] == 2.0


def test_coerce_sets_tuples_and_nested():
    out = report.coerce({"s": {1, 2}, "t": (1, (2, 3))})
    assert sorted(out["s"]) == [1, 2]
    assert out["t"] == [1, [2, 3]]


def test_coerce_dataframe_is_bounded():
    df = pd.DataFrame({"x": range(500), "y": range(500)})
    out = report.coerce(df)
    assert out["_dataframe"] is True
    assert out["shape"] == [500, 2]
    assert out["columns"] == ["x", "y"]
    assert len(out["records"]) == report.MAX_DF_ROWS
    assert out["truncated"] is True
    assert out["omitted_rows"] == 500 - report.MAX_DF_ROWS


def test_coerce_result_is_json_serialisable():
    import json
    payload = {"np": np.arange(3), "nan": float("nan"),
               "df": pd.DataFrame({"a": [1, 2]})}
    json.dumps(report.coerce(payload))  # must not raise


# ── describe_group ─────────────────────────────────────────────────────────────
def test_describe_group_basic_stats():
    rec = report.describe_group("WT", pd.Series([2.0, 4.0, 6.0], name="m"))
    assert rec["name"] == "WT"
    assert rec["n"] == 3
    assert rec["mean"] == pytest.approx(4.0)
    assert rec["sd"] == pytest.approx(2.0)
    assert rec["min"] == 2.0 and rec["max"] == 6.0
    assert rec["median"] == pytest.approx(4.0)


def test_describe_group_drops_nan_and_nonnumeric():
    rec = report.describe_group("g", [1.0, float("nan"), "bad", 3.0])
    assert rec["n"] == 2
    assert rec["mean"] == pytest.approx(2.0)


def test_describe_group_empty():
    rec = report.describe_group("g", [])
    assert rec == {"name": "g", "n": 0}


# ── significance + headlines ───────────────────────────────────────────────────
@pytest.mark.parametrize("p,stars", [
    (0.00001, "****"), (0.0005, "***"), (0.005, "**"),
    (0.04, "*"), (0.2, "ns"), (None, "ns"),
])
def test_significance_stars(p, stars):
    assert report.significance_stars(p) == stars


# ── build_comparison_record ─────────────────────────────────────────────────────
def test_build_comparison_record_shape_and_direction():
    rec = report.build_comparison_record(
        metric="NeuN_Mean",
        group_names=["WT", "KO"],
        group_values=[pd.Series([10.0, 12.0, 14.0]), pd.Series([6.0, 8.0, 10.0])],
        test="Independent T-Test",
        post_hoc="Mann-Whitney U",
        overall=(2.9, 0.013),
        comparisons=["1-2"],
        pairwise_pvalues=[0.013],
        effect_strings=["Effect sizes:", "WT vs KO: g=1.4 large"],
        normal=True,
    )
    assert rec["kind"] == "group_comparison"
    assert rec["metric"] == "NeuN_Mean"
    assert rec["n_groups"] == 2
    assert [g["name"] for g in rec["groups"]] == ["WT", "KO"]
    assert rec["groups"][0]["mean"] == pytest.approx(12.0)
    assert rec["test"]["name"] == "Independent T-Test"
    assert rec["test"]["p"] == pytest.approx(0.013)
    assert rec["direction"] == "WT > KO"
    pw = rec["pairwise"][0]
    assert pw["a"] == "WT" and pw["b"] == "KO"
    assert pw["p"] == pytest.approx(0.013) and pw["sig"] == "*"
    assert "NeuN_Mean" in rec["headline"] and "WT > KO" in rec["headline"]


def test_build_comparison_record_multigroup_direction():
    rec = report.build_comparison_record(
        metric="m",
        group_names=["A", "B", "C"],
        group_values=[pd.Series([1.0, 1.0]), pd.Series([5.0, 5.0]), pd.Series([3.0, 3.0])],
        test="One-Way ANOVA",
        overall=(4.0, 0.02),
        comparisons=["1-2", "1-3", "2-3"],
        pairwise_pvalues=[0.01, 0.3, 0.04],
    )
    assert "highest: B" in rec["direction"] and "lowest: A" in rec["direction"]
    assert len(rec["pairwise"]) == 3


def test_build_comparison_record_pads_missing_labels():
    rec = report.build_comparison_record(
        metric="m", group_names=["only"],
        group_values=[pd.Series([1.0]), pd.Series([2.0])],
        comparisons=["1-2"], pairwise_pvalues=[0.5],
    )
    assert rec["groups"][1]["name"] == "G2"


# ── build_correlation_record ────────────────────────────────────────────────────
def test_build_correlation_record():
    rec = report.build_correlation_record(
        x="Period", y="CK1d_IntDen", group="hAPP", n=12,
        r=0.72, p=0.004, method="spearmanr",
    )
    assert rec["kind"] == "correlation"
    assert rec["x"] == "Period" and rec["y"] == "CK1d_IntDen"
    assert rec["group"] == "hAPP" and rec["n"] == 12
    assert rec["r"] == pytest.approx(0.72)
    assert "CK1d_IntDen vs Period" in rec["headline"] and "hAPP" in rec["headline"]


def test_build_correlation_record_handles_nan():
    rec = report.build_correlation_record(x="a", y="b", n=1, r=float("nan"), p=float("nan"))
    assert rec["r"] is None and rec["p"] is None


def test_build_multivariable_regression_record():
    rec = report.build_multivariable_regression_record(
        predictor_set="Month",
        predictors=["month_sin", "month_cos"],
        y="AB42",
        group="Combined",
        n=24,
        r2=0.71,
        adj_r2=0.68,
        f=12.3,
        p=0.0008,
        q=0.002,
        df_model=2,
        df_resid=21,
        coefficients={"Intercept": 1.0, "month_sin": 0.5, "month_cos": -0.2},
    )
    assert rec["kind"] == "multivariable_regression"
    assert rec["predictor_set"] == "Month"
    assert rec["predictors"] == ["month_sin", "month_cos"]
    assert rec["r2"] == pytest.approx(0.71)
    assert rec["q"] == pytest.approx(0.002)
    assert "AB42 ~ Month" in rec["headline"]


def test_build_linear_model_record():
    rec = report.build_linear_model_record(
        dependent_variable="Totalcounts",
        formula="Totalcounts ~ Diagnosis + Age + Sex",
        group="Diagnosis",
        predictors=["Diagnosis", "Age", "Sex"],
        covariates=["Age", "Sex"],
        n=42,
        r2=0.62,
        adj_r2=0.58,
        f=9.1,
        p=0.004,
        coefficients={"Age": {"estimate": 1.2, "p": 0.01}},
        adjusted_means={"AD": {"adjusted_mean": 180.0, "ci_low": 170.0, "ci_high": 190.0}},
        component_models=[
            {
                "association": "activity",
                "formula": "Totalcounts ~ Diagnosis + Age + Sex",
                "covariates": ["Age", "Sex"],
            }
        ],
    )
    assert rec["kind"] == "linear_model"
    assert rec["dependent_variable"] == "Totalcounts"
    assert rec["group"] == "Diagnosis"
    assert rec["covariates"] == ["Age", "Sex"]
    assert rec["component_models"][0]["covariates"] == ["Age", "Sex"]
    assert rec["adjusted_means"]["AD"]["adjusted_mean"] == pytest.approx(180.0)
    assert "Totalcounts by Diagnosis" in rec["headline"]


# ── summarize_return ────────────────────────────────────────────────────────────
def test_summarize_return_none_for_figure_like():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure()
    try:
        assert report.summarize_return(fig) is None
    finally:
        plt.close(fig)
    assert report.summarize_return(None) is None
    assert report.summarize_return([1, 2, 3]) is None


def test_summarize_return_coerces_pipeline_dict():
    manifest = {"run_label": "r1", "n_pairs": 10,
                "selected": pd.DataFrame({"x": ["a"], "y": ["b"], "r": [0.9]})}
    out = report.summarize_return(manifest)
    assert out["run_label"] == "r1" and out["n_pairs"] == 10
    assert out["selected"]["_dataframe"] is True


# ── collector lifecycle ─────────────────────────────────────────────────────────
def test_collector_lifecycle():
    from PyFLASH.config import Config

    previous = Config.RECORD_STATS
    Config.RECORD_STATS = False
    try:
        assert report.is_active() is False
        report.emit({"kind": "x"})            # inert when disabled and not armed
        report.start()
        assert report.is_active() is True
        report.emit({"kind": "correlation", "x": "a", "y": "b"})
        records = report.collect()
        assert len(records) == 1 and records[0]["kind"] == "correlation"
        assert report.is_active() is False    # collect disarms
    finally:
        Config.RECORD_STATS = previous


def test_emit_drops_non_dict_records():
    report.start()
    report.emit(object())          # coerces to str -> not a dict -> dropped
    report.emit("bare string")     # dropped
    report.emit(["a", "list"])     # dropped
    report.emit({"kind": "correlation", "x": "a", "y": "b"})  # kept
    records = report.collect()
    assert len(records) == 1 and records[0]["kind"] == "correlation"


# ── render_digest ───────────────────────────────────────────────────────────────
def test_render_digest_contains_facts():
    summary = {
        "plot": "plot_mean_bars", "batch": "batch1",
        "run_id": "abc123", "timestamp": "2026-06-25T10:00:00",
        "params": {"column_strings": ["NeuN_Mean"], "factor": "Genotype"},
        "metrics": [report.build_comparison_record(
            metric="NeuN_Mean", group_names=["WT", "KO"],
            group_values=[pd.Series([10.0, 12.0]), pd.Series([6.0, 8.0])],
            test="Independent T-Test", overall=(3.0, 0.01),
            comparisons=["1-2"], pairwise_pvalues=[0.01],
        )],
    }
    md = report.render_digest(summary)
    assert "plot_mean_bars" in md
    assert "NeuN_Mean" in md
    assert "WT" in md and "KO" in md
    assert "p=" in md
    assert "abc123" in md


def test_render_digest_empty_metrics():
    md = report.render_digest({"plot": "plot_images", "batch": "b", "metrics": []})
    assert "No structured statistics" in md


def test_render_digest_tolerates_non_dict_metric():
    # Defensive: a stray non-dict metric must not crash digest rendering.
    md = report.render_digest({"plot": "p", "batch": "b", "metrics": ["bad", 3]})
    assert isinstance(md, str) and "Results" in md


def test_build_comparison_record_two_way_terms():
    rec = report.build_comparison_record(
        metric="m", group_names=["WT", "KO"],
        group_values=[pd.Series([1.0, 2.0]), pd.Series([3.0, 4.0])],
        test="Two-Way ANOVA",
        overall=([5.0, 2.0, 0.5], [0.001, 0.04, 0.6]),  # list-valued (per term)
        comparisons=["1-2"], pairwise_pvalues=[0.02],
        factor_terms=["Genotype", "Time", "Interaction"],
    )
    terms = rec["test"]["terms"]
    assert [t["name"] for t in terms] == ["Genotype", "Time", "Interaction"]
    assert terms[0]["p"] == pytest.approx(0.001)
    assert rec["test"].get("p") is None        # no single scalar p for multi-term
    assert "Genotype p=" in rec["headline"] and "Time p=" in rec["headline"]
    # Regression guard: the term-name handling must NOT corrupt pairwise GROUP
    # labels — these stay WT/KO, not the factor term names.
    pw = rec["pairwise"][0]
    assert pw["a"] == "WT" and pw["b"] == "KO"
    md = report.render_digest({"plot": "p", "batch": "b", "metrics": [rec]})
    assert "Genotype" in md


def test_render_digest_pipeline_section():
    summary = {
        "plot": "correlation_pipeline", "batch": "batch1", "metrics": [],
        "pipeline": {"run_label": "r1", "n_pairs": 20, "n_selected": 3,
                     "groups": [{"group": "hAPP", "n_rows": 8, "n_selected": 2}],
                     "selected_pairs": [{"x": "Period", "y": "CK1d", "r": 0.8}]},
    }
    md = report.render_digest(summary)
    assert "Pipeline summary" in md
    assert "n_selected" in md and "hAPP" in md
    assert "CK1d vs Period" in md


# ── end-to-end: multipleComparisons emits when armed ────────────────────────────
def test_multiple_comparisons_emits_record():
    from PyFLASH import stats

    g1 = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0], name="MyMetric")
    g2 = pd.Series([4.0, 5.0, 6.0, 7.0, 8.0], name="MyMetric")
    exp = types.SimpleNamespace()

    report.start()
    stats.multipleComparisons(
        exp, [g1, g2], ax=None, fig=None, scatter=None, bar=None,
        draw=False, group_labels=["WT", "KO"], comparisons=["1-2"],
    )
    records = report.collect()

    assert len(records) == 1
    rec = records[0]
    assert rec["kind"] == "group_comparison"
    assert rec["metric"] == "MyMetric"
    assert [g["name"] for g in rec["groups"]] == ["WT", "KO"]
    assert rec["groups"][0]["mean"] == pytest.approx(12.0)
    assert "T" in (rec["test"]["name"] or "")
    assert rec["pairwise"][0]["a"] == "WT"
    assert rec["direction"] == "WT > KO"


def test_multiple_comparisons_aligns_labels_when_group_empty():
    """An empty input group is dropped from valid_groups; the captured labels
    must stay aligned to the surviving groups, not slide onto the wrong values."""
    from PyFLASH import stats

    empty = pd.Series([], dtype=float)
    g_b = pd.Series([5.0, 6.0, 7.0])
    g_c = pd.Series([1.0, 2.0, 3.0])
    exp = types.SimpleNamespace()

    report.start()
    stats.multipleComparisons(
        exp, [empty, g_b, g_c], ax=None, fig=None, scatter=None, bar=None,
        draw=False, group_labels=["A", "B", "C"], comparisons=["1-2"],
    )
    records = report.collect()

    assert len(records) == 1
    groups = records[0]["groups"]
    # 'A' was empty and dropped; surviving groups must be labelled B and C with
    # B's mean ~6 and C's mean ~2 (NOT mislabelled as A,B).
    assert [g["name"] for g in groups] == ["B", "C"]
    assert groups[0]["mean"] == pytest.approx(6.0)
    assert groups[1]["mean"] == pytest.approx(2.0)


def test_emit_record_names_two_way_interaction_and_residual():
    """The 2WA overall p is [F1, F2, Interaction, Residual]; _emit_comparison_record
    must extend experiment.factor so trailing terms aren't anonymous term3/term4."""
    from PyFLASH import stats

    report.start()
    stats._emit_comparison_record(
        valid_groups=[pd.Series([1.0, 2.0]), pd.Series([3.0, 4.0])],
        group_labels=["WT", "KO"], cond_list=None,
        test="Two-Way ANOVA", post_hoc="Tukey",
        overall=([5.0, 2.0, 0.5, None], [0.001, 0.04, 0.6, None]),
        comparisons=["1-2"], results=[0.02], effect_strings=[],
        results_dict={}, normal=True,
        fallback_metric="m", valid_indices=[0, 1],
        factor_list=["Genotype", "Time"],
    )
    rec = report.collect()[0]
    assert [t["name"] for t in rec["test"]["terms"]] == \
        ["Genotype", "Time", "Interaction", "Residual"]
    # group labels still correct (not clobbered by term names)
    assert rec["pairwise"][0]["a"] == "WT" and rec["pairwise"][0]["b"] == "KO"


def test_cache_hit_preserves_normal_flag():
    """A stats-cache hit must emit the same `normal` value as the first run,
    not lose it to None."""
    from PyFLASH import stats
    from PyFLASH.config import Config

    g1 = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    g2 = pd.Series([4.0, 5.0, 6.0, 7.0, 8.0])
    exp = types.SimpleNamespace()
    prev = Config.STATS_CACHE
    Config.STATS_CACHE = True
    stats.clear_stats_cache()
    try:
        report.start()
        stats.multipleComparisons(
            exp, [g1, g2], ax=None, fig=None, scatter=None, bar=None,
            draw=False, group_labels=["A", "B"], comparisons=["1-2"],
            cache_key=("metric", frozenset({"A", "B"}), ()),
        )
        first = report.collect()[0]
        report.start()
        stats.multipleComparisons(   # same cache_key -> cache hit
            exp, [g1, g2], ax=None, fig=None, scatter=None, bar=None,
            draw=False, group_labels=["A", "B"], comparisons=["1-2"],
            cache_key=("metric", frozenset({"A", "B"}), ()),
        )
        second = report.collect()[0]
    finally:
        Config.STATS_CACHE = prev
        stats.clear_stats_cache()

    assert first["normal"] is not None
    assert second["normal"] == first["normal"]


def test_multiple_comparisons_inert_when_automatic_recording_disabled():
    from PyFLASH import stats
    from PyFLASH.config import Config

    g1 = pd.Series([1.0, 2.0, 3.0])
    g2 = pd.Series([4.0, 5.0, 6.0])
    exp = types.SimpleNamespace()
    previous = Config.RECORD_STATS
    Config.RECORD_STATS = False
    try:
        stats.multipleComparisons(
            exp, [g1, g2], ax=None, fig=None, scatter=None, bar=None,
            draw=False, group_labels=["A", "B"], comparisons=["1-2"],
        )
        assert report.collect() == []
    finally:
        Config.RECORD_STATS = previous
