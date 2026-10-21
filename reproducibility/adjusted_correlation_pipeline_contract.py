"""Independent whole-call witnesses for adjusted correlation outputs.

The reference combines Pingouin's independently implemented partial Pearson
correlation with direct least-squares, rank-correlation, F-test and multiplicity
calculations for the complete returned pipeline state.
"""
from itertools import combinations
from importlib.metadata import version
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


CAPABILITY_PREFIXES = {
    "PyFLASH.pipeline.adjusted_correlation": ("adjusted-correlation.pipeline.",),
    "adjusted_correlation_pipeline": ("adjusted-correlation.pipeline.",),
}

METHODS = {
    "pearsonr": "Pearson",
    "spearmanr": "Spearman",
    "kendalltau": "Kendall",
}
RTOL = 2e-11
ATOL = 2e-13


def _data():
    t = np.arange(24, dtype=float)
    w = np.sin(t * 0.11) + t * 0.04
    frame = pd.DataFrame(
        {
            "AnimalName": [f"S{i:02d}" for i in range(len(t))],
            "X": 0.8 * w + np.sin(t * 0.31) + t * 0.02,
            "Y": -0.65 * w + np.cos(t * 0.19) + t * 0.03,
            "W": w,
        },
        index=pd.Index([3 + 7 * i for i in range(len(t))], name="source-row"),
    )
    frame.attrs["contract-provenance"] = "retained"
    return frame


def _categorical_data():
    frame = _data()
    level = np.where(np.arange(len(frame)) % 2 == 0, "control", "treated")
    shift = np.where(level == "treated", 1.0, -1.0)
    frame["Batch"] = level
    frame["X"] += 0.8 * shift
    frame["Y"] -= 0.6 * shift
    return frame


def _bh(values):
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    adjusted = np.empty(len(values), dtype=float)
    running = 1.0
    for index in range(len(values) - 1, -1, -1):
        original = order[index]
        running = min(running, values[original] * len(values) / (index + 1))
        adjusted[original] = min(1.0, running)
    return adjusted


def _fit(y, predictors):
    y = np.asarray(y, dtype=float)
    design = np.column_stack([np.ones(len(y)), *[np.asarray(x, dtype=float) for x in predictors]])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ coefficients
    return design, coefficients, residuals


def _ordinary_pair(x, y, method):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    n = len(x)
    if method == "kendalltau":
        coefficient, pvalue = _kendall_exact_no_ties(x, y)
    else:
        if method == "spearmanr":
            x, y = _midranks(x), _midranks(y)
        coefficient = _pearson_coefficient(x, y)
        degrees = n - 2
        tvalue = coefficient * math.sqrt(degrees / max(1.0 - coefficient**2, np.finfo(float).eps))
        pvalue = float(2.0 * stats.t.sf(abs(tvalue), degrees))
    return {"n": len(x), "r": float(coefficient), "p": float(pvalue)}


def _pearson_coefficient(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    dx, dy = x - np.mean(x), y - np.mean(y)
    return float(np.sum(dx * dy) / math.sqrt(float(np.sum(dx * dx) * np.sum(dy * dy))))


def _midranks(values):
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    return ranks


def _kendall_exact_no_ties(x, y):
    """Tau and two-sided permutation probability from the inversion distribution."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(np.unique(x)) != len(x) or len(np.unique(y)) != len(y):
        raise ValueError("The frozen Kendall reference case requires untied values.")
    order = np.argsort(x, kind="mergesort")
    ordered_y = y[order]
    ranks = np.empty(len(y), dtype=int)
    ranks[np.argsort(ordered_y, kind="mergesort")] = np.arange(len(y))
    permutation = ranks
    discordant = sum(permutation[i] > permutation[j]
                     for i in range(len(permutation)) for j in range(i + 1, len(permutation)))
    pairs = len(permutation) * (len(permutation) - 1) // 2
    observed = abs(pairs - 2 * discordant)
    coefficient = (pairs - 2 * discordant) / pairs
    distribution = [1]
    for size in range(1, len(permutation) + 1):
        next_distribution = [0] * (len(distribution) + size - 1)
        for previous, count in enumerate(distribution):
            for added in range(size):
                next_distribution[previous + added] += count
        distribution = next_distribution
    extreme = sum(count for inversions, count in enumerate(distribution)
                  if abs(pairs - 2 * inversions) >= observed)
    return float(coefficient), float(extreme / math.factorial(len(permutation)))


def _adjusted_pair(frame, method):
    _, _, rx = _fit(frame["X"], [frame["W"]])
    _, _, ry = _fit(frame["Y"], [frame["W"]])
    if method == "spearmanr":
        coefficient = _pearson_coefficient(_midranks(rx), _midranks(ry))
    elif method == "kendalltau":
        coefficient, _unused_p = _kendall_exact_no_ties(rx, ry)
    else:
        coefficient = _pearson_coefficient(rx, ry)
    n, residual_df = len(frame), len(frame) - 2 - 1
    coefficient = float(coefficient)
    if method in {"pearsonr", "spearmanr"}:
        tvalue = coefficient * math.sqrt(residual_df / max(1.0 - coefficient**2, np.finfo(float).eps))
        pvalue = float(2.0 * stats.t.sf(abs(tvalue), residual_df))
    else:
        n_effective = max(float(residual_df + 2), 2.0)
        variance = 2.0 * (2.0 * n_effective + 5.0) / (9.0 * n_effective * (n_effective - 1.0))
        pvalue = float(2.0 * stats.norm.sf(abs(coefficient / math.sqrt(variance))))
    return {"n": n, "r": coefficient, "p": pvalue, "rank": 2, "df": residual_df}


def _screen_reference(frame, candidate="W"):
    rows = []
    for endpoint in ("X", "Y"):
        y = frame[endpoint].to_numpy(dtype=float)
        reduced_design, _reduced_beta, reduced_residuals = _fit(y, [])
        full_design, _full_beta, full_residuals = _fit(y, [frame[candidate]])
        rss_reduced = float(reduced_residuals @ reduced_residuals)
        rss_full = float(full_residuals @ full_residuals)
        df_diff = full_design.shape[1] - reduced_design.shape[1]
        df_resid = len(y) - full_design.shape[1]
        statistic = max(0.0, (rss_reduced - rss_full) / df_diff) / (rss_full / df_resid)
        rows.append({"candidate": candidate, "endpoint": endpoint, "tested": True,
                     "reason": "", "n": len(y), "f_statistic": statistic,
                     "df_diff": float(df_diff), "p_value": float(stats.f.sf(statistic, df_diff, df_resid))})
    rows.append({"candidate": candidate, "endpoint": candidate, "tested": False,
                 "reason": "candidate_is_endpoint", "n": 0,
                 "f_statistic": np.nan, "df_diff": np.nan, "p_value": np.nan})
    qvalues = _bh([row["p_value"] for row in rows if row["tested"]])
    q_index = 0
    for row in rows:
        if row["tested"]:
            row["q_value"] = float(qvalues[q_index])
            row["passes_gate"] = row["q_value"] < 0.05
            q_index += 1
        else:
            row["q_value"] = np.nan
            row["passes_gate"] = False
    passing = sum(bool(row["passes_gate"]) for row in rows)
    for row in rows:
        row.update(candidate_endpoint_hits=passing, promoted=passing > 0,
                   gate="fdr", alpha=0.05, min_endpoint_hits=1)
    return rows


def _model_reference(y, predictors):
    design, coefficients, residuals = _fit(y, predictors)
    n, rank = design.shape
    df_resid = n - rank
    rss = float(residuals @ residuals)
    mse = rss / df_resid
    covariance = mse * np.linalg.inv(design.T @ design)
    standard_errors = np.sqrt(np.diag(covariance))
    tvalues = coefficients / standard_errors
    pvalues = 2.0 * stats.t.sf(np.abs(tvalues), df_resid)
    critical = stats.t.ppf(0.975, df_resid)
    tss = float(np.sum((np.asarray(y, dtype=float) - np.mean(y)) ** 2))
    r_squared = 1.0 - rss / tss
    adjusted_r_squared = 1.0 - (1.0 - r_squared) * (n - 1) / df_resid
    log_likelihood = -0.5 * n * (math.log(2.0 * math.pi) + 1.0 + math.log(rss / n))
    return {
        "design": design, "coefficients": coefficients,
        "standard_errors": standard_errors, "t_values": tvalues,
        "p_values": pvalues, "ci_low": coefficients - critical * standard_errors,
        "ci_high": coefficients + critical * standard_errors, "n": n,
        "r_squared": r_squared, "adjusted_r_squared": adjusted_r_squared,
        "aic": -2.0 * log_likelihood + 2.0 * rank,
        "bic": -2.0 * log_likelihood + math.log(n) * rank,
    }


def _same_number(actual, expected, *, key):
    if math.isnan(float(expected)):
        return math.isnan(float(actual))
    return math.isclose(float(actual), float(expected), rel_tol=RTOL,
                        abs_tol=ATOL if key in {"r", "estimate", "std_error", "t_value",
                                                   "ci_low", "ci_high"} else 2e-12)


def _comparison(key, reference, expected, actual, agrees, *, shape):
    return {
        "contract": key, "reference": reference,
        "family": "independent-whole-adjusted-correlation-call",
        "status": "agree" if agrees else "disagree", "shape": shape,
        "missingness_equal": bool(agrees), "max_absolute_error": "",
        "rtol": RTOL, "atol": ATOL, "pyflash_nonfinite": "explicit-in-json",
        "frozen_reference_agrees": bool(agrees),
        "pyflash_values": json.dumps(actual, sort_keys=True, default=str, allow_nan=True),
        "reference_values": json.dumps(expected, sort_keys=True, default=str, allow_nan=True),
    }


def check(output):
    """Compare every returned numerical family for a screened, adjusted call."""
    from pingouin import partial_corr
    from PyFLASH.pipeline import adjusted_correlation
    from types import SimpleNamespace

    pingouin_version = version("pingouin")
    if pingouin_version != "0.5.5":
        raise RuntimeError(f"Expected pinned Pingouin 0.5.5; found {pingouin_version}.")

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frame = _data()
    original = frame.copy(deep=True)
    experiment = SimpleNamespace(summary=frame, fig_path="", data_path="", condition_list=[])
    result = adjusted_correlation(
        experiment, endpoints=["X", "Y", "W"], candidate_covariates=["W"],
        tests=tuple(METHODS), gate="fdr", alpha=0.05,
        covariate_gate="fdr", covariate_alpha=0.05, min_endpoint_hits=1,
        max_adjusted_regressions=1, save=False, verbose=False,
        run_label="adjusted-correlation-independent-contract",
    )
    rows = []

    expected_screen = _screen_reference(frame)
    observed_screen = result["covariate_screening"].to_dict(orient="records")
    screen_agrees = len(observed_screen) == len(expected_screen)
    for actual, expected in zip(observed_screen, expected_screen):
        for key in ("candidate", "endpoint", "tested", "reason", "n", "df_diff",
                    "passes_gate", "candidate_endpoint_hits", "promoted", "gate",
                    "alpha", "min_endpoint_hits"):
            screen_agrees &= actual[key] == expected[key] if not (isinstance(expected[key], float) and math.isnan(expected[key])) else math.isnan(float(actual[key]))
        for key in ("f_statistic", "p_value", "q_value"):
            screen_agrees &= _same_number(actual[key], expected[key], key=key)
    rows.append(_comparison(
        "adjusted-correlation.pipeline.candidate-screen",
        "independent-numpy-nested-OLS-F-test-and-BH",
        expected_screen, observed_screen, screen_agrees, shape="complete-candidate-by-endpoint-screening-table"))

    raw_expected = []
    for first, second in combinations(("X", "Y", "W"), 2):
        for method, display in METHODS.items():
            raw_expected.append({"x": first, "y": second, "method": display,
                                **_ordinary_pair(frame[first], frame[second], method)})
    for method in METHODS:
        indices = [i for i, row in enumerate(raw_expected) if row["method"] == METHODS[method]]
        qvalues = _bh([raw_expected[i]["p"] for i in indices])
        for i, qvalue in zip(indices, qvalues):
            raw_expected[i].update(q=float(qvalue), sig_p=raw_expected[i]["p"] < 0.05,
                                   sig_q=float(qvalue) < 0.05, passes=float(qvalue) < 0.05)
    raw_actual = result["raw"]["pairwise"].to_dict(orient="records")
    raw_agrees = len(raw_actual) == len(raw_expected)
    raw_fields = ("n", "r", "p", "q", "sig_p", "sig_q", "passes")
    for actual, expected in zip(raw_actual, raw_expected):
        raw_agrees &= (actual["x"], actual["y"], actual["method"]) == (expected["x"], expected["y"], expected["method"])
        for key in raw_fields:
            raw_agrees &= (_same_number(actual[key], expected[key], key=key)
                           if key in {"r", "p", "q"} else actual[key] == expected[key])
    rows.append(_comparison(
        "adjusted-correlation.pipeline.raw-pairwise",
        "SciPy-public-Pearson-Spearman-Kendall-tests-and-independent-BH",
        raw_expected, raw_actual, raw_agrees, shape="all-raw-pair-method-rows-and-gates"))

    pearson_reference = partial_corr(data=frame, x="X", y="Y", covar="W", method="pearson").iloc[0]
    adjusted_expected = []
    for method in METHODS:
        pair = _adjusted_pair(frame, method)
        if method == "pearsonr":
            pair["r"] = float(pearson_reference["r"])
            pair["p"] = float(pearson_reference["p-val"])
        adjusted_expected.append({"x": "X", "y": "Y", "method": METHODS[method], **pair})
    adjusted_q = _bh([row["p"] for row in adjusted_expected])
    for row, qvalue in zip(adjusted_expected, adjusted_q):
        row.update(q=float(qvalue), sig_p=row["p"] < 0.05,
                   sig_q=float(qvalue) < 0.05, passes=float(qvalue) < 0.05)
    adjusted_actual = result["adjusted"]["pairwise"].to_dict(orient="records")
    adjusted_agrees = len(adjusted_actual) == len(adjusted_expected)
    for actual, expected in zip(adjusted_actual, adjusted_expected):
        adjusted_agrees &= (actual["x"], actual["y"], actual["method"]) == (expected["x"], expected["y"], expected["method"])
        for key in ("n", "r", "p", "q", "sig_p", "sig_q", "passes", "covariate_design_rank", "adjusted_df_resid"):
            expected_key = {"covariate_design_rank": "rank", "adjusted_df_resid": "df"}.get(key, key)
            adjusted_agrees &= (_same_number(actual[key], expected[expected_key], key=key)
                                if expected_key in {"r", "p", "q"} else int(actual[key]) == int(expected[expected_key]) if expected_key in {"n", "rank", "df"}
                                else actual[key] == expected[expected_key])
    rows.append(_comparison(
        "adjusted-correlation.pipeline.adjusted-pairwise",
        "Pingouin-0.5.5-partial-Pearson-plus-independent-least-squares-residual-ranks-and-adjusted-df",
        adjusted_expected, adjusted_actual, adjusted_agrees,
        shape="all-adjusted-pair-method-rows-coefficients-p-q-rank-and-gates"))

    expected_selected = [{"x": "X", "y": "Y", "n_methods_sig": 3,
                         "median_abs_r": float(np.median([abs(row["r"]) for row in adjusted_expected]))}]
    actual_selected = result["adjusted"]["selected"]
    selected_agrees = len(actual_selected) == 1
    if selected_agrees:
        selected_row = actual_selected.iloc[0]
        selected_agrees = (selected_row["x"] == "X" and selected_row["y"] == "Y"
                           and int(selected_row["n_methods_sig"]) == 3
                           and _same_number(selected_row["median_abs_r"], expected_selected[0]["median_abs_r"], key="r"))
    selected_summary = {"selected": actual_selected.to_dict(orient="records"),
                        "raw_n_pairs": result["raw"]["n_pairs"],
                        "raw_n_selected": result["raw"]["n_selected"],
                        "adjusted_n_pairs": result["adjusted"]["n_pairs"],
                        "adjusted_n_selected": result["adjusted"]["n_selected"],
                        "promoted_covariates": result["promoted_covariates"],
                        "final_covariates": result["final_covariates"],
                        "final_endpoints": result["final_endpoints"],
                        "pipeline": result["pipeline"], "gate": result["gate"],
                        "value_matrices": result["value_matrices"]}
    expected_summary = {"selected": expected_selected, "raw_n_pairs": 3,
                        "raw_n_selected": sum(row["passes"] for row in raw_expected[::3]),
                        "adjusted_n_pairs": 1, "adjusted_n_selected": 1,
                        "promoted_covariates": ["W"], "final_covariates": ["W"],
                        "final_endpoints": ["X", "Y"], "pipeline": "adjusted_correlation",
                        "gate": "fdr", "value_matrices": "p"}
    raw_pair_gates = {}
    for row in raw_expected:
        raw_pair_gates[(row["x"], row["y"])] = raw_pair_gates.get((row["x"], row["y"]), False) or row["passes"]
    expected_summary["raw_n_selected"] = sum(raw_pair_gates.values())
    summary_agrees = selected_agrees and all(
        selected_summary[key] == expected_summary[key] for key in expected_summary if key != "selected")
    rows.append(_comparison(
        "adjusted-correlation.pipeline.selected-summary",
        "independent-method-gates-and-complete-pair-selection-contract",
        expected_summary, selected_summary, summary_agrees,
        shape="promotions-endpoint-sets-pair-counts-selection-and-manifest-options"))

    residual_expected = []
    for endpoint in ("X", "Y"):
        design, _beta, residual = _fit(frame[endpoint], [frame["W"]])
        rss = float(residual @ residual)
        tss = float(np.sum((frame[endpoint] - frame[endpoint].mean()) ** 2))
        r_squared = 1.0 - rss / tss
        adjusted_r_squared = 1.0 - (1.0 - r_squared) * (len(frame) - 1) / (len(frame) - design.shape[1])
        residual_expected.append({"endpoint": endpoint, "formula": f"{endpoint} ~ W",
                                  "nobs": len(frame), "r_squared": r_squared,
                                  "adj_r_squared": adjusted_r_squared})
    residual_actual = result["residual_models"].to_dict(orient="records")
    residual_agrees = len(residual_actual) == len(residual_expected)
    for actual, expected in zip(residual_actual, residual_expected):
        residual_agrees &= actual["endpoint"] == expected["endpoint"] and actual["formula"] == expected["formula"] and actual["nobs"] == expected["nobs"]
        residual_agrees &= _same_number(actual["r_squared"], expected["r_squared"], key="r")
        residual_agrees &= _same_number(actual["adj_r_squared"], expected["adj_r_squared"], key="r")
    rows.append(_comparison(
        "adjusted-correlation.pipeline.residual-models",
        "independent-numpy-least-squares-residualization",
        residual_expected, residual_actual, residual_agrees, shape="all-endpoint-nuisance-model-summaries"))

    model_expected = _model_reference(frame["Y"], [frame["X"], frame["W"]])
    model_actual = result["adjusted_regression_coefficients"].to_dict(orient="records")
    term_names = ("Intercept", "X", "W")
    model_agrees = len(model_actual) == len(term_names)
    for actual, term, index in zip(model_actual, term_names, range(len(term_names))):
        expected_values = {"estimate": model_expected["coefficients"][index],
                           "std_error": model_expected["standard_errors"][index],
                           "t_value": model_expected["t_values"][index],
                           "p_value": model_expected["p_values"][index],
                           "ci_low": model_expected["ci_low"][index],
                           "ci_high": model_expected["ci_high"][index]}
        model_agrees &= actual["term"] == term and actual["formula"] == "Y ~ X + W"
        model_agrees &= actual["nobs"] == model_expected["n"]
        for key, expected in expected_values.items():
            model_agrees &= _same_number(actual[key], expected, key=key)
    model_agrees &= all(not bool(row["is_primary_predictor"]) if row["term"] != "X" else bool(row["is_primary_predictor"]) for row in model_actual)
    summary_actual = result["adjusted_regression_summaries"].iloc[0].to_dict()
    for key, expected in (("r_squared", model_expected["r_squared"]),
                          ("adj_r_squared", model_expected["adjusted_r_squared"]),
                          ("aic", model_expected["aic"]), ("bic", model_expected["bic"])):
        model_agrees &= _same_number(summary_actual[key], expected, key=key)
    rows.append(_comparison(
        "adjusted-correlation.pipeline.regressions",
        "independent-numpy-OLS-covariance-student-tests-confidence-intervals-and-information-criteria",
        {"coefficients": [{"term": name} for name in term_names],
         "nobs": model_expected["n"], "r_squared": model_expected["r_squared"],
         "adjusted_r_squared": model_expected["adjusted_r_squared"],
         "aic": model_expected["aic"], "bic": model_expected["bic"]},
        {"coefficients": model_actual, "summary": summary_actual}, model_agrees,
        shape="complete-pairwise-OLS-coefficients-inference-and-summary"))

    ownership_agrees = frame.equals(original) and frame.attrs == original.attrs
    rows.append(_comparison(
        "adjusted-correlation.pipeline.input-ownership",
        "literal-index-columns-and-attrs-preservation",
        {"index": list(original.index), "columns": list(original.columns), "attrs": original.attrs},
        {"index": list(frame.index), "columns": list(frame.columns), "attrs": frame.attrs},
        ownership_agrees, shape="source-dataframe-ownership-and-metadata"))

    categorical_frame = _categorical_data()
    categorical_experiment = SimpleNamespace(
        summary=categorical_frame, fig_path="", data_path="", condition_list=[])
    categorical_result = adjusted_correlation(
        categorical_experiment, endpoints=["X", "Y"],
        covariates=["W", "Batch"], categorical=["Batch"],
        reference_levels={"Batch": "control"}, tests=("pearsonr",),
        gate="p", alpha=0.05, save=False, verbose=False,
        run_label="adjusted-correlation-categorical-reference",
    )
    dummy = (categorical_frame["Batch"] == "treated").to_numpy(dtype=float)
    design_x, _beta_x, residual_x = _fit(
        categorical_frame["X"], [categorical_frame["W"], dummy])
    design_y, _beta_y, residual_y = _fit(
        categorical_frame["Y"], [categorical_frame["W"], dummy])
    categorical_rank = int(np.linalg.matrix_rank(design_x))
    categorical_df = len(categorical_frame) - categorical_rank - 1
    categorical_r = _pearson_coefficient(residual_x, residual_y)
    categorical_t = categorical_r * math.sqrt(
        categorical_df / max(1.0 - categorical_r**2, np.finfo(float).eps))
    categorical_p = float(2.0 * stats.t.sf(abs(categorical_t), categorical_df))
    categorical_row = categorical_result["adjusted"]["pairwise"].iloc[0]
    categorical_raw = _ordinary_pair(
        categorical_frame["X"], categorical_frame["Y"], "pearsonr")
    raw_row = categorical_result["raw"]["pairwise"].iloc[0]
    adjusted_category_agrees = (
        int(categorical_row["n"]) == len(categorical_frame)
        and int(categorical_row["covariate_design_rank"]) == categorical_rank
        and int(categorical_row["adjusted_df_resid"]) == categorical_df
        and _same_number(categorical_row["r"], categorical_r, key="r")
        and _same_number(categorical_row["p"], categorical_p, key="p")
        and _same_number(categorical_row["q"], categorical_p, key="p")
        and bool(categorical_row["passes"]) is (categorical_p < 0.05)
        and int(raw_row["n"]) == len(categorical_frame)
        and _same_number(raw_row["r"], categorical_raw["r"], key="r")
        and _same_number(raw_row["p"], categorical_raw["p"], key="p")
        and categorical_result["categorical"] == ["Batch"]
        and categorical_result["reference_levels"] == {"Batch": "control"}
        and categorical_result["final_covariates"] == ["W", "Batch"]
        and categorical_result["promoted_covariates"] == []
    )
    rows.append(_comparison(
        "adjusted-correlation.pipeline.categorical-partial-pearson",
        "independent-treatment-dummy-OLS-residual-correlation-and-t-tail",
        {"n": len(categorical_frame), "r": categorical_r,
         "p": categorical_p, "design_rank": categorical_rank,
         "adjusted_df": categorical_df, "raw_r": categorical_raw["r"],
         "raw_p": categorical_raw["p"], "categorical": ["Batch"],
         "reference_levels": {"Batch": "control"},
         "final_covariates": ["W", "Batch"], "promoted_covariates": []},
        {"n": int(categorical_row["n"]), "r": float(categorical_row["r"]),
         "p": float(categorical_row["p"]),
         "design_rank": int(categorical_row["covariate_design_rank"]),
         "adjusted_df": int(categorical_row["adjusted_df_resid"]),
         "raw_r": float(raw_row["r"]), "raw_p": float(raw_row["p"]),
         "categorical": categorical_result["categorical"],
         "reference_levels": categorical_result["reference_levels"],
         "final_covariates": categorical_result["final_covariates"],
         "promoted_covariates": categorical_result["promoted_covariates"]},
        adjusted_category_agrees,
        shape="raw-versus-adjusted-result-with-explicit-categorical-reference"))

    filtered_reference_frame = categorical_frame[
        categorical_frame["Batch"] == "control"
    ].copy()
    filtered_experiment = SimpleNamespace(
        summary=categorical_frame, fig_path=str(output), data_path=str(output),
        condition_list=[])
    filtered_result = adjusted_correlation(
        filtered_experiment, endpoints=["X", "Y"], covariates=["W"],
        filter_by={"Batch": "control"}, tests=("pearsonr",),
        gate="p", alpha=0.05, save=False, verbose=False,
        run_label="adjusted-correlation-filter-by-alias",
    )
    filtered_raw_expected = _ordinary_pair(
        filtered_reference_frame["X"], filtered_reference_frame["Y"], "pearsonr")
    filtered_adjusted_expected = _adjusted_pair(filtered_reference_frame, "pearsonr")
    filtered_partial_reference = partial_corr(
        data=filtered_reference_frame, x="X", y="Y", covar="W",
        method="pearson").iloc[0]
    filtered_adjusted_expected["r"] = float(filtered_partial_reference["r"])
    filtered_adjusted_expected["p"] = float(filtered_partial_reference["p-val"])
    filtered_raw_actual = filtered_result["raw"]["pairwise"].iloc[0]
    filtered_adjusted_actual = filtered_result["adjusted"]["pairwise"].iloc[0]
    filtered_alias_agrees = (
        int(filtered_raw_actual["n"]) == filtered_raw_expected["n"]
        and int(filtered_adjusted_actual["n"]) == len(filtered_reference_frame)
        and int(filtered_adjusted_actual["covariate_design_rank"]) == 2
        and int(filtered_adjusted_actual["adjusted_df_resid"])
        == len(filtered_reference_frame) - 3
        and _same_number(filtered_raw_actual["r"], filtered_raw_expected["r"], key="r")
        and _same_number(filtered_raw_actual["p"], filtered_raw_expected["p"], key="p")
        and _same_number(filtered_adjusted_actual["r"], filtered_adjusted_expected["r"], key="r")
        and _same_number(filtered_adjusted_actual["p"], filtered_adjusted_expected["p"], key="p")
        and filtered_result["specificity"] == "('Batch', 'control')"
        and filtered_result["final_covariates"] == ["W"]
    )
    rows.append(_comparison(
        "adjusted-correlation.pipeline.filter-by-alias-partial-result",
        "literal Batch=control row filter, direct least squares and Pingouin 0.5.5 partial Pearson",
        {"raw": filtered_raw_expected,
         "adjusted": filtered_adjusted_expected,
         "specificity": "('Batch', 'control')",
         "final_covariates": ["W"]},
        {"raw": filtered_raw_actual.to_dict(),
         "adjusted": filtered_adjusted_actual.to_dict(),
         "specificity": filtered_result["specificity"],
         "final_covariates": filtered_result["final_covariates"]},
        filtered_alias_agrees,
        shape="alias-filtered-raw-and-adjusted-correlation-with-degrees-of-freedom"))

    categorical_residual_expected = []
    for endpoint, design, residual in (
        ("X", design_x, residual_x), ("Y", design_y, residual_y)):
        rss = float(residual @ residual)
        tss = float(np.sum((categorical_frame[endpoint]
                            - categorical_frame[endpoint].mean()) ** 2))
        r_squared = 1.0 - rss / tss
        adjusted_r_squared = 1.0 - (1.0 - r_squared) * (len(categorical_frame) - 1) / (
            len(categorical_frame) - design.shape[1])
        categorical_residual_expected.append({
            "endpoint": endpoint, "nobs": len(categorical_frame),
            "r_squared": r_squared, "adj_r_squared": adjusted_r_squared})
    categorical_residual_actual = categorical_result["residual_models"].to_dict(orient="records")
    categorical_residual_agrees = len(categorical_residual_actual) == 2
    for actual, expected in zip(categorical_residual_actual, categorical_residual_expected):
        categorical_residual_agrees &= (
            actual["endpoint"] == expected["endpoint"]
            and actual["formula"] == f"{expected['endpoint']} ~ W + Batch"
            and int(actual["nobs"]) == expected["nobs"]
            and _same_number(actual["r_squared"], expected["r_squared"], key="r")
            and _same_number(actual["adj_r_squared"], expected["adj_r_squared"], key="r")
        )
    rows.append(_comparison(
        "adjusted-correlation.pipeline.categorical-nuisance-models",
        "independent-numpy-treatment-dummy-least-squares",
        categorical_residual_expected, categorical_residual_actual,
        categorical_residual_agrees,
        shape="both-endpoint-categorical-nuisance-fits-and-adjusted-r-squared"))

    evidence = {
        "case": "24 rows; candidate W is screened against X/Y, promoted by independent nested-model tests, then controls Pearson/Spearman/Kendall residual correlations and Y~X+W regression",
        "reference_packages": {"pingouin": pingouin_version, "numpy": np.__version__,
                               "scipy": version("scipy")},
        "pearson_partial_reference": {"r": float(pearson_reference["r"]), "p": float(pearson_reference["p-val"]), "n": int(pearson_reference["n"])},
        "comparisons": rows,
    }
    (output / "adjusted-correlation-pipeline-independent-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True, default=str, allow_nan=True) + "\n",
        encoding="utf-8")
    failures = [row["contract"] for row in rows if row["status"] != "agree"]
    if failures:
        raise AssertionError("Adjusted-correlation pipeline disagreements: " + ", ".join(failures))
    return rows
