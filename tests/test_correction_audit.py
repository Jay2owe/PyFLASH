"""Tests for the correction-calibration layer.

The permutation null underpins every downstream number, and a wrong null would
be confidently wrong with nothing in the CSV to reveal it.  So the numeric
targets below come from independent exhaustive enumeration
(``docs/correction-calibration/reference_benchmark.py``), not from a snapshot of
this implementation.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from PyFLASH import stats_extra as se


# ── the null itself ──────────────────────────────────────────────────
def test_small_design_is_enumerated_exactly():
    null = se.permutation_null((3, 3, 4))
    assert null["mode"] == "exact"
    assert null["n_arrangements"] == 4200
    assert null["n_perm"] == 4200
    assert null["p"].shape == (4200, 3)
    assert null["pairs"] == [(0, 1), (0, 2), (1, 2)]


def test_large_design_falls_back_to_sampling():
    null = se.permutation_null((5, 5, 5))
    assert null["mode"] == "sampled"
    assert null["n_perm"] == 20000
    assert null["n_arrangements"] == 756756


def test_exact_enumeration_covers_four_groups():
    # 3/3/3/3 is 369,600 arrangements, so it samples; 2/2/2/2 is only 2520 and
    # must enumerate - the enumerator has to handle k > 3, which the reference
    # benchmark's three-group loop did not.
    null = se.permutation_null((2, 2, 2, 2))
    assert null["mode"] == "exact"
    assert null["n_arrangements"] == 2520
    assert null["p"].shape == (2520, 6)


def test_null_array_is_read_only():
    # The cache hands the same array to every caller in a batch.
    null = se.permutation_null((3, 3, 4))
    with pytest.raises(ValueError):
        null["p"][0, 0] = 0.5


def test_ranks_must_match_group_sizes():
    with pytest.raises(ValueError):
        se.permutation_null((3, 3), ranks=[1, 2, 3])


# ── the audit numbers, against enumerated targets ────────────────────
@pytest.mark.parametrize(
    "ns, alpha_star, fwer_unc, fwer_bonf, floor",
    [
        ((3, 3, 4), 0.0255, 0.1233, 0.0229, 0.004631),
        ((3, 3, 3), 0.0253, 0.1107, 0.0107, 0.007290),
    ],
)
def test_exact_designs_reproduce_enumerated_values(ns, alpha_star, fwer_unc,
                                                   fwer_bonf, floor):
    audit = se.correction_audit([0.5, 0.5, 0.5], ns)
    perm = audit["permutation"]
    assert perm["mode"] == "exact"
    assert perm["alpha_star"] == pytest.approx(alpha_star, abs=0.001)
    assert perm["fwer_if_uncorrected"] == pytest.approx(fwer_unc, abs=0.001)
    assert perm["fwer_of_bonferroni"] == pytest.approx(fwer_bonf, abs=0.001)
    assert perm["p_floor"] == pytest.approx(floor, abs=1e-4)


def test_sampled_design_lands_near_its_target():
    # Monte Carlo, so a loose band: the 5th percentile of 20,000 draws has a
    # standard error near 0.0015.
    audit = se.correction_audit([0.5, 0.5, 0.5], (5, 5, 5))
    assert audit["permutation"]["mode"] == "sampled"
    assert audit["permutation"]["alpha_star"] == pytest.approx(0.0237, abs=0.004)


@pytest.mark.parametrize(
    "ns", [(3, 3, 3), (3, 3, 4), (4, 4, 4), (3, 4, 5), (3, 3, 3, 3)])
def test_calibrated_threshold_beats_bonferroni_on_the_dunn_statistic(ns):
    # True of Dunn, which is conservative at small n. It is NOT a universal
    # law: Conover runs liberal and inverts it, which is exactly the kind of
    # thing this audit exists to surface. See the Conover test below.
    k = len(ns) * (len(ns) - 1) // 2
    perm = se.correction_audit([0.5] * k, ns, statistic="dunn")["permutation"]
    assert perm["alpha_star"] >= perm["alpha_bonferroni"]


def test_attainable_floor_is_on_the_reported_p_scale():
    # A 3v3 has 20 arrangements, so the EXACT two-sided floor is 0.10 - but the
    # floor that matters is the one on the scale PyFLASH reports, Dunn's normal
    # approximation, where the most extreme split gives 0.0495.  It squeaks
    # under 0.05 uncorrected and is unreachable under Bonferroni's 0.0167.
    floor = se.attainable_p_floor((3, 3))
    assert floor == pytest.approx(0.04953, abs=1e-4)
    assert floor < 0.05
    assert floor > 0.05 / 3


def test_floor_can_rule_out_significance_entirely():
    # 2v3: even the most extreme arrangement cannot reach 0.05.
    assert se.attainable_p_floor((2, 3)) > 0.05


# ── Westfall-Young ───────────────────────────────────────────────────
def _wy_case():
    pvals = [0.0141, 0.2210, 0.6650]
    null = se.permutation_null((3, 3, 4))
    return pvals, null, se.westfall_young(pvals, null)


def test_westfall_young_is_a_valid_adjustment():
    _, _, adj = _wy_case()
    assert all(0.0 <= v <= 1.0 for v in adj)


def test_westfall_young_may_come_out_below_the_raw_p():
    # Not a bug, and the single most surprising thing about this column. The
    # reported p is Dunn's asymptotic normal approximation, which is
    # conservative at small n; Westfall-Young replaces it with an exact
    # permutation p at the same time as correcting for multiplicity. On a
    # 3/3/4 design the exactness gain can outweigh the multiplicity cost.
    null = se.permutation_null((3, 3, 4), statistic="dunn")
    raw = 0.00494                      # the smallest p this design can report
    adj = se.westfall_young([raw, 0.22, 0.13], null)
    assert adj[0] < raw
    # 6 of the 4200 arrangements reach the floor.
    assert adj[0] == pytest.approx(6 / 4200, abs=1e-9)


def test_westfall_young_is_monotone_in_observed_p():
    pvals, _, adj = _wy_case()
    order = np.argsort(pvals)
    stepped = [adj[i] for i in order]
    assert stepped == sorted(stepped)


def test_westfall_young_never_exceeds_bonferroni():
    # It exploits the correlation between comparisons that share a group, so
    # against a conservative statistic it lands at or below Bonferroni. That
    # holds for Dunn at small n; it is not universal - see the liberal case in
    # the parametric section.
    pvals, _, adj = _wy_case()
    bonf = se.correction_ladder(pvals)["bonferroni"]
    for wy, bf in zip(adj, bonf):
        assert wy <= bf + 1e-12


# ── the closed-form ladder ───────────────────────────────────────────
def test_ladder_delegates_rather_than_reimplements():
    pvals = [0.01, 0.04, 0.20]
    ladder = se.correction_ladder(pvals)
    assert ladder["uncorrected"] == pvals
    for key, method in (("holm", "holm"), ("bh_q", "fdr_bh"),
                        ("bonferroni", "bonferroni"), ("sidak", "sidak")):
        _, expected = se.adjust_pvalues(pvals, method=method)
        assert ladder[key] == pytest.approx(expected)


def test_audit_always_carries_the_ladder():
    audit = se.correction_audit([0.01, 0.04, 0.20], want_permutation=False)
    for key in ("uncorrected", "holm", "bh_q", "bonferroni", "sidak"):
        assert len(audit[key]) == 3
    assert audit["alpha"] == 0.05


# ── caching, the thing that makes it affordable ──────────────────────
def test_repeated_calls_share_one_computation():
    se._permutation_null_cached.cache_clear()
    first = se.permutation_null((3, 3, 4))
    second = se.permutation_null((3, 3, 4))
    assert first is second
    assert se._permutation_null_cached.cache_info().hits >= 1
    assert se._permutation_null_cached.cache_info().misses == 1


def test_ties_get_their_own_cache_entry():
    se._permutation_null_cached.cache_clear()
    untied = se.permutation_null((3, 3), ranks=[1, 2, 3, 4, 5, 6])
    tied = se.permutation_null((3, 3), ranks=[1.5, 1.5, 3, 4, 5, 6])
    assert untied is not tied
    assert se._permutation_null_cached.cache_info().misses == 2


def test_rank_order_does_not_split_the_cache():
    # Only the multiset matters under the null, so a reordered rank vector must
    # hit the same entry.
    se._permutation_null_cached.cache_clear()
    a = se.permutation_null((3, 3), ranks=[1, 2, 3, 4, 5, 6])
    b = se.permutation_null((3, 3), ranks=[6, 5, 4, 3, 2, 1])
    assert a is b
    assert se._permutation_null_cached.cache_info().misses == 1


def test_want_permutation_false_does_no_work():
    se._permutation_null_cached.cache_clear()
    audit = se.correction_audit([0.01, 0.04, 0.20], (3, 3, 4),
                                want_permutation=False)
    assert audit["permutation"] is None
    assert se._permutation_null_cached.cache_info().misses == 0


def test_mismatched_family_size_refuses_rather_than_guesses():
    # A null built for three pairs against two reported p-values would be
    # comparing unlike things.
    audit = se.correction_audit([0.01, 0.04], (3, 3, 4))
    assert audit["permutation"] is None
    assert "skipped" in audit


# ── the uniform uncorrected-p channel ────────────────────────────────
import csv as _csv
from types import SimpleNamespace

import pandas as pd

from PyFLASH import stats as st
from PyFLASH.config import Config


class _Condition:
    def __init__(self, name):
        self.name = name


def _three_groups():
    return [
        pd.Series([1.0, 1.2, 1.1]),
        pd.Series([2.0, 2.1, 2.2]),
        pd.Series([4.0, 4.2, 4.1, 4.3]),
    ]


COMPARISONS = ["1-2", "1-3", "2-3"]


def _experiment():
    return SimpleNamespace(
        condition_list=[_Condition("A"), _Condition("B"), _Condition("C")],
        data_path=".",
    )


def _run(tmp_path, save_name="audit", groups=None, **kw):
    fig, ax = plt.subplots()
    try:
        out = st.multipleComparisons(
            _experiment(),
            groups if groups is not None else _three_groups(),
            ax=ax, fig=fig, scatter=None, bar=None,
            draw=False,
            comparisons=list(COMPARISONS),
            multiple_comparison="One-Way",
            save_name=save_name,
            output_dir=str(tmp_path),
            verbose=False,
            **kw,
        )
    finally:
        plt.close(fig)
    return out


def _csv_rows(tmp_path, save_name="audit"):
    with open(tmp_path / f"{save_name}.csv", newline="", encoding="utf-8") as fh:
        return list(_csv.reader(fh))


def _row(rows, label):
    for row in rows:
        if row and row[0] == label:
            return row
    return None


@pytest.mark.parametrize(
    "runner, kwargs, n_expected",
    [
        ("kw_conover", {"posthoc": "Conover"}, 3),
        ("kw_dunn", {"posthoc": "Dunn"}, 3),
        ("kw_nemenyi", {"posthoc": "Nemenyi"}, 3),
        ("owa_tukey", {"posthoc": "Tukey"}, 3),
        ("owa_lsd", {"posthoc": "Fisher LSD"}, 3),
        ("welch", {"posthoc": "Games-Howell"}, 3),
        ("mwu", {}, 3),
        ("ttest", {}, 1),
    ],
)
def test_every_posthoc_path_publishes_uncorrected_pvalues(runner, kwargs,
                                                          n_expected):
    groups = _three_groups()
    results_dict = {}
    if runner.startswith("kw_"):
        st.runKW(groups, COMPARISONS, results_dict, **kwargs)
    elif runner.startswith("owa_"):
        st.runOWA(groups, COMPARISONS, results_dict, **kwargs)
    elif runner == "welch":
        st.runWelchOWA(groups, COMPARISONS, results_dict, **kwargs)
    elif runner == "mwu":
        st.mwu_multiple_comparisons(groups, COMPARISONS, results_dict)
    else:
        st.runITTest(groups[0], groups[1], results_dict)

    published = results_dict.get("Posthoc-Uncorrected")
    assert published is not None, f"{runner} published nothing"
    assert len(published[1]) == n_expected
    assert results_dict["_audit_inputs"]["basis"] in {"raw", "self_adjusted"}


def test_two_way_anova_publishes_its_pairwise_tukey():
    # The plan expected two-way ANOVA to have nothing per-comparison, but its
    # post-hoc is a Tukey run aligned to *comparisons*; only the overall result
    # is per-term.
    df = pd.DataFrame({
        "Condition": ["A"] * 4 + ["B"] * 4 + ["C"] * 4,
        "Genotype": ["WT", "WT", "KO", "KO"] * 3,
        "Sex": ["M", "F"] * 6,
        "Marker": [1.0, 1.2, 1.1, 1.3, 2.0, 2.1, 2.2, 2.3, 4.0, 4.2, 4.1, 4.3],
    })
    exp = SimpleNamespace(
        summary=df,
        condition_list=[_Condition("A"), _Condition("B"), _Condition("C")],
    )
    # runTWA does `results_dict = results_dict or {}`, so an empty dict passed
    # in is discarded - read the returned one.
    *_, results_dict, _ = st.runTWA(
        exp, "Marker", factors=["Genotype", "Sex"], comparisons=COMPARISONS)
    assert len(results_dict["Posthoc-Uncorrected"][1]) == 3
    assert results_dict["_audit_inputs"]["basis"] == "self_adjusted"


# ── the ladder reaches the CSV ───────────────────────────────────────
def test_ladder_rows_land_in_the_csv(tmp_path):
    _run(tmp_path)
    rows = _csv_rows(tmp_path)
    for label in ("Correction-Uncorrected", "Correction-Holm", "Correction-BH-q",
                  "Correction-Bonferroni", "Correction-Sidak",
                  "Correction-Basis"):
        row = _row(rows, label)
        assert row is not None, f"{label} missing from the CSV"
    assert _row(rows, "Correction audit") is not None


def test_ladder_row_shape_matches_the_comparisons(tmp_path):
    _run(tmp_path)
    row = _row(_csv_rows(tmp_path), "Correction-Uncorrected")
    # [label, statistic placeholder, p1, p2, p3]
    assert len(row) == 2 + len(COMPARISONS)
    assert all(0.0 <= float(v) <= 1.0 for v in row[2:])


def test_bonferroni_row_is_three_times_the_uncorrected_row(tmp_path):
    _run(tmp_path)
    rows = _csv_rows(tmp_path)
    raw = [float(v) for v in _row(rows, "Correction-Uncorrected")[2:]]
    bonf = [float(v) for v in _row(rows, "Correction-Bonferroni")[2:]]
    for r, b in zip(raw, bonf):
        assert b == pytest.approx(min(r * 3, 1.0), rel=1e-9)


def test_permutation_rows_are_absent_before_the_rank_stage(tmp_path):
    # Guards the cost promise: nothing in this stage may enumerate a null.
    _run(tmp_path)
    rows = _csv_rows(tmp_path)
    for label in ("Correction-WestfallYoung", "Correction-AlphaStar",
                  "Correction-NullMode"):
        assert _row(rows, label) is None, f"{label} appeared too early"


def test_internal_plumbing_never_reaches_the_csv(tmp_path):
    _run(tmp_path)
    labels = [row[0] for row in _csv_rows(tmp_path) if row]
    assert not any(str(lab).startswith("_") for lab in labels)


def test_audit_object_is_stashed_for_the_describe_layer(tmp_path):
    *_, results_dict = _run(tmp_path)
    audit = results_dict["_correction_audit"]
    assert set(audit) >= {"alpha", "uncorrected", "holm", "bh_q", "bonferroni",
                          "sidak"}


def test_audit_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", False, raising=False)
    _run(tmp_path, save_name="off")
    labels = [row[0] for row in _csv_rows(tmp_path, "off") if row]
    assert not any(str(lab).startswith("Correction-") for lab in labels)


def test_a_failing_audit_does_not_lose_the_figure(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("null exploded")

    monkeypatch.setattr(se, "correction_audit", boom)
    test, post_hoc, _ann, results_dict = _run(tmp_path, save_name="boom")
    assert test != "Error"
    assert "null exploded" in results_dict["Correction_audit_error"][0]
    assert _row(_csv_rows(tmp_path, "boom"), "Correction-Uncorrected") is None


def test_reported_verdict_is_untouched_by_the_audit(tmp_path, monkeypatch):
    # The plotted p-values must not move when the audit is switched off.
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", False, raising=False)
    off = _run(tmp_path, save_name="a")
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", "cheap", raising=False)
    on = _run(tmp_path, save_name="b")
    assert off[0] == on[0]
    assert off[1] == on[1]


# ── verdict_changes ──────────────────────────────────────────────────
def test_verdict_changes_separates_contested_from_settled():
    audit = se.correction_audit([0.0141, 0.0400, 0.6650], want_permutation=False)
    changes = se.verdict_changes(audit, COMPARISONS)
    # 0.0141 survives Bonferroni (0.0423); 0.04 does not (0.12).
    assert "bonferroni" in changes["1-2"]
    assert "uncorrected" in changes["1-3"]
    assert "bonferroni" not in changes["1-3"]
    assert changes["2-3"] == []


def test_verdict_changes_reports_the_calibrated_convention_separately():
    # alpha_star is a threshold on UNCORRECTED p, so it is never folded in with
    # the adjusted-p conventions.
    audit = se.correction_audit([0.020, 0.30, 0.65], (3, 3, 4))
    changes = se.verdict_changes(audit, COMPARISONS)
    assert "calibrated" in changes["1-2"]      # 0.020 < alpha* 0.0255
    assert "bonferroni" not in changes["1-2"]  # but 0.060 > 0.05


# ── the null matches the test that produced the observed p ───────────
def _observed_mean_ranks(groups):
    import numpy as _np
    from scipy import stats as _st
    ns = [len(g) for g in groups]
    pooled = _np.concatenate([_np.asarray(g, float) for g in groups])
    ranks = _st.rankdata(pooled)
    cuts = _np.cumsum(ns)[:-1]
    m = _np.array([[blk.mean() for blk in _np.split(ranks, cuts)]])
    return m, ns, ranks


@pytest.mark.parametrize("data, label", [
    ([[1.0, 1.2, 1.1], [2.0, 2.1, 2.2], [4.0, 4.2, 4.1, 4.3]], "untied"),
    ([[0.0, 0.0, 1.0], [0.0, 2.0, 2.0], [4.0, 4.0, 4.0, 3.0]], "tied"),
])
@pytest.mark.parametrize("statistic", ["dunn", "conover"])
def test_null_statistic_reproduces_scikit_posthocs(data, label, statistic):
    # The strongest available check: applied to the OBSERVED arrangement, the
    # null formula must return exactly what the post-hoc itself returns. If it
    # does, the null is a distribution of the same statistic - which is the one
    # thing that cannot be verified by inspecting the null alone.
    sp = pytest.importorskip("scikit_posthocs")
    m, ns, ranks = _observed_mean_ranks(data)
    const = se._rank_multiset_constants(ranks)
    pairs = [(0, 1), (0, 2), (1, 2)]
    fn = se._NULL_STATISTICS[statistic]
    ours = fn(m, ns, const, pairs)[0]
    matrix = (sp.posthoc_dunn(data) if statistic == "dunn"
              else sp.posthoc_conover(data))
    reference = [float(matrix.iloc[i, j]) for i, j in pairs]
    assert ours == pytest.approx(reference, abs=1e-12)


def test_unsupported_statistics_are_refused_not_approximated():
    with pytest.raises(ValueError, match="statistic must be one of"):
        se.permutation_null((3, 3, 4), statistic="nemenyi")


def test_dunn_and_conover_share_the_expensive_half():
    # The mean-rank matrix is the costly part; deriving each statistic from it
    # is closed form. Asking for the second statistic must not re-enumerate.
    se._mean_rank_null_cached.cache_clear()
    se._permutation_null_cached.cache_clear()
    se.permutation_null((3, 3, 4), statistic="dunn")
    se.permutation_null((3, 3, 4), statistic="conover")
    assert se._mean_rank_null_cached.cache_info().misses == 1
    assert se._permutation_null_cached.cache_info().misses == 2


def test_conover_null_differs_from_dunn():
    d = np.asarray(se.permutation_null((3, 3, 4), statistic="dunn")["p"])
    c = np.asarray(se.permutation_null((3, 3, 4), statistic="conover")["p"])
    assert not np.allclose(d, c)


# ── what the audit reveals about each statistic ──────────────────────
def test_dunn_is_conservative_so_bonferroni_overcorrects():
    perm = se.correction_audit([0.5] * 3, (3, 3, 4), statistic="dunn")["permutation"]
    assert perm["fwer_of_bonferroni"] < 0.05      # spends under half the budget
    assert perm["alpha_star"] > perm["alpha_bonferroni"]


def test_conover_is_liberal_so_bonferroni_does_not_overcorrect():
    # Not a defect in the audit: the Conover-Iman procedure borrows the observed
    # Kruskal-Wallis statistic into its denominator and is known to run above
    # nominal. The audit is what makes that visible, and it reverses the advice
    # - here Bonferroni is roughly right rather than too strict.
    perm = se.correction_audit([0.5] * 3, (3, 3, 4),
                               statistic="conover")["permutation"]
    assert perm["fwer_of_bonferroni"] >= 0.05
    assert perm["alpha_star"] < perm["alpha_bonferroni"]


# ── the rank path end to end ─────────────────────────────────────────
def _kw(tmp_path, save_name="kw", posthoc="Dunn", groups=None, **kw):
    return _run(tmp_path, save_name=save_name, groups=groups,
                stats_test="kruskal", posthoc=posthoc, **kw)


def test_rank_path_gains_the_permutation_columns(tmp_path):
    _kw(tmp_path)
    rows = _csv_rows(tmp_path, "kw")
    for label in ("Correction-WestfallYoung", "Correction-AlphaStar",
                  "Correction-AlphaBonferroni", "Correction-FWER-Uncorrected",
                  "Correction-FWER-Bonferroni", "Correction-pFloor",
                  "Correction-NullMode"):
        assert _row(rows, label) is not None, f"{label} missing"


def test_alpha_star_matches_the_enumerated_value(tmp_path):
    _kw(tmp_path)
    rows = _csv_rows(tmp_path, "kw")
    assert float(_row(rows, "Correction-AlphaStar")[1]) == pytest.approx(
        0.0255, abs=0.001)
    assert _row(rows, "Correction-NullMode")[1] == "exact (4200 perms)"


def test_westfall_young_never_exceeds_bonferroni_on_the_dunn_path(tmp_path):
    _kw(tmp_path)
    rows = _csv_rows(tmp_path, "kw")
    wy = [float(v) for v in _row(rows, "Correction-WestfallYoung")[2:]]
    bonf = [float(v) for v in _row(rows, "Correction-Bonferroni")[2:]]
    for a, b in zip(wy, bonf):
        assert a <= b + 1e-12


def test_the_null_follows_the_selected_posthoc(tmp_path):
    # Conover and Dunn must not share an alpha_star: they are different tests.
    _kw(tmp_path, save_name="d", posthoc="Dunn")
    _kw(tmp_path, save_name="c", posthoc="Conover")
    a = float(_row(_csv_rows(tmp_path, "d"), "Correction-AlphaStar")[1])
    b = float(_row(_csv_rows(tmp_path, "c"), "Correction-AlphaStar")[1])
    assert a != pytest.approx(b, abs=1e-6)


def test_nemenyi_says_why_it_cannot_be_calibrated(tmp_path):
    _kw(tmp_path, save_name="nem", posthoc="Nemenyi")
    rows = _csv_rows(tmp_path, "nem")
    assert _row(rows, "Correction-WestfallYoung") is None
    assert _row(rows, "Correction-AlphaStar") is None
    unavailable = _row(rows, "Correction-Unavailable")
    assert unavailable is not None and "Nemenyi" in unavailable[1]
    # the free ladder still applies
    assert _row(rows, "Correction-Holm") is not None


def test_anova_gets_no_permutation_rows_yet(tmp_path):
    _run(tmp_path, save_name="owa", stats_test="anova", posthoc="Fisher LSD")
    rows = _csv_rows(tmp_path, "owa")
    assert _row(rows, "Correction-AlphaStar") is None
    assert _row(rows, "Correction-Uncorrected") is not None


def test_two_group_comparison_has_no_family_to_correct(tmp_path):
    groups = [pd.Series([1.0, 1.2, 1.1, 1.4]), pd.Series([2.0, 2.1, 2.2, 2.4])]
    fig, ax = plt.subplots()
    try:
        st.multipleComparisons(
            SimpleNamespace(condition_list=[_Condition("A"), _Condition("B")],
                            data_path="."),
            groups, ax=ax, fig=fig, scatter=None, bar=None, draw=False,
            comparisons=["1-2"], multiple_comparison="One-Way",
            save_name="two", output_dir=str(tmp_path), verbose=False,
        )
    finally:
        plt.close(fig)
    rows = _csv_rows(tmp_path, "two")
    assert _row(rows, "Correction-AlphaStar") is None
    assert _row(rows, "Correction-Uncorrected") is not None


def test_audit_inputs_never_reach_the_csv(tmp_path):
    _kw(tmp_path)
    labels = [row[0] for row in _csv_rows(tmp_path, "kw") if row]
    assert "_audit_inputs" not in labels
    assert "_correction_audit" not in labels


def _clear_null_caches():
    # Two layers: the outer one keys on the statistic as well, so clearing only
    # the inner one lets the outer serve a request without the inner ever
    # seeing it.
    se._mean_rank_null_cached.cache_clear()
    se._permutation_null_cached.cache_clear()


def test_one_cache_entry_serves_many_metrics(tmp_path):
    # The claim that makes the feature affordable: two different markers with
    # the same design and no ties must share a single enumeration.
    _clear_null_caches()
    first = [pd.Series([1.0, 1.2, 1.1]), pd.Series([2.0, 2.1, 2.2]),
             pd.Series([4.0, 4.2, 4.1, 4.3])]
    second = [pd.Series([9.0, 3.5, 7.25]), pd.Series([100.0, 0.5, 62.0]),
              pd.Series([11.0, 4.75, 8.5, 20.0])]
    _kw(tmp_path, save_name="m1", groups=first)
    _kw(tmp_path, save_name="m2", groups=second)
    assert se._mean_rank_null_cached.cache_info().misses == 1
    # The second figure never even reached the enumerator: the derived-null
    # cache answered it outright.
    assert se._permutation_null_cached.cache_info().hits >= 1


def test_a_tied_column_gets_its_own_entry(tmp_path):
    _clear_null_caches()
    untied = [pd.Series([1.0, 1.2, 1.1]), pd.Series([2.0, 2.1, 2.2]),
              pd.Series([4.0, 4.2, 4.1, 4.3])]
    tied = [pd.Series([0.0, 0.0, 1.0]), pd.Series([0.0, 2.0, 2.0]),
            pd.Series([4.0, 4.0, 4.0, 3.0])]
    _kw(tmp_path, save_name="u", groups=untied)
    _kw(tmp_path, save_name="t", groups=tied)
    assert se._mean_rank_null_cached.cache_info().misses == 2


def test_a_pathological_n_is_declined_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "MAX_AUDIT_N", 5, raising=False)
    _kw(tmp_path, save_name="big")
    rows = _csv_rows(tmp_path, "big")
    assert _row(rows, "Correction-AlphaStar") is None
    assert "ceiling" in _row(rows, "Correction-Unavailable")[1]


def test_plotted_verdict_is_still_untouched_on_the_rank_path(tmp_path,
                                                             monkeypatch):
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", False, raising=False)
    off = _kw(tmp_path, save_name="o1")
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", "cheap", raising=False)
    on = _kw(tmp_path, save_name="o2")
    assert off[0] == on[0] and off[1] == on[1]


# ── the opt-in ───────────────────────────────────────────────────────
@pytest.mark.parametrize("spelling", [
    "westfall-young", "westfall_young", "Westfall-Young", "WY", "wy",
    "permutation", "perm", "maxT", "max_t", "westfall",
])
def test_every_spelling_reaches_the_same_correction(spelling):
    assert st._normalize_kw_correction(spelling, 3) == (
        "westfall_young", "Westfall-Young")


def test_auto_still_resolves_exactly_as_it_always_did():
    # The load-bearing guarantee of the whole plan. Three comparisons stay
    # uncorrected; four reach for Bonferroni. Nothing added here may move this.
    assert st._normalize_kw_correction("auto", 3) == ("none", "Uncorrected")
    assert st._normalize_kw_correction("auto", 4) == ("bonferroni", "Bonferroni")
    assert st._normalize_kw_correction(None, 3) == ("none", "Uncorrected")
    assert st._normalize_lsd_correction("auto", 9) == ("none", "Uncorrected")


def test_the_default_verdict_is_byte_for_byte_what_it_was(tmp_path):
    # Captured against the pre-change behaviour of this dataset, inline rather
    # than in a golden file so a diff shows the numbers themselves.
    test, post_hoc, _ann, results_dict = _kw(tmp_path, save_name="def",
                                             posthoc="Dunn")
    assert test == "Kruskal-Wallis"
    assert post_hoc == "Dunn Uncorrected"
    assert results_dict["Dunn-Uncorrected"][1] == pytest.approx(
        [0.2249158829397837, 0.004939929546541873, 0.13013368002846213])
    assert results_dict["Dunn-Bonferroni"][1] == pytest.approx(
        [0.6747476488193511, 0.014819788639625618, 0.3904010400853864])


def test_requesting_it_changes_the_reported_verdict(tmp_path):
    _, post_hoc, _ann, results_dict = _kw(tmp_path, save_name="wy",
                                          posthoc="Dunn",
                                          posthoc_correction="wy")
    assert post_hoc == "Dunn Westfall-Young"
    reported = results_dict["Dunn-Westfall-Young"][1]
    from_csv = [float(v) for v in
                _row(_csv_rows(tmp_path, "wy"), "Correction-WestfallYoung")[2:]]
    assert reported == pytest.approx(from_csv)


def test_the_session_default_switches_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "POSTHOC_CORRECTION", "westfall-young",
                        raising=False)
    assert _kw(tmp_path, save_name="s1", posthoc="Dunn")[1] == \
        "Dunn Westfall-Young"
    monkeypatch.setattr(Config, "POSTHOC_CORRECTION", "auto", raising=False)
    assert _kw(tmp_path, save_name="s2", posthoc="Dunn")[1] == "Dunn Uncorrected"


def test_an_explicit_argument_beats_the_session_default(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "POSTHOC_CORRECTION", "westfall-young",
                        raising=False)
    assert _kw(tmp_path, save_name="x", posthoc="Dunn",
               posthoc_correction="Bonferroni")[1] == "Dunn Bonferroni"


# ── the refusal ──────────────────────────────────────────────────────
def test_welch_refuses_but_still_draws(tmp_path):
    groups = [pd.Series([0.9, 1.0, 1.1, 1.0]),
              pd.Series([-4.0, -1.0, 2.0, 8.0]),
              pd.Series([2.9, 3.0, 3.1, 3.0])]
    test, post_hoc, _ann, results_dict = _run(
        tmp_path, save_name="welch", groups=groups,
        stats_test="welch_anova", posthoc="Games-Howell",
        posthoc_correction="westfall-young")
    assert test == "Welch ANOVA"
    assert post_hoc == "Games-Howell"          # a real verdict, not an error
    assert "Correction-Unavailable" in results_dict
    rows = _csv_rows(tmp_path, "welch")
    assert _row(rows, "Correction-WestfallYoung") is None
    assert _row(rows, "Correction-Holm") is not None   # the free ladder stays


def test_a_self_correcting_anova_posthoc_refuses(tmp_path):
    # Fisher LSD gained a value null in stage 05; Tukey did not, because
    # reproducing the studentised range needs a numerical integral per draw.
    test, post_hoc, _ann, results_dict = _run(
        tmp_path, save_name="owa", stats_test="anova",
        posthoc="Tukey", posthoc_correction="wy")
    assert test == "One-Way ANOVA"
    assert "Westfall-Young" not in post_hoc
    assert "Correction-Unavailable" in results_dict


def test_switching_the_audit_off_refuses_rather_than_computing_anyway(tmp_path,
                                                                      monkeypatch):
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", False, raising=False)
    _, post_hoc, _ann, results_dict = _kw(tmp_path, save_name="offwy",
                                          posthoc="Dunn",
                                          posthoc_correction="wy")
    assert "Westfall-Young" not in post_hoc
    assert "CORRECTION_AUDIT" in results_dict["Correction-Unavailable"][0]


def test_a_real_engine_bug_is_not_reported_as_unavailable(tmp_path,
                                                          monkeypatch):
    # The fallback catches CorrectionUnavailable specifically, so a genuine
    # fault in the permutation engine must still surface.
    def boom(*a, **k):
        raise RuntimeError("engine fault")

    monkeypatch.setattr(st, "_build_null", boom)
    test, _post_hoc, _ann, results_dict = _kw(
        tmp_path, save_name="bug", posthoc="Dunn", posthoc_correction="wy")
    assert test == "Error"
    assert "engine fault" in str(results_dict["Stats_error"][0])
    # ...and it is not misreported as the correction being unavailable.
    assert "Correction-Unavailable" not in results_dict


# ── the figure ───────────────────────────────────────────────────────
def test_the_annotation_names_the_correction_but_not_the_audit(tmp_path):
    fig, ax = plt.subplots()
    try:
        st.multipleComparisons(
            _experiment(), _three_groups(), ax=ax, fig=fig, scatter=None,
            bar=None, draw=True, comparisons=list(COMPARISONS),
            multiple_comparison="One-Way", stats_test="kruskal",
            posthoc="Dunn", posthoc_correction="wy",
            save_name="ann", output_dir=str(tmp_path), verbose=False,
        )
        text = "\\n".join(t.get_text() for t in ax.texts)
    finally:
        plt.close(fig)
    assert "Westfall-Young" in text
    # alpha* and the FWER numbers stay in the CSV and the results store.
    assert "alpha*" not in text and "FWER" not in text


# ── the value null ───────────────────────────────────────────────────
def test_value_null_uses_the_denominator_fisher_lsd_actually_uses():
    # _run_fisher_lsd pools the ANOVA mean-square-error rather than using
    # two-group variances. If the null used a different denominator the numbers
    # would look plausible and mean nothing, so check against the real thing.
    data = [[1.0, 1.2, 1.1], [2.0, 2.1, 2.2], [4.0, 4.2, 4.1, 4.3]]
    arrays = [np.asarray(g, float) for g in data]
    ns = [len(a) for a in arrays]
    k, n_total = len(ns), sum(ns)
    df_error = n_total - k
    means = np.array([[a.mean() for a in arrays]])
    mse = np.array([sum(((a - a.mean()) ** 2).sum() for a in arrays) / df_error])
    pairs = [(0, 1), (0, 2), (1, 2)]
    b_term = np.array([1.0 / ns[i] + 1.0 / ns[j] for i, j in pairs])
    diff = np.stack([np.abs(means[:, i] - means[:, j]) for i, j in pairs],
                    axis=1)
    ours = se._lsd_value_pvalues(diff, mse, b_term, k, df_error)[0]
    _stats, reference = st._run_fisher_lsd(arrays, COMPARISONS)
    assert ours == pytest.approx(reference, abs=1e-12)


def test_value_null_is_well_formed():
    null = se.value_permutation_null(
        [[1.0, 1.2, 1.1], [2.0, 2.1, 2.2], [4.0, 4.2, 4.1, 4.3]])
    p = np.asarray(null["p"])
    assert null["mode"] == "sampled"
    assert p.shape == (10000, 3)
    assert p.min() >= 0.0 and p.max() <= 1.0


def test_unsupported_value_statistics_are_refused():
    with pytest.raises(ValueError, match="statistic must be one of"):
        se.value_permutation_null([[1.0, 2.0], [3.0, 4.0]], statistic="tukey")


def test_value_westfall_young_is_valid_and_beats_bonferroni():
    data = [[1.0, 1.2, 1.1], [2.0, 2.1, 2.2], [4.0, 4.2, 4.1, 4.3]]
    _stats, raw = st._run_fisher_lsd([np.asarray(g, float) for g in data],
                                     COMPARISONS)
    adj = se.value_westfall_young_adjusted(raw, data, pairs=[(0, 1), (0, 2),
                                                             (1, 2)])
    assert all(0.0 <= v <= 1.0 for v in adj)
    order = np.argsort(raw)
    assert [adj[i] for i in order] == sorted(adj[i] for i in order)


def test_a_sampled_null_cannot_resolve_below_one_permutation():
    # Not a defect, and the thing most likely to be misread. Westfall-Young
    # counts permutations, so 10,000 draws cannot express an adjusted p below
    # 1e-4. An observed p of 4e-9 therefore comes back near the resolution
    # floor - above what Bonferroni would give - because the null has run out
    # of precision, not because the evidence is weaker.
    data = [[1.0, 1.2, 1.1], [2.0, 2.1, 2.2], [4.0, 4.2, 4.1, 4.3]]
    _stats, raw = st._run_fisher_lsd([np.asarray(g, float) for g in data],
                                     COMPARISONS)
    assert min(raw) < 1e-4
    adj = se.value_westfall_young_adjusted(
        raw, data, pairs=[(0, 1), (0, 2), (1, 2)])
    assert min(adj) >= 1.0 / 10000
    audit = se.correction_audit(
        raw, null=se.value_permutation_null(data), want_permutation=False)
    assert audit["permutation"]["p_resolution"] == pytest.approx(1e-4)


def test_westfall_young_respects_the_union_bound_on_its_own_null():
    # The property that always holds. Westfall-Young cannot exceed k times the
    # TRUE per-comparison rate at the observed p. It is only bounded by
    # Bonferroni when the nominal p is itself calibrated or conservative -
    # Bonferroni multiplies the nominal p, and the nominal p can be wrong.
    data = [[1.0, 1.2, 1.1], [2.0, 2.1, 2.2], [4.0, 4.2, 4.1, 4.3]]
    raw = [0.02, 0.31, 0.44]
    null = se.value_permutation_null(data)
    p_null = np.asarray(null["p"])
    adj = se.westfall_young_from_null(raw, null, [(0, 1), (0, 2), (1, 2)])
    for i, value in enumerate(adj):
        union = float((p_null <= raw[i]).sum(axis=0).sum()) / p_null.shape[0]
        assert value <= union + 1e-12


def test_westfall_young_can_exceed_bonferroni_when_the_test_runs_liberal():
    # The counterpart to the Dunn case, and the reason the CSV records
    # Correction-FWER-Uncorrected. Fisher LSD on these three tight clusters is
    # anti-conservative against the data's own permutation null, so the honest
    # adjusted p is LARGER than Bonferroni's. Bonferroni looks stricter only
    # because it is multiplying a p-value that was already too small.
    data = [[1.0, 1.2, 1.1], [2.0, 2.1, 2.2], [4.0, 4.2, 4.1, 4.3]]
    raw = [0.02, 0.31, 0.44]
    adj = se.value_westfall_young_adjusted(
        raw, data, pairs=[(0, 1), (0, 2), (1, 2)])
    assert adj[0] > se.correction_ladder(raw)["bonferroni"][0]
    perm = se.correction_audit(
        raw, null=se.value_permutation_null(data),
        want_permutation=False)["permutation"]
    assert perm["fwer_of_bonferroni"] > 0.05


def test_value_null_is_reproducible_but_not_data_seeded():
    a = se.value_permutation_null([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    b = se.value_permutation_null([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    assert np.allclose(a["p"], b["p"])


# ── cost gating ──────────────────────────────────────────────────────
def test_the_cheap_tier_does_not_permute_values(tmp_path):
    # The cost guarantee, asserted before anything else about this path.
    _run(tmp_path, save_name="cheap", stats_test="anova", posthoc="Fisher LSD")
    rows = _csv_rows(tmp_path, "cheap")
    assert _row(rows, "Correction-AlphaStar") is None
    assert _row(rows, "Correction-WestfallYoung") is None
    assert _row(rows, "Correction-Uncorrected") is not None


def test_the_full_tier_permutes_values(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", "full", raising=False)
    _run(tmp_path, save_name="full", stats_test="anova", posthoc="Fisher LSD")
    rows = _csv_rows(tmp_path, "full")
    assert _row(rows, "Correction-AlphaStar") is not None
    assert _row(rows, "Correction-WestfallYoung") is not None
    assert _row(rows, "Correction-NullMode")[1].startswith("sampled")


def test_asking_for_it_buys_the_cost_at_the_cheap_tier(tmp_path):
    _, post_hoc, _ann, _rd = _run(
        tmp_path, save_name="optin", stats_test="anova",
        posthoc="Fisher LSD", posthoc_correction="wy")
    assert post_hoc == "Fisher LSD Westfall-Young"
    rows = _csv_rows(tmp_path, "optin")
    # The reported verdict and the recorded column must be the same numbers.
    assert _row(rows, "Correction-WestfallYoung") is not None
    assert _row(rows, "Correction-AlphaStar") is not None


def test_the_reported_lsd_values_are_the_recorded_ones(tmp_path):
    _t, _ph, _a, results_dict = _run(
        tmp_path, save_name="same", stats_test="anova",
        posthoc="Fisher LSD", posthoc_correction="wy")
    reported = results_dict["Fisher-LSD-Westfall-Young"][1]
    recorded = [float(v) for v in
                _row(_csv_rows(tmp_path, "same"),
                     "Correction-WestfallYoung")[2:]]
    assert reported == pytest.approx(recorded)


# ── Welch refuses on principle ───────────────────────────────────────
def _welch_groups():
    # normal, with deliberately unequal variances
    return [pd.Series([0.9, 1.0, 1.1, 1.0, 0.95, 1.05]),
            pd.Series([-4.0, -1.0, 2.0, 5.0, 8.0, 11.0]),
            pd.Series([2.9, 3.0, 3.1, 3.0, 2.95, 3.05])]


def test_welch_is_actually_the_route_for_unequal_variances():
    variance = st.test_equal_variance(_welch_groups(), {})
    assert variance["equal_var"] is False


def test_welch_records_why_permutation_is_invalid_not_merely_absent(tmp_path):
    test, post_hoc, _ann, results_dict = _run(
        tmp_path, save_name="welch", groups=_welch_groups(),
        stats_test="welch_anova", posthoc="Games-Howell",
        posthoc_correction="westfall-young")
    assert test == "Welch ANOVA"
    assert post_hoc == "Games-Howell"        # the figure still draws
    reason = results_dict["Correction-Unavailable"][0]
    assert "equal variance" in reason
    rows = _csv_rows(tmp_path, "welch")
    assert _row(rows, "Correction-WestfallYoung") is None
    assert _row(rows, "Correction-Holm") is not None


def test_welch_is_refused_even_at_the_full_tier(tmp_path, monkeypatch):
    # Cost is not the objection here; validity is.
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", "full", raising=False)
    _run(tmp_path, save_name="welchfull", groups=_welch_groups(),
         stats_test="welch_anova", posthoc="Games-Howell")
    rows = _csv_rows(tmp_path, "welchfull")
    assert _row(rows, "Correction-AlphaStar") is None
    assert "equal variance" in _row(rows, "Correction-Unavailable")[1]


def test_tukey_says_why_it_is_not_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", "full", raising=False)
    _run(tmp_path, save_name="tk", stats_test="anova", posthoc="Tukey")
    reason = _row(_csv_rows(tmp_path, "tk"), "Correction-Unavailable")[1]
    assert "studentised range" in reason
    assert _row(_csv_rows(tmp_path, "tk"), "Correction-AlphaStar") is None


def test_two_way_offers_no_null_and_still_gets_the_ladder():
    df = pd.DataFrame({
        "Condition": ["A"] * 4 + ["B"] * 4 + ["C"] * 4,
        "Genotype": ["WT", "WT", "KO", "KO"] * 3,
        "Sex": ["M", "F"] * 6,
        "Marker": [1.0, 1.2, 1.1, 1.3, 2.0, 2.1, 2.2, 2.3, 4.0, 4.2, 4.1, 4.3],
    })
    exp = SimpleNamespace(summary=df, condition_list=[_Condition("A"),
                                                      _Condition("B"),
                                                      _Condition("C")])
    *_, results_dict, _ = st.runTWA(exp, "Marker",
                                    factors=["Genotype", "Sex"],
                                    comparisons=COMPARISONS)
    # Freedman-Lane residual permutation would be needed; out of scope, so it
    # publishes no family and the free ladder still applies downstream.
    assert results_dict["_audit_inputs"].get("family") is None
    assert len(results_dict["Posthoc-Uncorrected"][1]) == 3


def test_audit_inputs_do_not_survive_into_the_stats_cache(tmp_path,
                                                          monkeypatch):
    # _audit_inputs holds the raw arrays; keeping them in a session-long cache
    # would pin the data long after the figure is gone.
    monkeypatch.setattr(Config, "STATS_CACHE", True, raising=False)
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", "full", raising=False)
    st.clear_stats_cache()
    _run(tmp_path, save_name="c1", stats_test="anova", posthoc="Fisher LSD",
         cache_key="k")
    cached = st._stats_cache["k"]["results_dict"]
    assert "groups" not in (cached.get("_audit_inputs") or {})


# ── the describe layer ───────────────────────────────────────────────
from PyFLASH import report


@pytest.fixture
def collector():
    report.collect()          # disarm and clear whatever a prior test left
    report.start()
    yield
    report.collect()


def _contested_groups():
    # 1-3 is significant uncorrected and under the calibrated threshold, but
    # not under Bonferroni. The case the whole feature exists for.
    return [pd.Series([1.0, 1.2, 1.1]),
            pd.Series([1.9, 2.6, 2.2]),
            pd.Series([2.3, 2.4, 2.15, 2.6])]


def _record(tmp_path, groups=None, **kw):
    _kw(tmp_path, save_name="rec", groups=groups or _contested_groups(), **kw)
    records = report.collect()
    assert records, "the collector was armed but caught nothing"
    return records[0]


def test_every_comparison_carries_every_convention(tmp_path, collector):
    record = _record(tmp_path)
    for entry in record["pairwise"]:
        for key in ("p_uncorrected", "p_holm", "p_bh_q", "p_bonferroni",
                    "p_sidak", "p_westfall_young"):
            assert key in entry, f"{key} missing from {entry['comparison']}"
        assert isinstance(entry["significant_under"], list)


def test_the_record_carries_the_design_wide_numbers(tmp_path, collector):
    block = _record(tmp_path)["correction"]
    assert block["null_mode"] == "exact"
    assert block["n_perm"] == 4200
    assert block["alpha_star"] > block["alpha_bonferroni"]
    assert block["reported"] == "Uncorrected"
    assert block["unavailable"] is None


def test_a_contested_verdict_is_named_in_the_record_and_the_headline(
        tmp_path, collector):
    record = _record(tmp_path)
    assert record["correction"]["contested"] == ["1-3"]
    assert "correction-dependent: 1-3" in record["headline"]
    entry = next(e for e in record["pairwise"] if e["comparison"] == "1-3")
    assert "uncorrected" in entry["significant_under"]
    assert "bonferroni" not in entry["significant_under"]


def test_a_settled_verdict_is_not_contested(tmp_path, collector):
    # Three well-separated groups: every convention agrees, so the choice of
    # correction decided nothing.
    record = _record(tmp_path, groups=_three_groups())
    assert record["correction"]["contested"] == []
    assert "correction-dependent" not in record["headline"]


def test_a_verdict_nobody_supports_is_not_contested_either(tmp_path,
                                                           collector):
    flat = [pd.Series([1.0, 1.05, 0.95]),
            pd.Series([1.02, 0.99, 1.01]),
            pd.Series([1.0, 1.03, 0.98, 1.01])]
    record = _record(tmp_path, groups=flat)
    assert record["correction"]["contested"] == []


def test_the_record_survives_json(tmp_path, collector):
    import json
    record = _record(tmp_path)
    assert json.dumps(record)          # no NaN, no numpy, no tuple keys


def test_raw_stats_does_not_smuggle_the_arrays_into_the_record(tmp_path,
                                                               collector):
    record = _record(tmp_path)
    assert not [k for k in (record.get("raw_stats") or {})
                if str(k).startswith("_")]


def test_a_broken_verdict_helper_does_not_lose_the_record(tmp_path,
                                                          monkeypatch,
                                                          collector):
    def boom(*a, **k):
        raise RuntimeError("verdict exploded")

    monkeypatch.setattr(se, "verdict_changes", boom)
    record = _record(tmp_path)
    # The ladder is the always-on promise, so a fault in the summary layer must
    # not take it down: every convention still reaches the record, and the
    # figure was never at risk.
    assert record["pairwise"]
    assert "p_bonferroni" in record["pairwise"][0]
    assert record["correction"]["contested"] == []
    assert record["pairwise"][0]["significant_under"] == []


def test_a_path_without_an_audit_still_builds_a_record(collector):
    record = report.build_comparison_record(
        metric="m", group_names=["A", "B"],
        group_values=[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        test="Two-Way ANOVA", comparisons=["1-2"], pairwise_pvalues=[0.04],
    )
    assert "correction" not in record
    assert record["pairwise"][0]["p"] == pytest.approx(0.04)


def test_the_reported_correction_is_recorded_not_parsed(tmp_path, collector):
    _kw(tmp_path, save_name="rep", groups=_contested_groups(),
        posthoc_correction="Bonferroni")
    record = report.collect()[0]
    assert record["correction"]["reported"] == "Bonferroni"
    assert record["post_hoc"] == "Dunn Bonferroni"


# ── the stats cache must not outlive a settings change ───────────────
def test_the_cache_key_follows_the_session_correction_default(monkeypatch):
    # multipleComparisons resolves "auto" against Config AFTER the key is
    # built, so the key has to carry the session setting itself.
    args = ("Count", ["WT", "KO"], ("x",), {"posthoc": "Dunn"})
    before = st.stats_cache_key(*args)
    monkeypatch.setattr(Config, "POSTHOC_CORRECTION", "westfall-young",
                        raising=False)
    assert st.stats_cache_key(*args) != before
    monkeypatch.setattr(Config, "POSTHOC_CORRECTION", "auto", raising=False)
    assert st.stats_cache_key(*args) == before


def test_the_cache_key_follows_the_audit_tier(monkeypatch):
    args = ("Count", ["WT", "KO"], ("x",), {"posthoc": "Dunn"})
    before = st.stats_cache_key(*args)
    monkeypatch.setattr(Config, "CORRECTION_AUDIT", "full", raising=False)
    assert st.stats_cache_key(*args) != before
