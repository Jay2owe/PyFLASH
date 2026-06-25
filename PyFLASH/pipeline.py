"""Composable high-level PyFLASH analysis pipelines."""

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
    _corr_isdir,
    _corr_isfile,
    _corr_makedirs,
    _corr_windows_extended_path,
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
from PyFLASH.utils import (
    is_excluded_mask,
    is_specificity_queue,
    iter_specificities,
    save_fig,
    specificity_path_parts,
    strip_name,
)
from PyFLASH import pipeline_io as _pio

__all__ = ["correlation", "adjusted_correlation", "data_overview"]


def _pipeline_specificity_suffix(specificity):
    parts = [strip_name(str(part)) for part in specificity_path_parts(specificity)]
    parts = [part for part in parts if part]
    return "_".join(parts) if parts else "specificity"


def _pipeline_child_run_label(run_label, specificity):
    if run_label is None:
        return None
    suffix = _pipeline_specificity_suffix(specificity)
    return f"{run_label}_{suffix}" if suffix else str(run_label)


def _pipeline_specificity_queue(func, experiment, specificity, kwargs, pipeline_name):
    """Run one independent pipeline per specificity filter.

    This mirrors plot-function specificity queue mode, but each child is a full
    pipeline run with its own run label, manifest, matrices, and tables.
    """
    queued_outputs = {}
    child_summaries = []
    base_label = kwargs.get("run_label")
    for spec_tuple in iter_specificities(specificity):
        child_kwargs = dict(kwargs)
        child_kwargs["specificity"] = spec_tuple
        child_kwargs["run_label"] = _pipeline_child_run_label(base_label, spec_tuple)
        result = func(experiment, **child_kwargs)
        queued_outputs[spec_tuple] = result
        child_summaries.append({
            "specificity": tuple(spec_tuple) if spec_tuple is not None else None,
            "run_label": result.get("run_label") if isinstance(result, dict) else None,
            "fig_dir": result.get("fig_dir") if isinstance(result, dict) else None,
            "data_dir": result.get("data_dir") if isinstance(result, dict) else None,
            "n_selected": result.get("n_selected") if isinstance(result, dict) else None,
            "adjusted_n_selected": (
                result.get("adjusted", {}).get("n_selected")
                if isinstance(result, dict) and isinstance(result.get("adjusted"), dict)
                else None
            ),
        })
    return {
        "pipeline": pipeline_name,
        "queued": True,
        "specificity": [tuple(spec) for spec in iter_specificities(specificity)],
        "run_label": base_label,
        "runs": child_summaries,
        "results": queued_outputs,
    }


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

    ``specificity`` follows PyFLASH queue semantics. A single tuple filters one
    run; a list of tuples runs independent child pipelines, one per filter, so
    each child has its own column resolution, FDR correction, regressions, and
    run folder. This is different from ``factor``, which panels groups inside
    one pipeline run.

    Returns a dict with the resolved run label, output directories, per-group
    counts, and the pairwise / selected-pair DataFrames.
    """
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            correlation, experiment, specificity, kwargs, "correlation")

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
    return _pio.run_dirs(experiment, "Adjusted Correlation Pipeline", run_label,
                         if_exists, clear_overwrite=clear_overwrite)


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
    return _pio.slug(f"adjusted_{len(endpoints)}endpoints", payload)


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

    ``specificity`` follows PyFLASH queue semantics. A single tuple filters one
    run; a list of tuples runs independent child pipelines, one per filter, so
    each child has its own covariate screening, residualization, FDR correction,
    and run folder.
    """
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            adjusted_correlation, experiment, specificity, kwargs,
            "adjusted_correlation")

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
        _pio.append_runs_index(experiment, "Adjusted Correlation Pipeline", {
            "run_label": manifest["run_label"],
            "n_initial_endpoints": len(manifest.get("initial_endpoints", [])),
            "n_final_endpoints": len(manifest.get("final_endpoints", [])),
            "n_final_covariates": len(manifest.get("final_covariates", [])),
            "n_promoted_covariates": len(manifest.get("promoted_covariates", [])),
            "tests": "/".join(manifest.get("tests", [])),
            "require": manifest.get("require"),
            "gate": manifest.get("gate"),
            "alpha": manifest.get("alpha"),
            "by": manifest.get("by"),
            "factor": manifest.get("factor"),
            "specificity": manifest.get("specificity"),
            "roi": manifest.get("roi"),
            "raw_n_selected": (manifest.get("raw") or {}).get("n_selected"),
            "adjusted_n_selected": (manifest.get("adjusted") or {}).get("n_selected"),
            "n_adjusted_regressions": manifest.get("n_adjusted_regressions"),
            "fig_dir": manifest["fig_dir"],
        })

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


# ── Data overview pipeline ───────────────────────────────────────────────────
# Identifier/metadata columns that are never treated as analysable metrics
# (mirrors the ``to_drop`` set used when ``experiment.createSummary`` builds the
# per-animal summary).
_OVW_ID_COLS = {
    "Region", "AnimalName", "Condition", "Label", "ImageROI",
    "ROINameRaw", "Hemisphere", "ROI",
}
_OVW_SENTINEL = "NOT_INCLUDED_IN_EXPERIMENT"


def _ovw_run_dirs(experiment, run_label, if_exists, *, clear_overwrite=True):
    return _pio.run_dirs(experiment, "Data Overview Pipeline", run_label,
                         if_exists, clear_overwrite=clear_overwrite)


def _ovw_slug(columns, by, factor, specificity, roi, sections, settings=None):
    payload = {
        "cols": sorted(str(c) for c in columns),
        "by": str(by),
        "factor": str(factor),
        "specificity": str(specificity),
        "roi": str(roi),
        "sections": sorted(str(s) for s in sections),
        # Output-changing knobs, so a different QC configuration hashes to a
        # different folder (otherwise if_exists='skip' could reuse a stale run).
        "settings": {str(k): str(v) for k, v in sorted((settings or {}).items())},
    }
    return _pio.slug(f"overview_{len(columns)}cols", payload)


def _ovw_append_runs_index(experiment, manifest):
    """Append one summary row per overview run to a shared index CSV."""
    counts = manifest.get("inventory_counts", {}) or {}
    # When the inventory section ran, report its (role-based) numeric count so it
    # is consistent with the n_boolean/n_constant columns beside it; only fall
    # back to the broader matrix-numeric count when the inventory was skipped.
    inventory_ran = "inventory" in (manifest.get("sections") or [])
    n_numeric = (counts.get("numeric", 0) if inventory_ran
                 else manifest.get("n_numeric_columns", 0))
    row = {
        "run_label": manifest["run_label"],
        "n_rows": manifest["n_rows"],
        "n_columns": manifest["n_columns"],
        "n_numeric": n_numeric,
        "n_categorical": counts.get("categorical", 0),
        "n_identifier": counts.get("identifier", 0),
        "n_boolean": counts.get("boolean", 0),
        "n_constant": counts.get("constant", 0),
        "n_all_missing": counts.get("all_missing", 0),
        "n_outlier_animals": manifest.get("n_outlier_animals", 0),
        "n_covarying_pairs": manifest.get("n_covarying_pairs", 0),
        "by": manifest["by"],
        "factor": manifest["factor"],
        "specificity": manifest["specificity"],
        "roi": manifest["roi"],
        "fig_dir": manifest["fig_dir"],
    }
    _pio.append_runs_index(experiment, "Data Overview Pipeline", row)


def _ovw_column_inventory(scope_df, columns):
    """Per-column data dictionary: role / dtype / missing / sentinel / unique.

    Classifies every requested column into one of ``numeric``, ``categorical``
    (string), ``boolean``, ``identifier``, ``constant`` (single distinct value),
    or ``all_missing``. NaN ("missing") is counted separately from the
    ``NOT_INCLUDED_IN_EXPERIMENT`` sentinel ("not measured for this animal").
    """
    rows = []
    n_total = int(len(scope_df))
    for col in columns:
        s = scope_df[col]
        sent_mask = s.astype(str).str.contains(_OVW_SENTINEL, na=False)
        excl_mask = is_excluded_mask(s)
        n_excluded = int(excl_mask.sum())
        # not-included sentinel and excluded-outlier token are separate "not a
        # present value" buckets; keep them apart for honest QC accounting.
        sent_mask = sent_mask & ~excl_mask
        n_sentinel = int(sent_mask.sum())
        drop_mask = sent_mask | excl_mask
        non_sent = s.where(~drop_mask, np.nan)
        n_nan = int((non_sent.isna() & ~drop_mask).sum())
        present = non_sent.dropna()
        n_present = int(len(present))
        nunique = int(present.nunique()) if n_present else 0
        coerced = (pd.to_numeric(present, errors="coerce")
                   if n_present else pd.Series([], dtype=float))
        is_numeric = bool(n_present > 0 and coerced.notna().all())
        # Detect booleans from the values too: a bool column carrying a sentinel
        # or NaN degrades to object dtype, which is_bool_dtype would miss.
        is_bool = bool(
            pd.api.types.is_bool_dtype(s)
            or (n_present > 0
                and present.map(lambda v: isinstance(v, (bool, np.bool_))).all()))
        if col in _OVW_ID_COLS:
            role = "identifier"
        elif n_present == 0:
            role = "all_missing"
        elif is_bool:
            role = "boolean"
        elif is_numeric:
            role = "constant" if nunique <= 1 else "numeric"
        else:
            role = "constant" if nunique <= 1 else "categorical"
        examples = ", ".join(str(v) for v in list(present.unique())[:3])
        rows.append({
            "column": col,
            "role": role,
            "dtype": str(s.dtype),
            "n_present": n_present,
            "n_missing": n_nan,
            "n_sentinel": n_sentinel,
            "n_excluded": n_excluded,
            "pct_missing": (round(100.0 * n_nan / n_total, 2)
                            if n_total else np.nan),
            "pct_unavailable": (
                round(100.0 * (n_nan + n_sentinel + n_excluded) / n_total, 2)
                if n_total else np.nan),
            "n_unique": nunique,
            "examples": examples,
        })
    return pd.DataFrame(rows)


def _ovw_group_counts(experiment, scope_df):
    """N animals per condition/factor level (the design table), plus the
    per-level distribution of ``numSections`` (ROI replication) when present."""
    rows = []
    has_animal = "AnimalName" in scope_df.columns
    total = int(scope_df["AnimalName"].nunique()) if has_animal else int(len(scope_df))
    rows.append({"grouping": "(all)", "level": "(total)", "n_animals": total,
                 "sections_min": np.nan, "sections_median": np.nan,
                 "sections_max": np.nan})
    cl = getattr(experiment, "condition_list", None)
    factors = list(getattr(cl, "factor", []) or [])
    group_cols = []
    for c in ["Condition"] + factors:
        if c in scope_df.columns and c not in group_cols:
            group_cols.append(c)
    has_sections = "numSections" in scope_df.columns
    for gc in group_cols:
        for level, sub in scope_df.groupby(gc):
            n = (int(sub["AnimalName"].nunique()) if has_animal else int(len(sub)))
            srow = {"grouping": gc, "level": str(level), "n_animals": n,
                    "sections_min": np.nan, "sections_median": np.nan,
                    "sections_max": np.nan}
            if has_sections:
                sec = pd.to_numeric(sub["numSections"], errors="coerce").dropna()
                if len(sec):
                    srow["sections_min"] = float(sec.min())
                    srow["sections_median"] = float(sec.median())
                    srow["sections_max"] = float(sec.max())
            rows.append(srow)
    return pd.DataFrame(rows)


def _ovw_availability(scope_df, numeric_df, numeric_cols, group_col="Condition"):
    """Per-numeric-column count of non-missing animals within each condition.

    Surfaces markers that were only measured in some conditions (sentinels mean
    a metric can be entirely absent for a group).
    """
    if group_col not in scope_df.columns or not numeric_cols:
        return pd.DataFrame()
    out = {}
    for level, sub in scope_df.groupby(group_col):
        idx = numeric_df.index.intersection(sub.index)
        out[str(level)] = numeric_df.loc[idx, numeric_cols].notna().sum()
    df = pd.DataFrame(out)
    df.index.name = "column"
    return df


def _ovw_descriptives(numeric_df, numeric_cols, groups):
    """Per (group, column) descriptive statistics (reuses report.describe_group)."""
    from PyFLASH import report
    from scipy import stats as sp_stats

    rows = []
    for glabel, gidx, _spec in groups:
        gnum = numeric_df.loc[numeric_df.index.intersection(gidx)]
        for col in numeric_cols:
            vals = gnum[col].dropna()
            rec = report.describe_group(col, vals)
            arr = vals.to_numpy(dtype=float)
            n = int(len(arr))
            mean = rec.get("mean")
            sd = rec.get("sd")
            cv = (abs(sd / mean) * 100.0
                  if (mean not in (None, 0) and sd is not None) else np.nan)
            skew = float(sp_stats.skew(arr)) if n >= 3 else np.nan
            kurt = float(sp_stats.kurtosis(arr)) if n >= 4 else np.nan
            rows.append({
                "group": str(glabel), "column": col, "n": rec.get("n"),
                "mean": mean, "sd": sd, "sem": rec.get("sem"),
                "median": rec.get("median"), "min": rec.get("min"),
                "max": rec.get("max"), "q25": rec.get("q25"), "q75": rec.get("q75"),
                "cv_pct": cv, "skew": skew, "kurtosis": kurt,
            })
    return pd.DataFrame(rows)


def _ovw_normality(numeric_df, numeric_cols, groups, alpha):
    """Per (group, column) Shapiro-Wilk / D'Agostino normality + a test hint."""
    from scipy import stats as sp_stats

    rows = []
    for glabel, gidx, _spec in groups:
        gnum = numeric_df.loc[numeric_df.index.intersection(gidx)]
        for col in numeric_cols:
            arr = gnum[col].dropna().to_numpy(dtype=float)
            n = int(len(arr))
            shapiro_p = np.nan
            dagostino_p = np.nan
            distinct = int(np.unique(arr).size) if n else 0
            if n >= 3 and distinct > 1:
                try:
                    shapiro_p = float(sp_stats.shapiro(arr).pvalue)
                except Exception:
                    pass
            if n >= 8 and distinct > 1:
                try:
                    dagostino_p = float(sp_stats.normaltest(arr).pvalue)
                except Exception:
                    pass
            has_shapiro = bool(np.isfinite(shapiro_p))
            is_normal = bool(has_shapiro and shapiro_p >= float(alpha))
            rows.append({
                "group": str(glabel), "column": col, "n": n,
                "shapiro_p": shapiro_p, "dagostino_p": dagostino_p,
                "is_normal": (is_normal if has_shapiro else None),
                "suggested": ("parametric" if is_normal
                              else ("nonparametric" if has_shapiro
                                    else "insufficient_n")),
            })
    return pd.DataFrame(rows)


def _ovw_outliers(scope_df, numeric_df, numeric_cols, groups,
                  methods, iqr_k, mad_threshold):
    """Flag outliers per (group, column) via :func:`stats_extra.flag_outliers`.

    Tags ``AnimalName`` so a flagged value points straight at the animal, and
    rolls up to a per-animal "flagged on N metrics" candidate-for-review table.
    """
    from PyFLASH.stats_extra import flag_outliers

    group_labels = pd.Series(index=numeric_df.index, dtype=object)
    for glabel, gidx, _spec in groups:
        group_labels.loc[numeric_df.index.intersection(gidx)] = str(glabel)
    flagged = flag_outliers(
        numeric_df, numeric_cols, group_labels=group_labels,
        methods=methods, iqr_k=iqr_k, mad_threshold=mad_threshold)

    name_lookup = scope_df["AnimalName"] if "AnimalName" in scope_df.columns else None

    def _animal(idx):
        if name_lookup is not None:
            try:
                return str(name_lookup.loc[idx])
            except Exception:
                return str(idx)
        return str(idx)

    cols = ["group", "column", "AnimalName", "value", "iqr_outlier",
            "mad_outlier", "modified_z", "iqr_lower", "iqr_upper"]
    if flagged.empty:
        outliers_df = pd.DataFrame(columns=cols)
    else:
        flagged = flagged.assign(AnimalName=flagged["row"].map(_animal))
        outliers_df = flagged[cols].reset_index(drop=True)
    if not outliers_df.empty:
        animals = (
            outliers_df.groupby("AnimalName")
            .agg(n_flags=("column", "size"),
                 n_columns=("column", "nunique"),
                 columns=("column", lambda c: ", ".join(sorted(set(c)))))
            .reset_index()
            .sort_values("n_flags", ascending=False)
            .reset_index(drop=True)
        )
    else:
        animals = pd.DataFrame(
            columns=["AnimalName", "n_flags", "n_columns", "columns"])
    return outliers_df, animals


def _ovw_covariation(numeric_df, numeric_cols, method, threshold, min_n):
    """Pooled pairwise correlation among numeric columns for redundancy screening.

    Returns (covarying_pairs, all_pairs, matrix). ``covarying_pairs`` are the
    pairs at or above ``threshold`` |r| — candidates for collinearity/duplication.
    Unlike the correlation pipeline this is a single-method, no-FDR, no-regression
    QC view; use ``pipeline.correlation`` for inferential work.
    """
    method_n = _normalize_correlation_method(method)
    disp = _correlation_display_name(method_n)
    cols = list(numeric_cols)
    mat = pd.DataFrame(np.nan, index=cols, columns=cols, dtype=float)
    pairs = []
    for i in range(len(cols)):
        mat.loc[cols[i], cols[i]] = 1.0
        for j in range(i + 1, len(cols)):
            a, b = cols[i], cols[j]
            sub = numeric_df[[a, b]].dropna()
            n = int(len(sub))
            if n < int(min_n) or sub[a].nunique() < 2 or sub[b].nunique() < 2:
                continue
            try:
                r, p = _compute_correlation(
                    sub[a].to_numpy(), sub[b].to_numpy(), method_n)
            except Exception:
                continue
            mat.loc[a, b] = r
            mat.loc[b, a] = r
            pairs.append({"x": a, "y": b, "n": n, "r": r,
                          "abs_r": abs(r), "p": p, "method": disp})
    pairs_df = pd.DataFrame(
        pairs, columns=["x", "y", "n", "r", "abs_r", "p", "method"])
    if not pairs_df.empty:
        pairs_df = pairs_df.sort_values(
            "abs_r", ascending=False).reset_index(drop=True)
        covarying = pairs_df[
            pairs_df["abs_r"] >= float(threshold)].reset_index(drop=True)
    else:
        covarying = pairs_df.copy()
    return covarying, pairs_df, mat


def _ovw_missingness_figure(scope_df, columns, tick_label_size, title):
    """Animals x columns map: present / missing (NaN) / not-included (sentinel)."""
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    cols = list(columns)
    n_rows = int(len(scope_df))
    if n_rows == 0 or len(cols) == 0:
        return None
    codes = np.zeros((n_rows, len(cols)), dtype=int)
    for j, col in enumerate(cols):
        s = scope_df[col]
        sent = s.astype(str).str.contains(_OVW_SENTINEL, na=False)
        nan = s.where(~sent, np.nan).isna() & (~sent)
        codes[:, j] = np.where(sent.to_numpy(), 2,
                               np.where(nan.to_numpy(), 1, 0))

    fig_w = min(max(7.0, len(cols) * 0.32), 30.0)
    fig_h = min(max(5.0, n_rows * 0.28), 27.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    cmap = ListedColormap(["#2ca25f", "#bdbdbd", "#fdae61"])
    ax.imshow(codes, aspect="auto", cmap=cmap, vmin=0, vmax=2,
              interpolation="none")
    tick_fs = max(6, min(int(tick_label_size), int(200 / max(len(cols), 1))))
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(
        [str(c)[:28] for c in cols], rotation=90, fontsize=tick_fs)
    if "AnimalName" in scope_df.columns:
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(
            [str(a)[:24] for a in scope_df["AnimalName"]],
            fontsize=max(6, min(int(tick_label_size), int(220 / max(n_rows, 1)))))
    ax.set_title(title, fontsize=int(tick_label_size))
    handles = [
        Patch(color="#2ca25f", label="present"),
        Patch(color="#bdbdbd", label="missing (NaN)"),
        Patch(color="#fdae61", label="not included"),
    ]
    ax.legend(handles=handles, bbox_to_anchor=(1.01, 1.0),
              loc="upper left", fontsize=9, frameon=False)
    fig.tight_layout()
    return fig


def data_overview(
    experiment,
    filtered_columns=None,
    by="all",
    factor=None,
    specificity=None,
    roi=None,
    save=True,
    column_strings=None,
    regex_string=None,
    exclude="",
    include_inventory=True,
    include_group_counts=True,
    include_descriptives=True,
    include_normality=True,
    include_outliers=True,
    include_covariation=True,
    outlier_methods=("iqr", "mad"),
    iqr_k=1.5,
    mad_threshold=3.5,
    covariation_method="pearsonr",
    covariation_threshold=0.9,
    min_n=3,
    alpha=0.05,
    plot_missingness=True,
    plot_covariation=True,
    tick_label_size=20,
    run_label=None,
    if_exists="overwrite",
    write_manifest=True,
    verbose=True,
):
    """One-call descriptive overview / QC report for a batch's summary table.

    A companion to :func:`correlation` / :func:`adjusted_correlation` that answers
    "what does this dataset look like?" before any hypothesis test: the Ns, which
    columns are numeric vs string, what is missing vs not-measured, which animals
    look like outliers, and which metrics covary (collinearity/redundancy).

    Everything is computed on the **animal-level summary** (N = animals), treating
    the ``NOT_INCLUDED_IN_EXPERIMENT`` sentinel as distinct from a true NaN.

    Sections (each toggleable, written as its own CSV)
    -------------------------------------------------
    - ``column_inventory`` — per-column role (numeric / categorical / boolean /
      identifier / constant / all-missing), dtype, present / missing / sentinel
      counts, unique count, and the numeric-vs-string column tally.
    - ``group_counts`` — N animals per condition / factor level (the design
      table) plus per-level ``numSections`` (ROI replication) min/median/max,
      and ``availability_by_condition`` (non-missing animals per metric per
      condition).
    - ``descriptives`` — per (group, column) n / mean / sd / sem / median / IQR /
      CV / skew / kurtosis.
    - ``normality`` — per (group, column) Shapiro-Wilk and D'Agostino with a
      parametric-vs-nonparametric hint.
    - ``outliers`` — Tukey IQR-fence and modified-z (MAD) flags tagged by
      ``AnimalName``, plus a per-animal ``outlier_animals`` roll-up.
    - ``covariation`` — pooled pairwise |r| screen for redundant/collinear
      metrics, with the full ``covariation_matrix``.

    Column selection follows the usual convention: ``filtered_columns`` (explicit
    names) or ``column_strings`` / ``regex_string`` / ``exclude`` (discovery), and
    defaults to *all* summary columns so the inventory is complete. Numeric
    sections operate only on the columns that resolve to numeric values.

    ``by`` / ``factor`` panel the descriptive / normality / outlier sections by
    condition or factor level (``by='all'`` pools); covariation and the inventory
    are always pooled across the scope. ``specificity`` follows PyFLASH queue
    semantics (a list of tuples runs one independent child overview per filter).

    Run management (``run_label`` / ``if_exists`` / ``save`` / ``write_manifest``)
    and the return shape (a manifest dict with the section DataFrames attached)
    mirror the other pipelines. Outputs land in
    ``Python Figures/Data Overview Pipeline/<run>/`` and
    ``Data and Stats/Data Overview Pipeline/<run>/``.
    """
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            data_overview, experiment, specificity, kwargs, "data_overview")

    _roi_base = _resolve_roi_bases(roi, experiment)[0]
    scope_df = _filtered_summary_for_specificity(
        experiment, specificity, roi_base=_roi_base)

    if filtered_columns is None and not column_strings and not regex_string:
        ex = ([exclude] if isinstance(exclude, str) and exclude
              else (list(exclude) if exclude else []))
        resolved_columns = [c for c in scope_df.columns
                            if not any(str(s) in str(c) for s in ex)]
    else:
        resolved_columns = _resolve_filtered_columns(
            experiment, filtered_columns=filtered_columns,
            column_strings=column_strings, regex_string=regex_string,
            exclude=exclude, source_df=scope_df,
        )
    if not resolved_columns:
        raise ValueError("data_overview: no columns matched the filter criteria.")

    num_df, numeric_cols, _dropped = _prepare_matrix_numeric_df(
        scope_df, resolved_columns,
        drop_duplicate_columns=False, require_complete_numeric=False,
    )
    duplicate_columns = []
    if num_df.shape[1] > 1:
        dup_mask = num_df.T.duplicated(keep="first")
        duplicate_columns = num_df.columns[dup_mask].tolist()

    sections = [name for name, on in (
        ("inventory", include_inventory),
        ("group_counts", include_group_counts),
        ("descriptives", include_descriptives),
        ("normality", include_normality),
        ("outliers", include_outliers),
        ("covariation", include_covariation),
    ) if on]

    label = run_label or _ovw_slug(
        resolved_columns, by, factor, specificity, _roi_base, sections,
        settings={
            "outlier_methods": tuple(str(m).lower() for m in (outlier_methods or ())),
            "iqr_k": float(iqr_k),
            "mad_threshold": float(mad_threshold),
            "covariation_method": str(covariation_method),
            "covariation_threshold": float(covariation_threshold),
            "min_n": int(min_n),
            "alpha": float(alpha),
        },
    )
    fig_dir, data_dir, resolved_label, reuse_existing = _ovw_run_dirs(
        experiment, label, if_exists, clear_overwrite=bool(save))
    manifest_path = os.path.join(data_dir, "manifest.json")
    if reuse_existing and _corr_isfile(manifest_path):
        cached = _corr_read_json(manifest_path)
        _log.hint(f"[data_overview] Reusing run {resolved_label!r} (if_exists='skip').")
        cached["reused"] = True
        return cached

    groups = _corr_pipeline_groups(
        experiment, scope_df, num_df, by, factor, specificity)

    # ── compute requested sections ──────────────────────────────────────────
    inventory = pd.DataFrame()
    inventory_counts = {}
    if include_inventory:
        inventory = _ovw_column_inventory(scope_df, resolved_columns)
        if not inventory.empty:
            inventory_counts = inventory["role"].value_counts().to_dict()

    group_counts = pd.DataFrame()
    availability = pd.DataFrame()
    if include_group_counts:
        group_counts = _ovw_group_counts(experiment, scope_df)
        availability = _ovw_availability(scope_df, num_df, numeric_cols)

    descriptives = pd.DataFrame()
    if include_descriptives and numeric_cols:
        descriptives = _ovw_descriptives(num_df, numeric_cols, groups)

    normality = pd.DataFrame()
    if include_normality and numeric_cols:
        normality = _ovw_normality(num_df, numeric_cols, groups, alpha)

    outliers = pd.DataFrame()
    outlier_animals = pd.DataFrame()
    if include_outliers and numeric_cols:
        outliers, outlier_animals = _ovw_outliers(
            scope_df, num_df, numeric_cols, groups,
            outlier_methods, iqr_k, mad_threshold)

    covarying = pd.DataFrame()
    covariation_pairs = pd.DataFrame()
    covariation_matrix = pd.DataFrame()
    if include_covariation and len(numeric_cols) >= 2:
        covarying, covariation_pairs, covariation_matrix = _ovw_covariation(
            num_df, numeric_cols, covariation_method,
            covariation_threshold, min_n)

    # ── write tables + figures ──────────────────────────────────────────────
    if save:
        _corr_makedirs(data_dir)
        if include_inventory and not inventory.empty:
            _corr_to_csv(inventory, os.path.join(data_dir, "column_inventory.csv"),
                         index=False)
        if include_group_counts:
            if not group_counts.empty:
                _corr_to_csv(group_counts,
                             os.path.join(data_dir, "group_counts.csv"), index=False)
            if not availability.empty:
                _corr_to_csv(availability,
                             os.path.join(data_dir, "availability_by_condition.csv"))
        if include_descriptives and not descriptives.empty:
            _corr_to_csv(descriptives,
                         os.path.join(data_dir, "descriptive_stats.csv"), index=False)
        if include_normality and not normality.empty:
            _corr_to_csv(normality, os.path.join(data_dir, "normality.csv"),
                         index=False)
        if include_outliers:
            _corr_to_csv(outliers, os.path.join(data_dir, "outliers.csv"),
                         index=False)
            _corr_to_csv(outlier_animals,
                         os.path.join(data_dir, "outlier_animals.csv"), index=False)
        if include_covariation and not covariation_matrix.empty:
            _corr_to_csv(covarying,
                         os.path.join(data_dir, "covariation_pairs.csv"), index=False)
            _corr_to_csv(covariation_matrix,
                         os.path.join(data_dir, "covariation_matrix.csv"))

        if plot_missingness or plot_covariation:
            _corr_makedirs(fig_dir)
        if plot_missingness:
            mfig = _ovw_missingness_figure(
                scope_df, resolved_columns, tick_label_size,
                "Data availability (animals x columns)")
            if mfig is not None:
                save_fig(mfig, fig_dir, "Missingness Map")
                plt.close(mfig)
        if (plot_covariation and include_covariation
                and not covariation_matrix.empty):
            sig = covariation_matrix.abs() >= float(covariation_threshold)
            cfig = _corr_pipeline_heatmap(
                covariation_matrix, sig,
                f"Covariation matrix  (* |r|>={covariation_threshold:g})",
                tick_label_size, cmap="coolwarm", vmin=-1.0, vmax=1.0,
                colorbar_label=f"{_correlation_display_name(_normalize_correlation_method(covariation_method))} r",
            )
            save_fig(cfig, fig_dir, "Covariation Matrix")
            plt.close(cfig)

    n_outlier_animals = int(len(outlier_animals)) if outlier_animals is not None else 0
    n_covarying_pairs = int(len(covarying)) if covarying is not None else 0

    manifest = {
        "run_label": resolved_label,
        "fig_dir": fig_dir,
        "data_dir": data_dir,
        "pipeline": "data_overview",
        "n_rows": int(len(scope_df)),
        "n_columns": int(len(resolved_columns)),
        "columns": list(resolved_columns),
        "numeric_columns": list(numeric_cols),
        "n_numeric_columns": int(len(numeric_cols)),
        "duplicate_columns": list(duplicate_columns),
        "inventory_counts": {str(k): int(v) for k, v in inventory_counts.items()},
        "sections": sections,
        "by": str(by),
        "factor": factor,
        "groups": [str(g[0]) for g in groups],
        "specificity": str(specificity) if specificity is not None else None,
        "roi": str(_roi_base) if _roi_base is not None else None,
        "outlier_methods": [str(m).lower() for m in (outlier_methods or ())],
        "iqr_k": float(iqr_k),
        "mad_threshold": float(mad_threshold),
        "n_outliers": int(len(outliers)) if outliers is not None else 0,
        "n_outlier_animals": n_outlier_animals,
        "covariation_method": _correlation_display_name(
            _normalize_correlation_method(covariation_method)),
        "covariation_threshold": float(covariation_threshold),
        "n_covarying_pairs": n_covarying_pairs,
        "alpha": float(alpha),
        "reused": False,
    }
    if save and write_manifest:
        _corr_write_json(manifest, manifest_path)
        _ovw_append_runs_index(experiment, manifest)

    if verbose:
        _log.confirm(
            f"[data_overview] {resolved_label}: {manifest['n_columns']} columns "
            f"({manifest['n_numeric_columns']} numeric), "
            f"{manifest['n_rows']} rows, {n_outlier_animals} animals flagged, "
            f"{n_covarying_pairs} covarying pairs."
        )

    result = dict(manifest)
    result["column_inventory"] = inventory
    result["group_counts"] = group_counts
    result["availability_by_condition"] = availability
    result["descriptives"] = descriptives
    result["normality"] = normality
    result["outliers"] = outliers
    result["outlier_animals"] = outlier_animals
    result["covariation"] = covarying
    result["covariation_matrix"] = covariation_matrix
    return result


