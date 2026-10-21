"""Exact leave-group-out references for the iterative linear-model search."""
from __future__ import annotations

from fractions import Fraction
from itertools import combinations
import json
import io
import math
from pathlib import Path


CAPABILITY_PREFIXES = {
    "PyFLASH.modelling.iterative_best_fit": ("iterative-best-fit.",),
}

INVALID_INPUT_CASES = (
    {"key": "iterative-best-fit.invalid-search-strategy", "parameters": {"search_strategy": "gradient"},
     "expected": "search_strategy must be 'exhaustive' or 'beam'."},
    {"key": "iterative-best-fit.invalid-cv-backend", "parameters": {"cv_backend": "cuda"},
     "expected": "cv_backend must be 'ultra', 'fast', or 'statsmodels'."},
    {"key": "iterative-best-fit.no-predictors-after-exclusion",
     "parameters": {"excluded_predictors": ["x", "z"]},
     "expected": "No predictors available after filtering. Check possible_predictors/column_strings/regex_string/predictor_exclude."},
    {"key": "iterative-best-fit.missing-dependent-variable",
     "parameters": {"dependent_variable": "missing"},
     "expected": "dependent_variable 'missing' not found in df."},
)


def cases():
    rows = []
    variants = [
        ("ultra-exhaustive-minmax", "ultra", "minmax", "exhaustive", 2, ["x", "z"], "Animal"),
        ("fast-exhaustive-zscore", "fast", "zscore", "exhaustive", 2, ["x", "z"], "Animal"),
        ("statsmodels-exhaustive-none", "statsmodels", "none", "exhaustive", 2, ["x", "z"], "Animal"),
        ("ultra-beam", "ultra", "none", "beam", 2, ["x", "z"], "Animal"),
        ("ultra-one-feature", "ultra", "none", "exhaustive", 1, ["x", "z"], "Animal"),
        ("ultra-rowwise-fallback", "ultra", "minmax", "exhaustive", 2, ["x"], None),
    ]
    for name, backend, normalize, strategy, max_features, predictors, cv_group in variants:
        rows.append({"key": f"iterative-best-fit.{name}",
                     "capability": "PyFLASH.modelling.iterative_best_fit",
                     "parameters": {"cv_backend": backend,
                                    "normalize_method": normalize,
                                    "search_strategy": strategy,
                                    "max_features": max_features,
                                    "possible_predictors": predictors,
                                    "cv_group_column": cv_group,
                                    "beam_width": 2,
                                    "batch_chunk_size": 2}})
    for name, predictor_options in [
        ("column-contains-alias", {"column_strings": "x"}),
        ("predictor-exclude-alias", {"predictor_exclude": "z"}),
        ("explicit-excluded-predictors", {"excluded_predictors": ["z"]}),
    ]:
        rows.append({"key": f"iterative-best-fit.{name}",
                     "capability": "PyFLASH.modelling.iterative_best_fit",
                     "parameters": {"cv_backend": "ultra", "normalize_method": "none",
                         "search_strategy": "exhaustive", "max_features": 1,
                         "possible_predictors": ["x", "z"], "cv_group_column": "Animal",
                         "beam_width": 2, "batch_chunk_size": 2,
                         "predictor_options": predictor_options}})
    rows.append({"key": "iterative-best-fit.top-single-and-feature-deltas",
                 "capability": "PyFLASH.modelling.iterative_best_fit",
                 "parameters": {"cv_backend": "ultra", "normalize_method": "none",
                     "search_strategy": "exhaustive", "max_features": 2,
                     "possible_predictors": ["x", "z"], "cv_group_column": "Animal",
                     "beam_width": 2, "batch_chunk_size": 2,
                     "top_n_single_predictors": 1, "plot_insights": False}})
    rows.append({"key": "iterative-best-fit.specificity-and-exclusion",
                 "capability": "PyFLASH.modelling.iterative_best_fit",
                 "parameters": {"cv_backend": "ultra", "normalize_method": "none",
                     "search_strategy": "exhaustive", "max_features": 1,
                     "possible_predictors": ["x"], "cv_group_column": "Animal",
                     "beam_width": 2, "batch_chunk_size": 2,
                     "input_options": {"specificity": ("Condition", "B", "C", "D"),
                                       "exclude": ("Condition", "D")}}})
    rows.append({"key": "iterative-best-fit.sentinel-and-missing-predictor",
                 "capability": "PyFLASH.modelling.iterative_best_fit",
                 "parameters": {"cv_backend": "ultra", "normalize_method": "none",
                     "search_strategy": "exhaustive", "max_features": 1,
                     "possible_predictors": ["x", "z"], "cv_group_column": "Animal",
                     "beam_width": 2, "batch_chunk_size": 2,
                     "dataset_variant": "sentinel-and-missing-z"}})
    for repeat in (False, True):
        rows.append({"key": f"iterative-best-fit.same-prefix-repeat-{str(repeat).lower()}",
                     "capability": "PyFLASH.modelling.iterative_best_fit",
                     "parameters": {"cv_backend": "ultra", "normalize_method": "none",
                         "search_strategy": "exhaustive", "max_features": 2,
                         "possible_predictors": ["x", "x_square"], "cv_group_column": "Animal",
                         "beam_width": 2, "batch_chunk_size": 2,
                         "repeat_features": repeat}})
    return rows


def required_keys():
    return ([row["key"] for row in cases()] +
            ["iterative-best-fit.legacy-tuple-return"] +
            [row["key"] for row in INVALID_INPUT_CASES] +
            ["iterative-best-fit.feature-insight-plots",
             "iterative-best-fit.plot-save-and-hue-routes"])


def records():
    return [
        {"Animal": "a0", "Condition": "A", "x": 0, "x_square": 0, "z": 4, "y": -1.0},
        {"Animal": "a0", "Condition": "A", "x": 1, "x_square": 1, "z": 2, "y": 3.0},
        {"Animal": "a1", "Condition": "B", "x": 2, "x_square": 4, "z": 1, "y": 6.25},
        {"Animal": "a1", "Condition": "B", "x": 3, "x_square": 9, "z": 4, "y": 5.25},
        {"Animal": "a2", "Condition": "C", "x": 4, "x_square": 16, "z": 2, "y": 9.5},
        {"Animal": "a2", "Condition": "C", "x": 5, "x_square": 25, "z": 0, "y": 13.5},
        {"Animal": "a3", "Condition": "D", "x": 6, "x_square": 36, "z": 5, "y": 10.75},
        {"Animal": "a3", "Condition": "D", "x": 7, "x_square": 49, "z": 1, "y": 16.75},
    ]


def _fraction(value):
    return Fraction(str(value))


def _solve(matrix, values):
    """Exact Gauss-Jordan solution for a full-rank normal-equation system."""
    n = len(values)
    augmented = [list(map(_fraction, row)) + [_fraction(value)]
                 for row, value in zip(matrix, values, strict=True)]
    for column in range(n):
        pivot = next((row for row in range(column, n)
                      if augmented[row][column] != 0), None)
        if pivot is None:
            raise ValueError("reference design is rank deficient")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [left - factor * right
                              for left, right in zip(augmented[row], augmented[column], strict=True)]
    return [augmented[row][-1] for row in range(n)]


def _fit_predict(train, test, subset):
    width = len(subset) + 1
    design = [[Fraction(1), *(_fraction(row[name]) for name in subset)] for row in train]
    y = [_fraction(row["y"]) for row in train]
    gram = [[sum((x[i] * x[j] for x in design), Fraction())
             for j in range(width)] for i in range(width)]
    rhs = [sum((x[i] * value for x, value in zip(design, y, strict=True)), Fraction())
           for i in range(width)]
    beta = _solve(gram, rhs)
    return [sum((coefficient * value for coefficient, value in
                 zip(beta, [Fraction(1), *(_fraction(row[name]) for name in subset)], strict=True)),
                Fraction()) for row in test]


def reference(row):
    """Independently fit each candidate on held-out group complements."""
    parameters = row["parameters"]
    source = records()
    if parameters.get("dataset_variant") == "sentinel-and-missing-z":
        source[0]["z"] = "NOT_INCLUDED_IN_EXPERIMENT"
        source[1]["z"] = None
    input_options = parameters.get("input_options", {})
    if "specificity" in input_options:
        column, *values = input_options["specificity"]
        source = [record for record in source if record[column] in values]
    if "exclude" in input_options:
        rules = input_options["exclude"]
        if rules and isinstance(rules[0], str):
            rules = [rules]
        for column, *values in rules:
            source = [record for record in source if record[column] not in values]
    sentinel_columns = []
    predictors = list(parameters["possible_predictors"])
    if parameters.get("dataset_variant") == "sentinel-and-missing-z":
        sentinel_columns = ["z"]
        source = [record for record in source
                  if "NOT_INCLUDED_IN_EXPERIMENT" not in (record["y"], record["x"], record["z"])]
        predictors = [name for name in predictors if name != "z"]
    predictor_options = parameters.get("predictor_options", {})
    if "column_strings" in predictor_options:
        needles = [predictor_options["column_strings"]]
        predictors = [name for name in predictors if any(n in name for n in needles)]
    if "predictor_exclude" in predictor_options:
        excluded = predictor_options["predictor_exclude"]
        predictors = [name for name in predictors if excluded not in name]
    for excluded in predictor_options.get("excluded_predictors", []):
        predictors = [name for name in predictors if name != excluded]
    max_features = min(max(1, parameters["max_features"]), len(predictors))
    subsets = []
    for size in range(1, max_features + 1):
        for subset in combinations(predictors, size):
            prefixes = [name.split(":", 1)[0].split("*", 1)[0].split("_", 1)[0]
                        for name in subset]
            if parameters.get("repeat_features", False) or len(prefixes) == len(set(prefixes)):
                subsets.append(subset)
    group_name = parameters["cv_group_column"]
    if group_name and group_name in source[0]:
        holdouts = list(dict.fromkeys(record[group_name] for record in source))
        folds = [[record for record in source if record[group_name] == group]
                 for group in holdouts]
    else:
        folds = [[record] for record in source]
    scores = {}
    predictions = {}
    actual = [float(record["y"]) for record in source]
    for subset in subsets:
        predicted = [None] * len(source)
        fold_errors = []
        for heldout in folds:
            held_ids = {id(record) for record in heldout}
            train = [record for record in source if id(record) not in held_ids]
            values = _fit_predict(train, heldout, subset)
            for record, value in zip(heldout, values, strict=True):
                predicted[source.index(record)] = value
            fold_errors.append(sum((abs(_fraction(record["y"])-value)
                                    for record, value in zip(heldout, values, strict=True)),
                                   Fraction()) / len(heldout))
        # The public leave-group-out objective gives each held-out group equal
        # weight, even when its row count differs; row-wise LOO averages rows.
        mae = sum(fold_errors, Fraction()) / len(fold_errors)
        scores[subset] = mae
        predictions[subset] = predicted
    best = min(subsets, key=lambda subset: scores[subset])
    rows = [{"subset": subset, "subset_size": len(subset),
             "score": float(scores[subset]), "formula": "y ~ " + " + ".join(subset),
             "predictors": " + ".join(subset)} for subset in subsets]
    rows.sort(key=lambda item: (item["subset_size"], item["score"], item["predictors"]))
    top_n = max(1, int(parameters.get("top_n_single_predictors", 3)))
    top_single = [{"predictor": item["subset"][0], "score": item["score"],
                   "formula": item["formula"]}
                  for item in sorted((item for item in rows if item["subset_size"] == 1),
                                     key=lambda item: (item["score"], item["subset"][0]))[:top_n]]
    score_by_subset = {item["subset"]: item["score"] for item in rows}
    feature_stats = {}
    for subset in subsets:
        if len(subset) <= 1:
            continue
        for feature in subset:
            parent = tuple(name for name in subset if name != feature)
            if parent not in score_by_subset:
                continue
            parent_score, score = score_by_subset[parent], score_by_subset[subset]
            delta = parent_score-score
            stat = feature_stats.setdefault(feature, {"deltas": [], "pct": [],
                "improved": 0, "reduced": 0, "unchanged": 0})
            stat["deltas"].append(delta)
            if parent_score != 0:
                stat["pct"].append(delta/abs(parent_score)*100)
            if delta > 0:
                stat["improved"] += 1
            elif delta < 0:
                stat["reduced"] += 1
            else:
                stat["unchanged"] += 1
    feature_summary = [{"feature": feature, "n_added": len(stat["deltas"]),
        "improved_count": stat["improved"], "reduced_count": stat["reduced"],
        "unchanged_count": stat["unchanged"], "mean_delta": sum(stat["deltas"])/len(stat["deltas"]),
        "mean_abs_delta": sum(abs(delta) for delta in stat["deltas"])/len(stat["deltas"]),
        "mean_pct_delta": sum(stat["pct"])/len(stat["pct"]) if stat["pct"] else float("nan")}
        for feature, stat in feature_stats.items()]
    requested_backend = parameters["cv_backend"]
    effective_backend = "statsmodels" if requested_backend == "statsmodels" else "ultra"
    effective_strategy = (parameters["search_strategy"] if effective_backend == "ultra"
                          else "exhaustive")
    return {"best_subset": best, "best_formula": "y ~ " + " + ".join(best),
            "best_score": float(scores[best]), "cv_actual": actual,
            "cv_predicted": [float(value) for value in predictions[best]],
            "all_model_scores": rows, "combinations_tested": len(subsets),
            "valid_models_tested": len(subsets), "cv_backend": effective_backend,
            "cv_backend_requested": requested_backend, "search_strategy": effective_strategy,
            "top_single_predictors": top_single,
            "feature_addition_summary": feature_summary,
            "removed_rows_sentinel": 1 if parameters.get("dataset_variant") == "sentinel-and-missing-z" else 0,
            "removed_predictors_nan": ["z"] if parameters.get("dataset_variant") == "sentinel-and-missing-z" else [],
            "removed_columns_sentinel": sentinel_columns,
            "removed_columns_nan": ["z"] if parameters.get("dataset_variant") == "sentinel-and-missing-z" else []}


def production(row):
    import pandas as pd
    from PyFLASH.modelling import iterative_best_fit

    parameters = row["parameters"]
    predictor_options = parameters.get("predictor_options", {})
    input_options = parameters.get("input_options", {})
    data = records()
    if parameters.get("dataset_variant") == "sentinel-and-missing-z":
        data[0]["z"] = "NOT_INCLUDED_IN_EXPERIMENT"
        data[1]["z"] = None
    result = iterative_best_fit(
        pd.DataFrame(data), "y", possible_predictors=parameters["possible_predictors"],
        max_features=parameters["max_features"], normalize_method=parameters["normalize_method"],
        plot=False, save=False, verbose=False, return_details=True,
        cv_group_column=parameters["cv_group_column"], cv_backend=parameters["cv_backend"],
        search_strategy=parameters["search_strategy"], beam_width=parameters["beam_width"],
        batch_chunk_size=parameters["batch_chunk_size"],
        repeat_features=parameters.get("repeat_features", False),
        **predictor_options,
        **input_options,
        top_n_single_predictors=parameters.get("top_n_single_predictors", 3),
        plot_insights=parameters.get("plot_insights", True),
        dataframe_kwargs={"fig_path": str(Path.cwd()), "data_path": str(Path.cwd())})
    scores = result["all_model_scores"]
    return {"best_subset": tuple(result["best_subset"]),
            "best_formula": result["best_model"], "best_score": result["best_score"],
            "cv_actual": result["cv_actual"], "cv_predicted": result["cv_predicted"],
            "all_model_scores": scores.to_dict(orient="records"),
            "combinations_tested": result["combinations_tested"],
            "valid_models_tested": result["valid_models_tested"],
            "cv_backend": result["cv_backend"],
            "cv_backend_requested": result["cv_backend_requested"],
            "search_strategy": result["search_strategy"],
            "top_single_predictors": result["top_single_predictors"],
            "feature_addition_summary": result["feature_addition_summary"].to_dict(orient="records"),
            "removed_rows_sentinel": result["removed_rows_sentinel"],
            "removed_predictors_nan": result["removed_predictors_nan"],
            "removed_columns_sentinel": result["removed_columns_sentinel"],
            "removed_columns_nan": result["removed_columns_nan"]}


def _legacy_tuple_expected():
    best = reference(cases()[0])
    subset = best["best_subset"]
    source = records()
    normalized = []
    for row in source:
        normalized_row = dict(row)
        for name in subset:
            values = [record[name] for record in source]
            lower, upper = min(values), max(values)
            normalized_row[name] = Fraction(row[name]-lower, upper-lower) if upper != lower else Fraction()
        normalized.append(normalized_row)
    design = [[Fraction(1), *(_fraction(row[name]) for name in subset)]
              for row in normalized]
    response = [_fraction(row["y"]) for row in normalized]
    width = len(subset) + 1
    gram = [[sum((x[i]*x[j] for x in design), Fraction())
             for j in range(width)] for i in range(width)]
    rhs = [sum((x[i]*y for x, y in zip(design, response, strict=True)), Fraction())
           for i in range(width)]
    coefficients = _solve(gram, rhs)
    return {"formula": best["best_formula"], "params": {
        name: float(value) for name, value in zip(("Intercept", *subset), coefficients, strict=True)}}


def _legacy_tuple_production():
    import pandas as pd
    from PyFLASH.modelling import iterative_best_fit

    result = iterative_best_fit(pd.DataFrame(records()), "y",
        possible_predictors=["x", "z"], max_features=2, normalize_method="minmax",
        plot=False, save=False, verbose=False, return_details=False,
        cv_group_column="Animal", cv_backend="ultra",
        dataframe_kwargs={"fig_path": str(Path.cwd()), "data_path": str(Path.cwd())})
    formula, params = result
    return {"formula": formula, "params": params.to_dict()}


def _invalid_case_production(case):
    import pandas as pd
    from PyFLASH.modelling import iterative_best_fit

    parameters = case["parameters"]
    dependent = parameters.get("dependent_variable", "y")
    options = {key: value for key, value in parameters.items()
               if key != "dependent_variable"}
    try:
        iterative_best_fit(pd.DataFrame(records()), dependent,
            possible_predictors=["x", "z"], max_features=2, plot=False,
            save=False, verbose=False, return_details=True, cv_group_column="Animal",
            dataframe_kwargs={"fig_path": str(Path.cwd()), "data_path": str(Path.cwd())},
            **options)
    except Exception as error:
        return {"error_type": type(error).__name__, "error": str(error)}
    return {"error_type": None, "error": None}


def _full_data_ols_reference():
    """Reconstruct the summary printed on the plot without calling statsmodels."""
    import mpmath

    source = records()
    predictors = ("x", "z")
    design = [[Fraction(1), *(_fraction(row[name]) for name in predictors)]
              for row in source]
    response = [_fraction(row["y"]) for row in source]
    width = len(design[0])
    gram = [[sum((row[i] * row[j] for row in design), Fraction())
             for j in range(width)] for i in range(width)]
    rhs = [sum((row[i] * value for row, value in zip(design, response, strict=True)), Fraction())
           for i in range(width)]
    beta = _solve(gram, rhs)
    fitted = [sum((coefficient * cell for coefficient, cell in zip(beta, row, strict=True)), Fraction())
              for row in design]
    residual_ss = sum(((actual - estimate) ** 2 for actual, estimate in
                       zip(response, fitted, strict=True)), Fraction())
    mean = sum(response, Fraction()) / len(response)
    total_ss = sum(((actual - mean) ** 2 for actual in response), Fraction())
    r_squared = 1 - residual_ss / total_ss
    n, df_model = len(response), len(predictors)
    df_resid = n - df_model - 1
    adjusted = 1 - (1 - r_squared) * Fraction(n - 1, df_resid)
    f_value = (r_squared / df_model) / ((1 - r_squared) / df_resid)
    mpmath.mp.dps = 80
    f_mp = mpmath.mpf(f_value.numerator) / f_value.denominator
    tail_x = mpmath.mpf(df_resid) / (df_resid + df_model * f_mp)
    f_pvalue = mpmath.betainc(df_resid / 2, df_model / 2, 0, tail_x, regularized=True)
    sse_per_n = mpmath.mpf(residual_ss.numerator) / residual_ss.denominator / n
    log_likelihood = -mpmath.mpf(n) / 2 * (
        mpmath.log(2 * mpmath.pi) + 1 + mpmath.log(sse_per_n)
    )
    k = df_model + 1
    aic = -2 * log_likelihood + 2 * k
    bic = -2 * log_likelihood + mpmath.log(n) * k
    return {
        "Intercept": float(beta[0]), "x": float(beta[1]), "z": float(beta[2]),
        "R2": float(r_squared), "Adj R2": float(adjusted),
        "F-stat": float(f_value), "F p-val": float(f_pvalue),
        "AIC": float(aic), "BIC": float(bic), "N": n,
        "df_model": df_model, "df_resid": df_resid,
    }


def _plot_route_row(output):
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import pandas as pd
    import PyFLASH.modelling as modelling
    from reprofig import attachment_for

    scratch = Path(output) / "unsaved-plot-inspection"
    scratch.mkdir(parents=True, exist_ok=True)
    plt.close("all")
    original_show = plt.show
    original_save_fig = modelling.save_fig
    save_calls = []

    def intercept_save(figure, save_path, image_name, *args, **kwargs):
        save_calls.append({
            "name": str(image_name),
            "save_path": str(save_path),
            "subfolder": kwargs.get("subfolder"),
            "figure_data": attachment_for(figure).get("data_tables", {}).get("figure_data") is not None,
            "statistics": len(attachment_for(figure).get("statistics", [])),
        })

    plt.show = lambda *args, **kwargs: None
    modelling.save_fig = intercept_save
    try:
        result = modelling.iterative_best_fit(pd.DataFrame(records()), "y",
            possible_predictors=["x", "z"], max_features=2, normalize_method="none",
            plot=True, save=True, verbose=False, return_details=True,
            cv_group_column="Animal", cv_backend="ultra", plot_insights=True,
            hue_column="Condition",
            dataframe_kwargs={"fig_path": str(scratch), "data_path": str(scratch)})
        numbers = plt.get_fignums()
        figures = [plt.figure(number) for number in numbers]
        scatter = figures[0]
        scatter_axis = scatter.axes[0]
        count_figure, delta_figure = figures[-2:]
        attached = attachment_for(scatter)
        tables = attached.get("data_tables", {})
        attached_plot = tables.get("figure_data")
        attached_stats = tables.get("statistics")
        statistic_values = (dict(zip(attached_stats["statistic"], attached_stats["value"], strict=True))
                            if attached_stats is not None else {})
        original_save_fig(scatter, save_calls[0]["save_path"], save_calls[0]["name"],
                          subfolder=save_calls[0]["subfolder"])
        from reprofig import extract_record
        saved_artifacts = sorted(scratch.rglob("*.svg"))
        saved_record = extract_record(saved_artifacts[0]).to_dict() if len(saved_artifacts) == 1 else {}
        saved_tables = {table["name"]: table for table in saved_record.get("data_tables", [])}
        saved_plot_table = saved_tables.get("figure_data", {}).get("contents", "")
        saved_stats_table = saved_tables.get("statistics", {}).get("contents", "")
        if saved_plot_table and saved_stats_table:
            saved_plot_frame = pd.read_csv(io.StringIO(saved_plot_table))
            saved_statistics_frame = pd.read_csv(io.StringIO(saved_stats_table))
            import numpy as np
            saved_csv_matches = (
                list(saved_plot_frame.columns) == list(attached_plot.columns) and
                saved_plot_frame["Condition"].tolist() == attached_plot["Condition"].tolist() and
                np.allclose(saved_plot_frame[["Predicted", "Actual"]].to_numpy(),
                            attached_plot[["Predicted", "Actual"]].to_numpy(),
                            rtol=1e-14, atol=1e-14) and
                len(saved_statistics_frame) == 12
            )
        else:
            saved_csv_matches = False
        independent_stats = _full_data_ols_reference()
        observed = {
            "figure_count": len(figures),
            "scatter_labels": [scatter_axis.get_xlabel(), scatter_axis.get_ylabel()],
            "scatter_points": sum(len(collection.get_offsets())
                                   for collection in scatter_axis.collections),
            "scatter_has_group_legend": scatter_axis.get_legend() is not None,
            "insight_titles": [count_figure.axes[0].get_title(),
                               delta_figure.axes[0].get_title()],
            "insight_bar_counts": [len(count_figure.axes[0].patches),
                                   len(delta_figure.axes[0].patches)],
            "insight_count_values": sorted(round(patch.get_height(), 9)
                                           for patch in count_figure.axes[0].patches),
            "insight_delta_values": sorted(round(patch.get_height(), 9)
                                            for patch in delta_figure.axes[0].patches),
            "result_subset": tuple(result["best_subset"]),
            "record_status": [attached.get("data_status"), attached.get("statistics_status")],
            "attached_plot_table": (list(attached_plot.columns), len(attached_plot))
                                   if attached_plot is not None else None,
            "attached_statistic_count": len(attached.get("statistics", [])),
            "attached_stats": statistic_values,
            "save_calls": save_calls,
            "native_saved_figure_count": len(saved_artifacts),
            "native_saved_record_status": [saved_record.get("data_status"),
                                           saved_record.get("statistics_status")],
            "native_saved_table_names": sorted(saved_tables),
            "native_saved_csv_matches": saved_csv_matches,
            "native_saved_statistic_count": len(saved_record.get("statistics", [])),
            "saved_files": [str(path.relative_to(scratch)) for path in scratch.rglob("*")
                            if path.is_file()],
        }
        independent = reference(cases()[0])["feature_addition_summary"]
        expected = {
            "figure_count": 5,
            "scatter_labels": ["Predicted Values", "Actual Values"],
            "scatter_points": len(records()),
            "scatter_has_group_legend": True,
            "insight_titles": ["Feature Addition Impact Counts", "Average Score Change When Feature Added"],
            "insight_bar_counts": [4, 2],
            "insight_count_values": [0.0, 0.0, 1.0, 1.0],
            "insight_delta_values": sorted(round(row["mean_delta"], 9) for row in independent),
            "result_subset": ("x", "z"),
            "record_status": ["complete", "complete"],
            "attached_plot_table": (["Predicted", "Actual", "Condition"], len(records())),
            "attached_statistic_count": 12,
            "attached_stats": independent_stats,
            "save_calls": [
                {"name": "Best Iterative Model for y", "save_path": str(scratch),
                 "subfolder": "Modelling", "figure_data": True, "statistics": 12},
                {"name": "Best Iterative Model for y x", "save_path": str(scratch),
                 "subfolder": "Modelling", "figure_data": False, "statistics": 0},
                {"name": "Best Iterative Model for y z", "save_path": str(scratch),
                 "subfolder": "Modelling", "figure_data": False, "statistics": 0},
                {"name": "Best Iterative Model for y Feature Addition Count Impact", "save_path": str(scratch),
                 "subfolder": "Modelling", "figure_data": False, "statistics": 0},
                {"name": "Best Iterative Model for y Feature Addition Mean Delta", "save_path": str(scratch),
                 "subfolder": "Modelling", "figure_data": False, "statistics": 0},
            ],
            "native_saved_figure_count": 1,
            "native_saved_record_status": ["complete", "complete"],
            "native_saved_table_names": ["figure_data", "statistics"],
            "native_saved_csv_matches": True,
            "native_saved_statistic_count": 12,
            "saved_files": [str(path.relative_to(scratch)) for path in scratch.rglob("*")
                            if path.is_file()],
        }
        observed_without_stats = dict(observed)
        expected_without_stats = dict(expected)
        observed_stats = observed_without_stats.pop("attached_stats")
        expected_stats = expected_without_stats.pop("attached_stats")
        statistics_agree = (
            observed_stats.keys() == expected_stats.keys() and
            all(math.isclose(float(observed_stats[key]), float(expected_stats[key]),
                             rel_tol=2e-9, abs_tol=2e-11)
                for key in expected_stats if key != "F p-val") and
            math.isclose(float(observed_stats["F p-val"]), float(expected_stats["F p-val"]),
                         rel_tol=1e-8, abs_tol=1e-28)
        )
        agrees = observed_without_stats == expected_without_stats and statistics_agree
    finally:
        modelling.save_fig = original_save_fig
        plt.show = original_show
        plt.close("all")
    return {"contract": "iterative-best-fit.feature-insight-plots",
        "reference": "exact-rational-held-out-and-full-data-ols-with-high-precision-F-tail",
        "family": "grouped-prediction-figure-record-statistics-and-all-save-call-routes",
        "status": "agree" if agrees else "disagree",
        "shape": "figure-count-axes-hue-points-independent-statistics-and-five-save-dispatches",
        "missingness_equal": agrees, "max_absolute_error": "", "rtol": 0., "atol": 0.,
        "pyflash_nonfinite": "none", "frozen_reference_agrees": True,
        "pyflash_values": json.dumps(observed, sort_keys=True),
        "reference_values": json.dumps(expected, sort_keys=True)}


def _equivalent(actual, expected, *, atol=1e-9, rtol=1e-8):
    import math
    if isinstance(expected, dict):
        return (actual.keys() == expected.keys() and
                all(_equivalent(actual[key], value, atol=atol, rtol=rtol)
                    for key, value in expected.items()))
    if isinstance(expected, (list, tuple)):
        return (len(actual) == len(expected) and
                all(_equivalent(a, e, atol=atol, rtol=rtol)
                    for a, e in zip(actual, expected, strict=True)))
    if isinstance(expected, (int, float, Fraction)) and not isinstance(expected, bool):
        try:
            a, e = float(actual), float(expected)
        except (TypeError, ValueError):
            return False
        return math.isclose(a, e, rel_tol=rtol, abs_tol=atol)
    return actual == expected


def validate(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    paired = []
    rows = []
    for case in cases():
        expected = reference(case)
        actual = production(case)
        agrees = _equivalent(actual, expected)
        rows.append({"contract": case["key"], "reference": "exact-rational-normal-equations-and-group-held-out-prediction",
            "family": "iterative-model-search-all-candidate-cv-scores",
            "status": "agree" if agrees else "disagree", "shape": "candidate-score-table-and-winning-held-out-predictions",
            "missingness_equal": agrees, "max_absolute_error": "", "rtol": 1e-8, "atol": 1e-9,
            "pyflash_nonfinite": "none", "frozen_reference_agrees": True,
            "pyflash_values": json.dumps(actual, sort_keys=True),
            "reference_values": json.dumps(expected, sort_keys=True)})
        paired.append({"case": case, "production": actual, "reference": expected, "agrees": agrees})
    tuple_actual, tuple_expected = _legacy_tuple_production(), _legacy_tuple_expected()
    tuple_agrees = _equivalent(tuple_actual, tuple_expected)
    rows.append({"contract": "iterative-best-fit.legacy-tuple-return",
        "reference": "exact-rational-full-data-normalized-least-squares-coefficients",
        "family": "backward-compatible-result-shape-and-fit-parameters",
        "status": "agree" if tuple_agrees else "disagree",
        "shape": "formula-and-named-coefficients", "missingness_equal": tuple_agrees,
        "max_absolute_error": "", "rtol": 1e-8, "atol": 1e-9,
        "pyflash_nonfinite": "none", "frozen_reference_agrees": True,
        "pyflash_values": json.dumps(tuple_actual, sort_keys=True),
        "reference_values": json.dumps(tuple_expected, sort_keys=True)})
    paired.append({"case": {"key": "iterative-best-fit.legacy-tuple-return"},
        "production": tuple_actual, "reference": tuple_expected, "agrees": tuple_agrees})
    for case in INVALID_INPUT_CASES:
        actual = _invalid_case_production(case)
        expected = {"error_type": "ValueError", "error": case["expected"]}
        agrees = actual == expected
        rows.append({"contract": case["key"], "reference": "declared-public-input-validation-error",
            "family": "invalid-argument-and-empty-search-boundaries",
            "status": "agree" if agrees else "disagree",
            "shape": "exception-type-and-complete-message", "missingness_equal": agrees,
            "max_absolute_error": "", "rtol": 0., "atol": 0.,
            "pyflash_nonfinite": "none", "frozen_reference_agrees": True,
            "pyflash_values": json.dumps(actual, sort_keys=True),
            "reference_values": json.dumps(expected, sort_keys=True)})
        paired.append({"case": case, "production": actual, "reference": expected,
                       "agrees": agrees})
    plot_row = _plot_route_row(output)
    rows.append(plot_row)
    paired.append({"case": {"key": plot_row["contract"]},
        "production": json.loads(plot_row["pyflash_values"]),
        "reference": json.loads(plot_row["reference_values"]),
        "agrees": plot_row["status"] == "agree"})
    saved_route_row = dict(plot_row)
    saved_route_row.update({
        "contract": "iterative-best-fit.plot-save-and-hue-routes",
        "family": "native-saved-scatter-exact-tables-and-condition-hue",
        "shape": "native-carrier-record-exact-data-statistics-and-five-save-dispatches",
    })
    rows.append(saved_route_row)
    paired.append({"case": {"key": saved_route_row["contract"]},
        "production": json.loads(saved_route_row["pyflash_values"]),
        "reference": json.loads(saved_route_row["reference_values"]),
        "agrees": saved_route_row["status"] == "agree"})
    (output / "iterative-best-fit-paired-data.json").write_text(
        json.dumps({"inputs": records(), "rows": paired}, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    return rows
