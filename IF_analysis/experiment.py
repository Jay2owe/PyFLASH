"""
Experiment class — imports CSVs, processes markers, builds summaries.
"""

import os
import re
import time
import zipfile
import numpy as np
import pandas as pd
from pathlib import Path
from functools import reduce
from collections import defaultdict
from collections.abc import Mapping
from read_roi import read_roi_zip
try:
    from roifile import roiread as roifile_read
except Exception:
    roifile_read = None

from IF_analysis.config import Config, check_directory
from IF_analysis.markers import (
    Attribute, Antibody, cellMarker, objectMarker, stainColors,
)
from IF_analysis.utils import (
    get_columns, get_nonobject_columns, adjust_for_volumemm,
    add_coloc_percentages, filter_dict,
    replace_cropped, add_scn_num, replace_week_int,
    normalize_image_roi_name, normalize_animal_name,
    ProgressTracker, format_elapsed,
)

# Maps subfolder names to marker class types
ATTRIBUTE_DICT = {
    "Objects": objectMarker,
    "Cells": cellMarker,
    "ROI Intensities": Antibody,
    "Attributes": Attribute,
}
NOT_INCLUDED_SENTINEL = "NOT_INCLUDED_IN_EXPERIMENT"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
BASE_IMAGE_COLUMNS = [
    "Experiment",
    "AnimalName",
    "Marker",
    "ROI",
    "ImageName",
    "ImagePath",
    "Extension",
]


def _empty_image_table() -> pd.DataFrame:
    return pd.DataFrame(columns=[c for c in BASE_IMAGE_COLUMNS if c != "Experiment"])


def _summarize_name_list(names, limit=3) -> str:
    cleaned = [str(name) for name in names if str(name).strip() != ""]
    if len(cleaned) == 0:
        return ""
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    return ", ".join(cleaned[:limit]) + f", +{len(cleaned) - limit} more"


def _image_marker_names(experiment) -> list[str]:
    names = set()
    for obj in getattr(experiment, "data", {}).values():
        if isinstance(obj, (objectMarker, cellMarker, Antibody)):
            names.add(str(obj.name).split("_ROI")[0])
    if len(names) == 0:
        names.update([str(m).split("_ROI")[0] for m in getattr(experiment, "markers", set())])
    return sorted(names, key=lambda s: (-len(str(s)), str(s)))


def _parse_image_name(image_name: str, marker_names) -> tuple[str, str]:
    image_name = str(image_name)
    for marker in marker_names:
        marker_s = str(marker)
        if image_name == marker_s:
            return marker_s, ""
        prefix = f"{marker_s}_"
        if image_name.startswith(prefix):
            return marker_s, image_name[len(prefix):]
    if "_" in image_name:
        marker, roi = image_name.split("_", 1)
        return marker, roi
    return image_name, ""


def _build_images_dict(image_df: pd.DataFrame) -> dict:
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return {}

    lookup = {}
    for row in image_df.itertuples(index=False):
        animal = str(getattr(row, "AnimalName", ""))
        marker = str(getattr(row, "Marker", ""))
        roi = str(getattr(row, "ROI", "") or getattr(row, "ImageName", ""))
        path = str(getattr(row, "ImagePath", ""))
        lookup.setdefault(animal, {}).setdefault(marker, {})[roi] = path
    return lookup


def _iter_source_order_objects(source, marker_names=None):
    data_dict = getattr(source, "data", {})
    if not isinstance(data_dict, Mapping) or len(data_dict) == 0:
        return []

    items = list(data_dict.items())
    marker_items = [
        item for item in items
        if isinstance(item[1], (objectMarker, cellMarker, Antibody))
    ]
    if len(marker_items) > 0:
        items = marker_items

    def _marker_label(item):
        key, value = item
        raw = str(getattr(value, "name", key)).strip()
        return raw.split("_ROI")[0].strip()

    if marker_names is None:
        return items

    if isinstance(marker_names, str):
        marker_iter = [marker_names]
    else:
        try:
            marker_iter = list(marker_names)
        except TypeError:
            marker_iter = [marker_names]

    requested = [
        str(marker).strip().casefold()
        for marker in marker_iter
        if str(marker).strip() != ""
    ]
    if len(requested) == 0:
        return items

    ordered = []
    used_idx = set()
    for marker in requested:
        for idx, item in enumerate(items):
            if idx in used_idx:
                continue
            if _marker_label(item).casefold() == marker:
                ordered.append(item)
                used_idx.add(idx)
    ordered.extend(item for idx, item in enumerate(items) if idx not in used_idx)
    return ordered


def _source_panel_order_rows(source, marker_names=None) -> pd.DataFrame:
    records = []
    seen_scns = set()
    group_counts = defaultdict(int)

    for key, value in _iter_source_order_objects(source, marker_names=marker_names):
        df = getattr(value, "df", None)
        if (
            not isinstance(df, pd.DataFrame)
            or df.empty
            or "AnimalName" not in df.columns
            or "ImageROI" not in df.columns
        ):
            continue

        if "Experiment" in df.columns:
            exp_values = df["Experiment"].fillna("").astype(str)
        else:
            exp_name = str(
                getattr(getattr(value, "experiment", None), "name", "")
                or getattr(source, "name", "")
            ).strip()
            exp_values = pd.Series(exp_name, index=df.index, dtype="object")

        scn_values = (
            df["SCN"].fillna("").astype(str)
            if "SCN" in df.columns
            else pd.Series("", index=df.index, dtype="object")
        )

        frame = pd.DataFrame({
            "Experiment": exp_values,
            "AnimalName": df["AnimalName"].fillna("").astype(str),
            "SCN": scn_values,
            "ImageROI": df["ImageROI"].fillna("").astype(str),
        }, index=df.index)

        for row in frame.itertuples(index=False):
            exp_name = str(getattr(row, "Experiment", "")).strip()
            animal_name = str(getattr(row, "AnimalName", "")).strip()
            scn_name = str(getattr(row, "SCN", "")).strip()
            image_roi = normalize_image_roi_name(getattr(row, "ImageROI", ""))
            if animal_name == "" or scn_name == "" or image_roi == "":
                continue

            exp_key = exp_name.casefold()
            animal_key = normalize_animal_name(animal_name).casefold()
            scn_key = scn_name.casefold()
            dedup_key = (exp_key, animal_key, scn_key)
            if dedup_key in seen_scns:
                continue
            seen_scns.add(dedup_key)

            group_key = (exp_key, animal_key)
            order_idx = group_counts[group_key]
            group_counts[group_key] = order_idx + 1
            records.append({
                "Experiment": exp_name,
                "AnimalName": animal_name,
                "SCN": scn_name,
                "ImageROI": image_roi,
                "__source_order__": int(order_idx),
            })

    if len(records) == 0:
        return pd.DataFrame(columns=["Experiment", "AnimalName", "SCN", "ImageROI", "__source_order__"])
    return pd.DataFrame.from_records(records)


def _sort_image_table(image_df: pd.DataFrame, source=None, marker_names=None) -> pd.DataFrame:
    """Sort image tables in ROI drawing order: LHSCN, RHSCN, LHSCN2, RHSCN2."""
    if not isinstance(image_df, pd.DataFrame) or image_df.empty:
        return image_df

    out = image_df.copy()
    sort_cols = []

    if "Experiment" in out.columns:
        sort_cols.append("Experiment")
    if "Condition" in out.columns:
        sort_cols.append("Condition")
    if "AnimalName" in out.columns:
        sort_cols.append("AnimalName")

    if "ROI" in out.columns:
        roi_norm = out["ROI"].map(normalize_image_roi_name)

        if source is not None and "AnimalName" in out.columns:
            order_rows = _source_panel_order_rows(source, marker_names=marker_names)
            if not order_rows.empty:
                order_map = order_rows.copy()
                order_map["__AnimalNameKey__"] = order_map["AnimalName"].map(normalize_animal_name)
                order_map["__ImageROIKey__"] = order_map["ImageROI"].map(normalize_image_roi_name)
                merge_cols = ["__AnimalNameKey__", "__ImageROIKey__"]
                out["__AnimalNameKey__"] = out["AnimalName"].map(normalize_animal_name)
                out["__ImageROIKey__"] = roi_norm
                if "Experiment" in out.columns and "Experiment" in order_map.columns:
                    order_map["__ExperimentKey__"] = order_map["Experiment"].fillna("").astype(str).str.casefold()
                    out["__ExperimentKey__"] = out["Experiment"].fillna("").astype(str).str.casefold()
                    merge_cols = ["__ExperimentKey__"] + merge_cols
                order_map = order_map[merge_cols + ["__source_order__"]].drop_duplicates(
                    subset=merge_cols,
                    keep="first",
                )
                out = out.merge(order_map, on=merge_cols, how="left")
                out["__source_missing__"] = out["__source_order__"].isna().astype(int)
                sort_cols.extend(["__source_missing__", "__source_order__"])

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

        out["__roi_group__"] = roi_norm.map(_roi_group)
        out["__roi_side__"] = roi_norm.map(_roi_side)
        out["__roi_norm__"] = roi_norm
        sort_cols.extend(["__roi_group__", "__roi_side__", "__roi_norm__", "ROI"])

    sort_cols.extend([c for c in ["Marker", "ImageName"] if c in out.columns])
    sort_cols = [c for idx, c in enumerate(sort_cols) if c not in sort_cols[:idx]]
    if len(sort_cols) == 0:
        return out

    out = out.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    return out.drop(
        columns=[
            "__roi_group__", "__roi_side__", "__roi_norm__",
            "__AnimalNameKey__", "__ImageROIKey__", "__ExperimentKey__",
            "__source_order__", "__source_missing__",
        ],
        errors="ignore",
    )


def _image_summary_meta(experiment):
    summary = getattr(experiment, "summary", None)
    if not isinstance(summary, pd.DataFrame) or summary.empty or "AnimalName" not in summary.columns:
        return None

    cols = ["AnimalName"]
    for col in ["Condition"]:
        if col in summary.columns and col not in cols:
            cols.append(col)
    for factor in getattr(experiment, "factor", []):
        if factor in summary.columns and factor not in cols:
            cols.append(factor)
    return summary[cols].drop_duplicates(subset=["AnimalName"])


def _attach_image_metadata(experiment, image_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(image_df, pd.DataFrame):
        return _empty_image_table()
    if image_df.empty:
        return image_df.copy()

    meta = _image_summary_meta(experiment)
    if meta is None:
        return image_df.copy()

    out = image_df.copy()
    refresh_cols = [c for c in meta.columns if c != "AnimalName" and c in out.columns]
    if len(refresh_cols) > 0:
        out = out.drop(columns=refresh_cols, errors="ignore")
    return out.merge(meta, on="AnimalName", how="left")


def _get_image_table(experiment, include_summary=True):
    image_df = getattr(experiment, "images", None)
    if not isinstance(image_df, pd.DataFrame):
        image_df = experiment.importImages(progress=False)
    if not isinstance(image_df, pd.DataFrame):
        image_df = _empty_image_table()
    if include_summary:
        if not image_df.empty:
            image_df = _attach_image_metadata(experiment, image_df)
            experiment.images = image_df
        return image_df.copy()

    base_cols = [c for c in BASE_IMAGE_COLUMNS if c in image_df.columns]
    return image_df[base_cols].copy()


def _parse_roi_name_from_zip_key(roi_key: str) -> str:
    roi_key_s = replace_week_int(str(roi_key).strip())
    if roi_key_s == "":
        return ""

    parts = [part.strip() for part in roi_key_s.split("_") if part.strip() != ""]
    if len(parts) <= 1:
        return roi_key_s

    roi_parts = parts[1:]
    while len(roi_parts) > 0 and roi_parts[-1].casefold().startswith("cropped"):
        roi_parts = roi_parts[:-1]
    if len(roi_parts) == 0:
        roi_parts = parts[1:]
    return "_".join(roi_parts)


def _uncropped_roi_zip_key(roi_key: str) -> str:
    return re.sub(r"_Cropped(?=(?:-\d+)?$)", "", str(roi_key).strip(), flags=re.IGNORECASE)


def _cropped_roi_zip_key(source_key: str) -> str:
    source = str(source_key).strip()
    match = re.search(r"-(\d+)$", source)
    if match is None:
        return f"{source}_Cropped"
    suffix = match.group(1)
    base = source[:-(len(suffix) + 1)]
    return f"{base}_Cropped-{suffix}"


def _scn_name_from_roi_keys(roi_key: str, source_key: str | None = None) -> tuple[str, str, str]:
    """Build stable AnimalName / SCN / raw-ROI labels from ROI zip keys."""
    roi_key_s = replace_week_int(str(roi_key).strip())
    source_key_s = replace_week_int(str(source_key).strip()) if source_key is not None else _uncropped_roi_zip_key(roi_key_s)

    parts = [part.strip() for part in roi_key_s.split("_") if part.strip() != ""]
    animal_name = parts[0] if len(parts) > 0 else ""

    source_roi_name = _parse_roi_name_from_zip_key(source_key_s)
    roi_name_raw = source_roi_name if source_roi_name != "" else _parse_roi_name_from_zip_key(roi_key_s)

    if len(parts) >= 2:
        scn_name = replace_week_int(parts[0]) + parts[1] + replace_cropped(parts[-1])
        scn_name = add_scn_num(scn_name, roi_key_s)
    else:
        scn_name = f"{animal_name}{roi_name_raw}" if animal_name != "" and roi_name_raw != "" else roi_name_raw
    return animal_name, scn_name, roi_name_raw


def _roi_info_value(info, key, default=None):
    if isinstance(info, Mapping):
        return info.get(key, default)
    return getattr(info, key, default)


def _build_roi_records_from_map(roi_map, *, include_cropped=True):
    if not isinstance(roi_map, Mapping) or len(roi_map) == 0:
        return None

    records = {}
    for roi_key, info in roi_map.items():
        roi_key_s = str(roi_key).strip()
        is_cropped = "cropped" in roi_key_s.casefold()
        if bool(include_cropped) != bool(is_cropped):
            continue

        if include_cropped:
            source_key = _uncropped_roi_zip_key(roi_key_s)
            scn_key = roi_key_s
        else:
            source_key = roi_key_s
            scn_key = _cropped_roi_zip_key(source_key)

        source_info = roi_map.get(source_key, info)
        animal_name, scn_name, roi_name_raw = _scn_name_from_roi_keys(scn_key, source_key=source_key)
        current_extents = _roi_extent_values(info)
        source_extents = _roi_extent_values(source_info)

        record = {
            "name": roi_key_s,
            "x": _roi_info_value(info, "x"),
            "y": _roi_info_value(info, "y"),
            "left": _roi_info_value(info, "left", current_extents.get("min_x")),
            "top": _roi_info_value(info, "top", current_extents.get("min_y")),
            "right": _roi_info_value(info, "right", current_extents.get("max_x")),
            "bottom": _roi_info_value(info, "bottom", current_extents.get("max_y")),
            "width": _roi_info_value(info, "width", current_extents.get("width")),
            "height": _roi_info_value(info, "height", current_extents.get("height")),
            "ImageMinX": source_extents.get("min_x"),
            "ImageMinY": source_extents.get("min_y"),
            "ImageMaxX": source_extents.get("max_x"),
            "ImageMaxY": source_extents.get("max_y"),
            "ImageLeft": _roi_info_value(source_info, "left", source_extents.get("min_x")),
            "ImageTop": _roi_info_value(source_info, "top", source_extents.get("min_y")),
            "ImageRight": _roi_info_value(source_info, "right", source_extents.get("max_x")),
            "ImageBottom": _roi_info_value(source_info, "bottom", source_extents.get("max_y")),
            "ImageWidth": _roi_info_value(source_info, "width", source_extents.get("width")),
            "ImageHeight": _roi_info_value(source_info, "height", source_extents.get("height")),
            "ROIKey": roi_key_s,
            "SourceROIKey": source_key,
            "SCN": scn_name,
            "AnimalName": animal_name,
            "ROINameRaw": roi_name_raw,
        }
        records[roi_key_s] = record

    return records if len(records) > 0 else None


def _roifile_coordinates(roi) -> np.ndarray | None:
    for attr in ["coordinates", "subpixel_coordinates", "integer_coordinates"]:
        value = getattr(roi, attr, None)
        if value is None:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        try:
            arr = np.asarray(value)
        except Exception:
            continue
        if arr.ndim == 2 and arr.shape[1] >= 2 and arr.size > 0:
            return arr[:, :2]
    return None


def _roi_extent_values(info) -> dict:
    """Summarize an ROI into a bounding frame using polygon coordinates first."""
    if isinstance(info, Mapping):
        x_vals = info.get("x", None)
        y_vals = info.get("y", None)
        left = info.get("left", None)
        top = info.get("top", None)
        right = info.get("right", None)
        bottom = info.get("bottom", None)
    else:
        x_vals = getattr(info, "x", None)
        y_vals = getattr(info, "y", None)
        left = getattr(info, "left", None)
        top = getattr(info, "top", None)
        right = getattr(info, "right", None)
        bottom = getattr(info, "bottom", None)

    out = {
        "min_x": None,
        "min_y": None,
        "max_x": None,
        "max_y": None,
        "width": None,
        "height": None,
    }

    try:
        if x_vals is not None and y_vals is not None:
            xs = np.asarray(x_vals, dtype=float).ravel()
            ys = np.asarray(y_vals, dtype=float).ravel()
            xs = xs[np.isfinite(xs)]
            ys = ys[np.isfinite(ys)]
            if xs.size > 0 and ys.size > 0:
                out["min_x"] = float(xs.min())
                out["min_y"] = float(ys.min())
                out["max_x"] = float(xs.max())
                out["max_y"] = float(ys.max())
    except Exception:
        pass

    try:
        left_f = None if left is None else float(left)
        top_f = None if top is None else float(top)
        right_f = None if right is None else float(right)
        bottom_f = None if bottom is None else float(bottom)
    except Exception:
        left_f, top_f, right_f, bottom_f = None, None, None, None

    if out["min_x"] is None and left_f is not None:
        out["min_x"] = left_f
    if out["min_y"] is None and top_f is not None:
        out["min_y"] = top_f
    if out["max_x"] is None and right_f is not None:
        out["max_x"] = right_f
    if out["max_y"] is None and bottom_f is not None:
        out["max_y"] = bottom_f

    if out["min_x"] is not None and out["max_x"] is not None:
        out["width"] = float(out["max_x"] - out["min_x"])
    if out["min_y"] is not None and out["max_y"] is not None:
        out["height"] = float(out["max_y"] - out["min_y"])
    return out


def _read_roi_zip_with_bounds(file_path: str):
    if roifile_read is None:
        return None

    try:
        rois = roifile_read(file_path)
    except Exception:
        return None
    if not isinstance(rois, list):
        rois = [rois]

    try:
        with zipfile.ZipFile(file_path) as zf:
            entry_names = [
                Path(name).stem
                for name in zf.namelist()
                if str(name).lower().endswith(".roi")
            ]
    except Exception:
        return None

    if len(entry_names) != len(rois):
        return None

    roifile_map = {}
    for entry_name, roi in zip(entry_names, rois):
        coords = _roifile_coordinates(roi)
        x_vals = None if coords is None else np.asarray(coords[:, 0], dtype=float)
        y_vals = None if coords is None else np.asarray(coords[:, 1], dtype=float)
        left = getattr(roi, "left", None)
        top = getattr(roi, "top", None)
        right = getattr(roi, "right", None)
        bottom = getattr(roi, "bottom", None)
        try:
            left = None if left is None else float(left)
            top = None if top is None else float(top)
            right = None if right is None else float(right)
            bottom = None if bottom is None else float(bottom)
        except Exception:
            left, top, right, bottom = None, None, None, None
        extents = _roi_extent_values({
            "x": x_vals,
            "y": y_vals,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
        })
        roifile_map[entry_name] = {
            "x": x_vals,
            "y": y_vals,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "min_x": extents.get("min_x"),
            "min_y": extents.get("min_y"),
            "max_x": extents.get("max_x"),
            "max_y": extents.get("max_y"),
            "width": extents.get("width"),
            "height": extents.get("height"),
        }

    return _build_roi_records_from_map(roifile_map, include_cropped=True)


def _read_full_roi_zip_with_bounds(file_path: str):
    if roifile_read is None:
        return None

    try:
        rois = roifile_read(file_path)
    except Exception:
        return None
    if not isinstance(rois, list):
        rois = [rois]

    try:
        with zipfile.ZipFile(file_path) as zf:
            entry_names = [
                Path(name).stem
                for name in zf.namelist()
                if str(name).lower().endswith(".roi")
            ]
    except Exception:
        return None

    if len(entry_names) != len(rois):
        return None

    roifile_map = {}
    for entry_name, roi in zip(entry_names, rois):
        coords = _roifile_coordinates(roi)
        x_vals = None if coords is None else np.asarray(coords[:, 0], dtype=float)
        y_vals = None if coords is None else np.asarray(coords[:, 1], dtype=float)
        left = getattr(roi, "left", None)
        top = getattr(roi, "top", None)
        right = getattr(roi, "right", None)
        bottom = getattr(roi, "bottom", None)
        try:
            left = None if left is None else float(left)
            top = None if top is None else float(top)
            right = None if right is None else float(right)
            bottom = None if bottom is None else float(bottom)
        except Exception:
            left, top, right, bottom = None, None, None, None
        extents = _roi_extent_values({
            "x": x_vals,
            "y": y_vals,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
        })
        roifile_map[entry_name] = {
            "x": x_vals,
            "y": y_vals,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "min_x": extents.get("min_x"),
            "min_y": extents.get("min_y"),
            "max_x": extents.get("max_x"),
            "max_y": extents.get("max_y"),
            "width": extents.get("width"),
            "height": extents.get("height"),
        }

    return _build_roi_records_from_map(roifile_map, include_cropped=False)


def _finalize_roi_name_labels(roi_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(roi_df, pd.DataFrame) or roi_df.empty:
        return pd.DataFrame(columns=["AnimalName", "SCN", "ImageROI"])

    out = roi_df.copy()
    base = out.get("ROINameRaw", out["SCN"]).fillna("").astype(str).str.strip()
    fallback = out["SCN"].fillna("").astype(str).str.strip()
    base = base.where(base != "", fallback)
    out["ImageROI"] = [normalize_image_roi_name(value) for value in base]

    if {"AnimalName", "ImageMinX", "ImageMaxX"}.issubset(out.columns) or {"AnimalName", "ImageLeft", "ImageRight"}.issubset(out.columns):
        match_mask = base.astype(str).str.fullmatch(r"(?i)SCN\d*(?:-\d+)?")
        if match_mask.any():
            group_num = (
                base[match_mask]
                .astype(str)
                .str.extract(r"(?i)^SCN(\d*)", expand=False)
                .fillna("")
                .replace("", "1")
            )
            centers = (
                pd.to_numeric(
                    out.loc[match_mask, "ImageMinX"] if "ImageMinX" in out.columns else out.loc[match_mask, "ImageLeft"],
                    errors="coerce",
                )
                + pd.to_numeric(
                    out.loc[match_mask, "ImageMaxX"] if "ImageMaxX" in out.columns else out.loc[match_mask, "ImageRight"],
                    errors="coerce",
                )
            ) / 2.0
            tmp = pd.DataFrame({
                "AnimalName": out.loc[match_mask, "AnimalName"].astype(str),
                "__group__": group_num.astype(str),
                "__center__": centers.astype(float),
            }, index=out.index[match_mask])
            tmp = tmp.dropna(subset=["__center__"])
            for (_, group), idxs in tmp.groupby(["AnimalName", "__group__"]).groups.items():
                ordered = list(
                    tmp.loc[list(idxs)]
                    .sort_values("__center__", kind="stable")
                    .index
                )
                suffix = "" if str(group) in {"", "1"} else str(group)
                if len(ordered) >= 1:
                    out.loc[ordered[0], "ImageROI"] = f"LHSCN{suffix}"
                if len(ordered) >= 2:
                    out.loc[ordered[1], "ImageROI"] = f"RHSCN{suffix}"

    out["__dup_index__"] = out.groupby(["AnimalName", "ImageROI"]).cumcount() + 1
    out["__dup_size__"] = out.groupby(["AnimalName", "ImageROI"])["ImageROI"].transform("size")
    dup_mask = out["__dup_size__"] > 1
    suffix_mask = dup_mask & (out["__dup_index__"] > 1)
    out.loc[suffix_mask, "ImageROI"] = (
        out.loc[suffix_mask, "ImageROI"]
        + "_"
        + out.loc[suffix_mask, "__dup_index__"].astype(str)
    )
    out = out.drop(columns=["__dup_index__", "__dup_size__"], errors="ignore")
    return out


def _image_roi_name_from_panel_index(index: int) -> str:
    panel_index = max(0, int(index))
    pair_index = (panel_index // 2) + 1
    side = "LH" if (panel_index % 2) == 0 else "RH"
    suffix = "" if pair_index == 1 else str(pair_index)
    return f"{side}SCN{suffix}"


def _align_image_roi_to_master_order(master_scn: pd.DataFrame) -> pd.DataFrame:
    if (
        not isinstance(master_scn, pd.DataFrame)
        or master_scn.empty
        or "AnimalName" not in master_scn.columns
        or "SCN" not in master_scn.columns
    ):
        return pd.DataFrame(columns=["AnimalName", "SCN", "ImageROI"])

    records = []
    for animal_name, group in master_scn.groupby("AnimalName", sort=False, dropna=False):
        ordered = group.reset_index(drop=True)
        for idx, row in ordered.iterrows():
            records.append({
                "AnimalName": row["AnimalName"],
                "SCN": row["SCN"],
                "ImageROI": _image_roi_name_from_panel_index(idx),
            })
    return pd.DataFrame.from_records(records)


def _apply_roi_name_map(df: pd.DataFrame, roi_name_map: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        return df
    if (
        not isinstance(roi_name_map, pd.DataFrame)
        or roi_name_map.empty
        or "AnimalName" not in df.columns
        or "SCN" not in df.columns
    ):
        return df

    preserved_image_roi = None
    if "ImageROI" in df.columns:
        preserved_image_roi = df["ImageROI"].copy()

    image_roi_cols = [c for c in df.columns if str(c).startswith("ImageROI")]
    base = df.drop(columns=image_roi_cols, errors="ignore").copy()
    base["__AnimalNameKey__"] = base["AnimalName"].map(normalize_animal_name)
    roi_map = roi_name_map[["AnimalName", "SCN", "ImageROI"]].drop_duplicates(
        subset=["AnimalName", "SCN"], keep="first"
    ).copy()
    roi_map["__AnimalNameKey__"] = roi_map["AnimalName"].map(normalize_animal_name)
    roi_map = roi_map.drop(columns=["AnimalName"], errors="ignore")
    out = base.merge(
        roi_map,
        on=["__AnimalNameKey__", "SCN"],
        how="left",
    ).drop(columns=["__AnimalNameKey__"], errors="ignore")
    if "ImageROI" in out.columns:
        roi_name = out["ImageROI"].fillna("").astype(str).str.strip()
        if preserved_image_roi is not None and len(preserved_image_roi) == len(out):
            prev_roi = preserved_image_roi.fillna("").astype(str).str.strip()
            roi_name = roi_name.where(roi_name != "", prev_roi)
        scn_vals = out["SCN"].fillna("").astype(str).str.strip()
        out["ImageROI"] = roi_name.where(roi_name != "", scn_vals)
    return out


def _replace_not_included_with_nan(df: pd.DataFrame, columns=None, sentinel=NOT_INCLUDED_SENTINEL):
    """Convert sentinel-like string cells to NaN for numeric-safe aggregation."""
    out = df.copy()
    cols = list(columns) if columns is not None else list(out.columns)
    for col in cols:
        if col not in out.columns:
            continue
        s = out[col]
        if (
            pd.api.types.is_object_dtype(s)
            or pd.api.types.is_string_dtype(s)
            or pd.api.types.is_categorical_dtype(s)
        ):
            mask = s.astype(str).str.contains(str(sentinel), na=False)
            if mask.any():
                out.loc[mask, col] = np.nan
    return out


def _to_numeric_series_excluding_sentinel(series: pd.Series, sentinel=NOT_INCLUDED_SENTINEL) -> pd.Series:
    """Convert a Series to numeric while treating sentinel tokens as missing."""
    s = series.copy()
    if (
        pd.api.types.is_object_dtype(s)
        or pd.api.types.is_string_dtype(s)
        or pd.api.types.is_categorical_dtype(s)
    ):
        mask = s.astype(str).str.contains(str(sentinel), na=False)
        if mask.any():
            s = s.mask(mask)
    return pd.to_numeric(s, errors='coerce')


def _log1p_nonnegative(series: pd.Series) -> pd.Series:
    """Log-normalize with log1p after dropping negative values."""
    s = pd.to_numeric(series, errors='coerce')
    s = s.where(s >= 0, np.nan)
    with np.errstate(invalid='ignore'):
        return np.log1p(s)


def _zscore_series(series: pd.Series) -> pd.Series:
    """Z-score a numeric series; constant series become 0 for valid rows."""
    s = pd.to_numeric(series, errors='coerce')
    mu = s.mean(skipna=True)
    sigma = s.std(skipna=True, ddof=0)
    if not np.isfinite(sigma) or sigma == 0:
        out = pd.Series(np.nan, index=s.index, dtype=float)
        out.loc[s.notna()] = 0.0
        return out
    return (s - mu) / sigma


def _coerce_binary_indicator(series: pd.Series) -> pd.Series:
    """Coerce mixed-type indicator series to boolean with NaN -> False."""
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


def _resolve_combo_intden_column(stain_df: pd.DataFrame, marker_name: str) -> str | None:
    """Pick the best per-object IntDen source column for combo IntDen totals."""
    exact = f"{marker_name}_IntDen"
    if exact in stain_df.columns:
        return exact

    esc = re.escape(str(marker_name))
    candidates = [
        str(c) for c in stain_df.columns
        if str(c).startswith(f"{marker_name}_")
        and ("IntDen" in str(c))
        and all(tok not in str(c) for tok in [
            "MeanIntDen", "StdDev", "Median", "Min", "Max",
            "Coloc", "Contains", "ClosestTo", "NumColoc", "NumClosestTo",
            "DistTo", "Ratio", "ROI",
        ])
    ]
    if len(candidates) == 0:
        return None

    def _rank(col: str):
        s = str(col)
        if s == f"{marker_name}_IntDen":
            return (0, len(s), s)
        if re.match(rf"^{esc}_IntDen(?:$|_)", s):
            return (1, len(s), s)
        return (2, len(s), s)

    candidates = sorted(candidates, key=_rank)
    return candidates[0]


def _resolve_combo_mean_intden_column(stain_df: pd.DataFrame, marker_name: str) -> str | None:
    """Pick a per-object MeanIntDen source column for combo mean-intensity summaries."""
    exact = f"{marker_name}_MeanIntDen"
    if exact in stain_df.columns:
        return exact

    esc = re.escape(str(marker_name))
    candidates = [
        str(c) for c in stain_df.columns
        if str(c).startswith(f"{marker_name}_")
        and ("MeanIntDen" in str(c))
        and all(tok not in str(c) for tok in [
            "Coloc", "Contains", "ClosestTo", "NumColoc", "NumClosestTo",
            "DistTo", "Ratio", "ROI",
        ])
    ]
    if len(candidates) == 0:
        return None

    def _rank(col: str):
        s = str(col)
        if s == f"{marker_name}_MeanIntDen":
            return (0, len(s), s)
        if re.match(rf"^{esc}_MeanIntDen(?:$|_)", s):
            return (1, len(s), s)
        return (2, len(s), s)

    candidates = sorted(candidates, key=_rank)
    return candidates[0]


def _combo_indicator_columns(df: pd.DataFrame, marker_name: str) -> list[str]:
    """Derived per-object combo membership columns stored on marker dataframes."""
    prefix = f"{str(marker_name)}_Combo_"
    metric_suffixes = ("_Count", "_Count%", "_IntDenTotal", "_MeanIntDen")
    out = []
    for col in df.columns:
        col_s = str(col)
        if not col_s.startswith(prefix):
            continue
        if any(col_s.endswith(suf) for suf in metric_suffixes):
            continue
        out.append(col_s)
    return out


def _build_coloc_combo_summaries(stain_df: pd.DataFrame, marker_name: str):
    """
    Build per-object combo indicators and per-animal combo summaries.

    Returns
    -------
    combo_indicator_df : DataFrame
        Columns:
        - <marker>_Combo_<signature>   (binary per-object membership)
    combo_count_df : DataFrame
        Columns:
        - <marker>_Combo_<signature>_Count
        - <marker>_Combo_<signature>_Count%
    combo_intden_df : DataFrame
        Columns:
        - <marker>_Combo_<signature>_IntDenTotal
    combo_mean_intden_df : DataFrame
        Columns:
        - <marker>_Combo_<signature>_MeanIntDen
    """
    if "AnimalName" not in stain_df.columns:
        return pd.DataFrame(index=stain_df.index), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    marker_s = str(marker_name)
    esc = re.escape(marker_s)
    patterns = [
        ("ColocCount", re.compile(rf"^{esc}_ColocCount(?P<m2>.+)$")),
        ("Contains", re.compile(rf"^{esc}_Contains_(?P<m2>.+)$")),
    ]
    kind_rank = {"ColocCount": 0, "Contains": 1}

    detected = []
    for c in stain_df.columns:
        c_s = str(c)
        for kind, rx in patterns:
            m = rx.match(c_s)
            if m is not None:
                detected.append((kind, str(m.group("m2")), c_s))
                break
    if len(detected) == 0:
        return pd.DataFrame(index=stain_df.index), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    detected = sorted(detected, key=lambda t: (str(t[1]), kind_rank[t[0]], str(t[2])))
    indicator_cols = [c for _, _, c in detected]

    base_count_col = f"{marker_s}_Count"
    if base_count_col in stain_df.columns:
        base_count = _to_numeric_series_excluding_sentinel(stain_df[base_count_col]).fillna(0.0)
        base_count = base_count.where(base_count > 0, 0.0)
        base_count = base_count.where(base_count <= 1, 1.0)
    else:
        base_count = pd.Series(1.0, index=stain_df.index, dtype=float)

    valid_mask = base_count > 0
    if not bool(valid_mask.any()):
        return pd.DataFrame(index=stain_df.index), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    work = stain_df.loc[valid_mask, ["AnimalName"] + indicator_cols].copy()
    work_animals = work["AnimalName"].astype(str)
    weight = base_count.loc[valid_mask].astype(float)

    bool_df = pd.DataFrame(index=work.index)
    for c in indicator_cols:
        bool_df[c] = _coerce_binary_indicator(work[c])

    signatures = []
    meta = [(kind, m2) for kind, m2, _ in detected]
    for row in bool_df.itertuples(index=False, name=None):
        parts = []
        for value, (kind, m2) in zip(row, meta):
            if not bool(value):
                # Negative states (e.g., marker-, woMarker) are intentionally
                # omitted from combo names as requested.
                continue
            if kind == "ColocCount":
                parts.append(f"{m2}+")
            else:
                parts.append(f"w{m2}")
        signatures.append("_".join(parts) if len(parts) > 0 else "None")
    combo_series = pd.Series(signatures, index=work.index, name="_combo")
    combo_indicator_df = pd.get_dummies(combo_series)
    combo_indicator_df = combo_indicator_df.reindex(
        columns=sorted(combo_indicator_df.columns.tolist()),
        fill_value=0,
    ).astype(np.int8)
    combo_indicator_df = combo_indicator_df.rename(
        columns={sig: f"{marker_s}_Combo_{str(sig)}" for sig in combo_indicator_df.columns}
    )
    combo_indicator_df = combo_indicator_df.reindex(stain_df.index, fill_value=0)

    count_input = pd.DataFrame({
        "AnimalName": work_animals,
        "_combo": combo_series,
        "_w": weight,
    })
    combo_count = count_input.groupby(["AnimalName", "_combo"])["_w"].sum().unstack(fill_value=0.0)
    count_cols = {
        c: f"{marker_s}_Combo_{str(c)}_Count"
        for c in combo_count.columns
    }
    combo_count = combo_count.rename(columns=count_cols)

    denom = weight.groupby(work_animals).sum().replace(0, np.nan)
    combo_pct = combo_count.div(denom, axis=0) * 100.0
    combo_pct = combo_pct.rename(columns={
        c: f"{str(c)}%"
        for c in combo_count.columns
    })
    combo_count_df = pd.concat([combo_count, combo_pct], axis=1)

    intden_col = _resolve_combo_intden_column(stain_df, marker_s)
    if intden_col is None:
        combo_intden = pd.DataFrame()
    else:
        intden = _to_numeric_series_excluding_sentinel(stain_df[intden_col]).loc[valid_mask].fillna(0.0)
        intden_input = pd.DataFrame({
            "AnimalName": work_animals,
            "_combo": combo_series,
            "_intden": intden,
        })
        combo_intden = intden_input.groupby(["AnimalName", "_combo"])["_intden"].sum().unstack(fill_value=0.0)
        combo_intden = combo_intden.rename(columns={
            c: f"{marker_s}_Combo_{str(c)}_IntDenTotal"
            for c in combo_intden.columns
        })

    mean_intden_col = _resolve_combo_mean_intden_column(stain_df, marker_s)
    if mean_intden_col is None:
        combo_mean_intden = pd.DataFrame()
    else:
        mean_intden = _to_numeric_series_excluding_sentinel(stain_df[mean_intden_col]).loc[valid_mask]
        mean_intden_input = pd.DataFrame({
            "AnimalName": work_animals,
            "_combo": combo_series,
            "_mean_intden": mean_intden,
        })
        combo_mean_intden = mean_intden_input.groupby(["AnimalName", "_combo"])["_mean_intden"].mean().unstack()
        combo_mean_intden = combo_mean_intden.rename(columns={
            c: f"{marker_s}_Combo_{str(c)}_MeanIntDen"
            for c in combo_mean_intden.columns
        })

    return combo_indicator_df, combo_count_df, combo_intden, combo_mean_intden


def _all_sources_are_sentinel(df: pd.DataFrame, cols, sentinel=NOT_INCLUDED_SENTINEL) -> pd.Series:
    """Row-wise mask: True when all provided source columns are sentinel-like strings."""
    valid_cols = [c for c in cols if c in df.columns]
    if len(valid_cols) == 0:
        return pd.Series(False, index=df.index)

    masks = []
    for col in valid_cols:
        s = df[col]
        if (
            pd.api.types.is_object_dtype(s)
            or pd.api.types.is_string_dtype(s)
            or pd.api.types.is_categorical_dtype(s)
        ):
            m = s.astype(str).str.contains(str(sentinel), na=False)
        else:
            m = pd.Series(False, index=df.index)
        masks.append(m)

    combined = masks[0].copy()
    for m in masks[1:]:
        combined = combined & m
    return combined


def _ensure_animalname_column(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee a merge-ready `AnimalName` column exists."""
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame(columns=["AnimalName"])

    out = df.copy()
    if "AnimalName" in out.columns:
        return out

    if out.index.nlevels == 1:
        idx_name = out.index.name
        out = out.reset_index()
        if idx_name is None and "index" in out.columns:
            out = out.rename(columns={"index": "AnimalName"})
        elif idx_name is not None and idx_name in out.columns and idx_name != "AnimalName":
            out = out.rename(columns={idx_name: "AnimalName"})
        if "AnimalName" not in out.columns:
            first_col = out.columns[0] if len(out.columns) > 0 else None
            if first_col is not None:
                out = out.rename(columns={first_col: "AnimalName"})
    else:
        out = out.reset_index()
        if "AnimalName" not in out.columns:
            first_col = out.columns[0] if len(out.columns) > 0 else None
            if first_col is not None:
                out = out.rename(columns={first_col: "AnimalName"})
    return out


def _condition_from_animal_name(values) -> pd.Series:
    """Derive condition token by keeping alphabetic chars from AnimalName."""
    s = pd.Series(values).astype(str)
    return s.map(lambda x: "".join(filter(str.isalpha, x)))


def _fill_intden_totals_with_zero(summary: pd.DataFrame, sentinel=NOT_INCLUDED_SENTINEL) -> pd.DataFrame:
    """
    Ensure IntDenTotal-like columns are zero-filled (never NaN), while preserving
    NOT_INCLUDED sentinel cells as sentinel strings.
    """
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        return summary

    out = summary.copy()
    intden_cols = [c for c in out.columns if "IntDenTotal" in str(c)]
    for col in intden_cols:
        s = out[col]
        if (
            pd.api.types.is_object_dtype(s)
            or pd.api.types.is_string_dtype(s)
            or pd.api.types.is_categorical_dtype(s)
        ):
            sent_mask = s.astype(str).str.contains(str(sentinel), na=False)
            num = pd.to_numeric(s.mask(sent_mask), errors="coerce").fillna(0.0)
            if sent_mask.any():
                mixed = num.astype(object)
                mixed.loc[sent_mask] = sentinel
                out[col] = mixed
            else:
                out[col] = num
        else:
            out[col] = pd.to_numeric(s, errors="coerce").fillna(0.0)
    return out


def _add_marker_scores(summary: pd.DataFrame) -> pd.DataFrame:
    """
    Add marker-level burden and fragmentation scores to summary.

    - burdenScore: mean of z-scored(log1p(feature)) across:
      IntDenTotal, VolumeTotal, SA/SurfaceTotal, and %AreaMean.
    - fragmentationScore: z-scored(log1p(Count / VolumeTotal)).
    """
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        return summary

    out = summary.copy()
    col_set = set(out.columns)
    marker_names = set()

    # Detect marker roots from relevant summary metric columns.
    patterns = [
        re.compile(r"^(?P<marker>.+)_IntDenTotal$"),
        re.compile(r"^(?P<marker>.+)_VolumeTotal$"),
        re.compile(r"^(?P<marker>.+)_(?:SA|Surface)Total$"),
        re.compile(r"^(?P<marker>.+)_Count$"),
        re.compile(r"^(?P<marker>.+)_%AreaMean$"),
    ]
    for col in out.columns:
        col_s = str(col)
        for rx in patterns:
            m = rx.match(col_s)
            if not m:
                continue
            marker = m.group("marker")
            if marker.endswith("_ROI"):
                marker = marker[:-4]
            marker_names.add(marker)
            break

    for marker in sorted(marker_names):
        intden_col = f"{marker}_IntDenTotal"
        volume_col = f"{marker}_VolumeTotal"
        surface_col = (
            f"{marker}_SATotal" if f"{marker}_SATotal" in col_set
            else f"{marker}_SurfaceTotal" if f"{marker}_SurfaceTotal" in col_set
            else None
        )
        area_col = (
            f"{marker}_ROI_%AreaMean" if f"{marker}_ROI_%AreaMean" in col_set
            else f"{marker}_%AreaMean" if f"{marker}_%AreaMean" in col_set
            else None
        )
        count_col = f"{marker}_Count"

        burden_sources = [c for c in [intden_col, volume_col, surface_col, area_col] if c in col_set]
        if len(burden_sources) > 0:
            burden_parts = []
            for col in burden_sources:
                raw = _to_numeric_series_excluding_sentinel(out[col])
                burden_parts.append(_zscore_series(_log1p_nonnegative(raw)))
            burden_df = pd.concat(burden_parts, axis=1)
            burden_score = burden_df.mean(axis=1, skipna=True)
            sentinel_mask = _all_sources_are_sentinel(out, burden_sources)
            if sentinel_mask.any():
                burden_score = burden_score.astype(object)
                burden_score.loc[sentinel_mask] = NOT_INCLUDED_SENTINEL
            out[f"{marker}_burdenScore"] = burden_score

        if count_col in col_set and volume_col in col_set:
            count_s = _to_numeric_series_excluding_sentinel(out[count_col])
            volume_s = _to_numeric_series_excluding_sentinel(out[volume_col])
            denom = volume_s.where(volume_s > 0, np.nan)
            frag_ratio = count_s / denom
            frag_score = _zscore_series(_log1p_nonnegative(frag_ratio))
            sentinel_mask = _all_sources_are_sentinel(out, [count_col, volume_col])
            if sentinel_mask.any():
                frag_score = frag_score.astype(object)
                frag_score.loc[sentinel_mask] = NOT_INCLUDED_SENTINEL
            out[f"{marker}_fragmentationScore"] = frag_score

    return out


def _get_stain_name_and_df(file_path):
    """Read a CSV and return (stain_name, DataFrame)."""
    stain_name = os.path.splitext(os.path.basename(file_path))[0]
    return stain_name, pd.read_csv(file_path)


class Experiment:
    """
    A single imaging experiment — imports data from an ImageJ pipeline
    output folder, processes markers, and creates summary statistics.
    """

    def __init__(self, name, filePath, threshold=None):
        self.name = name
        self.filePath = check_directory(filePath) or filePath
        self.data = {}
        self.markers = set()
        self.threshold = threshold or Config.THRESHOLD

    # ── Import ─────────────────────────────────────────────────────────

    def importCSVs(self, progress=True):
        """Import all CSV/ZIP files from the experiment folder structure."""
        labels_path = os.path.join(self.filePath, "Condition Labels.csv")
        if os.path.exists(labels_path):
            self.condition_labels = pd.read_csv(labels_path)

        threshold = self.threshold
        tasks = []
        for subfolder_name in sorted(os.listdir(self.filePath)):
            subfolder_path = os.path.join(self.filePath, subfolder_name)
            if not os.path.isdir(subfolder_path):
                continue
            if subfolder_name not in ATTRIBUTE_DICT:
                continue
            class_type = ATTRIBUTE_DICT[subfolder_name]
            for filename in sorted(os.listdir(subfolder_path)):
                file_path = os.path.join(subfolder_path, filename)
                if filename.endswith('.csv') or filename.endswith('.zip'):
                    tasks.append((subfolder_name, class_type, filename, file_path))

        tracker = ProgressTracker(
            f"{self.name} importCSVs",
            total=len(tasks),
            unit="file",
            enabled=progress and len(tasks) > 0,
        )
        csv_count = 0
        zip_count = 0
        category_counts = defaultdict(int)

        for subfolder_name, class_type, filename, file_path in tasks:
            tracker.start_item(filename, detail=subfolder_name)

            if filename.endswith('.csv'):
                stain_name, stain_df = _get_stain_name_and_df(file_path)
                self.markers.add(stain_name)
                csv_count += 1
                category_counts[subfolder_name] += 1

                if class_type == Antibody:
                    key = stain_name + "_ROI"
                else:
                    key = stain_name

                if class_type == Attribute:
                    self.data[key] = Attribute(key, stain_df, self)
                else:
                    args = [key, stain_df, self, stainColors[stain_name]]
                    if class_type == objectMarker:
                        args.append(threshold)
                    self.data[key] = class_type(*args)

            elif filename.endswith('.zip'):
                zip_count += 1
                category_counts[subfolder_name] += 1
                cropped_rois = _read_roi_zip_with_bounds(file_path)
                full_rois = _read_full_roi_zip_with_bounds(file_path)
                if cropped_rois is None or full_rois is None:
                    roi_data = read_roi_zip(file_path)
                    if cropped_rois is None:
                        cropped_rois = _build_roi_records_from_map(roi_data, include_cropped=True)
                    if full_rois is None:
                        full_rois = _build_roi_records_from_map(roi_data, include_cropped=False)
                self.data['ROIs'] = Attribute(
                    "ROIs", pd.DataFrame.from_dict(cropped_rois, orient='index'), self
                )
                if full_rois is not None:
                    self.data['ROIs To Draw'] = Attribute(
                        "ROIs To Draw", pd.DataFrame.from_dict(full_rois, orient='index'), self
                    )
            tracker.finish_item(filename)

        summary_parts = []
        if csv_count > 0:
            summary_parts.append(f"{csv_count} tables")
        if len(self.markers) > 0:
            summary_parts.append(f"{len(self.markers)} markers")
        if zip_count > 0:
            summary_parts.append(f"{zip_count} ROI zips")
        if len(category_counts) > 0:
            summary_parts.append(", ".join([f"{k}: {v}" for k, v in sorted(category_counts.items())]))
        self._last_csv_import_summary = " | ".join(summary_parts) if len(summary_parts) > 0 else "No CSV/ZIP files found"
        tracker.close(self._last_csv_import_summary)
        return self.data

    # ── Processing pipeline ────────────────────────────────────────────

    def processData(self, import_images=True, progress=True):
        """Run the full processing pipeline."""
        tracker = ProgressTracker(
            f"{self.name} processData",
            total=7,
            unit="step",
            enabled=progress,
        )

        tracker.start_item("Import CSVs")
        self.importCSVs(progress=progress)
        tracker.finish_item("Import CSVs", detail=getattr(self, "_last_csv_import_summary", None))

        tracker.start_item("Closest Distances")
        self.addClosestDistances(progress=progress)
        tracker.finish_item("Closest Distances", detail=getattr(self, "_last_closest_summary", None))

        tracker.start_item("Assign SCNs")
        self.assign_scn_number()
        tracker.finish_item("Assign SCNs", detail=getattr(self, "_last_scn_summary", None))

        tracker.start_item("Ventricle Distances")
        if 'ROIs' in self.data:
            self.addVentricleDistances(progress=progress)
            vent_detail = getattr(self, "_last_ventricle_summary", None)
        else:
            vent_detail = "Skipped: no ROI ventricle data"
        tracker.finish_item("Ventricle Distances", detail=vent_detail)

        tracker.start_item("Create Summary")
        self.createSummary(progress=progress)
        tracker.finish_item("Create Summary", detail=getattr(self, "_last_summary_summary", None))

        tracker.start_item("Create Save Paths")
        self.createSavePaths()
        self._last_save_path_summary = "Results folders ready"
        tracker.finish_item("Create Save Paths", detail=self._last_save_path_summary)

        tracker.start_item("Import Images" if import_images else "Skip Images")
        if import_images:
            self.importImages(progress=progress)
            image_detail = getattr(self, "_last_image_import_summary", None)
        else:
            self.images = None
            self.imagesDict = {}
            image_detail = "Skipped image import"
        tracker.finish_item("Import Images" if import_images else "Skip Images", detail=image_detail)

        animals = int(self.summary.shape[0]) if isinstance(getattr(self, "summary", None), pd.DataFrame) else 0
        tables = len(getattr(self, "data", {}))
        self._last_process_summary = f"{tables} data tables | {animals} animals"
        tracker.close(self._last_process_summary + f" | Total: {format_elapsed(time.perf_counter() - tracker.run_start)}")
        return self.data

    # ── Summary creation ───────────────────────────────────────────────

    def createSummary(self, progress=True):
        summary_dfs = []
        summed, meaned = [], []
        to_drop = ['SCN', 'AnimalName', 'Condition', 'Label', 'ImageROI', 'ROINameRaw']
        stains = list(self.data.values())
        tracker = ProgressTracker(
            f"{self.name} createSummary",
            total=len(stains),
            unit="table",
            enabled=progress and len(stains) > 0,
        )

        for stain in stains:
            tracker.start_item(getattr(stain, "name", type(stain).__name__))
            stain_df = stain.df.copy()
            existing_combo_indicator_cols = _combo_indicator_columns(stain_df, stain.name)
            if len(existing_combo_indicator_cols) > 0:
                stain_df = stain_df.drop(columns=existing_combo_indicator_cols, errors='ignore')
            metric_cols = [c for c in stain_df.columns if c not in to_drop]
            stain_df = _replace_not_included_with_nan(stain_df, columns=metric_cols)
            animal_index = stain_df.groupby('AnimalName').size().index

            mean_candidate_cols = get_columns(stain_df, regex_string='^(?!.*Count).*', exclude=to_drop)
            if len(mean_candidate_cols) > 0:
                mean_source = stain_df[mean_candidate_cols].copy()
                mean_numeric = mean_source.apply(pd.to_numeric, errors='coerce')
            else:
                mean_source = pd.DataFrame(index=stain_df.index)
                mean_numeric = mean_source

            mean_cols = [c for c in mean_numeric.columns if mean_numeric[c].notna().any()]
            other_cols = [c for c in mean_candidate_cols if c not in mean_cols]

            if len(mean_cols) > 0:
                grouped_numeric = pd.concat(
                    [stain_df[['AnimalName']], mean_numeric[mean_cols]],
                    axis=1
                ).groupby('AnimalName')[mean_cols].mean()
                mean_df = grouped_numeric.add_suffix('Mean')
                contains_mean_cols = [c for c in mean_df.columns if '_Contains_' in str(c)]
                if len(contains_mean_cols) > 0:
                    mean_df[contains_mean_cols] = mean_df[contains_mean_cols] * 100.0
            else:
                mean_df = pd.DataFrame(index=animal_index.copy())

            if len(other_cols) > 0:
                other_df = stain_df.groupby('AnimalName')[other_cols].first()
            else:
                other_df = pd.DataFrame(index=animal_index.copy())

            if not mean_df.empty:
                meaned.append(mean_cols)

            count_cols = get_columns(stain_df, regex_string='Count')
            if len(count_cols) > 0:
                count_numeric = stain_df[count_cols].apply(pd.to_numeric, errors='coerce')
                count_numeric = count_numeric.where((count_numeric <= 1) | count_numeric.isna(), 1)
                count_numeric['AnimalName'] = stain_df['AnimalName']
                # Keep historical behavior: all-NaN groups collapse to 0, not NaN.
                count_df = count_numeric.groupby('AnimalName')[count_cols].sum()
                count_df = add_coloc_percentages(count_df)
            else:
                count_df = pd.DataFrame(index=animal_index.copy())
            if not count_df.empty:
                meaned.append(count_cols)

            combo_indicator_df, combo_count_df, combo_intden_df, combo_mean_intden_df = _build_coloc_combo_summaries(
                stain_df,
                stain.name,
            )
            if len(existing_combo_indicator_cols) > 0:
                stain.df = stain.df.drop(columns=existing_combo_indicator_cols, errors='ignore')
            if not combo_indicator_df.empty:
                for combo_col in combo_indicator_df.columns:
                    stain.df[combo_col] = combo_indicator_df[combo_col].astype(np.int8)

            sum_cols = get_columns(stain_df, regex_string='Volume|IntDen|Surface',
                                   exclude=['Mean', 'ROI', 'Ratio'])
            if len(sum_cols) > 0:
                sum_numeric = stain_df[sum_cols].apply(pd.to_numeric, errors='coerce')
                sum_numeric['AnimalName'] = stain_df['AnimalName']
                # Keep historical behavior: all-NaN groups collapse to 0, not NaN.
                sum_df = sum_numeric.groupby('AnimalName')[sum_cols].sum().add_suffix('Total')
            else:
                sum_df = pd.DataFrame(index=animal_index.copy())
            if not sum_df.empty:
                summed.append(sum_df.columns.tolist())

            for block in [mean_df, count_df, combo_count_df, combo_mean_intden_df, sum_df, combo_intden_df, other_df]:
                summary_dfs.append(_ensure_animalname_column(block))
            tracker.finish_item(getattr(stain, "name", type(stain).__name__))

        self.summary = reduce(
            lambda l, r: pd.merge(l, r, left_on='AnimalName', right_on='AnimalName', how='outer'),
            summary_dfs
        )
        if "AnimalName" in self.summary.columns:
            self.summary["Condition"] = _condition_from_animal_name(self.summary["AnimalName"])
        else:
            self.summary["Condition"] = _condition_from_animal_name(self.summary.index)

        try:
            sections = (self.data['ROI Properties'].df
                        .groupby('AnimalName')['SCN'].nunique()
                        .reset_index(name='numSections'))
            self.summary = self.summary.merge(sections, on='AnimalName', how='left')
        except KeyError:
            self.summary['numSections'] = 1

        summed_cols = get_columns(self.summary, regex_string="Count|IntDen|Volume|Surface",
                                   exclude=["Mean", "%"])
        self.summary[summed_cols] = self.summary[summed_cols].div(
            self.summary['numSections'], axis=0
        )
        self.summary = adjust_for_volumemm(self.summary, summed_cols, 'AreaMean')
        self.summary = _add_marker_scores(self.summary)

        # Mark only behavior-only animals (no IF-source rows at all) as not included
        # for IF-derived columns. Keep analytical NaNs (e.g. undefined coloc metrics)
        # as NaN for animals that are present in IF sources.
        if_animals = set()
        if_columns = set()
        for stain in self.data.values():
            if not isinstance(stain, (objectMarker, cellMarker, Antibody)):
                continue
            stain_df = stain.df
            if "AnimalName" in stain_df.columns:
                if_animals.update(stain_df["AnimalName"].dropna().astype(str).tolist())
            marker_prefix = f"{stain.name.split('_ROI')[0]}_"
            for col in self.summary.columns:
                if str(col).startswith(marker_prefix):
                    if_columns.add(col)

        if len(if_columns) > 0:
            if "AnimalName" in self.summary.columns:
                animal_series = self.summary["AnimalName"].astype(str)
            else:
                animal_series = pd.Series(self.summary.index.astype(str), index=self.summary.index)
            no_if_mask = ~animal_series.isin(if_animals)
            if no_if_mask.any():
                cols = list(if_columns)
                block = _replace_not_included_with_nan(self.summary.loc[no_if_mask, cols], columns=cols)
                self.summary.loc[no_if_mask, cols] = block.where(
                    ~block.isna(),
                    NOT_INCLUDED_SENTINEL,
                )
        self.summary = _fill_intden_totals_with_zero(self.summary)
        self._last_summary_summary = f"{self.summary.shape[0]} animals x {self.summary.shape[1]} columns"
        tracker.close(self._last_summary_summary)
        return self.summary

    # ── Distance computations ──────────────────────────────────────────

    def addClosestDistances(self, progress=True):
        markers = [m for m in self.data.values()
                   if isinstance(m, (objectMarker, cellMarker))]
        pairs = [(m1, m2) for i, m1 in enumerate(markers) for j, m2 in enumerate(markers) if i != j]
        tracker = ProgressTracker(
            f"{self.name} closestDistances",
            total=len(pairs),
            unit="pair",
            enabled=progress and len(pairs) > 0,
        )
        for m1, m2 in pairs:
            label = f"{m1.name} -> {m2.name}"
            tracker.start_item(label)
            m1.find_closest_distances_between_markers(m2)
            tracker.finish_item(label)
        self._last_closest_summary = f"{len(markers)} markers | {len(pairs)} pairwise distance calculations"
        tracker.close(self._last_closest_summary)

    def addVentricleDistances(self, progress=True):
        rois = self.data['ROIs'].df
        markers = [m for m in self.data.values() if isinstance(m, (objectMarker, cellMarker))]
        tracker = ProgressTracker(
            f"{self.name} ventricleDistances",
            total=len(markers),
            unit="marker",
            enabled=progress and len(markers) > 0,
        )
        for marker in self.data.values():
            if isinstance(marker, (objectMarker, cellMarker)):
                tracker.start_item(marker.name)
                marker.find_distance_to_ventricle(rois)
                tracker.finish_item(marker.name)
        self._last_ventricle_summary = f"{len(markers)} markers updated with ventricle distances"
        tracker.close(self._last_ventricle_summary)

    # ── Condition assignment ───────────────────────────────────────────

    def set_condition_list(self, condition_list):
        self.condition_list = condition_list
        self.conditions = condition_list.conditions
        self.factor = condition_list.factor
        self.factorDict = condition_list.factorDict
        for f in self.factor:
            names = '|'.join([c.name for c in self.factorDict[f]])
            self.summary['Condition'] = [
                ''.join(filter(str.isalpha, n))
                for n in self.summary.reset_index()['AnimalName'].tolist()
            ]
            self.summary[f] = self.summary['Condition'].str.extract(f'({names})', expand=False)
            for key in self.data:
                df = self.data[key].df
                if 'Condition' in df.columns:
                    df[f] = df['Condition'].str.extract(f'({names})', expand=False)
        if isinstance(getattr(self, "images", None), pd.DataFrame) and not self.images.empty:
            self.images = _attach_image_metadata(self, self.images)
        return self.condition_list

    # ── SCN assignment ─────────────────────────────────────────────────

    def assign_scn_number(self):
        roi_dfs = [self.data[k].df.copy() for k in self.data if 'ROI Properties' in k]
        if len(roi_dfs) == 0:
            self.master_scn = pd.DataFrame(columns=["AnimalName", "SCN", "ImageROI"])
            self._last_scn_summary = "No ROI Properties tables found"
            return self.master_scn

        for roi_df in roi_dfs:
            roi_df["SCN"] = (
                roi_df["AnimalName"]
                + roi_df.groupby("AnimalName")["SCN"]
                    .transform(lambda s: (pd.factorize(s, sort=True)[0] + 1).astype(str))
            )

        failures = []
        for data in self.data.values():
            data.df.reset_index(inplace=True)
            try:
                data.df["SCN"] = (
                    data.df["AnimalName"]
                    + data.df.groupby("AnimalName")["SCN"]
                        .transform(lambda s: (pd.factorize(s, sort=True)[0] + 1).astype(str))
                )
            except KeyError:
                failures.append(data.name)

        roi_name_map = pd.DataFrame()
        rois_obj = self.data.get("ROIs", None)
        if rois_obj is not None and hasattr(rois_obj, "df") and isinstance(rois_obj.df, pd.DataFrame):
            rois_df = rois_obj.df.copy()
            if {"AnimalName", "SCN"}.issubset(rois_df.columns):
                roi_name_map = _finalize_roi_name_labels(rois_df)

        if not roi_name_map.empty:
            self.master_scn = (
                roi_name_map[["AnimalName", "SCN", "ImageROI"]]
                .drop_duplicates(subset=["AnimalName", "SCN"], keep="first")
                .drop_duplicates(subset=["AnimalName", "SCN"], keep="first")
                .reset_index(drop=True)
            )
            for data in self.data.values():
                if isinstance(getattr(data, "df", None), pd.DataFrame):
                    data.df = _apply_roi_name_map(data.df.copy(), roi_name_map)
        else:
            self.master_scn = (
                pd.concat(roi_dfs, ignore_index=True)[["AnimalName", "SCN"]]
                .drop_duplicates()
                .sort_values(["AnimalName", "SCN"])
                .reset_index(drop=True)
            )
            self.master_scn["ImageROI"] = self.master_scn["SCN"]

        source_order = _source_panel_order_rows(self)
        if not source_order.empty:
            scn_order = source_order[["AnimalName", "SCN", "__source_order__"]].drop_duplicates(
                subset=["AnimalName", "SCN"],
                keep="first",
            )
            self.master_scn = self.master_scn.merge(
                scn_order,
                on=["AnimalName", "SCN"],
                how="left",
            )
            self.master_scn["__source_missing__"] = self.master_scn["__source_order__"].isna().astype(int)
            self.master_scn = (
                self.master_scn
                .sort_values(
                    ["AnimalName", "__source_missing__", "__source_order__", "ImageROI", "SCN"],
                    kind="stable",
                )
                .drop(columns=["__source_order__", "__source_missing__"], errors="ignore")
                .reset_index(drop=True)
            )
        else:
            self.master_scn = (
                self.master_scn
                .sort_values(["AnimalName", "ImageROI", "SCN"], kind="stable")
                .reset_index(drop=True)
            )

        aligned_roi_map = _align_image_roi_to_master_order(self.master_scn)
        if not aligned_roi_map.empty:
            self.master_scn = (
                self.master_scn
                .drop(columns=["ImageROI"], errors="ignore")
                .merge(aligned_roi_map, on=["AnimalName", "SCN"], how="left")
                .reset_index(drop=True)
            )
            for data in self.data.values():
                if isinstance(getattr(data, "df", None), pd.DataFrame):
                    data.df = _apply_roi_name_map(data.df.copy(), aligned_roi_map)

        summary = f"{self.master_scn['AnimalName'].nunique()} animals | {len(self.master_scn)} SCNs"
        if len(failures) > 0:
            summary += f" | skipped: {_summarize_name_list(failures)}"
        self._last_scn_summary = summary
        return self.master_scn

    # ── Path management ────────────────────────────────────────────────

    def createSavePaths(self):
        results = os.path.join(os.path.dirname(self.filePath), "Results")
        self.fig_path = os.path.join(results, "Python Figures")
        self.image_fig_path = os.path.join(self.fig_path, "Images")
        self.representative_path = os.path.join(results, "Representative Images")
        self.legend_path = os.path.join(results, "Legends")
        self.data_path = os.path.join(results, "Data and Stats")
        self.csv_path = os.path.join(results, "Separate CSVs")
        self.column_path = os.path.join(self.csv_path, "Columns")
        self.attribute_path = os.path.join(self.csv_path, "Attributes")

        paths = [results, self.fig_path, self.image_fig_path,
                 self.representative_path, self.legend_path, self.data_path,
                 self.csv_path, self.column_path, self.attribute_path]
        # Per-marker folders with analysis-type subfolders
        analysis_types = ['Bars', 'Histograms', 'Ridgelines', 'ECDFs', 'PieCharts']
        for marker in self.markers:
            marker_dir = os.path.join(self.fig_path, marker)
            paths.append(marker_dir)
            for atype in analysis_types:
                paths.append(os.path.join(marker_dir, atype))
        # Cross-marker analysis-type folders
        for atype in ['Matrices', 'Rectangular', 'Locations', 'Regressions',
                      'Modelling', 'Volcano', 'UpSet', 'Sankey']:
            paths.append(os.path.join(self.fig_path, atype))
        for p in paths:
            os.makedirs(p, exist_ok=True)

    # ── Image import ───────────────────────────────────────────────────

    def importImages(self, progress=True):
        image_folder = os.path.join(os.path.dirname(self.filePath), "Images")
        self.image_root = image_folder
        if not os.path.exists(image_folder):
            self.images = _empty_image_table()
            self.imagesDict = {}
            self._last_image_import_summary = "No Images folder found"
            return self.images

        marker_names = _image_marker_names(self)
        records = []
        image_tasks = []
        for animal_folder in sorted(Path(image_folder).iterdir()):
            if not animal_folder.is_dir():
                continue
            animal_name = animal_folder.name
            for image_path in sorted(animal_folder.rglob("*")):
                if (not image_path.is_file()) or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                image_tasks.append((animal_name, image_path))

        tracker = ProgressTracker(
            f"{self.name} importImages",
            total=len(image_tasks),
            unit="image",
            enabled=progress and len(image_tasks) > 0,
        )
        for animal_name, image_path in image_tasks:
            tracker.start_item(image_path.name, detail=animal_name)
            marker_name, roi_name = _parse_image_name(image_path.stem, marker_names)
            records.append({
                "AnimalName": animal_name,
                "Marker": marker_name,
                "ROI": roi_name,
                "ImageName": image_path.stem,
                "ImagePath": str(image_path),
                "Extension": image_path.suffix.lower(),
            })
            tracker.finish_item(image_path.name)

        if len(records) == 0:
            self.images = _empty_image_table()
        else:
            self.images = _sort_image_table(
                _attach_image_metadata(
                    self,
                    pd.DataFrame.from_records(records)
                ),
                source=self,
            )
        self.imagesDict = _build_images_dict(self.images)
        markers = self.images["Marker"].dropna().astype(str).unique().tolist() if not self.images.empty else []
        animals = self.images["AnimalName"].dropna().astype(str).nunique() if not self.images.empty else 0
        self._last_image_import_summary = f"{len(self.images)} images | {animals} animals | {len(markers)} markers"
        tracker.close(self._last_image_import_summary)
        return self.images

    def getImageTable(self, include_summary=True):
        return _get_image_table(self, include_summary=include_summary)

    # ── CSV export ─────────────────────────────────────────────────────

    def save_csvs(self):
        self.save_column_csvs()
        self.save_attribute_csvs()

    def save_column_csvs(self):
        df = self.summary.copy()
        df.to_csv(os.path.join(self.csv_path, 'Summary.csv'), index=False)
        cols = [c for c in df.columns if c not in ['Condition', 'AnimalName']]
        for col in cols:
            col_data = {}
            for cond in self.condition_list:
                col_data[cond.name] = df[df['Condition'] == cond.name][col]
            col_df = pd.DataFrame(col_data)
            cleaned = pd.DataFrame({
                c: col_df[c].dropna().reset_index(drop=True) for c in col_df.columns
            })
            cleaned.to_csv(os.path.join(self.column_path, f'{col}.csv'), index=False)

    def save_attribute_csvs(self):
        for attr_name, attr in self.data.items():
            attr_type = type(attr).__name__
            attr.df.to_csv(os.path.join(self.attribute_path, f'{attr_name}_{attr_type}.csv'))
            print(f"{attr_name} data saved to CSV.")

    # ── Lookup helpers ─────────────────────────────────────────────────

    def getSCNDict(self):
        try:
            df = self.master_scn
            return {
                cond: {
                    animal: df[df['AnimalName'] == animal]['SCN'].unique().tolist()
                    for animal in self.summary[self.summary['Condition'] == cond]['AnimalName'].unique()
                }
                for cond in [c.name for c in self.condition_list]
            }
        except (KeyError, AttributeError):
            return {
                cond: self.summary[self.summary['Condition'] == cond]['AnimalName'].unique().tolist()
                for cond in [c.name for c in self.condition_list]
            }

    def info(self):
        print(f"Experiment: {self.name}")
        print(f"Path: {self.filePath}")
        print(f"Data keys: {list(self.data.keys())}")
        if hasattr(self, 'summary'):
            print(f"Conditions: {self.summary['Condition'].unique()}")

    # ── Serialization ──────────────────────────────────────────────────

    def __getstate__(self):
        state = self.__dict__.copy()
        image_df = state.get('images', None)
        if isinstance(image_df, pd.DataFrame) and 'ImageArray' in image_df.columns:
            state['images'] = image_df.drop(columns=['ImageArray']).copy()
        state.pop('imagesDict', None)
        state.pop('animal_dict', None)
        state.pop('var_name', None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        if isinstance(getattr(self, "images", None), pd.DataFrame) and 'ImageArray' in self.images.columns:
            self.images = self.images.drop(columns=['ImageArray']).copy()
        self.image_root = getattr(
            self,
            "image_root",
            os.path.join(os.path.dirname(self.filePath), "Images") if isinstance(getattr(self, "filePath", None), str) else None,
        )
        self.imagesDict = _build_images_dict(getattr(self, "images", None))
        for obj in self.data.values():
            if hasattr(obj, 'experiment'):
                obj.experiment = self

    def __repr__(self):
        return f"Experiment('{self.name}', markers={list(self.markers)})"


class MiniExperiment(Experiment):
    """Lightweight experiment — flat CSV folder, no marker subfolders."""

    def __init__(self, name, filePath):
        super().__init__(name, filePath)

    def importCSVs(self, progress=True):
        self.createSavePaths()

        labels_path = os.path.join(self.filePath, "Condition Labels.csv")
        if os.path.exists(labels_path):
            self.condition_labels = pd.read_csv(labels_path)

        files = [f for f in sorted(os.listdir(self.filePath)) if f.endswith('.csv') and f != 'Condition Labels.csv']
        tracker = ProgressTracker(
            f"{self.name} importCSVs",
            total=len(files),
            unit="file",
            enabled=progress and len(files) > 0,
        )

        for filename in files:
            tracker.start_item(filename)
            if filename.endswith('.csv') and filename != 'Condition Labels.csv':
                name = os.path.splitext(filename)[0]
                path = os.path.join(self.filePath, filename)
                self.data[name] = Attribute(name, pd.read_csv(path), self)
            tracker.finish_item(filename)
        self._last_csv_import_summary = f"{len(files)} tables"
        tracker.close(self._last_csv_import_summary)
        return self.data

    def createSummary(self, progress=True):
        summary_dfs = []
        for data in self.data.values():
            df = data.df
            numeric_cols, other_cols = get_nonobject_columns(df)
            other_cols = [c for c in other_cols if c not in {'AnimalName', 'ImageROI', 'ROINameRaw'}]
            summary_dfs.append(df.groupby('AnimalName')[numeric_cols].mean())
            summary_dfs.append(df.groupby('AnimalName')[other_cols].first())

        self.summary = reduce(
            lambda l, r: pd.merge(l, r, left_on='AnimalName', right_on='AnimalName', how='outer'),
            summary_dfs
        )
        if "AnimalName" in self.summary.columns:
            self.summary["Condition"] = _condition_from_animal_name(self.summary["AnimalName"])
        else:
            self.summary["Condition"] = _condition_from_animal_name(self.summary.index)
        self.summary = _add_marker_scores(self.summary)
        self.summary = _fill_intden_totals_with_zero(self.summary)
        self._last_summary_summary = f"{self.summary.shape[0]} animals x {self.summary.shape[1]} columns"
        return self.summary

    def processData(self, import_images=True, progress=True):
        tracker = ProgressTracker(
            f"{self.name} processData",
            total=4,
            unit="step",
            enabled=progress,
        )
        tracker.start_item("Import CSVs")
        self.importCSVs(progress=progress)
        tracker.finish_item("Import CSVs", detail=getattr(self, "_last_csv_import_summary", None))
        tracker.start_item("Create Summary")
        self.createSummary(progress=progress)
        tracker.finish_item("Create Summary", detail=getattr(self, "_last_summary_summary", None))
        tracker.start_item("Create Save Paths")
        self.createSavePaths()
        tracker.finish_item("Create Save Paths", detail="Results folders ready")
        tracker.start_item("Import Images" if import_images else "Skip Images")
        if import_images:
            self.importImages(progress=progress)
            image_detail = getattr(self, "_last_image_import_summary", None)
        else:
            self.images = None
            self.imagesDict = {}
            image_detail = "Skipped image import"
        tracker.finish_item("Import Images" if import_images else "Skip Images", detail=image_detail)
        self._last_process_summary = f"{len(self.data)} data tables | {self.summary.shape[0]} animals"
        tracker.close(self._last_process_summary)
