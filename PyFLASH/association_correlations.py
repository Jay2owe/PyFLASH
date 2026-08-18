"""Statistical engine for grouped multi-association correlation plots.

This module is internal. The public API is
``PyFLASH.plotting.plot_association_correlations``.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
from scipy import stats


TESTS = ("pearsonr", "spearmanr")
COVARIATE_ADJUSTMENTS = ("rank_then_residual", "residual_then_correlation")


def normalize_specs(associations):
    """Normalize named or unnamed ``{x, y, covariates}`` specifications."""
    if isinstance(associations, Mapping):
        items = list(associations.items())
    elif isinstance(associations, (list, tuple)):
        items = [(None, spec) for spec in associations]
    else:
        raise ValueError(
            "associations must be a mapping of {name: {x, y, covariates}} "
            "or a list of specification mappings"
        )
    if not items:
        raise ValueError("associations cannot be empty")

    normalized = []
    for index, (name, spec) in enumerate(items):
        if not isinstance(spec, Mapping):
            raise ValueError(f"association {index + 1} must be a mapping")
        x = spec.get("x")
        y = spec.get("y")
        if x is None or y is None:
            raise ValueError(f"association {index + 1} requires 'x' and 'y'")
        if str(x) == str(y):
            raise ValueError(f"association {index + 1} has identical x and y")
        covariates = spec.get("covariates", [])
        if covariates is None:
            covariates = []
        elif isinstance(covariates, str):
            covariates = [covariates]
        else:
            covariates = list(covariates)
        if any(str(column) in {str(x), str(y)} for column in covariates):
            raise ValueError(f"association {index + 1} repeats x or y as a covariate")
        label = str(name) if name is not None else f"{x} vs {y}"
        normalized.append(
            {
                "name": None if name is None else str(name),
                "label": label,
                "x": str(x),
                "y": str(y),
                "covariates": [str(column) for column in covariates],
            }
        )

    names = [spec["name"] for spec in normalized if spec["name"] is not None]
    if len(names) != len(set(names)):
        raise ValueError("association names must be unique")
    return normalized


def _normalize_test(test):
    key = str(test or "spearmanr").strip().lower().replace("_", "").replace("-", "")
    if key in {"s", "spearman", "spearmanr"}:
        return "spearmanr"
    if key in {"p", "pearson", "pearsonr"}:
        return "pearsonr"
    raise ValueError("test must be 'pearsonr' or 'spearmanr'")


def _normalize_covariate_adjustment(value):
    key = (
        str(value or "rank_then_residual")
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )
    if key in {"rank", "rankfirst", "rankthenresidual", "rankthenresidualize"}:
        return "rank_then_residual"
    if key in {
        "residual",
        "residualfirst",
        "residualthenrank",
        "residualthencorrelation",
        "residualthenspearman",
        "presentation",
    }:
        return "residual_then_correlation"
    raise ValueError(
        "covariate_adjustment must be 'rank_then_residual' or "
        "'residual_then_correlation'"
    )


def _rank_numeric(series):
    return pd.to_numeric(series, errors="coerce").rank(method="average").to_numpy(dtype=float)


def _numeric_array(series):
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)


def _design_matrix(frame, covariates, *, rank_numeric):
    blocks = []
    labels = ["Intercept"]
    for column in covariates:
        values = frame[column]
        numeric = pd.to_numeric(values, errors="coerce")
        present = values.notna()
        numeric_present = numeric.notna()
        if int(numeric_present.sum()) == int(present.sum()):
            arr = _rank_numeric(values) if rank_numeric else numeric.to_numpy(dtype=float)
            blocks.append(arr.reshape(-1, 1))
            labels.append(f"{'rank' if rank_numeric else 'value'}({column})")
        else:
            dummies = pd.get_dummies(values.astype(str), drop_first=True, dtype=float)
            if dummies.shape[1]:
                blocks.append(dummies.to_numpy(dtype=float))
                labels.extend([f"{column}={name}" for name in dummies.columns])
    matrix = np.ones((len(frame), 1), dtype=float)
    if blocks:
        matrix = np.column_stack([matrix, *blocks])
    return matrix, labels


def _residualize(values, matrix):
    beta = np.linalg.lstsq(matrix, values, rcond=None)[0]
    return values - matrix @ beta


def _correlation_method_label(test, covariates, covariate_adjustment):
    test = _normalize_test(test)
    adjustment = _normalize_covariate_adjustment(covariate_adjustment)
    if test == "spearmanr":
        if covariates and adjustment == "residual_then_correlation":
            return "Spearman residual correlation"
        return "partial Spearman" if covariates else "Spearman"
    return "partial Pearson" if covariates else "Pearson"


def _correlation_for_frame(
    frame,
    spec,
    test,
    covariate_adjustment="rank_then_residual",
):
    columns = [spec["x"], spec["y"], *spec["covariates"]]
    sub = frame[columns].dropna().copy()
    n = len(sub)
    covariates = list(spec["covariates"])
    adjustment = _normalize_covariate_adjustment(covariate_adjustment)
    if n < 3:
        return {
            "r": np.nan,
            "p": np.nan,
            "n": n,
            "covariate_df": np.nan,
            "dof": np.nan,
        }
    test = _normalize_test(test)
    rank = test == "spearmanr"
    rank_before_residualizing = rank and adjustment == "rank_then_residual"
    x = (
        _rank_numeric(sub[spec["x"]])
        if rank_before_residualizing
        else _numeric_array(sub[spec["x"]])
    )
    y = (
        _rank_numeric(sub[spec["y"]])
        if rank_before_residualizing
        else _numeric_array(sub[spec["y"]])
    )

    if covariates:
        matrix, _labels = _design_matrix(
            sub,
            covariates,
            rank_numeric=rank_before_residualizing,
        )
        matrix_rank = int(np.linalg.matrix_rank(matrix))
        covariate_df = matrix_rank - 1
        dof = n - matrix_rank - 1
        if dof <= 0:
            return {
                "r": np.nan,
                "p": np.nan,
                "n": n,
                "covariate_df": covariate_df,
                "dof": dof,
            }
        x = _residualize(x, matrix)
        y = _residualize(y, matrix)
    else:
        covariate_df = 0
        dof = n - 2

    if dof <= 0 or np.nanstd(x) == 0 or np.nanstd(y) == 0:
        r = np.nan
        p_value = np.nan
    elif covariates and (not rank or adjustment == "rank_then_residual"):
        r = float(stats.pearsonr(x, y).statistic)
        clipped = float(np.clip(r, -0.999999999999, 0.999999999999))
        t_stat = clipped * np.sqrt(dof / (1.0 - clipped**2))
        p_value = float(2.0 * stats.t.sf(abs(t_stat), dof))
    elif rank:
        res = stats.spearmanr(x, y)
        r = float(res.statistic)
        p_value = float(res.pvalue)
    else:
        res = stats.pearsonr(x, y)
        r = float(res.statistic)
        p_value = float(res.pvalue)

    return {
        "r": r,
        "p": p_value,
        "n": n,
        "covariate_df": covariate_df,
        "dof": dof,
    }


def _compute_correlations(
    scope_df,
    group_col,
    specs,
    group_order,
    test,
    min_n,
    covariate_adjustment,
):
    rows = []
    adjustment = _normalize_covariate_adjustment(covariate_adjustment)
    for order, spec in enumerate(specs):
        for group in group_order:
            group_frame = scope_df.loc[scope_df[group_col].astype(str).eq(str(group))]
            result = _correlation_for_frame(
                group_frame,
                spec,
                test,
                adjustment,
            )
            if int(result.get("n") or 0) < int(min_n):
                raise ValueError(
                    f"association {spec['label']!r} needs at least {int(min_n)} "
                    f"complete rows per group; found {group}: {result.get('n')}"
                )
            covariates = ", ".join(spec["covariates"])
            method = _correlation_method_label(test, spec["covariates"], adjustment)
            rows.append(
                {
                    "association_order": order,
                    "association": spec["label"],
                    "x": spec["x"],
                    "y": spec["y"],
                    "covariates": covariates,
                    "group": str(group),
                    "n": int(result["n"]),
                    "estimate": float(result["r"]),
                    "p": float(result["p"]),
                    "covariate_df": int(result["covariate_df"]),
                    "dof": int(result["dof"]),
                    "method": method,
                    "test": _normalize_test(test),
                    "covariate_adjustment": adjustment,
                }
            )
    return pd.DataFrame(rows)


def _bootstrap_correlations(
    scope_df,
    group_col,
    specs,
    group_order,
    test,
    resamples,
    seed,
    covariate_adjustment,
):
    rng = np.random.default_rng(seed)
    rows = []
    adjustment = _normalize_covariate_adjustment(covariate_adjustment)
    grouped = {
        str(group): scope_df.loc[scope_df[group_col].astype(str).eq(str(group))].copy()
        for group in group_order
    }
    target = int(resamples)
    attempts = 0
    max_attempts = max(target + 1000, target * 10)
    while len(rows) < target and attempts < max_attempts:
        row = {"resample": int(attempts)}
        attempts += 1
        valid = True
        for order, spec in enumerate(specs):
            for group in group_order:
                frame = grouped[str(group)]
                columns = [spec["x"], spec["y"], *spec["covariates"]]
                complete = frame[columns].dropna().copy()
                if complete.empty:
                    valid = False
                    break
                indices = rng.choice(len(complete), size=len(complete), replace=True)
                sample = complete.iloc[indices].reset_index(drop=True)
                result = _correlation_for_frame(sample, spec, test, adjustment)
                value = result.get("r")
                if value is None or not np.isfinite(float(value)):
                    valid = False
                    break
                row[f"{order}__{group}"] = float(value)
            if not valid:
                break
        if valid:
            rows.append(row)
    return pd.DataFrame(rows)


def _add_bootstrap_intervals(correlations, boot, ci_alpha):
    out = correlations.copy()
    low_q = 100.0 * float(ci_alpha) / 2.0
    high_q = 100.0 * (1.0 - float(ci_alpha) / 2.0)
    lows = []
    highs = []
    for row in out.itertuples(index=False):
        column = f"{int(row.association_order)}__{row.group}"
        if column in boot.columns and len(boot):
            low, high = np.percentile(boot[column].to_numpy(dtype=float), [low_q, high_q])
        else:
            low, high = np.nan, np.nan
        lows.append(float(low))
        highs.append(float(high))
    out["ci_low"] = lows
    out["ci_high"] = highs
    out["ci_method"] = "bootstrap"
    return out


def _fisher_z(value):
    return float(np.arctanh(np.clip(value, -0.999999999999, 0.999999999999)))


def _compute_heterogeneity(correlations):
    rows = []
    for association, subset in correlations.groupby("association", sort=False):
        z_values = np.asarray([_fisher_z(value) for value in subset["estimate"]], dtype=float)
        weights = (
            subset["n"].to_numpy(dtype=float)
            - subset["covariate_df"].to_numpy(dtype=float)
            - 3.0
        )
        valid = np.isfinite(z_values) & np.isfinite(weights) & (weights > 0)
        if int(valid.sum()) >= 2:
            z_bar = float(np.sum(weights[valid] * z_values[valid]) / np.sum(weights[valid]))
            statistic = float(np.sum(weights[valid] * (z_values[valid] - z_bar) ** 2))
            df = int(valid.sum() - 1)
            p_value = float(stats.chi2.sf(statistic, df))
        else:
            statistic = np.nan
            df = 0
            p_value = np.nan
        first = subset.iloc[0]
        rows.append(
            {
                "association_order": int(first["association_order"]),
                "association": str(association),
                "test": "Correlation homogeneity across groups",
                "method": "Inverse-variance Fisher-z Q test",
                "statistic": statistic,
                "df": df,
                "p": p_value,
                "covariates": str(first.get("covariates", "")),
                "total_n": int(subset["n"].sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("association_order", kind="mergesort").reset_index(drop=True)


def _compute_contrasts(correlations, boot, group_order, reference):
    rows = []
    for association, subset in correlations.groupby("association", sort=False):
        by_group = subset.set_index("group")
        ref = by_group.loc[str(reference)]
        for group in group_order:
            if str(group) == str(reference) or str(group) not in by_group.index:
                continue
            row = by_group.loc[str(group)]
            delta = float(row["estimate"]) - float(ref["estimate"])
            ref_col = f"{int(row['association_order'])}__{reference}"
            grp_col = f"{int(row['association_order'])}__{group}"
            if len(boot) and ref_col in boot.columns and grp_col in boot.columns:
                boot_delta = boot[grp_col].to_numpy(dtype=float) - boot[ref_col].to_numpy(dtype=float)
                delta_low, delta_high = np.percentile(boot_delta, [2.5, 97.5])
            else:
                delta_low, delta_high = np.nan, np.nan
            var_ref = 1.0 / (float(ref["n"]) - float(ref["covariate_df"]) - 3.0)
            var_group = 1.0 / (float(row["n"]) - float(row["covariate_df"]) - 3.0)
            se = float(np.sqrt(var_ref + var_group))
            z_diff = float((_fisher_z(row["estimate"]) - _fisher_z(ref["estimate"])) / se)
            p_value = float(2.0 * stats.norm.sf(abs(z_diff)))
            rows.append(
                {
                    "association_order": int(row["association_order"]),
                    "association": str(association),
                    "comparison": f"{group} - {reference}",
                    "reference": str(reference),
                    "group": str(group),
                    "estimate_reference": float(ref["estimate"]),
                    "estimate_group": float(row["estimate"]),
                    "delta": delta,
                    "ci_low": float(delta_low),
                    "ci_high": float(delta_high),
                    "n_reference": int(ref["n"]),
                    "n_group": int(row["n"]),
                    "z": z_diff,
                    "standard_error": se,
                    "p": p_value,
                }
            )
    return pd.DataFrame(rows)


def analyze(
    scope_df,
    *,
    group_col,
    specs,
    group_order,
    reference,
    test="spearmanr",
    ci_method="bootstrap",
    ci_alpha=0.05,
    bootstrap_resamples=5000,
    random_state=0,
    min_n=4,
    covariate_adjustment="rank_then_residual",
):
    """Compute grouped correlations, bootstrap CIs, heterogeneity, and contrasts."""
    test = _normalize_test(test)
    covariate_adjustment = _normalize_covariate_adjustment(covariate_adjustment)
    ci_method = str(ci_method).lower()
    if ci_method != "bootstrap":
        raise ValueError("association correlation CIs currently support ci_method='bootstrap'")
    if not (0 < float(ci_alpha) < 1):
        raise ValueError("ci_alpha must be between 0 and 1")
    if int(bootstrap_resamples) < 100:
        raise ValueError("bootstrap_resamples must be at least 100")
    if int(min_n) < 3:
        raise ValueError("min_n must be at least 3")
    if isinstance(specs, (list, tuple)) and all(
        isinstance(spec, Mapping) and "label" in spec for spec in specs
    ):
        specs = [dict(spec) for spec in specs]
    else:
        specs = normalize_specs(specs)
    group_order = [str(group) for group in group_order]
    reference = str(reference)
    correlations = _compute_correlations(
        scope_df,
        group_col,
        specs,
        group_order,
        test,
        min_n,
        covariate_adjustment,
    )
    boot = _bootstrap_correlations(
        scope_df,
        group_col,
        specs,
        group_order,
        test,
        bootstrap_resamples,
        random_state,
        covariate_adjustment,
    )
    correlations = _add_bootstrap_intervals(correlations, boot, ci_alpha)
    heterogeneity = _compute_heterogeneity(correlations)
    contrasts = _compute_contrasts(correlations, boot, group_order, reference)
    return {
        "schemas": specs,
        "correlations": correlations,
        "heterogeneity": heterogeneity,
        "contrasts": contrasts,
        "bootstrap": {
            "requested": int(bootstrap_resamples),
            "valid": int(len(boot)),
            "random_state": int(random_state),
        },
    }
