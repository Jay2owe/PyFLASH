"""
Plotting action functions and one-liner wrappers.

Each action function follows the contract:
    def action(ctx: Context, state: dict, **kwargs) -> dict | None

One-liners compose: run() + setup + action + teardown.

Usage:
    # One-liner
    plot_mean_bars(batch1, filtered_cols, specificity=('Time', 'WeekEight'))

    # Or use the action directly in a custom pipeline
    from PyFLASH.plotting import bar_chart_action
    run(batch, over=['columns', 'conditions'], action=bar_chart_action,
        columns=cols, points=True, normalize=True)
"""

import os
import csv
import time
import re
import shutil
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Mapping
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.colors import to_rgb as mpl_to_rgb
from matplotlib.ticker import LinearLocator

from PyFLASH.iteration import Context, run
from PyFLASH.config import Config, apply_matplotlib_fast_path
apply_matplotlib_fast_path()  # apply path-simplify rcParams + ioff() once, lazily
from PyFLASH._logging import logger as _log
from PyFLASH.experiment import _source_panel_order_rows
from PyFLASH.image_io import read_image_array, resolve_image_worker_count, get_image_shape
from PyFLASH.markers import stainColors
from PyFLASH.stats import (
    multipleComparisons,
    test_normality,
    runITTest,
    mwu_multiple_comparisons,
    stats_cache_key,
)
from PyFLASH.export import convert_name, convert_raw_name, convert_behavior_name
from PyFLASH.utils import (
    save_fig, round_up_to_nearest_5, get_columns, strip_name,
    convert_microns_to_pixels, convert_pixels_to_microns,
    normalize_image_roi_name, normalize_animal_name,
    flatten_specificity_values, is_specificity_queue,
    iter_specificities, filter_df_by_specificity,
    specificity_path_parts, resolve_column_key, raw_coloc_column_aliases,
    build_subfolder, resolve_roi_bases, is_excluded_mask,
)


# ── Optional Altair dependency for interactive HTML export ───────────
try:
    import altair as alt
    _HAS_ALTAIR = True
except ImportError:
    _HAS_ALTAIR = False


# Shared default used by location plots; this aliases the global stain color map
# so external edits to `stainColors` are picked up automatically here too.
LOCATION_MARKER_COLORS = stainColors


_CORRELATION_ALIASES = {
    "p": "pearsonr",
    "pearson": "pearsonr",
    "pearsonr": "pearsonr",
    "s": "spearmanr",
    "spearman": "spearmanr",
    "spearmanr": "spearmanr",
    "k": "kendalltau",
    "kendall": "kendalltau",
    "kendalltau": "kendalltau",
}

_CORRELATION_PANDAS_METHODS = {
    "pearsonr": "pearson",
    "spearmanr": "spearman",
    "kendalltau": "kendall",
}

_CORRELATION_DISPLAY_NAMES = {
    "pearsonr": "Pearson",
    "spearmanr": "Spearman",
    "kendalltau": "Kendall",
}


def _normalize_correlation_method(method):
    """Normalize accepted correlation method aliases to scipy-style names."""
    if method is None:
        return "pearsonr"
    key = str(method).strip().lower().replace("_", "").replace("-", "").replace(" ", "")
    if key in _CORRELATION_ALIASES:
        return _CORRELATION_ALIASES[key]
    valid = '"pearsonr"/"pearson"/"p", "spearmanr"/"spearman"/"s", or "kendalltau"/"kendall"/"k"'
    raise ValueError(f"Correlation method must be {valid}; got {method!r}.")


def _correlation_pandas_method(method):
    return _CORRELATION_PANDAS_METHODS[_normalize_correlation_method(method)]


def _correlation_display_name(method):
    return _CORRELATION_DISPLAY_NAMES[_normalize_correlation_method(method)]


def _correlation_filename_label(method):
    return _correlation_display_name(method)


def _correlation_function(method):
    from scipy import stats as sp_stats

    method = _normalize_correlation_method(method)
    if method == "pearsonr":
        return sp_stats.pearsonr
    if method == "spearmanr":
        return sp_stats.spearmanr
    return sp_stats.kendalltau


def _correlation_statistic(result):
    if hasattr(result, "correlation"):
        return result.correlation
    if hasattr(result, "statistic"):
        return result.statistic
    return result[0]


def _correlation_pvalue(result):
    if hasattr(result, "pvalue"):
        return result.pvalue
    return result[1]


def _compute_correlation(x, y, method):
    """Return (coefficient, p-value) for supported correlation methods."""
    method = _normalize_correlation_method(method)
    corr_fn = _correlation_function(method)
    if method == "pearsonr":
        result = corr_fn(x, y)
    else:
        try:
            result = corr_fn(x, y, nan_policy="omit")
        except TypeError:
            result = corr_fn(x, y)
    return float(_correlation_statistic(result)), float(_correlation_pvalue(result))


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# DISPLAY NAME HELPERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _mapped_display_name(raw_label: str):
    """Resolve display label via export name maps (supports <ab>/<ab2> placeholders)."""
    for converter in (
        lambda c: convert_name(c, truncate=False),
        convert_raw_name,
        lambda c: convert_behavior_name(c, truncate=False),
    ):
        try:
            label, _ = converter(raw_label)
            return label
        except KeyError:
            continue
    return None


_EXACT_DISPLAY_NAME_MAP = {
    # Cleaned MiniExperiment/human actigraphy columns. These are not ImageJ
    # marker metrics, so they must bypass generic ROI/count/volume rewrites.
    "sleeptreatment": "Sleep treatment",
    "Volumeanterior-inferiorHT": "Volume anterior-inferior HT",
    "Daysincludedintheanalysis": "Days included in the analysis",
    "Period(h)": "Period (h)",
    "Alphacounts(day)": "Alpha counts (day)",
    "Rhocounts(night)": "Rho counts (night)",
    "Totalcounts": "Total counts",
    "Avgactivityrest(L5)": "Avg activity rest (L5)",
    "Starttimerestingphase(h)": "Start time resting phase (h)",
    "Avgactivityactivephase(M10)": "Avg activity active phase (M10)",
    "Starttimeactivephase(h)": "Start time active phase (h)",
}

_IF_FALLBACK_MARKERS = (
    "_Count",
    "_CountRaw",
    "_Count%",
    "_IntDen",
    "_MeanIntDen",
    "_Volume",
    "_Surface",
    "_SAtoVolumeRatio",
    "_Area",
    "_ROI",
    "_Coloc",
    "_Contains",
    "_Any",
    "_Vol",
    "_CPC",
    "_Combo",
    "_burdenScore",
    "_fragmentationScore",
)

_IF_FALLBACK_METRIC_TOKENS = (
    "Count",
    "IntDen",
    "Volume",
    "Surface",
    "Area",
    "SAtoVolumeRatio",
)


def _exact_display_name(raw_label: str):
    return _EXACT_DISPLAY_NAME_MAP.get(str(raw_label))


def _uses_if_fallback_rewrites(raw_label: str) -> bool:
    """Return True only for structured IF/ImageJ-style metric columns."""
    label = str(raw_label)
    if "_" not in label:
        return False
    if any(token in label for token in _IF_FALLBACK_MARKERS):
        return True
    metric_tail = label.split("_", 1)[1]
    return any(token in metric_tail for token in _IF_FALLBACK_METRIC_TOKENS)


def _plain_display_name(raw_label: str, compact_per=False) -> str:
    out = str(raw_label).replace("_", " ").strip()
    if compact_per:
        out = re.sub(r"\s+per\s+", " / ", out)
    return out


def _minimalize_label(label: str) -> str:
    out = str(label)
    out = out.replace("(A.U.)", "")
    out = out.replace("ROI%Area", "%Area").replace("ROI %Area", "%Area")
    out = re.sub(r"\s*\((?:um\^?\d+|Âµm|µm|px|counts|hours|g|us)\)", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return re.sub(r"\s*Mean\s*$", "", out).strip()

def get_display_name(name, minimal=False, compact_per=False):
    """Convert a raw column name to a human-readable label."""
    raw_label = str(name)
    # Hide experiment suffixes in display labels only (save names remain unchanged).
    clean_label = re.sub(r"\.exp\d+$", "", raw_label)

    # Keep AOE as the short code in plots/axes.
    if clean_label.strip().casefold() == "aoe":
        return "AOE"

    exact = _exact_display_name(clean_label)
    if exact is not None:
        return _minimalize_label(exact) if minimal else exact

    # Prefer the export mapping logic first to keep naming consistent across modules.
    mapped = _mapped_display_name(clean_label)
    if mapped is not None:
        out = _minimalize_label(mapped) if minimal else mapped
        if out.strip().casefold() == "activity onset error":
            out = "AOE"
        if compact_per:
            out = re.sub(r"\s+per\s+", " / ", out)
        return out

    label = clean_label
    label = label.replace("LocomotoractivityIR(counts)", "LMA")
    if not _uses_if_fallback_rewrites(label):
        return _plain_display_name(label, compact_per=compact_per)

    # Matrix-friendly naming (minimal mode) without changing bar-plot labels.
    if minimal:
        marker = None
        metric = label
        if "_" in label:
            marker, metric = label.split("_", 1)
        metric = metric.replace("MeanIntDenMean", "Mean Pixel IntDen")
        metric = metric.replace("IntDenMean", "Mean IntDen")
        metric = metric.replace("IntDenTotal", "Total IntDen")
        metric = metric.replace("(A.U.)", "")
        metric = metric.replace("ROI%Area", "%Area").replace("ROI %Area", "%Area")
        metric = metric.replace("_", " ").strip()
        metric = re.sub(r"\s+", " ", metric)
        metric = re.sub(r"\s*Mean\s*$", "", metric).strip()
        if marker is not None and marker != "":
            return f"{marker} {metric}".strip()
        return metric
    raw_for_units = clean_label
    is_per_mm3 = (
        any(tok in raw_for_units for tok in ["Count", "IntDen", "Surface", "Volume"])
        and "Mean" not in raw_for_units
        and "%" not in raw_for_units
        and "Ratio" not in raw_for_units
    )
    replacements = [
        ('DistToClosest', 'Distance To Closest'),
        ('MeanIntDenMean', 'IntDen / Pixel' if not minimal else 'IntDen'),
        ('SAtoVolumeRatio', 'SA:Volume'),
        ('NonColocCount', 'Count Non-Colocalised with '),
        ('ColocCount', 'Count Colocalised with '),
        ('IntDen', 'IntDen (A.U.)'),
        ('Surface', 'SA (µm²)'),
        ('Volume', 'Volume (µm³)'),
        ('_', ' '),
    ]
    # Apply non-conflicting replacements in order
    if 'Mean' in label and 'Intensity' not in label:
        if 'MeanIntDen' not in label and 'period' not in label.lower():
            label = label.replace('Mean', ' / Obj' if 'ROI' not in label and not minimal else '')
    if 'Total' in label:
        # Keep 'Total' token for per-mm3 metrics so labels stay distinguishable.
        if not is_per_mm3:
            label = label.replace('Total', ' / ROI' if not minimal else '')
    for old, new in replacements:
        if old in label:
            label = label.replace(old, new)
    if 'Count' in label and 'Coloc' not in label:
        if is_per_mm3:
            label = label.replace('Count', 'Count')
        else:
            label = label.replace('Count', 'Count / ROI' if not minimal else 'N')
    if 'ROI %Area' in label:
        label = label.replace('ROI %Area', '%Area')
    if is_per_mm3 and (not minimal) and '/ 0.1mm³' not in label:
        label = f"{label} / 0.1mm³"
    label = re.sub(r"\s*Mean\s*$", "", label).strip()
    if compact_per:
        label = re.sub(r"\s+per\s+", " / ", label)
    return label


def set_display_name(ax, y_label=None, x_label=None, minimal=False, compact_per=False, **kwargs):
    """Set axis labels with display name conversion."""
    if y_label:
        ax.set_ylabel(get_display_name(y_label, minimal=minimal, compact_per=compact_per), **kwargs)
    if x_label:
        ax.set_xlabel(get_display_name(x_label, minimal=minimal, compact_per=compact_per), **kwargs)


# ── Interactive HTML export helpers (Altair, optional) ───────────────

def _export_html_bars(experiment, columns, specificity, save_path):
    """Export an interactive bar + strip chart as self-contained HTML."""
    if not _HAS_ALTAIR or not Config.EXPORT_HTML:
        return
    try:
        import altair as alt
        alt.data_transformers.disable_max_rows()
        charts = []
        for col in columns:
            df = experiment.summary[['AnimalName', 'Condition', col]].dropna()
            bar = alt.Chart(df).mark_bar().encode(
                x='Condition:N',
                y=alt.Y(f'{col}:Q', title=get_display_name(col)),
                color='Condition:N',
            )
            points = alt.Chart(df).mark_circle(size=40, opacity=0.6).encode(
                x='Condition:N',
                y=f'{col}:Q',
                color='Condition:N',
            )
            charts.append((bar + points).properties(title=get_display_name(col)))
        if charts:
            combined = alt.vconcat(*charts).resolve_scale(color='shared')
            html_path = os.path.join(save_path, 'interactive_bars.html')
            os.makedirs(save_path, exist_ok=True)
            combined.save(html_path, inline=True)
    except Exception:
        pass


def _export_html_histogram(experiment, marker, x_attr, specificity, save_path, by, factor):
    """Export an interactive histogram as self-contained HTML."""
    if not _HAS_ALTAIR or not Config.EXPORT_HTML:
        return
    try:
        import altair as alt
        alt.data_transformers.disable_max_rows()
        marker_key = _resolve_marker_data_key(experiment, marker)
        x = _resolve_histogram_x_column(experiment, marker_key, x_attr)
        df = experiment.data[marker_key].df[[x]].copy()
        df = df.dropna(subset=[x])
        group_col = factor if factor else 'Condition'
        if group_col not in df.columns:
            df = _enrich_df_grouping_columns(df, experiment, requested_by=group_col)
        if specificity is not None:
            df = _filter_df_by_specificity(df, specificity)
        chart = alt.Chart(df).mark_bar(opacity=0.7).encode(
            alt.X(f'{x}:Q', bin=alt.Bin(maxbins=30), title=get_display_name(x)),
            alt.Y('count():Q'),
            alt.Color(f'{group_col}:N'),
        ).properties(title=f'{get_display_name(x)} Histogram')
        html_path = os.path.join(save_path, 'interactive_histogram.html')
        os.makedirs(save_path, exist_ok=True)
        chart.save(html_path, inline=True)
    except Exception:
        pass


def _export_html_matrix(experiment, columns, specificity, save_path, by, factor, correlation):
    """Export an interactive correlation heatmap as self-contained HTML."""
    if not _HAS_ALTAIR or not Config.EXPORT_HTML:
        return
    try:
        import altair as alt
        alt.data_transformers.disable_max_rows()
        summary = experiment.summary
        if specificity is not None:
            summary = filter_df_by_specificity(summary, specificity)
        numeric = summary[columns].select_dtypes(include='number').dropna(axis=1, how='all')
        if numeric.shape[1] < 2:
            return
        corr = numeric.corr(method=_correlation_pandas_method(correlation))
        corr_long = corr.reset_index().melt(id_vars='index')
        corr_long.columns = ['Variable 1', 'Variable 2', 'Correlation']
        corr_long['Variable 1'] = corr_long['Variable 1'].map(get_display_name)
        corr_long['Variable 2'] = corr_long['Variable 2'].map(get_display_name)
        chart = alt.Chart(corr_long).mark_rect().encode(
            x=alt.X('Variable 1:N', title=None),
            y=alt.Y('Variable 2:N', title=None),
            color=alt.Color('Correlation:Q', scale=alt.Scale(scheme='redblue', domain=[-1, 1])),
            tooltip=['Variable 1', 'Variable 2', 'Correlation'],
        ).properties(title='Correlation Matrix')
        corr_label = _correlation_filename_label(correlation).lower()
        html_path = os.path.join(save_path, f'interactive_matrix_{corr_label}.html')
        os.makedirs(save_path, exist_ok=True)
        chart.save(html_path, inline=True)
    except Exception:
        pass


def _export_html_volcano(experiment, columns, specificity, save_path, control):
    """Export an interactive volcano scatter as self-contained HTML."""
    if not _HAS_ALTAIR or not Config.EXPORT_HTML:
        return
    try:
        import altair as alt
        alt.data_transformers.disable_max_rows()
        summary = experiment.summary
        if specificity is not None:
            summary = filter_df_by_specificity(summary, specificity)
        records = []
        control_rows = summary[summary['Condition'] == control]
        other_rows = summary[summary['Condition'] != control]
        for col in columns:
            if col not in summary.columns:
                continue
            ctrl_mean = control_rows[col].dropna().mean()
            other_mean = other_rows[col].dropna().mean()
            if ctrl_mean == 0 or pd.isna(ctrl_mean) or pd.isna(other_mean):
                continue
            pct_change = ((other_mean - ctrl_mean) / abs(ctrl_mean)) * 100
            from scipy.stats import ttest_ind
            stat_result = ttest_ind(
                control_rows[col].dropna(),
                other_rows[col].dropna(),
                equal_var=False,
            )
            p = stat_result.pvalue if stat_result.pvalue > 0 else 1e-300
            records.append({
                'Column': get_display_name(col),
                '% Change': pct_change,
                '-log10(p)': -np.log10(p),
            })
        if not records:
            return
        df = pd.DataFrame(records)
        chart = alt.Chart(df).mark_circle(size=60).encode(
            x=alt.X('% Change:Q', title='% Change vs Control'),
            y=alt.Y('-log10(p):Q', title='-log10(p-value)'),
            tooltip=['Column', '% Change', '-log10(p)'],
        ).properties(title=f'Volcano (vs {control})')
        html_path = os.path.join(save_path, 'interactive_volcano.html')
        os.makedirs(save_path, exist_ok=True)
        chart.save(html_path, inline=True)
    except Exception:
        pass


def _resolve_filtered_columns(experiment, filtered_columns=None,
                              column_strings=None, regex_string=None, exclude='',
                              source_df=None):
    """
    Resolve plotting columns from explicit names or inline filters.

    Priority:
        1) `filtered_columns` if provided
        2) `get_columns(experiment.summary, ...)` with inline filters
    """
    source_df = experiment.summary if source_df is None else source_df

    if filtered_columns is not None:
        resolved = []
        missing = []
        for col in filtered_columns:
            mapped = resolve_column_key(source_df, col)
            if mapped is None:
                missing.append(str(col))
                continue
            resolved.append(mapped)
        if len(missing) > 0:
            missing_preview = ", ".join(missing[:5])
            raise ValueError(f"No columns matched the provided names: {missing_preview}")
    else:
        if column_strings is None and regex_string is None:
            # Default behavior: consider all summary columns.
            resolved = experiment.summary.columns.tolist()
        else:
            resolved = get_columns(
                source_df,
                column_strings=column_strings,
                regex_string=regex_string,
                exclude=exclude,
            )
    if len(resolved) == 0:
        raise ValueError("No columns matched the provided filter criteria.")
    return resolved


# Thin aliases for internal _-prefixed references
_is_specificity_queue = is_specificity_queue
_iter_specificities = iter_specificities
_flatten_specificity_values = flatten_specificity_values
_filter_df_by_specificity = filter_df_by_specificity
_specificity_path_parts = specificity_path_parts
_resolve_roi_bases = resolve_roi_bases


def _filtered_summary_for_specificity(experiment, specificity, roi_base=None):
    if roi_base is not None and hasattr(experiment, 'summaries') and roi_base in experiment.summaries:
        summary = experiment.summaries[roi_base]
    else:
        summary = experiment.summary
    return filter_df_by_specificity(summary, specificity)


def _count_level_processes(experiment, level, factor=None, specificity=None, roi_base=None):
    summary = _filtered_summary_for_specificity(experiment, specificity, roi_base=roi_base)
    if level == 'conditions':
        return len(experiment.condition_list)
    if level == 'factors':
        if factor is None or factor not in summary.columns:
            return 0
        return int(summary[factor].dropna().nunique())
    if level == 'animals':
        return int(summary['AnimalName'].dropna().nunique()) if 'AnimalName' in summary.columns else 0
    if level in ('scns', 'regions'):
        return int(summary['Region'].dropna().nunique()) if 'Region' in summary.columns else 0
    if level == 'columns':
        return int(summary.shape[1])
    return 0


def _prepare_matrix_numeric_df(
    df,
    columns,
    sentinel="NOT_INCLUDED_IN_EXPERIMENT",
    drop_duplicate_columns=True,
    require_complete_numeric=True,
):
    """
    Matrix sanitization rules:
    - sentinel values are removable per-cell missing data.
    - if require_complete_numeric=True, any remaining true NaN/non-numeric
      values invalidate that column.
    """
    keep_cols = []
    dropped_cols = []
    coerced_map = {}
    for col in columns:
        if col not in df.columns:
            dropped_cols.append(col)
            continue
        raw = df[col].copy()
        sentinel_mask = (raw.astype(str).str.contains(str(sentinel), na=False)
                         | is_excluded_mask(raw))
        raw = raw.where(~sentinel_mask, np.nan)
        coerced = pd.to_numeric(raw, errors='coerce')
        if bool(require_complete_numeric):
            invalid_mask = coerced.isna() & (~sentinel_mask)
            if invalid_mask.any():
                dropped_cols.append(col)
                continue
        if coerced.notna().sum() == 0:
            dropped_cols.append(col)
            continue
        keep_cols.append(col)
        coerced_map[col] = coerced

    out = pd.DataFrame(index=df.index)
    for col in keep_cols:
        out[col] = coerced_map[col]
    # Remove exactly duplicated columns (same values row-wise, including NaN pattern).
    if bool(drop_duplicate_columns) and out.shape[1] > 1:
        dup_mask = out.T.duplicated(keep='first')
        if dup_mask.any():
            dup_cols = out.columns[dup_mask].tolist()
            dropped_cols.extend(dup_cols)
            out = out.loc[:, ~dup_mask]
            keep_cols = out.columns.tolist()
    return out, keep_cols, dropped_cols


def _coerce_series_for_corr(raw_series, sentinel="NOT_INCLUDED_IN_EXPERIMENT", allow_categorical=False):
    """
    Coerce one series for correlation with strict column validity.
    - Sentinel values are treated as removable missing entries.
    - Any remaining NaN/non-numeric invalidates the series unless categorical
      encoding is explicitly allowed.
    """
    s = raw_series.copy()
    # Match plot_matrices semantics: sentinel and EXCLUDED_OUTLIER values are
    # removable and should not invalidate the whole column.
    drop_mask = (s.astype(str) == sentinel) | is_excluded_mask(s)
    non_sentinel = s[~drop_mask]
    numeric_non_sentinel = pd.to_numeric(non_sentinel, errors='coerce')
    if len(numeric_non_sentinel) > 0 and not numeric_non_sentinel.isna().any():
        out = s.where(~drop_mask, np.nan)
        out = pd.to_numeric(out, errors='coerce')
        return out, False
    if not allow_categorical:
        return None, False
    # Categorical fallback for factor-like x columns.
    cat_source = s.where(~drop_mask, np.nan)
    cat = pd.Categorical(cat_source)
    codes = pd.Series(cat.codes, index=s.index, dtype=float).replace(-1, np.nan)
    # For categorical X, keep plot_matrices-like strictness on true missing:
    # if there are NaNs beyond sentinel removals, treat as invalid.
    if codes.notna().sum() == 0:
        return None, False
    return codes, True


def _prepare_rect_numeric_df(df, y_columns, x_columns,
                             sentinel="NOT_INCLUDED_IN_EXPERIMENT",
                             encode_x_categorical=False):
    """
    Prepare numeric-only rectangular matrix inputs.
    Returns:
        numeric_df, valid_y, valid_x, dropped_y, dropped_x, x_was_categorical
    """
    out = pd.DataFrame(index=df.index)
    valid_y, valid_x = [], []
    dropped_y, dropped_x = [], []
    x_was_categorical = {}

    for col in y_columns:
        if col not in df.columns:
            dropped_y.append(col)
            continue
        coerced, _ = _coerce_series_for_corr(
            df[col], sentinel=sentinel, allow_categorical=False
        )
        if coerced is None or len(coerced.dropna()) == 0:
            dropped_y.append(col)
            continue
        out[col] = coerced
        valid_y.append(col)

    for col in x_columns:
        if col not in df.columns:
            dropped_x.append(col)
            continue
        coerced, as_cat = _coerce_series_for_corr(
            df[col], sentinel=sentinel, allow_categorical=encode_x_categorical
        )
        if coerced is None or len(coerced.dropna()) == 0:
            dropped_x.append(col)
            continue
        out[col] = coerced
        valid_x.append(col)
        x_was_categorical[col] = bool(as_cat)

    return out, valid_y, valid_x, dropped_y, dropped_x, x_was_categorical


def _specificity_path_parts(specificity):
    if specificity is None:
        return []
    if not isinstance(specificity, (list, tuple)) or len(specificity) < 2:
        return []
    spec_key, *raw_vals = specificity
    spec_vals = _flatten_specificity_values(raw_vals)
    parts = [strip_name(str(spec_key))]
    if len(spec_vals) == 1:
        parts.append(strip_name(str(spec_vals[0])))
    elif len(spec_vals) > 1:
        combined = " and ".join([str(v) for v in spec_vals])
        parts.append(strip_name(combined))
    return parts


def _filter_df_by_values(df: pd.DataFrame, column: str, values):
    if column not in df.columns or values is None:
        return df
    requested = _flatten_specificity_values([values])
    requested = [v for v in requested if not (isinstance(v, float) and np.isnan(v))]
    if len(requested) == 0:
        return df

    col = df[column]
    if pd.api.types.is_object_dtype(col) or pd.api.types.is_string_dtype(col) or pd.api.types.is_categorical_dtype(col):
        norm_col = col.astype(str).str.strip().str.casefold()
        norm_vals = {str(v).strip().casefold() for v in requested}
        return df[norm_col.isin(norm_vals)]
    return df[col.isin(requested)]


def _filter_df_by_string_match(df: pd.DataFrame, column: str, patterns):
    if column not in df.columns or patterns is None:
        return df
    requested = _flatten_specificity_values([patterns])
    requested = [str(v).strip() for v in requested if str(v).strip() != ""]
    if len(requested) == 0:
        return df

    norm_col = df[column].fillna("").astype(str).str.casefold()
    mask = pd.Series(False, index=df.index)
    for pattern in requested:
        mask = mask | norm_col.str.contains(re.escape(pattern.casefold()), regex=True, na=False)
    return df[mask]


def _requested_image_markers(markers):
    requested = [
        str(marker).strip()
        for marker in _flatten_specificity_values([markers])
        if str(marker).strip() != ""
    ]
    deduped = []
    seen = set()
    for marker in requested:
        key = marker.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(marker)
    return deduped


def _image_marker_panel_label(markers, merge_label="Merge"):
    cleaned = []
    seen = set()
    for marker in markers or []:
        text = str(marker).strip()
        if text == "":
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    if len(cleaned) == 0:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return _image_merge_marker_label(cleaned, merge_label=merge_label)


def _resolve_image_marker_panels(image_df: pd.DataFrame, markers=None, merge=False, merge_label="Merge"):
    if not isinstance(image_df, pd.DataFrame) or "Marker" not in image_df.columns:
        return [], []

    available_markers = [
        str(marker).strip()
        for marker in image_df["Marker"].dropna().astype(str).tolist()
        if str(marker).strip() != ""
    ]
    if len(available_markers) == 0:
        return [], []

    available_in_order = list(dict.fromkeys(available_markers))
    available_map = {marker.casefold(): marker for marker in available_in_order}

    if markers is None:
        requested_groups = [[marker] for marker in available_in_order]
    else:
        requested_groups = _normalize_location_marker_panels(markers)

    panels = []
    flat_markers = []
    flat_seen = set()
    for group in requested_groups:
        resolved = []
        seen = set()
        for marker in group:
            resolved_marker = available_map.get(str(marker).strip().casefold())
            if resolved_marker is None:
                continue
            key = str(resolved_marker).casefold()
            if key in seen:
                continue
            seen.add(key)
            resolved.append(str(resolved_marker))
            if key not in flat_seen:
                flat_seen.add(key)
                flat_markers.append(str(resolved_marker))
        if len(resolved) == 0:
            continue
        panels.append({
            "markers": resolved,
            "label": _image_marker_panel_label(resolved, merge_label=merge_label),
            "key": _location_marker_panel_key(resolved),
            "is_merge": len(resolved) > 1,
        })

    if bool(merge) and len(flat_markers) > 1:
        merged_key = _location_marker_panel_key(flat_markers)
        if all(panel.get("key") != merged_key for panel in panels):
            panels.append({
                "markers": list(flat_markers),
                "label": _image_marker_panel_label(flat_markers, merge_label=merge_label),
                "key": merged_key,
                "is_merge": True,
            })

    return panels, flat_markers


def _image_panel_markers(panel):
    if isinstance(panel, dict):
        return [str(marker) for marker in panel.get("markers", []) if str(marker).strip() != ""]
    return _location_panel_markers(panel)


def _image_panel_key(panel):
    if isinstance(panel, dict):
        key = panel.get("key", None)
        if isinstance(key, tuple):
            return key
        return _location_marker_panel_key(panel.get("markers", []))
    return _location_panel_key(panel)


def _image_draw_roi_key_set(draw_rois, image_panels):
    if draw_rois in (None, False):
        return set()
    if draw_rois is True:
        return {_image_panel_key(panel) for panel in image_panels or []}
    out = set()
    for group in _normalize_location_marker_panels(draw_rois):
        out.add(_location_marker_panel_key(group))
    return out


def _resolve_image_panel_for_tile(image_panels, row, *, col_index=None):
    if not isinstance(image_panels, (list, tuple)) or len(image_panels) == 0:
        return None
    if len(image_panels) == 1:
        return image_panels[0]

    try:
        col = int(col_index) if col_index is not None else None
    except Exception:
        col = None
    if col is not None and 0 <= col < len(image_panels):
        return image_panels[col]

    if isinstance(row, Mapping):
        merge_markers = row.get("__merge_marker_names__", None)
        if isinstance(merge_markers, (list, tuple, set, np.ndarray, pd.Series, pd.Index)):
            merge_key = _location_marker_panel_key(merge_markers)
            for panel in image_panels:
                if _image_panel_key(panel) == merge_key:
                    return panel

        marker_name = str(row.get("Marker", "")).strip()
        if marker_name != "":
            marker_key = marker_name.casefold()
            for panel in image_panels:
                panel_markers = [str(m).strip().casefold() for m in _image_panel_markers(panel)]
                if len(panel_markers) == 1 and panel_markers[0] == marker_key:
                    return panel
            for panel in image_panels:
                panel_markers = [str(m).strip().casefold() for m in _image_panel_markers(panel)]
                if marker_key in panel_markers:
                    return panel

    return image_panels[0]


def _filter_images_to_marker_coherent_experiments(df: pd.DataFrame, markers):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    requested = _requested_image_markers(markers)
    if len(requested) <= 1 or "Experiment" not in df.columns or "Marker" not in df.columns:
        return df

    requested_norm = {marker.casefold() for marker in requested}
    if len(requested_norm) <= 1:
        return df

    keep_experiments = []
    for experiment_name, exp_df in df.groupby("Experiment", sort=False, dropna=False):
        available = {
            str(marker).strip().casefold()
            for marker in exp_df["Marker"].dropna().astype(str)
            if str(marker).strip() != ""
        }
        if requested_norm.issubset(available):
            keep_experiments.append(experiment_name)

    if len(keep_experiments) == 0:
        return df.iloc[0:0].copy()
    return df[df["Experiment"].isin(keep_experiments)].copy()


def _image_descriptor(values, max_items=3) -> str:
    cleaned = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text == "":
            continue
        if text not in cleaned:
            cleaned.append(text)
    if len(cleaned) == 0:
        return ""
    if len(cleaned) <= max_items:
        return "__".join([strip_name(v) for v in cleaned])
    return f"{strip_name(cleaned[0])}_and_{len(cleaned) - 1}_more"


def _image_tile_label(row) -> str:
    if bool(row.get("__is_merged__", False)):
        marker_label = str(row.get("__merge_marker_label__", "")).strip()
        if marker_label != "":
            return marker_label

    marker = str(row.get("Marker", "")).strip()
    image_name = str(row.get("ImageName", "")).strip()

    if marker != "":
        return marker
    if image_name != "":
        return image_name
    return ""


def _image_row_label(row) -> str:
    animal_name = str(row.get("AnimalName", "")).strip()
    roi = str(row.get("ROI", "")).strip()
    parts = []
    if animal_name != "":
        parts.append(animal_name)
    if roi != "":
        parts.append(roi)
    return "\n".join(parts)


def _image_row_group_label(row_slice, combine_rois=False) -> str:
    rows = [row for row in row_slice if row is not None]
    if len(rows) == 0:
        return ""

    animals = []
    rois = []
    for row in rows:
        animal_name = str(row.get("AnimalName", "")).strip()
        roi_name = str(row.get("ROI", "")).strip()
        if animal_name != "" and animal_name not in animals:
            animals.append(animal_name)
        if roi_name != "" and roi_name not in rois:
            rois.append(roi_name)

    if bool(combine_rois) and len(animals) == 1:
        if len(rois) == 0:
            return animals[0]
        return f"{animals[0]}\n{', '.join(rois)}"

    labels = []
    for row in rows:
        label = _image_row_label(row)
        if label != "" and label not in labels:
            labels.append(label)
    return labels[0] if len(labels) == 1 else ""


def _scale_bar_reference_row(row):
    if bool(row.get("__is_merged__", False)):
        merge_rows = row.get("__merge_rows__", [])
        if isinstance(merge_rows, list):
            for merge_row in merge_rows:
                if merge_row is not None:
                    return merge_row
    return row


def _normalize_scale_bar_location(location) -> str:
    value = str(location).strip().casefold().replace("-", " ").replace("_", " ")
    aliases = {
        "bottom left": "bottom left",
        "lower left": "bottom left",
        "left": "bottom left",
        "bottom right": "bottom right",
        "lower right": "bottom right",
        "right": "bottom right",
    }
    if value not in aliases:
        raise ValueError("scale_bar_location must be 'bottom left' or 'bottom right'.")
    return aliases[value]


def _resolve_image_width_microns(row, tile, image_width_microns=None, pixel_size=None):
    if image_width_microns is not None:
        return float(image_width_microns)

    ref_row = _scale_bar_reference_row(row)
    source_path = str(ref_row.get("ImagePath", "")).strip()
    width_px = None
    if source_path != "" and os.path.exists(source_path):
        try:
            _, width_px = get_image_shape(source_path)
        except Exception:
            width_px = None
    if width_px is None and tile is not None and getattr(tile, "ndim", 0) >= 2:
        width_px = int(tile.shape[1])
    if width_px is None:
        return None
    return float(convert_pixels_to_microns(width_px, pixel_size=pixel_size))


def _nice_scale_bar_length_microns(image_width_microns, target_fraction=0.2):
    total = float(image_width_microns)
    if not np.isfinite(total) or total <= 0:
        return None
    target = max(total * float(target_fraction), 1e-9)
    exponent = np.floor(np.log10(target))
    candidates = []
    for exp in [exponent - 1, exponent, exponent + 1]:
        for base in [1, 2, 5]:
            value = base * (10 ** exp)
            if value <= total:
                candidates.append(float(value))
    if len(candidates) == 0:
        return float(target)
    viable = [value for value in candidates if value <= target]
    if len(viable) > 0:
        return float(max(viable))
    return float(min(candidates))


def _format_scale_bar_microns(value):
    value_f = float(value)
    if abs(value_f - round(value_f)) < 0.05:
        return f"{int(round(value_f))} µm"
    return f"{value_f:.1f} µm"


def _resolve_scale_bar_fraction_and_label(row, tile,
                                          scale_bar_size=None,
                                          scale_bar_units="microns",
                                          image_width_microns=None,
                                          pixel_size=None):
    unit = str(scale_bar_units).strip().casefold().replace("_", " ")
    if unit in {"micron", "microns", "um", "µm"}:
        unit = "microns"
    elif unit in {"percent", "percentage", "%"}:
        unit = "percent"
    elif unit in {"fraction", "ratio"}:
        unit = "fraction"
    else:
        raise ValueError("scale_bar_units must be 'microns', 'percent', or 'fraction'.")

    total_width_microns = _resolve_image_width_microns(
        row,
        tile,
        image_width_microns=image_width_microns,
        pixel_size=pixel_size,
    )

    if unit == "microns":
        if scale_bar_size is None:
            if total_width_microns is None:
                raise ValueError("A physical image width is required to auto-size the scale bar.")
            scale_microns = _nice_scale_bar_length_microns(total_width_microns)
        else:
            scale_microns = float(scale_bar_size)
        if scale_microns <= 0:
            raise ValueError("scale_bar_size must be greater than zero.")
        if total_width_microns is None or total_width_microns <= 0:
            raise ValueError("A physical image width is required for micron scale bars.")
        fraction = float(scale_microns) / float(total_width_microns)
        label = _format_scale_bar_microns(scale_microns)
        return fraction, label

    if scale_bar_size is None:
        fraction = 0.2
    else:
        fraction = float(scale_bar_size)
        if unit == "percent":
            fraction = fraction / 100.0
    if fraction <= 0 or fraction >= 1:
        raise ValueError("scale bar fraction must be between 0 and 1.")

    if total_width_microns is not None and total_width_microns > 0:
        label = _format_scale_bar_microns(total_width_microns * fraction)
    elif unit == "percent":
        label = f"{fraction * 100:.0f}%"
    else:
        label = f"{fraction:.2f}x"
    return fraction, label


def _draw_scale_bar(ax, row, tile,
                    scale_bar=False,
                    scale_bar_location="bottom left",
                    scale_bar_size=None,
                    scale_bar_units="microns",
                    image_width_microns=None,
                    pixel_size=None,
                    scale_bar_color="white",
                    scale_bar_linewidth=4.0):
    if not scale_bar:
        return
    fraction, label = _resolve_scale_bar_fraction_and_label(
        row,
        tile,
        scale_bar_size=scale_bar_size,
        scale_bar_units=scale_bar_units,
        image_width_microns=image_width_microns,
        pixel_size=pixel_size,
    )
    location = _normalize_scale_bar_location(scale_bar_location)

    x_margin = 0.05
    y_bar = 0.08
    text_y = 0.115
    if location == "bottom right":
        x1 = 1.0 - x_margin
        x0 = x1 - fraction
    else:
        x0 = x_margin
        x1 = x0 + fraction

    if x0 < 0.0 or x1 > 1.0:
        raise ValueError("The requested scale bar is wider than the image.")

    ax.plot(
        [x0, x1],
        [y_bar, y_bar],
        transform=ax.transAxes,
        color=str(scale_bar_color),
        linewidth=float(scale_bar_linewidth),
        solid_capstyle="butt",
        clip_on=False,
        zorder=6,
    )
    ax.text(
        (x0 + x1) * 0.5,
        text_y,
        label,
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        color=str(scale_bar_color),
        fontsize=11,
        fontweight="bold",
        zorder=6,
    )


def _image_figure_title(image_df: pd.DataFrame, title=None) -> str:
    if title is not None:
        return str(title)

    parts = []
    markers = image_df["Marker"].dropna().astype(str).unique().tolist() if "Marker" in image_df.columns else []
    if len(markers) == 1:
        parts.append(markers[0])
    elif len(markers) > 1:
        parts.append(f"{len(markers)} markers")

    rois = image_df["ROI"].replace("", np.nan).dropna().astype(str).unique().tolist() if "ROI" in image_df.columns else []
    if len(rois) == 1:
        parts.append(rois[0])
    elif len(rois) > 1:
        parts.append(f"{len(rois)} ROIs")

    if len(parts) == 0:
        return "Image tiles"
    return " | ".join(parts)


def _image_save_name(image_df: pd.DataFrame) -> str:
    parts = []
    if "Condition" in image_df.columns:
        conds = image_df["Condition"].dropna().astype(str).unique().tolist()
        if len(conds) == 1:
            parts.append(conds[0])
    elif "AnimalName" in image_df.columns:
        animals = image_df["AnimalName"].dropna().astype(str).unique().tolist()
        if len(animals) == 1:
            parts.append(animals[0])

    markers = image_df["Marker"].dropna().astype(str).unique().tolist() if "Marker" in image_df.columns else []
    marker_desc = _image_descriptor(markers, max_items=2)
    if marker_desc != "":
        parts.append(marker_desc)

    rois = image_df["ROI"].replace("", np.nan).dropna().astype(str).unique().tolist() if "ROI" in image_df.columns else []
    roi_desc = _image_descriptor(rois, max_items=2)
    if roi_desc != "":
        parts.append(roi_desc)

    parts.append("tiles")
    cleaned = [strip_name(str(part)).strip() for part in parts if str(part).strip() != ""]
    return " ".join(cleaned)


REPRESENTATIVE_IMAGE_COLUMNS = [
    "SelectionGroup",
    "Condition",
    "Experiment",
    "AnimalName",
    "ROI",
    "RepresentativeMarkers",
    "RepresentativeMarkerKey",
    "SelectedAt",
]


def _empty_representative_image_table() -> pd.DataFrame:
    return pd.DataFrame(columns=REPRESENTATIVE_IMAGE_COLUMNS)


def _representative_marker_list(markers=None, marker_text=None) -> list[str]:
    if markers is not None:
        if isinstance(markers, str) and "|" in markers:
            raw = [part.strip() for part in str(markers).split("|")]
        else:
            raw = [
                str(marker).strip()
                for marker in _flatten_specificity_values([markers])
                if str(marker).strip() != ""
            ]
    elif marker_text is not None:
        raw = [part.strip() for part in str(marker_text).split("|")]
    else:
        raw = []

    cleaned = []
    seen = set()
    for marker in raw:
        marker_s = str(marker).strip()
        if marker_s == "":
            continue
        key = marker_s.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(marker_s)
    return cleaned


def _representative_marker_signature(markers=None, marker_text=None):
    marker_list = _representative_marker_list(markers=markers, marker_text=marker_text)
    marker_display = " | ".join(marker_list)
    marker_key = "|".join(sorted({marker.casefold() for marker in marker_list}))
    return marker_list, marker_display, marker_key


def _representative_marker_key(record) -> str:
    stored_key = str(record.get("RepresentativeMarkerKey", "")).strip()
    if stored_key != "":
        return stored_key
    _, _, inferred_key = _representative_marker_signature(marker_text=record.get("RepresentativeMarkers", ""))
    return inferred_key


def _representative_marker_keys(table) -> list[str]:
    if not isinstance(table, pd.DataFrame) or table.empty or "RepresentativeMarkerKey" not in table.columns:
        return []
    keys = [
        str(value).strip()
        for value in table["RepresentativeMarkerKey"].fillna("").astype(str).tolist()
        if str(value).strip() != ""
    ]
    return list(dict.fromkeys(keys))


def _normalize_representative_image_table(table) -> pd.DataFrame:
    if not isinstance(table, pd.DataFrame) or table.empty:
        return _empty_representative_image_table()
    out = table.copy()
    for col in REPRESENTATIVE_IMAGE_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[REPRESENTATIVE_IMAGE_COLUMNS].copy()
    for col in ["SelectionGroup", "Condition", "Experiment", "AnimalName", "ROI", "RepresentativeMarkers", "RepresentativeMarkerKey", "SelectedAt"]:
        out[col] = out[col].fillna("").astype(str)

    marker_displays = []
    marker_keys = []
    for marker_text, marker_key in zip(
        out["RepresentativeMarkers"].tolist(),
        out["RepresentativeMarkerKey"].tolist(),
    ):
        if str(marker_key).strip() != "":
            marker_list = _representative_marker_list(marker_text=marker_text)
            marker_display = " | ".join(marker_list) if len(marker_list) > 0 else str(marker_text).strip()
            normalized_key = str(marker_key).strip()
        else:
            _, marker_display, normalized_key = _representative_marker_signature(marker_text=marker_text)
        marker_displays.append(marker_display)
        marker_keys.append(normalized_key)
    out["RepresentativeMarkers"] = marker_displays
    out["RepresentativeMarkerKey"] = marker_keys

    out = out.drop_duplicates(
        subset=["Experiment", "Condition", "AnimalName", "ROI", "RepresentativeMarkerKey"],
        keep="last",
    )
    return out.reset_index(drop=True)


def _get_representative_image_table(source) -> pd.DataFrame:
    return _normalize_representative_image_table(getattr(source, "representative_images", None))


def _representative_selection_key(record) -> tuple:
    return tuple(str(record.get(col, "")).strip() for col in ["Experiment", "Condition", "AnimalName", "ROI"]) + (_representative_marker_key(record),)


def _representative_block_key_from_record(record, block_key_cols) -> tuple:
    return tuple(str(record.get(col, "")).strip() for col in block_key_cols)


def _representative_state_save_path(source):
    state_path = getattr(source, "_state_path", None)
    if isinstance(state_path, str) and state_path.strip() != "":
        return state_path
    csv_path = getattr(source, "csv_path", None)
    name = getattr(source, "name", None)
    if isinstance(csv_path, str) and csv_path.strip() != "" and isinstance(name, str) and name.strip() != "":
        return os.path.join(csv_path, f"{name}.pkl")
    return None


def _save_representative_source(source, verbose=False):
    from PyFLASH.serialization import save_state

    state_path = _representative_state_save_path(source)
    if state_path is None:
        return None
    save_state(source, state_path, verbose=verbose)
    return state_path


SAVED_IMAGE_EDIT_COLUMNS = [
    "AnimalFilter",
    "AnimalFilterKey",
    "Marker",
    "Brightness",
    "Contrast",
    "UpdatedAt",
]


def _empty_saved_image_edit_table() -> pd.DataFrame:
    return pd.DataFrame(columns=SAVED_IMAGE_EDIT_COLUMNS)


def _normalize_saved_image_edit_table(table) -> pd.DataFrame:
    if not isinstance(table, pd.DataFrame) or table.empty:
        return _empty_saved_image_edit_table()
    out = table.copy()
    for col in SAVED_IMAGE_EDIT_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[SAVED_IMAGE_EDIT_COLUMNS].copy()
    for col in ["AnimalFilter", "AnimalFilterKey", "Marker", "UpdatedAt"]:
        out[col] = out[col].fillna("").astype(str)
    out["Brightness"] = pd.to_numeric(out["Brightness"], errors="coerce").fillna(1.0).astype(float)
    out["Contrast"] = pd.to_numeric(out["Contrast"], errors="coerce").fillna(1.0).astype(float)
    out["Marker"] = out["Marker"].astype(str).str.strip()
    out["AnimalFilter"] = out["AnimalFilter"].astype(str).str.strip()
    out["AnimalFilterKey"] = out["AnimalFilterKey"].astype(str).str.strip()
    out = out[out["Marker"] != ""].copy()
    missing_filter_key = out["AnimalFilterKey"] == ""
    out.loc[missing_filter_key, "AnimalFilterKey"] = out.loc[missing_filter_key, "AnimalFilter"].astype(str).str.casefold()
    out["__marker_key__"] = out["Marker"].astype(str).str.casefold()
    out = out.drop_duplicates(
        subset=["AnimalFilterKey", "__marker_key__"],
        keep="last",
    )
    out = out.drop(columns=["__marker_key__"], errors="ignore")
    return out.reset_index(drop=True)


def _get_saved_image_edit_table(source) -> pd.DataFrame:
    return _normalize_saved_image_edit_table(getattr(source, "saved_image_edits", None))


def _saved_image_edit_filter_signature(animal_filter=None, specificity=None):
    filter_text = ""
    if animal_filter is not None and str(animal_filter).strip() != "":
        filter_text = str(animal_filter).strip()
    elif isinstance(specificity, (list, tuple)) and len(specificity) >= 2:
        spec_key, *raw_vals = specificity
        if str(spec_key).strip().casefold() == "animalname":
            values = []
            seen = set()
            for value in _flatten_specificity_values(raw_vals):
                value_s = str(value).strip()
                if value_s == "":
                    continue
                key = value_s.casefold()
                if key in seen:
                    continue
                seen.add(key)
                values.append(value_s)
            filter_text = " | ".join(values)
    return filter_text, str(filter_text).strip().casefold()


def _saved_image_adjustments(source, marker_names=None, *, animal_filter=None, specificity=None):
    table = _get_saved_image_edit_table(source)
    if table.empty:
        return {}
    _, filter_key = _saved_image_edit_filter_signature(animal_filter=animal_filter, specificity=specificity)
    filtered = table[table["AnimalFilterKey"].astype(str) == str(filter_key)].copy()
    if filtered.empty:
        return {}

    requested_markers = _image_adjustment_marker_names(marker_names)
    if len(requested_markers) > 0:
        requested_keys = {str(marker).casefold() for marker in requested_markers}
        filtered = filtered[filtered["Marker"].astype(str).str.casefold().isin(requested_keys)].copy()
    if filtered.empty:
        return {}

    out = {}
    for _, row in filtered.iterrows():
        marker_name = str(row.get("Marker", "")).strip()
        if marker_name == "":
            continue
        out[marker_name] = {
            "brightness": float(row.get("Brightness", 1.0)),
            "contrast": float(row.get("Contrast", 1.0)),
        }
    return _normalize_image_adjustments(out, marker_names=marker_names)


def _resolve_effective_image_adjustments(source, marker_names=None, *,
                                         animal_filter=None, specificity=None,
                                         image_adjustments=None,
                                         use_existing_edits=False):
    requested_markers = _image_adjustment_marker_names(marker_names)
    base = {}
    if bool(use_existing_edits):
        base = _saved_image_adjustments(
            source,
            marker_names=requested_markers,
            animal_filter=animal_filter,
            specificity=specificity,
        )
    if image_adjustments is None:
        return _normalize_image_adjustments(base, marker_names=requested_markers)

    merged = _normalize_image_adjustments(base, marker_names=requested_markers)
    override = _normalize_image_adjustments(image_adjustments, marker_names=requested_markers)
    merged.update(override)
    return _normalize_image_adjustments(merged, marker_names=requested_markers)


def _persist_saved_image_edits(source, marker_names=None, adjustments=None, *,
                               animal_filter=None, specificity=None,
                               autosave=True):
    requested_markers = _image_adjustment_marker_names(marker_names)
    normalized = _normalize_image_adjustments(adjustments, marker_names=requested_markers)
    filter_text, filter_key = _saved_image_edit_filter_signature(
        animal_filter=animal_filter,
        specificity=specificity,
    )
    marker_keys = {str(marker).casefold() for marker in requested_markers}
    existing = _get_saved_image_edit_table(source)

    if marker_keys:
        keep_existing = existing[
            ~(
                (existing["AnimalFilterKey"].astype(str) == str(filter_key))
                & (existing["Marker"].astype(str).str.casefold().isin(marker_keys))
            )
        ].copy()
    else:
        keep_existing = existing.copy()

    timestamp = pd.Timestamp.utcnow().isoformat()
    records = []
    for entry in normalized.values():
        marker_name = str(entry.get("marker", "")).strip()
        if marker_name == "":
            continue
        brightness = float(entry.get("brightness", 1.0))
        contrast = float(entry.get("contrast", 1.0))
        if abs(brightness - 1.0) < 1e-9 and abs(contrast - 1.0) < 1e-9:
            continue
        records.append({
            "AnimalFilter": filter_text,
            "AnimalFilterKey": filter_key,
            "Marker": marker_name,
            "Brightness": brightness,
            "Contrast": contrast,
            "UpdatedAt": timestamp,
        })

    new_table = pd.DataFrame.from_records(records, columns=SAVED_IMAGE_EDIT_COLUMNS)
    if keep_existing.empty:
        merged = new_table
    elif new_table.empty:
        merged = keep_existing
    else:
        merged = pd.concat([keep_existing, new_table], ignore_index=True)
    source.saved_image_edits = _normalize_saved_image_edit_table(merged)

    if autosave:
        _save_representative_source(source, verbose=False)
    return source.saved_image_edits


def _persist_image_edits_and_return(source, fig, marker_names=None, adjustments=None, *,
                                    animal_filter=None, specificity=None,
                                    autosave=True):
    saved = _persist_saved_image_edits(
        source,
        marker_names=marker_names,
        adjustments=adjustments,
        animal_filter=animal_filter,
        specificity=specificity,
        autosave=autosave,
    )
    if fig is not None:
        try:
            fig.PyFLASH_saved_image_edits = saved
        except Exception:
            pass
    return fig


def _get_source_image_table_for_representatives(source):
    if hasattr(source, "getImageTable"):
        image_df = source.getImageTable(include_summary=True)
    else:
        image_df = getattr(source, "images", None)
        if not isinstance(image_df, pd.DataFrame) and hasattr(source, "importImages"):
            image_df = source.importImages(progress=False)
    return image_df if isinstance(image_df, pd.DataFrame) else None


def _resolve_representative_marker_order(source, representative_df=None, image_df=None, marker_order=None):
    requested = _representative_marker_list(markers=marker_order)
    if len(requested) > 0:
        return requested

    stored = _representative_marker_list(markers=getattr(source, "representative_image_markers", None))
    if len(stored) > 0:
        return stored

    rep_df = _normalize_representative_image_table(representative_df)
    rep_keys = _representative_marker_keys(rep_df)
    if len(rep_keys) == 1 and "RepresentativeMarkers" in rep_df.columns:
        return _representative_marker_list(marker_text=rep_df["RepresentativeMarkers"].iloc[0])

    if isinstance(image_df, pd.DataFrame) and "Marker" in image_df.columns:
        return _resolve_requested_image_marker_order(image_df, markers=None)
    return []


def _filter_representative_table_by_markers(source, representative_df, marker_order=None, require_specific=False):
    rep_df = _normalize_representative_image_table(representative_df)
    if rep_df.empty:
        return rep_df, []

    resolved_marker_order = _resolve_representative_marker_order(
        source,
        representative_df=rep_df,
        marker_order=marker_order,
    )
    if len(resolved_marker_order) == 0:
        marker_keys = _representative_marker_keys(rep_df)
        if require_specific and len(marker_keys) > 1:
            raise ValueError("Multiple representative marker subsets are saved. Pass markers=[...] to choose one.")
        return rep_df, resolved_marker_order

    _, marker_display, marker_key = _representative_marker_signature(markers=resolved_marker_order)
    filtered = rep_df[rep_df["RepresentativeMarkerKey"].astype(str) == marker_key].copy()
    if filtered.empty:
        raise ValueError(f"No representative images have been selected for markers: {marker_display}")
    return filtered, resolved_marker_order


def _representative_marker_dir_name(marker_order) -> str:
    markers = [strip_name(str(marker)).strip() for marker in marker_order if str(marker).strip() != ""]
    if len(markers) == 0:
        return "RepresentativeImages"
    return "__".join(markers)


def _representative_export_root(source) -> str | None:
    rep_path = getattr(source, "representative_path", None)
    if not isinstance(rep_path, str) or rep_path.strip() == "":
        if hasattr(source, "createSavePaths"):
            try:
                source.createSavePaths()
            except Exception:
                pass
        rep_path = getattr(source, "representative_path", None)

    if isinstance(rep_path, str) and rep_path.strip() != "":
        os.makedirs(rep_path, exist_ok=True)
        return rep_path
    return None


def _representative_group_owner_name(source, experiment_name) -> str:
    owner = str(experiment_name).strip()
    if owner != "":
        return owner
    return str(getattr(source, "name", "RepresentativeImages")).strip() or "RepresentativeImages"


def _representative_export_dir(source, experiment_name, marker_order) -> str:
    rep_root = _representative_export_root(source)
    if rep_root is None:
        raise ValueError("Representative export path could not be resolved.")
    owner_name = strip_name(_representative_group_owner_name(source, experiment_name))
    marker_dir = _representative_marker_dir_name(marker_order)
    export_dir = os.path.join(rep_root, owner_name, marker_dir)
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _clean_representative_image_files(export_dir):
    removable_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    if not isinstance(export_dir, str) or not os.path.isdir(export_dir):
        return
    for name in os.listdir(export_dir):
        path = os.path.join(export_dir, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].casefold()
        if ext in removable_exts:
            try:
                os.remove(path)
            except Exception:
                pass


def _representative_copied_image_stem(row) -> str:
    parts = [
        str(row.get("Marker", "")).strip(),
        str(row.get("Condition", "")).strip(),
        str(row.get("ROI", "")).strip(),
    ]
    cleaned = [strip_name(part) for part in parts if part != ""]
    if len(cleaned) == 0:
        fallback = str(row.get("ImageName", "representative_image")).strip()
        return strip_name(fallback) or "representative_image"
    return "_".join(cleaned)


def _representative_csv_sort(source, representative_df: pd.DataFrame, image_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(representative_df, pd.DataFrame) or representative_df.empty:
        return representative_df
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return representative_df.reset_index(drop=True)

    join_cols = [
        col for col in ["Experiment", "Condition", "AnimalName", "ROI"]
        if col in representative_df.columns and col in image_df.columns
    ]
    if len(join_cols) == 0:
        return representative_df.reset_index(drop=True)

    ordered_images = _order_image_rows_by_source(source, image_df)
    key_df = ordered_images[join_cols].drop_duplicates().reset_index(drop=True)
    key_df["__rep_sort_order__"] = np.arange(len(key_df), dtype=int)
    out = representative_df.merge(key_df, on=join_cols, how="left")
    out = out.sort_values(["__rep_sort_order__"], kind="stable", na_position="last")
    return out.drop(columns=["__rep_sort_order__"], errors="ignore").reset_index(drop=True)


def _export_representative_assets(source, representative_df=None, image_df=None, marker_order=None,
                                  export_dir_override=None, write_csv=True):
    rep_df = _normalize_representative_image_table(
        _get_representative_image_table(source) if representative_df is None else representative_df
    )
    if rep_df.empty:
        return []

    image_df = _get_source_image_table_for_representatives(source) if image_df is None else image_df
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return []

    rep_df, resolved_marker_order = _filter_representative_table_by_markers(
        source,
        marker_order=marker_order,
        representative_df=rep_df,
        require_specific=(marker_order is not None),
    )
    if rep_df.empty:
        return []
    filtered_df = _filter_image_df_to_representatives(image_df, rep_df)
    if len(resolved_marker_order) > 0:
        filtered_df = _filter_df_by_values(filtered_df, "Marker", resolved_marker_order)
    if filtered_df.empty:
        return []

    if "Experiment" in filtered_df.columns and filtered_df["Experiment"].fillna("").astype(str).str.strip().nunique() > 0:
        experiment_names = list(dict.fromkeys(filtered_df["Experiment"].fillna("").astype(str).tolist()))
    else:
        experiment_names = [str(getattr(source, "name", "")).strip()]

    export_dirs = []
    cleaned_dirs = set()
    for experiment_name in experiment_names:
        exp_name = str(experiment_name).strip()
        if "Experiment" in rep_df.columns:
            rep_group = rep_df[rep_df["Experiment"].fillna("").astype(str) == exp_name].copy() if exp_name != "" else rep_df.copy()
        else:
            rep_group = rep_df.copy()
        if rep_group.empty:
            continue

        if "Experiment" in filtered_df.columns:
            image_group = filtered_df[filtered_df["Experiment"].fillna("").astype(str) == exp_name].copy() if exp_name != "" else filtered_df.copy()
        else:
            image_group = filtered_df.copy()
        if image_group.empty:
            continue

        group_marker_order = _resolve_representative_marker_order(
            source,
            representative_df=rep_group,
            image_df=image_group,
            marker_order=resolved_marker_order,
        )
        if len(group_marker_order) > 0:
            image_group = _filter_df_by_values(image_group, "Marker", group_marker_order)
        if image_group.empty:
            continue

        if isinstance(export_dir_override, str) and export_dir_override.strip() != "":
            export_dir = export_dir_override
            os.makedirs(export_dir, exist_ok=True)
        else:
            export_dir = _representative_export_dir(source, exp_name, group_marker_order)
        if export_dir not in cleaned_dirs:
            _clean_representative_image_files(export_dir)
            cleaned_dirs.add(export_dir)

        copy_rows = _order_image_rows_by_source(source, image_group, marker_names=group_marker_order)
        dedup_cols = [c for c in ["Condition", "AnimalName", "ROI", "Marker"] if c in copy_rows.columns]
        if len(dedup_cols) > 0:
            copy_rows = copy_rows.drop_duplicates(subset=dedup_cols, keep="first").reset_index(drop=True)

        copied_files_by_key = {}
        used_dest_names = set()
        for _, row in copy_rows.iterrows():
            source_path = str(row.get("ImagePath", "")).strip()
            if source_path == "" or not os.path.exists(source_path):
                continue
            ext = str(row.get("Extension", "")).strip() or os.path.splitext(source_path)[1]
            ext = ext if str(ext).startswith(".") else f".{ext}"
            stem = _representative_copied_image_stem(row)
            dest_name = f"{stem}{ext}"
            suffix = 2
            while dest_name.casefold() in used_dest_names:
                dest_name = f"{stem}_{suffix}{ext}"
                suffix += 1
            used_dest_names.add(dest_name.casefold())
            dest_path = os.path.join(export_dir, dest_name)
            shutil.copy2(source_path, dest_path)

            rep_key = tuple(str(row.get(col, "")).strip() for col in ["Experiment", "Condition", "AnimalName", "ROI"])
            copied_files_by_key.setdefault(rep_key, []).append(dest_name)

        if write_csv:
            csv_df = _representative_csv_sort(source, rep_group, image_group)
            csv_df["CopiedImages"] = [
                " | ".join(copied_files_by_key.get(
                    tuple(str(row.get(col, "")).strip() for col in ["Experiment", "Condition", "AnimalName", "ROI"]),
                    []
                ))
                for _, row in csv_df.iterrows()
            ]
            csv_df = csv_df.drop(columns=["RepresentativeMarkerKey"], errors="ignore")
            csv_df.to_csv(os.path.join(export_dir, "representative_image.csv"), index=False)
        export_dirs.append(export_dir)

    return list(dict.fromkeys(export_dirs))


def _representative_figure_dir(source, image_df: pd.DataFrame, marker_order) -> str:
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return _representative_export_dir(source, getattr(source, "name", ""), marker_order)
    if "Experiment" in image_df.columns:
        experiments = list(dict.fromkeys(image_df["Experiment"].fillna("").astype(str).tolist()))
        experiments = [exp for exp in experiments if exp.strip() != ""]
    else:
        experiments = []
    owner_name = experiments[0] if len(experiments) == 1 else getattr(source, "name", "")
    return _representative_export_dir(source, owner_name, marker_order)


def _representative_filter_dir_name(filter_value) -> str | None:
    values = [
        strip_name(str(value)).strip()
        for value in _flatten_specificity_values([filter_value])
        if str(value).strip() != ""
    ]
    values = [value for value in values if value != ""]
    if len(values) == 0:
        return None
    return "__".join(dict.fromkeys(values))


def _condition_label_map(source) -> dict:
    out = {}
    for cond in getattr(source, "condition_list", []):
        out[str(getattr(cond, "name", ""))] = str(getattr(cond, "label", getattr(cond, "name", "")))
    return out


def _condition_color_map(source) -> dict:
    out = {}
    for cond in getattr(source, "condition_list", []):
        out[str(getattr(cond, "name", ""))] = str(getattr(cond, "color", "black"))
    return out


def _representative_block_key_columns(image_df: pd.DataFrame, source) -> list[str]:
    cols = []
    if "Experiment" in image_df.columns and image_df["Experiment"].dropna().astype(str).nunique() > 1:
        cols.append("Experiment")
    if "Condition" in image_df.columns and image_df["Condition"].dropna().astype(str).nunique() > 1:
        cols.append("Condition")
    if len(cols) == 0:
        if "Condition" in image_df.columns:
            cols.append("Condition")
        elif "Experiment" in image_df.columns:
            cols.append("Experiment")
    return cols


def _representative_block_label(block_key, block_key_cols, source) -> str:
    if not isinstance(block_key, tuple):
        block_key = (block_key,)
    cond_labels = _condition_label_map(source)
    parts = []
    for col, value in zip(block_key_cols, block_key):
        text = str(value).strip()
        if col == "Condition":
            text = cond_labels.get(text, text)
        if text != "" and text.lower() != "nan":
            parts.append(text)
    if len(parts) == 0:
        return str(getattr(source, "name", "Representative images"))
    return " | ".join(parts)


def _representative_block_color(block_key, block_key_cols, source) -> str:
    if not isinstance(block_key, tuple):
        block_key = (block_key,)
    cond_colors = _condition_color_map(source)
    if "Condition" in block_key_cols:
        cond_value = str(block_key[block_key_cols.index("Condition")]).strip()
        return cond_colors.get(cond_value, "black")
    return "black"


def _representative_record_from_row(row, block_label, marker_order) -> dict:
    record = {col: "" for col in REPRESENTATIVE_IMAGE_COLUMNS}
    _, marker_display, marker_key = _representative_marker_signature(markers=marker_order)
    record["SelectionGroup"] = str(block_label)
    record["Condition"] = str(row.get("Condition", "")).strip()
    record["Experiment"] = str(row.get("Experiment", "")).strip()
    record["AnimalName"] = str(row.get("AnimalName", "")).strip()
    record["ROI"] = str(row.get("ROI", "")).strip()
    record["RepresentativeMarkers"] = marker_display
    record["RepresentativeMarkerKey"] = marker_key
    record["SelectedAt"] = ""
    return record


def _apply_source_image_roi_order(source, image_df: pd.DataFrame, marker_names=None) -> pd.DataFrame:
    if (
        not isinstance(image_df, pd.DataFrame)
        or image_df.empty
        or "AnimalName" not in image_df.columns
        or "ROI" not in image_df.columns
    ):
        return image_df

    order_rows = _source_panel_order_rows(source, marker_names=marker_names)
    if order_rows.empty:
        return image_df

    merge_cols = ["__AnimalNameKey__", "__ImageROIKey__"]
    order_map = order_rows.copy()
    order_map["__AnimalNameKey__"] = order_map["AnimalName"].map(normalize_animal_name)
    order_map["__ImageROIKey__"] = order_map["ImageROI"].map(normalize_image_roi_name)

    out = image_df.copy()
    out["__AnimalNameKey__"] = out["AnimalName"].map(normalize_animal_name)
    out["__ImageROIKey__"] = out["ROI"].map(normalize_image_roi_name)

    if "Experiment" in out.columns:
        out["__ExperimentKey__"] = out["Experiment"].fillna("").astype(str).str.casefold()
        order_map["__ExperimentKey__"] = order_map["Experiment"].fillna("").astype(str).str.casefold()
        merge_cols = ["__ExperimentKey__"] + merge_cols

    order_map = order_map[merge_cols + ["__source_order__"]].drop_duplicates(
        subset=merge_cols,
        keep="first",
    )
    out = out.merge(order_map, on=merge_cols, how="left")
    out["__source_missing__"] = out["__source_order__"].isna().astype(int)
    return out


def _order_image_rows_by_source(source, image_df: pd.DataFrame, marker_names=None) -> pd.DataFrame:
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return image_df

    if marker_names is None and "Marker" in image_df.columns:
        marker_names = [
            str(value).strip()
            for value in image_df["Marker"].dropna().astype(str).tolist()
            if str(value).strip() != ""
        ]

    work_df = _apply_source_image_roi_order(source, image_df.copy(), marker_names=marker_names)
    exp_order_map = {
        str(getattr(exp, "name", "")): idx
        for idx, exp in enumerate(getattr(source, "experiment_list", []))
    }
    cond_order_map = {
        str(getattr(cond, "name", "")): idx
        for idx, cond in enumerate(getattr(source, "condition_list", []))
    }

    sort_cols = []
    if "Condition" in work_df.columns:
        work_df["__cond_order__"] = work_df["Condition"].fillna("").astype(str).map(
            lambda x: cond_order_map.get(x, len(cond_order_map))
        )
        sort_cols.extend(["__cond_order__", "Condition"])
    if "Experiment" in work_df.columns:
        work_df["__exp_order__"] = work_df["Experiment"].fillna("").astype(str).map(
            lambda x: exp_order_map.get(x, len(exp_order_map))
        )
        sort_cols.extend(["__exp_order__", "Experiment"])

    if "__source_missing__" in work_df.columns and "__source_order__" in work_df.columns:
        sort_cols.extend(["__source_missing__", "__source_order__"])

    if "ROI" in work_df.columns:
        roi_norm = work_df["ROI"].map(normalize_image_roi_name)

        def _roi_group(value):
            match = re.fullmatch(r"(LH|RH)SCN(\d*)", str(value).strip().upper())
            if match is None:
                return float("inf")
            idx = match.group(2)
            return 1 if idx in {"", "1"} else int(idx)

        def _roi_side(value):
            match = re.fullmatch(r"(LH|RH)SCN(\d*)", str(value).strip().upper())
            if match is None:
                return 99
            return 0 if match.group(1) == "LH" else 1

        work_df["__roi_group__"] = roi_norm.map(_roi_group)
        work_df["__roi_side__"] = roi_norm.map(_roi_side)
        work_df["__roi_norm__"] = roi_norm

    sort_cols.extend(
        [c for c in ["AnimalName", "__roi_group__", "__roi_side__", "__roi_norm__", "ROI", "Marker", "ImageName"] if c in work_df.columns]
    )
    sort_cols = [c for idx, c in enumerate(sort_cols) if c not in sort_cols[:idx]]
    if len(sort_cols) > 0:
        work_df = work_df.sort_values(sort_cols, kind="stable")
    return work_df.drop(
        columns=[
            "__AnimalNameKey__", "__ImageROIKey__", "__ExperimentKey__",
            "__source_order__", "__source_missing__",
        ],
        errors="ignore",
    )


def _normalize_image_gap_units(tile_gap_units) -> str:
    if tile_gap_units is None:
        return "points"
    unit = str(tile_gap_units).strip().casefold().replace("_", "-")
    aliases = {
        "point": "points",
        "points": "points",
        "pt": "points",
        "pts": "points",
        "linewidth": "points",
        "line-width": "points",
        "spine": "points",
        "spine-width": "points",
        "relative": "relative",
        "fraction": "relative",
        "ratio": "relative",
    }
    unit = aliases.get(unit, unit)
    if unit not in {"points", "relative"}:
        raise ValueError("tile_gap_units must be 'points' or 'relative'.")
    return unit


def _resolve_image_gap_layout(tile_gap, tile_gap_units, axis_width_in, axis_height_in):
    gap_value = max(0.0, float(tile_gap))
    unit = _normalize_image_gap_units(tile_gap_units)

    if unit == "points":
        gap_width_in = gap_value / 72.0
        gap_height_in = gap_value / 72.0
        wspace = gap_width_in / max(axis_width_in, 1e-9)
        hspace = gap_height_in / max(axis_height_in, 1e-9)
    else:
        wspace = gap_value
        hspace = gap_value
        gap_width_in = axis_width_in * wspace
        gap_height_in = axis_height_in * hspace

    return {
        "gap_width_in": float(gap_width_in),
        "gap_height_in": float(gap_height_in),
        "wspace": float(wspace),
        "hspace": float(hspace),
        "units": unit,
    }


def _resolve_requested_image_marker_order(image_df: pd.DataFrame, markers):
    if "Marker" not in image_df.columns:
        return []

    available_markers = [
        str(marker).strip()
        for marker in image_df["Marker"].dropna().astype(str).tolist()
        if str(marker).strip() != ""
    ]
    if len(available_markers) == 0:
        return []

    available_in_order = list(dict.fromkeys(available_markers))
    available_map = {}
    for marker in available_in_order:
        available_map.setdefault(marker.casefold(), marker)

    if markers is None:
        return available_in_order

    requested = _requested_image_markers(markers)
    if len(requested) == 0:
        return available_in_order

    ordered = []
    for marker in requested:
        resolved = available_map.get(marker.casefold())
        if resolved is not None and resolved not in ordered:
            ordered.append(resolved)

    if len(ordered) == 0:
        return available_in_order
    return ordered


def _build_image_tile_slots(work_df: pd.DataFrame, marker_order, include_merge=False, merge_label="Merge",
                            single_marker_group_by_animal=False):
    panel_specs = []
    if isinstance(marker_order, list) and len(marker_order) > 0 and isinstance(marker_order[0], dict):
        panel_specs = marker_order
    else:
        panel_specs, _ = _resolve_image_marker_panels(
            work_df,
            marker_order,
            merge=include_merge,
            merge_label=merge_label,
        )

    if (
        not isinstance(work_df, pd.DataFrame)
        or work_df.empty
        or len(panel_specs) == 0
        or "AnimalName" not in work_df.columns
        or "ROI" not in work_df.columns
        or "Marker" not in work_df.columns
    ):
        row_records = [row for _, row in work_df.iterrows()]
        return row_records, len(row_records), None

    row_key_cols = [c for c in ["Condition", "Experiment", "AnimalName", "ROI"] if c in work_df.columns]
    if len(row_key_cols) == 0:
        row_key_cols = ["AnimalName", "ROI"]

    dedup_cols = row_key_cols + ["Marker"]
    deduped = work_df.drop_duplicates(subset=dedup_cols, keep="first").reset_index(drop=True)
    if deduped.empty:
        return [], 0, None

    if bool(single_marker_group_by_animal) and len(panel_specs) == 1 and len(_image_panel_markers(panel_specs[0])) == 1:
        row_key_cols = [c for c in ["Condition", "Experiment", "AnimalName"] if c in deduped.columns]
        if len(row_key_cols) == 0:
            row_key_cols = ["AnimalName"]

        roi_order = [
            str(value).strip()
            for value in deduped["ROI"].dropna().astype(str).tolist()
            if str(value).strip() != ""
        ]
        roi_order = list(dict.fromkeys(roi_order))
        if len(roi_order) == 0:
            return [], 0, None

        row_keys = [
            tuple(row[col] for col in row_key_cols)
            for _, row in deduped[row_key_cols].drop_duplicates().iterrows()
        ]
        row_key_to_index = {row_key: idx for idx, row_key in enumerate(row_keys)}
        roi_to_col = {roi_name: idx for idx, roi_name in enumerate(roi_order)}

        nrows = len(row_keys)
        ncols = len(roi_order)
        slot_records = [None] * (nrows * ncols)
        for _, row in deduped.iterrows():
            row_key = tuple(row[col] for col in row_key_cols)
            row_index = row_key_to_index.get(row_key)
            roi_name = str(row.get("ROI", "")).strip()
            col_index = roi_to_col.get(roi_name)
            if row_index is None or col_index is None:
                continue
            slot_records[(row_index * ncols) + col_index] = row
        return slot_records, nrows, ncols

    row_keys = [tuple(row[col] for col in row_key_cols) for _, row in deduped[row_key_cols].drop_duplicates().iterrows()]
    row_key_to_index = {row_key: idx for idx, row_key in enumerate(row_keys)}

    nrows = len(row_keys)
    ncols = len(panel_specs)
    slot_records = [None] * (nrows * ncols)
    for _, group in deduped.groupby(row_key_cols, sort=False, dropna=False):
        source_rows = [row for _, row in group.iterrows()]
        if len(source_rows) == 0:
            continue
        first_row = source_rows[0]
        row_key = tuple(first_row[col] for col in row_key_cols)
        row_index = row_key_to_index.get(row_key)
        if row_index is None:
            continue

        marker_row_map = {}
        for row in source_rows:
            marker_name = str(row.get("Marker", "")).strip()
            if marker_name == "":
                continue
            marker_row_map.setdefault(marker_name.casefold(), row)

        for col_index, panel in enumerate(panel_specs):
            panel_markers = _image_panel_markers(panel)
            if len(panel_markers) == 0:
                continue
            if len(panel_markers) == 1:
                row = marker_row_map.get(str(panel_markers[0]).casefold())
                if row is not None:
                    slot_records[(row_index * ncols) + col_index] = row
                continue

            source_rows_panel = []
            missing_marker = False
            for marker_name in panel_markers:
                row = marker_row_map.get(str(marker_name).casefold())
                if row is None:
                    missing_marker = True
                    break
                source_rows_panel.append(row)
            if missing_marker or len(source_rows_panel) == 0:
                continue

            merged_record = dict(first_row)
            merged_record["Marker"] = str(panel.get("label", "")).strip() or _image_merge_marker_label(panel_markers, merge_label=merge_label)
            merged_record["ImageName"] = "merged"
            merged_record["__is_merged__"] = True
            merged_record["__merge_marker_names__"] = list(panel_markers)
            merged_record["__merge_marker_label__"] = str(panel.get("label", "")).strip() or _image_merge_marker_label(panel_markers, merge_label=merge_label)
            merged_record["__merge_rows__"] = source_rows_panel
            slot_records[(row_index * ncols) + col_index] = merged_record

    return slot_records, nrows, ncols


def _limit_image_df_for_single_preview(image_df: pd.DataFrame, marker_order=None, *, merge=False):
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return image_df

    if "Marker" not in image_df.columns:
        return image_df.iloc[:1].copy().reset_index(drop=True)

    resolved_markers = _resolve_requested_image_marker_order(image_df, marker_order)
    first_row = image_df.iloc[0]

    if bool(merge) or len(resolved_markers) > 1:
        row_key_cols = [c for c in ["Condition", "Experiment", "AnimalName", "ROI"] if c in image_df.columns]
        subset = image_df.copy()
        for col in row_key_cols:
            subset = subset[subset[col] == first_row[col]]
        if len(resolved_markers) > 0:
            subset = _filter_df_by_values(subset, "Marker", resolved_markers)
        if not subset.empty:
            return subset.reset_index(drop=True)

    return image_df.iloc[:1].copy().reset_index(drop=True)


def _order_representative_selector_rows(source, image_df: pd.DataFrame, marker_names=None) -> pd.DataFrame:
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return image_df

    if marker_names is None and "Marker" in image_df.columns:
        marker_names = [
            str(value).strip()
            for value in image_df["Marker"].dropna().astype(str).tolist()
            if str(value).strip() != ""
        ]

    work_df = _apply_source_image_roi_order(source, image_df.copy(), marker_names=marker_names)
    exp_order_map = {
        str(getattr(exp, "name", "")): idx
        for idx, exp in enumerate(getattr(source, "experiment_list", []))
    }
    cond_order_map = {
        str(getattr(cond, "name", "")): idx
        for idx, cond in enumerate(getattr(source, "condition_list", []))
    }

    sort_cols = []
    if "Experiment" in work_df.columns:
        work_df["__exp_order__"] = work_df["Experiment"].fillna("").astype(str).map(
            lambda x: exp_order_map.get(x, len(exp_order_map))
        )
        sort_cols.extend(["__exp_order__", "Experiment"])
    if "Condition" in work_df.columns:
        work_df["__cond_order__"] = work_df["Condition"].fillna("").astype(str).map(
            lambda x: cond_order_map.get(x, len(cond_order_map))
        )
        sort_cols.extend(["__cond_order__", "Condition"])

    if "__source_missing__" in work_df.columns and "__source_order__" in work_df.columns:
        sort_cols.extend(["__source_missing__", "__source_order__"])

    if "ROI" in work_df.columns:
        roi_norm = work_df["ROI"].map(normalize_image_roi_name)

        def _roi_group(value):
            match = re.fullmatch(r"(LH|RH)SCN(\d*)", str(value).strip().upper())
            if match is None:
                return float("inf")
            idx = match.group(2)
            return 1 if idx in {"", "1"} else int(idx)

        def _roi_side(value):
            match = re.fullmatch(r"(LH|RH)SCN(\d*)", str(value).strip().upper())
            if match is None:
                return 99
            return 0 if match.group(1) == "LH" else 1

        work_df["__roi_group__"] = roi_norm.map(_roi_group)
        work_df["__roi_side__"] = roi_norm.map(_roi_side)
        work_df["__roi_norm__"] = roi_norm

    sort_cols.extend(
        [c for c in ["AnimalName", "__roi_group__", "__roi_side__", "__roi_norm__", "ROI", "Marker", "ImageName"] if c in work_df.columns]
    )
    sort_cols = [c for idx, c in enumerate(sort_cols) if c not in sort_cols[:idx]]
    if len(sort_cols) > 0:
        work_df = work_df.sort_values(sort_cols, kind="stable")
    return work_df.drop(
        columns=[
            "__AnimalNameKey__", "__ImageROIKey__", "__ExperimentKey__",
            "__source_order__", "__source_missing__",
        ],
        errors="ignore",
    )


def _condition_component_for_block(cond_obj, block_by):
    block_key = str(block_by).strip().casefold()
    if block_key == "":
        return None
    if block_key == "condition":
        return cond_obj

    for sub_cond in getattr(cond_obj, "conditionsList", []):
        factor_name = str(getattr(sub_cond, "factor", "")).strip().casefold()
        if factor_name == block_key:
            return sub_cond

    factor_value = getattr(cond_obj, "factor", None)
    if isinstance(factor_value, (list, tuple)):
        return None
    if str(factor_value).strip().casefold() == block_key:
        return cond_obj
    return None


def _condition_component_attr_map(source, block_by, attr="name") -> dict:
    out = {}
    block_key = str(block_by).strip()
    if block_key == "":
        return out

    for cond in getattr(source, "condition_list", []):
        component = _condition_component_for_block(cond, block_key)
        if component is None:
            continue
        name = str(getattr(component, "name", "")).strip()
        value = str(getattr(component, attr, getattr(component, "name", ""))).strip()
        if name != "" and name not in out:
            out[name] = value
    return out


def _resolve_representative_block_series(source, image_df: pd.DataFrame, block_by):
    if not isinstance(image_df, pd.DataFrame):
        return pd.Series(dtype=str)

    block_key = str(block_by).strip()
    if block_key == "" or block_key.casefold() in {"none", "all"}:
        return pd.Series(["All"] * len(image_df), index=image_df.index, name="__rep_block__")

    if block_key in image_df.columns:
        series = image_df[block_key]
    elif block_key.casefold() == "condition" and "Condition" in image_df.columns:
        series = image_df["Condition"]
    elif "Condition" in image_df.columns:
        factor_map = _condition_component_attr_map(source, block_key, attr="name")
        if len(factor_map) == 0:
            raise ValueError(f"block_by '{block_key}' was not found in representative images.")
        series = image_df["Condition"].fillna("").astype(str).map(
            lambda x: factor_map.get(str(x).strip(), "")
        )
    else:
        raise ValueError(f"block_by '{block_key}' was not found in representative images.")

    series = series.fillna("").astype(str).map(lambda x: str(x).strip())
    if len(series) > 0 and series.eq("").all():
        raise ValueError(f"block_by '{block_key}' did not resolve to any representative groups.")
    series.name = "__rep_block__"
    return series


def _resolve_representative_block_order(source, block_by, block_values) -> list[str]:
    ordered = []
    seen = set()

    def _add(value):
        value_s = str(value).strip()
        if value_s in seen or value_s == "":
            return
        seen.add(value_s)
        ordered.append(value_s)

    available = [str(value).strip() for value in block_values if str(value).strip() != ""]
    block_key = str(block_by).strip().casefold()

    if block_key == "condition":
        for cond in getattr(source, "condition_list", []):
            _add(getattr(cond, "name", ""))
    elif block_key == "experiment":
        for exp in getattr(source, "experiment_list", []):
            _add(getattr(exp, "name", ""))
    elif block_key not in {"", "none", "all"}:
        for cond in getattr(source, "condition_list", []):
            component = _condition_component_for_block(cond, block_key)
            if component is None:
                continue
            _add(getattr(component, "name", ""))

    for value in available:
        _add(value)
    if any(str(value).strip() == "" for value in block_values):
        ordered.append("")
    return ordered


def _representative_plot_block_title(source, block_by, block_value) -> str:
    value = str(block_value).strip()
    if value == "":
        return "Unspecified"

    block_key = str(block_by).strip().casefold()
    if block_key == "condition":
        return _condition_label_map(source).get(value, value)

    label_map = _condition_component_attr_map(source, block_by, attr="label")
    return label_map.get(value, value)


def _representative_plot_block_color(source, block_by, block_value) -> str:
    value = str(block_value).strip()
    if value == "":
        return "black"

    block_key = str(block_by).strip().casefold()
    if block_key == "condition":
        return _condition_color_map(source).get(value, "black")

    color_map = _condition_component_attr_map(source, block_by, attr="color")
    return color_map.get(value, "black")


def _collect_representative_plot_blocks(source, image_df: pd.DataFrame, marker_panels, marker_order=None, block_by="Condition", merge_label="Merge"):
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return []

    if marker_order is None:
        marker_order = []
        seen = set()
        for panel in marker_panels or []:
            for marker in _image_panel_markers(panel):
                key = str(marker).casefold()
                if key in seen:
                    continue
                seen.add(key)
                marker_order.append(str(marker))

    work_df = _order_image_rows_by_source(source, image_df, marker_names=marker_order)
    block_series = _resolve_representative_block_series(source, work_df, block_by)
    work_df = work_df.copy()
    work_df["__rep_block__"] = block_series

    block_values = list(dict.fromkeys(work_df["__rep_block__"].tolist()))
    ordered_block_values = _resolve_representative_block_order(source, block_by, block_values)

    blocks = []
    for block_value in ordered_block_values:
        block_df = work_df[work_df["__rep_block__"] == block_value].copy()
        if block_df.empty:
            continue
        block_df = _order_image_rows_by_source(source, block_df, marker_names=marker_order)
        slot_records, block_nrows, block_ncols = _build_image_tile_slots(
            block_df,
            marker_panels,
            merge_label=merge_label,
        )
        if block_ncols is None:
            block_ncols = 1
            row_slices = [[row] for row in slot_records]
        else:
            row_slices = [
                slot_records[(row_idx * block_ncols):((row_idx + 1) * block_ncols)]
                for row_idx in range(int(block_nrows))
            ]

        row_labels = []
        for row_slice in row_slices:
            labels = []
            for row in row_slice:
                if row is None:
                    continue
                label = _image_row_label(row)
                if label != "":
                    labels.append(label)
            unique_labels = list(dict.fromkeys(labels))
            row_labels.append(unique_labels[0] if len(unique_labels) == 1 else "")

        blocks.append({
            "value": str(block_value).strip(),
            "title": _representative_plot_block_title(source, block_by, block_value),
            "color": _representative_plot_block_color(source, block_by, block_value),
            "rows": row_slices,
            "row_labels": row_labels,
            "nrows": len(row_slices),
            "ncols": int(block_ncols),
            "panels": list(marker_panels),
        })

    return blocks


def _collect_representative_image_blocks(source, image_df: pd.DataFrame, marker_order, merge=True, merge_label="Merge"):
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return [], []

    work_df = _order_representative_selector_rows(source, image_df, marker_names=marker_order)
    block_key_cols = _representative_block_key_columns(work_df, source)

    existing, _ = _filter_representative_table_by_markers(
        source,
        _get_representative_image_table(source),
        marker_order=marker_order,
        require_specific=False,
    )
    existing_map = {
        _representative_block_key_from_record(row, block_key_cols): _representative_selection_key(row)
        for _, row in existing.iterrows()
    }

    if len(block_key_cols) == 0:
        grouped = [(tuple(), work_df)]
    else:
        grouped = list(work_df.groupby(block_key_cols, sort=False, dropna=False))

    blocks = []
    for raw_block_key, block_df in grouped:
        block_key = raw_block_key if isinstance(raw_block_key, tuple) else (raw_block_key,)
        block_label = _representative_block_label(block_key, block_key_cols, source)
        slot_records, block_nrows, block_ncols = _build_image_tile_slots(
            block_df,
            marker_order,
            include_merge=merge,
            merge_label=merge_label,
        )
        if block_ncols is None:
            block_ncols = 1
            row_slices = [[row] for row in slot_records]
        else:
            row_slices = [
                slot_records[(row_idx * block_ncols):((row_idx + 1) * block_ncols)]
                for row_idx in range(int(block_nrows))
            ]

        block_rows = []
        selected_key = existing_map.get(tuple(str(v).strip() for v in block_key))
        for row_slice in row_slices:
            first_non_merge = next(
                (
                    row for row in row_slice
                    if row is not None and not bool(row.get("__is_merged__", False))
                ),
                None,
            )
            first_row = first_non_merge if first_non_merge is not None else next((row for row in row_slice if row is not None), None)
            if first_row is None:
                continue
            selection_record = _representative_record_from_row(first_row, block_label, marker_order)
            row_key = _representative_selection_key(selection_record)
            block_rows.append({
                "row_label": _image_row_label(first_row),
                "tile_rows": row_slice,
                "selection_record": selection_record,
                "selection_key": row_key,
                "is_selected": selected_key == row_key,
            })

        if len(block_rows) == 0:
            continue
        blocks.append({
            "block_key": tuple(str(v).strip() for v in block_key),
            "block_key_cols": block_key_cols,
            "title": block_label,
            "color": _representative_block_color(block_key, block_key_cols, source),
            "rows": block_rows,
            "ncols": int(block_ncols),
        })

    return blocks, block_key_cols


def _image_row_key_columns(work_df: pd.DataFrame):
    row_key_cols = [c for c in ["Condition", "Experiment", "AnimalName", "ROI"] if c in work_df.columns]
    if len(row_key_cols) > 0:
        return row_key_cols
    fallback = [c for c in ["AnimalName", "ROI", "ImageName"] if c in work_df.columns]
    return fallback if len(fallback) > 0 else list(work_df.columns[:1])


def _image_merge_marker_label(marker_names, max_items=4, merge_label="Merge"):
    label = str(merge_label).strip()
    if label != "":
        return label

    cleaned = []
    for marker in marker_names:
        text = str(marker).strip()
        if text == "" or text in cleaned:
            continue
        cleaned.append(text)
    if len(cleaned) == 0:
        return ""
    if len(cleaned) <= max_items:
        return " + ".join(cleaned)
    return f"{cleaned[0]} + {len(cleaned) - 1} more"


def _normalize_image_adjustments(image_adjustments=None, marker_names=None):
    out = {}
    requested_markers = []
    for marker in _flatten_specificity_values([marker_names]) if marker_names is not None else []:
        marker_s = str(marker).strip()
        if marker_s != "" and marker_s.casefold() not in [m.casefold() for m in requested_markers]:
            requested_markers.append(marker_s)

    broadcast_brightness = 1.0
    broadcast_contrast = 1.0
    has_broadcast = False

    if isinstance(image_adjustments, Mapping):
        for key, value in image_adjustments.items():
            marker_s = str(key).strip()
            if marker_s == "":
                continue
            brightness = 1.0
            contrast = 1.0
            if isinstance(value, Mapping):
                try:
                    brightness = float(value.get("brightness", 1.0))
                except Exception:
                    brightness = 1.0
                try:
                    contrast = float(value.get("contrast", 1.0))
                except Exception:
                    contrast = 1.0
            elif isinstance(value, (list, tuple, np.ndarray, pd.Series, pd.Index)):
                vals = list(_flatten_specificity_values([value]))
                if len(vals) > 0:
                    try:
                        brightness = float(vals[0])
                    except Exception:
                        brightness = 1.0
                if len(vals) > 1:
                    try:
                        contrast = float(vals[1])
                    except Exception:
                        contrast = 1.0
            else:
                try:
                    brightness = float(value)
                except Exception:
                    brightness = 1.0
            out[marker_s.casefold()] = {
                "marker": marker_s,
                "brightness": brightness,
                "contrast": contrast,
            }
    elif image_adjustments is not None:
        has_broadcast = True
        if isinstance(image_adjustments, (list, tuple, np.ndarray, pd.Series, pd.Index)):
            vals = list(_flatten_specificity_values([image_adjustments]))
            if len(vals) > 0:
                try:
                    broadcast_brightness = float(vals[0])
                except Exception:
                    broadcast_brightness = 1.0
            if len(vals) > 1:
                try:
                    broadcast_contrast = float(vals[1])
                except Exception:
                    broadcast_contrast = 1.0
        else:
            try:
                broadcast_brightness = float(image_adjustments)
            except Exception:
                broadcast_brightness = 1.0

    for marker_s in requested_markers:
        out.setdefault(
            marker_s.casefold(),
            {
                "marker": marker_s,
                "brightness": broadcast_brightness if has_broadcast else 1.0,
                "contrast": broadcast_contrast if has_broadcast else 1.0,
            },
        )
    return out


def _image_adjustment_values(marker_name, image_adjustments=None):
    marker_s = str(marker_name).strip()
    if marker_s == "":
        return 1.0, 1.0
    normalized = _normalize_image_adjustments(image_adjustments)
    entry = normalized.get(marker_s.casefold(), None)
    if not isinstance(entry, Mapping):
        return 1.0, 1.0
    try:
        brightness = float(entry.get("brightness", 1.0))
    except Exception:
        brightness = 1.0
    try:
        contrast = float(entry.get("contrast", 1.0))
    except Exception:
        contrast = 1.0
    return brightness, contrast


def _image_adjustment_cache_key(marker_name, image_adjustments=None):
    brightness, contrast = _image_adjustment_values(marker_name, image_adjustments=image_adjustments)
    return (
        str(marker_name).strip().casefold(),
        round(float(brightness), 6),
        round(float(contrast), 6),
    )


def _image_array_to_rgb_float(tile):
    arr = np.asarray(tile)
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    elif arr.ndim == 3 and arr.shape[2] == 1:
        arr = np.repeat(arr, 3, axis=2)
    elif arr.ndim == 3 and arr.shape[2] >= 4:
        rgb = arr[..., :3].astype(np.float32, copy=False)
        alpha = arr[..., 3:4].astype(np.float32, copy=False)
        if np.issubdtype(arr.dtype, np.integer):
            alpha_scale = float(np.iinfo(arr.dtype).max)
        else:
            alpha_scale = 1.0 if np.nanmax(alpha) <= 1.0 else 255.0
        arr = rgb * np.clip(alpha / max(alpha_scale, 1e-9), 0.0, 1.0)
    elif arr.ndim == 3 and arr.shape[2] > 3:
        arr = arr[..., :3]

    arr = arr.astype(np.float32, copy=False)
    if np.issubdtype(np.asarray(tile).dtype, np.integer):
        arr /= float(np.iinfo(np.asarray(tile).dtype).max)
    else:
        finite = arr[np.isfinite(arr)]
        if finite.size > 0:
            finite_max = float(np.max(finite))
            if finite_max > 1.0:
                if finite_max <= 255.0:
                    arr /= 255.0
                else:
                    arr /= finite_max
    return np.clip(arr, 0.0, 1.0)


def _apply_image_adjustments(tile, marker_name=None, image_adjustments=None):
    if image_adjustments in (None, {}):
        return tile
    brightness, contrast = _image_adjustment_values(marker_name, image_adjustments=image_adjustments)
    if abs(float(brightness) - 1.0) < 1e-9 and abs(float(contrast) - 1.0) < 1e-9:
        return tile
    arr = _image_array_to_rgb_float(tile)
    arr = np.clip(arr * float(brightness), 0.0, 1.0)
    arr = np.clip((arr - 0.5) * float(contrast) + 0.5, 0.0, 1.0)
    return arr


def _apply_manual_brightness_contrast(arr, brightness, contrast):
    out = np.clip(np.asarray(arr, dtype=np.float32) * float(brightness), 0.0, 1.0)
    out = np.clip((out - 0.5) * float(contrast) + 0.5, 0.0, 1.0)
    return out


def _enhance_contrast_channel(channel, saturated=0.35):
    """Percentile-clip + linear stretch — exact match to ImageJ Enhance Contrast
    (ContrastEnhancer.java) with normalize=True.

    ``saturated`` is the total percentage clipped, split equally across both
    histogram tails (matching the Java ``threshold = pixelCount * saturated / 200``).
    """
    arr = np.asarray(channel, dtype=np.float32)
    lo_pct = float(saturated) / 2.0
    hi_pct = 100.0 - lo_pct
    p_lo, p_hi = np.percentile(arr, (lo_pct, hi_pct))
    if (p_hi - p_lo) < 1e-9:
        return arr
    return np.clip((arr - p_lo) / (p_hi - p_lo), 0.0, 1.0)


def _enhance_contrast_rgb(tile, saturated=0.35):
    """Apply per-channel percentile contrast enhancement to an RGB float tile."""
    rgb = _image_array_to_rgb_float(tile)
    out = np.empty_like(rgb, dtype=np.float32)
    for ch in range(out.shape[2]):
        out[..., ch] = _enhance_contrast_channel(rgb[..., ch], saturated=saturated)
    return out


def _suggest_auto_adjustments(tile, saturated=0.35):
    """Compute brightness/contrast values that approximate per-channel percentile
    contrast enhancement via the manual brightness/contrast model.

    Uses scipy.optimize when available, otherwise a coarse grid search.
    """
    source = _image_array_to_rgb_float(tile)
    target = _enhance_contrast_rgb(tile, saturated=saturated)

    source_sample = source[::4, ::4, ...]
    target_sample = target[::4, ::4, ...]

    def _mse(params):
        b, c = float(params[0]), float(params[1])
        trial = _apply_manual_brightness_contrast(source_sample, b, c)
        return float(np.mean((trial - target_sample) ** 2))

    try:
        from scipy.optimize import minimize
        result = minimize(_mse, x0=[1.0, 1.0], method='Powell',
                          bounds=[(0.01, 5.0), (0.01, 5.0)],
                          options={'maxfev': 200, 'ftol': 1e-6})
        return max(0.0, float(result.x[0])), max(0.0, float(result.x[1]))
    except ImportError:
        pass

    best_brightness, best_contrast, best_error = 1.0, 1.0, float("inf")
    for b in np.linspace(0.1, 3.0, 15, dtype=float):
        for c in np.linspace(0.1, 3.0, 15, dtype=float):
            err = _mse([b, c])
            if err < best_error:
                best_error, best_brightness, best_contrast = err, b, c
    return max(0.0, best_brightness), max(0.0, best_contrast)


def _center_crop_image_array(arr, target_height, target_width):
    height, width = arr.shape[:2]
    start_y = max(0, (height - target_height) // 2)
    start_x = max(0, (width - target_width) // 2)
    end_y = start_y + target_height
    end_x = start_x + target_width
    return arr[start_y:end_y, start_x:end_x, ...]


def _merge_image_arrays(image_arrays):
    prepared = [_image_array_to_rgb_float(tile) for tile in image_arrays if isinstance(tile, np.ndarray)]
    if len(prepared) == 0:
        raise ValueError("No image arrays were available for merging.")
    if len(prepared) == 1:
        return prepared[0]

    target_height = min(arr.shape[0] for arr in prepared)
    target_width = min(arr.shape[1] for arr in prepared)
    cropped = [_center_crop_image_array(arr, target_height, target_width) for arr in prepared]
    return np.maximum.reduce(cropped)


def _resolve_image_array(row, image_backend="auto",
                         fast_loading=False, preview_max_dim=None,
                         image_adjustments=None) -> np.ndarray:
    cached = row.get("ImageArray", None)
    marker_name = str(row.get("Marker", "")).strip() if hasattr(row, "get") else ""
    if isinstance(cached, np.ndarray):
        if cached.ndim >= 2:
            return _apply_image_adjustments(cached, marker_name=marker_name, image_adjustments=image_adjustments)
    if cached is not None and not (isinstance(cached, float) and np.isnan(cached)):
        try:
            cached_arr = np.asarray(cached)
            if cached_arr.ndim >= 2:
                return _apply_image_adjustments(cached_arr, marker_name=marker_name, image_adjustments=image_adjustments)
        except Exception:
            pass
    tile = read_image_array(
        row["ImagePath"],
        backend=image_backend,
        fast_loading=fast_loading,
        preview_max_dim=preview_max_dim,
    )
    return _apply_image_adjustments(tile, marker_name=marker_name, image_adjustments=image_adjustments)


def _draw_image_panel_roi_outline(ax, source, row, *, black_background=False):
    ref_row = _scale_bar_reference_row(row)
    if ref_row is None:
        return False

    exp_obj = _location_source_experiment(source, image_row=ref_row)
    animal_name = str(ref_row.get("AnimalName", "")).strip()
    scn_name = str(ref_row.get("Region", "")).strip()
    image_roi_name = str(ref_row.get("ImageROI", "")).strip() or str(ref_row.get("ROI", "")).strip()

    roi_row = _location_draw_roi_row(
        exp_obj,
        scn_name=scn_name,
        animal_name=animal_name,
        image_roi_name=image_roi_name,
    )
    if roi_row is None:
        return False

    polygon = _location_roi_polygon_xy(roi_row)
    if polygon is None:
        return False

    xs, ys = polygon
    line_color = "white" if bool(black_background) else "white"
    ax.plot(
        xs,
        ys,
        color=line_color,
        linewidth=1.75,
        linestyle=(0, (4, 3)),
        dash_capstyle='round',
        alpha=1.0,
        zorder=5.0,
    )
    return True


def _resolve_image_tile(row, image_backend="auto",
                        fast_loading=False, preview_max_dim=None,
                        image_adjustments=None) -> np.ndarray:
    merge_rows = row.get("__merge_rows__", None) if hasattr(row, "get") else None
    if isinstance(merge_rows, list) and len(merge_rows) > 0:
        source_tiles = [
            _resolve_image_array(
                source_row,
                image_backend=image_backend,
                fast_loading=fast_loading,
                preview_max_dim=preview_max_dim,
                image_adjustments=image_adjustments,
            )
            for source_row in merge_rows
        ]
        return _merge_image_arrays(source_tiles)
    return _resolve_image_array(
        row,
        image_backend=image_backend,
        fast_loading=fast_loading,
        preview_max_dim=preview_max_dim,
        image_adjustments=image_adjustments,
    )


def _preload_representative_tiles(blocks, image_backend="auto",
                                  fast_loading=True, preview_max_dim=None,
                                  image_adjustments=None,
                                  image_workers=None,
                                  progress_state=None,
                                  progress_label="Load representative tiles"):
    tasks = []
    for block_idx, block in enumerate(blocks):
        for row_idx, row in enumerate(block["rows"]):
            for col_idx, tile_row in enumerate(row["tile_rows"]):
                if tile_row is not None:
                    tasks.append((block_idx, row_idx, col_idx, tile_row))

    loaded = {}
    worker_count = resolve_image_worker_count(
        image_workers=image_workers,
        task_count=len(tasks),
        preload=True,
    )
    if len(tasks) == 0:
        if progress_state is not None:
            _image_progress_finish(progress_state, progress_label, detail="No representative tiles to load")
        return loaded

    if progress_state is not None:
        _progress_start_item(progress_state, progress_label)

    if worker_count <= 1:
        for block_idx, row_idx, col_idx, tile_row in tasks:
            try:
                loaded[(block_idx, row_idx, col_idx)] = _resolve_image_tile(
                    tile_row,
                    image_backend=image_backend,
                    fast_loading=fast_loading,
                    preview_max_dim=preview_max_dim,
                    image_adjustments=image_adjustments,
                )
            except Exception as exc:
                loaded[(block_idx, row_idx, col_idx)] = exc
        return loaded

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _resolve_image_tile,
                tile_row,
                image_backend,
                fast_loading,
                preview_max_dim,
                image_adjustments,
            ): (block_idx, row_idx, col_idx)
            for block_idx, row_idx, col_idx, tile_row in tasks
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                loaded[key] = future.result()
            except Exception as exc:
                loaded[key] = exc
    if progress_state is not None:
        _image_progress_finish(
            progress_state,
            progress_label,
            detail=f"{len(tasks)} tiles | {worker_count} worker{'s' if worker_count != 1 else ''}",
        )
    return loaded


def _merge_representative_tables(existing_table, new_table, marker_order=None):
    existing = _normalize_representative_image_table(existing_table)
    new = _normalize_representative_image_table(new_table)
    if new.empty:
        return existing

    subset_keys = _representative_marker_keys(new)
    if len(subset_keys) == 0 and marker_order is not None:
        _, _, marker_key = _representative_marker_signature(markers=marker_order)
        if marker_key != "":
            subset_keys = [marker_key]

    if len(subset_keys) == 0:
        return new

    keep_existing = existing[~existing["RepresentativeMarkerKey"].astype(str).isin(subset_keys)].copy()
    merged = pd.concat([keep_existing, new], ignore_index=True)
    return _normalize_representative_image_table(merged)


def _apply_representative_selections(source, selection_records, marker_order=None):
    table = _normalize_representative_image_table(pd.DataFrame.from_records(selection_records))
    source.representative_images = _merge_representative_tables(
        getattr(source, "representative_images", None),
        table,
        marker_order=marker_order,
    )
    if marker_order is not None:
        source.representative_image_markers = _representative_marker_list(markers=marker_order)

    if hasattr(source, "experiment_list"):
        for exp in getattr(source, "experiment_list", []):
            if not isinstance(table, pd.DataFrame) or table.empty:
                exp_new = _empty_representative_image_table()
            elif "Experiment" in table.columns:
                exp_new = _normalize_representative_image_table(
                    table[table["Experiment"].astype(str) == str(getattr(exp, "name", ""))].copy()
                )
            else:
                exp_new = table.copy()
            exp.representative_images = _merge_representative_tables(
                getattr(exp, "representative_images", None),
                exp_new,
                marker_order=marker_order,
            )
            if marker_order is not None:
                exp.representative_image_markers = _representative_marker_list(markers=marker_order)
    return source.representative_images


def _filter_image_df_to_representatives(image_df: pd.DataFrame, representative_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return image_df
    rep_df = _normalize_representative_image_table(representative_df)
    if rep_df.empty:
        return image_df.iloc[0:0].copy()

    join_cols = [
        col for col in ["Experiment", "Condition", "AnimalName", "ROI"]
        if col in image_df.columns and col in rep_df.columns
    ]
    if len(join_cols) == 0:
        raise ValueError("Representative image filtering requires shared identifier columns.")

    key_df = rep_df[join_cols].drop_duplicates().copy()
    return image_df.merge(key_df, on=join_cols, how="inner")


def _representative_experiment_lookup(source) -> dict:
    if hasattr(source, "experiment_list"):
        return {
            str(getattr(exp, "name", "")): exp
            for exp in getattr(source, "experiment_list", [])
        }
    return {str(getattr(source, "name", "")): source}


def _representative_block_experiment_name(block, source) -> str:
    for row in block.get("rows", []):
        exp_name = str(row.get("selection_record", {}).get("Experiment", "")).strip()
        if exp_name != "":
            return exp_name
    return str(getattr(source, "name", "")).strip()


def _summary_condition_order(exp_obj):
    summary = getattr(exp_obj, "summary", None)
    if not isinstance(summary, pd.DataFrame):
        return []
    if hasattr(exp_obj, "condition_list"):
        ordered = [
            str(getattr(cond, "name", "")).strip()
            for cond in getattr(exp_obj, "condition_list", [])
            if str(getattr(cond, "name", "")).strip() != ""
        ]
        if len(ordered) > 0:
            return ordered
    if "Condition" in summary.columns:
        return summary["Condition"].dropna().astype(str).tolist()
    return []


def _normalize_representative_stats_columns(stats_columns) -> list[str]:
    if stats_columns is None:
        return ["Count", "IntDenTotal"]
    requests = [
        str(value).strip()
        for value in _flatten_specificity_values([stats_columns])
        if str(value).strip() != ""
    ]
    if len(requests) == 0:
        return ["Count", "IntDenTotal"]
    return list(dict.fromkeys(requests))


def _resolve_representative_metric_specs(summary: pd.DataFrame, marker, stats_columns=None):
    requests = _normalize_representative_stats_columns(stats_columns)
    marker_s = str(marker).strip()
    if marker_s == "" or not isinstance(summary, pd.DataFrame) or summary.empty:
        return []

    metric_specs = []
    seen = set()
    for request in requests:
        candidates = []
        request_s = str(request).strip()
        if request_s == "":
            continue
        if "{marker}" in request_s:
            candidates.append(request_s.format(marker=marker_s))
        else:
            candidates.append(f"{marker_s}_{request_s}")
            candidates.append(request_s)
        for metric_col in candidates:
            metric_col_s = str(metric_col).strip()
            if metric_col_s == "" or metric_col_s in seen or metric_col_s not in summary.columns:
                continue
            seen.add(metric_col_s)
            metric_specs.append({
                "column": metric_col_s,
                "label": get_display_name(metric_col_s, minimal=True),
            })
            break
    return metric_specs


def _representative_stats_header_text(stats_columns=None) -> str:
    requests = _normalize_representative_stats_columns(stats_columns)
    labels = [get_display_name(col, minimal=True) for col in requests]
    if len(labels) == 0:
        return "Representative metrics across conditions"
    if len(labels) == 1:
        return f"{labels[0]} across conditions"
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]} across conditions"
    return f"{', '.join(labels[:-1])}, and {labels[-1]} across conditions"


def _resolve_representative_summary_specs(source, blocks, marker_order, stats_columns=None):
    exp_lookup = _representative_experiment_lookup(source)
    block_experiment_names = []
    for block in blocks:
        exp_name = _representative_block_experiment_name(block, source)
        if exp_name not in block_experiment_names:
            block_experiment_names.append(exp_name)

    specs = []
    for exp_name in block_experiment_names:
        exp_obj = exp_lookup.get(exp_name, source)
        summary = getattr(exp_obj, "summary", None)
        if not isinstance(summary, pd.DataFrame) or summary.empty:
            continue
        cond_order_raw = _summary_condition_order(exp_obj)
        cond_order = []
        seen = set()
        for cond in cond_order_raw:
            cond_s = str(cond).strip()
            if cond_s == "" or cond_s in seen:
                continue
            seen.add(cond_s)
            cond_order.append(cond_s)
        if len(cond_order) == 0 and "Condition" in summary.columns:
            cond_order = list(dict.fromkeys(summary["Condition"].dropna().astype(str).tolist()))

        marker_specs = []
        for marker in marker_order:
            metric_specs = _resolve_representative_metric_specs(
                summary,
                marker,
                stats_columns=stats_columns,
            )
            if len(metric_specs) == 0:
                continue
            marker_specs.append({
                "marker": str(marker),
                "metrics": metric_specs,
            })
        if len(marker_specs) == 0:
            continue
        specs.append({
            "experiment_name": exp_name,
            "summary": summary.copy(),
            "condition_order": cond_order,
            "marker_specs": marker_specs,
        })
    return specs


def _plot_representative_metric_axis(ax, summary_df, condition_order, metric_col, condition_colors=None):
    condition_colors = condition_colors or {}
    x_positions = {cond: idx for idx, cond in enumerate(condition_order)}
    for cond_name in condition_order:
        mask = summary_df["Condition"].astype(str) == str(cond_name) if "Condition" in summary_df.columns else pd.Series(True, index=summary_df.index)
        values = _to_numeric_excluding_not_included(summary_df.loc[mask, metric_col]).dropna()
        if len(values) == 0:
            continue
        x_base = x_positions[cond_name]
        if len(values) == 1:
            x_vals = np.array([x_base], dtype=float)
        else:
            x_vals = np.linspace(x_base - 0.14, x_base + 0.14, len(values))
        ax.scatter(
            x_vals,
            values.to_numpy(dtype=float),
            s=28,
            color=condition_colors.get(cond_name, "#9A9A9A"),
            alpha=0.55,
            linewidths=0.0,
            zorder=2,
        )
        mean_val = float(values.mean())
        ax.plot(
            [x_base - 0.18, x_base + 0.18],
            [mean_val, mean_val],
            color="black",
            linewidth=2.0,
            zorder=3,
        )

    ax.set_xticks(range(len(condition_order)))
    ax.set_xticklabels(condition_order, rotation=30, ha="right")
    ax.set_title(get_display_name(metric_col, minimal=True), fontsize=11)
    ax.tick_params(axis="both", labelsize=9)
    ax.grid(axis="y", alpha=0.18)
    sns.despine(trim=False, ax=ax)
    highlight = ax.scatter(
        [],
        [],
        s=100,
        facecolors="none",
        edgecolors="crimson",
        linewidths=2.0,
        zorder=4,
    )
    return {
        "artist": highlight,
        "metric_col": metric_col,
        "condition_order": condition_order,
        "summary": summary_df,
    }


def _apply_requested_order(columns, requested_order):
    """
    Reorder `columns` by a requested list while preserving unmatched columns.
    Matching is exact first, then prefix match.
    """
    cols = list(columns)
    if requested_order is None:
        return cols
    ordered = []
    used = set()
    for key in requested_order:
        key_s = str(key)
        # exact matches first
        for c in cols:
            if c in used:
                continue
            if str(c) == key_s:
                ordered.append(c)
                used.add(c)
        # then prefix-style matches
        for c in cols:
            if c in used:
                continue
            c_s = str(c)
            if c_s.startswith(key_s) or c_s.split("_", 1)[0] == key_s:
                ordered.append(c)
                used.add(c)
    for c in cols:
        if c not in used:
            ordered.append(c)
    return ordered


def _init_progress_state(state, func_name, total):
    if state.get('progress_state') is not None:
        return
    prog = {
        'func_name': func_name,
        'total': max(1, int(total)),
        'completed': 0,
        'sum_time': 0.0,
        'run_start': time.perf_counter(),
        'item_start': None,
        'handle': None,
    }
    try:
        from IPython.display import display
        prog['handle'] = display("", display_id=True)
    except Exception:
        prog['handle'] = None
    state['progress_state'] = prog


def _progress_start_item(state, item_name=None):
    prog = state.get('progress_state')
    if prog is not None:
        prog['item_start'] = time.perf_counter()
        if item_name is not None:
            _render_progress(state, item_name, in_progress=True)


def _render_progress(state, item_name, in_progress=False):
    prog = state.get('progress_state')
    if prog is None:
        return
    total = prog['total']
    done = min(prog['completed'], total)
    shown = min(done + (1 if in_progress and done < total else 0), total)
    pct = (shown / total) * 100.0
    bar_width = 28
    fill = int((shown / total) * bar_width)
    bar = "█" * fill + "·" * (bar_width - fill)
    remaining = max(0, total - done)
    if done > 0:
        avg = prog['sum_time'] / done
        eta = avg * remaining
        eta_text = time.strftime("%H:%M:%S", time.gmtime(max(0, int(round(eta)))))
        avg_text = f"{avg:.2f}s/process"
    else:
        eta_text = "estimating..."
        avg_text = "n/a"
    msg = (
        f"[{prog['func_name']}] {shown}/{total} process: {item_name}\n"
        f"[{bar}] {pct:5.1f}%\n"
        f"Estimated time to completion: {eta_text} | Avg/process: {avg_text}"
    )
    if prog.get('handle') is not None:
        try:
            import html as _html
            from IPython.display import HTML
            prog['handle'].update(HTML(f"<pre style='margin:0'>{_html.escape(msg)}</pre>"))
        except Exception:
            prog['handle'].update(msg)
    else:
        import sys
        sys.stdout.write("\r\033[2K")
        try:
            sys.stdout.write(msg)
        except UnicodeEncodeError:
            safe_msg = msg.replace("█", "#").replace("·", "-")
            sys.stdout.write(safe_msg)
        sys.stdout.flush()


def _progress_finish_item(state, item_name):
    prog = state.get('progress_state')
    if prog is None:
        return
    start = prog.get('item_start')
    if start is not None:
        prog['sum_time'] += (time.perf_counter() - start)
    prog['completed'] += 1
    _render_progress(state, item_name)


def _close_progress_state(state):
    prog = state.get('progress_state')
    if prog is None:
        return
    handle = prog.get('handle')
    if handle is not None:
        try:
            handle.update("")
        except Exception:
            pass
    state['progress_state'] = None


def _image_progress_finish(state, item_name, detail=None):
    prog = state.get('progress_state', {})
    if len(prog) == 0:
        return
    _progress_finish_item(state, item_name)
    prog = state.get('progress_state', {})
    if detail is None:
        return
    handle = prog.get('handle')
    msg = f"[{prog.get('func_name', 'progress')}] {item_name}: {detail}"
    if handle is not None:
        try:
            import html as _html
            from IPython.display import HTML
            handle.update(HTML(f"<pre style='margin:0'>{_html.escape(msg)}</pre>"))
        except Exception:
            handle.update(msg)
    else:
        try:
            import sys
            try:
                sys.stdout.write("\n" + msg + "\n")
            except UnicodeEncodeError:
                safe_msg = msg.replace("█", "#").replace("·", "-")
                sys.stdout.write("\n" + safe_msg + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def _image_progress_tracker(func_name, total, enabled=True):
    state = {}
    if enabled:
        _init_progress_state(state, func_name=func_name, total=total)
    return state


def _preload_image_rows(row_records, image_backend="auto",
                        fast_loading=False, preview_max_dim=None,
                        image_adjustments=None,
                        image_workers=None,
                        progress_state=None,
                        progress_label="Load image tiles"):
    record_items = [(idx, row) for idx, row in enumerate(row_records) if row is not None]
    worker_count = resolve_image_worker_count(
        image_workers=image_workers,
        task_count=len(record_items),
        preload=True,
    )
    loaded_tiles = {}
    if len(record_items) == 0:
        if progress_state is not None:
            _image_progress_finish(progress_state, progress_label, detail="No image tiles to load")
        return loaded_tiles

    if progress_state is not None:
        _progress_start_item(progress_state, progress_label)

    if worker_count > 1:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    _resolve_image_tile,
                    row,
                    image_backend,
                    fast_loading,
                    preview_max_dim,
                    image_adjustments,
                ): idx
                for idx, row in record_items
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    loaded_tiles[idx] = future.result()
                except Exception as exc:
                    loaded_tiles[idx] = exc
    else:
        for idx, row in record_items:
            try:
                loaded_tiles[idx] = _resolve_image_tile(
                    row,
                    image_backend=image_backend,
                    fast_loading=fast_loading,
                    preview_max_dim=preview_max_dim,
                    image_adjustments=image_adjustments,
                )
            except Exception as exc:
                loaded_tiles[idx] = exc

    if progress_state is not None:
        _image_progress_finish(
            progress_state,
            progress_label,
            detail=f"{len(record_items)} tiles | {worker_count} worker{'s' if worker_count != 1 else ''}",
        )
    return loaded_tiles


def _filter_plotable_numeric_columns(experiment, columns, factor=None):
    """
    Keep only columns with numeric data that can be plotted.

    For condition-based bars: require at least one condition with >=1 numeric value.
    For factor-based bars: require at least one factor level with >=1 numeric value.
    """
    summary = experiment.summary
    if factor is not None and factor in summary.columns:
        ordered_groups = list(summary[factor].dropna().unique())
        selector = lambda g: summary[summary[factor] == g]
    else:
        ordered_groups = [cond.name for cond in experiment.condition_list]
        selector = lambda g: summary[summary["Condition"] == g]

    keep = []
    for col in columns:
        if col not in summary.columns:
            continue
        any_numeric = False
        for group in ordered_groups:
            s = pd.to_numeric(selector(group)[col], errors="coerce").dropna()
            if len(s) > 0:
                any_numeric = True
                break
        if any_numeric:
            keep.append(col)
    return keep


def _resolve_action_axis(state, idx):
    """Resolve an axis for action functions without eager indexing errors."""
    ax = state.get('ax')
    if ax is not None:
        return ax
    axes = state.get('axes')
    if axes is None:
        return None
    try:
        i = int(idx)
        if 0 <= i < len(axes):
            return axes[i]
    except Exception:
        return None
    return None


def _resolve_group_label_color(ctx: Context):
    """
    Resolve display label/color for current regression group.

    For factor iteration, map factor value back to the corresponding condition
    definition so plots use cond.label and cond.color.
    """
    default_label = ctx.label if ctx.label else (ctx.condition or ctx.factor_value or "Group")
    default_color = ctx.color or 'black'

    if ctx.factor_value is None:
        return default_label, default_color

    def _norm(v):
        return str(v).strip().casefold()

    target = _norm(ctx.factor_value)
    candidates = []

    for fd in (
        getattr(ctx.experiment, 'factorDict', None),
        getattr(getattr(ctx.experiment, 'condition_list', None), 'factorDict', None),
    ):
        if not isinstance(fd, dict):
            continue
        if ctx.factor in fd:
            candidates.extend(list(fd.get(ctx.factor, [])))
            continue
        for k, vals in fd.items():
            if _norm(k) == _norm(ctx.factor):
                candidates.extend(list(vals))
                break

    if len(candidates) == 0:
        cond_list = getattr(ctx.experiment, 'condition_list', None)
        if cond_list is not None:
            try:
                candidates.extend(list(cond_list))
            except Exception:
                pass

    chosen = None
    for cond in candidates:
        name = getattr(cond, 'name', None)
        if name is None:
            continue
        if _norm(name) == target:
            chosen = cond
            break
    if chosen is None:
        for cond in candidates:
            name = getattr(cond, 'name', None)
            if name is None:
                continue
            name_norm = _norm(name)
            if target in name_norm or name_norm in target:
                chosen = cond
                break

    if chosen is None:
        return default_label, default_color

    label = getattr(chosen, 'label', None) or default_label
    color = getattr(chosen, 'color', None) or default_color
    return label, color


def _to_numeric_excluding_not_included(series, sentinel="NOT_INCLUDED_IN_EXPERIMENT"):
    """Coerce to numeric while dropping any NOT_INCLUDED sentinel-like strings."""
    s = series.copy()
    try:
        mask = s.astype(str).str.contains(str(sentinel), na=False)
        s = s.mask(mask, np.nan)
    except Exception:
        pass
    return pd.to_numeric(s, errors='coerce')


def _scatter_size_norm(reference_df: pd.DataFrame | None, size_col: str):
    """Return stable min/max normalization for 3D scatter marker sizes."""
    if not isinstance(reference_df, pd.DataFrame):
        return None
    if size_col not in reference_df.columns:
        raise KeyError(f"Column not found for size_by: {size_col}")

    ref_vals = _to_numeric_excluding_not_included(reference_df[size_col]).to_numpy(dtype=float)
    ref_finite = ref_vals[np.isfinite(ref_vals)]
    if ref_finite.size == 0:
        return None

    vmin = float(np.min(ref_finite))
    vmax = float(np.max(ref_finite))
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return None
    return (vmin, vmax)


def _scatter_point_sizes(
    df: pd.DataFrame,
    *,
    size_by=None,
    point_size=40,
    size_factor=1.0,
    size_norm=None,
) -> np.ndarray:
    """Resolve marker sizes for 3D scatter, optionally scaling by a data column."""
    n = int(len(df))
    if n <= 0:
        return np.asarray([], dtype=float)

    try:
        factor = float(size_factor)
    except (TypeError, ValueError):
        factor = 1.0
    if not np.isfinite(factor) or factor <= 0:
        factor = 1.0

    base_size = max(float(point_size), 1.0) * factor
    out = np.full(n, base_size, dtype=float)
    if size_by is None:
        return out
    if size_by not in df.columns:
        raise KeyError(f"Column not found for size_by: {size_by}")

    vals = _to_numeric_excluding_not_included(df[size_by]).to_numpy(dtype=float)
    finite = np.isfinite(vals)
    if not finite.any():
        return out

    if size_norm is None:
        finite_vals = vals[finite]
        vmin = float(np.min(finite_vals))
        vmax = float(np.max(finite_vals))
    else:
        vmin, vmax = size_norm

    min_size = max(8.0, base_size * 0.5)
    max_size = max(min_size, base_size * 2.5)

    if np.isfinite(vmin) and np.isfinite(vmax) and vmax > vmin:
        scaled = (vals[finite] - vmin) / (vmax - vmin)
        scaled = np.clip(scaled, 0.0, 1.0)
        out[finite] = min_size + scaled * (max_size - min_size)
    else:
        out[finite] = base_size

    return out


def _normalize_regression_series(series, mode, axis_name='value'):
    """Normalize a regression axis series according to the requested mode."""
    if mode is None or mode is False:
        return series

    if isinstance(mode, bool):
        if not mode:
            return series
        mode = (0.0, 1.0)

    values = series.to_numpy(dtype=float, copy=True)
    if values.size == 0:
        return series.astype(float)

    if isinstance(mode, str):
        key = str(mode).strip().casefold().replace('-', '').replace('_', '').replace(' ', '')
        if key != 'zscore':
            raise ValueError(
                f"{axis_name} normalization must be False, True, a (min, max) range, or 'Z-score'."
            )
        mean = float(np.nanmean(values))
        std = float(np.nanstd(values, ddof=0))
        if not np.isfinite(std) or std == 0.0:
            normalized = np.zeros_like(values, dtype=float)
        else:
            normalized = (values - mean) / std
        return pd.Series(normalized, index=series.index, name=series.name, dtype=float)

    if isinstance(mode, (list, tuple, np.ndarray, pd.Series, pd.Index)):
        try:
            target_min, target_max = mode
        except ValueError as exc:
            raise ValueError(
                f"{axis_name} normalization range must contain exactly two values."
            ) from exc

        target_min = float(target_min)
        target_max = float(target_max)
        if not np.isfinite(target_min) or not np.isfinite(target_max):
            raise ValueError(f"{axis_name} normalization range must be finite.")
        if target_min == target_max:
            raise ValueError(f"{axis_name} normalization range min and max must differ.")

        source_min = float(np.nanmin(values))
        source_max = float(np.nanmax(values))
        if not np.isfinite(source_min) or not np.isfinite(source_max):
            return pd.Series(values, index=series.index, name=series.name, dtype=float)
        if source_min == source_max:
            normalized = np.full(values.shape, target_min, dtype=float)
        else:
            scale = (target_max - target_min) / (source_max - source_min)
            normalized = ((values - source_min) * scale) + target_min
        return pd.Series(normalized, index=series.index, name=series.name, dtype=float)

    raise ValueError(
        f"{axis_name} normalization must be False, True, a (min, max) range, or 'Z-score'."
    )


def _compute_radar_scale_reference(df_source, columns):
    """Return per-column numeric min/max ranges for radar normalization."""
    if not isinstance(df_source, pd.DataFrame):
        return {}
    ranges = {}
    for col in columns:
        if col not in df_source.columns:
            continue
        values = _to_numeric_excluding_not_included(df_source[col]).to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            continue
        ranges[col] = (float(np.min(finite)), float(np.max(finite)))
    return ranges


def _normalize_radar_value(value, value_range):
    """Normalize one radar value to 0-1; constant ranges map to 0.5."""
    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return np.nan
    if not np.isfinite(value_f) or value_range is None:
        return np.nan
    low, high = value_range
    low = float(low)
    high = float(high)
    if not np.isfinite(low) or not np.isfinite(high):
        return np.nan
    if high == low:
        return 0.5
    return float(np.clip((value_f - low) / (high - low), 0.0, 1.0))


def _normalize_radar_radial_value_radii(radial_value_radii):
    """Validate fractional radii used for radar radial value labels."""
    if radial_value_radii is None or radial_value_radii is False:
        return ()

    if isinstance(radial_value_radii, str):
        text = radial_value_radii.strip()
        if text == "" or text.casefold() in {"none", "false", "off"}:
            return ()
        items = [p.strip() for p in re.split(r"[,;]", text) if p.strip() != ""]
    elif np.isscalar(radial_value_radii):
        items = [radial_value_radii]
    else:
        items = list(radial_value_radii)

    radii = []
    for item in items:
        radius = float(item)
        if not np.isfinite(radius) or radius < 0.0 or radius > 1.0:
            raise ValueError("radial_value_radii entries must be finite values between 0 and 1.")
        if not any(abs(radius - existing) < 1e-12 for existing in radii):
            radii.append(radius)
    return tuple(radii)


def _format_radar_radial_value_label(value, *, normalize=True):
    """Format values shown at selected radar radii."""
    value_f = float(value)
    if not np.isfinite(value_f):
        return ""
    if normalize:
        return f"{value_f:.2f}"
    return f"{value_f:.3g}"


def _radar_values_for_frame(df, columns, statistic, *, normalize=True,
                            scale_reference=None):
    """Return raw and plotted radar values for a dataframe slice."""
    raw_values = np.asarray([
        _radar_statistic(df[col], statistic) if col in df.columns else np.nan
        for col in columns
    ], dtype=float)
    if bool(normalize):
        if scale_reference is None:
            scale_reference = _compute_radar_scale_reference(df, columns)
        values = np.asarray([
            _normalize_radar_value(raw, scale_reference.get(col))
            for raw, col in zip(raw_values, columns)
        ], dtype=float)
    else:
        values = raw_values
    return raw_values, values


def _radar_animal_value_records(source_df, columns, statistic, *, normalize=True,
                                scale_reference=None):
    """Return per-animal radar values for overlay markers."""
    if not isinstance(source_df, pd.DataFrame) or "AnimalName" not in source_df.columns:
        return []

    records = []
    for animal_name, animal_df in source_df.groupby("AnimalName", sort=False, dropna=True):
        if str(animal_name).strip() == "":
            continue
        raw_values, values = _radar_values_for_frame(
            animal_df,
            columns,
            statistic,
            normalize=normalize,
            scale_reference=scale_reference,
        )
        if np.isfinite(values).any():
            records.append({
                "animal": animal_name,
                "values": values,
                "raw_values": raw_values,
            })
    return records


def _radar_statistic(values, statistic):
    """Reduce a numeric Series for one radar axis."""
    clean = _to_numeric_excluding_not_included(values).dropna()
    if len(clean) == 0:
        return np.nan
    arr = clean.to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return np.nan

    if callable(statistic):
        try:
            return float(statistic(arr))
        except TypeError:
            return float(statistic(pd.Series(arr)))

    key = str(statistic).strip().casefold()
    if key == "mean":
        return float(np.mean(arr))
    if key == "median":
        return float(np.median(arr))
    if key == "sum":
        return float(np.sum(arr))
    if key == "min":
        return float(np.min(arr))
    if key == "max":
        return float(np.max(arr))
    raise ValueError("statistic must be 'mean', 'median', 'sum', 'min', 'max', or a callable.")


def _radar_statistic_label(statistic):
    if callable(statistic):
        return getattr(statistic, "__name__", "custom")
    return str(statistic).strip() or "statistic"


def _radar_wrap_label(label, width):
    """Wrap long radar labels without adding a dependency."""
    import textwrap

    try:
        width_i = int(width)
    except (TypeError, ValueError):
        width_i = 0
    if width_i <= 0:
        return str(label)
    return "\n".join(textwrap.wrap(str(label), width=width_i, break_long_words=False)) or str(label)


def _style_radar_axis(ax, columns, *, normalize=True, tick_label_size=10, label_wrap=18,
                      radial_max=None, radial_value_radii=None,
                      radial_value_color="grey", radial_value_size=None):
    """Apply common polar-axis styling for radar plots."""
    n_cols = len(columns)
    if n_cols == 0:
        return np.asarray([], dtype=float)
    angles = np.linspace(0, 2 * np.pi, n_cols, endpoint=False)
    labels = [
        _radar_wrap_label(get_display_name(c, minimal=True, compact_per=True), label_wrap)
        for c in columns
    ]
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=tick_label_size)
    ax.tick_params(axis='x', pad=10)
    label_radii = _normalize_radar_radial_value_radii(radial_value_radii)
    radial_tick_size = max(7, tick_label_size - 2) if radial_value_size is None else float(radial_value_size)
    if normalize:
        ax.set_ylim(0.0, 1.0)
        if len(label_radii) > 0:
            ax.set_yticks(list(label_radii))
            ax.set_yticklabels(
                [_format_radar_radial_value_label(r, normalize=True) for r in label_radii],
                fontsize=radial_tick_size,
                color=str(radial_value_color),
            )
        else:
            ax.set_yticks([0.25, 0.5, 0.75, 1.0])
            ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=max(7, tick_label_size - 2))
    else:
        if radial_max is None or not np.isfinite(radial_max) or radial_max <= 0:
            radial_max = 1.0
        ax.set_ylim(0.0, float(radial_max) * 1.08)
        if len(label_radii) > 0:
            tick_values = [float(radial_max) * r for r in label_radii]
            ax.set_yticks(tick_values)
            ax.set_yticklabels(
                [_format_radar_radial_value_label(v, normalize=False) for v in tick_values],
                fontsize=radial_tick_size,
                color=str(radial_value_color),
            )
        else:
            ax.tick_params(axis='y', labelsize=max(7, tick_label_size - 2))
    ax.set_rlabel_position(90)
    ax.grid(True, alpha=0.35)
    return angles


def _radar_group_order(experiment, summary, *, factor=None):
    """Return plotted group names in PyFLASH condition/factor order."""
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        return []
    if factor is not None:
        if factor not in summary.columns:
            return []
        values = summary[factor].dropna().unique().tolist()
        ordered = []
        for cond in getattr(experiment, 'condition_list', []):
            match = next((v for v in values if str(v) in str(getattr(cond, 'name', ''))), None)
            if match is not None and match not in ordered:
                ordered.append(match)
        for v in values:
            if v not in ordered:
                ordered.append(v)
        return ordered

    if "Condition" not in summary.columns:
        return []
    present = set(summary["Condition"].dropna().astype(str).tolist())
    ordered = [
        str(getattr(cond, 'name'))
        for cond in getattr(experiment, 'condition_list', [])
        if str(getattr(cond, 'name', '')) in present
    ]
    for v in summary["Condition"].dropna().astype(str).tolist():
        if v not in ordered:
            ordered.append(v)
    return ordered


def _filter_radar_numeric_columns(experiment, columns, *, factor=None, specificity=None,
                                  roi_base=None, share_columns_across_panels=True):
    """Keep radar columns with numeric data in the relevant plotted groups."""
    summaries = getattr(experiment, 'summaries', None)
    if roi_base is not None and isinstance(summaries, dict) and roi_base in summaries:
        base_source = summaries[roi_base]
    else:
        base_source = experiment.summary
    source = _summary_for_queue_share(base_source, specificity)
    if not isinstance(source, pd.DataFrame) or source.empty:
        return []
    group_col = factor if factor is not None else "Condition"
    if group_col not in source.columns:
        return []
    group_order = _radar_group_order(experiment, source, factor=factor)
    groups = [g for g in group_order if len(source[source[group_col].astype(str) == str(g)]) > 0]

    keep = []
    for col in columns:
        if col not in source.columns:
            continue
        if not bool(share_columns_across_panels):
            values = _to_numeric_excluding_not_included(source[col]).dropna()
            if len(values) > 0 and np.isfinite(values.to_numpy(dtype=float)).any():
                keep.append(col)
            continue

        if len(groups) == 0:
            values = _to_numeric_excluding_not_included(source[col]).dropna()
            if len(values) > 0 and np.isfinite(values.to_numpy(dtype=float)).any():
                keep.append(col)
            continue

        has_all_groups = True
        for group in groups:
            group_df = source[source[group_col].astype(str) == str(group)]
            values = _to_numeric_excluding_not_included(group_df[col]).dropna()
            if len(values) == 0 or not np.isfinite(values.to_numpy(dtype=float)).any():
                has_all_groups = False
                break
        if has_all_groups:
            keep.append(col)
    return keep


def _merge_axis_range(axis_range=None, minimum=None, maximum=None):
    """Merge a `(min, max)` pair with explicit bound overrides."""
    lower = None
    upper = None

    if axis_range is not None:
        try:
            if len(axis_range) == 2:
                lower, upper = axis_range
        except TypeError:
            pass

    if minimum is not None:
        lower = minimum
    if maximum is not None:
        upper = maximum

    if lower is None and upper is None:
        return None
    return (lower, upper)


def _apply_axis_range(ax, axis_name, axis_range):
    """Apply a partial or full axis range, preserving the unset bound."""
    if axis_range is None:
        return

    if axis_name == 'x':
        getter = ax.get_xlim
        setter = ax.set_xlim
    elif axis_name == 'y':
        getter = ax.get_ylim
        setter = ax.set_ylim
    else:
        raise ValueError(f"Unsupported axis '{axis_name}'.")

    current_low, current_high = getter()
    low, high = axis_range
    low = current_low if low is None else float(low)
    high = current_high if high is None else float(high)

    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError(f"{axis_name}_axis limits must be finite numbers.")

    setter(low, high)


def _coerce_axis_limit_pair(value, *, name='axis'):
    """Coerce a `(low, high)` pair (or None) to a validated float tuple."""
    if value is None:
        return None
    try:
        low, high = value
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Axis limits for '{name}' must be a (min, max) pair."
        ) from exc
    if low is None and high is None:
        return None
    low_f = None if low is None else float(low)
    high_f = None if high is None else float(high)
    for bound in (low_f, high_f):
        if bound is not None and not np.isfinite(bound):
            raise ValueError(f"Axis limits for '{name}' must be finite numbers.")
    if low_f is not None and high_f is not None and low_f == high_f:
        raise ValueError(
            f"Axis limits for '{name}' must have distinct min and max."
        )
    return (low_f, high_f)


def _get_axis_limits_registry(experiment, *, create=False):
    """Return the experiment's axis-limit registry dict, or an empty dict."""
    if experiment is None:
        return {}
    current = getattr(experiment, 'axis_limits', None)
    if isinstance(current, dict):
        return current
    if create:
        setattr(experiment, 'axis_limits', {})
        return experiment.axis_limits
    return {}


def _lookup_axis_registry(experiment, column_name):
    """Look up a stored (low, high) axis range for `column_name`."""
    if experiment is None or column_name is None:
        return None
    registry = _get_axis_limits_registry(experiment)
    if not registry:
        return None
    stored = registry.get(column_name)
    if stored is None:
        return None
    try:
        return _coerce_axis_limit_pair(stored, name=str(column_name))
    except ValueError:
        return None


def _resolve_effective_axis_range(experiment, column_name, explicit_range):
    """Explicit range wins; otherwise consult the experiment registry."""
    if explicit_range is not None:
        return explicit_range
    return _lookup_axis_registry(experiment, column_name)


def _summary_for_queue_share(summary_df, specificity):
    """Return the subset of `summary_df` relevant for queue-share ranges.

    If `specificity` is a single filter tuple, apply it. If it is a queue of
    tuples, union across all queued filters so sibling sub-calls share the
    same combined range. ``None`` returns the summary unchanged.
    """
    if not isinstance(summary_df, pd.DataFrame) or summary_df.empty:
        return summary_df
    if specificity is None:
        return summary_df
    if _is_specificity_queue(specificity):
        frames = []
        for spec in _iter_specificities(specificity):
            subset = _filter_df_by_specificity(summary_df, spec)
            if isinstance(subset, pd.DataFrame) and not subset.empty:
                frames.append(subset)
        if not frames:
            return summary_df
        # Keep duplicate rows: we only need the frame for min/max of numeric
        # columns, and summary columns can contain unhashable values (lists)
        # that would break a dedup pass.
        return pd.concat(frames)
    filtered = _filter_df_by_specificity(summary_df, specificity)
    if isinstance(filtered, pd.DataFrame) and not filtered.empty:
        return filtered
    return summary_df


def _compute_queue_shared_ranges(df_source, columns):
    """Return `{column: (low, high)}` for reused columns with finite data.

    Columns not present in `df_source` or with <2 distinct finite values are
    skipped so downstream auto-scaling can still fall back to matplotlib.
    """
    if df_source is None or not isinstance(df_source, pd.DataFrame):
        return {}
    result = {}
    for col in columns:
        if col is None or col in result:
            continue
        if col not in df_source.columns:
            continue
        series = _to_numeric_excluding_not_included(df_source[col]).dropna()
        if len(series) == 0:
            continue
        low = float(series.min())
        high = float(series.max())
        if not (np.isfinite(low) and np.isfinite(high)) or low == high:
            continue
        result[col] = (low, high)
    return result


def set_axis_limits(experiment, mapping=None, **kwargs):
    """Register manual axis ranges on `experiment` for reuse across plots.

    The registry is consulted by plotting functions (regressions, scatter 3D,
    histograms, ridgelines, ECDFs, mean bars) when their own ``x_range`` /
    ``y_range`` / ``ymax`` parameters are not passed. Explicit per-call bounds
    always override the registry.

    Parameters
    ----------
    experiment : Experiment-like
        Any object; the dict is stored on ``experiment.axis_limits``.
    mapping : dict, optional
        ``{column: (low, high)}``. Pass ``None`` as the value to clear a key.
    **kwargs
        Shorthand for ``{column: (low, high)}`` entries.

    Examples
    --------
    >>> set_axis_limits(exp, {'PeriodMean': (22.0, 26.0)})
    >>> set_axis_limits(exp, PeriodMean=(22.0, 26.0))
    """
    registry = _get_axis_limits_registry(experiment, create=True)
    merged = {}
    if mapping is not None:
        if not isinstance(mapping, dict):
            raise TypeError("`mapping` must be a dict of column -> (min, max).")
        merged.update(mapping)
    merged.update(kwargs)
    for col, rng in merged.items():
        key = str(col)
        if rng is None:
            registry.pop(key, None)
            continue
        coerced = _coerce_axis_limit_pair(rng, name=key)
        if coerced is None:
            registry.pop(key, None)
            continue
        registry[key] = coerced
    return dict(registry)


def clear_axis_limits(experiment, columns=None):
    """Remove registry entries (all, or the given column subset)."""
    registry = _get_axis_limits_registry(experiment)
    if not registry:
        return {}
    if columns is None:
        registry.clear()
        return dict(registry)
    if isinstance(columns, str):
        columns = [columns]
    for col in columns:
        registry.pop(str(col), None)
    return dict(registry)


def lock_axis_limits(experiment, columns=None, *, source='summary',
                     overwrite=False):
    """Auto-populate the registry from the experiment's data ranges.

    Parameters
    ----------
    experiment : Experiment-like
        Source of data tables.
    columns : list or None
        Specific columns to lock. ``None`` = every numeric column in `source`.
    source : str
        ``'summary'`` uses ``experiment.summary``; any other value is treated
        as a marker key and uses ``experiment.data[source].df``.
    overwrite : bool
        By default, existing registry entries are preserved. Set True to
        replace them with freshly computed bounds.

    Returns
    -------
    dict
        A snapshot of the registry after locking.
    """
    registry = _get_axis_limits_registry(experiment, create=True)
    if str(source) == 'summary':
        df = getattr(experiment, 'summary', None)
    else:
        try:
            df = experiment.data[source].df.reset_index()
        except (AttributeError, KeyError) as exc:
            raise ValueError(
                f"Unknown lock_axis_limits source '{source}'."
            ) from exc
    if not isinstance(df, pd.DataFrame) or df.empty:
        return dict(registry)

    if columns is None:
        target_cols = [
            c for c in df.columns
            if pd.api.types.is_numeric_dtype(df[c])
            or df[c].dtype == object
        ]
    elif isinstance(columns, str):
        target_cols = [columns]
    else:
        target_cols = [str(c) for c in columns]

    for col in target_cols:
        if col not in df.columns:
            continue
        if not overwrite and col in registry:
            continue
        series = _to_numeric_excluding_not_included(df[col]).dropna()
        if len(series) == 0:
            continue
        low = float(series.min())
        high = float(series.max())
        if not (np.isfinite(low) and np.isfinite(high)) or low == high:
            continue
        registry[col] = (low, high)
    return dict(registry)


def _clip_segment_to_rect(x0, y0, x1, y1, x_limits, y_limits):
    """Clip a line segment to an axis-aligned rectangle."""
    xmin, xmax = sorted((float(x_limits[0]), float(x_limits[1])))
    ymin, ymax = sorted((float(y_limits[0]), float(y_limits[1])))

    dx = float(x1) - float(x0)
    dy = float(y1) - float(y0)
    t0 = 0.0
    t1 = 1.0

    for p, q in (
        (-dx, float(x0) - xmin),
        (dx, xmax - float(x0)),
        (-dy, float(y0) - ymin),
        (dy, ymax - float(y0)),
    ):
        if p == 0.0:
            if q < 0.0:
                return None
            continue

        t = q / p
        if p < 0.0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)

    return (
        (float(x0) + t0 * dx, float(y0) + t0 * dy),
        (float(x0) + t1 * dx, float(y0) + t1 * dy),
    )


def _axis_lower_bound_is_explicit(experiment, column, explicit_range):
    """Return True when the lower bound of an axis was pinned by the caller.

    Used by plotting functions that want to pad the bottom/left of an axis
    without overriding a user-supplied lower bound or a registry entry.
    """
    if explicit_range is not None:
        try:
            low = explicit_range[0]
        except (TypeError, IndexError):
            low = None
        if low is not None:
            return True
    reg = _lookup_axis_registry(experiment, column)
    if reg is not None and reg[0] is not None:
        return True
    return False


def _axis_upper_bound_is_explicit(experiment, column, explicit_range):
    """Mirror of `_axis_lower_bound_is_explicit` for the top/right side."""
    if explicit_range is not None:
        try:
            high = explicit_range[1]
        except (TypeError, IndexError):
            high = None
        if high is not None:
            return True
    reg = _lookup_axis_registry(experiment, column)
    if reg is not None and reg[1] is not None:
        return True
    return False


def _pad_axis_bounds(ax, margin, *,
                     pad_x_low=True, pad_x_high=True,
                     pad_y_low=True, pad_y_high=True):
    """Extend x/y bounds so the nearest data point sits at ``margin`` fraction
    of the axis span from each spine.

    Each side is padded independently when its current margin is below the
    target. When both sides of an axis need padding we solve simultaneously,
    because extending one side changes the span and therefore the fraction
    on the opposite side. If the current view already satisfies the target
    on a side, the axis is left alone — we only ever extend, never shrink.
    """
    if margin is None:
        return
    try:
        margin_f = float(margin)
    except (TypeError, ValueError):
        return
    if not np.isfinite(margin_f) or margin_f <= 0 or margin_f >= 0.5:
        return
    _pad_axis_bounds_one(ax, 'x', margin_f, pad_x_low, pad_x_high)
    _pad_axis_bounds_one(ax, 'y', margin_f, pad_y_low, pad_y_high)


def _scatter_axis_extent(ax, axis_index):
    """Return (min, max) from scatter-collection offsets on a given axis.

    Prefers matplotlib ``PathCollection`` offsets (scatter markers) so that
    extrapolated regression lines — whose clipped endpoints can sit far
    outside the scatter cloud — don't distort the margin calculation.
    """
    vals = []
    for coll in getattr(ax, 'collections', []):
        try:
            offsets = np.asarray(coll.get_offsets(), dtype=float)
        except Exception:
            continue
        if offsets.ndim != 2 or offsets.shape[0] == 0 or offsets.shape[1] <= axis_index:
            continue
        col = offsets[:, axis_index]
        finite = col[np.isfinite(col)]
        if finite.size:
            vals.append(finite)
    if not vals:
        return (None, None)
    all_vals = np.concatenate(vals)
    return (float(np.min(all_vals)), float(np.max(all_vals)))


def _pad_axis_bounds_one(ax, axis_name, margin_f, pad_low, pad_high):
    if not pad_low and not pad_high:
        return
    if axis_name == 'x':
        lo, hi = ax.get_xlim()
        dmin, dmax = _scatter_axis_extent(ax, 0)
        setter = ax.set_xlim
        datalim = ax.dataLim.intervalx
    else:
        lo, hi = ax.get_ylim()
        dmin, dmax = _scatter_axis_extent(ax, 1)
        setter = ax.set_ylim
        datalim = ax.dataLim.intervaly
    if dmin is None:
        try:
            dmin = float(datalim[0])
        except Exception:
            return
    if dmax is None:
        try:
            dmax = float(datalim[1])
        except Exception:
            return
    if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo
            and np.isfinite(dmin) and np.isfinite(dmax) and dmax > dmin):
        return
    span = hi - lo
    low_frac = (dmin - lo) / span
    high_frac = (hi - dmax) / span
    need_low = pad_low and low_frac < margin_f
    need_high = pad_high and high_frac < margin_f
    if not need_low and not need_high:
        return
    if need_low and need_high:
        data_span = dmax - dmin
        new_span = data_span / (1.0 - 2.0 * margin_f)
        pad = margin_f * new_span
        new_lo = dmin - pad
        new_hi = dmax + pad
    elif need_low:
        new_lo = (dmin - margin_f * hi) / (1.0 - margin_f)
        new_hi = hi
    else:
        new_hi = (dmax - margin_f * lo) / (1.0 - margin_f)
        new_lo = lo
    # Never shrink.
    if new_lo > lo:
        new_lo = lo
    if new_hi < hi:
        new_hi = hi
    if new_lo == lo and new_hi == hi:
        return
    setter(new_lo, new_hi)


def _clip_regression_line_to_axes(line, x_limits, y_limits):
    """Trim a regression line so its data stays inside the active axis box."""
    if line is None:
        return

    x_data = np.asarray(line.get_xdata(orig=False), dtype=float)
    y_data = np.asarray(line.get_ydata(orig=False), dtype=float)
    finite = np.isfinite(x_data) & np.isfinite(y_data)
    if np.count_nonzero(finite) < 2:
        return

    x_vals = x_data[finite]
    y_vals = y_data[finite]
    clipped = _clip_segment_to_rect(
        x_vals[0], y_vals[0],
        x_vals[-1], y_vals[-1],
        x_limits=x_limits,
        y_limits=y_limits,
    )
    if clipped is None:
        line.set_data([], [])
        return

    (x0, y0), (x1, y1) = clipped
    line.set_data([x0, x1], [y0, y1])


def _coerce_bool_like(series: pd.Series) -> pd.Series:
    """Coerce mixed binary-ish values to bool, treating NaN as False."""
    s = series.copy()
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(s):
        return s.fillna(0).ne(0)
    text = s.astype(str).str.strip().str.lower()
    mapped = text.map({
        "1": True, "0": False,
        "true": True, "false": False,
        "yes": True, "no": False,
        "y": True, "n": False,
        "t": True, "f": False,
    })
    numeric = pd.to_numeric(text, errors="coerce")
    fallback = numeric.fillna(0).ne(0)
    mapped = mapped.where(mapped.notna(), fallback)
    return mapped.fillna(False).astype(bool)


def _filter_marker_df_for_context(ctx: Context, df: pd.DataFrame) -> pd.DataFrame:
    """
    Robust marker-row filtering for the current context.

    Prefer direct factor/condition columns in marker data. If those are missing
    or use a different naming format, fall back to AnimalName membership from
    the corresponding summary subset.
    """
    out = df

    def _norm(series: pd.Series) -> pd.Series:
        return series.astype(str).str.strip().str.casefold()

    def _norm_animal(series: pd.Series) -> pd.Series:
        return series.map(normalize_animal_name)

    # Factor context (highest priority when iterating factors)
    if ctx.factor is not None and ctx.factor_value is not None:
        if ctx.factor in out.columns:
            target = str(ctx.factor_value).strip().casefold()
            direct = out[_norm(out[ctx.factor]) == target]
            if len(direct) > 0:
                out = direct
        elif "AnimalName" in out.columns and "AnimalName" in ctx.factor_df.columns:
            allowed = set(_norm_animal(ctx.factor_df["AnimalName"]).tolist())
            out = out[_norm_animal(out["AnimalName"]).isin(allowed)]

    # Condition context
    if ctx.condition is not None:
        if "Condition" in out.columns:
            target = str(ctx.condition).strip().casefold()
            direct = out[_norm(out["Condition"]) == target]
            if len(direct) > 0:
                out = direct
        elif "AnimalName" in out.columns and "AnimalName" in ctx.condition_df.columns:
            allowed = set(_norm_animal(ctx.condition_df["AnimalName"]).tolist())
            out = out[_norm_animal(out["AnimalName"]).isin(allowed)]

    # Animal context
    if ctx.animal is not None:
        if "AnimalName" in out.columns:
            target = normalize_animal_name(ctx.animal)
            out = out[_norm_animal(out["AnimalName"]) == target]
        elif "Region" in out.columns and "Region" in ctx.animal_df.columns:
            allowed_regions = set(_norm(ctx.animal_df["Region"]).tolist())
            out = out[_norm(out["Region"]).isin(allowed_regions)]

    # Region context
    if ctx.region is not None and "Region" in out.columns:
        target = str(ctx.region).strip().casefold()
        out = out[_norm(out["Region"]) == target]

    return out


def plot_images(experiment, markers=None,
                animal_filter=None, roi_filter=None,
                save=True, ncols=None,
                max_images=None, tile_size=4.0,
                title=None, show=True, verbose=True,
                tile_gap=0.0, tile_gap_units="points",
                image_backend="auto",
                merge=False,
                merge_label="Merge",
                draw_rois=None,
                scale_bar=False,
                scale_bar_location="bottom left",
                scale_bar_size=None,
                scale_bar_units="microns",
                image_width_microns=None,
                pixel_size=None,
                fast_loading=False,
                preview_max_dim=None,
                image_adjustments=None,
                edit_mode=False,
                use_existing_edits=False,
                image_workers=None,
                progress=True,
                _preview_single_image=False):
    if edit_mode:
        if hasattr(experiment, "getImageTable"):
            image_df = experiment.getImageTable(include_summary=True)
        else:
            image_df = getattr(experiment, "images", None)
            if not isinstance(image_df, pd.DataFrame) and hasattr(experiment, "importImages"):
                image_df = experiment.importImages(progress=False)
        if not isinstance(image_df, pd.DataFrame) or image_df.empty:
            raise ValueError("No imported images were found.")
        work_df = _filter_df_by_values(image_df, "Marker", markers)
        work_df = _filter_images_to_marker_coherent_experiments(work_df, markers)
        work_df = _filter_df_by_string_match(work_df, "AnimalName", animal_filter)
        work_df = _filter_df_by_string_match(work_df, "ROI", roi_filter)
        work_df = _order_image_rows_by_source(experiment, work_df, marker_names=markers).reset_index(drop=True)
        if max_images is not None and not merge:
            work_df = work_df.head(int(max_images)).copy()
        if work_df.empty:
            raise ValueError("No images matched the requested marker/animal_filter/roi_filter filters.")
        marker_order = _resolve_requested_image_marker_order(work_df, markers)
        effective_adjustments = _resolve_effective_image_adjustments(
            experiment,
            marker_order,
            animal_filter=animal_filter,
            image_adjustments=image_adjustments,
            use_existing_edits=use_existing_edits,
        )
        preview_dim = int(preview_max_dim) if preview_max_dim is not None else 512
        return _launch_image_edit_mode(
            marker_order,
            render_preview=lambda adjustments, preview_scope="full": plot_images(
                experiment,
                markers=markers,
                animal_filter=animal_filter,
                roi_filter=roi_filter,
                save=False,
                ncols=ncols,
                max_images=max_images,
                tile_size=tile_size,
                title=title,
                show=False,
                verbose=False,
                tile_gap=tile_gap,
                tile_gap_units=tile_gap_units,
                image_backend=image_backend,
                merge=merge,
                merge_label=merge_label,
                draw_rois=draw_rois,
                scale_bar=scale_bar,
                scale_bar_location=scale_bar_location,
                scale_bar_size=scale_bar_size,
                scale_bar_units=scale_bar_units,
                image_width_microns=image_width_microns,
                pixel_size=pixel_size,
                fast_loading=True,
                preview_max_dim=preview_dim,
                image_adjustments=adjustments,
                edit_mode=False,
                use_existing_edits=False,
                image_workers=image_workers,
                progress=False,
                _preview_single_image=(str(preview_scope).strip().casefold() == "single"),
            ),
            render_final=lambda adjustments: _persist_image_edits_and_return(
                experiment,
                plot_images(
                    experiment,
                    markers=markers,
                    animal_filter=animal_filter,
                    roi_filter=roi_filter,
                    save=save,
                    ncols=ncols,
                    max_images=max_images,
                    tile_size=tile_size,
                    title=title,
                    show=show,
                    verbose=verbose,
                    tile_gap=tile_gap,
                    tile_gap_units=tile_gap_units,
                    image_backend=image_backend,
                    merge=merge,
                    merge_label=merge_label,
                    draw_rois=draw_rois,
                    scale_bar=scale_bar,
                    scale_bar_location=scale_bar_location,
                    scale_bar_size=scale_bar_size,
                    scale_bar_units=scale_bar_units,
                    image_width_microns=image_width_microns,
                    pixel_size=pixel_size,
                    fast_loading=fast_loading,
                    preview_max_dim=preview_max_dim,
                    image_adjustments=adjustments,
                    edit_mode=False,
                    use_existing_edits=False,
                    image_workers=image_workers,
                    progress=progress,
                ),
                marker_names=marker_order,
                adjustments=adjustments,
                animal_filter=animal_filter,
            ),
            initial_adjustments=effective_adjustments,
            window_title="Edit Image Plot",
        )

    progress_state = _image_progress_tracker(
        "plot_images",
        total=5,
        enabled=progress,
    )

    _progress_start_item(progress_state, "Prepare image table")
    if hasattr(experiment, "getImageTable"):
        image_df = experiment.getImageTable(include_summary=True)
    else:
        image_df = getattr(experiment, "images", None)
        if not isinstance(image_df, pd.DataFrame) and hasattr(experiment, "importImages"):
            image_df = experiment.importImages(progress=False)

    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        raise ValueError("No imported images were found.")
    _image_progress_finish(progress_state, "Prepare image table", detail=f"{len(image_df)} available images")

    _progress_start_item(progress_state, "Filter images")
    work_df = _filter_df_by_values(image_df, "Marker", markers)
    work_df = _filter_images_to_marker_coherent_experiments(work_df, markers)
    work_df = _filter_df_by_string_match(work_df, "AnimalName", animal_filter)
    work_df = _filter_df_by_string_match(work_df, "ROI", roi_filter)
    work_df = _order_image_rows_by_source(experiment, work_df, marker_names=markers)
    work_df = work_df.reset_index(drop=True)
    if bool(_preview_single_image):
        work_df = _limit_image_df_for_single_preview(
            work_df,
            marker_order=markers,
            merge=merge,
        )

    if max_images is not None and not merge:
        work_df = work_df.head(int(max_images)).copy()

    if work_df.empty:
        raise ValueError("No images matched the requested marker/animal_filter/roi_filter filters.")

    image_panels, marker_order = _resolve_image_marker_panels(
        work_df,
        markers,
        merge=merge,
        merge_label=merge_label,
    )
    if len(image_panels) == 0 or len(marker_order) == 0:
        raise ValueError("No requested image marker panels were available to plot.")
    effective_image_adjustments = _resolve_effective_image_adjustments(
        experiment,
        marker_order,
        animal_filter=animal_filter,
        image_adjustments=image_adjustments,
        use_existing_edits=use_existing_edits,
    )
    single_marker_group_by_animal = len(image_panels) == 1 and len(_image_panel_markers(image_panels[0])) == 1
    row_records, forced_nrows, forced_ncols = _build_image_tile_slots(
        work_df,
        image_panels,
        merge_label=merge_label,
        single_marker_group_by_animal=single_marker_group_by_animal,
    )
    n_images = len([row for row in row_records if row is not None])
    if n_images == 0:
        raise ValueError("No images matched the requested marker/animal_filter/roi_filter filters.")
    _image_progress_finish(
        progress_state,
        "Filter images",
        detail=f"{n_images} tiles | {len(image_panels)} panels",
    )
    draw_roi_keys = _image_draw_roi_key_set(draw_rois, image_panels)

    loaded_tiles = _preload_image_rows(
        row_records,
        image_backend=image_backend,
        fast_loading=fast_loading,
        preview_max_dim=preview_max_dim,
        image_adjustments=effective_image_adjustments,
        image_workers=image_workers,
        progress_state=progress_state,
        progress_label="Load image tiles",
    )

    valid_tiles = [
        tile for tile in loaded_tiles.values()
        if isinstance(tile, np.ndarray) and tile.ndim >= 2 and tile.shape[0] > 0 and tile.shape[1] > 0
    ]
    if len(valid_tiles) > 0:
        tile_width_over_height = float(np.median([
            tile.shape[1] / tile.shape[0] for tile in valid_tiles
        ]))
    else:
        tile_width_over_height = 1.0
    tile_width_over_height = max(0.05, tile_width_over_height)
    content_top = 0.95
    if forced_ncols is not None and forced_nrows is not None:
        ncols = int(forced_ncols)
        nrows = int(forced_nrows)
    elif ncols is None:
        ncols = int(min(4, max(1, np.ceil(np.sqrt(n_images)))))
        ncols = max(1, int(ncols))
        nrows = int(np.ceil(len(row_records) / ncols))
    else:
        ncols = max(1, int(ncols))
        nrows = int(np.ceil(len(row_records) / ncols))

    row_labels = []
    for row_index in range(nrows):
        row_slice = row_records[row_index * ncols:(row_index + 1) * ncols]
        row_labels.append(
            _image_row_group_label(
                row_slice,
                combine_rois=single_marker_group_by_animal,
            )
        )

    has_row_labels = any(label != "" for label in row_labels)
    axis_height_in = float(tile_size)
    axis_width_in = axis_height_in * tile_width_over_height
    row_label_width_in = 0.55 if has_row_labels else 0.0
    gap_layout = _resolve_image_gap_layout(
        tile_gap=tile_gap,
        tile_gap_units=tile_gap_units,
        axis_width_in=axis_width_in,
        axis_height_in=axis_height_in,
    )

    _progress_start_item(progress_state, "Render figure")
    fig, axes = plt.subplots(
        nrows,
        ncols,
        squeeze=False,
        figsize=(
            row_label_width_in + (axis_width_in * ncols) + (gap_layout["gap_width_in"] * max(0, ncols - 1)),
            ((axis_height_in * nrows) + (gap_layout["gap_height_in"] * max(0, nrows - 1))) / content_top,
        ),
        gridspec_kw={"wspace": gap_layout["wspace"], "hspace": gap_layout["hspace"]},
    )

    for idx, (ax, row) in enumerate(zip(axes.flat, row_records)):
        if row is None:
            ax.axis("off")
            continue
        tile = None
        col_index = (idx % ncols) if ncols > 0 else None
        panel = _resolve_image_panel_for_tile(
            image_panels,
            row,
            col_index=col_index,
        )
        try:
            tile = loaded_tiles.get(idx)
            if isinstance(tile, Exception):
                raise tile
            if tile is None:
                tile = _resolve_image_tile(
                    row,
                    image_backend=image_backend,
                    fast_loading=fast_loading,
                    preview_max_dim=preview_max_dim,
                    image_adjustments=effective_image_adjustments,
                )
            if tile.ndim == 2:
                ax.imshow(tile, cmap="gray")
            else:
                ax.imshow(tile)
        except Exception as exc:
            ax.text(0.5, 0.5, f"Could not load image\n{exc}", ha="center", va="center", fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_box_aspect(1.0 / tile_width_over_height)
        if tile is not None:
            _draw_scale_bar(
                ax,
                row,
                tile,
                scale_bar=scale_bar,
                scale_bar_location=scale_bar_location,
                scale_bar_size=scale_bar_size,
                scale_bar_units=scale_bar_units,
                image_width_microns=image_width_microns,
                pixel_size=pixel_size,
            )
            if panel is not None and _image_panel_key(panel) in draw_roi_keys:
                _draw_image_panel_roi_outline(ax, experiment, row)
        ax.annotate(
            _image_tile_label(row),
            xy=(0.02, 0.98),
            xycoords="axes fraction",
            ha="left",
            va="top",
            color="white",
            fontsize=20,
            fontweight="bold",
        )
        for spine in ax.spines.values():
            spine.set_visible(False)

    for ax in axes.flat[len(row_records):]:
        ax.axis("off")

    fig_width_in = row_label_width_in + (axis_width_in * ncols) + (gap_layout["gap_width_in"] * max(0, ncols - 1))
    left_frac = (row_label_width_in / fig_width_in) if fig_width_in > 0 else 0.0

    fig.suptitle(_image_figure_title(work_df, title=title), fontsize=16)
    fig.subplots_adjust(
        left=left_frac,
        right=1.0,
        bottom=0.0,
        top=content_top,
        wspace=gap_layout["wspace"],
        hspace=gap_layout["hspace"],
    )

    if has_row_labels and ncols > 0:
        label_x = left_frac * 0.5
        for row_index, label in enumerate(row_labels):
            if label == "":
                continue
            row_ax = axes[row_index, 0]
            pos = row_ax.get_position()
            fig.text(
                label_x,
                (pos.y0 + pos.y1) * 0.5,
                label,
                rotation=90,
                ha="center",
                va="center",
                color="black",
                fontsize=12,
                fontweight="bold",
            )
    _image_progress_finish(progress_state, "Render figure", detail=f"{nrows} rows x {ncols} cols")

    save_path = None
    save_item = "Save figure" if save else "Finalize"
    _progress_start_item(progress_state, save_item)
    if save:
        if not hasattr(experiment, "image_fig_path"):
            experiment.createSavePaths()
        save_path = save_fig(
            fig,
            experiment.image_fig_path,
            f"{_image_save_name(work_df)} merged" if merge else _image_save_name(work_df),
            pad_inches=0.25,
            verbose=verbose,
        )
        save_detail = save_path
    else:
        save_detail = "Figure ready"

    fig.PyFLASH_image_df = work_df
    fig.PyFLASH_save_path = save_path
    fig.PyFLASH_image_adjustments = effective_image_adjustments
    if not show:
        plt.close(fig)
    _image_progress_finish(progress_state, save_item, detail=save_detail)
    return fig


def select_representative_images(source, markers=None,
                                 animal_filter=None, roi_filter=None,
                                 merge=True,
                                 merge_label="Merge",
                                 stats_columns=None,
                                 fast_loading=True, preview_max_dim=220,
                                 thumbnail_size=170,
                                 image_backend="auto", image_workers=None,
                                 block_layout="horizontal", block_columns=1,
                                 autosave_pickle=True,
                                 progress=True):
    import tkinter as tk
    from tkinter import ttk
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    progress_state = _image_progress_tracker(
        "select_representative_images",
        total=5,
        enabled=progress,
    )

    _progress_start_item(progress_state, "Prepare image table")
    if hasattr(source, "getImageTable"):
        image_df = source.getImageTable(include_summary=True)
    else:
        image_df = getattr(source, "images", None)
        if not isinstance(image_df, pd.DataFrame) and hasattr(source, "importImages"):
            image_df = source.importImages(progress=False)

    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        raise ValueError("No imported images were found.")
    _image_progress_finish(progress_state, "Prepare image table", detail=f"{len(image_df)} available images")

    _progress_start_item(progress_state, "Build representative blocks")
    work_df = _filter_df_by_values(image_df, "Marker", markers)
    work_df = _filter_images_to_marker_coherent_experiments(work_df, markers)
    work_df = _filter_df_by_string_match(work_df, "AnimalName", animal_filter)
    work_df = _filter_df_by_string_match(work_df, "ROI", roi_filter)
    if work_df.empty:
        raise ValueError("No images matched the requested marker/animal_filter/roi_filter filters.")

    marker_order = _resolve_requested_image_marker_order(work_df, markers)
    blocks, block_key_cols = _collect_representative_image_blocks(
        source,
        work_df,
        marker_order,
        merge=merge,
        merge_label=merge_label,
    )
    if len(blocks) == 0:
        raise ValueError("No representative image blocks could be created from the filtered images.")
    total_rows = sum(len(block["rows"]) for block in blocks)
    _image_progress_finish(progress_state, "Build representative blocks", detail=f"{len(blocks)} blocks | {total_rows} candidate rows")

    loaded_tiles = _preload_representative_tiles(
        blocks,
        image_backend=image_backend,
        fast_loading=fast_loading,
        preview_max_dim=preview_max_dim,
        image_workers=image_workers,
        progress_state=progress_state,
        progress_label="Load representative tiles",
    )

    def _array_to_photo(tile):
        rgb = _image_array_to_rgb_float(tile)
        arr = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
        image = Image.fromarray(arr)
        image.thumbnail((int(thumbnail_size), int(thumbnail_size)), Image.Resampling.BILINEAR)
        return ImageTk.PhotoImage(image)

    def _vertical_label_photo(text, font_size=16, fg="black"):
        text_s = str(text).strip()
        if text_s == "":
            image = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
            return ImageTk.PhotoImage(image)
        try:
            font = ImageFont.truetype("arial.ttf", int(font_size))
        except Exception:
            font = ImageFont.load_default()
        dummy = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.multiline_textbbox((0, 0), text_s, font=font, spacing=3, align="center")
        width = max(1, int(bbox[2] - bbox[0] + 8))
        height = max(1, int(bbox[3] - bbox[1] + 8))
        image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (4 - bbox[0], 4 - bbox[1]),
            text_s,
            font=font,
            fill=fg,
            spacing=3,
            align="center",
        )
        rotated = image.rotate(90, expand=True)
        return ImageTk.PhotoImage(rotated)

    selection_map = {}
    row_widgets = {}
    for block in blocks:
        selected_row = next((row for row in block["rows"] if row.get("is_selected")), None)
        if selected_row is not None:
            selection_map[block["block_key"]] = selected_row["selection_record"].copy()

    _apply_representative_selections(source, list(selection_map.values()), marker_order=marker_order)

    default_root = tk._default_root
    owns_root = default_root is None
    window = tk.Tk() if owns_root else tk.Toplevel(default_root)
    window.title(f"Representative Image Selector | {getattr(source, 'name', 'Images')}")
    window.geometry("1600x900")

    top_bar = tk.Frame(window, bg="white")
    top_bar.pack(side="top", fill="x")
    status_var = tk.StringVar(value="Click a row to choose one representative per block. Double-click an image to zoom.")
    status_label = tk.Label(top_bar, textvariable=status_var, anchor="w", bg="white")
    status_label.pack(side="left", fill="x", expand=True, padx=8, pady=6)

    dirty_state = {"value": False}
    stats_handles = []
    stats_canvas_refs = []

    def _commit_pickle(force=False):
        if not autosave_pickle and not force:
            return None
        save_path = _save_representative_source(source, verbose=False)
        export_dirs = _export_representative_assets(
            source,
            representative_df=_get_representative_image_table(source),
            image_df=image_df,
            marker_order=marker_order,
        )
        if save_path is not None and len(export_dirs) > 0:
            dirty_state["value"] = False
            status_var.set(f"Representative selections saved to {save_path} and exported to {export_dirs[0]}")
        elif save_path is not None:
            dirty_state["value"] = False
            status_var.set(f"Representative selections saved to {save_path}")
        elif len(export_dirs) > 0:
            dirty_state["value"] = False
            status_var.set(f"Representative selections exported to {export_dirs[0]}")
        else:
            status_var.set("Representative selections updated in memory. No pickle path was available.")
        return save_path

    def _sync_source():
        _apply_representative_selections(source, list(selection_map.values()), marker_order=marker_order)
        dirty_state["value"] = True

    def _refresh_stats_highlights():
        if len(stats_handles) == 0:
            return
        current_records = list(selection_map.values())
        for handle in stats_handles:
            summary_df = handle["summary"]
            metric_col = handle["metric_col"]
            exp_name = handle["experiment_name"]
            condition_order = handle["condition_order"]
            cond_positions = {cond: idx for idx, cond in enumerate(condition_order)}
            xs, ys = [], []
            for record in current_records:
                record_exp = str(record.get("Experiment", "")).strip() or str(getattr(source, "name", "")).strip()
                if record_exp != exp_name:
                    continue
                animal_name = str(record.get("AnimalName", "")).strip()
                condition_name = str(record.get("Condition", "")).strip()
                if animal_name == "" or condition_name not in cond_positions or metric_col not in summary_df.columns:
                    continue
                mask = summary_df["AnimalName"].astype(str) == animal_name if "AnimalName" in summary_df.columns else pd.Series(False, index=summary_df.index)
                if "Condition" in summary_df.columns and condition_name != "":
                    mask = mask & (summary_df["Condition"].astype(str) == condition_name)
                values = _to_numeric_excluding_not_included(summary_df.loc[mask, metric_col]).dropna()
                for value in values.tolist():
                    xs.append(cond_positions[condition_name])
                    ys.append(float(value))
            offsets = np.column_stack([xs, ys]) if len(xs) > 0 else np.empty((0, 2))
            handle["artist"].set_offsets(offsets)
            try:
                handle["canvas"].draw_idle()
            except Exception:
                pass

    def _row_style(block_key, selected_key):
        for row_key, widgets in row_widgets.get(block_key, {}).items():
            selected = row_key == selected_key
            bg = "#DCEEFF" if selected else "white"
            edge = "#2A6FBA" if selected else "#D0D0D0"
            container = widgets.get("container")
            if container is not None:
                container.configure(bg=bg, highlightbackground=edge, highlightcolor=edge)
            for widget in widgets.get("background_widgets", []):
                try:
                    widget.configure(bg=bg)
                except Exception:
                    pass

    def _select_row(block, row):
        selection_map[block["block_key"]] = row["selection_record"].copy()
        selection_map[block["block_key"]]["SelectedAt"] = pd.Timestamp.now().isoformat(timespec="seconds")
        _sync_source()
        _row_style(block["block_key"], row["selection_key"])
        _refresh_stats_highlights()
        status_var.set(f"Selected {row['row_label']} for {block['title']}")

    def _zoom_tile(tile_row, title_text):
        try:
            tile = _resolve_image_tile(
                tile_row,
                image_backend=image_backend,
                fast_loading=False,
                preview_max_dim=None,
            )
        except Exception as exc:
            status_var.set(f"Zoom failed: {exc}")
            return
        fig, ax = plt.subplots(figsize=(8, 8))
        if tile.ndim == 2:
            ax.imshow(tile, cmap="gray")
        else:
            ax.imshow(tile)
        ax.set_title(title_text)
        ax.set_xticks([])
        ax.set_yticks([])
        plt.show()

    save_button = ttk.Button(top_bar, text="Save", command=lambda: _commit_pickle(force=True))
    save_button.pack(side="right", padx=8, pady=6)

    _progress_start_item(progress_state, "Build stats window")
    stats_specs = _resolve_representative_summary_specs(
        source,
        blocks,
        marker_order,
        stats_columns=stats_columns,
    )
    stats_header_text = _representative_stats_header_text(stats_columns=stats_columns)
    stats_window = tk.Toplevel(window)
    stats_window.title(f"Representative Metrics | {getattr(source, 'name', 'Images')}")
    stats_window.geometry("1200x850")
    stats_window.configure(bg="white")
    stats_header = tk.Label(
        stats_window,
        text=stats_header_text,
        bg="white",
        font=("Segoe UI", 13, "bold"),
        anchor="w",
    )
    stats_header.pack(side="top", fill="x", padx=10, pady=(10, 6))

    stats_notebook = ttk.Notebook(stats_window)
    stats_notebook.pack(side="top", fill="both", expand=True, padx=8, pady=8)
    exp_lookup = _representative_experiment_lookup(source)
    if len(stats_specs) == 0:
        empty_tab = ttk.Frame(stats_notebook)
        stats_notebook.add(empty_tab, text="Summary")
        empty_label = tk.Label(
            empty_tab,
            text=f"No summary columns matching {', '.join(_normalize_representative_stats_columns(stats_columns))} were available for the requested markers.",
            bg="white",
            justify="center",
        )
        empty_label.pack(fill="both", expand=True, padx=16, pady=16)
    else:
        for spec in stats_specs:
            tab = ttk.Frame(stats_notebook)
            stats_notebook.add(tab, text=spec["experiment_name"])
            ncols_stats = max(1, len(spec["marker_specs"]))
            nrows_stats = max(1, max(len(marker_spec["metrics"]) for marker_spec in spec["marker_specs"]))
            fig, axes = plt.subplots(
                nrows_stats,
                ncols_stats,
                figsize=(4.6 * ncols_stats, 3.3 * nrows_stats),
                squeeze=False,
            )
            summary_df = spec["summary"]
            exp_obj = exp_lookup.get(spec["experiment_name"], source)
            condition_colors = _condition_color_map(exp_obj)
            spec_handles = []
            for col_idx, marker_spec in enumerate(spec["marker_specs"]):
                metrics = marker_spec["metrics"]
                for row_idx in range(nrows_stats):
                    ax = axes[row_idx, col_idx]
                    if row_idx >= len(metrics):
                        ax.axis("off")
                        continue
                    metric = metrics[row_idx]
                    handle = _plot_representative_metric_axis(
                        ax,
                        summary_df,
                        spec["condition_order"],
                        metric["column"],
                        condition_colors=condition_colors,
                    )
                    handle["experiment_name"] = spec["experiment_name"]
                    spec_handles.append(handle)
                    ax.set_xlabel("" if row_idx == 0 else "Condition")
                    if col_idx == 0:
                        ax.set_ylabel("Animal values")
                    else:
                        ax.set_ylabel("")
                    if row_idx == 0:
                        ax.text(
                            0.5,
                            1.18,
                            str(marker_spec["marker"]),
                            transform=ax.transAxes,
                            ha="center",
                            va="bottom",
                            fontsize=12,
                            fontweight="bold",
                        )
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=tab)
            canvas.draw()
            canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
            stats_canvas_refs.append((fig, canvas))
            for handle in spec_handles:
                handle["canvas"] = canvas
                stats_handles.append(handle)
    _refresh_stats_highlights()
    _image_progress_finish(progress_state, "Build stats window", detail=f"{len(stats_specs)} experiment panels")

    canvas_frame = tk.Frame(window, bg="white")
    canvas_frame.pack(side="top", fill="both", expand=True)
    canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=0)
    v_scroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
    h_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
    canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
    v_scroll.pack(side="right", fill="y")
    h_scroll.pack(side="bottom", fill="x")
    canvas.pack(side="left", fill="both", expand=True)

    content = tk.Frame(canvas, bg="white")
    content_id = canvas.create_window((0, 0), window=content, anchor="nw")

    def _on_content_configure(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    content.bind("<Configure>", _on_content_configure)

    def _on_canvas_configure(event):
        if str(block_layout).strip().casefold() == "vertical":
            canvas.itemconfigure(content_id, width=event.width)

    canvas.bind("<Configure>", _on_canvas_configure)

    photo_refs = []
    block_columns_eff = max(1, int(block_columns))
    if str(block_layout).strip().casefold() == "horizontal":
        block_columns_eff = max(block_columns_eff, len(blocks))

    for block_idx, block in enumerate(blocks):
        grid_row = block_idx // block_columns_eff
        grid_col = block_idx % block_columns_eff
        block_frame = tk.Frame(content, bg="white", bd=1, relief="solid", padx=6, pady=6)
        block_frame.grid(row=grid_row, column=grid_col, padx=10, pady=10, sticky="nw")

        title_label = tk.Label(
            block_frame,
            text=block["title"],
            anchor="w",
            justify="left",
            bg="white",
            fg=block["color"],
            font=("Segoe UI", 12, "bold"),
        )
        title_label.grid(row=0, column=0, columnspan=max(2, block["ncols"] + 1), sticky="w", pady=(0, 6))

        header_row = tk.Frame(block_frame, bg="white")
        header_row.grid(row=1, column=0, sticky="w")
        tk.Label(
            header_row,
            text="Animal / ROI",
            bg="white",
            font=("Segoe UI", 10, "bold"),
            width=4,
            anchor="center",
        ).grid(row=0, column=0, padx=(0, 6), pady=(0, 4))
        header_labels = list(marker_order)
        if merge and len(marker_order) > 1:
            header_labels.append(str(merge_label))
        for col_idx, header_text in enumerate(header_labels, start=1):
            tk.Label(
                header_row,
                text=str(header_text),
                bg="white",
                font=("Segoe UI", 10, "bold"),
                anchor="center",
            ).grid(row=0, column=col_idx, padx=4, pady=(0, 4))

        row_widgets[block["block_key"]] = {}
        for row_idx, row in enumerate(block["rows"], start=2):
            row_container = tk.Frame(
                block_frame,
                bg="white",
                highlightthickness=3,
                highlightbackground="#D0D0D0",
                highlightcolor="#D0D0D0",
                bd=0,
            )
            row_container.grid(row=row_idx, column=0, sticky="w", pady=4)
            background_widgets = [row_container]

            label_widget = tk.Label(
                row_container,
                text="",
                bg="white",
                anchor="center",
                bd=0,
                relief="flat",
            )
            label_photo = _vertical_label_photo(row["row_label"], font_size=16)
            label_widget.configure(image=label_photo)
            label_widget.image = label_photo
            photo_refs.append(label_photo)
            label_widget.grid(row=0, column=0, padx=(0, 6))
            background_widgets.append(label_widget)

            for col_idx, tile_row in enumerate(row["tile_rows"], start=1):
                tile_value = loaded_tiles.get((block_idx, row_idx - 2, col_idx - 1))
                if tile_row is None:
                    widget = tk.Label(row_container, text="", width=2, bg="white")
                    widget.grid(row=0, column=col_idx, padx=4)
                    background_widgets.append(widget)
                    continue
                if isinstance(tile_value, Exception):
                    widget = tk.Label(
                        row_container,
                        text="Load failed",
                        bg="white",
                        justify="center",
                        width=16,
                        height=8,
                    )
                    widget.grid(row=0, column=col_idx, padx=4)
                    background_widgets.append(widget)
                    continue
                photo = _array_to_photo(tile_value)
                photo_refs.append(photo)
                widget = tk.Label(row_container, image=photo, bg="white", bd=1, relief="flat")
                widget.image = photo
                widget.grid(row=0, column=col_idx, padx=4)
                background_widgets.append(widget)
                widget.bind(
                    "<Double-Button-1>",
                    lambda _event, tile_row=tile_row, title_text=f"{block['title']} | {row['row_label']}": _zoom_tile(tile_row, title_text),
                )

            for widget in background_widgets:
                widget.bind(
                    "<Button-1>",
                    lambda _event, block=block, row=row: _select_row(block, row),
                )

            row_widgets[block["block_key"]][row["selection_key"]] = {
                "container": row_container,
                "background_widgets": background_widgets,
            }

        selected_key = None
        if block["block_key"] in selection_map:
            selected_key = _representative_selection_key(selection_map[block["block_key"]])
        _row_style(block["block_key"], selected_key)

    def _on_stats_close():
        for fig_obj, _canvas in stats_canvas_refs:
            try:
                plt.close(fig_obj)
            except Exception:
                pass
        try:
            stats_window.destroy()
        except Exception:
            pass

    def _on_close():
        if dirty_state["value"] and autosave_pickle:
            _commit_pickle(force=True)
        _on_stats_close()
        window.destroy()

    stats_window.protocol("WM_DELETE_WINDOW", _on_stats_close)
    window.protocol("WM_DELETE_WINDOW", _on_close)
    _progress_start_item(progress_state, "Launch selector")

    if owns_root:
        window.mainloop()
    else:
        window.wait_window()

    selected_count = len(_get_representative_image_table(source))
    _image_progress_finish(
        progress_state,
        "Launch selector",
        detail=f"{selected_count} representative selections",
    )
    return _get_representative_image_table(source)


def _preload_image_blocks(blocks, image_backend="auto",
                          fast_loading=False, preview_max_dim=None,
                          image_adjustments=None,
                          image_workers=None,
                          progress_state=None,
                          progress_label="Load representative tiles"):
    flat_rows = []
    tile_lookup = {}
    for block_idx, block in enumerate(blocks):
        for row_idx, row_slice in enumerate(block.get("rows", [])):
            for col_idx, tile_row in enumerate(row_slice):
                flat_index = len(flat_rows)
                flat_rows.append(tile_row)
                tile_lookup[(block_idx, row_idx, col_idx)] = flat_index

    loaded_tiles = _preload_image_rows(
        flat_rows,
        image_backend=image_backend,
        fast_loading=fast_loading,
        preview_max_dim=preview_max_dim,
        image_adjustments=image_adjustments,
        image_workers=image_workers,
        progress_state=progress_state,
        progress_label=progress_label,
    )
    return loaded_tiles, tile_lookup


def _image_adjustment_marker_names(marker_names) -> list[str]:
    normalized = _normalize_image_adjustments(marker_names=marker_names)
    return [entry["marker"] for entry in normalized.values()]


def _launch_image_edit_mode(marker_names, *, render_preview, render_final,
                            initial_adjustments=None, window_title="Edit Images"):
    import tkinter as tk
    from tkinter import ttk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    marker_list = _image_adjustment_marker_names(marker_names)
    if len(marker_list) == 0:
        raise ValueError("edit_mode requires at least one marker with image data.")

    adjustments = _normalize_image_adjustments(initial_adjustments, marker_names=marker_list)
    default_root = tk._default_root
    owns_root = default_root is None
    window = tk.Tk() if owns_root else tk.Toplevel(default_root)
    window.title(str(window_title))
    window.geometry("1600x950")
    window.configure(bg="white")

    result = {"applied": False, "adjustments": None}
    preview_state = {"fig": None, "canvas": None, "widget": None, "job": None}

    root_frame = tk.Frame(window, bg="white")
    root_frame.pack(fill="both", expand=True)

    control_frame = tk.Frame(root_frame, bg="white", padx=10, pady=10)
    control_frame.pack(side="left", fill="y")

    preview_frame = tk.Frame(root_frame, bg="white")
    preview_frame.pack(side="right", fill="both", expand=True)

    status_var = tk.StringVar(value="Adjust brightness and contrast per marker. Preview updates live.")
    status_label = tk.Label(
        control_frame,
        textvariable=status_var,
        justify="left",
        anchor="w",
        bg="white",
        wraplength=320,
    )
    status_label.pack(fill="x", pady=(0, 10))

    slider_vars = {}
    single_preview_var = tk.BooleanVar(value=False)

    def _current_adjustments():
        current = {}
        for marker in marker_list:
            values = slider_vars[marker]
            current[marker] = {
                "brightness": float(values["brightness"].get()),
                "contrast": float(values["contrast"].get()),
            }
        return current

    def _update_value_labels():
        for marker in marker_list:
            values = slider_vars[marker]
            values["brightness_label"].configure(text=f"{float(values['brightness'].get()):.2f}")
            values["contrast_label"].configure(text=f"{float(values['contrast'].get()):.2f}")

    def _clear_preview():
        old_canvas = preview_state.get("canvas")
        old_widget = preview_state.get("widget")
        old_fig = preview_state.get("fig")
        if old_widget is not None:
            try:
                old_widget.destroy()
            except Exception:
                pass
        if old_canvas is not None:
            try:
                old_canvas.get_tk_widget().destroy()
            except Exception:
                pass
        if old_fig is not None:
            try:
                plt.close(old_fig)
            except Exception:
                pass
        preview_state["fig"] = None
        preview_state["canvas"] = None
        preview_state["widget"] = None
        preview_state["im_artist"] = None
        preview_state["bg"] = None

    def _fig_to_rgba(fig):
        """Rasterize a matplotlib figure to an RGBA numpy array."""
        fig.canvas.draw()
        buf = np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8)
        w, h = fig.canvas.get_width_height()
        return buf.reshape(h, w, 4).copy()

    def _render_preview():
        preview_state["job"] = None
        _update_value_labels()
        preview_scope = "single" if bool(single_preview_var.get()) else "full"
        if preview_scope == "single":
            status_var.set("Rendering single-image preview...")
        else:
            status_var.set("Rendering preview...")
        try:
            plot_fig = render_preview(_current_adjustments(), preview_scope=preview_scope)
            rgba = _fig_to_rgba(plot_fig)
            plt.close(plot_fig)

            if preview_state.get("canvas") is not None and preview_state.get("im_artist") is not None:
                im_artist = preview_state["im_artist"]
                im_artist.set_data(rgba)
                im_artist.set_extent([0, rgba.shape[1], rgba.shape[0], 0])
                display_ax = preview_state["fig"].axes[0]
                display_ax.set_xlim(0, rgba.shape[1])
                display_ax.set_ylim(rgba.shape[0], 0)
                canvas = preview_state["canvas"]
                bg = preview_state.get("bg")
                if bg is not None:
                    try:
                        canvas.restore_region(bg)
                        display_ax.draw_artist(im_artist)
                        canvas.blit(preview_state["fig"].bbox)
                        canvas.flush_events()
                    except Exception:
                        canvas.draw()
                else:
                    canvas.draw()
            else:
                _clear_preview()
                display_fig = plt.figure(figsize=(12, 8))
                display_ax = display_fig.add_axes([0, 0, 1, 1])
                display_ax.set_axis_off()
                im_artist = display_ax.imshow(
                    rgba, aspect='auto',
                    extent=[0, rgba.shape[1], rgba.shape[0], 0],
                    interpolation='bilinear', animated=True,
                )
                canvas = FigureCanvasTkAgg(display_fig, master=preview_frame)
                canvas.draw()
                widget = canvas.get_tk_widget()
                widget.pack(fill="both", expand=True)
                preview_state["fig"] = display_fig
                preview_state["canvas"] = canvas
                preview_state["widget"] = widget
                preview_state["im_artist"] = im_artist
                try:
                    preview_state["bg"] = canvas.copy_from_bbox(display_fig.bbox)
                except Exception:
                    preview_state["bg"] = None

            if preview_scope == "single":
                status_var.set("Adjust brightness and contrast per marker. Single-image live preview is enabled.")
            else:
                status_var.set("Adjust brightness and contrast per marker. Preview updates live.")
        except Exception as exc:
            _clear_preview()
            status_var.set(f"Preview failed: {exc}")

    def _schedule_preview(*_args):
        if preview_state.get("job") is not None:
            try:
                window.after_cancel(preview_state["job"])
            except Exception:
                pass
        preview_state["job"] = window.after(250, _render_preview)

    preview_frame_controls = tk.LabelFrame(control_frame, text="Preview", bg="white", padx=8, pady=8)
    preview_frame_controls.pack(fill="x", pady=(0, 8))
    ttk.Checkbutton(
        preview_frame_controls,
        text="Single-image live preview",
        variable=single_preview_var,
        command=_schedule_preview,
    ).pack(anchor="w")

    for marker in marker_list:
        marker_frame = tk.LabelFrame(control_frame, text=str(marker), bg="white", padx=8, pady=8)
        marker_frame.pack(fill="x", pady=4)
        brightness_var = tk.DoubleVar(value=float(adjustments[marker.casefold()]["brightness"]))
        contrast_var = tk.DoubleVar(value=float(adjustments[marker.casefold()]["contrast"]))
        brightness_spin = ttk.Spinbox(
            marker_frame,
            from_=0.0,
            to=5.0,
            increment=0.05,
            textvariable=brightness_var,
            width=7,
            command=_schedule_preview,
            format="%.2f",
        )
        contrast_spin = ttk.Spinbox(
            marker_frame,
            from_=0.0,
            to=5.0,
            increment=0.05,
            textvariable=contrast_var,
            width=7,
            command=_schedule_preview,
            format="%.2f",
        )
        brightness_label = tk.Label(marker_frame, text=f"{float(brightness_var.get()):.2f}", bg="white", width=6)
        contrast_label = tk.Label(marker_frame, text=f"{float(contrast_var.get()):.2f}", bg="white", width=6)

        tk.Label(marker_frame, text="Brightness", bg="white").grid(row=0, column=0, sticky="w")
        brightness_scale = ttk.Scale(
            marker_frame,
            from_=0.0,
            to=5.0,
            orient="horizontal",
            variable=brightness_var,
            command=_schedule_preview,
        )
        brightness_scale.grid(row=0, column=1, sticky="ew", padx=6)
        brightness_spin.grid(row=0, column=2, sticky="e", padx=(0, 6))
        brightness_label.grid(row=0, column=3, sticky="e")

        tk.Label(marker_frame, text="Contrast", bg="white").grid(row=1, column=0, sticky="w")
        contrast_scale = ttk.Scale(
            marker_frame,
            from_=0.0,
            to=5.0,
            orient="horizontal",
            variable=contrast_var,
            command=_schedule_preview,
        )
        contrast_scale.grid(row=1, column=1, sticky="ew", padx=6)
        contrast_spin.grid(row=1, column=2, sticky="e", padx=(0, 6))
        contrast_label.grid(row=1, column=3, sticky="e")
        marker_frame.grid_columnconfigure(1, weight=1)
        brightness_spin.bind("<Return>", _schedule_preview)
        brightness_spin.bind("<FocusOut>", _schedule_preview)
        contrast_spin.bind("<Return>", _schedule_preview)
        contrast_spin.bind("<FocusOut>", _schedule_preview)

        slider_vars[marker] = {
            "brightness": brightness_var,
            "contrast": contrast_var,
            "brightness_label": brightness_label,
            "contrast_label": contrast_label,
        }

    button_row = tk.Frame(control_frame, bg="white")
    button_row.pack(fill="x", pady=(10, 0))

    def _reset():
        for marker in marker_list:
            slider_vars[marker]["brightness"].set(1.0)
            slider_vars[marker]["contrast"].set(1.0)
        _schedule_preview()

    def _apply():
        result["applied"] = True
        result["adjustments"] = _current_adjustments()
        window.destroy()

    def _cancel():
        result["applied"] = False
        result["adjustments"] = None
        window.destroy()

    ttk.Button(button_row, text="Reset", command=_reset).pack(side="left", padx=(0, 6))
    ttk.Button(button_row, text="Apply", command=_apply).pack(side="left", padx=(0, 6))
    ttk.Button(button_row, text="Cancel", command=_cancel).pack(side="left")

    def _on_close():
        result["applied"] = False
        result["adjustments"] = None
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", _on_close)
    _render_preview()

    if owns_root:
        window.mainloop()
    else:
        window.wait_window()

    _clear_preview()
    if not result["applied"]:
        return None
    return render_final(result["adjustments"])


def _render_representative_image_blocks(source, image_df: pd.DataFrame, blocks,
                                        loaded_tiles, tile_lookup,
                                        block_layout="vertical",
                                        title=None,
                                        tile_size=4.0,
                                        tile_gap=2.0,
                                        tile_gap_units="points",
                                        image_backend="auto",
                                        scale_bar=False,
                                        scale_bar_location="bottom right",
                                        scale_bar_size=None,
                                        scale_bar_units="microns",
                                        image_width_microns=None,
                                        pixel_size=None,
                                        fast_loading=False,
                                        preview_max_dim=None,
                                        image_adjustments=None,
                                        draw_roi_keys=None):
    if len(blocks) == 0:
        raise ValueError("No representative image blocks were available to render.")

    layout = str(block_layout).strip().casefold()
    if layout not in {"vertical", "horizontal"}:
        raise ValueError("block_layout must be 'vertical' or 'horizontal'.")

    valid_tiles = [
        tile for tile in loaded_tiles.values()
        if isinstance(tile, np.ndarray) and tile.ndim >= 2 and tile.shape[0] > 0 and tile.shape[1] > 0
    ]
    if len(valid_tiles) > 0:
        tile_width_over_height = float(np.median([
            tile.shape[1] / tile.shape[0] for tile in valid_tiles
        ]))
    else:
        tile_width_over_height = 1.0
    tile_width_over_height = max(0.05, tile_width_over_height)

    axis_height_in = float(tile_size)
    axis_width_in = axis_height_in * tile_width_over_height
    has_row_labels = any(
        any(str(label).strip() != "" for label in block.get("row_labels", []))
        for block in blocks
    )
    row_label_width_in = 0.55 if has_row_labels else 0.0
    show_block_titles = any(str(block.get("title", "")).strip() != "" for block in blocks)
    block_title_height_in = 0.38 if show_block_titles else 0.0
    gap_layout = _resolve_image_gap_layout(
        tile_gap=tile_gap,
        tile_gap_units=tile_gap_units,
        axis_width_in=axis_width_in,
        axis_height_in=axis_height_in,
    )
    block_gap_in = max(
        8.0 / 72.0,
        (gap_layout["gap_width_in"] if layout == "horizontal" else gap_layout["gap_height_in"]) * 2.0,
    )

    block_widths = [
        row_label_width_in + (axis_width_in * int(block["ncols"])) + (gap_layout["gap_width_in"] * max(0, int(block["ncols"]) - 1))
        for block in blocks
    ]
    block_heights = [
        (block_title_height_in if show_block_titles else 0.0)
        + (axis_height_in * int(block["nrows"]))
        + (gap_layout["gap_height_in"] * max(0, int(block["nrows"]) - 1))
        for block in blocks
    ]

    content_top = 0.94
    if layout == "horizontal":
        fig_width_in = sum(block_widths) + (block_gap_in * max(0, len(blocks) - 1))
        fig_height_in = max(block_heights) / content_top
        outer_wspace = 0.0 if len(blocks) <= 1 else (block_gap_in / max(float(np.mean(block_widths)), 1e-9))
        fig = plt.figure(figsize=(fig_width_in, fig_height_in))
        outer = fig.add_gridspec(
            1,
            len(blocks),
            left=0.0,
            right=1.0,
            bottom=0.0,
            top=content_top,
            wspace=outer_wspace,
            width_ratios=block_widths,
        )
    else:
        fig_width_in = max(block_widths)
        fig_height_in = (sum(block_heights) + (block_gap_in * max(0, len(blocks) - 1))) / content_top
        outer_hspace = 0.0 if len(blocks) <= 1 else (block_gap_in / max(float(np.mean(block_heights)), 1e-9))
        fig = plt.figure(figsize=(fig_width_in, fig_height_in))
        outer = fig.add_gridspec(
            len(blocks),
            1,
            left=0.0,
            right=1.0,
            bottom=0.0,
            top=content_top,
            hspace=outer_hspace,
            height_ratios=block_heights,
        )

    label_ratio = (row_label_width_in / max(axis_width_in, 1e-9)) if has_row_labels else None
    title_ratio = (block_title_height_in / max(axis_height_in, 1e-9)) if show_block_titles else None

    for block_idx, block in enumerate(blocks):
        outer_spec = outer[0, block_idx] if layout == "horizontal" else outer[block_idx, 0]
        inner_rows = int(block["nrows"]) + (1 if show_block_titles else 0)
        inner_cols = int(block["ncols"]) + (1 if has_row_labels else 0)
        height_ratios = ([title_ratio] if show_block_titles else []) + ([1] * int(block["nrows"]))
        width_ratios = ([label_ratio] if has_row_labels else []) + ([1] * int(block["ncols"]))
        inner = outer_spec.subgridspec(
            inner_rows,
            inner_cols,
            hspace=gap_layout["hspace"],
            wspace=gap_layout["wspace"],
            height_ratios=height_ratios,
            width_ratios=width_ratios,
        )

        title_offset = 0
        if show_block_titles:
            title_ax = fig.add_subplot(inner[0, :])
            title_ax.axis("off")
            title_ax.text(
                0.0,
                0.5,
                str(block.get("title", "")),
                ha="left",
                va="center",
                fontsize=13,
                fontweight="bold",
                color=str(block.get("color", "black")),
            )
            title_offset = 1

        for row_idx, row_slice in enumerate(block.get("rows", [])):
            inner_row = row_idx + title_offset
            image_col_offset = 0
            if has_row_labels:
                label_ax = fig.add_subplot(inner[inner_row, 0])
                label_ax.axis("off")
                label_text = ""
                if row_idx < len(block.get("row_labels", [])):
                    label_text = str(block["row_labels"][row_idx]).strip()
                if label_text != "":
                    label_ax.text(
                        0.5,
                        0.5,
                        label_text,
                        rotation=90,
                        ha="center",
                        va="center",
                        color="black",
                        fontsize=12,
                        fontweight="bold",
                    )
                image_col_offset = 1

            for col_idx, row in enumerate(row_slice):
                ax = fig.add_subplot(inner[inner_row, image_col_offset + col_idx])
                if row is None:
                    ax.axis("off")
                    continue

                tile = None
                try:
                    tile_index = tile_lookup.get((block_idx, row_idx, col_idx))
                    tile = loaded_tiles.get(tile_index)
                    if isinstance(tile, Exception):
                        raise tile
                    if tile is None:
                        tile = _resolve_image_tile(
                            row,
                            image_backend=image_backend,
                            fast_loading=fast_loading,
                            preview_max_dim=preview_max_dim,
                            image_adjustments=image_adjustments,
                        )
                    if tile.ndim == 2:
                        ax.imshow(tile, cmap="gray")
                    else:
                        ax.imshow(tile)
                except Exception as exc:
                    ax.text(0.5, 0.5, f"Could not load image\n{exc}", ha="center", va="center", fontsize=10)

                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_box_aspect(1.0 / tile_width_over_height)
                if tile is not None:
                    _draw_scale_bar(
                        ax,
                        row,
                        tile,
                        scale_bar=scale_bar,
                        scale_bar_location=scale_bar_location,
                        scale_bar_size=scale_bar_size,
                        scale_bar_units=scale_bar_units,
                        image_width_microns=image_width_microns,
                        pixel_size=pixel_size,
                    )
                    panel = None
                    panels = block.get("panels", [])
                    if col_idx < len(panels):
                        panel = panels[col_idx]
                    if panel is not None and _image_panel_key(panel) in (draw_roi_keys or set()):
                        _draw_image_panel_roi_outline(ax, source, row)
                ax.annotate(
                    _image_tile_label(row),
                    xy=(0.02, 0.98),
                    xycoords="axes fraction",
                    ha="left",
                    va="top",
                    color="white",
                    fontsize=20,
                    fontweight="bold",
                )
                for spine in ax.spines.values():
                    spine.set_visible(False)

    fig.suptitle(_image_figure_title(image_df, title=title), fontsize=16)
    return fig


def plot_representative_images(source, markers=None,
                               animal_filter=None,
                               fast_loading=False, preview_max_dim=None,
                               image_backend="auto", image_workers=None,
                               image_adjustments=None,
                               edit_mode=False,
                               use_existing_edits=False,
                               draw_rois=None,
                               progress=True,
                               _preview_single_image=False, **kwargs):
    if edit_mode:
        representative_df = _get_representative_image_table(source)
        if representative_df.empty:
            raise ValueError("No representative images have been selected for this source.")
        representative_df, marker_request = _filter_representative_table_by_markers(
            source,
            representative_df,
            marker_order=markers,
            require_specific=True,
        )
        if hasattr(source, "getImageTable"):
            image_df = source.getImageTable(include_summary=True)
        else:
            image_df = getattr(source, "images", None)
            if not isinstance(image_df, pd.DataFrame) and hasattr(source, "importImages"):
                image_df = source.importImages(progress=False)
        if not isinstance(image_df, pd.DataFrame) or image_df.empty:
            raise ValueError("No imported images were found.")
        filtered_df = _filter_image_df_to_representatives(image_df, representative_df)
        filtered_df = _filter_df_by_values(filtered_df, "Marker", marker_request)
        filtered_df = _filter_images_to_marker_coherent_experiments(filtered_df, marker_request)
        filtered_df = _filter_df_by_string_match(filtered_df, "AnimalName", animal_filter)
        filtered_df = _order_image_rows_by_source(source, filtered_df, marker_names=marker_request).reset_index(drop=True)
        if filtered_df.empty:
            raise ValueError("No representative images matched the requested markers/animal_filter filters.")
        marker_order = _resolve_requested_image_marker_order(filtered_df, marker_request)
        if len(marker_order) == 0:
            raise ValueError("No representative marker images were available to edit.")
        preview_merge = bool(kwargs.get("merge", False))
        preview_merge_label = kwargs.get("merge_label", "Merge")
        image_panels, marker_order = _resolve_image_marker_panels(
            filtered_df,
            markers if markers is not None else marker_request,
            merge=preview_merge,
            merge_label=preview_merge_label,
        )
        effective_adjustments = _resolve_effective_image_adjustments(
            source,
            marker_order,
            animal_filter=animal_filter,
            image_adjustments=image_adjustments,
            use_existing_edits=use_existing_edits,
        )
        preview_dim = int(preview_max_dim) if preview_max_dim is not None else 512
        preview_kwargs = dict(kwargs)
        final_kwargs = dict(kwargs)
        return _launch_image_edit_mode(
            marker_order,
            render_preview=lambda adjustments, preview_scope="full": plot_representative_images(
                source,
                markers=markers,
                animal_filter=animal_filter,
                fast_loading=True,
                preview_max_dim=preview_dim,
                image_backend=image_backend,
                image_workers=image_workers,
                image_adjustments=adjustments,
                edit_mode=False,
                use_existing_edits=False,
                draw_rois=draw_rois,
                progress=False,
                _preview_single_image=(str(preview_scope).strip().casefold() == "single"),
                **dict(preview_kwargs, save=False, show=False, verbose=False),
            ),
            render_final=lambda adjustments: _persist_image_edits_and_return(
                source,
                plot_representative_images(
                    source,
                    markers=markers,
                    animal_filter=animal_filter,
                    fast_loading=fast_loading,
                    preview_max_dim=preview_max_dim,
                    image_backend=image_backend,
                    image_workers=image_workers,
                    image_adjustments=adjustments,
                    edit_mode=False,
                    use_existing_edits=False,
                    draw_rois=draw_rois,
                    progress=progress,
                    **final_kwargs,
                ),
                marker_names=marker_order,
                adjustments=adjustments,
                animal_filter=animal_filter,
            ),
            initial_adjustments=effective_adjustments,
            window_title="Edit Representative Images",
        )

    progress_state = _image_progress_tracker(
        "plot_representative_images",
        total=6,
        enabled=progress,
    )

    _progress_start_item(progress_state, "Prepare representative table")
    representative_df = _get_representative_image_table(source)
    if representative_df.empty:
        raise ValueError("No representative images have been selected for this source.")
    representative_df, marker_request = _filter_representative_table_by_markers(
        source,
        representative_df,
        marker_order=markers,
        require_specific=True,
    )
    _image_progress_finish(progress_state, "Prepare representative table", detail=f"{len(representative_df)} representative rows")

    _progress_start_item(progress_state, "Filter representative images")
    if hasattr(source, "getImageTable"):
        image_df = source.getImageTable(include_summary=True)
    else:
        image_df = getattr(source, "images", None)
        if not isinstance(image_df, pd.DataFrame) and hasattr(source, "importImages"):
            image_df = source.importImages(progress=False)

    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        raise ValueError("No imported images were found.")

    filtered_df = _filter_image_df_to_representatives(image_df, representative_df)
    if filtered_df.empty:
        raise ValueError("Stored representative selections did not match any imported images.")
    plot_kwargs = dict(kwargs)
    plot_kwargs.pop("progress", None)
    plot_kwargs.pop("fast_loading", None)
    plot_kwargs.pop("preview_max_dim", None)
    plot_kwargs.pop("image_backend", None)
    plot_kwargs.pop("image_workers", None)

    save = bool(plot_kwargs.pop("save", True))
    show = bool(plot_kwargs.pop("show", True))
    verbose = bool(plot_kwargs.pop("verbose", True))
    merge = bool(plot_kwargs.pop("merge", False))
    merge_label = plot_kwargs.pop("merge_label", "Merge")
    scale_bar = bool(plot_kwargs.pop("scale_bar", False))
    scale_bar_location = plot_kwargs.pop("scale_bar_location", "bottom left")
    scale_bar_size = plot_kwargs.pop("scale_bar_size", None)
    scale_bar_units = plot_kwargs.pop("scale_bar_units", "microns")
    image_width_microns = plot_kwargs.pop("image_width_microns", None)
    pixel_size = plot_kwargs.pop("pixel_size", None)
    tile_size = float(plot_kwargs.pop("tile_size", 4.0))
    tile_gap = float(plot_kwargs.pop("tile_gap", 0.0))
    tile_gap_units = plot_kwargs.pop("tile_gap_units", "points")
    title = plot_kwargs.pop("title", f"{getattr(source, 'name', 'Representative images')} representative images")
    block_layout = plot_kwargs.pop("block_layout", "horizontal")
    stack_by = plot_kwargs.pop("stack_by", None)
    block_by = plot_kwargs.pop("block_by", stack_by if stack_by is not None else "Condition")
    plot_kwargs.pop("ncols", None)
    plot_kwargs.pop("max_images", None)
    plot_kwargs.pop("roi_filter", None)

    filtered_df = _filter_df_by_values(filtered_df, "Marker", marker_request)
    filtered_df = _filter_images_to_marker_coherent_experiments(filtered_df, marker_request)
    filtered_df = _filter_df_by_string_match(filtered_df, "AnimalName", animal_filter)
    filtered_df = _order_image_rows_by_source(source, filtered_df, marker_names=marker_request).reset_index(drop=True)
    if bool(_preview_single_image):
        filtered_df = _limit_image_df_for_single_preview(
            filtered_df,
            marker_order=marker_request,
            merge=merge,
        )
    if filtered_df.empty:
        raise ValueError("No representative images matched the requested markers/animal_filter filters.")
    image_panels, marker_order = _resolve_image_marker_panels(
        filtered_df,
        markers if markers is not None else marker_request,
        merge=merge,
        merge_label=merge_label,
    )
    if len(image_panels) == 0 or len(marker_order) == 0:
        raise ValueError("No representative marker images were available to plot.")
    effective_image_adjustments = _resolve_effective_image_adjustments(
        source,
        marker_order,
        animal_filter=animal_filter,
        image_adjustments=image_adjustments,
        use_existing_edits=use_existing_edits,
    )
    _image_progress_finish(progress_state, "Filter representative images", detail=f"{len(filtered_df)} matching image rows")
    draw_roi_keys = _image_draw_roi_key_set(draw_rois, image_panels)

    _progress_start_item(progress_state, "Build representative blocks")
    blocks = _collect_representative_plot_blocks(
        source,
        filtered_df,
        image_panels,
        marker_order=marker_order,
        block_by=block_by,
        merge_label=merge_label,
    )
    if len(blocks) == 0:
        raise ValueError("No representative image blocks could be created from the filtered images.")
    _image_progress_finish(progress_state, "Build representative blocks", detail=f"{len(blocks)} blocks")

    loaded_tiles, tile_lookup = _preload_image_blocks(
        blocks,
        image_backend=image_backend,
        fast_loading=fast_loading,
        preview_max_dim=preview_max_dim,
        image_adjustments=effective_image_adjustments,
        image_workers=image_workers,
        progress_state=progress_state,
        progress_label="Load representative tiles",
    )

    _progress_start_item(progress_state, "Render representative images")
    fig = _render_representative_image_blocks(
        source,
        filtered_df,
        blocks,
        loaded_tiles,
        tile_lookup,
        block_layout=block_layout,
        title=title,
        tile_size=tile_size,
        tile_gap=tile_gap,
        tile_gap_units=tile_gap_units,
        image_backend=image_backend,
        scale_bar=scale_bar,
        scale_bar_location=scale_bar_location,
        scale_bar_size=scale_bar_size,
        scale_bar_units=scale_bar_units,
        image_width_microns=image_width_microns,
        pixel_size=pixel_size,
        fast_loading=fast_loading,
        preview_max_dim=preview_max_dim,
        image_adjustments=effective_image_adjustments,
        draw_roi_keys=draw_roi_keys,
    )
    _image_progress_finish(progress_state, "Render representative images", detail="Representative figure ready")

    save_item = "Save figure" if save else "Finalize"
    _progress_start_item(progress_state, save_item)
    save_path = None
    if save:
        figure_dir = _representative_figure_dir(source, filtered_df, marker_order)
        filter_dir = _representative_filter_dir_name(animal_filter)
        if filter_dir is not None:
            figure_dir = os.path.join(figure_dir, filter_dir)
            os.makedirs(figure_dir, exist_ok=True)
        export_dirs = _export_representative_assets(
            source,
            representative_df=representative_df,
            image_df=filtered_df,
            marker_order=marker_order,
            export_dir_override=figure_dir,
            write_csv=False,
        )
        block_desc = str(block_by).strip()
        save_name = "representative_images"
        if block_desc != "" and block_desc.casefold() not in {"condition", "none", "all"}:
            save_name = f"{save_name}_by_{block_desc}"
        if merge:
            save_name = f"{save_name}_merged"
        save_path = save_fig(
            fig,
            figure_dir,
            save_name,
            pad_inches=0.25,
            verbose=verbose,
        )
        if len(export_dirs) > 0:
            save_detail = f"{save_path} | copied images: {export_dirs[0]}"
        else:
            save_detail = save_path
    else:
        save_detail = "Figure ready"

    fig.PyFLASH_image_df = filtered_df
    fig.PyFLASH_representative_blocks = blocks
    fig.PyFLASH_save_path = save_path
    fig.PyFLASH_image_adjustments = effective_image_adjustments
    if not show:
        plt.close(fig)
    _image_progress_finish(progress_state, save_item, detail=save_detail)
    return fig


def _normalize_hist_bin_range(bin_range):
    """Validate/normalize (min, max) histogram range."""
    if bin_range is None:
        return None
    if not isinstance(bin_range, (list, tuple, np.ndarray, pd.Series, pd.Index)) or len(bin_range) != 2:
        raise ValueError("bin_range must be a 2-item sequence: (min, max).")
    lo = float(bin_range[0])
    hi = float(bin_range[1])
    if not np.isfinite(lo) or not np.isfinite(hi):
        raise ValueError("bin_range values must be finite numbers.")
    if hi <= lo:
        raise ValueError("bin_range max must be greater than min.")
    return (lo, hi)


def _coerce_hist_bin_edges(bin_edges):
    """Validate/normalize explicit histogram bin edges."""
    if bin_edges is None:
        return None
    try:
        edges = np.asarray(list(bin_edges), dtype=float).reshape(-1)
    except Exception as e:
        raise ValueError("bin_edges must be a 1D sequence of numeric edges.") from e
    edges = edges[np.isfinite(edges)]
    edges = np.unique(edges)
    if edges.size < 2:
        raise ValueError("bin_edges must contain at least two distinct finite values.")
    return edges


def _compute_hist_bin_edges(values, bins=30, binwidth=None, bin_range=None):
    """
    Build explicit edges for shared-bin histogram plotting.

    Priority:
    1) `binwidth` + range
    2) integer `bins` + range
    """
    arr = np.asarray(values, dtype=float).reshape(-1)
    arr = arr[np.isfinite(arr)]

    rng = _normalize_hist_bin_range(bin_range)
    if rng is None:
        if arr.size > 0:
            lo = float(np.min(arr))
            hi = float(np.max(arr))
        else:
            lo, hi = 0.0, 1.0
    else:
        lo, hi = rng

    if binwidth is not None:
        bw = float(binwidth)
        if not np.isfinite(bw) or bw <= 0:
            raise ValueError("binwidth must be a finite number > 0.")
        if hi <= lo:
            hi = lo + bw
        edges = np.arange(lo, hi + bw, bw, dtype=float)
        if edges.size < 2:
            edges = np.array([lo, lo + bw], dtype=float)
        if edges[-1] < hi:
            edges = np.append(edges, hi)
        edges[0] = lo
        if edges[-1] <= edges[0]:
            edges = np.array([lo, lo + bw], dtype=float)
        return edges

    try:
        n_bins = int(bins)
    except Exception as e:
        raise ValueError("bins must be an integer when binwidth is not provided.") from e
    if n_bins < 1:
        raise ValueError("bins must be >= 1.")
    if hi <= lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, n_bins + 1, dtype=float)


def _normalize_threshold_values(threshold):
    """Normalize threshold input to a sorted list of unique floats."""
    if threshold is None:
        return None
    if isinstance(threshold, str):
        raw = [threshold]
    elif isinstance(threshold, (list, tuple, set, np.ndarray, pd.Series, pd.Index)):
        raw = _flatten_specificity_values([threshold])
    else:
        raw = [threshold]

    values = []
    for t in raw:
        try:
            v = float(t)
        except Exception as e:
            raise ValueError("threshold must be numeric or a sequence of numeric values.") from e
        if not np.isfinite(v):
            raise ValueError("threshold values must be finite.")
        values.append(v)
    if len(values) == 0:
        raise ValueError("threshold list cannot be empty.")
    return sorted(set(values))


def _format_threshold_value(v):
    """Compact string formatting for threshold labels."""
    try:
        fv = float(v)
        if np.isfinite(fv):
            return f"{fv:g}"
    except Exception:
        pass
    return str(v)


def _build_pie_counts_from_series(series: pd.Series, threshold=None, drop_zeros=True):
    """
    Build pie labels/counts from a raw series.

    If `threshold` is provided, numeric values are grouped into threshold bins:
    <=t1, (t1,t2], ..., >tn.
    """
    raw = series.copy()
    try:
        sentinel_mask = raw.astype(str).str.contains("NOT_INCLUDED_IN_EXPERIMENT", na=False)
        raw = raw.mask(sentinel_mask, np.nan)
    except Exception:
        pass

    th_vals = _normalize_threshold_values(threshold)
    if th_vals is not None:
        numeric = _to_numeric_excluding_not_included(raw).dropna()
        if len(numeric) == 0:
            return [], []
        bins = [-np.inf] + list(th_vals) + [np.inf]
        labels = []
        if len(th_vals) == 1:
            t0 = _format_threshold_value(th_vals[0])
            labels = [f"<= {t0}", f"> {t0}"]
        else:
            labels.append(f"<= {_format_threshold_value(th_vals[0])}")
            for lo, hi in zip(th_vals[:-1], th_vals[1:]):
                labels.append(
                    f"> {_format_threshold_value(lo)} and <= {_format_threshold_value(hi)}"
                )
            labels.append(f"> {_format_threshold_value(th_vals[-1])}")
        cut = pd.cut(
            numeric,
            bins=bins,
            labels=labels,
            include_lowest=True,
            right=True,
        )
        counts = cut.value_counts(sort=False).reindex(labels, fill_value=0)
        if drop_zeros:
            counts = counts[counts > 0]
        return [str(k) for k in counts.index.tolist()], counts.astype(int).tolist()

    numeric = _to_numeric_excluding_not_included(raw)
    numeric_non_na = numeric.dropna()
    raw_non_na = raw.dropna()

    if len(numeric_non_na) > 0 and int(numeric_non_na.nunique()) > 12:
        raise ValueError(
            "Continuous numeric data detected for pie chart. "
            "Provide `threshold` (single value or list/tuple) to bin values."
        )

    if len(numeric_non_na) > 0:
        counts = numeric_non_na.value_counts(sort=False).sort_index()
        labels = [str(v) for v in counts.index.tolist()]
        return labels, counts.astype(int).tolist()

    text = raw_non_na.astype(str).str.strip()
    text = text[text != ""]
    if len(text) == 0:
        return [], []
    counts = text.value_counts(sort=False)
    counts = counts.sort_index(key=lambda idx: idx.astype(str))
    return [str(v) for v in counts.index.tolist()], counts.astype(int).tolist()


def _pie_gradient_colors(base_color, n):
    """
    Build pie colors from white -> base_color.

    Rules:
    - n=1: [base_color]
    - n=2: [white, base_color]
    - n>2: linear gradient from white (lowest) to base_color (highest)
    """
    n = int(max(0, n))
    if n == 0:
        return []
    try:
        base_rgb = np.array(mpl_to_rgb(base_color), dtype=float)
    except Exception:
        base_rgb = np.array(mpl_to_rgb("black"), dtype=float)

    white = np.array([1.0, 1.0, 1.0], dtype=float)
    if n == 1:
        return [tuple(base_rgb.tolist())]
    if n == 2:
        return [tuple(white.tolist()), tuple(base_rgb.tolist())]

    out = []
    for i in range(n):
        t = float(i) / float(n - 1)
        rgb = white + (base_rgb - white) * t
        out.append(tuple(np.clip(rgb, 0.0, 1.0).tolist()))
    return out


_COMBO_PIE_SUMMARY_SUFFIXES = (
    "_Count",
    "_Count%",
    "_CountRaw",
    "_IntDenTotal",
    "_MeanIntDen",
)


def _normalize_combo_pie_family(family):
    family_key = str(family).strip().casefold().replace("_", "")
    family_map = {
        "combo": ("volcombo", "VolCombo"),
        "detailed": ("volcombo", "VolCombo"),
        "volcombo": ("volcombo", "VolCombo"),
        "comboany": ("volcomboany", "VolComboAny"),
        "any": ("volcomboany", "VolComboAny"),
        "pooled": ("volcomboany", "VolComboAny"),
        "volcomboany": ("volcomboany", "VolComboAny"),
        "cpccombo": ("cpccombo", "CPCCombo"),
        "cpccomboany": ("cpccomboany", "CPCComboAny"),
    }
    if family_key in family_map:
        return family_map[family_key]
    raise ValueError(
        "family must be one of 'VolCombo', 'VolComboAny', 'CPCCombo', or 'CPCComboAny'."
    )


def _coerce_combo_indicator_flag(value):
    if pd.isna(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value) != 0
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return False
        return float(value) != 0.0
    text = str(value).strip().casefold()
    if text in {"", "0", "false", "no", "nan", "none"}:
        return False
    if "not_included_in_experiment" in text:
        return False
    return True


def _resolve_combo_family_columns(df, marker, family, include_none=True):
    family_key, family_prefix = _normalize_combo_pie_family(family)
    marker_s = str(marker).strip()
    prefixes = [family_prefix]
    if family_key == "volcombo":
        prefixes.append("Combo")
    elif family_key == "volcomboany":
        prefixes.append("ComboAny")

    combo_columns = []
    seen_cols = set()
    for family_prefix_candidate in prefixes:
        prefix = f"{marker_s}_{family_prefix_candidate}_"
        for col in df.columns:
            col_s = str(col)
            if col_s in seen_cols or not col_s.startswith(prefix):
                continue
            if any(col_s.endswith(suffix) for suffix in _COMBO_PIE_SUMMARY_SUFFIXES):
                continue
            signature = col_s[len(prefix):]
            if not include_none and signature == "None":
                continue
            combo_columns.append((col_s, signature))
            seen_cols.add(col_s)
    return combo_columns


def _build_combo_signature_series(df, combo_columns, include_none=True):
    category_order = []
    signature_values = []
    none_available = any(signature == "None" for _, signature in combo_columns)
    for _, signature in combo_columns:
        if signature not in category_order:
            category_order.append(signature)

    for _, row in df.iterrows():
        active_signatures = []
        for col_name, signature in combo_columns:
            if _coerce_combo_indicator_flag(row.get(col_name)):
                active_signatures.append(signature)
        if len(active_signatures) == 0:
            if include_none and none_available:
                label = "None"
            else:
                label = np.nan
        elif len(active_signatures) == 1:
            label = active_signatures[0]
        else:
            label = "_".join(active_signatures)
            if label not in category_order:
                category_order.append(label)
        signature_values.append(label)

    return pd.Series(signature_values, index=df.index), category_order


def _build_combo_counts_from_series(series: pd.Series, category_order, drop_zeros=True):
    raw = series.copy()
    text = raw.dropna().astype(str).str.strip()
    text = text[text != ""]
    if len(text) == 0:
        return [], []

    counts = text.value_counts(sort=False)
    ordered_categories = [cat for cat in category_order if cat in counts.index]
    ordered_categories.extend([cat for cat in counts.index.tolist() if cat not in ordered_categories])
    counts = counts.reindex(ordered_categories, fill_value=0)
    if drop_zeros:
        counts = counts[counts > 0]
    return [str(v) for v in counts.index.tolist()], counts.astype(int).tolist()


def _normalize_combo_collapse_markers(collapse_markers):
    if collapse_markers is None:
        return []
    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    if isinstance(collapse_markers, queue_types) and not isinstance(collapse_markers, str):
        values = [str(v).strip() for v in collapse_markers]
    else:
        values = [str(collapse_markers).strip()]
    out = []
    seen = set()
    for value in values:
        if value == "":
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _collapse_combo_signature(signature, family, collapse_markers):
    signature_s = str(signature).strip()
    if signature_s == "" or signature_s == "None" or len(collapse_markers) == 0:
        return signature_s or "None"

    family_key, _ = _normalize_combo_pie_family(family)
    work = f"_{signature_s}_"
    for marker_name in collapse_markers:
        tokens = [f"{marker_name}+"]
        if family_key in {"volcombo", "cpccombo"}:
            tokens.append(f"w{marker_name}")
        for token in tokens:
            work = work.replace(f"_{token}_", "_")
    work = re.sub(r"_+", "_", work).strip("_")
    return work if work != "" else "None"


def _collapse_combo_signature_series(series: pd.Series, category_order, family, collapse_markers,
                                     include_none=True):
    if len(collapse_markers) == 0:
        return series.copy(), list(category_order)

    collapsed = series.map(lambda v: _collapse_combo_signature(v, family, collapse_markers) if pd.notna(v) else np.nan)
    if not include_none:
        collapsed = collapsed.mask(collapsed.astype(str).eq("None"), np.nan)

    collapsed_order = []
    for signature in category_order:
        mapped = _collapse_combo_signature(signature, family, collapse_markers)
        if mapped == "None" and not include_none:
            continue
        if mapped not in collapsed_order:
            collapsed_order.append(mapped)
    return collapsed, collapsed_order


def _combo_collapse_display_suffix(collapse_markers):
    if len(collapse_markers) == 0:
        return ""
    return f" [collapse: {', '.join(collapse_markers)}]"


def _combo_collapse_save_suffix(collapse_markers):
    if len(collapse_markers) == 0:
        return ""
    safe = "-".join(strip_name(str(v)) for v in collapse_markers)
    return f"--collapse-{safe}"


def _normalize_pie_order(order):
    if order is None:
        return None
    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    if isinstance(order, str):
        values = [order]
    elif isinstance(order, queue_types):
        values = list(order)
    else:
        raise TypeError("order must be a string or list-like of category labels.")

    out = []
    seen = set()
    for value in values:
        value_s = str(value).strip()
        if value_s == "":
            continue
        key = value_s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value_s)
    return out


def _apply_pie_order(raw_labels, labels, counts, order):
    raw_labels_s = [str(label).strip() for label in raw_labels]
    labels_s = [str(label).strip() for label in labels]
    counts_list = list(counts)
    if order is None or len(order) == 0:
        return raw_labels_s, labels_s, counts_list

    entries = list(zip(raw_labels_s, labels_s, counts_list))
    raw_lookup = {}
    display_lookup = {}
    for idx, (raw_label, display_label, _) in enumerate(entries):
        raw_lookup.setdefault(raw_label.casefold(), []).append(idx)
        display_lookup.setdefault(display_label.casefold(), []).append(idx)

    ordered_idxs = []
    used = set()
    for requested in order:
        key = str(requested).strip().casefold()
        matched = raw_lookup.get(key)
        if matched is None:
            matched = display_lookup.get(key, [])
        for idx in matched:
            if idx in used:
                continue
            ordered_idxs.append(idx)
            used.add(idx)
    for idx in range(len(entries)):
        if idx not in used:
            ordered_idxs.append(idx)

    ordered_entries = [entries[idx] for idx in ordered_idxs]
    raw_out = [entry[0] for entry in ordered_entries]
    labels_out = [entry[1] for entry in ordered_entries]
    counts_out = [entry[2] for entry in ordered_entries]
    return raw_out, labels_out, counts_out


def _normalize_pie_labels_map(labels):
    if labels is None:
        return {}
    if not isinstance(labels, dict):
        raise TypeError("labels must be a dict mapping raw labels to display labels.")
    out = {}
    for raw_label, display_label in labels.items():
        raw_s = str(raw_label).strip()
        display_s = str(display_label).strip()
        if raw_s == "":
            raise ValueError("labels keys must not be empty.")
        if display_s == "":
            raise ValueError("labels values must not be empty.")
        out[raw_s] = display_s
    return out


def _apply_pie_labels_map(raw_labels, labels_map):
    raw_labels_s = [str(label) for label in raw_labels]
    if len(labels_map) == 0:
        return raw_labels_s

    mapped = []
    seen_display = {}
    for raw_label in raw_labels_s:
        display_label = str(labels_map.get(raw_label, raw_label))
        prev_raw = seen_display.get(display_label)
        if prev_raw is not None and prev_raw != raw_label:
            raise ValueError(
                "labels maps multiple categories to the same display label. "
                "Use collapse_markers for category merging instead."
            )
        seen_display[display_label] = raw_label
        mapped.append(display_label)
    return mapped


def _count_unique_animals(df: pd.DataFrame, mask=None):
    if "AnimalName" not in df.columns:
        return None
    animals = df["AnimalName"] if mask is None else df.loc[mask, "AnimalName"]
    animals = animals.dropna().astype(str).str.strip()
    animals = animals[animals != ""]
    return int(animals.nunique())


def _pie_valid_row_mask(series: pd.Series, threshold=None):
    raw = series.copy()
    try:
        sentinel_mask = raw.astype(str).str.contains("NOT_INCLUDED_IN_EXPERIMENT", na=False)
        raw = raw.mask(sentinel_mask, np.nan)
    except Exception:
        pass

    th_vals = _normalize_threshold_values(threshold)
    if th_vals is not None:
        numeric = _to_numeric_excluding_not_included(raw)
        return numeric.notna()

    numeric = _to_numeric_excluding_not_included(raw)
    numeric_non_na = numeric.dropna()
    if len(numeric_non_na) > 0:
        return numeric.notna()

    text = raw.astype(str).str.strip()
    return raw.notna() & (text != "")


def _append_animal_n_inline(label, n_animals=None, include_N=False):
    if not include_N or n_animals is None:
        return str(label)
    return f"{label} (N={int(n_animals)})"


def _append_animal_n_multiline(label, n_animals=None, include_N=False):
    if not include_N or n_animals is None:
        return str(label)
    return f"{label}\nN={int(n_animals)}"


def _format_specificity_title_fragment(specificity):
    if specificity is None:
        return ""
    if not isinstance(specificity, (list, tuple)) or len(specificity) < 2:
        return ""

    spec_key, *raw_vals = specificity
    values = [
        str(value).strip()
        for value in _flatten_specificity_values(raw_vals)
        if str(value).strip() != ""
    ]
    if len(values) == 0:
        return ""

    key_label = get_display_name(spec_key, minimal=True)
    if len(values) == 1:
        value_label = values[0]
    else:
        value_label = " + ".join(values)
    return f"{key_label}={value_label}"


def _build_pie_context_title(label, *, group_name=None, specificity=None,
                             n_animals=None, include_N=False):
    header_parts = []
    group_text = str(group_name).strip() if group_name is not None else ""
    if group_text != "":
        header_parts.append(group_text)
    specificity_text = _format_specificity_title_fragment(specificity)
    if specificity_text != "":
        header_parts.append(specificity_text)

    title_lines = []
    if len(header_parts) > 0:
        title_lines.append(" | ".join(header_parts))
    title_lines.append(
        _append_animal_n_inline(
            label,
            n_animals=n_animals,
            include_N=include_N,
        )
    )
    return "\n".join(title_lines)


def _resolve_include_N_flag(include_N=False, include_n=None):
    if include_n is not None:
        return bool(include_n)
    return bool(include_N)


def _resolve_pie_value_flags(show_counts=None, show_pct=None, as_counts=None):
    if show_counts is not None or show_pct is not None:
        return bool(show_counts), bool(show_pct)
    if as_counts is not None:
        return bool(as_counts), not bool(as_counts)
    return False, True


def _pie_uses_count_scale(show_counts=False, show_pct=True):
    return bool(show_counts) and not bool(show_pct)


def _pie_value_save_tag(show_counts=False, show_pct=True):
    if show_counts and show_pct:
        return "counts+percent"
    if show_counts:
        return "counts"
    if show_pct:
        return "percent"
    return "no-values"


def _counts_to_percentages(counts):
    arr = np.asarray(counts, dtype=float)
    total = float(arr.sum())
    if total <= 0:
        return [0.0 for _ in arr.tolist()]
    return ((arr / total) * 100.0).tolist()


def _format_pie_value_label(count, pct, show_counts=False, show_pct=True):
    label_parts = []
    if show_counts:
        label_parts.append(f"{int(round(float(count)))}")
    if show_pct:
        label_parts.append(f"{float(pct):.1f}%")
    return "\n".join(label_parts)


def _build_pie_autopct(total_count, show_counts=False, show_pct=True):
    if not show_counts and not show_pct:
        return None

    def _autopct(pct):
        if pct <= 0:
            return ""
        count = int(round((float(pct) / 100.0) * float(total_count)))
        return _format_pie_value_label(
            count,
            pct,
            show_counts=show_counts,
            show_pct=show_pct,
        )

    return _autopct


def _annotate_stacked_distribution(ax, x_pos, group_order, group_counts,
                                   category_order, show_counts=False,
                                   show_pct=True):
    if not show_counts and not show_pct:
        return

    use_count_scale = _pie_uses_count_scale(show_counts=show_counts, show_pct=show_pct)
    for i, group_name in enumerate(group_order):
        g_counts = group_counts.get(group_name, {})
        total = float(sum(float(v) for v in g_counts.values()))
        bottom = 0.0
        for cat in category_order:
            raw_val = float(g_counts.get(cat, 0.0))
            pct = (raw_val / total) * 100.0 if total > 0 else 0.0
            val = raw_val if use_count_scale else pct
            if val <= 0:
                continue
            ax.text(
                x_pos[i],
                bottom + (val / 2.0),
                _format_pie_value_label(
                    raw_val,
                    pct,
                    show_counts=show_counts,
                    show_pct=show_pct,
                ),
                ha="center",
                va="center",
                fontsize=8,
                color="black",
            )
            bottom += val


def _compute_ridgeline_density(values, x_grid, bw_adjust=1.0):
    """Compute a smooth density curve for ridgeline plotting."""
    arr = np.asarray(values, dtype=float).reshape(-1)
    arr = arr[np.isfinite(arr)]
    dens = np.zeros_like(x_grid, dtype=float)
    if arr.size == 0:
        return dens

    bw_adj = float(max(1e-6, bw_adjust))
    if arr.size >= 2 and float(np.nanstd(arr)) > 0:
        try:
            from scipy.stats import gaussian_kde
            kde = gaussian_kde(arr)
            try:
                kde.set_bandwidth(bw_method=kde.factor * bw_adj)
            except Exception:
                pass
            dens = np.asarray(kde(x_grid), dtype=float)
        except Exception:
            dens = np.zeros_like(x_grid, dtype=float)

    if not np.any(dens > 0):
        # Histogram-based fallback when KDE is unavailable/unstable.
        bins = max(20, min(80, int(np.sqrt(max(1, arr.size))) * 6))
        hist, edges = np.histogram(
            arr,
            bins=bins,
            range=(float(np.min(x_grid)), float(np.max(x_grid))),
            density=True,
        )
        centers = (edges[:-1] + edges[1:]) / 2.0
        dens = np.interp(x_grid, centers, hist, left=0.0, right=0.0)

    if not np.any(dens > 0):
        # Last-resort tiny bump around the median.
        mu = float(np.nanmedian(arr))
        span = max(1e-6, float(np.max(x_grid) - float(np.min(x_grid))))
        sigma = span * 0.01
        dens = np.exp(-0.5 * ((x_grid - mu) / sigma) ** 2)

    max_d = float(np.max(dens))
    if max_d > 0:
        dens = dens / max_d
    return dens


def _resolve_control_name(control, available_groups):
    """Resolve control name against available groups (case-insensitive)."""
    if control is None:
        raise ValueError("control must be provided for volcano plotting.")
    ctrl = str(control).strip()
    if ctrl == "":
        raise ValueError("control cannot be empty.")
    for g in available_groups:
        if str(g) == ctrl:
            return str(g)
    ctrl_cf = ctrl.casefold()
    for g in available_groups:
        if str(g).casefold() == ctrl_cf:
            return str(g)
    raise ValueError(
        f"Control '{control}' not found in available groups: "
        f"{', '.join([str(g) for g in available_groups])}"
    )


def _volcano_pairwise_pvalue(control_vals, group_vals, force_nonparametric=False):
    """
    Compute two-group p-value using the same test selection logic as plot_mean_bars.

    Logic mirrors multipleComparisons for two groups:
    - if either group has <=1 sample -> Mann-Whitney U
    - else if normal (and not force_nonparametric) -> independent t-test
    - else -> Mann-Whitney U
    """
    g1 = pd.to_numeric(pd.Series(control_vals), errors="coerce").dropna()
    g2 = pd.to_numeric(pd.Series(group_vals), errors="coerce").dropna()
    if len(g1) == 0 or len(g2) == 0:
        return np.nan, "N/A"
    valid = [g1, g2]
    normal, _, _ = test_normality(valid, make_plot=False)
    if force_nonparametric:
        normal = False

    results_dict = {}
    if any(len(g) <= 1 for g in valid) or (not normal):
        pvalues, _, _, _, test_name = mwu_multiple_comparisons(
            valid,
            ["1-2"],
            results_dict,
            ns="ns",
        )
        if len(pvalues) == 0:
            return np.nan, "Mann-Whitney U"
        return float(pvalues[0]), test_name

    pvalues, _, _, _, test_name = runITTest(g1, g2, results_dict, ns="ns")
    if len(pvalues) == 0:
        return np.nan, "Independent T Test"
    return float(pvalues[0]), test_name


def _volcano_percent_change(control_mean, group_mean):
    """Percent change vs control, robust to zero-control edge cases."""
    c = float(control_mean)
    g = float(group_mean)
    if not np.isfinite(c) or not np.isfinite(g):
        return np.nan
    if c == 0:
        if g == 0:
            return 0.0
        return np.nan
    return ((g - c) / abs(c)) * 100.0


def _volcano_signed_log_percent_change(percent_change):
    """
    Signed log-scale transform for percent-change values.

    Uses sign(x) * log10(1 + |x|) so decreases remain negative and x=0 maps to 0.
    """
    x = float(percent_change)
    if not np.isfinite(x):
        return np.nan
    return float(np.sign(x) * np.log10(1.0 + abs(x)))


def _spread_label_positions(targets, y_min, y_max, min_gap):
    """
    Distribute 1D label positions with a minimum gap while staying in bounds.

    Returns positions in the original order of `targets`.
    """
    vals = np.asarray(targets, dtype=float)
    if vals.size == 0:
        return []
    if vals.size == 1:
        return [float(np.clip(vals[0], y_min, y_max))]

    order = np.argsort(vals)
    sorted_vals = vals[order].copy()
    sorted_vals[0] = max(sorted_vals[0], y_min)
    for i in range(1, len(sorted_vals)):
        sorted_vals[i] = max(sorted_vals[i], sorted_vals[i - 1] + min_gap)

    overflow = sorted_vals[-1] - y_max
    if overflow > 0:
        sorted_vals -= overflow

    underflow = y_min - sorted_vals[0]
    if underflow > 0:
        sorted_vals += underflow

    # Backward pass to preserve minimum gaps after bound corrections.
    for i in range(len(sorted_vals) - 2, -1, -1):
        sorted_vals[i] = min(sorted_vals[i], sorted_vals[i + 1] - min_gap)
    sorted_vals = np.clip(sorted_vals, y_min, y_max)

    out = np.empty_like(sorted_vals)
    out[order] = sorted_vals
    return [float(v) for v in out]


def _normalize_volcano_label_mode(label_points):
    """Normalize label selection mode for volcano annotations."""
    if label_points is None:
        return "significant"
    mode = str(label_points).strip().lower().replace("_", "-")
    aliases = {
        "sig": "significant",
        "significant": "significant",
        "nonsig": "non-significant",
        "non-significant": "non-significant",
        "non-significant-only": "non-significant",
        "non significant": "non-significant",
        "nonsignificant": "non-significant",
        "both": "both",
        "all": "both",
        "none": "none",
        "off": "none",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"significant", "non-significant", "both", "none"}:
        raise ValueError(
            "label_points must be one of: 'significant', 'non-significant', 'both', or 'none'."
        )
    return mode


def _resolve_marker_data_key(experiment, marker):
    """Resolve marker key in experiment.data with tolerant matching."""
    data_dict = getattr(experiment, "data", None)
    if not isinstance(data_dict, dict):
        raise ValueError("Experiment does not expose a valid 'data' dictionary.")

    marker_s = str(marker).strip()
    if marker_s in data_dict and hasattr(data_dict[marker_s], "df"):
        return marker_s

    lower_map = {
        str(k).casefold(): k
        for k, v in data_dict.items()
        if hasattr(v, "df")
    }
    marker_cf = marker_s.casefold()
    if marker_cf in lower_map:
        return lower_map[marker_cf]

    pref = [
        k for k, v in data_dict.items()
        if hasattr(v, "df") and str(k).casefold().startswith(marker_cf)
    ]
    if len(pref) == 1:
        return pref[0]
    if len(pref) > 1:
        preview = ", ".join([str(p) for p in pref[:10]]) + ("..." if len(pref) > 10 else "")
        raise ValueError(f"Ambiguous marker '{marker_s}'. Matches: {preview}")

    available = sorted([str(k) for k, v in data_dict.items() if hasattr(v, "df")])
    preview = ", ".join(available[:12]) + ("..." if len(available) > 12 else "")
    raise ValueError(f"Marker '{marker_s}' not found. Available markers: {preview}")


def _resolve_histogram_x_column(experiment, marker_key, x_attr):
    """
    Resolve histogram x column using the same raw-name mapping as extended IF export.

    Examples:
    - x_attr='Volume'        -> '<marker>_Volume'
    - x_attr='volume'        -> '<marker>_Volume' (case-insensitive)
    - x_attr='Marker_Volume' -> '<marker>_Volume'
    - x_attr='Volume (µm³)'  -> '<marker>_Volume' (via convert_raw_name label)
    """
    cols = [str(c) for c in experiment.data[marker_key].df.columns]
    marker_s = str(marker_key)
    x_raw = str(x_attr).strip()
    if x_raw == "":
        raise ValueError("x_attr cannot be empty.")

    def _norm(s):
        return re.sub(r"[^a-z0-9]+", "", str(s).casefold())

    # Build alias index from actual marker columns.
    alias_map = {}

    def _add_alias(alias, col):
        if alias is None:
            return
        key = _norm(alias)
        if key == "":
            return
        alias_map.setdefault(key, [])
        if col not in alias_map[key]:
            alias_map[key].append(col)

    marker_prefix = f"{marker_s}_"
    for col in cols:
        _add_alias(col, col)  # full raw column
        for alias in raw_coloc_column_aliases(col):
            _add_alias(alias, col)

        if col.casefold().startswith(marker_prefix.casefold()):
            suffix = col[len(marker_s) + 1:]
            _add_alias(suffix, col)               # suffix alias, e.g. Volume
            _add_alias(f"{marker_s}_{suffix}", col)  # explicit marker-prefixed alias
            for alias in raw_coloc_column_aliases(suffix):
                _add_alias(alias, col)
                _add_alias(f"{marker_s}_{alias}", col)

        # Extended IF export mapping alias (same as convert_raw_name in export)
        try:
            export_label, _ = convert_raw_name(col)
            _add_alias(export_label, col)
        except KeyError:
            pass

    candidates = [x_raw]
    marker_prefix = f"{marker_s}_"
    if x_raw.casefold().startswith(marker_prefix.casefold()):
        candidates.append(x_raw[len(marker_s) + 1:])
    else:
        candidates.append(f"{marker_prefix}{x_raw}")

    def _resolve_exact_match(candidate, values, *, kind):
        hits = [value for value in values if str(value).casefold() == str(candidate).casefold()]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            preview = ", ".join(hits[:8]) + ("..." if len(hits) > 8 else "")
            raise ValueError(
                f"Ambiguous x_attr '{x_attr}' for marker '{marker_s}' ({kind} match). "
                f"Matches: {preview}"
            )
        return None

    # Prefer exact raw column names and exact marker-suffix matches before
    # expanding legacy/canonical alias equivalences such as Contains vs VolContains.
    for cand in candidates:
        resolved = _resolve_exact_match(cand, cols, kind="full-column")
        if resolved is not None:
            return resolved

    marker_cols = [c for c in cols if c.casefold().startswith(marker_prefix.casefold())]
    marker_suffixes = {
        c[len(marker_s) + 1:]: c
        for c in marker_cols
        if len(c) > len(marker_s) + 1
    }
    for cand in candidates:
        resolved = _resolve_exact_match(cand, marker_suffixes.keys(), kind="suffix")
        if resolved is not None:
            return marker_suffixes[resolved]

    # Resolve candidate aliases.
    for cand in candidates:
        hits = alias_map.get(_norm(cand), [])
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            preview = ", ".join(hits[:8]) + ("..." if len(hits) > 8 else "")
            raise ValueError(f"Ambiguous x_attr '{x_attr}' for marker '{marker_s}'. Matches: {preview}")
    marker_cols = [c for c in cols if c.startswith(marker_prefix)]
    preview = ", ".join(marker_cols[:12]) + ("..." if len(marker_cols) > 12 else "")
    raise ValueError(
        f"Column mapping failed for marker '{marker_s}' and x_attr '{x_attr}'. "
        f"Use a suffix (e.g. 'Volume') or full name (e.g. '{marker_s}_Volume'). "
        f"Available columns: {preview}"
    )


def _artifact_name(name: str) -> str:
    """Create collision-safe artifact names (e.g., keep % distinct from base column)."""
    return str(name).replace('%', '_pct')


def _resolve_coloc_source_df(source, marker: str, df_override: pd.DataFrame | None = None):
    """Resolve marker DataFrame from experiment/batch source (or pass-through DataFrame)."""
    if df_override is not None:
        return df_override.copy(), source if not isinstance(source, pd.DataFrame) else None

    if isinstance(source, pd.DataFrame):
        return source.copy(), None

    if source is None:
        raise ValueError(
            "plot_coloc_upset requires an experiment/batch source (or a DataFrame input)."
        )

    data_dict = getattr(source, "data", None)
    if not isinstance(data_dict, dict):
        raise ValueError(
            "Provided source does not expose a 'data' dictionary for marker lookup."
        )

    marker_key = str(marker)
    if marker_key in data_dict and hasattr(data_dict[marker_key], "df"):
        return data_dict[marker_key].df.copy(), source

    lower_map = {str(k).lower(): k for k in data_dict.keys()}
    marker_lower = marker_key.lower()
    if marker_lower in lower_map:
        k = lower_map[marker_lower]
        if hasattr(data_dict[k], "df"):
            return data_dict[k].df.copy(), source

    candidates = [
        k for k, v in data_dict.items()
        if hasattr(v, "df") and str(k).startswith(marker_key)
    ]
    if len(candidates) == 1:
        return data_dict[candidates[0]].df.copy(), source

    available = sorted([str(k) for k, v in data_dict.items() if hasattr(v, "df")])
    preview = ", ".join(available[:12]) + ("..." if len(available) > 12 else "")
    raise ValueError(
        f"Marker '{marker_key}' not found in source.data. "
        f"Available marker keys: {preview}"
    )


def _enrich_df_grouping_columns(df: pd.DataFrame, exp_obj, requested_by: str | None = None):
    """Backfill Condition/factor columns from summary (or AnimalName parsing)."""
    out = df.copy()
    if exp_obj is None:
        return out

    cond_list = getattr(exp_obj, "condition_list", None)
    factors = []
    if cond_list is not None and hasattr(cond_list, "factor"):
        try:
            factors = list(cond_list.factor)
        except Exception:
            factors = []

    need_condition = "Condition" not in out.columns
    need_factors = [f for f in factors if f not in out.columns]
    need_requested = (
        requested_by is not None
        and requested_by not in {"conditions", "Condition"}
        and requested_by not in out.columns
    )
    if (not need_condition) and len(need_factors) == 0:
        if not need_requested:
            return out

    # If Region lives in index, expose it as a column for merge keys.
    if "Region" not in out.columns and str(out.index.name) == "Region":
        out = out.reset_index()

    summary = getattr(exp_obj, "summary", None)
    if isinstance(summary, pd.DataFrame) and len(summary) > 0:
        summary_cols = set(summary.columns)
        map_targets = ["Condition"] + [f for f in factors if f in summary_cols]
        if need_requested and requested_by in summary_cols and requested_by not in map_targets:
            map_targets.append(requested_by)

        if "Region" in out.columns and "Region" in summary_cols:
            region_cols = ["Region"] + [c for c in ["AnimalName"] + map_targets if c in summary_cols]
            region_map = summary[region_cols].dropna(subset=["Region"]).drop_duplicates(subset=["Region"], keep="first")
            out = out.merge(region_map, on="Region", how="left", suffixes=("", "__region"))
            for col in [c for c in ["AnimalName"] + map_targets if f"{c}__region" in out.columns]:
                if col in out.columns:
                    out[col] = out[col].where(out[col].notna(), out[f"{col}__region"])
                else:
                    out[col] = out[f"{col}__region"]
                out.drop(columns=[f"{col}__region"], inplace=True)

        if "AnimalName" in out.columns and "AnimalName" in summary_cols:
            an_cols = ["AnimalName"] + [c for c in map_targets if c in summary_cols]
            an_map = summary[an_cols].dropna(subset=["AnimalName"]).drop_duplicates(subset=["AnimalName"], keep="first")
            out = out.merge(an_map, on="AnimalName", how="left", suffixes=("", "__an"))
            for col in [c for c in map_targets if f"{c}__an" in out.columns]:
                if col in out.columns:
                    out[col] = out[col].where(out[col].notna(), out[f"{col}__an"])
                else:
                    out[col] = out[f"{col}__an"]
                out.drop(columns=[f"{col}__an"], inplace=True)

    if "Condition" not in out.columns and "AnimalName" in out.columns:
        out["Condition"] = [
            "".join(filter(str.isalpha, str(n)))
            for n in out["AnimalName"].tolist()
        ]

    if "Condition" in out.columns and len(factors) > 0:
        factor_dict = getattr(cond_list, "factorDict", {}) if cond_list is not None else {}
        for f in factors:
            if f in out.columns and out[f].notna().any():
                continue
            names = []
            if isinstance(factor_dict, dict) and f in factor_dict:
                names = [str(c.name) for c in factor_dict[f] if hasattr(c, "name")]
            if len(names) == 0:
                continue
            pattern = "(" + "|".join([re.escape(n) for n in names]) + ")"
            extracted = out["Condition"].astype(str).str.extract(pattern, expand=False)
            if f in out.columns:
                out[f] = out[f].where(out[f].notna(), extracted)
            else:
                out[f] = extracted

    return out


def _context_marker_df(ctx: Context, marker_name) -> pd.DataFrame:
    """Resolve marker df and apply the same grouping/context filtering style used elsewhere."""
    marker_key = _resolve_marker_data_key(ctx.experiment, marker_name)
    df = ctx.experiment.data[marker_key].df.reset_index()
    requested_by = ctx.factor if ctx.factor is not None else "Condition"
    df = _enrich_df_grouping_columns(df, ctx.experiment, requested_by=requested_by)
    return _filter_marker_df_for_context(ctx, df)


def location_tick_params(location_ax, hide_legend=True, black_background=False,
                         panel_line_width=1, row_index=0, n_rows=1,
                         col_index=0, n_cols=1,
                         x_limits=None, y_limits=None):
    """Style location scatter axes for tight side-by-side layout."""
    if x_limits is None:
        location_ax.set_xlim(xmin=0, xmax=500)
    else:
        location_ax.set_xlim(float(x_limits[0]), float(x_limits[1]))
    if y_limits is None:
        location_ax.set_ylim(ymin=-800, ymax=0)
    else:
        location_ax.set_ylim(float(y_limits[0]), float(y_limits[1]))
    location_ax.tick_params(
        axis='both', which='both',
        bottom=False, top=False, left=False, right=False,
        labelbottom=False, labelleft=False,
    )
    try:
        location_ax.set_box_aspect(1)
    except Exception:
        pass
    legend = location_ax.get_legend()
    if hide_legend and legend is not None:
        legend.set_visible(False)
    location_ax.set_facecolor('black' if bool(black_background) else 'none')
    line_width = max(0.0, float(panel_line_width))
    show_left = True
    show_right = int(col_index) == (max(1, int(n_cols)) - 1)
    show_top = int(row_index) == 0
    show_bottom = True

    spine_visibility = {
        'left': show_left,
        'right': show_right,
        'top': show_top,
        'bottom': show_bottom,
    }
    for spine_name, visible in spine_visibility.items():
        spine = location_ax.spines[spine_name]
        spine.set_visible(bool(visible))
        if visible:
            spine.set_color('white')
            spine.set_linewidth(line_width)
    location_ax.set(ylabel=None, xlabel=None)


def _resolve_location_extra_entry(experiment, objects, extra_graph):
    """Resolve one marker/column pair for an additional filtered location panel."""
    col_name = str(extra_graph).strip()
    if col_name == "":
        raise ValueError("Empty extra_graph column name.")
    resolved_objects = []
    seen = set()
    for obj in objects:
        obj_key = _resolve_marker_data_key(experiment, obj)
        if obj_key not in seen:
            seen.add(obj_key)
            resolved_objects.append(obj_key)

    matches = []
    for obj_key in resolved_objects:
        df = experiment.data[obj_key].df
        if col_name in df.columns:
            matches.append(obj_key)

    if len(matches) == 1:
        marker_key = matches[0]
    elif len(matches) > 1:
        preview = ", ".join([str(m) for m in matches])
        raise ValueError(
            f"Extra location graph column '{col_name}' is ambiguous across markers: {preview}"
        )
    else:
        marker_guess = col_name.split("_", 1)[0]
        marker_key = _resolve_marker_data_key(experiment, marker_guess)
        if col_name not in experiment.data[marker_key].df.columns:
            raise ValueError(
                f"Column '{col_name}' was not found in marker '{marker_key}' data."
            )

    label = get_display_name(col_name, compact_per=True)
    marker_prefix = f"{marker_key} "
    if label.casefold().startswith(marker_prefix.casefold()):
        label = label[len(marker_prefix):].strip()

    return {
        "marker": marker_key,
        "column": col_name,
        "label": label if label else col_name,
    }


def _normalize_location_marker_panels(markers):
    """Normalize marker panel input; tuples/lists mean merged marker panels."""
    seq_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)

    def _as_group(item):
        if isinstance(item, str):
            text = item.strip()
            return [text] if text else []
        if isinstance(item, seq_types):
            out = []
            for val in _flatten_specificity_values([item]):
                text = str(val).strip()
                if text:
                    out.append(text)
            return out
        text = str(item).strip()
        return [text] if text else []

    if markers is None:
        return []
    if isinstance(markers, str):
        group = _as_group(markers)
        return [group] if len(group) > 0 else []
    if isinstance(markers, tuple):
        group = _as_group(markers)
        return [group] if len(group) > 0 else []
    if isinstance(markers, (list, set, np.ndarray, pd.Series, pd.Index)):
        panels = []
        for item in list(markers):
            if item is None:
                continue
            group = _as_group(item)
            if len(group) == 0:
                continue
            if isinstance(item, str):
                panels.append([group[0]])
            else:
                panels.append(group)
        return panels
    group = _as_group(markers)
    return [group] if len(group) > 0 else []


def _location_marker_panel_label(markers):
    cleaned = []
    seen = set()
    for marker in markers or []:
        text = str(marker).strip()
        if text == "":
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    if len(cleaned) == 0:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return " + ".join(cleaned)


def _location_marker_panel_key(markers):
    cleaned = []
    seen = set()
    for marker in markers or []:
        text = str(marker).strip()
        if text == "":
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    return tuple(cleaned)


def _resolve_location_marker_panels(experiment, markers):
    panels = []
    for group in _normalize_location_marker_panels(markers):
        resolved = []
        seen = set()
        for marker in group:
            resolved_marker = _resolve_marker_data_key(experiment, marker)
            key = str(resolved_marker).casefold()
            if key in seen:
                continue
            seen.add(key)
            resolved.append(str(resolved_marker))
        if len(resolved) == 0:
            continue
        panels.append({
            "markers": resolved,
            "label": _location_marker_panel_label(resolved),
            "key": _location_marker_panel_key(resolved),
        })
    return panels


def _location_panel_markers(panel):
    if isinstance(panel, dict):
        return [str(marker) for marker in panel.get("markers", []) if str(marker).strip() != ""]
    if isinstance(panel, str):
        text = panel.strip()
        return [text] if text else []
    return [
        str(marker).strip()
        for marker in _flatten_specificity_values([panel])
        if str(marker).strip() != ""
    ]


def _location_panel_label(panel):
    if isinstance(panel, dict):
        label = str(panel.get("label", "")).strip()
        if label != "":
            return label
        return _location_marker_panel_label(panel.get("markers", []))
    return _location_marker_panel_label(_location_panel_markers(panel))


def _location_panel_key(panel):
    if isinstance(panel, dict):
        key = panel.get("key", None)
        if isinstance(key, tuple):
            return key
        return _location_marker_panel_key(panel.get("markers", []))
    return _location_marker_panel_key(_location_panel_markers(panel))


def _location_draw_roi_key_set(draw_roi, image_panels):
    if draw_roi in (None, False):
        return set()
    if draw_roi is True:
        return {_location_panel_key(panel) for panel in image_panels or []}
    out = set()
    for group in _normalize_location_marker_panels(draw_roi):
        out.add(_location_marker_panel_key(group))
    return out


def _normalize_location_extra_graphs(extra_graph, merge_extra_graphs=False):
    """Normalize extra_graph into a list of panel groups; tuples mean overlay groups."""
    seq_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)

    def _as_group(item):
        if isinstance(item, str):
            text = item.strip()
            return [text] if text else []
        if isinstance(item, seq_types):
            out = []
            for val in _flatten_specificity_values([item]):
                text = str(val).strip()
                if text:
                    out.append(text)
            return out
        text = str(item).strip()
        return [text] if text else []

    if extra_graph is None:
        return []
    if isinstance(extra_graph, str):
        return [[extra_graph.strip()]] if str(extra_graph).strip() else []
    if isinstance(extra_graph, tuple):
        group = _as_group(extra_graph)
        panels = [group] if len(group) > 0 else []
        if not bool(merge_extra_graphs):
            return panels
        merged = []
        seen = set()
        for panel in panels:
            for col in panel:
                if col not in seen:
                    seen.add(col)
                    merged.append(col)
        return [merged] if len(merged) > 0 else []
    if isinstance(extra_graph, (list, set, np.ndarray, pd.Series, pd.Index)):
        panels = []
        for item in list(extra_graph):
            if item is None:
                continue
            if isinstance(item, tuple):
                group = _as_group(item)
            elif isinstance(item, (list, set, np.ndarray, pd.Series, pd.Index)) and not isinstance(item, str):
                group = _as_group(item)
            else:
                group = _as_group(item)
                if len(group) > 1:
                    # Plain list-like top-level items other than tuples are treated as one panel.
                    pass
            if len(group) > 0:
                if not isinstance(item, tuple) and isinstance(item, str):
                    panels.append([group[0]])
                else:
                    panels.append(group)
        if not bool(merge_extra_graphs):
            return panels
        merged = []
        seen = set()
        for panel in panels:
            for col in panel:
                if col not in seen:
                    seen.add(col)
                    merged.append(col)
        return [merged] if len(merged) > 0 else []
    text = str(extra_graph).strip()
    panels = [[text]] if text else []
    if not bool(merge_extra_graphs):
        return panels
    return panels


def _location_overlay_bright_palette(n):
    """High-contrast palette for overlaying many extra_graph filters on one panel."""
    n_colors = max(0, int(n))
    if n_colors == 0:
        return []
    seed = [
        "#FFFFFF",  # white
        "#FFF176",  # yellow
        "#FF4D4D",  # red
        "#00E5FF",  # cyan
        "#76FF03",  # lime
        "#FF9100",  # orange
        "#FF40FF",  # magenta
        "#40C4FF",  # sky blue
        "#FFD740",  # amber
        "#64FFDA",  # aqua mint
    ]
    if n_colors <= len(seed):
        return [_coerce_location_plot_color(c) for c in seed[:n_colors]]
    extra = [tuple(c) for c in sns.color_palette("husl", n_colors=n_colors - len(seed))]
    return ([_coerce_location_plot_color(c) for c in seed] + extra)[:n_colors]


def _resolve_location_extra_color_map(extra_panels, extra_graph_colors=None,
                                      marker_colors=None, color_mode="set2"):
    """Resolve colors for extra location panels from dict/list/single value inputs."""
    flat_entries = []
    seen_cols = set()
    for panel in extra_panels:
        for entry in panel.get("entries", []):
            col = str(entry["column"])
            if col not in seen_cols:
                seen_cols.add(col)
                flat_entries.append(entry)

    if len(flat_entries) == 0:
        return {}

    mode = str(color_mode).strip().lower()
    if mode == "marker":
        default_map = {
            str(entry["column"]): _resolve_location_marker_color(
                entry.get("marker"),
                marker_colors=marker_colors,
            )
            for entry in flat_entries
        }
    elif mode == "overlay_bright":
        bright_palette = _location_overlay_bright_palette(len(flat_entries))
        default_map = {
            str(entry["column"]): bright_palette[i]
            for i, entry in enumerate(flat_entries)
        }
    else:
        default_palette = sns.color_palette("Set2", n_colors=max(1, len(flat_entries)))
        default_map = {
            str(entry["column"]): default_palette[i]
            for i, entry in enumerate(flat_entries)
        }

    # Tuple/list-defined merged extra panels should still default to the
    # high-contrast overlay palette even when only that one panel is merged.
    if mode != "overlay_bright":
        for panel in extra_panels:
            entries = list(panel.get("entries", []))
            if len(entries) <= 1:
                continue
            bright_palette = _location_overlay_bright_palette(len(entries))
            for i, entry in enumerate(entries):
                default_map[str(entry["column"])] = bright_palette[i]

    if extra_graph_colors is None:
        return default_map

    if isinstance(extra_graph_colors, dict):
        out = {}
        missing = []
        for entry in flat_entries:
            col = str(entry["column"])
            label = str(entry.get("label", col))
            color = None
            for key in (col, label):
                if key in extra_graph_colors:
                    color = extra_graph_colors[key]
                    break
            if color is None:
                missing.append(col)
            else:
                out[col] = color
        for col in missing:
            out[col] = default_map[col]
        return out

    if isinstance(extra_graph_colors, str):
        return {str(entry["column"]): extra_graph_colors for entry in flat_entries}

    if isinstance(extra_graph_colors, (list, tuple, np.ndarray, pd.Series, pd.Index)):
        colors = _flatten_specificity_values([extra_graph_colors])
        if len(colors) < len(flat_entries):
            raise ValueError(
                "extra_graph_colors sequence must provide at least one color per unique extra_graph column."
            )
        return {
            str(entry["column"]): colors[i]
            for i, entry in enumerate(flat_entries)
        }

    raise TypeError(
        "extra_graph_colors must be None, a dict, a color string, or a sequence of colors."
    )


def _resolve_location_extra_panels(experiment, objects, extra_graph, extra_graph_colors=None,
                                   marker_colors=None, merge_extra_graphs=False):
    """Resolve extra_graph input into panel specs for separate/overlay location plots."""
    groups = _normalize_location_extra_graphs(
        extra_graph,
        merge_extra_graphs=merge_extra_graphs,
    )
    if len(groups) == 0:
        return []

    panels = []
    for group in groups:
        entries = []
        seen_cols = set()
        for col_name in group:
            entry = _resolve_location_extra_entry(experiment, objects, col_name)
            col = str(entry["column"])
            if col in seen_cols:
                continue
            seen_cols.add(col)
            entries.append(entry)
        if len(entries) == 0:
            continue
        if len(entries) == 1:
            panel_label = str(entries[0]["label"])
        else:
            panel_label = _location_overlay_panel_label(entries)
        panels.append({
            "entries": entries,
            "label": panel_label,
        })

    color_mode = "overlay_bright" if bool(merge_extra_graphs) else "marker"
    color_map = _resolve_location_extra_color_map(
        panels,
        extra_graph_colors=extra_graph_colors,
        marker_colors=marker_colors,
        color_mode=color_mode,
    )
    for panel in panels:
        for entry in panel["entries"]:
            entry["color"] = color_map.get(str(entry["column"]))
    return panels


def _location_point_sizes(df: pd.DataFrame, marker_name, *, reference_df=None) -> np.ndarray:
    """Create readable point sizes for location panels using marker volume when available."""
    n = int(len(df))
    if n <= 0:
        return np.asarray([], dtype=float)
    size_col = f'{marker_name}_Volume'
    if size_col not in df.columns:
        return np.full(n, 45.0, dtype=float)
    vals = _to_numeric_excluding_not_included(df[size_col]).to_numpy(dtype=float)
    out = np.full(n, 45.0, dtype=float)
    finite = np.isfinite(vals)
    if not finite.any():
        return out
    ref_df = reference_df if isinstance(reference_df, pd.DataFrame) else df
    if size_col in ref_df.columns:
        ref_vals = _to_numeric_excluding_not_included(ref_df[size_col]).to_numpy(dtype=float)
        ref_finite = ref_vals[np.isfinite(ref_vals)]
    else:
        ref_finite = np.asarray([], dtype=float)
    finite_vals = vals[finite]
    if ref_finite.size > 0:
        vmin = float(np.min(ref_finite))
        vmax = float(np.max(ref_finite))
    else:
        vmin = float(np.min(finite_vals))
        vmax = float(np.max(finite_vals))
    if vmax > vmin:
        out[finite] = 25.0 + 95.0 * ((finite_vals - vmin) / (vmax - vmin))
    else:
        out[finite] = 60.0
    return out


def _location_size_norm(reference_df: pd.DataFrame | None, size_col: str):
    """Return stable min/max size normalization from the reference dataframe."""
    if not isinstance(reference_df, pd.DataFrame) or size_col not in reference_df.columns:
        return None
    ref_vals = _to_numeric_excluding_not_included(reference_df[size_col]).to_numpy(dtype=float)
    ref_finite = ref_vals[np.isfinite(ref_vals)]
    if ref_finite.size == 0:
        return None
    vmin = float(np.min(ref_finite))
    vmax = float(np.max(ref_finite))
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return None
    return (vmin, vmax)


def _location_marker_candidates(marker_name) -> list[str]:
    marker_s = str(marker_name).strip()
    if marker_s == "":
        return []
    candidates = [marker_s]
    trimmed = re.sub(r"_(?:exp)?\d+$", "", marker_s, flags=re.IGNORECASE)
    if trimmed != "" and trimmed not in candidates:
        candidates.append(trimmed)
    return candidates


def _location_marker_columns(df: pd.DataFrame, marker_name, raw=False) -> dict:
    """Resolve location coordinate/intensity/size columns for one marker dataframe."""
    x_suffix = "_RawXM" if bool(raw) else "_XM"
    y_suffix = "_RawYM" if bool(raw) else "_YM"

    for prefix in _location_marker_candidates(marker_name):
        x_col = f"{prefix}{x_suffix}"
        y_col = f"{prefix}{y_suffix}"
        if x_col in df.columns and y_col in df.columns:
            return {
                "prefix": prefix,
                "x": x_col,
                "y": y_col,
                "hue": f"{prefix}_IntDen",
                "size": f"{prefix}_Volume",
            }

    candidate_prefixes = []
    seen = set()
    for col in df.columns:
        col_s = str(col)
        if not col_s.endswith(x_suffix):
            continue
        prefix = col_s[:-len(x_suffix)]
        if prefix == "" or prefix in seen:
            continue
        y_col = f"{prefix}{y_suffix}"
        if y_col not in df.columns:
            continue
        seen.add(prefix)
        candidate_prefixes.append(prefix)

    marker_cf = str(marker_name).strip().casefold()
    matched = [
        prefix for prefix in candidate_prefixes
        if prefix.casefold() == marker_cf
        or prefix.casefold().startswith(marker_cf)
        or marker_cf.startswith(prefix.casefold())
    ]
    if len(matched) == 1:
        prefix = matched[0]
    elif len(candidate_prefixes) == 1:
        prefix = candidate_prefixes[0]
    else:
        prefix = str(marker_name).strip()

    return {
        "prefix": prefix,
        "x": f"{prefix}{x_suffix}",
        "y": f"{prefix}{y_suffix}",
        "hue": f"{prefix}_IntDen",
        "size": f"{prefix}_Volume",
    }


def _location_panel_has_not_included(df: pd.DataFrame, columns,
                                     sentinel="NOT_INCLUDED_IN_EXPERIMENT") -> bool:
    """True when any panel-relevant column contains NOT_INCLUDED sentinel text."""
    col_list = []
    for col in columns:
        if col in df.columns and col not in col_list:
            col_list.append(col)
    if len(col_list) == 0:
        return False

    for col in col_list:
        s = df[col]
        if (
            pd.api.types.is_object_dtype(s)
            or pd.api.types.is_string_dtype(s)
            or pd.api.types.is_categorical_dtype(s)
        ):
            try:
                if bool(s.astype(str).str.contains(str(sentinel), na=False).any()):
                    return True
            except Exception:
                continue
    return False


def _coerce_location_plot_color(color, fallback="grey"):
    """Resolve named/custom colors to a Matplotlib-safe color value."""
    color_dict = getattr(Config, "COLORS", {}) or {}
    lower_map = {str(k).casefold(): v for k, v in color_dict.items()}

    def _resolve(value):
        if value is None:
            return None
        if isinstance(value, (list, tuple, np.ndarray)):
            try:
                return tuple(mpl_to_rgb(value))
            except Exception:
                return None
        color_s = str(value).strip()
        if color_s == "":
            return None
        if color_s in color_dict:
            return color_dict[color_s]
        if color_s.casefold() in lower_map:
            return lower_map[color_s.casefold()]
        try:
            mpl_to_rgb(color_s)
            return color_s
        except Exception:
            return None

    resolved = _resolve(color)
    if resolved is not None:
        return resolved
    resolved_fallback = _resolve(fallback)
    return resolved_fallback if resolved_fallback is not None else "grey"


def _resolve_location_marker_color(marker_name, marker_colors=None):
    """Resolve one marker color from an explicit or global marker->color mapping."""
    color_map = LOCATION_MARKER_COLORS if marker_colors is None else marker_colors
    if not isinstance(color_map, Mapping):
        raise TypeError("marker_colors must be a dict-like mapping of marker names to colors.")

    marker_s = str(marker_name).strip()
    if marker_s in color_map:
        return _coerce_location_plot_color(color_map[marker_s])

    marker_cf = marker_s.casefold()
    for key, value in color_map.items():
        if str(key).strip().casefold() == marker_cf:
            return _coerce_location_plot_color(value)

    prefix_matches = []
    for key, value in color_map.items():
        key_s = str(key).strip()
        key_cf = key_s.casefold()
        if marker_cf.startswith(key_cf) or key_cf.startswith(marker_cf):
            prefix_matches.append((len(key_s), value))
    if len(prefix_matches) > 0:
        prefix_matches = sorted(prefix_matches, key=lambda item: item[0], reverse=True)
        return _coerce_location_plot_color(prefix_matches[0][1])

    return _coerce_location_plot_color(None)


def _mix_location_color(color, target_rgb, amount):
    """Blend a base color toward white/black for location hue gradients."""
    base_rgb = np.array(mpl_to_rgb(_coerce_location_plot_color(color)), dtype=float)
    target = np.array(target_rgb, dtype=float)
    mixed = ((1.0 - float(amount)) * base_rgb) + (float(amount) * target)
    return tuple(np.clip(mixed, 0.0, 1.0))


def _location_marker_palette(marker_name, marker_colors=None):
    """Create a light->dark palette from the resolved marker color."""
    base_color = _resolve_location_marker_color(marker_name, marker_colors=marker_colors)
    light_color = _mix_location_color(base_color, (1.0, 1.0, 1.0), amount=0.60)
    dark_color = _mix_location_color(base_color, (0.0, 0.0, 0.0), amount=0.35)
    return sns.blend_palette([light_color, dark_color], as_cmap=True)


def _location_contrast_edgecolor(color, black_background=False):
    """Choose a contrasting marker edge so bright fills remain visible."""
    try:
        r, g, b = mpl_to_rgb(_coerce_location_plot_color(color))
    except Exception:
        return "white" if bool(black_background) else "black"
    luminance = (0.2126 * float(r)) + (0.7152 * float(g)) + (0.0722 * float(b))
    if bool(black_background):
        return "black" if luminance >= 0.70 else "white"
    return "black" if luminance >= 0.60 else "white"


def _filter_image_df_for_context(ctx: Context, df: pd.DataFrame) -> pd.DataFrame:
    """Apply condition/factor/animal/region filtering to an imported image table."""
    out = df

    def _norm(series: pd.Series) -> pd.Series:
        return series.astype(str).str.strip().str.casefold()

    def _norm_animal(series: pd.Series) -> pd.Series:
        return series.map(normalize_animal_name)

    if ctx.factor is not None and ctx.factor_value is not None and ctx.factor in out.columns:
        target = str(ctx.factor_value).strip().casefold()
        direct = out[_norm(out[ctx.factor]) == target]
        if len(direct) > 0:
            out = direct

    if ctx.condition is not None and "Condition" in out.columns:
        target = str(ctx.condition).strip().casefold()
        direct = out[_norm(out["Condition"]) == target]
        if len(direct) > 0:
            out = direct

    if ctx.animal is not None and "AnimalName" in out.columns:
        target = normalize_animal_name(ctx.animal)
        out = out[_norm_animal(out["AnimalName"]) == target]

    if ctx.region is not None:
        target = str(ctx.region).strip().casefold()
        if "ROI" in out.columns:
            direct = out[_norm(out["ROI"]) == target]
            if len(direct) > 0:
                out = direct
        elif "ImageName" in out.columns:
            direct = out[_norm(out["ImageName"]) == target]
            if len(direct) > 0:
                out = direct

    return out


def _location_panel_scn(ctx: Context, df: pd.DataFrame, image_row=None) -> str | None:
    if getattr(ctx, "region", None) not in (None, ""):
        return str(ctx.region).strip()
    if isinstance(df, pd.DataFrame) and "Region" in df.columns:
        scns = [
            str(value).strip()
            for value in df["Region"].dropna().astype(str).tolist()
            if str(value).strip() != ""
        ]
        scns = list(dict.fromkeys(scns))
        if len(scns) == 1:
            return scns[0]
    if image_row is not None:
        roi_name = str(image_row.get("ROI", "")).strip()
        if roi_name != "":
            return roi_name
    return None


def _location_panel_image_roi(ctx: Context, df: pd.DataFrame, image_row=None) -> str | None:
    if isinstance(df, pd.DataFrame) and "ImageROI" in df.columns:
        roi_names = [
            normalize_image_roi_name(value)
            for value in df["ImageROI"].dropna().astype(str).tolist()
            if normalize_image_roi_name(value) != ""
        ]
        roi_names = list(dict.fromkeys(roi_names))
        if len(roi_names) == 1:
            return roi_names[0]
    if image_row is not None:
        roi_name = normalize_image_roi_name(image_row.get("ROI", ""))
        if roi_name != "":
            return roi_name
    return _location_panel_scn(ctx, df, image_row=image_row)


def _location_image_row_roi_name(value, *, from_image_name=False) -> str:
    text = str(value).strip()
    if text == "":
        return ""
    if from_image_name and "_" in text:
        text = text.rsplit("_", 1)[-1]
    return normalize_image_roi_name(text)


def _location_roi_aliases(value, animal_name=None) -> set[str]:
    value_s = str(value).strip()
    aliases = set()
    if value_s == "":
        return aliases

    value_cf = value_s.casefold()
    aliases.add(value_cf)
    aliases.add(re.sub(r"[^a-z0-9]+", "", value_cf))

    animal_s = str(animal_name).strip()
    if animal_s != "":
        animal_cf = animal_s.casefold()
        if value_cf.startswith(animal_cf):
            trimmed = value_cf[len(animal_cf):].strip("_ -")
            if trimmed != "":
                aliases.add(trimmed)
                aliases.add(re.sub(r"[^a-z0-9]+", "", trimmed))

    tail_num = re.search(r"(\d+)$", value_cf)
    if tail_num is not None:
        idx = str(int(tail_num.group(1)))
        aliases.add(idx)
        aliases.add(f"scn{idx}")
        aliases.add(f"roi{idx}")
        aliases.add(f"cropped{idx}")

    parts = [part for part in re.split(r"[_\s\-]+", value_cf) if part != ""]
    for part in parts:
        aliases.add(part)

    return {alias for alias in aliases if alias != ""}


def _location_match_roi_rows(image_df: pd.DataFrame, scn_name=None, animal_name=None) -> pd.DataFrame:
    if not isinstance(image_df, pd.DataFrame) or image_df.empty or scn_name in (None, ""):
        return image_df

    normalized_target = normalize_image_roi_name(scn_name)
    if normalized_target != "":
        exact_mask = pd.Series(False, index=image_df.index)
        for col in ["ROI", "ImageName"]:
            if col not in image_df.columns:
                continue
            norm_series = image_df[col].map(
                lambda value: _location_image_row_roi_name(value, from_image_name=(col == "ImageName"))
            )
            exact_mask = exact_mask | (norm_series == normalized_target)
        exact = image_df[exact_mask].copy()
        if not exact.empty:
            return exact

    target_aliases = _location_roi_aliases(scn_name, animal_name=animal_name)
    if len(target_aliases) == 0:
        return image_df

    roi_mask = pd.Series(False, index=image_df.index)
    for col in ["ROI", "ImageName"]:
        if col not in image_df.columns:
            continue
        series = image_df[col].fillna("").astype(str)
        alias_mask = series.map(
            lambda value: len(_location_roi_aliases(value, animal_name=animal_name) & target_aliases) > 0
        )
        roi_mask = roi_mask | alias_mask.astype(bool)

    matched = image_df[roi_mask].copy()
    return matched if not matched.empty else image_df.iloc[0:0].copy()


def _location_source_experiment(source, image_row=None, state=None):
    exp_name = ""
    if image_row is not None:
        exp_name = str(image_row.get("Experiment", "")).strip()
    if exp_name == "":
        return source

    exp_lookup = None if state is None else state.get("location_experiment_lookup")
    if not isinstance(exp_lookup, dict) or len(exp_lookup) == 0:
        exp_lookup = _representative_experiment_lookup(source)
        if isinstance(state, dict):
            state["location_experiment_lookup"] = exp_lookup
    return exp_lookup.get(exp_name, source)


def _location_marker_source_experiment_name(source, marker_name) -> str:
    data_dict = getattr(source, "data", None)
    if not isinstance(data_dict, dict):
        return ""
    try:
        marker_key = _resolve_marker_data_key(source, marker_name)
    except Exception:
        return ""
    marker_obj = data_dict.get(marker_key, None)
    exp_obj = getattr(marker_obj, "experiment", None)
    exp_name = str(getattr(exp_obj, "name", "")).strip()
    return exp_name


def _location_aux_table_frame(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        return df
    index_name = str(df.index.name).strip() if df.index.name is not None else ""
    if index_name != "" and index_name not in df.columns:
        return df.reset_index(drop=False).copy()
    return df.reset_index(drop=True).copy()


def _location_aux_table(exp_obj, table_name) -> pd.DataFrame | None:
    data_dict = getattr(exp_obj, "data", None)
    if not isinstance(data_dict, dict):
        return None

    target = str(table_name).strip().casefold()
    for key, value in data_dict.items():
        if not hasattr(value, "df"):
            continue
        if str(key).strip().casefold() == target:
            return _location_aux_table_frame(value.df)

    prefix_matches = []
    for key, value in data_dict.items():
        if not hasattr(value, "df"):
            continue
        key_s = str(key).strip().casefold()
        if key_s.startswith(target):
            prefix_matches.append(_location_aux_table_frame(value.df))
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    return None


def _location_roi_bounds(exp_obj, scn_name=None, animal_name=None, image_roi_name=None):
    roi_df = _location_aux_table(exp_obj, "ROIs")
    if not isinstance(roi_df, pd.DataFrame) or roi_df.empty:
        return None

    if animal_name not in (None, "") and "AnimalName" in roi_df.columns:
        mask = roi_df["AnimalName"].map(normalize_animal_name) == normalize_animal_name(animal_name)
        narrowed = roi_df[mask]
        if not narrowed.empty:
            roi_df = narrowed

    normalized_image_roi = normalize_image_roi_name(image_roi_name)
    if normalized_image_roi != "" and "ImageROI" in roi_df.columns:
        mask = roi_df["ImageROI"].map(normalize_image_roi_name) == normalized_image_roi
        narrowed = roi_df[mask]
        if not narrowed.empty:
            roi_df = narrowed
    if scn_name not in (None, "") and "Region" in roi_df.columns:
        mask = roi_df["Region"].astype(str).str.strip().str.casefold() == str(scn_name).strip().casefold()
        narrowed = roi_df[mask]
        if not narrowed.empty:
            roi_df = narrowed
    if roi_df.empty:
        return None

    row = roi_df.iloc[0]
    bounds = {}
    image_bound_map = {
        "left": ["ImageMinX", "ImageLeft", "left"],
        "top": ["ImageMinY", "ImageTop", "top"],
        "right": ["ImageMaxX", "ImageRight", "right"],
        "bottom": ["ImageMaxY", "ImageBottom", "bottom"],
        "width": ["ImageWidth", "width"],
        "height": ["ImageHeight", "height"],
    }
    for target_key, source_cols in image_bound_map.items():
        for source_col in source_cols:
            if source_col not in row.index:
                continue
            try:
                value = float(row[source_col])
            except Exception:
                continue
            if np.isfinite(value):
                bounds[target_key] = value
                break

    if "width" not in bounds and "left" in bounds and "right" in bounds:
        bounds["width"] = float(bounds["right"] - bounds["left"])
    if "height" not in bounds and "top" in bounds and "bottom" in bounds:
        bounds["height"] = float(bounds["bottom"] - bounds["top"])

    x_vals = row.get("x", None)
    y_vals = row.get("y", None)
    try:
        if x_vals is not None and y_vals is not None:
            xs = np.asarray(x_vals, dtype=float).ravel()
            ys = np.asarray(y_vals, dtype=float).ravel()
            xs = xs[np.isfinite(xs)]
            ys = ys[np.isfinite(ys)]
            if xs.size > 0 and ys.size > 0:
                bounds.setdefault("left", float(xs.min()))
                bounds.setdefault("top", float(ys.min()))
                bounds.setdefault("width", float(xs.max() - xs.min()))
                bounds.setdefault("height", float(ys.max() - ys.min()))
    except Exception:
        pass

    if "width" not in bounds or "height" not in bounds:
        return None
    return bounds


def _location_draw_roi_row(exp_obj, scn_name=None, animal_name=None, image_roi_name=None):
    roi_df = _location_aux_table(exp_obj, "ROIs To Draw")
    if not isinstance(roi_df, pd.DataFrame) or roi_df.empty:
        return None

    if animal_name not in (None, "") and "AnimalName" in roi_df.columns:
        mask = roi_df["AnimalName"].map(normalize_animal_name) == normalize_animal_name(animal_name)
        narrowed = roi_df[mask]
        if not narrowed.empty:
            roi_df = narrowed

    normalized_image_roi = normalize_image_roi_name(image_roi_name)
    if normalized_image_roi != "" and "ImageROI" in roi_df.columns:
        mask = roi_df["ImageROI"].map(normalize_image_roi_name) == normalized_image_roi
        narrowed = roi_df[mask]
        if not narrowed.empty:
            roi_df = narrowed

    if scn_name not in (None, "") and "Region" in roi_df.columns:
        mask = roi_df["Region"].astype(str).str.strip().str.casefold() == str(scn_name).strip().casefold()
        narrowed = roi_df[mask]
        if not narrowed.empty:
            roi_df = narrowed

    if roi_df.empty:
        return None
    return roi_df.iloc[0]


def _location_roi_dimensions(exp_obj, scn_name=None, animal_name=None):
    roi_props = _location_aux_table(exp_obj, "ROI Properties")
    if not isinstance(roi_props, pd.DataFrame) or roi_props.empty:
        return None

    if animal_name not in (None, "") and "AnimalName" in roi_props.columns:
        mask = roi_props["AnimalName"].map(normalize_animal_name) == normalize_animal_name(animal_name)
        narrowed = roi_props[mask]
        if not narrowed.empty:
            roi_props = narrowed
    if scn_name not in (None, "") and "Region" in roi_props.columns:
        mask = roi_props["Region"].astype(str).str.strip().str.casefold() == str(scn_name).strip().casefold()
        narrowed = roi_props[mask]
        if not narrowed.empty:
            roi_props = narrowed
    if roi_props.empty:
        return None

    row = roi_props.iloc[0]
    out = {}
    for key in ["Width", "Height"]:
        if key in row.index:
            try:
                out[key] = float(row[key])
            except Exception:
                pass
    if "Width" not in out or "Height" not in out:
        return None
    return out


def _location_marker_image_rows(image_df: pd.DataFrame, marker_prefix) -> pd.DataFrame:
    if "Marker" not in image_df.columns:
        return image_df.iloc[0:0].copy()
    candidates = _location_marker_candidates(marker_prefix)
    if len(candidates) == 0:
        return image_df.iloc[0:0].copy()

    marker_cf = image_df["Marker"].fillna("").astype(str).str.strip().str.casefold()
    mask = pd.Series(False, index=image_df.index)
    for candidate in candidates:
        cand_cf = str(candidate).strip().casefold()
        mask = mask | (marker_cf == cand_cf)
    matched = image_df[mask].copy()
    if not matched.empty:
        return matched

    mask = pd.Series(False, index=image_df.index)
    for candidate in candidates:
        cand_cf = str(candidate).strip().casefold()
        mask = mask | marker_cf.str.startswith(cand_cf)
    return image_df[mask].copy()


def _location_exact_roi_rows(image_df: pd.DataFrame, roi_name=None, animal_name=None) -> pd.DataFrame:
    if not isinstance(image_df, pd.DataFrame) or image_df.empty or roi_name in (None, ""):
        return image_df.iloc[0:0].copy()

    target_normalized = normalize_image_roi_name(roi_name)
    if target_normalized == "":
        return image_df.iloc[0:0].copy()
    mask = pd.Series(False, index=image_df.index)
    for col in ["ROI", "ImageName"]:
        if col not in image_df.columns:
            continue
        norm_series = image_df[col].map(
            lambda value: _location_image_row_roi_name(value, from_image_name=(col == "ImageName"))
        )
        mask = mask | (norm_series == target_normalized)
    exact = image_df[mask].copy()
    return exact if not exact.empty else image_df.iloc[0:0].copy()


def _score_location_image_row(row, *, roi_name=None, marker_prefix=None, experiment_name=None) -> tuple:
    roi_target = str(roi_name or "").strip().casefold()
    roi_target_compact = re.sub(r"[^a-z0-9]+", "", roi_target)
    marker_target = str(marker_prefix or "").strip().casefold()
    exp_target = str(experiment_name or "").strip().casefold()

    row_exp = str(row.get("Experiment", "")).strip().casefold()
    row_roi = str(row.get("ROI", "")).strip().casefold()
    row_roi_compact = re.sub(r"[^a-z0-9]+", "", row_roi)
    row_name = str(row.get("ImageName", "")).strip()
    row_name_cf = row_name.casefold()
    row_name_compact = re.sub(r"[^a-z0-9]+", "", row_name_cf)

    exact_experiment = int(exp_target != "" and row_exp == exp_target)
    exact_roi = int(roi_target != "" and row_roi == roi_target)
    compact_roi = int(roi_target_compact != "" and row_roi_compact == roi_target_compact)

    canonical_stem = ""
    canonical_compact = ""
    if marker_target != "" and roi_target != "":
        canonical_stem = f"{marker_target}_{roi_target}"
        canonical_compact = re.sub(r"[^a-z0-9]+", "", canonical_stem)
    exact_name = int(canonical_stem != "" and row_name_cf == canonical_stem)
    compact_name = int(canonical_compact != "" and row_name_compact == canonical_compact)

    has_merge = int("merge" in row_name_cf)
    has_variant = int(any(token in row_name_cf for token in ["bright", "brighter", "contrast", "enhanced", "copy"]))
    extra_suffix = int(canonical_compact != "" and row_name_compact.startswith(canonical_compact) and row_name_compact != canonical_compact)

    return (
        exact_experiment,
        exact_roi,
        compact_roi,
        exact_name,
        compact_name,
        -has_merge,
        -has_variant,
        -extra_suffix,
        -len(row_name_cf),
        row_name_cf,
    )


def _location_select_best_image_row(image_df: pd.DataFrame, *, roi_name=None, marker_prefix=None, experiment_name=None):
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return None
    scored = image_df.copy()
    scored["__score__"] = [
        _score_location_image_row(
            row,
            roi_name=roi_name,
            marker_prefix=marker_prefix,
            experiment_name=experiment_name,
        )
        for _, row in scored.iterrows()
    ]
    scored = scored.sort_values("__score__", ascending=False, kind="stable")
    return scored.drop(columns=["__score__"], errors="ignore").iloc[0]


def _resolve_location_image_row(ctx: Context, state, df: pd.DataFrame, marker_name):
    image_df = state.get("location_image_table") if isinstance(state, dict) else None
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return None

    marker_cols = _location_marker_columns(df, marker_name, raw=True)
    filtered = _filter_image_df_for_context(ctx, image_df)
    if filtered.empty:
        return None

    scn_name = _location_panel_scn(ctx, df)
    image_roi_name = _location_panel_image_roi(ctx, df)
    animal_name = str(getattr(ctx, "animal", "")).strip()
    experiment_name = _location_marker_source_experiment_name(ctx.experiment, marker_name)
    if experiment_name != "" and "Experiment" in filtered.columns:
        exp_match = filtered[
            filtered["Experiment"].fillna("").astype(str).str.strip().str.casefold() == experiment_name.casefold()
        ]
        if not exp_match.empty:
            filtered = exp_match
    if image_roi_name not in (None, ""):
        exact_roi = _location_exact_roi_rows(filtered, roi_name=image_roi_name, animal_name=animal_name)
        if not exact_roi.empty:
            filtered = exact_roi
        else:
            roi_match = _location_match_roi_rows(filtered, scn_name=image_roi_name, animal_name=animal_name)
            if not roi_match.empty:
                filtered = roi_match
    elif scn_name not in (None, ""):
        roi_match = _location_match_roi_rows(filtered, scn_name=scn_name, animal_name=animal_name)
        if not roi_match.empty:
            filtered = roi_match

    filtered = _location_marker_image_rows(filtered, marker_cols["prefix"])
    if filtered.empty:
        return None

    sort_cols = [col for col in ["Experiment", "AnimalName", "ROI", "ImageName"] if col in filtered.columns]
    if len(sort_cols) > 0:
        filtered = filtered.sort_values(sort_cols, kind="stable")
    if len(filtered) == 1:
        return filtered.iloc[0]
    return _location_select_best_image_row(
        filtered,
        roi_name=image_roi_name or scn_name,
        marker_prefix=marker_cols["prefix"],
        experiment_name=experiment_name,
    )


def _location_image_array(image_row, state, image_backend="auto"):
    if image_row is None:
        return None
    image_path = str(image_row.get("ImagePath", "")).strip()
    if image_path == "":
        return None
    image_adjustments = {}
    if isinstance(state, dict):
        image_adjustments = state.get("location_image_adjustments", {})
    fast_loading = bool(state.get("location_fast_loading", False)) if isinstance(state, dict) else False
    preview_max_dim = state.get("location_preview_max_dim", None) if isinstance(state, dict) else None
    marker_name = str(image_row.get("Marker", "")).strip()
    adj_key = _image_adjustment_cache_key(marker_name, image_adjustments=image_adjustments)
    cache = state.setdefault("location_image_cache", {}) if isinstance(state, dict) else {}
    cache_key = (image_path, adj_key, bool(fast_loading), preview_max_dim)
    if cache_key in cache:
        return cache[cache_key]
    image = read_image_array(
        image_path,
        backend=image_backend,
        fast_loading=fast_loading,
        preview_max_dim=preview_max_dim,
    )
    image = _apply_image_adjustments(image, marker_name=marker_name, image_adjustments=image_adjustments)
    if isinstance(state, dict):
        cache[cache_key] = image
    return image


def _location_overlay_coordinates(ctx: Context, state, df: pd.DataFrame, marker_name, image_row, image_array):
    marker_cols = _location_marker_columns(df, marker_name, raw=True)
    raw_x_col = marker_cols["x"]
    raw_y_col = marker_cols["y"]
    if raw_x_col not in df.columns or raw_y_col not in df.columns:
        return None

    x_vals = _to_numeric_excluding_not_included(df[raw_x_col]).to_numpy(dtype=float)
    y_vals = _to_numeric_excluding_not_included(df[raw_y_col]).to_numpy(dtype=float)
    valid = np.isfinite(x_vals) & np.isfinite(y_vals)
    if not valid.any():
        return None

    image_h, image_w = image_array.shape[:2]
    exp_obj = _location_source_experiment(ctx.experiment, image_row=image_row, state=state)
    scn_name = _location_panel_scn(ctx, df, image_row=image_row)
    image_roi_name = _location_panel_image_roi(ctx, df, image_row=image_row)
    animal_name = str(image_row.get("AnimalName", "")).strip() or str(getattr(ctx, "animal", "")).strip()

    roi_dims = _location_roi_dimensions(exp_obj, scn_name=scn_name, animal_name=animal_name)
    roi_bounds = _location_roi_bounds(
        exp_obj,
        scn_name=scn_name,
        animal_name=animal_name,
        image_roi_name=image_roi_name,
    )

    # Convert the stored raw location coordinates into the pixel frame used for
    # image overlay, then apply the ROI-origin shift used for the current panel.
    full_x_px = np.asarray(convert_microns_to_pixels(x_vals), dtype=float)
    full_y_px = np.asarray(convert_microns_to_pixels(y_vals), dtype=float)

    shift_from_original = False
    if isinstance(roi_bounds, dict):
        roi_left = float(roi_bounds.get("left", 0.0) or 0.0)
        roi_top = float(roi_bounds.get("top", 0.0) or 0.0)
        shift_from_original = (
            ("left" in roi_bounds)
            or ("top" in roi_bounds)
        )
    if shift_from_original and isinstance(roi_bounds, dict):
        x_plot = full_x_px + roi_left
        y_plot = full_y_px + roi_top
    else:
        x_plot = full_x_px
        y_plot = full_y_px

    x_plot = np.clip(x_plot, 0.0, max(0.0, float(image_w) - 1.0))
    y_plot = np.clip(y_plot, 0.0, max(0.0, float(image_h) - 1.0))

    return {
        "x": x_plot,
        "y": y_plot,
        "valid": valid,
        "limits": ((0.0, float(image_w)), (float(image_h), 0.0)),
        "marker_prefix": marker_cols["prefix"],
    }


def _location_point_edgecolors(df: pd.DataFrame, marker_name, *, hue=True, marker_colors=None):
    marker_cols = _location_marker_columns(df, marker_name, raw=False)
    marker_prefix = marker_cols["prefix"]
    base_rgb = np.asarray(mpl_to_rgb(_resolve_location_marker_color(marker_prefix, marker_colors=marker_colors)), dtype=float)
    n = int(len(df))
    if n <= 0:
        return np.empty((0, 3), dtype=float)

    edgecolors = np.repeat(base_rgb[None, :], n, axis=0)
    hue_col = marker_cols["hue"]
    if (not bool(hue)) or hue_col not in df.columns:
        return edgecolors

    hue_vals = _to_numeric_excluding_not_included(df[hue_col]).to_numpy(dtype=float)
    finite = np.isfinite(hue_vals)
    if not finite.any():
        return edgecolors

    cmap = _location_marker_palette(marker_prefix, marker_colors=marker_colors)
    finite_vals = hue_vals[finite]
    vmin = float(np.min(finite_vals))
    vmax = float(np.max(finite_vals))
    if vmax > vmin:
        scaled = (finite_vals - vmin) / (vmax - vmin)
        edgecolors[finite] = np.asarray(cmap(scaled))[:, :3]
    else:
        edgecolors[finite] = np.asarray(cmap(0.75))[:3]
    return edgecolors


def _draw_location_overlay_background(ax, image_array):
    if image_array.ndim == 2:
        ax.imshow(image_array, cmap="gray", origin="upper", zorder=0)
    else:
        ax.imshow(image_array, origin="upper", zorder=0)


def _location_roi_polygon_xy(row):
    x_vals = row.get("x", None)
    y_vals = row.get("y", None)
    if x_vals is None or y_vals is None:
        return None
    try:
        xs = np.asarray(x_vals, dtype=float).ravel()
        ys = np.asarray(y_vals, dtype=float).ravel()
    except Exception:
        return None
    valid = np.isfinite(xs) & np.isfinite(ys)
    xs = xs[valid]
    ys = ys[valid]
    if xs.size == 0 or ys.size == 0:
        return None
    if xs[0] != xs[-1] or ys[0] != ys[-1]:
        xs = np.concatenate([xs, xs[:1]])
        ys = np.concatenate([ys, ys[:1]])
    return xs, ys


def _location_transform_roi_polygon(xs, ys, *, overlay_with_images=False):
    if bool(overlay_with_images):
        return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)

    x_plot = convert_pixels_to_microns(np.asarray(xs, dtype=float)) * (500.0 / 1024.0)
    y_plot = convert_pixels_to_microns(np.asarray(ys, dtype=float)) * (-800.0 / 1024.0)
    return x_plot, y_plot


def _draw_location_roi_outline(ax, ctx: Context, state, df: pd.DataFrame,
                               *, overlay_with_images=False, image_row=None,
                               black_background=False):
    exp_obj = _location_source_experiment(ctx.experiment, image_row=image_row, state=state)
    scn_name = _location_panel_scn(ctx, df, image_row=image_row)
    image_roi_name = _location_panel_image_roi(ctx, df, image_row=image_row)
    animal_name = str(getattr(ctx, "animal", "")).strip()
    if image_row is not None:
        animal_name = str(image_row.get("AnimalName", "")).strip() or animal_name

    roi_row = _location_draw_roi_row(
        exp_obj,
        scn_name=scn_name,
        animal_name=animal_name,
        image_roi_name=image_roi_name,
    )
    if roi_row is None:
        return False

    polygon = _location_roi_polygon_xy(roi_row)
    if polygon is None:
        return False

    xs, ys = _location_transform_roi_polygon(
        polygon[0],
        polygon[1],
        overlay_with_images=overlay_with_images,
    )
    line_color = "white" if (bool(overlay_with_images) or bool(black_background)) else "black"
    ax.plot(
        xs,
        ys,
        color=line_color,
        linewidth=1.75,
        linestyle=(0, (4, 3)),
        dash_capstyle='round',
        alpha=1.0,
        zorder=2.0,
    )
    return True


def _draw_location_overlay_points(ax, x_vals, y_vals, sizes, edgecolors, *, zorder=3.0):
    overlay_sizes = (np.asarray(sizes, dtype=float) * 1.15) + 10.0
    ax.scatter(
        x_vals,
        y_vals,
        s=overlay_sizes,
        facecolors="none",
        edgecolors=edgecolors,
        linewidths=1.25,
        alpha=1.0,
        zorder=float(zorder),
    )


def _location_overlay_payload(ctx: Context, state, df: pd.DataFrame, marker_name, *, image_backend="auto"):
    image_row = _resolve_location_image_row(ctx, state, df, marker_name)
    if image_row is None:
        return None
    image_array = _location_image_array(image_row, state, image_backend=image_backend)
    if not isinstance(image_array, np.ndarray) or image_array.ndim < 2:
        return None
    coords = _location_overlay_coordinates(ctx, state, df, marker_name, image_row, image_array)
    if coords is None:
        return None
    coords["image"] = image_array
    coords["image_row"] = image_row
    return coords


def _location_overlay_payload_from_image(ctx: Context, state, df: pd.DataFrame,
                                         marker_name, image_row, image_array):
    if image_row is None or not isinstance(image_array, np.ndarray):
        return None
    coords = _location_overlay_coordinates(ctx, state, df, marker_name, image_row, image_array)
    if coords is None:
        return None
    coords["image"] = image_array
    coords["image_row"] = image_row
    return coords


def _location_image_panel_payload(ctx: Context, state, panel, *, specificity=None, image_backend="auto"):
    marker_names = _location_panel_markers(panel)
    image_rows = []
    image_arrays = []
    for marker_name in marker_names:
        try:
            df = _context_marker_df(ctx, marker_name)
        except Exception:
            continue
        df = _filter_df_by_specificity(df, specificity)
        image_row = _resolve_location_image_row(ctx, state, df, marker_name)
        if image_row is None:
            continue
        image_array = _location_image_array(image_row, state, image_backend=image_backend)
        if not isinstance(image_array, np.ndarray) or image_array.ndim < 2:
            continue
        image_rows.append(image_row)
        image_arrays.append(image_array)
    if len(image_arrays) == 0:
        return None
    merged_image = _merge_image_arrays(image_arrays)
    image_h, image_w = merged_image.shape[:2]
    return {
        "image": merged_image,
        "image_row": image_rows[0],
        "image_rows": image_rows,
        "limits": ((0.0, float(image_w)), (float(image_h), 0.0)),
    }


def _draw_location_image_panel(ax, ctx: Context, state, panel, *,
                               specificity=None,
                               draw_roi=False, black_background=False,
                               annotate=True):
    payload = _location_image_panel_payload(
        ctx,
        state,
        panel,
        specificity=specificity,
    )
    if payload is None:
        return None
    _draw_location_overlay_background(ax, payload["image"])
    marker_names = _location_panel_markers(panel)
    if bool(draw_roi) and len(marker_names) > 0:
        roi_df = _filter_df_by_specificity(_context_marker_df(ctx, marker_names[0]), specificity)
        _draw_location_roi_outline(
            ax,
            ctx,
            state,
            roi_df,
            overlay_with_images=True,
            image_row=payload["image_row"],
            black_background=black_background,
        )
    ax.set_facecolor('black' if bool(black_background) else 'none')
    if bool(annotate):
        _annotate_location_panel(ax, _location_panel_label(panel))
    return {
        "x_limits": payload["limits"][0],
        "y_limits": payload["limits"][1],
        "image_row": payload["image_row"],
        "image": payload["image"],
    }


def _location_panel_save_tag(objects, extra_panels):
    """Build a save-name stem by listing the plotted location panels."""
    panel_tags = []
    seen = set()

    for obj in objects or []:
        tag = _artifact_name(_location_panel_label(obj))
        if tag and tag not in seen:
            seen.add(tag)
            panel_tags.append(tag)

    for panel in extra_panels or []:
        for entry in panel.get("entries", []):
            tag = _artifact_name(str(entry.get("column", "")).strip())
            if tag and tag not in seen:
                seen.add(tag)
                panel_tags.append(tag)

    if len(panel_tags) == 0:
        return None
    return "__".join(panel_tags)


def _normalize_location_image_layout(image_layout) -> str:
    value = str(image_layout).strip().casefold().replace("_", " ").replace("-", " ")
    aliases = {
        "shared": "shared",
        "overlay": "shared",
        "overlaid": "shared",
        "same": "shared",
        "same axis": "shared",
        "sameaxis": "shared",
        "separate": "separate",
        "side by side": "separate",
        "sidebyside": "separate",
        "split": "separate",
    }
    normalized = aliases.get(value, value)
    if normalized not in {"shared", "separate"}:
        raise ValueError("image_layout must be 'shared' or 'separate'.")
    return normalized


def _location_context_name(ctx: Context, level, display=False):
    """Resolve the current outer grouping name for titles, saves, and progress."""
    level_s = str(level).strip().lower()
    if level_s == "conditions":
        if display and str(ctx.label).strip() != "":
            return str(ctx.label)
        return str(ctx.condition or "all")
    if level_s == "animals":
        return str(ctx.animal or ctx.condition or "all")
    if level_s in ("scns", "regions"):
        return str(ctx.region or ctx.animal or ctx.condition or "all")
    if level_s == "factors":
        return str(ctx.factor_value or ctx.condition or "all")
    if level_s == "columns":
        return str(ctx.column or "all")
    for value in (ctx.factor_value, ctx.region, ctx.animal, ctx.condition):
        if value not in (None, ""):
            return str(value)
    return "all"


def _location_join_rows(ctx: Context, join_by):
    """Number of row panels required for the current inner join level."""
    join_s = str(join_by).strip().lower()
    if join_s == "animals":
        return max(1, int(ctx.num_animals or 0))
    if join_s in ("scns", "regions"):
        return max(1, int(ctx.num_regions or 0))
    return 1


def _location_join_index(ctx: Context, join_by):
    """Row index for the current inner join item."""
    join_s = str(join_by).strip().lower()
    if join_s == "animals":
        return int(ctx.animal_index)
    if join_s in ("scns", "regions"):
        return int(ctx.region_index)
    return 0


def _location_active_panel_count(objects, extra_panels):
    """Count only location panels that are actually rendered."""
    return max(1, len(list(objects or [])) + len(list(extra_panels or [])))


def _location_display_panel_count(objects, extra_panels, *,
                                  overlay_with_images=False, image_layout="shared"):
    return _location_active_panel_count(objects, extra_panels)


def _location_panel_axes(axes_row, panel_index, *,
                         overlay_with_images=False, image_layout="shared"):
    idx = int(panel_index)
    return {
        "image_ax": None,
        "scatter_ax": axes_row[idx],
        "image_idx": None,
        "scatter_idx": idx,
    }


def _location_overlay_panel_label(entries):
    """Short overlay-panel label based on the source marker(s)."""
    markers = []
    seen = set()
    for entry in entries or []:
        marker_name = str(entry.get("marker", "")).strip()
        if marker_name == "" or marker_name in seen:
            continue
        seen.add(marker_name)
        markers.append(marker_name)
    if len(markers) == 1:
        return f"{markers[0]} Subsets"
    if len(markers) == 2:
        return f"{markers[0]} + {markers[1]} Subsets"
    if len(markers) > 2:
        return "Marker Subsets"
    return "Subsets"


def _location_legend_label(text):
    """Clean extra-panel legend labels for readability."""
    out = re.sub(r"\bVolComboAny\b", "", str(text))
    out = re.sub(r"\bVolCombo\b", "", out)
    out = re.sub(r"\bCPCComboAny\b", "", out)
    out = re.sub(r"\bCPCCombo\b", "", out)
    out = re.sub(r"\bComboAny\b", "", out)
    out = re.sub(r"\bCombo\b", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _location_panel_annotation_text(panel):
    """Build top-left annotation text for an extra location panel."""
    entries = panel.get("entries", []) if isinstance(panel, dict) else []
    if len(entries) > 1 and isinstance(panel, dict):
        label = str(panel.get("label", "")).strip()
        if label != "":
            return label
    column_names = []
    seen = set()
    for entry in entries:
        col = str(entry.get("column", "")).strip()
        if col == "" or col in seen:
            continue
        seen.add(col)
        column_names.append(col)
    if len(column_names) > 0:
        return "\n".join(column_names)
    return str(panel.get("label", "Filtered")) if isinstance(panel, dict) else "Filtered"


def _annotate_location_panel(ax, text):
    """Draw the top-left location panel label with consistent styling."""
    ax.annotate(
        str(text),
        xy=(0.02, 0.975), xycoords='axes fraction',
        fontsize=30, ha='left', va='top', color='white', weight='bold',
    )


def _resolve_location_colocaliser_panels(experiment, objects, colocaliser, extra_graph_colors=None):
    """Resolve colocaliser requests into _Contains_ filtered location panels."""
    if colocaliser in (None, False):
        return []

    resolved_objects = [_resolve_marker_data_key(experiment, obj) for obj in objects]
    base_object_set = {str(obj) for obj in resolved_objects}
    scalar_seq_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)

    def _make_panel(container_marker, other_marker):
        container_key = _resolve_marker_data_key(experiment, container_marker)
        other_s = str(other_marker).strip()
        if other_s == "":
            raise ValueError("colocaliser marker names cannot be empty.")
        col_name = f"{container_key}_Contains_{other_s}"
        if col_name not in experiment.data[container_key].df.columns:
            raise ValueError(
                f"Column '{col_name}' was not found in marker '{container_key}' data."
            )
        entry = _resolve_location_extra_entry(experiment, resolved_objects, col_name)
        entry["label"] = f"{container_key} Contains {other_s}"
        return {"entries": [entry], "label": entry["label"]}

    panel_specs = []

    if colocaliser is True:
        for container in resolved_objects:
            for other in resolved_objects:
                if str(other) == str(container):
                    continue
                col_name = f"{container}_Contains_{other}"
                if col_name in experiment.data[container].df.columns:
                    panel_specs.append((container, other))
    else:
        if isinstance(colocaliser, str):
            other_s = str(colocaliser).strip()
            found_any = False
            for container in resolved_objects:
                col_name = f"{container}_Contains_{other_s}"
                if col_name in experiment.data[container].df.columns:
                    panel_specs.append((container, other_s))
                    found_any = True
            if not found_any:
                expected = ", ".join([f"{obj}_Contains_{other_s}" for obj in resolved_objects])
                raise ValueError(
                    f"No _Contains_ columns found for colocaliser='{other_s}'. "
                    f"Expected one of: {expected}"
                )
        elif isinstance(colocaliser, scalar_seq_types):
            raw_specs = list(colocaliser)
            for spec in raw_specs:
                if spec in (None, False):
                    continue
                if isinstance(spec, str):
                    other_s = str(spec).strip()
                    matched = False
                    for container in resolved_objects:
                        col_name = f"{container}_Contains_{other_s}"
                        if col_name in experiment.data[container].df.columns:
                            panel_specs.append((container, other_s))
                            matched = True
                    if not matched:
                        expected = ", ".join([f"{obj}_Contains_{other_s}" for obj in resolved_objects])
                        raise ValueError(
                            f"No _Contains_ columns found for colocaliser='{other_s}'. "
                            f"Expected one of: {expected}"
                        )
                    continue

                if isinstance(spec, scalar_seq_types):
                    vals = list(spec)
                    if len(vals) != 2:
                        raise ValueError(
                            "colocaliser tuples/lists must be two items: (container_marker, other_marker)"
                        )
                    container_s = str(vals[0]).strip()
                    other_s = str(vals[1]).strip()
                    if container_s == "" or other_s == "":
                        raise ValueError(
                            "colocaliser tuples/lists must be two non-empty items: (container_marker, other_marker)"
                        )
                    if container_s not in base_object_set:
                        container_s = _resolve_marker_data_key(experiment, container_s)
                    panel_specs.append((container_s, other_s))
                    continue

                raise TypeError(
                    "colocaliser items must be marker strings or (container_marker, other_marker) pairs."
                )
        else:
            raise TypeError(
                "colocaliser must be None/False, True, a marker string, or a list/tuple of marker strings or pairs."
            )

    panels = []
    seen = set()
    for container_marker, other_marker in panel_specs:
        key = (str(container_marker), str(other_marker))
        if key in seen:
            continue
        seen.add(key)
        panels.append(_make_panel(container_marker, other_marker))

    if len(panels) == 0:
        return []

    color_map = _resolve_location_extra_color_map(panels, extra_graph_colors=extra_graph_colors)
    for panel in panels:
        for entry in panel["entries"]:
            entry["color"] = color_map.get(str(entry["column"]))
    return panels


def _plot_location_panel(ax, df, marker_name, *, annotate=True, panel_label=None,
                         hue=True, marker_colors=None,
                         draw_roi=False,
                         image_layout="shared", image_ax=None,
                         overlay_with_images=False, ctx=None, state=None,
                         black_background=False):
    """Render one location scatter panel."""
    marker_cols = _location_marker_columns(df, marker_name, raw=False)
    x_col = marker_cols["x"]
    y_col = marker_cols["y"]
    if x_col not in df.columns or y_col not in df.columns:
        raise ValueError(
            f"Location columns '{x_col}'/'{y_col}' were not found for marker '{marker_name}'."
        )

    resolved_image_layout = _normalize_location_image_layout(image_layout)
    shared_image_axis = bool(overlay_with_images) and resolved_image_layout == "shared"
    separate_image_axis = bool(overlay_with_images) and resolved_image_layout == "separate" and image_ax is not None

    if bool(overlay_with_images) and ctx is not None and isinstance(state, dict):
        payload = _location_overlay_payload(ctx, state, df, marker_name)
        if payload is not None:
            if shared_image_axis:
                _draw_location_overlay_background(ax, payload["image"])
                if bool(draw_roi):
                    _draw_location_roi_outline(
                        ax,
                        ctx,
                        state,
                        df,
                        overlay_with_images=True,
                        image_row=payload.get("image_row"),
                        black_background=black_background,
                    )
                sizes = _location_point_sizes(df, payload["marker_prefix"], reference_df=df)
                edgecolors = np.repeat(
                    np.asarray(mpl_to_rgb("white"), dtype=float)[None, :],
                    len(df),
                    axis=0,
                )
                _draw_location_overlay_points(
                    ax,
                    payload["x"],
                    payload["y"],
                    sizes,
                    edgecolors,
                    zorder=3.0,
                )
                if annotate:
                    _annotate_location_panel(ax, panel_label or str(marker_name))
                return {
                    "x_limits": payload["limits"][0],
                    "y_limits": payload["limits"][1],
                    "overlay": True,
                    "image_panel_limits": None,
                }
            if separate_image_axis:
                _draw_location_overlay_background(image_ax, payload["image"])
                if bool(draw_roi):
                    _draw_location_roi_outline(
                        image_ax,
                        ctx,
                        state,
                        df,
                        overlay_with_images=True,
                        image_row=payload.get("image_row"),
                        black_background=black_background,
                    )
                image_ax.set_facecolor('black' if bool(black_background) else 'none')
                return_image_limits = (payload["limits"][0], payload["limits"][1])
            else:
                return_image_limits = None
        else:
            return_image_limits = None
    else:
        return_image_limits = None

    plot_kwargs = dict(x=x_col, y=y_col, data=df, ax=ax, edgecolor='white')
    marker_color = _resolve_location_marker_color(marker_cols["prefix"], marker_colors=marker_colors)
    hue_col = marker_cols["hue"]
    size_col = marker_cols["size"]
    if bool(hue) and hue_col in df.columns:
        plot_kwargs['hue'] = hue_col
        plot_kwargs['palette'] = _location_marker_palette(marker_cols["prefix"], marker_colors=marker_colors)
    else:
        plot_kwargs['color'] = marker_color
    if size_col in df.columns:
        plot_kwargs['size'] = size_col
        plot_kwargs['sizes'] = (25.0, 120.0)
        size_norm = _location_size_norm(df, size_col)
        if size_norm is not None:
            plot_kwargs['size_norm'] = size_norm
    if bool(draw_roi) and ctx is not None:
        _draw_location_roi_outline(
            ax,
            ctx,
            state,
            df,
            overlay_with_images=False,
            image_row=None,
            black_background=black_background,
        )
    sns.scatterplot(**plot_kwargs)

    if annotate:
        _annotate_location_panel(ax, panel_label or str(marker_name))
    return {
        "x_limits": None,
        "y_limits": None,
        "overlay": False,
        "image_panel_limits": return_image_limits,
    }


def _plot_location_marker_group_panel(ax, ctx: Context, state, panel, *,
                                      annotate=True,
                                      hue=True,
                                      marker_colors=None,
                                      shared_image_panel=None,
                                      draw_roi=False,
                                      black_background=False,
                                      specificity=None,
                                      show_legend=False):
    from matplotlib.lines import Line2D

    marker_names = _location_panel_markers(panel)
    if len(marker_names) == 0:
        return {
            "x_limits": None,
            "y_limits": None,
            "overlay": False,
            "image_panel_limits": None,
        }

    image_payload = None
    if shared_image_panel is not None:
        image_payload = _location_image_panel_payload(
            ctx,
            state,
            shared_image_panel,
            specificity=specificity,
        )
        if image_payload is not None:
            _draw_location_overlay_background(ax, image_payload["image"])
            if bool(draw_roi) and len(marker_names) > 0:
                roi_df = _filter_df_by_specificity(_context_marker_df(ctx, marker_names[0]), specificity)
                _draw_location_roi_outline(
                    ax,
                    ctx,
                    state,
                    roi_df,
                    overlay_with_images=True,
                    image_row=image_payload["image_row"],
                    black_background=black_background,
                )

    handles = []
    labels = []
    any_plotted = False

    for marker_name in marker_names:
        df = _filter_df_by_specificity(_context_marker_df(ctx, marker_name), specificity)
        marker_cols = _location_marker_columns(df, marker_name, raw=False)
        x_col = marker_cols["x"]
        y_col = marker_cols["y"]
        hue_col = marker_cols["hue"]
        size_col = marker_cols["size"]
        sentinel_cols = [x_col, y_col]
        if bool(hue) and image_payload is None:
            sentinel_cols.append(hue_col)
        sentinel_cols.append(size_col)
        if _location_panel_has_not_included(df, sentinel_cols):
            continue

        marker_color = _resolve_location_marker_color(marker_cols["prefix"], marker_colors=marker_colors)
        edge_color = _location_contrast_edgecolor(marker_color, black_background=black_background)
        sizes = _location_point_sizes(df, marker_cols["prefix"], reference_df=df)

        if image_payload is not None:
            overlay_payload = _location_overlay_payload_from_image(
                ctx,
                state,
                df,
                marker_name,
                image_payload["image_row"],
                image_payload["image"],
            )
            if overlay_payload is None:
                continue
            edgecolors = np.repeat(
                np.asarray(mpl_to_rgb("white"), dtype=float)[None, :],
                len(df),
                axis=0,
            )
            _draw_location_overlay_points(
                ax,
                overlay_payload["x"],
                overlay_payload["y"],
                sizes,
                edgecolors,
                zorder=3.0,
            )
        else:
            plot_kwargs = dict(
                x=x_col,
                y=y_col,
                data=df,
                ax=ax,
                edgecolor='white',
                legend=False,
            )
            if bool(hue) and hue_col in df.columns:
                plot_kwargs['hue'] = hue_col
                plot_kwargs['palette'] = _location_marker_palette(marker_cols["prefix"], marker_colors=marker_colors)
            else:
                plot_kwargs['color'] = marker_color
            if size_col in df.columns:
                plot_kwargs['size'] = size_col
                plot_kwargs['sizes'] = (25.0, 120.0)
                size_norm = _location_size_norm(df, size_col)
                if size_norm is not None:
                    plot_kwargs['size_norm'] = size_norm
            sns.scatterplot(**plot_kwargs)

        if show_legend and len(marker_names) > 1:
            handles.append(
                Line2D(
                    [0], [0],
                    marker='o', linestyle='',
                    markerfacecolor=marker_color, markeredgecolor=edge_color,
                    markersize=16, alpha=1,
                )
            )
            labels.append(marker_name)
        any_plotted = True

    if annotate:
        _annotate_location_panel(ax, _location_panel_label(panel))
    if show_legend and len(handles) > 1:
        legend = ax.legend(
            handles,
            labels,
            loc='upper left',
            bbox_to_anchor=(1.01, 1.0),
            borderaxespad=0.0,
            frameon=False,
            title=None,
            fontsize=20,
            handlelength=0.8,
            handletextpad=0.25,
            labelspacing=0.35,
        )
        if legend is not None:
            for txt in legend.get_texts():
                txt.set_color('white')

    if image_payload is not None and any_plotted:
        return {
            "x_limits": image_payload["limits"][0],
            "y_limits": image_payload["limits"][1],
            "overlay": True,
            "image_panel_limits": None,
        }
    return {
        "x_limits": None,
        "y_limits": None,
        "overlay": False,
        "image_panel_limits": None,
    }


def _save_plotly_figure(fig, save_path, image_name, subfolder=None, verbose=True):
    """
    Save a Plotly figure as SVG if possible, else HTML fallback.

    SVG export requires the optional `kaleido` package.
    """
    image_name = strip_name(str(image_name))
    target_dir = save_path
    if subfolder is not None:
        target_dir = os.path.join(target_dir, subfolder)
    os.makedirs(target_dir, exist_ok=True)

    svg_path = os.path.join(target_dir, f"{image_name}.svg")
    try:
        fig.write_image(svg_path, format="svg")
        if verbose:
            _log.confirm(f"Figure saved to {svg_path}")
        return svg_path
    except Exception:
        html_path = os.path.join(target_dir, f"{image_name}.html")
        fig.write_html(html_path, include_plotlyjs="cdn")
        if verbose:
            _log.confirm(f"Figure saved to {html_path} (HTML fallback; install kaleido for SVG export)")
        return html_path


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ACTION FUNCTIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _bar_style_cycle(style_cycle=None) -> list:
    """Resolve the style-collision cycle, falling back to the default order.

    Default order: solid ``"fill"`` first (today's look is preserved), then a
    hollow outline, then hatch patterns for any further levels of a secondary
    factor. A caller-supplied *style_cycle* is used verbatim — so the
    first-colliding member keeps ``"fill"`` only if the custom cycle also starts
    with ``"fill"``; put it first to preserve the solid baseline.
    """
    if style_cycle:
        return [str(s) for s in style_cycle if str(s)]
    return ["fill", "hollow", "///", "...", "xxx", "\\\\\\"]


def _resolve_group_styles(group_order, color_map, explicit_styles, style_cycle=None) -> dict:
    """Assign a bar style to every group, varying only true (colour, style) collisions.

    Groups that share a colour are the ones at risk of looking identical (a
    crossed design collapses the secondary factor onto the primary's colour).
    Within each colour bucket we honour any explicitly-authored non-``"fill"``
    style first, then hand the remaining members distinct styles from the cycle.
    Buckets with a single member -- and therefore every non-crossed design --
    keep their own style untouched, so existing figures render exactly as before.
    """
    from collections import defaultdict

    default = "fill"
    cycle = _bar_style_cycle(style_cycle)

    buckets = defaultdict(list)
    for name in group_order:
        key = str(color_map.get(name, "")).strip().lower()
        buckets[key].append(name)

    resolved = {}
    for _color, names in buckets.items():
        if len(names) <= 1:
            for name in names:
                resolved[name] = explicit_styles.get(name, default) or default
            continue
        # Honour explicit, non-default styles before auto-assigning the rest.
        taken = set()
        for name in names:
            style = explicit_styles.get(name, default) or default
            if style != default:
                resolved[name] = style
                taken.add(style)
        pool = [s for s in cycle if s not in taken]
        pool_idx = 0
        for name in names:
            if name in resolved:
                continue
            if pool_idx < len(pool):
                resolved[name] = pool[pool_idx]
                pool_idx += 1
            else:
                resolved[name] = default
    return resolved


def _apply_bar_style(patches, style, color, line_width=2.5):
    """Restyle freshly-drawn bar patches for a non-default ``style`` token.

    ``"hollow"`` becomes an outline in the bar colour; any other token is used
    as a matplotlib hatch pattern (white-on-colour for contrast). ``"fill"`` is
    handled by the caller (it skips this entirely), so the solid path stays byte
    for byte identical to the original drawing.
    """
    style = (style or "fill")
    for patch in patches:
        if style in ("hollow", "outline", "open"):
            patch.set_facecolor("none")
            patch.set_edgecolor(color)
            patch.set_linewidth(line_width)
            patch.set_hatch(None)
        else:
            patch.set_facecolor(color)
            patch.set_hatch(style)
            patch.set_edgecolor("white")
            patch.set_linewidth(0.0)


def _resolve_bar_point_color(value, group_color, default):
    """Resolve point fill/edge color shorthands for mean-bar overlays."""
    if value is None:
        value = default
    if isinstance(value, str):
        key = value.strip().lower()
        if key in {"group", "condition", "color", "colour"}:
            return group_color
        if key in {"none", "transparent"}:
            return "none"
    return value


def _style_render(style) -> dict:
    """Translate a style token into per-primitive rendering hints.

    The same ``style`` channel reads differently across plot families: a bar is
    a patch, a radar trace is a line+fill+markers, a regression is markers+line.
    This returns the relevant pieces so each plot can honour the channel
    consistently — solid/dashed/dotted lines, filled vs open markers, and an
    optional hatch — without each call site re-deriving the mapping.
    """
    style = (style or "fill")
    if style == "fill":
        return {"filled": True, "hatch": None, "linestyle": "-", "marker_filled": True}
    if style in ("hollow", "outline", "open"):
        return {"filled": False, "hatch": None, "linestyle": "--", "marker_filled": False}
    return {"filled": True, "hatch": style, "linestyle": ":", "marker_filled": True}


def _style_map_for(conditions, auto_style=True, style_cycle=None, present=None) -> dict:
    """Bucket *conditions* by colour and resolve a style for each, by name.

    With *auto_style* off every member collapses to ``"fill"`` — matching the
    bar path, so disabling the channel is consistent across all plots. When
    *present* is given (a set of group names actually rendered), absent groups
    are dropped before bucketing so a lone survivor of a colour pair is not
    needlessly styled — again matching the bar path, which resolves against the
    groups present in the data rather than the whole design.
    """
    if present is not None:
        conditions = [c for c in conditions if str(getattr(c, "name", "")) in present]
    order = [str(getattr(c, "name", "")) for c in conditions]
    if not auto_style:
        return {name: "fill" for name in order}
    color_map = {str(getattr(c, "name", "")): getattr(c, "color", "") for c in conditions}
    explicit = {str(getattr(c, "name", "")): getattr(c, "style", "fill") for c in conditions}
    return _resolve_group_styles(order, color_map, explicit, style_cycle=style_cycle)


def _condition_style_map(experiment, auto_style=True, style_cycle=None, present=None) -> dict:
    """Resolve each condition's style over ``condition_list`` (or *present* subset).

    Buckets conditions by colour and varies only true (colour, style)
    collisions, exactly like the bar path. ``present`` restricts resolution to
    the conditions actually rendered. Returns ``{condition_name: style}``.
    """
    clist = list(getattr(experiment, "condition_list", []) or [])
    return _style_map_for(clist, auto_style=auto_style, style_cycle=style_cycle,
                          present=present)


def _factor_style_map(experiment, factor, auto_style=True, style_cycle=None,
                      present=None) -> dict:
    """Resolve each level of a single *factor* to a style, by level name.

    Mirrors :func:`_condition_style_map` but over the factor's sub-conditions
    (``conditionList.factorDict``), so factor-mode plots honour styles authored
    on a factor's levels and still vary any two levels that share a colour.
    ``present`` restricts resolution to the levels actually rendered.
    """
    clist = getattr(experiment, "condition_list", None)
    factor_dict = getattr(clist, "factorDict", {}) if clist is not None else {}
    conds = factor_dict.get(factor, []) if isinstance(factor_dict, dict) else []
    return _style_map_for(conds, auto_style=auto_style, style_cycle=style_cycle,
                          present=present)


def _present_group_names(ctx: Context, column) -> set | None:
    """Names present in the (roi-filtered) summary for *column*.

    Mirrors how the bar path derives ``present`` (see plot_mean_bars setup) so
    non-bar plots resolve over the same subset. Presence here means *has rows in
    the dataset*, deliberately NOT *has plottable values for the column/marker
    currently drawn*: a group's style is fixed by the design and stays stable
    across every column/panel, rather than flickering solid↔styled depending on
    whether its colour-partner happens to have numeric data for one panel.
    Returns ``None`` (no restriction) if the summary or column is unavailable.
    """
    summary = getattr(ctx, "summary", None)
    if summary is None or column not in getattr(summary, "columns", []):
        return None
    return set(summary[column].dropna().astype(str).unique())


def _resolved_condition_style(ctx: Context, state: dict,
                              auto_style=True, style_cycle=None) -> str:
    """Style token for the current group, caching the resolved map in *state*.

    Factor mode resolves over the factor's levels; condition mode over the whole
    crossed design. Both restrict to the groups present in the data, vary only
    true (colour, style) collisions, and collapse to ``"fill"`` when
    *auto_style* is off.
    """
    if ctx.factor_value is not None:
        cache = state.get("__factor_style_map__")
        if cache is None:
            cache = _factor_style_map(
                ctx.experiment, ctx.factor,
                auto_style=auto_style, style_cycle=style_cycle,
                present=_present_group_names(ctx, ctx.factor))
            state["__factor_style_map__"] = cache
        return cache.get(str(ctx.factor_value), "fill")
    cache = state.get("__condition_style_map__")
    if cache is None:
        cache = _condition_style_map(
            ctx.experiment, auto_style=auto_style, style_cycle=style_cycle,
            present=_present_group_names(ctx, "Condition"))
        state["__condition_style_map__"] = cache
    return cache.get(str(ctx.condition), "fill")


def _style_patch(color, style, label=None):
    """A legend swatch whose fill/outline/hatch mirrors a styled bar."""
    import matplotlib.patches as mpatches

    render = _style_render(style)
    if not render["filled"]:
        return mpatches.Patch(facecolor="none", edgecolor=color, linewidth=2.0,
                              hatch=render["hatch"], label=label)
    return mpatches.Patch(facecolor=color,
                          edgecolor=("white" if render["hatch"] else "none"),
                          hatch=render["hatch"], label=label)


def _condition_style_handles(experiment, names=None, labels=None,
                             color_map=None, style_map=None,
                             auto_style=True, style_cycle=None):
    """Build (handles, labels) for a colour+style condition key.

    Pass explicit ``names``/``color_map``/``style_map`` (e.g. the bar plot's
    already-resolved state) for an exact match, or let it resolve the whole
    design from *experiment*.
    """
    if color_map is None:
        color_map = _condition_color_map(experiment)
    if style_map is None:
        style_map = _condition_style_map(
            experiment, auto_style=auto_style, style_cycle=style_cycle)
    if names is None:
        names = list(color_map.keys())
    label_map = _condition_label_map(experiment) if labels is None else None

    handles, out_labels = [], []
    for name in names:
        label = (labels.get(name) if isinstance(labels, dict)
                 else (label_map.get(name, name) if label_map else name))
        handles.append(_style_patch(color_map.get(name, "black"),
                                    style_map.get(name, "fill"), label=label))
        out_labels.append(label)
    return handles, out_labels


def _apply_pie_wedge_style(wedges, style, color):
    """Hatch pie wedges for a non-default style so same-colour pies differ.

    Pies are inherently filled, so ``hollow`` is rendered as a default hatch
    rather than an empty wedge. That hatch (``"oo"``) is deliberately distinct
    from every hatch token in the default cycle (``/// ... xxx \\\\``) so a third
    same-colour level (which resolves to ``"///"``) never collides with the
    second (``hollow``); explicit hatch tokens pass straight through.
    """
    render = _style_render(style)
    hatch = render["hatch"] or (None if render["filled"] else "oo")
    if not hatch:
        return
    for wedge in wedges:
        wedge.set_hatch(hatch)
        wedge.set_edgecolor(color)


def bar_chart_action(ctx: Context, state: dict,
                     points=True, normalize=False,
                     point_fill="white", point_edge="group",
                     point_size=9, point_linewidth=3, **kwargs):
    """
    Plot a single bar + scatter points for one condition within one column.

    Expects state['ax'] to exist (set by setup).
    """
    ax = state['ax']
    col = ctx.column
    df = (ctx.factor_df if ctx.factor_value is not None else ctx.condition_df).reset_index()
    numeric_values = _to_numeric_excluding_not_included(df[col])

    if normalize:
        skip = any(c in col for c in ['%', 'VolumeMean', 'SurfaceMean', 'Ratio', 'Dist', 'Contains'])
        skip = skip or ('Coloc' in col and 'ColocCount' not in col)
        if not skip:
            col_min, col_max = numeric_values.min(), numeric_values.max()
            if pd.notna(col_min) and pd.notna(col_max) and col_max != col_min:
                numeric_values = (numeric_values - col_min) / (col_max - col_min) * 100

    df[col] = numeric_values
    values = numeric_values.dropna()
    if len(values) == 0:
        return {'condition': ctx.condition, 'mean': np.nan, 'n': 0}

    group_key = ctx.condition if ctx.condition is not None else ctx.factor_value
    mean = values.mean()
    color = state.get('group_color_map', {}).get(group_key, ctx.color or 'black')
    fallback_idx = ctx.condition_index if ctx.condition is not None else ctx.factor_index
    idx = state.get('group_index_map', {}).get(group_key, fallback_idx)

    # Bar
    n_patches_before = len(ax.patches)
    bar = sns.barplot(x=[idx], y=[mean], width=0.2, ax=ax, gap=-2.5,
                      color=color, edgecolor=None, saturation=1)

    # Second visual channel: restyle this bar when its (colour, style) collides
    # with another condition. 'fill' leaves the solid drawing untouched.
    style = state.get('group_style_map', {}).get(group_key, 'fill')
    if style and style != 'fill':
        _apply_bar_style(ax.patches[n_patches_before:], style, color)

    # Points (per animal)
    scatter = None
    if points:
        tmp = df[['AnimalName', col]].copy()
        tmp[col] = _to_numeric_excluding_not_included(tmp[col])
        animal_means = tmp.groupby('AnimalName')[col].mean().dropna()
        if len(animal_means) == 0:
            animal_means = pd.Series(dtype=float)
        point_face = _resolve_bar_point_color(point_fill, color, "white")
        point_edge = _resolve_bar_point_color(point_edge, color, "group")
        scatter = sns.swarmplot(
            x=[idx] * len(animal_means), y=animal_means.values,
            size=point_size, color=point_face, edgecolor=point_edge,
            linewidth=point_linewidth,
            label=(ctx.label if ctx.label else str(group_key)), clip_on=False, zorder=3, ax=ax,
        )

    # Store for stats/annotation in teardown
    if group_key is not None:
        state.setdefault('col_dfs_map', {})[group_key] = values
        state.setdefault('col_dfs_by_index', {})[idx] = values
        state.setdefault('group_key_by_index', {})[idx] = group_key
    else:
        state.setdefault('col_dfs', []).append(values)
    state.setdefault('bar', bar)
    state.setdefault('scatter', scatter)

    return {'condition': ctx.condition, 'mean': mean, 'n': len(values)}


def scatter_action(ctx: Context, state: dict,
                   marker=None, y=None, x=None, **kwargs):
    """Plot a strip/scatter for one condition."""
    ax = state['ax']
    df = _context_marker_df(ctx, marker) if marker else ctx.condition_df
    specificity = kwargs.get('specificity_filter', kwargs.get('specificity'))
    df = _filter_df_by_specificity(df, specificity)
    color = ctx.color

    plot = sns.stripplot(
        x=ctx.condition_index, y=y, data=df,
        color=color, s=7, alpha=0.6, jitter=0.3, ax=ax,
    )
    sns.despine(trim=False, ax=ax)
    return {'scatter': plot}


def histogram_action(ctx: Context, state: dict,
                     marker=None, x=None, bins=30, binwidth=None,
                     kde=False, alpha=0.5, stat='count',
                     invert_x=False, bin_range=None,
                     bins_spec=None, ymax=None, **kwargs):
    """Plot a histogram for one condition."""
    combine = bool(kwargs.get('combine', False) or kwargs.get('merge', False))
    idx = 0 if combine else (ctx.factor_index if ctx.factor_value is not None else ctx.condition_index)
    ax = _resolve_action_axis(state, idx)
    if ax is None:
        raise IndexError("No valid axis available for histogram_action.")
    df = ctx.experiment.data[marker].df.reset_index()
    df = _filter_marker_df_for_context(ctx, df)
    specificity = kwargs.get('specificity_filter', kwargs.get('specificity'))
    df = _filter_df_by_specificity(df, specificity)
    if x not in df.columns:
        raise ValueError(f"Column '{x}' not found in marker '{marker}' dataframe.")
    df = df.copy()
    df[x] = _to_numeric_excluding_not_included(df[x])
    df = df[df[x].notna()]

    group_name, group_color = _resolve_group_label_color(ctx)
    hist_kwargs = dict(
        data=df, x=x, ax=ax, color=group_color,
        alpha=alpha, stat=stat, kde=kde,
        edgecolor="none", linewidth=0,
    )
    if bins_spec is not None:
        hist_kwargs['bins'] = bins_spec
    else:
        hist_kwargs['bins'] = bins
        if binwidth is not None:
            hist_kwargs['binwidth'] = binwidth
        if bin_range is not None:
            hist_kwargs['binrange'] = bin_range

    if combine and len(df) > 0:
        hist_kwargs['label'] = group_name
    hist = sns.histplot(**hist_kwargs)
    # Force mapped axis labels (instead of raw dataframe column names).
    x_label = get_display_name(x, compact_per=True)
    marker_s = str(marker).strip()
    marker_prefix = f"{marker_s}_"
    if marker_s and str(x).casefold().startswith(marker_prefix.casefold()):
        marker_label = marker_s
        if marker_label.casefold() not in x_label.casefold():
            x_label = f"{marker_label} {x_label}".strip()
    ax.set_xlabel(x_label)
    stat_label_map = {
        "count": "Count",
        "frequency": "Frequency",
        "probability": "Probability",
        "percent": "Percent",
        "density": "Density",
    }
    stat_key = str(stat).strip().casefold()
    ax.set_ylabel(stat_label_map.get(stat_key, str(stat)))
    if ymax is not None:
        ax.set_ylim(top=float(ymax))
    if invert_x:
        ax.invert_xaxis()
    sns.despine(trim=False, ax=ax)
    return {'histogram': hist, 'condition': ctx.condition, 'group': group_name}


def ridgeline_action(ctx: Context, state: dict,
                     marker=None, x=None, x_grid=None,
                     ridge_height=0.85, alpha=0.55,
                     line_width=1.5, bw_adjust=1.0, **kwargs):
    """Plot one ridgeline density for the current condition/factor group."""
    ax = _resolve_action_axis(state, 0)
    if ax is None:
        raise IndexError("No valid axis available for ridgeline_action.")

    df = ctx.experiment.data[marker].df.reset_index()
    df = _filter_marker_df_for_context(ctx, df)
    specificity = kwargs.get('specificity_filter', kwargs.get('specificity'))
    df = _filter_df_by_specificity(df, specificity)
    if x not in df.columns:
        raise ValueError(f"Column '{x}' not found in marker '{marker}' dataframe.")

    values = _to_numeric_excluding_not_included(df[x]).dropna()
    idx = ctx.factor_index if ctx.factor_value is not None else ctx.condition_index
    group_name, group_color = _resolve_group_label_color(ctx)
    state.setdefault("ridge_labels", {})[idx] = group_name

    if len(values) == 0:
        return {'group': group_name, 'n': 0}

    dens = _compute_ridgeline_density(values.to_numpy(), x_grid, bw_adjust=bw_adjust)
    ridge_h = float(max(0.05, ridge_height))
    y0 = float(idx)
    y = y0 + (dens * ridge_h)

    ax.fill_between(
        x_grid, y0, y,
        color=group_color, alpha=float(alpha),
        linewidth=0.0, zorder=2 + idx,
    )
    ax.plot(
        x_grid, y,
        color=group_color, linewidth=float(line_width),
        zorder=3 + idx,
    )
    # Baseline separator for readability.
    ax.hlines(y0, float(np.min(x_grid)), float(np.max(x_grid)),
              color="white", linewidth=0.6, alpha=0.8, zorder=1)

    return {'group': group_name, 'n': int(len(values))}


def pie_chart_action(ctx: Context, state: dict,
                     marker=None, x=None, threshold=None,
                     start_angle=90, line_width=1.0,
                     plot_format='pie', as_counts=None,
                     order=None, **kwargs):
    """Plot a pie chart for one condition/factor group."""
    idx = ctx.factor_index if ctx.factor_value is not None else ctx.condition_index
    ax = _resolve_action_axis(state, idx)
    if ax is None:
        raise IndexError("No valid axis available for pie_chart_action.")

    df = ctx.experiment.data[marker].df.reset_index()
    df = _filter_marker_df_for_context(ctx, df)
    specificity = kwargs.get('specificity_filter', kwargs.get('specificity'))
    df = _filter_df_by_specificity(df, specificity)
    if x not in df.columns:
        raise ValueError(f"Column '{x}' not found in marker '{marker}' dataframe.")

    raw_labels, counts = _build_pie_counts_from_series(
        df[x],
        threshold=threshold,
        drop_zeros=(str(plot_format).strip().casefold() != 'bar'),
    )
    labels_map = _normalize_pie_labels_map(kwargs.get("labels"))
    labels = _apply_pie_labels_map(raw_labels, labels_map)
    raw_labels, labels, counts = _apply_pie_order(raw_labels, labels, counts, order)
    percentages = _counts_to_percentages(counts)
    n_animals = _count_unique_animals(df, mask=_pie_valid_row_mask(df[x], threshold=threshold))
    show_counts, show_pct = _resolve_pie_value_flags(
        show_counts=kwargs.get("show_counts"),
        show_pct=kwargs.get("show_pct"),
        as_counts=as_counts,
    )
    include_N = _resolve_include_N_flag(
        include_N=kwargs.get("include_N", False),
        include_n=kwargs.get("include_n"),
    )
    group_name, group_color = _resolve_group_label_color(ctx)

    x_label = get_display_name(x, compact_per=True)
    marker_s = str(marker).strip()
    marker_prefix = f"{marker_s}_"
    if marker_s and str(x).casefold().startswith(marker_prefix.casefold()):
        marker_label = marker_s
        if marker_label.casefold() not in x_label.casefold():
            x_label = f"{marker_label} {x_label}".strip()

    ax.clear()
    if len(counts) == 0:
        ax.axis("off")
        ax.text(0.5, 0.5, "No data available", ha="center", va="center")
    else:
        lw = max(0.0, float(line_width))
        plot_mode = str(plot_format).strip().casefold()
        if plot_mode == "bar":
            # Accumulate distributions for one combined stacked bar chart.
            state.setdefault("pie_bar_group_order", [])
            if group_name not in state["pie_bar_group_order"]:
                state["pie_bar_group_order"].append(group_name)
            state.setdefault("pie_bar_group_counts", {})[group_name] = {
                str(k): int(v) for k, v in zip(labels, counts)
            }
            state.setdefault("pie_bar_group_colors", {})[group_name] = group_color
            state.setdefault("pie_bar_group_styles", {})[group_name] = _resolved_condition_style(
                ctx, state, kwargs.get('auto_style', True), kwargs.get('style_cycle'))
            state.setdefault("pie_bar_group_n_animals", {})[group_name] = n_animals
            state.setdefault("pie_bar_category_order", [])
            state.setdefault("pie_bar_category_pairs", [])
            known_display_labels = {
                str(display_label)
                for _, display_label in state["pie_bar_category_pairs"]
            }
            for raw_label, lab in zip(raw_labels, labels):
                if lab not in state["pie_bar_category_order"]:
                    state["pie_bar_category_order"].append(lab)
                if lab not in known_display_labels:
                    state["pie_bar_category_pairs"].append((str(raw_label), str(lab)))
                    known_display_labels.add(str(lab))
            # Actual rendering happens in wrapper teardown (once, after all groups).
            ax.axis("off")
        else:
            edgecolor = group_color if lw > 0 else "none"
            pie_colors = _pie_gradient_colors(group_color, len(counts))
            total_count = int(np.sum(np.asarray(counts, dtype=float)))
            autopct = _build_pie_autopct(
                total_count,
                show_counts=show_counts,
                show_pct=show_pct,
            )
            _pie_style = _resolved_condition_style(
                ctx, state, kwargs.get('auto_style', True), kwargs.get('style_cycle'))
            _wedges = ax.pie(
                counts,
                labels=labels,
                startangle=float(start_angle),
                counterclock=False,
                autopct=autopct,
                wedgeprops={"linewidth": lw, "edgecolor": edgecolor},
                colors=pie_colors,
                textprops={"fontsize": 10},
            )[0]
            _apply_pie_wedge_style(_wedges, _pie_style, group_color)
            ax.axis("equal")
    if str(plot_format).strip().casefold() != "bar":
        ax.set_title(
            _build_pie_context_title(
                x_label,
                group_name=group_name,
                specificity=specificity,
                n_animals=n_animals,
                include_N=include_N,
            ),
            fontsize=14,
            weight="bold",
        )
    sns.despine(trim=False, ax=ax)
    return {
        'pie_labels': labels,
        'pie_raw_labels': raw_labels,
        'pie_counts': counts,
        'pie_percentages': percentages,
        'group': group_name,
        'n_animals': n_animals,
    }


def combo_pie_action(ctx: Context, state: dict,
                     marker=None, family="comboany",
                     include_none=True,
                     start_angle=90, line_width=1.0,
                     plot_format='pie', as_counts=None,
                     order=None, **kwargs):
    """Plot a pie chart for mutually exclusive Vol/CPC combo-family membership."""
    idx = ctx.factor_index if ctx.factor_value is not None else ctx.condition_index
    ax = _resolve_action_axis(state, idx)
    if ax is None:
        raise IndexError("No valid axis available for combo_pie_action.")

    family_key, family_prefix = _normalize_combo_pie_family(family)
    df = ctx.experiment.data[marker].df.reset_index()
    df = _filter_marker_df_for_context(ctx, df)
    specificity = kwargs.get('specificity_filter', kwargs.get('specificity'))
    df = _filter_df_by_specificity(df, specificity)

    combo_columns = _resolve_combo_family_columns(
        df,
        marker=marker,
        family=family_key,
        include_none=bool(include_none),
    )
    if len(combo_columns) == 0:
        raise ValueError(
            f"No {family_prefix} columns found for marker '{marker}'."
        )

    signature_series, category_order = _build_combo_signature_series(
        df,
        combo_columns,
        include_none=bool(include_none),
    )
    collapse_markers = _normalize_combo_collapse_markers(kwargs.get("collapse_markers"))
    signature_series, category_order = _collapse_combo_signature_series(
        signature_series,
        category_order,
        family=family_key,
        collapse_markers=collapse_markers,
        include_none=bool(include_none),
    )
    raw_labels, counts = _build_combo_counts_from_series(
        signature_series,
        category_order=category_order,
        drop_zeros=(str(plot_format).strip().casefold() != 'bar'),
    )
    labels_map = _normalize_pie_labels_map(kwargs.get("labels"))
    labels = _apply_pie_labels_map(raw_labels, labels_map)
    raw_labels, labels, counts = _apply_pie_order(raw_labels, labels, counts, order)
    percentages = _counts_to_percentages(counts)
    valid_mask = signature_series.notna() & signature_series.astype(str).str.strip().ne("")
    n_animals = _count_unique_animals(df, mask=valid_mask)
    show_counts, show_pct = _resolve_pie_value_flags(
        show_counts=kwargs.get("show_counts"),
        show_pct=kwargs.get("show_pct"),
        as_counts=as_counts,
    )
    include_N = _resolve_include_N_flag(
        include_N=kwargs.get("include_N", False),
        include_n=kwargs.get("include_n"),
    )
    group_name, group_color = _resolve_group_label_color(ctx)

    x_label = (
        f"{str(marker).strip()} {family_prefix}"
        f"{_combo_collapse_display_suffix(collapse_markers)}"
    ).strip()
    ax.clear()
    if len(counts) == 0:
        ax.axis("off")
        ax.text(0.5, 0.5, "No data available", ha="center", va="center")
    else:
        lw = max(0.0, float(line_width))
        plot_mode = str(plot_format).strip().casefold()
        if plot_mode == "bar":
            state.setdefault("pie_bar_group_order", [])
            if group_name not in state["pie_bar_group_order"]:
                state["pie_bar_group_order"].append(group_name)
            state.setdefault("pie_bar_group_counts", {})[group_name] = {
                str(k): int(v) for k, v in zip(labels, counts)
            }
            state.setdefault("pie_bar_group_colors", {})[group_name] = group_color
            state.setdefault("pie_bar_group_styles", {})[group_name] = _resolved_condition_style(
                ctx, state, kwargs.get('auto_style', True), kwargs.get('style_cycle'))
            state.setdefault("pie_bar_group_n_animals", {})[group_name] = n_animals
            state.setdefault("pie_bar_category_order", [])
            state.setdefault("pie_bar_category_pairs", [])
            known_display_labels = {
                str(display_label)
                for _, display_label in state["pie_bar_category_pairs"]
            }
            for raw_label, lab in zip(raw_labels, labels):
                if lab not in state["pie_bar_category_order"]:
                    state["pie_bar_category_order"].append(lab)
                if lab not in known_display_labels:
                    state["pie_bar_category_pairs"].append((str(raw_label), str(lab)))
                    known_display_labels.add(str(lab))
            ax.axis("off")
        else:
            edgecolor = group_color if lw > 0 else "none"
            pie_colors = _pie_gradient_colors(group_color, len(counts))
            total_count = int(np.sum(np.asarray(counts, dtype=float)))
            autopct = _build_pie_autopct(
                total_count,
                show_counts=show_counts,
                show_pct=show_pct,
            )
            _pie_style = _resolved_condition_style(
                ctx, state, kwargs.get('auto_style', True), kwargs.get('style_cycle'))
            _wedges = ax.pie(
                counts,
                labels=labels,
                startangle=float(start_angle),
                counterclock=False,
                autopct=autopct,
                wedgeprops={"linewidth": lw, "edgecolor": edgecolor},
                colors=pie_colors,
                textprops={"fontsize": 10},
            )[0]
            _apply_pie_wedge_style(_wedges, _pie_style, group_color)
            ax.axis("equal")
    if str(plot_format).strip().casefold() != "bar":
        ax.set_title(
            _build_pie_context_title(
                x_label,
                group_name=group_name,
                specificity=specificity,
                n_animals=n_animals,
                include_N=include_N,
            ),
            fontsize=14,
            weight="bold",
        )
    sns.despine(trim=False, ax=ax)
    return {
        'pie_labels': labels,
        'pie_raw_labels': raw_labels,
        'pie_counts': counts,
        'pie_percentages': percentages,
        'group': group_name,
        'n_animals': n_animals,
    }


def radar_action(ctx: Context, state: dict,
                 filtered_columns=None, statistic="mean", normalize=True,
                 fill=True, alpha=0.20, line_width=2.0, point_size=28,
                 tick_label_size=10, label_wrap=18, include_N=False,
                 show_animal_xs=True, animal_x_marker="x", animal_x_size=38,
                 animal_x_alpha=0.75, animal_x_color=None,
                 radial_value_radii=(0.30, 1.00), radial_value_color="grey",
                 radial_value_size=None,
                 **kwargs):
    """Plot one radar polygon for one condition/factor group."""
    by = 'factor' if ctx.factor_value is not None else 'condition'
    idx = ctx.factor_index if by == 'factor' else ctx.condition_index
    combine = bool(kwargs.get('combine', False))
    ax_idx = 0 if combine else idx
    ax = _resolve_action_axis(state, ax_idx)
    if ax is None:
        raise IndexError(f"No valid axis available for radar_action ({by} index={idx}).")

    columns = list(filtered_columns or [])
    if len(columns) < 3:
        raise ValueError("plot_radar needs at least three numeric columns.")

    source_df = ctx.factor_df if by == 'factor' else ctx.condition_df
    group_name, group_color = _resolve_group_label_color(ctx)
    _render = _style_render(_resolved_condition_style(
        ctx, state, kwargs.get('auto_style', True), kwargs.get('style_cycle')))
    scale_reference = kwargs.get('scale_reference')
    if bool(normalize) and scale_reference is None:
        scale_reference = _compute_radar_scale_reference(source_df, columns)
    raw_values, values = _radar_values_for_frame(
        source_df,
        columns,
        statistic,
        normalize=normalize,
        scale_reference=scale_reference,
    )
    animal_values = (
        _radar_animal_value_records(
            source_df,
            columns,
            statistic,
            normalize=normalize,
            scale_reference=scale_reference,
        )
        if bool(show_animal_xs)
        else []
    )

    valid_row_mask = pd.Series(False, index=source_df.index)
    for col in columns:
        if col in source_df.columns:
            valid_row_mask = valid_row_mask | _to_numeric_excluding_not_included(source_df[col]).notna()
    if 'AnimalName' in source_df.columns:
        n_animals = int(source_df.loc[valid_row_mask, 'AnimalName'].nunique())
    else:
        n_animals = int(valid_row_mask.sum())

    finite = np.isfinite(values)
    if not finite.any():
        state['radar_skip_save'] = True
        return {
            'radar': None,
            'group': group_name,
            'n_animals': n_animals,
            'values': values,
            'raw_values': raw_values,
            'animal_values': animal_values,
        }

    state['radar_skip_save'] = False
    state['radar_series_count'] = int(state.get('radar_series_count', 0)) + 1
    raw_max = float(np.nanmax(values[finite]))
    state['radar_raw_max'] = max(float(state.get('radar_raw_max', 0.0)), raw_max)

    radial_max = None if bool(normalize) else state.get('radar_raw_max')
    angles = _style_radar_axis(
        ax,
        columns,
        normalize=bool(normalize),
        tick_label_size=tick_label_size,
        label_wrap=label_wrap,
        radial_max=radial_max,
        radial_value_radii=radial_value_radii,
        radial_value_color=radial_value_color,
        radial_value_size=radial_value_size,
    )
    closed_angles = np.concatenate([angles, angles[:1]])
    closed_values = np.concatenate([values, values[:1]])
    legend_label = str(group_name)
    if include_N:
        legend_label = f"{legend_label} (n={n_animals})"

    ax.plot(
        closed_angles,
        closed_values,
        color=group_color,
        linewidth=float(line_width),
        linestyle=_render["linestyle"],
        label=legend_label,
        zorder=3,
    )
    if bool(fill) and _render["filled"]:
        polys = ax.fill(closed_angles, closed_values, color=group_color,
                        alpha=float(alpha), zorder=2)
        if _render["hatch"]:
            for poly in polys:
                poly.set_hatch(_render["hatch"])
                poly.set_edgecolor(group_color)
    if point_size is not None and float(point_size) > 0:
        if _render["marker_filled"]:
            ax.scatter(
                angles, values, color=group_color, s=float(point_size),
                edgecolor='black', linewidth=0.4, zorder=4,
            )
        else:
            ax.scatter(
                angles, values, facecolors='none', edgecolors=group_color,
                s=float(point_size), linewidth=1.2, zorder=4,
            )
    if (
        bool(show_animal_xs)
        and animal_x_marker is not None
        and animal_x_size is not None
        and float(animal_x_size) > 0
    ):
        marker_color = group_color if animal_x_color is None else animal_x_color
        marker_alpha = None if animal_x_alpha is None else float(animal_x_alpha)
        for record in animal_values:
            animal_y = np.asarray(record.get("values", []), dtype=float)
            animal_mask = np.isfinite(animal_y)
            if not animal_mask.any():
                continue
            ax.scatter(
                angles[animal_mask],
                animal_y[animal_mask],
                marker=animal_x_marker,
                s=float(animal_x_size),
                color=marker_color,
                alpha=marker_alpha,
                linewidths=1.0,
                label="_nolegend_",
                zorder=5,
            )

    title_label = f"{group_name} ({_radar_statistic_label(statistic)})"
    if include_N and not combine:
        title_label = f"{title_label}, n={n_animals}"
    if not combine:
        ax.set_title(title_label, fontsize=13, weight='bold', pad=18)
    return {
        'radar': ax,
        'group': group_name,
        'n_animals': n_animals,
        'values': values,
        'raw_values': raw_values,
        'animal_values': animal_values,
    }


def regression_action(ctx: Context, state: dict,
                      x=None, y=None, normalize_x=True, normalize_y=True,
                      test=None, **kwargs):
    """Plot a regression for one condition/factor."""
    by = 'factor' if ctx.factor_value is not None else 'condition'
    idx = ctx.factor_index if by == 'factor' else ctx.condition_index
    combine = bool(kwargs.get('combine', False))
    ax_idx = 0 if combine else idx
    ax = _resolve_action_axis(state, ax_idx)
    if ax is None:
        raise IndexError(f"No valid axis available for regression_action ({by} index={idx}).")
    group_name, group_color = _resolve_group_label_color(ctx)

    source_df = ctx.factor_df if by == 'factor' else ctx.condition_df
    df = source_df[[x, y]].copy()
    x_range = kwargs.get('x_range')
    y_range = kwargs.get('y_range')
    clip_fit_line = bool(kwargs.get('clip_fit_line', True))
    for col_name in (x, y):
        df[col_name] = _to_numeric_excluding_not_included(df[col_name])
    df = df.dropna(subset=[x, y])
    df[x] = _normalize_regression_series(df[x], normalize_x, axis_name=x)
    df[y] = _normalize_regression_series(df[y], normalize_y, axis_name=y)

    # Fall back to the experiment-level axis registry when no explicit bounds
    # were supplied. Normalization remaps values, so the registry is only a
    # valid reference when the axis is rendered in native units.
    if not normalize_x:
        x_range = _resolve_effective_axis_range(ctx.experiment, x, x_range)
    if not normalize_y:
        y_range = _resolve_effective_axis_range(ctx.experiment, y, y_range)

    if df.empty:
        set_display_name(ax, y, x, compact_per=True, fontdict={'weight': 'normal'}, size=25)
        sns.despine(trim=False, ax=ax)
        entry = {'group': group_name, 'p': np.nan, 'r': np.nan}
        if combine:
            state['regression_stats_entries'] = state.get('regression_stats_entries', []) + [entry]
        else:
            state['regression_stats_entries'] = [entry]
        return {'regression': None, 'r': np.nan, 'p': np.nan, 'group': group_name}

    color = group_color
    line_count_before = len(ax.lines)
    coll_count_before = len(ax.collections)
    if len(df) >= 2:
        reg = sns.regplot(
            x=x, y=y, data=df, ax=ax, color=color, ci=None,
            scatter_kws={'s': 400},
            line_kws={'lw': 6.75},
        )
    else:
        reg = sns.regplot(
            x=x, y=y, data=df, ax=ax, color=color, ci=None, fit_reg=False,
            scatter_kws={'s': 400},
        )

    fit_line = ax.lines[-1] if len(df) >= 2 and len(ax.lines) > line_count_before else None

    # Second visual channel: open markers + dashed/dotted fit line when this
    # condition shares a colour with another (e.g. crossed designs in combine).
    _render = _style_render(_resolved_condition_style(
        ctx, state, kwargs.get('auto_style', True), kwargs.get('style_cycle')))
    if not _render["marker_filled"]:
        for coll in ax.collections[coll_count_before:]:
            coll.set_facecolors('none')
            coll.set_edgecolors(color)
    if fit_line is not None and _render["linestyle"] != "-":
        fit_line.set_linestyle(_render["linestyle"])

    _apply_axis_range(ax, 'x', x_range)
    _apply_axis_range(ax, 'y', y_range)

    if clip_fit_line and fit_line is not None:
        _clip_regression_line_to_axes(fit_line, ax.get_xlim(), ax.get_ylim())

    if len(df) >= 2:
        try:
            corr, pval = _compute_correlation(df[x], df[y], test)
        except Exception:
            corr = np.nan
            pval = np.nan
    else:
        corr = np.nan
        pval = np.nan

    corr_text = _format_regression_rvalue(corr)
    sig_text = _get_annotation(float(pval), ns='') if np.isfinite(pval) else ''
    stats_text = f'r = {corr_text}{(" " + sig_text) if sig_text else ""}'

    entry = {'group': group_name, 'p': pval, 'r': corr}
    if combine:
        state['regression_stats_entries'] = state.get('regression_stats_entries', []) + [entry]
        note_idx = state.get('combine_rho_note_idx', 0)
        y_pos = max(0.02, 0.96 - (note_idx * 0.055))
        ax.annotate(
            f'{group_name}: {stats_text}',
            xy=(0.98, y_pos), xycoords='axes fraction',
            fontsize=13, ha='right', va='top', weight='bold', color=color,
        )
        state['combine_rho_note_idx'] = note_idx + 1
    else:
        state['regression_stats_entries'] = [entry]
        ax.annotate(
            stats_text,
            xy=(0.98, 0.95), xycoords='axes fraction',
            fontsize=22, ha='right', va='top', weight='bold',
        )

    set_display_name(ax, y, x, compact_per=True, fontdict={'weight': 'normal'}, size=25)
    sns.despine(trim=False, ax=ax)
    try:
        import PyFLASH.report as _report
        if _report.is_active():
            _report.emit(_report.build_correlation_record(
                x=x, y=y, group=group_name, n=int(len(df)),
                r=corr, p=pval, method=test,
            ))
    except Exception:
        pass
    return {
        'regression': reg,
        'r': corr,
        'p': pval,
        'group': group_name,
    }


def _format_side_stats_pvalue(p):
    """Format p-values consistently for compact side-panel summaries."""
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(p):
        return "n/a"
    if p < 0.0001:
        return f"{p:.2e}"
    return f"{p:.4f}".rstrip("0").rstrip(".")


def _format_regression_rvalue(r):
    try:
        r = float(r)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(r):
        return "n/a"
    return f"{r:.2f}"


def _regression_test_display_name(test):
    return _correlation_display_name(test)


def _annotate_regression_stats_summary(ax, entries, test):
    """Draw regression stats to the right of the axes, mirroring mean-bar stats."""
    lines = [f"Test: {_regression_test_display_name(test)}"]
    for entry in entries or []:
        label = str(entry.get("group") or "Group")
        lines.append(f"{label}: p={_format_side_stats_pvalue(entry.get('p'))}")

    ax.text(
        1.02, 1.0, "\n".join(lines),
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=10,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        clip_on=False,
    )


def scatter_3d_action(ctx: Context, state: dict,
                      x=None, y=None, z=None,
                      normalize_x=False, normalize_y=False, normalize_z=False,
                      **kwargs):
    """Plot a 3D scatter for one condition/factor."""
    by = 'factor' if ctx.factor_value is not None else 'condition'
    idx = ctx.factor_index if by == 'factor' else ctx.condition_index
    combine = bool(kwargs.get('combine', False))
    ax_idx = 0 if combine else idx
    ax = _resolve_action_axis(state, ax_idx)
    if ax is None:
        raise IndexError(f"No valid axis available for scatter_3d_action ({by} index={idx}).")
    group_name, group_color = _resolve_group_label_color(ctx)

    source_df = ctx.factor_df if by == 'factor' else ctx.condition_df
    size_by = kwargs.get('size_by')
    cols = [x, y, z]
    if size_by is not None and size_by not in cols:
        cols.append(size_by)
    df = source_df[cols].copy()
    x_range = kwargs.get('x_range')
    y_range = kwargs.get('y_range')
    z_range = kwargs.get('z_range')
    for col_name in (x, y, z):
        df[col_name] = _to_numeric_excluding_not_included(df[col_name])
    df = df.dropna(subset=[x, y, z])
    df[x] = _normalize_regression_series(df[x], normalize_x, axis_name=x)
    df[y] = _normalize_regression_series(df[y], normalize_y, axis_name=y)
    df[z] = _normalize_regression_series(df[z], normalize_z, axis_name=z)

    if not normalize_x:
        x_range = _resolve_effective_axis_range(ctx.experiment, x, x_range)
    if not normalize_y:
        y_range = _resolve_effective_axis_range(ctx.experiment, y, y_range)
    if not normalize_z:
        z_range = _resolve_effective_axis_range(ctx.experiment, z, z_range)

    if df.empty:
        return {'scatter': None, 'group': group_name}

    point_size = kwargs.get('point_size', 40)
    size_factor = kwargs.get('size_factor', 1.0)
    alpha = kwargs.get('alpha', 0.7)
    sizes = _scatter_point_sizes(
        df,
        size_by=size_by,
        point_size=point_size,
        size_factor=size_factor,
        size_norm=state.get('size_norm'),
    )
    ax.scatter(
        df[x], df[y], df[z],
        c=group_color, s=sizes, alpha=alpha,
        label=group_name,
        edgecolors='white', linewidths=0.3,
    )

    if x_range is not None and len(x_range) == 2:
        ax.set_xlim3d(x_range[0], x_range[1])
    if y_range is not None and len(y_range) == 2:
        ax.set_ylim3d(y_range[0], y_range[1])
    if z_range is not None and len(z_range) == 2:
        ax.set_zlim3d(z_range[0], z_range[1])

    ax.set_xlabel(get_display_name(x, compact_per=True), fontsize=12, weight='normal')
    ax.set_ylabel(get_display_name(y, compact_per=True), fontsize=12, weight='normal')
    ax.set_zlabel(get_display_name(z, compact_per=True), fontsize=12, weight='normal')

    return {'scatter': ax, 'group': group_name}


def location_scatter_action(ctx: Context, state: dict,
                            object_panels=None, merge=True,
                            colocalise=True, **kwargs):
    """Plot spatial locations for one animal/SCN."""
    from matplotlib.lines import Line2D

    join_by = kwargs.get('join_by', 'animals')
    idx = _location_join_index(ctx, join_by)

    extra_panels = kwargs.get('extra_panels') or []
    image_panels = kwargs.get('image_panels') or []
    point_n_cols = _location_active_panel_count(object_panels, extra_panels)
    image_layout = _normalize_location_image_layout(kwargs.get('image_layout', 'shared'))
    annotate = bool(kwargs.get('annotate', True))
    use_hue = bool(kwargs.get('hue', True))
    black_background = bool(kwargs.get('black_background', False))
    specificity = kwargs.get('specificity_filter')
    draw_roi_keys = kwargs.get('draw_roi_keys', set())
    shared_image_axis = len(image_panels) > 0 and image_layout == "shared"
    separate_image_axis = len(image_panels) > 0 and image_layout == "separate"
    if separate_image_axis:
        scatter_axes_grid = state['location_scatter_axes_grid']
        image_axes_grid = state['location_image_axes_grid']
        scatter_axes = list(np.ravel(scatter_axes_grid[idx, :max(1, point_n_cols)]))
        image_axes = list(np.ravel(image_axes_grid[idx, :image_axes_grid.shape[1]]))
    else:
        axes_grid = state['location_axes_grid']
        scatter_axes = list(np.ravel(axes_grid[idx, :max(1, point_n_cols)]))
        image_axes = [None] * max(1, len(image_panels))
    panel_line_width = max(0.0, float(kwargs.get('panel_line_width', 0.5)))
    marker_colors = kwargs.get('marker_colors')
    used_scatter_axes = set()
    used_image_axes = set()
    legend_axes = set()
    axis_limits = {}
    image_axis_limits = {}
    if separate_image_axis:
        for image_idx, image_panel in enumerate(image_panels):
            if image_idx >= len(image_axes):
                break
            image_info = _draw_location_image_panel(
                image_axes[image_idx],
                ctx,
                state,
                image_panel,
                specificity=specificity,
                draw_roi=_location_panel_key(image_panel) in draw_roi_keys,
                black_background=black_background,
                annotate=annotate,
            )
            if image_info is not None:
                image_axis_limits[image_idx] = (
                    image_info.get("x_limits"),
                    image_info.get("y_limits"),
                )
                used_image_axes.add(image_idx)

    for panel_idx, panel in enumerate(object_panels or []):
        if panel_idx >= len(scatter_axes):
            break
        shared_image_panel = image_panels[panel_idx] if shared_image_axis and panel_idx < len(image_panels) else None
        panel_info = _plot_location_marker_group_panel(
            scatter_axes[panel_idx],
            ctx,
            state,
            panel,
            annotate=annotate,
            hue=use_hue,
            marker_colors=marker_colors,
            shared_image_panel=shared_image_panel,
            draw_roi=(_location_panel_key(shared_image_panel) in draw_roi_keys) if shared_image_panel is not None else False,
            black_background=black_background,
            specificity=specificity,
            show_legend=(len(_location_panel_markers(panel)) > 1),
        )
        if isinstance(panel_info, dict) and panel_info.get("overlay"):
            axis_limits[panel_idx] = (panel_info.get("x_limits"), panel_info.get("y_limits"))
        if len(_location_panel_markers(panel)) > 1:
            legend_axes.add(panel_idx)
        used_scatter_axes.add(panel_idx)

    for panel_offset, panel in enumerate(extra_panels):
        panel_idx = len(object_panels or []) + panel_offset
        if panel_idx >= len(scatter_axes):
            break
        ax = scatter_axes[panel_idx]
        handles = []
        labels = []
        skip_panel = False
        legend_font_size = 20
        legend_marker_size = 16
        overlay_panel = len(panel.get("entries", [])) > 1
        panel_markers = []
        for entry in panel.get("entries", []):
            marker_name = str(entry.get("marker", "")).strip()
            if marker_name != "" and marker_name not in panel_markers:
                panel_markers.append(marker_name)
        if overlay_panel:
            base_markers = []
            seen_base_markers = set()
            for entry in panel.get("entries", []):
                marker_name = str(entry.get("marker", "")).strip()
                if marker_name == "" or marker_name in seen_base_markers:
                    continue
                seen_base_markers.add(marker_name)
                base_markers.append(marker_name)
            for marker_name in base_markers:
                base_df = _context_marker_df(ctx, marker_name)
                specificity = kwargs.get('specificity_filter')
                base_df = _filter_df_by_specificity(base_df, specificity)
                marker_cols = _location_marker_columns(base_df, marker_name, raw=False)
                x_col = marker_cols["x"]
                y_col = marker_cols["y"]
                if x_col not in base_df.columns or y_col not in base_df.columns:
                    raise ValueError(
                        f"Location columns '{x_col}'/'{y_col}' were not found for marker '{marker_name}' dataframe."
                    )
                if _location_panel_has_not_included(base_df, [x_col, y_col, marker_cols["size"]]):
                    continue
                base_color = _resolve_location_marker_color(marker_cols["prefix"], marker_colors=marker_colors)
                base_edge = _location_contrast_edgecolor(base_color, black_background=black_background)
                base_sizes = _location_point_sizes(base_df, marker_cols["prefix"], reference_df=base_df)
                if shared_image_axis:
                    base_payload = _location_overlay_payload(ctx, state, base_df, marker_name)
                    if base_payload is not None:
                        edgecolors = np.repeat(
                            np.asarray(mpl_to_rgb(base_color), dtype=float)[None, :],
                            len(base_df),
                            axis=0,
                        )
                        _draw_location_overlay_points(
                            ax,
                            base_payload["x"],
                            base_payload["y"],
                            base_sizes,
                            edgecolors,
                            zorder=1.0,
                        )
                    else:
                        ax.scatter(
                            base_df[x_col], base_df[y_col],
                            s=base_sizes, c=[base_color], edgecolors=base_edge, linewidths=0.35,
                            alpha=1, zorder=1.0, label=marker_name,
                        )
                else:
                    ax.scatter(
                        base_df[x_col], base_df[y_col],
                        s=base_sizes, c=[base_color], edgecolors=base_edge, linewidths=0.35,
                        alpha=1, zorder=1.0, label=marker_name,
                    )
                handles.append(
                    Line2D(
                        [0], [0],
                        marker='o', linestyle='',
                        markerfacecolor=base_color, markeredgecolor=base_edge,
                        markersize=legend_marker_size, alpha=1,
                    )
                )
                labels.append(marker_name)
        for entry in panel.get("entries", []):
            marker_name = entry['marker']
            filter_col = entry['column']
            df = _context_marker_df(ctx, marker_name)
            df = _filter_df_by_specificity(df, specificity)
            panel_ref_df = df.copy()
            if filter_col not in df.columns:
                raise ValueError(
                    f"Column '{filter_col}' was not found in marker '{marker_name}' dataframe."
                )
            df = df[_coerce_bool_like(df[filter_col])]
            marker_cols = _location_marker_columns(df, marker_name, raw=False)
            x_col = marker_cols["x"]
            y_col = marker_cols["y"]
            if x_col not in df.columns or y_col not in df.columns:
                raise ValueError(
                    f"Location columns '{x_col}'/'{y_col}' were not found for marker '{marker_name}'."
                )
            if _location_panel_has_not_included(df, [filter_col, x_col, y_col, marker_cols["size"]]):
                skip_panel = True
                break
            color = entry.get('color', 'white')
            edge_color = _location_contrast_edgecolor(color, black_background=black_background)
            size_ref_df = panel_ref_df if overlay_panel else df
            sizes = _location_point_sizes(df, marker_cols["prefix"], reference_df=size_ref_df)
            ax.scatter(
                df[x_col], df[y_col],
                s=sizes, c=[color], edgecolors=edge_color, linewidths=0.35,
                alpha=1, zorder=3.0, label=entry.get('label', filter_col),
            )
            handles.append(
                Line2D(
                    [0], [0],
                    marker='o', linestyle='',
                    markerfacecolor=color, markeredgecolor=edge_color,
                    markersize=legend_marker_size,
                )
            )
            labels.append(_location_legend_label(entry.get('label', filter_col)))

        if skip_panel:
            continue
        if annotate:
            _annotate_location_panel(ax, _location_panel_annotation_text(panel))
        if len(handles) > 1:
            legend = ax.legend(
                handles,
                labels,
                loc='upper left',
                bbox_to_anchor=(1.01, 1.0),
                borderaxespad=0.0,
                frameon=False,
                title=None,
                fontsize=legend_font_size,
                handlelength=0.8,
                handletextpad=0.25,
                labelspacing=0.35,
            )
            if legend is not None:
                for txt in legend.get_texts():
                    txt.set_color('white')
            legend_axes.add(panel_idx)
        used_scatter_axes.add(panel_idx)

    # Clean up axes
    for ax_idx, ax in enumerate(scatter_axes):
        if ax_idx in used_scatter_axes:
            location_tick_params(
                ax,
                hide_legend=(ax_idx not in legend_axes),
                black_background=black_background,
                panel_line_width=panel_line_width,
                row_index=idx,
                n_rows=(scatter_axes_grid.shape[0] if separate_image_axis else state['location_axes_grid'].shape[0]),
                col_index=ax_idx,
                n_cols=point_n_cols,
                x_limits=axis_limits.get(ax_idx, (None, None))[0],
                y_limits=axis_limits.get(ax_idx, (None, None))[1],
            )
            if ax_idx in legend_axes:
                legend = ax.get_legend()
                if legend is not None:
                    for txt in legend.get_texts():
                        txt.set_color('white')
        else:
            if black_background:
                ax.set_facecolor('black')
            ax.axis("off")
    if separate_image_axis:
        for ax_idx, ax in enumerate(image_axes):
            if ax_idx in used_image_axes:
                location_tick_params(
                    ax,
                    hide_legend=True,
                    black_background=black_background,
                    panel_line_width=panel_line_width,
                    row_index=idx,
                    n_rows=image_axes_grid.shape[0],
                    col_index=ax_idx,
                    n_cols=image_axes_grid.shape[1],
                    x_limits=image_axis_limits.get(ax_idx, (None, None))[0],
                    y_limits=image_axis_limits.get(ax_idx, (None, None))[1],
                )
            else:
                if black_background:
                    ax.set_facecolor('black')
                ax.axis("off")

    return {'name': ctx.animal or ctx.region}


def matrix_action(ctx: Context, state: dict,
                  filtered_columns=None, correlation='pearsonr',
                  first_columns=None, tick_label_size=25,
                  marker=None, prefix_order=None, marker_order=None,
                  drop_duplicate_columns=True,
                  enforce_shared_columns=False,
                  shared_columns=None,
                  **kwargs):
    """Plot a correlation matrix for one condition/factor."""
    ax = state['ax']
    fig = state['fig']
    correlation = _normalize_correlation_method(correlation)

    by = 'factor' if ctx.factor_value else 'condition'
    if marker:
        df = _context_marker_df(ctx, marker)
        specificity = kwargs.get('specificity_filter', kwargs.get('specificity'))
        df = _filter_df_by_specificity(df, specificity)
    else:
        df = ctx.factor_df if by == 'factor' else ctx.condition_df

    if bool(enforce_shared_columns) and shared_columns is not None:
        use_cols = list(shared_columns)
        converted = pd.DataFrame(index=df.index)
        dropped_cols = []
        sentinel = "NOT_INCLUDED_IN_EXPERIMENT"
        for col in use_cols:
            if col not in df.columns:
                converted[col] = np.nan
                dropped_cols.append(col)
                continue
            s = df[col].copy()
            sentinel_mask = s.astype(str).str.contains(str(sentinel), na=False)
            s = s.where(~sentinel_mask, np.nan)
            converted[col] = pd.to_numeric(s, errors='coerce')
        df = converted.reindex(columns=use_cols)
        valid_cols = use_cols
    else:
        df, valid_cols, dropped_cols = _prepare_matrix_numeric_df(
            df,
            filtered_columns,
            drop_duplicate_columns=bool(drop_duplicate_columns),
            require_complete_numeric=True,
        )
    if len(valid_cols) < 2:
        ax.text(
            0.5, 0.5,
            "Not enough valid numeric columns for matrix\n(after filtering/sentinel handling).",
            ha='center', va='center', transform=ax.transAxes
        )
        ax.set_axis_off()
        return {'heatmap': None, 'correlations': {}, 'dropped_columns': dropped_cols}

    def _marker_key(col_name):
        col_name = str(col_name)
        return col_name.split("_", 1)[0] if "_" in col_name else col_name
    # Backward-compatible alias: marker_order -> prefix_order.
    if prefix_order is None and marker_order is not None:
        prefix_order = marker_order
    marker_rank = {}
    if prefix_order is not None:
        marker_rank = {str(m): i for i, m in enumerate(prefix_order)}
    def _prefix_rank(col_name):
        col_s = str(col_name)
        if prefix_order is None:
            return 10**9
        for i, pref in enumerate(prefix_order):
            p = str(pref)
            if col_s.startswith(p) or _marker_key(col_s) == p:
                return i
        return 10**9
    def _marker_sort_tuple(col_name):
        mk = _marker_key(col_name)
        return (_prefix_rank(col_name), mk, str(col_name))

    if first_columns:
        pinned = [c for c in first_columns if c in df.columns]
        remaining = [c for c in df.columns if c not in pinned]
        remaining = sorted(remaining, key=_marker_sort_tuple)
        df = df.reindex(columns=pinned + remaining)
    else:
        grouped = sorted(df.columns.tolist(), key=_marker_sort_tuple)
        df = df.reindex(columns=grouped)

    corr = df.corr(method=_correlation_pandas_method(correlation))
    n_cols = max(1, len(corr.columns))
    # Adaptive sizing: treat tick_label_size as an upper bound. Large matrices
    # with long labels otherwise allocate most of the canvas to tick text and
    # visually crush the heatmap.
    tick_fs = max(7, min(int(tick_label_size), int(130 / n_cols)))
    star_fs = min(25, max(8, int(220 / n_cols)))
    coeff_label = f"{_correlation_display_name(correlation)} coefficient"

    heatmap = sns.heatmap(corr, annot=False, fmt=".2f", cmap='coolwarm',
                          linewidths=0.5, ax=ax, vmin=-1, vmax=1)
    try:
        cbar = heatmap.collections[0].colorbar
        cbar_tick_fs = max(16, int(tick_fs * 1.2))
        cbar_label_fs = max(18, int(tick_fs * 1.35))
        cbar.ax.tick_params(labelsize=cbar_tick_fs, width=2.0, length=8)
        cbar.ax.text(
            1.02, 1.05, coeff_label,
            transform=cbar.ax.transAxes,
            ha='left', va='bottom',
            fontsize=cbar_label_fs,
            fontweight='bold',
        )
    except Exception:
        pass

    # Annotate significance
    results = {}
    for i, c1 in enumerate(corr.columns):
        for j, c2 in enumerate(corr.columns):
            if i < j:
                valid = df[[c1, c2]].dropna()
                if len(valid) > 1:
                    coefficient, p_value = _compute_correlation(valid[c1], valid[c2], correlation)
                    star = _get_annotation(p_value, ns='')
                    ax.text(j + 0.5, i + 0.6, star, ha='center', va='center',
                            fontsize=star_fs, color='black', fontweight='bold')
                    results[f'{c1} vs {c2}'] = (p_value, coefficient)

    # Relabel ticks
    labels = [get_display_name(c, minimal=True) for c in corr.columns]
    tick_pos = np.arange(len(corr.columns), dtype=float) + 0.5
    ax.set_xticks(tick_pos)
    ax.set_yticks(tick_pos)
    ax.set_xticklabels(
        labels, rotation=60, ha='right', va='top',
        rotation_mode='anchor', fontsize=tick_fs,
    )
    ax.set_yticklabels(labels, rotation=0, ha='right', fontsize=tick_fs)

    return {'heatmap': heatmap, 'correlations': results}


def _get_annotation(p, ns='ns'):
    if ns == 'p':
        ns = round(p, 3)
    if p < 0.0001:
        return '****'
    elif p < 0.001:
        return '***'
    elif p < 0.01:
        return '**'
    elif p < 0.05:
        return '*'
    return ns


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ONE-LINER WRAPPERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def plot_mean_bars(experiment, filtered_columns=None,
                   points=True, normalize=False,
                   point_fill="white", point_edge="group",
                   point_size=9, point_linewidth=3,
                   specificity=None, roi=None, comparisons=None,
                   force_nonparametric=False, ns='ns',
                   posthoc='Conover', posthoc_correction='auto',
                   multiple_comparison='One-Way',
                   bottom_ticks=False, bottom_tick_labels=False,
                   factor=None, save=True,
                   column_strings=None, regex_string=None, exclude='',
                   save_normality=True, normality_dpi=96,
                   auto_style=True, style_cycle=None, legend=False,
                   dry_run=False):
    """
    Bar chart with individual data points for each column × condition.

    One figure per column, all conditions side by side.

    Conditions carry a second visual channel beyond ``color`` — a ``style``
    ("fill", "hollow", or a matplotlib hatch like "///"). When *auto_style* is
    True (default), any two conditions that would otherwise share a colour *and*
    style (e.g. the diagnosis×sex bars of a crossed design, which all inherit
    the diagnosis colour) are automatically given distinct styles so the
    secondary factor reads clearly. Styles authored on the conditions always
    win; *style_cycle* overrides the default fill→hollow→hatch order. Designs
    with no such collision render exactly as before. Set ``auto_style=False`` to
    disable and keep every bar solid.

    When *dry_run* is True, compute stats for every column but skip
    figure creation/saving.  Returns a pandas DataFrame of results.

    The overlaid points keep the historical white-fill/group-outline look by
    default. Set ``point_fill="group"``, ``point_edge="none"``, and tune
    ``point_size``/``point_linewidth`` for filled condition-coloured dots.
    """
    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_mean_bars(
                experiment,
                filtered_columns=filtered_columns,
                points=points,
                normalize=normalize,
                point_fill=point_fill,
                point_edge=point_edge,
                point_size=point_size,
                point_linewidth=point_linewidth,
                specificity=specificity,
                roi=_rb,
                comparisons=comparisons,
                force_nonparametric=force_nonparametric,
                ns=ns,
                posthoc=posthoc,
                posthoc_correction=posthoc_correction,
                multiple_comparison=multiple_comparison,
                bottom_ticks=bottom_ticks,
                bottom_tick_labels=bottom_tick_labels,
                factor=factor,
                save=save,
                column_strings=column_strings,
                regex_string=regex_string,
                exclude=exclude,
                save_normality=save_normality,
                normality_dpi=normality_dpi,
                auto_style=auto_style,
                style_cycle=style_cycle,
                legend=legend,
                dry_run=dry_run,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    # Queue mode: allow multiple specificity filters in one call.
    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec_tuple in _iter_specificities(specificity):
            queued_outputs[spec_tuple] = plot_mean_bars(
                experiment,
                filtered_columns=filtered_columns,
                points=points,
                normalize=normalize,
                point_fill=point_fill,
                point_edge=point_edge,
                point_size=point_size,
                point_linewidth=point_linewidth,
                specificity=spec_tuple,
                roi=roi,
                comparisons=comparisons,
                force_nonparametric=force_nonparametric,
                ns=ns,
                posthoc=posthoc,
                posthoc_correction=posthoc_correction,
                multiple_comparison=multiple_comparison,
                bottom_ticks=bottom_ticks,
                bottom_tick_labels=bottom_tick_labels,
                factor=factor,
                save=save,
                column_strings=column_strings,
                regex_string=regex_string,
                exclude=exclude,
                save_normality=save_normality,
                normality_dpi=normality_dpi,
                auto_style=auto_style,
                style_cycle=style_cycle,
                legend=legend,
                dry_run=dry_run,
            )
        return queued_outputs

    saved_columns_log = []
    skipped_columns_log = []
    shared_fig_ref = {"fig": None}
    not_included_sentinel = "NOT_INCLUDED_IN_EXPERIMENT"

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_mean_bars',
            total=len(resolved_columns),
        )
        _progress_start_item(state, ctx.column)
        n_conds = ctx.num_conditions
        if factor:
            factor_values = list(ctx.summary[factor].dropna().unique())
            group_order = []
            for cond in ctx.experiment.condition_list:
                match = next((v for v in factor_values if str(v) in str(cond.name)), None)
                if match is not None and match not in group_order:
                    group_order.append(match)
            for v in factor_values:
                if v not in group_order:
                    group_order.append(v)
            n_conds = len(group_order)
            group_color_map = {}
            explicit_styles = {}
            group_label_map = {}
            factor_dict = getattr(ctx.experiment.condition_list, "factorDict", {})
            if isinstance(factor_dict, dict) and factor in factor_dict:
                for c in factor_dict[factor]:
                    if hasattr(c, "name") and hasattr(c, "color"):
                        group_name = str(c.name)
                        group_color_map[group_name] = c.color
                        explicit_styles[group_name] = getattr(c, "style", "fill")
                        group_label_map[group_name] = str(
                            getattr(c, "label", getattr(c, "name", group_name))
                        )
            for gv in group_order:
                if str(gv) in group_color_map:
                    continue
                match = next(
                    (c.color for c in ctx.experiment.condition_list if str(gv) in str(c.name)),
                    None
                )
                if match is not None:
                    group_color_map[str(gv)] = match
                group_label_map.setdefault(str(gv), str(gv))
        else:
            present = set(ctx.summary['Condition'].dropna().unique().tolist())
            group_order = [
                cond.name for cond in ctx.experiment.condition_list
                if cond.name in present
            ]
            if len(group_order) == 0:
                group_order = [cond.name for cond in ctx.experiment.condition_list]
            n_conds = len(group_order)
            group_color_map = {cond.name: cond.color for cond in ctx.experiment.condition_list}
            explicit_styles = {
                cond.name: getattr(cond, 'style', 'fill')
                for cond in ctx.experiment.condition_list
            }
            group_label_map = _condition_label_map(ctx.experiment)
        # Second visual channel: vary style only where conditions collide on
        # (colour, style). No-collision designs keep every bar solid.
        if auto_style:
            group_style_map = _resolve_group_styles(
                group_order, group_color_map, explicit_styles, style_cycle=style_cycle,
            )
        else:
            group_style_map = {}
        # Reuse one canvas across columns to reduce figure allocation overhead.
        if 'shared_fig' not in state or 'shared_ax' not in state:
            fig, ax = plt.subplots(figsize=(n_conds * 2/3, 5))
            state['shared_fig'] = fig
            state['shared_ax'] = ax
            shared_fig_ref["fig"] = fig
        else:
            fig = state['shared_fig']
            ax = state['shared_ax']
            ax.clear()
            fig.set_size_inches(n_conds * 2/3, 5, forward=True)
        state['fig'] = fig
        state['ax'] = ax
        state['col_dfs'] = []
        state['col_dfs_map'] = {}
        state['col_dfs_by_index'] = {}
        state['group_key_by_index'] = {}
        state['group_order'] = group_order
        state['group_index_map'] = {name: i for i, name in enumerate(group_order)}
        state['group_color_map'] = group_color_map
        state['group_style_map'] = group_style_map
        state['group_label_map'] = group_label_map
        # Start full per-column timing (setup + actions + stats + save)

    def teardown(ctx, state, results):

        ax = state['ax']
        fig = state['fig']
        col = ctx.column
        spec_tag = None
        if specificity is not None:
            spec_key, *spec_vals = specificity
            spec_vals_str = "_".join([str(v) for v in spec_vals]) if spec_vals else "filtered"
            spec_tag = strip_name(f"{spec_key}_{spec_vals_str}")

        # Column validity rule:
        # - rows with NOT_INCLUDED_IN_EXPERIMENT (or malformed repeats) are excluded
        # - NaN/non-numeric rows are dropped
        # - plot proceeds if any numeric values remain
        if factor:
            include_mask = ctx.summary[factor].isin(state.get('group_order', []))
        else:
            include_mask = ctx.summary['Condition'].isin(state.get('group_order', []))
        included = ctx.summary.loc[include_mask, col]
        valid_numeric = _to_numeric_excluding_not_included(
            included,
            sentinel=not_included_sentinel,
        ).dropna()
        if len(valid_numeric) == 0:
            skipped_columns_log.append(f"{col} (no numeric values after NOT_INCLUDED/NaN filtering)")
            _progress_finish_item(state, col)
            state['col_dfs'] = []
            state['col_dfs_map'] = {}
            state['col_dfs_by_index'] = {}
            state['group_key_by_index'] = {}
            return

        # Label + ticks
        set_display_name(ax, col, compact_per=True, fontdict={'weight': 'normal'}, size=25)
        if legend:
            # Colour+style key so the secondary factor's texture is readable.
            handles, labels_out = _condition_style_handles(
                experiment,
                names=state.get('group_order', []),
                color_map=state.get('group_color_map', {}),
                style_map=state.get('group_style_map', {}),
            )
            if handles:
                # Sit the key below the bars, clear of the right-side stats
                # panel and the significance brackets above.
                ax.legend(handles, labels_out, frameon=False, fontsize=11,
                          loc='upper center', bbox_to_anchor=(0.5, -0.06),
                          ncol=min(len(handles), 4))
            else:
                ax.legend().set_visible(False)
        else:
            ax.legend().set_visible(False)
        sns.despine(trim=False, ax=ax)

        group_order = state.get('group_order', [])
        group_label_map = state.get('group_label_map', {})
        if len(group_order) > 0:
            ax.set_xticks(range(len(group_order)))
            ax.set_xticklabels(
                [group_label_map.get(str(name), str(name)) for name in group_order],
                rotation=60, ha='right',
            )
        ax.tick_params(
            axis='x',
            which='both',
            bottom=bool(bottom_ticks),
            top=False,
            labelbottom=bool(bottom_tick_labels),
        )

        # Y axis scaling
        if state.get('col_dfs_by_index'):
            ordered_idxs = sorted(
                [i for i, s in state['col_dfs_by_index'].items() if len(s) > 0]
            )
            ordered_keys = [
                state.get('group_key_by_index', {}).get(i, str(i))
                for i in ordered_idxs
            ]
            col_dfs = [state['col_dfs_by_index'][i] for i in ordered_idxs]
        elif state.get('col_dfs_map'):
            ordered_keys = [
                key for key in state.get('group_order', [])
                if key in state['col_dfs_map'] and len(state['col_dfs_map'][key]) > 0
            ]
            col_dfs = [state['col_dfs_map'][key] for key in ordered_keys]
        else:
            ordered_keys = []
            col_dfs = [s for s in state.get('col_dfs', []) if len(s) > 0]

        # Keep figure width proportional to the number of groups actually plotted.
        n_groups = max(1, len(col_dfs))
        fig.set_size_inches(n_groups * 2/3, 5, forward=True)

        all_vals = pd.concat(col_dfs) if len(col_dfs) > 0 else pd.Series(dtype=float)
        registry_range = _lookup_axis_registry(experiment, col)
        if len(all_vals) > 0:
            per_group_tops = []
            for s in col_dfs:
                s = pd.to_numeric(pd.Series(s), errors='coerce').dropna()
                if len(s) == 0:
                    continue
                mean_s = float(s.mean())
                sem_s = float(s.std(ddof=1) / np.sqrt(len(s))) if len(s) > 1 else 0.0
                per_group_tops.append(max(float(s.max()), mean_s + sem_s))
            top_val = max(per_group_tops) if len(per_group_tops) > 0 else float(all_vals.max())
            if registry_range is not None and registry_range[1] is not None:
                # Respect the registered upper bound so sibling figures line up
                # even when individual groups don't hit the ceiling.
                ymax = float(registry_range[1])
            else:
                ymax = round_up_to_nearest_5(top_val)
            if ymax > 0:
                if registry_range is not None and registry_range[0] is not None:
                    ax.set_ylim(bottom=float(registry_range[0]), top=ymax)
                else:
                    ax.set_ylim(ymax=ymax)
                # Keep top major tick exactly at ymax so the top-left tick cap
                # is present consistently across columns.
                ax.yaxis.set_major_locator(LinearLocator(numticks=5))

        if len(col_dfs) >= 2:
            safe_col_name = _artifact_name(col)
            stats_name = safe_col_name if spec_tag is None else f"{safe_col_name}__{spec_tag}"
            if 'ordered_idxs' in locals() and len(ordered_keys) > 0:
                group_positions = ordered_idxs
            else:
                group_positions = [
                    state['group_index_map'][key]
                    for key in ordered_keys
                    if key in state['group_index_map']
                ] if len(ordered_keys) > 0 else None
            if len(ordered_keys) > 0:
                group_colors = [
                    state.get('group_color_map', {}).get(key, "black")
                    for key in ordered_keys
                ]
            else:
                group_colors = None
            stats_error = None
            _sc_key = (
                stats_cache_key(
                    col,
                    ordered_keys,
                    specificity,
                    {
                        "force_nonparametric": bool(force_nonparametric),
                        "multiple_comparison": multiple_comparison,
                        "posthoc": posthoc,
                        "posthoc_correction": posthoc_correction,
                    },
                )
                if ordered_keys else None
            )
            try:
                test_used, posthoc_used, _, _stats_result = multipleComparisons(
                    experiment,
                    col_dfs,
                    ax=ax,
                    fig=fig,
                    scatter=state.get('scatter'),
                    bar=state.get('bar'),
                    save_name=stats_name,
                    comparisons=comparisons,
                    force_nonparametric=force_nonparametric,
                    posthoc=posthoc,
                    posthoc_correction=posthoc_correction,
                    multiple_comparison=multiple_comparison,
                    ns=ns,
                    max_override=ymax if len(all_vals) > 0 else None,
                    group_labels=ordered_keys if len(ordered_keys) > 0 else None,
                    group_positions=group_positions,
                    group_colors=group_colors,
                    verbose=False,
                    save_normality=save_normality,
                    normality_dpi=normality_dpi,
                    cache_key=_sc_key,
                )
                if test_used == "Error":
                    stats_error = posthoc_used
            except Exception as e:
                stats_error = str(e)
                ax.text(
                    1.02, 1.0, f"Stats error:\n{stats_error}",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=10, color="crimson",
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9},
                    clip_on=False,
                )

            if stats_error is not None: 
                error_path = os.path.join(experiment.data_path, "Stats_Errors.csv")
                write_header = not os.path.exists(error_path)
                with open(error_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if write_header:
                        writer.writerow(["Column", "Specificity", "Error"])
                    spec_str = ""
                    if specificity is not None:
                        spec_str = f"{specificity[0]}=" + ",".join([str(v) for v in specificity[1:]])
                    writer.writerow([col, spec_str, stats_error])

            # Keep top tick aligned with the top of the y-axis.
            if len(all_vals) > 0 and ymax > 0:
                ax.set_ylim(ymax=ymax)
                ax.yaxis.set_major_locator(LinearLocator(numticks=5))

        marker_name = col.split('_')[0] if '_' in col else col
        subfolder, suffix = build_subfolder(
            plot_type='Bars',
            marker=marker_name if marker_name != col else None,
            factor=factor, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        if save:
            save_fig(fig, experiment.fig_path, _artifact_name(col) + suffix, subfolder=subfolder, verbose=False)
        saved_columns_log.append(col)
        _progress_finish_item(state, col)

        # Reset per-column state
        state['col_dfs'] = []
        state['col_dfs_map'] = {}
        state['col_dfs_by_index'] = {}
        state['group_key_by_index'] = {}

    resolved_columns = _resolve_filtered_columns(
        experiment,
        filtered_columns=filtered_columns,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=exclude,
    )
    resolved_columns = _filter_plotable_numeric_columns(
        experiment,
        resolved_columns,
        factor=factor,
    )
    if len(resolved_columns) == 0:
        raise ValueError(
            "No plottable numeric columns were found after filtering. "
            "Try different filters or remove non-numeric columns."
        )

    # ── Dry-run mode: compute stats without rendering figures ─────────
    if dry_run:
        from PyFLASH.stats import test_normality as _test_norm
        summary = experiment.summary
        if specificity is not None:
            from PyFLASH.utils import filter_df_by_specificity as _filt
            summary = _filt(summary, specificity)
        if factor:
            group_col = factor
        else:
            group_col = 'Condition'
        groups = [str(g) for g in summary[group_col].dropna().unique()]
        rows = []
        for col in resolved_columns:
            vals = pd.to_numeric(summary[col], errors='coerce').dropna()
            if len(vals) == 0:
                rows.append({'Column': col, 'N': 0, 'Test': 'N/A', 'PostHoc': 'N/A'})
                continue
            col_dfs = []
            for g in groups:
                g_vals = pd.to_numeric(
                    summary.loc[summary[group_col] == g, col], errors='coerce'
                ).dropna()
                if len(g_vals) > 0:
                    col_dfs.append(g_vals)
            if len(col_dfs) < 2:
                rows.append({'Column': col, 'N': int(len(vals)), 'Test': 'N/A', 'PostHoc': 'N/A'})
                continue
            normal, _, _ = _test_norm(col_dfs, make_plot=False)
            if force_nonparametric:
                normal = False
            # Determine test without executing (mirrors multipleComparisons logic)
            if len(col_dfs) == 2:
                test_name = 'Independent T-Test' if normal else 'Mann-Whitney U'
            else:
                if normal:
                    test_name = 'One-Way ANOVA' if multiple_comparison == 'One-Way' else 'Two-Way ANOVA'
                else:
                    test_name = 'Kruskal-Wallis'
            # Quick p-value
            try:
                if len(col_dfs) == 2:
                    if normal:
                        _, p = runITTest(col_dfs[0], col_dfs[1], {}, ns=ns)[:2]
                        p_val = p[0] if isinstance(p, list) else p
                    else:
                        pvals, _, _, _, _ = mwu_multiple_comparisons(col_dfs, ['1-2'], {}, ns=ns)
                        p_val = pvals[0] if pvals else float('nan')
                else:
                    from scipy.stats import kruskal, f_oneway as _fow
                    if normal:
                        _, p_val = _fow(*col_dfs)
                    else:
                        _, p_val = kruskal(*col_dfs)
            except Exception:
                p_val = float('nan')
            rows.append({
                'Column': col,
                'N': int(len(vals)),
                'Groups': len(col_dfs),
                'Normal': normal,
                'Test': test_name,
                'p_value': float(p_val) if not isinstance(p_val, list) else float(p_val[0]),
            })
        df_out = pd.DataFrame(rows)
        _log.status(df_out.to_string(index=False))
        return df_out

    inner = 'factors' if factor else 'conditions'
    out = None
    try:
        out = run(
            experiment, over=['columns', inner],
            action=bar_chart_action,
            columns=resolved_columns, factor=factor,
            specificity=specificity,
            setup=setup, teardown=teardown,
            points=points, normalize=normalize,
            point_fill=point_fill, point_edge=point_edge,
            point_size=point_size, point_linewidth=point_linewidth,
            roi_base=_roi_base,
        )
    finally:
        # Close the shared canvas once at the end.
        shared_fig = shared_fig_ref.get("fig")
        if shared_fig is not None:
            plt.close(shared_fig)
    # Finish in-place line for terminal contexts.
    try:
        import sys
        sys.stdout.write("\n")
        sys.stdout.flush()
    except Exception:
        pass
    saved = saved_columns_log
    verb = "Saved" if save else "Processed"
    _log.confirm(f"[plot_mean_bars] {verb} columns ({len(saved)}): {', '.join(saved)}")
    if len(skipped_columns_log) > 0:
        _log.hint(f"[plot_mean_bars] Skipped columns ({len(skipped_columns_log)}): {', '.join(skipped_columns_log)}")
    try:
        if save and Config.EXPORT_HTML:
            subfolder_html, _ = build_subfolder(
                plot_type='Bars', factor=factor, specificity=specificity,
                aliases=getattr(experiment, 'aliases', None),
                roi_base=_roi_base, multi_roi=_multi_roi,
            )
            html_save_path = os.path.join(experiment.fig_path, subfolder_html) if subfolder_html else experiment.fig_path
            _export_html_bars(experiment, resolved_columns, specificity, html_save_path)
    except Exception:
        pass
    return out


def plot_condition_key(experiment, save=True, save_path=None,
                       filename="condition_key", auto_style=True, style_cycle=None,
                       ncol=1, title=None, dpi=200):
    """Render a standalone colour+style key (legend) for the conditions.

    Each condition becomes a swatch whose fill / outline / hatch matches how its
    bars (and radar/pie/regression marks) render — so a figure assembled
    externally can carry a legend that conveys *both* channels: colour for the
    primary factor and texture for the secondary. Mirrors the same collision
    resolution the plots use, so the key always agrees with the figures.

    Returns the saved path (``save=True``) or the Figure (``save=False``).
    """
    handles, labels = _condition_style_handles(
        experiment, auto_style=auto_style, style_cycle=style_cycle)
    if not handles:
        raise ValueError("No conditions to build a key from.")

    ncol = max(1, int(ncol))
    nrow = int(np.ceil(len(handles) / ncol))
    fig, ax = plt.subplots(figsize=(max(2.5, 3.0 * ncol), max(1.0, 0.5 * nrow)))
    ax.axis("off")
    ax.legend(
        handles, labels, loc="center", frameon=False, ncol=ncol,
        handlelength=1.6, handleheight=1.3, fontsize=13, title=title,
    )

    if not save:
        return fig
    path = save_path or os.path.join(
        getattr(experiment, "fig_path", "."), f"{filename}.png")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    _log.confirm(f"[plot_condition_key] Saved key to {path}")
    return path


def plot_locations(experiment, objects,
                   separate_by='conditions', join_by='animals',
                   merge=True, colocalise=True, annotate=True,
                   extra_graphs=None,
                   images=None,
                   colocaliser=None,
                   extra_graph_colors=None,
                   image_layout="shared",
                   draw_rois=None,
                   hue=True,
                   marker_colors=None,
                   black_background=False,
                   panel_line_width=2.0,
                   dpi=100, save=True,
                   fast_loading=False,
                   preview_max_dim=None,
                   image_adjustments=None,
                   edit_mode=False,
                   use_existing_edits=False,
                   specificity=None, roi=None,
                   extra_graph=None,
                   merge_extra_graphs=None,
                   overlay_with_images=None,
                   draw_roi=None,
                   overlay_all_extra_graphs=None,
                   _return_fig=False):
    """
    Spatial scatter plots: one figure per condition, one row per animal.

    If `annotate=True`, each marker panel is labeled in the top-left in white.
    `objects`, `images`, and `extra_graphs` all accept lists where tuple items
    define merged panels. For example:
    - `objects=['CK1d', ('CK1d', 'mCherry')]`
    - `images=['CK1d', ('CK1d', 'mCherry')]`
    - `extra_graphs=['CK1d_Combo_DAPI+', ('CK1d_Combo_DAPI+', 'CK1d_Combo_mCherry+')]`

    `extra_graphs` can be:
    - a single marker dataframe column name (one extra filtered panel)
    - a list of column names (multiple extra filtered panels)
    - a tuple of column names (overlay those filtered subsets on one panel)
    - a list mixing strings and tuples, where tuples define overlay panels

    Example:
    - `extra_graphs='Caspase_ColocmCherryCount'`
    - `extra_graphs=['Caspase_ColocmCherryCount', 'Caspase_Contains_mCherry']`
    - `extra_graphs=[('Caspase_ColocmCherryCount', 'Caspase_Contains_mCherry')]`

    `extra_graph_colors` can be a dict mapping extra_graph column -> color, a single
    color string, or a sequence of colors matching the unique extra_graph columns.
    If omitted, extra_graph panels use the parent marker color by default.

    If `images` are provided, matching imported ROI images are used. Use
    `image_layout='shared'` to overlay image and points on the same axis, or
    `image_layout='separate'` to place one block of real images beside one block
    of point panels within the same figure. In `separate` mode, the image block
    shows only the base marker images, while subset/extra panels remain points-only.

    `draw_rois` can be a list using the same panel syntax as `images`. ROI outlines
    are only drawn on matching image panels. `draw_rois=True` still means draw ROIs
    on all image panels.

    `hue=True` colors points by `<marker>_IntDen` using a light->dark palette derived
    from the marker color in `marker_colors` (or the global `LOCATION_MARKER_COLORS`,
    which aliases `stainColors`). `hue=False` uses the resolved marker color directly.

    `marker_colors` can be any dict-like mapping of marker name -> color. Users can
    also modify `LOCATION_MARKER_COLORS` / `stainColors` directly to change defaults.

    `black_background=True` sets the location figure and axes backgrounds to black.

    `panel_line_width` controls the white axis spine width used as the separator
    between panels. Horizontal subplot spacing is forced to zero.

    `edit_mode=True` opens a Tk editor that previews low-resolution image panels
    and lets you adjust brightness/contrast per marker. The same per-marker
    adjustments are reused across all matching image panels and merged image layers.

    `colocaliser` adds panels based on `_Contains_` columns:
    - `True`: auto-detect across the plotted objects
    - `'mCherry'`: for each plotted object, use `<object>_Contains_mCherry` if present
    - `[('Caspase3', 'mCherry'), ('Iba1', 'DAPI')]`: explicit pairs
    """
    if extra_graphs is None and extra_graph is not None:
        extra_graphs = extra_graph
    if images is None and bool(overlay_with_images):
        images = objects
    if draw_rois is None and draw_roi is not None:
        draw_rois = draw_roi
    legacy_merge_extra = bool(merge_extra_graphs) or bool(overlay_all_extra_graphs)
    image_layout = _normalize_location_image_layout(image_layout)

    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_locations(
                experiment, objects,
                separate_by=separate_by, join_by=join_by,
                merge=merge, colocalise=colocalise, annotate=annotate,
                extra_graphs=extra_graphs, images=images, colocaliser=colocaliser,
                extra_graph_colors=extra_graph_colors,
                image_layout=image_layout,
                draw_rois=draw_rois,
                hue=hue, marker_colors=marker_colors,
                black_background=black_background,
                panel_line_width=panel_line_width,
                fast_loading=fast_loading,
                preview_max_dim=preview_max_dim,
                image_adjustments=image_adjustments,
                edit_mode=edit_mode,
                use_existing_edits=use_existing_edits,
                dpi=dpi, save=save,
                specificity=specificity,
                roi=_rb,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_locations(
                experiment, objects,
                separate_by=separate_by, join_by=join_by,
                merge=merge, colocalise=colocalise, annotate=annotate,
                extra_graphs=extra_graphs, images=images, colocaliser=colocaliser,
                extra_graph_colors=extra_graph_colors,
                image_layout=image_layout,
                draw_rois=draw_rois,
                hue=hue, marker_colors=marker_colors,
                black_background=black_background,
                panel_line_width=panel_line_width,
                fast_loading=fast_loading,
                preview_max_dim=preview_max_dim,
                image_adjustments=image_adjustments,
                edit_mode=edit_mode,
                use_existing_edits=use_existing_edits,
                dpi=dpi, save=save,
                specificity=spec,
                roi=roi,
            )
        return queued_outputs

    object_panels = _resolve_location_marker_panels(experiment, objects)
    image_panels = _resolve_location_marker_panels(experiment, images)
    image_marker_order = []
    seen_image_markers = set()
    for panel in image_panels:
        for marker_name in _location_panel_markers(panel):
            key = str(marker_name).casefold()
            if key in seen_image_markers:
                continue
            seen_image_markers.add(key)
            image_marker_order.append(str(marker_name))
    normalized_image_adjustments = _normalize_image_adjustments(
        _resolve_effective_image_adjustments(
            experiment,
            image_marker_order,
            specificity=specificity,
            image_adjustments=image_adjustments,
            use_existing_edits=use_existing_edits,
        ),
        marker_names=image_marker_order,
    )
    if edit_mode:
        if len(image_marker_order) == 0:
            raise ValueError("edit_mode requires image panels. Pass images=[...] to enable image editing.")
        preview_dim = int(preview_max_dim) if preview_max_dim is not None else 512
        preview_image_panel = image_panels[0] if len(image_panels) > 0 else tuple(image_marker_order)
        preview_image_markers = _location_panel_markers(preview_image_panel)
        preview_image_merge = len(preview_image_markers) > 1
        return _launch_image_edit_mode(
            image_marker_order,
            render_preview=lambda adjustments, preview_scope="full": (
                plot_images(
                    experiment,
                    markers=preview_image_markers,
                    save=False,
                    title="Location image preview",
                    show=False,
                    verbose=False,
                    image_backend="auto",
                    merge=preview_image_merge,
                    merge_label="Merge",
                    fast_loading=True,
                    preview_max_dim=preview_dim,
                    image_adjustments=adjustments,
                    edit_mode=False,
                    use_existing_edits=False,
                    image_workers=None,
                    progress=False,
                    _preview_single_image=True,
                )
                if str(preview_scope).strip().casefold() == "single"
                else plot_locations(
                    experiment,
                    objects,
                    separate_by=separate_by,
                    join_by=join_by,
                    merge=merge,
                    colocalise=colocalise,
                    annotate=annotate,
                    extra_graphs=extra_graphs,
                    images=images,
                    colocaliser=colocaliser,
                    extra_graph_colors=extra_graph_colors,
                    image_layout=image_layout,
                    draw_rois=draw_rois,
                    hue=hue,
                    marker_colors=marker_colors,
                    black_background=black_background,
                    panel_line_width=panel_line_width,
                    dpi=dpi,
                    save=False,
                    fast_loading=True,
                    preview_max_dim=preview_dim,
                    image_adjustments=adjustments,
                    edit_mode=False,
                    use_existing_edits=False,
                    specificity=specificity,
                    _return_fig=True,
                )
            ),
            render_final=lambda adjustments: _persist_image_edits_and_return(
                experiment,
                plot_locations(
                    experiment,
                    objects,
                    separate_by=separate_by,
                    join_by=join_by,
                    merge=merge,
                    colocalise=colocalise,
                    annotate=annotate,
                    extra_graphs=extra_graphs,
                    images=images,
                    colocaliser=colocaliser,
                    extra_graph_colors=extra_graph_colors,
                    image_layout=image_layout,
                    draw_rois=draw_rois,
                    hue=hue,
                    marker_colors=marker_colors,
                    black_background=black_background,
                    panel_line_width=panel_line_width,
                    dpi=dpi,
                    save=save,
                    fast_loading=fast_loading,
                    preview_max_dim=preview_max_dim,
                    image_adjustments=adjustments,
                    edit_mode=False,
                    use_existing_edits=False,
                    specificity=specificity,
                ),
                marker_names=image_marker_order,
                adjustments=adjustments,
                specificity=specificity,
            ),
            initial_adjustments=normalized_image_adjustments,
            window_title="Edit Location Images",
        )
    if len(image_panels) > len(object_panels) and image_layout == "shared":
        raise ValueError(
            "When image_layout='shared', the images list cannot have more panels than objects."
        )
    resolved_object_markers = []
    seen_object_markers = set()
    for panel in object_panels:
        for marker in _location_panel_markers(panel):
            key = str(marker).casefold()
            if key in seen_object_markers:
                continue
            seen_object_markers.add(key)
            resolved_object_markers.append(marker)
    extra_graph_panels = _resolve_location_extra_panels(
        experiment,
        resolved_object_markers,
        extra_graphs,
        extra_graph_colors=extra_graph_colors,
        marker_colors=marker_colors,
        merge_extra_graphs=legacy_merge_extra,
    )
    colocaliser_panels = _resolve_location_colocaliser_panels(
        experiment,
        resolved_object_markers,
        colocaliser,
        extra_graph_colors=extra_graph_colors,
    )
    extra_panels = extra_graph_panels + colocaliser_panels
    draw_roi_keys = _location_draw_roi_key_set(draw_rois, image_panels)
    logical_n_cols = _location_active_panel_count(object_panels, extra_panels)
    display_n_cols = _location_display_panel_count(
        object_panels,
        extra_panels,
        overlay_with_images=len(image_panels) > 0,
        image_layout=image_layout,
    )
    returned_fig = {}

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_locations',
            total=_count_level_processes(experiment, separate_by, specificity=specificity),
        )
        outer_name = _location_context_name(ctx, separate_by)
        _progress_start_item(state, outer_name)
        n_rows = _location_join_rows(ctx, join_by)
        panel_size_in = 6.0
        title_strip_in = 1.20
        panel_area_h_in = panel_size_in * n_rows
        fig_h_in = panel_area_h_in + title_strip_in
        top_frac = panel_area_h_in / fig_h_in if fig_h_in > 0 else 1.0
        def _apply_background(axes_grid):
            if black_background:
                for ax in np.ravel(axes_grid):
                    try:
                        ax.set_facecolor('black')
                    except Exception:
                        pass

        if len(image_panels) > 0 and image_layout == "separate":
            image_n_cols = max(1, len(list(image_panels or [])))
            block_gap = 0.04
            fig_w_in = panel_size_in * (image_n_cols + display_n_cols)
            fig = plt.figure(figsize=(fig_w_in, fig_h_in), dpi=dpi)
            if black_background:
                fig.patch.set_facecolor('black')
            outer_gs = fig.add_gridspec(
                1,
                2,
                left=0.0,
                right=1.0,
                bottom=0.0,
                top=top_frac,
                wspace=block_gap,
                width_ratios=[image_n_cols, display_n_cols],
            )
            image_sgs = outer_gs[0, 0].subgridspec(n_rows, image_n_cols, wspace=0.0, hspace=0.0)
            scatter_sgs = outer_gs[0, 1].subgridspec(n_rows, display_n_cols, wspace=0.0, hspace=0.0)
            image_axes_grid = np.empty((n_rows, image_n_cols), dtype=object)
            scatter_axes_grid = np.empty((n_rows, display_n_cols), dtype=object)
            for r in range(n_rows):
                for c in range(image_n_cols):
                    image_axes_grid[r, c] = fig.add_subplot(image_sgs[r, c])
                for c in range(display_n_cols):
                    scatter_axes_grid[r, c] = fig.add_subplot(scatter_sgs[r, c])
            _apply_background(image_axes_grid)
            _apply_background(scatter_axes_grid)
            state['fig'] = fig
            state['location_scatter_axes_grid'] = scatter_axes_grid
            state['location_image_axes_grid'] = image_axes_grid
        else:
            fig = plt.figure(figsize=(panel_size_in * display_n_cols, fig_h_in), dpi=dpi)
            if black_background:
                fig.patch.set_facecolor('black')
            axes_grid = np.asarray(
                fig.subplots(
                    n_rows,
                    display_n_cols,
                    squeeze=False,
                    gridspec_kw={'wspace': 0.0, 'hspace': 0.0},
                ),
                dtype=object,
            )
            try:
                fig.subplots_adjust(left=0.0, right=1.0, bottom=0.0, top=top_frac, wspace=0.0, hspace=0.0)
            except Exception:
                pass
            _apply_background(axes_grid)
            state['fig'] = fig
            state['location_axes_grid'] = axes_grid
        if len(image_panels) > 0:
            try:
                image_df = experiment.getImageTable(include_summary=True)
            except Exception:
                image_df = getattr(experiment, "images", None)
                if not isinstance(image_df, pd.DataFrame) and hasattr(experiment, "importImages"):
                    try:
                        image_df = experiment.importImages(progress=False)
                    except Exception:
                        image_df = None
            state['location_image_table'] = image_df if isinstance(image_df, pd.DataFrame) else pd.DataFrame()
            state['location_image_cache'] = {}
            state['location_experiment_lookup'] = _representative_experiment_lookup(experiment)
        state['location_image_adjustments'] = normalized_image_adjustments
        state['location_fast_loading'] = bool(fast_loading)
        state['location_preview_max_dim'] = preview_max_dim
        state['location_return_fig'] = bool(_return_fig)
        state['location_title_y'] = top_frac + ((1.0 - top_frac) * 0.60)

    def teardown(ctx, state, results):
        fig = state['fig']
        outer_name = _location_context_name(ctx, separate_by)
        title_name = _location_context_name(ctx, separate_by, display=True)
        title_kwargs = dict(
            fontsize=40,
            weight='bold',
            y=float(state.get('location_title_y', 0.985)),
            color='white',
        )
        panel_tag = _location_panel_save_tag(object_panels, extra_panels)
        if panel_tag is None:
            base_name = f'{outer_name} per {join_by}'
        else:
            base_name = f'{outer_name} {panel_tag} per {join_by}'
        subfolder, suffix = build_subfolder(
            plot_type='Locations',
            factor=None, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        fig.suptitle(title_name, **title_kwargs)
        fig.PyFLASH_image_adjustments = normalized_image_adjustments
        if save:
            save_fig(fig, experiment.fig_path, base_name + suffix, subfolder=subfolder)
        _progress_finish_item(state, outer_name)
        if state.get('location_return_fig'):
            returned_fig['fig'] = fig
        else:
            plt.close(fig)

    run_result = run(
        experiment, over=[separate_by, join_by],
        action=location_scatter_action,
        setup=setup, teardown=teardown,
        object_panels=object_panels, merge=merge, colocalise=colocalise,
        image_panels=image_panels,
        extra_panels=extra_panels,
        annotate=annotate, hue=hue, marker_colors=marker_colors,
        image_layout=image_layout,
        draw_roi_keys=draw_roi_keys,
        black_background=black_background,
        panel_line_width=panel_line_width,
        join_by=join_by,
        specificity_filter=specificity,
        specificity=specificity,
        roi_base=_roi_base,
    )
    if _return_fig:
        return returned_fig.get('fig')
    return run_result


def plot_regressions(experiment, x, y,
                     by='conditions', factor=None,
                     test='pearsonr',
                     normalize_x=True, normalize_y=True,
                     specificity=None, roi=None, save=True, combine=False,
                     x_range=None, y_range=None,
                     xmin=None, xmax=None, ymin=None, ymax=None,
                     clip_fit_line=True, share_axes=True, margin=0.1,
                     auto_style=True, style_cycle=None):
    """
    Regression plot: one figure per condition/factor, or a combined overlay.
    Supports queued x/y inputs:
        - x scalar, y list -> one plot per y
        - x list, y scalar -> one plot per x
        - x list, y list -> all x×y combinations
    `normalize_x` / `normalize_y` accept False, True (= 0-1 min-max), a
    `(min, max)` output range, or 'Z-score'.

    Shared axis scales
    ------------------
    When ``x`` or ``y`` is a list, every column that appears in more than one
    combination gets the same axis range in each panel (``share_axes=True``,
    default). Pass ``share_axes=False`` to let each panel auto-scale. Explicit
    ``x_range`` / ``y_range`` / ``xmin`` / ``xmax`` etc. always win.

    For separate calls (e.g. different markers against the same x column),
    register the shared column once via
    ``PyFLASH.set_axis_limits(exp, {'PeriodMean': (22, 26)})`` and every
    subsequent plot picks the bounds up automatically.

    Axis breathing room
    -------------------
    ``margin`` (default ``0.1``) is the target fractional distance between
    every spine and the nearest data point. With ``margin=0.1`` the lowest
    and highest x/y values each sit 10% of the axis span off their spines.
    Each side is padded independently and only when the autoscaled view
    leaves less breathing room than the target — we never shrink the axis.
    Sides that the caller pinned (``x_range`` / ``y_range`` / ``xmin`` /
    ``xmax`` / ``ymin`` / ``ymax`` or a registry entry with that bound set)
    are left untouched. Must be < 0.5. Pass ``margin=0`` to disable.
    """
    x_range = _merge_axis_range(x_range, xmin, xmax)
    y_range = _merge_axis_range(y_range, ymin, ymax)

    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_regressions(
                experiment, x, y,
                by=by, factor=factor, test=test,
                normalize_x=normalize_x, normalize_y=normalize_y,
                specificity=specificity, roi=_rb, save=save, combine=combine,
                x_range=x_range, y_range=y_range,
                clip_fit_line=clip_fit_line, share_axes=share_axes,
                margin=margin,
                auto_style=auto_style, style_cycle=style_cycle,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1
    test_label = _correlation_filename_label(test)

    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    x_is_queue = isinstance(x, queue_types)
    y_is_queue = isinstance(y, queue_types)
    if x_is_queue or y_is_queue:
        x_values = _flatten_specificity_values([x]) if x_is_queue else [x]
        y_values = _flatten_specificity_values([y]) if y_is_queue else [y]
        if len(x_values) == 0 or len(y_values) == 0:
            raise ValueError("Queued x/y inputs must contain at least one value.")

        # Pre-compute shared ranges for columns that appear in more than one
        # combination so sibling panels line up on comparable axes.
        shared_ranges = {}
        if share_axes and not normalize_x and not normalize_y:
            x_counts = pd.Series(x_values).value_counts()
            y_counts = pd.Series(y_values).value_counts()
            # X column is repeated if len(y_values) > 1; Y column is repeated
            # if len(x_values) > 1. Also pick up any literal duplicates.
            shared_cols = set()
            for col, n in x_counts.items():
                if n > 1 or len(y_values) > 1:
                    shared_cols.add(col)
            for col, n in y_counts.items():
                if n > 1 or len(x_values) > 1:
                    shared_cols.add(col)
            shared_cols -= set(_get_axis_limits_registry(experiment).keys())
            summary_df = getattr(experiment, 'summary', None)
            # Restrict to rows that the active specificity/queue will actually
            # plot, otherwise rows filtered out downstream still widen the
            # shared range.
            scoped_df = _summary_for_queue_share(summary_df, specificity)
            shared_ranges = _compute_queue_shared_ranges(scoped_df, shared_cols)
            # Pre-pad so the data minimum sits at `margin` fraction of the
            # axis span from the spine, matching the teardown semantics. Child
            # calls treat this padded range as a pinned bound and skip
            # further padding.
            try:
                margin_f = float(margin) if margin is not None else 0.0
            except (TypeError, ValueError):
                margin_f = 0.0
            if np.isfinite(margin_f) and 0 < margin_f < 0.5:
                def _pad_both(low, high):
                    data_span = high - low
                    new_span = data_span / (1.0 - 2.0 * margin_f)
                    pad = margin_f * new_span
                    return (low - pad, high + pad)
                shared_ranges = {
                    col: _pad_both(low, high)
                    for col, (low, high) in shared_ranges.items()
                }

        queued_outputs = {}
        for x_val in x_values:
            for y_val in y_values:
                key = (x_val, y_val)
                sub_x_range = x_range if x_range is not None else shared_ranges.get(x_val)
                sub_y_range = y_range if y_range is not None else shared_ranges.get(y_val)
                queued_outputs[key] = plot_regressions(
                    experiment,
                    x=x_val,
                    y=y_val,
                    by=by,
                    factor=factor,
                    test=test,
                    normalize_x=normalize_x,
                    normalize_y=normalize_y,
                    specificity=specificity,
                    roi=roi,
                    save=save,
                    combine=combine,
                    x_range=sub_x_range,
                    y_range=sub_y_range,
                    clip_fit_line=clip_fit_line,
                    share_axes=share_axes,
                    margin=margin,
                    auto_style=auto_style, style_cycle=style_cycle,
                )
        return queued_outputs

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_regressions(
                experiment, x, y,
                by=by, factor=factor, test=test,
                normalize_x=normalize_x, normalize_y=normalize_y,
                specificity=spec, roi=roi, save=save, combine=combine,
                x_range=x_range, y_range=y_range,
                clip_fit_line=clip_fit_line, share_axes=share_axes,
                margin=margin,
                auto_style=auto_style, style_cycle=style_cycle,
            )
        return queued_outputs

    level = 'factors' if factor else by

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_regressions',
            total=_count_level_processes(experiment, level, factor=factor, specificity=specificity),
        )
        _progress_start_item(state)
        if combine:
            if state.get('fig') is None or state.get('ax') is None:
                fig, ax = plt.subplots(figsize=(8, 8))
                state['fig'] = fig
                state['ax'] = ax
                state['regression_stats_entries'] = []
        else:
            fig, ax = plt.subplots(figsize=(8, 8))
            state['fig'] = fig
            state['ax'] = ax
            state['regression_stats_entries'] = []

    # Margin applies to each spine independently whenever the corresponding
    # bound wasn't pinned by the caller or the axis-limit registry.
    # Normalized axes ([0, 1] / (min, max) / Z-score) benefit from the same
    # breathing room so scatter points at the edges don't sit on the spine.
    margin_enabled = bool(margin)
    pad_x_low = margin_enabled and not _axis_lower_bound_is_explicit(experiment, x, x_range)
    pad_x_high = margin_enabled and not _axis_upper_bound_is_explicit(experiment, x, x_range)
    pad_y_low = margin_enabled and not _axis_lower_bound_is_explicit(experiment, y, y_range)
    pad_y_high = margin_enabled and not _axis_upper_bound_is_explicit(experiment, y, y_range)

    def teardown(ctx, state, results):
        name, _ = _resolve_group_label_color(ctx)
        name = name or 'Combined'
        _progress_finish_item(state, name)

        if combine:
            prog = state.get('progress_state', {})
            is_last = int(prog.get('completed', 0)) >= int(prog.get('total', 1))
            if not is_last:
                return
            fig = state.get('fig')
            ax = state.get('ax')
            if fig is None or ax is None:
                return
            _pad_axis_bounds(
                ax, margin,
                pad_x_low=pad_x_low, pad_x_high=pad_x_high,
                pad_y_low=pad_y_low, pad_y_high=pad_y_high,
            )
            _annotate_regression_stats_summary(
                ax,
                state.get('regression_stats_entries', []),
                test=test,
            )
            subfolder, suffix = build_subfolder(
                plot_type='Regressions',
                factor=factor, specificity=specificity,
                aliases=getattr(experiment, 'aliases', None),
                roi_base=_roi_base, multi_roi=_multi_roi,
            )
            if save:
                save_fig(fig, experiment.fig_path,
                         f'{x} vs {y} (Combined) {test_label}' + suffix, subfolder=subfolder)
            plt.close(fig)
            return

        fig = state['fig']
        _pad_axis_bounds(
            state['ax'], margin,
            pad_x_low=pad_x_low, pad_x_high=pad_x_high,
            pad_y_low=pad_y_low, pad_y_high=pad_y_high,
        )
        _annotate_regression_stats_summary(
            state['ax'],
            state.get('regression_stats_entries', []),
            test=test,
        )
        subfolder, suffix = build_subfolder(
            plot_type='Regressions',
            factor=factor, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        if save:
            save_fig(fig, experiment.fig_path,
                     f'{x} vs {y} ({name}) {test_label}' + suffix, subfolder=subfolder)
        plt.close(fig)

    return run(
        experiment, over=level, action=regression_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        x=x, y=y, normalize_x=normalize_x, normalize_y=normalize_y, test=test,
        combine=combine, x_range=x_range, y_range=y_range,
        clip_fit_line=clip_fit_line,
        auto_style=auto_style, style_cycle=style_cycle,
        roi_base=_roi_base,
    )


def plot_scatter_3d(experiment, x, y, z,
                    by='conditions', factor=None,
                    specificity=None, roi=None, save=True, combine=False,
                    x_range=None, y_range=None, z_range=None,
                    xmin=None, xmax=None, ymin=None, ymax=None,
                    zmin=None, zmax=None,
                    normalize_x=False, normalize_y=False, normalize_z=False,
                    point_size=40, size_by=None, size_factor=1.0, alpha=0.7,
                    elevation=None, azimuth=None,
                    figsize=(10, 8), share_axes=True):
    """
    3D scatter plot: one figure per condition/factor, or a combined overlay.
    Supports queued x/y/z inputs:
        - Any of x, y, z as a list -> one plot per combination
        - x list, y list, z list -> all x*y*z combinations
    `normalize_x` / `normalize_y` / `normalize_z` accept False, True
    (= 0-1 min-max), a `(min, max)` output range, or 'Z-score'.
    Size controls:
        - point_size sets the baseline marker area
        - size_by maps marker size from a numeric summary column
        - size_factor multiplies the final marker sizes
    Shared axis scales:
        - `share_axes=True` (default) forces columns reused across queued
          combinations to use the same range.
        - Set ``experiment.axis_limits`` via ``set_axis_limits`` to share
          ranges across separate calls.
    """
    x_range = _merge_axis_range(x_range, xmin, xmax)
    y_range = _merge_axis_range(y_range, ymin, ymax)
    z_range = _merge_axis_range(z_range, zmin, zmax)

    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_scatter_3d(
                experiment, x, y, z,
                by=by, factor=factor,
                specificity=specificity, roi=_rb, save=save, combine=combine,
                x_range=x_range, y_range=y_range, z_range=z_range,
                normalize_x=normalize_x, normalize_y=normalize_y, normalize_z=normalize_z,
                point_size=point_size, size_by=size_by, size_factor=size_factor, alpha=alpha,
                elevation=elevation, azimuth=azimuth,
                figsize=figsize, share_axes=share_axes,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    x_is_queue = isinstance(x, queue_types)
    y_is_queue = isinstance(y, queue_types)
    z_is_queue = isinstance(z, queue_types)
    if x_is_queue or y_is_queue or z_is_queue:
        x_values = _flatten_specificity_values([x]) if x_is_queue else [x]
        y_values = _flatten_specificity_values([y]) if y_is_queue else [y]
        z_values = _flatten_specificity_values([z]) if z_is_queue else [z]
        if len(x_values) == 0 or len(y_values) == 0 or len(z_values) == 0:
            raise ValueError("Queued x/y/z inputs must contain at least one value.")

        shared_ranges = {}
        if share_axes and not normalize_x and not normalize_y and not normalize_z:
            # A column on axis A is "shared" whenever some other combo uses the
            # same column on the same axis, i.e. either the value repeats along
            # that axis or at least one of the other axes has multiple values.
            shared_cols = set()
            y_by_z = len(y_values) * len(z_values)
            x_by_z = len(x_values) * len(z_values)
            x_by_y = len(x_values) * len(y_values)
            for col in set(x_values):
                if x_values.count(col) > 1 or y_by_z > 1:
                    shared_cols.add(col)
            for col in set(y_values):
                if y_values.count(col) > 1 or x_by_z > 1:
                    shared_cols.add(col)
            for col in set(z_values):
                if z_values.count(col) > 1 or x_by_y > 1:
                    shared_cols.add(col)
            shared_cols -= set(_get_axis_limits_registry(experiment).keys())
            summary_df = getattr(experiment, 'summary', None)
            shared_ranges = _compute_queue_shared_ranges(summary_df, shared_cols)
            # scatter_3d keeps its default autoscale behaviour (no pad) so no
            # extra margin is folded in here. A future `margin` kwarg on
            # plot_scatter_3d would hook in at this spot.

        queued_outputs = {}
        for x_val in x_values:
            for y_val in y_values:
                for z_val in z_values:
                    key = (x_val, y_val, z_val)
                    sub_x_range = x_range if x_range is not None else shared_ranges.get(x_val)
                    sub_y_range = y_range if y_range is not None else shared_ranges.get(y_val)
                    sub_z_range = z_range if z_range is not None else shared_ranges.get(z_val)
                    queued_outputs[key] = plot_scatter_3d(
                        experiment,
                        x=x_val, y=y_val, z=z_val,
                        by=by, factor=factor,
                        specificity=specificity, roi=roi,
                        save=save, combine=combine,
                        x_range=sub_x_range, y_range=sub_y_range, z_range=sub_z_range,
                        normalize_x=normalize_x, normalize_y=normalize_y, normalize_z=normalize_z,
                        point_size=point_size, size_by=size_by, size_factor=size_factor, alpha=alpha,
                        elevation=elevation, azimuth=azimuth,
                        figsize=figsize, share_axes=share_axes,
                    )
        return queued_outputs

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_scatter_3d(
                experiment, x, y, z,
                by=by, factor=factor,
                specificity=spec, roi=roi, save=save, combine=combine,
                x_range=x_range, y_range=y_range, z_range=z_range,
                normalize_x=normalize_x, normalize_y=normalize_y, normalize_z=normalize_z,
                point_size=point_size, size_by=size_by, size_factor=size_factor, alpha=alpha,
                elevation=elevation, azimuth=azimuth,
                figsize=figsize, share_axes=share_axes,
            )
        return queued_outputs

    level = 'factors' if factor else by

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_scatter_3d',
            total=_count_level_processes(experiment, level, factor=factor, specificity=specificity),
        )
        _progress_start_item(state)
        if size_by is not None and 'size_norm' not in state:
            state['size_norm'] = _scatter_size_norm(ctx.summary, size_by)
        if combine:
            if state.get('fig') is None or state.get('ax') is None:
                fig = plt.figure(figsize=figsize)
                ax = fig.add_subplot(111, projection='3d')
                state['fig'] = fig
                state['ax'] = ax
        else:
            fig = plt.figure(figsize=figsize)
            ax = fig.add_subplot(111, projection='3d')
            state['fig'] = fig
            state['ax'] = ax

    def teardown(ctx, state, results):
        name, _ = _resolve_group_label_color(ctx)
        name = name or 'Combined'
        _progress_finish_item(state, name)

        fig = state.get('fig')
        ax = state.get('ax')

        if combine:
            prog = state.get('progress_state', {})
            is_last = int(prog.get('completed', 0)) >= int(prog.get('total', 1))
            if not is_last:
                return
            if fig is None or ax is None:
                return
            ax.legend(fontsize=10, loc='upper left')
            if elevation is not None or azimuth is not None:
                ax.view_init(
                    elev=elevation if elevation is not None else ax.elev,
                    azim=azimuth if azimuth is not None else ax.azim,
                )
            subfolder, suffix = build_subfolder(
                plot_type='Scatter3D',
                factor=factor, specificity=specificity,
                aliases=getattr(experiment, 'aliases', None),
                roi_base=_roi_base, multi_roi=_multi_roi,
            )
            if save:
                save_fig(fig, experiment.fig_path,
                         f'{x} vs {y} vs {z} (Combined)' + suffix, subfolder=subfolder)
            plt.close(fig)
            return

        if elevation is not None or azimuth is not None:
            ax.view_init(
                elev=elevation if elevation is not None else ax.elev,
                azim=azimuth if azimuth is not None else ax.azim,
            )
        subfolder, suffix = build_subfolder(
            plot_type='Scatter3D',
            factor=factor, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        if save:
            save_fig(fig, experiment.fig_path,
                     f'{x} vs {y} vs {z} ({name})' + suffix, subfolder=subfolder)
        plt.close(fig)

    return run(
        experiment, over=level, action=scatter_3d_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        x=x, y=y, z=z,
        combine=combine,
        x_range=x_range, y_range=y_range, z_range=z_range,
        normalize_x=normalize_x, normalize_y=normalize_y, normalize_z=normalize_z,
        point_size=point_size, size_by=size_by, size_factor=size_factor, alpha=alpha,
        roi_base=_roi_base,
    )


def plot_histograms(experiment, marker, x_attr,
                    by='conditions', factor=None,
                    bins=30, binwidth=None, kde=False,
                    alpha=0.5, stat='count',
                    merge=False, combine=False, invert_x=False, ymax=None, save=True,
                    specificity=None, roi=None,
                    bin_range=None, bin_edges=None, share_bins=False,
                    xmin=None, xmax=None, share_axes=True):
    """
    Histogram: one figure per condition/factor, or a combined overlay.
    Supports queued marker/x_attr inputs:
        - marker scalar, x_attr list -> one plot per x_attr
        - marker list, x_attr scalar -> one plot per marker
        - marker list, x_attr list -> all marker x x_attr combinations
    Column mapping:
    - x_attr can be a suffix (e.g. 'volume', 'surface') or a full marker
      column name (e.g. 'Syn_Volume').
    Backward-compatible aliases:
    - merge=True behaves like combine=True.
    Bin behavior:
    - combine=True always shares bins across groups.
    - share_bins=True enables shared bins across separate per-group figures.
    - Use bin_range=(min, max) / xmin / xmax for exact histogram range.
    - Use bin_edges=[...] for exact shared bin edges.
    Shared axis scales:
    - ``share_axes=True`` (default) lets the experiment-level axis registry
      (see ``set_axis_limits``) supply ``bin_range`` and ``ymax`` when they
      are not passed explicitly.
    """
    bin_range = _merge_axis_range(bin_range, xmin, xmax)
    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_histograms(
                experiment, marker, x_attr,
                by=by, factor=factor,
                bins=bins, binwidth=binwidth, kde=kde,
                alpha=alpha, stat=stat,
                merge=merge, combine=combine, invert_x=invert_x, ymax=ymax, save=save,
                specificity=specificity, roi=_rb,
                bin_range=bin_range, bin_edges=bin_edges, share_bins=share_bins,
                share_axes=share_axes,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    marker_is_queue = isinstance(marker, queue_types) and not isinstance(marker, str)
    xattr_is_queue = isinstance(x_attr, queue_types) and not isinstance(x_attr, str)
    if marker_is_queue or xattr_is_queue:
        marker_values = _flatten_specificity_values([marker]) if marker_is_queue else [marker]
        xattr_values = _flatten_specificity_values([x_attr]) if xattr_is_queue else [x_attr]
        if len(marker_values) == 0 or len(xattr_values) == 0:
            raise ValueError("Queued marker/x_attr inputs must contain at least one value.")
        queued_outputs = {}
        for m_val in marker_values:
            for xa_val in xattr_values:
                key = (m_val, xa_val)
                queued_outputs[key] = plot_histograms(
                    experiment,
                    marker=m_val,
                    x_attr=xa_val,
                    by=by,
                    factor=factor,
                    bins=bins,
                    binwidth=binwidth,
                    bin_range=bin_range,
                    bin_edges=bin_edges,
                    share_bins=share_bins,
                    kde=kde,
                    alpha=alpha,
                    stat=stat,
                    merge=merge,
                    combine=combine,
                    invert_x=invert_x,
                    ymax=ymax,
                    save=save,
                    specificity=specificity,
                    roi=roi,
                    share_axes=share_axes,
                )
        return queued_outputs

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_histograms(
                experiment, marker, x_attr,
                by=by, factor=factor,
                bins=bins, binwidth=binwidth, bin_range=bin_range,
                bin_edges=bin_edges, share_bins=share_bins, kde=kde,
                alpha=alpha, stat=stat, merge=merge, combine=combine, invert_x=invert_x,
                ymax=ymax, save=save, specificity=spec, roi=roi,
                share_axes=share_axes,
            )
        return queued_outputs

    marker_key = _resolve_marker_data_key(experiment, marker)
    x = _resolve_histogram_x_column(experiment, marker_key, x_attr)
    if share_axes and bin_range is None:
        bin_range = _lookup_axis_registry(experiment, x)
    # Fill any half-bounds (from partial xmin/xmax or a registry entry such as
    # `(None, 25.0)`) from the marker data so downstream validation doesn't
    # choke on None.
    if bin_range is not None and (bin_range[0] is None or bin_range[1] is None):
        marker_df_for_bounds = experiment.data[marker_key].df.reset_index()
        marker_df_for_bounds = _filter_df_by_specificity(marker_df_for_bounds, specificity)
        data_values = _to_numeric_excluding_not_included(marker_df_for_bounds[x]).dropna()
        if len(data_values) == 0:
            bin_range = None
        else:
            data_lo = float(data_values.min())
            data_hi = float(data_values.max())
            lo = data_lo if bin_range[0] is None else float(bin_range[0])
            hi = data_hi if bin_range[1] is None else float(bin_range[1])
            bin_range = (lo, hi) if hi > lo else None
    level = 'factors' if factor else by
    combine_mode = bool(combine or merge)
    share_bins_mode = bool(combine_mode or share_bins)
    bin_range_norm = _normalize_hist_bin_range(bin_range)
    bins_spec = _coerce_hist_bin_edges(bin_edges)
    if ymax is not None:
        ymax = float(ymax)
        if not np.isfinite(ymax) or ymax <= 0:
            raise ValueError("ymax must be a finite number > 0.")

    if share_bins_mode and bins_spec is None:
        marker_df_all = experiment.data[marker_key].df.reset_index()
        marker_df_all = _filter_df_by_specificity(marker_df_all, specificity)
        all_values = _to_numeric_excluding_not_included(marker_df_all[x]).dropna().to_numpy()
        bins_spec = _compute_hist_bin_edges(
            all_values,
            bins=bins,
            binwidth=binwidth,
            bin_range=bin_range_norm,
        )

    _hist_shared_fig_ref = {"fig": None}

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_histograms',
            total=_count_level_processes(experiment, level, factor=factor, specificity=specificity),
        )
        _progress_start_item(state)
        if combine_mode:
            if state.get('fig') is None or state.get('ax') is None:
                fig, ax = plt.subplots(figsize=(8, 8))
                state['fig'] = fig
                state['ax'] = ax
        else:
            if 'shared_fig' not in state or 'shared_ax' not in state:
                fig, ax = plt.subplots(figsize=(8, 8))
                state['shared_fig'] = fig
                state['shared_ax'] = ax
                _hist_shared_fig_ref["fig"] = fig
            else:
                fig = state['shared_fig']
                ax = state['shared_ax']
                ax.clear()
            state['fig'] = fig
            state['ax'] = ax

    def teardown(ctx, state, results):
        fig = state['fig']
        name = ctx.factor_value or ctx.condition or 'Combined'
        subfolder, suffix = build_subfolder(
            plot_type='Histograms', marker=marker_key,
            factor=factor, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        _progress_finish_item(state, name)

        if combine_mode:
            prog = state.get('progress_state', {})
            is_last = int(prog.get('completed', 0)) >= int(prog.get('total', 1))
            if not is_last:
                return
            ax = state.get('ax')
            if ax is not None:
                handles, labels = ax.get_legend_handles_labels()
                if len(labels) > 0:
                    seen = {}
                    for h, l in zip(handles, labels):
                        if l not in seen:
                            seen[l] = h
                    legend_title = str(factor) if factor is not None else 'Condition'
                    ax.legend(
                        list(seen.values()), list(seen.keys()),
                        title=legend_title, frameon=False,
                    )
            if save:
                save_fig(fig, experiment.fig_path,
                         f'{x} Histogram (Combined)' + suffix, subfolder=subfolder)
            plt.close(fig)
            return

        if save:
            save_fig(fig, experiment.fig_path,
                     f'{x} Histogram {name}' + suffix, subfolder=subfolder)

    result = run(
        experiment, over=level, action=histogram_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        marker=marker_key, x=x, bins=bins, binwidth=binwidth,
        bin_range=bin_range_norm, bins_spec=bins_spec, ymax=ymax,
        kde=kde, alpha=alpha, stat=stat, invert_x=invert_x,
        merge=combine_mode, combine=combine_mode,
        specificity_filter=specificity,
        roi_base=_roi_base,
    )
    if not combine_mode and _hist_shared_fig_ref.get("fig") is not None:
        plt.close(_hist_shared_fig_ref["fig"])
    try:
        if Config.EXPORT_HTML:
            subfolder_html, _ = build_subfolder(
                plot_type='Histograms', marker=marker_key, factor=factor,
                specificity=specificity,
                aliases=getattr(experiment, 'aliases', None),
                roi_base=_roi_base, multi_roi=_multi_roi,
            )
            html_save_path = os.path.join(experiment.fig_path, subfolder_html) if subfolder_html else experiment.fig_path
            _export_html_histogram(experiment, marker, x_attr, specificity, html_save_path, by, factor)
    except Exception:
        pass
    return result


def plot_ridgeline(experiment, marker, x_attr,
                   by='conditions', factor=None,
                   ridge_height=0.85, alpha=0.55,
                   line_width=1.5, bw_adjust=1.0,
                   save=True, specificity=None, roi=None,
                   bottom_ticks=True, bottom_tick_labels=True,
                   x_range=None, xmin=None, xmax=None, share_axes=True):
    """
    Ridgeline density plot by condition/factor for one marker attribute.

    Similar input style to `plot_histograms`:
    - accepts marker and x_attr scalar or list-like (all combinations)
    - supports specificity queue mode

    Shared axis scales:
    - ``x_range=(min, max)`` / ``xmin`` / ``xmax`` force the x-axis range.
    - ``share_axes=True`` (default) lets the experiment-level axis registry
      (see ``set_axis_limits``) supply the x-axis range when none is passed.
    """
    x_range = _merge_axis_range(x_range, xmin, xmax)
    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_ridgeline(
                experiment, marker, x_attr,
                by=by, factor=factor,
                ridge_height=ridge_height, alpha=alpha,
                line_width=line_width, bw_adjust=bw_adjust,
                save=save, specificity=specificity, roi=_rb,
                bottom_ticks=bottom_ticks, bottom_tick_labels=bottom_tick_labels,
                x_range=x_range, share_axes=share_axes,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    marker_is_queue = isinstance(marker, queue_types) and not isinstance(marker, str)
    xattr_is_queue = isinstance(x_attr, queue_types) and not isinstance(x_attr, str)
    if marker_is_queue or xattr_is_queue:
        marker_values = _flatten_specificity_values([marker]) if marker_is_queue else [marker]
        xattr_values = _flatten_specificity_values([x_attr]) if xattr_is_queue else [x_attr]
        if len(marker_values) == 0 or len(xattr_values) == 0:
            raise ValueError("Queued marker/x_attr inputs must contain at least one value.")
        queued_outputs = {}
        for m_val in marker_values:
            for xa_val in xattr_values:
                key = (m_val, xa_val)
                queued_outputs[key] = plot_ridgeline(
                    experiment,
                    marker=m_val,
                    x_attr=xa_val,
                    by=by,
                    factor=factor,
                    ridge_height=ridge_height,
                    alpha=alpha,
                    line_width=line_width,
                    bw_adjust=bw_adjust,
                    save=save,
                    specificity=specificity,
                    roi=roi,
                    bottom_ticks=bottom_ticks,
                    bottom_tick_labels=bottom_tick_labels,
                    x_range=x_range,
                    share_axes=share_axes,
                )
        return queued_outputs

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_ridgeline(
                experiment,
                marker=marker,
                x_attr=x_attr,
                by=by,
                factor=factor,
                ridge_height=ridge_height,
                alpha=alpha,
                line_width=line_width,
                bw_adjust=bw_adjust,
                save=save,
                specificity=spec,
                roi=roi,
                bottom_ticks=bottom_ticks,
                bottom_tick_labels=bottom_tick_labels,
                x_range=x_range,
                share_axes=share_axes,
            )
        return queued_outputs

    marker_key = _resolve_marker_data_key(experiment, marker)
    x = _resolve_histogram_x_column(experiment, marker_key, x_attr)
    level = 'factors' if factor else by
    total_groups = _count_level_processes(experiment, level, factor=factor, specificity=specificity)

    marker_df_all = experiment.data[marker_key].df.reset_index()
    marker_df_all = _filter_df_by_specificity(marker_df_all, specificity)
    all_values = _to_numeric_excluding_not_included(marker_df_all[x]).dropna().to_numpy()
    if all_values.size == 0:
        raise ValueError(f"No numeric values available for ridgeline plot: {x}")

    effective_range = x_range
    if share_axes and effective_range is None:
        effective_range = _lookup_axis_registry(experiment, x)

    if effective_range is not None:
        reg_low, reg_high = effective_range
        data_min = float(np.min(all_values))
        data_max = float(np.max(all_values))
        x_min = data_min if reg_low is None else float(reg_low)
        x_max = data_max if reg_high is None else float(reg_high)
    else:
        x_min = float(np.min(all_values))
        x_max = float(np.max(all_values))

    if x_max <= x_min:
        pad = 1.0 if x_min == 0 else abs(x_min) * 0.05
        x_min -= pad
        x_max += pad
    elif effective_range is None:
        pad = (x_max - x_min) * 0.05
        x_min -= pad
        x_max += pad
    x_grid = np.linspace(x_min, x_max, 400, dtype=float)

    try:
        ridge_height_f = float(ridge_height)
    except Exception as e:
        raise ValueError("ridge_height must be numeric.") from e
    ridge_height_f = max(0.05, ridge_height_f)
    try:
        alpha_f = float(alpha)
    except Exception as e:
        raise ValueError("alpha must be numeric.") from e
    alpha_f = min(1.0, max(0.0, alpha_f))
    try:
        line_width_f = float(line_width)
    except Exception as e:
        raise ValueError("line_width must be numeric.") from e
    line_width_f = max(0.0, line_width_f)
    try:
        bw_adjust_f = float(bw_adjust)
    except Exception as e:
        raise ValueError("bw_adjust must be numeric.") from e
    bw_adjust_f = max(1e-6, bw_adjust_f)

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_ridgeline',
            total=total_groups,
        )
        _progress_start_item(state)
        if state.get('fig') is None or state.get('ax') is None:
            fig_h = max(2.8, float(max(1, total_groups)) * 0.8 + 1.5)
            fig, ax = plt.subplots(figsize=(8.2, fig_h))
            state['fig'] = fig
            state['ax'] = ax

    def teardown(ctx, state, results):
        name, _ = _resolve_group_label_color(ctx)
        _progress_finish_item(state, name)

        prog = state.get('progress_state', {})
        is_last = int(prog.get('completed', 0)) >= int(prog.get('total', 1))
        if not is_last:
            return

        fig = state.get('fig')
        ax = state.get('ax')
        if fig is None or ax is None:
            return

        ridge_labels = state.get("ridge_labels", {})
        if len(ridge_labels) > 0:
            idxs = sorted(ridge_labels.keys())
            ax.set_yticks([float(i) + ridge_height_f * 0.5 for i in idxs])
            ax.set_yticklabels([ridge_labels[i] for i in idxs])
            ax.set_ylim(min(idxs) - 0.15, max(idxs) + ridge_height_f + 0.35)
        else:
            ax.set_yticks([])

        ax.set_xlim(x_min, x_max)
        x_label = get_display_name(x, compact_per=True)
        marker_s = str(marker_key).strip()
        marker_prefix = f"{marker_s}_"
        if marker_s and str(x).casefold().startswith(marker_prefix.casefold()):
            if marker_s.casefold() not in x_label.casefold():
                x_label = f"{marker_s} {x_label}".strip()
        ax.set_xlabel(x_label)
        ax.set_ylabel("")
        ax.tick_params(
            axis='x',
            which='both',
            bottom=bool(bottom_ticks),
            top=False,
            labelbottom=bool(bottom_tick_labels),
        )
        ax.tick_params(axis='y', length=0)
        sns.despine(trim=False, ax=ax)
        fig.tight_layout()

        subfolder, suffix = build_subfolder(
            plot_type='Ridgelines', marker=marker_key,
            factor=factor, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        if save:
            save_fig(fig, experiment.fig_path, f'{x} Ridgeline' + suffix, subfolder=subfolder)
        plt.close(fig)

    return run(
        experiment, over=level, action=ridgeline_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        marker=marker_key,
        x=x,
        x_grid=x_grid,
        ridge_height=ridge_height_f,
        alpha=alpha_f,
        line_width=line_width_f,
        bw_adjust=bw_adjust_f,
        specificity_filter=specificity,
        roi_base=_roi_base,
    )


def ecdf_action(ctx: Context, state: dict,
                marker=None, x=None,
                line_width=2.0, alpha=1.0,
                stat='proportion', complementary=False, **kwargs):
    """Plot an ECDF line for one condition/factor group."""
    ax = _resolve_action_axis(state, 0)
    if ax is None:
        raise IndexError("No valid axis available for ecdf_action.")

    df = ctx.experiment.data[marker].df.reset_index()
    df = _filter_marker_df_for_context(ctx, df)
    specificity = kwargs.get('specificity_filter', kwargs.get('specificity'))
    df = _filter_df_by_specificity(df, specificity)
    if x not in df.columns:
        raise ValueError(f"Column '{x}' not found in marker '{marker}' dataframe.")
    values = _to_numeric_excluding_not_included(df[x]).dropna()

    group_name, group_color = _resolve_group_label_color(ctx)
    if len(values) == 0:
        ax.text(0.5, 0.5, "No data available", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return {'group': group_name, 'n': 0}

    sns.ecdfplot(
        x=values,
        ax=ax,
        color=group_color,
        linewidth=float(max(0.0, line_width)),
        alpha=float(min(1.0, max(0.0, alpha))),
        stat=str(stat),
        complementary=bool(complementary),
    )

    x_label = get_display_name(x, compact_per=True)
    marker_s = str(marker).strip()
    marker_prefix = f"{marker_s}_"
    if marker_s and str(x).casefold().startswith(marker_prefix.casefold()):
        if marker_s.casefold() not in x_label.casefold():
            x_label = f"{marker_s} {x_label}".strip()
    ax.set_xlabel(x_label)

    stat_key = str(stat).strip().casefold()
    if stat_key == 'count':
        y_label = "Count"
    else:
        y_label = "Proportion"
    if bool(complementary):
        y_label = f"Complementary {y_label}"
    ax.set_ylabel(y_label)
    sns.despine(trim=False, ax=ax)
    return {'group': group_name, 'n': int(len(values))}


def plot_ecdf(experiment, marker, x_attr,
              by='conditions', factor=None,
              line_width=2.0, alpha=1.0,
              stat='proportion', complementary=False,
              save=True, specificity=None, roi=None,
              bottom_ticks=True, bottom_tick_labels=True,
              x_range=None, xmin=None, xmax=None, share_axes=True):
    """
    ECDF plot by condition/factor for one marker attribute.

    Similar input style to `plot_histograms`:
    - accepts marker and x_attr scalar or list-like (all combinations)
    - supports specificity queue mode

    Shared axis scales:
    - ``x_range=(min, max)`` / ``xmin`` / ``xmax`` force the x-axis range.
    - ``share_axes=True`` (default) lets the experiment-level axis registry
      (see ``set_axis_limits``) supply the x-axis range when none is passed.
    """
    x_range = _merge_axis_range(x_range, xmin, xmax)
    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_ecdf(
                experiment, marker, x_attr,
                by=by, factor=factor,
                line_width=line_width, alpha=alpha,
                stat=stat, complementary=complementary,
                save=save, specificity=specificity, roi=_rb,
                bottom_ticks=bottom_ticks, bottom_tick_labels=bottom_tick_labels,
                x_range=x_range, share_axes=share_axes,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    marker_is_queue = isinstance(marker, queue_types) and not isinstance(marker, str)
    xattr_is_queue = isinstance(x_attr, queue_types) and not isinstance(x_attr, str)
    if marker_is_queue or xattr_is_queue:
        marker_values = _flatten_specificity_values([marker]) if marker_is_queue else [marker]
        xattr_values = _flatten_specificity_values([x_attr]) if xattr_is_queue else [x_attr]
        if len(marker_values) == 0 or len(xattr_values) == 0:
            raise ValueError("Queued marker/x_attr inputs must contain at least one value.")
        queued_outputs = {}
        for m_val in marker_values:
            for xa_val in xattr_values:
                key = (m_val, xa_val)
                queued_outputs[key] = plot_ecdf(
                    experiment,
                    marker=m_val,
                    x_attr=xa_val,
                    by=by,
                    factor=factor,
                    line_width=line_width,
                    alpha=alpha,
                    stat=stat,
                    complementary=complementary,
                    save=save,
                    specificity=specificity,
                    roi=roi,
                    bottom_ticks=bottom_ticks,
                    bottom_tick_labels=bottom_tick_labels,
                    x_range=x_range,
                    share_axes=share_axes,
                )
        return queued_outputs

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_ecdf(
                experiment,
                marker=marker,
                x_attr=x_attr,
                by=by,
                factor=factor,
                line_width=line_width,
                alpha=alpha,
                stat=stat,
                complementary=complementary,
                save=save,
                specificity=spec,
                roi=roi,
                bottom_ticks=bottom_ticks,
                bottom_tick_labels=bottom_tick_labels,
                x_range=x_range,
                share_axes=share_axes,
            )
        return queued_outputs

    marker_key = _resolve_marker_data_key(experiment, marker)
    x = _resolve_histogram_x_column(experiment, marker_key, x_attr)
    level = 'factors' if factor else by

    effective_x_range = x_range
    if share_axes and effective_x_range is None:
        effective_x_range = _lookup_axis_registry(experiment, x)

    stat_key = str(stat).strip().casefold()
    if stat_key not in {"proportion", "count"}:
        raise ValueError("stat must be 'proportion' or 'count'.")
    try:
        line_width_f = float(line_width)
    except Exception as e:
        raise ValueError("line_width must be numeric.") from e
    line_width_f = max(0.0, line_width_f)
    try:
        alpha_f = float(alpha)
    except Exception as e:
        raise ValueError("alpha must be numeric.") from e
    alpha_f = min(1.0, max(0.0, alpha_f))

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_ecdf',
            total=_count_level_processes(experiment, level, factor=factor, specificity=specificity),
        )
        _progress_start_item(state)
        fig, ax = plt.subplots(figsize=(8, 8))
        state['fig'] = fig
        state['ax'] = ax

    def teardown(ctx, state, results):
        fig = state['fig']
        name = ctx.factor_value or ctx.condition or 'Combined'
        ax = state.get('ax')
        if ax is not None:
            _apply_axis_range(ax, 'x', effective_x_range)
            ax.tick_params(
                axis='x',
                which='both',
                bottom=bool(bottom_ticks),
                top=False,
                labelbottom=bool(bottom_tick_labels),
            )
        subfolder, suffix = build_subfolder(
            plot_type='ECDFs', marker=marker_key,
            factor=factor, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        if save:
            save_fig(fig, experiment.fig_path, f'{x} ECDF {name}' + suffix, subfolder=subfolder)
        _progress_finish_item(state, name)
        plt.close(fig)

    return run(
        experiment, over=level, action=ecdf_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        marker=marker_key,
        x=x,
        line_width=line_width_f,
        alpha=alpha_f,
        stat=stat_key,
        complementary=bool(complementary),
        specificity_filter=specificity,
        roi_base=_roi_base,
    )


def volcano_action(ctx: Context, state: dict,
                   volcano_columns=None, control=None,
                   factor=None, force_nonparametric=False,
                   p_threshold=0.05, label_points='significant',
                   **kwargs):
    """Plot one volcano panel for current group vs control across selected columns."""
    ax = _resolve_action_axis(state, 0)
    if ax is None:
        raise IndexError("No valid axis available for volcano_action.")

    summary = ctx.summary
    if not isinstance(volcano_columns, (list, tuple, pd.Index, np.ndarray)) or len(volcano_columns) == 0:
        raise ValueError("volcano_action requires a non-empty `volcano_columns` list.")

    group_name = ctx.factor_value if ctx.factor_value is not None else ctx.condition
    if group_name is None:
        raise ValueError("Could not resolve current group for volcano plot.")
    group_name = str(group_name)
    control_name = str(control)

    active_factor = factor if factor is not None else ctx.factor
    if active_factor is not None:
        if active_factor not in summary.columns:
            raise ValueError(f"Factor column '{active_factor}' not found in summary.")
        control_mask = summary[active_factor].astype(str) == control_name
        group_mask = summary[active_factor].astype(str) == group_name
    else:
        if "Condition" not in summary.columns:
            raise ValueError("Column 'Condition' not found in summary.")
        control_mask = summary["Condition"].astype(str) == control_name
        group_mask = summary["Condition"].astype(str) == group_name

    control_n = int(control_mask.sum())
    group_n = int(group_mask.sum())
    state["volcano_group_name"] = group_name
    if group_name == control_name:
        state["volcano_skip_save"] = True
        ax.axis("off")
        ax.text(0.5, 0.5, "Control group (reference)", ha="center", va="center")
        return {"group": group_name, "n_points": 0}
    if control_n == 0 or group_n == 0:
        state["volcano_skip_save"] = True
        ax.axis("off")
        ax.text(0.5, 0.5, "No data for control/group", ha="center", va="center")
        return {"group": group_name, "n_points": 0}

    _, group_color = _resolve_group_label_color(ctx)
    label_mode = _normalize_volcano_label_mode(label_points)
    p_thr = float(p_threshold) if p_threshold is not None else 0.05
    if not np.isfinite(p_thr) or p_thr <= 0 or p_thr >= 1:
        raise ValueError("p_threshold must be a finite number between 0 and 1.")
    y_thr = -np.log10(p_thr)

    rows = []
    for col in volcano_columns:
        if col not in summary.columns:
            continue
        c_vals = _to_numeric_excluding_not_included(summary.loc[control_mask, col]).dropna()
        g_vals = _to_numeric_excluding_not_included(summary.loc[group_mask, col]).dropna()
        if len(c_vals) == 0 or len(g_vals) == 0:
            continue
        c_mean = float(c_vals.mean())
        g_mean = float(g_vals.mean())
        x_pct = _volcano_percent_change(c_mean, g_mean)
        if not np.isfinite(x_pct):
            continue
        x_log_pct = _volcano_signed_log_percent_change(x_pct)
        if not np.isfinite(x_log_pct):
            continue
        p_val, test_name = _volcano_pairwise_pvalue(
            c_vals,
            g_vals,
            force_nonparametric=force_nonparametric,
        )
        if not np.isfinite(p_val):
            continue
        p_val = max(float(p_val), 1e-300)
        y_sig = -np.log10(p_val)
        is_sig = bool(p_val < p_thr)
        rows.append({
            "column": str(col),
            "x_pct": float(x_pct),
            "x_log_pct": float(x_log_pct),
            "p": float(p_val),
            "y_sig": float(y_sig),
            "significant": is_sig,
            "test": test_name,
        })

    if len(rows) == 0:
        state["volcano_skip_save"] = True
        ax.axis("off")
        ax.text(0.5, 0.5, "No comparable numeric columns", ha="center", va="center")
        return {"group": group_name, "n_points": 0}

    dfp = pd.DataFrame(rows).sort_values("x_log_pct", kind="stable")
    sig = dfp[dfp["significant"]]
    nonsig = dfp[~dfp["significant"]]

    x_vals = pd.to_numeric(dfp["x_log_pct"], errors="coerce").to_numpy(dtype=float)
    y_vals = pd.to_numeric(dfp["y_sig"], errors="coerce").to_numpy(dtype=float)
    x_min = float(np.nanmin(np.r_[x_vals, 0.0])) if x_vals.size else -1.0
    x_max = float(np.nanmax(np.r_[x_vals, 0.0])) if x_vals.size else 1.0
    if not np.isfinite(x_min):
        x_min = -1.0
    if not np.isfinite(x_max):
        x_max = 1.0
    if x_min == x_max:
        x_min -= 0.5
        x_max += 0.5
    x_span = max(1e-9, x_max - x_min)

    y_max_data = float(np.nanmax(np.r_[y_vals, y_thr])) if y_vals.size else float(y_thr)
    if not np.isfinite(y_max_data) or y_max_data <= 0:
        y_max_data = 1.0
    y_low = 0.0
    y_high = y_max_data * 1.12
    y_span = max(1e-9, y_high - y_low)

    label_margin = max(0.16, 0.24 * x_span)
    edge_pad = max(0.08, 0.10 * x_span)
    left_label_x = x_min - label_margin
    right_label_x = x_max + label_margin
    ax.set_xlim(left_label_x - edge_pad, right_label_x + edge_pad)
    ax.set_ylim(y_low, y_high)

    ax.axhline(y_thr, linestyle="--", linewidth=1.2, color="black", alpha=0.8)
    ax.axvline(0.0, linestyle="-", linewidth=1.0, color="black", alpha=0.25)

    if len(nonsig) > 0:
        ax.scatter(
            nonsig["x_log_pct"], nonsig["y_sig"],
            s=48, c="#BFBFBF", edgecolors="white", linewidths=0.5, zorder=2,
        )
    if len(sig) > 0:
        ax.scatter(
            sig["x_log_pct"], sig["y_sig"],
            s=56, c=group_color, edgecolors="white", linewidths=0.6, zorder=3,
        )

    # Place labels on side margins and spread them vertically to reduce overlap.
    label_df = None
    if label_mode == "significant":
        label_df = sig
    elif label_mode == "non-significant":
        label_df = nonsig
    elif label_mode == "both":
        label_df = dfp

    if label_df is not None and len(label_df) > 0:
        y_min_labels = y_low + 0.04 * y_span
        y_max_labels = y_high - 0.04 * y_span
        min_gap = 0.055 * y_span

        left_sig = label_df[label_df["x_log_pct"] < 0].copy().sort_values("y_sig", kind="stable")
        right_sig = label_df[label_df["x_log_pct"] >= 0].copy().sort_values("y_sig", kind="stable")

        left_label_y = _spread_label_positions(
            left_sig["y_sig"].to_numpy(dtype=float),
            y_min_labels,
            y_max_labels,
            min_gap,
        )
        right_label_y = _spread_label_positions(
            right_sig["y_sig"].to_numpy(dtype=float),
            y_min_labels,
            y_max_labels,
            min_gap,
        )

        for row, y_txt in zip(left_sig.itertuples(index=False), left_label_y):
            label = get_display_name(row.column, compact_per=True)
            label_color = group_color if bool(row.significant) else "#7F7F7F"
            ax.annotate(
                label,
                xy=(row.x_log_pct, row.y_sig),
                xytext=(left_label_x, y_txt),
                textcoords="data",
                ha="right",
                va="center",
                fontsize=9,
                color=label_color,
                arrowprops={
                    "arrowstyle": "-",
                    "color": label_color,
                    "lw": 0.8,
                    "shrinkA": 0,
                    "shrinkB": 0,
                },
                zorder=4,
            )

        for row, y_txt in zip(right_sig.itertuples(index=False), right_label_y):
            label = get_display_name(row.column, compact_per=True)
            label_color = group_color if bool(row.significant) else "#7F7F7F"
            ax.annotate(
                label,
                xy=(row.x_log_pct, row.y_sig),
                xytext=(right_label_x, y_txt),
                textcoords="data",
                ha="left",
                va="center",
                fontsize=9,
                color=label_color,
                arrowprops={
                    "arrowstyle": "-",
                    "color": label_color,
                    "lw": 0.8,
                    "shrinkA": 0,
                    "shrinkB": 0,
                },
                zorder=4,
            )

    x_label = f"signed log10(1 + |% change|) vs {control_name}"
    ax.set_xlabel(x_label)
    ax.set_ylabel("-log10(p-value)")
    ax.set_title(f"{group_name} vs {control_name}", fontsize=14, weight="bold")
    sns.despine(trim=False, ax=ax)

    state["volcano_skip_save"] = False
    state["volcano_points"] = int(len(dfp))
    return {"group": group_name, "n_points": int(len(dfp))}


def plot_volcano(experiment, filtered_columns=None,
                 by='conditions', factor=None,
                 control=None,
                 specificity=None, roi=None,
                 force_nonparametric=False,
                 p_threshold=0.05,
                 label_points='significant',
                 save=True,
                 column_strings=None, regex_string=None, exclude=''):
    """
    Volcano plot of signed log(% change vs control) against -log10(p)
    across selected columns.

    Similar column-filtering style to `plot_mean_bars` and grouping style to
    histogram/regression wrappers.

    label_points controls point annotations:
    - 'significant' (default)
    - 'non-significant'
    - 'both'
    - 'none'
    """
    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_volcano(
                experiment,
                filtered_columns=filtered_columns,
                by=by, factor=factor, control=control,
                specificity=specificity, roi=_rb,
                force_nonparametric=force_nonparametric,
                p_threshold=p_threshold,
                label_points=label_points,
                save=save,
                column_strings=column_strings, regex_string=regex_string, exclude=exclude,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_volcano(
                experiment,
                filtered_columns=filtered_columns,
                by=by,
                factor=factor,
                control=control,
                specificity=spec,
                roi=roi,
                force_nonparametric=force_nonparametric,
                p_threshold=p_threshold,
                label_points=label_points,
                save=save,
                column_strings=column_strings,
                regex_string=regex_string,
                exclude=exclude,
            )
        return queued_outputs

    resolved_columns = _resolve_filtered_columns(
        experiment,
        filtered_columns=filtered_columns,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=exclude,
    )
    resolved_columns = _filter_plotable_numeric_columns(
        experiment,
        resolved_columns,
        factor=factor,
    )
    if len(resolved_columns) == 0:
        raise ValueError(
            "No plottable numeric columns were found after filtering. "
            "Try different filters or remove non-numeric columns."
        )

    level = 'factors' if factor else by
    if level not in {'conditions', 'factors'}:
        raise ValueError("plot_volcano supports grouping by conditions or factors.")

    summary_filtered = _filtered_summary_for_specificity(experiment, specificity)
    if level == 'factors':
        if factor is None:
            raise ValueError("factor must be provided when grouping by factors.")
        if factor not in summary_filtered.columns:
            raise ValueError(f"Factor column '{factor}' not found in summary.")
        available_groups = [str(v) for v in summary_filtered[factor].dropna().unique().tolist()]
        if len(available_groups) == 0:
            raise ValueError(f"No groups found for factor '{factor}' after specificity filtering.")
    else:
        available_groups = [str(c.name) for c in experiment.condition_list]
    control_name = _resolve_control_name(control, available_groups)

    _volcano_shared_fig_ref = {"fig": None}

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_volcano',
            total=_count_level_processes(experiment, level, factor=factor, specificity=specificity),
        )
        group_name = ctx.factor_value if factor is not None else ctx.condition
        _progress_start_item(state, group_name)
        if 'shared_fig' not in state or 'shared_ax' not in state:
            fig, ax = plt.subplots(figsize=(8, 8))
            state['shared_fig'] = fig
            state['shared_ax'] = ax
            _volcano_shared_fig_ref["fig"] = fig
        else:
            fig = state['shared_fig']
            ax = state['shared_ax']
            ax.clear()
        state['fig'] = fig
        state['ax'] = ax
        state['volcano_skip_save'] = False
        state['volcano_group_name'] = group_name
        state['volcano_points'] = 0

    def teardown(ctx, state, results):
        fig = state['fig']
        group_name = state.get('volcano_group_name') or (ctx.factor_value if factor is not None else ctx.condition)

        subfolder, suffix = build_subfolder(
            plot_type='Volcano',
            factor=factor, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )

        if save and not bool(state.get('volcano_skip_save', False)):
            save_fig(
                fig,
                experiment.fig_path,
                f'Volcano {group_name} vs {control_name}' + suffix,
                subfolder=subfolder,
            )
        _progress_finish_item(state, group_name)

    result = run(
        experiment, over=level, action=volcano_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        volcano_columns=resolved_columns,
        control=control_name,
        force_nonparametric=force_nonparametric,
        p_threshold=p_threshold,
        label_points=label_points,
        roi_base=_roi_base,
    )
    if _volcano_shared_fig_ref.get("fig") is not None:
        plt.close(_volcano_shared_fig_ref["fig"])
    try:
        if Config.EXPORT_HTML:
            subfolder_html, _ = build_subfolder(
                plot_type='Volcano', factor=factor, specificity=specificity,
                aliases=getattr(experiment, 'aliases', None),
                roi_base=_roi_base, multi_roi=_multi_roi,
            )
            html_save_path = os.path.join(experiment.fig_path, subfolder_html) if subfolder_html else experiment.fig_path
            _export_html_volcano(experiment, resolved_columns, specificity, html_save_path, control_name)
    except Exception:
        pass
    return result


def plot_radar(experiment, filtered_columns=None,
               by='conditions', factor=None,
               specificity=None, roi=None, save=True,
               combine=False,
               column_strings=None, regex_string=None, exclude='',
               statistic='mean',
               normalize=True, share_scale=True,
               share_columns_across_panels=True,
               fill=True, alpha=0.20, line_width=2.0, point_size=28,
               tick_label_size=10, label_wrap=18,
               include_N=False,
               show_animal_xs=True, animal_x_marker="x", animal_x_size=38,
               animal_x_alpha=0.75, animal_x_color=None,
               radial_value_radii=(0.30, 1.00), radial_value_color="grey",
               radial_value_size=None,
               figsize=(8, 8),
               auto_style=True, style_cycle=None,
               _scale_reference=None, _resolved_columns=None):
    """
    Radar/spider plot across selected summary columns.

    One polygon is drawn per condition or factor level.  With combine=False,
    each group is saved as a separate radar plot.  With combine=True, all
    groups are overlaid on one radar plot.

    `filtered_columns` defines the radar axes.  `column_strings`,
    `regex_string`, and `exclude` use the same column-filtering style as
    `plot_mean_bars`, `plot_matrices`, and `plot_volcano`.

    `specificity` supports a single tuple, e.g. ("Time", "WeekEight"), or a
    queue of tuples, e.g. [("Time", "WeekFour"), ("Time", "WeekEight")].
    When normalize=True and share_scale=True, queued calls share the same
    per-column min/max reference so sibling radar plots are comparable.

    By default, x markers show each contributing animal's values on the same
    axes as the group polygon. Grey radial value labels are shown at 30% and
    100% of the plotted radius; pass radial_value_radii=None to disable them
    or provide custom fractional radii.
    """
    radial_value_radii = _normalize_radar_radial_value_radii(radial_value_radii)

    # ROI queue mode - iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_radar(
                experiment,
                filtered_columns=filtered_columns,
                by=by, factor=factor,
                specificity=specificity, roi=_rb, save=save,
                combine=combine,
                column_strings=column_strings, regex_string=regex_string, exclude=exclude,
                statistic=statistic,
                normalize=normalize, share_scale=share_scale,
                share_columns_across_panels=share_columns_across_panels,
                fill=fill, alpha=alpha, line_width=line_width, point_size=point_size,
                tick_label_size=tick_label_size, label_wrap=label_wrap,
                include_N=include_N,
                show_animal_xs=show_animal_xs,
                animal_x_marker=animal_x_marker,
                animal_x_size=animal_x_size,
                animal_x_alpha=animal_x_alpha,
                animal_x_color=animal_x_color,
                radial_value_radii=radial_value_radii,
                radial_value_color=radial_value_color,
                radial_value_size=radial_value_size,
                figsize=figsize,
                auto_style=auto_style, style_cycle=style_cycle,
                _scale_reference=_scale_reference,
                _resolved_columns=_resolved_columns,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    if _resolved_columns is None:
        summaries = getattr(experiment, 'summaries', None)
        resolved_columns = _resolve_filtered_columns(
            experiment,
            filtered_columns=filtered_columns,
            column_strings=column_strings,
            regex_string=regex_string,
            exclude=exclude,
            source_df=(summaries[_roi_base] if isinstance(summaries, dict) and _roi_base in summaries else None),
        )
        resolved_columns = _filter_radar_numeric_columns(
            experiment,
            resolved_columns,
            factor=factor,
            specificity=specificity,
            roi_base=_roi_base,
            share_columns_across_panels=share_columns_across_panels,
        )
    else:
        resolved_columns = list(_resolved_columns)

    if len(resolved_columns) < 3:
        raise ValueError(
            "plot_radar needs at least three plottable numeric columns after filtering."
        )

    scale_reference = _scale_reference
    if bool(normalize) and bool(share_scale) and scale_reference is None:
        summaries = getattr(experiment, 'summaries', None)
        if isinstance(summaries, dict) and _roi_base in summaries:
            scale_source = summaries[_roi_base]
        else:
            scale_source = experiment.summary
        scale_source = _summary_for_queue_share(scale_source, specificity)
        scale_reference = _compute_radar_scale_reference(scale_source, resolved_columns)

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_radar(
                experiment,
                filtered_columns=resolved_columns,
                by=by,
                factor=factor,
                specificity=spec,
                roi=roi,
                save=save,
                combine=combine,
                statistic=statistic,
                normalize=normalize,
                share_scale=share_scale,
                share_columns_across_panels=share_columns_across_panels,
                fill=fill,
                alpha=alpha,
                line_width=line_width,
                point_size=point_size,
                tick_label_size=tick_label_size,
                label_wrap=label_wrap,
                include_N=include_N,
                show_animal_xs=show_animal_xs,
                animal_x_marker=animal_x_marker,
                animal_x_size=animal_x_size,
                animal_x_alpha=animal_x_alpha,
                animal_x_color=animal_x_color,
                radial_value_radii=radial_value_radii,
                radial_value_color=radial_value_color,
                radial_value_size=radial_value_size,
                figsize=figsize,
                auto_style=auto_style, style_cycle=style_cycle,
                _scale_reference=scale_reference,
                _resolved_columns=resolved_columns,
            )
        return queued_outputs

    level = 'factors' if factor else by
    if level not in {'conditions', 'factors'}:
        raise ValueError("plot_radar supports grouping by conditions or factors.")
    if level == 'factors':
        summary_for_factor = _filtered_summary_for_specificity(experiment, specificity, roi_base=_roi_base)
        if factor is None or factor not in summary_for_factor.columns:
            raise ValueError(f"Factor column '{factor}' not found in summary.")

    combine_mode = bool(combine)
    _radar_shared_fig_ref = {"fig": None}

    def _new_radar_fig():
        return plt.subplots(figsize=figsize, subplot_kw={'projection': 'polar'})

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_radar',
            total=_count_level_processes(experiment, level, factor=factor, specificity=specificity, roi_base=_roi_base),
        )
        _progress_start_item(state)
        if combine_mode:
            if state.get('fig') is None or state.get('ax') is None:
                fig, ax = _new_radar_fig()
                state['fig'] = fig
                state['ax'] = ax
                state['radar_series_count'] = 0
                state['radar_raw_max'] = 0.0
        else:
            if 'shared_fig' not in state or 'shared_ax' not in state:
                fig, ax = _new_radar_fig()
                state['shared_fig'] = fig
                state['shared_ax'] = ax
                _radar_shared_fig_ref["fig"] = fig
            else:
                fig = state['shared_fig']
                ax = state['shared_ax']
                ax.clear()
            state['fig'] = fig
            state['ax'] = ax
            state['radar_series_count'] = 0
            state['radar_raw_max'] = 0.0
        state['radar_skip_save'] = False

    def teardown(ctx, state, results):
        fig = state.get('fig')
        ax = state.get('ax')
        name = ctx.factor_value or ctx.condition or 'Combined'
        _progress_finish_item(state, name)

        subfolder, suffix = build_subfolder(
            plot_type='Radar',
            factor=factor,
            specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base,
            multi_roi=_multi_roi,
        )
        stat_label = _radar_statistic_label(statistic)

        if combine_mode:
            prog = state.get('progress_state', {})
            is_last = int(prog.get('completed', 0)) >= int(prog.get('total', 1))
            if not is_last:
                return
            if fig is None or ax is None:
                return
            if int(state.get('radar_series_count', 0)) == 0:
                ax.text(0.5, 0.5, "No data available", transform=ax.transAxes,
                        ha='center', va='center')
            else:
                if not bool(normalize):
                    _style_radar_axis(
                        ax,
                        resolved_columns,
                        normalize=False,
                        tick_label_size=tick_label_size,
                        label_wrap=label_wrap,
                        radial_max=state.get('radar_raw_max'),
                        radial_value_radii=radial_value_radii,
                        radial_value_color=radial_value_color,
                        radial_value_size=radial_value_size,
                    )
                handles, labels = ax.get_legend_handles_labels()
                if len(labels) > 0:
                    seen = {}
                    for h, l in zip(handles, labels):
                        if l not in seen:
                            seen[l] = h
                    legend_title = str(factor) if factor is not None else 'Condition'
                    ax.legend(
                        list(seen.values()), list(seen.keys()),
                        title=legend_title,
                        frameon=False,
                        loc='center left',
                        bbox_to_anchor=(1.08, 0.5),
                    )
            ax.set_title(f"Radar {stat_label} (Combined)", fontsize=14, weight='bold', pad=18)
            if save:
                save_fig(fig, experiment.fig_path,
                         f'Radar {stat_label} Combined' + suffix,
                         subfolder=subfolder)
            plt.close(fig)
            return

        if int(state.get('radar_series_count', 0)) == 0 or bool(state.get('radar_skip_save', False)):
            return
        if fig is not None and ax is not None and save:
            save_fig(fig, experiment.fig_path,
                     f'Radar {stat_label} {name}' + suffix,
                     subfolder=subfolder)

    result = run(
        experiment,
        over=level,
        action=radar_action,
        factor=factor,
        specificity=specificity,
        setup=setup,
        teardown=teardown,
        filtered_columns=resolved_columns,
        statistic=statistic,
        normalize=normalize,
        fill=fill,
        alpha=alpha,
        line_width=line_width,
        point_size=point_size,
        tick_label_size=tick_label_size,
        label_wrap=label_wrap,
        include_N=include_N,
        show_animal_xs=show_animal_xs,
        animal_x_marker=animal_x_marker,
        animal_x_size=animal_x_size,
        animal_x_alpha=animal_x_alpha,
        animal_x_color=animal_x_color,
        radial_value_radii=radial_value_radii,
        radial_value_color=radial_value_color,
        radial_value_size=radial_value_size,
        combine=combine_mode,
        scale_reference=scale_reference if bool(share_scale) else None,
        auto_style=auto_style, style_cycle=style_cycle,
        roi_base=_roi_base,
    )
    if not combine_mode and _radar_shared_fig_ref.get("fig") is not None:
        plt.close(_radar_shared_fig_ref["fig"])
    return result


def plot_pie_charts(experiment, marker, x_attr,
                    by='conditions', factor=None,
                    threshold=None,
                    start_angle=90, line_width=1.0,
                    save=True, specificity=None, roi=None,
                    plot_format='pie', show_counts=None, show_pct=None,
                    labels=None, order=None,
                    include_N=False, as_counts=None, include_n=None,
                    bottom_ticks=False, bottom_tick_labels=False,
                    auto_style=True, style_cycle=None):
    """
    Pie chart distribution by condition/factor for one marker attribute.

    Similar input style to `plot_histograms`:
    - accepts marker and x_attr scalar or list-like (all combinations)
    - supports specificity queue mode

    Threshold grouping:
    - threshold = single number -> two groups: <=t and >t
    - threshold = list/tuple -> bins: <=t1, (t1,t2], ..., >tn

    Style:
    - start_angle: starting angle for wedges.
    - line_width: wedge border width.
    - plot_format: 'pie' (default) or 'bar'.
      For 'bar', all conditions/factor groups are shown on one stacked bar chart.
    - show_counts: display counts.
    - show_pct: display percentages.
    - labels: optional dict mapping plotted labels/bins to display text.
    - order: optional category order. The first ordered category starts at the
      top and proceeds clockwise, so it occupies the top-right side of the pie.
    - include_N: append the number of contributing animals (unique AnimalName).
    - as_counts/include_n: backward-compatible aliases.
    - bottom_ticks / bottom_tick_labels: x-axis tick visibility for bar mode.
    """
    show_counts_flag, show_pct_flag = _resolve_pie_value_flags(
        show_counts=show_counts,
        show_pct=show_pct,
        as_counts=as_counts,
    )
    include_N_flag = _resolve_include_N_flag(include_N=include_N, include_n=include_n)
    order_norm = _normalize_pie_order(order)
    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_pie_charts(
                experiment, marker, x_attr,
                auto_style=auto_style, style_cycle=style_cycle,
                by=by, factor=factor, threshold=threshold,
                start_angle=start_angle, line_width=line_width,
                save=save, specificity=specificity, roi=_rb,
                plot_format=plot_format,
                show_counts=show_counts_flag,
                show_pct=show_pct_flag,
                labels=labels, order=order_norm,
                include_N=include_N_flag,
                bottom_ticks=bottom_ticks, bottom_tick_labels=bottom_tick_labels,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    marker_is_queue = isinstance(marker, queue_types) and not isinstance(marker, str)
    xattr_is_queue = isinstance(x_attr, queue_types) and not isinstance(x_attr, str)
    if marker_is_queue or xattr_is_queue:
        marker_values = _flatten_specificity_values([marker]) if marker_is_queue else [marker]
        xattr_values = _flatten_specificity_values([x_attr]) if xattr_is_queue else [x_attr]
        if len(marker_values) == 0 or len(xattr_values) == 0:
            raise ValueError("Queued marker/x_attr inputs must contain at least one value.")
        queued_outputs = {}
        for m_val in marker_values:
            for xa_val in xattr_values:
                key = (m_val, xa_val)
                queued_outputs[key] = plot_pie_charts(
                    experiment,
                    marker=m_val,
                    x_attr=xa_val,
                    auto_style=auto_style, style_cycle=style_cycle,
                    by=by,
                    factor=factor,
                    threshold=threshold,
                    start_angle=start_angle,
                    line_width=line_width,
                    save=save,
                    specificity=specificity,
                    roi=roi,
                    plot_format=plot_format,
                    show_counts=show_counts_flag,
                    show_pct=show_pct_flag,
                    labels=labels,
                    order=order_norm,
                    include_N=include_N_flag,
                    bottom_ticks=bottom_ticks,
                    bottom_tick_labels=bottom_tick_labels,
                )
        return queued_outputs

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_pie_charts(
                experiment,
                marker=marker,
                x_attr=x_attr,
                auto_style=auto_style, style_cycle=style_cycle,
                by=by,
                factor=factor,
                threshold=threshold,
                start_angle=start_angle,
                line_width=line_width,
                save=save,
                specificity=spec,
                roi=roi,
                plot_format=plot_format,
                show_counts=show_counts_flag,
                show_pct=show_pct_flag,
                labels=labels,
                order=order_norm,
                include_N=include_N_flag,
                bottom_ticks=bottom_ticks,
                bottom_tick_labels=bottom_tick_labels,
            )
        return queued_outputs

    marker_key = _resolve_marker_data_key(experiment, marker)
    x = _resolve_histogram_x_column(experiment, marker_key, x_attr)
    level = 'factors' if factor else by
    total_groups = _count_level_processes(experiment, level, factor=factor, specificity=specificity)
    plot_mode = str(plot_format).strip().casefold()
    if plot_mode not in {"pie", "bar"}:
        raise ValueError("plot_format must be 'pie' or 'bar'.")
    combine_bar_mode = (plot_mode == "bar")
    use_count_scale = _pie_uses_count_scale(
        show_counts=show_counts_flag,
        show_pct=show_pct_flag,
    )

    th_vals = _normalize_threshold_values(threshold)
    try:
        start_angle_f = float(start_angle)
    except Exception as e:
        raise ValueError("start_angle must be numeric.") from e
    try:
        line_width_f = float(line_width)
    except Exception as e:
        raise ValueError("line_width must be numeric.") from e
    if line_width_f < 0:
        raise ValueError("line_width must be >= 0.")

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_pie_charts',
            total=total_groups,
        )
        _progress_start_item(state)
        if combine_bar_mode:
            if state.get('fig') is None or state.get('ax') is None:
                fig_w = max(1, int(max(1, total_groups))) * (2.0 / 3.0)
                fig, ax = plt.subplots(figsize=(fig_w, 5))
                state['fig'] = fig
                state['ax'] = ax
        else:
            fig, ax = plt.subplots(figsize=(8, 8))
            state['fig'] = fig
            state['ax'] = ax

    def teardown(
        ctx, state, results,
        _use_count_scale=use_count_scale,
        _include_N_flag=include_N_flag,
        _show_counts_flag=show_counts_flag,
        _show_pct_flag=show_pct_flag,
    ):
        fig = state['fig']
        name = ctx.factor_value or ctx.condition or 'Combined'
        subfolder, suffix = build_subfolder(
            plot_type='PieCharts', marker=marker_key,
            factor=factor, specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        _progress_finish_item(state, name)

        if combine_bar_mode:
            prog = state.get('progress_state', {})
            is_last = int(prog.get('completed', 0)) >= int(prog.get('total', 1))
            if not is_last:
                return

            ax = state.get('ax')
            if ax is None:
                return
            ax.clear()

            group_order = state.get("pie_bar_group_order", [])
            group_counts = state.get("pie_bar_group_counts", {})
            group_colors = state.get("pie_bar_group_colors", {})
            group_styles = state.get("pie_bar_group_styles", {})
            group_n_animals = state.get("pie_bar_group_n_animals", {})
            category_order = state.get("pie_bar_category_order", [])
            category_pairs = state.get("pie_bar_category_pairs", [])
            if len(category_pairs) > 0:
                cat_raw = [pair[0] for pair in category_pairs]
                cat_display = [pair[1] for pair in category_pairs]
                _, category_order, _ = _apply_pie_order(
                    cat_raw,
                    cat_display,
                    [None] * len(cat_display),
                    order_norm,
                )
            else:
                category_order = _apply_requested_order(category_order, order_norm)

            if len(group_order) == 0 or len(category_order) == 0:
                ax.axis("off")
                ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            else:
                x_pos = np.arange(len(group_order), dtype=float)
                # Match plot_mean_bars visual bar width.
                width = 0.5
                n_cat = max(1, len(category_order))
                max_stack_total = 0.0
                for i, g in enumerate(group_order):
                    g_counts = group_counts.get(g, {})
                    total = float(sum(float(v) for v in g_counts.values()))
                    max_stack_total = max(max_stack_total, total)
                    bottom = 0.0
                    g_color = group_colors.get(g, "black")
                    g_style = group_styles.get(g, "fill")
                    grad = _pie_gradient_colors(g_color, n_cat)
                    for j, cat in enumerate(category_order):
                        raw_val = float(g_counts.get(cat, 0.0))
                        val = raw_val if _use_count_scale else ((raw_val / total) * 100.0 if total > 0 else 0.0)
                        if val <= 0:
                            continue
                        edgecolor = g_color if line_width_f > 0 else "none"
                        _stack_bars = ax.bar(
                            x_pos[i], val, width=width, bottom=bottom,
                            color=grad[j], edgecolor=edgecolor, linewidth=line_width_f,
                        )
                        # Second visual channel: hatch this group's stack when it
                        # shares a colour with another (matches the pie wedges).
                        if g_style and g_style != "fill":
                            _apply_pie_wedge_style(_stack_bars, g_style, g_color)
                        bottom += val

                ax.set_xticks(x_pos)
                ax.set_xticklabels(
                    [
                        _append_animal_n_multiline(
                            g,
                            n_animals=group_n_animals.get(g),
                            include_N=_include_N_flag,
                        )
                        for g in group_order
                    ],
                    rotation=20,
                    ha="right",
                )
                _annotate_stacked_distribution(
                    ax,
                    x_pos,
                    group_order,
                    group_counts,
                    category_order,
                    show_counts=_show_counts_flag,
                    show_pct=_show_pct_flag,
                )
                ax.tick_params(
                    axis='x',
                    which='both',
                    bottom=bool(bottom_ticks),
                    top=False,
                    labelbottom=bool(bottom_tick_labels),
                )
                legend_title = get_display_name(x, compact_per=True)
                marker_s = str(marker_key).strip()
                marker_prefix = f"{marker_s}_"
                axis_label = legend_title
                if marker_s and str(x).casefold().startswith(marker_prefix.casefold()):
                    if marker_s.casefold() not in axis_label.casefold():
                        axis_label = f"{marker_s} {axis_label}".strip()
                    leading = f"{marker_s} "
                    if legend_title.casefold().startswith(leading.casefold()):
                        legend_title = legend_title[len(leading):].strip()
                scale_unit = "counts" if _use_count_scale else "percent"
                if _use_count_scale:
                    ax.set_ylabel(f"{axis_label} ({scale_unit})")
                    ymax_bar = round_up_to_nearest_5(max_stack_total)
                    if ymax_bar > 0:
                        ax.set_ylim(0, ymax_bar)
                        # Keep top major tick exactly at ymax so the top-left
                        # cap/tick appears consistently (same style intent as plot_mean_bars).
                        ax.yaxis.set_major_locator(LinearLocator(numticks=5))
                else:
                    ax.set_ylabel(f"{axis_label} ({scale_unit})")
                    ax.set_ylim(0, 100)
                    ax.yaxis.set_major_locator(LinearLocator(numticks=5))
                ax.set_xlabel("")

                legend_colors = _pie_gradient_colors("black", n_cat)
                handles = [
                    plt.Rectangle((0, 0), 1, 1, facecolor=legend_colors[j], edgecolor="none")
                    for j in range(n_cat)
                ]
                ax.legend(handles, category_order, title=legend_title, frameon=False,
                          bbox_to_anchor=(1.02, 1.0), loc="upper left")
                sns.despine(trim=False, ax=ax)
                fig.tight_layout()

            if save:
                unit_tag = _pie_value_save_tag(
                    show_counts=_show_counts_flag,
                    show_pct=_show_pct_flag,
                )
                save_fig(fig, experiment.fig_path,
                         f'{x} Bar (Combined) {unit_tag}' + suffix, subfolder=subfolder)
            plt.close(fig)
            return

        if save:
            unit_tag = _pie_value_save_tag(
                show_counts=_show_counts_flag,
                show_pct=_show_pct_flag,
            )
            save_fig(fig, experiment.fig_path,
                     f'{x} Pie {name} {unit_tag}' + suffix, subfolder=subfolder)
        plt.close(fig)

    return run(
        experiment, over=level, action=pie_chart_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        marker=marker_key, x=x,
        threshold=th_vals,
        start_angle=start_angle_f,
        line_width=line_width_f,
        plot_format=plot_mode,
        show_counts=bool(show_counts_flag),
        show_pct=bool(show_pct_flag),
        labels=labels,
        order=order_norm,
        include_N=bool(include_N_flag),
        specificity_filter=specificity,
        auto_style=auto_style, style_cycle=style_cycle,
        roi_base=_roi_base,
    )


def plot_combo_pies(experiment, marker,
                    family='comboany',
                    by='conditions', factor=None,
                    start_angle=90, line_width=1.0,
                    save=True, specificity=None, roi=None,
                    plot_format='pie', show_counts=None, show_pct=None,
                    labels=None, order=None,
                    include_none=True,
                    collapse_markers=None,
                    include_N=False, as_counts=None, include_n=None,
                    bottom_ticks=False, bottom_tick_labels=False,
                    auto_style=True, style_cycle=None):
    """
    Pie or stacked-bar distributions for mutually exclusive combo families.

    `family` controls which per-object combo columns are used:
    - 'VolCombo': detailed volumetric coloc/contains combo family
    - 'VolComboAny': pooled volumetric Any-based combo family
    - 'CPCCombo': detailed CPC coloc/contains combo family
    - 'CPCComboAny': pooled CPC Any-based combo family

    Each object contributes to exactly one category, so the family partitions
    the marker population. `include_none=True` retains the explicit `None`
    category when present. `include_N=True` appends the number of
    contributing animals (unique AnimalName). `labels` remaps the final
    displayed combo signatures after any collapse. `order` controls category
    sequence clockwise from the top so the first ordered category sits on the
    top-right side of the pie. `as_counts/include_n` are backward-compatible
    aliases.
    """
    show_counts_flag, show_pct_flag = _resolve_pie_value_flags(
        show_counts=show_counts,
        show_pct=show_pct,
        as_counts=as_counts,
    )
    include_N_flag = _resolve_include_N_flag(include_N=include_N, include_n=include_n)
    order_norm = _normalize_pie_order(order)
    collapse_markers_norm = _normalize_combo_collapse_markers(collapse_markers)
    collapse_display_suffix = _combo_collapse_display_suffix(collapse_markers_norm)
    collapse_save_suffix = _combo_collapse_save_suffix(collapse_markers_norm)
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_combo_pies(
                experiment,
                marker,
                family=family,
                by=by,
                factor=factor,
                auto_style=auto_style, style_cycle=style_cycle,
                start_angle=start_angle,
                line_width=line_width,
                save=save,
                specificity=specificity,
                roi=_rb,
                plot_format=plot_format,
                show_counts=show_counts_flag,
                show_pct=show_pct_flag,
                labels=labels,
                order=order_norm,
                include_none=include_none,
                collapse_markers=collapse_markers_norm,
                include_N=include_N_flag,
                bottom_ticks=bottom_ticks,
                bottom_tick_labels=bottom_tick_labels,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    queue_types = (list, tuple, set, np.ndarray, pd.Series, pd.Index)
    marker_is_queue = isinstance(marker, queue_types) and not isinstance(marker, str)
    family_is_queue = isinstance(family, queue_types) and not isinstance(family, str)
    if marker_is_queue or family_is_queue:
        marker_values = _flatten_specificity_values([marker]) if marker_is_queue else [marker]
        family_values = _flatten_specificity_values([family]) if family_is_queue else [family]
        if len(marker_values) == 0 or len(family_values) == 0:
            raise ValueError("Queued marker/family inputs must contain at least one value.")
        queued_outputs = {}
        for m_val in marker_values:
            for fam_val in family_values:
                key = (m_val, fam_val)
                queued_outputs[key] = plot_combo_pies(
                    experiment,
                    marker=m_val,
                    family=fam_val,
                    auto_style=auto_style, style_cycle=style_cycle,
                    by=by,
                    factor=factor,
                    start_angle=start_angle,
                    line_width=line_width,
                    save=save,
                    specificity=specificity,
                    roi=roi,
                    plot_format=plot_format,
                    show_counts=show_counts_flag,
                    show_pct=show_pct_flag,
                    labels=labels,
                    order=order_norm,
                    include_none=include_none,
                    collapse_markers=collapse_markers_norm,
                    include_N=include_N_flag,
                    bottom_ticks=bottom_ticks,
                    bottom_tick_labels=bottom_tick_labels,
                )
        return queued_outputs

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_combo_pies(
                experiment,
                marker=marker,
                family=family,
                by=by,
                factor=factor,
                auto_style=auto_style, style_cycle=style_cycle,
                start_angle=start_angle,
                line_width=line_width,
                save=save,
                specificity=spec,
                roi=roi,
                plot_format=plot_format,
                show_counts=show_counts_flag,
                show_pct=show_pct_flag,
                labels=labels,
                order=order_norm,
                include_none=include_none,
                collapse_markers=collapse_markers_norm,
                include_N=include_N_flag,
                bottom_ticks=bottom_ticks,
                bottom_tick_labels=bottom_tick_labels,
            )
        return queued_outputs

    marker_key = _resolve_marker_data_key(experiment, marker)
    family_key, family_prefix = _normalize_combo_pie_family(family)
    level = 'factors' if factor else by
    total_groups = _count_level_processes(experiment, level, factor=factor, specificity=specificity)
    plot_mode = str(plot_format).strip().casefold()
    if plot_mode not in {"pie", "bar"}:
        raise ValueError("plot_format must be 'pie' or 'bar'.")
    combine_bar_mode = (plot_mode == "bar")
    use_count_scale = _pie_uses_count_scale(
        show_counts=show_counts_flag,
        show_pct=show_pct_flag,
    )

    try:
        start_angle_f = float(start_angle)
    except Exception as e:
        raise ValueError("start_angle must be numeric.") from e
    try:
        line_width_f = float(line_width)
    except Exception as e:
        raise ValueError("line_width must be numeric.") from e
    if line_width_f < 0:
        raise ValueError("line_width must be >= 0.")

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_combo_pies',
            total=total_groups,
        )
        _progress_start_item(state)
        if combine_bar_mode:
            if state.get('fig') is None or state.get('ax') is None:
                fig_w = max(1, int(max(1, total_groups))) * (2.0 / 3.0)
                fig, ax = plt.subplots(figsize=(fig_w, 5))
                state['fig'] = fig
                state['ax'] = ax
        else:
            fig, ax = plt.subplots(figsize=(8, 8))
            state['fig'] = fig
            state['ax'] = ax

    def teardown(
        ctx, state, results,
        _use_count_scale=use_count_scale,
        _include_N_flag=include_N_flag,
        _show_counts_flag=show_counts_flag,
        _show_pct_flag=show_pct_flag,
    ):
        fig = state['fig']
        name = ctx.factor_value or ctx.condition or 'Combined'
        subfolder, suffix = build_subfolder(
            plot_type='ComboPies',
            marker=marker_key,
            factor=factor,
            specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base,
            multi_roi=_multi_roi,
        )
        _progress_finish_item(state, name)

        if combine_bar_mode:
            prog = state.get('progress_state', {})
            is_last = int(prog.get('completed', 0)) >= int(prog.get('total', 1))
            if not is_last:
                return

            ax = state.get('ax')
            if ax is None:
                return
            ax.clear()

            group_order = state.get("pie_bar_group_order", [])
            group_counts = state.get("pie_bar_group_counts", {})
            group_colors = state.get("pie_bar_group_colors", {})
            group_styles = state.get("pie_bar_group_styles", {})
            group_n_animals = state.get("pie_bar_group_n_animals", {})
            category_order = state.get("pie_bar_category_order", [])
            category_pairs = state.get("pie_bar_category_pairs", [])
            if len(category_pairs) > 0:
                cat_raw = [pair[0] for pair in category_pairs]
                cat_display = [pair[1] for pair in category_pairs]
                _, category_order, _ = _apply_pie_order(
                    cat_raw,
                    cat_display,
                    [None] * len(cat_display),
                    order_norm,
                )
            else:
                category_order = _apply_requested_order(category_order, order_norm)

            if len(group_order) == 0 or len(category_order) == 0:
                ax.axis("off")
                ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            else:
                x_pos = np.arange(len(group_order), dtype=float)
                width = 0.5
                n_cat = max(1, len(category_order))
                max_stack_total = 0.0
                for i, g in enumerate(group_order):
                    g_counts = group_counts.get(g, {})
                    total = float(sum(float(v) for v in g_counts.values()))
                    max_stack_total = max(max_stack_total, total)
                    bottom = 0.0
                    g_color = group_colors.get(g, "black")
                    g_style = group_styles.get(g, "fill")
                    grad = _pie_gradient_colors(g_color, n_cat)
                    for j, cat in enumerate(category_order):
                        raw_val = float(g_counts.get(cat, 0.0))
                        val = raw_val if use_count_scale else ((raw_val / total) * 100.0 if total > 0 else 0.0)
                        if val <= 0:
                            continue
                        edgecolor = g_color if line_width_f > 0 else "none"
                        _stack_bars = ax.bar(
                            x_pos[i], val, width=width, bottom=bottom,
                            color=grad[j], edgecolor=edgecolor, linewidth=line_width_f,
                        )
                        # Second visual channel: hatch this group's stack when it
                        # shares a colour with another (matches the pie wedges).
                        if g_style and g_style != "fill":
                            _apply_pie_wedge_style(_stack_bars, g_style, g_color)
                        bottom += val

                ax.set_xticks(x_pos)
                ax.set_xticklabels(
                    [
                        _append_animal_n_multiline(
                            g,
                            n_animals=group_n_animals.get(g),
                            include_N=include_N_flag,
                        )
                        for g in group_order
                    ],
                    rotation=20,
                    ha="right",
                )
                _annotate_stacked_distribution(
                    ax,
                    x_pos,
                    group_order,
                    group_counts,
                    category_order,
                    show_counts=show_counts_flag,
                    show_pct=show_pct_flag,
                )
                ax.tick_params(
                    axis='x',
                    which='both',
                    bottom=bool(bottom_ticks),
                    top=False,
                    labelbottom=bool(bottom_tick_labels),
                )
                axis_label = f"{marker_key} {family_prefix}{collapse_display_suffix}".strip()
                scale_unit = "counts" if use_count_scale else "percent"
                ax.set_ylabel(f"{axis_label} ({scale_unit})")
                if use_count_scale:
                    ymax_bar = round_up_to_nearest_5(max_stack_total)
                    if ymax_bar > 0:
                        ax.set_ylim(0, ymax_bar)
                        ax.yaxis.set_major_locator(LinearLocator(numticks=5))
                else:
                    ax.set_ylim(0, 100)
                    ax.yaxis.set_major_locator(LinearLocator(numticks=5))
                ax.set_xlabel("")

                legend_colors = _pie_gradient_colors("black", n_cat)
                handles = [
                    plt.Rectangle((0, 0), 1, 1, facecolor=legend_colors[j], edgecolor="none")
                    for j in range(n_cat)
                ]
                ax.legend(handles, category_order, title=axis_label, frameon=False,
                          bbox_to_anchor=(1.02, 1.0), loc="upper left")
                sns.despine(trim=False, ax=ax)
                fig.tight_layout()

            if save:
                unit_tag = _pie_value_save_tag(
                    show_counts=show_counts_flag,
                    show_pct=show_pct_flag,
                )
                save_fig(
                    fig,
                    experiment.fig_path,
                    f'{marker_key} {family_prefix} Bar (Combined) {unit_tag}{collapse_save_suffix}' + suffix,
                    subfolder=subfolder,
                )
            plt.close(fig)
            return

        if save:
            unit_tag = _pie_value_save_tag(
                show_counts=show_counts_flag,
                show_pct=show_pct_flag,
            )
            save_fig(
                fig,
                experiment.fig_path,
                f'{marker_key} {family_prefix} Pie {name} {unit_tag}{collapse_save_suffix}' + suffix,
                subfolder=subfolder,
            )
        plt.close(fig)

    return run(
        experiment, over=level, action=combo_pie_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        marker=marker_key,
        family=family_key,
        include_none=bool(include_none),
        collapse_markers=collapse_markers_norm,
        start_angle=start_angle_f,
        line_width=line_width_f,
        plot_format=plot_mode,
        show_counts=bool(show_counts_flag),
        show_pct=bool(show_pct_flag),
        labels=labels,
        order=order_norm,
        include_N=bool(include_N_flag),
        specificity_filter=specificity,
        auto_style=auto_style, style_cycle=style_cycle,
        roi_base=_roi_base,
    )


def plot_matrices(experiment, filtered_columns=None,
                  by='conditions', factor=None,
                  correlation='pearsonr',
                  first_columns=None, tick_label_size=20,
                  marker=None, specificity=None, roi=None, save=True,
                  column_strings=None, regex_string=None, exclude='',
                  prefix_order=None, marker_order=None,
                  share_columns_across_panels=True):
    """
    Correlation matrix: one figure per condition or factor value.
    """
    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_matrices(
                experiment,
                filtered_columns=filtered_columns,
                by=by, factor=factor,
                correlation=correlation,
                first_columns=first_columns, tick_label_size=tick_label_size,
                marker=marker, specificity=specificity, roi=_rb, save=save,
                column_strings=column_strings, regex_string=regex_string, exclude=exclude,
                prefix_order=prefix_order, marker_order=marker_order,
                share_columns_across_panels=share_columns_across_panels,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_matrices(
                experiment,
                filtered_columns=filtered_columns,
                by=by,
                factor=factor,
                correlation=correlation,
                first_columns=first_columns,
                tick_label_size=tick_label_size,
                marker=marker,
                prefix_order=prefix_order,
                marker_order=marker_order,
                share_columns_across_panels=share_columns_across_panels,
                specificity=spec,
                roi=roi,
                save=save,
                column_strings=column_strings,
                regex_string=regex_string,
                exclude=exclude,
            )
        return queued_outputs

    corr_label = _correlation_filename_label(correlation)

    matrix_source_df = experiment.summary
    if marker is not None:
        marker_key = _resolve_marker_data_key(experiment, marker)
        matrix_source_df = experiment.data[marker_key].df

    resolved_columns = _resolve_filtered_columns(
        experiment,
        filtered_columns=filtered_columns,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=exclude,
        source_df=matrix_source_df,
    )

    level = 'factors' if factor else by

    def _matrix_panel_frames_for_shared_columns():
        summary_filtered = _filtered_summary_for_specificity(experiment, specificity)
        if marker is not None:
            marker_key = _resolve_marker_data_key(experiment, marker)
            source_df = experiment.data[marker_key].df.copy()
            source_df = _enrich_df_grouping_columns(
                source_df,
                experiment,
                requested_by=(factor if factor is not None else "Condition"),
            )
            source_df = _filter_df_by_specificity(source_df, specificity)
        else:
            source_df = summary_filtered

        panels = []
        if level == 'factors':
            if factor is None or factor not in source_df.columns:
                return panels
            vals = source_df[factor].dropna().unique().tolist()
            ordered = []
            for cond in experiment.condition_list:
                match = next((v for v in vals if str(v) in str(cond.name)), None)
                if match is not None and match not in ordered:
                    ordered.append(match)
            for v in vals:
                if v not in ordered:
                    ordered.append(v)
            for v in ordered:
                panel_df = source_df[source_df[factor] == v]
                if len(panel_df) > 0:
                    panels.append(panel_df)
            return panels

        if level == 'conditions':
            if "Condition" not in source_df.columns:
                source_df = _enrich_df_grouping_columns(source_df, experiment, requested_by="Condition")
            if "Condition" not in source_df.columns:
                return panels
            seen = set()
            for cond in experiment.condition_list:
                name = str(cond.name)
                panel_df = source_df[source_df["Condition"] == name]
                if len(panel_df) > 0:
                    panels.append(panel_df)
                    seen.add(name)
            extras = [
                str(v) for v in source_df["Condition"].dropna().unique().tolist()
                if str(v) not in seen
            ]
            for name in extras:
                panel_df = source_df[source_df["Condition"] == name]
                if len(panel_df) > 0:
                    panels.append(panel_df)
            return panels

        if len(source_df) > 0:
            panels.append(source_df)
        return panels

    if bool(share_columns_across_panels):
        panel_frames = _matrix_panel_frames_for_shared_columns()
        keep_sets = []
        for panel_df in panel_frames:
            _, keep_cols, _ = _prepare_matrix_numeric_df(
                panel_df,
                resolved_columns,
                drop_duplicate_columns=False,
                require_complete_numeric=True,
            )
            keep_sets.append(set(keep_cols))
        if len(keep_sets) > 0:
            shared_set = set.intersection(*keep_sets)
            shared_cols = [c for c in resolved_columns if c in shared_set]
            resolved_columns = shared_cols
            if len(resolved_columns) == 0:
                _log.warn("[plot_matrices] No shared valid columns across panels after NaN/sentinel filtering.")

    n = len(resolved_columns)
    fig_w = min(max(6.0, n * 0.35), 30.0)
    fig_h = min(max(5.4, n * 0.315), 27.0)
    tick_label_size_eff = min(tick_label_size, max(4, int(300 / max(1, n))))
    drop_duplicate_columns_for_action = not bool(share_columns_across_panels)

    _matrix_shared_fig_ref = {"fig": None}

    def setup(ctx, state):
        _init_progress_state(
            state,
            func_name='plot_matrices',
            total=_count_level_processes(experiment, level, factor=factor, specificity=specificity),
        )
        _progress_start_item(state)
        if 'shared_fig' not in state or 'shared_ax' not in state:
            fig, ax = plt.subplots(figsize=(fig_w, fig_h))
            state['shared_fig'] = fig
            state['shared_ax'] = ax
            _matrix_shared_fig_ref["fig"] = fig
        else:
            fig = state['shared_fig']
            ax = state['shared_ax']
            ax.clear()
        state['fig'] = fig
        state['ax'] = ax

    def teardown(ctx, state, results):
        fig = state['fig']
        name = ctx.factor_value or ctx.condition or 'Combined'
        subfolder, suffix = build_subfolder(
            plot_type='Matrices',
            factor=factor if factor is not None else str(by).rstrip('s'),
            specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        if save:
            title = f'{name} {corr_label} Correlation Matrix'
            if marker is not None:
                title = f'{marker} {title}'
            save_fig(fig, experiment.fig_path, title + suffix, subfolder=subfolder)
        _progress_finish_item(state, name)

    result = run(
        experiment, over=level, action=matrix_action,
        factor=factor, specificity=specificity,
        setup=setup, teardown=teardown,
        filtered_columns=resolved_columns,
        correlation=correlation, first_columns=first_columns,
        tick_label_size=tick_label_size_eff, marker=marker,
        prefix_order=prefix_order, marker_order=marker_order,
        drop_duplicate_columns=drop_duplicate_columns_for_action,
        enforce_shared_columns=bool(share_columns_across_panels),
        shared_columns=resolved_columns,
        specificity_filter=specificity,
        roi_base=_roi_base,
    )
    if _matrix_shared_fig_ref.get("fig") is not None:
        plt.close(_matrix_shared_fig_ref["fig"])
    try:
        if Config.EXPORT_HTML:
            subfolder_html, _ = build_subfolder(
                plot_type='Matrices',
                factor=factor if factor is not None else str(by).rstrip('s'),
                specificity=specificity,
                aliases=getattr(experiment, 'aliases', None),
                roi_base=_roi_base, multi_roi=_multi_roi,
            )
            html_save_path = os.path.join(experiment.fig_path, subfolder_html) if subfolder_html else experiment.fig_path
            _export_html_matrix(experiment, resolved_columns, specificity, html_save_path, by, factor, correlation)
    except Exception:
        pass
    return result


# ── Correlation pipeline ───────────────────────────────────────────────
# Matrix (per method) → FDR/p significance gate (AND/OR) → regression plots
# for the surviving pairs, all written into one self-contained run folder.

_CORR_METHOD_SHORT = {"pearsonr": "P", "spearmanr": "S", "kendalltau": "K"}


def _corr_pipeline_use_fdr(gate):
    """True when the gate selects on FDR q-values rather than raw p-values."""
    return str(gate).strip().lower() in (
        "fdr", "q", "qvalue", "q_value", "q-value", "fdr_bh", "bh"
    )


# ── Pipeline run-folder / manifest I/O ───────────────────────────────────────
# Canonical implementation lives in PyFLASH.pipeline_io; these thin wrappers keep
# the historical _corr_* names while delegating to that single shared version, so
# the correlation / adjusted / overview pipelines resolve run folders, slugs, and
# the runs index identically (and Windows long-path safely).
from PyFLASH import pipeline_io as _pio

_corr_windows_extended_path = _pio.windows_extended_path
_corr_makedirs = _pio.makedirs
_corr_isfile = _pio.isfile
_corr_isdir = _pio.isdir
_corr_clear_run_dir = _pio.clear_run_dir
_corr_to_csv = _pio.to_csv
_corr_write_json = _pio.write_json
_corr_read_json = _pio.read_json
_corr_pipeline_data_root = _pio.data_root


def _corr_pipeline_slug(columns, against_columns, methods, require, gate, alpha,
                        by, factor, specificity, roi):
    """Deterministic short run name derived from the configuration."""
    payload = {
        "cols": sorted(str(c) for c in columns),
        "against": sorted(str(c) for c in (against_columns or [])),
        "tests": list(methods),
        "require": str(require).lower(),
        "gate": str(gate).lower(),
        "alpha": float(alpha),
        "by": str(by),
        "factor": str(factor),
        "specificity": str(specificity),
        "roi": str(roi),
    }
    short = "".join(_CORR_METHOD_SHORT.get(m, "?") for m in methods)
    return _pio.slug(f"{len(columns)}cols_{short}_{str(gate).lower()}", payload)


def _corr_pipeline_run_dirs(experiment, run_label, if_exists, *, clear_overwrite=True):
    """Return (fig_dir, data_dir, resolved_label, reuse_existing) for a correlation run."""
    return _pio.run_dirs(experiment, "Correlation Pipeline", run_label, if_exists,
                         clear_overwrite=clear_overwrite)


def _corr_pipeline_groups(experiment, scope_df, num_df, by, factor, specificity):
    """Yield (group_label, row_index, regression_specificity) for paneling.

    ``by='all'`` (default) is a single pooled group; ``factor`` panels by factor
    level; ``by='conditions'`` panels by condition. The regression specificity
    scopes the per-group regression rows when the user has not already pinned a
    specificity.
    """
    pooled = [("All", num_df.index, specificity)]
    if factor:
        enriched = _enrich_df_grouping_columns(scope_df, experiment, requested_by=factor)
        if factor not in enriched.columns:
            return pooled
        groups = []
        vals = enriched[factor].dropna().unique().tolist()
        ordered_vals = []
        factor_dict = getattr(getattr(experiment, "condition_list", None), "factorDict", {})
        for cond in factor_dict.get(factor, []):
            name = getattr(cond, "name", None)
            match = next((v for v in vals if str(v) == str(name)), None)
            if match is not None and match not in ordered_vals:
                ordered_vals.append(match)
        for v in vals:
            if v not in ordered_vals:
                ordered_vals.append(v)
        for v in ordered_vals:
            idx = num_df.index.intersection(enriched.index[enriched[factor] == v])
            if len(idx) > 0:
                reg_spec = specificity if specificity is not None else (factor, v)
                groups.append((str(v), idx, reg_spec))
        return groups or pooled
    if str(by).strip().lower() == "conditions":
        enriched = _enrich_df_grouping_columns(scope_df, experiment, requested_by="Condition")
        if "Condition" not in enriched.columns:
            return pooled
        groups = []
        for cond in getattr(experiment, "condition_list", []):
            name = str(cond.name)
            idx = num_df.index.intersection(enriched.index[enriched["Condition"] == name])
            if len(idx) > 0:
                reg_spec = specificity if specificity is not None else ("Condition", name)
                groups.append((name, idx, reg_spec))
        return groups or pooled
    return pooled


def _corr_pipeline_compute(num_df, row_cols, col_cols, methods,
                           gate, alpha, require, min_n, square):
    """Pairwise correlations across methods + FDR + AND/OR gate.

    ``num_df`` is already numeric (sentinels/NaN coerced). Returns long-form
    rows, per-method square/rectangular matrices (coef/p/q/significance), a gate
    matrix, and a ranked selected-pair frame.
    """
    from PyFLASH.stats_extra import apply_fdr

    use_fdr = _corr_pipeline_use_fdr(gate)
    require_all = str(require).strip().lower() == "and"
    row_cols = list(row_cols)
    mcols = list(row_cols) if square else list(col_cols)

    if square:
        pairs = [(row_cols[i], row_cols[j])
                 for i in range(len(row_cols)) for j in range(i + 1, len(row_cols))]
    else:
        pairs = [(a, b) for a in row_cols for b in col_cols if a != b]

    stat = {m: {} for m in methods}            # (x, y) -> (n, r, p)
    for m in methods:
        for x, y in pairs:
            sub = num_df[[x, y]].dropna()
            n = int(len(sub))
            if n < int(min_n) or sub[x].nunique() < 2 or sub[y].nunique() < 2:
                stat[m][(x, y)] = (n, np.nan, np.nan)
                continue
            try:
                r, p = _compute_correlation(sub[x].to_numpy(), sub[y].to_numpy(), m)
            except Exception:
                r, p = np.nan, np.nan
            stat[m][(x, y)] = (n, r, p)

    qval = {m: {} for m in methods}
    for m in methods:
        labels = [pr for pr in pairs if np.isfinite(stat[m][pr][2])]
        if labels:
            adjusted = apply_fdr(
                [stat[m][pr][2] for pr in labels], alpha=alpha
            )["p_adjusted"].tolist()
            for pr, q in zip(labels, adjusted):
                qval[m][pr] = float(q)

    rows, selected, pass_pairs = [], [], set()
    for x, y in pairs:
        sig_count, abs_rs = 0, []
        for m in methods:
            n, r, p = stat[m][(x, y)]
            q = qval[m].get((x, y), np.nan)
            sig_p = bool(np.isfinite(p) and p < alpha)
            sig_q = bool(np.isfinite(q) and q < alpha)
            sig = sig_q if use_fdr else sig_p
            sig_count += int(sig)
            if np.isfinite(r):
                abs_rs.append(abs(float(r)))
            rows.append({
                "x": x, "y": y,
                "x_label": get_display_name(x, minimal=True),
                "y_label": get_display_name(y, minimal=True),
                "method": _correlation_display_name(m),
                "n": n, "r": r, "p": p, "q": q,
                "sig_p": sig_p, "sig_q": sig_q, "passes": sig,
            })
        passed = (sig_count == len(methods)) if require_all else (sig_count > 0)
        if passed:
            pass_pairs.add((x, y))
            selected.append({
                "x": x, "y": y,
                "x_label": get_display_name(x, minimal=True),
                "y_label": get_display_name(y, minimal=True),
                "n_methods_sig": sig_count,
                "median_abs_r": float(np.median(abs_rs)) if abs_rs else np.nan,
            })

    long_df = pd.DataFrame(rows)
    sel_cols = ["x", "y", "x_label", "y_label", "n_methods_sig", "median_abs_r"]
    if selected:
        sel_df = pd.DataFrame(selected).sort_values(
            "median_abs_r", ascending=False, na_position="last"
        ).reset_index(drop=True)
    else:
        sel_df = pd.DataFrame(columns=sel_cols)

    coef, pmat, qmat, sigmat = {}, {}, {}, {}
    for m in methods:
        c = pd.DataFrame(np.nan, index=list(row_cols), columns=mcols, dtype=float)
        pm = c.copy()
        qm = c.copy()
        sg = pd.DataFrame(False, index=list(row_cols), columns=mcols)
        if square:
            for col in row_cols:
                c.loc[col, col] = 1.0
        for x, y in pairs:
            n, r, p = stat[m][(x, y)]
            q = qval[m].get((x, y), np.nan)
            sig = (np.isfinite(q) and q < alpha) if use_fdr else (np.isfinite(p) and p < alpha)
            c.loc[x, y] = r
            pm.loc[x, y] = p
            qm.loc[x, y] = q
            sg.loc[x, y] = bool(sig)
            if square:
                c.loc[y, x] = r
                pm.loc[y, x] = p
                qm.loc[y, x] = q
                sg.loc[y, x] = bool(sig)
        coef[m], pmat[m], qmat[m], sigmat[m] = c, pm, qm, sg

    gate_mat = pd.DataFrame(False, index=list(row_cols), columns=mcols)
    for x, y in pass_pairs:
        gate_mat.loc[x, y] = True
        if square:
            gate_mat.loc[y, x] = True

    return {
        "long": long_df, "selected": sel_df,
        "coef": coef, "p": pmat, "q": qmat, "sig": sigmat,
        "gate": gate_mat, "pairs": pairs,
    }


def _corr_pipeline_sig_from_values(value_df, alpha):
    """Boolean matrix where finite p/q values pass ``alpha``."""
    numeric = value_df.apply(lambda s: pd.to_numeric(s, errors="coerce"))
    return numeric.lt(float(alpha)).fillna(False)


def _corr_difference_use_fdr(gate):
    return str(gate).strip().lower() in ("fdr", "q", "qvalue", "q_value", "q-value", "fdr_bh", "bh")


def _normal_sf(x):
    """Standard normal survival function without requiring scipy."""
    import math
    return 0.5 * math.erfc(float(x) / math.sqrt(2.0))


def _corr_fisher_z_pvalue(r1, n1, r2, n2):
    """Two-sided independent-correlation Fisher r-to-z p-value."""
    if (
        not np.isfinite(r1) or not np.isfinite(r2)
        or int(n1) <= 3 or int(n2) <= 3
        or abs(float(r1)) >= 1.0 or abs(float(r2)) >= 1.0
    ):
        return np.nan
    se = np.sqrt((1.0 / (int(n1) - 3)) + (1.0 / (int(n2) - 3)))
    if not np.isfinite(se) or se <= 0:
        return np.nan
    z = (np.arctanh(float(r1)) - np.arctanh(float(r2))) / se
    return float(2.0 * _normal_sf(abs(z)))


def _corr_group_result_dict(groups_results):
    """Map group labels to computed correlation result payloads."""
    out = {}
    for item in groups_results or []:
        label = str(item.get("group", ""))
        if label:
            out[label] = item.get("result")
    return out


def _corr_pair_label_lookup(experiment, groups_results):
    """Map existing group labels and 1-based comparison indices to labels."""
    labels = [str(item.get("group", "")) for item in groups_results or []]
    lookup = {label.casefold(): label for label in labels if label}
    for i, label in enumerate(labels, start=1):
        if label:
            lookup[str(i)] = label
    return lookup


def _corr_default_difference_comparisons(experiment, groups_results, *,
                                         prefer_condition_comparisons=False):
    """Prefer conditionList comparisons, otherwise all observed group pairs."""
    comparisons = getattr(getattr(experiment, "condition_list", None), "comparisons", None)
    if prefer_condition_comparisons and comparisons:
        return list(comparisons)
    labels = [str(item.get("group", "")) for item in groups_results or [] if item.get("group")]
    return [(labels[i], labels[j])
            for i in range(len(labels)) for j in range(i + 1, len(labels))]


def _corr_resolve_difference_comparisons(experiment, groups_results, comparisons=None, *,
                                         prefer_condition_comparisons=False):
    """Return ``[(left_label, right_label, comparison_label), ...]``."""
    specs = _corr_default_difference_comparisons(
        experiment, groups_results,
        prefer_condition_comparisons=prefer_condition_comparisons,
    ) if comparisons is None else comparisons
    if specs in (False, [], (), ""):
        return []
    if isinstance(specs, str):
        specs = [specs]
    lookup = _corr_pair_label_lookup(experiment, groups_results)
    resolved = []
    for spec in specs:
        left = right = None
        if isinstance(spec, str):
            token = spec.strip()
            if "-" in token and " vs " not in token.lower():
                parts = [p.strip() for p in token.split("-", 1)]
            elif " vs " in token.lower():
                lower = token.lower()
                pos = lower.find(" vs ")
                parts = [token[:pos].strip(), token[pos + 4:].strip()]
            else:
                raise ValueError(f"Invalid matrix difference comparison {spec!r}.")
            left = lookup.get(parts[0].casefold(), lookup.get(parts[0]))
            right = lookup.get(parts[1].casefold(), lookup.get(parts[1]))
        elif isinstance(spec, (list, tuple)) and len(spec) >= 2:
            left = lookup.get(str(spec[0]).casefold(), lookup.get(str(spec[0])))
            right = lookup.get(str(spec[1]).casefold(), lookup.get(str(spec[1])))
        if left is None or right is None:
            valid = ", ".join([k for k in lookup.keys() if not str(k).isdigit()])
            raise ValueError(
                f"Could not resolve matrix difference comparison {spec!r}. "
                f"Available groups: {valid}."
            )
        resolved.append((left, right, f"{left} vs {right}"))
    return resolved


def _corr_comparison_pairs(index_labels, column_labels, square):
    if square:
        return [
            (index_labels[i], index_labels[j])
            for i in range(len(index_labels))
            for j in range(i + 1, len(index_labels))
        ]
    return [(x, y) for x in index_labels for y in column_labels if x != y]


def _corr_result_pair_lookup(result, method):
    long_df = result.get("long") if isinstance(result, dict) else None
    if not isinstance(long_df, pd.DataFrame) or long_df.empty:
        return {}
    method_name = _correlation_display_name(method)
    sub = long_df[long_df["method"].astype(str) == method_name]
    return {
        (row["x"], row["y"]): (row.get("n", np.nan), row.get("r", np.nan))
        for _, row in sub.iterrows()
    }


def _corr_compute_difference_payload(left_result, right_result, methods, *,
                                     alpha=0.05, gate="fdr",
                                     test="fisher_z"):
    """Compare two computed correlation-result payloads cell by cell."""
    from PyFLASH.stats_extra import apply_fdr

    use_fdr = _corr_difference_use_fdr(gate)
    methods = [_normalize_correlation_method(m)
               for m in ([methods] if isinstance(methods, str) else list(methods))]
    output = {"methods": {}, "long": pd.DataFrame()}
    long_rows = []

    for method in methods:
        left_coef = left_result["coef"][method]
        right_coef = right_result["coef"][method]
        idx = list(left_coef.index)
        cols = list(left_coef.columns)
        square = idx == cols
        signed = left_coef.astype(float) - right_coef.astype(float)
        absolute = signed.abs()
        pmat = pd.DataFrame(np.nan, index=idx, columns=cols, dtype=float)
        qmat = pmat.copy()
        sig = pd.DataFrame(False, index=idx, columns=cols)

        pair_lookup_left = _corr_result_pair_lookup(left_result, method)
        pair_lookup_right = _corr_result_pair_lookup(right_result, method)
        p_labels, p_values = [], []
        inferential = (
            str(test).strip().lower() in ("fisher_z", "fisher", "z")
            and method == "pearsonr"
        )
        for x, y in _corr_comparison_pairs(idx, cols, square):
            n1, r1 = pair_lookup_left.get((x, y), pair_lookup_left.get((y, x), (np.nan, np.nan)))
            n2, r2 = pair_lookup_right.get((x, y), pair_lookup_right.get((y, x), (np.nan, np.nan)))
            p = _corr_fisher_z_pvalue(r1, n1, r2, n2) if inferential else np.nan
            pmat.loc[x, y] = p
            if square:
                pmat.loc[y, x] = p
            if np.isfinite(p):
                p_labels.append((x, y))
                p_values.append(float(p))

        if p_values:
            adjusted = apply_fdr(p_values, alpha=alpha)["p_adjusted"].tolist()
            for (x, y), q in zip(p_labels, adjusted):
                qmat.loc[x, y] = float(q)
                if square:
                    qmat.loc[y, x] = float(q)
        gate_values = qmat if use_fdr else pmat
        sig = _corr_pipeline_sig_from_values(gate_values, alpha)

        for x, y in _corr_comparison_pairs(idx, cols, square):
            long_rows.append({
                "x": x, "y": y,
                "x_label": get_display_name(x, minimal=True),
                "y_label": get_display_name(y, minimal=True),
                "method": _correlation_display_name(method),
                "r_left": left_coef.loc[x, y],
                "r_right": right_coef.loc[x, y],
                "signed_delta": signed.loc[x, y],
                "absolute_delta": absolute.loc[x, y],
                "p": pmat.loc[x, y],
                "q": qmat.loc[x, y],
                "passes": bool(sig.loc[x, y]),
                "difference_test": "Fisher z" if inferential else "descriptive_only",
            })

        output["methods"][method] = {
            "signed": signed,
            "absolute": absolute,
            "p": pmat,
            "q": qmat,
            "sig": sig,
            "inferential": inferential,
        }

    output["long"] = pd.DataFrame(long_rows)
    return output


def _corr_difference_matrix_fig(matrix, title, tick_label_size, *,
                                kind="signed", sig_df=None, alpha=0.05):
    if kind == "signed":
        return _corr_pipeline_heatmap(
            matrix, sig_df, title, tick_label_size,
            cmap="coolwarm", vmin=-2.0, vmax=2.0,
            colorbar_label="delta r",
        )
    if kind == "absolute":
        return _corr_pipeline_heatmap(
            matrix, sig_df, title, tick_label_size,
            cmap="magma", vmin=0.0, vmax=2.0,
            colorbar_label="absolute delta r",
        )
    if kind == "p":
        return _corr_pipeline_heatmap(
            matrix, _corr_pipeline_sig_from_values(matrix, alpha), title,
            tick_label_size, cmap="viridis_r", vmin=0.0, vmax=1.0,
            colorbar_label="difference p value",
        )
    if kind == "q":
        return _corr_pipeline_heatmap(
            matrix, _corr_pipeline_sig_from_values(matrix, alpha), title,
            tick_label_size, cmap="viridis_r", vmin=0.0, vmax=1.0,
            colorbar_label="difference FDR q value",
        )
    if kind == "gate":
        return _corr_pipeline_heatmap(
            matrix.astype(float), matrix, title, tick_label_size,
            cmap="Reds", vmin=0.0, vmax=1.0,
            colorbar_label="passes difference gate",
        )
    raise ValueError(f"Unknown matrix difference kind {kind!r}.")


def _corr_matrix_difference_label(methods, comparisons, factor, by):
    method_bits = "".join(_CORR_METHOD_SHORT.get(m, m[:1].upper()) for m in methods)
    comp_bits = f"{len(comparisons)}comparisons"
    group_bits = str(factor or by or "groups")
    return strip_name(f"matrix_differences_{group_bits}_{method_bits}_{comp_bits}") or "matrix_differences"


def _corr_render_matrix_differences(
    experiment,
    groups_results,
    methods,
    *,
    comparisons=None,
    prefer_condition_comparisons=False,
    fig_dir=None,
    data_dir=None,
    save=True,
    tick_label_size=20,
    alpha=0.05,
    gate="fdr",
    test="fisher_z",
    plot_signed=True,
    plot_absolute=True,
    plot_pvalue_matrices=True,
    plot_qvalue_matrices=True,
    plot_gate_matrix=True,
):
    """Render/save pairwise matrix differences from already-computed groups."""
    def _write_csv(frame, path, **kwargs):
        _corr_to_csv(frame, path, **kwargs)

    def _csv_path(directory, preferred_name, compact_name):
        path = os.path.join(directory, preferred_name)
        if os.name == "nt" and len(path) >= 248:
            return os.path.join(directory, compact_name)
        return path

    def _comparison_folder(label, data_root=None, fig_root=None):
        preferred = strip_name(label) or "comparison"
        if os.name != "nt":
            return preferred
        digest = hashlib.sha1(str(label).encode("utf-8")).hexdigest()[:10]
        compact = f"cmp_{digest}"
        checks = []
        if data_root:
            checks.append(os.path.join(data_root, preferred, "p_Pearson.csv"))
        if fig_root:
            checks.append(os.path.join(
                fig_root, preferred, "Matrices",
                f"{strip_name('Pearson Q Matrix')}.svg",
            ))
        return compact if any(len(path) >= 248 for path in checks) else preferred

    def _fig_target(root, comp_safe, preferred_name, compact_name):
        subfolder = os.path.join(comp_safe, "Matrices")
        name = preferred_name
        path = os.path.join(root, subfolder, f"{strip_name(name)}.svg")
        if os.name == "nt" and len(path) >= 248:
            name = compact_name
            path = os.path.join(root, subfolder, f"{strip_name(name)}.svg")
        if os.name == "nt" and len(path) >= 248:
            subfolder = os.path.join(comp_safe, "M")
        return name, subfolder

    methods = [_normalize_correlation_method(m)
               for m in ([methods] if isinstance(methods, str) else list(methods))]
    comparisons_resolved = _corr_resolve_difference_comparisons(
        experiment,
        groups_results,
        comparisons=comparisons,
        prefer_condition_comparisons=prefer_condition_comparisons,
    )
    group_map = _corr_group_result_dict(groups_results)
    if len(comparisons_resolved) == 0:
        return {
            "comparisons": [],
            "long": pd.DataFrame(),
            "n_comparisons": 0,
            "n_difference_tests": 0,
            "n_difference_significant": 0,
        }

    all_long = []
    summaries = []
    for left_label, right_label, comp_label in comparisons_resolved:
        left_res = group_map[left_label]
        right_res = group_map[right_label]
        payload = _corr_compute_difference_payload(
            left_res, right_res, methods,
            alpha=alpha, gate=gate, test=test,
        )
        comp_safe = _comparison_folder(comp_label, data_dir, fig_dir)
        comp_data_dir = os.path.join(data_dir, comp_safe) if data_dir else None

        long_df = payload["long"].copy()
        if not long_df.empty:
            long_df.insert(0, "comparison", comp_label)
            long_df.insert(1, "left_group", left_label)
            long_df.insert(2, "right_group", right_label)
            all_long.append(long_df)
            if save and comp_data_dir:
                _write_csv(
                    long_df,
                    _csv_path(comp_data_dir, "matrix_differences.csv", "diffs.csv"),
                    index=False,
                )

        comp_summary = {
            "comparison": comp_label,
            "left_group": left_label,
            "right_group": right_label,
            "methods": [],
        }

        for method in methods:
            disp = _correlation_display_name(method)
            mres = payload["methods"][method]
            inferential = bool(mres.get("inferential"))
            n_sig = int(np.nansum(mres["sig"].to_numpy(dtype=bool))) // (2 if list(mres["sig"].index) == list(mres["sig"].columns) else 1)
            comp_summary["methods"].append({
                "method": disp,
                "inferential": inferential,
                "n_significant": n_sig,
            })
            if save and comp_data_dir:
                _write_csv(mres["signed"], _csv_path(comp_data_dir, f"signed_delta_{disp}.csv", f"signed_{disp}.csv"))
                _write_csv(mres["absolute"], _csv_path(comp_data_dir, f"absolute_delta_{disp}.csv", f"abs_{disp}.csv"))
                if inferential:
                    _write_csv(mres["p"], _csv_path(comp_data_dir, f"pvalues_difference_{disp}.csv", f"p_{disp}.csv"))
                    _write_csv(mres["q"], _csv_path(comp_data_dir, f"qvalues_difference_{disp}.csv", f"q_{disp}.csv"))
                    _write_csv(mres["sig"].astype(int), _csv_path(comp_data_dir, f"gate_difference_{disp}.csv", f"gate_{disp}.csv"))

            if save and fig_dir:
                if plot_signed:
                    sfig = _corr_difference_matrix_fig(
                        mres["signed"], f"{disp} signed correlation difference\n{comp_label}: left - right",
                        tick_label_size, kind="signed",
                        sig_df=mres["sig"] if inferential else None, alpha=alpha,
                    )
                    fig_name, fig_sub = _fig_target(
                        fig_dir, comp_safe,
                        f"{disp} Signed Difference Matrix",
                        f"{disp} Signed Delta",
                    )
                    save_fig(sfig, fig_dir, fig_name, subfolder=fig_sub)
                    plt.close(sfig)
                if plot_absolute:
                    afig = _corr_difference_matrix_fig(
                        mres["absolute"], f"{disp} absolute correlation difference\n{comp_label}: |left - right|",
                        tick_label_size, kind="absolute",
                        sig_df=mres["sig"] if inferential else None, alpha=alpha,
                    )
                    fig_name, fig_sub = _fig_target(
                        fig_dir, comp_safe,
                        f"{disp} Absolute Difference Matrix",
                        f"{disp} Abs Delta",
                    )
                    save_fig(afig, fig_dir, fig_name, subfolder=fig_sub)
                    plt.close(afig)
                if inferential and plot_pvalue_matrices:
                    pfig = _corr_difference_matrix_fig(
                        mres["p"], f"{disp} correlation-difference P-Value Matrix\n{comp_label} (* p<{alpha:g})",
                        tick_label_size, kind="p", alpha=alpha,
                    )
                    fig_name, fig_sub = _fig_target(
                        fig_dir, comp_safe,
                        f"{disp} Difference P-Value Matrix",
                        f"{disp} P Matrix",
                    )
                    save_fig(pfig, fig_dir, fig_name, subfolder=fig_sub)
                    plt.close(pfig)
                if inferential and plot_qvalue_matrices:
                    qfig = _corr_difference_matrix_fig(
                        mres["q"], f"{disp} correlation-difference FDR Q-Value Matrix\n{comp_label} (* q<{alpha:g})",
                        tick_label_size, kind="q", alpha=alpha,
                    )
                    fig_name, fig_sub = _fig_target(
                        fig_dir, comp_safe,
                        f"{disp} Difference FDR Q-Value Matrix",
                        f"{disp} Q Matrix",
                    )
                    save_fig(qfig, fig_dir, fig_name, subfolder=fig_sub)
                    plt.close(qfig)
                if inferential and plot_gate_matrix:
                    gfig = _corr_difference_matrix_fig(
                        mres["sig"], f"{disp} correlation-difference gate\n{comp_label} @ {'q' if _corr_difference_use_fdr(gate) else 'p'}<{alpha:g}",
                        tick_label_size, kind="gate", alpha=alpha,
                    )
                    fig_name, fig_sub = _fig_target(
                        fig_dir, comp_safe,
                        f"{disp} Difference Gate Matrix",
                        f"{disp} Gate Matrix",
                    )
                    save_fig(gfig, fig_dir, fig_name, subfolder=fig_sub)
                    plt.close(gfig)
        summaries.append(comp_summary)

    combined_long = pd.concat(all_long, ignore_index=True) if all_long else pd.DataFrame()
    if save and data_dir:
        _write_csv(combined_long, os.path.join(data_dir, "matrix_differences.csv"), index=False)

    n_tests = int(combined_long["p"].notna().sum()) if "p" in combined_long else 0
    n_sig = int(combined_long["passes"].sum()) if "passes" in combined_long else 0
    return {
        "comparisons": summaries,
        "long": combined_long,
        "n_comparisons": len(summaries),
        "n_difference_tests": n_tests,
        "n_difference_significant": n_sig,
    }


def _corr_pipeline_heatmap(value_df, sig_df, title, tick_label_size, *,
                           cmap="coolwarm", vmin=-1.0, vmax=1.0,
                           colorbar_label=None):
    """Render a pipeline matrix using the same visual language as plot_matrices."""
    ycols = list(value_df.index)
    xcols = list(value_df.columns)
    ny, nx = len(ycols), len(xcols)
    n = max(nx, ny, 1)
    fig_w = min(max(7.0, nx * 0.42), 30.0)
    fig_h = min(max(6.2, ny * 0.38), 27.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    matrix = value_df.apply(lambda s: pd.to_numeric(s, errors="coerce"))
    tick_fs = max(7, min(int(tick_label_size), int(130 / n)))
    star_fs = min(25, max(8, int(220 / n)))

    heatmap = sns.heatmap(
        matrix, annot=False, fmt=".2f", cmap=cmap,
        linewidths=0.5, ax=ax, vmin=vmin, vmax=vmax,
    )
    try:
        cbar = heatmap.collections[0].colorbar
        cbar_tick_fs = max(8, min(12, int(tick_fs * 1.1)))
        cbar_label_fs = max(9, min(13, int(tick_fs * 1.15)))
        cbar.ax.tick_params(labelsize=cbar_tick_fs, width=1.2, length=5)
        if colorbar_label:
            cbar.ax.text(
                1.02, 1.05, colorbar_label,
                transform=cbar.ax.transAxes,
                ha="left", va="bottom",
                fontsize=cbar_label_fs,
                fontweight="bold",
            )
    except Exception:
        pass

    if sig_df is not None:
        sig = sig_df.reindex(index=ycols, columns=xcols).fillna(False).to_numpy()
        for i in range(ny):
            for j in range(nx):
                if bool(sig[i, j]):
                    ax.text(j + 0.5, i + 0.6, "*", ha="center", va="center",
                            fontsize=star_fs, color="black", fontweight="bold")

    labels_x = [get_display_name(c, minimal=True) for c in xcols]
    labels_y = [get_display_name(c, minimal=True) for c in ycols]
    tick_pos_x = np.arange(nx, dtype=float) + 0.5
    tick_pos_y = np.arange(ny, dtype=float) + 0.5
    ax.set_xticks(tick_pos_x)
    ax.set_yticks(tick_pos_y)
    ax.set_xticklabels(
        labels_x, rotation=60, ha="right", va="top",
        rotation_mode="anchor", fontsize=tick_fs,
    )
    ax.set_yticklabels(labels_y, rotation=0, ha="right", fontsize=tick_fs)
    ax.set_title(title, fontsize=int(tick_label_size))
    max_x_len = max([len(str(label)) for label in labels_x] or [1])
    max_y_len = max([len(str(label)) for label in labels_y] or [1])
    left = min(0.42, max(0.20, 0.08 + max_y_len * 0.0065))
    bottom = min(0.42, max(0.22, 0.08 + max_x_len * 0.008))
    fig.subplots_adjust(left=left, bottom=bottom, right=0.86, top=0.88)
    return fig


def _corr_pipeline_append_runs_index(experiment, manifest):
    """Append one summary row per run to a shared index CSV (overwrite by label)."""
    row = {
        "run_label": manifest["run_label"],
        "n_rows": manifest["n_rows"],
        "n_columns": len(manifest["columns"]),
        "tests": "/".join(manifest["tests"]),
        "require": manifest["require"],
        "gate": manifest["gate"],
        "alpha": manifest["alpha"],
        "by": manifest["by"],
        "factor": manifest["factor"],
        "specificity": manifest["specificity"],
        "roi": manifest["roi"],
        "n_pairs": manifest["n_pairs"],
        "n_selected": manifest["n_selected"],
        "n_regressions": manifest["n_regressions"],
        "n_difference_comparisons": (manifest.get("difference_matrices") or {}).get("n_comparisons", 0),
        "n_difference_significant": (manifest.get("difference_matrices") or {}).get("n_difference_significant", 0),
        "fig_dir": manifest["fig_dir"],
    }
    _pio.append_runs_index(experiment, "Correlation Pipeline", row)


def plot_matrix_differences(
    experiment,
    filtered_columns=None,
    against_columns=None,
    by="conditions",
    factor=None,
    comparisons=None,
    specificity=None,
    roi=None,
    save=True,
    column_strings=None,
    regex_string=None,
    exclude="",
    against_column_strings=None,
    against_regex_string=None,
    against_exclude="",
    correlation="pearsonr",
    alpha=0.05,
    min_n=3,
    difference_gate="fdr",
    difference_test="fisher_z",
    plot_signed=True,
    plot_absolute=True,
    plot_pvalue_matrices=True,
    plot_qvalue_matrices=True,
    plot_gate_matrix=True,
    tick_label_size=20,
    run_label=None,
):
    """Compare correlation matrices between conditions/factor groups.

    For each requested comparison, this computes each group's correlation
    matrix, then plots ``r_left - r_right`` and ``abs(r_left - r_right)`` cell
    by cell. Pearson matrices also get an independent-groups Fisher r-to-z
    difference test by default, saved as p-value, FDR q-value, and gate
    matrices. Spearman/Kendall difference matrices are descriptive unless a
    future test backend is added.
    """
    methods = [_normalize_correlation_method(t)
               for t in ([correlation] if isinstance(correlation, str) else list(correlation))]
    if not methods:
        raise ValueError("correlation must name at least one method.")

    _roi_base = _resolve_roi_bases(roi, experiment)[0]
    scope_df = _filtered_summary_for_specificity(experiment, specificity, roi_base=_roi_base)
    resolved_columns = _resolve_filtered_columns(
        experiment,
        filtered_columns=filtered_columns,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=exclude,
        source_df=scope_df,
    )
    use_against = (against_columns is not None or against_column_strings
                   or against_regex_string or against_exclude)
    against_resolved = []
    if use_against:
        against_resolved = _resolve_filtered_columns(
            experiment,
            filtered_columns=against_columns,
            column_strings=against_column_strings,
            regex_string=against_regex_string,
            exclude=against_exclude,
            source_df=scope_df,
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
                "plot_matrix_differences needs at least 2 numeric columns with "
                f"data; got {len(row_valid)} after filtering."
            )
    else:
        row_valid = [c for c in resolved_columns if c in valid_set]
        col_valid = [c for c in against_resolved if c in valid_set]
        if len(row_valid) < 1 or len(col_valid) < 1:
            raise ValueError(
                "plot_matrix_differences rectangular mode needs at least one "
                f"numeric column on each side; got {len(row_valid)} × {len(col_valid)}."
            )

    groups = _corr_pipeline_groups(experiment, scope_df, num_df, by, factor, specificity)
    if len(groups) < 2:
        raise ValueError(
            "plot_matrix_differences needs at least two groups. Use "
            "by='conditions' or factor='...' to split the data."
        )

    groups_results = []
    for glabel, gidx, _greg_spec in groups:
        gnum = num_df.loc[num_df.index.intersection(gidx)]
        res = _corr_pipeline_compute(
            gnum, row_valid, col_valid, methods,
            gate=difference_gate, alpha=alpha, require="or",
            min_n=min_n, square=square,
        )
        groups_results.append({
            "group": str(glabel),
            "n_rows": int(len(gnum)),
            "result": res,
        })

    prefer_condition = factor is None and str(by).strip().lower() == "conditions"
    resolved_comparisons = _corr_resolve_difference_comparisons(
        experiment,
        groups_results,
        comparisons=comparisons,
        prefer_condition_comparisons=prefer_condition,
    )
    label = run_label or _corr_matrix_difference_label(methods, resolved_comparisons, factor, by)
    fig_dir = os.path.join(experiment.fig_path, "Matrix Differences", strip_name(label))
    data_dir = os.path.join(_corr_pipeline_data_root(experiment), "Matrix Differences", strip_name(label))

    diff = _corr_render_matrix_differences(
        experiment,
        groups_results,
        methods,
        comparisons=resolved_comparisons,
        prefer_condition_comparisons=False,
        fig_dir=fig_dir,
        data_dir=data_dir,
        save=save,
        tick_label_size=tick_label_size,
        alpha=alpha,
        gate=difference_gate,
        test=difference_test,
        plot_signed=plot_signed,
        plot_absolute=plot_absolute,
        plot_pvalue_matrices=plot_pvalue_matrices,
        plot_qvalue_matrices=plot_qvalue_matrices,
        plot_gate_matrix=plot_gate_matrix,
    )

    manifest = {
        "run_label": strip_name(label),
        "fig_dir": fig_dir,
        "data_dir": data_dir,
        "mode": "rectangular" if not square else "square",
        "columns": list(row_valid),
        "against_columns": list(col_valid) if not square else None,
        "correlation": [_correlation_display_name(m) for m in methods],
        "by": str(by),
        "factor": factor,
        "comparisons": diff["comparisons"],
        "alpha": float(alpha),
        "difference_gate": str(difference_gate).lower(),
        "difference_test": str(difference_test),
        "n_comparisons": diff["n_comparisons"],
        "n_difference_tests": diff["n_difference_tests"],
        "n_difference_significant": diff["n_difference_significant"],
        "groups": [
            {"group": item["group"], "n_rows": item["n_rows"]}
            for item in groups_results
        ],
    }
    if save:
        _corr_write_json(manifest, os.path.join(data_dir, "manifest.json"))
    result = dict(manifest)
    result["differences"] = diff["long"]
    return result


def plot_correlation_pipeline(
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
    """Compatibility wrapper for :func:`PyFLASH.pipeline.correlation`."""
    kwargs = dict(locals())
    experiment = kwargs.pop("experiment")
    from PyFLASH.pipeline import correlation as _correlation_pipeline

    return _correlation_pipeline(experiment, **kwargs)


def plot_rect_matrices(
    experiment,
    filtered_columns=None,
    against_columns=None,
    by='conditions',
    factor=None,
    specificity=None,
    roi=None,
    save=True,
    correlation='pearsonr',
    tick_label_size=20,
    column_strings=None,
    regex_string=None,
    exclude='',
    against_column_strings=None,
    against_regex_string=None,
    against_exclude='',
    conditions=None,
    encode_x_categorical=True,
    combine_conditions=True,
    column_order=None,
    against_order=None,
    share_columns_across_panels=True,
    blank_panel_on_nan=False,
):
    """
    Rectangular correlation heatmaps (Y columns vs X columns), optionally
    combining multiple conditions/factor levels into one figure.

    Options:
    - share_columns_across_panels: enforce one shared valid column set.
    - blank_panel_on_nan: keep requested columns and annotate only NaN
      matrix cells with "NaN" (instead of dropping columns).
    """
    # ROI queue mode — iterate over ROI bases
    _roi_bases = _resolve_roi_bases(roi, experiment)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_rect_matrices(
                experiment,
                filtered_columns=filtered_columns,
                against_columns=against_columns,
                by=by, factor=factor,
                specificity=specificity, roi=_rb,
                save=save, correlation=correlation,
                tick_label_size=tick_label_size,
                column_strings=column_strings, regex_string=regex_string, exclude=exclude,
                against_column_strings=against_column_strings,
                against_regex_string=against_regex_string, against_exclude=against_exclude,
                conditions=conditions, encode_x_categorical=encode_x_categorical,
                combine_conditions=combine_conditions,
                column_order=column_order, against_order=against_order,
                share_columns_across_panels=share_columns_across_panels,
                blank_panel_on_nan=blank_panel_on_nan,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, experiment)) > 1

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_rect_matrices(
                experiment,
                filtered_columns=filtered_columns,
                against_columns=against_columns,
                by=by,
                factor=factor,
                specificity=spec,
                roi=roi,
                save=save,
                correlation=correlation,
                tick_label_size=tick_label_size,
                column_strings=column_strings,
                regex_string=regex_string,
                exclude=exclude,
                against_column_strings=against_column_strings,
                against_regex_string=against_regex_string,
                against_exclude=against_exclude,
                conditions=conditions,
                encode_x_categorical=encode_x_categorical,
                combine_conditions=combine_conditions,
                column_order=column_order,
                against_order=against_order,
                share_columns_across_panels=share_columns_across_panels,
                blank_panel_on_nan=blank_panel_on_nan,
            )
        return queued_outputs

    y_columns = _resolve_filtered_columns(
        experiment,
        filtered_columns=filtered_columns,
        column_strings=column_strings,
        regex_string=regex_string,
        exclude=exclude,
    )
    effective_against_exclude = against_exclude
    if effective_against_exclude in ("", None, []):
        effective_against_exclude = exclude
    x_columns = _resolve_filtered_columns(
        experiment,
        filtered_columns=against_columns,
        column_strings=against_column_strings,
        regex_string=against_regex_string,
        exclude=effective_against_exclude,
    )

    if len(y_columns) == 0:
        raise ValueError("No Y columns resolved for rectangular matrix.")
    if len(x_columns) == 0:
        raise ValueError("No X columns (against columns) resolved.")
    y_columns = _apply_requested_order(y_columns, column_order)
    x_columns = _apply_requested_order(x_columns, against_order)

    summary = _filtered_summary_for_specificity(experiment, specificity)
    condition_label_map = {c.name: getattr(c, "label", c.name) for c in experiment.condition_list}
    condition_color_map = {c.name: getattr(c, "color", "black") for c in experiment.condition_list}
    factor_label_map = {}
    factor_dict = getattr(experiment.condition_list, "factorDict", {})
    if isinstance(factor_dict, dict) and factor in factor_dict:
        for item in factor_dict[factor]:
            if hasattr(item, "name"):
                factor_label_map[str(item.name)] = getattr(item, "label", item.name)
    panels = []
    if factor is not None:
        if factor not in summary.columns:
            raise ValueError(f"Factor '{factor}' not found in summary.")
        vals = summary[factor].dropna().unique().tolist()
        ordered = []
        for cond in experiment.condition_list:
            match = next((v for v in vals if str(v) in str(cond.name)), None)
            if match is not None and match not in ordered:
                ordered.append(match)
        for v in vals:
            if v not in ordered:
                ordered.append(v)
        def _factor_display(v):
            key = str(v)
            if key in factor_label_map:
                return factor_label_map[key]
            match = next(
                (getattr(c, "label", c.name) for c in experiment.condition_list if key in str(c.name)),
                key,
            )
            return match
        panels = [('factor', str(v), summary[summary[factor] == v], _factor_display(v)) for v in ordered]
    elif by == 'conditions':
        cond_order = [c.name for c in experiment.condition_list]
        if conditions is not None:
            wanted = set(conditions)
            cond_order = [c for c in cond_order if c in wanted]
        for cond_name in cond_order:
            cdf = summary[summary['Condition'] == cond_name]
            if len(cdf) > 0:
                panels.append((
                    'condition',
                    cond_name,
                    cdf,
                    condition_label_map.get(cond_name, cond_name),
                ))
    else:
        panels = [('all', 'Combined', summary, 'Combined')]

    if len(panels) == 0:
        raise ValueError("No panels to plot after condition/factor/specificity filtering.")

    shared_y_columns = list(y_columns)
    shared_x_columns = list(x_columns)
    if bool(share_columns_across_panels) and not bool(blank_panel_on_nan):
        y_keep_sets = []
        x_keep_sets = []
        for _, _, panel_df, _ in panels:
            _, vy, vx, _, _, _ = _prepare_rect_numeric_df(
                panel_df,
                y_columns=y_columns,
                x_columns=x_columns,
                encode_x_categorical=encode_x_categorical,
            )
            y_keep_sets.append(set(vy))
            x_keep_sets.append(set(vx))
        if len(y_keep_sets) > 0:
            shared_y_set = set.intersection(*y_keep_sets)
            shared_y_columns = [c for c in y_columns if c in shared_y_set]
        if len(x_keep_sets) > 0:
            shared_x_set = set.intersection(*x_keep_sets)
            shared_x_columns = [c for c in x_columns if c in shared_x_set]

    if bool(blank_panel_on_nan):
        global_dropped_y = []
        global_dropped_x = []
        panel_y_columns = list(y_columns)
        panel_x_columns = list(x_columns)
    else:
        global_dropped_y = [c for c in y_columns if c not in shared_y_columns]
        global_dropped_x = [c for c in x_columns if c not in shared_x_columns]
        panel_y_columns = list(shared_y_columns)
        panel_x_columns = list(shared_x_columns)

    if len(panel_y_columns) == 0 or len(panel_x_columns) == 0:
        raise ValueError(
            "No shared valid columns across panels after NaN/sentinel filtering. "
            "Try disabling share_columns_across_panels or relaxing filters."
        )

    n_panels = len(panels)
    state = {}
    _init_progress_state(state, func_name='plot_rect_matrices', total=n_panels)
    correlation = _normalize_correlation_method(correlation)
    corr_label = _correlation_filename_label(correlation)
    coeff_label = f"{corr_label} coefficient"

    outputs = {}
    max_y = max(1, len(panel_y_columns))
    max_x = max(1, len(panel_x_columns))
    panel_h = min(20.0, max(3.6, 0.44 * max_y + 1.9))
    # Width follows x/y cell aspect so square cells do not create large
    # horizontal dead-space between panels.
    panel_w = min(6.0, max(1.2, panel_h * (max_x / max(1, max_y))))

    panel_fig_axes = []
    fig, axes = plt.subplots(
        1, n_panels,
        figsize=(panel_w * n_panels, panel_h),
        squeeze=False,
    )
    panel_fig_axes = [(fig, axes[0][i], i == n_panels - 1) for i in range(n_panels)]

    first_mappable = None
    for i, (kind, panel_name, panel_df, panel_display_name) in enumerate(panels):
        _progress_start_item(state, panel_name)
        fig, ax, show_cbar = panel_fig_axes[i]

        if bool(blank_panel_on_nan):
            # Keep full requested axes for this panel; NaN handling is done
            # per-square via pairwise dropna in the correlation loop below.
            valid_y = list(panel_y_columns)
            valid_x = list(panel_x_columns)
            dropped_y, dropped_x = [], []
            x_was_categorical = {}
            num_df = pd.DataFrame(index=panel_df.index)
            for y_col in valid_y:
                if y_col in panel_df.columns:
                    num_df[y_col] = _to_numeric_excluding_not_included(panel_df[y_col])
                else:
                    num_df[y_col] = np.nan
            for x_col in valid_x:
                if x_col in panel_df.columns:
                    coerced, as_cat = _coerce_series_for_corr(
                        panel_df[x_col],
                        allow_categorical=encode_x_categorical,
                    )
                    if coerced is None:
                        coerced = _to_numeric_excluding_not_included(panel_df[x_col])
                        as_cat = False
                    num_df[x_col] = coerced
                    x_was_categorical[x_col] = bool(as_cat)
                else:
                    num_df[x_col] = np.nan
                    x_was_categorical[x_col] = False
        else:
            num_df, valid_y, valid_x, dropped_y, dropped_x, x_was_categorical = _prepare_rect_numeric_df(
                panel_df,
                y_columns=panel_y_columns,
                x_columns=panel_x_columns,
                encode_x_categorical=encode_x_categorical,
            )

        title_text = "\n".join([t for t in str(panel_display_name).split("-") if t != ""])
        if kind == 'condition':
            title_color = condition_color_map.get(panel_name, "black")
        else:
            title_color = next(
                (c.color for c in experiment.condition_list if str(panel_name) in str(c.name)),
                "black",
            )

        if len(valid_y) == 0 or len(valid_x) == 0:
            ax.text(
                0.5, 0.5,
                "No valid columns for this panel\n(after NaN/sentinel handling).",
                ha='center', va='center', transform=ax.transAxes,
            )
            ax.set_axis_off()
            ax.set_title(
                title_text,
                fontsize=max(14, int(tick_label_size * 1.15)),
                pad=14,
                color=title_color,
            )
            out_dy = global_dropped_y + [c for c in dropped_y if c not in global_dropped_y]
            out_dx = global_dropped_x + [c for c in dropped_x if c not in global_dropped_x]
            if bool(blank_panel_on_nan):
                out_dy, out_dx = [], []
            outputs[panel_name] = {
                'correlations': {},
                'dropped_y': out_dy,
                'dropped_x': out_dx,
            }
            _progress_finish_item(state, panel_name)
            continue

        corr_mat = pd.DataFrame(index=valid_y, columns=valid_x, dtype=float)
        p_mat = pd.DataFrame(index=valid_y, columns=valid_x, dtype=float)
        corr_results = {}
        for y_col in valid_y:
            for x_col in valid_x:
                pair = num_df[[y_col, x_col]].dropna()
                if len(pair) > 1:
                    coefficient, p_value = _compute_correlation(pair[y_col], pair[x_col], correlation)
                    corr_mat.loc[y_col, x_col] = coefficient
                    p_mat.loc[y_col, x_col] = p_value
                    corr_results[f'{y_col} vs {x_col}'] = (
                        p_value,
                        coefficient,
                    )
                else:
                    corr_mat.loc[y_col, x_col] = np.nan
                    p_mat.loc[y_col, x_col] = np.nan

        hm = sns.heatmap(
            corr_mat,
            annot=False,
            fmt=".2f",
            cmap='coolwarm',
            linewidths=0.5,
            ax=ax,
            vmin=-1,
            vmax=1,
            cbar=False,
            square=False,
        )
        # Keep cells square without forcing large inter-panel whitespace.
        try:
            ax.set_box_aspect(max(1, len(valid_y)) / max(1, len(valid_x)))
        except Exception:
            pass
        if first_mappable is None and len(hm.collections) > 0:
            first_mappable = hm.collections[0]

        # Significance stars.
        n_for_star = max(1, max(len(valid_x), len(valid_y)))
        star_fs = min(28, max(9, int(220 / n_for_star)))
        for yi, y_col in enumerate(valid_y):
            for xi, x_col in enumerate(valid_x):
                p_val = p_mat.loc[y_col, x_col]
                if pd.isna(p_val):
                    continue
                star = _get_annotation(float(p_val), ns='')
                if star != '':
                    ax.text(
                        xi + 0.5, yi + 0.64, star,
                        ha='center', va='center',
                        fontsize=star_fs, color='black', fontweight='bold',
                    )

        if bool(blank_panel_on_nan):
            nan_fs = max(8, int(star_fs * 0.82))
            for yi, y_col in enumerate(valid_y):
                for xi, x_col in enumerate(valid_x):
                    if pd.isna(corr_mat.loc[y_col, x_col]):
                        ax.text(
                            xi + 0.5, yi + 0.5, "NaN",
                            ha='center', va='center',
                            fontsize=nan_fs, color="#7A7A7A", fontweight='bold',
                        )

        x_labels = []
        for c in valid_x:
            disp = get_display_name(c, minimal=True)
            x_labels.append(disp)
        y_labels = [get_display_name(c, minimal=True) for c in valid_y]

        # Keep tick/label cardinality explicit to avoid FixedLocator mismatches
        # when matplotlib prunes ticks on dense/small axes.
        x_tick_pos = np.arange(len(valid_x), dtype=float) + 0.5
        y_tick_pos = np.arange(len(valid_y), dtype=float) + 0.5
        ax.set_xticks(x_tick_pos)
        ax.set_yticks(y_tick_pos)

        ax.set_xticklabels(x_labels, rotation=60, ha='right', fontsize=tick_label_size)
        if i == 0:
            ax.set_yticklabels(y_labels, rotation=0, ha='right', fontsize=tick_label_size)
        else:
            ax.set_yticks([])
            ax.set_ylabel("")
            ax.tick_params(axis='y', left=False)
        ax.set_title(
            title_text,
            fontsize=max(14, int(tick_label_size * 1.15)),
            pad=14,
            color=title_color,
        )

        out_dy = global_dropped_y + [c for c in dropped_y if c not in global_dropped_y]
        out_dx = global_dropped_x + [c for c in dropped_x if c not in global_dropped_x]
        if bool(blank_panel_on_nan):
            out_dy, out_dx = [], []
        outputs[panel_name] = {
            'correlations': corr_results,
            'dropped_y': out_dy,
            'dropped_x': out_dx,
        }
        _progress_finish_item(state, panel_name)

    big_fig = panel_fig_axes[0][0]
    # Keep panels tightly packed; reserve a slim strip for colorbar.
    big_fig.subplots_adjust(left=0.06, right=0.92, wspace=0.02)
    if first_mappable is not None:
        try:
            last_ax = panel_fig_axes[-1][1]
            last_pos = last_ax.get_position()
            cbar_pad = 0.008
            cbar_width = 0.024
            cbar_height_frac = 0.72
            cbar_height = last_pos.height * cbar_height_frac
            cbar_y0 = last_pos.y0 + (last_pos.height - cbar_height) / 2.0
            cax = big_fig.add_axes([
                min(0.985 - cbar_width, last_pos.x1 + cbar_pad),
                cbar_y0,
                cbar_width,
                cbar_height,
            ])
            cbar = big_fig.colorbar(first_mappable, cax=cax)
            cbar.ax.tick_params(
                labelsize=max(11, int(tick_label_size * 1.05)),
                width=1.2,
                length=5,
            )
            try:
                cbar.outline.set_visible(False)
            except Exception:
                pass
            cbar.ax.text(
                1.03, 1.04, coeff_label,
                transform=cbar.ax.transAxes,
                ha='left', va='bottom',
                fontsize=max(13, int(tick_label_size * 1.15)),
                fontweight='normal',
            )
        except Exception:
            pass
    # Avoid tight_layout here; it can expand inter-panel spacing with fixed-aspect axes.
    if save:
        subfolder, suffix = build_subfolder(
            plot_type='Rectangular', marker='Matrices',
            factor=factor if factor is not None else str(by).rstrip('s'),
            specificity=specificity,
            aliases=getattr(experiment, 'aliases', None),
            roi_base=_roi_base, multi_roi=_multi_roi,
        )
        panel_names = " and ".join([p[1] for p in panels[:3]])
        if len(panels) > 3:
            panel_names += " and more"
        title = f"Rectangular {corr_label} Correlation Matrix ({panel_names})"
        save_fig(big_fig, experiment.fig_path, title + suffix, subfolder=subfolder)
    plt.close(big_fig)
    return outputs


def plot_coloc_upset(
    source,
    marker: "str|list[str]|tuple[str, ...]",
    *,
    specificity=None,
    roi=None,
    by: str | None = None,          # None = auto (condition panels if available); "conditions"/"Condition"; or a factor column name
    remove_closest: bool = False,
    include_neither: bool = False,
    min_count: int = 1,
    normalize: bool = False,        # show % of total instead of counts
    sort_by: str = "cardinality",   # same semantics as upsetplot
    title: str | None = None,
    save: bool = True,
    df: pd.DataFrame | None = None, # optional override (defaults to source.data[marker].df)
    experiment=None,                # optional legacy alias for save/order context
    dpi: int = 110,
):
    """
    Plot UpSet intersections for binary colocalisation metrics for `marker`.

    `marker` can be a single marker string or a list/tuple of markers. When a list
    is provided, one UpSet run is executed per marker and a dict is returned.

    Auto-detected indicator columns (any that exist):
    - "{marker}_ColocCount<marker2>"
    - "{marker}_ClosestTo_<marker2>" (excluded when remove_closest=True)
    - "{marker}_Contains_<marker2>"

    Boolean coercion accepts 0/1, True/False, "0"/"1", "true"/"false", "yes"/"no".
    NaN values are treated as False.

    Grouping:
    - by=None: if multiple conditions remain after specificity filtering, one plot per condition;
      otherwise one combined plot.
    - by="conditions" (or "Condition"): one plot per condition.
    - by="<factor>": one plot per unique factor value.

    `source` is typically a Batch/Experiment object; marker data are resolved from
    `source.data[marker].df`. If `source` is a DataFrame, it is used directly.
    """
    try:
        from upsetplot import UpSet, from_indicators
    except Exception as e:
        raise ImportError(
            "Missing optional dependency 'upsetplot'. Install with: pip install upsetplot"
        ) from e

    # ROI queue mode — iterate over ROI bases
    _exp_for_roi = source if not isinstance(source, pd.DataFrame) else experiment
    _roi_bases = _resolve_roi_bases(roi, _exp_for_roi)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_coloc_upset(
                source, marker,
                specificity=specificity, roi=_rb,
                by=by, remove_closest=remove_closest,
                include_neither=include_neither, min_count=min_count,
                normalize=normalize, sort_by=sort_by,
                title=title, save=save, df=df,
                experiment=experiment, dpi=dpi,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, _exp_for_roi)) > 1

    # Marker queue mode: pass a list/tuple of markers and run one UpSet per marker.
    if isinstance(marker, (list, tuple, set, np.ndarray, pd.Series, pd.Index)) and not isinstance(marker, str):
        marker_list = []
        seen_markers = set()
        for m in marker:
            m_s = str(m).strip()
            if not m_s or m_s in seen_markers:
                continue
            seen_markers.add(m_s)
            marker_list.append(m_s)
        if len(marker_list) == 0:
            raise ValueError("No valid marker names were provided.")
        if df is not None:
            raise ValueError("`df` override can only be used with a single marker string.")

        queued_outputs = {}
        for m in marker_list:
            queued_outputs[m] = plot_coloc_upset(
                source,
                m,
                specificity=specificity,
                roi=roi,
                by=by,
                remove_closest=remove_closest,
                include_neither=include_neither,
                min_count=min_count,
                normalize=normalize,
                sort_by=sort_by,
                title=title,
                save=save,
                df=None,
                experiment=experiment,
                dpi=dpi,
            )
        return queued_outputs

    source_df, exp_obj = _resolve_coloc_source_df(source, marker, df_override=df)
    if exp_obj is None and experiment is not None and not isinstance(experiment, pd.DataFrame):
        exp_obj = experiment
    by_mode = by
    if isinstance(by_mode, str):
        by_clean = by_mode.strip()
        by_mode = "conditions" if by_clean.casefold() in {"condition", "conditions"} else by_clean
    source_df = _enrich_df_grouping_columns(source_df, exp_obj, requested_by=by_mode)

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_coloc_upset(
                source,
                marker,
                specificity=spec,
                roi=roi,
                by=by_mode,
                remove_closest=remove_closest,
                include_neither=include_neither,
                min_count=min_count,
                normalize=normalize,
                sort_by=sort_by,
                title=title,
                save=save,
                df=source_df,
                experiment=exp_obj,
                dpi=dpi,
            )
        return queued_outputs

    marker_s = str(marker)
    esc = re.escape(marker_s)
    kind_patterns = [
        ("ColocCount", re.compile(rf"^{esc}_ColocCount(?P<m2>.+)$")),
        ("Contains", re.compile(rf"^{esc}_Contains_(?P<m2>.+)$")),
    ]
    if not remove_closest:
        kind_patterns.insert(1, ("ClosestTo", re.compile(rf"^{esc}_ClosestTo_(?P<m2>.+)$")))
    kind_rank = {"ColocCount": 0, "ClosestTo": 1, "Contains": 2}

    detected = []
    for c in source_df.columns:
        c_s = str(c)
        for kind, pattern in kind_patterns:
            m = pattern.match(c_s)
            if m is not None:
                detected.append((kind, str(m.group("m2")), c_s))
                break
    if len(detected) == 0:
        expected_parts = [
            f"'{marker_s}_ColocCount<marker2>'",
            f"'{marker_s}_Contains_<marker2>'",
        ]
        if not remove_closest:
            expected_parts.insert(1, f"'{marker_s}_ClosestTo_<marker2>'")
        raise ValueError(
            f"No colocalisation columns detected for marker '{marker_s}'. "
            f"Expected column patterns: {', '.join(expected_parts)}."
        )

    detected = sorted(detected, key=lambda t: (str(t[1]), kind_rank[t[0]], str(t[2])))
    coloc_cols = list(dict.fromkeys([c for _, _, c in detected]))
    def _format_indicator_name(kind: str, marker2_s: str) -> str:
        target = str(marker2_s).strip()
        if kind == "ColocCount":
            return f"{target}+"
        if kind == "ClosestTo":
            return f"{target} NN"
        if kind == "Contains":
            return f"Contains {target}"
        return f"{kind} {target}"

    indicator_names = {}
    for kind, marker2_s, col in detected:
        indicator_names[col] = _format_indicator_name(kind, marker2_s)

    work_df = _filter_df_by_specificity(source_df, specificity)

    def _coerce_binary(series: pd.Series) -> pd.Series:
        s = series.copy()
        if pd.api.types.is_bool_dtype(s):
            return s.fillna(False).astype(bool)
        if pd.api.types.is_numeric_dtype(s):
            return s.fillna(0).ne(0)
        text = s.astype(str).str.strip().str.lower()
        mapped = text.map({
            "1": True, "0": False,
            "true": True, "false": False,
            "yes": True, "no": False,
            "y": True, "n": False,
            "t": True, "f": False,
        })
        numeric = pd.to_numeric(text, errors="coerce")
        fallback = numeric.fillna(0).ne(0)
        mapped = mapped.where(mapped.notna(), fallback)
        return mapped.fillna(False).astype(bool)

    def _condition_order(values):
        vals = [v for v in values if pd.notna(v)]
        if exp_obj is not None and hasattr(exp_obj, "condition_list"):
            ordered = []
            for cond in exp_obj.condition_list:
                name = getattr(cond, "name", None)
                if name in vals and name not in ordered:
                    ordered.append(name)
            extras = sorted([v for v in vals if v not in ordered], key=lambda z: str(z))
            return ordered + extras
        return sorted(vals, key=lambda z: str(z))

    def _factor_order(values):
        vals = [v for v in values if pd.notna(v)]
        if exp_obj is not None and hasattr(exp_obj, "condition_list"):
            ordered = []
            for cond in exp_obj.condition_list:
                c_name = str(getattr(cond, "name", ""))
                match = next((v for v in vals if str(v) in c_name), None)
                if match is not None and match not in ordered:
                    ordered.append(match)
            extras = sorted([v for v in vals if v not in ordered], key=lambda z: str(z))
            return ordered + extras
        return sorted(vals, key=lambda z: str(z))

    condition_color_map = {}
    factor_color_map = {}
    if exp_obj is not None and hasattr(exp_obj, "condition_list"):
        try:
            condition_color_map = {
                str(c.name): getattr(c, "color", "black")
                for c in exp_obj.condition_list
            }
        except Exception:
            condition_color_map = {}
        if by_mode not in (None, "conditions"):
            factor_dict = getattr(exp_obj.condition_list, "factorDict", {})
            if isinstance(factor_dict, dict) and by_mode in factor_dict:
                for item in factor_dict[by_mode]:
                    if hasattr(item, "name"):
                        factor_color_map[str(item.name)] = getattr(item, "color", "black")

    def _panel_color(panel_name, panel_df):
        name_s = str(panel_name)
        if by_mode == "conditions" or (by_mode is None and auto_group_by == "Condition"):
            return condition_color_map.get(name_s, "black")
        if by_mode not in (None, "conditions"):
            if name_s in factor_color_map:
                return factor_color_map[name_s]
            if exp_obj is not None and hasattr(exp_obj, "condition_list"):
                match = next(
                    (
                        getattr(c, "color", "black")
                        for c in exp_obj.condition_list
                        if name_s in str(getattr(c, "name", ""))
                    ),
                    None,
                )
                if match is not None:
                    return match
        if "Condition" in panel_df.columns:
            cond_vals = panel_df["Condition"].dropna().astype(str).unique().tolist()
            if len(cond_vals) == 1:
                return condition_color_map.get(cond_vals[0], "black")
        return "black"

    base_title = title or f"{marker_s} overlap"
    auto_group_by = None
    if by_mode is None:
        if "Condition" in work_df.columns:
            ordered = _condition_order(work_df["Condition"].dropna().unique().tolist())
            if len(ordered) > 1:
                auto_group_by = "Condition"
                panels = [(str(v), work_df[work_df["Condition"] == v]) for v in ordered]
            else:
                panels = [("Combined", work_df)]
        else:
            panels = [("Combined", work_df)]
    elif by_mode == "conditions":
        if "Condition" not in work_df.columns:
            raise ValueError("Column 'Condition' is required when by='conditions'.")
        ordered = _condition_order(work_df["Condition"].dropna().unique().tolist())
        panels = [(str(v), work_df[work_df["Condition"] == v]) for v in ordered]
    else:
        if by_mode not in work_df.columns:
            raise ValueError(f"Column '{by_mode}' not found for grouping.")
        ordered = _factor_order(work_df[by_mode].dropna().unique().tolist())
        panels = [(str(v), work_df[work_df[by_mode] == v]) for v in ordered]

    state = {}
    _init_progress_state(
        state,
        func_name='plot_coloc_upset',
        total=len(panels),
    )
    outputs = {}
    for panel_name, panel_df in panels:
        _progress_start_item(state, panel_name)
        panel_df = panel_df.copy()
        bool_df = pd.DataFrame(index=panel_df.index)
        for c in coloc_cols:
            bool_df[c] = _coerce_binary(panel_df[c])

        data = from_indicators(coloc_cols, bool_df[coloc_cols])
        combos = data.index.to_frame(index=False)
        subset_counts = combos.value_counts(sort=False)
        if getattr(subset_counts.index, "nlevels", 1) == len(coloc_cols):
            subset_counts.index.names = coloc_cols

        if not include_neither and len(subset_counts) > 0:
            any_true = subset_counts.index.to_frame(index=False).any(axis=1).to_numpy()
            subset_counts = subset_counts[any_true]

        if min_count > 1 and len(subset_counts) > 0:
            subset_counts = subset_counts[subset_counts >= int(min_count)]

        total_n = int(len(bool_df))
        subset_values = subset_counts.astype(float)
        if normalize:
            if total_n > 0:
                subset_values = (subset_values / float(total_n)) * 100.0
            else:
                subset_values = subset_values * 0.0

        subset_values.index = subset_values.index.set_names(
            [indicator_names.get(n, n) for n in subset_values.index.names]
        )

        plot_sort_by = sort_by
        if not normalize:
            # Add a synthetic "Total" intersection as the first column.
            idx_frame = subset_values.index.to_frame(index=False)
            idx_frame["Total"] = False
            if len(idx_frame) == 0:
                subset_values = pd.Series(dtype=float)
                subset_values.index = pd.MultiIndex.from_arrays([[]], names=["Total"])
            else:
                subset_values.index = pd.MultiIndex.from_frame(idx_frame)

            total_names = list(subset_values.index.names)
            total_tuple = tuple(True if name == "Total" else False for name in total_names)
            total_idx = pd.MultiIndex.from_tuples([total_tuple], names=total_names)
            total_series = pd.Series([float(total_n)], index=total_idx)

            remaining = subset_values
            if sort_by == "cardinality":
                remaining = remaining.sort_values(ascending=False, kind="stable")
            elif sort_by == "degree" and len(remaining) > 1:
                deg = remaining.index.to_frame(index=False).sum(axis=1).to_numpy()
                order = np.argsort(-deg, kind="stable")
                remaining = remaining.iloc[order]
            subset_values = pd.concat([total_series, remaining])
            plot_sort_by = "input"

        fig = plt.figure(dpi=dpi)
        if len(subset_values) == 0:
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.5, 0.5, "No intersections passed filters", ha="center", va="center")
        else:
            panel_color = _panel_color(panel_name, panel_df)
            upset = UpSet(subset_values, sort_by=plot_sort_by, facecolor=panel_color)
            try:
                axes = upset.plot(fig=fig)
            except TypeError:
                axes = upset.plot()
                fig = next(iter(axes.values())).figure if isinstance(axes, dict) and len(axes) > 0 else plt.gcf()
            if isinstance(axes, dict):
                inter_ax = axes.get("intersections")
                if inter_ax is not None:
                    inter_ax.set_ylabel("% of rows" if normalize else "Count")

        if by_mode is None and auto_group_by is None:
            title_text = base_title
        elif by_mode is None and auto_group_by == "Condition":
            title_text = f"{base_title} (Condition={panel_name})"
        elif by_mode == "conditions":
            title_text = f"{base_title} (Condition={panel_name})"
        else:
            title_text = f"{base_title} ({by_mode}={panel_name})"
        if normalize:
            title_text = f"{title_text} [% of n={total_n}]"
        fig.suptitle(title_text, fontsize=14, weight="bold")

        if save and exp_obj is not None:
            subfolder, suffix = build_subfolder(
                plot_type='UpSet', marker=marker_s,
                factor=by_mode if by_mode is not None and by_mode != "conditions" else None,
                specificity=specificity,
                aliases=getattr(exp_obj, 'aliases', None),
                roi_base=_roi_base, multi_roi=_multi_roi,
            )
            norm_tag = "normalized" if normalize else "rawcounts"
            closest_tag = "noClosest" if remove_closest else "withClosest"
            if (by_mode is None and auto_group_by == "Condition") or by_mode == "conditions":
                cond_tag = strip_name(str(panel_name))
                save_name = f"UpSet Plot_{norm_tag}_{closest_tag}_Condition_{cond_tag}"
            elif by_mode is not None:
                panel_tag = strip_name(str(panel_name))
                by_tag = strip_name(str(by_mode))
                save_name = f"UpSet Plot_{norm_tag}_{closest_tag}_{by_tag}_{panel_tag}"
            else:
                save_name = f"UpSet Plot_{norm_tag}_{closest_tag}"
            save_fig(fig, exp_obj.fig_path, save_name + suffix, subfolder=subfolder)

        outputs[panel_name] = fig
        _progress_finish_item(state, panel_name)

    try:
        import sys
        sys.stdout.write("\n")
        sys.stdout.flush()
    except Exception:
        pass

    if len(outputs) == 1 and by_mode is None and auto_group_by is None:
        return outputs["Combined"]
    return outputs


def plot_coloc_sankey(
    source,
    marker: "str|list[str]|tuple[str, ...]",
    *,
    df: "pd.DataFrame|None" = None,
    specificity=None,
    roi=None,
    by: str | None = None,
    remove_closest: bool = False,
    false_bottom: bool = False,      # True => True nodes at top, False nodes at bottom per layer
    include_neither: bool = True,
    min_count: int = 1,
    normalize: bool = False,
    order: str | list[str] = "auto",
    title: str | None = None,
    save: bool = True,
    experiment=None,
    dpi: int = 110,
):
    """
    Plot a conditional branching Sankey (alluvial) for marker colocalisation indicators.

    `marker` can be a single marker string or a list/tuple of markers. When a list
    is provided, one Sankey run is executed per marker and a dict is returned.

    Columns are auto-detected from:
    - "{marker}_ColocCount*"
    - "{marker}_ClosestTo_*" (excluded when remove_closest=True)
    - "{marker}_Contains_*"

    Branching expands across active branches:
    Total -> C1 True/False
    Then each active branch is split again at C2, C3, ...
    (full combinations when include_neither=True; true-only spine when include_neither=False).

    Layout option:
    - false_bottom=True: force True nodes above False nodes in each layer.

    NaN values are treated as False.

    Save behavior:
    - If `save=True` and an experiment/batch object is available, saves under:
      `fig_path/<marker>/...`
    - Uses SVG via Plotly image export when available (`kaleido`), else falls back to HTML.
    """
    try:
        import plotly.graph_objects as go
    except Exception as e:
        raise ImportError(
            "Missing optional dependency 'plotly'. Install with: pip install plotly"
        ) from e
    try:
        from matplotlib.colors import to_rgb
    except Exception:
        to_rgb = None

    # ROI queue mode — iterate over ROI bases
    _exp_for_roi = source if not isinstance(source, pd.DataFrame) else experiment
    _roi_bases = _resolve_roi_bases(roi, _exp_for_roi)
    if len(_roi_bases) > 1:
        _queued = {}
        for _rb in _roi_bases:
            _queued[_rb] = plot_coloc_sankey(
                source, marker,
                df=df, specificity=specificity, roi=_rb,
                by=by, remove_closest=remove_closest,
                false_bottom=false_bottom, include_neither=include_neither,
                min_count=min_count, normalize=normalize,
                order=order, title=title, save=save,
                experiment=experiment, dpi=dpi,
            )
        return _queued
    _roi_base = _roi_bases[0]
    _multi_roi = len(_resolve_roi_bases(None, _exp_for_roi)) > 1

    # Marker queue mode: pass a list/tuple of markers and run one Sankey per marker.
    if isinstance(marker, (list, tuple, set, np.ndarray, pd.Series, pd.Index)) and not isinstance(marker, str):
        marker_list = []
        seen_markers = set()
        for m in marker:
            m_s = str(m).strip()
            if not m_s or m_s in seen_markers:
                continue
            seen_markers.add(m_s)
            marker_list.append(m_s)
        if len(marker_list) == 0:
            raise ValueError("No valid marker names were provided.")
        if df is not None:
            raise ValueError("`df` override can only be used with a single marker string.")

        queued_outputs = {}
        for m in marker_list:
            queued_outputs[m] = plot_coloc_sankey(
                source,
                m,
                df=None,
                specificity=specificity,
                roi=roi,
                by=by,
                remove_closest=remove_closest,
                false_bottom=false_bottom,
                include_neither=include_neither,
                min_count=min_count,
                normalize=normalize,
                order=order,
                title=title,
                save=save,
                experiment=experiment,
                dpi=dpi,
            )
        return queued_outputs

    try:
        min_count_i = int(min_count)
    except Exception as e:
        raise ValueError("min_count must be an integer >= 1.") from e
    if min_count_i < 1:
        min_count_i = 1

    source_df, exp_obj = _resolve_coloc_source_df(source, marker, df_override=df)
    if exp_obj is None and experiment is not None and not isinstance(experiment, pd.DataFrame):
        exp_obj = experiment

    by_mode = by
    if isinstance(by_mode, str):
        by_clean = by_mode.strip()
        by_mode = "conditions" if by_clean.casefold() in {"condition", "conditions"} else by_clean

    source_df = _enrich_df_grouping_columns(source_df, exp_obj, requested_by=by_mode)

    if _is_specificity_queue(specificity):
        queued_outputs = {}
        for spec in _iter_specificities(specificity):
            queued_outputs[spec] = plot_coloc_sankey(
                source,
                marker,
                df=source_df,
                specificity=spec,
                roi=roi,
                by=by_mode,
                remove_closest=remove_closest,
                false_bottom=false_bottom,
                include_neither=include_neither,
                min_count=min_count_i,
                normalize=normalize,
                order=order,
                title=title,
                save=save,
                experiment=exp_obj,
                dpi=dpi,
            )
        return queued_outputs

    marker_s = str(marker)
    esc = re.escape(marker_s)
    kind_patterns = [
        ("ColocCount", re.compile(rf"^{esc}_ColocCount(?P<m2>.+)$")),
        ("Contains", re.compile(rf"^{esc}_Contains_(?P<m2>.+)$")),
    ]
    if not remove_closest:
        kind_patterns.insert(1, ("ClosestTo", re.compile(rf"^{esc}_ClosestTo_(?P<m2>.+)$")))

    detected = []
    for c in source_df.columns:
        c_s = str(c)
        for kind, pattern in kind_patterns:
            m = pattern.match(c_s)
            if m is not None:
                detected.append((kind, str(m.group("m2")), c_s))
                break

    dedup = []
    seen_cols = set()
    for item in detected:
        col = item[2]
        if col in seen_cols:
            continue
        seen_cols.add(col)
        dedup.append(item)

    if len(dedup) == 0:
        expected_parts = [
            f"'{marker_s}_ColocCount<marker2>'",
            f"'{marker_s}_Contains_<marker2>'",
        ]
        if not remove_closest:
            expected_parts.insert(1, f"'{marker_s}_ClosestTo_<marker2>'")
        raise ValueError(
            f"No colocalisation columns detected for marker '{marker_s}'. "
            f"Expected column patterns: {', '.join(expected_parts)}."
        )

    def _format_indicator_name(kind: str, marker2_s: str) -> str:
        target = str(marker2_s).strip()
        if kind == "ColocCount":
            return f"{target}+"
        if kind == "ClosestTo":
            return f"{target} NN"
        if kind == "Contains":
            return f"Contains {target}"
        return f"{kind} {target}"

    if isinstance(order, str):
        order_mode = order.strip().casefold()
        if order_mode in {"auto", "detected", "stable"}:
            ordered_detected = dedup
        elif order_mode in {"alphabetical", "alpha"}:
            ordered_detected = sorted(dedup, key=lambda t: str(t[2]))
        else:
            raise ValueError(
                "Unsupported order string. Use 'auto', 'detected', 'stable', "
                "'alphabetical', or provide a list of column keys."
            )
    elif isinstance(order, (list, tuple, set, np.ndarray, pd.Series, pd.Index)):
        requested = [str(x) for x in _flatten_specificity_values([order])]
        col_to_tuple = {t[2]: t for t in dedup}
        ordered_cols = _apply_requested_order(list(col_to_tuple.keys()), requested)
        ordered_detected = [col_to_tuple[c] for c in ordered_cols if c in col_to_tuple]
    else:
        raise TypeError("order must be a string mode or a list of column names.")

    coloc_cols = [t[2] for t in ordered_detected]
    indicator_names = {t[2]: _format_indicator_name(t[0], t[1]) for t in ordered_detected}

    work_df = _filter_df_by_specificity(source_df, specificity)

    def _coerce_binary(series: pd.Series) -> pd.Series:
        s = series.copy()
        if pd.api.types.is_bool_dtype(s):
            return s.fillna(False).astype(bool)
        if pd.api.types.is_numeric_dtype(s):
            return s.fillna(0).ne(0)
        text = s.astype(str).str.strip().str.lower()
        mapped = text.map({
            "1": True, "0": False,
            "true": True, "false": False,
            "yes": True, "no": False,
            "y": True, "n": False,
            "t": True, "f": False,
        })
        numeric = pd.to_numeric(text, errors="coerce")
        fallback = numeric.fillna(0).ne(0)
        mapped = mapped.where(mapped.notna(), fallback)
        return mapped.fillna(False).astype(bool)

    def _condition_order(values):
        vals = [v for v in values if pd.notna(v)]
        if exp_obj is not None and hasattr(exp_obj, "condition_list"):
            ordered = []
            for cond in exp_obj.condition_list:
                name = getattr(cond, "name", None)
                if name in vals and name not in ordered:
                    ordered.append(name)
            extras = sorted([v for v in vals if v not in ordered], key=lambda z: str(z))
            return ordered + extras
        return sorted(vals, key=lambda z: str(z))

    def _factor_order(values):
        vals = [v for v in values if pd.notna(v)]
        if exp_obj is not None and hasattr(exp_obj, "condition_list"):
            ordered = []
            for cond in exp_obj.condition_list:
                c_name = str(getattr(cond, "name", ""))
                match = next((v for v in vals if str(v) in c_name), None)
                if match is not None and match not in ordered:
                    ordered.append(match)
            extras = sorted([v for v in vals if v not in ordered], key=lambda z: str(z))
            return ordered + extras
        return sorted(vals, key=lambda z: str(z))

    condition_color_map = {}
    factor_color_map = {}
    if exp_obj is not None and hasattr(exp_obj, "condition_list"):
        try:
            condition_color_map = {
                str(c.name): getattr(c, "color", "black")
                for c in exp_obj.condition_list
            }
        except Exception:
            condition_color_map = {}
        if by_mode not in (None, "conditions"):
            factor_dict = getattr(exp_obj.condition_list, "factorDict", {})
            if isinstance(factor_dict, dict) and by_mode in factor_dict:
                for item in factor_dict[by_mode]:
                    if hasattr(item, "name"):
                        factor_color_map[str(item.name)] = getattr(item, "color", "black")

    def _panel_color(panel_name, panel_df):
        name_s = str(panel_name)
        if by_mode == "conditions" or (by_mode is None and auto_group_by == "Condition"):
            return condition_color_map.get(name_s, "black")
        if by_mode not in (None, "conditions"):
            if name_s in factor_color_map:
                return factor_color_map[name_s]
            if exp_obj is not None and hasattr(exp_obj, "condition_list"):
                match = next(
                    (
                        getattr(c, "color", "black")
                        for c in exp_obj.condition_list
                        if name_s in str(getattr(c, "name", ""))
                    ),
                    None,
                )
                if match is not None:
                    return match
        if "Condition" in panel_df.columns:
            cond_vals = panel_df["Condition"].dropna().astype(str).unique().tolist()
            if len(cond_vals) == 1:
                return condition_color_map.get(cond_vals[0], "black")
        return "black"

    def _rgba(color, alpha):
        a = max(0.0, min(1.0, float(alpha)))
        if to_rgb is None:
            return f"rgba(0,0,0,{a:.3f})"
        try:
            r, g, b = to_rgb(color)
        except Exception:
            r, g, b = to_rgb("black")
        return f"rgba({int(round(r * 255))},{int(round(g * 255))},{int(round(b * 255))},{a:.3f})"

    def _resolve_marker_color_from_source(src, marker_name: str):
        if isinstance(src, pd.DataFrame) or src is None:
            return "black"
        data_dict = getattr(src, "data", None)
        if not isinstance(data_dict, dict):
            return "black"

        key = str(marker_name)
        candidate = None
        if key in data_dict:
            candidate = data_dict[key]
        else:
            lower_map = {str(k).lower(): k for k in data_dict.keys()}
            key_lower = key.lower()
            if key_lower in lower_map:
                candidate = data_dict[lower_map[key_lower]]
            else:
                pref = [k for k in data_dict.keys() if str(k).startswith(key)]
                if len(pref) == 1:
                    candidate = data_dict[pref[0]]

        color = getattr(candidate, "color", None) if candidate is not None else None
        if color is None:
            return "black"
        return color

    base_title = title or f"{marker_s} Sankey"
    marker_color = _resolve_marker_color_from_source(source, marker_s)
    auto_group_by = None
    if by_mode is None:
        if "Condition" in work_df.columns:
            ordered = _condition_order(work_df["Condition"].dropna().unique().tolist())
            if len(ordered) > 1:
                auto_group_by = "Condition"
                panels = [(str(v), work_df[work_df["Condition"] == v]) for v in ordered]
            else:
                panels = [("Combined", work_df)]
        else:
            panels = [("Combined", work_df)]
    elif by_mode == "conditions":
        if "Condition" not in work_df.columns:
            raise ValueError("Column 'Condition' is required when by='conditions'.")
        ordered = _condition_order(work_df["Condition"].dropna().unique().tolist())
        panels = [(str(v), work_df[work_df["Condition"] == v]) for v in ordered]
    else:
        if by_mode not in work_df.columns:
            raise ValueError(f"Column '{by_mode}' not found for grouping.")
        ordered = _factor_order(work_df[by_mode].dropna().unique().tolist())
        panels = [(str(v), work_df[work_df[by_mode] == v]) for v in ordered]

    def _fmt_node_label(base: str, count: int, total: int) -> str:
        if normalize and total > 0:
            pct = 100.0 * float(count) / float(total)
            return f"{base}\nn={count} ({pct:.1f}%)"
        return f"{base}\nn={count}"

    def _branch_label(base_label: str, is_true: bool) -> str:
        txt = str(base_label).strip()
        # ColocCount labels are formatted as "<marker2>+"; false branch should read "<marker2>-".
        if txt.endswith("+"):
            return txt if is_true else (txt[:-1] + "-")
        # For Contains / ClosestTo keep base text and remove explicit True/False suffixes.
        return txt

    state = {}
    _init_progress_state(
        state,
        func_name='plot_coloc_sankey',
        total=len(panels),
    )
    outputs = {}
    for panel_name, panel_df in panels:
        _progress_start_item(state, panel_name)
        panel_df = panel_df.copy()
        total_n = int(len(panel_df))
        panel_color = marker_color

        bool_df = pd.DataFrame(index=panel_df.index)
        for c in coloc_cols:
            bool_df[c] = _coerce_binary(panel_df[c])

        n_layers = len(coloc_cols) + 1  # Total + each indicator stage

        # Build deterministic layered nodes and links across all branch combinations.
        node_meta = {}
        layer_nodes = {i: [] for i in range(n_layers)}
        links = []

        def _add_node(key, layer, base_label, count, kind, path):
            if key in node_meta:
                return key
            node_meta[key] = {
                "layer": int(layer),
                "base_label": str(base_label),
                "count": int(count),
                "kind": str(kind),
                "path": str(path),
            }
            layer_nodes[int(layer)].append(key)
            return key

        root_key = ("root", "")
        all_mask = pd.Series(True, index=bool_df.index, dtype=bool)
        _add_node(root_key, 0, "Total", total_n, "root", "")

        active = [{"key": root_key, "mask": all_mask, "path": ""}]
        for i, c in enumerate(coloc_cols, start=1):
            label = indicator_names.get(c, str(c))
            next_active = []
            for parent in active:
                parent_key = parent["key"]
                parent_mask = parent["mask"]
                parent_path = parent["path"]
                n_parent = int(parent_mask.sum())
                if n_parent <= 0:
                    continue

                true_mask = parent_mask & bool_df[c]
                false_mask = parent_mask & (~bool_df[c])
                n_true = int(true_mask.sum())
                n_false = int(false_mask.sum())

                branch_items = []
                if n_true >= min_count_i:
                    branch_items.append(("T", true_mask, n_true, "true", _branch_label(label, True)))
                if include_neither and n_false >= min_count_i:
                    branch_items.append(("F", false_mask, n_false, "false", _branch_label(label, False)))

                if false_bottom:
                    branch_items = sorted(
                        branch_items,
                        key=lambda b: (0 if b[0] == "T" else 1, f"{parent_path}{b[0]}"),
                    )
                else:
                    branch_items = sorted(
                        branch_items,
                        key=lambda b: (-int(b[2]), 0 if b[0] == "T" else 1, f"{parent_path}{b[0]}"),
                    )

                for branch_code, child_mask, child_count, child_kind, child_text in branch_items:
                    child_path = f"{parent_path}{branch_code}"
                    child_key = ("stage", i, child_path)
                    _add_node(child_key, i, child_text, int(child_count), child_kind, child_path)
                    links.append({
                        "source_key": parent_key,
                        "target_key": child_key,
                        "count": int(child_count),
                        "kind": child_kind,
                    })
                    next_active.append({
                        "key": child_key,
                        "mask": child_mask,
                        "path": child_path,
                    })

            if len(next_active) == 0:
                break
            if false_bottom:
                next_active = sorted(
                    next_active,
                    key=lambda a: (0 if a["path"].endswith("T") else 1, a["path"]),
                )
            else:
                next_active = sorted(
                    next_active,
                    key=lambda a: (-int(a["mask"].sum()), a["path"]),
                )
            active = next_active

        # Deterministic node order: by layer with stable per-path ordering.
        for layer_idx in range(1, n_layers):
            keys = layer_nodes.get(layer_idx, [])
            if false_bottom:
                layer_nodes[layer_idx] = sorted(
                    keys,
                    key=lambda k: (
                        0 if str(node_meta[k]["kind"]).endswith("true") else 1,
                        str(node_meta[k].get("path", "")),
                        -int(node_meta[k]["count"]),
                        str(k),
                    ),
                )
            else:
                layer_nodes[layer_idx] = sorted(
                    keys,
                    key=lambda k: (-int(node_meta[k]["count"]), str(node_meta[k].get("path", "")), str(k)),
                )

        ordered_keys = []
        for layer_idx in range(n_layers):
            ordered_keys.extend(layer_nodes.get(layer_idx, []))

        key_to_idx = {k: i for i, k in enumerate(ordered_keys)}

        # Explicit fixed node positions: evenly spaced x layers and y slots.
        node_x, node_y, node_labels, node_colors = [], [], [], []
        true_node_color = "rgba(46,160,67,0.85)"
        false_node_color = "rgba(214,64,64,0.85)"
        for layer_idx in range(n_layers):
            keys = layer_nodes.get(layer_idx, [])
            if len(keys) == 0:
                continue
            if n_layers == 1:
                x_val = 0.5
            else:
                x_val = float(layer_idx) / float(n_layers - 1)
            if len(keys) == 1:
                y_vals = [0.5]
            else:
                y_vals = [float(i + 1) / float(len(keys) + 1) for i in range(len(keys))]
            for j, key in enumerate(keys):
                meta = node_meta[key]
                node_x.append(x_val)
                node_y.append(y_vals[j])
                node_labels.append(_fmt_node_label(meta["base_label"], int(meta["count"]), total_n))
                if meta["kind"] in {"true", "outcome_true"}:
                    node_colors.append(true_node_color)
                elif meta["kind"] in {"false", "outcome_false"}:
                    node_colors.append(false_node_color)
                else:
                    node_colors.append(_rgba(panel_color, 0.90))

        link_items = []
        for lk in links:
            s = lk["source_key"]
            t = lk["target_key"]
            if s not in key_to_idx or t not in key_to_idx:
                continue
            cnt = int(lk["count"])
            if cnt < min_count_i:
                continue
            pct = (100.0 * float(cnt) / float(total_n)) if total_n > 0 else 0.0
            link_items.append({
                "source": key_to_idx[s],
                "target": key_to_idx[t],
                "count": cnt,
                "value": pct if normalize else float(cnt),
                "kind": lk["kind"],
                "pct": pct,
            })

        link_items = sorted(
            link_items,
            key=lambda d: (-float(d["count"]), int(d["source"]), int(d["target"]), str(d["kind"])),
        )

        if len(link_items) == 0 or len(ordered_keys) == 0:
            fig = go.Figure()
            fig.add_annotation(
                text="No branches passed filters",
                x=0.5, y=0.5, showarrow=False,
                xref="paper", yref="paper",
                font=dict(size=16),
            )
        else:
            link_source = [d["source"] for d in link_items]
            link_target = [d["target"] for d in link_items]
            link_value = [d["value"] for d in link_items]
            link_custom = [
                [
                    d["count"],
                    d["pct"],
                    node_labels[int(d["source"])],
                    node_labels[int(d["target"])],
                ]
                for d in link_items
            ]
            link_color = []
            for d in link_items:
                if str(d["kind"]).startswith("true"):
                    link_color.append("rgba(46,160,67,0.50)")
                else:
                    link_color.append("rgba(214,64,64,0.20)")

            annotation_text = [str(lbl).replace("\n", "<br>") for lbl in node_labels]
            node_pad = 25
            node_thickness = 20
            node_dict = dict(
                pad=node_pad,
                thickness=node_thickness,
                line=dict(color="rgba(0,0,0,0.25)", width=0.5),
                label=[""] * len(node_labels),
                x=node_x,
                y=node_y,
                color=node_colors,
                align="left",
            )
            try:
                sankey_trace = go.Sankey(
                    arrangement="fixed",
                    node=node_dict,
                    link=dict(
                        source=link_source,
                        target=link_target,
                        value=link_value,
                        color=link_color,
                        customdata=link_custom,
                        hovertemplate=(
                            "%{customdata[2]} -> %{customdata[3]}<br>"
                            "Count: %{customdata[0]}<br>"
                            "Percent of panel: %{customdata[1]:.2f}%<extra></extra>"
                        ),
                    ),
                )
            except Exception:
                node_dict.pop("align", None)
                sankey_trace = go.Sankey(
                    arrangement="fixed",
                    node=node_dict,
                    link=dict(
                        source=link_source,
                        target=link_target,
                        value=link_value,
                        color=link_color,
                        customdata=link_custom,
                        hovertemplate=(
                            "%{customdata[2]} -> %{customdata[3]}<br>"
                            "Count: %{customdata[0]}<br>"
                            "Percent of panel: %{customdata[1]:.2f}%<extra></extra>"
                        ),
                    ),
                )

            fig = go.Figure(data=[sankey_trace])
            for xi, yi, txt in zip(node_x, node_y, annotation_text):
                # Sankey node y uses top-origin; paper coords use bottom-origin.
                ann_y = 1.0 - float(yi)
                fig.add_annotation(
                    x=min(1.0, max(0.0, float(xi))),
                    y=min(1.0, max(0.0, ann_y)),
                    xref="paper",
                    yref="paper",
                    text=txt,
                    showarrow=False,
                    xanchor="center",
                    yanchor="middle",
                    align="center",
                    textangle=0,
                    font=dict(size=9, color="black"),
                )

        if by_mode is None and auto_group_by is None:
            title_text = base_title
        elif by_mode is None and auto_group_by == "Condition":
            title_text = f"{base_title} (Condition={panel_name})"
        elif by_mode == "conditions":
            title_text = f"{base_title} (Condition={panel_name})"
        else:
            title_text = f"{base_title} ({by_mode}={panel_name})"
        if normalize:
            title_text = f"{title_text} [% of n={total_n}]"

        fig.update_layout(
            title=dict(text=title_text, x=0.5),
            font=dict(size=12),
            margin=dict(l=40, r=40, t=80, b=30),
            width=int(1200 * (dpi / 110.0)),
            height=max(500, 80 * n_layers),
        )

        if save and exp_obj is not None:
            subfolder, suffix = build_subfolder(
                plot_type='Sankey', marker=marker_s,
                factor=by_mode if by_mode is not None and by_mode != "conditions" else None,
                specificity=specificity,
                aliases=getattr(exp_obj, 'aliases', None),
                roi_base=_roi_base, multi_roi=_multi_roi,
            )

            norm_tag = "normalized" if normalize else "rawcounts"
            neither_tag = "withFalse" if include_neither else "trueOnly"
            closest_tag = "noClosest" if remove_closest else "withClosest"
            layout_tag = "falseBottom" if false_bottom else "flowOrder"
            if (by_mode is None and auto_group_by == "Condition") or by_mode == "conditions":
                cond_tag = strip_name(str(panel_name))
                save_name = f"Sankey_{norm_tag}_{neither_tag}_{closest_tag}_{layout_tag}_Condition_{cond_tag}"
            elif by_mode is not None:
                panel_tag = strip_name(str(panel_name))
                by_tag = strip_name(str(by_mode))
                save_name = f"Sankey_{norm_tag}_{neither_tag}_{closest_tag}_{layout_tag}_{by_tag}_{panel_tag}"
            else:
                save_name = f"Sankey_{norm_tag}_{neither_tag}_{closest_tag}_{layout_tag}"
            _save_plotly_figure(fig, exp_obj.fig_path, save_name + suffix, subfolder=subfolder)

        outputs[panel_name] = fig
        _progress_finish_item(state, panel_name)

    try:
        import sys
        sys.stdout.write("\n")
        sys.stdout.flush()
    except Exception:
        pass

    if len(outputs) == 1 and by_mode is None and auto_group_by is None:
        return outputs["Combined"]
    return outputs


# ═══════════════════════════════════════════════════════════════════════
#  Cheat-sheet utility
# ═══════════════════════════════════════════════════════════════════════

_PARAM_DESCRIPTIONS = {
    # ── Common to most functions ─────────────────────────────────────
    'experiment':           'Experiment or Batch object containing your data.',
    'source':               'Experiment, Batch, or MiniExperiment data source.',
    'filtered_columns':     'List of column names to plot (e.g. ["DAPI_Count", "Iba1_Volume"]).',
    'column_strings':       'Substring filter — include columns whose names contain this string.',
    'regex_string':         'Regex filter — include columns whose names match this pattern.',
    'exclude':              'Exclude columns whose names contain this substring.',
    'specificity':          'Filter data by a factor value. Tuple: ("Time", "WeekEight"). '
                            'Queue: [("Time","WeekEight"), ("Time","WeekFour")]; '
                            'pipelines run each queued filter as an independent child run.',
    'save':                 'Whether to save figures to disk (default True).',
    'factor':               'Group by a factor column instead of Condition (e.g. "Genotype").',
    'by':                   'Grouping mode: "conditions" (default) or a factor column name.',
    'comparisons':          'Explicit pairwise comparisons for stats, e.g. ["1-2", "1-3"].',
    'normalize':            'Normalize values to the first condition (fold-change).',
    'ns':                   'Label for non-significant results (default "ns").',
    'multiple_comparison':  'Stats test type: "One-Way" (ANOVA/Kruskal) or "Two-Way".',
    'force_nonparametric':  'Force non-parametric tests regardless of normality.',
    'posthoc':              'Non-parametric post-hoc test for Kruskal-Wallis: "Conover" or "Dunn".',
    'posthoc_correction':   'Post-hoc p-value correction: "auto", "Bonferroni", or "Uncorrected".',
    'bottom_ticks':         'Show tick marks on the bottom axis.',
    'bottom_tick_labels':   'Show tick labels on the bottom axis.',
    'save_normality':       'Save normality test Q-Q plots as PNG.',
    'normality_dpi':        'DPI for normality test figures.',
    'dry_run':              'Compute stats without rendering; returns a DataFrame summary.',
    'combine':              'Overlay all groups on one panel instead of separate figures.',
    'merge':                'Synonym for combine in some functions.',
    # ── Marker-based functions ───────────────────────────────────────
    'marker':               'Marker name (e.g. "Iba1") or list of markers.',
    'markers':              'List of marker names to include (None = all).',
    'x_attr':               'Attribute suffix to plot (e.g. "Volume", "Count", "IntDen").',
    'x':                    'X-axis column name or marker attribute.',
    'y':                    'Y-axis column name or marker attribute.',
    # ── Histogram / density ──────────────────────────────────────────
    'bins':                 'Number of histogram bins (default 30).',
    'binwidth':             'Fixed bin width (overrides bins if set).',
    'bin_range':            'Explicit (min, max) range for bins.',
    'bin_edges':            'Explicit array of bin edges.',
    'share_bins':           'Use identical bin edges across all panels.',
    'kde':                  'Overlay a kernel density estimate curve.',
    'alpha':                'Transparency of bars/fills (0-1).',
    'stat':                 'Y-axis statistic: "count", "proportion", "density".',
    'invert_x':             'Flip the x-axis direction.',
    'ymax':                 'Manual upper limit for y-axis.',
    # ── Ridgeline ────────────────────────────────────────────────────
    'ridge_height':         'Overlap fraction between ridgeline rows (default 0.85).',
    'bw_adjust':            'Bandwidth multiplier for KDE smoothing.',
    'line_width':           'Width of density outline strokes.',
    # ── ECDF ─────────────────────────────────────────────────────────
    'complementary':        'Plot 1-ECDF (survival function) instead of ECDF.',
    # ── Regression ───────────────────────────────────────────────────
    'test':                 'Correlation test: "pearsonr", "spearmanr", or "kendalltau" '
                            '(aliases "pearson"/"p", "spearman"/"s", "kendall"/"k" also work).',
    'normalize_x':          "X normalization mode: False, True (= 0-1 min-max), "
                            "(min, max), or 'Z-score'.",
    'normalize_y':          "Y normalization mode: False, True (= 0-1 min-max), "
                            "(min, max), or 'Z-score'.",
    'x_range':              'Manual (min, max) for x-axis.',
    'y_range':              'Manual (min, max) for y-axis.',
    'z_range':              'Manual (min, max) for z-axis (3D scatter).',
    'xmin':                 'Manual lower limit for x-axis.',
    'xmax':                 'Manual upper limit for x-axis.',
    'ymin':                 'Manual lower limit for y-axis.',
    'zmin':                 'Manual lower limit for z-axis (3D scatter).',
    'zmax':                 'Manual upper limit for z-axis (3D scatter).',
    'share_axes':           'When True (default), consult the experiment-level axis registry '
                            '(see `set_axis_limits`) for any missing x/y/z bounds, and reuse the '
                            'same range across queued sibling combinations when a column repeats.',
    'clip_fit_line':        'Trim the regression line to the active x/y limits (default True).',
    'margin':               'Target fractional distance between every spine and the nearest '
                            'data point (default 0.1 = 10% of axis span). Each side is padded '
                            'independently and only when the view has less breathing room than '
                            'this target; we never shrink. Sides pinned by the caller or the '
                            'axis registry are left untouched. Must be < 0.5. Pass 0 to disable.',
    # ── Volcano ──────────────────────────────────────────────────────
    'control':              'Name of the control condition for fold-change calculation.',
    'p_threshold':          'Significance threshold for highlighting (default 0.05).',
    'label_points':         '"significant" to label sig. points, "all", or None.',
    # Radar
    'statistic':            'Group summary for each radar axis: "mean", "median", "sum", "min", "max", or callable.',
    'share_scale':          'For normalized radar plots, use one per-column min/max scale across panels/queues.',
    'fill':                 'Fill radar polygons as well as drawing outlines.',
    'point_size':           'Marker size for radar vertices or baseline size for 3D scatter points.',
    'label_wrap':           'Maximum radar-axis label width before wrapping. Use 0 to disable wrapping.',
    'show_animal_xs':       'For radar plots, overlay one x marker per contributing animal on each axis.',
    'animal_x_marker':      'Marker style for per-animal radar overlays (default "x").',
    'animal_x_size':        'Marker size for per-animal radar x overlays. Use 0 to hide them.',
    'animal_x_alpha':       'Transparency for per-animal radar x overlays.',
    'animal_x_color':       'Optional color override for per-animal radar x overlays (default group color).',
    'radial_value_radii':   'Fractional radar radii to label with values, e.g. (0.30, 1.00). None disables labels.',
    'radial_value_color':   'Color for radar radial value labels (default grey).',
    'radial_value_size':    'Font size for radar radial value labels (default follows tick_label_size).',
    'figsize':              'Matplotlib figure size in inches.',
    # ── Pie charts ───────────────────────────────────────────────────
    'threshold':            'Value(s) for binning data into groups.',
    'start_angle':          'Rotation angle for the first slice (default 90).',
    'plot_format':          '"pie" for pie chart, "bar" for stacked bar.',
    'show_counts':          'Display counts. If used alone in bar mode, the y-axis uses raw counts.',
    'show_pct':             'Display percentages. If used in bar mode, the y-axis uses percent.',
    'labels':               'Optional dict mapping plotted category labels to display labels.',
    'include_N':            'Append contributing animal count (unique AnimalName) to pie titles or group labels.',
    'collapse_markers':     'For combo pies, ignore these partner markers and re-aggregate signatures at plot time.',
    'as_counts':            'Legacy alias: show counts only when true, percent only when false.',
    'include_n':            'Legacy alias for include_N.',
    # ── Correlation matrices ─────────────────────────────────────────
    'correlation':          'Correlation method: "pearsonr", "spearmanr", or "kendalltau" '
                            '(aliases "pearson"/"p", "spearman"/"s", "kendall"/"k" also work).',
    'first_columns':        'Pin these columns to the left of the matrix.',
    'tick_label_size':      'Font size for axis tick labels.',
    'prefix_order':         'Custom ordering of column prefixes.',
    'marker_order':         'Custom ordering of markers.',
    'share_columns_across_panels': 'Use same columns in every panel (default True).',
    'drop_duplicate_columns':      'Remove duplicate column entries.',
    # ── Rectangular matrices ─────────────────────────────────────────
    'against_columns':          'Columns for the second axis (rows vs columns).',
    'against_column_strings':   'Substring filter for second-axis columns.',
    'against_regex_string':     'Regex filter for second-axis columns.',
    'against_exclude':          'Exclude filter for second-axis columns.',
    # ── Correlation pipeline ─────────────────────────────────────────
    'tests':                    'Correlation methods to run, e.g. ("pearsonr", "spearmanr", "kendalltau").',
    'require':                  'Combine methods with "and" (pair must pass every test) or "or" (any test).',
    'gate':                     'Significance basis for selecting pairs: "fdr" (q-values) or "p" (raw p-values).',
    'min_n':                    'Minimum paired observations required to test a correlation (default 3).',
    'max_regressions':          'Cap on regression plots for surviving pairs; None plots all.',
    'plot_pvalue_matrices':     'For correlation_pipeline, save raw p-value matrix heatmaps for each test.',
    'plot_qvalue_matrices':     'For correlation_pipeline, save FDR q-value matrix heatmaps for each test.',
    'plot_difference_matrices': 'For correlation_pipeline, compare grouped correlation matrices pairwise.',
    'difference_comparisons':   'Matrix-difference comparisons: ["1-2"] or explicit pairs like [("AD", "MCI")].',
    'difference_gate':          'Significance basis for matrix-difference gate: "fdr"/q-values or "p"/raw p-values.',
    'difference_alpha':         'Alpha threshold for matrix-difference p/q/gate heatmaps. Defaults to pipeline alpha.',
    'difference_test':          'Correlation-difference test backend. "fisher_z" tests independent Pearson correlations.',
    'plot_difference_signed':   'Save signed correlation-difference matrices (left minus right).',
    'plot_difference_absolute': 'Save absolute correlation-difference matrices abs(left minus right).',
    'plot_difference_pvalue_matrices': 'Save Fisher-z p-value heatmaps for supported matrix differences.',
    'plot_difference_qvalue_matrices': 'Save FDR q-value heatmaps for supported matrix differences.',
    'plot_difference_gate_matrix':     'Save binary gate heatmaps for supported matrix differences.',
    'regression_factor':        'Factor used to colour/group the regression scatter (e.g. "Diagnosis").',
    'regression_test':          'Correlation method annotated on each regression plot.',
    'regression_combine':       'Overlay all regression groups on one panel (default True).',
    'run_label':                'Name for this run folder; auto-derived from columns+settings if omitted.',
    'if_exists':                'On run-folder collision: "overwrite" (default), "version", "error", or "skip".',
    'write_manifest':           'Write manifest.json and append to the runs index (default True).',
    'conditions':               'Subset of conditions to include.',
    'encode_x_categorical':     'Treat x-axis as categorical.',
    'combine_conditions':       'Combine all conditions into one panel.',
    'column_order':             'Custom ordering for primary columns.',
    'against_order':            'Custom ordering for second-axis columns.',
    'blank_panel_on_nan':       'Show blank panel when all values are NaN.',
    # ── Images ───────────────────────────────────────────────────────
    'animal_filter':        'Show only specific animals (name or list).',
    'roi_filter':           'Show only specific ROIs.',
    'ncols':                'Number of columns in the image grid.',
    'max_images':           'Maximum number of images to show.',
    'tile_size':            'Size of each image tile in inches.',
    'title':                'Custom title for the figure.',
    'show':                 'Display the figure interactively.',
    'verbose':              'Print detailed progress messages.',
    'tile_gap':             'Gap between tiles.',
    'tile_gap_units':       'Units for tile_gap: "points" or "inches".',
    'image_backend':        'Image loading backend: "auto", "tifffile", "pil".',
    'draw_rois':            'Draw ROI outlines on images.',
    'scale_bar':            'Add a scale bar to images.',
    'scale_bar_location':   'Position: "bottom left", "bottom right", etc.',
    'scale_bar_size':       'Scale bar length in microns.',
    'scale_bar_units':      '"microns" or "pixels".',
    'image_width_microns':  'Known image width for scale bar calculation.',
    'pixel_size':           'Microns per pixel (overrides Config.PIXEL_SIZE).',
    # ── Representative images ────────────────────────────────────────
    'fast_loading':         'Use lower-resolution loading for speed.',
    'preview_max_dim':      'Max dimension in pixels for preview thumbnails.',
    'image_adjustments':    'Dict of per-marker brightness/contrast adjustments.',
    'edit_mode':            'Launch interactive editor for selecting images.',
    'use_existing_edits':   'Reuse previously saved edit selections.',
    'progress':             'Show progress bar during loading.',
    'image_workers':        'Number of parallel workers for image loading.',
    # ── Locations ────────────────────────────────────────────────────
    'objects':              'Marker(s) to plot as scatter points.',
    'separate_by':          'Panel separation mode: "conditions", "animals".',
    'join_by':              'What to combine within a panel: "animals", "rois".',
    'colocalise':           'Show colocalisation overlay.',
    'annotate':             'Add text annotations to panels.',
    'extra_graphs':         'Additional markers to overlay as separate graphs.',
    'images':               'Background image marker(s).',
    'colocaliser':          'Colocalisation marker to highlight.',
    'extra_graph_colors':   'Colors for extra graph overlays.',
    'image_layout':         '"shared" or "per_panel" image arrangement.',
    'hue':                  'Color-code points by group.',
    'marker_colors':        'Custom color dict for markers.',
    'black_background':     'Use black background for location plots.',
    'panel_line_width':     'Border line width for panels.',
    'dpi':                  'Resolution for raster elements.',
    # ── Colocalisation plots ─────────────────────────────────────────
    'remove_closest':       'Remove closest-neighbour coloc artifacts.',
    'include_neither':      'Include "neither" category in upset/sankey.',
    'min_count':            'Minimum count threshold for display.',
    'sort_by':              'Upset sorting: "cardinality" or "degree".',
    'df':                   'Optional pre-filtered DataFrame override.',
    'false_bottom':         'Sankey: True nodes at top, False at bottom.',
    'order':                'Custom ordering. For pie charts, sets slice/stack order clockwise from the top; for Sankey, use "auto" or a list of markers.',
    # ── Shared ───────────────────────────────────────────────────────
    'points':               'Overlay individual data points on bar charts.',
    'point_fill':           'Mean bars: data-point fill color; use "group" to fill points with each group color.',
    'point_edge':           'Mean bars: data-point edge color; use "group" for each group color or "none" for no edge.',
    'point_linewidth':      'Mean bars: linewidth for overlaid data-point edges.',
    'enforce_shared_columns': 'Force all panels to use the same column set.',
    'shared_columns':       'Explicit list of columns to share across panels.',
}


def cheat_sheet(func_name=None):
    """Print a parameter reference for plot functions.

    Call with no arguments to list all plot functions.
    Call with a function name for detailed parameter info.

    Examples
    --------
    >>> cheat_sheet()                    # list all plot functions
    >>> cheat_sheet('plot_mean_bars')    # detailed params for one function
    >>> cheat_sheet('histograms')        # shorthand without plot_ prefix
    """
    import inspect as _inspect
    import importlib as _importlib
    import sys as _sys

    _this = _sys.modules[__name__]
    plot_funcs = {}
    for _n in dir(_this):
        if _n.startswith('plot_') and callable(getattr(_this, _n)):
            _obj = getattr(_this, _n)
            if hasattr(_obj, '__code__'):
                plot_funcs[_n] = _obj

    if func_name is None:
        print("=" * 70)
        print("  PyFLASH — Plot Function Reference")
        print("=" * 70)
        print()
        for name in sorted(plot_funcs):
            doc = (plot_funcs[name].__doc__ or '').strip().split('\n')[0]
            print(f"  {name}")
            if doc:
                print(f"    {doc}")
            print()
        print("-" * 70)
        print("  Call cheat_sheet('function_name') for detailed parameters.")
        print("  e.g. cheat_sheet('plot_mean_bars') or cheat_sheet('histograms')")
        print("=" * 70)
        return

    # Resolve name (supports shorthand without 'plot_' prefix, plus dotted
    # module targets used by pipeline registry entries).
    key = func_name
    func = None
    if isinstance(key, str) and "." in key:
        try:
            module_name, attr = key.rsplit(".", 1)
            module = _importlib.import_module(module_name)
            func = getattr(module, attr)
        except Exception:
            func = None
    if func is None and key not in plot_funcs:
        key = f"plot_{func_name}"
    if func is None and key not in plot_funcs:
        matches = [n for n in plot_funcs if func_name in n]
        if len(matches) == 1:
            key = matches[0]
        else:
            print(f"Unknown function '{func_name}'. Available:")
            for n in sorted(plot_funcs):
                print(f"  {n}")
            return

    if func is None:
        func = plot_funcs[key]
    sig = _inspect.signature(func)
    doc = (func.__doc__ or '').strip()
    first_line = doc.split('\n')[0] if doc else ''

    print()
    print("=" * 70)
    print(f"  {key}")
    if first_line:
        print(f"  {first_line}")
    print("=" * 70)
    print()

    for p in sig.parameters.values():
        name = p.name
        default = p.default

        if name.startswith('_'):
            continue
        desc = _PARAM_DESCRIPTIONS.get(name, '')

        if default is _inspect.Parameter.empty:
            default_str = '(required)'
        elif default is None:
            default_str = 'None'
        elif isinstance(default, str):
            default_str = f'"{default}"'
        else:
            default_str = str(default)

        req = '*' if default is _inspect.Parameter.empty else ' '
        print(f"  {req} {name:<30s} = {default_str}")
        if desc:
            print(f"    {desc}")
        print()

    print("-" * 70)
    print("  * = required parameter")
    print("=" * 70)


# ─────────────────────────────────────────────────────────────────────
# Statistical analysis plots: power curves, marker-profile PCA, and
# time-course growth-curve fits.  These complement the stats helpers in
# PyFLASH.stats_extra and are registered in spec.PLOT_REGISTRY.
# ─────────────────────────────────────────────────────────────────────
def _stat_plot_save_path(batch, save_path):
    """Resolve a save directory for a stats plot from an explicit path or batch."""
    if save_path is not None:
        return save_path
    for attr in ("fig_path", "data_path"):
        p = getattr(batch, attr, None)
        if p:
            return p
    return "."


def _categorical_colors(values, palette=None):
    """Map unique categorical values to colors (provided palette or tab10)."""
    uniques = list(dict.fromkeys(values))
    if isinstance(palette, dict):
        return {v: palette.get(v, "grey") for v in uniques}
    cmap = plt.get_cmap("tab10")
    return {v: cmap(i % 10) for i, v in enumerate(uniques)}


def _numeric_feature_matrix(df, columns):
    """Coerce selected columns to a numeric matrix, dropping rows with any NaN."""
    num = df[columns].apply(pd.to_numeric, errors="coerce")
    num = num.replace([np.inf, -np.inf], np.nan)
    keep = num.notna().all(axis=1)
    return num.loc[keep], keep


def plot_power_curve(batch=None, *, effect_sizes=(0.2, 0.5, 0.8), n_range=(2, 30),
                     alpha=0.05, observed=None, observed_n=None,
                     target_powers=(0.8, 0.9), test="t-test", k_groups=2,
                     title=None, save=False, save_path=None,
                     save_name="power_curve", dpi=600, return_data=False):
    """Plot statistical power vs sample size per group.

    One curve per entry in ``effect_sizes`` (plus the ``observed`` effect if
    given).  Vertical line at ``observed_n``; horizontal guides at
    ``target_powers``.  ``test='t-test'`` (two groups) or ``'anova'``
    (``k_groups`` groups).  ``batch`` is unused except for save-path resolution
    (present so the function is callable from the spec runner).  Returns the
    figure (or ``(fig, DataFrame)`` when ``return_data=True``).
    """
    if str(test).lower() in ("anova", "f", "f-test"):
        from statsmodels.stats.power import FTestAnovaPower
        analysis = FTestAnovaPower()

        def _power(es, n):
            return float(analysis.power(effect_size=es, nobs=n * k_groups,
                                        alpha=alpha, k_groups=k_groups))
    else:
        from statsmodels.stats.power import TTestIndPower
        analysis = TTestIndPower()

        def _power(es, n):
            return float(analysis.power(effect_size=es, nobs1=n, alpha=alpha, ratio=1.0))

    ns = np.arange(int(n_range[0]), int(n_range[1]) + 1)
    effects = list(effect_sizes)
    if observed is not None and np.isfinite(observed):
        effects = effects + [abs(float(observed))]

    fig, ax = plt.subplots(figsize=(8, 6), layout="constrained")
    rows = []
    for es in effects:
        powers = [_power(abs(es), int(n)) for n in ns]
        is_obs = observed is not None and np.isclose(es, abs(float(observed)))
        label = f"observed d={abs(es):.2f}" if is_obs else f"d={es:.2f}"
        ax.plot(ns, powers, lw=2.5 if is_obs else 2,
                ls="--" if is_obs else "-",
                color="black" if is_obs else None, label=label)
        for n, p in zip(ns, powers):
            rows.append({"effect_size": abs(es), "n_per_group": int(n), "power": p, "observed": is_obs})

    for tp in target_powers:
        ax.axhline(tp, color="grey", lw=1, ls=":")
        ax.text(ns[-1], tp, f" {int(tp * 100)}%", va="center", fontsize=10, color="grey")
    if observed_n is not None:
        ax.axvline(observed_n, color="crimson", lw=1.5, ls="-.")
        ax.text(observed_n, 0.02, f" n={observed_n}", color="crimson", fontsize=10, rotation=90, va="bottom")

    ax.set_xlabel("n per group")
    ax.set_ylabel("Power")
    ax.set_ylim(0, 1.02)
    ax.set_title(title or f"Power analysis ({test}, alpha={alpha})")
    ax.legend(frameon=False)

    if save:
        save_fig(fig, _stat_plot_save_path(batch, save_path), strip_name(save_name), verbose=False)
    data = pd.DataFrame(rows)
    return (fig, data) if return_data else fig


def plot_marker_pca(batch, columns=None, column_strings=None, regex_string=None,
                    exclude='', hue_column="Condition", specificity=None,
                    standardize=True, n_components=2, annotate_loadings=True,
                    max_loadings=12, palette=None, title=None,
                    save=False, save_path=None, save_name=None, dpi=600,
                    return_data=False):
    """PCA biplot of animal-level marker profiles, coloured by ``hue_column``.

    Builds the feature matrix from ``batch.summary`` (one row per animal),
    selecting columns by explicit list or ``column_strings``/``regex_string``/
    ``exclude`` (same semantics as ``get_columns``).  Standardises per column by
    default so large-magnitude IntDen columns do not dominate.  Returns the
    figure (or ``(fig, {scores, loadings, explained_variance})``).
    """
    from sklearn.decomposition import PCA

    summary = getattr(batch, "summary", None)
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        raise ValueError("batch.summary must be a non-empty DataFrame.")
    df = filter_df_by_specificity(summary, specificity)

    if columns is not None:
        feat_cols = [c for c in columns if c in df.columns]
    else:
        feat_cols = get_columns(df, column_strings=column_strings,
                                regex_string=regex_string, exclude=exclude)
    feat_cols = [c for c in feat_cols if c != hue_column]
    if len(feat_cols) < 2:
        raise ValueError("Need at least 2 numeric feature columns for PCA.")

    X, keep = _numeric_feature_matrix(df, feat_cols)
    if len(X) < 3:
        raise ValueError("Need at least 3 complete rows (animals) for PCA.")
    if hue_column in df.columns:
        hue = df.loc[keep, hue_column].astype(str)
    else:
        hue = pd.Series(["all"] * len(X), index=X.index)

    Xv = X.to_numpy(dtype=float)
    if standardize:
        mu = Xv.mean(axis=0)
        sd = Xv.std(axis=0, ddof=0)
        sd[sd == 0] = 1.0
        Xv = (Xv - mu) / sd

    n_keep = min(max(2, int(n_components)), Xv.shape[1], Xv.shape[0])
    pca = PCA(n_components=n_keep)
    scores = pca.fit_transform(Xv)
    evr = pca.explained_variance_ratio_

    fig, ax = plt.subplots(figsize=(8, 7), layout="constrained")
    color_map = _categorical_colors(list(hue.unique()), palette)
    for level in hue.unique():
        m = (hue == level).to_numpy()
        ax.scatter(scores[m, 0], scores[m, 1], s=70, alpha=0.85,
                   color=color_map[level], edgecolor="black", linewidth=0.5, label=str(level))

    if annotate_loadings:
        load = pca.components_[:2].T  # (features, 2)
        scale = 0.9 * np.abs(scores[:, :2]).max() / (np.abs(load).max() or 1.0)
        order = np.argsort(-(load[:, 0] ** 2 + load[:, 1] ** 2))[:max_loadings]
        for i in order:
            ax.arrow(0, 0, load[i, 0] * scale, load[i, 1] * scale,
                     color="grey", alpha=0.6, head_width=scale * 0.02, length_includes_head=True)
            ax.text(load[i, 0] * scale * 1.08, load[i, 1] * scale * 1.08,
                    str(feat_cols[i]), fontsize=8, color="dimgrey", ha="center", va="center")

    ax.axhline(0, color="lightgrey", lw=0.8, zorder=0)
    ax.axvline(0, color="lightgrey", lw=0.8, zorder=0)
    ax.set_xlabel(f"PC1 ({evr[0] * 100:.1f}%)")
    ax.set_ylabel(f"PC2 ({evr[1] * 100:.1f}%)")
    ax.set_title(title or f"Marker profile PCA (n={len(X)} animals)")
    ax.legend(frameon=False, title=hue_column)

    if save:
        save_fig(fig, _stat_plot_save_path(batch, save_path),
                 strip_name(save_name or "marker_pca"), verbose=False)

    if return_data:
        scores_df = pd.DataFrame(scores[:, :2], columns=["PC1", "PC2"], index=X.index)
        scores_df[hue_column] = hue
        loadings_df = pd.DataFrame(pca.components_[:2].T, index=feat_cols, columns=["PC1", "PC2"])
        return fig, {"scores": scores_df, "loadings": loadings_df, "explained_variance": evr}
    return fig


def plot_timecourse(batch, column, time_col="Time", group_col="Genotype",
                    model="auto", specificity=None, time_map=None,
                    animal_col="AnimalName", palette=None, show_points=True,
                    title=None, save=False, save_path=None, save_name=None,
                    dpi=600, return_data=False):
    """Fit and plot a growth curve per group across an ordered time factor.

    Fits :func:`PyFLASH.stats_extra.fit_growth_curve` to the animal-level points
    of each ``group_col`` level (x = numeric time, y = ``column``), overlays the
    fitted curve and the per-timepoint mean +/- SEM.  ``time_map`` maps a
    categorical time factor to numbers (e.g. ``{'WeekTwo': 2, 'WeekEight': 8}``).
    Returns the figure (or ``(fig, {group: fit_dict})``).
    """
    from PyFLASH.stats_extra import _resolve_numeric_time, fit_growth_curve

    summary = getattr(batch, "summary", None)
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        raise ValueError("batch.summary must be a non-empty DataFrame.")
    df = filter_df_by_specificity(summary, specificity).copy()
    for needed in (column, time_col):
        if needed not in df.columns:
            raise ValueError(f"column '{needed}' not found in batch.summary.")
    df["_t"] = _resolve_numeric_time(df[time_col], time_map)
    df["_v"] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["_t", "_v"])
    if df.empty:
        raise ValueError("No numeric (time, value) rows after parsing; pass time_map?")

    if group_col in df.columns:
        groups = list(dict.fromkeys(df[group_col].astype(str)))
    else:
        df[group_col] = "all"
        groups = ["all"]

    fig, ax = plt.subplots(figsize=(8, 6), layout="constrained")
    color_map = _categorical_colors(groups, palette)
    fits = {}
    for grp in groups:
        sub = df[df[group_col].astype(str) == grp]
        x = sub["_t"].to_numpy(float)
        y = sub["_v"].to_numpy(float)
        color = color_map[grp]
        if show_points:
            ax.scatter(x, y, s=30, alpha=0.4, color=color, edgecolor="none")
        agg = sub.groupby("_t")["_v"].agg(["mean", "sem", "count"]).reset_index()
        ax.errorbar(agg["_t"], agg["mean"], yerr=agg["sem"].fillna(0.0),
                    fmt="o", color=color, capsize=4, lw=2, markersize=7, zorder=3)
        try:
            fit = fit_growth_curve(x, y, model=model)
            xs = np.linspace(float(np.min(x)), float(np.max(x)), 100)
            ax.plot(xs, fit["predict"](xs), color=color, lw=2.5,
                    label=f"{grp} ({fit['model']}, R^2={fit['r_squared']:.2f})")
            fits[grp] = fit
        except Exception as e:
            _log.hint(f"[plot_timecourse] fit failed for group '{grp}': {e}")
            ax.plot([], [], color=color, label=f"{grp} (fit failed)")
            fits[grp] = None

    ax.set_xlabel(time_col)
    ax.set_ylabel(str(column))
    ax.set_title(title or f"{column} time-course")
    ax.legend(frameon=False, title=group_col)

    if save:
        save_fig(fig, _stat_plot_save_path(batch, save_path),
                 strip_name(save_name or f"{column}_timecourse"), verbose=False)
    return (fig, fits) if return_data else fig
