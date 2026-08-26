"""
Model selection utilities.

Currently includes iterative_best_fit for leave-one-out cross-validated
iterative feature-subset search using linear regression (statsmodels OLS).
"""

from __future__ import annotations

import itertools
import hashlib
import json
import math
import os
import re
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm
from matplotlib import pyplot as plt

from PyFLASH._logging import logger as _log
from PyFLASH.config import apply_matplotlib_fast_path
apply_matplotlib_fast_path()
from PyFLASH.aesthetics import pyflash_point_size
from PyFLASH.dataframe import coerce_dataframe_input
from PyFLASH.aliases import (
    normalize_filter_by,
    prefer_alias,
    resolve_data_column_aliases,
)
try:
    from patsy import dmatrices
except Exception:  # pragma: no cover - optional import fallback
    dmatrices = None

from PyFLASH.utils import (
    save_fig, strip_name, get_columns,
    flatten_specificity_values, is_specificity_queue,
    iter_specificities, filter_df_by_specificity,
    resolve_column_key, specificity_path_parts,
)


NOT_INCLUDED_SENTINEL = "NOT_INCLUDED_IN_EXPERIMENT"
DEFAULT_EXCLUDED_PREDICTORS = {"Condition", "AnimalName", "Genotype", "Time"}


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for v in values:
        s = str(v)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _sentinel_like_mask(series, sentinel=NOT_INCLUDED_SENTINEL) -> pd.Series:
    """Mask sentinel-like tokens including common misspellings.

    Also matches the ``EXCLUDED_`` analysis-exclusion sentinels (outlier or
    manual; see :data:`PyFLASH.utils.EXCLUDED_SENTINEL_PREFIX`) so values removed
    by a rule or by the user are dropped from numeric coercion just like
    never-measured cells.
    """
    s = pd.Series(series)
    # EXCLUDED_ is anchored to the string start (it is always a leading token),
    # so a legitimate value merely *containing* the substring is not dropped.
    pat = r"(?:NOT_INCLUDED|NOT_INLCUDED|^EXCLUDED_)"
    try:
        base = s.astype(str).str.contains(pat, case=False, na=False, regex=True)
    except Exception:
        base = pd.Series(False, index=s.index)
    if sentinel:
        try:
            exact = s.astype(str).str.contains(str(sentinel), case=False, na=False)
            base = base | exact
        except Exception:
            pass
    return base


def _to_numeric_excluding_not_included(series, sentinel=NOT_INCLUDED_SENTINEL) -> pd.Series:
    s = pd.Series(series).copy()
    try:
        mask = _sentinel_like_mask(s, sentinel=sentinel)
        s = s.mask(mask, np.nan)
    except Exception:
        pass
    return pd.to_numeric(s, errors="coerce")


_flatten_specificity_values = flatten_specificity_values


_filter_df_by_specificity = filter_df_by_specificity


def _normalize_filter_tuples(spec_or_exclude):
    """
    Normalize one filter tuple or a list of tuples to a list[tuple].

    Accepted:
    - ('Condition', 'hAPP')
    - [('Condition', 'hAPP'), ('Genotype', 'Syn')]
    """
    if spec_or_exclude is None:
        return []
    if (
        isinstance(spec_or_exclude, (list, tuple))
        and len(spec_or_exclude) > 0
        and isinstance(spec_or_exclude[0], (list, tuple))
    ):
        out = []
        for item in spec_or_exclude:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append(tuple(item))
        return out
    if isinstance(spec_or_exclude, (list, tuple)) and len(spec_or_exclude) >= 2:
        return [tuple(spec_or_exclude)]
    return []


_resolve_column_key = resolve_column_key


def _drop_unused_categorical_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Remove unused categories so filtered-out levels do not linger."""
    out = df.copy()
    for col in out.columns:
        if isinstance(out[col].dtype, pd.CategoricalDtype):
            try:
                out[col] = out[col].cat.remove_unused_categories()
            except Exception:
                pass
    return out


def _normalize_exclude_strings(exclude) -> list[str]:
    if exclude is None or exclude == "":
        return []
    if isinstance(exclude, str):
        return [exclude]
    if isinstance(exclude, (list, tuple, set, np.ndarray, pd.Series, pd.Index)):
        out = []
        for v in exclude:
            sv = str(v)
            if sv != "":
                out.append(sv)
        return out
    return [str(exclude)]


def _filter_predictor_names(
    predictors: Iterable[str],
    column_strings=None,
    regex_string=None,
    exclude="",
) -> list[str]:
    """
    Filter predictor expressions by name using plotting-like column filters.
    """
    out = [str(p) for p in predictors]

    include_tokens = None
    if column_strings is not None:
        if isinstance(column_strings, str):
            include_tokens = [column_strings]
        else:
            include_tokens = [str(s) for s in column_strings]
        include_tokens = [s for s in include_tokens if s != ""]
        if len(include_tokens) == 0:
            include_tokens = None

    regex_compiled = None
    if regex_string is not None:
        regex_compiled = re.compile(str(regex_string))

    exclude_tokens = _normalize_exclude_strings(exclude)

    filtered = []
    for p in out:
        if include_tokens is not None and not any(tok in p for tok in include_tokens):
            continue
        if regex_compiled is not None and regex_compiled.search(p) is None:
            continue
        if len(exclude_tokens) > 0 and any(tok in p for tok in exclude_tokens):
            continue
        filtered.append(p)
    return _unique_preserve_order(filtered)


def _resolve_possible_predictors(
    df: pd.DataFrame,
    possible_predictors: Iterable[str] | None = None,
    column_strings=None,
    regex_string=None,
    exclude="",
) -> list[str]:
    """
    Resolve predictor pool from explicit list or plotting-style column filters.
    """
    if possible_predictors is None:
        if column_strings is None and regex_string is None:
            return [str(c) for c in df.columns]
        resolved = get_columns(
            df,
            column_strings=column_strings,
            regex_string=regex_string,
            exclude=exclude,
        )
        return [str(c) for c in resolved]

    return _filter_predictor_names(
        possible_predictors,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=exclude,
    )


def _exclude_df_by_rules(df: pd.DataFrame, exclude):
    """
    Exclude rows matching one or more tuple rules.

    Examples:
    - ('Condition', 'Syn')
    - ('Genotype', 'hAPP', 'NLGF')
    - [('Condition', 'Syn'), ('Time', 'WeekTwo')]
    """
    out = df
    for rule in _normalize_filter_tuples(exclude):
        key, *raw_vals = rule
        resolved_key = _resolve_column_key(out, key)
        if resolved_key is None:
            continue
        vals = _flatten_specificity_values(raw_vals)
        if len(vals) == 0:
            continue
        col = out[resolved_key]
        if (
            pd.api.types.is_object_dtype(col)
            or pd.api.types.is_string_dtype(col)
            or pd.api.types.is_categorical_dtype(col)
        ):
            norm_col = col.astype(str).str.strip().str.casefold()
            norm_vals = [str(v).strip().casefold() for v in vals if str(v).strip() != ""]
            if len(norm_vals) == 0:
                continue
            mask = norm_col.isin(norm_vals)
            # Also treat string rules as substring matches for common factor patterns
            # (e.g., "Syn" should exclude "Syn-..." levels).
            for nv in norm_vals:
                mask = mask | norm_col.str.contains(re.escape(nv), na=False)
            out = out[~mask]
        else:
            out = out[~col.isin(vals)]
    return out


_is_specificity_queue = is_specificity_queue
_iter_specificities = iter_specificities
_specificity_subfolder_parts = specificity_path_parts


def _normalize_numeric_dataframe(
    df: pd.DataFrame,
    method: str = "minmax",
    exclude_columns: Iterable[str] | None = None,
    sentinel: str = NOT_INCLUDED_SENTINEL,
) -> pd.DataFrame:
    """
    Normalize numeric-like columns while preserving non-numeric columns.

    Supported methods:
    - "minmax": (x - min) / (max - min)
    - "zscore": (x - mean) / std
    - "none": no scaling
    """
    method_s = str(method).strip().lower()
    if method_s not in {"minmax", "zscore", "none"}:
        raise ValueError("method must be one of: 'minmax', 'zscore', 'none'.")

    out = df.copy()
    exclude = set(exclude_columns or [])
    if method_s == "none":
        return out

    for col in out.columns:
        if col in exclude:
            continue
        numeric = _to_numeric_excluding_not_included(out[col], sentinel=sentinel)
        if numeric.notna().sum() == 0:
            continue
        if method_s == "minmax":
            vmin = float(numeric.min(skipna=True))
            vmax = float(numeric.max(skipna=True))
            denom = vmax - vmin
            if not np.isfinite(denom) or denom == 0:
                scaled = pd.Series(np.nan, index=numeric.index, dtype=float)
                scaled.loc[numeric.notna()] = 0.0
            else:
                scaled = (numeric - vmin) / denom
        else:  # zscore
            mu = float(numeric.mean(skipna=True))
            sigma = float(numeric.std(skipna=True, ddof=0))
            if not np.isfinite(sigma) or sigma == 0:
                scaled = pd.Series(np.nan, index=numeric.index, dtype=float)
                scaled.loc[numeric.notna()] = 0.0
            else:
                scaled = (numeric - mu) / sigma
        out[col] = scaled
    return out


def _safe_predictor_prefix(expr: str) -> str:
    """
    Prefix key used for repeat_features filtering.

    Examples:
    - "Iba1_ROI_Area:Drug" -> "Iba1"
    - "C(Drug)" -> "Drug"
    - "Q('MOAB-2_IntDenTotal')" -> "MOAB-2"
    """
    s = str(expr).strip()
    if ":" in s:
        s = s.split(":", 1)[0].strip()
    if "*" in s:
        s = s.split("*", 1)[0].strip()

    m_q = re.match(r"""Q\(\s*['"](.+?)['"]\s*\)""", s)
    if m_q:
        s = m_q.group(1)
    m_c = re.match(r"""C\(\s*([^)]+)\s*\)""", s)
    if m_c:
        s = m_c.group(1).strip().strip("'\"")

    if "_" in s:
        return s.split("_", 1)[0]
    return s


def _predictor_referenced_columns(expr: str, available_columns: set[str]) -> list[str]:
    """
    Resolve concrete DataFrame columns referenced by a predictor expression.
    """
    out = []
    expr_s = str(expr).strip()
    if expr_s in available_columns:
        return [expr_s]

    # Quoted patsy references: Q('col-name')
    for q_col in re.findall(r"""Q\(\s*['"](.+?)['"]\s*\)""", expr_s):
        if q_col in available_columns and q_col not in out:
            out.append(q_col)

    # C(col) categorical references.
    for c_col in re.findall(r"""C\(\s*([^)]+?)\s*\)""", expr_s):
        c_clean = str(c_col).strip().strip("'\"")
        if c_clean in available_columns and c_clean not in out:
            out.append(c_clean)

    # Plain token references (for interactions like x1:Drug).
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr_s):
        if tok in {"C", "Q", "I", "np"}:
            continue
        if tok in available_columns and tok not in out:
            out.append(tok)
    return out


def _drop_rows_with_sentinel_across_columns(
    df: pd.DataFrame,
    columns: Iterable[str],
    sentinel: str = NOT_INCLUDED_SENTINEL,
):
    """
    Drop rows where any referenced column contains NOT_INCLUDED sentinel text.

    This mirrors plotting behavior where sentinel values are treated as missing
    data points (row-level removal), not as column-level invalidators.
    """
    out = df.copy()
    col_list = [str(c) for c in _unique_preserve_order(columns) if str(c) in out.columns]
    if len(col_list) == 0:
        return out, [], 0

    drop_mask = pd.Series(False, index=out.index)
    sentinel_columns = []
    for col in col_list:
        col_mask = _sentinel_like_mask(out[col], sentinel=sentinel)
        if bool(col_mask.any()):
            sentinel_columns.append(col)
        drop_mask = drop_mask | col_mask

    dropped_rows = int(drop_mask.sum())
    if dropped_rows > 0:
        out = out.loc[~drop_mask].copy()
    return out, _unique_preserve_order(sentinel_columns), dropped_rows


def _filter_predictors_for_nan(
    df: pd.DataFrame,
    predictors: list[str],
):
    """
    Remove predictor expressions referencing columns with true NaN values.
    """
    available_columns = set([str(c) for c in df.columns])
    kept = []
    removed_nan = []

    for pred in predictors:
        pred_s = str(pred)
        refs = _predictor_referenced_columns(pred_s, available_columns)
        if len(refs) == 0:
            kept.append(pred_s)
            continue
        has_nan = False
        for col in refs:
            if df[col].isna().any():
                has_nan = True
                break
        if has_nan:
            removed_nan.append(pred_s)
            continue
        kept.append(pred_s)

    return _unique_preserve_order(kept), _unique_preserve_order(removed_nan)


def _is_valid_formula_identifier(name: str) -> bool:
    return bool(re.match(r"^[A-Za-z_]\w*$", str(name)))


def _quote_formula_name(name: str) -> str:
    s = str(name)
    if _is_valid_formula_identifier(s):
        return s
    escaped = s.replace("\\", "\\\\").replace("'", "\\'")
    return f"Q('{escaped}')"


def _format_predictor_for_formula(predictor: str, available_columns: set[str]) -> str:
    s = str(predictor).strip()
    if s in available_columns:
        return _quote_formula_name(s)
    return s


def _build_formula(dependent_variable: str, predictors: Iterable[str], available_columns: set[str]) -> str:
    dep = _quote_formula_name(dependent_variable) if dependent_variable in available_columns else str(dependent_variable)
    terms = [_format_predictor_for_formula(p, available_columns) for p in predictors]
    if len(terms) == 0:
        raise ValueError("At least one predictor is required.")
    return f"{dep} ~ " + " + ".join(terms)


def _as_string_list(value, *, name="value") -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, pd.Index, np.ndarray, pd.Series)):
        return [str(v) for v in list(value) if str(v).strip() != ""]
    raise TypeError(f"{name} must be a string or iterable of strings.")


def _normalize_interactions(interactions) -> list:
    if interactions is None:
        return []
    if isinstance(interactions, str):
        return [interactions]
    if (
        isinstance(interactions, tuple)
        and len(interactions) >= 2
        and not any(isinstance(v, (list, tuple)) for v in interactions)
    ):
        return [interactions]
    if isinstance(interactions, (list, tuple)):
        return list(interactions)
    raise TypeError("interactions must be a string, pair tuple, or iterable.")


def _resolve_summary_column(df: pd.DataFrame, key, *, required=True):
    """Resolve a user-facing column key against a processed summary table."""
    if key in df.columns:
        return key
    resolved = _resolve_column_key(df, key)
    if resolved is not None:
        return resolved

    target = re.sub(r"[^A-Za-z0-9]+", "", str(key)).casefold()
    if target != "":
        for col in df.columns:
            col_key = re.sub(r"[^A-Za-z0-9]+", "", str(col)).casefold()
            if col_key == target:
                return col

    if required:
        raise ValueError(f"Column '{key}' was not found in batch.summary.")
    return None


def _resolve_summary_columns(df: pd.DataFrame, columns, *, kind="columns") -> list[str]:
    resolved = []
    for col in _as_string_list(columns, name=kind):
        resolved.append(str(_resolve_summary_column(df, col, required=True)))
    return _unique_preserve_order(resolved)


_EMPTY_MEDICATION_VALUES = {
    "", "0", "0.0", "nan", "na", "n/a", "none", "no", "nil", "not applicable",
    "not recorded", "unknown",
}


def _split_medication_tokens(value) -> list[str]:
    """Split a free-text medication cell into normalized tokens."""
    if pd.isna(value):
        return []
    text = str(value).strip()
    if text.casefold() in _EMPTY_MEDICATION_VALUES:
        return []
    text = re.sub(r"\([^)]*\)", " ", text)
    parts = re.split(r"[,;/|+]|\band\b|&", text, flags=re.IGNORECASE)
    tokens = []
    for part in parts:
        token = re.sub(r"\s+", " ", str(part)).strip(" .:-_\t\r\n").casefold()
        if token == "" or token in _EMPTY_MEDICATION_VALUES:
            continue
        tokens.append(token)
    return _unique_preserve_order(tokens)


def _safe_generated_column(existing: set[str], prefix: str, token: str) -> str:
    base = f"{prefix}_{token}"
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_")
    if safe == "" or re.match(r"^\d", safe):
        safe = f"flag_{safe}"
    candidate = safe
    idx = 2
    while candidate in existing:
        candidate = f"{safe}_{idx}"
        idx += 1
    existing.add(candidate)
    return candidate


def _add_medication_flags(
    df: pd.DataFrame,
    medication_columns,
    *,
    mode="any",
    min_count=2,
) -> tuple[pd.DataFrame, list[str], dict]:
    """Add any/token medication flags and return generated predictor columns."""
    med_cols = _resolve_summary_columns(
        df, medication_columns, kind="medication_columns")
    mode_key = str(mode).strip().lower()
    if mode_key not in {"any", "tokens", "both"}:
        raise ValueError("medication_mode must be 'any', 'tokens', or 'both'.")
    min_count_i = max(1, int(min_count))

    out = df.copy()
    existing = set([str(c) for c in out.columns])
    generated = []
    metadata = {"columns": {}, "mode": mode_key, "min_count": min_count_i}

    for col in med_cols:
        series_tokens = out[col].map(_split_medication_tokens)
        col_meta = {"any": None, "tokens": {}}
        prefix = re.sub(r"[^A-Za-z0-9_]+", "_", str(col)).strip("_") or "meds"

        if mode_key in {"any", "both"}:
            any_col = _safe_generated_column(existing, prefix, "any")
            out[any_col] = series_tokens.map(lambda vals: int(len(vals) > 0))
            generated.append(any_col)
            col_meta["any"] = any_col

        if mode_key in {"tokens", "both"}:
            counts = {}
            for vals in series_tokens:
                for token in vals:
                    counts[token] = counts.get(token, 0) + 1
            for token in sorted(counts):
                if counts[token] < min_count_i:
                    continue
                flag_col = _safe_generated_column(existing, prefix, token)
                out[flag_col] = series_tokens.map(
                    lambda vals, t=token: int(t in vals)
                )
                generated.append(flag_col)
                col_meta["tokens"][token] = {
                    "column": flag_col,
                    "count": int(counts[token]),
                }

        metadata["columns"][col] = col_meta

    return out, generated, metadata


def _linear_model_reference_value(series: pd.Series, requested):
    levels = list(pd.Series(series).dropna().unique())
    for level in levels:
        if level == requested:
            return level
    requested_s = str(requested)
    for level in levels:
        if str(level) == requested_s:
            return level
    raise ValueError(
        f"Reference level {requested!r} was not found in column "
        f"'{getattr(series, 'name', '')}'. Available levels: {levels}"
    )


def _linear_model_term(name: str, *, categorical: set[str], reference_levels: dict) -> str:
    quoted = _quote_formula_name(name)
    if str(name) not in categorical:
        return quoted
    if str(name) in reference_levels:
        ref = reference_levels[str(name)]
        return f"C({quoted}, Treatment(reference={repr(ref)}))"
    return f"C({quoted})"


def _linear_model_interaction_term(
    interaction,
    *,
    categorical: set[str],
    reference_levels: dict,
    available_columns: set[str],
) -> str:
    if isinstance(interaction, (list, tuple)) and len(interaction) >= 2:
        parts = [str(_resolve_summary_column(pd.DataFrame(columns=list(available_columns)), p, required=False) or p)
                 for p in interaction]
        return ":".join([
            _linear_model_term(p, categorical=categorical, reference_levels=reference_levels)
            for p in parts
        ])
    return str(interaction)


def _linear_model_run_dir(base_dir: str, run_label: str, if_exists: str) -> tuple[str, str]:
    policy = str(if_exists).strip().lower()
    if policy not in {"overwrite", "version", "error"}:
        raise ValueError("if_exists must be 'overwrite', 'version', or 'error'.")
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(run_label).strip()).strip("_")
    if label == "":
        label = "linear_models"

    root = os.path.join(str(base_dir), "Modelling", "Linear Models")

    def _path(lab):
        return os.path.join(root, lab)

    out = _path(label)
    if os.path.exists(out):
        if policy == "error":
            raise RuntimeError(f"Linear model run already exists: {out}")
        if policy == "version":
            idx = 2
            while os.path.exists(_path(f"{label}_v{idx}")):
                idx += 1
            label = f"{label}_v{idx}"
            out = _path(label)
    os.makedirs(out, exist_ok=True)
    return out, label


def _fit_linear_models(
    batch,
    dependent_variables,
    predictors,
    *,
    categorical="auto",
    reference_levels=None,
    interactions=None,
    medication_columns=None,
    medication_mode="any",
    medication_min_count=2,
    specificity=None,
    exclude=None,
    cov_type=None,
    cov_kwds=None,
    alpha=0.05,
    fdr_method="fdr_bh",
    fdr_family="all",
    save=True,
    output_dir=None,
    run_label="linear_models",
    if_exists="version",
    return_fits=False,
    verbose=True,
):
    """Fit adjusted OLS models for one or more dependent variables.

    Private modelling backend used by the public linear-model pipeline. It
    returns coefficient and model-summary tables, and optionally preserves the
    legacy table-only save path used by ``run_linear_model_pipeline``.
    """
    if not hasattr(batch, "summary"):
        raise ValueError("First argument must expose a .summary DataFrame.")
    df = getattr(batch, "summary", None)
    if not isinstance(df, pd.DataFrame) or len(df) == 0:
        raise ValueError("batch.summary must be a non-empty pandas DataFrame.")

    if _is_specificity_queue(specificity):
        return {
            spec: _fit_linear_models(
                batch,
                dependent_variables=dependent_variables,
                predictors=predictors,
                categorical=categorical,
                reference_levels=reference_levels,
                interactions=interactions,
                medication_columns=medication_columns,
                medication_mode=medication_mode,
                medication_min_count=medication_min_count,
                specificity=spec,
                exclude=exclude,
                cov_type=cov_type,
                cov_kwds=cov_kwds,
                alpha=alpha,
                fdr_method=fdr_method,
                fdr_family=fdr_family,
                save=save,
                output_dir=output_dir,
                run_label=run_label,
                if_exists=if_exists,
                return_fits=return_fits,
                verbose=verbose,
            )
            for spec in _iter_specificities(specificity)
        }

    dep_vars = _resolve_summary_columns(
        df, dependent_variables, kind="dependent_variables")
    predictor_terms = []
    predictor_columns = []
    for pred in _as_string_list(predictors, name="predictors"):
        col = _resolve_summary_column(df, pred, required=False)
        if col is not None:
            predictor_columns.append(str(col))
            predictor_terms.append(str(col))
        else:
            predictor_terms.append(str(pred))
    predictor_terms = _unique_preserve_order(predictor_terms)
    predictor_columns = _unique_preserve_order(predictor_columns)
    if len(predictor_terms) == 0:
        raise ValueError("At least one predictor is required.")

    work_df = _filter_df_by_specificity(df, specificity).copy()
    pre_exclude_n = len(work_df)
    work_df = _exclude_df_by_rules(work_df, exclude).copy()
    work_df = _drop_unused_categorical_levels(work_df)
    if verbose and exclude is not None:
        _log.hint(
            f"[run_linear_model_pipeline] Exclude filter removed "
            f"{pre_exclude_n - len(work_df)} rows."
        )
    if len(work_df) == 0:
        raise ValueError("No rows remain after specificity/exclude filtering.")

    generated_medication_predictors = []
    medication_metadata = {}
    if medication_columns is not None:
        work_df, generated_medication_predictors, medication_metadata = (
            _add_medication_flags(
                work_df,
                medication_columns,
                mode=medication_mode,
                min_count=medication_min_count,
            )
        )
        predictor_terms.extend(generated_medication_predictors)
        predictor_columns.extend(generated_medication_predictors)
        predictor_terms = _unique_preserve_order(predictor_terms)
        predictor_columns = _unique_preserve_order(predictor_columns)

    reference_levels = dict(reference_levels or {})
    resolved_reference_levels = {}
    for key, value in reference_levels.items():
        col = _resolve_summary_column(work_df, key, required=True)
        resolved_reference_levels[str(col)] = value

    if categorical is None:
        categorical_set = set()
    elif isinstance(categorical, str) and categorical.strip().lower() == "auto":
        categorical_set = {
            str(col)
            for col in predictor_columns
            if (
                pd.api.types.is_object_dtype(work_df[col])
                or isinstance(work_df[col].dtype, pd.CategoricalDtype)
                or pd.api.types.is_bool_dtype(work_df[col])
            )
        }
        categorical_set.update(resolved_reference_levels.keys())
    else:
        categorical_set = set(
            _resolve_summary_columns(work_df, categorical, kind="categorical")
        )

    # Validate and normalize categorical references after filtering, before
    # those values are written into formula terms.
    for col in list(categorical_set):
        if col in resolved_reference_levels:
            resolved_reference_levels[col] = _linear_model_reference_value(
                work_df[col], resolved_reference_levels[col])

    available_columns = set([str(c) for c in work_df.columns])
    formula_terms = [
        _linear_model_term(
            str(term),
            categorical=categorical_set,
            reference_levels=resolved_reference_levels,
        )
        if str(term) in available_columns else str(term)
        for term in predictor_terms
    ]
    for interaction in _normalize_interactions(interactions):
        if isinstance(interaction, (list, tuple)):
            formula_terms.append(
                _linear_model_interaction_term(
                    interaction,
                    categorical=categorical_set,
                    reference_levels=resolved_reference_levels,
                    available_columns=available_columns,
                )
            )
        else:
            formula_terms.append(str(interaction))
    formula_terms = _unique_preserve_order(formula_terms)

    coeff_rows = []
    model_rows = []
    fits = {}
    metadata_rows = []

    for dep in dep_vars:
        dep_term = _quote_formula_name(dep)
        formula = f"{dep_term} ~ " + " + ".join(formula_terms)

        ref_columns = [dep]
        ref_columns.extend([c for c in predictor_columns if c in work_df.columns])
        for expr in predictor_terms:
            if str(expr) in work_df.columns:
                continue
            ref_columns.extend(
                _predictor_referenced_columns(str(expr), set(work_df.columns))
            )
        ref_columns = _unique_preserve_order(ref_columns)

        model_df, sentinel_cols, sentinel_rows = _drop_rows_with_sentinel_across_columns(
            work_df,
            ref_columns,
            sentinel=NOT_INCLUDED_SENTINEL,
        )
        model_df = model_df.copy()
        model_df[dep] = _to_numeric_excluding_not_included(model_df[dep])

        numeric_predictor_columns = [
            col for col in predictor_columns
            if col in model_df.columns and col not in categorical_set
        ]
        for col in numeric_predictor_columns:
            model_df[col] = _to_numeric_excluding_not_included(model_df[col])
        for col in categorical_set:
            if col in model_df.columns:
                model_df[col] = model_df[col].where(model_df[col].notna(), np.nan)

        drop_cols = _unique_preserve_order(
            [dep] + [c for c in predictor_columns if c in model_df.columns]
        )
        n_before_drop = len(model_df)
        model_df = model_df.dropna(subset=drop_cols)
        model_df = _drop_unused_categorical_levels(model_df)
        if len(model_df) < 3:
            raise ValueError(
                f"Need at least 3 complete rows to fit '{dep}'. "
                f"Only {len(model_df)} rows remain."
            )

        model = sm.OLS.from_formula(formula, data=model_df)
        if cov_type is None or str(cov_type).strip().lower() in {"", "nonrobust"}:
            fit = model.fit()
            fit_cov_type = "nonrobust"
        else:
            fit = model.fit(cov_type=str(cov_type), cov_kwds=dict(cov_kwds or {}))
            fit_cov_type = str(cov_type)
        fits[dep] = fit

        ci = fit.conf_int(alpha=float(alpha))
        for term in fit.params.index:
            low, high = ci.loc[term].tolist()
            coeff_rows.append({
                "dependent_variable": dep,
                "term": str(term),
                "estimate": float(fit.params.loc[term]),
                "std_error": float(fit.bse.loc[term]),
                "t_value": float(fit.tvalues.loc[term]),
                "p_value": float(fit.pvalues.loc[term]),
                "ci_low": float(low),
                "ci_high": float(high),
                "alpha": float(alpha),
                "formula": formula,
                "nobs": float(fit.nobs),
                "cov_type": fit_cov_type,
            })

        model_rows.append({
            "dependent_variable": dep,
            "formula": formula,
            "n_input": int(len(work_df)),
            "n_after_sentinel_filter": int(n_before_drop),
            "nobs": float(fit.nobs),
            "n_dropped": int(len(work_df) - int(fit.nobs)),
            "removed_rows_sentinel": int(sentinel_rows),
            "removed_columns_sentinel": "; ".join(sentinel_cols),
            "df_model": float(fit.df_model),
            "df_resid": float(fit.df_resid),
            "r_squared": float(getattr(fit, "rsquared", np.nan)),
            "adj_r_squared": float(getattr(fit, "rsquared_adj", np.nan)),
            "f_statistic": float(getattr(fit, "fvalue", np.nan)),
            "f_pvalue": float(getattr(fit, "f_pvalue", np.nan)),
            "aic": float(getattr(fit, "aic", np.nan)),
            "bic": float(getattr(fit, "bic", np.nan)),
            "cov_type": fit_cov_type,
        })

        metadata_rows.append({
            "dependent_variable": dep,
            "model_rows": int(fit.nobs),
            "complete_case_rows_removed": int(n_before_drop - int(fit.nobs)),
            "sentinel_rows_removed": int(sentinel_rows),
        })

    coefficients = pd.DataFrame(coeff_rows)
    model_summaries = pd.DataFrame(model_rows)
    metadata = pd.DataFrame(metadata_rows)

    coefficients["q_value"] = np.nan
    coefficients["reject_fdr"] = False
    fdr_scope = str(fdr_family).strip().lower()
    if fdr_scope not in {"none", "no", "false"} and len(coefficients) > 0:
        mask = (
            coefficients["term"].astype(str).ne("Intercept")
            & np.isfinite(coefficients["p_value"].astype(float))
        )
        if mask.any():
            labels = coefficients.index[mask].tolist()
            if fdr_scope in {"dependent_variable", "by_dependent_variable", "by_endpoint", "endpoint"}:
                families = coefficients.loc[mask, "dependent_variable"].tolist()
            else:
                families = ["all"] * len(labels)
            from PyFLASH.stats_extra import apply_fdr
            adjusted = apply_fdr(
                coefficients.loc[mask, "p_value"].tolist(),
                labels=labels,
                families=families,
                method=fdr_method,
                alpha=float(alpha),
            )
            for _, row in adjusted.iterrows():
                idx = row["label"]
                coefficients.loc[idx, "q_value"] = float(row["p_adjusted"])
                coefficients.loc[idx, "reject_fdr"] = bool(row["reject"])

    save_dir = None
    resolved_run_label = str(run_label)
    if save:
        base_dir = output_dir or getattr(batch, "data_path", None)
        if base_dir is None:
            if verbose:
                _log.warn(
                    "[run_linear_model_pipeline] batch.data_path not found. "
                    "Skipping save."
                )
        else:
            save_dir, resolved_run_label = _linear_model_run_dir(
                str(base_dir), run_label, if_exists)
            coefficients.to_csv(
                os.path.join(save_dir, "linear_model_coefficients.csv"),
                index=False,
            )
            model_summaries.to_csv(
                os.path.join(save_dir, "linear_model_summaries.csv"),
                index=False,
            )
            metadata.to_csv(
                os.path.join(save_dir, "linear_model_metadata.csv"),
                index=False,
            )
            manifest = {
                "run_label": resolved_run_label,
                "dependent_variables": dep_vars,
                "predictors": predictor_terms,
                "categorical": sorted(categorical_set),
                "reference_levels": {
                    str(k): str(v) for k, v in resolved_reference_levels.items()
                },
                "interactions": [
                    str(item) for item in _normalize_interactions(interactions)
                ],
                "medication_predictors": generated_medication_predictors,
                "medication_metadata": medication_metadata,
                "alpha": float(alpha),
                "fdr_method": str(fdr_method),
                "fdr_family": str(fdr_family),
                "cov_type": str(cov_type or "nonrobust"),
                "specificity": str(specificity),
                "exclude": str(exclude),
            }
            with open(os.path.join(save_dir, "manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2, default=str)

    if verbose:
        _log.confirm(
            "[run_linear_model_pipeline] Fitted "
            f"{len(dep_vars)} endpoint model(s); "
            f"{len(coefficients)} coefficient rows."
        )
        if save_dir is not None:
            _log.confirm(f"[run_linear_model_pipeline] Saved tables to {save_dir}")

    result = {
        "coefficients": coefficients,
        "model_summaries": model_summaries,
        "metadata": metadata,
        "formulas": {
            row["dependent_variable"]: row["formula"]
            for _, row in model_summaries.iterrows()
        },
        "predictors": predictor_terms,
        "categorical": sorted(categorical_set),
        "reference_levels": resolved_reference_levels,
        "medication_predictors": generated_medication_predictors,
        "medication_metadata": medication_metadata,
        "run_label": resolved_run_label,
        "output_dir": save_dir,
    }
    if return_fits:
        result["fits"] = fits
    return result


def run_linear_model_pipeline(
    batch,
    dependent_variables,
    predictors,
    *,
    categorical="auto",
    reference_levels=None,
    interactions=None,
    medication_columns=None,
    medication_mode="any",
    medication_min_count=2,
    specificity=None,
    exclude=None,
    cov_type=None,
    cov_kwds=None,
    alpha=0.05,
    fdr_method="fdr_bh",
    fdr_family="all",
    save=True,
    output_dir=None,
    run_label="linear_models",
    if_exists="version",
    return_fits=False,
    verbose=True,
):
    """Compatibility wrapper for the original table-only linear model workflow.

    New analysis runs should use :func:`PyFLASH.pipeline.linear_model`, which
    writes pipeline folders, adjusted means, figures, manifests, and montages.
    This wrapper keeps existing notebooks working with the original
    ``Modelling/Linear Models`` output location.
    """
    return _fit_linear_models(
        batch,
        dependent_variables=dependent_variables,
        predictors=predictors,
        categorical=categorical,
        reference_levels=reference_levels,
        interactions=interactions,
        medication_columns=medication_columns,
        medication_mode=medication_mode,
        medication_min_count=medication_min_count,
        specificity=specificity,
        exclude=exclude,
        cov_type=cov_type,
        cov_kwds=cov_kwds,
        alpha=alpha,
        fdr_method=fdr_method,
        fdr_family=fdr_family,
        save=save,
        output_dir=output_dir,
        run_label=run_label,
        if_exists=if_exists,
        return_fits=return_fits,
        verbose=verbose,
    )


def _subset_key(subset: Iterable[str]) -> tuple[str, ...]:
    return tuple([str(s) for s in subset])


def _feature_change_summary_df(feature_stats: dict) -> pd.DataFrame:
    rows = []
    for feature, stats in feature_stats.items():
        deltas = stats.get("delta", [])
        pct_deltas = stats.get("pct_delta", [])
        rows.append({
            "feature": str(feature),
            "n_added": int(stats.get("n_added", 0)),
            "improved_count": int(stats.get("improved_count", 0)),
            "reduced_count": int(stats.get("reduced_count", 0)),
            "unchanged_count": int(stats.get("unchanged_count", 0)),
            "mean_delta": float(np.mean(deltas)) if len(deltas) > 0 else np.nan,
            "mean_abs_delta": float(np.mean(np.abs(deltas))) if len(deltas) > 0 else np.nan,
            "mean_pct_delta": float(np.mean(pct_deltas)) if len(pct_deltas) > 0 else np.nan,
        })
    if len(rows) == 0:
        return pd.DataFrame(
            columns=[
                "feature",
                "n_added",
                "improved_count",
                "reduced_count",
                "unchanged_count",
                "mean_delta",
                "mean_abs_delta",
                "mean_pct_delta",
            ]
        )
    out = pd.DataFrame(rows)
    out = out.sort_values(
        by=["improved_count", "mean_delta", "n_added", "feature"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    return out


def _insight_plot_config(n_features: int) -> dict:
    """
    Adaptive layout so insight bars remain readable with large feature counts.
    """
    n = max(1, int(n_features))
    if n <= 30:
        fig_w = max(10.0, 6.5 + (0.33 * n))
        tick_size = max(7, 11 - int(n / 12))
        return {
            "orientation": "vertical",
            "figsize": (fig_w, 6.5),
            "tick_size": tick_size,
            "rotation": 60,
            "bar_width": 0.42,
        }

    # Horizontal layout is much clearer for many features.
    fig_h = min(40.0, max(8.0, 3.0 + (0.23 * n)))
    tick_size = max(6, 10 - int((n - 30) / 35))
    return {
        "orientation": "horizontal",
        "figsize": (12.0, fig_h),
        "tick_size": tick_size,
        "rotation": 0,
        "bar_width": 0.36,
    }


def _leave_one_out_mae(
    df: pd.DataFrame,
    formula: str,
    dependent_variable: str,
    group_column: str | None = "AnimalName",
    collect_predictions: bool = True,
):
    """
    LOO-CV MAE for one formula.

    If `group_column` exists, performs leave-one-group-out (e.g., leave one
    animal out), computes MAE per held-out group, then averages across groups.
    Otherwise falls back to row-wise leave-one-out.
    Returns (mae, actual, predicted, params, fold_mae_list).
    """
    n = len(df)
    if n < 2:
        return np.inf, [], [], None, []

    actual = [] if bool(collect_predictions) else None
    predicted = [] if bool(collect_predictions) else None
    last_params = None
    fold_mae_list = []

    if group_column is not None and group_column in df.columns:
        group_series = df[group_column]
        group_values = group_series.dropna().astype(str).unique().tolist()
        if len(group_values) < 2:
            return np.inf, [], [], None, []

        for g in group_values:
            test_mask = group_series.astype(str) == str(g)
            train = df.loc[~test_mask]
            test = df.loc[test_mask]
            if len(train) < 2 or len(test) == 0:
                return np.inf, [], [], None, []
            try:
                fit = sm.OLS.from_formula(formula, data=train).fit()
                pred = pd.to_numeric(pd.Series(fit.predict(test), index=test.index), errors="coerce")
                true = pd.to_numeric(test[dependent_variable], errors="coerce")
            except Exception:
                return np.inf, [], [], None, []

            pair = pd.DataFrame({"y": true, "yhat": pred}).dropna()
            if len(pair) == 0:
                return np.inf, [], [], None, []

            fold_mae = float(np.mean(np.abs(pair["y"] - pair["yhat"])))
            if not np.isfinite(fold_mae):
                return np.inf, [], [], None, []
            fold_mae_list.append(fold_mae)
            if bool(collect_predictions):
                actual.extend(pair["y"].tolist())
                predicted.extend(pair["yhat"].tolist())
                last_params = fit.params

        mae = float(np.mean(fold_mae_list))
        return mae, (actual or []), (predicted or []), last_params, fold_mae_list

    # Row-wise fallback.
    row_idx = np.arange(n)
    for i in row_idx:
        train = df.iloc[row_idx != i]
        test = df.iloc[[i]]
        try:
            fit = sm.OLS.from_formula(formula, data=train).fit()
            pred_val = float(np.asarray(fit.predict(test))[0])
            true_val = float(pd.to_numeric(test[dependent_variable], errors="coerce").iloc[0])
        except Exception:
            return np.inf, [], [], None, []

        if not np.isfinite(pred_val) or not np.isfinite(true_val):
            return np.inf, [], [], None, []

        err = abs(true_val - pred_val)
        fold_mae_list.append(float(err))
        if bool(collect_predictions):
            actual.append(true_val)
            predicted.append(pred_val)
            last_params = fit.params

    mae = float(np.mean(fold_mae_list))
    return mae, (actual or []), (predicted or []), last_params, fold_mae_list


def _leave_one_out_mae_fast(
    df: pd.DataFrame,
    formula: str,
    dependent_variable: str,
    group_column: str | None = "AnimalName",
    collect_predictions: bool = True,
):
    """
    Faster LOO-CV MAE using one Patsy design-matrix build per formula and
    numpy least-squares for each fold.
    """
    if dmatrices is None:
        return np.inf, [], [], None, []

    try:
        y_df, x_df = dmatrices(formula, data=df, return_type="dataframe")
    except Exception:
        return np.inf, [], [], None, []

    if len(y_df) < 2 or x_df.shape[1] == 0:
        return np.inf, [], [], None, []

    try:
        y = np.asarray(y_df.iloc[:, 0], dtype=float)
        x = np.asarray(x_df, dtype=float)
    except Exception:
        return np.inf, [], [], None, []

    if (not np.isfinite(y).all()) or (not np.isfinite(x).all()):
        return np.inf, [], [], None, []

    n = len(y)
    if n < 2:
        return np.inf, [], [], None, []

    actual = [] if bool(collect_predictions) else None
    predicted = [] if bool(collect_predictions) else None
    fold_mae_list = []
    last_params = None

    if group_column is not None and group_column in df.columns:
        group_series = df.loc[y_df.index, group_column]
        group_values = group_series.dropna().astype(str).unique().tolist()
        if len(group_values) < 2:
            return np.inf, [], [], None, []

        group_as_str = group_series.astype(str)
        for g in group_values:
            test_mask = (group_as_str == str(g)).to_numpy()
            train_mask = ~test_mask
            if int(train_mask.sum()) < 2 or int(test_mask.sum()) == 0:
                return np.inf, [], [], None, []
            try:
                beta, *_ = np.linalg.lstsq(x[train_mask], y[train_mask], rcond=None)
                yhat = np.asarray(x[test_mask] @ beta, dtype=float)
                ytrue = np.asarray(y[test_mask], dtype=float)
            except Exception:
                return np.inf, [], [], None, []

            good = np.isfinite(yhat) & np.isfinite(ytrue)
            if int(good.sum()) == 0:
                return np.inf, [], [], None, []
            err = np.abs(ytrue[good] - yhat[good])
            fold_mae = float(np.mean(err))
            if not np.isfinite(fold_mae):
                return np.inf, [], [], None, []
            fold_mae_list.append(fold_mae)
            if bool(collect_predictions):
                actual.extend(ytrue[good].tolist())
                predicted.extend(yhat[good].tolist())
                last_params = pd.Series(beta, index=x_df.columns)

        mae = float(np.mean(fold_mae_list))
        return mae, (actual or []), (predicted or []), last_params, fold_mae_list

    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        test_mask = ~train_mask
        try:
            beta, *_ = np.linalg.lstsq(x[train_mask], y[train_mask], rcond=None)
            yhat = np.asarray(x[test_mask] @ beta, dtype=float)
            ytrue = np.asarray(y[test_mask], dtype=float)
        except Exception:
            return np.inf, [], [], None, []
        if yhat.size != 1 or ytrue.size != 1:
            return np.inf, [], [], None, []
        pred_val = float(yhat[0])
        true_val = float(ytrue[0])
        if not np.isfinite(pred_val) or not np.isfinite(true_val):
            return np.inf, [], [], None, []
        fold_mae_list.append(float(abs(true_val - pred_val)))
        if bool(collect_predictions):
            actual.append(true_val)
            predicted.append(pred_val)
            last_params = pd.Series(beta, index=x_df.columns)

    mae = float(np.mean(fold_mae_list))
    return mae, (actual or []), (predicted or []), last_params, fold_mae_list


def _leave_one_out_mae_matrix_fast(
    x: np.ndarray,
    y: np.ndarray,
    predictor_names: list[str],
    group_values=None,
    group_indices=None,
    collect_predictions: bool = True,
):
    """
    Ultra-fast LOO/group-LOO MAE from prebuilt numeric design matrix.
    Adds an intercept column internally.
    """
    try:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float).reshape(-1)
    except Exception:
        return np.inf, [], [], None, []

    if x.ndim != 2 or y.ndim != 1:
        return np.inf, [], [], None, []
    n = x.shape[0]
    if n < 2 or x.shape[1] == 0 or n != y.shape[0]:
        return np.inf, [], [], None, []
    if (not np.isfinite(x).all()) or (not np.isfinite(y).all()):
        return np.inf, [], [], None, []

    x1 = np.column_stack([np.ones((n, 1), dtype=float), x])
    col_names = ["Intercept"] + [str(c) for c in predictor_names]

    actual = [] if bool(collect_predictions) else None
    predicted = [] if bool(collect_predictions) else None
    fold_mae_list = []
    last_beta = None
    last_params = None

    # Group-wise leave-one-group-out.
    if group_indices is not None:
        group_idx_list = [np.asarray(idx, dtype=int) for idx in group_indices if len(idx) > 0]
        if len(group_idx_list) < 2:
            return np.inf, [], [], None, []
    elif group_values is not None:
        g_series = pd.Series(group_values)
        g = g_series.astype(str).to_numpy()
        if len(g) != n:
            return np.inf, [], [], None, []
        uniq = g_series[g_series.notna()].astype(str).unique().tolist()
        if len(uniq) < 2:
            return np.inf, [], [], None, []
        group_idx_list = [np.flatnonzero(g == str(gv)) for gv in uniq]
        group_idx_list = [idx for idx in group_idx_list if len(idx) > 0]
        if len(group_idx_list) < 2:
            return np.inf, [], [], None, []
    else:
        group_idx_list = None

    if group_idx_list is not None:
        s_full = x1.T @ x1
        t_full = x1.T @ y
        for test_idx in group_idx_list:
            test_mask = np.zeros(n, dtype=bool)
            test_mask[test_idx] = True
            train_n = int((~test_mask).sum())
            test_n = int(test_mask.sum())
            if train_n < 2 or test_n == 0:
                return np.inf, [], [], None, []

            xg = x1[test_idx]
            yg = y[test_idx]
            s_train = s_full - (xg.T @ xg)
            t_train = t_full - (xg.T @ yg)
            try:
                beta = np.linalg.solve(s_train, t_train)
            except Exception:
                try:
                    beta = np.linalg.lstsq(s_train, t_train, rcond=None)[0]
                except Exception:
                    return np.inf, [], [], None, []

            yhat = xg @ beta
            if not np.isfinite(yhat).all():
                return np.inf, [], [], None, []
            err = np.abs(yg - yhat)
            fold_mae = float(np.mean(err))
            if not np.isfinite(fold_mae):
                return np.inf, [], [], None, []
            fold_mae_list.append(fold_mae)
            if bool(collect_predictions):
                actual.extend(yg.tolist())
                predicted.extend(yhat.tolist())
                last_beta = beta.copy()

        mae = float(np.mean(fold_mae_list))
        if bool(collect_predictions) and last_beta is not None:
            last_params = pd.Series(last_beta, index=col_names)
        return mae, (actual or []), (predicted or []), last_params, fold_mae_list

    # Row-wise LOO with PRESS identity from one full fit.
    s_full = x1.T @ x1
    try:
        s_inv = np.linalg.inv(s_full)
    except Exception:
        s_inv = np.linalg.pinv(s_full)

    beta = s_inv @ (x1.T @ y)
    yhat = x1 @ beta
    resid = y - yhat
    h = np.einsum("ij,jk,ik->i", x1, s_inv, x1)
    denom = 1.0 - h
    tiny = np.abs(denom) <= 1e-10

    if bool(tiny.any()):
        # Fallback for near-singular leverage cases.
        for i in range(n):
            train_mask = np.ones(n, dtype=bool)
            train_mask[i] = False
            xt = x1[train_mask]
            yt = y[train_mask]
            try:
                b_i = np.linalg.lstsq(xt, yt, rcond=None)[0]
            except Exception:
                return np.inf, [], [], None, []
            y_pred_i = float(x1[i] @ b_i)
            y_true_i = float(y[i])
            if not np.isfinite(y_pred_i) or not np.isfinite(y_true_i):
                return np.inf, [], [], None, []
            fold_mae_list.append(float(abs(y_true_i - y_pred_i)))
            if bool(collect_predictions):
                actual.append(y_true_i)
                predicted.append(y_pred_i)
        mae = float(np.mean(fold_mae_list))
        if bool(collect_predictions):
            last_params = pd.Series(beta, index=col_names)
        return mae, (actual or []), (predicted or []), last_params, fold_mae_list

    loo_err = resid / denom
    loo_pred = y - loo_err
    if (not np.isfinite(loo_pred).all()) or (not np.isfinite(loo_err).all()):
        return np.inf, [], [], None, []

    fold_mae_list = np.abs(loo_err).astype(float).tolist()
    if bool(collect_predictions):
        actual = y.astype(float).tolist()
        predicted = loo_pred.astype(float).tolist()
    mae = float(np.mean(np.abs(loo_err)))
    if bool(collect_predictions):
        last_params = pd.Series(beta, index=col_names)
    return mae, (actual or []), (predicted or []), last_params, fold_mae_list


# ---------------------------------------------------------------------------
# Batched scoring — vectorised across all model subsets at a given level k
# ---------------------------------------------------------------------------

def _batch_press_mae(x1, y, idx_arr, chunk_size=5000):
    """
    Batch LOO MAE for many models using the PRESS identity.

    Parameters
    ----------
    x1 : ndarray (n, p+1)
        Full design matrix (intercept at column 0, all candidate predictors).
    y : ndarray (n,)
        Response vector.
    idx_arr : ndarray (M, k+1), int
        Column indices into *x1* for each model (col 0 = intercept).
    chunk_size : int
        Models per vectorised batch (controls peak memory).

    Returns
    -------
    mae : ndarray (M,)
        LOO MAE per model (``inf`` for degenerate models).
    """
    n = x1.shape[0]
    M, k1 = idx_arr.shape
    mae = np.full(M, np.inf)

    G_full = x1.T @ x1          # (p+1, p+1)
    c_full = x1.T @ y            # (p+1,)

    for start in range(0, M, chunk_size):
        end = min(start + chunk_size, M)
        idx = idx_arr[start:end]                    # (C, k+1)
        C = end - start

        # Sub-Gram matrices via advanced indexing
        G_sub = G_full[idx[:, :, None], idx[:, None, :]]   # (C, k+1, k+1)
        c_sub = c_full[idx]                                  # (C, k+1)

        # Batch invert — singular models handled below
        try:
            G_inv = np.linalg.inv(G_sub)
        except np.linalg.LinAlgError:
            # At least one singular model in the chunk — fall back per-model
            G_inv = np.empty_like(G_sub)
            ok = np.ones(C, dtype=bool)
            for j in range(C):
                try:
                    G_inv[j] = np.linalg.inv(G_sub[j])
                except np.linalg.LinAlgError:
                    G_inv[j] = 0.0
                    ok[j] = False
            mae[start:end][~ok] = np.inf
            if not ok.any():
                continue
            # Zero out bad entries so downstream math doesn't NaN-propagate;
            # their mae slots are already inf and will be skipped.

        beta = np.einsum("cij,cj->ci", G_inv, c_sub)       # (C, k+1)

        # X_batch: (C, n, k+1)
        X_batch = x1[:, idx.ravel()].reshape(n, C, k1).transpose(1, 0, 2)

        yhat = np.einsum("cnj,cj->cn", X_batch, beta)       # (C, n)
        resid = y[None, :] - yhat                            # (C, n)

        # Hat-matrix diagonal
        XG = np.einsum("cnj,cjk->cnk", X_batch, G_inv)      # (C, n, k+1)
        h = np.einsum("cnk,cnk->cn", XG, X_batch)            # (C, n)
        del XG

        denom = 1.0 - h
        bad_lev = np.abs(denom) <= 1e-10
        denom[bad_lev] = 1.0                                  # avoid /0
        press = resid / denom

        mae_chunk = np.mean(np.abs(press), axis=1)
        mae_chunk[bad_lev.any(axis=1)] = np.inf
        mae_chunk[~np.isfinite(mae_chunk)] = np.inf
        mae[start:end] = mae_chunk

    return mae


def _batch_group_loo_mae(x1, y, idx_arr, group_indices, chunk_size=5000):
    """
    Batch group-LOO MAE for many models.

    Same signature contract as :func:`_batch_press_mae` but folds are
    defined by *group_indices* (list of 1-d int arrays, one per group).
    """
    M, k1 = idx_arr.shape
    G_num = len(group_indices)
    mae = np.full(M, np.inf)

    G_full = x1.T @ x1
    c_full = x1.T @ y

    G_groups = []
    c_groups = []
    for gidx in group_indices:
        xg = x1[gidx]
        yg = y[gidx]
        G_groups.append(xg.T @ xg)
        c_groups.append(xg.T @ yg)

    for start in range(0, M, chunk_size):
        end = min(start + chunk_size, M)
        idx = idx_arr[start:end]
        C = end - start

        G_sub_full = G_full[idx[:, :, None], idx[:, None, :]]
        c_sub_full = c_full[idx]

        fold_mae = np.zeros((C, G_num))
        valid = np.ones((C, G_num), dtype=bool)

        for g, gidx_g in enumerate(group_indices):
            G_g_sub = G_groups[g][idx[:, :, None], idx[:, None, :]]
            c_g_sub = c_groups[g][idx]

            A_train = G_sub_full - G_g_sub
            b_train = c_sub_full - c_g_sub

            try:
                # b needs trailing dim so numpy uses batched vector solve
                beta = np.linalg.solve(
                    A_train, b_train[..., np.newaxis],
                )[..., 0]
            except np.linalg.LinAlgError:
                beta = np.full((C, k1), np.nan)
                for j in range(C):
                    try:
                        beta[j] = np.linalg.solve(A_train[j], b_train[j])
                    except Exception:
                        valid[j, g] = False

            # Test-set predictions
            xg_full = x1[gidx_g]          # (m, p+1)
            yg = y[gidx_g]                 # (m,)
            m = len(gidx_g)

            X_test = xg_full[:, idx.ravel()].reshape(m, C, k1).transpose(1, 0, 2)
            yhat = np.einsum("cmj,cj->cm", X_test, beta)

            err = np.abs(yg[None, :] - yhat)
            fold_mae[:, g] = np.mean(err, axis=1)
            valid[~np.isfinite(yhat).all(axis=1), g] = False

        mae_chunk = np.mean(fold_mae, axis=1)
        mae_chunk[~valid.all(axis=1)] = np.inf
        mae_chunk[~np.isfinite(mae_chunk)] = np.inf
        mae[start:end] = mae_chunk

    return mae


def _batch_score(x1, y, idx_arr, group_indices, chunk_size=5000):
    """Dispatch to PRESS (row-LOO) or group-LOO batch scorer."""
    if group_indices is not None and len(group_indices) >= 2:
        return _batch_group_loo_mae(x1, y, idx_arr, group_indices, chunk_size)
    return _batch_press_mae(x1, y, idx_arr, chunk_size)


# ---------------------------------------------------------------------------
# Beam-search expansion
# ---------------------------------------------------------------------------

def _beam_expand(surviving, n_predictors, repeat_features, prefix_list):
    """
    Expand a beam of surviving subsets by adding one predictor.

    Parameters
    ----------
    surviving : list[tuple[int, ...]]
        Current beam (predictor *index* tuples, 0-based).
    n_predictors : int
        Total number of candidate predictors.
    repeat_features : bool
        Allow same-prefix predictors in one subset.
    prefix_list : list[str]
        ``prefix_list[i]`` = prefix for predictor *i*.

    Returns
    -------
    candidates : list[tuple[int, ...]]
        Unique expanded subsets (sorted internally, deduplicated).
    """
    seen = set()
    out = []
    for sub in surviving:
        sub_set = set(sub)
        for p in range(n_predictors):
            if p in sub_set:
                continue
            new_sub = tuple(sorted(sub + (p,)))
            if new_sub in seen:
                continue
            if not repeat_features:
                prefixes = [prefix_list[i] for i in new_sub]
                if len(prefixes) != len(set(prefixes)):
                    continue
            seen.add(new_sub)
            out.append(new_sub)
    return out


def _iter_feature_combinations(
    predictors: list[str],
    max_features: int,
    repeat_features: bool = False,
) -> list[tuple[str, ...]]:
    combos: list[tuple[str, ...]] = []
    for k in range(1, int(max_features) + 1):
        combos.extend(
            _iter_valid_feature_combinations_by_size(
                predictors,
                k,
                repeat_features=repeat_features,
            )
        )
    return combos


def _iter_valid_feature_combinations_by_size(
    predictors: list[str],
    size: int,
    repeat_features: bool = False,
    prefix_list: list[str] | None = None,
):
    """Yield combinations while enforcing the same-prefix filter during search."""
    size_i = int(size)
    if size_i <= 0:
        return
    if bool(repeat_features):
        yield from itertools.combinations(predictors, size_i)
        return

    predictors = [str(p) for p in predictors]
    prefixes = prefix_list if prefix_list is not None else [_safe_predictor_prefix(p) for p in predictors]
    n_predictors = len(predictors)
    current: list[int] = []
    used_prefixes: set[str] = set()

    def _walk(start: int):
        remaining = size_i - len(current)
        if remaining == 0:
            yield tuple(predictors[i] for i in current)
            return
        last_start = n_predictors - remaining + 1
        for idx in range(start, last_start):
            prefix = prefixes[idx]
            if prefix in used_prefixes:
                continue
            current.append(idx)
            used_prefixes.add(prefix)
            yield from _walk(idx + 1)
            used_prefixes.remove(prefix)
            current.pop()

    yield from _walk(0)


def _count_valid_feature_combinations(
    predictors: list[str],
    max_features: int,
    repeat_features: bool = False,
    prefix_list: list[str] | None = None,
) -> int:
    max_i = max(0, min(int(max_features), len(predictors)))
    if max_i == 0:
        return 0
    if bool(repeat_features):
        return int(sum(math.comb(len(predictors), k) for k in range(1, max_i + 1)))

    prefixes = prefix_list if prefix_list is not None else [_safe_predictor_prefix(p) for p in predictors]
    group_sizes = pd.Series([str(p) for p in prefixes], dtype=object).value_counts().to_list()

    # Valid subsets choose at most one predictor from each same-prefix group.
    # Count coefficients of product(1 + group_size*x), truncated at max_i.
    coeff = [1] + [0] * max_i
    for group_size in group_sizes:
        g = int(group_size)
        for k in range(max_i, 0, -1):
            coeff[k] += coeff[k - 1] * g
    return int(sum(coeff[1: max_i + 1]))


def _primary_predictor(expr: str) -> str:
    s = str(expr).strip()
    for op in [":", "*", "+"]:
        if op in s:
            s = s.split(op, 1)[0].strip()
    m_q = re.match(r"""Q\(\s*['"](.+?)['"]\s*\)""", s)
    if m_q:
        return m_q.group(1)
    m_c = re.match(r"""C\(\s*([^)]+)\s*\)""", s)
    if m_c:
        return m_c.group(1).strip().strip("'\"")
    return s


def _format_predictor_annotation(predictors: list[str], max_features: int, line_len: int = 78) -> str:
    """Build a wrapped annotation string for predictor pool metadata."""
    header = f"max_features: {int(max_features)}"
    if len(predictors) == 0:
        return header + "\npossible predictors: none"

    lines = []
    current = ""
    for p in predictors:
        tok = str(p)
        if current == "":
            current = tok
        elif len(current) + 2 + len(tok) <= int(line_len):
            current = f"{current}, {tok}"
        else:
            lines.append(current)
            current = tok
    if current != "":
        lines.append(current)

    return "\n".join([header, "possible predictors:"] + lines)


def _format_model_annotation(model_fit, max_param_lines: int = 14) -> str:
    """Build model-parameters + summary annotation text."""
    lines = ["model params:"]
    params = getattr(model_fit, "params", None)
    if params is not None:
        p_ser = pd.Series(params)
        shown = 0
        for key, value in p_ser.items():
            if shown >= int(max_param_lines):
                break
            try:
                val_txt = f"{float(value):.4g}"
            except Exception:
                val_txt = str(value)
            lines.append(f"{key}: {val_txt}")
            shown += 1
        if len(p_ser) > int(max_param_lines):
            lines.append(f"... (+{len(p_ser) - int(max_param_lines)} more)")
    else:
        lines.append("n/a")

    def _fmt_num(v, fmt=".4g"):
        try:
            fv = float(v)
        except Exception:
            return "n/a"
        if not np.isfinite(fv):
            return "n/a"
        return format(fv, fmt)

    summary_lines = [
        "summary:",
        f"R²: {_fmt_num(getattr(model_fit, 'rsquared', np.nan))}",
        f"Adj R²: {_fmt_num(getattr(model_fit, 'rsquared_adj', np.nan))}",
        f"F-stat: {_fmt_num(getattr(model_fit, 'fvalue', np.nan))}",
        f"F p-val: {_fmt_num(getattr(model_fit, 'f_pvalue', np.nan), '.3g')}",
        f"AIC: {_fmt_num(getattr(model_fit, 'aic', np.nan))}",
        f"BIC: {_fmt_num(getattr(model_fit, 'bic', np.nan))}",
        f"N: {_fmt_num(getattr(model_fit, 'nobs', np.nan), '.0f')}",
        f"df_model: {_fmt_num(getattr(model_fit, 'df_model', np.nan), '.0f')}",
        f"df_resid: {_fmt_num(getattr(model_fit, 'df_resid', np.nan), '.0f')}",
    ]
    return "\n".join(lines + summary_lines)


def iterative_best_fit(
    batch,
    dependent_variable: str,
    repeat_features: bool = False,
    max_features: int = 0,
    possible_predictors: Iterable[str] | None = None,
    column_strings=None,
    regex_string=None,
    predictor_exclude="",
    data_col_contains=None,
    data_col_regex=None,
    data_col_exclude=None,
    normalize_method: str = "minmax",
    excluded_predictors: Iterable[str] | None = None,
    hue_column: str = "Condition",
    color_by: str | None = None,
    palette: dict | None = None,
    save: bool = True,
    dpi: int = 600,
    plot: bool = True,
    verbose: bool = True,
    return_details: bool = False,
    specificity=None,
    filter_by=None,
    exclude=None,
    cv_group_column: str | None = "AnimalName",
    cv_backend: str = "fast",
    plot_insights: bool = True,
    top_n_single_predictors: int = 3,
    search_strategy: str = "exhaustive",
    beam_width: int = 100,
    batch_chunk_size: int = 5000,
    conditions=None,
    condition_col: str = "Condition",
    factor_cols=None,
    animal_col: str = "AnimalName",
    group_list=None,
    groups=None,
    group_col=None,
    group_cols=None,
    subject_col=None,
    dataframe_kwargs=None,
):
    """
    Iterative leave-one-out CV search for the best linear formula fit.

    Parameters mirror the legacy notebook function while adding:
    - possible_predictors can be filtered via:
      column_strings / regex_string / predictor_exclude
      using the same matching semantics as plotting.get_columns.
    - normalize_method: 'minmax' | 'zscore' | 'none'
    - save controls figure export (path/name derived from batch object)
    - specificity: tuple filter like ('Time', 'WeekFour', 'WeekEight')
      or queue of tuples
    - exclude: tuple or list of tuples to remove rows, e.g.
      ('Condition', 'Syn') or [('Condition', 'Syn'), ('Genotype', 'hAPP')]
    - first arg must expose batch.summary (and batch.fig_path when save=True)
    - cv_group_column: leave-one-group-out column (default 'AnimalName').
      If missing, falls back to row-wise leave-one-out.
    - cv_backend: 'ultra' (matrix backend when possible),
      'fast' (patsy + numpy lstsq) or 'statsmodels'
    - plot_insights: plot feature-addition insight bar plots.
    - top_n_single_predictors: number of top single-feature models to report.
    - return_details: return rich result dict (instead of tuple)
    - search_strategy: 'exhaustive' (test every combination) or 'beam'
      (forward beam search — much faster for large predictor pools, may miss
      the global optimum in rare cases).
    - beam_width: how many top models to carry forward at each level when
      search_strategy='beam'. Default 100.
    - batch_chunk_size: number of models per vectorised batch in the ultra
      backend.  Controls peak memory; default 5000 is fine for n < 1000.
    """
    _, column_strings, regex_string, predictor_exclude = resolve_data_column_aliases(
        filtered_columns=None,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=predictor_exclude,
        data_cols=None,
        data_col_contains=data_col_contains,
        data_col_regex=data_col_regex,
        data_col_exclude=data_col_exclude,
    )
    hue_column = prefer_alias(
        hue_column,
        color_by,
        current_name="hue_column",
        alias_name="color_by",
        default="Condition",
    )
    specificity = prefer_alias(
        specificity,
        normalize_filter_by(filter_by),
        current_name="specificity",
        alias_name="filter_by",
    )
    batch = coerce_dataframe_input(
        batch,
        conditions=conditions,
        condition_col=condition_col,
        factor_cols=factor_cols,
        animal_col=animal_col,
        group_list=group_list,
        groups=groups,
        group_col=group_col,
        group_cols=group_cols,
        subject_col=subject_col,
        dataframe_kwargs=dataframe_kwargs,
    )
    if not hasattr(batch, "summary"):
        raise ValueError("First argument must be a batch-like object exposing .summary.")
    df = getattr(batch, "summary", None)
    if not isinstance(df, pd.DataFrame) or len(df) == 0:
        raise ValueError("batch.summary must be a non-empty pandas DataFrame.")

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = iterative_best_fit(
                batch,
                dependent_variable=dependent_variable,
                repeat_features=repeat_features,
                max_features=max_features,
                possible_predictors=possible_predictors,
                column_strings=column_strings,
                regex_string=regex_string,
                predictor_exclude=predictor_exclude,
                normalize_method=normalize_method,
                excluded_predictors=excluded_predictors,
                hue_column=hue_column,
                palette=palette,
                save=save,
                dpi=dpi,
                plot=plot,
                plot_insights=plot_insights,
                top_n_single_predictors=top_n_single_predictors,
                verbose=verbose,
                return_details=return_details,
                specificity=spec,
                exclude=exclude,
                cv_group_column=cv_group_column,
                cv_backend=cv_backend,
                search_strategy=search_strategy,
                beam_width=beam_width,
                batch_chunk_size=batch_chunk_size,
            )
        return queued_outputs

    if dependent_variable not in df.columns:
        raise ValueError(f"dependent_variable '{dependent_variable}' not found in df.")

    predictor_name_blacklist = set(DEFAULT_EXCLUDED_PREDICTORS)
    if excluded_predictors is not None:
        predictor_name_blacklist.update([str(c) for c in excluded_predictors])
    predictor_name_blacklist.add(str(dependent_variable))

    predictors = _resolve_possible_predictors(
        df,
        possible_predictors=possible_predictors,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=predictor_exclude,
    )
    predictors = [p for p in predictors if str(p) not in predictor_name_blacklist]
    predictors = _unique_preserve_order(predictors)
    if len(predictors) == 0:
        raise ValueError(
            "No predictors available after filtering. "
            "Check possible_predictors/column_strings/regex_string/predictor_exclude."
        )

    exclude_filter = exclude
    work_df = _filter_df_by_specificity(df, specificity).copy()
    pre_exclude_n = len(work_df)
    work_df = _exclude_df_by_rules(work_df, exclude_filter).copy()
    work_df = _drop_unused_categorical_levels(work_df)
    if verbose and exclude_filter is not None:
        _log.hint(f"[iterative_best_fit] Exclude filter removed {pre_exclude_n - len(work_df)} rows.")
    if len(work_df) == 0:
        raise ValueError("No rows remain after specificity/exclude filtering.")

    referenced_columns = set([str(c) for c in work_df.columns])
    model_ref_columns = [str(dependent_variable)]
    for pred in predictors:
        model_ref_columns.extend(_predictor_referenced_columns(pred, referenced_columns))
    work_df, removed_sentinel_columns, removed_sentinel_rows = _drop_rows_with_sentinel_across_columns(
        work_df,
        model_ref_columns,
        sentinel=NOT_INCLUDED_SENTINEL,
    )
    if verbose:
        _log.hint(
            f"[iterative_best_fit] Removed {removed_sentinel_rows} rows with "
            "NOT_INCLUDED sentinel values."
        )
    if len(work_df) == 0:
        raise ValueError("No rows remain after NOT_INCLUDED sentinel filtering.")

    dep_num = _to_numeric_excluding_not_included(work_df[dependent_variable])
    valid_dep = dep_num.notna()
    work_df = work_df.loc[valid_dep].copy()
    dep_num = dep_num.loc[valid_dep]
    if len(work_df) < 3:
        raise ValueError("Need at least 3 valid rows for iterative_best_fit.")
    work_df[dependent_variable] = dep_num

    predictors, removed_nan_predictors = _filter_predictors_for_nan(
        work_df,
        predictors,
    )
    referenced_columns = set([str(c) for c in work_df.columns])
    removed_nan_columns = _unique_preserve_order(
        [
            col
            for pred in removed_nan_predictors
            for col in _predictor_referenced_columns(pred, referenced_columns)
            if col in work_df.columns and work_df[col].isna().any()
        ]
    )
    if len(predictors) == 0:
        raise ValueError(
            "No predictors available after dropping predictors with NaN values."
        )

    max_features_i = int(max_features) if int(max_features) > 0 else len(predictors)
    max_features_i = max(1, min(max_features_i, len(predictors)))
    if verbose and len(removed_nan_predictors) > 0:
        _log.hint(
            "[iterative_best_fit] Bypassed predictors due to NaN values: "
            + ", ".join(removed_nan_predictors)
        )

    model_df = _normalize_numeric_dataframe(
        work_df,
        method=normalize_method,
        exclude_columns=predictor_name_blacklist,
        sentinel=NOT_INCLUDED_SENTINEL,
    )
    # Keep target on original scale.
    model_df[dependent_variable] = work_df[dependent_variable]

    # Validate search strategy
    search_strat = str(search_strategy).strip().lower()
    if search_strat not in {"exhaustive", "beam"}:
        raise ValueError("search_strategy must be 'exhaustive' or 'beam'.")

    from math import comb as _comb_func
    total_exhaustive_estimate = sum(
        _comb_func(len(predictors), k) for k in range(1, max_features_i + 1)
    )

    if verbose:
        _log.status(f"Total combinations (exhaustive): ~{total_exhaustive_estimate}")
        _log.status(f"Search strategy: {search_strat}")
        if search_strat == "beam":
            _log.status(f"Beam width: {int(beam_width)}")
        _log.status(f"CV backend: {str(cv_backend).strip().lower()}")
        if cv_group_column is not None and cv_group_column in model_df.columns:
            n_groups = int(model_df[cv_group_column].dropna().astype(str).nunique())
            _log.status(f"CV mode: leave-one-{cv_group_column}-out ({n_groups} groups)")
        else:
            _log.status("CV mode: row-wise leave-one-out")

    start_time = time.time()
    best_score = np.inf
    best_formula = None
    best_subset = None
    best_actual = []
    best_predicted = []
    best_cv_params = None
    best_fold_mae = []
    valid_models = 0
    try:
        top_n_single = max(1, int(top_n_single_predictors))
    except Exception:
        top_n_single = 3
    model_score_by_subset = {}
    all_model_rows = []
    single_model_rows = []
    feature_add_stats = {}

    available_columns = set([str(c) for c in model_df.columns])
    dep_term = _quote_formula_name(dependent_variable) if dependent_variable in available_columns else str(dependent_variable)
    term_map = {str(p): _format_predictor_for_formula(str(p), available_columns) for p in predictors}

    def _formula_for_subset(subset_vals):
        return f"{dep_term} ~ " + " + ".join([term_map[str(p)] for p in subset_vals])

    requested_backend = str(cv_backend).strip().lower()
    if requested_backend not in {"ultra", "fast", "statsmodels"}:
        raise ValueError("cv_backend must be 'ultra', 'fast', or 'statsmodels'.")

    simple_backend_ready = False
    x_simple_all = None
    y_simple_all = None
    simple_col_idx = {}
    simple_group_values = None
    simple_group_indices = None
    if requested_backend in {"ultra", "fast"}:
        simple_candidate = [str(p) for p in predictors if str(p) in model_df.columns]
        if len(simple_candidate) == len(predictors):
            x_simple_df = model_df[simple_candidate].apply(pd.to_numeric, errors="coerce")
            y_simple = pd.to_numeric(model_df[dependent_variable], errors="coerce")
            if bool(x_simple_df.notna().all().all()) and bool(y_simple.notna().all()):
                x_simple = x_simple_df.to_numpy(dtype=float, copy=False)
                y_simple_v = y_simple.to_numpy(dtype=float, copy=False)
                if np.isfinite(x_simple).all() and np.isfinite(y_simple_v).all():
                    simple_backend_ready = True
                    x_simple_all = x_simple
                    y_simple_all = y_simple_v
                    simple_col_idx = {str(name): i for i, name in enumerate(simple_candidate)}
                    if cv_group_column is not None and cv_group_column in model_df.columns:
                        simple_group_values = model_df[cv_group_column]
                        g_ser = model_df[cv_group_column]
                        g_arr = g_ser.astype(str).to_numpy()
                        g_unique = g_ser[g_ser.notna()].astype(str).unique().tolist()
                        if len(g_unique) >= 2:
                            simple_group_indices = [np.flatnonzero(g_arr == gv) for gv in g_unique]
                            simple_group_indices = [idx for idx in simple_group_indices if len(idx) > 0]

    if requested_backend == "statsmodels":
        backend = "statsmodels"
    elif requested_backend == "ultra":
        if simple_backend_ready:
            backend = "ultra"
        elif dmatrices is not None:
            backend = "fast"
            if verbose:
                _log.hint("[iterative_best_fit] Ultra backend unavailable for current predictors; falling back to fast backend.")
        else:
            backend = "statsmodels"
            if verbose:
                _log.hint("[iterative_best_fit] Ultra backend unavailable and patsy missing; falling back to statsmodels backend.")
    else:  # requested fast
        if simple_backend_ready:
            backend = "ultra"
        elif dmatrices is not None:
            backend = "fast"
        else:
            backend = "statsmodels"
            if verbose:
                _log.hint("[iterative_best_fit] patsy not available, falling back to statsmodels backend.")

    if verbose and backend != requested_backend:
        _log.hint(f"[iterative_best_fit] Effective backend: {backend}")

    # Determine whether to use the vectorised batched path.
    use_batched = backend == "ultra" and simple_backend_ready
    if search_strat == "beam" and not use_batched:
        if verbose:
            _log.hint(
                "[iterative_best_fit] Beam search requires the ultra backend; "
                "falling back to exhaustive."
            )
        search_strat = "exhaustive"

    # ------------------------------------------------------------------
    # BATCHED PATH  (ultra backend — exhaustive or beam)
    # ------------------------------------------------------------------
    if use_batched:
        n_obs = x_simple_all.shape[0]
        n_pred = len(predictors)
        x1_batched = np.column_stack(
            [np.ones((n_obs, 1), dtype=float), x_simple_all],
        )
        prefix_list = [_safe_predictor_prefix(str(p)) for p in predictors]

        batch_group_idx = simple_group_indices
        if batch_group_idx is not None and len(batch_group_idx) < 2:
            batch_group_idx = None

        def _record_scores(subsets_idx, mae_arr):
            """Post-process a batch of scores into the bookkeeping dicts."""
            nonlocal valid_models, best_score, best_formula, best_subset
            for j, sub_idx in enumerate(subsets_idx):
                mae_val = float(mae_arr[j])
                pred_names = tuple(str(predictors[i]) for i in sub_idx)
                formula = _formula_for_subset(pred_names)
                if not np.isfinite(mae_val):
                    continue
                valid_models += 1
                model_score_by_subset[pred_names] = mae_val
                all_model_rows.append({
                    "subset": pred_names,
                    "subset_size": len(pred_names),
                    "score": mae_val,
                    "formula": formula,
                })
                if len(pred_names) == 1:
                    single_model_rows.append({
                        "predictor": pred_names[0],
                        "score": mae_val,
                        "formula": formula,
                    })
                if mae_val < best_score:
                    best_score = mae_val
                    best_formula = formula
                    best_subset = pred_names
                    if verbose:
                        _log.status(
                            f"Best so far: {best_formula} | "
                            f"LOO MAE: {best_score:.6g}"
                        )

        if search_strat == "beam":
            # ---------- BEAM SEARCH ----------
            beam_w = max(1, int(beam_width))
            models_scored = 0

            for k in range(1, max_features_i + 1):
                if k == 1:
                    candidates = [(i,) for i in range(n_pred)]
                    if not repeat_features:
                        seen_pfx = set()
                        filtered = []
                        for c in candidates:
                            pfx = prefix_list[c[0]]
                            if pfx not in seen_pfx:
                                seen_pfx.add(pfx)
                                filtered.append(c)
                        candidates = filtered
                else:
                    prev_scored = [
                        (s, sc)
                        for s, sc in model_score_by_subset.items()
                        if len(s) == k - 1 and np.isfinite(sc)
                    ]
                    prev_scored.sort(key=lambda x: x[1])
                    prev_beam_names = [s for s, _ in prev_scored[:beam_w]]
                    # Convert name-tuples back to index-tuples
                    name_to_idx = {str(predictors[i]): i for i in range(n_pred)}
                    prev_beam_idx = [
                        tuple(name_to_idx[n] for n in names)
                        for names in prev_beam_names
                    ]
                    candidates = _beam_expand(
                        prev_beam_idx, n_pred, repeat_features, prefix_list,
                    )

                if len(candidates) == 0:
                    break

                idx_arr = np.array(
                    [[0] + [ci + 1 for ci in sub] for sub in candidates],
                    dtype=int,
                )
                if verbose:
                    _log.status(
                        f"Beam level {k}: scoring {len(candidates)} candidates"
                    )

                mae_arr = _batch_score(
                    x1_batched, y_simple_all, idx_arr,
                    batch_group_idx, int(batch_chunk_size),
                )
                _record_scores(candidates, mae_arr)
                models_scored += len(candidates)

            _total_models_scored = models_scored
            if verbose:
                _log.status(
                    f"Beam search complete: {models_scored} models scored "
                    f"({valid_models} valid)"
                )

        else:
            # ---------- EXHAUSTIVE BATCHED ----------
            models_done = 0
            for k in range(1, max_features_i + 1):
                subsets_k = [
                    combo
                    for combo in itertools.combinations(range(n_pred), k)
                    if repeat_features
                    or len(set(prefix_list[i] for i in combo)) == k
                ]
                if len(subsets_k) == 0:
                    continue

                idx_arr = np.array(
                    [[0] + [ci + 1 for ci in sub] for sub in subsets_k],
                    dtype=int,
                )
                if verbose:
                    _log.status(
                        f"Level {k}: scoring {len(subsets_k)} "
                        f"{k}-feature models (batched)"
                    )

                mae_arr = _batch_score(
                    x1_batched, y_simple_all, idx_arr,
                    batch_group_idx, int(batch_chunk_size),
                )
                _record_scores(subsets_k, mae_arr)
                models_done += len(subsets_k)

            _total_models_scored = models_done
            if verbose:
                _log.status(
                    f"Batched search complete: {models_done} models scored "
                    f"({valid_models} valid)"
                )

        # Build feature_add_stats from all recorded scores.
        for subset_key, score_val in model_score_by_subset.items():
            if len(subset_key) <= 1:
                continue
            for added_feature in subset_key:
                parent_subset = tuple(s for s in subset_key if s != added_feature)
                parent_score = model_score_by_subset.get(parent_subset, None)
                if parent_score is None or not np.isfinite(parent_score):
                    continue
                delta = float(parent_score - score_val)
                pct_delta = np.nan
                if float(parent_score) != 0:
                    pct_delta = float((delta / abs(float(parent_score))) * 100.0)
                stats = feature_add_stats.setdefault(
                    str(added_feature),
                    {
                        "n_added": 0, "improved_count": 0,
                        "reduced_count": 0, "unchanged_count": 0,
                        "delta": [], "pct_delta": [],
                    },
                )
                stats["n_added"] += 1
                stats["delta"].append(delta)
                if np.isfinite(pct_delta):
                    stats["pct_delta"].append(pct_delta)
                if delta > 0:
                    stats["improved_count"] += 1
                elif delta < 0:
                    stats["reduced_count"] += 1
                else:
                    stats["unchanged_count"] += 1

        # Collect predictions for the winning model only (single CV run).
        if best_subset is not None:
            best_col_idx = [simple_col_idx[str(c)] for c in best_subset]
            x_sub = x_simple_all[:, best_col_idx]
            _, best_actual, best_predicted, best_cv_params, best_fold_mae = (
                _leave_one_out_mae_matrix_fast(
                    x_sub,
                    y_simple_all,
                    predictor_names=[str(c) for c in best_subset],
                    group_values=simple_group_values,
                    group_indices=simple_group_indices,
                    collect_predictions=True,
                )
            )

    # ------------------------------------------------------------------
    # SEQUENTIAL PATH  (fast / statsmodels fallback)
    # ------------------------------------------------------------------
    else:
        combinations = _iter_feature_combinations(
            predictors,
            max_features=max_features_i,
            repeat_features=bool(repeat_features),
        )
        if len(combinations) == 0:
            raise ValueError("No predictor combinations to test.")

        from PyFLASH.utils import ProgressTracker
        _tracker = ProgressTracker(
            "iterative_best_fit", len(combinations), unit="model",
            enabled=verbose,
        )

        for i, subset in enumerate(combinations, start=1):
            _tracker.start_item(" + ".join(str(s) for s in subset))
            if backend == "ultra":
                idx = [simple_col_idx[str(c)] for c in subset]
                x_sub = x_simple_all[:, idx]
                mae, actual, predicted, params, fold_mae = (
                    _leave_one_out_mae_matrix_fast(
                        x_sub,
                        y_simple_all,
                        predictor_names=[str(c) for c in subset],
                        group_values=simple_group_values,
                        group_indices=simple_group_indices,
                        collect_predictions=False,
                    )
                )
            elif backend == "fast":
                formula = _formula_for_subset(subset)
                mae, actual, predicted, params, fold_mae = (
                    _leave_one_out_mae_fast(
                        model_df,
                        formula,
                        dependent_variable=dependent_variable,
                        group_column=cv_group_column,
                        collect_predictions=False,
                    )
                )
            else:
                formula = _formula_for_subset(subset)
                mae, actual, predicted, params, fold_mae = _leave_one_out_mae(
                    model_df,
                    formula,
                    dependent_variable=dependent_variable,
                    group_column=cv_group_column,
                    collect_predictions=False,
                )
            if np.isfinite(mae):
                valid_models += 1
                subset_key = _subset_key(subset)
                score_val = float(mae)
                formula = _formula_for_subset(subset)
                model_score_by_subset[subset_key] = score_val
                all_model_rows.append({
                    "subset": subset_key,
                    "subset_size": int(len(subset_key)),
                    "score": score_val,
                    "formula": formula,
                })
                if len(subset_key) == 1:
                    single_model_rows.append({
                        "predictor": subset_key[0],
                        "score": score_val,
                        "formula": formula,
                    })
                elif len(subset_key) > 1:
                    for added_feature in subset_key:
                        parent_subset = tuple(
                            [s for s in subset_key if s != added_feature]
                        )
                        parent_score = model_score_by_subset.get(
                            parent_subset, None,
                        )
                        if parent_score is None or (
                            not np.isfinite(parent_score)
                        ):
                            continue
                        delta = float(parent_score - score_val)
                        pct_delta = np.nan
                        if float(parent_score) != 0:
                            pct_delta = float(
                                (delta / abs(float(parent_score))) * 100.0
                            )
                        stats = feature_add_stats.setdefault(
                            str(added_feature),
                            {
                                "n_added": 0,
                                "improved_count": 0,
                                "reduced_count": 0,
                                "unchanged_count": 0,
                                "delta": [],
                                "pct_delta": [],
                            },
                        )
                        stats["n_added"] += 1
                        stats["delta"].append(delta)
                        if np.isfinite(pct_delta):
                            stats["pct_delta"].append(pct_delta)
                        if delta > 0:
                            stats["improved_count"] += 1
                        elif delta < 0:
                            stats["reduced_count"] += 1
                        else:
                            stats["unchanged_count"] += 1
                if mae < best_score:
                    if backend == "ultra":
                        idx = [simple_col_idx[str(c)] for c in subset]
                        x_sub = x_simple_all[:, idx]
                        mae_full, actual, predicted, params, fold_mae = (
                            _leave_one_out_mae_matrix_fast(
                                x_sub,
                                y_simple_all,
                                predictor_names=[str(c) for c in subset],
                                group_values=simple_group_values,
                                group_indices=simple_group_indices,
                                collect_predictions=True,
                            )
                        )
                    elif backend == "fast":
                        mae_full, actual, predicted, params, fold_mae = (
                            _leave_one_out_mae_fast(
                                model_df,
                                formula,
                                dependent_variable=dependent_variable,
                                group_column=cv_group_column,
                                collect_predictions=True,
                            )
                        )
                    else:
                        mae_full, actual, predicted, params, fold_mae = (
                            _leave_one_out_mae(
                                model_df,
                                formula,
                                dependent_variable=dependent_variable,
                                group_column=cv_group_column,
                                collect_predictions=True,
                            )
                        )
                    if not np.isfinite(mae_full):
                        continue
                    best_score = float(mae_full)
                    best_formula = formula
                    best_subset = subset
                    best_actual = actual
                    best_predicted = predicted
                    best_cv_params = params
                    best_fold_mae = fold_mae
                    if verbose:
                        _log.status(
                            f"Best so far: {best_formula} | "
                            f"LOO MAE: {best_score:.6g}"
                        )

            _tracker.finish_item(
                detail=(
                    f"Best: {best_formula or 'none'} | MAE: {best_score:.6g}"
                    if best_formula
                    else None
                ),
            )
        _tracker.close()
        _total_models_scored = len(combinations)

    if best_formula is None or best_subset is None or len(best_actual) == 0:
        raise ValueError(
            "No valid model could be fitted. "
            "Check predictor expressions and missing data."
        )

    best_fit = sm.OLS.from_formula(best_formula, data=model_df).fit()
    all_models_df = pd.DataFrame(all_model_rows)
    if len(all_models_df) > 0:
        all_models_df = all_models_df.copy()
        all_models_df["predictors"] = all_models_df["subset"].apply(
            lambda vals: " + ".join([str(v) for v in vals])
        )
        all_models_df = all_models_df.sort_values(
            by=["subset_size", "score", "predictors"],
            ascending=[True, True, True],
        ).reset_index(drop=True)
    if len(single_model_rows) > 0:
        single_model_df = pd.DataFrame(single_model_rows).sort_values(
            by=["score", "predictor"], ascending=[True, True]
        ).reset_index(drop=True)
    else:
        single_model_df = pd.DataFrame(columns=["predictor", "score", "formula"])
    top_single_df = single_model_df.head(top_n_single).copy()
    feature_change_df = _feature_change_summary_df(feature_add_stats)

    if verbose:
        _log.status(f"Best Model: {best_formula}")
        _log.status(f"Best Score (LOO MAE): {best_score:.6g}")
        _log.status(f"Params:\n{best_fit.params}")
        _log.status(f"R^2: {best_fit.rsquared}")
        _log.status(f"Adj R^2: {best_fit.rsquared_adj}")
        _log.status(f"F-statistic: {best_fit.fvalue}")
        _log.status(f"F-statistic p-value: {best_fit.f_pvalue}")
        _log.status(f"Model Summary:\n{best_fit.summary()}")
        _log.status(f"Valid models tested: {valid_models}/{_total_models_scored}")
        if len(top_single_df) > 0:
            _log.status(f"Top {top_n_single} single predictors:")
            for _, row in top_single_df.iterrows():
                _log.status(f"  - {row['predictor']}: {float(row['score']):.6g}")
        if len(feature_change_df) > 0:
            top_feature = feature_change_df.iloc[0]
            _log.hint(
                "[iterative_best_fit] Feature most often improving models: "
                f"{top_feature['feature']} ({int(top_feature['improved_count'])} improvements)"
            )
        if len(removed_sentinel_columns) > 0:
            _log.hint(
                "[iterative_best_fit] Sentinel rows were removed based on columns: "
                + ", ".join(removed_sentinel_columns)
            )
        if len(removed_nan_columns) > 0:
            _log.hint(
                "[iterative_best_fit] Columns removed due to NaN: "
                + ", ".join(removed_nan_columns)
            )
        else:
            _log.hint("[iterative_best_fit] Columns removed due to NaN: none")

    auto_save_root = getattr(batch, "fig_path", None)
    if auto_save_root is not None:
        auto_save_root = str(auto_save_root)
    _aliases = getattr(batch, 'aliases', None)
    from PyFLASH.utils import build_subfolder
    subfolder, suffix = build_subfolder('Modelling', specificity=specificity, aliases=_aliases)
    base_save_name = f"Best Iterative Model for {dependent_variable}{suffix}"
    if save and auto_save_root is None and verbose:
        _log.warn("[iterative_best_fit] batch.fig_path not found. Skipping save.")

    if plot:
        scatter_df = pd.DataFrame({
            "Predicted": best_predicted,
            "Actual": best_actual,
        })
        if hue_column in work_df.columns and len(work_df) == len(scatter_df):
            scatter_df[hue_column] = work_df[hue_column].to_numpy()

        fig, ax = plt.subplots(1, 1, figsize=(13.5, 6.5))
        fig.subplots_adjust(right=0.60)
        if hue_column in scatter_df.columns:
            sns.scatterplot(
                data=scatter_df,
                x="Predicted",
                y="Actual",
                hue=hue_column,
                ax=ax,
                s=pyflash_point_size(backend="area"),
                palette=palette,
            )
        else:
            sns.scatterplot(
                data=scatter_df,
                x="Predicted",
                y="Actual",
                ax=ax,
                s=pyflash_point_size(backend="area"),
            )
        lo = float(np.nanmin(np.r_[scatter_df["Predicted"], scatter_df["Actual"]]))
        hi = float(np.nanmax(np.r_[scatter_df["Predicted"], scatter_df["Actual"]]))
        if np.isfinite(lo) and np.isfinite(hi):
            ax.plot([lo, hi], [lo, hi], linestyle="--", color="black", alpha=0.6)
        ax.set_xlabel("Predicted Values")
        ax.set_ylabel("Actual Values")
        model_annotation = _format_model_annotation(best_fit)
        fig.text(
            0.63,
            0.96,
            model_annotation,
            ha="left",
            va="top",
            fontsize=8,
            family="monospace",
            color="black",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.92},
        )
        fig.set_dpi(dpi)
        if save and auto_save_root is not None:
            save_fig(
                fig,
                auto_save_root,
                base_save_name,
                subfolder=subfolder,
                verbose=False,
            )
        plt.show()

        # Plot single-predictor relationships for interpretable terms.
        work_cols_set = set([str(c) for c in work_df.columns])
        for predictor in best_subset:
            refs = _predictor_referenced_columns(str(predictor), work_cols_set)
            if len(refs) == 0:
                base_predictor = _primary_predictor(predictor)
                if base_predictor in work_cols_set:
                    refs = [base_predictor]
            if len(refs) == 0:
                continue
            x_predictor = next(
                (r for r in refs if r not in {hue_column, dependent_variable}),
                refs[0],
            )
            if x_predictor == hue_column:
                continue
            if x_predictor not in work_df.columns:
                continue
            reg_df = work_df.copy()
            reg_df[x_predictor] = _to_numeric_excluding_not_included(reg_df[x_predictor])
            reg_df[dependent_variable] = _to_numeric_excluding_not_included(reg_df[dependent_variable])
            reg_df = reg_df.dropna(subset=[x_predictor, dependent_variable])
            if len(reg_df) < 2:
                continue
            if hue_column in reg_df.columns:
                lm = sns.lmplot(
                    y=dependent_variable,
                    x=x_predictor,
                    data=reg_df,
                    hue=hue_column,
                    ci=None,
                    palette=palette,
                )
            else:
                lm = sns.lmplot(
                    y=dependent_variable,
                    x=x_predictor,
                    data=reg_df,
                    ci=None,
                )
            lm.fig.set_dpi(dpi)
            if save and auto_save_root is not None:
                save_fig(
                    lm.fig,
                    auto_save_root,
                    f"{base_save_name} {x_predictor}",
                    subfolder=subfolder,
                    verbose=False,
                )
            plt.show()

        if plot_insights and len(feature_change_df) > 0:
            ordered_features = feature_change_df["feature"].tolist()
            n_features = len(ordered_features)
            cfg = _insight_plot_config(n_features)
            xpos = np.arange(n_features)

            fig_counts, ax_counts = plt.subplots(1, 1, figsize=cfg["figsize"])
            width = float(cfg["bar_width"])
            improved_vals = feature_change_df["improved_count"].to_numpy(dtype=float)
            reduced_vals = feature_change_df["reduced_count"].to_numpy(dtype=float)
            if cfg["orientation"] == "horizontal":
                ax_counts.barh(
                    xpos - (width / 2.0),
                    improved_vals,
                    height=width,
                    color="#3B8B3B",
                    label="Improved",
                )
                ax_counts.barh(
                    xpos + (width / 2.0),
                    reduced_vals,
                    height=width,
                    color="#B04A4A",
                    label="Reduced",
                )
                ax_counts.set_yticks(xpos)
                ax_counts.set_yticklabels(ordered_features)
                ax_counts.invert_yaxis()
                ax_counts.set_xlabel("Count")
                ax_counts.set_ylabel("Feature Added")
            else:
                ax_counts.bar(
                    xpos - (width / 2.0),
                    improved_vals,
                    width=width,
                    color="#3B8B3B",
                    label="Improved",
                )
                ax_counts.bar(
                    xpos + (width / 2.0),
                    reduced_vals,
                    width=width,
                    color="#B04A4A",
                    label="Reduced",
                )
                ax_counts.set_xticks(xpos)
                ax_counts.set_xticklabels(
                    ordered_features, rotation=cfg["rotation"], ha="right"
                )
                ax_counts.set_ylabel("Count")
                ax_counts.set_xlabel("Feature Added")
            ax_counts.tick_params(axis="both", labelsize=cfg["tick_size"])
            ax_counts.set_title("Feature Addition Impact Counts")
            ax_counts.legend(frameon=False)
            fig_counts.set_dpi(dpi)
            plt.tight_layout()
            if save and auto_save_root is not None:
                save_fig(
                    fig_counts,
                    auto_save_root,
                    f"{base_save_name} Feature Addition Count Impact",
                    subfolder=subfolder,
                    verbose=False,
                )
            plt.show()

            fig_delta, ax_delta = plt.subplots(1, 1, figsize=cfg["figsize"])
            mean_deltas = feature_change_df["mean_delta"].to_numpy(dtype=float)
            colors = np.where(mean_deltas >= 0, "#3B8B3B", "#B04A4A")
            if cfg["orientation"] == "horizontal":
                ax_delta.barh(
                    xpos,
                    mean_deltas,
                    height=0.62,
                    color=colors,
                )
                ax_delta.axvline(0.0, color="black", linestyle="--", linewidth=1.0, alpha=0.7)
                ax_delta.set_yticks(xpos)
                ax_delta.set_yticklabels(ordered_features)
                ax_delta.invert_yaxis()
                ax_delta.set_xlabel("Mean Δ Score (parent - child)")
                ax_delta.set_ylabel("Feature Added")
            else:
                ax_delta.bar(
                    xpos,
                    mean_deltas,
                    width=0.62,
                    color=colors,
                )
                ax_delta.axhline(0.0, color="black", linestyle="--", linewidth=1.0, alpha=0.7)
                ax_delta.set_xticks(xpos)
                ax_delta.set_xticklabels(
                    ordered_features, rotation=cfg["rotation"], ha="right"
                )
                ax_delta.set_ylabel("Mean Δ Score (parent - child)")
                ax_delta.set_xlabel("Feature Added")
            ax_delta.tick_params(axis="both", labelsize=cfg["tick_size"])
            ax_delta.set_title("Average Score Change When Feature Added")
            fig_delta.set_dpi(dpi)
            plt.tight_layout()
            if save and auto_save_root is not None:
                save_fig(
                    fig_delta,
                    auto_save_root,
                    f"{base_save_name} Feature Addition Mean Delta",
                    subfolder=subfolder,
                    verbose=False,
                )
            plt.show()

    result = {
        "best_model": best_formula,
        "best_subset": tuple(best_subset),
        "best_score": float(best_score),
        "best_params": best_fit.params,
        "best_fit": best_fit,
        "cv_params": best_cv_params,
        "cv_actual": best_actual,
        "cv_predicted": best_predicted,
        "cv_fold_mae": best_fold_mae,
        "cv_group_column": cv_group_column,
        "cv_backend": backend,
        "cv_backend_requested": requested_backend,
        "combinations_tested": _total_models_scored,
        "valid_models_tested": valid_models,
        "search_strategy": search_strat if use_batched else "exhaustive",
        "specificity": specificity,
        "exclude": exclude_filter,
        "removed_rows_sentinel": int(removed_sentinel_rows),
        "removed_predictors_nan": removed_nan_predictors,
        "removed_columns_sentinel": removed_sentinel_columns,
        "removed_columns_nan": removed_nan_columns,
        "top_single_predictors": top_single_df.to_dict(orient="records"),
        "single_model_scores": single_model_df,
        "feature_addition_summary": feature_change_df,
        "all_model_scores": all_models_df,
    }
    if return_details:
        return result
    return best_formula, best_fit.params


# ---------------------------------------------------------------------------
# Classification model sweep
# ---------------------------------------------------------------------------

def _classifier_one_hot_encoder():
    """Return a dense OneHotEncoder across old and new scikit-learn versions."""
    from sklearn.preprocessing import OneHotEncoder

    try:
        return OneHotEncoder(
            handle_unknown="infrequent_if_exist",
            min_frequency=2,
            sparse_output=False,
        )
    except TypeError:  # scikit-learn < 1.2
        return OneHotEncoder(
            handle_unknown="ignore",
            sparse=False,
        )


class _PyFLASHOrdinalLogistic:
    """Pickle-safe sklearn-compatible wrapper around mord.LogisticIT."""

    def __init__(self, alpha: float = 1.0, max_iter: int = 10000):
        self.alpha = alpha
        self.max_iter = max_iter

    def get_params(self, deep: bool = True):
        return {"alpha": self.alpha, "max_iter": self.max_iter}

    def set_params(self, **params):
        for key, value in params.items():
            setattr(self, key, value)
        return self

    def fit(self, X, y):
        from mord import LogisticIT

        self.classes_ = np.array(sorted(np.unique(y)))
        self.model_ = LogisticIT(alpha=self.alpha, max_iter=self.max_iter)
        self.model_.fit(X, y)
        return self

    def predict(self, X):
        return self.model_.predict(X).astype(int)

    def predict_proba(self, X):
        raw = np.asarray(self.model_.predict_proba(X), dtype=float)
        if raw.shape[1] == len(self.classes_):
            return raw
        aligned = np.zeros((raw.shape[0], len(self.classes_)), dtype=float)
        for col_idx in range(min(raw.shape[1], len(self.classes_))):
            aligned[:, col_idx] = raw[:, col_idx]
        row_sums = aligned.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        return aligned / row_sums


def _classification_model_configs(
    preset: str = "ultra_compact",
    model_families: Iterable[str] | None = None,
    random_state: int = 20260708,
) -> list[dict[str, Any]]:
    """
    Build a compact library of classifier configurations for model sweeps.

    Presets:
    - ultra_compact: one representative per family, intended for large sweeps.
    - compact: a small grid.
    - full: a broader discovery grid.
    """
    from sklearn.discriminant_analysis import (
        LinearDiscriminantAnalysis,
        QuadraticDiscriminantAnalysis,
    )
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import SVC

    preset_key = str(preset).strip().lower()
    if preset_key not in {"ultra_compact", "compact", "full"}:
        raise ValueError("model_preset must be 'ultra_compact', 'compact', or 'full'.")
    ultra = preset_key == "ultra_compact"
    compact = preset_key in {"ultra_compact", "compact"}

    wanted = None
    if model_families is not None:
        wanted = {str(f).strip().lower() for f in model_families if str(f).strip()}

    def _include(family: str) -> bool:
        return wanted is None or str(family).strip().lower() in wanted

    configs: list[dict[str, Any]] = []

    if _include("ridge_multinomial_logistic"):
        ridge_cs = [1.0] if ultra else ([0.1, 1.0] if compact else [0.03, 0.1, 0.3, 1.0, 3.0])
        for c_val in ridge_cs:
            configs.append({
                "family": "ridge_multinomial_logistic",
                "name": f"ridge_C={c_val:g}",
                "estimator": LogisticRegression(
                    penalty="l2",
                    solver="lbfgs",
                    C=c_val,
                    max_iter=50000,
                    random_state=random_state,
                ),
                "params": {"C": c_val},
            })

    if _include("elastic_net_multinomial_logistic"):
        elastic_params = (
            [(0.1, 0.5)]
            if ultra
            else [(0.1, 0.5), (1.0, 0.5)]
            if compact
            else [(c_val, ratio) for c_val in [0.1, 0.3, 1.0] for ratio in [0.1, 0.5, 0.9]]
        )
        for c_val, ratio in elastic_params:
            configs.append({
                "family": "elastic_net_multinomial_logistic",
                "name": f"elastic_C={c_val:g}_l1={ratio:g}",
                "estimator": LogisticRegression(
                    penalty="elasticnet",
                    solver="saga",
                    C=c_val,
                    l1_ratio=ratio,
                    max_iter=50000,
                    random_state=random_state,
                ),
                "params": {"C": c_val, "l1_ratio": ratio},
            })

    if _include("ordinal_logistic"):
        try:
            from mord import LogisticIT  # noqa: F401
        except Exception:
            LogisticIT = None

        if LogisticIT is not None:
            ordinal_alphas = [1.0] if ultra else ([1.0, 10.0] if compact else [0.1, 1.0, 10.0, 100.0])
            for alpha in ordinal_alphas:
                configs.append({
                    "family": "ordinal_logistic",
                    "name": f"ordinal_alpha={alpha:g}",
                    "estimator": _PyFLASHOrdinalLogistic(alpha=alpha, max_iter=50000),
                    "params": {"alpha": alpha},
                })

    if _include("shrinkage_lda"):
        lda_shrinkages = ["auto"] if compact else ["auto", 0.1, 0.5, 0.9]
        for shrinkage in lda_shrinkages:
            configs.append({
                "family": "shrinkage_lda",
                "name": f"lda_shrinkage={shrinkage}",
                "estimator": LinearDiscriminantAnalysis(solver="lsqr", shrinkage=shrinkage),
                "params": {"shrinkage": shrinkage},
            })

    if _include("regularised_qda"):
        qda_regs = [0.7] if ultra else ([0.5, 0.9] if compact else [0.1, 0.3, 0.5, 0.7, 0.9])
        for reg in qda_regs:
            configs.append({
                "family": "regularised_qda",
                "name": f"qda_reg={reg:g}",
                "estimator": QuadraticDiscriminantAnalysis(reg_param=reg),
                "params": {"reg_param": reg},
            })

    if _include("polynomial_svm"):
        svm_params = (
            [(1.0, 1.0)]
            if compact
            else [(c_val, coef0) for c_val in [0.1, 1.0, 10.0] for coef0 in [0.0, 1.0]]
        )
        for c_val, coef0 in svm_params:
            configs.append({
                "family": "polynomial_svm",
                "name": f"poly_svm_C={c_val:g}_coef0={coef0:g}",
                "estimator": SVC(
                    kernel="poly",
                    degree=2,
                    C=c_val,
                    coef0=coef0,
                    probability=not ultra,
                    random_state=random_state,
                ),
                "params": {"C": c_val, "degree": 2, "coef0": coef0},
            })

    if _include("shallow_random_forest"):
        rf_params = (
            [(2, 2, "sqrt", 50)]
            if ultra
            else [(2, 2, "sqrt", 200)]
            if compact
            else [(depth, leaf, max_feat, 200) for depth in [1, 2] for leaf in [2, 4] for max_feat in ["sqrt", 0.5]]
        )
        for depth, leaf, max_feat, n_estimators in rf_params:
            configs.append({
                "family": "shallow_random_forest",
                "name": f"rf_depth={depth}_leaf={leaf}_mf={max_feat}",
                "estimator": RandomForestClassifier(
                    n_estimators=n_estimators,
                    max_depth=depth,
                    min_samples_leaf=leaf,
                    max_features=max_feat,
                    random_state=random_state,
                    n_jobs=1,
                ),
                "params": {
                    "max_depth": depth,
                    "min_samples_leaf": leaf,
                    "max_features": max_feat,
                    "n_estimators": n_estimators,
                },
            })

    if _include("shallow_gradient_boosting"):
        gb_params = (
            [(10, 0.1, 1, 2)]
            if ultra
            else [(25, 0.1, 1, 2)]
            if compact
            else [(n_est, lr, depth, 2) for n_est in [10, 25] for lr in [0.03, 0.1] for depth in [1, 2]]
        )
        for n_estimators, lr, depth, leaf in gb_params:
            configs.append({
                "family": "shallow_gradient_boosting",
                "name": f"gb_n={n_estimators}_lr={lr:g}_depth={depth}",
                "estimator": GradientBoostingClassifier(
                    n_estimators=n_estimators,
                    learning_rate=lr,
                    max_depth=depth,
                    min_samples_leaf=leaf,
                    random_state=random_state,
                ),
                "params": {
                    "n_estimators": n_estimators,
                    "learning_rate": lr,
                    "max_depth": depth,
                    "min_samples_leaf": leaf,
                },
            })

    if len(configs) == 0:
        raise ValueError(
            "No classifier configurations selected. "
            "Check model_families names."
        )
    return configs


def _prepare_classifier_feature_frame(
    df: pd.DataFrame,
    features: Iterable[str],
    sentinel: str = NOT_INCLUDED_SENTINEL,
) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """
    Convert numeric-looking columns once and keep categorical columns as objects.

    Missing values are not filled here; imputation happens inside each
    cross-validation fold.
    """
    out = pd.DataFrame(index=df.index)
    type_map: dict[str, str] = {}
    removed: list[str] = []

    for feature in features:
        col = str(feature)
        if col not in df.columns:
            removed.append(col)
            continue
        raw = pd.Series(df[col], index=df.index)
        sentinel_mask = _sentinel_like_mask(raw, sentinel=sentinel)
        masked = raw.mask(sentinel_mask, np.nan)
        numeric = _to_numeric_excluding_not_included(raw, sentinel=sentinel)

        nonmissing = masked.notna()
        nonmissing_count = int(nonmissing.sum())
        parsed_count = int(numeric.loc[nonmissing].notna().sum()) if nonmissing_count else 0
        if nonmissing_count == 0:
            removed.append(col)
            continue

        if parsed_count == nonmissing_count:
            out[col] = numeric
            type_map[col] = "numeric"
        else:
            out[col] = masked.astype(object)
            type_map[col] = "categorical"

    return out, type_map, _unique_preserve_order(removed)


def _build_classifier_preprocessor(
    type_map: dict[str, str],
    features: Iterable[str],
    normalize_method: str = "zscore",
):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import MinMaxScaler, StandardScaler

    feature_list = [str(f) for f in features]
    numeric = [f for f in feature_list if type_map.get(f) == "numeric"]
    categorical = [f for f in feature_list if type_map.get(f) == "categorical"]

    transformers = []
    if numeric:
        num_steps = [("imputer", SimpleImputer(strategy="median"))]
        norm = str(normalize_method).strip().lower()
        if norm == "minmax":
            num_steps.append(("scaler", MinMaxScaler()))
        elif norm != "none":
            num_steps.append(("scaler", StandardScaler()))
        transformers.append(("num", Pipeline(num_steps), numeric))

    if categorical:
        transformers.append((
            "cat",
            Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", _classifier_one_hot_encoder()),
            ]),
            categorical,
        ))

    if not transformers:
        raise ValueError("No usable numeric or categorical predictors in subset.")
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.0)


def _classifier_cv_splitter(
    y: np.ndarray,
    cv: str = "stratified5",
    random_state: int = 20260708,
):
    from sklearn.model_selection import LeaveOneOut, StratifiedKFold

    cv_key = str(cv).strip().lower()
    if cv_key in {"loo", "leave_one_out", "leave-one-out"}:
        return LeaveOneOut()

    n_splits = 5
    m = re.match(r"stratified(\d+)", cv_key)
    if m:
        n_splits = int(m.group(1))
    elif cv_key not in {"stratified", "stratified5"}:
        raise ValueError("cv must be 'stratified5', 'stratifiedN', or 'loo'.")

    _, counts = np.unique(y, return_counts=True)
    min_count = int(np.min(counts)) if len(counts) else 0
    if min_count < 2:
        raise ValueError("Stratified CV needs at least 2 samples in every class.")
    n_splits = max(2, min(int(n_splits), min_count))
    return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)


def _align_classifier_proba(
    estimator,
    x_test: pd.DataFrame,
    class_codes: np.ndarray,
    pred: np.ndarray | None = None,
) -> np.ndarray:
    if hasattr(estimator, "predict_proba"):
        proba = np.asarray(estimator.predict_proba(x_test), dtype=float)
        estimator_classes = getattr(estimator, "classes_", None)
        if estimator_classes is None and hasattr(estimator, "named_steps"):
            estimator_classes = getattr(estimator.named_steps.get("clf"), "classes_", None)
    else:
        if pred is None:
            pred = np.asarray(estimator.predict(x_test), dtype=int)
        else:
            pred = np.asarray(pred, dtype=int)
        proba = np.zeros((len(pred), len(class_codes)), dtype=float)
        contiguous_codes = np.arange(len(class_codes), dtype=int)
        if np.array_equal(class_codes, contiguous_codes):
            valid = (pred >= 0) & (pred < len(class_codes))
            if np.any(valid):
                rows = np.flatnonzero(valid)
                proba[rows, pred[valid].astype(int)] = 1.0
        else:
            for row_idx, pred_code in enumerate(pred):
                matches = np.flatnonzero(class_codes == int(pred_code))
                if len(matches):
                    proba[row_idx, int(matches[0])] = 1.0
        return proba

    if proba.ndim != 2:
        raise ValueError("predict_proba returned a non-2D array.")

    aligned = np.zeros((len(x_test), len(class_codes)), dtype=float)
    if estimator_classes is None:
        if proba.shape[1] == len(class_codes):
            aligned = proba
        else:
            aligned[:, : min(proba.shape[1], len(class_codes))] = proba[:, : min(proba.shape[1], len(class_codes))]
    else:
        for col_idx, cls in enumerate(estimator_classes):
            try:
                cls_i = int(cls)
            except Exception:
                continue
            matches = np.flatnonzero(class_codes == cls_i)
            if len(matches) and col_idx < proba.shape[1]:
                aligned[:, int(matches[0])] = proba[:, col_idx]

    row_sums = aligned.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return aligned / row_sums


def _classifier_metrics_from_predictions(
    y: np.ndarray,
    pred: np.ndarray,
    proba: np.ndarray,
    class_codes: np.ndarray,
    fold_id: np.ndarray | None = None,
    collect_predictions: bool = False,
) -> dict[str, Any] | None:
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        f1_score,
        log_loss,
        roc_auc_score,
    )

    if int((pred >= 0).sum()) != len(y) or not np.isfinite(proba).all():
        return None

    row: dict[str, Any] = {
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
    }
    try:
        row["macro_ovr_auc"] = float(
            roc_auc_score(y, proba, labels=class_codes, multi_class="ovr", average="macro")
        )
    except Exception:
        row["macro_ovr_auc"] = np.nan
    try:
        row["log_loss"] = float(log_loss(y, proba, labels=class_codes))
    except Exception:
        row["log_loss"] = np.nan

    if collect_predictions:
        row["prediction_code"] = pred
        row["probability"] = proba
        if fold_id is not None:
            row["fold"] = fold_id
    return row


def _build_classifier_cv_matrices(
    feature_frame: pd.DataFrame,
    type_map: dict[str, str],
    features: Iterable[str],
    cv_splits: list[tuple[np.ndarray, np.ndarray]],
    normalize_method: str = "zscore",
    y: np.ndarray | None = None,
    fold_y_train: list[np.ndarray] | None = None,
    fold_class_valid: list[bool] | None = None,
) -> list[dict[str, Any]] | None:
    """Fit fold-local preprocessing once for a subset and reuse it across classifiers."""
    from sklearn.base import clone

    feature_list = [str(f) for f in features]
    x_all = feature_frame[feature_list]
    try:
        preprocessor = _build_classifier_preprocessor(type_map, feature_list, normalize_method)
    except Exception:
        return None

    folds: list[dict[str, Any]] = []
    for fold_pos, (train_idx, test_idx) in enumerate(cv_splits):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fold_preprocessor = clone(preprocessor)
                x_train = fold_preprocessor.fit_transform(x_all.iloc[train_idx])
                x_test = fold_preprocessor.transform(x_all.iloc[test_idx])
        except Exception:
            return None
        fold = {
            "train_idx": train_idx,
            "test_idx": test_idx,
            "x_train": np.asarray(x_train, dtype=float),
            "x_test": np.asarray(x_test, dtype=float),
        }
        if fold_y_train is not None and fold_pos < len(fold_y_train):
            y_train = fold_y_train[fold_pos]
            fold["y_train"] = y_train
            if fold_class_valid is not None and fold_pos < len(fold_class_valid):
                fold["train_has_multiple_classes"] = bool(fold_class_valid[fold_pos])
            else:
                fold["train_has_multiple_classes"] = bool(len(np.unique(y_train)) >= 2)
        elif y is not None:
            y_train = y[train_idx]
            fold["y_train"] = y_train
            if fold_class_valid is not None and fold_pos < len(fold_class_valid):
                fold["train_has_multiple_classes"] = bool(fold_class_valid[fold_pos])
            else:
                fold["train_has_multiple_classes"] = bool(len(np.unique(y_train)) >= 2)
        folds.append(fold)
    return folds


def _score_classifier_subset_from_cv_matrices(
    cv_matrices: list[dict[str, Any]] | None,
    y: np.ndarray,
    config: dict[str, Any],
    class_codes: np.ndarray,
    collect_predictions: bool = False,
    fold_class_valid: list[bool] | None = None,
) -> dict[str, Any] | None:
    if not cv_matrices:
        return None
    from sklearn.base import clone

    pred = np.full(len(y), -1, dtype=int)
    proba = np.full((len(y), len(class_codes)), np.nan, dtype=float)
    fold_id = np.full(len(y), -1, dtype=int) if collect_predictions else None

    for fold_idx, fold in enumerate(cv_matrices, start=1):
        train_idx = fold["train_idx"]
        test_idx = fold["test_idx"]
        if fold_class_valid is not None and fold_idx - 1 < len(fold_class_valid):
            valid_fold = bool(fold_class_valid[fold_idx - 1])
        else:
            valid_fold = fold.get("train_has_multiple_classes", None)
            if valid_fold is None:
                valid_fold = len(np.unique(y[train_idx])) >= 2
        if not valid_fold:
            return None
        y_train = fold.get("y_train", y[train_idx])
        estimator = clone(config["estimator"])
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                estimator.fit(fold["x_train"], y_train)
                fold_pred = np.asarray(estimator.predict(fold["x_test"]), dtype=int)
                pred[test_idx] = fold_pred
                proba[test_idx] = _align_classifier_proba(
                    estimator,
                    fold["x_test"],
                    class_codes,
                    pred=fold_pred,
                )
                if fold_id is not None:
                    fold_id[test_idx] = int(fold_idx)
        except Exception:
            return None

    return _classifier_metrics_from_predictions(
        y,
        pred,
        proba,
        class_codes,
        fold_id=fold_id,
        collect_predictions=collect_predictions,
    )


def _score_prepared_subset_configs_worker(
    prepared,
    configs: list[dict[str, Any]],
    y: np.ndarray,
    class_codes: np.ndarray,
    fold_class_valid: list[bool] | None = None,
) -> list[dict[str, Any]]:
    """Process-safe worker: score all configs for one prepared subset."""
    subset_list, features_text, features_json, _numeric_col_idx, subset_cv_matrices = prepared
    if subset_cv_matrices is None:
        return []

    rows = []
    for config in configs:
        metrics = _score_classifier_subset_from_cv_matrices(
            subset_cv_matrices,
            y,
            config,
            class_codes,
            collect_predictions=False,
            fold_class_valid=fold_class_valid,
        )
        if metrics is None:
            continue
        rows.append({
            "family": config["family"],
            "model_config": config["name"],
            "params_json": config.get("_params_json") or json.dumps(config["params"], sort_keys=True),
            "subset_size": len(subset_list),
            "features": features_text,
            "features_json": features_json,
            "features_tuple": tuple(subset_list),
            **metrics,
        })
    return rows


def _score_classifier_subset(
    feature_frame: pd.DataFrame,
    type_map: dict[str, str],
    y: np.ndarray,
    features: Iterable[str],
    config: dict[str, Any],
    class_codes: np.ndarray,
    cv: str = "stratified5",
    normalize_method: str = "zscore",
    random_state: int = 20260708,
    collect_predictions: bool = False,
    cv_splits: list[tuple[np.ndarray, np.ndarray]] | None = None,
    fold_class_valid: list[bool] | None = None,
) -> dict[str, Any] | None:
    from sklearn.base import clone
    from sklearn.pipeline import Pipeline

    feature_list = [str(f) for f in features]
    x_all = feature_frame[feature_list]
    if cv_splits is None:
        splitter = _classifier_cv_splitter(y, cv=cv, random_state=random_state)
        splits = list(splitter.split(x_all, y))
    else:
        splits = cv_splits
    pred = np.full(len(y), -1, dtype=int)
    proba = np.full((len(y), len(class_codes)), np.nan, dtype=float)
    fold_id = np.full(len(y), -1, dtype=int) if collect_predictions else None

    for fold_idx, (train_idx, test_idx) in enumerate(splits, start=1):
        valid_fold = (
            bool(fold_class_valid[fold_idx - 1])
            if fold_class_valid is not None and fold_idx - 1 < len(fold_class_valid)
            else len(np.unique(y[train_idx])) >= 2
        )
        if not valid_fold:
            return None
        pipe = Pipeline([
            ("preprocess", _build_classifier_preprocessor(type_map, feature_list, normalize_method)),
            ("clf", clone(config["estimator"])),
        ])
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pipe.fit(x_all.iloc[train_idx], y[train_idx])
                fold_pred = np.asarray(pipe.predict(x_all.iloc[test_idx]), dtype=int)
                pred[test_idx] = fold_pred
                proba[test_idx] = _align_classifier_proba(
                    pipe,
                    x_all.iloc[test_idx],
                    class_codes,
                    pred=fold_pred,
                )
                if fold_id is not None:
                    fold_id[test_idx] = int(fold_idx)
        except Exception:
            return None

    return _classifier_metrics_from_predictions(
        y,
        pred,
        proba,
        class_codes,
        fold_id=fold_id,
        collect_predictions=collect_predictions,
    )


def _build_numeric_classifier_cv_cache(
    feature_frame: pd.DataFrame,
    type_map: dict[str, str],
    cv_splits: list[tuple[np.ndarray, np.ndarray]],
    normalize_method: str = "zscore",
    y: np.ndarray | None = None,
    fold_y_train: list[np.ndarray] | None = None,
    fold_class_valid: list[bool] | None = None,
) -> dict[str, Any] | None:
    """
    Precompute fold-wise numeric imputation and scaling for all numeric columns.

    For numeric-only subsets this is equivalent to a fold-local
    SimpleImputer(strategy='median') plus StandardScaler or MinMaxScaler,
    but avoids rebuilding and refitting a preprocessing pipeline for every
    subset/configuration pair.
    """
    numeric_features = [
        str(col)
        for col in feature_frame.columns
        if type_map.get(str(col)) == "numeric"
    ]
    if len(numeric_features) == 0:
        return None

    try:
        x_raw = feature_frame[numeric_features].to_numpy(dtype=float, copy=True)
    except Exception:
        return None
    x_raw[~np.isfinite(x_raw)] = np.nan

    norm = str(normalize_method).strip().lower()
    folds = []
    for fold_pos, (train_idx, test_idx) in enumerate(cv_splits):
        x_train_raw = x_raw[train_idx]
        x_test_raw = x_raw[test_idx]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            med = np.nanmedian(x_train_raw, axis=0)
        valid = np.isfinite(med)
        med_safe = np.where(valid, med, 0.0)

        x_train = np.where(np.isnan(x_train_raw), med_safe, x_train_raw)
        x_test = np.where(np.isnan(x_test_raw), med_safe, x_test_raw)

        if norm == "minmax":
            data_min = np.min(x_train, axis=0)
            data_max = np.max(x_train, axis=0)
            scale = data_max - data_min
            scale = np.where(np.isfinite(scale) & (scale != 0.0), scale, 1.0)
            x_train = (x_train - data_min) / scale
            x_test = (x_test - data_min) / scale
        elif norm != "none":
            mean = np.mean(x_train, axis=0)
            scale = np.std(x_train, axis=0, ddof=0)
            scale = np.where(np.isfinite(scale) & (scale != 0.0), scale, 1.0)
            x_train = (x_train - mean) / scale
            x_test = (x_test - mean) / scale

        fold = {
            "train_idx": train_idx,
            "test_idx": test_idx,
            "x_train": np.asarray(x_train, dtype=float),
            "x_test": np.asarray(x_test, dtype=float),
            "valid": np.asarray(valid, dtype=bool),
        }
        if fold_y_train is not None and fold_pos < len(fold_y_train):
            y_train = fold_y_train[fold_pos]
            fold["y_train"] = y_train
            if fold_class_valid is not None and fold_pos < len(fold_class_valid):
                fold["train_has_multiple_classes"] = bool(fold_class_valid[fold_pos])
            else:
                fold["train_has_multiple_classes"] = bool(len(np.unique(y_train)) >= 2)
        elif y is not None:
            y_train = y[train_idx]
            fold["y_train"] = y_train
            if fold_class_valid is not None and fold_pos < len(fold_class_valid):
                fold["train_has_multiple_classes"] = bool(fold_class_valid[fold_pos])
            else:
                fold["train_has_multiple_classes"] = bool(len(np.unique(y_train)) >= 2)
        folds.append(fold)

    return {
        "features": numeric_features,
        "feature_index": {name: idx for idx, name in enumerate(numeric_features)},
        "folds": folds,
        "normalize_method": norm,
    }


def _slice_numeric_classifier_cv_matrices(
    numeric_cv_cache: dict[str, Any] | None,
    col_idx: np.ndarray,
) -> list[dict[str, Any]] | None:
    """Materialize a numeric subset once so all classifier configs reuse it."""
    if numeric_cv_cache is None:
        return None
    col_idx = np.asarray(col_idx, dtype=int)
    folds = []
    for fold in numeric_cv_cache.get("folds", []):
        if not bool(np.asarray(fold["valid"])[col_idx].all()):
            return None
        out = {
            "train_idx": fold["train_idx"],
            "test_idx": fold["test_idx"],
            "x_train": fold["x_train"][:, col_idx],
            "x_test": fold["x_test"][:, col_idx],
        }
        if "y_train" in fold:
            out["y_train"] = fold["y_train"]
        if "train_has_multiple_classes" in fold:
            out["train_has_multiple_classes"] = fold["train_has_multiple_classes"]
        folds.append(out)
    return folds


def _score_classifier_subset_fast_numeric(
    numeric_cv_cache: dict[str, Any] | None,
    type_map: dict[str, str],
    y: np.ndarray,
    features: Iterable[str],
    config: dict[str, Any],
    class_codes: np.ndarray,
    collect_predictions: bool = False,
    col_idx: np.ndarray | None = None,
    fold_class_valid: list[bool] | None = None,
) -> dict[str, Any] | None:
    """Score a numeric-only subset using cached fold matrices."""
    if numeric_cv_cache is None:
        return None
    from sklearn.base import clone

    feature_list = [str(f) for f in features]
    if col_idx is None:
        if any(type_map.get(f) != "numeric" for f in feature_list):
            return None
        feature_index = numeric_cv_cache.get("feature_index", {})
        if any(f not in feature_index for f in feature_list):
            return None
        col_idx = np.asarray([feature_index[f] for f in feature_list], dtype=int)
    else:
        col_idx = np.asarray(col_idx, dtype=int)

    pred = np.full(len(y), -1, dtype=int)
    proba = np.full((len(y), len(class_codes)), np.nan, dtype=float)
    fold_id = np.full(len(y), -1, dtype=int) if collect_predictions else None

    for fold_idx, fold in enumerate(numeric_cv_cache.get("folds", []), start=1):
        train_idx = fold["train_idx"]
        test_idx = fold["test_idx"]
        if fold_class_valid is not None and fold_idx - 1 < len(fold_class_valid):
            valid_fold = bool(fold_class_valid[fold_idx - 1])
        else:
            valid_fold = fold.get("train_has_multiple_classes", None)
            if valid_fold is None:
                valid_fold = len(np.unique(y[train_idx])) >= 2
        if not valid_fold:
            return None
        if not bool(np.asarray(fold["valid"])[col_idx].all()):
            return None

        x_train = fold["x_train"][:, col_idx]
        x_test = fold["x_test"][:, col_idx]
        y_train = fold.get("y_train", y[train_idx])
        estimator = clone(config["estimator"])
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                estimator.fit(x_train, y_train)
                fold_pred = np.asarray(estimator.predict(x_test), dtype=int)
                pred[test_idx] = fold_pred
                proba[test_idx] = _align_classifier_proba(
                    estimator,
                    x_test,
                    class_codes,
                    pred=fold_pred,
                )
                if fold_id is not None:
                    fold_id[test_idx] = int(fold_idx)
        except Exception:
            return None

    return _classifier_metrics_from_predictions(
        y,
        pred,
        proba,
        class_codes,
        fold_id=fold_id,
        collect_predictions=collect_predictions,
    )


def _score_classifier_subset_auto(
    feature_frame: pd.DataFrame,
    type_map: dict[str, str],
    y: np.ndarray,
    features: Iterable[str],
    config: dict[str, Any],
    class_codes: np.ndarray,
    cv: str = "stratified5",
    normalize_method: str = "zscore",
    random_state: int = 20260708,
    collect_predictions: bool = False,
    cv_splits: list[tuple[np.ndarray, np.ndarray]] | None = None,
    numeric_cv_cache: dict[str, Any] | None = None,
    fast_numeric: bool = True,
    numeric_col_idx: np.ndarray | None = None,
    cv_matrices: list[dict[str, Any]] | None = None,
    fold_class_valid: list[bool] | None = None,
) -> dict[str, Any] | None:
    if bool(fast_numeric):
        metrics = _score_classifier_subset_fast_numeric(
            numeric_cv_cache,
            type_map,
            y,
            features,
            config,
            class_codes,
            collect_predictions=collect_predictions,
            col_idx=numeric_col_idx,
            fold_class_valid=fold_class_valid,
        )
        if metrics is not None:
            return metrics

    if cv_matrices is not None:
        metrics = _score_classifier_subset_from_cv_matrices(
            cv_matrices,
            y,
            config,
            class_codes,
            collect_predictions=collect_predictions,
            fold_class_valid=fold_class_valid,
        )
        if metrics is not None:
            return metrics

    return _score_classifier_subset(
        feature_frame,
        type_map,
        y,
        features,
        config,
        class_codes,
        cv=cv,
        normalize_method=normalize_method,
        random_state=random_state,
        collect_predictions=collect_predictions,
        cv_splits=cv_splits,
        fold_class_valid=fold_class_valid,
    )


def _classifier_sort_spec(scoring: str) -> tuple[list[str], list[bool]]:
    score = str(scoring).strip()
    if score == "":
        score = "balanced_accuracy"
    lower_is_better = score in {"log_loss", "loss"}
    if score == "loss":
        score = "log_loss"
    columns = [score, "macro_ovr_auc", "macro_f1", "balanced_accuracy", "family", "features"]
    ascending = [bool(lower_is_better), False, False, False, True, True]
    return columns, ascending


def _sort_classifier_results(results: pd.DataFrame, scoring: str) -> pd.DataFrame:
    if len(results) == 0:
        return results.copy()
    columns, ascending = _classifier_sort_spec(scoring)
    columns = [c for c in columns if c in results.columns]
    ascending = ascending[: len(columns)]
    return results.sort_values(columns, ascending=ascending).reset_index(drop=True)


def _feature_recurrence_summary(
    results: pd.DataFrame,
    top_n: int,
    scoring: str = "balanced_accuracy",
) -> pd.DataFrame:
    if len(results) == 0:
        return pd.DataFrame()
    top = _sort_classifier_results(results, scoring).head(max(1, int(top_n)))
    score_col = "log_loss" if str(scoring).strip() in {"log_loss", "loss"} else str(scoring).strip()
    if score_col not in top.columns:
        score_col = "balanced_accuracy"
    lower_is_better = score_col == "log_loss"

    rows = []
    features_seen = sorted({f for subset in top["features_tuple"] for f in subset})
    for feature in features_seen:
        sub = top[top["features_tuple"].map(lambda vals, feat=feature: feat in vals)]
        metric_vals = pd.to_numeric(sub[score_col], errors="coerce")
        rows.append({
            "feature": feature,
            "top_n_appearances": int(len(sub)),
            f"best_{score_col}": float(metric_vals.min() if lower_is_better else metric_vals.max()),
            f"mean_{score_col}": float(metric_vals.mean()),
            "best_balanced_accuracy": float(pd.to_numeric(sub["balanced_accuracy"], errors="coerce").max()),
            "best_macro_ovr_auc": float(pd.to_numeric(sub["macro_ovr_auc"], errors="coerce").max(skipna=True)),
        })
    if len(rows) == 0:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["top_n_appearances", "best_balanced_accuracy", "feature"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _classifier_sweep_data_hash(
    target_text: pd.Series,
    feature_frame: pd.DataFrame,
    predictors: list[str],
    target: str,
) -> str:
    """Stable hash for deciding whether checkpoint rows match this data."""
    try:
        sig_df = pd.concat(
            [pd.Series(target_text, name=str(target)), feature_frame[predictors]],
            axis=1,
        )
        row_hash = pd.util.hash_pandas_object(sig_df, index=True).to_numpy(dtype=np.uint64)
        h = hashlib.sha256()
        h.update(json.dumps([str(c) for c in sig_df.columns]).encode("utf-8"))
        h.update(row_hash.tobytes())
        return h.hexdigest()
    except Exception:
        return ""


def _plot_classifier_sweep_outputs(
    results: pd.DataFrame,
    feature_stats: pd.DataFrame,
    figures_dir: Path,
    scoring: str = "balanced_accuracy",
    class_count: int = 3,
    dpi: int = 220,
) -> None:
    if len(results) == 0:
        return
    figures_dir.mkdir(parents=True, exist_ok=True)
    score_col = "log_loss" if str(scoring).strip() in {"log_loss", "loss"} else str(scoring).strip()
    if score_col not in results.columns:
        score_col = "balanced_accuracy"
    top = _sort_classifier_results(results, score_col).head(30).copy()
    if "rank" not in top.columns:
        top.insert(0, "rank", np.arange(1, len(top) + 1))
    top["model_label"] = (
        top["rank"].astype(str)
        + ". "
        + top["family"].astype(str)
        + "\n"
        + top["features"].astype(str).str.slice(0, 95)
    )

    plt.figure(figsize=(10, 8))
    sns.barplot(data=top, y="model_label", x=score_col, hue="subset_size", dodge=False)
    if score_col != "log_loss" and class_count > 0:
        plt.axvline(1.0 / float(class_count), color="black", linestyle="--", linewidth=1)
    plt.xlabel(f"Cross-validated {score_col.replace('_', ' ')}")
    plt.ylabel("")
    plt.title("Top iterative classifier sweep models")
    plt.tight_layout()
    save_fig(
        plt.gcf(), figures_dir, "top_iterative_model_sweep",
        figure_formats=("png",), dpi=dpi, rasterize=False,
        transparent=False, verbose=False,
    )
    plt.close()

    pivot = results.pivot_table(
        index="family",
        columns="subset_size",
        values=score_col,
        aggfunc="min" if score_col == "log_loss" else "max",
    )
    if len(pivot) > 0:
        plt.figure(figsize=(8, 5))
        sns.heatmap(pivot, annot=True, fmt=".2f", cmap="viridis")
        plt.title(f"Best {score_col.replace('_', ' ')} by model family and subset size")
        plt.tight_layout()
        save_fig(
            plt.gcf(), figures_dir, "family_by_subset_size_heatmap",
            figure_formats=("png",), dpi=dpi, rasterize=False,
            transparent=False, verbose=False,
        )
        plt.close()

    if feature_stats is not None and not feature_stats.empty:
        show = feature_stats.head(25).copy()
        plt.figure(figsize=(9, 8))
        sns.barplot(data=show, y="feature", x="top_n_appearances", color="#3A6EA5")
        plt.xlabel("Appearances among top ranked models")
        plt.ylabel("")
        plt.title("Features recurring in top models")
        plt.tight_layout()
        save_fig(
            plt.gcf(), figures_dir, "top_feature_recurrence",
            figure_formats=("png",), dpi=dpi, rasterize=False,
            transparent=False, verbose=False,
        )
        plt.close()


def _classifier_sweep_permutation_test(
    feature_frame: pd.DataFrame,
    type_map: dict[str, str],
    y: np.ndarray,
    top_row: pd.Series,
    config: dict[str, Any],
    class_codes: np.ndarray,
    n_permutations: int,
    cv: str,
    scoring: str,
    normalize_method: str,
    random_state: int,
) -> pd.DataFrame:
    n_perm = int(n_permutations)
    if n_perm <= 0:
        return pd.DataFrame()
    score_col = "log_loss" if str(scoring).strip() in {"log_loss", "loss"} else str(scoring).strip()
    if score_col not in top_row.index:
        score_col = "balanced_accuracy"
    observed = float(top_row[score_col])
    lower_is_better = score_col == "log_loss"
    features = list(top_row["features_tuple"])
    rng = np.random.default_rng(int(random_state))
    perm_scores = []
    for _ in range(n_perm):
        y_perm = np.array(y, copy=True)
        rng.shuffle(y_perm)
        metrics = _score_classifier_subset(
            feature_frame,
            type_map,
            y_perm,
            features,
            config,
            class_codes,
            cv=cv,
            normalize_method=normalize_method,
            random_state=random_state,
            collect_predictions=False,
        )
        if metrics is None:
            continue
        score_val = metrics.get(score_col, np.nan)
        if np.isfinite(score_val):
            perm_scores.append(float(score_val))

    if len(perm_scores) == 0:
        return pd.DataFrame()
    scores_arr = np.asarray(perm_scores, dtype=float)
    if lower_is_better:
        extreme = int(np.sum(scores_arr <= observed))
    else:
        extreme = int(np.sum(scores_arr >= observed))
    pvalue = float((extreme + 1) / (len(scores_arr) + 1))
    return pd.DataFrame([{
        "family": top_row["family"],
        "model_config": top_row["model_config"],
        "features": top_row["features"],
        "subset_size": int(top_row["subset_size"]),
        "scoring": score_col,
        "observed_score": observed,
        "pvalue": pvalue,
        "permutation_mean": float(np.mean(scores_arr)),
        "permutation_sd": float(np.std(scores_arr, ddof=1)) if len(scores_arr) > 1 else np.nan,
        "n_permutations_requested": n_perm,
        "n_permutations_valid": int(len(scores_arr)),
        "permutation_scores": ";".join(f"{v:.6f}" for v in scores_arr),
    }])


def _write_classifier_sweep_readme(
    outdir: Path,
    df: pd.DataFrame,
    target: str,
    predictors: list[str],
    configs: list[dict[str, Any]],
    results: pd.DataFrame,
    permutations: pd.DataFrame,
    class_labels: list[str],
    max_features: int,
    cv: str,
    search_strategy: str,
    model_preset: str,
    scoring: str,
) -> None:
    top = _sort_classifier_results(results, scoring).head(15)
    try:
        subset_count = sum(math.comb(len(predictors), k) for k in range(1, int(max_features) + 1))
    except Exception:
        subset_count = np.nan
    lines = [
        "# Iterative Model Sweep",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "This is a discovery screen: many feature subsets and classifier settings are tested, then ranked.",
        "Use an independent validation set, nested cross-validation, or a search-level label-shuffle test before treating the top model as confirmed.",
        "",
        "## Dataset",
        "",
        f"- Rows used: {len(df)}",
        f"- Target: `{target}`",
        "- Class counts: " + ", ".join(f"{label}={int((df[target].astype(str) == str(label)).sum())}" for label in class_labels),
        f"- Candidate predictors: {len(predictors)}",
        f"- Max subset size: {int(max_features)}",
        f"- Exhaustive subset estimate: {subset_count}",
        f"- Classifier configurations: {len(configs)}",
        f"- Valid model scores: {len(results)}",
        f"- CV mode: `{cv}`",
        f"- Search strategy: `{search_strategy}`",
        f"- Model preset: `{model_preset}`",
        f"- Ranking metric: `{scoring}`",
        "",
        "## Top Results",
        "",
    ]
    if len(top) > 0:
        show_cols = [
            c for c in [
                "rank",
                "family",
                "model_config",
                "subset_size",
                "balanced_accuracy",
                "macro_ovr_auc",
                "macro_f1",
                "log_loss",
                "features",
            ]
            if c in top.columns
        ]
        lines.append(top[show_cols].to_string(index=False))
        lines.append("")

    if permutations is not None and not permutations.empty:
        lines.extend([
            "## Top-Model Label Shuffle",
            "",
            permutations.drop(columns=["permutation_scores"], errors="ignore").to_string(index=False),
            "",
            "This shuffle only tests the selected top model, not the whole search process.",
            "",
        ])

    lines.extend([
        "## Key Files",
        "",
        "- `iterative_model_sweep_scores.csv`",
        "- `top_iterative_model_sweep_scores.csv`",
        "- `top_feature_recurrence.csv`",
        "- `top_model_predictions.csv`",
        "- `top_model_permutation_test.csv`",
        "- `top_iterative_model_sweep.png`",
        "- `family_by_subset_size_heatmap.png`",
        "- `top_feature_recurrence.png`",
    ])
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def iterative_model_sweep(
    batch_or_df=None,
    target: str | None = None,
    possible_predictors: Iterable[str] | None = None,
    data_cols: Iterable[str] | None = None,
    predictors: Iterable[str] | None = None,
    candidate_predictors: Iterable[str] | None = None,
    column_strings=None,
    regex_string=None,
    predictor_exclude="",
    data_col_contains=None,
    data_col_regex=None,
    data_col_exclude=None,
    excluded_predictors: Iterable[str] | None = None,
    max_features: int = 2,
    repeat_features: bool = False,
    model_preset: str = "ultra_compact",
    model_families: Iterable[str] | None = None,
    class_order: Iterable[Any] | None = None,
    cv: str = "stratified5",
    scoring: str = "balanced_accuracy",
    specificity=None,
    filter_by=None,
    exclude=None,
    normalize_method: str = "zscore",
    search_strategy: str = "exhaustive",
    beam_width: int = 100,
    save: bool = True,
    output_dir: str | os.PathLike | None = None,
    run_label: str = "iterative_model_sweep",
    top_n: int = 200,
    permutations: int = 0,
    checkpoint_every: int = 250,
    resume: bool = False,
    plot: bool = True,
    dpi: int = 220,
    random_state: int = 20260708,
    fast_numeric: bool = True,
    n_jobs: int = 1,
    parallel_backend: str = "threads",
    parallel_batch_size: int = 256,
    verbose: bool = True,
    return_details: bool = True,
    data=None,
):
    """
    Iteratively sweep feature subsets and classifier families for a class target.

    This is the classification counterpart to :func:`iterative_best_fit`.
    It is meant for discovery screens such as Control vs MCI vs AD from a
    candidate panel of volume/activity/covariate columns.

    Parameters
    ----------
    batch_or_df:
        Either a PyFLASH batch-like object exposing ``.summary`` or a pandas
        DataFrame.
    target:
        Categorical target column to predict.
    possible_predictors / column_strings / regex_string:
        Candidate predictor selection.  Predictors must be real DataFrame
        columns; formula terms are not used for this classifier sweep.
    max_features:
        Test every subset size from 1..max_features when exhaustive.  In beam
        mode this is the maximum depth.
    search_strategy:
        ``"exhaustive"`` tests every subset. ``"beam"`` expands only the best
        subsets from the previous level and is much faster for large feature
        pools, but can miss the global best subset.
    model_preset:
        ``"ultra_compact"``, ``"compact"``, or ``"full"`` classifier grids.
    cv:
        ``"stratified5"`` (default), ``"stratifiedN"``, or ``"loo"``.
    n_jobs:
        Number of parallel scoring workers. Use -1 for all cores. Parallel
        scoring uses threads by default so cached CV matrices are shared.
    parallel_backend:
        ``"threads"`` or ``"processes"``. Processes can be faster for large
        exhaustive sweeps but have more startup overhead on Windows.

    Returns
    -------
    dict by default, including the ranked score table, best feature subset,
    fitted final estimator, feature recurrence table, and output paths.
    """
    batch_or_df = prefer_alias(
        batch_or_df,
        data,
        current_name="batch_or_df",
        alias_name="data",
    )
    if batch_or_df is None:
        raise ValueError("iterative_model_sweep needs data= or a first positional data argument.")
    if target is None:
        raise ValueError("iterative_model_sweep needs target=.")
    possible_predictors = prefer_alias(
        possible_predictors,
        data_cols,
        current_name="possible_predictors",
        alias_name="data_cols",
    )
    possible_predictors = prefer_alias(
        possible_predictors,
        predictors,
        current_name="possible_predictors/data_cols",
        alias_name="predictors",
    )
    possible_predictors = prefer_alias(
        possible_predictors,
        candidate_predictors,
        current_name="possible_predictors/data_cols",
        alias_name="candidate_predictors",
    )
    _, column_strings, regex_string, predictor_exclude = resolve_data_column_aliases(
        filtered_columns=None,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=predictor_exclude,
        data_cols=None,
        data_col_contains=data_col_contains,
        data_col_regex=data_col_regex,
        data_col_exclude=data_col_exclude,
    )
    specificity = prefer_alias(
        specificity,
        normalize_filter_by(filter_by),
        current_name="specificity",
        alias_name="filter_by",
    )

    if isinstance(batch_or_df, pd.DataFrame):
        source_df = batch_or_df
        batch_fig_path = None
    elif hasattr(batch_or_df, "summary"):
        source_df = getattr(batch_or_df, "summary", None)
        batch_fig_path = getattr(batch_or_df, "fig_path", None)
    else:
        raise ValueError("First argument must be a pandas DataFrame or expose .summary.")
    if not isinstance(source_df, pd.DataFrame) or len(source_df) == 0:
        raise ValueError("Input data must be a non-empty pandas DataFrame.")

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = iterative_model_sweep(
                batch_or_df,
                target=target,
                possible_predictors=possible_predictors,
                column_strings=column_strings,
                regex_string=regex_string,
                predictor_exclude=predictor_exclude,
                excluded_predictors=excluded_predictors,
                max_features=max_features,
                repeat_features=repeat_features,
                model_preset=model_preset,
                model_families=model_families,
                class_order=class_order,
                cv=cv,
                scoring=scoring,
                specificity=spec,
                exclude=exclude,
                normalize_method=normalize_method,
                search_strategy=search_strategy,
                beam_width=beam_width,
                save=save,
                output_dir=output_dir,
                run_label=run_label,
                top_n=top_n,
                permutations=permutations,
                checkpoint_every=checkpoint_every,
                resume=resume,
                plot=plot,
                dpi=dpi,
                random_state=random_state,
                fast_numeric=fast_numeric,
                n_jobs=n_jobs,
                parallel_backend=parallel_backend,
                parallel_batch_size=parallel_batch_size,
                verbose=verbose,
                return_details=return_details,
            )
        return queued_outputs

    df = source_df.copy()
    if target not in df.columns:
        raise ValueError(f"target '{target}' not found in DataFrame.")

    predictor_name_blacklist = set(DEFAULT_EXCLUDED_PREDICTORS)
    predictor_name_blacklist.add(str(target))
    if excluded_predictors is not None:
        predictor_name_blacklist.update([str(c) for c in excluded_predictors])

    predictors = _resolve_possible_predictors(
        df,
        possible_predictors=possible_predictors,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=predictor_exclude,
    )
    predictors = [
        str(p)
        for p in predictors
        if str(p) in df.columns and str(p) not in predictor_name_blacklist
    ]
    predictors = _unique_preserve_order(predictors)
    if len(predictors) == 0:
        raise ValueError(
            "No predictor columns available after filtering. "
            "Check possible_predictors/column_strings/regex_string."
        )

    work_df = _filter_df_by_specificity(df, specificity).copy()
    pre_exclude_n = len(work_df)
    work_df = _exclude_df_by_rules(work_df, exclude).copy()
    work_df = _drop_unused_categorical_levels(work_df)
    if verbose and exclude is not None:
        _log.hint(f"[iterative_model_sweep] Exclude filter removed {pre_exclude_n - len(work_df)} rows.")
    if len(work_df) == 0:
        raise ValueError("No rows remain after specificity/exclude filtering.")

    target_series = pd.Series(work_df[target], index=work_df.index)
    valid_target = target_series.notna() & (~_sentinel_like_mask(target_series))
    target_text = target_series.astype(str).str.strip()
    valid_target = valid_target & (target_text != "")

    if class_order is not None:
        class_labels = [str(c) for c in class_order]
        valid_target = valid_target & target_text.isin(class_labels)
    else:
        class_labels = _unique_preserve_order(target_text.loc[valid_target].tolist())

    work_df = work_df.loc[valid_target].copy()
    target_text = target_text.loc[valid_target]
    if len(class_labels) < 2:
        raise ValueError("Target must contain at least two classes.")
    if len(work_df) < len(class_labels) * 2:
        raise ValueError("Too few rows remain for classification cross-validation.")

    class_to_code = {label: idx for idx, label in enumerate(class_labels)}
    y = target_text.map(class_to_code).to_numpy(dtype=int)
    class_codes = np.arange(len(class_labels), dtype=int)

    feature_frame, type_map, removed_empty_features = _prepare_classifier_feature_frame(
        work_df,
        predictors,
    )
    predictors = [p for p in predictors if p in feature_frame.columns and p not in removed_empty_features]
    predictors = _unique_preserve_order(predictors)
    if len(predictors) == 0:
        raise ValueError("No predictors contain usable values after sentinel/missing filtering.")
    feature_frame = feature_frame[predictors].copy()

    max_features_i = int(max_features) if int(max_features) > 0 else len(predictors)
    max_features_i = max(1, min(max_features_i, len(predictors)))
    strategy = str(search_strategy).strip().lower()
    if strategy not in {"exhaustive", "beam"}:
        raise ValueError("search_strategy must be 'exhaustive' or 'beam'.")

    configs = _classification_model_configs(
        preset=model_preset,
        model_families=model_families,
        random_state=random_state,
    )
    for cfg in configs:
        cfg["_params_json"] = json.dumps(cfg["params"], sort_keys=True)
    config_lookup = {cfg["name"]: cfg for cfg in configs}
    cv_splits = [
        (np.asarray(train_idx, dtype=int), np.asarray(test_idx, dtype=int))
        for train_idx, test_idx in _classifier_cv_splitter(y, cv=cv, random_state=random_state).split(feature_frame, y)
    ]
    fold_y_train = [y[train_idx] for train_idx, _ in cv_splits]
    fold_class_valid = [len(np.unique(y_train)) >= 2 for y_train in fold_y_train]
    numeric_cv_cache = (
        _build_numeric_classifier_cv_cache(
            feature_frame,
            type_map,
            cv_splits,
            normalize_method=normalize_method,
            y=y,
            fold_y_train=fold_y_train,
            fold_class_valid=fold_class_valid,
        )
        if bool(fast_numeric)
        else None
    )

    if output_dir is not None:
        outdir = Path(output_dir)
    elif save and batch_fig_path is not None:
        outdir = Path(batch_fig_path) / "Modelling" / "Model Sweep" / str(run_label)
    else:
        outdir = Path.cwd() / "Modelling" / "Model Sweep" / str(run_label)
    stats_dir = outdir
    figures_dir = outdir
    if save:
        outdir.mkdir(parents=True, exist_ok=True)

    prefix_list = [_safe_predictor_prefix(p) for p in predictors]
    subset_estimate = _count_valid_feature_combinations(
        predictors,
        max_features_i,
        repeat_features=bool(repeat_features),
        prefix_list=prefix_list,
    )
    total_estimate = subset_estimate * len(configs)
    if verbose:
        _log.status(f"[iterative_model_sweep] Rows: {len(work_df)}")
        _log.status(
            "[iterative_model_sweep] Classes: "
            + ", ".join(f"{label}={int(np.sum(y == code))}" for label, code in class_to_code.items())
        )
        _log.status(f"[iterative_model_sweep] Candidate predictors: {len(predictors)}")
        _log.status(f"[iterative_model_sweep] Search strategy: {strategy}")
        _log.status(f"[iterative_model_sweep] Subsets estimate: {subset_estimate}")
        _log.status(f"[iterative_model_sweep] Model configs: {len(configs)}")
        _log.status(f"[iterative_model_sweep] Total score estimate: {total_estimate}")
        if int(n_jobs) != 1:
            _log.status(f"[iterative_model_sweep] Parallel workers: {int(n_jobs)}")
        if removed_empty_features:
            _log.hint(
                "[iterative_model_sweep] Bypassed empty predictors: "
                + ", ".join(removed_empty_features)
            )

    resume_signature = {
        "signature_version": 1,
        "target": str(target),
        "class_labels": [str(v) for v in class_labels],
        "predictors": [str(v) for v in predictors],
        "data_hash": _classifier_sweep_data_hash(target_text, feature_frame, predictors, target),
        "max_features": int(max_features_i),
        "repeat_features": bool(repeat_features),
        "model_preset": str(model_preset),
        "configs": [
            {
                "family": str(cfg["family"]),
                "name": str(cfg["name"]),
                "params_json": str(cfg.get("_params_json") or json.dumps(cfg["params"], sort_keys=True)),
            }
            for cfg in configs
        ],
        "cv": str(cv),
        "scoring": str(scoring),
        "normalize_method": str(normalize_method),
        "search_strategy": str(strategy),
        "beam_width": int(beam_width),
        "random_state": int(random_state),
        "specificity": repr(specificity),
        "exclude": repr(exclude),
    }

    partial_path = stats_dir / "iterative_model_sweep_scores_partial.csv"
    partial_meta_path = stats_dir / "iterative_model_sweep_scores_partial.meta.json"
    rows: list[dict[str, Any]] = []
    completed_keys: set[str] = set()
    resumed_partial = False
    if bool(resume) and save and partial_path.exists():
        meta_matches = False
        if partial_meta_path.exists():
            try:
                prior_signature = json.loads(partial_meta_path.read_text(encoding="utf-8"))
                meta_matches = prior_signature == resume_signature
            except Exception:
                meta_matches = False
        if meta_matches:
            partial = pd.read_csv(partial_path)
            for _, row in partial.iterrows():
                row_dict = row.to_dict()
                try:
                    row_dict["features_tuple"] = tuple(json.loads(row_dict["features_json"]))
                except Exception:
                    row_dict["features_tuple"] = tuple(str(row_dict.get("features", "")).split(" + "))
                key = f"{row_dict.get('model_config')}||{row_dict.get('features')}"
                completed_keys.add(key)
                rows.append(row_dict)
            resumed_partial = True
            if verbose:
                _log.status(f"[iterative_model_sweep] Resumed {len(rows)} prior scores.")
        else:
            if verbose:
                _log.hint(
                    "[iterative_model_sweep] Existing partial checkpoint does not "
                    "match this run; starting a fresh checkpoint."
                )
            for stale_path in [partial_path, partial_meta_path]:
                try:
                    stale_path.unlink()
                except Exception:
                    pass
    elif save and partial_path.exists():
        for stale_path in [partial_path, partial_meta_path]:
            try:
                stale_path.unlink()
            except Exception:
                pass

    partial_rows_flushed = len(rows) if resumed_partial else 0

    def _write_partial(force: bool = False) -> None:
        nonlocal partial_rows_flushed
        if not save or len(rows) <= partial_rows_flushed:
            return
        if not force and int(checkpoint_every) > 0:
            if len(rows) - partial_rows_flushed < int(checkpoint_every):
                return
        elif not force and int(checkpoint_every) <= 0:
            return
        partial_df = pd.DataFrame(rows[partial_rows_flushed:]).copy()
        partial_df = partial_df.drop(columns=["features_tuple", "rank", "model_label"], errors="ignore")
        if not partial_meta_path.exists():
            partial_meta_path.write_text(
                json.dumps(resume_signature, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        write_header = not partial_path.exists()
        partial_df.to_csv(
            partial_path,
            mode="a" if partial_path.exists() else "w",
            header=write_header,
            index=False,
            float_format="%.17g",
        )
        partial_rows_flushed = len(rows)

    name_to_index = {p: i for i, p in enumerate(predictors)}

    def _passes_repeat_filter(subset_names: Iterable[str]) -> bool:
        if repeat_features:
            return True
        prefixes = [_safe_predictor_prefix(s) for s in subset_names]
        return len(prefixes) == len(set(prefixes))

    def _prepare_subset_scoring(subset: tuple[str, ...]):
        subset_list = [str(s) for s in subset]
        features_text = " + ".join(subset_list)
        features_json = json.dumps(subset_list)
        numeric_col_idx = None
        subset_cv_matrices = None
        if bool(fast_numeric) and numeric_cv_cache is not None:
            feature_index = numeric_cv_cache.get("feature_index", {})
            if all(type_map.get(f) == "numeric" and f in feature_index for f in subset_list):
                numeric_col_idx = np.asarray([feature_index[f] for f in subset_list], dtype=int)
                subset_cv_matrices = _slice_numeric_classifier_cv_matrices(
                    numeric_cv_cache,
                    numeric_col_idx,
                )
                if subset_cv_matrices is not None:
                    numeric_col_idx = None
        if subset_cv_matrices is None:
            subset_cv_matrices = _build_classifier_cv_matrices(
                feature_frame,
                type_map,
                subset_list,
                cv_splits,
                normalize_method=normalize_method,
                y=y,
                fold_y_train=fold_y_train,
                fold_class_valid=fold_class_valid,
            )
        return subset_list, features_text, features_json, numeric_col_idx, subset_cv_matrices

    def _score_one_model(
        subset: tuple[str, ...],
        config: dict[str, Any],
        prepared=None,
    ) -> dict[str, Any] | None:
        if prepared is None:
            subset_list, features_text, features_json, numeric_col_idx, subset_cv_matrices = (
                _prepare_subset_scoring(subset)
            )
        else:
            subset_list, features_text, features_json, numeric_col_idx, subset_cv_matrices = prepared
        metrics = _score_classifier_subset_auto(
            feature_frame,
            type_map,
            y,
            subset_list,
            config,
            class_codes,
            cv=cv,
            normalize_method=normalize_method,
            random_state=random_state,
            collect_predictions=False,
            cv_splits=cv_splits,
            numeric_cv_cache=numeric_cv_cache if subset_cv_matrices is None else None,
            fast_numeric=bool(fast_numeric) and numeric_col_idx is not None,
            numeric_col_idx=numeric_col_idx,
            cv_matrices=subset_cv_matrices,
            fold_class_valid=fold_class_valid,
        )
        if metrics is None:
            return None
        return {
            "family": config["family"],
            "model_config": config["name"],
            "params_json": config.get("_params_json") or json.dumps(config["params"], sort_keys=True),
            "subset_size": len(subset_list),
            "features": features_text,
            "features_json": features_json,
            "features_tuple": tuple(subset_list),
            **metrics,
        }

    def _record_scored_rows(scored_rows: list[dict[str, Any] | None], keys: list[str]) -> None:
        for row, key in zip(scored_rows, keys):
            completed_keys.add(key)
            if row is not None:
                rows.append(row)
        if int(checkpoint_every) > 0:
            _write_partial()

    def _progress(done_counter: int) -> None:
        if verbose and (done_counter % 250 == 0 or done_counter == total_estimate):
            elapsed = time.time() - start_time
            rate = done_counter / elapsed if elapsed > 0 else float("nan")
            _log.status(
                f"[iterative_model_sweep] Scored {done_counter}/{total_estimate} "
                f"configs ({rate:.1f}/s, valid={len(rows)})"
            )

    def _score_subset(subset: tuple[str, ...], done_counter: int) -> int:
        subset = tuple(str(s) for s in subset)
        pre_features_text = " + ".join(subset)
        if all(f"{config['name']}||{pre_features_text}" in completed_keys for config in configs):
            return done_counter
        subset_list, features_text, features_json, numeric_col_idx, subset_cv_matrices = (
            _prepare_subset_scoring(subset)
        )
        prepared = (subset_list, features_text, features_json, numeric_col_idx, subset_cv_matrices)
        for config in configs:
            key = f"{config['name']}||{features_text}"
            if key in completed_keys:
                continue
            row = _score_one_model(subset, config, prepared=prepared)
            done_counter += 1
            _record_scored_rows([row], [key])
            _progress(done_counter)
        return done_counter

    def _score_candidate_subsets(candidates: Iterable[tuple[str, ...]], done_counter: int) -> int:
        n_jobs_i = int(n_jobs)
        batch_size = max(1, int(parallel_batch_size))

        if n_jobs_i == 1:
            for subset in candidates:
                done_counter = _score_subset(tuple(subset), done_counter)
            return done_counter

        try:
            from joblib import Parallel, delayed
        except Exception:
            if verbose:
                _log.hint("[iterative_model_sweep] joblib unavailable; falling back to serial scoring.")
            for subset in candidates:
                done_counter = _score_subset(tuple(subset), done_counter)
            return done_counter

        backend_key = str(parallel_backend).strip().lower()
        if backend_key in {"process", "processes", "loky"}:
            parallel = Parallel(
                n_jobs=n_jobs_i,
                prefer="processes",
                batch_size="auto",
            )
        else:
            parallel = Parallel(
                n_jobs=n_jobs_i,
                prefer="threads",
                require="sharedmem",
                batch_size="auto",
            )
        pending: list[tuple[tuple[Any, ...], list[dict[str, Any]], list[str]]] = []

        def _score_subset_configs_thread_worker(
            subset: tuple[str, ...],
            configs_to_run: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            prepared = _prepare_subset_scoring(subset)
            return _score_prepared_subset_configs_worker(
                prepared,
                configs_to_run,
                y,
                class_codes,
                fold_class_valid,
            )

        def _flush_pending() -> None:
            nonlocal done_counter, pending
            if len(pending) == 0:
                return
            chunk = pending
            pending = []
            if backend_key in {"process", "processes", "loky"}:
                scored = parallel(
                    delayed(_score_prepared_subset_configs_worker)(
                        prepared,
                        configs_to_run,
                        y,
                        class_codes,
                        fold_class_valid,
                    )
                    for prepared, configs_to_run, _keys in chunk
                )
            else:
                scored = parallel(
                    delayed(_score_subset_configs_thread_worker)(subset, configs_to_run)
                    for subset, configs_to_run, _keys in chunk
                )
            done_counter += sum(len(keys) for _prepared, _configs_to_run, keys in chunk)
            for _prepared, _configs_to_run, keys in chunk:
                completed_keys.update(keys)
            for group_rows in scored:
                rows.extend(group_rows)
            if int(checkpoint_every) > 0:
                _write_partial()
            _progress(done_counter)

        for subset in candidates:
            subset = tuple(str(s) for s in subset)
            features_text = " + ".join(subset)
            configs_to_run = []
            keys = []
            for config in configs:
                key = f"{config['name']}||{features_text}"
                if key in completed_keys:
                    continue
                configs_to_run.append(config)
                keys.append(key)
            if len(configs_to_run) == 0:
                continue
            if backend_key in {"process", "processes", "loky"}:
                prepared = _prepare_subset_scoring(subset)
            else:
                prepared = subset
            pending.append((prepared, configs_to_run, keys))
            if len(pending) >= batch_size:
                _flush_pending()
        _flush_pending()
        return done_counter

    start_time = time.time()
    done = 0
    if strategy == "exhaustive":
        for k in range(1, max_features_i + 1):
            if verbose:
                _log.status(f"[iterative_model_sweep] Level {k}: exhaustive scoring")
            candidates = _iter_valid_feature_combinations_by_size(
                predictors,
                k,
                repeat_features=bool(repeat_features),
                prefix_list=prefix_list,
            )
            done = _score_candidate_subsets(candidates, done)
    else:
        beam_w = max(1, int(beam_width))
        surviving: list[tuple[str, ...]] = []
        for k in range(1, max_features_i + 1):
            if k == 1:
                candidates = [(p,) for p in predictors]
            else:
                if len(rows) == 0 or len(surviving) == 0:
                    break
                surviving_idx = [
                    tuple(name_to_index[name] for name in subset if name in name_to_index)
                    for subset in surviving
                ]
                expanded_idx = _beam_expand(
                    surviving_idx,
                    len(predictors),
                    bool(repeat_features),
                    prefix_list,
                )
                candidates = [tuple(predictors[i] for i in idx_tuple) for idx_tuple in expanded_idx]

            if verbose:
                _log.status(
                    f"[iterative_model_sweep] Beam level {k}: scoring {len(candidates)} subsets"
                )
            done = _score_candidate_subsets((tuple(subset) for subset in candidates), done)

            level_results = pd.DataFrame(rows)
            if len(level_results) == 0:
                surviving = []
                continue
            level_results = level_results[level_results["subset_size"] == k].copy()
            if len(level_results) == 0:
                surviving = []
                continue
            level_results = _sort_classifier_results(level_results, scoring)
            surviving = list(dict.fromkeys(level_results["features_tuple"].tolist()))[:beam_w]

    _write_partial(force=True)
    if len(rows) == 0:
        raise RuntimeError("No valid model scores were produced.")

    results = pd.DataFrame(rows)
    results = _sort_classifier_results(results, scoring)
    if "rank" in results.columns:
        results = results.drop(columns=["rank"])
    results.insert(0, "rank", np.arange(1, len(results) + 1))
    results["model_label"] = (
        results["rank"].astype(str)
        + ". "
        + results["family"].astype(str)
        + "\n"
        + results["features"].astype(str).str.slice(0, 95)
    )

    top_row = results.iloc[0].copy()
    best_features = list(top_row["features_tuple"])
    best_config = config_lookup[str(top_row["model_config"])]
    best_metrics = _score_classifier_subset_auto(
        feature_frame,
        type_map,
        y,
        best_features,
        best_config,
        class_codes,
        cv=cv,
        normalize_method=normalize_method,
        random_state=random_state,
        collect_predictions=True,
        cv_splits=cv_splits,
        numeric_cv_cache=numeric_cv_cache,
        fast_numeric=fast_numeric,
        fold_class_valid=fold_class_valid,
    )
    if best_metrics is None:
        raise RuntimeError("Best model could not be refit for prediction output.")

    from sklearn.base import clone
    from sklearn.pipeline import Pipeline

    best_estimator = Pipeline([
        ("preprocess", _build_classifier_preprocessor(type_map, best_features, normalize_method)),
        ("clf", clone(best_config["estimator"])),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        best_estimator.fit(feature_frame[best_features], y)

    pred_codes = np.asarray(best_metrics["prediction_code"], dtype=int)
    proba = np.asarray(best_metrics["probability"], dtype=float)
    predictions = pd.DataFrame({
        "row_index": work_df.index.to_numpy(),
        "fold": np.asarray(best_metrics["fold"], dtype=int),
        "actual": [class_labels[int(code)] for code in y],
        "actual_code": y,
        "predicted": [class_labels[int(code)] if 0 <= int(code) < len(class_labels) else "" for code in pred_codes],
        "predicted_code": pred_codes,
    })
    for code, label in enumerate(class_labels):
        predictions[f"prob_{label}"] = proba[:, code]

    feature_stats = _feature_recurrence_summary(results, int(top_n), scoring=scoring)
    permutation_df = _classifier_sweep_permutation_test(
        feature_frame,
        type_map,
        y,
        top_row,
        best_config,
        class_codes,
        int(permutations),
        cv,
        scoring,
        normalize_method,
        int(random_state),
    )

    output_results = results.drop(columns=["features_tuple", "model_label"], errors="ignore")
    if save:
        output_results.to_csv(
            stats_dir / "iterative_model_sweep_scores.csv",
            index=False,
            float_format="%.17g",
        )
        output_results.head(max(1, int(top_n))).to_csv(
            stats_dir / "top_iterative_model_sweep_scores.csv",
            index=False,
            float_format="%.17g",
        )
        feature_stats.to_csv(
            stats_dir / "top_feature_recurrence.csv",
            index=False,
            float_format="%.17g",
        )
        predictions.to_csv(
            stats_dir / "top_model_predictions.csv",
            index=False,
            float_format="%.17g",
        )
        permutation_df.to_csv(
            stats_dir / "top_model_permutation_test.csv",
            index=False,
            float_format="%.17g",
        )
        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "target": str(target),
            "class_labels": class_labels,
            "class_counts": {label: int(np.sum(y == code)) for label, code in class_to_code.items()},
            "predictors": predictors,
            "removed_empty_features": removed_empty_features,
            "max_features": int(max_features_i),
            "subset_estimate": int(subset_estimate),
            "classifier_config_count": int(len(configs)),
            "valid_model_scores": int(len(results)),
            "cv": str(cv),
            "scoring": str(scoring),
            "model_preset": str(model_preset),
            "search_strategy": str(strategy),
            "beam_width": int(beam_width),
            "fast_numeric": bool(fast_numeric),
            "n_jobs": int(n_jobs),
            "parallel_backend": str(parallel_backend),
            "parallel_batch_size": int(parallel_batch_size),
            "best_family": str(top_row["family"]),
            "best_model_config": str(top_row["model_config"]),
            "best_features": best_features,
        }
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if plot:
            _plot_classifier_sweep_outputs(
                results,
                feature_stats,
                figures_dir,
                scoring=scoring,
                class_count=len(class_labels),
                dpi=int(dpi),
            )
        _write_classifier_sweep_readme(
            outdir,
            work_df.assign(**{target: target_text.to_numpy()}),
            target,
            predictors,
            configs,
            results,
            permutation_df,
            class_labels,
            max_features_i,
            cv,
            strategy,
            model_preset,
            scoring,
        )

    if verbose:
        score_col = "log_loss" if str(scoring).strip() in {"log_loss", "loss"} else str(scoring).strip()
        if score_col not in top_row.index:
            score_col = "balanced_accuracy"
        _log.confirm(
            "[iterative_model_sweep] Best: "
            f"{top_row['family']} / {top_row['model_config']} | "
            f"{score_col}={float(top_row[score_col]):.4g} | "
            f"features: {' + '.join(best_features)}"
        )
        if save:
            _log.confirm(f"[iterative_model_sweep] Saved outputs to {outdir}")

    result = {
        "best_family": str(top_row["family"]),
        "best_model": str(top_row["model_config"]),
        "best_features": tuple(best_features),
        "best_score": float(top_row[
            "log_loss" if str(scoring).strip() in {"log_loss", "loss"} and "log_loss" in top_row.index
            else scoring if str(scoring).strip() in top_row.index
            else "balanced_accuracy"
        ]),
        "best_metrics": {
            key: float(top_row[key])
            for key in ["accuracy", "balanced_accuracy", "macro_f1", "macro_ovr_auc", "log_loss"]
            if key in top_row.index and pd.notna(top_row[key])
        },
        "best_estimator": best_estimator,
        "class_labels": class_labels,
        "class_to_code": class_to_code,
        "feature_type_map": type_map,
        "predictors": predictors,
        "removed_empty_features": removed_empty_features,
        "all_model_scores": results,
        "top_feature_recurrence": feature_stats,
        "top_model_predictions": predictions,
        "top_model_permutation_test": permutation_df,
        "output_dir": str(outdir) if save else None,
        "stats_dir": str(stats_dir) if save else None,
        "figures_dir": str(figures_dir) if save else None,
        "search_strategy": strategy,
        "cv": cv,
        "scoring": scoring,
        "model_preset": model_preset,
        "fast_numeric": bool(fast_numeric),
        "n_jobs": int(n_jobs),
        "parallel_backend": str(parallel_backend),
        "parallel_batch_size": int(parallel_batch_size),
    }
    if return_details:
        return result
    return str(top_row["model_config"]), tuple(best_features)
