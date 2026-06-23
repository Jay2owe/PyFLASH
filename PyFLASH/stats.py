"""
Statistical testing and plot annotation utilities.
"""

from __future__ import annotations

import csv
import math
import os
from typing import Iterable

from PyFLASH._logging import logger as _log

import numpy as np
import pandas as pd
import scikit_posthocs as sp
import seaborn as sns
import statsmodels.api as sm
from matplotlib import pyplot as plt
from scipy import stats
from scipy.stats import anderson, f_oneway, kstest, normaltest, ttest_ind_from_stats
from statsmodels.formula.api import ols
import itertools

from PyFLASH.config import apply_matplotlib_fast_path
apply_matplotlib_fast_path()

try:
    from scipy.stats import tukey_hsd
except ImportError:  # pragma: no cover
    tukey_hsd = None
    from statsmodels.stats.multicomp import pairwise_tukeyhsd

from PyFLASH.utils import save_fig, strip_name

# ── Stats result cache ──────────────────────────────────────────────
# Keyed on (column_name, frozenset(condition_names), specificity_tuple).
# Populated by multipleComparisons when Config.STATS_CACHE is True.
# Call clear_stats_cache() between independent analysis runs.
_stats_cache: dict = {}


def stats_cache_key(column_name, condition_names, specificity):
    """Build a hashable cache key for a stats computation."""
    conds = frozenset(condition_names) if condition_names else frozenset()
    spec = tuple(specificity) if specificity else ()
    return (str(column_name), conds, spec)


def clear_stats_cache():
    """Reset the stats cache (call between independent analysis runs)."""
    _stats_cache.clear()


def get_annotation(p, ns="ns"):
    """Return significance annotation text for a p-value."""
    if ns == "p":
        ns = round(float(p), 3)
    if p < 0.0001:
        return "****"
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ns


def extract_p_and_stats_from_results(result_object, comparisons):
    pvalues = []
    statistics = []
    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        pvalues.append(float(result_object.pvalue[first, second]))
        statistics.append(float(result_object.statistic[first, second]))
    return statistics, pvalues


def results_to_excel(results_dict, other, experiment_save_path, save_name, verbose=True):
    out_path = f"{experiment_save_path}\\{save_name}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Statistics Results"])
        writer.writerow(["Test", "Statistic", "P-Values"])
        for test_name, values in results_dict.items():
            if len(values) > 1 and isinstance(values[1], list):
                row = [test_name, values[0], *values[1]]
            else:
                row = [test_name, values[0], values[1]]
            writer.writerow(row)
        writer.writerow([""])
        writer.writerow(["Analysis Summary"])
        for key, value in other.items():
            row = [key, *value] if isinstance(value, list) else [key, value]
            writer.writerow(row)
    if verbose:
        _log.confirm(f"Stats results saved to {out_path}")


def bonferroni_correction(p_value, n_tests):
    return min(float(p_value) * int(n_tests), 1.0)


def sidak_correction(p_value, n_tests):
    return 1 - (1 - float(p_value)) ** int(n_tests)


def modified_anderson(data):
    ad_stat, _, _ = anderson(data)
    ad_stat = ad_stat * (1 + (0.75 / 50) + 2.25 / (50**2))
    if ad_stat >= 0.6:
        p = math.exp(1.2937 - 5.709 * ad_stat - 0.0186 * (ad_stat**2))
    elif ad_stat >= 0.34:
        p = math.exp(0.9177 - 4.279 * ad_stat - 1.38 * (ad_stat**2))
    elif ad_stat > 0.2:
        p = 1 - math.exp(-8.318 + 42.796 * ad_stat - 59.938 * (ad_stat**2))
    else:
        p = 1 - math.exp(-13.436 + 101.14 * ad_stat - 223.73 * (ad_stat**2))
    return ad_stat, p


def _coerce_groups(df_list: Iterable) -> list[pd.Series]:
    groups = []
    for g in df_list:
        s = pd.to_numeric(pd.Series(g), errors="coerce").dropna()
        if not s.empty:
            groups.append(s)
    return groups


def _run_tukey(*groups):
    if tukey_hsd is not None:
        return tukey_hsd(*groups)

    values = np.concatenate([np.asarray(g, dtype=float) for g in groups])
    labels = np.concatenate([[i] * len(g) for i, g in enumerate(groups)])
    result = pairwise_tukeyhsd(values, labels)
    n = len(groups)
    stat = np.zeros((n, n), dtype=float)
    pval = np.ones((n, n), dtype=float)
    idx = 0
    for i in range(n):
        for j in range(i + 1, n):
            stat[i, j] = stat[j, i] = float(result.meandiffs[idx])
            pval[i, j] = pval[j, i] = float(result.pvalues[idx])
            idx += 1

    class TukeyResult:
        statistic = stat
        pvalue = pval

    return TukeyResult()


def runITTest(group1, group2, results_dict, ns="ns"):
    g1 = pd.to_numeric(pd.Series(group1), errors="coerce").dropna()
    g2 = pd.to_numeric(pd.Series(group2), errors="coerce").dropna()
    n1, n2 = len(g1), len(g2)
    if n1 < 2 or n2 < 2:
        return [1.0], [ns], (float("nan"), 1.0), results_dict, "Independent T Test"

    mean1, mean2 = g1.mean(), g2.mean()
    var1, var2 = np.var(g1, ddof=1), np.var(g2, ddof=1)
    std1, std2 = np.sqrt(var1), np.sqrt(var2)
    f_stat = var1 / var2 if var2 > 0 else np.inf
    fp_value = stats.f.cdf(f_stat, n1 - 1, n2 - 1) if np.isfinite(f_stat) else 0.0
    equal_var = fp_value >= 0.05
    statistic, pvalue = ttest_ind_from_stats(
        mean1=mean1,
        std1=std1,
        nobs1=n1,
        mean2=mean2,
        std2=std2,
        nobs2=n2,
        equal_var=equal_var,
    )
    results_dict["Independent T Test"] = [float(statistic), float(pvalue)]
    annotation = [get_annotation(pvalue, ns)]
    return [float(pvalue)], annotation, (float(statistic), float(pvalue)), results_dict, "Independent T Test"


def mwu_multiple_comparisons(df_list, comparisons, results_dict, ns="ns"):
    groups = _coerce_groups(df_list)
    if len(groups) < 2:
        return [], [], ([], []), results_dict, "Mann-Whitney U"
    statistics = []
    pvalues = []
    for comparison in comparisons:
        first, second = [int(part) - 1 for part in comparison.split("-")]
        statistic, pvalue = stats.mannwhitneyu(groups[first], groups[second])
        statistics.append(float(statistic))
        pvalues.append(float(pvalue))
    results_dict["Mann-Whitney U"] = [statistics, pvalues]
    annotations = [get_annotation(pvalue, ns) for pvalue in pvalues]
    return pvalues, annotations, (statistics, pvalues), results_dict, "Mann-Whitney U"


def runOWA(df_list, comparisons, results_dict, ns="ns"):
    groups = _coerce_groups(df_list)
    if len(groups) < 2 or any(len(g) <= 1 for g in groups):
        return [], [], (float("nan"), float("nan")), results_dict, "Tukey"
    f_stat, pvalue = f_oneway(*groups)
    results_dict["OWA"] = [float(f_stat), float(pvalue)]
    try:
        tukey_result = _run_tukey(*groups)
    except ValueError:
        return [], [], (float(f_stat), float(pvalue)), results_dict, "Tukey"
    statistics, pvalues = extract_p_and_stats_from_results(tukey_result, comparisons)
    results_dict["Tukey"] = [statistics, pvalues]
    annotations = [get_annotation(p, ns) for p in pvalues]
    return pvalues, annotations, (float(f_stat), float(pvalue)), results_dict, "Tukey"


def runKW(df_list, comparisons, results_dict, posthoc="Conover", ns="ns"):
    groups = _coerce_groups(df_list)
    if len(groups) < 2:
        return [], [], (float("nan"), float("nan")), results_dict, posthoc
    try:
        kw_statistic, kw_pvalue = stats.kruskal(*groups)
    except ValueError as e:
        msg = str(e)
        results_dict["KW_error"] = [msg, np.nan]
        return [], [], (float("nan"), float("nan")), results_dict, f"{posthoc} (error: {msg})"
    results_dict["KW"] = [float(kw_statistic), float(kw_pvalue)]
    correction = "Bonferroni" if len(comparisons) > 3 else "Uncorrected"

    try:
        dunn_df = sp.posthoc_dunn(groups)
        conover_df = sp.posthoc_conover(groups)
    except Exception as e:
        msg = str(e)
        results_dict["Posthoc_error"] = [msg, np.nan]
        return [], [], (float(kw_statistic), float(kw_pvalue)), results_dict, f"{posthoc} (error: {msg})"
    n_tests = len(comparisons)
    dunn_uncorrected = []
    conover_uncorrected = []
    dunn_bonferroni = []
    conover_bonferroni = []

    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        dunn_p = float(dunn_df.iloc[first, second])
        conover_p = float(conover_df.iloc[first, second])
        dunn_uncorrected.append(dunn_p)
        conover_uncorrected.append(conover_p)
        dunn_bonferroni.append(bonferroni_correction(dunn_p, n_tests))
        conover_bonferroni.append(bonferroni_correction(conover_p, n_tests))

    results_dict["Conover-Bonferroni"] = [1, conover_bonferroni]
    results_dict["Conover-Uncorrected"] = [1, conover_uncorrected]
    results_dict["Dunn-Bonferroni"] = [1, dunn_bonferroni]
    results_dict["Dunn-Uncorrected"] = [1, dunn_uncorrected]

    use_corrected = len(comparisons) > 3
    conover = conover_bonferroni if use_corrected else conover_uncorrected
    dunn = dunn_bonferroni if use_corrected else dunn_uncorrected
    posthoc_result = conover if posthoc == "Conover" else dunn
    posthoc_string = f"{posthoc} {correction}"
    annotations = [get_annotation(result, ns) for result in posthoc_result]
    return posthoc_result, annotations, (float(kw_statistic), float(kw_pvalue)), results_dict, posthoc_string


def runTWA(experiment, column, factors=None, comparisons=None, results_dict=None, ns="ns"):
    exp_df = experiment.summary
    factors = factors or experiment.condition_list.factor
    comparisons = comparisons or ["1-2", "2-3", "1-3"]
    results_dict = results_dict or {}
    if len(factors) < 2:
        raise ValueError("Two-way ANOVA requires at least two factors.")

    model = ols(
        f"{column} ~ C({factors[0]}) + C({factors[1]}) + C({factors[0]}):C({factors[1]})",
        data=exp_df,
    ).fit()
    anova_results = sm.stats.anova_lm(model, typ=2)
    for index, row in anova_results.iterrows():
        key = f"2WA {index.strip('C()')}"
        results_dict[key] = [float(row["sum_sq"]), float(row["PR(>F)"])]

    sum_sqs = [float(row["sum_sq"]) for _, row in anova_results.iterrows()]
    pvals = [float(row["PR(>F)"]) for _, row in anova_results.iterrows()]

    cond_list = experiment.condition_list
    groups = [exp_df[exp_df["Condition"] == cond.name][column].dropna() for cond in cond_list]
    tukey_results = _run_tukey(*groups)
    statistics, pairwise_pvalues = extract_p_and_stats_from_results(tukey_results, comparisons)
    results_dict["Tukey"] = [statistics, pairwise_pvalues]
    annotations = [get_annotation(result, ns) for result in pairwise_pvalues]
    return pairwise_pvalues, annotations, (sum_sqs, pvals), results_dict, "Tukey"

def test_normality(df_list, make_plot=True):
    groups = _coerce_groups(df_list)
    if len(groups) == 0:
        fig = None
        if make_plot:
            fig, _ = plt.subplots(1, 2, layout="constrained", figsize=(10, 5))
        return False, {}, fig
    all_data = pd.concat(groups).dropna()
    if len(all_data) < 3:
        fig = None
        if make_plot:
            fig, _ = plt.subplots(1, 2, layout="constrained", figsize=(10, 5))
        return False, {}, fig
    results_dict = {}

    norm_fig = None
    norm_ax = None
    if make_plot:
        norm_fig, norm_ax = plt.subplots(1, 2, layout="constrained", figsize=(10, 5))
        n = max(1, int(len(all_data)))
        n_bins = max(8, min(32, int(np.sqrt(n) * 2)))
        lo = float(np.nanmin(all_data))
        hi = float(np.nanmax(all_data))
        if not np.isfinite(lo) or not np.isfinite(hi):
            lo, hi = 0.0, 1.0
        if hi <= lo:
            hi = lo + 1.0
        sns.histplot(all_data, bins=n_bins, binrange=(lo, hi), ax=norm_ax[0])
        sm.qqplot(all_data, ax=norm_ax[1], fit=True, line="45")

    # D'Agostino-Pearson requires at least 8 samples.
    if len(all_data) >= 8:
        stat_k2, p_k2 = normaltest(all_data)
        results_dict["DA"] = [float(stat_k2), float(p_k2)]
    else:
        p_k2 = float("nan")
        results_dict["DA"] = [float("nan"), float("nan")]

    stat_a, p_a = modified_anderson(all_data)
    stat_ks, p_ks = kstest(all_data, "norm")
    stat_sw, p_sw = stats.shapiro(all_data)
    results_dict["A"] = [float(stat_a), float(p_a)]
    results_dict["KS"] = [float(stat_ks), float(p_ks)]
    results_dict["SW_all"] = [float(stat_sw), float(p_sw)]

    if make_plot and norm_ax is not None:
        pval_string = (
            f"K2: {round(p_k2, 2) if not np.isnan(p_k2) else 'n<8'}\n"
            f"A: {round(p_a, 2)}\n"
            f"KS: {round(p_ks, 2)}\n"
            f"W: {round(p_sw, 2)}"
        )
        norm_ax[0].annotate(pval_string, xy=(0.8, 0.8), size=10, xycoords="axes fraction")

    valid_pvals = [value[1] for value in results_dict.values() if not np.isnan(value[1])]
    normality_count = sum(1 for p in valid_pvals if p > 0.05)
    if len(valid_pvals) == 0:
        normality = False
    else:
        normality = normality_count >= max(1, (len(valid_pvals) // 2) + (len(valid_pvals) % 2))
    return normality, results_dict, norm_fig


def _default_comparisons(num_groups):
    comps = []
    for gap in range(1, num_groups):
        for first in range(1, num_groups - gap + 1):
            second = first + gap
            comps.append(f"{first}-{second}")
    return comps


def _sanitize_comparisons(comparisons, n_groups):
    """Keep only well-formed comparisons inside 1..n_groups."""
    if comparisons is None:
        return []
    valid = []
    seen = set()
    for comp in comparisons:
        try:
            first, second = [int(part) for part in str(comp).split("-")]
        except Exception:
            continue
        if first == second:
            continue
        if not (1 <= first <= n_groups and 1 <= second <= n_groups):
            continue
        norm = f"{min(first, second)}-{max(first, second)}"
        if norm in seen:
            continue
        seen.add(norm)
        valid.append(norm)
    return valid


def _fmt_p(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "n/a"
    if np.isnan(p):
        return "n/a"
    if p < 0.0001:
        return f"{p:.2e}"
    return f"{p:.4f}".rstrip("0").rstrip(".")


def _fmt_es(v):
    """Format an effect size / CI bound (not a p-value): fixed 2 decimals."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "n/a"
    if np.isnan(v):
        return "n/a"
    return f"{v:.2f}"


def _name_of(item):
    return item.name if hasattr(item, "name") else str(item)


STATS_ANNOTATION_X = 1.08
STATS_ANNOTATION_Y = 1.0


def _annotate_stats_summary(ax, test, post_hoc, overall, comparisons, pairwise_pvalues, condition_list, factor_list=None, effect_strings=None):
    """Draw a compact statistics summary to the right of the plot."""
    lines = [f"Test: {test}", f"Post-hoc: {post_hoc}"]

    overall_p = overall[1] if isinstance(overall, tuple) and len(overall) > 1 else None
    if isinstance(overall_p, list):
        labels = factor_list or ["Factor 1", "Factor 2", "Interaction", "Residual"]
        for i, p in enumerate(overall_p):
            name = labels[i] if i < len(labels) else f"Term {i+1}"
            lines.append(f"{name} p={_fmt_p(p)}")
    elif overall_p is not None:
        lines.append(f"Group p={_fmt_p(overall_p)}")

    for i, p in enumerate(pairwise_pvalues):
        if i >= len(comparisons):
            break
        comp = comparisons[i]
        try:
            a, b = [int(x) - 1 for x in comp.split("-")]
            if 0 <= a < len(condition_list) and 0 <= b < len(condition_list):
                label = f"{_name_of(condition_list[a])} vs {_name_of(condition_list[b])}"
            else:
                label = comp
        except Exception:
            label = comp
        lines.append(f"{label}: p={_fmt_p(p)}")

    if effect_strings:
        lines.append("")
        lines.extend(str(s) for s in effect_strings)

    ax.text(
        STATS_ANNOTATION_X, STATS_ANNOTATION_Y, "\n".join(lines),
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=10,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        clip_on=False,
    )


def _annotate_stats_error(ax, error_message):
    """Draw a compact error annotation to the right of the plot."""
    msg = str(error_message)
    if len(msg) > 140:
        msg = msg[:137] + "..."
    ax.text(
        STATS_ANNOTATION_X, STATS_ANNOTATION_Y, f"Stats error:\n{msg}",
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=10,
        color="crimson",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9},
        clip_on=False,
    )


def print_comparison_results(comparisons, condition_list, individual_results, overall_f, overall_p, normality, test, post_hoc, experiment_name, factor_list=None):
    """Build readable summary strings for group and pairwise results."""
    _ = experiment_name, factor_list  # retained for notebook compatibility
    if not isinstance(overall_p, list):
        group_comparison_string = {"Group difference": get_annotation(overall_p, "ns")}
    else:
        labels = factor_list or ["Factor 1", "Factor 2", "Interaction", "Residual"]
        group_comparison_string = {
            labels[i] if i < len(labels) else f"Term {i+1}": get_annotation(p, "ns")
            for i, p in enumerate(overall_p)
        }

    comparison_strings = []
    for i, comparison in enumerate(comparisons):
        if i >= len(individual_results):
            break
        first, second = [int(part) - 1 for part in comparison.split("-")]
        comparison_strings.append(
            f"{_name_of(condition_list[first])} vs {_name_of(condition_list[second])} {get_annotation(individual_results[i], 'ns')}"
        )
    return group_comparison_string, comparison_strings


def plot_comparison_lines_from_figdata(
    scatter, bar, ax,
    annotations=None, comparisons=None,
    errobar_width=0.12, lw=2, pad=10, handles_fraction=0.3,
    max_override=None,
    group_values=None, group_positions=None, group_colors=None,
):
    if scatter is None or bar is None:
        return None
    annotations = annotations or []
    comparisons = comparisons or []
    if not hasattr(scatter, "collections") or not scatter.collections:
        return None
    bar_xs = sorted({patch.get_x() + patch.get_width() / 2 for patch in bar.patches})
    if group_positions is not None and len(group_positions) > 0:
        bar_xs = [float(x) for x in group_positions]
    if len(bar_xs) == 0:
        return None

    # Use provided numeric groups when available (most reliable for SEM/error bar placement).
    if group_values is not None and len(group_values) > 0:
        y_by_center = {}
        centers_with_data = []
        for i, vals in enumerate(group_values):
            if i >= len(bar_xs):
                break
            y = pd.to_numeric(pd.Series(vals), errors="coerce").dropna().to_numpy(dtype=float)
            if len(y) == 0:
                continue
            c = bar_xs[i]
            y_by_center[c] = y.tolist()
            centers_with_data.append(c)
        if group_colors is not None and len(group_colors) > 0:
            color_by_center = {}
            for i, cx in enumerate(centers_with_data):
                color_by_center[cx] = group_colors[i] if i < len(group_colors) else "black"
        else:
            color_by_center = {x: "black" for x in centers_with_data}
    else:
        # Fallback: infer groups from plotted swarm points.
        y_by_center = {x: [] for x in bar_xs}
        color_by_center = {x: "black" for x in bar_xs}
        for coll in scatter.collections:
            offsets = coll.get_offsets()
            if offsets is None or len(offsets) == 0:
                continue
            edge = coll.get_edgecolor()
            edge_color = edge[0] if edge is not None and len(edge) > 0 else "black"
            for x, y in np.asarray(offsets, dtype=float):
                if not np.isfinite(y):
                    continue
                nearest = min(bar_xs, key=lambda c: abs(c - x))
                y_by_center[nearest].append(float(y))
                color_by_center[nearest] = edge_color
        centers_with_data = [x for x in bar_xs if len(y_by_center[x]) > 0]
    n = len(centers_with_data)
    if n == 0:
        return None

    means = [float(np.mean(y_by_center[x])) for x in centers_with_data]
    sems = [
        float(np.std(y_by_center[x], ddof=1) / np.sqrt(len(y_by_center[x])))
        if len(y_by_center[x]) > 1 else 0.0
        for x in centers_with_data
    ]
    max_height = max(float(np.max(y_by_center[x])) for x in centers_with_data)
    error_heights = np.add(means, sems)
    max_all = max(max_height, float(np.max(error_heights)))
    if max_override is not None:
        max_all = max(max_all, float(max_override))

    # Ensure axis range can always contain error bars (comparisons are drawn above via clip_on=False).
    cur_ymin, cur_ymax = ax.get_ylim()
    min_required_top = float(np.max(error_heights)) * 1.03 if len(error_heights) > 0 else cur_ymax
    if cur_ymax < min_required_top:
        ax.set_ylim(cur_ymin, min_required_top)

    pad_height = max_all / pad if max_all > 0 else 1.0
    handles = pad_height * handles_fraction
    base_height = max_all + pad_height
    line_kws = {"lw": lw, "color": "black", "zorder": 1, "clip_on": False}

    # Plot SEM lines at each bar center.
    for i in range(n):
        cx = centers_with_data[i]
        c = color_by_center[cx]
        ax.plot([cx, cx], [means[i], error_heights[i]], color=c, zorder=2.5, lw=2.5)
        ax.plot([cx - errobar_width, cx + errobar_width], [error_heights[i], error_heights[i]], color=c, zorder=2.6, lw=2.5)

    # Default comparisons if none given.
    if comparisons == []:
        pair_iter = itertools.combinations(range(1, n + 1), 2)
        sorted_pairs = sorted(pair_iter, key=lambda x: (x[1] - x[0], x[0]))
        comparisons = [f"{a}-{b}" for a, b in sorted_pairs]

    # Plot comparison brackets.
    updated_x_heights = {}
    offset = 0.1
    top_drawn = max_all
    for i, comparison in enumerate(comparisons):
        if i >= len(annotations):
            break
        start_index, end_index = [int(v) - 1 for v in comparison.split("-")]
        if start_index < 0 or end_index < 0 or start_index >= n or end_index >= n:
            continue
        lo, hi = min(start_index, end_index), max(start_index, end_index)
        xs_cov = centers_with_data[lo:hi + 1]
        present = [x for x in xs_cov if x in updated_x_heights]
        height = max([updated_x_heights[x] for x in present]) if len(present) >= 2 else base_height

        x_left = centers_with_data[lo] + offset
        x_right = centers_with_data[hi] - offset
        ax.plot([x_left, x_left], [height, height + handles], **line_kws)
        ax.plot([x_right, x_right], [height, height + handles], **line_kws)
        ax.plot([x_left, x_right], [height + handles, height + handles], **line_kws)
        x_mid = (x_left + x_right) / 2
        annot = annotations[i]
        # Lift all annotation text slightly for better separation from bracket lines.
        text_lift = base_height * 0.02
        # Keep 'ns' and numeric p text above the line; keep asterisks near the line.
        if annot == "ns":
            annot_y = (height + handles) + base_height * 0.015 + text_lift
        elif isinstance(annot, float):
            annot_y = (height + handles) + base_height * 0.015 + text_lift
        else:
            annot_y = (height + handles) - base_height * 0.018 + text_lift
        ax.text(
            x_mid, annot_y, annot,
            ha="center",
            va="center",
            size=18 if annot == "ns" else 15 if isinstance(annot, float) else 35,
            clip_on=False,
            weight="bold" if annot != "ns" else "normal",
        )

        new_height = height + pad_height + handles
        updated_x_heights.update({x: new_height for x in xs_cov})
        top_drawn = max(top_drawn, new_height + handles)

    return max_all

def plot_comparison_lines_from_fig_data(*args, **kwargs):
    """Backward-compatible alias for alternative function naming."""
    return plot_comparison_lines_from_figdata(*args, **kwargs)


def _effects_to_results_dict(effects, results_dict):
    """Record computed effect sizes into the results dict written to CSV."""
    for key, value in (effects.get("overall") or {}).items():
        results_dict[f"Effect overall ({key})"] = [
            float(value) if value is not None else np.nan, np.nan,
        ]
    for row in effects.get("pairwise", []):
        results_dict[f"Effect {row['comparison']} ({row['metric']})"] = [
            float(row["value"]) if row.get("value") is not None else np.nan,
            [row.get("ci_low"), row.get("ci_high")],
        ]
    return results_dict


def _format_effect_strings(effects, condition_list):
    """Build compact, human-readable effect-size lines for figure/CSV."""
    if not effects:
        return []
    out = []
    for key, value in (effects.get("overall") or {}).items():
        out.append(f"{key.replace('_', ' ')}={_fmt_es(value)}")
    for row in effects.get("pairwise", []):
        comp = row.get("comparison", "")
        try:
            a, b = [int(x) - 1 for x in str(comp).split("-")]
            if 0 <= a < len(condition_list) and 0 <= b < len(condition_list):
                label = f"{_name_of(condition_list[a])} vs {_name_of(condition_list[b])}"
            else:
                label = comp
        except Exception:
            label = comp
        metric = row.get("metric", "effect")
        short = {"hedges_g": "g", "rank_biserial_r": "r"}.get(metric, metric)
        lo, hi = row.get("ci_low"), row.get("ci_high")
        if lo is not None and hi is not None and np.isfinite(lo) and np.isfinite(hi):
            ci_txt = f" [{_fmt_es(lo)}, {_fmt_es(hi)}]"
        else:
            ci_txt = ""
        interp = row.get("interpretation", "")
        interp_txt = f" {interp}" if interp and interp != "n/a" else ""
        out.append(f"{label}: {short}={_fmt_es(row.get('value'))}{ci_txt}{interp_txt}")
    return (["Effect sizes:"] + out) if out else []


def multipleComparisons(
    experiment,
    dfs,
    ax,
    fig,
    scatter,
    bar,
    multiple_comparison="Two-Way",
    save_name=None,
    comparisons=None,
    force_nonparametric=False,
    max_override=None,
    ns="ns",
    annotate_summary=True,
    group_labels=None,
    group_positions=None,
    group_colors=None,
    verbose=False,
    save_normality=False,
    normality_dpi=120,
    draw=True,
    cache_key=None,
):
    """Run group and post-hoc tests, save stats CSV, and optionally annotate.

    When *draw* is False the computation runs but no annotations are added
    to the axes.  The fourth return element is the results dict.

    When *cache_key* is provided and ``Config.STATS_CACHE`` is True,
    previously computed results are reused (draw still runs if requested).
    """
    from PyFLASH.config import Config

    if not dfs:
        return "N/A", "N/A", None, {}
    clean_dfs = [pd.to_numeric(pd.Series(g), errors="coerce").dropna() for g in dfs]
    valid_groups = [g for g in clean_dfs if len(g) > 0]
    if len(valid_groups) < 2:
        return "N/A", "N/A", None, {}

    # ── Cache lookup ────────────────────────────────────────────────
    cached = None
    if cache_key is not None and Config.STATS_CACHE:
        cached = _stats_cache.get(cache_key)
    if cached is not None:
        test = cached['test']
        post_hoc = cached['post_hoc']
        annotations = cached['annotations']
        results = cached['results']
        overall = cached['overall']
        results_dict = cached['results_dict']
        comparisons = cached['comparisons']
        cond_list = group_labels if group_labels is not None else experiment.condition_list
        results_strings = cached.get('results_strings', {})
        effect_strings = cached.get('effect_strings', [])
        if save_name:
            results_to_excel(results_dict, results_strings, experiment.data_path, save_name, verbose=verbose)
        annotation_objects = None
        if draw:
            annotation_objects = plot_comparison_lines_from_figdata(
                scatter, bar, ax,
                annotations=annotations,
                comparisons=comparisons,
                errobar_width=0.12, lw=2,
                max_override=max_override,
                group_values=valid_groups,
                group_positions=group_positions,
                group_colors=group_colors,
            )
            if annotate_summary:
                _annotate_stats_summary(
                    ax=ax, test=test, post_hoc=post_hoc, overall=overall,
                    comparisons=comparisons, pairwise_pvalues=results,
                    condition_list=cond_list,
                    factor_list=experiment.factor if hasattr(experiment, "factor") else None,
                    effect_strings=effect_strings,
                )
        return test, post_hoc, annotation_objects, results_dict

    if comparisons is None:
        default_from_conditions = getattr(experiment.condition_list, "comparisons", None)
        comparisons = default_from_conditions if default_from_conditions is not None else _default_comparisons(len(valid_groups))
    comparisons = _sanitize_comparisons(comparisons, len(valid_groups))
    if len(comparisons) == 0 and len(valid_groups) >= 2:
        comparisons = _default_comparisons(len(valid_groups))
    cond_list = group_labels if group_labels is not None else experiment.condition_list
    normal, results_dict, norm_fig = test_normality(valid_groups, make_plot=save_normality)
    if save_name and save_normality and norm_fig is not None:
        fname = f"{strip_name(save_name)}_normality.png"
        out_path = os.path.join(experiment.data_path, fname)
        norm_fig.savefig(out_path, bbox_inches="tight", dpi=normality_dpi)
        if verbose:
            _log.confirm(f"Normality figure saved to {out_path}")
    if norm_fig is not None:
        plt.close(norm_fig)
    if force_nonparametric:
        normal = False

    try:
        if len(valid_groups) == 2:
            # If either group is too small for t-test assumptions, fall back to MWU.
            if any(len(g) <= 1 for g in valid_groups):
                results, annotations, overall, results_dict, post_hoc = mwu_multiple_comparisons(
                    valid_groups, ["1-2"], results_dict, ns
                )
                test = "Mann-Whitney U"
                comparisons = ["1-2"]
            else:
                results, annotations, overall, results_dict, post_hoc = runITTest(
                    valid_groups[0], valid_groups[1], results_dict, ns
                )
                test = "Independent T-Test"
                comparisons = ["1-2"]
        else:
            if (not normal) or any(len(g) <= 1 for g in valid_groups):
                results, annotations, overall, results_dict, post_hoc = runKW(valid_groups, comparisons, results_dict, ns=ns)
                test = "Kruskal-Wallis"
            elif multiple_comparison == "One-Way":
                results, annotations, overall, results_dict, post_hoc = runOWA(valid_groups, comparisons, results_dict, ns)
                test = "One-Way ANOVA"
            else:
                results, annotations, overall, results_dict, post_hoc = runTWA(
                    experiment,
                    pd.Series(valid_groups[0]).name,
                    comparisons=comparisons,
                    results_dict=results_dict,
                    ns=ns,
                )
                test = "Two-Way ANOVA"
    except Exception as e:
        err = str(e)
        results_dict["Stats_error"] = [err, np.nan]
        if draw and annotate_summary:
            _annotate_stats_error(ax, err)
        if save_name:
            results_to_excel(
                results_dict,
                {"Group Test Used": "Error", "Post-Hoc Test Used": f"Error: {err}", "Comparisons": []},
                experiment.data_path,
                save_name,
                verbose=verbose,
            )
        return "Error", f"Error: {err}", None, results_dict

    group_strings, comp_strings = print_comparison_results(
        comparisons,
        cond_list,
        results,
        overall[0],
        overall[1],
        normal,
        test,
        post_hoc,
        save_name or "Comparison",
        experiment.factor if hasattr(experiment, "factor") else None,
    )

    results_strings = {
        "Group Test Used": test,
        **group_strings,
        "Post-Hoc Test Used": post_hoc,
        "Comparisons": comp_strings,
    }

    # ── Effect sizes ────────────────────────────────────────────────
    effects = {}
    effect_strings = []
    if getattr(Config, "EFFECT_SIZES", True):
        try:
            from PyFLASH import stats_extra as _se
            effects = _se.effect_sizes_for_test(
                valid_groups, test, comparisons,
                ci=getattr(Config, "EFFECT_CI", True),
                n_resamples=getattr(Config, "EFFECT_CI_RESAMPLES", 5000),
            )
            _effects_to_results_dict(effects, results_dict)
            effect_strings = _format_effect_strings(effects, cond_list)
            if effect_strings:
                results_strings["Effect sizes"] = effect_strings[1:]  # drop header for CSV
        except Exception as e:
            results_dict["Effect_error"] = [str(e), np.nan]

    if save_name:
        results_to_excel(results_dict, results_strings, experiment.data_path, save_name, verbose=verbose)
    annotation_objects = None
    if draw:
        annotation_objects = plot_comparison_lines_from_figdata(
            scatter,
            bar,
            ax,
            annotations=annotations,
            comparisons=comparisons,
            errobar_width=0.12,
            lw=2,
            max_override=max_override,
            group_values=valid_groups,
            group_positions=group_positions,
            group_colors=group_colors,
        )
        if annotate_summary:
            _annotate_stats_summary(
                ax=ax,
                test=test,
                post_hoc=post_hoc,
                overall=overall,
                comparisons=comparisons,
                pairwise_pvalues=results,
                condition_list=cond_list,
                factor_list=experiment.factor if hasattr(experiment, "factor") else None,
                effect_strings=effect_strings,
            )

    # ── Cache store ──────────────────────────────────────────────────
    if cache_key is not None and Config.STATS_CACHE:
        _stats_cache[cache_key] = {
            'test': test,
            'post_hoc': post_hoc,
            'annotations': annotations,
            'results': results,
            'overall': overall,
            'results_dict': results_dict,
            'comparisons': comparisons,
            'results_strings': results_strings,
            'effect_strings': effect_strings,
        }

    return test, post_hoc, annotation_objects, results_dict
