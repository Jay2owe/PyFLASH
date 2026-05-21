"""
Model selection utilities.

Currently includes iterative_best_fit for leave-one-out cross-validated
iterative feature-subset search using linear regression (statsmodels OLS).
"""

from __future__ import annotations

import itertools
import os
import re
import time
from typing import Iterable

import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm
from matplotlib import pyplot as plt

from PyFLASH._logging import logger as _log
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
    """Mask sentinel-like tokens including common misspellings."""
    s = pd.Series(series)
    pat = r"(?:NOT_INCLUDED|NOT_INLCUDED)"
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
        if pd.api.types.is_categorical_dtype(out[col]):
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
    combos = []
    for k in range(1, int(max_features) + 1):
        for combo in itertools.combinations(predictors, k):
            prefixes = [_safe_predictor_prefix(c) for c in combo]
            if repeat_features or len(prefixes) == len(set(prefixes)):
                combos.append(combo)
    return combos


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
    normalize_method: str = "minmax",
    excluded_predictors: Iterable[str] | None = None,
    hue_column: str = "Condition",
    palette: dict | None = None,
    save: bool = True,
    dpi: int = 600,
    plot: bool = True,
    verbose: bool = True,
    return_details: bool = False,
    specificity=None,
    exclude=None,
    cv_group_column: str | None = "AnimalName",
    cv_backend: str = "fast",
    plot_insights: bool = True,
    top_n_single_predictors: int = 3,
    search_strategy: str = "exhaustive",
    beam_width: int = 100,
    batch_chunk_size: int = 5000,
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
                s=70,
                palette=palette,
            )
        else:
            sns.scatterplot(
                data=scatter_df,
                x="Predicted",
                y="Actual",
                ax=ax,
                s=70,
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
