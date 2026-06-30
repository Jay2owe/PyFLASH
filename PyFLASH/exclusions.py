"""
Outlier exclusion / marking for downstream analysis.

``data_overview`` *reports* outliers; this module lets you act on them. The
design is **non-destructive and reversible**: every function returns a cleaned
*shallow copy* of the experiment whose per-animal summary tables are replaced
with copies (the heavy raw ``.data`` is shared by reference, so this is cheap),
and the original object is never mutated. That matters because the ``/pyflash``
runner keeps a 288 MB batch resident — mutating it in place would leak across
requests.

Two phases:

- **mark** — :func:`mark_outliers` / :func:`mark_exclusions` record an audit
  *ledger* of which cells/animals to drop, without changing any value. Stackable
  across passes; ideal for "show me the flagged points" before committing.
- **apply / exclude** — :func:`apply_exclusions` realises a ledger (or explicit
  cells/animals) by writing the ``EXCLUDED_OUTLIER`` sentinel (or NaN) into the
  cleaned summary. :func:`exclude_outliers` is detect + mark + apply in one call.

The excluded values use the reason-coded ``EXCLUDED_OUTLIER`` sentinel
(:func:`PyFLASH.utils.excluded_outlier_token`), which every numeric-coercion path
treats as analysis-missing (so all existing plots/stats ignore it) while QC
reporting still counts it separately from a true NaN or a never-measured cell.

Granularity:

- ``scope="cell"`` (default) blanks only the flagged (animal, metric) value, so
  the animal still contributes to its other metrics.
- ``scope="animal"`` blanks every metric for an animal flagged on enough metrics
  — the "this animal is a write-off" case.
"""
from __future__ import annotations

import copy
import os

import numpy as np
import pandas as pd

from PyFLASH._logging import logger as _log
from PyFLASH.utils import (
    excluded_manual_token,
    excluded_outlier_token,
    resolve_roi_bases,
    strip_name,
)

__all__ = [
    "apply_exclusions",
    "exclude_outliers",
    "exclude_animals",
    "mark_exclusions",
    "mark_outliers",
    "mark_animals",
    "clear_exclusions",
]

# Identifier/metadata columns that are never analysable metrics (mirrors the
# ``to_drop`` set used when the per-animal summary is built).
_ID_COLS = {
    "Region", "AnimalName", "Condition", "Label", "ImageROI",
    "ROINameRaw", "Hemisphere", "ROI",
}

_LEDGER_COLS = [
    "AnimalName", "column", "group", "original_value", "kind", "reason",
    "scope", "fill",
]


def _token_for(rec, fill):
    """The sentinel to write for a record.

    Precedence: an explicit ``fill`` argument, then a ``fill`` recorded on the
    record (when realising a previously-marked ledger, so ``mark(fill=np.nan)``
    stays NaN on apply), then the kind-coded default sentinel.
    """
    if fill is not None:
        return fill
    if "fill" in rec:
        return rec["fill"]
    if rec.get("kind") == "manual":
        return excluded_manual_token(rec.get("reason"))
    return excluded_outlier_token(rec.get("reason"))


# ── internals ────────────────────────────────────────────────────────────────
def _resolve_base(experiment, roi):
    """Resolve the single ROI-base summary key to operate on."""
    return resolve_roi_bases(roi, experiment)[0]


def _summary_for(experiment, base):
    summaries = getattr(experiment, "summaries", None)
    if isinstance(summaries, dict) and base in summaries:
        return summaries[base]
    return getattr(experiment, "summary", None)


def _clean_copy(experiment):
    """Shallow-copy the experiment with a fresh ``summaries`` dict of copies.

    The original is left untouched; only the (small) per-animal summary frames
    are duplicated, so the heavy raw data is shared by reference.
    """
    exp = copy.copy(experiment)
    summaries = getattr(experiment, "summaries", None)
    if isinstance(summaries, dict):
        exp.summaries = {k: v.copy() for k, v in summaries.items()}
        # Keep a plain `.summary` attribute consistent with the cleaned dict (so a
        # downstream that reads `.summary` directly never sees the original). On a
        # real Experiment `.summary` is a property over `.summaries`, so this just
        # re-sets the same frame harmlessly; on a plain-attr object it rebinds it.
        if hasattr(experiment, "summary"):
            scn = exp.summaries.get("SCN")
            if scn is None and exp.summaries:
                scn = next(iter(exp.summaries.values()))
            if scn is not None:
                try:
                    exp.summary = scn
                except Exception:
                    pass
    else:
        summary = getattr(experiment, "summary", None)
        if isinstance(summary, pd.DataFrame):
            try:
                exp.summary = summary.copy()
            except Exception:
                pass
    return exp


def _metric_columns(df):
    """Numeric metric columns (everything coercible to numbers, minus IDs)."""
    out = []
    for col in df.columns:
        if col in _ID_COLS:
            continue
        if pd.to_numeric(df[col], errors="coerce").notna().sum() > 0:
            out.append(col)
    return out


def _cells_from_outliers(outliers, scope, columns, animals_table, animal_min_flags,
                         metric_cols):
    """Build a list of (animal, column, group, original_value, rule) cell records.

    ``outliers`` is a ``data_overview`` outliers table (one row per flagged
    (group, column, animal)). For ``scope="animal"`` the flagged cells are
    expanded to every metric column for animals exceeding ``animal_min_flags``.
    """
    records = []
    if outliers is None or len(outliers) == 0:
        return records

    def _rule(row):
        bits = []
        if bool(row.get("iqr_outlier", False)):
            bits.append("iqr")
        if bool(row.get("mad_outlier", False)):
            bits.append("mad")
        if bool(row.get("rout_outlier", False)):
            bits.append("rout")
        return "+".join(bits) or "outlier"

    if scope == "cell":
        for _, row in outliers.iterrows():
            col = row["column"]
            if columns is not None and col not in set(columns):
                continue
            records.append({
                "AnimalName": str(row["AnimalName"]),
                "column": str(col),
                "group": str(row.get("group", "")),
                "original_value": row.get("value", np.nan),
                "kind": "outlier",
                "reason": _rule(row),
            })
        return records

    # scope == "animal": expand flagged animals across all metric columns.
    if animals_table is not None and len(animals_table) > 0:
        flagged_animals = animals_table[
            animals_table["n_columns"] >= int(animal_min_flags)]["AnimalName"]
    else:
        counts = (outliers.groupby("AnimalName")["column"].nunique()
                  if len(outliers) else pd.Series(dtype=int))
        flagged_animals = counts[counts >= int(animal_min_flags)].index
    target_cols = list(columns) if columns is not None else list(metric_cols)
    for animal in flagged_animals:
        for col in target_cols:
            records.append({
                "AnimalName": str(animal),
                "column": str(col),
                "group": "",
                "original_value": np.nan,
                "kind": "outlier",
                "reason": f"animal(min_flags>={int(animal_min_flags)})",
            })
    return records


def _write_cells(df, records, fill):
    """Blank ``records`` cells in ``df`` (in place on the copy); return updated ledger.

    Captures the original value per cell into the ledger before overwriting, so
    the exclusion is auditable and the original experiment (untouched) restores it.
    """
    if "AnimalName" not in df.columns:
        raise ValueError(
            "exclusions need an 'AnimalName' column in the summary table.")
    ledger = []
    by_animal = {str(a): (df["AnimalName"].astype(str) == str(a)) for a in
                 {r["AnimalName"] for r in records}}
    for rec in records:
        col = rec["column"]
        if col not in df.columns:
            continue
        mask = by_animal.get(rec["AnimalName"])
        if mask is None or not mask.any():
            continue
        original = rec.get("original_value")
        if original is None or (isinstance(original, float) and np.isnan(original)):
            vals = df.loc[mask, col].tolist()
            original = vals[0] if vals else np.nan
        token = _token_for(rec, fill)
        # Writing a string sentinel into a numeric column needs an object dtype,
        # else pandas warns (and will eventually raise) on the dtype mismatch.
        if isinstance(token, str) and not pd.api.types.is_object_dtype(df[col].dtype):
            df[col] = df[col].astype(object)
        df.loc[mask, col] = token
        ledger.append({
            "AnimalName": rec["AnimalName"], "column": col,
            "group": rec.get("group", ""), "original_value": original,
            "kind": rec.get("kind", ""), "reason": rec.get("reason", ""),
            "scope": rec.get("scope", ""), "fill": token,
        })
    return pd.DataFrame(ledger, columns=_LEDGER_COLS)


def _attach_ledger(exp, new_ledger, prior):
    frames = [f for f in (prior, new_ledger)
              if isinstance(f, pd.DataFrame) and not f.empty]
    exp.exclusions = (pd.concat(frames, ignore_index=True)
                      if frames else pd.DataFrame(columns=_LEDGER_COLS))
    return exp


# ── public API ───────────────────────────────────────────────────────────────
def _manual_records(df, cells, animals, columns, reason, kind):
    """Build manual cell/animal exclusion records (kind/reason coded).

    ``animals`` may be a list (sharing ``reason``) or a ``{animal: reason}`` dict
    for per-animal reasons.
    """
    records = []
    for animal, col in (cells or []):
        records.append({"AnimalName": str(animal), "column": str(col),
                        "group": "", "original_value": np.nan,
                        "kind": kind, "reason": (reason or ""), "scope": "cell"})
    if isinstance(animals, dict):
        items = [(str(a), r) for a, r in animals.items()]
    else:
        items = [(str(a), reason) for a in (animals or [])]
    target_cols = list(columns) if columns is not None else _metric_columns(df)
    for animal, r in items:
        for col in target_cols:
            records.append({"AnimalName": animal, "column": str(col),
                            "group": "", "original_value": np.nan,
                            "kind": kind, "reason": (r or ""), "scope": "animal"})
    return records


def _set_summary_and_save(exp, ledger, base, *, action, scope, save, run_label,
                          verbose):
    n_cells = int(len(ledger))
    n_animals = int(ledger["AnimalName"].nunique()) if n_cells else 0
    reasons = (sorted({str(r) for r in ledger["reason"] if str(r)})
               if n_cells else [])
    exp.exclusion_summary = {
        "action": action, "scope": scope, "roi": str(base),
        "n_excluded_cells": n_cells, "n_animals_affected": n_animals,
        "reasons": reasons,
    }
    if save and n_cells:
        out_dir = os.path.join(
            getattr(exp, "data_path", None)
            or os.path.dirname(getattr(exp, "fig_path", ".") or "."),
            "Exclusions")
        os.makedirs(out_dir, exist_ok=True)
        label = strip_name(str(run_label)) if run_label else f"{scope}_{base}"
        ledger.to_csv(os.path.join(out_dir, f"exclusions_{label}.csv"), index=False)
    if verbose:
        verb = "excluded" if action == "exclude" else "marked"
        _log.confirm(
            f"[{action}_exclusions] {verb} {n_cells} cell(s) across "
            f"{n_animals} animal(s) (scope={scope}, roi={base}).")
    return exp


def _apply_manual(experiment, *, cells=None, animals=None, columns=None,
                  reason=None, kind="manual", fill=None, roi=None, apply=True,
                  save=False, run_label=None, verbose=False):
    base = _resolve_base(experiment, roi)
    exp = _clean_copy(experiment)
    df = _summary_for(exp, base)
    if df is None:
        raise ValueError("exclusions: experiment has no summary table.")
    records = _manual_records(df, cells, animals, columns, reason, kind)
    target = df if apply else df.copy()  # mark-only writes to a discarded copy
    ledger = _write_cells(target, records, fill)
    _attach_ledger(exp, ledger, getattr(experiment, "exclusions", None))
    scope = ("animal" if (animals is not None and not cells)
             else "cell" if cells else "manual")
    _set_summary_and_save(
        exp, ledger, base, action=("exclude" if apply else "mark"), scope=scope,
        save=save, run_label=run_label, verbose=verbose)
    return exp


def apply_exclusions(experiment, *, cells=None, animals=None, columns=None,
                     reason=None, kind="manual", fill=None, roi=None):
    """Return a cleaned copy with the given cells/animals blanked for analysis.

    ``cells`` is an iterable of ``(animal_name, column)``; ``animals`` is an
    iterable of animal names (or a ``{animal: reason}`` dict) blanked across
    ``columns`` (or every metric column). ``reason`` is recorded in the ledger and
    encoded into the cell sentinel (``EXCLUDED_MANUAL:<reason>``). With neither
    ``cells`` nor ``animals``, a previously recorded ``experiment.exclusions``
    ledger (from :func:`mark_outliers` / :func:`mark_animals`) is realised
    instead. ``fill`` overrides the sentinel (pass ``np.nan`` for a plain blank).

    The original ``experiment`` is never modified.
    """
    if cells is None and animals is None:
        base = _resolve_base(experiment, roi)
        exp = _clean_copy(experiment)
        df = _summary_for(exp, base)
        if df is None:
            raise ValueError("apply_exclusions: experiment has no summary table.")
        prior = getattr(experiment, "exclusions", None)
        records = []
        if isinstance(prior, pd.DataFrame) and not prior.empty:
            has_fill = "fill" in prior.columns
            for _, row in prior.iterrows():
                rec = {
                    "AnimalName": str(row["AnimalName"]),
                    "column": str(row["column"]),
                    "group": row.get("group", ""),
                    "original_value": row.get("original_value", np.nan),
                    "kind": row.get("kind", "manual"),
                    "reason": row.get("reason", ""),
                    "scope": row.get("scope", ""),
                }
                if has_fill:
                    # Preserve the originally-marked fill (e.g. np.nan) on apply.
                    rec["fill"] = row["fill"]
                records.append(rec)
        ledger = _write_cells(df, records, fill)
        _attach_ledger(exp, ledger, None)
        _set_summary_and_save(exp, ledger, base, action="exclude", scope="ledger",
                              save=False, run_label=None, verbose=False)
        return exp
    return _apply_manual(experiment, cells=cells, animals=animals, columns=columns,
                         reason=reason, kind=kind, fill=fill, roi=roi, apply=True,
                         save=False, verbose=False)


def _detect_outliers(experiment, *, filtered_columns, column_strings, regex_string,
                     exclude, by, factor, specificity, roi, methods, iqr_k,
                     mad_threshold, rout_q):
    """Reuse the data_overview detection path so flags match the QC report exactly."""
    from PyFLASH.pipeline import data_overview

    ov = data_overview(
        experiment,
        filtered_columns=filtered_columns, column_strings=column_strings,
        regex_string=regex_string, exclude=exclude,
        by=by, factor=factor, specificity=specificity, roi=roi,
        include_inventory=False, include_group_counts=False,
        include_descriptives=False, include_normality=False,
        include_covariation=False, include_outliers=True,
        outlier_methods=methods, iqr_k=iqr_k, mad_threshold=mad_threshold,
        rout_q=rout_q,
        save=False, plot_missingness=False, plot_covariation=False, verbose=False,
    )
    return ov["outliers"], ov.get("outlier_animals"), ov.get("numeric_columns", [])


def _exclude_or_mark(experiment, *, apply, filtered_columns, column_strings,
                     regex_string, exclude, by, factor, specificity, scope,
                     methods, iqr_k, mad_threshold, rout_q, animal_min_flags,
                     fill, roi, outliers, save, run_label, verbose):
    base = _resolve_base(experiment, roi)
    outlier_animals = None
    numeric_cols = []
    if outliers is None:
        outliers, outlier_animals, numeric_cols = _detect_outliers(
            experiment, filtered_columns=filtered_columns,
            column_strings=column_strings, regex_string=regex_string,
            exclude=exclude, by=by, factor=factor, specificity=specificity,
            roi=roi, methods=methods, iqr_k=iqr_k,
            mad_threshold=mad_threshold, rout_q=rout_q)

    base_df = _summary_for(experiment, base)
    metric_cols = numeric_cols or _metric_columns(base_df)
    columns = None  # detection already restricted the column set
    records = _cells_from_outliers(
        outliers, scope, columns, outlier_animals, animal_min_flags, metric_cols)
    for rec in records:
        rec["scope"] = scope

    exp = _clean_copy(experiment)
    df = _summary_for(exp, base)
    if apply:
        ledger = _write_cells(df, records, fill)
    else:
        # Mark only: record the ledger (with original values) but blank nothing.
        ledger = _write_cells(df.copy(), records, fill)  # df.copy() is discarded
    _attach_ledger(exp, ledger, getattr(experiment, "exclusions", None))

    n_cells = int(len(ledger))
    n_animals = int(ledger["AnimalName"].nunique()) if n_cells else 0
    exp.exclusion_summary = {
        "action": "exclude" if apply else "mark",
        "scope": scope, "roi": str(base), "methods": [str(m).lower() for m in methods],
        "iqr_k": float(iqr_k), "mad_threshold": float(mad_threshold),
        "rout_q": float(rout_q),
        "n_excluded_cells": n_cells, "n_animals_affected": n_animals,
    }

    if save and n_cells:
        out_dir = os.path.join(
            getattr(experiment, "data_path", None)
            or os.path.dirname(getattr(experiment, "fig_path", ".") or "."),
            "Exclusions")
        os.makedirs(out_dir, exist_ok=True)
        label = strip_name(str(run_label)) if run_label else f"{scope}_{base}"
        ledger.to_csv(os.path.join(out_dir, f"exclusions_{label}.csv"), index=False)

    if verbose:
        verb = "excluded" if apply else "marked"
        _log.confirm(
            f"[{'exclude' if apply else 'mark'}_outliers] {verb} {n_cells} cell(s) "
            f"across {n_animals} animal(s) (scope={scope}, roi={base}).")
    return exp


def exclude_outliers(experiment, *, filtered_columns=None, column_strings=None,
                     regex_string=None, exclude="", by="all", factor=None,
                     specificity=None, scope="cell", methods=("rout",),
                     iqr_k=1.5, mad_threshold=3.5, rout_q=1.0,
                     animal_min_flags=2, fill=None, roi=None, outliers=None,
                     save=False, run_label=None,
                     verbose=True):
    """Detect outliers and return a cleaned copy with them removed from analysis.

    Detection reuses the exact ``data_overview`` path (same column resolution,
    ``by``/``factor``/``specificity`` paneling, and outlier rules), so what is
    excluded matches the QC report. Pass an ``outliers`` table (e.g. the one
    ``data_overview`` returns) to skip re-detection.

    ``scope="cell"`` blanks each flagged (animal, metric) value; ``scope="animal"``
    blanks every metric for animals flagged on ``>= animal_min_flags`` metrics.
    The returned experiment carries an audit ``.exclusions`` ledger and an
    ``.exclusion_summary``; the original is untouched. Feed the result straight
    into any plot/stat function.
    """
    return _exclude_or_mark(
        experiment, apply=True, filtered_columns=filtered_columns,
        column_strings=column_strings, regex_string=regex_string, exclude=exclude,
        by=by, factor=factor, specificity=specificity, scope=scope, methods=methods,
        iqr_k=iqr_k, mad_threshold=mad_threshold, rout_q=rout_q,
        animal_min_flags=animal_min_flags, fill=fill, roi=roi,
        outliers=outliers, save=save, run_label=run_label, verbose=verbose)


def mark_outliers(experiment, *, filtered_columns=None, column_strings=None,
                  regex_string=None, exclude="", by="all", factor=None,
                  specificity=None, scope="cell", methods=("rout",),
                  iqr_k=1.5, mad_threshold=3.5, rout_q=1.0,
                  animal_min_flags=2, fill=None, roi=None, outliers=None,
                  save=False, run_label=None,
                  verbose=True):
    """Non-destructive twin of :func:`exclude_outliers`.

    Records which cells/animals *would* be excluded into a ``.exclusions`` ledger
    (with their original values) but changes no data. Realise it later with
    :func:`apply_exclusions` (called with no cells/animals reads the ledger), or
    inspect the ledger to colour the flagged points in a plot.
    """
    return _exclude_or_mark(
        experiment, apply=False, filtered_columns=filtered_columns,
        column_strings=column_strings, regex_string=regex_string, exclude=exclude,
        by=by, factor=factor, specificity=specificity, scope=scope, methods=methods,
        iqr_k=iqr_k, mad_threshold=mad_threshold, rout_q=rout_q,
        animal_min_flags=animal_min_flags, fill=fill, roi=roi,
        outliers=outliers, save=save, run_label=run_label, verbose=verbose)


def mark_exclusions(experiment, *, cells=None, animals=None, columns=None,
                    reason=None, roi=None):
    """Record an explicit manual exclusion ledger without changing any data.

    Mirror of :func:`apply_exclusions`' inputs, but non-destructive: attach the
    ledger to a copy and realise later via ``apply_exclusions(marked)``.
    """
    return _apply_manual(experiment, cells=cells, animals=animals, columns=columns,
                         reason=reason, kind="manual", fill=None, roi=roi,
                         apply=False, save=False, verbose=False)


def exclude_animals(experiment, animals, *, reason=None, columns=None, roi=None,
                    fill=None, save=False, run_label=None, verbose=True):
    """Manually exclude whole animals from analysis, with a reason.

    ``animals`` is a single name, a list of names (sharing ``reason``), or a
    ``{animal: reason}`` dict for per-animal reasons. Every metric for each animal
    (or just ``columns``) is set to the ``EXCLUDED_MANUAL:<reason>`` sentinel in a
    cleaned copy — so the reason is visible in each cell of the animal's row and
    every downstream plot/stat ignores it — the reason is recorded in the
    ``.exclusions`` ledger, and the original experiment is untouched.

        clean = exclude_animals(batch, "M12", reason="damaged section")
        clean = exclude_animals(batch, {"M12": "damaged", "M07": "wrong genotype"})
    """
    if isinstance(animals, str):
        animals = [animals]
    return _apply_manual(experiment, animals=animals, columns=columns, reason=reason,
                         kind="manual", fill=fill, roi=roi, apply=True, save=save,
                         run_label=run_label, verbose=verbose)


def mark_animals(experiment, animals, *, reason=None, columns=None, roi=None,
                 verbose=True):
    """Non-destructive twin of :func:`exclude_animals` (records the ledger only)."""
    if isinstance(animals, str):
        animals = [animals]
    return _apply_manual(experiment, animals=animals, columns=columns, reason=reason,
                         kind="manual", fill=None, roi=roi, apply=False, save=False,
                         verbose=verbose)


def clear_exclusions(experiment):
    """Return a copy with any recorded ``.exclusions`` ledger removed."""
    exp = _clean_copy(experiment)
    exp.exclusions = pd.DataFrame(columns=_LEDGER_COLS)
    if hasattr(exp, "exclusion_summary"):
        try:
            delattr(exp, "exclusion_summary")
        except Exception:
            exp.exclusion_summary = None
    return exp
