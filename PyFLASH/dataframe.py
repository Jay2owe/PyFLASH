"""Adapters for using already-tabular data with PyFLASH functions."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from PyFLASH.aliases import resolve_dataframe_aliases, resolve_group_style_aliases


@dataclass
class DataFrameTable:
    """Small marker-table wrapper exposing the ``.df`` attribute PyFLASH expects."""

    name: str
    df: pd.DataFrame


def _as_condition_list(conditions):
    if conditions is None:
        raise ValueError("groups or conditions are required for from_dataframe().")
    if hasattr(conditions, "condition_list") and hasattr(conditions, "factorDict"):
        return conditions
    try:
        values = list(conditions)
    except TypeError as exc:
        raise TypeError(
            "groups must be a PyFLASH groupList/conditionList or an iterable of group objects."
        ) from exc
    if len(values) == 0:
        raise ValueError("groups must contain at least one group.")
    from PyFLASH.conditions import groupList

    return groupList(values)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _unique_preserve_order(values):
    seen = set()
    out = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text == "":
            continue
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _value_from_spec(spec, name, index, default=None):
    if spec is None:
        return default
    if isinstance(spec, Mapping):
        return spec.get(name, spec.get(str(name), default))
    values = _as_list(spec)
    if index < len(values):
        return values[index]
    return default


def _comparison_token(pair, names):
    if isinstance(pair, str):
        text = pair.strip()
        if re.match(r"^\d+\s*-\s*\d+$", text):
            first, second = [int(part.strip()) for part in text.split("-", 1)]
            return f"{first}-{second}"
        parts = [p.strip() for p in re.split(r"\s*(?:,|:|->| vs | v )\s*", text) if p.strip()]
        if len(parts) == 2:
            pair = tuple(parts)
        else:
            raise ValueError(f"Could not parse comparison {pair!r}.")
    if not isinstance(pair, (tuple, list)) or len(pair) != 2:
        raise ValueError(f"Comparison {pair!r} must be '1-2' or a pair of names.")
    lookup = {str(name).strip().casefold(): i + 1 for i, name in enumerate(names)}
    resolved = []
    for item in pair:
        if isinstance(item, (int, np.integer)):
            idx = int(item)
        else:
            key = str(item).strip().casefold()
            if key not in lookup:
                raise ValueError(f"Comparison references unknown condition {item!r}.")
            idx = lookup[key]
        resolved.append(idx)
    return f"{resolved[0]}-{resolved[1]}"


def _resolve_auto_comparisons(names, comparisons=None, comparison_mode=None, control=None):
    names = [str(name) for name in names]
    if comparisons is not None:
        return [_comparison_token(pair, names) for pair in _as_list(comparisons)]
    mode = str(comparison_mode or "").strip().lower()
    if mode in {"", "none", "default"}:
        return None
    if mode in {"all", "all_pairs", "all-pairs", "pairwise"}:
        return [f"{i + 1}-{j + 1}" for i in range(len(names)) for j in range(i + 1, len(names))]
    if mode in {"sequential", "adjacent"}:
        return [f"{i + 1}-{i + 2}" for i in range(max(0, len(names) - 1))]
    if mode in {"control", "vs_control", "vs-control"}:
        if control is None:
            control = names[0] if names else None
        lookup = {name.strip().casefold(): i + 1 for i, name in enumerate(names)}
        key = str(control).strip().casefold()
        if key not in lookup:
            raise ValueError(f"control {control!r} is not one of {names}.")
        c_idx = lookup[key]
        return [f"{c_idx}-{i + 1}" for i in range(len(names)) if i + 1 != c_idx]
    raise ValueError(
        "comparison_mode must be one of None, 'all', 'control', or 'sequential'."
    )


def _build_single_factor_conditions(
    df,
    *,
    factor,
    values,
    labels=None,
    colors=None,
    styles=None,
    comparisons=None,
    comparison_mode=None,
    control=None,
):
    from PyFLASH.conditions import condition, conditionList
    from PyFLASH.conditions import _resolve_color

    names = _unique_preserve_order(values)
    if not names:
        names = ["All"]
    conditions = []
    for idx, name in enumerate(names):
        label = _value_from_spec(labels, name, idx, default=name)
        color = _resolve_color(_value_from_spec(colors, name, idx, default=None), idx)
        style = _value_from_spec(styles, name, idx, default="fill")
        conditions.append(condition(str(label), str(name), color, str(factor), style=style))
    return conditionList(
        conditions,
        comparisons=_resolve_auto_comparisons(
            names,
            comparisons=comparisons,
            comparison_mode=comparison_mode,
            control=control,
        ),
    )


def _auto_condition_list(
    df,
    *,
    condition_col="Condition",
    factor_cols=None,
    factor_mappings=None,
    condition_order=None,
    condition_labels=None,
    condition_colors=None,
    condition_styles=None,
    comparisons=None,
    comparison_mode=None,
    control=None,
):
    if not isinstance(df, pd.DataFrame):
        raise TypeError("conditions can only be inferred from a pandas DataFrame.")

    factor_mappings = factor_mappings or {}
    factors = _as_list(factor_cols)
    if factors:
        missing = [factor for factor in factors if factor not in df.columns]
        if missing:
            raise ValueError(f"factor_cols not found in DataFrame: {missing}")
        from functools import reduce
        from PyFLASH.conditions import conditionList, zipConditionLists

        per_factor = []
        for factor in factors:
            mapped = _map_series_values(
                df[factor],
                factor_mappings.get(factor, {}),
                allowed_values=None,
            )
            order = None
            if isinstance(condition_order, Mapping):
                order = condition_order.get(factor)
            values = _as_list(order) if order is not None else mapped.tolist()
            per_factor.append(
                _build_single_factor_conditions(
                    df,
                    factor=factor,
                    values=values,
                    labels=condition_labels.get(factor) if isinstance(condition_labels, Mapping) else None,
                    colors=condition_colors.get(factor) if isinstance(condition_colors, Mapping) else None,
                    styles=condition_styles.get(factor) if isinstance(condition_styles, Mapping) else None,
                )
            )
        if len(per_factor) == 1:
            cl = per_factor[0]
        else:
            crossed = reduce(
                lambda left, right: conditionList(list(zipConditionLists(left, right))),
                per_factor,
            )
            names = [cond.name for cond in crossed]
            crossed.comparisons = _resolve_auto_comparisons(
                names,
                comparisons=comparisons,
                comparison_mode=comparison_mode,
                control=control,
            )
            cl = crossed
        return cl

    if condition_col is not None and condition_col in df.columns:
        mapped = _map_series_values(
            df[condition_col],
            factor_mappings.get("Condition", factor_mappings.get(condition_col, {})),
            allowed_values=None,
        )
        values = _as_list(condition_order) if condition_order is not None else mapped.tolist()
        return _build_single_factor_conditions(
            df,
            factor=condition_col,
            values=values,
            labels=condition_labels,
            colors=condition_colors,
            styles=condition_styles,
            comparisons=comparisons,
            comparison_mode=comparison_mode,
            control=control,
        )

    return _build_single_factor_conditions(
        df,
        factor="Group",
        values=["All"],
        labels=condition_labels,
        colors=condition_colors,
        styles=condition_styles,
        comparisons=comparisons,
        comparison_mode=comparison_mode,
        control=control,
    )


def _format_animal_name(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return np.nan
        numeric = pd.to_numeric(text, errors="coerce")
        if (
            pd.notna(numeric)
            and np.isfinite(numeric)
            and np.isclose(numeric, round(float(numeric)))
        ):
            return str(int(round(float(numeric))))
        return text
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if (
        isinstance(value, (float, np.floating))
        and np.isfinite(value)
        and np.isclose(value, round(float(value)))
    ):
        return str(int(round(float(value))))
    text = str(value).strip()
    return text if text != "" else np.nan


def _condition_components(cond) -> dict[str, str]:
    if hasattr(cond, "conditionsList"):
        return {str(c.factor): str(c.name) for c in cond.conditionsList}
    factor = getattr(cond, "factor", None)
    if factor is None:
        return {}
    if isinstance(factor, list):
        return {str(factor[0]): str(getattr(cond, "name", ""))} if factor else {}
    return {str(factor): str(getattr(cond, "name", ""))}


def _lookup_from_names(values) -> dict[str, str]:
    lookup = {}
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            lookup[text.casefold()] = text
    return lookup


def _condition_value_lookup(condition_list) -> dict[str, str]:
    lookup = {}
    for cond in condition_list:
        for value in (getattr(cond, "name", None), getattr(cond, "label", None)):
            if value is None:
                continue
            text = str(value).strip()
            if text:
                lookup[text.casefold()] = str(getattr(cond, "name", text))
    return lookup


def _map_series_values(series, mapping, allowed_values=None):
    if isinstance(mapping, Mapping):
        mapping_lookup = {
            str(k).strip().casefold(): str(v)
            for k, v in mapping.items()
            if str(k).strip()
        }
    else:
        mapping_lookup = {}
    allowed_lookup = _lookup_from_names(allowed_values or [])

    def _map(value):
        if pd.isna(value):
            return np.nan
        text = str(value).strip()
        if text == "":
            return np.nan
        key = text.casefold()
        if key in mapping_lookup:
            return mapping_lookup[key]
        if key in allowed_lookup:
            return allowed_lookup[key]
        return text

    return series.map(_map)


def _normalise_animal_column(df, animal_col):
    out = df.copy()
    if animal_col is not None and animal_col in out.columns:
        source = out[animal_col]
        out["AnimalName"] = source
    elif "AnimalName" in out.columns:
        source = out["AnimalName"]
    else:
        source = pd.Series(out.index, index=out.index)
        out["AnimalName"] = source
    out["AnimalName"] = source.map(_format_animal_name)
    keep = out["AnimalName"].notna() & out["AnimalName"].astype(str).str.strip().ne("")
    return out.loc[keep].copy()


def _normalise_frame(
    df,
    *,
    condition_list,
    condition_col="Condition",
    animal_col="AnimalName",
    factor_mappings=None,
    require_condition=True,
):
    if not isinstance(df, pd.DataFrame):
        raise TypeError("from_dataframe inputs must be pandas DataFrames.")

    out = _normalise_animal_column(df.dropna(how="all"), animal_col)
    factors = [str(f) for f in (getattr(condition_list, "factor", []) or [])]
    factor_mappings = factor_mappings or {}

    for factor in factors:
        if factor not in out.columns:
            continue
        allowed = [
            getattr(cond, "name", None)
            for cond in getattr(condition_list, "factorDict", {}).get(factor, [])
        ]
        out[factor] = _map_series_values(
            out[factor],
            factor_mappings.get(factor, {}),
            allowed_values=allowed,
        )

    if condition_col is not None and condition_col in out.columns:
        out["Condition"] = _map_series_values(
            out[condition_col],
            factor_mappings.get("Condition", {}),
            allowed_values=_condition_value_lookup(condition_list).values(),
        )
        lookup = _condition_value_lookup(condition_list)
        out["Condition"] = out["Condition"].map(
            lambda v: lookup.get(str(v).strip().casefold(), v)
            if pd.notna(v) else np.nan
        )
    elif "Condition" in out.columns:
        lookup = _condition_value_lookup(condition_list)
        out["Condition"] = out["Condition"].map(
            lambda v: lookup.get(str(v).strip().casefold(), v)
            if pd.notna(v) else np.nan
        )

    if "Condition" not in out.columns and factors and all(f in out.columns for f in factors):
        condition_lookup = {}
        for cond in condition_list:
            components = _condition_components(cond)
            key = tuple(components.get(factor) for factor in factors)
            if all(value is not None and str(value).strip() for value in key):
                condition_lookup[key] = str(getattr(cond, "name", "".join(key)))

        def _condition_from_row(row):
            key = tuple(row.get(factor) for factor in factors)
            if any(pd.isna(value) or str(value).strip() == "" for value in key):
                return np.nan
            return condition_lookup.get(key, "".join(str(value) for value in key))

        out["Condition"] = out.apply(_condition_from_row, axis=1)

    if "Condition" not in out.columns:
        try:
            conds = list(condition_list)
        except TypeError:
            conds = []
        if len(conds) == 1 and str(getattr(conds[0], "name", "")) == "All":
            out["Condition"] = "All"

    if require_condition and "Condition" not in out.columns:
        raise ValueError(
            "DataFrame input must include a Condition column, a condition_col, "
            "or all factor columns from the supplied conditions."
        )
    if require_condition:
        valid = out["Condition"].notna() & out["Condition"].astype(str).str.strip().ne("")
        out = out.loc[valid].copy()

    return out


def _merge_summary_metadata(df, summary, factors):
    columns = ["AnimalName", "Condition"] + [f for f in factors if f in summary.columns]
    columns = [c for c in columns if c in summary.columns and c not in df.columns]
    if "AnimalName" not in df.columns or not columns:
        return df
    metadata_cols = ["AnimalName"] + columns
    metadata = summary[metadata_cols].drop_duplicates(subset=["AnimalName"])
    return df.merge(metadata, on="AnimalName", how="left")


def _build_region_dict(summary, region_col=None):
    if not isinstance(summary, pd.DataFrame):
        return {}
    if "Condition" not in summary.columns or "AnimalName" not in summary.columns:
        return {}
    region_source = region_col if region_col in summary.columns else None
    region_dict = {}
    for condition_name, cdf in summary.groupby("Condition", dropna=True):
        animals = {}
        for animal_name, adf in cdf.groupby("AnimalName", dropna=True):
            if region_source is None:
                regions = ["summary"]
            else:
                regions = [
                    str(v)
                    for v in adf[region_source].dropna().unique().tolist()
                    if str(v).strip()
                ]
                if not regions:
                    regions = ["summary"]
            animals[str(animal_name)] = regions
        region_dict[str(condition_name)] = animals
    return region_dict


class DataFrameExperiment:
    """PyFLASH-compatible object backed by user-supplied DataFrames."""

    data_layout = "dataframe"

    def __init__(
        self,
        summary,
        conditions=None,
        *,
        group_list=None,
        groups=None,
        name="DataFrame",
        condition_col="Condition",
        factor_cols=None,
        animal_col="AnimalName",
        group_col=None,
        group_cols=None,
        subject_col=None,
        factor_mappings=None,
        condition_order=None,
        condition_labels=None,
        condition_colors=None,
        condition_styles=None,
        comparisons=None,
        comparison_mode=None,
        control=None,
        group_order=None,
        group_labels=None,
        group_colors=None,
        group_styles=None,
        group_comparisons=None,
        group_comparison_mode=None,
        group_control=None,
        fig_path=None,
        data_path=None,
        file_path=None,
        aliases=None,
        summaries=None,
        data=None,
        images=None,
        representative_images=None,
        roi_base="SCN",
        region_col=None,
    ):
        conditions, condition_col, factor_cols, animal_col = resolve_dataframe_aliases(
            conditions=conditions,
            condition_col=condition_col,
            factor_cols=factor_cols,
            animal_col=animal_col,
            group_list=group_list,
            groups=groups,
            group_col=group_col,
            group_cols=group_cols,
            subject_col=subject_col,
        )
        (
            condition_order,
            condition_labels,
            condition_colors,
            condition_styles,
            comparisons,
            comparison_mode,
            control,
        ) = resolve_group_style_aliases(
            condition_order=condition_order,
            condition_labels=condition_labels,
            condition_colors=condition_colors,
            condition_styles=condition_styles,
            condition_comparisons=comparisons,
            condition_comparison_mode=comparison_mode,
            condition_control=control,
            group_order=group_order,
            group_labels=group_labels,
            group_colors=group_colors,
            group_styles=group_styles,
            group_comparisons=group_comparisons,
            group_comparison_mode=group_comparison_mode,
            group_control=group_control,
        )
        self.name = str(name)
        self.condition_list = (
            _as_condition_list(conditions)
            if conditions is not None
            else _auto_condition_list(
                summary,
                condition_col=condition_col,
                factor_cols=factor_cols,
                factor_mappings=factor_mappings,
                condition_order=condition_order,
                condition_labels=condition_labels,
                condition_colors=condition_colors,
                condition_styles=condition_styles,
                comparisons=comparisons,
                comparison_mode=comparison_mode,
                control=control,
            )
        )
        self.factorDict = getattr(self.condition_list, "factorDict", {})
        self.factor = list(getattr(self.condition_list, "factor", []) or [])
        self.aliases = aliases or {}
        self.filePath = os.fspath(file_path or os.getcwd())
        self.fig_path = os.fspath(
            fig_path
            if fig_path is not None
            else os.path.join(self.filePath, "Results", "Python Figures")
        )
        self.data_path = os.fspath(
            data_path
            if data_path is not None
            else os.path.join(self.filePath, "Results", "Data and Stats")
        )
        self.export_path = os.path.join(self.filePath, "Exports")
        self.image_fig_path = os.path.join(self.fig_path, "Images")
        self.representative_path = os.path.join(self.filePath, "Results", "Representative Images")
        self.legend_path = os.path.join(self.filePath, "Results", "Legends")

        self.summary = _normalise_frame(
            summary,
            condition_list=self.condition_list,
            condition_col=None if factor_cols else condition_col,
            animal_col=animal_col,
            factor_mappings=factor_mappings,
            require_condition=True,
        )

        if summaries is None:
            self.summaries = {str(roi_base): self.summary}
        else:
            self.summaries = {
                str(key): _normalise_frame(
                    value,
                    condition_list=self.condition_list,
                    condition_col=None if factor_cols else condition_col,
                    animal_col=animal_col,
                    factor_mappings=factor_mappings,
                    require_condition=True,
                )
                for key, value in summaries.items()
            }
            self.summaries.setdefault(str(roi_base), self.summary)

        self.region_dicts = {
            key: _build_region_dict(value, region_col=region_col)
            for key, value in self.summaries.items()
        }
        self.region_dict = self.region_dicts.get(str(roi_base), _build_region_dict(self.summary, region_col=region_col))

        self.data = {}
        for key, value in (data or {}).items():
            frame = value.df if hasattr(value, "df") else value
            frame = _normalise_animal_column(pd.DataFrame(frame).dropna(how="all"), animal_col)
            frame = _merge_summary_metadata(frame, self.summary, self.factor)
            frame = _normalise_frame(
                frame,
                condition_list=self.condition_list,
                condition_col="Condition",
                animal_col="AnimalName",
                factor_mappings=factor_mappings,
                require_condition=True,
            )
            self.data[str(key)] = DataFrameTable(str(key), frame)

        self.markers = set(self.data)
        self.images = images.copy() if isinstance(images, pd.DataFrame) else images
        self.imagesDict = {}
        self.representative_images = (
            representative_images.copy()
            if isinstance(representative_images, pd.DataFrame)
            else representative_images
        )

    def createSavePaths(self):
        """Create the common output directories and return ``self``."""
        for path in (
            self.fig_path,
            self.data_path,
            self.export_path,
            self.image_fig_path,
            self.representative_path,
            self.legend_path,
        ):
            os.makedirs(path, exist_ok=True)
        return self

    def getRegionDict(self, roi_base=None):
        """Return the condition -> animal -> region mapping used by iteration."""
        if roi_base is not None and str(roi_base) in self.region_dicts:
            return self.region_dicts[str(roi_base)]
        return self.region_dict

    def set_condition_list(self, condition_list):
        self.condition_list = _as_condition_list(condition_list)
        self.factorDict = getattr(self.condition_list, "factorDict", {})
        self.factor = list(getattr(self.condition_list, "factor", []) or [])
        return self

    def processData(self, *_, **__):
        """Compatibility no-op; DataFrameExperiment is already processed."""
        return self


def from_dataframe(summary, conditions=None, **kwargs):
    """Return a PyFLASH-compatible object backed by user-supplied DataFrames.

    Parameters are the same as :class:`DataFrameExperiment`. Pass a summary
    DataFrame plus either a ``groupList``/``conditionList`` or grouping columns
    such as ``group_col=...`` / ``group_cols=...``.
    """

    return DataFrameExperiment(summary, conditions, **kwargs)


def coerce_dataframe_input(
    obj,
    *,
    conditions=None,
    condition_col="Condition",
    factor_cols=None,
    animal_col="AnimalName",
    group_list=None,
    groups=None,
    group_col=None,
    group_cols=None,
    subject_col=None,
    factor_mappings=None,
    condition_order=None,
    condition_labels=None,
    condition_colors=None,
    condition_styles=None,
    condition_comparisons=None,
    condition_comparison_mode=None,
    condition_control=None,
    group_order=None,
    group_labels=None,
    group_colors=None,
    group_styles=None,
    group_comparisons=None,
    group_comparison_mode=None,
    group_control=None,
    fig_path=None,
    data_path=None,
    name="DataFrame",
    dataframe_kwargs=None,
):
    """Wrap raw DataFrame inputs; leave existing PyFLASH-like objects unchanged."""

    if not isinstance(obj, pd.DataFrame):
        return obj
    extra = dict(dataframe_kwargs or {})
    explicit = {
        "conditions": conditions,
        "group_list": group_list,
        "groups": groups,
        "name": name,
        "condition_col": condition_col,
        "factor_cols": factor_cols,
        "animal_col": animal_col,
        "group_col": group_col,
        "group_cols": group_cols,
        "subject_col": subject_col,
        "factor_mappings": factor_mappings,
        "condition_order": condition_order,
        "condition_labels": condition_labels,
        "condition_colors": condition_colors,
        "condition_styles": condition_styles,
        "comparisons": condition_comparisons,
        "comparison_mode": condition_comparison_mode,
        "control": condition_control,
        "group_order": group_order,
        "group_labels": group_labels,
        "group_colors": group_colors,
        "group_styles": group_styles,
        "group_comparisons": group_comparisons,
        "group_comparison_mode": group_comparison_mode,
        "group_control": group_control,
        "fig_path": fig_path,
        "data_path": data_path,
    }
    for key, value in explicit.items():
        if value is not None:
            extra[key] = value
    return from_dataframe(
        obj,
        **extra,
    )
