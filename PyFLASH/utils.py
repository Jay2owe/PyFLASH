"""
Shared utility functions used across the package.
"""

import os
import re
import math
import time
import threading
import tempfile
import warnings
from contextlib import contextmanager
from collections.abc import Mapping
import numpy as np
import pandas as pd

from PyFLASH._logging import logger as _log

# Shared missing-value tag; presentation code must not import microscopy
# processing merely to recognise an excluded experiment measurement.
NOT_INCLUDED_SENTINEL = "NOT_INCLUDED_IN_EXPERIMENT"


# ── Figure-save observers ─────────────────────────────────────────────
# A decoupled hook so higher layers can watch every figure as it is saved without
# this low-level module importing them. The pipeline montage layer
# (``PyFLASH.pipeline_montage``) registers an observer for the duration of a
# pipeline run to capture the live figure before the caller closes it. Each
# observer is called as ``cb(figure, full_path, image_name, subfolder, key)`` and
# must never raise — a misbehaving observer is isolated so it can't break a save.
_FIG_SAVE_OBSERVERS = []


def register_fig_save_observer(callback):
    """Register a ``save_fig`` observer (idempotent)."""
    if callback not in _FIG_SAVE_OBSERVERS:
        _FIG_SAVE_OBSERVERS.append(callback)


def unregister_fig_save_observer(callback):
    """Remove a previously-registered ``save_fig`` observer (no-op if absent)."""
    try:
        _FIG_SAVE_OBSERVERS.remove(callback)
    except ValueError:
        pass


_FIG_SAVED_OBSERVERS = []


def register_fig_saved_observer(callback):
    """Register a post-write observer, called once the file exists (idempotent).

    Distinct from ``register_fig_save_observer``, which fires with the live
    figure *before* the write so a montage can capture it. Anything that needs
    to read, hash or annotate the written file belongs here instead.
    """
    if callback not in _FIG_SAVED_OBSERVERS:
        _FIG_SAVED_OBSERVERS.append(callback)


def unregister_fig_saved_observer(callback):
    """Remove a previously-registered post-write observer (no-op if absent)."""
    try:
        _FIG_SAVED_OBSERVERS.remove(callback)
    except ValueError:
        pass


def _notify_fig_saved_observers(full_path, image_name, subfolder, key):
    for cb in list(_FIG_SAVED_OBSERVERS):
        try:
            cb(full_path, image_name, subfolder, key)
        except Exception:
            pass


def _notify_fig_save_observers(figure, full_path, image_name, subfolder, key):
    for cb in list(_FIG_SAVE_OBSERVERS):
        try:
            cb(figure, full_path, image_name, subfolder, key)
        except Exception:
            pass  # an observer must never break a figure save


# ── Column display-label overrides ────────────────────────────────────
# A thread-local stack of ``{raw_column: display_label}`` mappings. The single
# display-name resolver ``PyFLASH.plotting.get_display_name`` consults the active
# mapping *before* its house rewrites, so a user-supplied ``column_labels`` renames
# any column's legend / axis / annotation text everywhere a plot routes text
# through ``get_display_name`` — with no per-call plumbing. The shared ``run()``
# harness (``PyFLASH.iteration``) and individual plot wrappers push a mapping for
# the duration of a render via ``column_label_overrides(...)``. Overrides affect
# *displayed text only*: the underlying column identity (palette keys, describe
# records, saved data) is unchanged.
_LABEL_OVERRIDES = threading.local()


def _label_override_stack():
    stack = getattr(_LABEL_OVERRIDES, "stack", None)
    if stack is None:
        stack = []
        _LABEL_OVERRIDES.stack = stack
    return stack


def active_column_label(*names):
    """Return the user override for the first of ``names`` present in the active
    mapping (innermost push wins), or ``None`` when no override is in effect.

    Callers pass the candidate keys in priority order — typically the raw column
    name and its ``.expN``-cleaned form — so either spelling of a key matches.
    """
    stack = _label_override_stack()
    if not stack:
        return None
    for mapping in reversed(stack):
        for name in names:
            if name in mapping:
                return mapping[name]
    return None


def normalize_column_labels(columns, column_labels):
    """Return the *user overrides only* as ``{str(column): str(label)}``.

    ``column_labels`` accepts either a ``{column: label}`` mapping (its items are
    taken verbatim) or a positional list matching ``columns`` one-for-one (zipped
    against them). ``None``/empty yields ``{}``. Columns with no override are left
    out so the house ``get_display_name`` logic still handles them.
    """
    if not column_labels:
        return {}
    if isinstance(column_labels, Mapping):
        return {str(k): str(v) for k, v in column_labels.items()}
    labels = list(column_labels)
    cols = list(columns) if columns is not None else []
    if len(cols) != len(labels):
        raise ValueError(
            f"column_labels list length ({len(labels)}) must match the number of "
            f"plotted columns ({len(cols)})."
        )
    return {str(c): str(lbl) for c, lbl in zip(cols, labels)}


@contextmanager
def column_label_overrides(mapping):
    """Push a ``{raw_column: display_label}`` mapping for the duration of the block.

    ``mapping`` is a plain dict (usually the output of
    :func:`normalize_column_labels`); ``None``/empty is a no-op. Nested pushes
    shadow outer ones and are always popped, even on error.
    """
    normalized = {str(k): str(v) for k, v in mapping.items()} if mapping else None
    if not normalized:
        yield
        return
    stack = _label_override_stack()
    stack.append(normalized)
    try:
        yield
    finally:
        stack.pop()


def resolve_column_labels(columns, column_labels, display=None):
    """Return a full ``{column: display_label}`` for every column in ``columns``.

    Unlike :func:`normalize_column_labels` (user entries only), this fills every
    column: an explicit override when present, otherwise ``display(column)`` — by
    default the house ``get_display_name(col, minimal=True)``. Use it when a plot
    needs labels as *data* (matrix column headers, an x-tick list) rather than via
    the ``get_display_name`` text path. Accepts the same dict-or-list forms.
    """
    cols = list(columns)
    if display is None:
        from PyFLASH.plotting import get_display_name
        display = lambda c: get_display_name(c, minimal=True)
    overrides = normalize_column_labels(cols, column_labels)
    out = {}
    for c in cols:
        if c in overrides:
            out[c] = overrides[c]
        elif str(c) in overrides:
            out[c] = overrides[str(c)]
        else:
            out[c] = display(c)
    return out


# ── Analysis-exclusion sentinels ──────────────────────────────────────
# Token written into a summary cell when a value is deliberately *excluded* from
# analysis. Distinct from NOT_INCLUDED_IN_EXPERIMENT ("never measured"): an
# excluded value WAS measured but was removed — either automatically as an
# outlier (``EXCLUDED_OUTLIER:<rule>``) or manually by the user with a reason
# (``EXCLUDED_MANUAL:<reason>``). Both share the ``EXCLUDED_`` family prefix, so
# the numeric-coercion paths treat them as analysis-missing (like the
# not-included sentinel) while QC reporting counts them separately and the reason
# stays visible in the cell.
EXCLUDED_SENTINEL_PREFIX = "EXCLUDED_"          # family prefix recognised everywhere
EXCLUDED_OUTLIER_PREFIX = "EXCLUDED_OUTLIER"
EXCLUDED_MANUAL_PREFIX = "EXCLUDED_MANUAL"


def excluded_outlier_token(reason=None):
    """Outlier-exclusion sentinel, optionally tagged with the rule that fired.

    ``excluded_outlier_token("iqr")`` -> ``"EXCLUDED_OUTLIER:iqr"``.
    """
    return f"{EXCLUDED_OUTLIER_PREFIX}:{reason}" if reason else EXCLUDED_OUTLIER_PREFIX


def excluded_manual_token(reason=None):
    """Manual-exclusion sentinel, optionally tagged with the user's reason.

    ``excluded_manual_token("damaged section")`` ->
    ``"EXCLUDED_MANUAL:damaged section"``. The reason is free text (shown in the
    cell for provenance) and is ignored by the coercion paths.
    """
    return f"{EXCLUDED_MANUAL_PREFIX}:{reason}" if reason else EXCLUDED_MANUAL_PREFIX


def is_excluded_mask(series):
    """Boolean mask of cells holding any ``EXCLUDED_`` analysis-exclusion token."""
    s = pd.Series(series)
    try:
        return s.astype(str).str.startswith(EXCLUDED_SENTINEL_PREFIX)
    except Exception:
        return pd.Series(False, index=s.index)


# Back-compat alias (the predicate now covers manual exclusions too).
is_excluded_outlier_mask = is_excluded_mask


# ── Specificity helpers (canonical versions) ──────────────────────────

def flatten_specificity_values(values):
    """Flatten nested iterables in specificity value lists."""
    out = []
    for v in values:
        if isinstance(v, (list, tuple, set, np.ndarray, pd.Series, pd.Index)):
            out.extend(list(v))
        else:
            out.append(v)
    return out


class HashableSpecificityMapping(dict):
    """Mapping specificity that can also be used as a queue result key."""

    def __hash__(self):
        frozen = []
        for key, value in self.items():
            vals = flatten_specificity_values(
                list(value) if isinstance(value, (list, tuple, set)) else [value]
            )
            frozen.append((str(key), tuple(str(v) for v in vals)))
        return hash(tuple(frozen))


def freeze_specificity_mapping(specificity):
    """Return a hashable copy of mapping-style specificity filters."""

    if isinstance(specificity, HashableSpecificityMapping):
        return specificity
    if isinstance(specificity, Mapping):
        return HashableSpecificityMapping(specificity)
    return specificity


def is_specificity_queue(specificity):
    """True when specificity is a list of specificity tuples/mappings.

    Example queue: [('Time', 'WeekFour'), ('Time', 'WeekEight')]
    Not a queue:   ('Time', 'WeekFour')
    """
    return (
        isinstance(specificity, (list, tuple))
        and len(specificity) > 0
        and isinstance(specificity[0], (list, tuple, Mapping))
    )


def iter_specificities(specificity):
    """Yield individual specificity tuples from a queue or single spec."""
    if is_specificity_queue(specificity):
        for item in specificity:
            if isinstance(item, Mapping):
                yield freeze_specificity_mapping(item)
                continue
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                yield tuple(item)
    else:
        yield specificity


def resolve_column_key(df, key):
    """Resolve column key with case-insensitive/trim matching plus legacy aliases."""
    if key in df.columns:
        return key

    candidates = [str(key).strip()]
    candidates.extend(summary_column_aliases(key))
    candidates.extend(raw_coloc_column_aliases(key))
    targets = {str(candidate).strip().casefold() for candidate in candidates}

    for col in df.columns:
        if str(col).strip().casefold() in targets:
            return col
    return None


_LEGACY_SUMMARY_COLOC_MEAN_RE = re.compile(
    r"^(?P<marker>.+)_Coloc(?P<target>.+)Mean(?P<exp>\.exp\d+)?$"
)
_CANONICAL_SUMMARY_COLOC_MEAN_RE = re.compile(
    r"^(?P<marker>.+)_Coloc_(?P<target>.+)_Mean(?P<exp>\.exp\d+)?$"
)
_LEGACY_SUMMARY_COLOC_COUNT_RE = re.compile(
    r"^(?P<marker>.+)_ColocCount(?P<target>.+?)(?P<pct>%?)(?P<exp>\.exp\d+)?$"
)
_CANONICAL_SUMMARY_COLOC_COUNT_RE = re.compile(
    r"^(?P<marker>.+)_Coloc_(?P<target>.+)_Count(?P<pct>%?)(?P<exp>\.exp\d+)?$"
)


def summary_column_aliases(key):
    """
    Return equivalent summary-column spellings for legacy/current coloc names.

    This keeps refactored summary schemas compatible with existing plot configs
    and any saved column references that still use the legacy coloc naming.
    """
    key_s = str(key).strip()
    aliases = []

    m = _LEGACY_SUMMARY_COLOC_MEAN_RE.match(key_s)
    if m is not None:
        aliases.append(
            f"{m.group('marker')}_Coloc_{m.group('target')}_Mean{m.group('exp') or ''}"
        )
        aliases.append(
            f"{m.group('marker')}_VolColoc_{m.group('target')}_Mean{m.group('exp') or ''}"
        )

    m = _CANONICAL_SUMMARY_COLOC_MEAN_RE.match(key_s)
    if m is not None:
        aliases.append(
            f"{m.group('marker')}_Coloc{m.group('target')}Mean{m.group('exp') or ''}"
        )
        aliases.append(
            f"{m.group('marker')}_VolColoc_{m.group('target')}_Mean{m.group('exp') or ''}"
        )

    m = re.match(
        r"^(?P<marker>.+)_VolColoc_(?P<target>.+)_Mean(?P<exp>\.exp\d+)?$",
        key_s,
    )
    if m is not None:
        aliases.append(
            f"{m.group('marker')}_Coloc_{m.group('target')}_Mean{m.group('exp') or ''}"
        )
        aliases.append(
            f"{m.group('marker')}_Coloc{m.group('target')}Mean{m.group('exp') or ''}"
        )

    m = _LEGACY_SUMMARY_COLOC_COUNT_RE.match(key_s)
    if m is not None:
        aliases.append(
            f"{m.group('marker')}_Coloc_{m.group('target')}_Count{m.group('pct') or ''}{m.group('exp') or ''}"
        )
        aliases.append(
            f"{m.group('marker')}_VolColoc_{m.group('target')}_Count{m.group('pct') or ''}{m.group('exp') or ''}"
        )

    m = _CANONICAL_SUMMARY_COLOC_COUNT_RE.match(key_s)
    if m is not None:
        aliases.append(
            f"{m.group('marker')}_ColocCount{m.group('target')}{m.group('pct') or ''}{m.group('exp') or ''}"
        )
        aliases.append(
            f"{m.group('marker')}_VolColoc_{m.group('target')}_Count{m.group('pct') or ''}{m.group('exp') or ''}"
        )

    m = re.match(
        r"^(?P<marker>.+)_VolColoc_(?P<target>.+)_Count(?P<pct>(?:%|Raw)?)"
        r"(?P<exp>\.exp\d+)?$",
        key_s,
    )
    if m is not None:
        aliases.append(
            f"{m.group('marker')}_Coloc_{m.group('target')}_Count{m.group('pct') or ''}{m.group('exp') or ''}"
        )
        if (m.group('pct') or "") != "Raw":
            aliases.append(
                f"{m.group('marker')}_ColocCount{m.group('target')}{m.group('pct') or ''}{m.group('exp') or ''}"
            )

    replacement_pairs = [
        ("_Contains_", "_VolContains_"),
        ("_Any_", "_VolAny_"),
        ("_NumColoc_", "_VolNumColoc_"),
        ("_ComboAny_", "_VolComboAny_"),
        ("_Combo_", "_VolCombo_"),
    ]
    for old, new in replacement_pairs:
        if old in key_s and new not in key_s and "_CPC" not in key_s and "_Vol" not in key_s:
            aliases.append(key_s.replace(old, new, 1))
        if new in key_s:
            aliases.append(key_s.replace(new, old, 1))

    return list(dict.fromkeys([a for a in aliases if a != key_s]))


def raw_coloc_column_aliases(key):
    """
    Return equivalent raw per-object coloc spellings with/without the separator.

    Canonical raw overlap columns are now `Marker_Coloc_Target`, but marker-level
    workflows may still refer to the legacy `Marker_ColocTarget` form.
    """
    key_s = str(key).strip()
    if key_s == "" or key_s.endswith("Mean") or key_s.endswith("%"):
        return []

    aliases = []

    m = re.match(r"^(?P<prefix>.+_Coloc)_(?P<target>.+?)(?P<exp>\.exp\d+)?$", key_s)
    if m is not None:
        aliases.append(f"{m.group('prefix')}{m.group('target')}{m.group('exp') or ''}")
        aliases.append(f"{m.group('prefix').replace('_Coloc', '_VolColoc')}_{m.group('target')}{m.group('exp') or ''}")

    m = re.match(r"^(?P<prefix>.+_Coloc)(?P<target>(?!Count)[^_].+?)(?P<exp>\.exp\d+)?$", key_s)
    if m is not None and "_Coloc_" not in key_s:
        aliases.append(f"{m.group('prefix')}_{m.group('target')}{m.group('exp') or ''}")
        aliases.append(f"{m.group('prefix').replace('_Coloc', '_VolColoc')}_{m.group('target')}{m.group('exp') or ''}")

    m = re.match(r"^(?P<prefix>.+_VolColoc)_(?P<target>.+?)(?P<exp>\.exp\d+)?$", key_s)
    if m is not None:
        aliases.append(f"{m.group('prefix').replace('_VolColoc', '_Coloc')}_{m.group('target')}{m.group('exp') or ''}")
        aliases.append(f"{m.group('prefix').replace('_VolColoc', '_Coloc')}{m.group('target')}{m.group('exp') or ''}")

    replacement_pairs = [
        ("_Contains_", "_VolContains_"),
        ("_Any_", "_VolAny_"),
        ("_NumColoc_", "_VolNumColoc_"),
        ("_ComboAny_", "_VolComboAny_"),
        ("_Combo_", "_VolCombo_"),
        ("ColocCount", "VolColocCount"),
    ]
    for old, new in replacement_pairs:
        if old in key_s and new not in key_s and "_CPC" not in key_s and "_Vol" not in key_s:
            aliases.append(key_s.replace(old, new, 1))
        if new in key_s:
            aliases.append(key_s.replace(new, old, 1))

    return list(dict.fromkeys([a for a in aliases if a != key_s]))


def _filter_df_by_specificity_tuple(df, spec_key, raw_vals):
    resolved_key = resolve_column_key(df, spec_key)
    if resolved_key is None:
        return df
    spec_vals = flatten_specificity_values(raw_vals)
    if len(spec_vals) == 0:
        return df
    col = df[resolved_key]
    if (
        pd.api.types.is_object_dtype(col)
        or pd.api.types.is_string_dtype(col)
        or pd.api.types.is_categorical_dtype(col)
    ):
        norm_col = col.astype(str).str.strip().str.casefold()
        norm_vals = {str(v).strip().casefold() for v in spec_vals}
        return df[norm_col.isin(norm_vals)]
    return df[col.isin(spec_vals)]


def filter_df_by_specificity(df, specificity):
    """Filter a DataFrame by a specificity tuple or mapping.

    Tuple syntax filters one column, e.g. ``('Time', 'WeekEight')``.
    Mapping syntax filters all keys with AND semantics, e.g.
    ``{'Sex': 'Female', 'Region': 'SCN'}``.
    """
    if specificity is None:
        return df
    if isinstance(specificity, Mapping):
        out = df
        for key, value in specificity.items():
            raw_vals = list(value) if isinstance(value, (list, tuple, set)) else [value]
            out = _filter_df_by_specificity_tuple(out, key, raw_vals)
        return out
    if not isinstance(specificity, (list, tuple)) or len(specificity) < 2:
        return df
    spec_key, *raw_vals = specificity
    return _filter_df_by_specificity_tuple(df, spec_key, raw_vals)


def specificity_path_parts(specificity):
    """Convert specificity tuple to subfolder path components."""
    if specificity is None:
        return []
    if isinstance(specificity, Mapping):
        parts = []
        for key, value in specificity.items():
            vals = flatten_specificity_values(
                list(value) if isinstance(value, (list, tuple, set)) else [value]
            )
            val_text = " and ".join([str(v) for v in vals])
            parts.append(strip_name(f"{key}.{val_text}" if val_text else str(key)))
        return parts
    if not isinstance(specificity, (list, tuple)) or len(specificity) < 2:
        return []
    spec_key, *raw_vals = specificity
    flat_vals = flatten_specificity_values(raw_vals)
    parts = [strip_name(str(spec_key))]
    if len(flat_vals) == 1:
        parts.append(strip_name(str(flat_vals[0])))
    elif len(flat_vals) > 1:
        combined = " and ".join([str(v) for v in flat_vals])
        parts.append(strip_name(combined))
    return parts


# ── Alias system ──────────────────────────────────────────────────────

def generate_aliases(vocabulary):
    """Build shortest-unambiguous abbreviations for a set of terms.

    Strategy:
    - Terms <= 3 chars are kept as-is.
    - CamelCase terms use initials first (e.g. WeekEight → WE, WeekFour → WF).
    - Other terms start at first 2 chars.
    - Collisions are resolved by extending until unique.

    Parameters
    ----------
    vocabulary : iterable of str
        The terms to abbreviate (factor names, condition values, etc.)

    Returns
    -------
    dict : {original_term: abbreviation}
    """
    import re as _re
    terms = sorted(set(str(t) for t in vocabulary if t is not None))
    aliases = {}
    for t in terms:
        if len(t) <= 3:
            aliases[t] = t
            continue
        # Try CamelCase initials: WeekEight → WE, WeekFour → WF
        camel_parts = _re.findall(r'[A-Z][a-z]*|[a-z]+|[0-9]+', t)
        if len(camel_parts) >= 2:
            initials = ''.join(p[0].upper() for p in camel_parts)
            aliases[t] = initials
        else:
            aliases[t] = t[:2]

    # Resolve collisions by extending abbreviations
    max_iters = 50
    for _ in range(max_iters):
        seen = {}
        collisions = set()
        for term, abbr in aliases.items():
            if abbr in seen:
                collisions.add(term)
                collisions.add(seen[abbr])
            else:
                seen[abbr] = term
        if not collisions:
            break
        for term in collisions:
            cur = aliases[term]
            if len(cur) < len(term):
                aliases[term] = term[:len(cur) + 1]
    return aliases


def apply_alias(term, aliases=None):
    """Look up a term's alias. Falls back to the full term if no alias."""
    if aliases and term in aliases:
        return aliases[term]
    from PyFLASH.config import Config
    if term in Config.ALIASES:
        return Config.ALIASES[term]
    return str(term)


def build_specificity_alias(specificity, aliases=None):
    """Encode a specificity tuple as a compact filename suffix.

    Examples:
        ('Time', 'WeekEight')           → 'TM.W8'   (with aliases)
        ('Time', 'WeekFour', 'WeekEight') → 'TM.W4+W8'
        None                             → ''
    """
    if specificity is None:
        return ''
    if isinstance(specificity, Mapping):
        parts = []
        for key, value in specificity.items():
            vals = flatten_specificity_values(
                list(value) if isinstance(value, (list, tuple, set)) else [value]
            )
            key_alias = apply_alias(str(key), aliases)
            val_aliases = [apply_alias(str(v), aliases) for v in vals]
            parts.append(
                f"{key_alias}.{'+'.join(val_aliases)}" if val_aliases else key_alias
            )
        return "+".join([p for p in parts if p])
    if not isinstance(specificity, (list, tuple)) or len(specificity) < 2:
        return ''
    spec_key, *raw_vals = specificity
    flat_vals = flatten_specificity_values(raw_vals)
    key_alias = apply_alias(spec_key, aliases)
    val_aliases = [apply_alias(str(v), aliases) for v in flat_vals]
    if len(val_aliases) == 0:
        return key_alias
    return f"{key_alias}.{'+'.join(val_aliases)}"


def resolve_roi_bases(roi, experiment):
    """Resolve an roi parameter to a list of ROI base strings.

    None           → all ROI bases from experiment.summaries (default).
    'SCN'          → ['SCN']
    ['SCN', 'OC']  → ['SCN', 'OC']
    """
    if roi is None:
        if hasattr(experiment, 'summaries') and experiment.summaries:
            return sorted(experiment.summaries.keys())
        return ['SCN']
    if isinstance(roi, str):
        return [roi]
    return list(roi)


def build_subfolder(plot_type=None, marker=None, factor=None,
                    specificity=None, aliases=None, roi_base=None,
                    multi_roi=False):
    """Build a save subfolder and filename suffix for a plot.

    Returns (subfolder, suffix) where:
    - subfolder: e.g. 'Iba1/Bars' or 'Matrices' (max 2 levels)
    - suffix: e.g. '--GT.W8' or '' (encoded factor + specificity)

    Single-marker plots go under marker/type/.
    Cross-marker plots go under type/.
    Factor and specificity are encoded into the filename suffix, never as folders.
    When multi_roi is True, roi_base is prepended as a top-level folder.
    """
    parts = []
    if multi_roi and roi_base is not None:
        parts.append(strip_name(str(roi_base)))
    if marker is not None:
        parts.append(strip_name(str(marker)))
    if plot_type is not None:
        parts.append(strip_name(str(plot_type)))
    subfolder = os.path.join(*parts) if parts else None

    suffix_parts = []
    if factor is not None:
        suffix_parts.append(apply_alias(str(factor), aliases))
    spec_alias = build_specificity_alias(specificity, aliases)
    if spec_alias:
        suffix_parts.append(spec_alias)

    suffix = '--' + '--'.join(suffix_parts) if suffix_parts else ''
    return subfolder, suffix


def build_pipeline_suffix(*, block=None, group=None, group_key=None,
                          specificity=None, aliases=None):
    """Encode pipeline run conditions as a compact filename suffix.

    Lets pipeline outputs (correlation matrices, gate matrices, their CSVs) sit
    flat in one folder, distinguished by a concise condition tag, instead of being
    buried in ``<block>/<group>/Matrices/`` subfolders. Tokens are joined with a
    single ``_`` — unlike :func:`build_subfolder`'s ``--`` (which ``save_fig``'s
    ``strip_name`` deletes), ``_`` survives sanitisation, so the *same* tag appears
    on both figures (saved via ``save_fig``) and CSVs (written directly). The
    ``key.value`` / ``+`` grammar of the aliases themselves is unchanged.

    Tokens, in order, when present:
    - ``block``       → bare aliased token, e.g. ``'Raw'`` / ``'Adjusted'``.
    - ``group``       → ``'group_key.group'`` (e.g. ``'GT.WT'``) when a
      ``group_key`` (the ``by``/``factor`` column) is given, else the bare
      aliased group label.
    - ``specificity`` → delegated to :func:`build_specificity_alias`
      (e.g. ``'Dx.AD'``).

    Returns ``''`` when nothing is set.

    Examples:
        block='Adjusted', group='WT', group_key='Genotype'  → '_Adjusted_GT.WT'
        specificity=('Diagnosis', 'AD')                      → '_Dx.AD'
    """
    parts = []
    if block is not None:
        token = apply_alias(str(block), aliases)
        if token:
            parts.append(token)
    if group is not None:
        group_token = apply_alias(str(group), aliases)
        if group_token:
            if group_key is not None:
                key_token = apply_alias(str(group_key), aliases)
                parts.append(f"{key_token}.{group_token}" if key_token else group_token)
            else:
                parts.append(group_token)
    spec_alias = build_specificity_alias(specificity, aliases)
    if spec_alias:
        parts.append(spec_alias)

    if not parts:
        return ''
    # Sanitise so the tag is filesystem-safe AND identical on figures (which
    # ``save_fig`` re-runs through ``strip_name``) and CSVs (written directly).
    # Without this, a token containing a stripped char (e.g. ``-``) would survive
    # in the CSV name but vanish from the figure name. ``strip_name`` keeps ``_``,
    # ``.`` and ``+`` (our separators/grammar) and removes ``-``/``:``/``/`` etc.
    return strip_name('_' + '_'.join(parts))


# ── String helpers ─────────────────────────────────────────────────────

def strip_name(name):
    """Sanitise a string for use as a filename."""
    for ch in ['-', "'", '<', '>', ':', '%', '³', '\n']:
        name = name.replace(ch, '')
    name = name.replace('/', 'per').replace('//', '').replace('\\', '')
    return name


def normalize_image_roi_name(name):
    """Normalize ROI/image labels to the file-style form used in image names.

    Handles both legacy SCN-only names and general Hemisphere+Region names.
    """
    value = str(name).strip()
    if value == "":
        return ""

    compact = re.sub(r"[\s_]+", "", value).upper()

    # Already in image-file form with hemisphere prefix, e.g. LHSCN1, RHOC1
    match = re.fullmatch(r"(LH|RH)(\w+\d+)", compact)
    if match is not None:
        return compact

    # Legacy: LHSCN / RHSCN (no digit) — keep as-is
    match = re.fullmatch(r"(LH|RH)SCN(\d*)", compact)
    if match is not None:
        side, idx = match.groups()
        idx = "" if idx in {"", "1"} else idx
        return f"{side}SCN{idx}"

    # ROI zip form, e.g. SCN, SCN-1, SCN2, SCN2-1
    match = re.fullmatch(r"SCN(\d*)(?:-(\d+))?", compact)
    if match is not None:
        idx, side_suffix = match.groups()
        idx = "" if idx in {"", "1"} else idx
        side = "RH" if side_suffix == "1" else "LH"
        return f"{side}SCN{idx}"

    # General region name (e.g. OC1) — return as-is
    return compact


def normalize_animal_name(name):
    """Normalize animal identifiers for cross-source matching."""
    value = replace_week_int(str(name).strip())
    if value == "":
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def format_elapsed(seconds):
    """Format elapsed seconds as HH:MM:SS."""
    seconds = max(0.0, float(seconds))
    return time.strftime("%H:%M:%S", time.gmtime(int(round(seconds))))


class ProgressTracker:
    """Notebook/terminal-friendly progress display with timing and ETA."""

    def __init__(self, name, total, unit="item", enabled=True):
        self.name = str(name)
        self.total = max(0, int(total))
        self.unit = str(unit)
        self.enabled = bool(enabled)
        self.completed = 0
        self.sum_time = 0.0
        self.run_start = time.perf_counter()
        self.item_start = None
        self.current_item = None
        self.detail = None
        self._closed = False
        self._handle = None

        if self.enabled:
            try:
                from IPython.display import display
                self._handle = display("", display_id=True)
            except Exception:
                self._handle = None

    def start_item(self, item_name=None, detail=None):
        if self._closed:
            return
        self.item_start = time.perf_counter()
        self.current_item = None if item_name is None else str(item_name)
        self.detail = None if detail is None else str(detail)
        self._render(in_progress=True)

    def finish_item(self, item_name=None, detail=None, step=1):
        if self._closed:
            return
        if item_name is not None:
            self.current_item = str(item_name)
        if detail is not None:
            self.detail = str(detail)
        if self.item_start is not None:
            self.sum_time += (time.perf_counter() - self.item_start)
        self.item_start = None
        self.completed = min(self.total, self.completed + int(step)) if self.total > 0 else self.completed + int(step)
        self._render(in_progress=False)

    def close(self, detail=None):
        if self._closed:
            return
        if self.item_start is not None:
            self.sum_time += (time.perf_counter() - self.item_start)
            self.item_start = None
        if detail is not None:
            self.detail = str(detail)
        if self.total > 0:
            self.completed = self.total
        self._render(in_progress=False, completed=True)
        self._closed = True
        if self._handle is None and self.enabled:
            import sys
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _render(self, in_progress=False, completed=False):
        if not self.enabled:
            return

        total = max(1, self.total)
        done = min(self.completed, total)
        shown = min(done + (1 if in_progress and done < total else 0), total)
        pct = 100.0 if self.total == 0 else (shown / total) * 100.0
        bar_width = 28
        fill = bar_width if self.total == 0 else int((shown / total) * bar_width)
        bar = "█" * fill + "." * (bar_width - fill)
        elapsed = time.perf_counter() - self.run_start

        if done > 0:
            avg = (self.sum_time / done) if self.sum_time > 0 else (elapsed / done)
            remaining = max(0, total - done)
            eta_text = format_elapsed(avg * remaining)
            avg_text = f"{avg:.2f}s/{self.unit}"
        else:
            eta_text = "estimating..."
            avg_text = "n/a"

        status = self.current_item or ("Complete" if completed else "Working")
        total_label = self.total if self.total > 0 else 0
        lines = [
            f"[{self.name}] {shown}/{total_label} {self.unit}s: {status}",
            f"[{bar}] {pct:5.1f}%",
            f"Elapsed: {format_elapsed(elapsed)} | ETA: {eta_text} | Avg/{self.unit}: {avg_text}",
        ]
        if self.detail:
            lines.append(str(self.detail))
        msg = "\n".join(lines)

        if self._handle is not None:
            try:
                import html as _html
                from IPython.display import HTML
                self._handle.update(HTML(f"<pre style='margin:0'>{_html.escape(msg)}</pre>"))
            except Exception:
                self._handle.update(msg)
        else:
            import sys
            sys.stdout.write("\r\033[2K")
            sys.stdout.write(msg)
            sys.stdout.flush()


def clean_column_name(name):
    """Standardise column names from ImageJ CSV output."""
    return (name
            .replace("Colocalisation with ", "Coloc_")
            .replace(" ", "")
            .replace("(micron^3)", "")
            .replace("(micron^2)", ""))


# ── DataFrame helpers ──────────────────────────────────────────────────

def add_suffix(df, columns, suffix):
    """Append a suffix to specified column names."""
    rename_map = {col: col + suffix for col in columns}
    return df.rename(columns=rename_map)


def get_columns(df, column_strings=None, regex_string=None, exclude=''):
    """
    Select column names by substring match or regex.

    Parameters
    ----------
    df : DataFrame
    column_strings : list of str, optional
        Return columns containing any of these substrings.
    regex_string : str, optional
        Return columns matching this regex.
    exclude : str or list of str
        Exclude columns containing any of these substrings.
    """
    if exclude != "" and isinstance(exclude, str):
        exclude = [exclude]
    if column_strings is not None:
        return [col for col in df.columns
                if any(s in col for s in column_strings)
                and not any(s in col for s in exclude)]
    else:
        return [col for col in df.filter(regex=regex_string).columns.tolist()
                if not any(s in col for s in exclude)]


def get_nonobject_columns(df):
    """Separate text metadata from columns used for numeric summaries."""
    # Pandas 3 infers text as StringDtype rather than object. Keep both in
    # the metadata path so subject labels and covariates are never averaged.
    other = [col for col in df.columns
             if pd.api.types.is_object_dtype(df[col].dtype)
             or pd.api.types.is_string_dtype(df[col].dtype)]
    numeric = [col for col in df.columns if col not in other]
    return numeric, other


def extract_region_base(region_name):
    """SCN1 → SCN, OC1 → OC. Strips trailing digits."""
    return re.sub(r'\d+$', '', str(region_name).strip())


def normalize_hemisphere(value):
    """Normalize hemisphere values: L→LH, R→RH, LH→LH, RH→RH, empty→''."""
    v = str(value).strip().upper()
    if v in ('L', 'LH'):
        return 'LH'
    if v in ('R', 'RH'):
        return 'RH'
    return ''


def adjust_for_volumemm(df, columns, volume_column):
    """Normalize selected measurements per 0.1 cubic millimetres of tissue.

    The historical ``volume_column`` argument names an area in square
    micrometres. Multiply that original area by the configured section
    thickness in micrometres, even when the area itself is a selected target.
    Each requested column is normalized once; validation precedes all writes.
    Missing areas or measurements give missing outputs.
    """
    from PyFLASH.config import Config
    if not df.columns.is_unique:
        raise ValueError("Volume-normalization columns must have unique names.")
    columns = list(dict.fromkeys([columns] if isinstance(columns, str) else columns))
    if not columns:
        return df
    missing = [name for name in [volume_column] + columns if name not in df.columns]
    if missing:
        raise KeyError("Missing volume-normalization columns: " + str(missing))
    thickness = _finite_real_fraction(Config.SECTION_THICKNESS_UM,
        label="Section thickness", allow_missing=False, positive=True)
    areas = [_finite_real_fraction(value, label="Tissue area", positive=True)
             for value in df[volume_column]]
    computed = {}
    for name in columns:
        values = []
        for value, area in zip(df[name], areas):
            measurement = _finite_real_fraction(value, label="Measurements")
            if measurement is None or area is None:
                values.append(np.nan)
            else:
                try:
                    values.append(float(measurement * 100000000 / (area * thickness)))
                except OverflowError as error:
                    raise ValueError("Normalized measurement exceeds the supported floating-point range.") from error
        computed[name] = np.asarray(values, dtype=float)
    for name, values in computed.items():
        df[name] = values
    return df


def add_coloc_percentages(df):
    """Add percentages for exact positive/negative count-column pairs.

    Preserve original columns and append new percentages in count-name order.
    Existing percentage columns are refreshed, never used as counts themselves.
    Counts must be finite, nonnegative integers or floats; missing counts give
    missing percentages. Calculate each percentage from the represented counts
    before rounding, so a large sum or tiny fraction cannot erase a percentage.
    """
    if not df.columns.is_unique:
        raise ValueError("Colocalisation count columns must have unique names.")
    token = '_NonColocCount'
    pairs = {}
    for negative in df.columns:
        if not isinstance(negative, str) or negative.endswith('%'):
            continue
        candidates = []
        for match in re.finditer(re.escape(token), negative):
            positive = negative[:match.start()]+'_ColocCount'+negative[match.end():]
            if positive in df.columns:
                candidates.append(positive)
        if len(candidates) > 1:
            raise ValueError("Ambiguous colocalisation count pair: " + negative)
        if candidates:
            positive = candidates[0]
            if positive in pairs and pairs[positive] != negative:
                raise ValueError("Ambiguous colocalisation count pair: " + positive)
            pairs[positive] = negative
    computed = {}
    for positive in sorted(pairs):
        negative = pairs[positive]
        positive_percentages = []
        negative_percentages = []
        for positive_count, negative_count in zip(df[positive], df[negative]):
            numerator = _finite_real_fraction(positive_count, label="Colocalisation counts", nonnegative=True)
            remainder = _finite_real_fraction(negative_count, label="Colocalisation counts", nonnegative=True)
            if numerator is None or remainder is None or numerator + remainder == 0:
                positive_percentages.append(np.nan)
                negative_percentages.append(np.nan)
            else:
                total = numerator + remainder
                positive_percentages.append(float(100 * numerator / total))
                negative_percentages.append(float(100 * remainder / total))
        computed[positive+'%'] = np.asarray(positive_percentages, dtype=float)
        computed[negative+'%'] = np.asarray(negative_percentages, dtype=float)
    # All pairs must be computable before any existing table field is changed.
    for name, values in computed.items():
        df[name] = values
    return df


# ── Numeric helpers ────────────────────────────────────────────────────

def round_up_to_nearest_5(x):
    """Return the next half-decade plot bound that encloses the input.

    Compare the converted floating-point bounds, preserving familiar decimal
    boundaries such as 0.4. Missing and zero inputs retain their zero bound.
    Refuse an input or rounded bound that cannot be represented on the plot.
    """
    from decimal import Decimal, ROUND_CEILING, localcontext
    supplied = _finite_real_fraction(x, label="Axis bound")
    if supplied is None or supplied == 0:
        return 0
    if abs(supplied) > float.fromhex('0x1.fffffffffffffp+1023'):
        raise ValueError("Axis bound exceeds the supported floating-point range.")
    with localcontext() as context:
        # Every binary64 input has a terminating decimal representation with
        # fewer than 1,100 digits. This also makes the division by 5 exact.
        context.prec = 2200
        value = Decimal(supplied.numerator) / Decimal(supplied.denominator)
        increment = Decimal(5).scaleb(value.copy_abs().adjusted() - 1)
        multiplier = (value / increment).to_integral_value(rounding=ROUND_CEILING)
        while float((multiplier - 1) * increment) >= supplied:
            multiplier -= 1
        rounded = float(multiplier * increment)
    if not math.isfinite(rounded):
        raise ValueError("Rounded axis bound exceeds the supported floating-point range.")
    return rounded


def flatten(xss):
    """Flatten a list of lists."""
    return [x for xs in xss for x in xs]


def remove_none(data):
    """Remove None values from a list."""
    return [x for x in data if x is not None]


def convert_microns_to_pixels(microns, pixel_size=None):
    """Convert micrometres using explicit um/px or default px/um calibration."""
    from PyFLASH.config import Config
    calibration, direct_default = _pixel_conversion_scale(pixel_size, Config.PIXEL_SIZE)
    return _calibrated_conversion(microns, calibration, multiply=direct_default)


def convert_pixels_to_microns(pixels, pixel_size=None):
    """Convert pixels using explicit um/px or default px/um calibration."""
    from PyFLASH.config import Config
    calibration, direct_default = _pixel_conversion_scale(pixel_size, Config.PIXEL_SIZE)
    return _calibrated_conversion(pixels, calibration, multiply=not direct_default)


# ── Geometry / ROI helpers ─────────────────────────────────────────────

def _numeric_array_preserving_integers(values):
    """Delay a lossy mixed integer/float conversion until after arithmetic."""
    array = np.asarray(values)
    if isinstance(values, np.ndarray) or array.dtype.kind not in 'fc':
        return array
    supplied = np.asarray(values, dtype=object)
    for value, converted in zip(supplied.flat, array.flat):
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, int) and value != float(converted.real):
            return supplied
    return array


def _real_coordinate_array(values, *, label, allow_zero_imaginary=False):
    """Keep integer coordinates exact when another cell is a floating value."""
    array = _numeric_array_preserving_integers(values)
    if array.dtype.kind in 'biuf' and isinstance(values, np.ndarray):
        if not np.isfinite(array).all():
            raise ValueError(label + ' needs finite real coordinates.')
        return array
    supplied = np.array(values, dtype=object, copy=True)
    keep_exact = array.dtype.kind == 'O'
    for index, value in enumerate(supplied.flat):
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, complex):
            if not allow_zero_imaginary or value.imag != 0:
                raise ValueError(label + ' needs finite real coordinates.')
            value = value.real
        if not isinstance(value, (bool, int, float)) or isinstance(value, float) and not math.isfinite(value):
            raise ValueError(label + ' needs finite real coordinates.')
        supplied.flat[index] = value
        if isinstance(value, int) and array.dtype.kind in 'fc' and value != float(array.flat[index].real):
            keep_exact = True
    if array.dtype.kind not in 'biufcO':
        raise ValueError(label + ' needs finite real coordinates.')
    if keep_exact:
        return supplied
    return array.real if array.dtype.kind == 'c' else array


def trace_downward_nearest(x, y):
    """Trace downward with exact nearest-point ordering and original row indices.

    Distances and the slope cutoff use the exact represented coordinates.
    An enclosing vertical bound excludes distant points before comparison;
    approximate proposals can tighten that bound but never select the path.
    """
    from bisect import bisect_right
    try:
        x = _real_coordinate_array(x, label='Tracing')
        y = _real_coordinate_array(y, label='Tracing')
    except ValueError as error:
        raise ValueError('Tracing needs paired finite one-dimensional real coordinates with at least two points.') from error
    if (x.ndim!=1 or y.ndim!=1 or len(x)!=len(y) or len(x)<2
):
        raise ValueError('Tracing needs paired finite one-dimensional real coordinates with at least two points.')
    if y.min()==y.max():
        raise ValueError('Coordinates cannot form a downward path within the slope limit.')
    ratios=[value.as_integer_ratio() for value in x.tolist()+y.tolist()]
    denominator=max(value[1] for value in ratios)
    coordinates=[numerator*(denominator//divisor) for numerator,divisor in ratios]
    x_grid=np.asarray(coordinates[:len(x)],dtype=object)
    y_grid=np.asarray(coordinates[len(x):],dtype=object)
    y_order=np.argsort(y,kind='stable')
    y_sorted=y_grid[y_order]
    starts=sorted(range(len(x)),key=lambda i:(y_grid[i],-x_grid[i],i))
    def squared_distance(first,second):
        dx=x_grid[first]-x_grid[second];dy=y_grid[first]-y_grid[second]
        return dx*dx+dy*dy
    for start in starts:
        path=[start];cur=start
        while True:
            lower=bisect_right(y_sorted,y_grid[cur])
            if lower==len(y_sorted):break
            first=int(y_order[lower])
            bound=squared_distance(first,cur)
            upper=bisect_right(y_sorted,y_grid[cur]+math.isqrt(bound),lo=lower)
            if upper-lower>32:
                eligible=y_order[lower:upper]
                # This is a proposal only. Its exact distance supplies an
                # enclosing bound even if the approximate choice is wrong.
                try:
                    with np.errstate(all='ignore'):
                        dx=np.asarray(x[eligible],dtype=float)-float(x[cur])
                        dy=np.asarray(y[eligible],dtype=float)-float(y[cur])
                        proposal=int(eligible[np.argmin(np.hypot(dx,dy))])
                    bound=min(bound,squared_distance(proposal,cur))
                except OverflowError:
                    pass  # Exact bounds still choose the path; the proposal is optional.
                upper=bisect_right(y_sorted,y_grid[cur]+math.isqrt(bound),lo=lower)
            candidates=np.sort(y_order[lower:upper])
            dx=x_grid[candidates]-x_grid[cur]
            dy=y_grid[candidates]-y_grid[cur]
            nxt=int(candidates[np.argmin(dx*dx+dy*dy)])
            if x_grid[nxt]-x_grid[cur] < -2*(y_grid[nxt]-y_grid[cur]):break
            path.append(nxt);cur=nxt
        if len(path)>1:
            indices=np.asarray(path,dtype=int)
            return x[indices],y[indices],indices
        if lower==len(y_sorted):break
    raise ValueError('Coordinates cannot form a downward path within the slope limit.')


def moving_average(a, w=7):
    """Padded moving average, preserving small values and cancellation.

    Widths below two retain the historical no-op. Even widths retain the
    historical output length of one more than the input. Real NumPy numeric
    inputs through float64 are averaged from their exact represented values;
    complex64/complex128 components use the same exact averaging. Object
    arrays of supported Python/NumPy numeric scalars use that averaging and
    retain object output dtype. Other carriers retain convolution behaviour.
    """
    supplied_a = a
    a = np.asarray(a)
    if w < 2:
        return a
    input_dtype = a.dtype
    a = _numeric_array_preserving_integers(supplied_a)
    from operator import index
    w = index(w)
    if a.ndim != 1:
        raise ValueError("Moving averages need a one-dimensional signal.")
    object_numeric = False
    if a.dtype.kind == 'O' and a.ndim == 1:
        supplied = a.tolist()
        def supported(value):
            if type(value) in (bool, int, float, complex):
                return True
            if isinstance(value, np.generic):
                return (value.dtype.kind in 'biu'
                        or value.dtype.kind == 'f' and value.dtype.itemsize <= 8
                        or value.dtype.kind == 'c' and value.dtype.itemsize <= 16)
            return False
        if all(supported(value) for value in supplied):
            if any(isinstance(value, (complex, np.complexfloating)) for value in supplied):
                real = moving_average(np.asarray([value.real for value in supplied], dtype=object), w)
                imaginary = moving_average(np.asarray([value.imag for value in supplied], dtype=object), w)
                return np.asarray([complex(r, i) for r, i in zip(real, imaginary)], dtype=object if input_dtype.kind == 'O' else np.complex128)
            object_numeric = True
    if a.dtype.kind == 'c' and a.dtype.itemsize <= 16:
        if a.ndim != 1:
            raise ValueError("Moving averages need a one-dimensional signal.")
        real = moving_average(a.real, w)
        imaginary = moving_average(a.imag, w)
        result = np.empty(real.shape, dtype=np.complex128)
        result.real = real
        result.imag = imaginary
        return result
    pad = w // 2
    ap = np.pad(a, (pad, pad), mode="edge")
    if not object_numeric and (a.dtype.kind not in 'biuf' or a.dtype.kind == 'f' and a.dtype.itemsize > 8):
        return np.convolve(ap, np.ones(w) / w, mode="valid")
    if a.ndim != 1:
        raise ValueError("Moving averages need a one-dimensional signal.")
    # Binary integer coordinates avoid an overflowing sum or an underflowing
    # per-observation weight. Missing/infinite windows keep their own states.
    ratios = []
    states = []
    for value in ap.tolist():
        if object_numeric and isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, int):
            ratios.append((value, 1)); states.append(0)
        elif math.isnan(value):
            ratios.append((0, 1)); states.append(1)
        elif math.isinf(value):
            ratios.append((0, 1)); states.append(2 if value > 0 else 3)
        else:
            ratios.append(value.as_integer_ratio()); states.append(0)
    denominator = max(divisor for _, divisor in ratios)
    values = [numerator * (denominator // divisor) for numerator, divisor in ratios]
    total = sum(values[:w])
    counts = [states[:w].count(state) for state in range(4)]
    result = []
    divisor = denominator * w
    for start in range(len(values) - w + 1):
        if counts[1] or counts[2] and counts[3]:
            result.append(np.nan)
        elif counts[2]:
            result.append(np.inf)
        elif counts[3]:
            result.append(-np.inf)
        else:
            result.append(total / divisor)
        end = start + w
        if end < len(values):
            total += values[end] - values[start]
            counts[states[end]] += 1
            counts[states[start]] -= 1
    return np.asarray(result, dtype=object if object_numeric and input_dtype.kind == 'O' else float)


def points_to_polyline_distance(px, py, x_line, y_line):
    """Return distances and nearest boundary points, keeping first-segment ties."""
    supplied = (px, py, x_line, y_line)
    original_arrays = None if all(isinstance(values, np.ndarray) and values.dtype.kind == 'f' for values in supplied) else [np.array(values, dtype=object, copy=True) for values in supplied]
    if original_arrays is not None:
        for values in original_arrays:
            for index, value in enumerate(values.flat):
                if isinstance(value, (complex, np.complexfloating)):
                    if value.imag != 0:
                        raise ValueError('Point and polyline coordinates must be real.')
                    values.flat[index] = value.real
    arrays = [np.asarray(values, dtype=float) for values in (supplied if original_arrays is None else original_arrays)]
    if any(values.ndim != 1 for values in arrays):
        raise ValueError('Point and polyline coordinates must be one-dimensional.')
    px, py, x_line, y_line = arrays
    if len(px) != len(py) or len(x_line) != len(y_line):
        raise ValueError('Each coordinate pair must have matching lengths.')
    if len(x_line) < 2:
        raise ValueError('A polyline requires at least two vertices.')
    if any(not np.isfinite(values).all() for values in arrays):
        raise ValueError('Point and polyline coordinates must be finite.')
    if not len(px):
        return np.empty(0, dtype=float), np.empty((0, 2), dtype=float)
    integer_precision_lost = original_arrays is not None and any(
        isinstance(value, (int, np.integer)) and int(value) != float(converted)
        for original, floating in zip(original_arrays, arrays)
        for value, converted in zip(original.flat, floating.flat)
    )
    if integer_precision_lost:
        return _exact_polyline_distance(*original_arrays)
    pxx, pyy = px[:, None], py[:, None]
    x0, y0 = x_line[:-1][None, :], y_line[:-1][None, :]
    x1, y1 = x_line[1:][None, :], y_line[1:][None, :]
    with np.errstate(over='ignore', invalid='ignore'):
        dx, dy = x1-x0, y1-y0
        ox, oy = pxx-x0, pyy-y0
    extreme = False
    for values in (dx, dy, ox, oy):
        absolute = np.abs(values)
        nonzero = absolute[absolute != 0]
        if not np.isfinite(values).all() or (nonzero.size and
                (nonzero.max() > 1e150 or nonzero.min() < 1e-150)):
            extreme = True
            break
    if extreme:
        return _exact_polyline_distance(px, py, x_line, y_line)
    seg_len2 = dx*dx + dy*dy
    seg_len2 = np.where(seg_len2 == 0, 1., seg_len2)
    t = np.clip((ox*dx + oy*dy)/seg_len2, 0., 1.)
    cx, cy = x0+t*dx, y0+t*dy
    d2 = (pxx-cx)**2 + (pyy-cy)**2
    best = d2.argmin(axis=1)
    return np.sqrt(d2.min(axis=1)), np.column_stack((cx[np.arange(len(px)), best], cy[np.arange(len(px)), best]))


def filter_dict(my_dict, key_substring):
    """Filter a dict to keys containing a substring."""
    return {k: v for k, v in my_dict.items() if key_substring in k}


# ── Plotting helpers ───────────────────────────────────────────────────

def rc_params(line_width=2, tick_major_width=2, tick_major_size=11,
              tick_label_size=20, font_weight='normal', font_family='Arial',
              labelsize=22, labelweight='normal',
              title_size=20, title_weight='bold',
              despine=True, legend_frame=False, legend_fontsize=15,
              tick_direction='out', figure_size=(7.0, 5.0),
              save_bbox='fixed', save_pad_inches=0.1, save_dpi=600):
    """Set matplotlib rcParams for PyFLASH's uniform house aesthetic.

    Compatibility helper: prefer ``PyFLASH.set_pyflash_style()`` for new code.
    That front door applies these Matplotlib defaults plus PyFLASH semantic
    styling such as marker sizes, significance annotations, and matrix colours.

    The defaults encode the look of the reference plots (bar charts and
    correlation matrices): Arial, bold axis labels, bold titles, despined
    top/right spines, frameless legends, and thick ticks/spines. Because these
    are matplotlib *rcParams*, every plot — current and future — inherits them
    automatically *unless the plotting code hard-codes its own value*; so new
    plot functions get the house style for free.

    The originals from the analysis notebook
    (``font_weight='normal', tick_label_size=20, tick_major_size=11,
    tick_major_width=2, line_width=2``) remain the defaults, so the notebook's
    explicit call is unchanged. Pass any argument to override one knob.

    Notes
    -----
    Colour is intentionally *not* set here (no ``axes.prop_cycle``) — palette is
    handled per plot. ``despine`` toggles ``axes.spines.top/right`` (heatmaps are
    unaffected since their cells fill the axes); polar/3D axes ignore it.
    """
    from matplotlib import pyplot as plt
    from PyFLASH.config import apply_matplotlib_fast_path
    apply_matplotlib_fast_path()
    bbox_rc = (
        "standard"
        if str(save_bbox).strip().lower() in {"standard", "canvas", "none", "false"}
        else "tight"
    )
    updates = {
        'axes.linewidth': line_width,
        'xtick.major.width': tick_major_width,
        'ytick.major.width': tick_major_width,
        'xtick.major.size': tick_major_size,
        'ytick.major.size': tick_major_size,
        'xtick.labelsize': tick_label_size,
        'ytick.labelsize': tick_label_size,
        'xtick.direction': tick_direction,
        'ytick.direction': tick_direction,
        'axes.labelsize': labelsize,
        'axes.labelweight': labelweight,
        'axes.titlesize': title_size,
        'axes.titleweight': title_weight,
        'axes.spines.top': not despine,
        'axes.spines.right': not despine,
        'legend.frameon': legend_frame,
        'legend.fontsize': legend_fontsize,
        'legend.title_fontsize': legend_fontsize,
        'font.weight': font_weight,
        'font.family': font_family,
        'savefig.dpi': save_dpi,
        'savefig.bbox': bbox_rc,
        'savefig.pad_inches': save_pad_inches,
        # Keep SVG text editable (real <text>, not glyph paths) and render any
        # mathtext ($…$) in the house body font rather than DejaVu-oblique.
        'svg.fonttype': 'none',
        'mathtext.default': 'regular',
    }
    if figure_size is not None:
        updates['figure.figsize'] = figure_size
    plt.rcParams.update(updates)



def rasterize_data_artists(figure, threshold=50):
    """Mark dense data artists as rasterized for faster SVG saving.

    Collections (scatter, violin, strip), patch collections, and images
    with more than *threshold* elements are rasterized.  Text, spines,
    and axes structure remain vector for crisp labels in the SVG.
    """
    for ax in figure.get_axes():
        for coll in ax.collections:
            try:
                if hasattr(coll, 'get_offsets') and len(coll.get_offsets()) > threshold:
                    coll.set_rasterized(True)
            except Exception:
                pass
        for patch in ax.patches:
            try:
                patch.set_rasterized(False)
            except Exception:
                pass


_DIRECT_FIGURE_EXTENSIONS = {
    "svg", "pdf", "png", "jpg", "jpeg", "jpe", "tif", "tiff",
    "webp", "avif", "heic", "heif",
}


def _normalise_figure_formats(values):
    if isinstance(values, str):
        values = [values]
    normalised = []
    for value in values or ():
        extension = str(value).strip().lower().lstrip(".")
        if extension not in _DIRECT_FIGURE_EXTENSIONS:
            raise ValueError(
                f"Unsupported direct figure format {value!r}. Use one of "
                f"{sorted(_DIRECT_FIGURE_EXTENSIONS)}, or use "
                "PyFLASH.publication.embed_file for an existing document or "
                "scientific container."
            )
        if extension not in normalised:
            normalised.append(extension)
    if not normalised:
        raise ValueError("At least one figure format is required")
    return normalised


def _format_options_for(options, extension):
    if not options:
        return None
    keys = {str(key).lower().lstrip(".") for key in options}
    if keys & _DIRECT_FIGURE_EXTENSIONS:
        aliases = {
            "jpg": "jpeg", "jpe": "jpeg", "tif": "tiff", "heic": "heif"
        }
        requested = aliases.get(extension, extension)
        for key, value in options.items():
            candidate = aliases.get(str(key).lower().lstrip("."), str(key).lower().lstrip("."))
            if candidate == requested:
                return dict(value or {})
        return None
    return dict(options)


def save_fig(figure, save_path, image_name, extra_artist=None,
             pad_inches=None, subfolder=None, verbose=True,
             skip_existing=None, rasterize=True, montage=False,
             save_bbox=None, figure_profile=None,
             figure_safe_columns=None, public_sources=None,
             write_companion_csv=None, figure_formats=None, dpi=None,
             dpi_preset=None, render_preset=None, width=None, height=None,
             format_options=None, allow_reencode=None, transparent=True,
             sanitize_name=True, proof=None, proof_policy=None, preview_of=None):
    """Save one audited figure to every requested direct ReproFig carrier.

    Parameters
    ----------
    skip_existing : bool or None
        If True, skip saving when the output file already exists.
        None falls back to ``Config.SKIP_EXISTING``.
    montage : bool
        Hint passed through to any registered figure-save observer (see
        ``register_fig_save_observer``) marking this figure as a *headline*
        figure for the pipeline montage layer. Has no effect on the saved file;
        it only flags the figure as one of a run's most important graphs so
        ``PyFLASH.pipeline_montage`` puts it on the overview montage.
    save_bbox : {"fixed", "tight"}, optional
        Per-figure override for the active PyFLASH export geometry. ``None``
        keeps the global style. Use ``"tight"`` for figures whose authored
        width carries meaning, such as compact mean bars with one slot per
        group.
    figure_profile : {"master", "public", "minimal_public"}, optional
        Embedded record profile. ``None`` uses ``Config.FIGURE_PROFILE``.
        Public profiles are privacy-validated before the target is replaced.
    figure_safe_columns : sequence or mapping, optional
        Explicit public column allowlist. Required for unclassified tables.
    public_sources : mapping, optional
        Approved replacements for internal source references.
    write_companion_csv : bool, optional
        Also write disposable data/statistics CSV files beside the figure. The
        master remains self-contained when these files are absent.
    figure_formats : sequence of str, optional
        Direct output carriers. ``None`` uses ``Config.FIGURE_FORMATS``. SVG,
        PDF, PNG, JPEG, TIFF, WebP, AVIF and HEIF are supported and all receive
        the same ReproFig identity. Existing documents and scientific
        containers are handled by ``PyFLASH.publication.embed_file``.
    dpi, dpi_preset, render_preset : optional
        Exact dots per inch, or ReproFig's ``screen``, ``continuous_tone`` or
        ``line_art`` preset. Exact ``dpi`` wins.
    width, height : float, optional
        Render dimensions in inches. Supplying one preserves the aspect ratio.
    format_options : mapping, optional
        Encoder options for every format, or a mapping keyed by format.
    transparent : bool
        Preserve a transparent canvas when the chosen carrier supports it.
    sanitize_name : bool
        Remove legacy filesystem-hostile characters from ``image_name``. Set
        false only when the caller has already supplied a deliberate filename.
    proof : bool, optional
        Capture semantic marks and a shared proof root. The default remains off.
    preview_of : path, optional
        Render an auxiliary preview from this figure's producing save call.
        Written carriers retain their identity and evidence. Skipped/no-write
        calls use fresh evidence, preserving the old carrier and pending saves.
        Preview rendering preserves privacy and pixels, does not notify output
        or montage observers, and refuses a changed or unrelated primary file.
    proof_policy : mapping, optional
        Required verification meanings plus non-secret signing, trust and
        encryption references. Password values are accepted only through the
        named environment-variable fields in the policy.
    """
    from matplotlib import pyplot as plt
    from PyFLASH.config import Config, apply_matplotlib_fast_path
    from PyFLASH.aesthetics import (
        _apply_presentation,
        apply_pyflash_figure_geometry,
        normalize_pyflash_svg_canvas,
        pyflash_savefig_kwargs,
    )
    apply_matplotlib_fast_path()
    is_preview = preview_of is not None
    preview_record = None
    if is_preview:
        evidence = getattr(figure, "_pyflash_preview_evidence", {}).get(os.path.abspath(preview_of))
        if os.path.isfile(preview_of):
            from reprofig import extract_record
            saved = extract_record(preview_of)
            if evidence is not None and evidence["written"]:
                from PyFLASH._cache_identity import file_hash
                if file_hash(preview_of) != evidence["sha256"]:
                    raise ValueError("Primary figure changed after this render.")
        if evidence is None:
            raise ValueError("Preview source does not belong to this figure render.")
        preview_record = evidence["record"]
    else:
        figure._pyflash_preview_evidence = {}
    fixed_canvas = not is_preview and bool(getattr(figure, "_pyflash_fixed_canvas", False))

    def _windows_extended_path(path):
        if os.name != "nt":
            return path
        abs_path = os.path.abspath(path)
        if abs_path.startswith("\\\\?\\"):
            return abs_path
        if abs_path.startswith("\\\\"):
            return "\\\\?\\UNC\\" + abs_path.lstrip("\\")
        return "\\\\?\\" + abs_path

    image_name = strip_name(image_name) if sanitize_name else str(image_name)
    if subfolder is not None:
        save_path = os.path.join(save_path, subfolder)

    selected_formats = _normalise_figure_formats(
        figure_formats
        if figure_formats is not None
        else getattr(Config, "FIGURE_FORMATS", ("svg",))
    )
    full_paths = [
        os.path.join(save_path, f"{image_name}.{extension}")
        for extension in selected_formats
    ]
    full_path = full_paths[0]

    save_full_paths = list(full_paths)
    # Warn if path approaches Windows MAX_PATH limit, then save through the
    # extended-length path prefix so long metric names still write correctly.
    if os.name == "nt" and len(full_path) > 245:
        warnings.warn(
            f"Path length ({len(full_path)} chars) exceeds 245. "
            f"Consider setting Config.ALIASES or shortening the base path. "
            f"Path: {full_path}",
            stacklevel=2,
        )
        save_full_paths = [_windows_extended_path(path) for path in full_paths]

    use_skip = skip_existing if skip_existing is not None else Config.SKIP_EXISTING
    selected_profile = (
        figure_profile
        if figure_profile is not None
        else getattr(Config, "FIGURE_PROFILE", "master")
    )
    if preview_record is not None:
        selected_profile = preview_record.distribution_profile
    if selected_profile not in {"master", "public", "minimal_public"}:
        raise ValueError(
            "figure_profile must be 'master', 'public', or 'minimal_public'"
        )
    if figure_safe_columns is None:
        figure_safe_columns = getattr(Config, "FIGURE_SAFE_COLUMNS", None)
    if public_sources is None:
        public_sources = getattr(Config, "FIGURE_PUBLIC_SOURCES", None)
    if write_companion_csv is None:
        write_companion_csv = bool(getattr(Config, "FIGURE_COMPANION_CSV", False))
    if dpi is None:
        dpi = getattr(Config, "FIGURE_DPI", None)
    if dpi_preset is None:
        dpi_preset = getattr(Config, "FIGURE_DPI_PRESET", None)
    if render_preset is None:
        render_preset = getattr(Config, "FIGURE_RENDER_PRESET", None)
    if width is None and not is_preview:
        width = getattr(Config, "FIGURE_WIDTH", None)
    if height is None and not is_preview:
        height = getattr(Config, "FIGURE_HEIGHT", None)
    if format_options is None:
        format_options = getattr(Config, "FIGURE_FORMAT_OPTIONS", None)
    if allow_reencode is None:
        allow_reencode = bool(getattr(Config, "FIGURE_ALLOW_REENCODE", False))
    if proof_policy is None:
        proof_policy = getattr(Config, "FIGURE_PROOF_POLICY", None)
    proof_policy = dict(proof_policy or {})
    if proof is None:
        proof = bool(getattr(Config, "FIGURE_PROOF", False) or proof_policy)
    proof = bool(proof)

    if not is_preview:
        _apply_presentation(figure)
    # Notify observers with the live figure before the caller closes it (and
    # before rasterize_data_artists mutates it for SVG). Fires regardless of
    # SAVE_MODE / skip so a montage can capture even a skipped/no-write run.
    if _FIG_SAVE_OBSERVERS and not is_preview:
        _notify_fig_save_observers(figure, full_path, image_name, subfolder, bool(montage))

    from PyFLASH import provenance

    def _prepare_export_record(persist=True):
        from PyFLASH import provenance
        if not persist:
            with provenance._unstaged_save(full_path):
                return _prepare_export_record()
        _prepared_record = None
        _described = None
        _svg_metadata = {}
        try:
            from PyFLASH import provenance

            if preview_record is not None:
                _prepared_record, _svg_metadata, _described = preview_record, {}, None
            else:
                _prepared_record, _svg_metadata, _described = provenance.prepare_figure_record(
                    figure,
                    full_path,
                    image_name,
                    figure_profile=selected_profile,
                    safe_columns=figure_safe_columns,
                    public_sources=public_sources,
                    proof=proof,
                )
        except Exception as exc:
            if selected_profile != "master" or proof:
                raise
            warnings.warn(
                f"Figure provenance is incomplete: {type(exc).__name__}: {exc}",
                stacklevel=2,
            )
            try:
                _svg_metadata = provenance.svg_metadata(full_path, image_name)
            except Exception:
                _svg_metadata = {}

        return _prepared_record, _svg_metadata, _described

    def _remember_current_record(record):
        if not is_preview and record is not None:
            from reprofig import derive_profile
            current_record = derive_profile(record, selected_profile,
                safe_columns=figure_safe_columns, public_sources=public_sources)
            figure._pyflash_preview_evidence = {
                os.path.abspath(path): {"record": current_record, "written": False}
                for path in full_paths
            }

    if Config.SAVE_MODE or is_preview:
        os.makedirs(_windows_extended_path(save_path), exist_ok=True)
        if use_skip and all(os.path.isfile(path) for path in save_full_paths):
            _prepared_record, _svg_metadata, _described = _prepare_export_record(persist=False)
            _remember_current_record(_prepared_record)
            if verbose:
                _log.hint(f"Skipped (exists): {full_path}")
            return full_path

        if rasterize and not is_preview:
            rasterize_data_artists(figure)

        # Attach the overlap-safe layout engine just before saving so over-long
        # titles are shrunk to fit and an overlapping suptitle is lifted clear,
        # without shrinking the data axes. No-op for figures flagged manual or
        # created with their own (e.g. constrained) engine.
        if not is_preview and getattr(Config, "USE_PYFLASH_LAYOUT", True):
            from PyFLASH.layout import apply_pyflash_layout
            apply_pyflash_layout(figure)
        if not fixed_canvas and not is_preview:
            apply_pyflash_figure_geometry(figure, save_bbox=save_bbox)

        # Guarantee editable text at the single figure choke point regardless of
        # what rcParams the caller left active: every string stays a real <text>
        # element and mathtext renders in the body font (not vectorised glyphs).
        # Carry the producing call inside the file as well as in the folder's
        # figures.json: a manifest is keyed by filename, so a renamed or copied
        # figure loses the entry but keeps what is embedded in the SVG.
        cached_paths = [path for path in save_full_paths if use_skip and os.path.isfile(path)]
        _prepared_record, _svg_metadata, _described = _prepare_export_record(persist=not cached_paths)
        if proof and _prepared_record is not None:
            from PyFLASH._figure_proof import capture_figure
            _prepared_record.extensions['render_manifest'] = capture_figure(figure).to_dict()
        if cached_paths:
            from reprofig import derive_profile, extract_record, validate_artifact

            if _prepared_record is None:
                raise ValueError("Cannot complete cached figure formats without current evidence.")
            if proof:
                from PyFLASH._figure_proof import capture_figure
                _prepared_record.extensions["render_manifest"] = capture_figure(figure).to_dict()
            current = derive_profile(_prepared_record, selected_profile,
                safe_columns=figure_safe_columns, public_sources=public_sources)

            def scientific_evidence(record):
                payload = record.to_dict()
                # Identity and time belong to the first carrier. Everything
                # describing its science and producer must still match.
                payload.pop("figure_id", None)
                payload.pop("created_at", None)
                payload.pop("integrity", None)
                producer = dict(payload.get("producer") or {})
                arguments = dict(producer.get("arguments") or {})
                arguments.pop("write_companion_csv", None)
                if "arguments" in producer:
                    producer["arguments"] = arguments
                payload["producer"] = producer
                sources = [dict(source) for source in payload.get("sources", [])]
                for source in sources:
                    if source.get("sha256"):
                        source.pop("modified_at", None)
                        source.pop("size_bytes", None)
                payload["sources"] = sources
                extensions = dict(payload.get("extensions") or {})
                # Each carrier binds its own rendered pixels to the shared
                # evidence. The semantic manifest above must still agree.
                extensions.pop("visual_reference", None)
                proof_data = extensions.pop("proof", None)
                if proof_data is not None:
                    extensions["proof"] = {key: proof_data.get(key) for key in
                        ("statistical_specifications", "claims", "opaque_statistics")}
                payload["extensions"] = extensions
                return payload

            cached = None
            for path in cached_paths:
                validation = validate_artifact(path, expected_profile=selected_profile,
                    public_safety=selected_profile != "master")
                if not validation.valid:
                    raise ValueError("Cached figure format is invalid: " + str(path))
                record = extract_record(path)
                if scientific_evidence(record) != scientific_evidence(current):
                    raise ValueError("Cached figure evidence differs from this render; use a new name or disable skip_existing.")
                if cached is not None and (record.figure_id != cached.figure_id or
                        (record.extensions.get("proof") or {}).get("root_sha256") !=
                        (cached.extensions.get("proof") or {}).get("root_sha256")):
                    raise ValueError("Cached figure formats disagree on identity or proof root.")
                cached = record
            # Render from the complete current record so profile reduction
            # happens exactly once, including with older ReproFig releases.
            _prepared_record.figure_id = cached.figure_id
            _prepared_record.created_at = cached.created_at
            if "write_companion_csv" in (cached.producer.get("arguments") or {}):
                arguments = dict(_prepared_record.producer.get("arguments") or {})
                arguments["write_companion_csv"] = cached.producer["arguments"]["write_companion_csv"]
                _prepared_record.producer["arguments"] = arguments
            # Content hashes identify source bytes. Retain the first carrier's
            # time metadata so an unrelated touch cannot change its proof root.
            for source in _prepared_record.sources:
                for previous in cached.sources:
                    if (source.sha256 and source.sha256 == previous.sha256 and
                            source.role == previous.role and source.relative_path == previous.relative_path and
                            source.uri == previous.uri):
                        source.modified_at = previous.modified_at
                        source.size_bytes = previous.size_bytes
                        break
        _remember_current_record(_prepared_record)

        from reprofig import save_figure as _reprofig_save_figure
        from reprofig import validate_artifact

        _companion_base_record = _prepared_record
        _variant_record = _prepared_record
        base_savefig_kwargs = pyflash_savefig_kwargs(
            dpi=dpi,
            bbox_inches=save_bbox,
            pad_inches=pad_inches,
            bbox_extra_artists=extra_artist,
            transparent=bool(transparent),
        )
        if is_preview:
            base_savefig_kwargs.update(facecolor="white", transparent=False,
                                       bbox_inches="tight", pad_inches=plt.rcParams["savefig.pad_inches"])
        elif fixed_canvas:
            base_savefig_kwargs["bbox_inches"] = None
        for index, (carrier_path, save_carrier_path, extension) in enumerate(
            zip(full_paths, save_full_paths, selected_formats)
        ):
            if use_skip and os.path.isfile(save_carrier_path):
                continue
            descriptor, temporary_path = tempfile.mkstemp(
                dir=_windows_extended_path(save_path),
                prefix=f".{image_name}.",
                suffix=f".{extension}",
            )
            os.close(descriptor)
            # ReproFig distinguishes a not-yet-written target by suffix.  An
            # empty mkstemp file looks like a corrupt carrier instead.
            os.unlink(temporary_path)
            temporary_save_path = _windows_extended_path(temporary_path)
            try:
                with plt.rc_context({'svg.fonttype': 'none', 'mathtext.default': 'regular',
                                     **({'savefig.bbox': None} if fixed_canvas else {})}):
                    if _variant_record is None or (_variant_record.distribution_profile == "minimal_public"):
                        figure.savefig(
                            temporary_save_path,
                            format=extension,
                            **base_savefig_kwargs,
                        )
                        _saved_record = None
                        if _variant_record is not None:
                            # Reuse the existing carrier-embedding API for a
                            # metadata-only record. Older ReproFig releases
                            # cannot derive that reduced profile a second time.
                            from reprofig import embed_file, refresh_visual_reference
                            _saved_record = _variant_record
                            if proof:
                                _saved_record = refresh_visual_reference(
                                    temporary_save_path, _saved_record
                                )
                            embed_file(temporary_save_path, _saved_record,
                                       output_path=temporary_save_path)
                    else:
                        _saved_record = _reprofig_save_figure(
                            figure,
                            temporary_save_path,
                            record=_variant_record,
                            figure_profile=selected_profile,
                            dpi=dpi,
                            dpi_preset=dpi_preset,
                            render_preset=render_preset,
                            width=width,
                            height=height,
                            format_options=_format_options_for(
                                format_options, extension
                            ),
                            write_companion_csv=False,
                            savefig_kwargs=base_savefig_kwargs,
                            allow_reencode=bool(allow_reencode),
                            safe_columns=figure_safe_columns,
                            public_sources=public_sources,
                            proof=proof,
                            # PyFLASH normalizes the SVG canvas after rendering;
                            # policy signing/encryption is therefore applied
                            # below, after the final visual reference refresh.
                            proof_policy=None,
                        )
                if extension == "svg" and not fixed_canvas:
                    normalize_pyflash_svg_canvas(
                        temporary_save_path, save_bbox=save_bbox
                    )
                    if proof and _saved_record is not None:
                        from reprofig import embed_file, refresh_visual_reference

                        _saved_record = refresh_visual_reference(
                            temporary_save_path, _saved_record
                        )
                        embed_file(
                            temporary_save_path,
                            _saved_record,
                            output_path=temporary_save_path,
                        )
                if proof and _saved_record is not None:
                    from reprofig import apply_artifact_policy

                    _saved_record, _proof_report = apply_artifact_policy(
                        temporary_save_path,
                        proof_policy,
                        record=_saved_record,
                        reuse_encrypted_sections=any(
                            bool(value.get("encrypted"))
                            for value in (
                                (_saved_record.extensions.get("proof") or {}).get(
                                    "sections", []
                                )
                            )
                        ),
                    )
                    reports = dict(
                        getattr(figure, "_reprofig_proof_reports", {}) or {}
                    )
                    reports[carrier_path] = _proof_report.to_dict()
                    setattr(figure, "_reprofig_proof_reports", reports)
                    # Reuse encrypted sections across variants so every carrier
                    # has one evidence root; signatures are rebound per visual.
                    _variant_record = _saved_record
                if _saved_record is not None:
                    if cached_paths and proof and (
                            (_saved_record.extensions.get("proof") or {}).get("root_sha256") !=
                            (cached.extensions.get("proof") or {}).get("root_sha256")):
                        raise ValueError("Completed figure format would change the cached proof root.")
                    validation = validate_artifact(
                        temporary_save_path,
                        expected_profile=selected_profile,
                        public_safety=selected_profile != "master",
                    )
                    if not validation.valid:
                        raise ValueError(
                            "; ".join(
                                issue.message
                                for issue in validation.issues
                                if issue.severity == "error"
                            )
                        )
                os.replace(temporary_save_path, save_carrier_path)
                if not is_preview and _saved_record is not None:
                    from PyFLASH._cache_identity import file_hash
                    figure._pyflash_preview_evidence[os.path.abspath(carrier_path)] = {
                        "record": _saved_record, "written": True,
                        "sha256": file_hash(save_carrier_path),
                    }
            finally:
                try:
                    os.unlink(temporary_save_path)
                except OSError:
                    pass

            if _prepared_record is not None and not is_preview:
                provenance.stage_prepared_save(
                    carrier_path, _described, _saved_record
                )
            if _FIG_SAVED_OBSERVERS and not is_preview:
                _notify_fig_saved_observers(
                    carrier_path, image_name, subfolder, bool(montage)
                )
        if _companion_base_record is not None and write_companion_csv:
            from reprofig import derive_profile, write_companion_tables

            companion_profile = (
                "public" if selected_profile == "minimal_public"
                else selected_profile
            )
            companion_record = derive_profile(
                _companion_base_record,
                companion_profile,
                safe_columns=figure_safe_columns,
                public_sources=public_sources,
            )
            write_companion_tables(companion_record, full_path)
        try:
            from reprofig import detach as _detach_figure_record

            _detach_figure_record(figure)
        except Exception:
            pass

    if not Config.SAVE_MODE and not is_preview:
        _prepared_record, _svg_metadata, _described = _prepare_export_record(persist=False)
        _remember_current_record(_prepared_record)

    if verbose:
        _log.confirm(f"Figure saved to {full_path}")
    return full_path


def plot_legend_separately(ax, n_labels, flat=False):
    """Extract a legend from axes into its own figure."""
    from matplotlib import pyplot as plt
    label_params = ax.get_legend_handles_labels()
    figl, axl = plt.subplots()
    axl.axis(False)
    axl.legend(*label_params, loc="center", frameon=False,
               fontsize=20, ncols=n_labels if flat else 1)
    ax.legend().set_visible(False)
    return figl


# ── SCN / name helpers (used during import) ───────────────────────────

def replace_cropped(s):
    s_lower = s.lower()
    if s_lower == "cropped":
        return "1"
    if s_lower.startswith("cropped-"):
        return str(int(s_lower.split("-")[1]) + 1)
    return replace_week_int(s)


def add_scn_num(name, fullname):
    num = int(fullname.split("SCN")[-1].split("_")[0]) if fullname.split("SCN")[-1].split("_")[0] != '' else 0
    return name[:-1] + str(int(name[-1]) + num)


def replace_week_int(s):
    value = str(s)

    def _repl(match):
        num = match.group(1)
        word_map = {"2": "Two", "4": "Four", "8": "Eight"}
        return f"Week{word_map.get(num, num)}"

    return re.sub(r"(?i)week\s*([248])(?!\d)", _repl, value)


def _register_provenance_observer():
    """Record what produced every saved figure.

    Registered here rather than in ``PyFLASH/__init__`` so the package keeps its
    lazy submodule loading: anything that can call ``save_fig`` has already
    imported this module. ``provenance`` imports nothing from here at module
    level, so there is no cycle.
    """
    try:
        from PyFLASH import provenance

        register_fig_saved_observer(provenance._observer)
    except Exception:
        pass


_register_provenance_observer()


def _calibrated_conversion(values, calibration, *, multiply):
    scale = _finite_real_fraction(calibration, label='Pixel calibration', allow_missing=False, positive=True)
    array = np.asarray(values)
    if array.dtype.kind not in 'biufO':
        raise TypeError('Coordinates must contain real numbers.')
    if array.dtype.kind == 'f' and array.dtype.itemsize > 8:
        raise ValueError('Coordinates must be representable in binary64.')
    if array.dtype.kind == 'f':
        array = array.astype(float, copy=False)
    use_exact = array.ndim == 0 or array.dtype.kind in 'biuO'
    try:
        floating_scale = float(scale)
        use_exact = use_exact or not np.isfinite(floating_scale) or floating_scale == 0.
        use_exact = use_exact or _finite_real_fraction(floating_scale,label='Pixel calibration') != scale
    except OverflowError:
        floating_scale = None
        use_exact = True
    if use_exact:
        converted=[]
        for value in array.flat:
            original = _finite_real_fraction(value,label='Coordinate',allow_missing=True)
            if original is None:
                converted.append(np.nan)
                continue
            exact = original*scale if multiply else original/scale
            try: result=float(exact)
            except OverflowError as exc:
                raise ValueError('Converted coordinate exceeds the floating-point range.') from exc
            if not np.isfinite(result):
                raise ValueError('Converted coordinate exceeds the floating-point range.')
            converted.append(result)
        result=np.asarray(converted,dtype=float).reshape(array.shape)
    else:
        if np.isinf(array).any():
            raise ValueError('Coordinates must be finite or missing.')
        with np.errstate(over='ignore',invalid='ignore',under='ignore',divide='ignore'):
            result=np.multiply(array,floating_scale) if multiply else np.divide(array,floating_scale)
        if np.isinf(result).any():
            raise ValueError('Converted coordinate exceeds the floating-point range.')
    if isinstance(values,pd.Series):
        output=pd.Series(result,index=values.index,name=values.name)
        output.attrs=values.attrs.copy()
        return output
    if isinstance(values,pd.DataFrame):
        output=pd.DataFrame(result,index=values.index,columns=values.columns)
        output.attrs=values.attrs.copy()
        return output
    if array.ndim==0:
        return float(result)
    return result

def _exact_polyline_distance(px, py, x_line, y_line):
    """Avoid squaring in binary64 when represented coordinates are extreme."""
    from decimal import Decimal, localcontext
    from fractions import Fraction
    def exact(value):
        if isinstance(value, np.generic): value=value.item()
        return Fraction(value) if isinstance(value,int) else Fraction(*float(value).as_integer_ratio())
    vertices = [(exact(x), exact(y)) for x, y in zip(x_line, y_line)]
    segments = []
    for (x0,y0),(x1,y1) in zip(vertices, vertices[1:]):
        dx, dy = x1-x0, y1-y0
        segments.append((x0,y0,dx,dy,dx*dx+dy*dy))
    distances=[];closest=[]
    for xx, yy in zip(px,py):
        x,y = exact(xx),exact(yy)
        best_distance=None;best_point=None
        for x0,y0,dx,dy,denominator in segments:
            t = min(Fraction(1), max(Fraction(0), ((x-x0)*dx+(y-y0)*dy)/denominator)) if denominator else Fraction(0)
            cx,cy=x0+t*dx,y0+t*dy
            squared=(x-cx)**2+(y-cy)**2
            if best_distance is None or squared < best_distance:
                best_distance,best_point=squared,(cx,cy)
        with localcontext() as context:
            context.prec=2200
            distance=float((Decimal(best_distance.numerator)/Decimal(best_distance.denominator)).sqrt())
        if not np.isfinite(distance):
            raise ValueError('Polyline distance exceeds the floating-point range.')
        distances.append(distance)
        closest.append([float(coordinate) for coordinate in best_point])
    return np.asarray(distances,dtype=float),np.asarray(closest,dtype=float).reshape(-1,2)

def _finite_real_fraction(value, *, label, allow_missing=True, nonnegative=False,
                          positive=False):
    """Read a supplied real measurement exactly before dependent arithmetic."""
    from fractions import Fraction
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or value is pd.NA or isinstance(value, float) and math.isnan(value):
        if allow_missing:
            return None
        raise ValueError(label + " must be present.")
    if not isinstance(value, (int, float)):
        raise TypeError(label + " must be integers or floats.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(label + " must be finite.")
    if positive and value <= 0:
        raise ValueError(label + " must be positive.")
    if nonnegative and value < 0:
        raise ValueError(label + " must be nonnegative.")
    return Fraction(value)

def _pixel_conversion_scale(pixel_size, configured_pixels_per_micron):
    """Keep ImageJ's represented physical calibration when it is available."""
    if pixel_size is not None:
        return pixel_size, False
    configured = _finite_real_fraction(configured_pixels_per_micron,
        label='Pixel calibration', allow_missing=False, positive=True)
    try:
        physical = float(1/configured)
    except OverflowError:
        physical = np.inf
    if np.isfinite(physical) and physical > 0:
        return physical, False
    # An unavailable intermediate reciprocal must not erase a finite answer.
    return configured_pixels_per_micron, True
