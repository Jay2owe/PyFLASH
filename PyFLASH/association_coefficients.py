"""Statistical engine for multi-association coefficient plots.

This module is internal. The public API is
``PyFLASH.plotting.plot_association_coefficients``.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
from scipy import stats


VALUES = ("beta", "slope")
CI_METHODS = ("bootstrap", "ols")


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
        normalized.append(
            {
                "name": None if name is None else str(name),
                "x": str(x),
                "y": str(y),
                "covariates": [str(column) for column in covariates],
            }
        )

    names = [spec["name"] for spec in normalized if spec["name"] is not None]
    if len(names) != len(set(names)):
        raise ValueError("association names must be unique")
    return normalized


def _model_schema(scope_df, group_col, spec, group_order, min_n, value):
    """Freeze aligned numeric arrays and encoding for fast bootstrap refits."""
    n_rows = len(scope_df)
    group_values = scope_df[group_col].astype(str).to_numpy(dtype=object)
    x_values = pd.to_numeric(scope_df[spec["x"]], errors="coerce").to_numpy(dtype=float)
    y_values = pd.to_numeric(scope_df[spec["y"]], errors="coerce").to_numpy(dtype=float)
    valid = np.isin(group_values, np.asarray(group_order, dtype=object))
    valid &= np.isfinite(x_values) & np.isfinite(y_values)

    covariate_parts = []
    covariate_names = []
    covariate_schema = []
    for column in spec["covariates"]:
        series = scope_df[column]
        numeric = pd.to_numeric(series, errors="coerce")
        present = series.notna().to_numpy()
        numeric_present = numeric.notna().to_numpy()
        if int(numeric_present.sum()) == int(present.sum()):
            values = numeric.to_numpy(dtype=float)
            valid &= np.isfinite(values)
            covariate_parts.append(values[:, None])
            covariate_names.append(str(column))
            covariate_schema.append({"column": column, "kind": "numeric", "levels": []})
        else:
            valid &= present
            levels = list(dict.fromkeys(series.loc[present].astype("object").tolist()))
            values = series.astype("object")
            covariate_schema.append(
                {"column": column, "kind": "categorical", "levels": levels}
            )
            for level in levels[1:]:
                covariate_parts.append(values.eq(level).to_numpy(dtype=float)[:, None])
                covariate_names.append(f"{column}[{level}]")

    covariate_values = (
        np.column_stack(covariate_parts)
        if covariate_parts
        else np.zeros((n_rows, 0), dtype=float)
    )
    counts = {
        group: int(np.sum(valid & (group_values == group))) for group in group_order
    }
    insufficient = {
        group: int(counts.get(group, 0))
        for group in group_order
        if int(counts.get(group, 0)) < int(min_n)
    }
    if insufficient:
        raise ValueError(
            f"association {spec['label']!r} needs at least {int(min_n)} complete "
            f"rows per group; found {insufficient}"
        )
    x = x_values[valid]
    y = y_values[valid]
    x_sd = float(np.std(x))
    y_sd = float(np.std(y))
    if x_sd <= 0 or y_sd <= 0:
        raise ValueError(f"association {spec['label']!r} has no x or y variation")
    return {
        "spec": spec,
        "covariate_schema": covariate_schema,
        "covariate_names": covariate_names,
        "covariate_values": covariate_values,
        "group_values": group_values,
        "x_values": x_values,
        "y_values": y_values,
        "valid": valid,
        "x_mean": float(np.mean(x)),
        "x_sd": x_sd,
        "y_mean": float(np.mean(y)),
        "y_sd": y_sd,
        "value": value,
    }


def _design(schema, positions, group_order, reference):
    spec = schema["spec"]
    positions = np.asarray(positions, dtype=int)
    positions = positions[schema["valid"][positions]]
    x = schema["x_values"][positions]
    y = schema["y_values"][positions]
    if schema["value"] == "beta":
        x = (x - schema["x_mean"]) / schema["x_sd"]
        y = (y - schema["y_mean"]) / schema["y_sd"]

    nonreference = [group for group in group_order if group != reference]
    group_values = schema["group_values"][positions]
    group_design = (
        np.column_stack(
            [(group_values == group).astype(float) for group in nonreference]
        )
        if nonreference
        else np.zeros((len(positions), 0), dtype=float)
    )
    interactions = group_design * x[:, None]
    covariates = schema["covariate_values"][positions]
    design = np.column_stack(
        [np.ones(len(positions), dtype=float), x, group_design, interactions, covariates]
    )
    terms = (
        ["Intercept", str(spec["x"])]
        + [f"group[{group}]" for group in nonreference]
        + [f"{spec['x']}:group[{group}]" for group in nonreference]
        + schema["covariate_names"]
    )
    counts = {
        group: int(np.sum(group_values == group)) for group in group_order
    }
    return design, y, terms, nonreference, counts


def _ols_fit(design, outcome):
    n, n_terms = design.shape
    rank = int(np.linalg.matrix_rank(design))
    if n <= n_terms or rank < n_terms:
        raise ValueError("association model design is rank deficient")
    xtx_inv = np.linalg.pinv(design.T @ design)
    coefficients = xtx_inv @ design.T @ outcome
    residuals = outcome - design @ coefficients
    df_resid = n - rank
    sigma2 = float(residuals @ residuals) / float(df_resid)
    return coefficients, sigma2 * xtx_inv, int(df_resid)


def _fit_schema(schema, positions, group_order, reference, min_n):
    design, outcome, terms, nonreference, counts = _design(
        schema, positions, group_order, reference
    )
    if any(int(counts.get(group, 0)) < int(min_n) for group in group_order):
        raise ValueError("association bootstrap sample has too few complete rows")
    coefficients, covariance, df_resid = _ols_fit(design, outcome)
    interaction_start = 2 + len(nonreference)
    interaction_indices = list(
        range(interaction_start, interaction_start + len(nonreference))
    )
    slope_contrasts = []
    for group in group_order:
        contrast = np.zeros(len(coefficients), dtype=float)
        contrast[1] = 1.0
        if group != reference:
            contrast[interaction_indices[nonreference.index(group)]] = 1.0
        slope_contrasts.append(contrast)
    slopes = np.asarray(
        [contrast @ coefficients for contrast in slope_contrasts], dtype=float
    )
    slope_variances = np.asarray(
        [contrast @ covariance @ contrast for contrast in slope_contrasts], dtype=float
    )
    interaction_values = np.asarray(coefficients[interaction_indices], dtype=float)
    return {
        "slopes": slopes,
        "slope_variances": slope_variances,
        "interactions": interaction_values,
        "terms": terms,
        "coefficients": coefficients,
        "covariance": covariance,
        "df_resid": df_resid,
        "n": int(len(outcome)),
        "counts": {group: int(counts.get(group, 0)) for group in group_order},
    }


def _fit_all(schemas, positions, group_order, reference, min_n):
    fits = [
        _fit_schema(schema, positions, group_order, reference, min_n)
        for schema in schemas
    ]
    slopes = np.concatenate([fit["slopes"] for fit in fits])
    interactions = np.concatenate([fit["interactions"] for fit in fits])
    return fits, slopes, interactions


def _apply_shared_complete_cases(schemas, group_order, min_n):
    """Use one complete-case cohort for every model in the joint analysis."""
    shared_valid = np.logical_and.reduce([schema["valid"] for schema in schemas])
    for schema in schemas:
        schema["valid"] = shared_valid.copy()
        counts = {
            group: int(
                np.sum(shared_valid & (schema["group_values"] == group))
            )
            for group in group_order
        }
        insufficient = {
            group: count
            for group, count in counts.items()
            if count < int(min_n)
        }
        if insufficient:
            raise ValueError(
                "shared complete-case cohort needs at least "
                f"{int(min_n)} rows per group; found {insufficient}"
            )
        x = schema["x_values"][shared_valid]
        y = schema["y_values"][shared_valid]
        x_sd = float(np.std(x))
        y_sd = float(np.std(y))
        if x_sd <= 0 or y_sd <= 0:
            raise ValueError(
                f"association {schema['spec']['label']!r} has no x or y variation"
            )
        schema["x_mean"] = float(np.mean(x))
        schema["x_sd"] = x_sd
        schema["y_mean"] = float(np.mean(y))
        schema["y_sd"] = y_sd


def _bootstrap(
    scope_df,
    group_col,
    schemas,
    group_order,
    reference,
    min_n,
    bootstrap_resamples,
    random_state,
):
    rng = np.random.default_rng(random_state)
    shared_valid = schemas[0]["valid"]
    group_positions = {
        group: np.flatnonzero(
            shared_valid
            & scope_df[group_col].astype(str).eq(group).to_numpy()
        )
        for group in group_order
    }
    slope_rows = []
    interaction_rows = []
    for _ in range(int(bootstrap_resamples)):
        sampled_positions = np.concatenate(
            [
                rng.choice(positions, size=len(positions), replace=True)
                for positions in group_positions.values()
            ]
        )
        try:
            _fits, slopes, interactions = _fit_all(
                schemas, sampled_positions, group_order, reference, min_n
            )
        except (ValueError, np.linalg.LinAlgError):
            continue
        if np.isfinite(slopes).all() and np.isfinite(interactions).all():
            slope_rows.append(slopes)
            interaction_rows.append(interactions)

    slopes = np.asarray(slope_rows, dtype=float)
    interactions = np.asarray(interaction_rows, dtype=float)
    minimum_valid = max(50, int(float(bootstrap_resamples) * 0.8))
    if len(slopes) < minimum_valid:
        raise RuntimeError(
            f"only {len(slopes)} of {int(bootstrap_resamples)} bootstrap samples "
            "were valid"
        )
    return slopes, interactions


def _joint_test(observed_interactions, bootstrap_interactions):
    covariance = np.atleast_2d(
        np.asarray(np.cov(bootstrap_interactions, rowvar=False, ddof=1), dtype=float)
    )
    degrees_freedom = int(np.linalg.matrix_rank(covariance))
    statistic = float(
        observed_interactions @ np.linalg.pinv(covariance) @ observed_interactions
    )
    return {
        "test": "Joint group moderation of association coefficients",
        "statistic": statistic,
        "df": degrees_freedom,
        "p": float(stats.chi2.sf(statistic, degrees_freedom)),
        "covariance": covariance,
    }


def _tables(
    schemas,
    observed_fits,
    observed_slopes,
    observed_interactions,
    bootstrap_slopes,
    bootstrap_interactions,
    group_order,
    reference,
    ci_method,
    ci_alpha,
):
    alpha = float(ci_alpha)
    quantiles = [100 * alpha / 2, 100 * (1 - alpha / 2)]
    slope_ci = np.percentile(bootstrap_slopes, quantiles, axis=0)
    interaction_ci = np.percentile(bootstrap_interactions, quantiles, axis=0)
    interaction_covariance = np.atleast_2d(
        np.cov(bootstrap_interactions, rowvar=False, ddof=1)
    )
    coefficient_rows = []
    interaction_rows = []
    slope_index = 0
    interaction_index = 0
    nonreference = [group for group in group_order if group != reference]

    for association_index, (schema, fit) in enumerate(zip(schemas, observed_fits)):
        spec = schema["spec"]
        for group_index, group in enumerate(group_order):
            estimate = float(observed_slopes[slope_index])
            if ci_method == "bootstrap":
                ci_low = float(slope_ci[0, slope_index])
                ci_high = float(slope_ci[1, slope_index])
                standard_error = float(np.std(bootstrap_slopes[:, slope_index], ddof=1))
            else:
                variance = float(fit["slope_variances"][group_index])
                standard_error = float(np.sqrt(max(variance, 0.0)))
                critical = float(stats.t.ppf(1 - alpha / 2, fit["df_resid"]))
                ci_low = estimate - critical * standard_error
                ci_high = estimate + critical * standard_error
            coefficient_rows.append(
                {
                    "association_order": association_index,
                    "association": spec["label"],
                    "x": str(spec["x"]),
                    "y": str(spec["y"]),
                    "covariates": ", ".join(map(str, spec["covariates"])),
                    "group": str(group),
                    "n": int(fit["counts"][group]),
                    "estimate": estimate,
                    "standard_error": standard_error,
                    "ci_low": float(ci_low),
                    "ci_high": float(ci_high),
                    "value": schema["value"],
                    "ci_method": ci_method,
                }
            )
            slope_index += 1

        for group in nonreference:
            estimate = float(observed_interactions[interaction_index])
            standard_error = float(
                np.sqrt(max(interaction_covariance[interaction_index, interaction_index], 0.0))
            )
            z_value = estimate / standard_error if standard_error > 0 else np.nan
            interaction_rows.append(
                {
                    "association_order": association_index,
                    "association": spec["label"],
                    "x": str(spec["x"]),
                    "y": str(spec["y"]),
                    "covariates": ", ".join(map(str, spec["covariates"])),
                    "reference": str(reference),
                    "group": str(group),
                    "estimate": estimate,
                    "standard_error": standard_error,
                    "ci_low": float(interaction_ci[0, interaction_index]),
                    "ci_high": float(interaction_ci[1, interaction_index]),
                    "z": float(z_value),
                    "p": (
                        float(2 * stats.norm.sf(abs(z_value)))
                        if np.isfinite(z_value)
                        else np.nan
                    ),
                    "value": schema["value"],
                }
            )
            interaction_index += 1
    return pd.DataFrame(coefficient_rows), pd.DataFrame(interaction_rows)


def analyze(
    scope_df,
    *,
    group_col,
    specs,
    group_order,
    reference,
    value="beta",
    ci_method="bootstrap",
    ci_alpha=0.05,
    bootstrap_resamples=5000,
    random_state=0,
    min_n=4,
):
    """Fit all association models and return plot-ready tables and joint test."""
    value = str(value).lower()
    ci_method = str(ci_method).lower()
    if value not in VALUES:
        raise ValueError(f"value must be one of {VALUES}; got {value!r}")
    if ci_method not in CI_METHODS:
        raise ValueError(f"ci_method must be one of {CI_METHODS}; got {ci_method!r}")
    if not (0 < float(ci_alpha) < 1):
        raise ValueError("ci_alpha must be between 0 and 1")
    if int(bootstrap_resamples) < 100:
        raise ValueError("bootstrap_resamples must be at least 100")
    if int(min_n) < 3:
        raise ValueError("min_n must be at least 3")

    schemas = [
        _model_schema(scope_df, group_col, spec, group_order, min_n, value)
        for spec in specs
    ]
    _apply_shared_complete_cases(schemas, group_order, min_n)
    observed_positions = np.arange(len(scope_df), dtype=int)
    observed_fits, observed_slopes, observed_interactions = _fit_all(
        schemas, observed_positions, group_order, reference, min_n
    )
    bootstrap_slopes, bootstrap_interactions = _bootstrap(
        scope_df,
        group_col,
        schemas,
        group_order,
        reference,
        min_n,
        bootstrap_resamples,
        random_state,
    )
    coefficients, interactions = _tables(
        schemas,
        observed_fits,
        observed_slopes,
        observed_interactions,
        bootstrap_slopes,
        bootstrap_interactions,
        group_order,
        reference,
        ci_method,
        ci_alpha,
    )
    joint = _joint_test(observed_interactions, bootstrap_interactions)
    joint.update(
        {
            "reference": reference,
            "bootstrap_resamples": int(bootstrap_resamples),
            "bootstrap_valid": int(len(bootstrap_slopes)),
            "random_state": random_state,
        }
    )
    return {
        "schemas": schemas,
        "coefficients": coefficients,
        "interactions": interactions,
        "joint_test": joint,
        "bootstrap": {
            "requested": int(bootstrap_resamples),
            "valid": int(len(bootstrap_slopes)),
            "random_state": random_state,
        },
    }
