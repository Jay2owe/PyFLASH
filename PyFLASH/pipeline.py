"""Composable high-level PyFLASH analysis pipelines."""

import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from PyFLASH._logging import logger as _log
from PyFLASH.modelling import (
    _fit_linear_models,
    _linear_model_reference_value,
    _quote_formula_name,
    _resolve_summary_column,
    _sentinel_like_mask,
    _to_numeric_excluding_not_included,
)
from PyFLASH.plotting import (
    _CORR_PVALUE_CMAP,
    _CORR_QVALUE_CMAP,
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
    _corr_pipeline_slug,
    _corr_pipeline_use_fdr,
    _corr_read_json,
    _corr_resolve_value_matrix_flags,
    _corr_render_matrix_differences,
    _corr_to_csv,
    _corr_value_matrix_label,
    _corr_write_json,
    _correlation_display_name,
    _enrich_df_grouping_columns,
    _filtered_summary_for_specificity,
    _normalize_correlation_method,
    _prepare_matrix_numeric_df,
    _resolve_filtered_columns,
    _resolve_roi_bases,
    plot_regressions,
    # Shared group-comparison plot cores (also the standalone plot_* functions).
    _superplot_figure,
    _effect_forest_figure,
    _stats_matrix_figure,
    _volcano_table_figure,
    _resolve_marker_roi_long,
    _animal_group_map_from_groups,
    _linear_model_adjusted_means_figure,
    _linear_model_coefficient_forest_figure,
    # Rhythm module: standalone plot functions the rhythm pipeline reuses (§8).
    _resolve_rhythm_frame,
    plot_cosinor,
    plot_acrophase_clock,
)
from PyFLASH.utils import (
    build_pipeline_suffix,
    build_specificity_alias,
    filter_df_by_specificity,
    is_excluded_mask,
    is_specificity_queue,
    iter_specificities,
    save_fig,
)
from PyFLASH import pipeline_io as _pio
from PyFLASH.pipeline_montage import capture_secondary, montage_pipeline

__all__ = ["correlation", "adjusted_correlation", "data_overview",
           "group_comparison", "linear_model", "rhythm"]

# ── Overview-montage contract (enforced uniformity for new pipelines) ─────────
# Every pipeline run writes, in addition to its many individual figures, one
# "overview montage": a single contact-sheet PNG of the run's most important
# graphs, sorted to the top of the run's ``fig_dir``. This keeps the package's
# output uniform — whatever pipeline produced a run, the first figure in the
# folder is always the at-a-glance summary.
#
# The format is ENFORCED, not hoped for (mirrors the describe-layer forcing
# function in spec.py). When you add a function to ``__all__``:
#   1. give it a ``montage=True`` parameter (the per-call toggle), and
#   2. wear the ``@montage_pipeline(...)`` decorator, and
#   3. tag its headline ``save_fig(...)`` calls with ``montage=True`` so they
#      land on the montage (everything else is captured as a secondary panel up
#      to a cap — e.g. regression scatter plots).
# Or, if the pipeline genuinely produces no figures to montage, add its name to
# ``MONTAGE_EXEMPT`` below with a reason. ``tests/test_pipeline_montage.py`` fails
# until one of those is true. See ``PyFLASH/pipeline_montage.py`` and CLAUDE.md.
MONTAGE_EXEMPT: set[str] = set()


def _pipeline_specificity_queue(func, experiment, specificity, kwargs, pipeline_name,
                                *, append_index=None):
    """Run a specificity *queue* as one merged run sharing a single folder.

    Mirrors plot-function queue mode: instead of one independent run folder per
    filter, every condition writes into ONE run folder, its figures and tables
    distinguished by a concise specificity tag in the filename (e.g. ``_Dx.AD``).
    This keeps conditions side-by-side and trivially comparable.

    Mechanism: the first condition runs normally and resolves+clears the shared
    run folder; the rest are handed those same dirs via ``_run_dirs`` (no
    re-clear). Every condition runs with ``write_manifest=False`` (writes no
    manifest/index row), ``montage=False`` (so its figures are captured by the
    parent's montage session instead of triggering a per-condition montage), and
    ``_tag_specificity=True`` (so its outputs carry the condition tag). After the
    loop we write ONE combined manifest + ONE runs-index row and return a normal
    (non-queued) result dict, so the ``@montage_pipeline`` decorator builds a
    single overview montage spanning all conditions.
    """
    specs = list(iter_specificities(specificity))
    save = bool(kwargs.get("save", True))
    write_manifest_final = bool(kwargs.get("write_manifest", True))
    aliases = getattr(experiment, "aliases", None)
    defer_corr_regressions = pipeline_name == "correlation"

    # All conditions share one folder, distinguished only by their specificity
    # filename tag. If two conditions sanitise to the same tag (e.g. values that
    # differ only by a character ``strip_name`` deletes, like ``"A-B"`` vs ``"AB"``)
    # the later condition would silently overwrite the earlier one's figures/tables.
    # Fail loudly instead of losing data.
    spec_tags = [build_pipeline_suffix(specificity=spec, aliases=aliases) for spec in specs]
    # Compare on a filesystem-equivalent key: the run folder lives on the user's
    # (case-insensitive) Windows filesystem, so ``_Dx.AD`` and ``_Dx.ad`` collide on
    # disk even though the strings differ. ``normcase`` lowercases on Windows and is
    # a no-op on case-sensitive POSIX (where they are genuinely distinct).
    norm_keys = [os.path.normcase(t) for t in spec_tags]
    dup_tags = sorted({spec_tags[i] for i, k in enumerate(norm_keys)
                       if norm_keys.count(k) > 1})
    if dup_tags:
        raise ValueError(
            f"[{pipeline_name}] specificity queue produces colliding filename "
            f"tag(s) {dup_tags!r} for different conditions, which would overwrite "
            "each other in the shared run folder. Give the conditions distinct "
            "names/aliases so their tags differ.")

    def _len_or_none(value):
        return len(value) if isinstance(value, (list, tuple)) else None

    child_results = []
    conditions = []
    shared = None  # (fig_dir, data_dir, run_label) resolved by the first condition
    for spec in specs:
        child_kwargs = dict(kwargs)
        child_kwargs["specificity"] = spec
        # The shared folder is auto-named (run_label=None) from the *first* child's
        # slug; feed it the whole queue so two queues that share a first condition
        # but differ later still resolve to distinct folders.
        child_kwargs["_slug_specificity"] = specs
        child_kwargs["write_manifest"] = False
        child_kwargs["montage"] = False
        child_kwargs["_tag_specificity"] = True
        if defer_corr_regressions:
            child_kwargs["max_regressions"] = 0
        if shared is not None:
            child_kwargs["_run_dirs"] = shared
        result = func(experiment, **child_kwargs)
        rd = result if isinstance(result, dict) else {}
        if shared is None and rd.get("reused"):
            # First condition reused an existing run (if_exists='skip'); honour skip
            # for the whole queue rather than recomputing the rest into its folder.
            return result
        child_results.append(result)
        if shared is None and rd:
            shared = (rd.get("fig_dir"), rd.get("data_dir"), rd.get("run_label"))
        cond = {
            "specificity": list(spec) if spec is not None else None,
            "spec_tag": build_specificity_alias(spec, aliases),
            "run_label": rd.get("run_label"),
            "n_rows": rd.get("n_rows"),
            "n_pairs": rd.get("n_pairs"),
            "n_selected": rd.get("n_selected"),
            "adjusted_n_selected": (
                (rd.get("adjusted") or {}).get("n_selected")
                if isinstance(rd.get("adjusted"), dict) else None),
        }
        # Adjusted-correlation covariate screening can differ by condition; record
        # the per-condition outcome here (the combined manifest's top-level covariate
        # lists are only the first condition's, so this is the queue-level truth).
        if "final_endpoints" in rd or "final_covariates" in rd:
            cond.update({
                "n_final_endpoints": _len_or_none(rd.get("final_endpoints")),
                "n_final_covariates": _len_or_none(rd.get("final_covariates")),
                "n_promoted_covariates": _len_or_none(rd.get("promoted_covariates")),
            })
        # data_overview column roles (numeric/constant/all_missing/...) are scoped to
        # each condition's filtered rows, so they can differ by condition. Record the
        # per-condition truth here (the combined manifest's top-level inventory is
        # only the first condition's; the per-condition column_inventory_<tag>.csv
        # files hold the full breakdown).
        if "inventory_counts" in rd or "n_numeric_columns" in rd:
            cond.update({
                "n_numeric_columns": rd.get("n_numeric_columns"),
                "inventory_counts": rd.get("inventory_counts"),
            })
        conditions.append(cond)

    fig_dir, data_dir, resolved_label = shared or (None, None, kwargs.get("run_label"))
    # Use the first condition's manifest as a structural template (it carries the
    # pipeline-specific, condition-invariant keys like columns/tests/inventory
    # counts), then strip heavy DataFrames so the combined manifest stays a light,
    # JSON-clean summary; ``conditions`` is the per-condition source of truth.
    template = child_results[0] if child_results and isinstance(child_results[0], dict) else {}
    combined = {k: v for k, v in template.items() if not isinstance(v, pd.DataFrame)}
    for blk in ("raw", "adjusted"):
        if isinstance(combined.get(blk), dict):
            combined[blk] = {k: v for k, v in combined[blk].items()
                             if not isinstance(v, pd.DataFrame)}
    # Drop first-condition-only per-group / per-pair detail: ``conditions`` is the
    # per-condition source of truth, and leaving these would sit inconsistently
    # beside the queue-total scalar counts below (``report.render_digest`` reads
    # ``groups`` / ``selected_pairs``).
    for k in ("groups", "selected_pairs", "plotted_pairs"):
        combined.pop(k, None)
    for blk in ("raw", "adjusted"):
        if isinstance(combined.get(blk), dict):
            combined[blk].pop("groups", None)
    combined.update({
        "pipeline": pipeline_name,
        "run_label": resolved_label,
        "fig_dir": fig_dir,
        "data_dir": data_dir,
        "specificity": [list(s) if s is not None else None for s in specs],
        "conditions": conditions,
        "n_conditions": len(specs),
        "reused": False,
    })

    # Replace condition-varying scalar counts with totals across all conditions, so
    # the one combined manifest + runs-index row aren't silently first-condition
    # values. Condition-invariant fields (columns, tests, inventory counts) keep the
    # template value. ``conditions`` carries the per-condition breakdown.
    def _sum_across(getter):
        vals = [getter(r) for r in child_results if isinstance(r, dict)]
        nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return sum(nums) if nums and len(nums) == len(child_results) else None

    for key in ("n_rows", "n_pairs", "n_selected", "n_regressions",
                "n_adjusted_regressions", "n_outlier_animals", "n_outliers",
                "n_covarying_pairs", "n_effect_sizes", "n_condition_distribution_rows",
                "n_tests", "n_significant", "n_fallback_markers", "n_skipped_markers",
                "n_models", "n_adjusted_means"):
        if key in combined:
            combined[key] = _sum_across(lambda r, k=key: r.get(k))
    for blk in ("raw", "adjusted"):
        if isinstance(combined.get(blk), dict):
            for key in ("n_pairs", "n_selected"):
                if key in combined[blk]:
                    combined[blk][key] = _sum_across(
                        lambda r, b=blk, k=key: (r.get(b) or {}).get(k))
    # Matrix-difference counts also sum across conditions.
    if isinstance(combined.get("difference_matrices"), dict):
        for key in ("n_comparisons", "n_difference_tests", "n_difference_significant"):
            if key in combined["difference_matrices"]:
                combined["difference_matrices"][key] = _sum_across(
                    lambda r, k=key: (r.get("difference_matrices") or {}).get(k))

    if defer_corr_regressions:
        plotted_pairs = _corr_queue_plot_regressions(
            experiment, child_results, specs, kwargs, fig_dir)
        combined["plotted_pairs"] = plotted_pairs
        combined["n_regressions"] = len(plotted_pairs)

    if save and write_manifest_final and data_dir:
        _pio.write_json(combined, os.path.join(data_dir, "manifest.json"))
        if append_index is not None:
            try:
                append_index(experiment, combined)
            except Exception as exc:  # never let index bookkeeping break a run
                _log.warn(f"[{pipeline_name}] queue runs-index update failed: {exc}")
    return combined


@montage_pipeline(title="Correlation Pipeline")
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
    gate="p",
    alpha=0.05,
    min_n=3,
    max_regressions=12,
    regression_factor=None,
    regression_test="pearsonr",
    regression_combine=True,
    normalize_x=False,
    normalize_y=False,
    tick_label_size=20,
    value_matrices="p",
    plot_pvalue_matrices=None,
    plot_qvalue_matrices=None,
    plot_difference_matrices=False,
    difference_comparisons=None,
    difference_gate=None,
    difference_alpha=None,
    difference_test="fisher_z",
    plot_difference_signed=True,
    plot_difference_absolute=True,
    plot_difference_pvalue_matrices=True,
    plot_difference_qvalue_matrices=False,
    plot_difference_gate_matrix=True,
    run_label=None,
    if_exists="overwrite",
    write_manifest=True,
    montage=True,
    _run_dirs=None,
    _tag_specificity=False,
    _slug_specificity=None,
):
    """Correlation discovery -> significance gate -> regression plots, in one run.

    Phase 1 builds one full correlation matrix per method in ``tests`` over the
    chosen columns. Phase 2 corrects p-values (Benjamini-Hochberg) and keeps the
    metric pairs that pass the gate, combining the methods with ``require``
    ('and' / 'or') on either raw p-values (``gate='p'``, default) or FDR q-values
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
    p-value matrices for each correlation method, alongside the coefficient
    matrices and the combined gate matrix. Set ``value_matrices='q'`` or
    ``value_matrices='both'`` to save FDR q-value heatmaps; both p-value and
    q-value CSV tables are always written. The older
    ``plot_pvalue_matrices`` / ``plot_qvalue_matrices`` booleans still work and
    override ``value_matrices`` when supplied. Asterisks on coefficient matrices
    always mark raw p-value significance; q-values remain visible in the
    dedicated FDR q-value matrices and in the gate matrix when ``gate='fdr'``.

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

    - ``Python Figures/Correlation Pipeline/<run>/`` - the matrices,
      regression plots, ``pairwise_correlations.csv`` (r/p/q/significance per
      method), ``selected_pairs.csv``, per-method matrix CSVs, and
      ``manifest.json``.
    - ``Python Figures/Correlation Pipeline/_runs_index.csv`` - one row per run
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
    run; a list of tuples runs every filter into ONE shared run folder, each
    condition's matrices/tables/regressions distinguished by a concise specificity
    tag in the filename (e.g. ``_Dx.AD``), with one combined overview montage. This
    is different from ``factor``, which panels groups inside one run (the group is
    likewise encoded into the filename, e.g. ``_GT.WT``).

    Returns a dict with the resolved run label, output directories, per-group
    counts, and the pairwise / selected-pair DataFrames.
    """
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            correlation, experiment, specificity, kwargs, "correlation",
            append_index=_corr_pipeline_append_runs_index)

    methods = [_normalize_correlation_method(t)
               for t in ([tests] if isinstance(tests, str) else list(tests))]
    if not methods:
        raise ValueError("tests must name at least one correlation method.")
    if str(require).strip().lower() not in ("and", "or"):
        raise ValueError(f"require must be 'and' or 'or'; got {require!r}.")
    plot_pvalue_matrices, plot_qvalue_matrices = _corr_resolve_value_matrix_flags(
        value_matrices, plot_pvalue_matrices, plot_qvalue_matrices)
    value_matrices_label = _corr_value_matrix_label(
        plot_pvalue_matrices, plot_qvalue_matrices)
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

    # Run folder resolution. In queue-merge mode ``_slug_specificity`` is the full
    # queue, so the auto-named shared folder is unique to the whole queue (not just
    # this first condition).
    label = run_label or _corr_pipeline_slug(
        slug_cols, against_resolved, methods, require, gate, alpha,
        by, factor,
        (_slug_specificity if _slug_specificity is not None else specificity),
        _roi_base,
        settings={
            "min_n": int(min_n),
            "max_regressions": max_regressions,
            "regression_factor": regression_factor,
            "regression_test": str(regression_test),
            "regression_combine": bool(regression_combine),
            "normalize_x": bool(normalize_x),
            "normalize_y": bool(normalize_y),
            "value_matrices": value_matrices_label,
            "plot_difference_matrices": bool(plot_difference_matrices),
            "difference_comparisons": difference_comparisons,
            "difference_gate": difference_gate,
            "difference_alpha": difference_alpha,
            "difference_test": str(difference_test),
        },
    )
    if _run_dirs is not None:
        # Queue-merge: a sibling condition already resolved+cleared the shared
        # run folder; reuse it so all conditions land together (see
        # _pipeline_specificity_queue).
        fig_dir, data_dir, resolved_label = _run_dirs
        reuse_existing = False
    else:
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
    # Group identity is encoded into the output filename (e.g. ``_GT.WT``) rather
    # than a per-group folder, so every group's matrices/tables sit flat in one
    # ``Matrices/`` folder / run data dir and stay trivially comparable. In
    # queue-merge mode the per-condition specificity is also woven into the name
    # (``_GT.WT_Dx.AD``) so conditions sharing the folder never collide.
    group_key = factor if factor else (
        "Condition" if str(by).strip().lower() == "conditions" else None)
    aliases = getattr(experiment, "aliases", None)
    spec_for_filename = specificity if _tag_specificity else None
    spec_tag = build_pipeline_suffix(specificity=spec_for_filename, aliases=aliases)
    reg_by, reg_factor, reg_specificity = _corr_regression_scope(
        by, factor, specificity, regression_factor,
        slug_specificity=_slug_specificity,
    )

    combined_long, combined_selected, group_summaries, plotted_pairs = [], [], [], []
    groups_results = []
    first_long = first_selected = None

    for gi, (glabel, gidx, _greg_spec) in enumerate(groups):
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

        tag = build_pipeline_suffix(
            group=(None if single else glabel),
            group_key=(None if single else group_key),
            specificity=spec_for_filename,
            aliases=aliases,
        )

        if save:
            matrices_data_dir = os.path.join(data_dir, "Matrices")
            _corr_to_csv(res["long"], os.path.join(data_dir, f"pairwise_correlations{tag}.csv"), index=False)
            _corr_to_csv(res["selected"], os.path.join(data_dir, f"selected_pairs{tag}.csv"), index=False)
            for m in methods:
                disp = _correlation_display_name(m)
                _corr_to_csv(res["coef"][m], os.path.join(matrices_data_dir, f"coef_{disp}{tag}.csv"))
                _corr_to_csv(res["p"][m], os.path.join(matrices_data_dir, f"pvalues_{disp}{tag}.csv"))
                _corr_to_csv(res["q"][m], os.path.join(matrices_data_dir, f"qvalues_{disp}{tag}.csv"))
            _corr_to_csv(res["gate"].astype(int), os.path.join(matrices_data_dir, f"gate_matrix{tag}.csv"))

            star = "p<%g" % alpha
            suffix = "" if single else f" - {glabel}"
            for m in methods:
                disp = _correlation_display_name(m)
                fig = _corr_pipeline_heatmap(
                    res["coef"][m], None,
                    f"{disp} Correlation Matrix{suffix}  (* {star})",
                    tick_label_size,
                    cmap="coolwarm", vmin=-1.0, vmax=1.0,
                    colorbar_label=f"{disp} coefficient",
                    annotation_df=res["p"][m],
                    annotation_alpha=alpha,
                )
                save_fig(fig, fig_dir, f"{disp} Correlation Matrix{tag}",
                         subfolder="Matrices", montage=True)
                plt.close(fig)
                if plot_pvalue_matrices:
                    pfig = _corr_pipeline_heatmap(
                        res["p"][m], None,
                        f"{disp} P-Value Matrix{suffix}  (* p<{alpha:g})",
                        tick_label_size,
                        cmap=_CORR_PVALUE_CMAP, vmin=0.0, vmax=1.0,
                        colorbar_label="raw p value",
                        annotation_df=res["p"][m],
                        annotation_alpha=alpha,
                    )
                    save_fig(pfig, fig_dir, f"{disp} P-Value Matrix{tag}", subfolder="Matrices")
                    plt.close(pfig)
                if plot_qvalue_matrices:
                    qfig = _corr_pipeline_heatmap(
                        res["q"][m], None,
                        f"{disp} FDR Q-Value Matrix{suffix}  (* q<{alpha:g})",
                        tick_label_size,
                        cmap=_CORR_QVALUE_CMAP, vmin=0.0, vmax=1.0,
                        colorbar_label="FDR q value",
                        annotation_df=res["q"][m],
                        annotation_alpha=alpha,
                    )
                    save_fig(qfig, fig_dir, f"{disp} FDR Q-Value Matrix{tag}", subfolder="Matrices")
                    plt.close(qfig)
            gate_ttl = (f"Pairs passing gate{suffix}\n{require.upper()} of "
                        + "/".join(_correlation_display_name(m) for m in methods)
                        + f" @ {'q' if use_fdr else 'p'}<{alpha}")
            gfig = _corr_pipeline_heatmap(
                res["gate"].astype(float), res["gate"], gate_ttl, tick_label_size,
                cmap="Reds", vmin=0.0, vmax=1.0,
                colorbar_label="passes gate",
            )
            save_fig(gfig, fig_dir, f"Gate Passing Matrix{tag}",
                     subfolder="Matrices", montage=True)
            plt.close(gfig)

        sel = res["selected"]
        group_summaries.append({
            "group": str(glabel), "n_rows": int(len(gnum)),
            "n_pairs": int(len(res["pairs"])), "n_selected": int(len(sel)),
            "n_regressions": 0,
        })

    long_all = pd.concat(combined_long, ignore_index=True) if combined_long else pd.DataFrame()
    selected_all = pd.concat(combined_selected, ignore_index=True) if combined_selected else pd.DataFrame()
    if save and not single:
        _corr_to_csv(long_all, os.path.join(data_dir, f"pairwise_correlations{spec_tag}.csv"), index=False)
        _corr_to_csv(selected_all, os.path.join(data_dir, f"selected_pairs{spec_tag}.csv"), index=False)

    # Regressions for surviving pairs (redirect output into the run folder).
    # By default, the line grouping follows the matrix grouping: factor-grouped
    # matrices get factor lines, condition-grouped matrices get condition lines,
    # and same-column specificity queues get one line per queued value.
    plot_selected = _corr_selected_for_regression(selected_all, max_regressions)
    reg_fig_root = fig_dir
    orig_fig_path = getattr(experiment, "fig_path", None)
    with capture_secondary("regression"):
        for _, prow in plot_selected.iterrows():
            x, y = prow["x"], prow["y"]
            try:
                experiment.fig_path = reg_fig_root
                plot_regressions(
                    experiment, x=x, y=y, by=reg_by, factor=reg_factor,
                    test=regression_test, normalize_x=normalize_x, normalize_y=normalize_y,
                    specificity=reg_specificity, roi=_roi_base, save=save,
                    combine=regression_combine,
                )
                plotted_pairs.append({
                    "x": x, "y": y,
                    "group": None,
                    "regression_factor": reg_factor,
                    "median_abs_r": float(prow.get("median_abs_r", np.nan)),
                })
            except Exception as exc:
                _log.warn(f"[correlation_pipeline] Regression {x} vs {y} failed: {exc}")
            finally:
                if orig_fig_path is not None:
                    experiment.fig_path = orig_fig_path

    plotted_pair_keys = {(str(p["x"]), str(p["y"])) for p in plotted_pairs}
    if plotted_pair_keys:
        for summary in group_summaries:
            if "group" in selected_all.columns:
                subset = selected_all[
                    selected_all["group"].astype(str).eq(str(summary["group"]))
                ]
            else:
                subset = selected_all
            group_pairs = {
                (str(row["x"]), str(row["y"]))
                for _, row in subset.iterrows()
            }
            summary["n_regressions"] = len(group_pairs.intersection(plotted_pair_keys))

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
            name_suffix=spec_tag,
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
        "value_matrices": value_matrices_label,
        "plot_pvalue_matrices": bool(plot_pvalue_matrices),
        "plot_qvalue_matrices": bool(plot_qvalue_matrices),
        "coefficient_matrix_star_source": "raw_p_value",
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


def _corr_queue_specificity_scope(specificity):
    """Return one union specificity for a same-column specificity queue."""
    if not is_specificity_queue(specificity):
        return None
    specs = list(iter_specificities(specificity))
    if not specs:
        return None
    key = specs[0][0]
    values = []
    for spec in specs:
        if len(spec) < 2 or str(spec[0]) != str(key):
            return None
        for value in spec[1:]:
            if isinstance(value, (list, tuple, set, pd.Index, np.ndarray, pd.Series)):
                values.extend(list(value))
            else:
                values.append(value)
    if not values:
        return None
    return (key, values)


def _corr_regression_scope(by, factor, specificity, regression_factor,
                           slug_specificity=None):
    """Resolve regression grouping to match the matrix grouping by default."""
    queue_scope = _corr_queue_specificity_scope(slug_specificity)
    scope_specificity = queue_scope if queue_scope is not None else specificity
    if regression_factor is not None:
        return by, regression_factor, scope_specificity
    if factor is not None:
        return by, factor, scope_specificity
    if str(by).strip().lower() == "conditions":
        return "conditions", None, scope_specificity
    if queue_scope is not None:
        return by, queue_scope[0], queue_scope
    return "conditions", None, scope_specificity


def _corr_selected_for_regression(selected, max_regressions):
    """Deduplicate selected pairs before drawing pipeline regression figures."""
    if not isinstance(selected, pd.DataFrame) or selected.empty:
        return pd.DataFrame(columns=["x", "y", "median_abs_r"])
    if "x" not in selected.columns or "y" not in selected.columns:
        return pd.DataFrame(columns=["x", "y", "median_abs_r"])
    rows = selected.copy()
    if "median_abs_r" not in rows.columns:
        rows["median_abs_r"] = np.nan
    rows["_pair_key"] = list(zip(rows["x"].astype(str), rows["y"].astype(str)))
    rows["_row_order"] = np.arange(len(rows))
    rows["_sort_score"] = pd.to_numeric(rows["median_abs_r"], errors="coerce")
    rows = (
        rows.sort_values(
            ["_sort_score", "_row_order"],
            ascending=[False, True],
            na_position="last",
        )
        .drop_duplicates("_pair_key", keep="first")
        .drop(columns=["_pair_key", "_row_order", "_sort_score"])
        .reset_index(drop=True)
    )
    if max_regressions is not None:
        rows = rows.head(int(max_regressions))
    return rows


def _corr_queue_plot_regressions(experiment, child_results, specs, kwargs, fig_dir):
    selected_frames = []
    for result in child_results:
        if not isinstance(result, dict):
            continue
        selected = result.get("selected")
        if isinstance(selected, pd.DataFrame) and not selected.empty:
            selected_frames.append(selected)
    selected_all = (
        pd.concat(selected_frames, ignore_index=True)
        if selected_frames else pd.DataFrame()
    )
    plot_selected = _corr_selected_for_regression(
        selected_all, kwargs.get("max_regressions"))
    if plot_selected.empty:
        return []

    reg_by, reg_factor, reg_specificity = _corr_regression_scope(
        kwargs.get("by", "all"),
        kwargs.get("factor"),
        None,
        kwargs.get("regression_factor"),
        slug_specificity=specs,
    )
    roi_base = _resolve_roi_bases(kwargs.get("roi"), experiment)[0]
    save = bool(kwargs.get("save", True))
    orig_fig_path = getattr(experiment, "fig_path", None)
    plotted_pairs = []
    with capture_secondary("regression"):
        for _, row in plot_selected.iterrows():
            x, y = row["x"], row["y"]
            try:
                experiment.fig_path = fig_dir
                plot_regressions(
                    experiment,
                    x=x,
                    y=y,
                    by=reg_by,
                    factor=reg_factor,
                    test=kwargs.get("regression_test", "pearsonr"),
                    normalize_x=kwargs.get("normalize_x", False),
                    normalize_y=kwargs.get("normalize_y", False),
                    specificity=reg_specificity,
                    roi=roi_base,
                    save=save,
                    combine=kwargs.get("regression_combine", True),
                )
                plotted_pairs.append({
                    "x": x,
                    "y": y,
                    "group": None,
                    "regression_factor": reg_factor,
                    "median_abs_r": float(row.get("median_abs_r", np.nan)),
                })
            except Exception as exc:
                _log.warn(f"[correlation_pipeline] Regression {x} vs {y} failed: {exc}")
            finally:
                if orig_fig_path is not None:
                    experiment.fig_path = orig_fig_path
    return plotted_pairs


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


def _adj_auto_is_categorical(series):
    """Auto-detect a categorical column, ignoring sentinel / EXCLUDED_ cells.

    A numeric column that only became ``object`` dtype because it holds a
    not-included sentinel or an ``EXCLUDED_`` exclusion token must NOT be treated
    as categorical — its non-sentinel values are numbers. Genuine string/boolean
    columns still classify as categorical.
    """
    if pd.api.types.is_bool_dtype(series) or isinstance(series.dtype, pd.CategoricalDtype):
        return True
    if not pd.api.types.is_object_dtype(series):
        return False
    raw = pd.Series(series)
    # Judge on genuine values only: ignore sentinel/EXCLUDED_ cells AND true NaNs
    # (a numeric column may legitimately have both).
    present = raw[~_sentinel_like_mask(raw)].dropna()
    if len(present) == 0:
        return False
    # An object-dtype boolean (degraded by a sentinel) is categorical.
    if present.map(lambda v: isinstance(v, (bool, np.bool_))).all():
        return True
    coerced = pd.to_numeric(present, errors="coerce")
    # Categorical only if a genuine value is non-numeric.
    return bool(coerced.isna().any())


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
            if col in df.columns and _adj_auto_is_categorical(df[col])
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
            # Drop both the not-included sentinel and EXCLUDED_ tokens so neither
            # becomes a spurious category level.
            sentinel = _sentinel_like_mask(raw)
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


def _adj_corr_append_runs_index(experiment, manifest):
    """Append one summary row per adjusted-correlation run to its shared index."""
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


def _adj_corr_slug(endpoints, covariates, candidates, methods, gate, alpha, by,
                   factor, settings=None):
    payload = {
        "endpoints": sorted(str(c) for c in endpoints),
        "covariates": sorted(str(c) for c in covariates),
        "candidates": sorted(str(c) for c in candidates),
        "methods": list(methods),
        "gate": str(gate).lower(),
        "alpha": float(alpha),
        "by": str(by),
        "factor": str(factor),
        # Output-changing knobs, so a materially different run hashes to a
        # different folder (otherwise if_exists='skip' could reuse a stale run).
        # pipeline_io.slug canonicalises dict/set order for a stable hash.
        "settings": settings or {},
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
    filename_spec=None,
):
    groups = _corr_pipeline_groups(experiment, scope_df, num_df, by, factor, specificity)
    single = len(groups) == 1
    combined_long, combined_selected, group_summaries = [], [], []
    use_fdr = _corr_pipeline_use_fdr(gate)
    # Block (Raw/Adjusted) + group identity ride in the filename (e.g.
    # ``--Adjusted--GT.WT``) so every block/group's matrices sit flat in one
    # ``Matrices/`` folder / run data dir instead of nested block/group folders.
    group_key = factor if factor else (
        "Condition" if str(by).strip().lower() == "conditions" else None)
    aliases = getattr(experiment, "aliases", None)

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

        tag = build_pipeline_suffix(
            block=block_name,
            group=(None if single else glabel),
            group_key=(None if single else group_key),
            specificity=filename_spec,
            aliases=aliases,
        )
        if save:
            matrices_data_dir = os.path.join(data_dir, "Matrices")
            _corr_to_csv(res["long"], os.path.join(data_dir, f"pairwise_correlations{tag}.csv"), index=False)
            _corr_to_csv(res["selected"], os.path.join(data_dir, f"selected_pairs{tag}.csv"), index=False)
            for method in methods:
                disp = _correlation_display_name(method)
                _corr_to_csv(res["coef"][method], os.path.join(matrices_data_dir, f"coef_{disp}{tag}.csv"))
                _corr_to_csv(res["p"][method], os.path.join(matrices_data_dir, f"pvalues_{disp}{tag}.csv"))
                _corr_to_csv(res["q"][method], os.path.join(matrices_data_dir, f"qvalues_{disp}{tag}.csv"))
                suffix = "" if single else f" - {glabel}"
                star = "p<%g" % alpha
                fig = _corr_pipeline_heatmap(
                    res["coef"][method], None,
                    f"{block_name} {disp} Correlation Matrix{suffix}  (* {star})",
                    tick_label_size,
                    cmap="coolwarm", vmin=-1.0, vmax=1.0,
                    colorbar_label=f"{disp} coefficient",
                    annotation_df=res["p"][method],
                    annotation_alpha=alpha,
                )
                save_fig(fig, fig_dir, f"{disp} Correlation Matrix{tag}",
                         subfolder="Matrices", montage=True)
                plt.close(fig)
                if plot_pvalue_matrices:
                    pfig = _corr_pipeline_heatmap(
                        res["p"][method], None,
                        f"{block_name} {disp} P-Value Matrix{suffix}  (* p<{alpha:g})",
                        tick_label_size,
                        cmap=_CORR_PVALUE_CMAP, vmin=0.0, vmax=1.0,
                        colorbar_label="raw p value",
                        annotation_df=res["p"][method],
                        annotation_alpha=alpha,
                    )
                    save_fig(pfig, fig_dir, f"{disp} P-Value Matrix{tag}", subfolder="Matrices")
                    plt.close(pfig)
                if plot_qvalue_matrices:
                    qfig = _corr_pipeline_heatmap(
                        res["q"][method], None,
                        f"{block_name} {disp} FDR Q-Value Matrix{suffix}  (* q<{alpha:g})",
                        tick_label_size,
                        cmap=_CORR_QVALUE_CMAP, vmin=0.0, vmax=1.0,
                        colorbar_label="FDR q value",
                        annotation_df=res["q"][method],
                        annotation_alpha=alpha,
                    )
                    save_fig(qfig, fig_dir, f"{disp} FDR Q-Value Matrix{tag}", subfolder="Matrices")
                    plt.close(qfig)
            _corr_to_csv(res["gate"].astype(int), os.path.join(matrices_data_dir, f"gate_matrix{tag}.csv"))
            gate_ttl = (f"{block_name} pairs passing gate{suffix}\n{str(require).upper()} of "
                        + "/".join(_correlation_display_name(m) for m in methods)
                        + f" @ {'q' if use_fdr else 'p'}<{alpha:g}")
            gfig = _corr_pipeline_heatmap(
                res["gate"].astype(float), res["gate"], gate_ttl, tick_label_size,
                cmap="Reds", vmin=0.0, vmax=1.0,
                colorbar_label="passes gate",
            )
            save_fig(gfig, fig_dir, f"Gate Passing Matrix{tag}",
                     subfolder="Matrices", montage=True)
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
        block_tag = build_pipeline_suffix(block=block_name, specificity=filename_spec, aliases=aliases)
        _corr_to_csv(long_all, os.path.join(data_dir, f"pairwise_correlations{block_tag}.csv"), index=False)
        _corr_to_csv(selected_all, os.path.join(data_dir, f"selected_pairs{block_tag}.csv"), index=False)
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


@montage_pipeline(title="Adjusted Correlation Pipeline")
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
    gate="p",
    alpha=0.05,
    min_n=3,
    max_adjusted_regressions=None,
    tick_label_size=20,
    value_matrices="p",
    plot_pvalue_matrices=None,
    plot_qvalue_matrices=None,
    run_label=None,
    if_exists="overwrite",
    write_manifest=True,
    verbose=True,
    montage=True,
    _run_dirs=None,
    _tag_specificity=False,
    _slug_specificity=None,
):
    """Raw correlation -> covariate screening -> adjusted regression/correlation.

    ``covariates`` are always adjusted for. ``candidate_covariates`` are first
    screened against the endpoint set; promoted candidates are added to the
    adjustment set and removed from the adjusted endpoint matrix when they were
    also listed as endpoints.

    ``specificity`` follows PyFLASH queue semantics. A single tuple filters one
    run; a list of tuples runs every filter into ONE shared run folder, each
    condition's matrices/tables distinguished by a concise specificity tag in the
    filename (e.g. ``_Dx.AD``), with one combined overview montage. Matrix heatmaps
    default to raw p-values; set ``value_matrices='q'`` or ``value_matrices='both'``
    to save FDR q-value heatmaps too. The p-value and q-value CSV tables are always
    written. Asterisks on coefficient matrices always mark raw p-value significance.
    """
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            adjusted_correlation, experiment, specificity, kwargs,
            "adjusted_correlation", append_index=_adj_corr_append_runs_index)

    methods = [_normalize_correlation_method(t)
               for t in ([tests] if isinstance(tests, str) else list(tests))]
    if not methods:
        raise ValueError("tests must name at least one correlation method.")
    if str(require).strip().lower() not in {"and", "or"}:
        raise ValueError(f"require must be 'and' or 'or'; got {require!r}.")
    plot_pvalue_matrices, plot_qvalue_matrices = _corr_resolve_value_matrix_flags(
        value_matrices, plot_pvalue_matrices, plot_qvalue_matrices)
    value_matrices_label = _corr_value_matrix_label(
        plot_pvalue_matrices, plot_qvalue_matrices)

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
        settings={
            "require": str(require).lower(),
            "min_n": int(min_n),
            "covariate_gate": str(covariate_gate).lower(),
            "covariate_alpha": covariate_alpha,
            "min_endpoint_hits": int(min_endpoint_hits),
            "max_adjusted_regressions": max_adjusted_regressions,
            "categorical": categorical,
            "reference_levels": reference_levels,
            "specificity": (_slug_specificity if _slug_specificity is not None else specificity),
            "roi": _roi_base,
            "value_matrices": value_matrices_label,
        },
    )
    if _run_dirs is not None:
        # Queue-merge: share the run folder a sibling condition already resolved.
        fig_dir, data_dir, resolved_label = _run_dirs
        reuse_existing = False
    else:
        fig_dir, data_dir, resolved_label, reuse_existing = _adj_corr_run_dirs(
            experiment, label, if_exists, clear_overwrite=bool(save))
    manifest_path = os.path.join(data_dir, "manifest.json")
    if reuse_existing and _corr_isfile(manifest_path):
        cached = _corr_read_json(manifest_path)
        cached["reused"] = True
        return cached
    aliases = getattr(experiment, "aliases", None)
    spec_for_filename = specificity if _tag_specificity else None
    spec_tag = build_pipeline_suffix(specificity=spec_for_filename, aliases=aliases)

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
        filename_spec=spec_for_filename,
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
        filename_spec=spec_for_filename,
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
        _corr_to_csv(screening, os.path.join(data_dir, f"covariate_screening{spec_tag}.csv"), index=False)
        _corr_to_csv(endpoint_status, os.path.join(data_dir, f"endpoint_status{spec_tag}.csv"), index=False)
        _corr_to_csv(residual_models, os.path.join(data_dir, f"residual_models{spec_tag}.csv"), index=False)
        _corr_to_csv(
            regression_coeffs,
            os.path.join(data_dir, f"adjusted_regression_coefficients{spec_tag}.csv"),
            index=False,
        )
        _corr_to_csv(
            regression_summaries,
            os.path.join(data_dir, f"adjusted_regression_summaries{spec_tag}.csv"),
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
        "value_matrices": value_matrices_label,
        "plot_pvalue_matrices": bool(plot_pvalue_matrices),
        "plot_qvalue_matrices": bool(plot_qvalue_matrices),
        "coefficient_matrix_star_source": "raw_p_value",
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
        _adj_corr_append_runs_index(experiment, manifest)

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
                  methods, iqr_k, mad_threshold, rout_q):
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
        methods=methods, iqr_k=iqr_k, mad_threshold=mad_threshold,
        rout_q=rout_q)

    name_lookup = scope_df["AnimalName"] if "AnimalName" in scope_df.columns else None

    def _animal(idx):
        if name_lookup is not None:
            try:
                return str(name_lookup.loc[idx])
            except Exception:
                return str(idx)
        return str(idx)

    cols = ["group", "column", "AnimalName", "value", "iqr_outlier",
            "mad_outlier", "modified_z", "iqr_lower", "iqr_upper",
            "rout_outlier", "rout_p", "rout_threshold", "rout_t",
            "rout_center", "rout_rsdr"]
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


def _ovw_missingness_codes(scope_df, columns):
    """Animals x columns code matrix: 0 present, 1 NaN, 2 not-included, 3 excluded."""
    cols = list(columns)
    n_rows = int(len(scope_df))
    codes = np.zeros((n_rows, len(cols)), dtype=int)
    for j, col in enumerate(cols):
        s = scope_df[col]
        excl = is_excluded_mask(s).to_numpy()
        sent = (s.astype(str).str.contains(_OVW_SENTINEL, na=False).to_numpy()
                & ~excl)
        nan = s.isna().to_numpy() & ~sent & ~excl
        codes[:, j] = np.select([excl, sent, nan], [3, 2, 1], default=0)
    return codes


def _ovw_missingness_figure(scope_df, columns, tick_label_size, title):
    """Animals x columns map: present / missing (NaN) / not-included / excluded."""
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    cols = list(columns)
    n_rows = int(len(scope_df))
    if n_rows == 0 or len(cols) == 0:
        return None
    codes = _ovw_missingness_codes(scope_df, cols)

    fig_w = min(max(7.0, len(cols) * 0.32), 30.0)
    fig_h = min(max(5.0, n_rows * 0.28), 27.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    cmap = ListedColormap(["#2ca25f", "#bdbdbd", "#fdae61", "#de2d26"])
    ax.imshow(codes, aspect="auto", cmap=cmap, vmin=0, vmax=3,
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
        Patch(color="#de2d26", label="excluded"),
    ]
    ax.legend(handles=handles, bbox_to_anchor=(1.01, 1.0),
              loc="upper left", fontsize=9, frameon=False)
    fig.tight_layout()
    return fig


def _ovw_short_label(value, limit=34):
    text = str(value)
    limit = max(4, int(limit))
    return text if len(text) <= limit else text[:limit - 1] + "..."


def _ovw_numeric_figure_columns(numeric_cols, inventory):
    """Numeric columns worth visualising; excludes identifiers/all-missing roles."""
    cols = list(numeric_cols or [])
    common_ids = {"animalname", "animal", "id", "subject", "subjectid"}
    if inventory is None or inventory.empty or "column" not in inventory.columns:
        return [c for c in cols if str(c).replace("_", "").lower() not in common_ids]
    inv = inventory.set_index("column")
    out = []
    for col in cols:
        if str(col).replace("_", "").lower() in common_ids:
            continue
        role = str(inv.loc[col, "role"]) if col in inv.index else ""
        if role in {"identifier", "all_missing"}:
            continue
        out.append(col)
    return out


def _ovw_limit_columns(columns, max_items):
    cols = list(columns or [])
    if max_items is None:
        return cols
    return cols[:max(1, int(max_items))]


def _ovw_group_counts_figure(group_counts, tick_label_size, max_items):
    """Bar chart of animal counts per condition/factor level."""
    if group_counts is None or group_counts.empty:
        return None
    df = group_counts.copy()
    detail = df[df["grouping"].astype(str) != "(all)"].copy()
    if detail.empty:
        detail = df.copy()
    if max_items is not None and len(detail) > int(max_items):
        detail = detail.nlargest(int(max_items), "n_animals")

    detail["label"] = np.where(
        detail["grouping"].astype(str).eq("(all)"),
        detail["level"].astype(str),
        detail["grouping"].astype(str) + ": " + detail["level"].astype(str),
    )
    detail = detail.iloc[::-1].reset_index(drop=True)
    n = len(detail)
    fig_h = min(max(3.5, 0.38 * n + 1.7), 18.0)
    fig, ax = plt.subplots(figsize=(8.5, fig_h))
    y = np.arange(n)
    groupings = detail["grouping"].astype(str).tolist()
    palette = dict(zip(sorted(set(groupings)), plt.cm.tab10.colors))
    colors = [palette[g] for g in groupings]
    ax.barh(y, detail["n_animals"].astype(float), color=colors, alpha=0.86)
    ax.set_yticks(y)
    ax.set_yticklabels(
        [_ovw_short_label(v, 42) for v in detail["label"]],
        fontsize=max(7, int(tick_label_size) - 8),
    )
    ax.set_xlabel("Animals", fontsize=max(9, int(tick_label_size) - 5))
    ax.set_title("Group counts", fontsize=int(tick_label_size))
    xmax = float(detail["n_animals"].max()) if len(detail) else 0.0
    ax.set_xlim(0, xmax * 1.15 + 1)
    for yi, val in zip(y, detail["n_animals"]):
        ax.text(float(val) + max(0.15, xmax * 0.02), yi, str(int(val)),
                va="center", fontsize=max(7, int(tick_label_size) - 9))
    ax.grid(axis="x", alpha=0.25)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fig


def _ovw_availability_figure(availability, tick_label_size, max_items):
    """Heatmap of available animal counts for each metric x condition."""
    if availability is None or availability.empty:
        return None
    df = availability.copy()
    df = df.apply(pd.to_numeric, errors="coerce")
    if df.empty or df.shape[1] == 0:
        return None
    order = df.min(axis=1).sort_values(kind="mergesort").index.tolist()
    df = df.loc[order]
    if max_items is not None and len(df) > int(max_items):
        df = df.iloc[:int(max_items)]

    arr = df.to_numpy(dtype=float)
    fig_w = min(max(7.0, df.shape[1] * 1.2), 16.0)
    fig_h = min(max(4.0, df.shape[0] * 0.32 + 1.8), 18.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(arr, aspect="auto", cmap="YlGnBu", interpolation="none")
    ax.set_title("Availability by condition", fontsize=int(tick_label_size))
    ax.set_xticks(range(df.shape[1]))
    ax.set_xticklabels([_ovw_short_label(c, 22) for c in df.columns],
                       rotation=45, ha="right",
                       fontsize=max(7, int(tick_label_size) - 8))
    ax.set_yticks(range(df.shape[0]))
    ax.set_yticklabels([_ovw_short_label(i, 42) for i in df.index],
                       fontsize=max(7, int(tick_label_size) - 9))
    if df.size <= 180:
        for i in range(df.shape[0]):
            for j in range(df.shape[1]):
                val = arr[i, j]
                if np.isfinite(val):
                    ax.text(j, i, str(int(val)), ha="center", va="center",
                            fontsize=7, color="black")
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Non-missing animals")
    fig.tight_layout()
    return fig


def _ovw_metric_distributions_figure(numeric_df, numeric_cols, tick_label_size,
                                     max_items):
    """Z-scored animal-level distributions for each numeric summary metric."""
    cols = []
    data = []
    for col in _ovw_limit_columns(numeric_cols, max_items):
        vals = pd.to_numeric(numeric_df[col], errors="coerce").dropna()
        if len(vals) < 2:
            continue
        sd = float(vals.std(ddof=1))
        if not np.isfinite(sd) or sd == 0:
            continue
        z = ((vals - float(vals.mean())) / sd).to_numpy(dtype=float)
        cols.append(col)
        data.append(z)
    if not data:
        return None

    n = len(data)
    fig_h = min(max(4.5, 0.34 * n + 1.8), 18.0)
    fig, ax = plt.subplots(figsize=(9.0, fig_h))
    bp = ax.boxplot(data, vert=False, patch_artist=True, showfliers=False,
                    widths=0.62)
    for patch in bp["boxes"]:
        patch.set_facecolor("#9ecae1")
        patch.set_edgecolor("#3182bd")
        patch.set_alpha(0.75)
    for key in ("whiskers", "caps", "medians"):
        for artist in bp[key]:
            artist.set_color("#08519c")
            artist.set_linewidth(1.2)
    for yi, vals in enumerate(data, start=1):
        jitter = np.linspace(-0.17, 0.17, len(vals)) if len(vals) > 1 else [0]
        ax.scatter(vals, yi + jitter, s=14, color="#252525", alpha=0.55,
                   linewidths=0)
    ax.axvline(0, color="#636363", linewidth=1.0, alpha=0.7)
    ax.set_yticks(range(1, n + 1))
    ax.set_yticklabels([_ovw_short_label(c, 44) for c in cols],
                       fontsize=max(7, int(tick_label_size) - 9))
    ax.set_xlabel("Z-score within metric", fontsize=max(9, int(tick_label_size) - 5))
    ax.set_title("Metric distributions", fontsize=int(tick_label_size))
    ax.grid(axis="x", alpha=0.25)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fig


def _ovw_descriptives_figure(descriptives, tick_label_size, max_items):
    """Rank metrics by coefficient of variation from descriptive statistics."""
    if descriptives is None or descriptives.empty:
        return None
    df = descriptives.copy()
    required = {"column", "n", "cv_pct", "q25", "q75"}
    if not required.issubset(df.columns):
        return None
    df["iqr"] = pd.to_numeric(df["q75"], errors="coerce") - pd.to_numeric(
        df["q25"], errors="coerce")
    agg = (
        df.groupby("column", as_index=False)
        .agg(n_min=("n", "min"), cv_pct=("cv_pct", "mean"), iqr=("iqr", "mean"))
    )
    agg["cv_pct"] = pd.to_numeric(agg["cv_pct"], errors="coerce")
    agg = agg[np.isfinite(agg["cv_pct"])]
    if agg.empty:
        return None
    agg = agg.sort_values("cv_pct", ascending=False, kind="mergesort")
    if max_items is not None and len(agg) > int(max_items):
        agg = agg.head(int(max_items))
    agg = agg.iloc[::-1].reset_index(drop=True)

    n = len(agg)
    fig_h = min(max(4.0, 0.34 * n + 1.8), 18.0)
    fig, ax = plt.subplots(figsize=(9.0, fig_h))
    y = np.arange(n)
    ax.barh(y, agg["cv_pct"], color="#74c476", alpha=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels([_ovw_short_label(c, 44) for c in agg["column"]],
                       fontsize=max(7, int(tick_label_size) - 9))
    ax.set_xlabel("Coefficient of variation (%)",
                  fontsize=max(9, int(tick_label_size) - 5))
    ax.set_title("Descriptive variability summary", fontsize=int(tick_label_size))
    xmax = float(agg["cv_pct"].max()) if len(agg) else 0.0
    ax.set_xlim(0, xmax * 1.2 + 1)
    for yi, row in agg.iterrows():
        ax.text(float(row["cv_pct"]) + max(0.15, xmax * 0.02), yi,
                f"n>={int(row['n_min'])}", va="center",
                fontsize=max(7, int(tick_label_size) - 9))
    ax.grid(axis="x", alpha=0.25)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fig


def _ovw_normality_figure(normality, alpha, tick_label_size, max_items):
    """Heatmap of Shapiro p-values with nonparametric hints overlaid."""
    if normality is None or normality.empty:
        return None
    if not {"group", "column", "shapiro_p", "suggested"}.issubset(normality.columns):
        return None
    df = normality.copy()
    df["shapiro_p"] = pd.to_numeric(df["shapiro_p"], errors="coerce")
    order = (
        df.groupby("column")["shapiro_p"].min().sort_values(kind="mergesort")
        .index.tolist()
    )
    if max_items is not None and len(order) > int(max_items):
        order = order[:int(max_items)]
    df = df[df["column"].isin(order)]
    if df.empty:
        return None
    pvt = df.pivot_table(index="group", columns="column", values="shapiro_p",
                         aggfunc="min").reindex(columns=order)
    arr = pvt.to_numpy(dtype=float)
    masked = np.ma.masked_invalid(arr)
    cmap = plt.cm.viridis.copy()
    cmap.set_bad("#d9d9d9")

    fig_w = min(max(8.0, pvt.shape[1] * 0.55 + 2.0), 24.0)
    fig_h = min(max(3.5, pvt.shape[0] * 0.45 + 2.0), 12.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(masked, aspect="auto", cmap=cmap, vmin=0.0, vmax=1.0,
                   interpolation="none")
    ax.set_title(f"Normality screen (Shapiro p, alpha={float(alpha):g})",
                 fontsize=int(tick_label_size))
    ax.set_xticks(range(pvt.shape[1]))
    ax.set_xticklabels([_ovw_short_label(c, 26) for c in pvt.columns],
                       rotation=90, fontsize=max(7, int(tick_label_size) - 9))
    ax.set_yticks(range(pvt.shape[0]))
    ax.set_yticklabels([_ovw_short_label(g, 28) for g in pvt.index],
                       fontsize=max(7, int(tick_label_size) - 8))
    if pvt.size <= 220:
        for i in range(pvt.shape[0]):
            for j in range(pvt.shape[1]):
                p = arr[i, j]
                if not np.isfinite(p):
                    txt = "n/a"
                else:
                    txt = "NP" if p < float(alpha) else "P"
                ax.text(j, i, txt, ha="center", va="center",
                        fontsize=7, color="white" if np.isfinite(p) and p < 0.45 else "black")
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Shapiro p-value")
    fig.tight_layout()
    return fig


def _ovw_outlier_summary_figure(outliers, outlier_animals, tick_label_size,
                                max_items):
    """Two-panel roll-up of outlier flags by animal and metric."""
    has_animals = outlier_animals is not None and not outlier_animals.empty
    has_outliers = outliers is not None and not outliers.empty
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    fig.suptitle("Outlier summary", fontsize=int(tick_label_size))

    ax = axes[0]
    if has_animals:
        a = outlier_animals.copy().sort_values("n_flags", ascending=False)
        if max_items is not None and len(a) > int(max_items):
            a = a.head(int(max_items))
        a = a.iloc[::-1].reset_index(drop=True)
        y = np.arange(len(a))
        ax.barh(y, a["n_flags"].astype(float), color="#fb6a4a", alpha=0.88)
        ax.set_yticks(y)
        ax.set_yticklabels([_ovw_short_label(v, 24) for v in a["AnimalName"]],
                           fontsize=max(7, int(tick_label_size) - 9))
        ax.set_xlabel("Flags")
        ax.set_title("Animals")
    else:
        ax.text(0.5, 0.5, "No flagged animals", ha="center", va="center")
        ax.set_axis_off()

    ax = axes[1]
    if has_outliers:
        m = (
            outliers.groupby("column").size().rename("n_flags")
            .reset_index().sort_values("n_flags", ascending=False)
        )
        if max_items is not None and len(m) > int(max_items):
            m = m.head(int(max_items))
        m = m.iloc[::-1].reset_index(drop=True)
        y = np.arange(len(m))
        ax.barh(y, m["n_flags"].astype(float), color="#9e9ac8", alpha=0.9)
        ax.set_yticks(y)
        ax.set_yticklabels([_ovw_short_label(v, 34) for v in m["column"]],
                           fontsize=max(7, int(tick_label_size) - 9))
        ax.set_xlabel("Flags")
        ax.set_title("Metrics")
    else:
        ax.text(0.5, 0.5, "No flagged metrics", ha="center", va="center")
        ax.set_axis_off()

    for ax in axes:
        ax.grid(axis="x", alpha=0.25)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def _ovw_covariation_pairs_figure(covarying, threshold, tick_label_size,
                                  max_items):
    """Ranked bar chart of high-correlation metric pairs."""
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.set_title(f"Covarying metric pairs (|r| >= {float(threshold):g})",
                 fontsize=int(tick_label_size))
    if covarying is None or covarying.empty:
        ax.text(0.5, 0.5, "No pairs passed the threshold",
                ha="center", va="center")
        ax.set_axis_off()
        fig.tight_layout()
        return fig

    df = covarying.copy().sort_values("abs_r", ascending=False)
    if max_items is not None and len(df) > int(max_items):
        df = df.head(int(max_items))
    df["label"] = df.apply(
        lambda r: f"{_ovw_short_label(r['x'], 24)} vs {_ovw_short_label(r['y'], 24)}",
        axis=1,
    )
    df = df.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(df))
    colors = np.where(df["r"].astype(float) >= 0, "#de2d26", "#3182bd")
    ax.barh(y, df["abs_r"].astype(float), color=colors, alpha=0.88)
    ax.axvline(float(threshold), color="#252525", linestyle="--", linewidth=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels(df["label"], fontsize=max(7, int(tick_label_size) - 9))
    ax.set_xlabel("Absolute correlation")
    ax.set_xlim(0, 1.02)
    for yi, row in df.iterrows():
        ax.text(min(float(row["abs_r"]) + 0.015, 1.0), yi,
                f"r={float(row['r']):.2f}", va="center",
                fontsize=max(7, int(tick_label_size) - 9))
    ax.grid(axis="x", alpha=0.25)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fig


def _ovw_groups_from_column(scope_df, num_df, column, specificity):
    """Return ordered groups from an arbitrary summary column."""
    if column not in scope_df.columns:
        return []
    groups = []
    values = scope_df[column].dropna().unique().tolist()
    for value in values:
        idx = num_df.index.intersection(scope_df.index[scope_df[column] == value])
        if len(idx) > 0:
            reg_spec = specificity if specificity is not None else (column, value)
            groups.append((str(value), idx, reg_spec))
    return groups


def _ovw_distribution_groups(experiment, scope_df, num_df, by, factor, specificity,
                             split_by=None, split_mode="cross"):
    """Groups used for condition/factor distribution views.

    The broader overview defaults to pooled ``by='all'`` for some analyses, but
    distribution views are most useful split by Condition. When no factor is
    requested and a Condition column exists, use condition groups by default.
    When ``split_by`` is given it takes precedence over ``by``/``factor`` and the
    multi-dimension resolver drives the distribution/effect-size sections too, so
    both group axes stay consistent within a run.
    """
    if split_by is not None:
        return _ovw_multi_groups(
            experiment, scope_df, num_df, split_by, split_mode, specificity)
    pooled = [("All", num_df.index, specificity)]
    if factor:
        groups = _corr_pipeline_groups(
            experiment, scope_df, num_df, by, factor, specificity)
        if groups and not (len(groups) == 1 and str(groups[0][0]) == "All"):
            return groups
        return _ovw_groups_from_column(scope_df, num_df, factor, specificity) or pooled

    by_key = str(by).strip()
    by_lower = by_key.lower()
    if by_lower in {"condition", "conditions", "all", ""}:
        if "Condition" in scope_df.columns:
            groups = _corr_pipeline_groups(
                experiment, scope_df, num_df, "conditions", None, specificity)
            if groups and not (len(groups) == 1 and str(groups[0][0]) == "All"):
                return groups
            return _ovw_groups_from_column(
                scope_df, num_df, "Condition", specificity) or pooled
        return pooled

    if by_key in scope_df.columns:
        return _ovw_groups_from_column(scope_df, num_df, by_key, specificity) or pooled
    return pooled


# Separator joining split-key levels into a composite group label, e.g.
# ``"WT | Male"`` for a Condition x Sex cross cell. Kept as a single constant so
# the group builder and the effect-control resolver split/join identically.
_OVW_COMPOSITE_SEP = " | "


def _ovw_ordered_levels(experiment, enriched, key):
    """Return the present levels of ``key`` in a declared order.

    Prefers the design ordering (``condition_list`` for ``Condition``,
    ``factorDict`` for a registered factor); any level without a declared order
    (e.g. an ad-hoc ``Sex`` column) falls back to first-seen.
    """
    present = []
    for v in enriched[key].dropna().tolist():
        if v not in present:
            present.append(v)
    ordered = []
    if str(key) == "Condition":
        for cond in getattr(experiment, "condition_list", []) or []:
            name = getattr(cond, "name", None)
            match = next((v for v in present if str(v) == str(name)), None)
            if match is not None and match not in ordered:
                ordered.append(match)
    else:
        factor_dict = getattr(getattr(experiment, "condition_list", None),
                              "factorDict", {}) or {}
        for cond in factor_dict.get(key, []) if isinstance(factor_dict, dict) else []:
            name = getattr(cond, "name", None)
            match = next((v for v in present if str(v) == str(name)), None)
            if match is not None and match not in ordered:
                ordered.append(match)
    for v in present:
        if v not in ordered:
            ordered.append(v)
    return ordered


def _ovw_multi_groups(experiment, scope_df, num_df, split_by, split_mode,
                      specificity):
    """Resolve multi-dimension split groups as ``(label, row_index, reg_spec)``.

    ``split_by`` is a single key or a list of keys (each ``"Condition"`` or any
    summary column / factor). A single key delegates to the one-axis resolver so
    ``split_by="Condition"`` matches ``by="conditions"`` exactly. With multiple
    keys:

    - ``split_mode="cross"`` yields the cartesian product, first-key-major, with
      composite labels (``"WT | Male"``) and AND-intersected row indices; empty
      product cells are dropped.
    - ``split_mode="parallel"`` concatenates each axis independently, prefixing
      labels with the key (``"Sex=Male"``) so axes never collide.

    Raises ``ValueError`` if a key is not resolvable in the summary/factors.
    """
    keys = [split_by] if isinstance(split_by, str) else list(split_by)
    if not keys:
        raise ValueError("data_overview: split_by is empty; pass a key or list of keys.")
    if len(keys) == 1:
        k = str(keys[0])
        enriched = _enrich_df_grouping_columns(scope_df, experiment, requested_by=k)
        if k not in enriched.columns:
            raise ValueError(
                f"data_overview: split key {k!r} is not resolvable in the summary "
                f"or factors.")
        return _corr_pipeline_groups(
            experiment, scope_df, num_df,
            ("conditions" if k == "Condition" else "all"),
            (None if k == "Condition" else k), specificity)

    # Per-key ordered [(key, level, row_index)] axes.
    level_maps = []
    for k in keys:
        k = str(k)
        enriched = _enrich_df_grouping_columns(scope_df, experiment, requested_by=k)
        if k not in enriched.columns:
            raise ValueError(
                f"data_overview: split key {k!r} is not resolvable in the summary "
                f"or factors.")
        axis = []
        for v in _ovw_ordered_levels(experiment, enriched, k):
            idx = num_df.index.intersection(enriched.index[enriched[k] == v])
            axis.append((k, v, idx))
        level_maps.append(axis)

    groups = []
    if str(split_mode).strip().lower() == "parallel":
        for axis in level_maps:                       # concat each axis, prefixed labels
            for k, v, idx in axis:
                if len(idx) > 0:
                    groups.append((f"{k}={v}", idx, specificity))
    else:                                             # cross: cartesian product, AND indices
        import itertools
        for combo in itertools.product(*level_maps):
            idx = combo[0][2]
            for _, _, part in combo[1:]:
                idx = idx.intersection(part)
            if len(idx) > 0:                          # drop empty product cells
                label = _OVW_COMPOSITE_SEP.join(str(v) for _, v, _ in combo)
                groups.append((label, idx, specificity))
    return groups or [("All", num_df.index, specificity)]


def _ovw_condition_distribution_stats(scope_df, numeric_df, numeric_cols, groups):
    """Per (group, column) descriptive stats plus availability accounting."""
    columns = [
        "group", "column", "n_total", "n", "n_missing", "n_sentinel",
        "n_excluded", "pct_unavailable", "mean", "sd", "sem", "median",
        "q25", "q75", "iqr", "min", "max", "cv_pct",
    ]
    rows = []
    for glabel, gidx, _spec in groups:
        scope_idx = scope_df.index.intersection(gidx)
        num_idx = numeric_df.index.intersection(gidx)
        for col in numeric_cols:
            raw = scope_df.loc[scope_idx, col] if col in scope_df.columns else pd.Series(dtype=object)
            excluded = is_excluded_mask(raw)
            sentinel = raw.astype(str).str.contains(_OVW_SENTINEL, na=False) & ~excluded
            true_nan = raw.isna() & ~sentinel & ~excluded
            vals = pd.to_numeric(
                numeric_df.loc[num_idx, col], errors="coerce"
            ).dropna().astype(float)
            n_total = int(len(raw))
            n = int(len(vals))
            if n > 0:
                mean = float(vals.mean())
                median = float(vals.median())
                q25 = float(vals.quantile(0.25))
                q75 = float(vals.quantile(0.75))
                vmin = float(vals.min())
                vmax = float(vals.max())
            else:
                mean = median = q25 = q75 = vmin = vmax = np.nan
            sd = float(vals.std(ddof=1)) if n >= 2 else np.nan
            sem = float(sd / np.sqrt(n)) if n >= 2 and np.isfinite(sd) else np.nan
            iqr = float(q75 - q25) if np.isfinite(q25) and np.isfinite(q75) else np.nan
            cv = (
                abs(sd / mean) * 100.0
                if n >= 2 and np.isfinite(sd) and np.isfinite(mean) and mean != 0
                else np.nan
            )
            n_missing = int(true_nan.sum())
            n_sentinel = int(sentinel.sum())
            n_excluded = int(excluded.sum())
            unavailable = n_missing + n_sentinel + n_excluded
            rows.append({
                "group": str(glabel),
                "column": col,
                "n_total": n_total,
                "n": n,
                "n_missing": n_missing,
                "n_sentinel": n_sentinel,
                "n_excluded": n_excluded,
                "pct_unavailable": (
                    round(100.0 * unavailable / n_total, 2) if n_total else np.nan
                ),
                "mean": mean,
                "sd": sd,
                "sem": sem,
                "median": median,
                "q25": q25,
                "q75": q75,
                "iqr": iqr,
                "min": vmin,
                "max": vmax,
                "cv_pct": cv,
            })
    return pd.DataFrame(rows, columns=columns)


def _ovw_validate_distribution_plot(kind):
    key = str(kind).strip().lower()
    aliases = {
        "rain": "raincloud",
        "rainclouds": "raincloud",
        "box": "boxstrip",
        "boxplot": "boxstrip",
        "points": "strip",
        "point": "strip",
    }
    key = aliases.get(key, key)
    valid = {"raincloud", "boxstrip", "violin", "strip"}
    if key not in valid:
        raise ValueError(
            "condition_distribution_plot must be one of "
            "'raincloud', 'boxstrip', 'violin', or 'strip'."
        )
    return key


def _ovw_group_palette(labels):
    colors = list(plt.cm.tab20.colors)
    if len(labels) <= 10:
        colors = list(plt.cm.tab10.colors)
    return {str(label): colors[i % len(colors)] for i, label in enumerate(labels)}


def _ovw_scaled_group_values(numeric_df, col, idx, scale):
    vals = pd.to_numeric(numeric_df.loc[numeric_df.index.intersection(idx), col],
                         errors="coerce").dropna().astype(float)
    if str(scale).lower() != "zscore":
        return vals.to_numpy(dtype=float)
    all_vals = pd.to_numeric(numeric_df[col], errors="coerce").dropna()
    if len(all_vals) < 2:
        return np.asarray([], dtype=float)
    sd = float(all_vals.std(ddof=1))
    if not np.isfinite(sd) or sd == 0:
        return np.asarray([], dtype=float)
    return ((vals - float(all_vals.mean())) / sd).to_numpy(dtype=float)


def _ovw_condition_distribution_figure(numeric_df, numeric_cols, groups,
                                       tick_label_size, max_items,
                                       plot_kind="raincloud", scale="raw"):
    """Small-multiple condition/factor distributions for selected metrics."""
    cols = _ovw_limit_columns(numeric_cols, max_items)
    if not cols or not groups:
        return None
    kind = _ovw_validate_distribution_plot(plot_kind)
    scale_key = str(scale).strip().lower()
    if scale_key not in {"raw", "zscore"}:
        raise ValueError("condition distribution scale must be 'raw' or 'zscore'.")

    labels = [str(g[0]) for g in groups]
    palette = _ovw_group_palette(labels)
    prepared = []
    for col in cols:
        data = [_ovw_scaled_group_values(numeric_df, col, gidx, scale_key)
                for _glabel, gidx, _spec in groups]
        if any(len(values) > 0 for values in data):
            prepared.append((col, data))
    if not prepared:
        return None

    n = len(prepared)
    ncols = 2 if n > 1 else 1
    nrows = int(np.ceil(n / ncols))
    fig_w = 7.2 * ncols
    fig_h = min(max(3.7 * nrows, 4.2), 24.0)
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h),
                             squeeze=False)
    axes_flat = axes.reshape(-1)
    positions = np.arange(1, len(labels) + 1)

    for ax, (col, data) in zip(axes_flat, prepared):
        nonempty = [(i, vals) for i, vals in enumerate(data) if len(vals) > 0]
        if kind in {"raincloud", "violin"} and nonempty:
            violin = ax.violinplot(
                [vals for _i, vals in nonempty],
                positions=[positions[i] for i, _vals in nonempty],
                widths=0.78,
                showmeans=False,
                showmedians=False,
                showextrema=False,
            )
            for body, (i, _vals) in zip(violin["bodies"], nonempty):
                body.set_facecolor(palette[labels[i]])
                body.set_edgecolor(palette[labels[i]])
                body.set_alpha(0.28 if kind == "raincloud" else 0.45)
        if kind in {"raincloud", "boxstrip"} and nonempty:
            bp = ax.boxplot(
                [vals for _i, vals in nonempty],
                positions=[positions[i] for i, _vals in nonempty],
                widths=0.32,
                patch_artist=True,
                showfliers=False,
            )
            for patch, (i, _vals) in zip(bp["boxes"], nonempty):
                patch.set_facecolor("white")
                patch.set_edgecolor(palette[labels[i]])
                patch.set_linewidth(1.3)
            for key in ("whiskers", "caps", "medians"):
                for artist in bp[key]:
                    artist.set_color("#252525")
                    artist.set_linewidth(1.0)
        if kind in {"raincloud", "boxstrip", "strip"}:
            for i, vals in enumerate(data):
                if len(vals) == 0:
                    continue
                if len(vals) == 1:
                    jitter = np.asarray([0.0])
                else:
                    jitter = np.linspace(-0.16, 0.16, len(vals))
                ax.scatter(
                    positions[i] + jitter,
                    vals,
                    s=18,
                    color=palette[labels[i]],
                    alpha=0.72,
                    linewidths=0,
                    zorder=3,
                )
        ax.set_title(_ovw_short_label(col, 54), fontsize=max(9, int(tick_label_size) - 4))
        ax.set_xticks(positions)
        ax.set_xticklabels([_ovw_short_label(label, 20) for label in labels],
                           rotation=35, ha="right",
                           fontsize=max(7, int(tick_label_size) - 9))
        ax.set_ylabel("Z-score" if scale_key == "zscore" else "Value",
                      fontsize=max(8, int(tick_label_size) - 7))
        ax.grid(axis="y", alpha=0.22)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

    for ax in axes_flat[len(prepared):]:
        ax.set_axis_off()
    title = "Condition distributions"
    if scale_key == "zscore":
        title = "Condition distributions (z-scored within metric)"
    fig.suptitle(title, fontsize=int(tick_label_size))
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


def _ovw_condition_fingerprint(condition_stats, stat="median"):
    """Z-scored group x metric matrix from condition distribution stats."""
    if condition_stats is None or condition_stats.empty:
        return pd.DataFrame()
    stat_col = str(stat).strip()
    if stat_col not in condition_stats.columns:
        raise ValueError(
            "fingerprint_stat must be one of the statistic columns in "
            "condition_distribution_stats.csv, e.g. 'median' or 'mean'."
        )
    pvt = condition_stats.pivot_table(
        index="group", columns="column", values=stat_col, aggfunc="first")
    if pvt.empty:
        return pvt
    out = pvt.copy().astype(float)
    for col in out.columns:
        vals = pd.to_numeric(out[col], errors="coerce")
        finite = vals[np.isfinite(vals)]
        if len(finite) < 2:
            out[col] = np.nan
            continue
        sd = float(finite.std(ddof=0))
        if not np.isfinite(sd) or sd == 0:
            out[col] = vals.where(~np.isfinite(vals), 0.0)
        else:
            out[col] = (vals - float(finite.mean())) / sd
    return out


def _ovw_condition_variability(condition_stats, stat="cv_pct"):
    """Group x metric variability matrix."""
    if condition_stats is None or condition_stats.empty:
        return pd.DataFrame()
    stat_col = str(stat).strip()
    if stat_col not in condition_stats.columns:
        raise ValueError("variability_stat must be a column in condition_distribution_stats.csv.")
    return condition_stats.pivot_table(
        index="group", columns="column", values=stat_col, aggfunc="first")


def _ovw_matrix_figure(matrix, title, tick_label_size, max_items,
                       cmap="viridis", center_zero=False, colorbar_label=None):
    """Generic small overview heatmap for group x metric matrices."""
    if matrix is None or matrix.empty:
        return None
    df = matrix.copy()
    if max_items is not None and df.shape[1] > int(max_items):
        variability = df.apply(
            lambda s: pd.to_numeric(s, errors="coerce").max()
            - pd.to_numeric(s, errors="coerce").min(),
            axis=0,
        ).sort_values(ascending=False, kind="mergesort")
        df = df.loc[:, variability.head(int(max_items)).index]
    if df.empty:
        return None
    arr = df.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    masked = np.ma.masked_invalid(arr)
    cm = plt.get_cmap(cmap).copy()
    cm.set_bad("#d9d9d9")
    if center_zero:
        finite = arr[np.isfinite(arr)]
        vmax = max(1.0, float(np.nanmax(np.abs(finite)))) if finite.size else 1.0
        vmin = -vmax
    else:
        finite = arr[np.isfinite(arr)]
        vmin = float(np.nanmin(finite)) if finite.size else 0.0
        vmax = float(np.nanmax(finite)) if finite.size else 1.0
        if vmax <= vmin:
            vmax = vmin + 1.0
    fig_w = min(max(7.5, df.shape[1] * 0.52 + 2.0), 24.0)
    fig_h = min(max(3.6, df.shape[0] * 0.55 + 2.0), 14.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(masked, aspect="auto", cmap=cm, vmin=vmin, vmax=vmax,
                   interpolation="none")
    ax.set_title(title, fontsize=int(tick_label_size))
    ax.set_xticks(range(df.shape[1]))
    ax.set_xticklabels([_ovw_short_label(c, 28) for c in df.columns],
                       rotation=90, fontsize=max(7, int(tick_label_size) - 9))
    ax.set_yticks(range(df.shape[0]))
    ax.set_yticklabels([_ovw_short_label(g, 28) for g in df.index],
                       fontsize=max(7, int(tick_label_size) - 8))
    if df.size <= 120:
        for i in range(df.shape[0]):
            for j in range(df.shape[1]):
                val = arr[i, j]
                if np.isfinite(val):
                    ax.text(j, i, f"{val:.2g}", ha="center", va="center",
                            fontsize=7, color="black")
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    if colorbar_label:
        cbar.set_label(colorbar_label)
    fig.tight_layout()
    return fig


def _ovw_resolve_effect_control(groups, effect_control):
    """Resolve the control axis into ``(control_display, contrasts)``.

    ``contrasts`` is a list of ``(control_label, group_label)`` pairs to compare.
    Composite (crossed) group labels like ``"WT | Male"`` are handled with the
    minimal robust rule (documented in :func:`data_overview`):

    1. ``effect_control=None`` -> the first group is the single control, compared
       against every other group.
    2. ``effect_control`` exactly matches a group label -> that group is the single
       control (works for a composite named in full, e.g. ``"WT | Male"``).
    3. otherwise, if ``effect_control`` matches the FIRST split-key component of the
       composite labels -> it is the control *per remaining-key stratum* (e.g.
       ``"WT | Male"`` controls ``"KO | Male"`` and ``"WT | Female"`` controls
       ``"KO | Female"``); ``control_display`` is the matched component string.
    4. otherwise -> ``ValueError``.
    """
    labels = [str(g[0]) for g in groups]
    if len(labels) == 0:
        return None, []
    if effect_control is None:
        control = labels[0]
        return control, [(control, g) for g in labels if g != control]
    target = str(effect_control).strip().casefold()
    for label in labels:                              # rule 2: exact label match
        if label.strip().casefold() == target:
            return label, [(label, g) for g in labels if g != label]

    # rule 3: match the first component of composite labels -> per-stratum control.
    if any(_OVW_COMPOSITE_SEP in lbl for lbl in labels):
        strata = {}                                   # remaining-key suffix -> [(first, label)]
        for lbl in labels:
            parts = [p.strip() for p in lbl.split(_OVW_COMPOSITE_SEP)]
            strata.setdefault(tuple(parts[1:]), []).append((parts[0], lbl))
        contrasts = []
        matched = False
        for _rest, members in strata.items():
            ctrl_lbl = next((lbl for first, lbl in members
                             if first.casefold() == target), None)
            if ctrl_lbl is None:
                continue
            matched = True
            contrasts.extend((ctrl_lbl, lbl) for _first, lbl in members
                             if lbl != ctrl_lbl)
        if matched:
            return str(effect_control), contrasts

    raise ValueError(
        f"effect_control {effect_control!r} is not a group label or the first "
        f"split-key component of {labels}.")


def _ovw_effect_sizes(numeric_df, numeric_cols, groups, effect_control=None,
                      min_n=3):
    """Control-vs-group mean differences and standardized effect sizes."""
    columns = [
        "control", "group", "column", "n_control", "n_group",
        "mean_control", "mean_group", "mean_difference", "percent_change",
        "cohen_d", "hedges_g", "hedges_g_ci_low", "hedges_g_ci_high",
    ]
    if not groups or len(groups) < 2 or not numeric_cols:
        return pd.DataFrame(columns=columns), None
    control_display, contrasts = _ovw_resolve_effect_control(groups, effect_control)
    group_map = {str(glabel): gidx for glabel, gidx, _spec in groups}

    rows = []
    for control_label, glabel in contrasts:
        ctrl_idx = group_map.get(control_label)
        gidx = group_map.get(glabel)
        if ctrl_idx is None or gidx is None:
            continue
        for col in numeric_cols:
            ctrl = pd.to_numeric(
                numeric_df.loc[numeric_df.index.intersection(ctrl_idx), col],
                errors="coerce",
            ).dropna().astype(float)
            vals = pd.to_numeric(
                numeric_df.loc[numeric_df.index.intersection(gidx), col],
                errors="coerce",
            ).dropna().astype(float)
            n_ctrl = int(len(ctrl))
            n_group = int(len(vals))
            if n_ctrl < int(min_n) or n_group < int(min_n):
                continue
            mean_ctrl = float(ctrl.mean())
            mean_group = float(vals.mean())
            diff = mean_group - mean_ctrl
            pct = (diff / abs(mean_ctrl)) * 100.0 if mean_ctrl != 0 else np.nan
            sd_ctrl = float(ctrl.std(ddof=1)) if n_ctrl >= 2 else np.nan
            sd_group = float(vals.std(ddof=1)) if n_group >= 2 else np.nan
            dfree = n_ctrl + n_group - 2
            if dfree > 0 and np.isfinite(sd_ctrl) and np.isfinite(sd_group):
                pooled = np.sqrt(
                    (((n_ctrl - 1) * sd_ctrl ** 2) + ((n_group - 1) * sd_group ** 2))
                    / dfree
                )
            else:
                pooled = np.nan
            if np.isfinite(pooled) and pooled > 0:
                cohen_d = diff / pooled
                correction = 1.0 - (3.0 / (4.0 * dfree - 1.0)) if dfree > 1 else 1.0
                hedges_g = cohen_d * correction
                se_d = np.sqrt(
                    ((n_ctrl + n_group) / (n_ctrl * n_group))
                    + (cohen_d ** 2 / (2.0 * max(dfree, 1)))
                )
                se_g = se_d * correction
                ci_low = hedges_g - 1.96 * se_g
                ci_high = hedges_g + 1.96 * se_g
            else:
                cohen_d = hedges_g = ci_low = ci_high = np.nan
            rows.append({
                "control": control_label,
                "group": glabel,
                "column": col,
                "n_control": n_ctrl,
                "n_group": n_group,
                "mean_control": mean_ctrl,
                "mean_group": mean_group,
                "mean_difference": diff,
                "percent_change": pct,
                "cohen_d": cohen_d,
                "hedges_g": hedges_g,
                "hedges_g_ci_low": ci_low,
                "hedges_g_ci_high": ci_high,
            })
    return pd.DataFrame(rows, columns=columns), control_display


@montage_pipeline(title="Data Overview Pipeline")
def data_overview(
    experiment,
    filtered_columns=None,
    by="all",
    factor=None,
    split_by=None,
    split_mode="cross",
    nest=False,
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
    include_condition_distributions=True,
    include_effect_sizes=True,
    outlier_methods=("rout",),
    iqr_k=1.5,
    mad_threshold=3.5,
    rout_q=1.0,
    covariation_method="pearsonr",
    covariation_threshold=0.9,
    min_n=3,
    alpha=0.05,
    plot_missingness=True,
    plot_covariation=True,
    plot_group_counts=True,
    plot_availability=True,
    plot_descriptives=True,
    plot_normality=True,
    plot_outliers=True,
    plot_covariation_pairs=True,
    plot_condition_distributions=True,
    plot_condition_distribution_zscores=True,
    plot_condition_fingerprint=True,
    plot_condition_variability=True,
    plot_effect_sizes=True,
    condition_distribution_plot="raincloud",
    fingerprint_stat="median",
    variability_stat="cv_pct",
    effect_control=None,
    max_plot_items=30,
    tick_label_size=20,
    run_label=None,
    if_exists="overwrite",
    write_manifest=True,
    verbose=True,
    montage=True,
    _run_dirs=None,
    _tag_specificity=False,
    _slug_specificity=None,
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
    - ``outliers`` — ROUT, Tukey IQR-fence, and/or modified-z (MAD) flags
      tagged by ``AnimalName``, plus a per-animal ``outlier_animals`` roll-up.
    - ``covariation`` — pooled pairwise |r| screen for redundant/collinear
      metrics, with the full ``covariation_matrix``.

    Saved figures mirror the tables: group counts, availability by condition,
    z-scored metric distributions, descriptive variability, normality hints,
    outlier roll-ups, covarying-pair bars, missingness, and the covariation
    matrix. Each figure class has a ``plot_*`` toggle, and ``max_plot_items``
    caps long ranked summaries.

    Column selection follows the usual convention: ``filtered_columns`` (explicit
    names) or ``column_strings`` / ``regex_string`` / ``exclude`` (discovery), and
    defaults to *all* summary columns so the inventory is complete. Numeric
    sections operate only on the columns that resolve to numeric values.

    ``by`` / ``factor`` panel the descriptive / normality / outlier sections by
    condition or factor level (``by='all'`` pools); covariation and the inventory
    are always pooled across the scope. ``specificity`` follows PyFLASH queue
    semantics (a list of tuples runs every filter into ONE shared run folder, each
    condition's tables/figures tagged with a concise specificity suffix in the
    filename, e.g. ``_Dx.AD``, with one combined overview montage).

    ``split_by`` is the multi-dimension successor to ``by``/``factor`` and, when
    given, takes precedence over both for the group-panelled sections (single-axis
    ``by``/``factor`` stays the default when ``split_by is None``). It is a key or
    a list of keys, each ``"Condition"`` or any summary column / factor:

    - ``split_by="Condition"`` reproduces ``by="conditions"`` exactly.
    - ``split_by=["Condition", "Sex"]`` with ``split_mode="cross"`` (default)
      panels the cartesian product first-key-major, with composite labels
      (``"WT | Male"``) over AND-intersected animals; empty product cells drop out.
    - ``split_mode="parallel"`` instead concatenates each axis independently, its
      labels prefixed by the key (``"Sex=Male"``) so the axes never collide.

    Levels order by design where declared (``condition_list`` / ``factorDict``) and
    otherwise first-seen (an ad-hoc key like ``Sex`` has no declared order).
    ``nest`` is a cosmetic flag reserved for the nested view; the ``cross`` order is
    already first-key-major, so it currently only distinguishes the run folder.

    ``effect_control`` names the effect-size baseline. With composite (crossed)
    labels the minimal rule is: an exact group-label match is the single control
    (name the composite in full, e.g. ``"WT | Male"``); otherwise a match against
    the FIRST split-key component makes it the control *per remaining-key stratum*
    (``effect_control="WT"`` -> ``"WT | Male"`` controls ``"KO | Male"`` and
    ``"WT | Female"`` controls ``"KO | Female"``); anything else raises ``ValueError``.

    Run management (``run_label`` / ``if_exists`` / ``save`` / ``write_manifest``)
    and the return shape (a manifest dict with the section DataFrames attached)
    mirror the other pipelines. Outputs land in
    ``Python Figures/Data Overview Pipeline/<run>/``.
    """
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            data_overview, experiment, specificity, kwargs, "data_overview",
            append_index=_ovw_append_runs_index)

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
        ("condition_distributions", include_condition_distributions),
        ("effect_sizes", include_effect_sizes),
    ) if on]

    label = run_label or _ovw_slug(
        resolved_columns, by, factor,
        (_slug_specificity if _slug_specificity is not None else specificity),
        _roi_base, sections,
        settings={
            "outlier_methods": tuple(str(m).lower() for m in (outlier_methods or ())),
            "iqr_k": float(iqr_k),
            "mad_threshold": float(mad_threshold),
            "rout_q": float(rout_q),
            "covariation_method": str(covariation_method),
            "covariation_threshold": float(covariation_threshold),
            "min_n": int(min_n),
            "alpha": float(alpha),
            "plot_missingness": bool(plot_missingness),
            "plot_covariation": bool(plot_covariation),
            "plot_group_counts": bool(plot_group_counts),
            "plot_availability": bool(plot_availability),
            "plot_descriptives": bool(plot_descriptives),
            "plot_normality": bool(plot_normality),
            "plot_outliers": bool(plot_outliers),
            "plot_covariation_pairs": bool(plot_covariation_pairs),
            "plot_condition_distributions": bool(plot_condition_distributions),
            "plot_condition_distribution_zscores": bool(plot_condition_distribution_zscores),
            "plot_condition_fingerprint": bool(plot_condition_fingerprint),
            "plot_condition_variability": bool(plot_condition_variability),
            "plot_effect_sizes": bool(plot_effect_sizes),
            "condition_distribution_plot": str(condition_distribution_plot),
            "fingerprint_stat": str(fingerprint_stat),
            "variability_stat": str(variability_stat),
            "effect_control": effect_control,
            "max_plot_items": max_plot_items,
            # Grouping-changing knobs: distinct splits land in distinct folders.
            "split_by": (split_by if isinstance(split_by, str)
                         else (list(split_by) if split_by is not None else None)),
            "split_mode": str(split_mode),
            "nest": bool(nest),
        },
    )
    if _run_dirs is not None:
        # Queue-merge: share the run folder a sibling condition already resolved.
        fig_dir, data_dir, resolved_label = _run_dirs
        reuse_existing = False
    else:
        fig_dir, data_dir, resolved_label, reuse_existing = _ovw_run_dirs(
            experiment, label, if_exists, clear_overwrite=bool(save))
    manifest_path = os.path.join(data_dir, "manifest.json")
    if reuse_existing and _corr_isfile(manifest_path):
        cached = _corr_read_json(manifest_path)
        _log.hint(f"[data_overview] Reusing run {resolved_label!r} (if_exists='skip').")
        cached["reused"] = True
        return cached
    # In queue-merge mode every output carries a concise specificity tag so the
    # conditions sharing this folder never overwrite each other.
    spec_tag = build_pipeline_suffix(
        specificity=(specificity if _tag_specificity else None),
        aliases=getattr(experiment, "aliases", None))

    if split_by is not None:
        # Multi-dimension splitting drives both group axes; single-axis
        # by/factor is preserved exactly when split_by is None.
        groups = _ovw_multi_groups(
            experiment, scope_df, num_df, split_by, split_mode, specificity)
        distribution_groups = groups
    else:
        groups = _corr_pipeline_groups(
            experiment, scope_df, num_df, by, factor, specificity)
        distribution_groups = _ovw_distribution_groups(
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
            outlier_methods, iqr_k, mad_threshold, rout_q)

    covarying = pd.DataFrame()
    covariation_pairs = pd.DataFrame()
    covariation_matrix = pd.DataFrame()
    if include_covariation and len(numeric_cols) >= 2:
        covarying, covariation_pairs, covariation_matrix = _ovw_covariation(
            num_df, numeric_cols, covariation_method,
            covariation_threshold, min_n)

    condition_distributions = pd.DataFrame()
    condition_fingerprint = pd.DataFrame()
    condition_variability = pd.DataFrame()
    if include_condition_distributions and numeric_cols:
        condition_distributions = _ovw_condition_distribution_stats(
            scope_df, num_df, numeric_cols, distribution_groups)
        condition_fingerprint = _ovw_condition_fingerprint(
            condition_distributions, stat=fingerprint_stat)
        condition_variability = _ovw_condition_variability(
            condition_distributions, stat=variability_stat)

    effect_sizes = pd.DataFrame()
    resolved_effect_control = None
    if include_effect_sizes and numeric_cols:
        effect_sizes, resolved_effect_control = _ovw_effect_sizes(
            num_df, numeric_cols, distribution_groups,
            effect_control=effect_control, min_n=min_n)

    # ── write tables + figures ──────────────────────────────────────────────
    if save:
        _corr_makedirs(data_dir)
        if include_inventory and not inventory.empty:
            _corr_to_csv(inventory, os.path.join(data_dir, f"column_inventory{spec_tag}.csv"),
                         index=False)
        if include_group_counts:
            if not group_counts.empty:
                _corr_to_csv(group_counts,
                             os.path.join(data_dir, f"group_counts{spec_tag}.csv"), index=False)
            if not availability.empty:
                _corr_to_csv(availability,
                             os.path.join(data_dir, f"availability_by_condition{spec_tag}.csv"))
        if include_descriptives and not descriptives.empty:
            _corr_to_csv(descriptives,
                         os.path.join(data_dir, f"descriptive_stats{spec_tag}.csv"), index=False)
        if include_normality and not normality.empty:
            _corr_to_csv(normality, os.path.join(data_dir, f"normality{spec_tag}.csv"),
                         index=False)
        if include_outliers:
            _corr_to_csv(outliers, os.path.join(data_dir, f"outliers{spec_tag}.csv"),
                         index=False)
            _corr_to_csv(outlier_animals,
                         os.path.join(data_dir, f"outlier_animals{spec_tag}.csv"), index=False)
        if include_covariation and not covariation_matrix.empty:
            _corr_to_csv(covarying,
                         os.path.join(data_dir, f"covariation_pairs{spec_tag}.csv"), index=False)
            _corr_to_csv(covariation_matrix,
                         os.path.join(data_dir, f"covariation_matrix{spec_tag}.csv"))
        if include_condition_distributions:
            _corr_to_csv(
                condition_distributions,
                os.path.join(data_dir, f"condition_distribution_stats{spec_tag}.csv"),
                index=False,
            )
            if not condition_fingerprint.empty:
                _corr_to_csv(
                    condition_fingerprint,
                    os.path.join(data_dir, f"condition_fingerprint{spec_tag}.csv"),
                )
            if not condition_variability.empty:
                _corr_to_csv(
                    condition_variability,
                    os.path.join(data_dir, f"condition_variability{spec_tag}.csv"),
                )
        if include_effect_sizes:
            _corr_to_csv(
                effect_sizes,
                os.path.join(data_dir, f"effect_sizes{spec_tag}.csv"),
                index=False,
            )

        if any((
            plot_group_counts, plot_availability, plot_descriptives,
            plot_normality, plot_outliers, plot_covariation_pairs,
            plot_condition_distributions, plot_condition_distribution_zscores,
            plot_condition_fingerprint, plot_condition_variability,
            plot_effect_sizes, plot_missingness, plot_covariation,
        )):
            _corr_makedirs(fig_dir)
        figure_numeric_cols = _ovw_numeric_figure_columns(numeric_cols, inventory)
        distribution_numeric_cols = _ovw_numeric_figure_columns(
            numeric_cols, inventory)
        if plot_group_counts and include_group_counts and not group_counts.empty:
            gfig = _ovw_group_counts_figure(
                group_counts, tick_label_size, max_plot_items)
            if gfig is not None:
                save_fig(gfig, fig_dir, f"Group Counts{spec_tag}", montage=True)
                plt.close(gfig)
        if plot_availability and include_group_counts and not availability.empty:
            plot_availability_df = (
                availability.loc[availability.index.intersection(figure_numeric_cols)]
                if figure_numeric_cols else availability
            )
            afig = _ovw_availability_figure(
                plot_availability_df, tick_label_size, max_plot_items)
            if afig is not None:
                save_fig(afig, fig_dir, f"Availability by Condition{spec_tag}", montage=True)
                plt.close(afig)
        if plot_descriptives and include_descriptives and figure_numeric_cols:
            dfig = _ovw_metric_distributions_figure(
                num_df, figure_numeric_cols, tick_label_size, max_plot_items)
            if dfig is not None:
                save_fig(dfig, fig_dir, f"Metric Distributions{spec_tag}", montage=True)
                plt.close(dfig)
            sfig = _ovw_descriptives_figure(
                descriptives[descriptives["column"].isin(figure_numeric_cols)]
                if not descriptives.empty and "column" in descriptives.columns
                else descriptives,
                tick_label_size, max_plot_items,
            )
            if sfig is not None:
                save_fig(sfig, fig_dir, f"Descriptive Summary{spec_tag}", montage=True)
                plt.close(sfig)
        if plot_normality and include_normality and not normality.empty:
            nfig = _ovw_normality_figure(
                normality[normality["column"].isin(figure_numeric_cols)]
                if figure_numeric_cols and "column" in normality.columns
                else normality,
                alpha, tick_label_size, max_plot_items,
            )
            if nfig is not None:
                save_fig(nfig, fig_dir, f"Normality Summary{spec_tag}", montage=True)
                plt.close(nfig)
        if plot_outliers and include_outliers:
            ofig = _ovw_outlier_summary_figure(
                outliers, outlier_animals, tick_label_size, max_plot_items)
            if ofig is not None:
                save_fig(ofig, fig_dir, f"Outlier Summary{spec_tag}", montage=True)
                plt.close(ofig)
        if plot_covariation_pairs and include_covariation:
            plot_covarying = covarying
            if (figure_numeric_cols and not covarying.empty
                    and {"x", "y"}.issubset(covarying.columns)):
                keep = set(figure_numeric_cols)
                plot_covarying = covarying[
                    covarying["x"].isin(keep) & covarying["y"].isin(keep)]
            pfig = _ovw_covariation_pairs_figure(
                plot_covarying, covariation_threshold, tick_label_size, max_plot_items)
            if pfig is not None:
                save_fig(pfig, fig_dir, f"Covariation Pairs{spec_tag}", montage=True)
                plt.close(pfig)
        if (plot_condition_distributions and include_condition_distributions
                and distribution_numeric_cols):
            rfig = _ovw_condition_distribution_figure(
                num_df, distribution_numeric_cols, distribution_groups,
                tick_label_size, max_plot_items,
                plot_kind=condition_distribution_plot,
                scale="raw",
            )
            if rfig is not None:
                save_fig(rfig, fig_dir, f"Condition Distributions{spec_tag}", montage=True)
                plt.close(rfig)
        if (plot_condition_distribution_zscores and include_condition_distributions
                and distribution_numeric_cols):
            zfig = _ovw_condition_distribution_figure(
                num_df, distribution_numeric_cols, distribution_groups,
                tick_label_size, max_plot_items,
                plot_kind=condition_distribution_plot,
                scale="zscore",
            )
            if zfig is not None:
                save_fig(zfig, fig_dir, f"Condition Distribution Z Scores{spec_tag}", montage=True)
                plt.close(zfig)
        if (plot_condition_fingerprint and include_condition_distributions
                and not condition_fingerprint.empty):
            ffig = _ovw_matrix_figure(
                condition_fingerprint,
                f"Condition fingerprint ({fingerprint_stat} z-score)",
                tick_label_size,
                max_plot_items,
                cmap="coolwarm",
                center_zero=True,
                colorbar_label="Z-score across groups",
            )
            if ffig is not None:
                save_fig(ffig, fig_dir, f"Condition Fingerprint{spec_tag}", montage=True)
                plt.close(ffig)
        if (plot_condition_variability and include_condition_distributions
                and not condition_variability.empty):
            vfig = _ovw_matrix_figure(
                condition_variability,
                f"Condition variability ({variability_stat})",
                tick_label_size,
                max_plot_items,
                cmap="YlOrRd",
                center_zero=False,
                colorbar_label=str(variability_stat),
            )
            if vfig is not None:
                save_fig(vfig, fig_dir, f"Condition Variability{spec_tag}", montage=True)
                plt.close(vfig)
        if plot_effect_sizes and include_effect_sizes and not effect_sizes.empty:
            # Shared forest renderer; the overview variant colours each row by its
            # group (palette) and labels rows "<group> vs <control> | <column>".
            _es_groups = effect_sizes["group"].astype(str).tolist()
            _es_palette = _ovw_group_palette(_es_groups)
            efig = _effect_forest_figure(
                effect_sizes, value_col=None, tick_label_size=tick_label_size,
                max_items=max_plot_items,
                ci_cols=("hedges_g_ci_low", "hedges_g_ci_high"),
                labels=[
                    f"{_ovw_short_label(r['group'], 16)} vs "
                    f"{_ovw_short_label(r['control'], 16)} | "
                    f"{_ovw_short_label(r['column'], 32)}"
                    for _, r in effect_sizes.iterrows()
                ],
                colors=[_es_palette[g] for g in _es_groups],
                xlabel="Hedges g (group - control)",
            )
            if efig is not None:
                save_fig(efig, fig_dir, f"Effect Size Forest{spec_tag}", montage=True)
                plt.close(efig)
        if plot_missingness:
            mfig = _ovw_missingness_figure(
                scope_df, resolved_columns, tick_label_size,
                "Data availability (animals x columns)")
            if mfig is not None:
                save_fig(mfig, fig_dir, f"Missingness Map{spec_tag}", montage=True)
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
            save_fig(cfig, fig_dir, f"Covariation Matrix{spec_tag}", montage=True)
            plt.close(cfig)

    n_outlier_animals = int(len(outlier_animals)) if outlier_animals is not None else 0
    n_covarying_pairs = int(len(covarying)) if covarying is not None else 0
    n_effect_sizes = int(len(effect_sizes)) if effect_sizes is not None else 0

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
        "split_by": (split_by if isinstance(split_by, str)
                     else (list(split_by) if split_by is not None else None)),
        "split_mode": str(split_mode) if split_by is not None else None,
        "nest": bool(nest),
        "groups": [str(g[0]) for g in groups],
        "condition_distribution_groups": [str(g[0]) for g in distribution_groups],
        "specificity": str(specificity) if specificity is not None else None,
        "roi": str(_roi_base) if _roi_base is not None else None,
        "outlier_methods": [str(m).lower() for m in (outlier_methods or ())],
        "iqr_k": float(iqr_k),
        "mad_threshold": float(mad_threshold),
        "rout_q": float(rout_q),
        "n_outliers": int(len(outliers)) if outliers is not None else 0,
        "n_outlier_animals": n_outlier_animals,
        "covariation_method": _correlation_display_name(
            _normalize_correlation_method(covariation_method)),
        "covariation_threshold": float(covariation_threshold),
        "n_covarying_pairs": n_covarying_pairs,
        "n_condition_distribution_rows": int(len(condition_distributions)),
        "n_effect_sizes": n_effect_sizes,
        "effect_control": resolved_effect_control,
        "alpha": float(alpha),
        "plots": {
            "group_counts": bool(plot_group_counts),
            "availability": bool(plot_availability),
            "descriptives": bool(plot_descriptives),
            "normality": bool(plot_normality),
            "outliers": bool(plot_outliers),
            "covariation_pairs": bool(plot_covariation_pairs),
            "condition_distributions": bool(plot_condition_distributions),
            "condition_distribution_zscores": bool(plot_condition_distribution_zscores),
            "condition_fingerprint": bool(plot_condition_fingerprint),
            "condition_variability": bool(plot_condition_variability),
            "effect_sizes": bool(plot_effect_sizes),
            "condition_distribution_plot": str(condition_distribution_plot),
            "fingerprint_stat": str(fingerprint_stat),
            "variability_stat": str(variability_stat),
            "missingness": bool(plot_missingness),
            "covariation": bool(plot_covariation),
            "max_plot_items": max_plot_items,
        },
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
            f"{n_covarying_pairs} covarying pairs, {n_effect_sizes} effect sizes."
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
    result["condition_distributions"] = condition_distributions
    result["condition_fingerprint"] = condition_fingerprint
    result["condition_variability"] = condition_variability
    result["effect_sizes"] = effect_sizes
    return result


# ── Group Comparison pipeline ────────────────────────────────────────────────
# The inferential sibling of data_overview's effect-size section. data_overview
# computes control-vs-group Hedges g DESCRIPTIVELY but runs no test;
# group_comparison adds the inferential layer: per marker it runs the correct test
# (animal = experimental unit), attaches the matched effect size + CI + power, and
# (only on an explicit `screen=True`) corrects across markers within each contrast.
# See docs/new_pipeline_plans/01_group_comparison.md and PREFERENCES.md.
#
# Multiplicity preference (PREFERENCES.md §2-3): different markers are distinct
# pre-specified endpoints, NOT a family, so the default is p-only — q is computed
# ONLY when the run is declared an exploratory screen. p is ALWAYS present; every
# q-bearing figure has a p counterpart.

_GC_PARAMETRIC_TESTS = {"Independent T-Test", "One-Way ANOVA", "Two-Way ANOVA"}


def _gc_run_dirs(experiment, run_label, if_exists, *, clear_overwrite=True):
    return _pio.run_dirs(experiment, "Group Comparison Pipeline", run_label,
                         if_exists, clear_overwrite=clear_overwrite)


def _gc_slug(columns, by, factor, specificity, roi, settings=None):
    payload = {
        "columns": sorted(str(c) for c in columns),
        "by": str(by),
        "factor": str(factor),
        "specificity": str(specificity),
        "roi": str(roi),
        "settings": settings or {},
    }
    return _pio.slug(f"groupcmp_{len(columns)}markers", payload)


def _gc_append_runs_index(experiment, manifest):
    """Append one summary row per group-comparison run to its shared index."""
    _pio.append_runs_index(experiment, "Group Comparison Pipeline", {
        "run_label": manifest.get("run_label"),
        "n_markers": manifest.get("n_markers"),
        "n_comparisons": manifest.get("n_comparisons"),
        "engine": manifest.get("engine"),
        "n_tests": manifest.get("n_tests"),
        "n_significant": manifest.get("n_significant"),
        "screen": manifest.get("screen"),
        "gate": manifest.get("gate"),
        "alpha": manifest.get("alpha"),
        "by": manifest.get("by"),
        "factor": manifest.get("factor"),
        "specificity": manifest.get("specificity"),
        "roi": manifest.get("roi"),
        "fig_dir": manifest.get("fig_dir"),
    })


def _gc_resolve_control(labels, control):
    """Resolve the reference/control group label (case-insensitive); None passes."""
    if control is None:
        return None
    target = str(control).strip().casefold()
    for label in labels:
        if str(label).strip().casefold() == target:
            return str(label)
    raise ValueError(f"control {control!r} is not one of {list(labels)}.")


def _gc_resolve_comparisons(comparisons, group_labels, control):
    """Return ordered, de-duplicated ``(reference, group)`` label pairs.

    ``reference`` is the control side; effect and %change are computed as
    ``group`` relative to ``reference`` (positive => group exceeds reference).
    Accepts ``"i-j"`` 1-based tokens or explicit ``(a, b)`` pairs. With no
    explicit comparisons: control-vs-each when a control is set, else all
    unordered pairs (first label of each pair as reference).
    """
    labels = [str(g) for g in group_labels]
    label_set = set(labels)
    ctrl = str(control) if control is not None else None
    pairs = []
    if comparisons:
        for comp in comparisons:
            if isinstance(comp, (tuple, list)) and len(comp) == 2:
                a, b = str(comp[0]), str(comp[1])
            else:
                toks = str(comp).split("-")
                if len(toks) != 2:
                    continue
                try:
                    ia, ib = int(toks[0]) - 1, int(toks[1]) - 1
                except ValueError:
                    continue
                if not (0 <= ia < len(labels) and 0 <= ib < len(labels)):
                    continue
                a, b = labels[ia], labels[ib]
            if a not in label_set or b not in label_set or a == b:
                continue
            # Put the control on the reference side when one side is the control.
            if ctrl is not None and b == ctrl and a != ctrl:
                a, b = b, a
            pairs.append((a, b))
    elif ctrl is not None and ctrl in label_set:
        pairs = [(ctrl, b) for b in labels if b != ctrl]
    else:
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                pairs.append((labels[i], labels[j]))
    seen, out = set(), []
    for p in pairs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _gc_group_arrays(num_df, col, groups):
    """Return ``{label: np.ndarray}`` of animal-level values for one column."""
    out = {}
    for glabel, gidx, _spec in groups:
        vals = pd.to_numeric(
            num_df.loc[num_df.index.intersection(gidx), col], errors="coerce"
        ).dropna().astype(float).to_numpy()
        out[str(glabel)] = vals
    return out


def _gc_marker_tokens(pairs, arrays, min_n):
    """For one marker, drop pairs whose either group has < ``min_n`` animals.

    Returns ``(involved_labels, tokens, surviving_pairs)`` where ``tokens`` are
    1-based ``"i-j"`` indices into ``involved_labels`` (the groups actually tested
    for this marker), aligned positionally to ``surviving_pairs``.
    """
    involved, surv = [], []
    for a, b in pairs:
        if len(arrays.get(a, ())) >= min_n and len(arrays.get(b, ())) >= min_n:
            for label in (a, b):
                if label not in involved:
                    involved.append(label)
            surv.append((a, b))
    tokens = [f"{involved.index(a) + 1}-{involved.index(b) + 1}" for a, b in surv]
    return involved, tokens, surv


def _gc_extract_auto(test, post_hoc, results_dict, tokens):
    """Parse omnibus + per-token pairwise p-values from a ``multipleComparisons``
    ``results_dict`` (pairwise p's are positional lists keyed by test/post-hoc)."""
    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return float("nan")

    omnibus = float("nan")
    pair_list = None
    if test == "Independent T-Test":
        entry = results_dict.get("Independent T Test")
        if entry is not None:
            omnibus = _f(entry[1])
            pair_list = [_f(entry[1])]
    elif test == "Mann-Whitney U":
        entry = results_dict.get("Mann-Whitney U")
        if entry is not None and isinstance(entry[1], (list, tuple)):
            pair_list = [_f(p) for p in entry[1]]
            omnibus = pair_list[0] if pair_list else float("nan")
    elif test == "One-Way ANOVA":
        omn = results_dict.get("OWA")
        if omn is not None:
            omnibus = _f(omn[1])
        tukey = results_dict.get("Tukey")
        if tukey is not None and isinstance(tukey[1], (list, tuple)):
            pair_list = [_f(p) for p in tukey[1]]
    elif test == "Kruskal-Wallis":
        kw = results_dict.get("KW")
        if kw is not None:
            omnibus = _f(kw[1])
        # post_hoc is e.g. "Conover Bonferroni"; the results_dict key is hyphenated.
        ph = results_dict.get(str(post_hoc).replace(" ", "-"))
        if ph is not None and isinstance(ph[1], (list, tuple)):
            pair_list = [_f(p) for p in ph[1]]
    if pair_list is None:
        pair_list = [float("nan")] * len(tokens)
    if len(pair_list) < len(tokens):
        pair_list = pair_list + [float("nan")] * (len(tokens) - len(pair_list))
    return omnibus, {tok: pair_list[i] for i, tok in enumerate(tokens)}


def _gc_effect(group_vals, ref_vals, *, parametric=True, ci=True, n_resamples=5000):
    """Animal-mean effect size (uniform across engines, per PREFERENCES.md / spec).

    Hedges g (+ bootstrap CI) is the common axis for every figure; rank-biserial
    is added when the chosen test was non-parametric.
    """
    from PyFLASH.stats_extra import (
        effect_ci, hedges_g, interpret_magnitude, rank_biserial,
    )

    g = float("nan")
    if len(group_vals) and len(ref_vals):
        g = float(hedges_g(group_vals, ref_vals))
    lo = hi = float("nan")
    if ci and np.isfinite(g):
        try:
            lo, hi = effect_ci(group_vals, ref_vals, "hedges", n_resamples=n_resamples)
            lo, hi = float(lo), float(hi)
        except Exception:
            lo = hi = float("nan")
    rb = float("nan")
    if not parametric and len(group_vals) and len(ref_vals):
        try:
            rb = float(rank_biserial(group_vals, ref_vals))
        except Exception:
            rb = float("nan")
    return {
        "hedges_g": g,
        "ci_low": lo,
        "ci_high": hi,
        "rank_biserial": rb,
        "interpretation": interpret_magnitude(g, "d") if np.isfinite(g) else "",
    }


def _gc_mixed_pair(roi_long, ref, group):
    """Two-sided p for ``group`` vs ``ref`` from a linear mixed model on ROI rows
    (animal as random intercept). NaN on singular / non-converged / failed fits
    so the caller falls the marker back to the animal-mean engine."""
    import warnings

    sub = roi_long[roi_long["group"].isin([ref, group])].copy()
    # Need >= 2 ROI-backed animals in EACH group for the random-effect model to be
    # estimable; otherwise return NaN so the marker falls back to the animal-mean
    # engine (a 1-vs-many animal split could otherwise fit a misleading p).
    per_group = sub.groupby("group")["AnimalName"].nunique()
    if int(per_group.get(ref, 0)) < 2 or int(per_group.get(group, 0)) < 2:
        return float("nan")
    sub["group"] = pd.Categorical(sub["group"], categories=[ref, group])
    try:
        import statsmodels.formula.api as smf

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = smf.mixedlm("value ~ C(group)", sub,
                              groups=sub["AnimalName"]).fit(reml=False, method="lbfgs")
        if not getattr(fit, "converged", True):
            return float("nan")
        # Match the fixed-effect condition contrast ("C(group)[T.<level>]"),
        # never the random-effect variance term ("Group Var").
        for name in fit.pvalues.index:
            if str(name).startswith("C(group)"):
                return float(fit.pvalues[name])
    except Exception:
        return float("nan")
    return float("nan")


def _gc_resample_hier(animal_arrays, rng):
    """One hierarchical-bootstrap replicate: resample animals, then ROIs within."""
    n = len(animal_arrays)
    means = []
    for k in rng.integers(0, n, n):
        arr = animal_arrays[k]
        means.append(float(arr[rng.integers(0, len(arr), len(arr))].mean()))
    return float(np.mean(means)) if means else float("nan")


def _gc_bootstrap_pair(roi_long, ref, group, n_boot, random_state):
    """Hierarchical bootstrap (animals then ROIs) for ``group`` vs ``ref``.

    Returns ``(p, ci_low, ci_high)`` for the raw mean difference (group - ref).
    """
    a = [g["value"].to_numpy()
         for _, g in roi_long[roi_long["group"] == ref].groupby("AnimalName")]
    b = [g["value"].to_numpy()
         for _, g in roi_long[roi_long["group"] == group].groupby("AnimalName")]
    a = [x for x in a if len(x)]
    b = [x for x in b if len(x)]
    if len(a) < 2 or len(b) < 2:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(random_state)
    diffs = np.empty(int(n_boot), dtype=float)
    for i in range(int(n_boot)):
        diffs[i] = _gc_resample_hier(b, rng) - _gc_resample_hier(a, rng)
    diffs = diffs[np.isfinite(diffs)]
    if len(diffs) == 0:
        return float("nan"), float("nan"), float("nan")
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    # Two-sided bootstrap p with the (count + 1) / (B + 1) finite-sample
    # correction, so a strong effect reports a small non-zero p, never exactly 0.
    b_n = len(diffs)
    n_le = int(np.sum(diffs <= 0.0))
    n_ge = int(np.sum(diffs >= 0.0))
    p = 2.0 * min((n_le + 1) / (b_n + 1), (n_ge + 1) / (b_n + 1))
    return float(min(1.0, p)), float(lo), float(hi)


def _gc_emit_record(metric, names, values, test, post_hoc, omnibus_p, tokens,
                    pair_list, normal):
    """Best-effort describe-layer emit (no-op unless PyFLASH.report is armed)."""
    try:
        import PyFLASH.report as report

        if not report.is_active():
            return
        report.emit(report.build_comparison_record(
            metric=metric, group_names=names, group_values=values,
            test=test, post_hoc=post_hoc,
            overall=(float("nan"), omnibus_p),
            comparisons=tokens, pairwise_pvalues=pair_list,
            effect_strings=[], raw_stats={}, normal=normal, factor_terms=None,
        ))
    except Exception:
        pass


@montage_pipeline(title="Group Comparison Pipeline")
def group_comparison(
    experiment,
    filtered_columns=None,
    column_strings=None,
    regex_string=None,
    exclude="",
    by="conditions",
    factor=None,
    specificity=None,
    roi=None,
    comparisons=None,
    control=None,
    engine="auto",
    force_nonparametric=False,
    posthoc="Conover",
    posthoc_correction="auto",
    n_boot=2000,
    random_state=0,
    screen=False,
    families="comparison",
    gate="p",
    alpha=0.05,
    effect_ci=True,
    n_resamples=5000,
    report_power=True,
    plot_volcano=True,
    plot_forest=True,
    plot_stats_matrix=True,
    plot_bars=True,
    plot_superplots=False,
    max_bar_markers=30,
    tick_label_size=20,
    min_n=3,
    run_label=None,
    if_exists="overwrite",
    save=True,
    write_manifest=True,
    montage=True,
    _run_dirs=None,
    _tag_specificity=False,
    _slug_specificity=None,
):
    """Per-marker group comparison across conditions, in one manifested run.

    For every numeric marker, the correct test is run across the chosen groups
    (the experimental unit is the **animal**), the matched animal-level effect
    size (Hedges g + bootstrap CI; rank-biserial for non-parametric tests) and
    achieved power are attached, and the run writes a results table, headline
    figures (volcano, effect-size forest, marker x contrast stats matrix), a
    SuperPlot per top marker (optional), secondary per-marker bar charts, a
    manifest, and an overview montage.

    Engines (``engine=``)
    ---------------------
    ``'auto'`` (default) tests animal-level summary values via the shared
    :func:`PyFLASH.stats.multipleComparisons` engine (auto parametric/
    non-parametric by normality) — identical to the per-marker bar charts.
    ``'mixed'`` fits a linear mixed model on ROI-level rows (animal as a random
    intercept) and ``'bootstrap'`` runs a hierarchical bootstrap; both are
    genuinely nested (no animal-mean collapse) and report ICC. When ROI-level
    data cannot be resolved for a marker, ``'mixed'``/``'bootstrap'`` fall back
    to the animal-mean ``'auto'`` test for that marker and note it.

    Multiplicity (``screen=`` / ``gate=``)
    --------------------------------------
    By default each marker stands on its own **raw p** — different markers are
    distinct endpoints, not a family. Pass ``screen=True`` to declare the run an
    exploratory screen: an FDR q-value is then added per contrast across markers
    (``families='comparison'``; pass a ``{marker: family}`` dict to customise).
    **p is always reported; every q figure has a p counterpart.** ``gate='p'``
    (default) flags significance (the ``significant`` column) on p; ``gate='fdr'``
    flags it on q and requires ``screen=True``. (Secondary bar charts are chosen
    by strongest |effect|, not by the gate.)

    Grouping follows the usual PyFLASH semantics (``by``/``factor``/
    ``specificity``/``roi`` + the specificity queue). Returns a dict manifest with
    the resolved run label, directories, per-(marker, contrast) records, and
    counts.

    Notes
    -----
    - Test selection for the ``'auto'`` engine routes through the shared
      :func:`PyFLASH.stats.multipleComparisons` engine (so the headline figures
      and the secondary bar charts agree). For exactly **two** groups it uses an
      independent two-sample t-test (the shared engine applies a heuristic
      equal-variance check to pick Student's vs Welch's; Mann-Whitney U only when
      a group has < 2 values);
      normality-based and ``force_nonparametric`` switching applies to designs
      with **>= 3** groups, where it picks One-Way ANOVA vs Kruskal-Wallis.
      Crossed (factorial) designs are compared as their condition groups
      (always one-way); true two-way interaction screening is left to a future
      pipeline.
    - The secondary per-marker bar charts show the engine's default (all-pairwise)
      brackets; the results table, volcano, forest and stats matrix are
      authoritative for the selected ``comparisons``/``control`` contrasts.
    """
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            group_comparison, experiment, specificity, kwargs, "group_comparison",
            append_index=_gc_append_runs_index)

    engine = str(engine).strip().lower()
    if engine not in ("auto", "mixed", "bootstrap"):
        raise ValueError(f"engine must be 'auto', 'mixed', or 'bootstrap'; got {engine!r}.")
    gate = str(gate).strip().lower()
    if gate not in ("p", "fdr"):
        raise ValueError(f"gate must be 'p' or 'fdr'; got {gate!r}.")
    if gate == "fdr" and not screen:
        raise ValueError(
            "gate='fdr' requires screen=True (no cross-marker q is computed "
            "otherwise — different markers are not a family by default).")

    _roi_base = _resolve_roi_bases(roi, experiment)[0]
    scope_df = _filtered_summary_for_specificity(experiment, specificity, roi_base=_roi_base)
    resolved_columns = _resolve_filtered_columns(
        experiment, filtered_columns=filtered_columns,
        column_strings=column_strings, regex_string=regex_string,
        exclude=exclude, source_df=scope_df,
    )
    num_df, numeric_cols, _dropped = _prepare_matrix_numeric_df(
        scope_df, resolved_columns, drop_duplicate_columns=False,
        require_complete_numeric=False,
    )
    if len(numeric_cols) < 1:
        raise ValueError(
            "group_comparison needs at least one numeric marker column with data; "
            f"got {len(numeric_cols)} after filtering.")

    groups = _corr_pipeline_groups(experiment, scope_df, num_df, by, factor, specificity)
    group_labels = [str(g[0]) for g in groups]
    if len(groups) < 2:
        raise ValueError(
            "group_comparison needs at least 2 groups to compare; got "
            f"{len(groups)} for by={by!r}, factor={factor!r}. Use a factor/by that "
            "splits the data into >= 2 groups.")
    control_label = _gc_resolve_control(group_labels, control)
    comp_source = comparisons
    if comp_source is None and factor is None:
        # Inherit the condition list's default comparisons ONLY when grouping by
        # condition. Those tokens index the condition_list, so resolve them to
        # explicit (name, name) label pairs (robust to group ordering). When a
        # ``factor`` defines the groups, its levels are not the condition_list, so
        # inheriting condition tokens would mis-map — fall through to
        # control-vs-each / all-pairs over the factor levels instead.
        cl = getattr(experiment, "condition_list", None)
        raw = getattr(cl, "comparisons", None)
        try:
            names = [str(getattr(c, "name", c)) for c in cl] if cl is not None else []
        except TypeError:  # condition_list isn't iterable
            names = []
        if raw and names:
            resolved = []
            for tok in raw:
                try:
                    i, j = (int(p) - 1 for p in str(tok).split("-"))
                except (ValueError, AttributeError):
                    continue
                if 0 <= i < len(names) and 0 <= j < len(names):
                    resolved.append((names[i], names[j]))
            comp_source = resolved or None
    pairs = _gc_resolve_comparisons(comp_source, group_labels, control_label)
    if not pairs:
        raise ValueError(
            "group_comparison resolved no group comparisons; check comparisons/"
            f"control against the groups {group_labels}.")

    label = run_label or _gc_slug(
        numeric_cols, by, factor,
        (_slug_specificity if _slug_specificity is not None else specificity),
        _roi_base,
        settings={
            "engine": engine, "screen": bool(screen), "families": str(families),
            "gate": gate, "alpha": float(alpha), "min_n": int(min_n),
            "control": control_label, "force_nonparametric": bool(force_nonparametric),
            "posthoc": str(posthoc), "posthoc_correction": str(posthoc_correction),
            "comparisons": [f"{a}|{b}" for a, b in pairs],
            "n_boot": int(n_boot),
        },
    )
    if _run_dirs is not None:
        fig_dir, data_dir, resolved_label = _run_dirs
        reuse_existing = False
    else:
        fig_dir, data_dir, resolved_label, reuse_existing = _gc_run_dirs(
            experiment, label, if_exists, clear_overwrite=bool(save))
    manifest_path = os.path.join(data_dir, "manifest.json")
    if reuse_existing and _corr_isfile(manifest_path):
        cached = _corr_read_json(manifest_path)
        _log.hint(f"[group_comparison] Reusing run {resolved_label!r} (if_exists='skip').")
        cached["reused"] = True
        return cached
    spec_tag = build_pipeline_suffix(
        specificity=(specificity if _tag_specificity else None),
        aliases=getattr(experiment, "aliases", None))

    # Map each in-scope animal to its comparison-group label so the nested (ROI)
    # engines + SuperPlots group by the SAME factor/condition as the animal-mean
    # engine, restricted to the specificity-filtered animals.
    animal_group_map = _animal_group_map_from_groups(scope_df, groups)

    def _run_auto(col, arrays, involved, tokens):
        from PyFLASH.stats import multipleComparisons

        # Name the per-group series so the auto-emitted describe record carries the
        # marker as its metric (multipleComparisons reads the series' .name).
        dfs = [pd.Series(arrays[l], name=str(col)) for l in involved]
        return multipleComparisons(
            experiment, dfs, None, None, None, None,
            multiple_comparison="One-Way", comparisons=tokens,
            force_nonparametric=force_nonparametric, posthoc=posthoc,
            posthoc_correction=posthoc_correction, group_labels=involved,
            save_normality=False, draw=False, verbose=False,
        )

    # ── Per-marker testing ──────────────────────────────────────────────────
    records, omnibus_rows, descriptive_rows, skipped = [], [], [], []
    n_fallback = 0
    for col in numeric_cols:
        arrays = _gc_group_arrays(num_df, col, groups)
        # Per-marker descriptives for every group with data (independent of the
        # comparison subset) -> group_descriptives.csv.
        for glabel in group_labels:
            v = arrays.get(glabel)
            if v is None or len(v) == 0:
                continue
            sd = float(np.std(v, ddof=1)) if len(v) >= 2 else float("nan")
            descriptive_rows.append({
                "marker": str(col), "group": glabel, "n": int(len(v)),
                "mean": float(np.mean(v)), "sd": sd,
                "sem": (sd / np.sqrt(len(v))) if np.isfinite(sd) else float("nan"),
                "median": float(np.median(v)),
            })

        involved, tokens, surv = _gc_marker_tokens(pairs, arrays, min_n)
        if not surv:
            skipped.append({"marker": str(col),
                            "reason": f"fewer than 2 groups with >= {int(min_n)} animals"})
            continue

        engine_used = engine
        marker_test = None
        omnibus_p = float("nan")
        icc_val = float("nan")
        pair_p = {}
        parametric = True
        fell_back = False
        fallback_reason = None

        # Nested engines first; fall the whole marker back to the animal-mean
        # engine when ROI data is absent OR the nested fit yields no usable p
        # (singular/non-converged/too few ROI animals).
        if engine in ("mixed", "bootstrap"):
            roi_long = _resolve_marker_roi_long(experiment, col, animal_group_map, _roi_base)
            if roi_long is None:
                engine_used, fell_back, fallback_reason = "auto", True, "no ROI data"
            else:
                try:
                    from PyFLASH.stats_extra import icc1

                    icc_val = float(icc1(roi_long, "value"))
                except Exception:
                    icc_val = float("nan")
                nested = {}
                for (ref, grp), tok in zip(surv, tokens):
                    if engine == "mixed":
                        nested[tok] = _gc_mixed_pair(roi_long, ref, grp)
                    else:
                        nested[tok], _lo, _hi = _gc_bootstrap_pair(
                            roi_long, ref, grp, n_boot, random_state)
                if nested and all(np.isfinite(v) for v in nested.values()):
                    marker_test = ("Linear Mixed Model" if engine == "mixed"
                                   else "Hierarchical Bootstrap")
                    pair_p = nested
                    _gc_emit_record(
                        str(col), involved, [arrays[l] for l in involved],
                        marker_test, "", omnibus_p, tokens,
                        [pair_p.get(t, float("nan")) for t in tokens], None)
                else:
                    # Fall back to the animal-mean test, but KEEP the ICC computed
                    # from the ROI rows — it still characterises the marker.
                    engine_used, fell_back = "auto", True
                    fallback_reason = "nested fit failed"

        if engine == "auto" or fell_back:
            try:
                test, post_hoc, _ann, results_dict = _run_auto(col, arrays, involved, tokens)
            except Exception as exc:
                _log.warn(f"[group_comparison] {col}: test failed ({exc}); skipped.")
                skipped.append({"marker": str(col), "reason": f"test error: {exc}"})
                continue
            if test in ("Error", "N/A"):
                skipped.append({"marker": str(col), "reason": f"test returned {test}"})
                continue
            omnibus_p, pair_p = _gc_extract_auto(test, post_hoc, results_dict, tokens)
            # Degenerate marker (constant / zero variance / post-hoc error): no
            # finite p anywhere -> record as skipped rather than emit NaN rows.
            if (not any(np.isfinite(v) for v in pair_p.values())
                    and not np.isfinite(omnibus_p)):
                skipped.append({"marker": str(col),
                                "reason": "no valid test result (constant/zero-variance or error)"})
                continue
            parametric = test in _GC_PARAMETRIC_TESTS
            marker_test = test if not fell_back else f"{test} (fallback: {fallback_reason})"
            if fell_back:
                n_fallback += 1
            # multipleComparisons already emits the describe record when armed.

        from PyFLASH.stats_extra import achieved_power, required_n

        marker_records = []
        for (ref, grp), tok in zip(surv, tokens):
            p = float(pair_p.get(tok, float("nan")))
            # A contrast with no usable p (e.g. a failed post-hoc cell) is dropped
            # rather than emitted as a NaN row.
            if not np.isfinite(p):
                continue
            gref, ggrp = arrays[ref], arrays[grp]
            eff = _gc_effect(ggrp, gref, parametric=parametric, ci=effect_ci,
                             n_resamples=n_resamples)
            mean_ref = float(np.mean(gref)) if len(gref) else float("nan")
            mean_grp = float(np.mean(ggrp)) if len(ggrp) else float("nan")
            pct = ((mean_grp - mean_ref) / abs(mean_ref) * 100.0
                   if np.isfinite(mean_ref) and mean_ref != 0 else float("nan"))
            power = (float(achieved_power(eff["hedges_g"], len(ggrp), len(gref), alpha))
                     if report_power else float("nan"))
            req_n = float("nan")
            if report_power and np.isfinite(eff["hedges_g"]):
                rn = required_n(eff["hedges_g"], alpha=alpha, power=0.8)
                req_n = float(np.ceil(rn)) if np.isfinite(rn) else float("nan")
            marker_records.append({
                "marker": str(col),
                "comparison": f"{grp} vs {ref}",
                "reference": ref,
                "group": grp,
                "test": marker_test,
                "engine": engine_used,
                "n_reference": int(len(gref)),
                "n_group": int(len(ggrp)),
                "mean_reference": mean_ref,
                "mean_group": mean_grp,
                "percent_change": pct,
                "hedges_g": eff["hedges_g"],
                "ci_low": eff["ci_low"],
                "ci_high": eff["ci_high"],
                "rank_biserial": eff["rank_biserial"],
                "interpretation": eff["interpretation"],
                "p": p,
                "omnibus_p": omnibus_p,
                "icc": icc_val,
                "achieved_power": power,
                "required_n_80": req_n,
            })

        if not marker_records:
            # Every contrast for this marker lacked a usable p (e.g. omnibus
            # finite but all post-hoc cells failed) -> skip rather than keep an
            # orphan omnibus row with no contrasts.
            skipped.append({"marker": str(col),
                            "reason": "no finite p for any contrast"})
            continue
        records.extend(marker_records)
        omnibus_rows.append({
            "marker": str(col), "test": marker_test, "engine": engine_used,
            "n_groups": len(involved), "omnibus_p": omnibus_p, "icc": icc_val,
        })

    res_df = pd.DataFrame(records)
    omnibus_df = pd.DataFrame(omnibus_rows)
    descriptives_df = pd.DataFrame(descriptive_rows)
    skipped_df = pd.DataFrame(skipped)

    # ── Multiplicity: cross-marker q ONLY in explicit screen mode ───────────
    has_q = False
    if screen and not res_df.empty:
        from PyFLASH.stats_extra import apply_fdr

        keys = [f"{r['marker']}||{r['comparison']}" for _, r in res_df.iterrows()]
        pvals = {k: float(p) for k, p in zip(keys, res_df["p"])}
        if isinstance(families, dict):
            fams = {f"{r['marker']}||{r['comparison']}":
                    str(families.get(r["marker"], "all")) for _, r in res_df.iterrows()}
        else:  # 'comparison' (default): one family per contrast across markers
            fams = {f"{r['marker']}||{r['comparison']}": str(r["comparison"])
                    for _, r in res_df.iterrows()}
        fdr = apply_fdr(pvals, families=fams, alpha=float(alpha))
        qmap = dict(zip(fdr["label"], fdr["p_adjusted"]))
        res_df["q"] = [qmap.get(k, float("nan")) for k in keys]
        has_q = True

    gate_col = "q" if gate == "fdr" else "p"
    if res_df.empty:
        res_df_significant = pd.Series([], dtype=bool)
    else:
        res_df["significant"] = (
            pd.to_numeric(res_df[gate_col], errors="coerce") < float(alpha))
        res_df_significant = res_df["significant"]
    n_significant = int(res_df_significant.sum()) if len(res_df_significant) else 0

    # ── Tables + figures ────────────────────────────────────────────────────
    value_cols = ["p"] + (["q"] if has_q else [])
    if save:
        _corr_makedirs(data_dir)
        _corr_to_csv(res_df, os.path.join(data_dir, f"group_comparison_results{spec_tag}.csv"),
                     index=False)
        _corr_to_csv(omnibus_df, os.path.join(data_dir, f"omnibus{spec_tag}.csv"), index=False)
        _corr_to_csv(descriptives_df,
                     os.path.join(data_dir, f"group_descriptives{spec_tag}.csv"), index=False)
        if not skipped_df.empty:
            _corr_to_csv(skipped_df, os.path.join(data_dir, f"skipped_markers{spec_tag}.csv"),
                         index=False)
        _corr_makedirs(fig_dir)
        if not res_df.empty:
            if plot_volcano:
                for vc in value_cols:
                    for comp in list(dict.fromkeys(res_df["comparison"])):
                        sub = res_df[res_df["comparison"] == comp]
                        vfig = _volcano_table_figure(
                            sub, vc, alpha,
                            f"Volcano: {comp}  ({'q' if vc == 'q' else 'p'})",
                            tick_label_size)
                        if vfig is not None:
                            save_fig(vfig, fig_dir, f"Volcano {comp} {vc}{spec_tag}",
                                     subfolder="Volcano", montage=True)
                            plt.close(vfig)
            if plot_forest:
                for vc in value_cols:
                    ffig = _effect_forest_figure(res_df, vc, alpha, tick_label_size,
                                             max_bar_markers)
                    if ffig is not None:
                        save_fig(ffig, fig_dir, f"Effect Size Forest {vc}{spec_tag}",
                                 montage=True)
                        plt.close(ffig)
            if plot_stats_matrix:
                for vc in value_cols:
                    mfig = _stats_matrix_figure(res_df, vc, alpha, tick_label_size)
                    if mfig is not None:
                        save_fig(mfig, fig_dir, f"Stats Matrix {vc}{spec_tag}",
                                 montage=True)
                        plt.close(mfig)
            # SuperPlots (optional, ROI-grain) for the strongest markers.
            if plot_superplots:
                ranked = (res_df.assign(_abs=res_df["hedges_g"].abs())
                          .sort_values("_abs", ascending=False, kind="mergesort"))
                seen_markers = []
                with capture_secondary("superplots"):
                    for m in ranked["marker"]:
                        if m in seen_markers:
                            continue
                        seen_markers.append(m)
                        if max_bar_markers is not None and len(seen_markers) > int(max_bar_markers):
                            break
                        roi_long = _resolve_marker_roi_long(experiment, m, animal_group_map, _roi_base)
                        if roi_long is None:
                            continue
                        sfig = _superplot_figure(roi_long, group_labels, m, tick_label_size)
                        if sfig is not None:
                            save_fig(sfig, fig_dir, f"SuperPlot {m}{spec_tag}",
                                     subfolder="SuperPlots")
                            plt.close(sfig)
            # Secondary per-marker bar charts (strongest |g| first), capped.
            if plot_bars:
                ranked = (res_df.assign(_abs=res_df["hedges_g"].abs())
                          .sort_values("_abs", ascending=False, kind="mergesort"))
                sel_markers = []
                for m in ranked["marker"]:
                    if m not in sel_markers:
                        sel_markers.append(m)
                if max_bar_markers is not None:
                    sel_markers = sel_markers[:int(max_bar_markers)]
                from PyFLASH.plotting import plot_mean_bars

                orig_fig_path = getattr(experiment, "fig_path", None)
                with capture_secondary("bars"):
                    for m in sel_markers:
                        try:
                            experiment.fig_path = fig_dir
                            plot_mean_bars(
                                experiment, filtered_columns=[m], by=by, factor=factor,
                                specificity=specificity,
                                roi=_roi_base, force_nonparametric=force_nonparametric,
                                posthoc=posthoc, posthoc_correction=posthoc_correction,
                                save=True, save_normality=False,
                            )
                        except Exception as exc:
                            _log.warn(f"[group_comparison] bar chart {m} failed: {exc}")
                        finally:
                            if orig_fig_path is not None:
                                experiment.fig_path = orig_fig_path

    distinct_tests = list(dict.fromkeys(
        omnibus_df["test"].astype(str))) if not omnibus_df.empty else []
    comparisons_out = [f"{b} vs {a}" for a, b in pairs]
    manifest = {
        "run_label": resolved_label,
        "fig_dir": fig_dir,
        "data_dir": data_dir,
        "pipeline": "group_comparison",
        "n_rows": int(len(num_df)),
        "engine": engine,
        "screen": bool(screen),
        "families": str(families),
        "gate": gate,
        "alpha": float(alpha),
        "min_n": int(min_n),
        "by": str(by),
        "factor": factor,
        "specificity": str(specificity) if specificity is not None else None,
        "roi": str(_roi_base) if _roi_base is not None else None,
        "control": control_label,
        "markers": [str(c) for c in numeric_cols],
        "n_markers": int(len(numeric_cols)),
        "comparisons": comparisons_out,
        "n_comparisons": int(len(pairs)),
        "groups": [{"group": str(g[0]), "n_rows": int(len(num_df.index.intersection(g[1])))}
                   for g in groups],
        "n_tests": int(len(res_df)),
        "n_significant": n_significant,
        "n_fallback_markers": int(n_fallback),
        "n_skipped_markers": int(len(skipped)),
        "tests": distinct_tests,
        "has_q": bool(has_q),
        "force_nonparametric": bool(force_nonparametric),
        # Digest-friendly aliases (report._digest_pipeline reads these).
        "n_pairs": int(len(res_df)),
        "n_selected": n_significant,
        "selected_pairs": (
            [{"x": str(r["marker"]), "y": str(r["comparison"]),
              "r": float(r["hedges_g"]) if np.isfinite(r["hedges_g"]) else None}
             for _, r in res_df[res_df_significant].iterrows()]
            if (len(res_df_significant) and n_significant) else []),
        "reused": False,
    }
    if save and write_manifest:
        _corr_write_json(manifest, manifest_path)
        _gc_append_runs_index(experiment, manifest)

    _log.confirm(
        f"[group_comparison] {resolved_label}: {len(numeric_cols)} markers x "
        f"{len(pairs)} contrasts via {engine}, {len(res_df)} tests, "
        f"{n_significant} significant ({gate}<{alpha}), {len(skipped)} skipped."
    )
    result = dict(manifest)
    result["results_table"] = res_df
    result["omnibus"] = omnibus_df
    result["descriptives"] = descriptives_df
    result["skipped"] = skipped_df
    return result


def _lm_run_dirs(experiment, run_label, if_exists, *, clear_overwrite=True):
    return _pio.run_dirs(experiment, "Linear Model Pipeline", run_label, if_exists,
                         clear_overwrite=clear_overwrite)


def _lm_slug(dependent_variables, group, predictors, specificity, roi, settings=None):
    return _pio.slug("linear_model", {
        "dependent_variables": list(dependent_variables or []),
        "group": group,
        "predictors": list(predictors or []),
        "specificity": str(specificity),
        "roi": str(roi),
        "settings": settings or {},
    })


def _lm_append_runs_index(experiment, manifest):
    _pio.append_runs_index(experiment, "Linear Model Pipeline", {
        "run_label": manifest.get("run_label"),
        "pipeline": "linear_model",
        "n_rows": manifest.get("n_rows"),
        "n_models": manifest.get("n_models"),
        "n_adjusted_means": manifest.get("n_adjusted_means"),
        "dependent_variables": "; ".join(manifest.get("dependent_variables", [])),
        "group": manifest.get("group"),
        "predictors": "; ".join(manifest.get("predictors", [])),
        "specificity": manifest.get("specificity"),
        "roi": manifest.get("roi"),
    })


def _lm_unique(values):
    seen = set()
    out = []
    for value in values or []:
        s = str(value)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _lm_as_list(value, *, name):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, pd.Index, np.ndarray, pd.Series)):
        return [str(v) for v in list(value) if str(v).strip() != ""]
    raise TypeError(f"{name} must be a string or iterable of strings.")


def _lm_resolve_terms(df, terms, *, kind):
    resolved = []
    for term in _lm_as_list(terms, name=kind):
        col = _resolve_summary_column(df, term, required=False)
        resolved.append(str(col) if col is not None else str(term))
    return _lm_unique(resolved)


def _lm_categorical_arg(df, predictors, categorical, group_col):
    if isinstance(categorical, str) and categorical.strip().lower() == "auto":
        resolved = []
        for pred in predictors:
            if pred not in df.columns:
                continue
            col = df[pred]
            if (
                _adj_auto_is_categorical(col)
                or isinstance(col.dtype, pd.CategoricalDtype)
                or pd.api.types.is_bool_dtype(col)
            ):
                resolved.append(pred)
    elif categorical is None:
        resolved = []
    else:
        resolved = [
            str(_resolve_summary_column(df, col, required=True))
            for col in _lm_as_list(categorical, name="categorical")
        ]
    if group_col is not None:
        resolved.insert(0, group_col)
    return _lm_unique(resolved)


def _lm_mode(series):
    values = pd.Series(series).dropna()
    if values.empty:
        return np.nan
    try:
        mode = values.mode(dropna=True)
        if len(mode):
            return mode.iloc[0]
    except Exception:
        pass
    return values.iloc[0]


def _lm_group_order(experiment, frame, group_col):
    levels = list(pd.Series(frame[group_col]).dropna().unique())
    if not levels:
        return []
    wanted = []
    if str(group_col) == "Condition":
        wanted.extend([
            getattr(c, "name", c)
            for c in getattr(experiment, "condition_list", []) or []
        ])
    factor_dict = getattr(getattr(experiment, "condition_list", None), "factorDict", {})
    if isinstance(factor_dict, dict) and group_col in factor_dict:
        wanted.extend([
            getattr(item, "name", item)
            for item in factor_dict.get(group_col, []) or []
        ])
    ordered = []
    for want in wanted:
        match = next((level for level in levels if str(level) == str(want)), None)
        if match is not None and match not in ordered:
            ordered.append(match)
    ordered.extend([level for level in levels if level not in ordered])
    return ordered


def _lm_group_colors(experiment, group_col):
    colors = {}
    if str(group_col) == "Condition":
        for c in getattr(experiment, "condition_list", []) or []:
            colors[str(getattr(c, "name", c))] = getattr(c, "color", "black")
    factor_dict = getattr(getattr(experiment, "condition_list", None), "factorDict", {})
    if isinstance(factor_dict, dict) and group_col in factor_dict:
        for item in factor_dict.get(group_col, []) or []:
            colors[str(getattr(item, "name", item))] = getattr(item, "color", "black")
    return colors


def _lm_covariate_profile_key(covariate_profile):
    profile = str(covariate_profile).strip().lower().replace("-", "_")
    aliases = {
        "mean/mode": "mean_mode",
        "mean_mode": "mean_mode",
        "reference_grid": "reference_grid",
        "ref_grid": "reference_grid",
        "emm": "reference_grid",
        "emms": "reference_grid",
        "emmeans": "reference_grid",
        "estimated_marginal_means": "reference_grid",
        "observed": "observed",
        "observed_marginal": "observed",
        "sample": "observed",
        "standardized": "observed",
        "g_computation": "observed",
        "counterfactual": "observed",
    }
    if profile in aliases:
        return aliases[profile]
    raise ValueError(
        "covariate_profile must be 'mean_mode', 'reference_grid'/'emm', "
        "or 'observed'."
    )


def _lm_weight_key(weights):
    key = str(weights).strip().lower().replace("-", "_")
    aliases = {
        "equal": "equal",
        "balanced": "equal",
        "observed": "observed",
        "sample": "observed",
        "proportional": "observed",
        "cells": "observed",
        "cell": "observed",
    }
    if key in aliases:
        return aliases[key]
    raise ValueError("adjusted_mean_weights must be 'equal' or 'observed'.")


def _lm_is_categorical_column(model_df, col, categorical_set):
    if col in categorical_set:
        return True
    series = model_df[col]
    return (
        pd.api.types.is_object_dtype(series)
        or isinstance(series.dtype, pd.CategoricalDtype)
        or pd.api.types.is_bool_dtype(series)
    )


def _lm_observed_levels(series):
    if isinstance(series.dtype, pd.CategoricalDtype):
        values = [
            level for level in series.cat.categories
            if pd.Series(series).astype(object).eq(level).any()
        ]
    else:
        values = list(pd.Series(series).dropna().unique())
    return [value for value in values if not pd.isna(value)]


def _lm_prediction_frame(model_df, dependent_variable, group_col, level,
                         categorical_set, reference_levels):
    row = {}
    for col in model_df.columns:
        if col == dependent_variable:
            vals = _to_numeric_excluding_not_included(model_df[col])
            row[col] = float(vals.mean(skipna=True)) if vals.notna().any() else 0.0
            continue
        if col == group_col:
            row[col] = level
            continue
        series = model_df[col]
        if (
            col in categorical_set
            or pd.api.types.is_object_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype)
            or pd.api.types.is_bool_dtype(series)
        ):
            row[col] = reference_levels.get(col, _lm_mode(series))
        else:
            vals = _to_numeric_excluding_not_included(series)
            row[col] = float(vals.mean(skipna=True)) if vals.notna().any() else _lm_mode(series)
    pred = pd.DataFrame([row])
    for col in pred.columns:
        if col in model_df.columns and isinstance(model_df[col].dtype, pd.CategoricalDtype):
            pred[col] = pd.Categorical(pred[col], categories=model_df[col].cat.categories)
    return pred


def _lm_apply_model_categories(pred, model_df):
    pred = pred.copy()
    for col in pred.columns:
        if col in model_df.columns and isinstance(model_df[col].dtype, pd.CategoricalDtype):
            pred[col] = pd.Categorical(pred[col], categories=model_df[col].cat.categories)
    return pred


def _lm_reference_grid_frame(model_df, dependent_variable, group_col, level,
                             categorical_set, reference_levels, grid_columns=None):
    from itertools import product

    grid_columns = set(grid_columns or [])
    cat_cols = [
        col for col in model_df.columns
        if col in grid_columns
        and col not in {dependent_variable, group_col}
        and _lm_is_categorical_column(model_df, col, categorical_set)
    ]
    levels_by_col = []
    for col in cat_cols:
        levels = _lm_observed_levels(model_df[col])
        if not levels:
            levels = [reference_levels.get(col, _lm_mode(model_df[col]))]
        levels_by_col.append(levels)
    combos = list(product(*levels_by_col)) if levels_by_col else [()]

    rows = []
    for combo in combos:
        row = {}
        combo_map = dict(zip(cat_cols, combo))
        for col in model_df.columns:
            if col == dependent_variable:
                vals = _to_numeric_excluding_not_included(model_df[col])
                row[col] = float(vals.mean(skipna=True)) if vals.notna().any() else 0.0
            elif col == group_col:
                row[col] = level
            elif col in combo_map:
                row[col] = combo_map[col]
            elif _lm_is_categorical_column(model_df, col, categorical_set):
                row[col] = reference_levels.get(col, _lm_mode(model_df[col]))
            else:
                vals = _to_numeric_excluding_not_included(model_df[col])
                row[col] = float(vals.mean(skipna=True)) if vals.notna().any() else _lm_mode(model_df[col])
        rows.append(row)
    frame = _lm_apply_model_categories(pd.DataFrame(rows), model_df)
    return frame, cat_cols


def _lm_reference_grid_weights(model_df, frame, cat_cols, weight_key):
    if len(frame) == 0:
        return np.asarray([], dtype=float)
    if weight_key == "equal" or not cat_cols:
        return np.repeat(1.0 / len(frame), len(frame))

    observed = model_df[cat_cols].dropna()
    if observed.empty:
        return np.repeat(1.0 / len(frame), len(frame))
    counts = observed.groupby(cat_cols, dropna=False).size()
    weights = []
    for _, row in frame[cat_cols].iterrows():
        key = tuple(row[col] for col in cat_cols)
        if len(cat_cols) == 1:
            key = key[0]
        weights.append(float(counts.get(key, 0.0)))
    weights = np.asarray(weights, dtype=float)
    total = float(weights.sum())
    if total <= 0 or not np.isfinite(total):
        return np.repeat(1.0 / len(frame), len(frame))
    return weights / total


def _lm_observed_profile_frame(model_df, dependent_variable, group_col, level):
    frame = model_df.copy()
    frame[group_col] = level
    return _lm_apply_model_categories(frame, model_df)


def _lm_design_matrix(fit, frame):
    from patsy import build_design_matrices

    design_info = getattr(getattr(fit.model, "data", None), "design_info", None)
    if design_info is None:
        return None, None
    exog = build_design_matrices([design_info], frame, return_type="dataframe")[0]
    params_index = list(fit.params.index)
    exog = exog.reindex(columns=params_index, fill_value=0.0)
    return exog.to_numpy(dtype=float), params_index


def _lm_linear_function_summary(fit, linvec, *, alpha):
    params_index = list(fit.params.index)
    params = np.asarray(fit.params.reindex(params_index), dtype=float)
    cov = fit.cov_params()
    if hasattr(cov, "loc"):
        cov = cov.loc[params_index, params_index]
    cov = np.asarray(cov, dtype=float)
    linvec = np.asarray(linvec, dtype=float)

    estimate = float(np.dot(linvec, params))
    variance = float(np.dot(linvec, np.dot(cov, linvec)))
    std_error = float(np.sqrt(max(variance, 0.0))) if np.isfinite(variance) else np.nan
    df_resid = float(getattr(fit, "df_resid", np.nan))
    use_t = bool(getattr(fit, "use_t", True))
    statistic = np.nan
    p_value = np.nan
    ci_low = np.nan
    ci_high = np.nan
    distribution = "normal"
    if std_error > 0:
        statistic = estimate / std_error
        try:
            if use_t and np.isfinite(df_resid):
                from scipy import stats as sp_stats
                crit = float(sp_stats.t.ppf(1.0 - float(alpha) / 2.0, df_resid))
                p_value = float(2.0 * sp_stats.t.sf(abs(statistic), df_resid))
                distribution = "t"
            else:
                from scipy import stats as sp_stats
                crit = float(sp_stats.norm.ppf(1.0 - float(alpha) / 2.0))
                p_value = float(2.0 * sp_stats.norm.sf(abs(statistic)))
            ci_low = estimate - crit * std_error
            ci_high = estimate + crit * std_error
        except Exception:
            pass
    return {
        "estimate": estimate,
        "std_error": std_error,
        "ci_low": float(ci_low) if np.isfinite(ci_low) else np.nan,
        "ci_high": float(ci_high) if np.isfinite(ci_high) else np.nan,
        "statistic": float(statistic) if np.isfinite(statistic) else np.nan,
        "p_value": float(p_value) if np.isfinite(p_value) else np.nan,
        "df_resid": df_resid,
        "reference_distribution": distribution,
    }


def _lm_adjusted_prediction_data(experiment, fit_result, dependent_variable, group_col,
                                 *, covariate_profile, adjusted_mean_weights, alpha):
    profile = _lm_covariate_profile_key(covariate_profile)
    weight_key = _lm_weight_key(adjusted_mean_weights)
    fits = fit_result.get("fits") or {}
    fit = fits.get(dependent_variable)
    if fit is None:
        return None
    model_data = getattr(getattr(fit, "model", None), "data", None)
    model_df = getattr(model_data, "frame", None)
    if not isinstance(model_df, pd.DataFrame) or group_col not in model_df.columns:
        return None
    categorical_set = set(fit_result.get("categorical") or [])
    reference_levels = dict(fit_result.get("reference_levels") or {})
    predictor_columns = [
        str(col) for col in (fit_result.get("predictors") or [])
        if str(col) in model_df.columns and str(col) != group_col
    ]
    levels = _lm_group_order(experiment, model_df, group_col)
    if not levels:
        return None
    functions = []
    pred_frames = []
    for level in levels:
        if profile == "mean_mode":
            frame = _lm_prediction_frame(
                model_df, dependent_variable, group_col, level,
                categorical_set, reference_levels,
            )
            weights = np.asarray([1.0], dtype=float)
            grid_columns = []
        elif profile == "reference_grid":
            frame, grid_columns = _lm_reference_grid_frame(
                model_df, dependent_variable, group_col, level,
                categorical_set, reference_levels,
                grid_columns=predictor_columns,
            )
            weights = _lm_reference_grid_weights(model_df, frame, grid_columns, weight_key)
        else:
            frame = _lm_observed_profile_frame(model_df, dependent_variable, group_col, level)
            weights = np.repeat(1.0 / len(frame), len(frame)) if len(frame) else np.asarray([], dtype=float)
            grid_columns = list(predictor_columns)
        if len(frame) == 0 or len(weights) != len(frame):
            continue
        weights = np.asarray(weights, dtype=float)
        total = float(weights.sum())
        if total <= 0 or not np.isfinite(total):
            weights = np.repeat(1.0 / len(frame), len(frame))
        else:
            weights = weights / total
        xmat, _ = _lm_design_matrix(fit, frame)
        if xmat is None:
            continue
        linvec = np.average(xmat, axis=0, weights=weights)
        summary = _lm_linear_function_summary(fit, linvec, alpha=alpha)
        functions.append({
            "level": level,
            "pred_df": frame,
            "weights": weights,
            "linvec": linvec,
            "summary": summary,
            "grid_columns": list(grid_columns),
        })
        pred_frames.append(frame.assign(_pyflash_lm_group=str(level)))
    if not functions:
        return None
    pred_summary = pd.DataFrame([
        {
            "mean": item["summary"]["estimate"],
            "mean_se": item["summary"]["std_error"],
            "mean_ci_lower": item["summary"]["ci_low"],
            "mean_ci_upper": item["summary"]["ci_high"],
        }
        for item in functions
    ])
    return {
        "fit": fit,
        "model_df": model_df,
        "levels": [item["level"] for item in functions],
        "pred_df": pd.concat(pred_frames, ignore_index=True) if pred_frames else pd.DataFrame(),
        "pred_summary": pred_summary,
        "linear_functions": functions,
        "profile": profile,
        "weights": weight_key,
    }


def _lm_adjusted_means_table(experiment, fit_result, dependent_variables, group_col,
                             *, covariate_profile, adjusted_mean_weights, alpha):
    rows = []
    for dep in dependent_variables:
        pred = _lm_adjusted_prediction_data(
            experiment, fit_result, dep, group_col,
            covariate_profile=covariate_profile,
            adjusted_mean_weights=adjusted_mean_weights,
            alpha=alpha,
        )
        if pred is None:
            continue
        model_df = pred["model_df"]
        for item in pred["linear_functions"]:
            level = item["level"]
            mask = model_df[group_col].astype(str).eq(str(level))
            raw_values = _to_numeric_excluding_not_included(model_df.loc[mask, dep])
            summary = item["summary"]
            rows.append({
                "dependent_variable": str(dep),
                "group_col": str(group_col),
                "group": str(level),
                "n": int(mask.sum()),
                "raw_mean": (
                    float(raw_values.mean(skipna=True))
                    if raw_values.notna().any() else float("nan")
                ),
                "adjusted_mean": float(summary.get("estimate", np.nan)),
                "mean_se": float(summary.get("std_error", np.nan)),
                "ci_low": float(summary.get("ci_low", np.nan)),
                "ci_high": float(summary.get("ci_high", np.nan)),
                "alpha": float(alpha),
                "covariate_profile": pred["profile"],
                "adjusted_mean_weights": pred["weights"],
                "reference_grid_rows": int(len(item["pred_df"])),
                "reference_grid_columns": "; ".join(item["grid_columns"]),
            })
    return pd.DataFrame(rows)


def _lm_default_comparisons(num_groups):
    comps = []
    for gap in range(1, int(num_groups)):
        for first in range(1, int(num_groups) - gap + 1):
            comps.append(f"{first}-{first + gap}")
    return comps


def _lm_sanitize_comparisons(comparisons, n_groups):
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
        token = f"{min(first, second)}-{max(first, second)}"
        if token not in seen:
            valid.append(token)
            seen.add(token)
    return valid


def _lm_adjusted_mean_comparisons_table(
    experiment, fit_result, dependent_variables, group_col,
    *,
    covariate_profile,
    adjusted_mean_weights,
    adjusted_mean_p_adjust,
    adjusted_mean_p_family,
    alpha,
    comparisons=None,
):
    rows = []
    for dep in dependent_variables:
        pred = _lm_adjusted_prediction_data(
            experiment, fit_result, dep, group_col,
            covariate_profile=covariate_profile,
            adjusted_mean_weights=adjusted_mean_weights,
            alpha=alpha,
        )
        if pred is None:
            continue
        fit = pred["fit"]
        levels = [str(level) for level in pred["levels"]]
        n_groups = len(levels)
        comp_tokens = _lm_sanitize_comparisons(comparisons, n_groups)
        if not comp_tokens:
            default_from_conditions = getattr(
                getattr(experiment, "condition_list", None), "comparisons", None)
            comp_tokens = _lm_sanitize_comparisons(default_from_conditions, n_groups)
        if not comp_tokens and n_groups >= 2:
            comp_tokens = _lm_default_comparisons(n_groups)
        if not comp_tokens:
            continue
        linvecs = [np.asarray(item["linvec"], dtype=float) for item in pred["linear_functions"]]
        for comp in comp_tokens:
            first, second = [int(part) - 1 for part in comp.split("-")]
            if first < 0 or second < 0 or first >= n_groups or second >= n_groups:
                continue
            contrast = linvecs[second] - linvecs[first]
            summary = _lm_linear_function_summary(fit, contrast, alpha=alpha)
            rows.append({
                "dependent_variable": str(dep),
                "group_col": str(group_col),
                "comparison": comp,
                "left_group": levels[first],
                "right_group": levels[second],
                "estimate": summary["estimate"],
                "std_error": summary["std_error"],
                "t_value": summary["statistic"],
                "p_value": summary["p_value"],
                "df_resid": summary["df_resid"],
                "alpha": float(alpha),
                "test": "Adjusted linear contrast",
                "covariate_profile": pred["profile"],
                "adjusted_mean_weights": pred["weights"],
                "reference_distribution": summary["reference_distribution"],
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    method = str(adjusted_mean_p_adjust).strip().lower().replace("-", "_")
    if method in {"", "none", "no", "false", "raw", "uncorrected"}:
        out["p_adjusted"] = pd.to_numeric(out["p_value"], errors="coerce")
        out["reject_adjusted"] = out["p_adjusted"] <= float(alpha)
        out["p_adjust_method"] = "none"
        return out
    family_key = str(adjusted_mean_p_family).strip().lower()
    if family_key in {"dependent_variable", "by_dependent_variable", "by_endpoint", "endpoint"}:
        families = out["dependent_variable"].astype(str).tolist()
    else:
        families = ["all"] * len(out)
    try:
        from PyFLASH.stats_extra import apply_fdr
        adjusted = apply_fdr(
            out["p_value"].tolist(),
            labels=list(out.index),
            families=families,
            method=method,
            alpha=float(alpha),
        )
        for _, row in adjusted.iterrows():
            idx = row["label"]
            out.loc[idx, "p_adjusted"] = float(row["p_adjusted"])
            out.loc[idx, "reject_adjusted"] = bool(row["reject"])
    except Exception:
        out["p_adjusted"] = pd.to_numeric(out["p_value"], errors="coerce")
        out["reject_adjusted"] = out["p_adjusted"] <= float(alpha)
    out["p_adjust_method"] = method
    return out


def _lm_emit_report(fit_result, adjusted_means_df, group_col, predictors):
    try:
        import PyFLASH.report as report
        if not report.is_active():
            return
        coeffs = fit_result.get("coefficients")
        summaries = fit_result.get("model_summaries")
        if not isinstance(coeffs, pd.DataFrame) or not isinstance(summaries, pd.DataFrame):
            return
        for _, summary in summaries.iterrows():
            dep = str(summary.get("dependent_variable"))
            csub = coeffs[coeffs["dependent_variable"].astype(str).eq(dep)]
            coeff_payload = {}
            for _, row in csub.iterrows():
                coeff_payload[str(row.get("term"))] = {
                    "estimate": row.get("estimate"),
                    "p": row.get("p_value"),
                    "q": row.get("q_value"),
                    "ci_low": row.get("ci_low"),
                    "ci_high": row.get("ci_high"),
                }
            mean_payload = {}
            if isinstance(adjusted_means_df, pd.DataFrame) and not adjusted_means_df.empty:
                msub = adjusted_means_df[
                    adjusted_means_df["dependent_variable"].astype(str).eq(dep)
                ]
                for _, row in msub.iterrows():
                    mean_payload[str(row.get("group"))] = {
                        "adjusted_mean": row.get("adjusted_mean"),
                        "ci_low": row.get("ci_low"),
                        "ci_high": row.get("ci_high"),
                        "n": row.get("n"),
                    }
            report.emit(report.build_linear_model_record(
                dependent_variable=dep,
                formula=summary.get("formula"),
                group=group_col,
                predictors=predictors,
                n=summary.get("nobs"),
                r2=summary.get("r_squared"),
                adj_r2=summary.get("adj_r_squared"),
                f=summary.get("f_statistic"),
                p=summary.get("f_pvalue"),
                coefficients=coeff_payload,
                adjusted_means=mean_payload,
            ))
    except Exception:
        return


@montage_pipeline(title="Linear Model Pipeline")
def linear_model(
    experiment,
    dependent_variables=None,
    predictors=None,
    *,
    group=None,
    categorical="auto",
    reference_levels=None,
    interactions=None,
    medication_columns=None,
    medication_mode="any",
    medication_min_count=2,
    specificity=None,
    roi=None,
    exclude=None,
    cov_type=None,
    cov_kwds=None,
    alpha=0.05,
    fdr_method="fdr_bh",
    fdr_family="all",
    adjusted_means=True,
    covariate_profile="mean_mode",
    adjusted_mean_weights="equal",
    adjusted_mean_p_adjust="holm",
    adjusted_mean_p_family="dependent_variable",
    plot_adjusted_means=True,
    plot_coefficients=True,
    coefficient_gate="p",
    max_coefficient_terms=60,
    tick_label_size=20,
    run_label=None,
    if_exists="overwrite",
    save=True,
    write_manifest=True,
    montage=True,
    verbose=True,
    _run_dirs=None,
    _tag_specificity=False,
    _slug_specificity=None,
):
    """Adjusted linear-model pipeline with coefficient and adjusted-mean plots."""
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            linear_model, experiment, specificity, kwargs, "linear_model",
            append_index=_lm_append_runs_index)

    if dependent_variables is None:
        raise ValueError("linear_model needs dependent_variables.")
    dep_source = getattr(experiment, "summary", None)
    if not isinstance(dep_source, pd.DataFrame) or dep_source.empty:
        raise ValueError("experiment.summary must be a non-empty pandas DataFrame.")

    _roi_base = _resolve_roi_bases(roi, experiment)[0]
    scope_df = _filtered_summary_for_specificity(experiment, specificity, roi_base=_roi_base)
    dep_vars = [
        str(_resolve_summary_column(scope_df, col, required=True))
        for col in _lm_as_list(dependent_variables, name="dependent_variables")
    ]
    dep_vars = _lm_unique(dep_vars)
    if not dep_vars:
        raise ValueError("linear_model resolved no dependent variables.")

    group_col = (
        str(_resolve_summary_column(scope_df, group, required=True))
        if group is not None else None
    )
    if (adjusted_means or plot_adjusted_means) and group_col is None:
        raise ValueError(
            "linear_model adjusted means need group=<column>. "
            "Set adjusted_means=False and plot_adjusted_means=False for model-only runs."
        )
    adjustment_predictors = [
        pred for pred in _lm_resolve_terms(scope_df, predictors, kind="predictors")
        if pred != group_col
    ]
    adjustment_predictors = _lm_unique(adjustment_predictors)
    model_predictors = []
    if group_col is not None:
        model_predictors.append(group_col)
    model_predictors.extend(adjustment_predictors)
    model_predictors = _lm_unique(model_predictors)
    if not model_predictors:
        raise ValueError("linear_model needs at least one predictor or group.")
    categorical_arg = _lm_categorical_arg(scope_df, model_predictors, categorical, group_col)

    label = run_label or _lm_slug(
        dep_vars, group_col, model_predictors,
        (_slug_specificity if _slug_specificity is not None else specificity),
        _roi_base,
        settings={
            "categorical": categorical_arg,
            "reference_levels": reference_levels or {},
            "interactions": [str(x) for x in (interactions or [])],
            "cov_type": str(cov_type or "nonrobust"),
            "alpha": float(alpha),
            "fdr_family": str(fdr_family),
            "adjusted_means": bool(adjusted_means),
            "covariate_profile": str(covariate_profile),
            "adjusted_mean_weights": str(adjusted_mean_weights),
            "adjusted_mean_p_adjust": str(adjusted_mean_p_adjust),
            "adjusted_mean_p_family": str(adjusted_mean_p_family),
        },
    )
    if _run_dirs is not None:
        fig_dir, data_dir, resolved_label = _run_dirs
        reuse_existing = False
    elif save:
        fig_dir, data_dir, resolved_label, reuse_existing = _lm_run_dirs(
            experiment, label, if_exists, clear_overwrite=bool(save))
    else:
        fig_dir = data_dir = None
        resolved_label = str(label)
        reuse_existing = False

    manifest_path = os.path.join(data_dir, "manifest.json") if data_dir else None
    if reuse_existing and manifest_path and _pio.isfile(manifest_path):
        cached = _pio.read_json(manifest_path)
        _log.hint(f"[linear_model] Reusing run {resolved_label!r} (if_exists='skip').")
        cached["reused"] = True
        return cached

    scope = SimpleNamespace(
        summary=scope_df,
        data_path=getattr(experiment, "data_path", None),
    )
    fit_result = _fit_linear_models(
        scope,
        dependent_variables=dep_vars,
        predictors=model_predictors,
        categorical=categorical_arg,
        reference_levels=reference_levels,
        interactions=interactions,
        medication_columns=medication_columns,
        medication_mode=medication_mode,
        medication_min_count=medication_min_count,
        specificity=None,
        exclude=exclude,
        cov_type=cov_type,
        cov_kwds=cov_kwds,
        alpha=alpha,
        fdr_method=fdr_method,
        fdr_family=fdr_family,
        save=False,
        return_fits=True,
        verbose=False,
    )
    coefficients = fit_result["coefficients"]
    model_summaries = fit_result["model_summaries"]
    metadata = fit_result["metadata"]
    adjusted_df = (
        _lm_adjusted_means_table(
            experiment, fit_result, dep_vars, group_col,
            covariate_profile=covariate_profile,
            adjusted_mean_weights=adjusted_mean_weights,
            alpha=alpha)
        if adjusted_means and group_col is not None else pd.DataFrame()
    )
    adjusted_comparisons_df = (
        _lm_adjusted_mean_comparisons_table(
            experiment, fit_result, dep_vars, group_col,
            covariate_profile=covariate_profile,
            adjusted_mean_weights=adjusted_mean_weights,
            adjusted_mean_p_adjust=adjusted_mean_p_adjust,
            adjusted_mean_p_family=adjusted_mean_p_family,
            alpha=alpha,
        )
        if adjusted_means and group_col is not None else pd.DataFrame()
    )
    _lm_emit_report(fit_result, adjusted_df, group_col, adjustment_predictors)

    spec_tag = build_pipeline_suffix(
        specificity=(specificity if _tag_specificity else None),
        aliases=getattr(experiment, "aliases", None))
    group_colors = _lm_group_colors(experiment, group_col) if group_col else {}
    adjusted_means_dir = (
        os.path.join(data_dir, "Adjusted Means")
        if data_dir and plot_adjusted_means and not adjusted_df.empty
        else data_dir
    )

    if save:
        _pio.makedirs(data_dir)
        _pio.to_csv(coefficients, os.path.join(data_dir, f"linear_model_coefficients{spec_tag}.csv"),
                    index=False)
        _pio.to_csv(model_summaries, os.path.join(data_dir, f"linear_model_summaries{spec_tag}.csv"),
                    index=False)
        _pio.to_csv(metadata, os.path.join(data_dir, f"linear_model_metadata{spec_tag}.csv"),
                    index=False)
        if not adjusted_df.empty:
            _pio.makedirs(adjusted_means_dir)
            _pio.to_csv(adjusted_df,
                        os.path.join(adjusted_means_dir,
                                     f"linear_model_adjusted_means{spec_tag}.csv"),
                        index=False)
        if not adjusted_comparisons_df.empty:
            _pio.makedirs(adjusted_means_dir)
            _pio.to_csv(
                adjusted_comparisons_df,
                os.path.join(
                    adjusted_means_dir,
                    f"linear_model_adjusted_mean_comparisons{spec_tag}.csv"),
                index=False,
            )
        _pio.makedirs(fig_dir)
        if plot_coefficients and not coefficients.empty:
            cfig = _linear_model_coefficient_forest_figure(
                coefficients,
                alpha=alpha,
                gate=coefficient_gate,
                tick_label_size=tick_label_size,
                max_terms=max_coefficient_terms,
            )
            if cfig is not None:
                save_fig(cfig, fig_dir, f"Coefficient Forest{spec_tag}",
                         montage=True)
                plt.close(cfig)
        if plot_adjusted_means and not adjusted_df.empty:
            order = list(dict.fromkeys(adjusted_df["group"].astype(str)))
            for dep in dep_vars:
                fig = _linear_model_adjusted_means_figure(
                    adjusted_df,
                    dep,
                    group_col,
                    group_order=order,
                    group_color_map=group_colors,
                    comparisons=adjusted_comparisons_df,
                    source=experiment,
                    alpha=alpha,
                    tick_label_size=tick_label_size,
                )
                if fig is not None:
                    save_fig(fig, fig_dir, f"Adjusted Means {dep}{spec_tag}",
                             subfolder="Adjusted Means", montage=True)
                    plt.close(fig)

    manifest = {
        "run_label": resolved_label,
        "fig_dir": fig_dir,
        "data_dir": data_dir,
        "adjusted_means_dir": adjusted_means_dir,
        "pipeline": "linear_model",
        "n_rows": int(len(scope_df)),
        "dependent_variables": dep_vars,
        "n_models": int(len(dep_vars)),
        "group": group_col,
        "predictors": list(adjustment_predictors),
        "model_terms": list(fit_result.get("predictors") or model_predictors),
        "covariates": list(adjustment_predictors),
        "categorical": list(fit_result.get("categorical") or []),
        "reference_levels": {str(k): str(v) for k, v in (fit_result.get("reference_levels") or {}).items()},
        "interactions": [str(item) for item in (interactions or [])],
        "medication_predictors": list(fit_result.get("medication_predictors") or []),
        "alpha": float(alpha),
        "fdr_method": str(fdr_method),
        "fdr_family": str(fdr_family),
        "cov_type": str(cov_type or "nonrobust"),
        "specificity": str(specificity) if specificity is not None else None,
        "roi": str(_roi_base) if _roi_base is not None else None,
        "exclude": str(exclude),
        "adjusted_means": bool(adjusted_means),
        "n_adjusted_means": int(len(adjusted_df)),
        "n_adjusted_mean_comparisons": int(len(adjusted_comparisons_df)),
        "covariate_profile": str(covariate_profile),
        "adjusted_mean_weights": str(adjusted_mean_weights),
        "adjusted_mean_p_adjust": str(adjusted_mean_p_adjust),
        "adjusted_mean_p_family": str(adjusted_mean_p_family),
        "plot_adjusted_means": bool(plot_adjusted_means),
        "plot_coefficients": bool(plot_coefficients),
        "reused": False,
    }
    if save and write_manifest and manifest_path:
        _pio.write_json(manifest, manifest_path)
        _lm_append_runs_index(experiment, manifest)

    if verbose:
        _log.confirm(
            f"[linear_model] {resolved_label}: {len(dep_vars)} model(s), "
            f"{len(coefficients)} coefficient rows, {len(adjusted_df)} adjusted means."
        )

    result = dict(manifest)
    result["coefficients"] = coefficients
    result["model_summaries"] = model_summaries
    result["metadata"] = metadata
    result["adjusted_means_table"] = adjusted_df
    result["adjusted_mean_comparisons"] = adjusted_comparisons_df
    return result


# ── Rhythm pipeline ──────────────────────────────────────────────────────────
# The genuinely-new capability (PREFERENCES.md §1): cosinor + circular statistics.
# Two modes on a subject-level frame (an experiment .summary or a plain DataFrame,
# so external human/actigraphy CSVs work):
#   * cosinor mode  — column(s) sampled across time_col -> per-group cosinor fits,
#                     rhythm plots, a parameter table, and a group-difference test.
#   * parameter mode — a pre-computed acrophase column (+ optional scalar params) ->
#                     circular acrophase clock, a between-group circular test, and a
#                     scalar-parameter comparison table.
# Multiplicity follows §2-3: raw p is always the default; an FDR q is added ONLY as
# a duplicate column when the run is declared an exploratory screen (screen=True),
# never replacing p, and gate='fdr' requires screen=True.


def _rhythm_run_dirs(experiment, run_label, if_exists, *, clear_overwrite=True):
    return _pio.run_dirs(experiment, "Rhythm Pipeline", run_label,
                         if_exists, clear_overwrite=clear_overwrite)


def _rhythm_slug(mode, cols, group_col, specificity, settings=None):
    payload = {"mode": str(mode), "cols": sorted(str(c) for c in cols),
               "group_col": str(group_col), "specificity": str(specificity),
               "settings": settings or {}}
    return _pio.slug(f"rhythm_{mode}", payload)


def _rhythm_append_runs_index(experiment, manifest):
    _pio.append_runs_index(experiment, "Rhythm Pipeline", {
        "run_label": manifest.get("run_label"),
        "mode": manifest.get("mode"),
        "period": manifest.get("period"),
        "group_col": manifest.get("group_col"),
        "n_groups": manifest.get("n_groups"),
        "n_params": manifest.get("n_params"),
        "phase_test_p": manifest.get("phase_test_p"),
        "n_significant": manifest.get("n_significant"),
        "screen": manifest.get("screen"),
        "gate": manifest.get("gate"),
        "alpha": manifest.get("alpha"),
        "specificity": manifest.get("specificity"),
        "fig_dir": manifest.get("fig_dir"),
    })


def _rhythm_param_tests(df, param_cols, group_col, groups, *, screen, families, alpha):
    """Compare each scalar rhythm parameter across groups (raw p; q only on screen).

    Kruskal-Wallis for >= 3 groups, Welch's t for 2, plus a monotonic trend
    (Spearman rho against the ordered group index — informative for a progression
    axis). Returns a tidy DataFrame; ``p_adjusted`` is added ONLY when
    ``screen=True`` (an opt-in exploratory correction), never replacing the raw
    ``p_value``.

    ``families`` controls the FDR grouping under ``screen``: ``'parameter'``
    (default) treats the whole parameter panel as one BH family; ``'none'`` /
    ``'each'`` gives each parameter its own family (q == p, no cross-parameter
    penalty); a ``{parameter: family}`` dict corrects within named families.
    """
    from scipy import stats as _sps
    from PyFLASH.stats_extra import apply_fdr

    codes = {g: i for i, g in enumerate(groups)}
    rows = []
    for col in param_cols:
        by = {g: pd.to_numeric(df[df[group_col].astype(str) == g][col], errors="coerce")
                 .dropna().to_numpy() for g in groups}
        present = [(g, v) for g, v in by.items() if len(v) >= 2]
        rec = {"parameter": str(col), "n": int(sum(len(v) for v in by.values()))}
        for g in groups:
            rec[f"mean_{g}"] = float(np.mean(by[g])) if len(by[g]) else float("nan")
        if len(present) < 2:
            rec.update(test="skipped (n<2 in >=2 groups)", statistic=float("nan"),
                       p_value=float("nan"), trend_rho=float("nan"), trend_p=float("nan"))
            rows.append(rec)
            continue
        glab = [g for g, _ in present]
        arrs = [v for _, v in present]
        if len(arrs) == 2:
            stat, p = _sps.ttest_ind(arrs[0], arrs[1], equal_var=False)
            test = "Welch t"
        else:
            stat, p = _sps.kruskal(*arrs)
            test = "Kruskal-Wallis"
        allv = np.concatenate(arrs)
        allc = np.concatenate([[codes[g]] * len(v) for g, v in present])
        if len(set(allc)) > 1:
            rho, ptr = _sps.spearmanr(allc, allv)
        else:
            rho, ptr = float("nan"), float("nan")
        rec.update(test=test, statistic=float(stat), p_value=float(p),
                   trend_rho=float(rho), trend_p=float(ptr))
        rows.append(rec)
    out = pd.DataFrame(rows)
    if screen and not out.empty and out["p_value"].notna().any():
        # Opt-in exploratory screen: add a duplicate q column (raw p_value is
        # never overwritten). `families` groups the BH correction.
        params = list(out["parameter"])
        if isinstance(families, dict):
            fam = {str(p): str(families.get(p, "all")) for p in params}
        elif str(families).lower() in ("none", "each", "per-parameter"):
            fam = {str(p): str(p) for p in params}      # each its own family -> q == p
        else:                                            # 'parameter': one panel-wide family
            fam = {str(p): "parameter" for p in params}
        fdr = apply_fdr(dict(zip(out["parameter"], out["p_value"])),
                        families=fam, method="fdr_bh", alpha=float(alpha))
        qmap = dict(zip(fdr["label"], fdr["p_adjusted"]))
        out["p_adjusted"] = out["parameter"].map(qmap)
    return out


@montage_pipeline(title="Rhythm Pipeline")
def rhythm(
    experiment,
    column=None,
    columns=None,
    time_col="Time",
    group_col=None,
    group_order=None,
    period=24.0,
    period_free=False,
    method="pooled",
    animal_col=None,
    phase_col=None,
    param_cols=None,
    radius_col=None,
    specificity=None,
    screen=False,
    families="parameter",
    gate="p",
    alpha=0.05,
    palette=None,
    run_label=None,
    if_exists="overwrite",
    save=True,
    write_manifest=True,
    montage=True,
    _run_dirs=None,
    _tag_specificity=False,
    _slug_specificity=None,
):
    """Cosinor + circular rhythm analysis in one manifested run.

    Period-generic (``period=24`` daily, ``12`` circannual, ``period_free`` for a
    free-running tau). Works on an experiment ``.summary`` or a plain DataFrame.

    Modes
    -----
    - **Cosinor** (pass ``column`` or ``columns`` + ``time_col``): fits a cosinor
      per ``group_col`` level for every column, saves a rhythm plot each (reusing
      :func:`plot_cosinor`), a ``cosinor_parameters`` table (MESOR / amplitude /
      acrophase / rhythmicity p), and — with >= 2 groups — a
      ``cosinor_group_test`` (does the rhythm differ between groups). ``method``
      handles repeated measures: ``'pooled'`` / ``'population_mean'`` / ``'mixed'``.
    - **Parameter** (pass ``phase_col``, e.g. a pre-computed ``"Acrophase (h)"``):
      draws a circular acrophase clock (reusing :func:`plot_acrophase_clock`),
      writes ``circular_phase_stats`` + a between-group ``phase_group_test``
      (Watson-Williams), and — with ``param_cols`` — a ``parameter_tests`` table
      comparing each scalar parameter across groups. ``radius_col`` adds a
      phase x amplitude figure.

    Multiplicity (``screen=`` / ``gate=``)
    --------------------------------------
    Raw **p** is always the default and drives significance. Pass ``screen=True`` to
    add an FDR **q** as a *duplicate* ``p_adjusted`` column across the parameter
    panel (never replacing p); ``gate='fdr'`` requires it. Different parameters are
    not treated as a family unless you opt in (PREFERENCES.md §2-3).

    Returns a dict manifest (run label, dirs, counts, the phase test) with the
    computed tables attached.
    """
    if is_specificity_queue(specificity):
        kwargs = dict(locals())
        kwargs.pop("experiment")
        return _pipeline_specificity_queue(
            rhythm, experiment, specificity, kwargs, "rhythm",
            append_index=_rhythm_append_runs_index)

    gate = str(gate).strip().lower()
    if gate not in ("p", "fdr"):
        raise ValueError(f"gate must be 'p' or 'fdr'; got {gate!r}.")
    if gate == "fdr" and not screen:
        raise ValueError(
            "gate='fdr' requires screen=True (no cross-parameter q is computed "
            "otherwise — different parameters are not a family by default).")

    df = filter_df_by_specificity(_resolve_rhythm_frame(experiment), specificity).copy()

    cosinor_cols = list(columns) if columns else ([column] if column else [])
    if phase_col:
        mode = "parameter"
    elif cosinor_cols:
        mode = "cosinor"
    else:
        raise ValueError(
            "rhythm needs either phase_col (parameter mode) or column/columns + "
            "time_col (cosinor mode).")
    if mode == "cosinor":
        if time_col not in df.columns:
            raise ValueError(
                f"rhythm (cosinor mode): time_col {time_col!r} not found in the data.")
        if not any(c in df.columns for c in cosinor_cols):
            raise ValueError(
                f"rhythm (cosinor mode): none of columns {cosinor_cols} found in the data.")

    gcol = group_col if (group_col and group_col in df.columns) else None
    if gcol is not None:
        df = df[df[gcol].notna()]
        groups = [g for g in dict.fromkeys(df[gcol].astype(str))]
        if group_order:
            ordered = [str(g) for g in group_order if str(g) in groups]
            groups = ordered + [g for g in groups if g not in ordered]
    else:
        groups = ["all"]

    slug_cols = cosinor_cols if mode == "cosinor" else ([phase_col] + list(param_cols or []))
    label = run_label or _rhythm_slug(
        mode, slug_cols, gcol,
        (_slug_specificity if _slug_specificity is not None else specificity),
        settings={"period": float(period), "period_free": bool(period_free),
                  "method": str(method), "screen": bool(screen), "gate": gate,
                  "families": str(families), "alpha": float(alpha),
                  "radius_col": str(radius_col), "time_col": str(time_col)})
    if _run_dirs is not None:
        fig_dir, data_dir, resolved_label = _run_dirs
        reuse_existing = False
    else:
        fig_dir, data_dir, resolved_label, reuse_existing = _rhythm_run_dirs(
            experiment, label, if_exists, clear_overwrite=bool(save))
    manifest_path = os.path.join(data_dir, "manifest.json")
    if reuse_existing and _corr_isfile(manifest_path):
        cached = _corr_read_json(manifest_path)
        _log.hint(f"[rhythm] Reusing run {resolved_label!r} (if_exists='skip').")
        cached["reused"] = True
        return cached
    spec_tag = build_pipeline_suffix(
        specificity=(specificity if _tag_specificity else None),
        aliases=getattr(experiment, "aliases", None))
    if save:
        # save_fig only makedirs when a subfolder is given, so create the run
        # folders up front (before any figure/table write) as the other pipelines do.
        _corr_makedirs(fig_dir)
        _corr_makedirs(data_dir)

    tables = {}
    phase_test = None
    n_params = 0
    n_significant = 0
    extra = {}

    if mode == "cosinor":
        from PyFLASH.stats_extra import cosinor_table, cosinor_group_test, apply_fdr

        present_cols = [c for c in cosinor_cols if c in df.columns]
        for c in cosinor_cols:
            if c not in df.columns:
                _log.hint(f"[rhythm] cosinor column {c!r} not found; skipped.")
        ct = []
        for col in present_cols:
            t = cosinor_table(df, time_col, col, group_col=gcol, animal_col=animal_col,
                              period=period, period_free=period_free, method=method)
            t.insert(0, "column", str(col))
            ct.append(t)
        if ct:
            tables["cosinor_parameters"] = pd.concat(ct, ignore_index=True)
        if gcol and len(groups) >= 2:
            gt = []
            for col in present_cols:
                r = cosinor_group_test(df, time_col, col, gcol, period=period)
                gt.append({"column": str(col), "F": r["F"], "p": r["p"],
                           "df1": r["df1"], "df2": r["df2"], "n": r["n"]})
            if gt:
                gtd = pd.DataFrame(gt)
                # Opt-in screen: correct the rhythm-difference p across the column
                # panel and add a duplicate q, so gate='fdr' selects consistently
                # with parameter mode. p is always kept.
                if screen and gtd["p"].notna().any():
                    fdr = apply_fdr(dict(zip(gtd["column"], gtd["p"])),
                                    method="fdr_bh", alpha=float(alpha))
                    gtd["p_adjusted"] = gtd["column"].map(
                        dict(zip(fdr["label"], fdr["p_adjusted"])))
                tables["cosinor_group_test"] = gtd
                gcol_sel = ("p_adjusted" if (gate == "fdr" and "p_adjusted" in gtd.columns)
                            else "p")
                n_significant = int((pd.to_numeric(gtd[gcol_sel], errors="coerce")
                                     < float(alpha)).sum())
        drawn = 0
        for col in present_cols:
            try:
                fig, _fits = plot_cosinor(
                    df, col, time_col=time_col, group_col=gcol, period=period,
                    period_free=period_free, palette=palette, save=save,
                    save_path=fig_dir, save_name=f"Cosinor {col}{spec_tag}",
                    montage=(drawn == 0), return_data=True)
                plt.close(fig)
                drawn += 1
            except Exception as exc:
                _log.warn(f"[rhythm] cosinor plot failed for {col!r}: {exc}")
        n_params = len(present_cols)
        extra["columns"] = [str(c) for c in present_cols]

    else:  # parameter mode
        from PyFLASH.stats_extra import circular_stats  # noqa: F401 (used via plot)

        if phase_col not in df.columns:
            raise ValueError(f"rhythm: phase_col {phase_col!r} not found in the data.")
        fig, clock_stats = plot_acrophase_clock(
            df, phase_col=phase_col, group_col=gcol, period=period,
            group_order=group_order, palette=palette,
            save=save, save_path=fig_dir, save_name=f"Acrophase Clock{spec_tag}",
            montage=True, return_data=True)
        plt.close(fig)
        if radius_col and radius_col in df.columns:
            try:
                fig2, _ = plot_acrophase_clock(
                    df, phase_col=phase_col, group_col=gcol, period=period,
                    radius_col=radius_col, group_order=group_order, palette=palette,
                    save=save, save_path=fig_dir, save_name=f"Phase-Amplitude{spec_tag}",
                    montage=True, return_data=True)
                plt.close(fig2)
            except Exception as exc:
                _log.warn(f"[rhythm] phase-amplitude plot failed: {exc}")

        crows = [{"group": g, "n": st.get("n"), "mean_phase": st.get("mean"),
                  "resultant_r": st.get("r"), "rayleigh_z": st.get("rayleigh_z"),
                  "rayleigh_p": st.get("rayleigh_p")}
                 for g, st in clock_stats.get("groups", {}).items()]
        if crows:
            tables["circular_phase_stats"] = pd.DataFrame(crows)
        # Two complementary between-group circular tests: mean phase
        # (Watson-Williams) AND spread (Wallraff dispersion), so a phase that
        # keeps its mean but scatters more is not missed.
        phase_test = clock_stats.get("watson_williams") or clock_stats.get("rayleigh")
        phase_rows = []
        if phase_test:
            kind = "Watson-Williams (mean)" if "F" in phase_test else "Rayleigh (clustering)"
            row = {"test": kind}
            row.update({k: v for k, v in phase_test.items() if k != "means"})
            phase_rows.append(row)
        if gcol and len(groups) >= 2:
            from PyFLASH.stats_extra import circular_dispersion_test
            disp = circular_dispersion_test(
                [pd.to_numeric(df[df[gcol].astype(str) == g][phase_col], errors="coerce")
                 .dropna().to_numpy() for g in groups], period)
            phase_rows.append({"test": "Wallraff (dispersion)", "statistic": disp["statistic"],
                               "p": disp["p"], "k": disp["k"], "n": disp["n"]})
        if phase_rows:
            tables["phase_group_test"] = pd.DataFrame(phase_rows)

        if param_cols and gcol and len(groups) >= 2:
            pcols = [c for c in param_cols if c in df.columns]
            if pcols:
                pt = _rhythm_param_tests(df, pcols, gcol, groups,
                                         screen=screen, families=families, alpha=alpha)
                tables["parameter_tests"] = pt
                n_params = len(pcols)
                gate_col = "p_adjusted" if gate == "fdr" else "p_value"
                if gate_col in pt.columns:
                    n_significant = int((pd.to_numeric(pt[gate_col], errors="coerce")
                                         < float(alpha)).sum())
        extra["phase_col"] = str(phase_col)

    if save:
        _corr_makedirs(data_dir)
        for name, tbl in tables.items():
            if isinstance(tbl, pd.DataFrame) and not tbl.empty:
                _corr_to_csv(tbl, os.path.join(data_dir, f"{name}{spec_tag}.csv"),
                             index=False)

    phase_test_p = (float(phase_test["p"]) if phase_test
                    and np.isfinite(phase_test.get("p", np.nan)) else None)
    manifest = {
        "run_label": resolved_label, "pipeline": "rhythm", "mode": mode,
        "period": float(period), "period_free": bool(period_free), "method": str(method),
        "group_col": gcol, "groups": list(groups), "n_groups": len(groups),
        "n_params": int(n_params), "phase_test": phase_test, "phase_test_p": phase_test_p,
        "screen": bool(screen), "gate": gate, "alpha": float(alpha),
        "n_significant": int(n_significant), "specificity": str(specificity),
        "fig_dir": fig_dir, "data_dir": data_dir, "reused": False,
    }
    manifest.update(extra)
    if save and write_manifest:
        _corr_write_json(manifest, manifest_path)
        _rhythm_append_runs_index(experiment, manifest)
    _log.confirm(
        f"[rhythm] {resolved_label}: mode={mode}, {len(groups)} groups, "
        f"{n_params} params, {n_significant} significant.")

    result = dict(manifest)
    for name, tbl in tables.items():
        result[name] = tbl
    return result
