"""Composable high-level PyFLASH analysis pipelines."""

import hashlib
import json
import os

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from PyFLASH._logging import logger as _log
from PyFLASH.modelling import (
    _linear_model_reference_value,
    _quote_formula_name,
    _resolve_summary_column,
    _to_numeric_excluding_not_included,
)
from PyFLASH.plotting import (
    _corr_clear_run_dir,
    _compute_correlation,
    _corr_isfile,
    _corr_makedirs,
    _corr_pipeline_append_runs_index,
    _corr_pipeline_compute,
    _corr_pipeline_data_root,
    _corr_pipeline_groups,
    _corr_pipeline_heatmap,
    _corr_pipeline_run_dirs,
    _corr_pipeline_sig_from_values,
    _corr_pipeline_slug,
    _corr_pipeline_use_fdr,
    _corr_read_json,
    _corr_render_matrix_differences,
    _corr_to_csv,
    _corr_write_json,
    _correlation_display_name,
    _filtered_summary_for_specificity,
    _normalize_correlation_method,
    _prepare_matrix_numeric_df,
    _resolve_filtered_columns,
    _resolve_roi_bases,
    plot_regressions,
)
from PyFLASH.utils import save_fig, strip_name

__all__ = ["correlation", "adjusted_correlation"]


def correlation(
    experiment,
    filtered_columns=None,
    against_columns=None,
    by="all",
    factor=None,
    specificity=None,
    roi=None,
    save=True,
    column_strings=None,
    regex_string=None,
    exclude="",
    against_column_strings=None,
    against_regex_string=None,
    against_exclude="",
    tests=("pearsonr", "spearmanr", "kendalltau"),
    require="and",
    gate="fdr",
    alpha=0.05,
    min_n=3,
    max_regressions=12,
    regression_factor=None,
    regression_test="pearsonr",
    regression_combine=True,
    normalize_x=False,
    normalize_y=False,
    tick_label_size=20,
    plot_pvalue_matrices=True,
    plot_qvalue_matrices=True,
    plot_difference_matrices=False,
    difference_comparisons=None,
    difference_gate=None,
    difference_alpha=None,
    difference_test="fisher_z",
    plot_difference_signed=True,
    plot_difference_absolute=True,
    plot_difference_pvalue_matrices=True,
    plot_difference_qvalue_matrices=True,
    plot_difference_gate_matrix=True,
    run_label=None,
    if_exists="overwrite",
    write_manifest=True,
):
    """Correlation discovery -> significance gate -> regression plots, in one run.

    Phase 1 builds one full correlation matrix per method in ``tests`` over the
    chosen columns. Phase 2 corrects p-values (Benjamini-Hochberg) and keeps the
    metric pairs that pass the gate, combining the methods with ``require``
    ('and' / 'or') on either raw p-values (``gate='p'``) or FDR q-values
    (``gate='fdr'``). Phase 3 draws a regression plot for each surviving pair
    (strongest by median |r| first, capped at ``max_regressions``).

    Columns
    -------
    ``filtered_columns`` (or ``column_strings`` / ``regex_string`` / ``exclude``)
    selects the metric set for a square all-vs-all matrix. Supplying
    ``against_columns`` (or its discovery variants) switches to a rectangular
    ``filtered_columns`` x ``against_columns`` analysis instead.

    Matrix figures
    --------------
    Coefficient matrices use the same seaborn heatmap styling as
    :func:`plot_matrices`. By default the pipeline also saves visual raw
    p-value and FDR q-value matrices for each correlation method, alongside
    the coefficient matrices and the combined gate matrix. Set
    ``plot_pvalue_matrices=False`` or ``plot_qvalue_matrices=False`` to skip
    those extra heatmaps while still writing the CSV tables.

    Difference matrices
    -------------------
    Set ``plot_difference_matrices=True`` to compare the grouped matrices
    pairwise. The pipeline writes signed deltas (left - right), absolute deltas,
    and, for Pearson correlations, Fisher r-to-z p/q/gate matrices for each
    requested comparison. ``difference_comparisons`` accepts PyFLASH comparison
    strings (``"1-2"``) or explicit pairs (``("AD", "MCI")``).

    Run management
    --------------

    Every call writes into its own run folder so previous runs are never
    silently lost and you can try several column sets side by side:

    - ``Python Figures/Correlation Pipeline/<run>/`` - the matrices and
      regression plots.
    - ``Data and Stats/Correlation Pipeline/<run>/`` -
      ``pairwise_correlations.csv`` (r/p/q/significance per method),
      ``selected_pairs.csv``, per-method matrix CSVs, and ``manifest.json``.
    - ``Data and Stats/Correlation Pipeline/_runs_index.csv`` - one row per run
      for quick comparison.

    ``run_label`` names the folder; when omitted it is auto-derived from the
    column set and settings, so a different column list lands in a different
    folder automatically while identical settings reuse one. ``if_exists``
    controls collisions: ``'overwrite'`` (default, replace in place),
    ``'version'`` (next free ``_vN``), ``'error'`` (raise), or ``'skip'``
    (return the cached manifest without recomputing).

    Grouping
    --------
    ``by='all'`` (default) computes one pooled matrix. ``factor='Diagnosis'`` or
    ``by='conditions'`` panel the matrices/gate/regressions per group.
    ``regression_factor`` colors/groups the regression scatter (e.g. one pooled
    matrix with AD/MCI/Control regression points), independent of the matrix
    paneling.

    Returns a dict with the resolved run label, output directories, per-group
    counts, and the pairwise / selected-pair DataFrames.
    """
    methods = [_normalize_correlation_method(t)
               for t in ([tests] if isinstance(tests, str) else list(tests))]
    if not methods:
        raise ValueError("tests must name at least one correlation method.")
    if str(require).strip().lower() not in ("and", "or"):
        raise ValueError(f"require must be 'and' or 'or'; got {require!r}.")
    use_fdr = _corr_pipeline_use_fdr(gate)

    _roi_base = _resolve_roi_bases(roi, experiment)[0]

    # Resolve the analysis dataset (specificity/ROI scope) and columns.
    scope_df = _filtered_summary_for_specificity(experiment, specificity, roi_base=_roi_base)
    resolved_columns = _resolve_filtered_columns(
        experiment, filtered_columns=filtered_columns,
        column_strings=column_strings, regex_string=regex_string,
        exclude=exclude, source_df=scope_df,
    )
    use_against = (against_columns is not None or against_column_strings
                   or against_regex_string or against_exclude)
    against_resolved = []
    if use_against:
        against_resolved = _resolve_filtered_columns(
            experiment, filtered_columns=against_columns,
            column_strings=against_column_strings, regex_string=against_regex_string,
            exclude=against_exclude, source_df=scope_df,
        )

    union = list(dict.fromkeys(list(resolved_columns) + list(against_resolved)))
    num_df, valid_all, _dropped = _prepare_matrix_numeric_df(
        scope_df, union, drop_duplicate_columns=False, require_complete_numeric=False,
    )
    valid_set = set(valid_all)
    square = not use_against
    if square:
        row_valid = [c for c in resolved_columns if c in valid_set]
        col_valid = row_valid
        if len(row_valid) < 2:
            raise ValueError(
                "pipeline.correlation needs at least 2 numeric columns with "
                f"data; got {len(row_valid)} after filtering."
            )
        slug_cols = row_valid
    else:
        row_valid = [c for c in resolved_columns if c in valid_set]
        col_valid = [c for c in against_resolved if c in valid_set]
        if len(row_valid) < 1 or len(col_valid) < 1:
            raise ValueError(
                "pipeline.correlation rectangular mode needs at least one "
                f"numeric column on each side; got {len(row_valid)} x {len(col_valid)}."
            )
        slug_cols = list(dict.fromkeys(row_valid + col_valid))

    # Run folder resolution.
    label = run_label or _corr_pipeline_slug(
        slug_cols, against_resolved, methods, require, gate, alpha,
        by, factor, specificity, _roi_base,
    )
    fig_dir, data_dir, resolved_label, reuse_existing = _corr_pipeline_run_dirs(
        experiment, label, if_exists, clear_overwrite=bool(save),
    )
    manifest_path = os.path.join(data_dir, "manifest.json")
    if reuse_existing and _corr_isfile(manifest_path):
        cached = _corr_read_json(manifest_path)
        _log.hint(f"[correlation_pipeline] Reusing run {resolved_label!r} (if_exists='skip').")
        cached["reused"] = True
        return cached

    groups = _corr_pipeline_groups(experiment, scope_df, num_df, by, factor, specificity)
    single = len(groups) == 1
    reg_factor = regression_factor
    reg_by = by if reg_factor is not None else "conditions"

    combined_long, combined_selected, group_summaries, plotted_pairs = [], [], [], []
    groups_results = []
    first_long = first_selected = None

    for gi, (glabel, gidx, greg_spec) in enumerate(groups):
        gnum = num_df.loc[num_df.index.intersection(gidx)]
        res = _corr_pipeline_compute(
            gnum, row_valid, col_valid, methods, gate, alpha, require, min_n, square,
        )
        groups_results.append({
            "group": str(glabel),
            "n_rows": int(len(gnum)),
            "result": res,
        })
        if gi == 0:
            first_long, first_selected = res["long"], res["selected"]

        g_long = res["long"] if single else res["long"].assign(group=str(glabel))
        g_sel = res["selected"] if single else res["selected"].assign(group=str(glabel))
        combined_long.append(g_long)
        combined_selected.append(g_sel)

        grp_sub = "" if single else strip_name(str(glabel))
        g_data_dir = os.path.join(data_dir, grp_sub) if grp_sub else data_dir
        g_fig_sub = os.path.join(grp_sub, "Matrices") if grp_sub else "Matrices"

        if save:
            _corr_to_csv(res["long"], os.path.join(g_data_dir, "pairwise_correlations.csv"), index=False)
            _corr_to_csv(res["selected"], os.path.join(g_data_dir, "selected_pairs.csv"), index=False)
            for m in methods:
                disp = _correlation_display_name(m)
                _corr_to_csv(res["coef"][m], os.path.join(g_data_dir, f"coef_{disp}.csv"))
                _corr_to_csv(res["p"][m], os.path.join(g_data_dir, f"pvalues_{disp}.csv"))
                _corr_to_csv(res["q"][m], os.path.join(g_data_dir, f"qvalues_{disp}.csv"))
            _corr_to_csv(res["gate"].astype(int), os.path.join(g_data_dir, "gate_matrix.csv"))

            star = ("q<%g" % alpha) if use_fdr else ("p<%g" % alpha)
            suffix = "" if single else f" - {glabel}"
            for m in methods:
                disp = _correlation_display_name(m)
                fig = _corr_pipeline_heatmap(
                    res["coef"][m], res["sig"][m],
                    f"{disp} Correlation Matrix{suffix}  (* {star})",
                    tick_label_size,
                    cmap="coolwarm", vmin=-1.0, vmax=1.0,
                    colorbar_label=f"{disp} coefficient",
                )
                save_fig(fig, fig_dir, f"{disp} Correlation Matrix", subfolder=g_fig_sub)
                plt.close(fig)
                if plot_pvalue_matrices:
                    pfig = _corr_pipeline_heatmap(
                        res["p"][m], _corr_pipeline_sig_from_values(res["p"][m], alpha),
                        f"{disp} P-Value Matrix{suffix}  (* p<{alpha:g})",
                        tick_label_size,
                        cmap="viridis_r", vmin=0.0, vmax=1.0,
                        colorbar_label="raw p value",
                    )
                    save_fig(pfig, fig_dir, f"{disp} P-Value Matrix", subfolder=g_fig_sub)
                    plt.close(pfig)
                if plot_qvalue_matrices:
                    qfig = _corr_pipeline_heatmap(
                        res["q"][m], _corr_pipeline_sig_from_values(res["q"][m], alpha),
                        f"{disp} FDR Q-Value Matrix{suffix}  (* q<{alpha:g})",
                        tick_label_size,
                        cmap="viridis_r", vmin=0.0, vmax=1.0,
                        colorbar_label="FDR q value",
                    )
                    save_fig(qfig, fig_dir, f"{disp} FDR Q-Value Matrix", subfolder=g_fig_sub)
                    plt.close(qfig)
            gate_ttl = (f"Pairs passing gate{suffix}\n{require.upper()} of "
                        + "/".join(_correlation_display_name(m) for m in methods)
                        + f" @ {'q' if use_fdr else 'p'}<{alpha}")
            gfig = _corr_pipeline_heatmap(
                res["gate"].astype(float), res["gate"], gate_ttl, tick_label_size,
                cmap="Reds", vmin=0.0, vmax=1.0,
                colorbar_label="passes gate",
            )
            save_fig(gfig, fig_dir, "Gate Passing Matrix", subfolder=g_fig_sub)
            plt.close(gfig)

        # Regressions for surviving pairs (redirect output into the run folder).
        sel = res["selected"]
        plot_sel = sel if max_regressions is None else sel.head(int(max_regressions))
        reg_fig_root = os.path.join(fig_dir, grp_sub) if grp_sub else fig_dir
        orig_fig_path = getattr(experiment, "fig_path", None)
        g_plotted = []
        for _, prow in plot_sel.iterrows():
            x, y = prow["x"], prow["y"]
            try:
                experiment.fig_path = reg_fig_root
                plot_regressions(
                    experiment, x=x, y=y, by=reg_by, factor=reg_factor,
                    test=regression_test, normalize_x=normalize_x, normalize_y=normalize_y,
                    specificity=greg_spec, roi=_roi_base, save=save, combine=regression_combine,
                )
                g_plotted.append({
                    "x": x, "y": y,
                    "group": (None if single else str(glabel)),
                    "median_abs_r": float(prow.get("median_abs_r", np.nan)),
                })
            except Exception as exc:
                _log.warn(f"[correlation_pipeline] Regression {x} vs {y} failed: {exc}")
            finally:
                if orig_fig_path is not None:
                    experiment.fig_path = orig_fig_path

        plotted_pairs.extend(g_plotted)
        group_summaries.append({
            "group": str(glabel), "n_rows": int(len(gnum)),
            "n_pairs": int(len(res["pairs"])), "n_selected": int(len(sel)),
            "n_regressions": len(g_plotted),
        })

    long_all = pd.concat(combined_long, ignore_index=True) if combined_long else pd.DataFrame()
    selected_all = pd.concat(combined_selected, ignore_index=True) if combined_selected else pd.DataFrame()
    if save and not single:
        _corr_to_csv(long_all, os.path.join(data_dir, "pairwise_correlations.csv"), index=False)
        _corr_to_csv(selected_all, os.path.join(data_dir, "selected_pairs.csv"), index=False)

    total_pairs = int(sum(g["n_pairs"] for g in group_summaries))
    total_selected = int(sum(g["n_selected"] for g in group_summaries))
    difference_summary = {
        "enabled": bool(plot_difference_matrices),
        "comparisons": [],
        "n_comparisons": 0,
        "n_difference_tests": 0,
        "n_difference_significant": 0,
    }
    if plot_difference_matrices and len(groups_results) >= 2:
        d_alpha = alpha if difference_alpha is None else float(difference_alpha)
        d_gate = gate if difference_gate is None else difference_gate
        prefer_condition = factor is None and str(by).strip().lower() == "conditions"
        diff = _corr_render_matrix_differences(
            experiment,
            groups_results,
            methods,
            comparisons=difference_comparisons,
            prefer_condition_comparisons=prefer_condition,
            fig_dir=os.path.join(fig_dir, "Matrix Differences"),
            data_dir=os.path.join(data_dir, "Matrix Differences"),
            save=save,
            tick_label_size=tick_label_size,
            alpha=d_alpha,
            gate=d_gate,
            test=difference_test,
            plot_signed=plot_difference_signed,
            plot_absolute=plot_difference_absolute,
            plot_pvalue_matrices=plot_difference_pvalue_matrices,
            plot_qvalue_matrices=plot_difference_qvalue_matrices,
            plot_gate_matrix=plot_difference_gate_matrix,
        )
        difference_summary = {
            "enabled": True,
            "comparisons": diff["comparisons"],
            "n_comparisons": diff["n_comparisons"],
            "n_difference_tests": diff["n_difference_tests"],
            "n_difference_significant": diff["n_difference_significant"],
            "alpha": float(d_alpha),
            "gate": str(d_gate).lower(),
            "test": str(difference_test),
        }
    manifest = {
        "run_label": resolved_label,
        "fig_dir": fig_dir,
        "data_dir": data_dir,
        "mode": "rectangular" if not square else "square",
        "n_rows": int(len(num_df)),
        "columns": list(row_valid),
        "against_columns": list(col_valid) if not square else None,
        "tests": [_correlation_display_name(m) for m in methods],
        "require": str(require).lower(),
        "gate": str(gate).lower(),
        "alpha": float(alpha),
        "min_n": int(min_n),
        "plot_pvalue_matrices": bool(plot_pvalue_matrices),
        "plot_qvalue_matrices": bool(plot_qvalue_matrices),
        "difference_matrices": difference_summary,
        "by": str(by),
        "factor": factor,
        "specificity": str(specificity) if specificity is not None else None,
        "roi": str(_roi_base) if _roi_base is not None else None,
        "n_pairs": total_pairs,
        "n_selected": total_selected,
        "n_regressions": len(plotted_pairs),
        "regression_factor": reg_factor,
        "regression_test": _correlation_display_name(_normalize_correlation_method(regression_test)),
        "groups": group_summaries,
        "selected_pairs": selected_all.to_dict(orient="records"),
        "plotted_pairs": plotted_pairs,
        "reused": False,
    }
    if save and write_manifest:
        _corr_write_json(manifest, manifest_path)
        _corr_pipeline_append_runs_index(experiment, manifest)

    _log.confirm(
        f"[correlation_pipeline] {resolved_label}: {total_pairs} pairs, "
        f"{total_selected} passed ({str(require).lower()}/{str(gate).lower()}), "
        f"{len(plotted_pairs)} regressions."
    )
    result_obj = dict(manifest)
    result_obj["pairwise"] = long_all
    result_obj["selected"] = selected_all
    return result_obj


def _adj_as_list(value, *, name="value"):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, pd.Index, np.ndarray, pd.Series)):
        return [str(v) for v in list(value) if str(v).strip() != ""]
    raise TypeError(f"{name} must be a string or iterable of strings.")


def _adj_unique(values):
    out = []
    seen = set()
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _adj_resolve_columns(df, columns, *, kind="columns"):
    resolved = []
    for col in _adj_as_list(columns, name=kind):
        resolved.append(str(_resolve_summary_column(df, col, required=True)))
    return _adj_unique(resolved)


def _adj_resolve_categorical(df, columns, categorical, reference_levels):
    resolved_refs = {}
    for key, value in dict(reference_levels or {}).items():
        col = str(_resolve_summary_column(df, key, required=True))
        resolved_refs[col] = _linear_model_reference_value(df[col], value)

    if categorical is None:
        categorical_set = set()
    elif isinstance(categorical, str) and categorical.strip().lower() == "auto":
        categorical_set = {
            str(col)
            for col in columns
            if col in df.columns
            and (
                pd.api.types.is_object_dtype(df[col])
                or isinstance(df[col].dtype, pd.CategoricalDtype)
                or pd.api.types.is_bool_dtype(df[col])
            )
        }
    else:
        categorical_set = set(_adj_resolve_columns(df, categorical, kind="categorical"))
    categorical_set.update(resolved_refs.keys())
    return categorical_set, resolved_refs


def _adj_model_frame(df, columns, categorical_set, reference_levels=None):
    reference_levels = dict(reference_levels or {})
    cols = [c for c in _adj_unique(columns) if c in df.columns]
    out = pd.DataFrame(index=df.index)
    for col in cols:
        if col in categorical_set:
            raw = df[col].copy()
            sentinel = raw.astype(str).str.contains("NOT_INCLUDED_IN_EXPERIMENT", na=False)
            out[col] = raw.where(~sentinel, np.nan)
            if col in reference_levels:
                ref = reference_levels[col]
                levels = list(pd.Series(out[col]).dropna().unique())
                ordered = [ref] + [level for level in levels if level != ref]
                out[col] = pd.Categorical(out[col], categories=ordered)
        else:
            out[col] = _to_numeric_excluding_not_included(df[col])
    return out.dropna(subset=cols)


def _adj_formula_terms(predictors):
    return [_quote_formula_name(str(pred)) for pred in predictors]


def _adj_fit_ols(df, dependent, predictors, categorical_set, reference_levels):
    import statsmodels.api as sm

    predictors = _adj_unique(predictors)
    model_df = _adj_model_frame(
        df, [dependent] + predictors, categorical_set, reference_levels)
    if len(model_df) < 3:
        raise ValueError(
            f"Need at least 3 complete rows to fit '{dependent}'. "
            f"Only {len(model_df)} rows remain."
        )
    dep = _quote_formula_name(dependent)
    rhs = "1" if len(predictors) == 0 else " + ".join(
        _adj_formula_terms(predictors)
    )
    formula = f"{dep} ~ {rhs}"
    fit = sm.OLS.from_formula(formula, data=model_df).fit()
    return fit, model_df, formula


def _adj_screen_covariates(
    df,
    endpoints,
    always_covariates,
    candidate_covariates,
    *,
    categorical_set,
    reference_levels,
    alpha,
    gate,
    min_endpoint_hits,
):
    rows = []
    always_covariates = _adj_unique(always_covariates)
    for candidate in candidate_covariates:
        for endpoint in endpoints:
            if str(candidate) == str(endpoint):
                rows.append({
                    "candidate": candidate,
                    "endpoint": endpoint,
                    "tested": False,
                    "reason": "candidate_is_endpoint",
                    "n": 0,
                    "f_statistic": np.nan,
                    "df_diff": np.nan,
                    "p_value": np.nan,
                })
                continue
            try:
                full_predictors = _adj_unique(always_covariates + [candidate])
                model_df = _adj_model_frame(
                    df, [endpoint] + full_predictors, categorical_set, reference_levels)
                if len(model_df) < 4:
                    raise ValueError("too_few_complete_rows")
                if model_df[candidate].nunique(dropna=True) < 2:
                    raise ValueError("candidate_has_one_level")
                full_fit, _full_df, _full_formula = _adj_fit_ols(
                    model_df, endpoint, full_predictors,
                    categorical_set, reference_levels,
                )
                reduced_fit, _reduced_df, _reduced_formula = _adj_fit_ols(
                    model_df, endpoint, always_covariates,
                    categorical_set, reference_levels,
                )
                f_stat, p_value, df_diff = full_fit.compare_f_test(reduced_fit)
                rows.append({
                    "candidate": candidate,
                    "endpoint": endpoint,
                    "tested": True,
                    "reason": "",
                    "n": int(full_fit.nobs),
                    "f_statistic": float(f_stat),
                    "df_diff": float(df_diff),
                    "p_value": float(p_value),
                })
            except Exception as exc:
                rows.append({
                    "candidate": candidate,
                    "endpoint": endpoint,
                    "tested": False,
                    "reason": str(exc),
                    "n": 0,
                    "f_statistic": np.nan,
                    "df_diff": np.nan,
                    "p_value": np.nan,
                })

    screening = pd.DataFrame(rows)
    if screening.empty:
        return screening, []

    screening["q_value"] = np.nan
    screening["passes_gate"] = False
    tested_mask = screening["tested"] & np.isfinite(screening["p_value"].astype(float))
    if tested_mask.any():
        from PyFLASH.stats_extra import apply_fdr

        labels = screening.index[tested_mask].tolist()
        adjusted = apply_fdr(
            screening.loc[tested_mask, "p_value"].tolist(),
            labels=labels,
            alpha=float(alpha),
        )
        for _, row in adjusted.iterrows():
            idx = row["label"]
            screening.loc[idx, "q_value"] = float(row["p_adjusted"])

    use_fdr = _corr_pipeline_use_fdr(gate)
    gate_col = "q_value" if use_fdr else "p_value"
    screening.loc[tested_mask, "passes_gate"] = (
        screening.loc[tested_mask, gate_col].astype(float) < float(alpha)
    )

    min_hits = max(1, int(min_endpoint_hits))
    hit_counts = screening.groupby("candidate")["passes_gate"].sum().to_dict()
    promoted = [
        candidate for candidate in candidate_covariates
        if int(hit_counts.get(candidate, 0)) >= min_hits
    ]
    screening["candidate_endpoint_hits"] = screening["candidate"].map(
        lambda c: int(hit_counts.get(c, 0))
    )
    screening["promoted"] = screening["candidate"].isin(promoted)
    screening["gate"] = str(gate).lower()
    screening["alpha"] = float(alpha)
    screening["min_endpoint_hits"] = int(min_hits)
    return screening, promoted


def _adj_residualize_endpoints(
    df,
    endpoints,
    covariates,
    *,
    categorical_set,
    reference_levels,
):
    residuals = pd.DataFrame(index=df.index)
    rows = []
    for endpoint in endpoints:
        if len(covariates) == 0:
            vals = _to_numeric_excluding_not_included(df[endpoint])
            resid = vals - vals.mean(skipna=True)
            residuals[endpoint] = resid
            rows.append({
                "endpoint": endpoint,
                "formula": f"{_quote_formula_name(endpoint)} ~ 1",
                "nobs": int(vals.notna().sum()),
                "r_squared": 0.0,
                "adj_r_squared": 0.0,
            })
            continue
        fit, model_df, formula = _adj_fit_ols(
            df, endpoint, covariates, categorical_set, reference_levels)
        residuals.loc[model_df.index, endpoint] = fit.resid
        rows.append({
            "endpoint": endpoint,
            "formula": formula,
            "nobs": int(fit.nobs),
            "r_squared": float(getattr(fit, "rsquared", np.nan)),
            "adj_r_squared": float(getattr(fit, "rsquared_adj", np.nan)),
        })
    return residuals, pd.DataFrame(rows)


def _adj_corr_run_dirs(experiment, run_label, if_exists, *, clear_overwrite=True):
    base_fig = os.path.join(experiment.fig_path, "Adjusted Correlation Pipeline")
    base_data = os.path.join(_corr_pipeline_data_root(experiment), "Adjusted Correlation Pipeline")
    policy = str(if_exists).strip().lower()
    if policy not in {"overwrite", "version", "error", "skip"}:
        raise ValueError(
            "if_exists must be 'overwrite', 'version', 'error', or 'skip'; "
            f"got {if_exists!r}."
        )

    def _dirs(lbl):
        safe = strip_name(str(lbl))
        if not safe:
            raise ValueError("run_label must resolve to a non-empty folder name.")
        return os.path.join(base_fig, safe), os.path.join(base_data, safe)

    fig_dir, data_dir = _dirs(run_label)
    exists = os.path.isdir(fig_dir) or os.path.isdir(data_dir)
    if not exists:
        return fig_dir, data_dir, run_label, False
    if policy == "overwrite":
        if clear_overwrite:
            _corr_clear_run_dir(fig_dir, base_fig)
            _corr_clear_run_dir(data_dir, base_data)
        return fig_dir, data_dir, run_label, False
    if policy == "skip":
        return fig_dir, data_dir, run_label, True
    if policy == "error":
        raise RuntimeError(
            f"Adjusted correlation run {run_label!r} already exists. Pass "
            f"if_exists='overwrite'/'version'/'skip' or a different run_label."
        )
    idx = 2
    while True:
        cand = f"{run_label}_v{idx}"
        fig_dir, data_dir = _dirs(cand)
        if not (os.path.isdir(fig_dir) or os.path.isdir(data_dir)):
            return fig_dir, data_dir, cand, False
        idx += 1


def _adj_corr_slug(endpoints, covariates, candidates, methods, gate, alpha, by, factor):
    payload = {
        "endpoints": sorted(str(c) for c in endpoints),
        "covariates": sorted(str(c) for c in covariates),
        "candidates": sorted(str(c) for c in candidates),
        "methods": list(methods),
        "gate": str(gate).lower(),
        "alpha": float(alpha),
        "by": str(by),
        "factor": str(factor),
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:6]
    return f"adjusted_{len(endpoints)}endpoints_{digest}"


def _adj_covariate_design_rank(df, covariates, categorical_set, reference_levels):
    """Rank of the covariate design matrix, including the intercept."""
    if len(df) == 0:
        return 0
    covariates = _adj_unique(covariates)
    if len(covariates) == 0:
        return 1
    cov_df = _adj_model_frame(df, covariates, categorical_set, reference_levels)
    if len(cov_df) == 0:
        return 0
    design = pd.DataFrame({"Intercept": np.ones(len(cov_df), dtype=float)}, index=cov_df.index)
    for cov in covariates:
        if cov in categorical_set:
            dummies = pd.get_dummies(cov_df[cov], prefix=cov, drop_first=True, dtype=float)
            for col in dummies.columns:
                design[str(col)] = dummies[col].astype(float)
        else:
            design[cov] = pd.to_numeric(cov_df[cov], errors="coerce").astype(float)
    design = design.dropna(axis=0, how="any")
    if len(design) == 0:
        return 0
    return int(np.linalg.matrix_rank(design.to_numpy(dtype=float)))


def _adj_partial_corr_pvalue(r, method, n, design_rank):
    """Covariate-adjusted p-value approximation for a residual correlation."""
    from scipy import stats as sp_stats

    if not np.isfinite(r):
        return np.nan
    df_resid = int(n) - int(design_rank) - 1
    if df_resid <= 0:
        return np.nan
    r = float(r)
    if abs(r) >= 1.0:
        return 0.0
    method = _normalize_correlation_method(method)
    if method in {"pearsonr", "spearmanr"}:
        denom = max(1.0 - r * r, np.finfo(float).eps)
        t_stat = r * np.sqrt(float(df_resid) / denom)
        return float(2.0 * sp_stats.t.sf(abs(t_stat), df_resid))
    if method == "kendalltau":
        # Normal approximation for Kendall tau with an effective sample size
        # reduced by the fitted covariate design. This is conservative relative
        # to using the original n and avoids overstating residualized gates.
        n_eff = max(float(df_resid + 2), 2.0)
        var_tau = (2.0 * (2.0 * n_eff + 5.0)) / (9.0 * n_eff * (n_eff - 1.0))
        if var_tau <= 0 or not np.isfinite(var_tau):
            return np.nan
        z_stat = r / np.sqrt(var_tau)
        return float(2.0 * sp_stats.norm.sf(abs(z_stat)))
    return np.nan


def _adj_apply_partial_pvalues(
    res,
    residual_num_df,
    source_df,
    covariates,
    *,
    categorical_set,
    reference_levels,
    methods,
    gate,
    alpha,
    require,
):
    """Replace residual-correlation p/q/gates with covariate-df-adjusted values."""
    if len(covariates) == 0:
        return res

    from PyFLASH.stats_extra import apply_fdr

    methods = [_normalize_correlation_method(m) for m in methods]
    long = res["long"].copy()
    p_lookup = {}
    n_lookup = {}
    rank_lookup = {}
    for (x, y) in res["pairs"]:
        sub = residual_num_df[[x, y]].dropna()
        n = int(len(sub))
        rank = _adj_covariate_design_rank(
            source_df.loc[sub.index],
            covariates,
            categorical_set,
            reference_levels,
        )
        n_lookup[(x, y)] = n
        rank_lookup[(x, y)] = rank
        for method in methods:
            try:
                r, _old_p = _compute_correlation(sub[x].to_numpy(), sub[y].to_numpy(), method)
            except Exception:
                r = np.nan
            p_lookup[(x, y, method)] = _adj_partial_corr_pvalue(r, method, n, rank)

    long["q"] = np.nan
    long["sig_p"] = False
    long["sig_q"] = False
    long["passes"] = False
    for idx, row in long.iterrows():
        key = (row["x"], row["y"])
        method = _normalize_correlation_method(row["method"])
        p = p_lookup.get((row["x"], row["y"], method), np.nan)
        long.at[idx, "n"] = n_lookup.get(key, row.get("n", np.nan))
        long.at[idx, "p"] = p
        long.at[idx, "covariate_design_rank"] = rank_lookup.get(key, np.nan)
        df_resid = n_lookup.get(key, 0) - rank_lookup.get(key, 0) - 1
        long.at[idx, "adjusted_df_resid"] = df_resid if df_resid > 0 else np.nan

    for method in methods:
        mask = (
            long["method"].astype(str).eq(_correlation_display_name(method))
            & np.isfinite(long["p"].astype(float))
        )
        if not mask.any():
            continue
        labels = long.index[mask].tolist()
        adjusted = apply_fdr(
            long.loc[mask, "p"].tolist(),
            labels=labels,
            alpha=float(alpha),
        )
        for _, row in adjusted.iterrows():
            long.loc[row["label"], "q"] = float(row["p_adjusted"])

    use_fdr = _corr_pipeline_use_fdr(gate)
    long["sig_p"] = np.isfinite(long["p"].astype(float)) & (long["p"].astype(float) < float(alpha))
    long["sig_q"] = np.isfinite(long["q"].astype(float)) & (long["q"].astype(float) < float(alpha))
    long["passes"] = long["sig_q"] if use_fdr else long["sig_p"]

    require_all = str(require).strip().lower() == "and"
    selected = []
    pass_pairs = set()
    for (x, y), grp in long.groupby(["x", "y"], sort=False):
        sig_count = int(grp["passes"].sum())
        passed = (sig_count == len(methods)) if require_all else (sig_count > 0)
        if not passed:
            continue
        pass_pairs.add((x, y))
        abs_rs = [abs(float(v)) for v in grp["r"] if np.isfinite(v)]
        selected.append({
            "x": x,
            "y": y,
            "x_label": grp["x_label"].iloc[0],
            "y_label": grp["y_label"].iloc[0],
            "n_methods_sig": sig_count,
            "median_abs_r": float(np.median(abs_rs)) if abs_rs else np.nan,
        })
    sel_cols = ["x", "y", "x_label", "y_label", "n_methods_sig", "median_abs_r"]
    selected_df = (
        pd.DataFrame(selected).sort_values(
            "median_abs_r", ascending=False, na_position="last"
        ).reset_index(drop=True)
        if selected else pd.DataFrame(columns=sel_cols)
    )

    coef, pmat, qmat, sigmat = {}, {}, {}, {}
    cols = list(res["coef"][methods[0]].index)
    gate_mat = pd.DataFrame(False, index=cols, columns=cols)
    for method in methods:
        disp = _correlation_display_name(method)
        c = res["coef"][method].copy()
        pm = pd.DataFrame(np.nan, index=c.index, columns=c.columns, dtype=float)
        qm = pm.copy()
        sg = pd.DataFrame(False, index=c.index, columns=c.columns)
        sub = long[long["method"].astype(str).eq(disp)]
        for _, row in sub.iterrows():
            x, y = row["x"], row["y"]
            pm.loc[x, y] = row["p"]
            pm.loc[y, x] = row["p"]
            qm.loc[x, y] = row["q"]
            qm.loc[y, x] = row["q"]
            sg.loc[x, y] = bool(row["passes"])
            sg.loc[y, x] = bool(row["passes"])
        coef[method], pmat[method], qmat[method], sigmat[method] = c, pm, qm, sg
    for x, y in pass_pairs:
        gate_mat.loc[x, y] = True
        gate_mat.loc[y, x] = True

    out = dict(res)
    out.update({
        "long": long,
        "selected": selected_df,
        "coef": coef,
        "p": pmat,
        "q": qmat,
        "sig": sigmat,
        "gate": gate_mat,
    })
    return out


def _adj_write_corr_block(
    experiment,
    scope_df,
    num_df,
    columns,
    *,
    methods,
    gate,
    alpha,
    require,
    min_n,
    by,
    factor,
    specificity,
    fig_dir,
    data_dir,
    block_name,
    save,
    tick_label_size,
    plot_pvalue_matrices,
    plot_qvalue_matrices,
    pvalue_adjuster=None,
):
    groups = _corr_pipeline_groups(experiment, scope_df, num_df, by, factor, specificity)
    single = len(groups) == 1
    combined_long, combined_selected, group_summaries = [], [], []
    use_fdr = _corr_pipeline_use_fdr(gate)

    for glabel, gidx, _greg_spec in groups:
        gnum = num_df.loc[num_df.index.intersection(gidx)]
        res = _corr_pipeline_compute(
            gnum, columns, columns, methods, gate, alpha, require, min_n, True)
        if pvalue_adjuster is not None:
            res = pvalue_adjuster(res, gnum)
        g_long = res["long"] if single else res["long"].assign(group=str(glabel))
        g_sel = res["selected"] if single else res["selected"].assign(group=str(glabel))
        combined_long.append(g_long)
        combined_selected.append(g_sel)

        grp_sub = "" if single else strip_name(str(glabel))
        data_sub = os.path.join(data_dir, block_name, grp_sub) if grp_sub else os.path.join(data_dir, block_name)
        fig_sub = os.path.join(block_name, grp_sub, "Matrices") if grp_sub else os.path.join(block_name, "Matrices")
        if save:
            _corr_to_csv(res["long"], os.path.join(data_sub, "pairwise_correlations.csv"), index=False)
            _corr_to_csv(res["selected"], os.path.join(data_sub, "selected_pairs.csv"), index=False)
            for method in methods:
                disp = _correlation_display_name(method)
                _corr_to_csv(res["coef"][method], os.path.join(data_sub, f"coef_{disp}.csv"))
                _corr_to_csv(res["p"][method], os.path.join(data_sub, f"pvalues_{disp}.csv"))
                _corr_to_csv(res["q"][method], os.path.join(data_sub, f"qvalues_{disp}.csv"))
                suffix = "" if single else f" - {glabel}"
                star = ("q<%g" % alpha) if use_fdr else ("p<%g" % alpha)
                fig = _corr_pipeline_heatmap(
                    res["coef"][method], res["sig"][method],
                    f"{block_name} {disp} Correlation Matrix{suffix}  (* {star})",
                    tick_label_size,
                    cmap="coolwarm", vmin=-1.0, vmax=1.0,
                    colorbar_label=f"{disp} coefficient",
                )
                save_fig(fig, fig_dir, f"{disp} Correlation Matrix", subfolder=fig_sub)
                plt.close(fig)
                if plot_pvalue_matrices:
                    pfig = _corr_pipeline_heatmap(
                        res["p"][method], _corr_pipeline_sig_from_values(res["p"][method], alpha),
                        f"{block_name} {disp} P-Value Matrix{suffix}  (* p<{alpha:g})",
                        tick_label_size,
                        cmap="viridis_r", vmin=0.0, vmax=1.0,
                        colorbar_label="raw p value",
                    )
                    save_fig(pfig, fig_dir, f"{disp} P-Value Matrix", subfolder=fig_sub)
                    plt.close(pfig)
                if plot_qvalue_matrices:
                    qfig = _corr_pipeline_heatmap(
                        res["q"][method], _corr_pipeline_sig_from_values(res["q"][method], alpha),
                        f"{block_name} {disp} FDR Q-Value Matrix{suffix}  (* q<{alpha:g})",
                        tick_label_size,
                        cmap="viridis_r", vmin=0.0, vmax=1.0,
                        colorbar_label="FDR q value",
                    )
                    save_fig(qfig, fig_dir, f"{disp} FDR Q-Value Matrix", subfolder=fig_sub)
                    plt.close(qfig)
            _corr_to_csv(res["gate"].astype(int), os.path.join(data_sub, "gate_matrix.csv"))
            gate_ttl = (f"{block_name} pairs passing gate{suffix}\n{str(require).upper()} of "
                        + "/".join(_correlation_display_name(m) for m in methods)
                        + f" @ {'q' if use_fdr else 'p'}<{alpha:g}")
            gfig = _corr_pipeline_heatmap(
                res["gate"].astype(float), res["gate"], gate_ttl, tick_label_size,
                cmap="Reds", vmin=0.0, vmax=1.0,
                colorbar_label="passes gate",
            )
            save_fig(gfig, fig_dir, "Gate Passing Matrix", subfolder=fig_sub)
            plt.close(gfig)

        group_summaries.append({
            "group": str(glabel),
            "n_rows": int(len(gnum)),
            "n_pairs": int(len(res["pairs"])),
            "n_selected": int(len(res["selected"])),
        })

    long_all = pd.concat(combined_long, ignore_index=True) if combined_long else pd.DataFrame()
    selected_all = pd.concat(combined_selected, ignore_index=True) if combined_selected else pd.DataFrame()
    if save and not single:
        _corr_to_csv(long_all, os.path.join(data_dir, block_name, "pairwise_correlations.csv"), index=False)
        _corr_to_csv(selected_all, os.path.join(data_dir, block_name, "selected_pairs.csv"), index=False)
    return {
        "pairwise": long_all,
        "selected": selected_all,
        "groups": group_summaries,
        "n_pairs": int(sum(g["n_pairs"] for g in group_summaries)),
        "n_selected": int(sum(g["n_selected"] for g in group_summaries)),
    }


def _adj_pair_list(*frames):
    pairs = []
    seen = set()
    for frame in frames:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        for _, row in frame.iterrows():
            pair = (str(row["x"]), str(row["y"]))
            key = tuple(sorted(pair))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(pair)
    return pairs


def _adj_fit_pairwise_regressions(
    df,
    pairs,
    covariates,
    *,
    categorical_set,
    reference_levels,
    alpha,
    max_regressions,
):
    if max_regressions is not None:
        pairs = pairs[:int(max_regressions)]
    coeff_rows, summary_rows = [], []
    for x, y in pairs:
        predictors = _adj_unique([x] + list(covariates))
        try:
            fit, _model_df, formula = _adj_fit_ols(
                df, y, predictors, categorical_set, reference_levels)
            ci = fit.conf_int(alpha=float(alpha))
            for term in fit.params.index:
                low, high = ci.loc[term].tolist()
                coeff_rows.append({
                    "x": x,
                    "y": y,
                    "dependent_variable": y,
                    "primary_predictor": x,
                    "term": str(term),
                    "is_primary_predictor": str(term) == _quote_formula_name(x),
                    "estimate": float(fit.params.loc[term]),
                    "std_error": float(fit.bse.loc[term]),
                    "t_value": float(fit.tvalues.loc[term]),
                    "p_value": float(fit.pvalues.loc[term]),
                    "ci_low": float(low),
                    "ci_high": float(high),
                    "formula": formula,
                    "nobs": float(fit.nobs),
                })
            summary_rows.append({
                "x": x,
                "y": y,
                "formula": formula,
                "nobs": float(fit.nobs),
                "r_squared": float(getattr(fit, "rsquared", np.nan)),
                "adj_r_squared": float(getattr(fit, "rsquared_adj", np.nan)),
                "aic": float(getattr(fit, "aic", np.nan)),
                "bic": float(getattr(fit, "bic", np.nan)),
                "error": "",
            })
        except Exception as exc:
            summary_rows.append({
                "x": x,
                "y": y,
                "formula": "",
                "nobs": 0.0,
                "r_squared": np.nan,
                "adj_r_squared": np.nan,
                "aic": np.nan,
                "bic": np.nan,
                "error": str(exc),
            })

    coefficients = pd.DataFrame(coeff_rows)
    summaries = pd.DataFrame(summary_rows)
    if len(coefficients) > 0:
        coefficients["q_value"] = np.nan
        coefficients["reject_fdr"] = False
        mask = coefficients["term"].astype(str).ne("Intercept") & np.isfinite(
            coefficients["p_value"].astype(float)
        )
        if mask.any():
            from PyFLASH.stats_extra import apply_fdr

            labels = coefficients.index[mask].tolist()
            adjusted = apply_fdr(
                coefficients.loc[mask, "p_value"].tolist(),
                labels=labels,
                alpha=float(alpha),
            )
            for _, row in adjusted.iterrows():
                idx = row["label"]
                coefficients.loc[idx, "q_value"] = float(row["p_adjusted"])
                coefficients.loc[idx, "reject_fdr"] = bool(row["reject"])
    return coefficients, summaries


def adjusted_correlation(
    experiment,
    endpoints=None,
    *,
    filtered_columns=None,
    covariates=None,
    candidate_covariates=None,
    categorical="auto",
    reference_levels=None,
    covariate_gate="fdr",
    covariate_alpha=None,
    min_endpoint_hits=1,
    by="all",
    factor=None,
    specificity=None,
    roi=None,
    save=True,
    column_strings=None,
    regex_string=None,
    exclude="",
    tests=("pearsonr", "spearmanr", "kendalltau"),
    require="and",
    gate="fdr",
    alpha=0.05,
    min_n=3,
    max_adjusted_regressions=None,
    tick_label_size=20,
    plot_pvalue_matrices=True,
    plot_qvalue_matrices=True,
    run_label=None,
    if_exists="overwrite",
    write_manifest=True,
    verbose=True,
):
    """Raw correlation -> covariate screening -> adjusted regression/correlation.

    ``covariates`` are always adjusted for. ``candidate_covariates`` are first
    screened against the endpoint set; promoted candidates are added to the
    adjustment set and removed from the adjusted endpoint matrix when they were
    also listed as endpoints.
    """
    methods = [_normalize_correlation_method(t)
               for t in ([tests] if isinstance(tests, str) else list(tests))]
    if not methods:
        raise ValueError("tests must name at least one correlation method.")
    if str(require).strip().lower() not in {"and", "or"}:
        raise ValueError(f"require must be 'and' or 'or'; got {require!r}.")

    _roi_base = _resolve_roi_bases(roi, experiment)[0]
    scope_df = _filtered_summary_for_specificity(experiment, specificity, roi_base=_roi_base)

    endpoint_spec = endpoints if endpoints is not None else filtered_columns
    initial_endpoints = _resolve_filtered_columns(
        experiment,
        filtered_columns=endpoint_spec,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=exclude,
        source_df=scope_df,
    )
    raw_num_df, raw_valid, raw_dropped = _prepare_matrix_numeric_df(
        scope_df,
        initial_endpoints,
        drop_duplicate_columns=False,
        require_complete_numeric=False,
    )
    initial_endpoints = [col for col in initial_endpoints if col in set(raw_valid)]
    if len(initial_endpoints) < 2:
        raise ValueError(
            "adjusted_correlation needs at least 2 numeric endpoint columns; "
            f"got {len(initial_endpoints)} after filtering."
        )

    always_covariates = _adj_resolve_columns(scope_df, covariates, kind="covariates")
    candidate_covariates = _adj_resolve_columns(
        scope_df, candidate_covariates, kind="candidate_covariates")
    candidate_covariates = [
        col for col in candidate_covariates if col not in set(always_covariates)
    ]
    overlap = sorted(set(initial_endpoints).intersection(always_covariates))
    if overlap:
        raise ValueError(
            "Columns cannot be both endpoints and always covariates. Put these "
            f"in candidate_covariates instead: {', '.join(overlap)}"
        )

    all_adjustment_candidates = _adj_unique(always_covariates + candidate_covariates)
    categorical_set, resolved_refs = _adj_resolve_categorical(
        scope_df,
        _adj_unique(initial_endpoints + all_adjustment_candidates),
        categorical,
        reference_levels,
    )

    screen_alpha = float(alpha if covariate_alpha is None else covariate_alpha)
    screening, promoted = _adj_screen_covariates(
        scope_df,
        initial_endpoints,
        always_covariates,
        candidate_covariates,
        categorical_set=categorical_set,
        reference_levels=resolved_refs,
        alpha=screen_alpha,
        gate=covariate_gate,
        min_endpoint_hits=min_endpoint_hits,
    )
    promoted = _adj_unique(promoted)
    final_covariates = _adj_unique(always_covariates + promoted)
    final_endpoints = [col for col in initial_endpoints if col not in set(promoted)]
    if len(final_endpoints) < 2:
        raise ValueError(
            "Fewer than 2 endpoints remain after promoted candidate covariates "
            f"were removed: {final_endpoints!r}."
        )

    label = run_label or _adj_corr_slug(
        initial_endpoints, always_covariates, candidate_covariates,
        methods, gate, alpha, by, factor,
    )
    fig_dir, data_dir, resolved_label, reuse_existing = _adj_corr_run_dirs(
        experiment, label, if_exists, clear_overwrite=bool(save))
    manifest_path = os.path.join(data_dir, "manifest.json")
    if reuse_existing and _corr_isfile(manifest_path):
        cached = _corr_read_json(manifest_path)
        cached["reused"] = True
        return cached

    residual_df, residual_models = _adj_residualize_endpoints(
        scope_df,
        final_endpoints,
        final_covariates,
        categorical_set=categorical_set,
        reference_levels=resolved_refs,
    )
    adjusted_num_df = residual_df[final_endpoints]

    raw_block = _adj_write_corr_block(
        experiment,
        scope_df,
        raw_num_df[initial_endpoints],
        initial_endpoints,
        methods=methods,
        gate=gate,
        alpha=float(alpha),
        require=require,
        min_n=min_n,
        by=by,
        factor=factor,
        specificity=specificity,
        fig_dir=fig_dir,
        data_dir=data_dir,
        block_name="Raw",
        save=save,
        tick_label_size=tick_label_size,
        plot_pvalue_matrices=plot_pvalue_matrices,
        plot_qvalue_matrices=plot_qvalue_matrices,
    )
    adjusted_pvalue_adjuster = None
    if len(final_covariates) > 0:
        def adjusted_pvalue_adjuster(res, gnum):
            return _adj_apply_partial_pvalues(
                res,
                gnum,
                scope_df,
                final_covariates,
                categorical_set=categorical_set,
                reference_levels=resolved_refs,
                methods=methods,
                gate=gate,
                alpha=float(alpha),
                require=require,
            )

    adjusted_block = _adj_write_corr_block(
        experiment,
        scope_df,
        adjusted_num_df,
        final_endpoints,
        methods=methods,
        gate=gate,
        alpha=float(alpha),
        require=require,
        min_n=min_n,
        by=by,
        factor=factor,
        specificity=specificity,
        fig_dir=fig_dir,
        data_dir=data_dir,
        block_name="Adjusted",
        save=save,
        tick_label_size=tick_label_size,
        plot_pvalue_matrices=plot_pvalue_matrices,
        plot_qvalue_matrices=plot_qvalue_matrices,
        pvalue_adjuster=adjusted_pvalue_adjuster,
    )

    regression_pairs = [
        pair for pair in _adj_pair_list(raw_block["selected"], adjusted_block["selected"])
        if pair[0] in final_endpoints and pair[1] in final_endpoints
    ]
    regression_coeffs, regression_summaries = _adj_fit_pairwise_regressions(
        scope_df,
        regression_pairs,
        final_covariates,
        categorical_set=categorical_set,
        reference_levels=resolved_refs,
        alpha=float(alpha),
        max_regressions=max_adjusted_regressions,
    )

    endpoint_status = pd.DataFrame([
        {
            "endpoint": endpoint,
            "kept_as_endpoint": endpoint in final_endpoints,
            "promoted_to_covariate": endpoint in promoted,
            "dropped_before_raw_correlation": endpoint in raw_dropped,
        }
        for endpoint in _adj_unique(initial_endpoints + list(raw_dropped))
    ])

    if save:
        _corr_makedirs(data_dir)
        _corr_to_csv(screening, os.path.join(data_dir, "covariate_screening.csv"), index=False)
        _corr_to_csv(endpoint_status, os.path.join(data_dir, "endpoint_status.csv"), index=False)
        _corr_to_csv(residual_models, os.path.join(data_dir, "residual_models.csv"), index=False)
        _corr_to_csv(
            regression_coeffs,
            os.path.join(data_dir, "adjusted_regression_coefficients.csv"),
            index=False,
        )
        _corr_to_csv(
            regression_summaries,
            os.path.join(data_dir, "adjusted_regression_summaries.csv"),
            index=False,
        )

    manifest = {
        "run_label": resolved_label,
        "fig_dir": fig_dir,
        "data_dir": data_dir,
        "pipeline": "adjusted_correlation",
        "initial_endpoints": initial_endpoints,
        "final_endpoints": final_endpoints,
        "always_covariates": always_covariates,
        "candidate_covariates": candidate_covariates,
        "promoted_covariates": promoted,
        "final_covariates": final_covariates,
        "categorical": sorted(categorical_set),
        "reference_levels": {str(k): str(v) for k, v in resolved_refs.items()},
        "covariate_gate": str(covariate_gate).lower(),
        "covariate_alpha": screen_alpha,
        "min_endpoint_hits": int(max(1, int(min_endpoint_hits))),
        "tests": [_correlation_display_name(m) for m in methods],
        "require": str(require).lower(),
        "gate": str(gate).lower(),
        "alpha": float(alpha),
        "min_n": int(min_n),
        "by": str(by),
        "factor": factor,
        "specificity": str(specificity) if specificity is not None else None,
        "roi": str(_roi_base) if _roi_base is not None else None,
        "raw": {
            "n_pairs": raw_block["n_pairs"],
            "n_selected": raw_block["n_selected"],
            "groups": raw_block["groups"],
        },
        "adjusted": {
            "n_pairs": adjusted_block["n_pairs"],
            "n_selected": adjusted_block["n_selected"],
            "groups": adjusted_block["groups"],
            "p_value_model": (
                "residual_correlation_with_covariate_df"
                if final_covariates else "ordinary_correlation"
            ),
        },
        "n_adjusted_regressions": int(len(regression_summaries)),
        "reused": False,
    }
    if save and write_manifest:
        _corr_write_json(manifest, manifest_path)

    if verbose:
        _log.confirm(
            f"[adjusted_correlation] {resolved_label}: "
            f"{len(promoted)} promoted covariate(s), "
            f"{len(final_endpoints)} adjusted endpoint(s), "
            f"{adjusted_block['n_selected']} adjusted pair(s) passed."
        )

    result = dict(manifest)
    result["covariate_screening"] = screening
    result["endpoint_status"] = endpoint_status
    result["residual_models"] = residual_models
    result["adjusted_regression_coefficients"] = regression_coeffs
    result["adjusted_regression_summaries"] = regression_summaries
    result["raw"] = dict(result["raw"])
    result["raw"]["pairwise"] = raw_block["pairwise"]
    result["raw"]["selected"] = raw_block["selected"]
    result["adjusted"] = dict(result["adjusted"])
    result["adjusted"]["pairwise"] = adjusted_block["pairwise"]
    result["adjusted"]["selected"] = adjusted_block["selected"]
    return result


