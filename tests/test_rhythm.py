"""Tests for the rhythm module: cosinor + circular statistics and the pipeline.

Covers the genuinely-new stats (``fit_cosinor``, circular tests) recovering known
parameters, and the ``rhythm`` pipeline in both modes honouring the enforced
contracts (montage/save toggles, run folders, and the p-primary / opt-in-q
multiplicity convention from PREFERENCES.md).
"""

import os
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest

from PyFLASH import pipeline
from PyFLASH.stats_extra import (
    fit_cosinor, cosinor_table, cosinor_group_test,
    circular_stats, rayleigh_test, watson_williams, circular_linear_corr,
)


# ── cosinor fit ──────────────────────────────────────────────────────────────
def test_fit_cosinor_recovers_known_parameters():
    rng = np.random.default_rng(0)
    t = np.tile([0, 4, 8, 12, 16, 20], 6).astype(float)
    y = 100 + 40 * np.cos(2 * np.pi / 24 * (t - 14)) + rng.normal(0, 3, len(t))
    f = fit_cosinor(t, y, period=24)
    assert f["mesor"] == pytest.approx(100, abs=3)
    assert f["amplitude"] == pytest.approx(40, abs=5)
    assert f["acrophase"] == pytest.approx(14, abs=0.7)
    assert f["r_squared"] > 0.9
    assert f["p"] < 1e-6            # clearly rhythmic


def test_fit_cosinor_flat_series_is_not_rhythmic():
    rng = np.random.default_rng(1)
    t = np.tile([0, 4, 8, 12, 16, 20], 6).astype(float)
    y = 100 + rng.normal(0, 10, len(t))    # no rhythm
    f = fit_cosinor(t, y, period=24)
    assert f["p"] > 0.05
    assert f["amplitude"] < 15


def test_fit_cosinor_requires_enough_points():
    with pytest.raises(ValueError):
        fit_cosinor([0, 6, 12], [1, 2, 3], period=24)


def test_fit_cosinor_free_period_recovers_tau():
    rng = np.random.default_rng(2)
    t = np.linspace(0, 96, 60)
    y = 50 + 20 * np.cos(2 * np.pi / 25.0 * (t - 6)) + rng.normal(0, 2, len(t))
    f = fit_cosinor(t, y, period=24, period_free=True)
    assert f["period"] == pytest.approx(25.0, abs=0.6)


def test_acrophase_is_circular_wraparound():
    # A peak near midnight should be recovered near 0/24, not mid-day.
    t = np.array([0, 4, 8, 12, 16, 20] * 4, float)
    y = 10 + 5 * np.cos(2 * np.pi / 24 * (t - 0.0))
    f = fit_cosinor(t, y, period=24)
    assert min(f["acrophase"], 24 - f["acrophase"]) < 0.5


# ── circular statistics ──────────────────────────────────────────────────────
def test_circular_stats_clustered_vs_uniform():
    rng = np.random.default_rng(3)
    clustered = (14 + rng.normal(0, 0.5, 40)) % 24
    uniform = rng.uniform(0, 24, 40)
    assert circular_stats(clustered, 24)["r"] > 0.9
    assert rayleigh_test(clustered, 24)["p"] < 0.001
    assert circular_stats(uniform, 24)["r"] < 0.4
    assert rayleigh_test(uniform, 24)["p"] > 0.05


def test_circular_mean_wraps_midnight():
    vals = np.array([23.5, 23.9, 0.1, 0.5, 23.7, 0.3])
    m = circular_stats(vals, 24)["mean"]
    assert min(m, 24 - m) < 0.5     # mean near midnight, not ~12


def test_watson_williams_detects_phase_difference():
    rng = np.random.default_rng(4)
    a = (10 + rng.normal(0, 1, 25)) % 24
    b = (16 + rng.normal(0, 1, 25)) % 24
    same = (10 + rng.normal(0, 1, 25)) % 24
    assert watson_williams([a, b], 24)["p"] < 0.001
    assert watson_williams([a, same], 24)["p"] > 0.05


def test_circular_linear_corr_detects_association():
    rng = np.random.default_rng(5)
    x = np.linspace(0, 10, 40)
    theta = (2 + 1.5 * x + rng.normal(0, 0.3, 40)) % 24   # phase tracks x
    out = circular_linear_corr(theta, x, 24)
    assert out["r"] > 0.5 and out["p"] < 0.01


# ── cosinor table / group test ───────────────────────────────────────────────
def _two_group_timeseries(amp_a=40, amp_b=15, seed=6):
    rng = np.random.default_rng(seed)
    rows = []
    for grp, amp in [("A", amp_a), ("B", amp_b)]:
        for zt in [0, 4, 8, 12, 16, 20]:
            for _ in range(4):
                rows.append({"grp": grp, "Time": f"ZT{zt}",
                             "val": 100 + amp * np.cos(2 * np.pi / 24 * (zt - 14))
                                    + rng.normal(0, 3)})
    return pd.DataFrame(rows)


def test_cosinor_table_pooled():
    df = _two_group_timeseries()
    tbl = cosinor_table(df, "Time", "val", group_col="grp", period=24)
    assert set(tbl["group"]) == {"A", "B"}
    a = tbl[tbl["group"] == "A"].iloc[0]
    assert a["amplitude"] == pytest.approx(40, abs=6)
    assert a["p_rhythm"] < 0.01


def test_cosinor_group_test_detects_amplitude_difference():
    df = _two_group_timeseries(amp_a=45, amp_b=8)
    res = cosinor_group_test(df, "Time", "val", "grp", period=24)
    assert res["p"] < 0.05


# ── pipeline: fixtures ───────────────────────────────────────────────────────
def _exp(df, tmp_path):
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    return SimpleNamespace(summary=df, summaries={"SCN": df},
                           fig_path=fig_path, data_path=data_path,
                           aliases=None, condition_list=[])


def _param_df(seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    specs = [("Control", 14.0, 55), ("MCI", 15.0, 40), ("AD", 16.0, 28)]
    for grp, ph, amp in specs:
        for _ in range(14):
            rows.append({"Dx": grp,
                         "Acrophase (h)": (ph + rng.normal(0, 1.5)) % 24,
                         "Amplitude": max(amp + rng.normal(0, 8), 1),
                         "IS": np.clip(rng.normal(0.5, 0.1), 0.05, 0.95)})
    return pd.DataFrame(rows)


# ── pipeline: cosinor mode ───────────────────────────────────────────────────
def test_rhythm_cosinor_mode(tmp_path):
    df = _two_group_timeseries()
    exp = _exp(df, tmp_path)
    res = pipeline.rhythm(exp, column="val", time_col="Time", group_col="grp",
                          period=24, run_label="cos")
    assert res["mode"] == "cosinor"
    assert res["data_dir"] == res["fig_dir"]
    assert res.get("montage") and os.path.isfile(res["montage"])
    assert os.path.isfile(os.path.join(res["data_dir"], "cosinor_parameters.csv"))
    assert os.path.isfile(os.path.join(res["data_dir"], "cosinor_group_test.csv"))
    assert "cosinor_parameters" in res


# ── pipeline: parameter mode + multiplicity convention ───────────────────────
def test_rhythm_parameter_mode_and_phase_test(tmp_path):
    exp = _exp(_param_df(), tmp_path)
    res = pipeline.rhythm(exp, phase_col="Acrophase (h)", group_col="Dx",
                          group_order=["Control", "MCI", "AD"],
                          param_cols=["Amplitude", "IS"], radius_col="Amplitude",
                          period=24, run_label="param")
    assert res["mode"] == "parameter"
    assert res["data_dir"] == res["fig_dir"]
    assert res.get("montage") and os.path.isfile(res["montage"])
    assert res["phase_test"]["p"] < 0.05          # phase differs (planted)
    pt = res["parameter_tests"]
    assert "p_value" in pt.columns
    # Amplitude declines across the ordered groups -> negative trend, significant.
    amp = pt[pt["parameter"] == "Amplitude"].iloc[0]
    assert amp["p_value"] < 0.05 and amp["trend_rho"] < 0


def test_rhythm_default_is_raw_p_only_no_q(tmp_path):
    exp = _exp(_param_df(), tmp_path)
    res = pipeline.rhythm(exp, phase_col="Acrophase (h)", group_col="Dx",
                          param_cols=["Amplitude", "IS"], period=24, run_label="raw")
    # Default (screen=False): no FDR q column at all — raw p is primary.
    assert "p_adjusted" not in res["parameter_tests"].columns
    assert res["screen"] is False


def test_rhythm_screen_adds_q_as_duplicate(tmp_path):
    exp = _exp(_param_df(), tmp_path)
    res = pipeline.rhythm(exp, phase_col="Acrophase (h)", group_col="Dx",
                          param_cols=["Amplitude", "IS"], period=24,
                          screen=True, run_label="screen")
    pt = res["parameter_tests"]
    # Opt-in screen: q is ADDED as a duplicate; raw p_value is preserved.
    assert "p_adjusted" in pt.columns and "p_value" in pt.columns


def test_rhythm_gate_fdr_requires_screen(tmp_path):
    exp = _exp(_param_df(), tmp_path)
    with pytest.raises(ValueError):
        pipeline.rhythm(exp, phase_col="Acrophase (h)", group_col="Dx",
                        param_cols=["Amplitude"], gate="fdr", run_label="bad")


def test_rhythm_on_miniexperiment_batch(tmp_path):
    # The idiomatic way to analyse an external subject-level CSV: load it as a
    # MiniExperiment -> Batch (which carries its own Results paths), exactly the
    # path a pickled batch takes. rhythm() then writes into the batch's Results.
    from PyFLASH.batch import Batch
    from PyFLASH.conditions import condition, conditionList
    from PyFLASH.experiment import MiniExperiment

    src = _param_df().reset_index().rename(columns={"index": "subject"})
    src.to_csv(tmp_path / "Data.csv", index=False)
    conds = conditionList([condition("Control", "Control", "#787a7c", "Dx"),
                           condition("MCI", "MCI", "#4369b2", "Dx"),
                           condition("AD", "AD", "#9f1c1f", "Dx")])
    exp = MiniExperiment("Human", str(tmp_path), animal_column="subject")
    batch = Batch("human", [exp], conds, str(tmp_path))
    batch.processData(import_images=False, progress=False)
    res = pipeline.rhythm(batch, phase_col="Acrophase(h)", group_col="Dx",
                          group_order=["Control", "MCI", "AD"],
                          param_cols=["Amplitude", "IS"], run_label="mini")
    assert res["mode"] == "parameter"
    assert res["data_dir"] == res["fig_dir"]
    assert res.get("montage") and os.path.isfile(res["montage"])
    # outputs live under the batch's own Results tree
    assert "Results" in res["fig_dir"] and res["fig_dir"].startswith(str(tmp_path))


def test_rhythm_montage_toggle_off(tmp_path):
    exp = _exp(_param_df(), tmp_path)
    res = pipeline.rhythm(exp, phase_col="Acrophase (h)", group_col="Dx",
                          period=24, run_label="nomontage", montage=False)
    assert "montage" not in res


def test_rhythm_screen_writes_q_to_csv(tmp_path):
    exp = _exp(_param_df(), tmp_path)
    res = pipeline.rhythm(exp, phase_col="Acrophase (h)", group_col="Dx",
                          param_cols=["Amplitude", "IS"], period=24,
                          screen=True, run_label="screencsv")
    csv = os.path.join(res["data_dir"], "parameter_tests.csv")
    on_disk = pd.read_csv(csv)
    assert "p_adjusted" in on_disk.columns and "p_value" in on_disk.columns
    # q is never smaller than the raw p under BH.
    both = on_disk.dropna(subset=["p_value", "p_adjusted"])
    assert (both["p_adjusted"] >= both["p_value"] - 1e-9).all()


def test_rhythm_gate_fdr_selects_on_q(tmp_path):
    exp = _exp(_param_df(), tmp_path)
    res = pipeline.rhythm(exp, phase_col="Acrophase (h)", group_col="Dx",
                          param_cols=["Amplitude", "IS"], period=24,
                          screen=True, gate="fdr", run_label="gatefdr")
    pt = res["parameter_tests"]
    expected = int((pd.to_numeric(pt["p_adjusted"], errors="coerce") < 0.05).sum())
    assert res["n_significant"] == expected


def test_rhythm_cosinor_screen_adds_q_and_gate_fdr_selects(tmp_path):
    df = _two_group_timeseries(amp_a=45, amp_b=8)
    exp = _exp(df, tmp_path)
    res = pipeline.rhythm(exp, column="val", time_col="Time", group_col="grp",
                          period=24, screen=True, gate="fdr", run_label="cosscreen")
    gt = res["cosinor_group_test"]
    assert "p_adjusted" in gt.columns and "p" in gt.columns
    expected = int((pd.to_numeric(gt["p_adjusted"], errors="coerce") < 0.05).sum())
    assert res["n_significant"] == expected


def test_rhythm_families_none_gives_q_equals_p(tmp_path):
    exp = _exp(_param_df(), tmp_path)
    res = pipeline.rhythm(exp, phase_col="Acrophase (h)", group_col="Dx",
                          param_cols=["Amplitude", "IS"], period=24,
                          screen=True, families="none", run_label="famnone")
    pt = res["parameter_tests"].dropna(subset=["p_value", "p_adjusted"])
    # each parameter its own family -> BH on a single p is that p.
    assert np.allclose(pt["p_value"].to_numpy(), pt["p_adjusted"].to_numpy())
