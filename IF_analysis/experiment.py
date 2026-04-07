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

from IF_analysis._logging import logger as _log
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
    extract_region_base, normalize_hemisphere,
    ProgressTracker, format_elapsed,
)
from IF_analysis.export import format_summary_for_display

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
    seen_regions = set()
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

        region_values = (
            df["Region"].fillna("").astype(str)
            if "Region" in df.columns
            else pd.Series("", index=df.index, dtype="object")
        )

        frame = pd.DataFrame({
            "Experiment": exp_values,
            "AnimalName": df["AnimalName"].fillna("").astype(str),
            "Region": region_values,
            "ImageROI": df["ImageROI"].fillna("").astype(str),
        }, index=df.index)

        for row in frame.itertuples(index=False):
            exp_name = str(getattr(row, "Experiment", "")).strip()
            animal_name = str(getattr(row, "AnimalName", "")).strip()
            region_name = str(getattr(row, "Region", "")).strip()
            image_roi = normalize_image_roi_name(getattr(row, "ImageROI", ""))
            if animal_name == "" or region_name == "" or image_roi == "":
                continue

            exp_key = exp_name.casefold()
            animal_key = normalize_animal_name(animal_name).casefold()
            region_key = region_name.casefold()
            dedup_key = (exp_key, animal_key, region_key)
            if dedup_key in seen_regions:
                continue
            seen_regions.add(dedup_key)

            group_key = (exp_key, animal_key)
            order_idx = group_counts[group_key]
            group_counts[group_key] = order_idx + 1
            records.append({
                "Experiment": exp_name,
                "AnimalName": animal_name,
                "Region": region_name,
                "ImageROI": image_roi,
                "__source_order__": int(order_idx),
            })

    if len(records) == 0:
        return pd.DataFrame(columns=["Experiment", "AnimalName", "Region", "ImageROI", "__source_order__"])
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
            v = str(value).strip().upper()
            # Match hemisphere-prefixed region: LHSCN1, RHOC2, etc.
            match = re.fullmatch(r"(?:LH|RH)?(\w+?)(\d+)", v)
            if match is None:
                return float("inf")
            return int(match.group(2))

        def _roi_side(value):
            v = str(value).strip().upper()
            if v.startswith("LH"):
                return 0
            if v.startswith("RH"):
                return 1
            return 99

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
        return pd.DataFrame(columns=["AnimalName", "Region", "ImageROI"])

    out = roi_df.copy()

    # If Hemisphere column is populated, construct ImageROI directly
    has_hemisphere = (
        "Hemisphere" in out.columns
        and out["Hemisphere"].fillna("").astype(str).str.strip().ne("").any()
    )

    if has_hemisphere:
        hemisphere = out["Hemisphere"].fillna("").astype(str).str.strip()
        region = out["Region"].fillna("").astype(str).str.strip()
        out["ImageROI"] = hemisphere + region
    else:
        # Old format fallback: assign LH/RH by alternating order per animal
        base = out.get("ROINameRaw", out["Region"]).fillna("").astype(str).str.strip()
        fallback = out["Region"].fillna("").astype(str).str.strip()
        base = base.where(base != "", fallback)
        out["ImageROI"] = [normalize_image_roi_name(value) for value in base]

        # Assign hemisphere by alternating LH/RH within each animal
        for animal, group in out.groupby("AnimalName", sort=False):
            idxs = group.index.tolist()
            for i, idx in enumerate(idxs):
                side = "LH" if i % 2 == 0 else "RH"
                region_val = out.loc[idx, "Region"]
                out.loc[idx, "ImageROI"] = f"{side}{region_val}"

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


def _align_image_roi_to_master_order(master_region: pd.DataFrame) -> pd.DataFrame:
    if (
        not isinstance(master_region, pd.DataFrame)
        or master_region.empty
        or "AnimalName" not in master_region.columns
        or "Region" not in master_region.columns
    ):
        return pd.DataFrame(columns=["AnimalName", "Region", "ImageROI"])

    records = []
    for animal_name, group in master_region.groupby("AnimalName", sort=False, dropna=False):
        ordered = group.reset_index(drop=True)
        for idx, row in ordered.iterrows():
            region_base = extract_region_base(row["Region"])
            panel_index = max(0, int(idx))
            pair_index = (panel_index // 2) + 1
            side = "LH" if (panel_index % 2) == 0 else "RH"
            suffix = str(pair_index) if pair_index > 1 else ""
            records.append({
                "AnimalName": row["AnimalName"],
                "Region": row["Region"],
                "ImageROI": f"{side}{region_base}{suffix}",
            })
    return pd.DataFrame.from_records(records)


def _normalize_region_key_series(values) -> pd.Series:
    """Canonicalize region identifiers for safe joins across mixed dtypes."""
    series = pd.Series(values, copy=False)
    out = series.fillna("").astype(str).str.strip()
    out = out.str.replace(r"\.0+$", "", regex=True)
    numeric_mask = out.str.fullmatch(r"\d+", na=False)
    out.loc[numeric_mask] = "SCN" + out.loc[numeric_mask]
    out = out.str.replace(r"^(SCN)\.0+$", r"\1", regex=True)
    out = out.str.replace(r"^(SCN\d+)\.0+$", r"\1", regex=True)
    return out


def _apply_roi_name_map(df: pd.DataFrame, roi_name_map: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        return df
    if (
        not isinstance(roi_name_map, pd.DataFrame)
        or roi_name_map.empty
        or "AnimalName" not in df.columns
        or "Region" not in df.columns
    ):
        return df

    preserved_image_roi = None
    if "ImageROI" in df.columns:
        preserved_image_roi = df["ImageROI"].copy()

    image_roi_cols = [c for c in df.columns if str(c).startswith("ImageROI")]
    base = df.drop(columns=image_roi_cols, errors="ignore").copy()
    base["__AnimalNameKey__"] = base["AnimalName"].map(normalize_animal_name)
    base["__RegionKey__"] = _normalize_region_key_series(base["Region"])
    roi_map = roi_name_map[["AnimalName", "Region", "ImageROI"]].drop_duplicates(
        subset=["AnimalName", "Region"], keep="first"
    ).copy()
    roi_map["__AnimalNameKey__"] = roi_map["AnimalName"].map(normalize_animal_name)
    roi_map["__RegionKey__"] = _normalize_region_key_series(roi_map["Region"])
    roi_map = roi_map.drop(columns=["AnimalName", "Region"], errors="ignore")
    out = base.merge(
        roi_map,
        on=["__AnimalNameKey__", "__RegionKey__"],
        how="left",
    ).drop(columns=["__AnimalNameKey__", "__RegionKey__"], errors="ignore")
    if "ImageROI" in out.columns:
        roi_name = out["ImageROI"].fillna("").astype(str).str.strip()
        if preserved_image_roi is not None and len(preserved_image_roi) == len(out):
            prev_roi = preserved_image_roi.fillna("").astype(str).str.strip()
            roi_name = roi_name.where(roi_name != "", prev_roi)
        region_vals = out["Region"].fillna("").astype(str).str.strip()
        out["ImageROI"] = roi_name.where(roi_name != "", region_vals)
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


def _fill_missing_behavior_with_sentinel(
    summary: pd.DataFrame,
    behavior_cols,
    behavior_animals=None,
    sentinel=NOT_INCLUDED_SENTINEL,
) -> pd.DataFrame:
    """Fill missing behaviour cells and absent behaviour rows with sentinel text."""
    out = summary.copy()
    cols = [
        col for col in list(behavior_cols or [])
        if col in out.columns and col != "AnimalName"
    ]
    if len(cols) == 0:
        return out

    animals = {
        str(animal)
        for animal in (behavior_animals or [])
        if pd.notna(animal)
    }
    if "AnimalName" in out.columns:
        animal_series = out["AnimalName"].astype(str)
    else:
        animal_series = pd.Series(out.index.astype(str), index=out.index)

    if len(animals) > 0:
        absent_animals = ~animal_series.isin(animals)
    else:
        absent_animals = pd.Series(False, index=out.index, dtype=bool)

    for col in cols:
        series = out[col].astype("object")
        series_str = series.astype("string")
        sentinel_mask = series_str.str.contains(str(sentinel), na=False)
        blank_mask = series_str.fillna("").str.strip().eq("")
        missing_mask = series.isna() | blank_mask | sentinel_mask | absent_animals
        if missing_mask.any():
            series.loc[missing_mask] = sentinel
            out[col] = series

    return out


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


def _any_indicator_columns(df: pd.DataFrame, marker_name: str) -> list[str]:
    """Derived per-object pooled coloc/contains indicator columns."""
    prefix = f"{str(marker_name)}_Any_"
    return [str(col) for col in df.columns if str(col).startswith(prefix)]


def _build_any_indicator_columns(stain_df: pd.DataFrame, marker_name: str) -> pd.DataFrame:
    """Build per-object pooled indicators where Any = ColocCount OR Contains."""
    marker_s = str(marker_name)
    esc = re.escape(marker_s)
    coloc_rx = re.compile(rf"^{esc}_ColocCount(?P<m2>.+)$")
    contains_rx = re.compile(rf"^{esc}_Contains_(?P<m2>.+)$")

    coloc_cols = {}
    contains_cols = {}
    for col in stain_df.columns:
        col_s = str(col)
        m = coloc_rx.match(col_s)
        if m is not None:
            coloc_cols[str(m.group("m2"))] = col_s
            continue
        m = contains_rx.match(col_s)
        if m is not None:
            contains_cols[str(m.group("m2"))] = col_s

    targets = sorted(set(coloc_cols) | set(contains_cols))
    if len(targets) == 0:
        return pd.DataFrame(index=stain_df.index)

    any_df = pd.DataFrame(index=stain_df.index)
    for target in targets:
        pooled = pd.Series(False, index=stain_df.index)
        if target in coloc_cols:
            pooled = pooled | _coerce_binary_indicator(stain_df[coloc_cols[target]])
        if target in contains_cols:
            pooled = pooled | _coerce_binary_indicator(stain_df[contains_cols[target]])
        any_df[f"{marker_s}_Any_{target}"] = pooled.astype(np.int8)
    return any_df


def _build_binary_indicator_count_summaries(
    stain_df: pd.DataFrame,
    marker_name: str,
    *,
    family_name: str,
    detected,
) -> pd.DataFrame:
    """Build per-animal standalone binary-indicator counts and percentages."""
    if "AnimalName" not in stain_df.columns:
        return pd.DataFrame()
    if len(detected) == 0:
        return pd.DataFrame()

    marker_s = str(marker_name)
    detected = sorted(detected, key=lambda t: (str(t[0]), str(t[1])))
    indicator_cols = [c for _, c in detected]
    rename_map = {
        c: f"{marker_s}_{family_name}_{target}_Count"
        for target, c in detected
    }

    base_count_col = f"{marker_s}_Count"
    if base_count_col in stain_df.columns:
        base_count = _to_numeric_series_excluding_sentinel(stain_df[base_count_col]).fillna(0.0)
        base_count = base_count.where(base_count > 0, 0.0)
        base_count = base_count.where(base_count <= 1, 1.0)
    else:
        base_count = pd.Series(1.0, index=stain_df.index, dtype=float)

    valid_mask = base_count > 0
    if not bool(valid_mask.any()):
        return pd.DataFrame()

    work = stain_df.loc[valid_mask, ["AnimalName"] + indicator_cols].copy()
    work_animals = work["AnimalName"].astype(str)
    indicator_numeric = pd.DataFrame(index=work.index)
    for col in indicator_cols:
        indicator_numeric[col] = _coerce_binary_indicator(work[col]).astype(float)

    out_count_df = pd.concat([work[["AnimalName"]], indicator_numeric], axis=1)
    out_count_df = out_count_df.groupby("AnimalName")[indicator_cols].sum().rename(columns=rename_map)

    denom = base_count.loc[valid_mask].groupby(work_animals).sum().replace(0, np.nan)
    out_pct_df = out_count_df.div(denom, axis=0) * 100.0
    out_pct_df = out_pct_df.rename(columns={
        col: f"{str(col)}%"
        for col in out_count_df.columns
    })

    return pd.concat([out_count_df, out_pct_df], axis=1)


def _build_any_count_summaries(stain_df: pd.DataFrame, marker_name: str) -> pd.DataFrame:
    """Build per-animal standalone Any counts and percentages."""
    marker_s = str(marker_name)
    esc = re.escape(marker_s)
    any_rx = re.compile(rf"^{esc}_Any_(?P<m2>.+)$")

    detected = []
    for col in stain_df.columns:
        col_s = str(col)
        m = any_rx.match(col_s)
        if m is not None:
            detected.append((str(m.group("m2")), col_s))

    return _build_binary_indicator_count_summaries(
        stain_df,
        marker_name,
        family_name="Any",
        detected=detected,
    )


def _build_coloc_count_summaries(stain_df: pd.DataFrame, marker_name: str) -> pd.DataFrame:
    """Build per-animal standalone Coloc counts and percentages."""
    marker_s = str(marker_name)
    esc = re.escape(marker_s)
    coloc_rx = re.compile(rf"^{esc}_ColocCount(?P<m2>.+)$")

    detected = []
    for col in stain_df.columns:
        col_s = str(col)
        m = coloc_rx.match(col_s)
        if m is not None:
            detected.append((str(m.group("m2")), col_s))

    return _build_binary_indicator_count_summaries(
        stain_df,
        marker_name,
        family_name="Coloc",
        detected=detected,
    )


def _build_contains_count_summaries(stain_df: pd.DataFrame, marker_name: str) -> pd.DataFrame:
    """Build per-animal standalone Contains counts and percentages."""
    marker_s = str(marker_name)
    esc = re.escape(marker_s)
    contains_rx = re.compile(rf"^{esc}_Contains_(?P<m2>.+)$")

    detected = []
    for col in stain_df.columns:
        col_s = str(col)
        m = contains_rx.match(col_s)
        if m is not None:
            detected.append((str(m.group("m2")), col_s))

    return _build_binary_indicator_count_summaries(
        stain_df,
        marker_name,
        family_name="Contains",
        detected=detected,
    )


def _rename_legacy_coloc_mean_summary_columns(mean_df: pd.DataFrame, marker_name: str) -> pd.DataFrame:
    """Rename raw coloc mean summaries to canonical `<marker>_Coloc_<target>_Mean`."""
    if not isinstance(mean_df, pd.DataFrame) or mean_df.empty:
        return mean_df

    marker_s = str(marker_name)
    esc = re.escape(marker_s)
    canonical_raw_rx = re.compile(rf"^{esc}_Coloc_(?P<m2>.+)Mean$")
    legacy_rx = re.compile(rf"^{esc}_Coloc(?P<m2>[^_].+)Mean$")
    rename_map = {}
    for col in mean_df.columns:
        col_s = str(col)
        m = canonical_raw_rx.match(col_s)
        if m is not None:
            rename_map[col_s] = f"{marker_s}_Coloc_{str(m.group('m2'))}_Mean"
            continue

        m = legacy_rx.match(col_s)
        if m is not None:
            rename_map[col_s] = f"{marker_s}_Coloc_{str(m.group('m2'))}_Mean"

    if len(rename_map) == 0:
        return mean_df
    return mean_df.rename(columns=rename_map)


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


def _combo_indicator_columns(
    df: pd.DataFrame,
    marker_name: str,
    family_name: str = "Combo",
) -> list[str]:
    """Derived per-object combo membership columns stored on marker dataframes."""
    prefix = f"{str(marker_name)}_{str(family_name)}_"
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


def _build_combo_summaries_from_detected(
    stain_df: pd.DataFrame,
    marker_name: str,
    family_name: str,
    detected,
):
    """Build per-object combo indicators and per-animal combo summaries."""
    if "AnimalName" not in stain_df.columns:
        return pd.DataFrame(index=stain_df.index), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if len(detected) == 0:
        return pd.DataFrame(index=stain_df.index), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    marker_s = str(marker_name)
    detected = sorted(detected, key=lambda t: (str(t[0]), int(t[1]), str(t[2]), str(t[3])))
    indicator_cols = [c for _, _, c, _ in detected]
    indicator_tokens = [token for _, _, _, token in detected]

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
    for row in bool_df.itertuples(index=False, name=None):
        parts = []
        for value, token in zip(row, indicator_tokens):
            if not bool(value):
                continue
            # Negative states (e.g., marker-, woMarker) are intentionally
            # omitted from combo names as requested.
            parts.append(str(token))
        signatures.append("_".join(parts) if len(parts) > 0 else "None")
    combo_series = pd.Series(signatures, index=work.index, name="_combo")
    combo_indicator_df = pd.get_dummies(combo_series)
    combo_indicator_df = combo_indicator_df.reindex(
        columns=sorted(combo_indicator_df.columns.tolist()),
        fill_value=0,
    ).astype(np.int8)
    combo_indicator_df = combo_indicator_df.rename(
        columns={sig: f"{marker_s}_{family_name}_{str(sig)}" for sig in combo_indicator_df.columns}
    )
    combo_indicator_df = combo_indicator_df.reindex(stain_df.index, fill_value=0)

    count_input = pd.DataFrame({
        "AnimalName": work_animals,
        "_combo": combo_series,
        "_w": weight,
    })
    combo_count = count_input.groupby(["AnimalName", "_combo"])["_w"].sum().unstack(fill_value=0.0)
    count_cols = {
        c: f"{marker_s}_{family_name}_{str(c)}_Count"
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
            c: f"{marker_s}_{family_name}_{str(c)}_IntDenTotal"
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
            c: f"{marker_s}_{family_name}_{str(c)}_MeanIntDen"
            for c in combo_mean_intden.columns
        })

    return combo_indicator_df, combo_count_df, combo_intden, combo_mean_intden


def _build_coloc_combo_summaries(stain_df: pd.DataFrame, marker_name: str):
    """
    Build detailed per-object combo indicators and per-animal combo summaries.

    This keeps `ColocCount` and `Contains` as separate positive states.
    """
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
                marker2 = str(m.group("m2"))
                token = f"{marker2}+" if kind == "ColocCount" else f"w{marker2}"
                detected.append((marker2, kind_rank[kind], c_s, token))
                break

    return _build_combo_summaries_from_detected(
        stain_df,
        marker_name,
        family_name="Combo",
        detected=detected,
    )


def _build_any_combo_summaries(stain_df: pd.DataFrame, marker_name: str):
    """
    Build pooled per-object combo indicators and per-animal combo summaries.

    This uses derived `Any` columns where Any = ColocCount OR Contains.
    """
    marker_s = str(marker_name)
    esc = re.escape(marker_s)
    any_rx = re.compile(rf"^{esc}_Any_(?P<m2>.+)$")

    detected = []
    for c in stain_df.columns:
        c_s = str(c)
        m = any_rx.match(c_s)
        if m is not None:
            marker2 = str(m.group("m2"))
            detected.append((marker2, 0, c_s, f"{marker2}+"))

    return _build_combo_summaries_from_detected(
        stain_df,
        marker_name,
        family_name="ComboAny",
        detected=detected,
    )


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


def _standardize_csv_columns(df):
    """Standardize CSV format: ensure Region/Hemisphere columns exist.

    New format: has Hemisphere + Region columns.
    Old format: has SCN column — convert to Region, add empty Hemisphere.
    Also drops pre-computed marker-specific columns from new-format CSVs.
    """
    cols = set(df.columns)

    if 'Region' in cols:
        # New format — normalize hemisphere and drop pre-computed columns
        if 'Hemisphere' in cols:
            df['Hemisphere'] = df['Hemisphere'].fillna('').apply(normalize_hemisphere)
        else:
            df['Hemisphere'] = ''
        if 'ROI' not in cols:
            df['ROI'] = 'SCN'
        # Drop pre-computed columns that the pipeline will recompute
        drop_cols = [c for c in df.columns if (
            c.endswith('_um')
            or '_DistToClosest_' in c
            or '_ClosestTo_' in c
            or '_NumColoc_' in c
            or '_Contains_' in c
            or '_NumClosestTo_' in c
        )]
        if drop_cols:
            df = df.drop(columns=drop_cols)
        # Drop legacy SCN column if both exist
        if 'SCN' in cols:
            df = df.drop(columns=['SCN'])
    elif 'SCN' in cols:
        # Old format — convert SCN to Region, default ROI to SCN
        df = df.rename(columns={'SCN': 'Region'})
        df['Region'] = 'SCN' + df['Region'].astype(str)
        df['Hemisphere'] = ''
        df['ROI'] = 'SCN'
    else:
        # Neither column — add empty placeholders
        df['Region'] = ''
        df['Hemisphere'] = ''
        df['ROI'] = 'SCN'

    return df


def _get_stain_name_and_df(file_path):
    """Read a CSV and return (stain_name, DataFrame)."""
    stain_name = os.path.splitext(os.path.basename(file_path))[0]
    df = pd.read_csv(file_path)
    df = _standardize_csv_columns(df)
    return stain_name, df


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

    @property
    def summary(self):
        """Backward-compat: return the SCN summary from summaries dict."""
        if not hasattr(self, 'summaries') or not self.summaries:
            return pd.DataFrame(columns=["AnimalName"])
        return self.summaries.get('SCN', next(iter(self.summaries.values())))

    @summary.setter
    def summary(self, value):
        """Backward-compat setter: store as SCN summary."""
        if not hasattr(self, 'summaries'):
            self.summaries = {}
        if isinstance(value, pd.DataFrame):
            self.summaries['SCN'] = value

    def createSummary(self, progress=True):
        stains = list(self.data.values())
        to_drop = ['Region', 'AnimalName', 'Condition', 'Label', 'ImageROI',
                    'ROINameRaw', 'Hemisphere', 'ROI']

        # Pre-compute combo indicators once (side effect on stain.df)
        for stain in stains:
            stain_df = stain.df.copy()
            existing_any = _any_indicator_columns(stain_df, stain.name)
            existing_combo = _combo_indicator_columns(stain_df, stain.name, family_name="Combo")
            existing_combo_any = _combo_indicator_columns(stain_df, stain.name, family_name="ComboAny")
            existing = list(dict.fromkeys(existing_any + existing_combo + existing_combo_any))
            if len(existing) > 0:
                stain_df = stain_df.drop(columns=existing, errors='ignore')

            any_indicator_df = _build_any_indicator_columns(stain_df, stain.name)
            if not any_indicator_df.empty:
                for any_col in any_indicator_df.columns:
                    stain_df[any_col] = any_indicator_df[any_col].astype(np.int8)

            combo_indicator_df, _, _, _ = _build_coloc_combo_summaries(stain_df, stain.name)
            combo_any_indicator_df, _, _, _ = _build_any_combo_summaries(stain_df, stain.name)
            if len(existing) > 0:
                stain.df = stain.df.drop(columns=existing, errors='ignore')
            if not any_indicator_df.empty:
                for any_col in any_indicator_df.columns:
                    stain.df[any_col] = any_indicator_df[any_col].astype(np.int8)
            if not combo_indicator_df.empty:
                for combo_col in combo_indicator_df.columns:
                    stain.df[combo_col] = combo_indicator_df[combo_col].astype(np.int8)
            if not combo_any_indicator_df.empty:
                for combo_col in combo_any_indicator_df.columns:
                    stain.df[combo_col] = combo_any_indicator_df[combo_col].astype(np.int8)

        # Discover all ROI bases across all stain data
        all_roi_bases = set()
        for stain in stains:
            if 'ROI' in stain.df.columns:
                for v in stain.df['ROI'].dropna().astype(str).unique():
                    all_roi_bases.add(extract_region_base(v))
        if not all_roi_bases:
            all_roi_bases = {'SCN'}

        tracker = ProgressTracker(
            f"{self.name} createSummary",
            total=len(all_roi_bases) * len(stains),
            unit="table",
            enabled=progress and len(stains) > 0,
        )

        self.summaries = {}
        for roi_base in sorted(all_roi_bases):
            summary_dfs = []
            behavior_animals = set()
            behavior_summary_cols = set()

            for stain in stains:
                tracker.start_item(f"{roi_base}/{getattr(stain, 'name', type(stain).__name__)}")
                stain_df = stain.df.copy()
                is_behavior = str(getattr(stain, "name", "")).casefold() in {"behaviour", "behavior"}

                # Filter to this ROI base
                if 'ROI' in stain_df.columns:
                    mask = stain_df['ROI'].fillna('').astype(str).apply(
                        lambda v, rb=roi_base: extract_region_base(v) == rb
                    )
                    stain_df = stain_df[mask]
                if stain_df.empty:
                    tracker.finish_item(f"{roi_base}/{getattr(stain, 'name', type(stain).__name__)}")
                    continue

                existing = (
                    _combo_indicator_columns(stain_df, stain.name, family_name="Combo")
                    + _combo_indicator_columns(stain_df, stain.name, family_name="ComboAny")
                )
                if len(existing) > 0:
                    stain_df = stain_df.drop(columns=existing, errors='ignore')
                metric_cols = [c for c in stain_df.columns if c not in to_drop]
                stain_df = _replace_not_included_with_nan(stain_df, columns=metric_cols)
                animal_index = stain_df.groupby('AnimalName').size().index

                if is_behavior and "AnimalName" in stain_df.columns:
                    behavior_animals.update(stain_df["AnimalName"].dropna().astype(str).tolist())

                mean_candidate_cols = [
                    c for c in metric_cols
                    if 'Count' not in str(c)
                    and '_Any_' not in str(c)
                    and '_Contains_' not in str(c)
                ]
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
                    mean_df = _rename_legacy_coloc_mean_summary_columns(mean_df, stain.name)
                else:
                    mean_df = pd.DataFrame(index=animal_index.copy())

                if len(other_cols) > 0:
                    other_df = stain_df.groupby('AnimalName')[other_cols].first()
                else:
                    other_df = pd.DataFrame(index=animal_index.copy())

                count_cols = [
                    c for c in get_columns(stain_df, regex_string='Count')
                    if not re.match(rf"^{re.escape(str(stain.name))}_ColocCount.+$", str(c))
                    and not re.match(rf"^{re.escape(str(stain.name))}_NonColocCount.+$", str(c))
                ]
                if len(count_cols) > 0:
                    count_numeric = stain_df[count_cols].apply(pd.to_numeric, errors='coerce')
                    count_numeric = count_numeric.where((count_numeric <= 1) | count_numeric.isna(), 1)
                    count_numeric['AnimalName'] = stain_df['AnimalName']
                    count_df = count_numeric.groupby('AnimalName')[count_cols].sum()
                    count_df = add_coloc_percentages(count_df)
                else:
                    count_df = pd.DataFrame(index=animal_index.copy())
                coloc_count_df = _build_coloc_count_summaries(stain_df, stain.name)
                contains_count_df = _build_contains_count_summaries(stain_df, stain.name)
                any_count_df = _build_any_count_summaries(stain_df, stain.name)

                _, combo_count_df, combo_intden_df, combo_mean_intden_df = _build_coloc_combo_summaries(
                    stain_df, stain.name,
                )
                _, combo_any_count_df, combo_any_intden_df, combo_any_mean_intden_df = _build_any_combo_summaries(
                    stain_df, stain.name,
                )

                sum_cols = get_columns(stain_df, regex_string='Volume|IntDen|Surface',
                                       exclude=['Mean', 'ROI', 'Ratio'])
                if len(sum_cols) > 0:
                    sum_numeric = stain_df[sum_cols].apply(pd.to_numeric, errors='coerce')
                    sum_numeric['AnimalName'] = stain_df['AnimalName']
                    sum_df = sum_numeric.groupby('AnimalName')[sum_cols].sum().add_suffix('Total')
                else:
                    sum_df = pd.DataFrame(index=animal_index.copy())

                for block in [mean_df, count_df, coloc_count_df, contains_count_df, any_count_df,
                              combo_count_df, combo_any_count_df,
                              combo_mean_intden_df, combo_any_mean_intden_df,
                              sum_df, combo_intden_df, combo_any_intden_df, other_df]:
                    block = _ensure_animalname_column(block)
                    summary_dfs.append(block)
                    if is_behavior:
                        behavior_summary_cols.update(
                            col for col in block.columns
                            if col != "AnimalName"
                        )
                tracker.finish_item(f"{roi_base}/{getattr(stain, 'name', type(stain).__name__)}")

            if not summary_dfs:
                continue

            roi_summary = reduce(
                lambda l, r: pd.merge(l, r, left_on='AnimalName', right_on='AnimalName', how='outer'),
                summary_dfs
            )
            if "AnimalName" in roi_summary.columns:
                roi_summary["Condition"] = _condition_from_animal_name(roi_summary["AnimalName"])
            else:
                roi_summary["Condition"] = _condition_from_animal_name(roi_summary.index)

            # numSections: count unique Regions per animal within this ROI base
            try:
                roi_props = self.data['ROI Properties'].df
                if 'ROI' in roi_props.columns:
                    roi_mask = roi_props['ROI'].fillna('').astype(str).apply(
                        lambda v, rb=roi_base: extract_region_base(v) == rb
                    )
                    roi_props_filtered = roi_props[roi_mask]
                else:
                    roi_props_filtered = roi_props
                sections = (roi_props_filtered
                            .groupby('AnimalName')['Region'].nunique()
                            .reset_index(name='numSections'))
                roi_summary = roi_summary.merge(sections, on='AnimalName', how='left')
            except KeyError:
                roi_summary['numSections'] = 1

            summed_cols = get_columns(roi_summary, regex_string="Count|IntDen|Volume|Surface",
                                       exclude=["Mean", "%"])
            roi_summary[summed_cols] = roi_summary[summed_cols].div(
                roi_summary['numSections'], axis=0
            )
            raw_count_cols = [c for c in summed_cols if str(c).endswith('_Count')]
            raw_count_df = (
                roi_summary[raw_count_cols].copy()
                if len(raw_count_cols) > 0 else pd.DataFrame(index=roi_summary.index)
            )
            area_mean = None
            if 'ROI_Area' in roi_summary.columns:
                area_mean = pd.to_numeric(roi_summary['ROI_Area'], errors='coerce')
            elif 'AreaMean' in roi_summary.columns:
                area_mean = pd.to_numeric(roi_summary['AreaMean'], errors='coerce')
            elif 'Area(um^2)Mean' in roi_summary.columns:
                area_mean = pd.to_numeric(roi_summary['Area(um^2)Mean'], errors='coerce')
            elif 'Area(pixel)Mean' in roi_summary.columns:
                area_mean = (
                    pd.to_numeric(roi_summary['Area(pixel)Mean'], errors='coerce')
                    * (Config.PIXEL_SIZE ** 2)
                )
            if area_mean is not None:
                roi_summary['ROI_Area'] = area_mean

            section_volume_um3 = None
            if 'VolumeMean' in roi_summary.columns:
                section_volume_um3 = pd.to_numeric(roi_summary['VolumeMean'], errors='coerce')
            elif 'Volume(micron^3)Mean' in roi_summary.columns:
                section_volume_um3 = pd.to_numeric(
                    roi_summary['Volume(micron^3)Mean'], errors='coerce'
                )
            elif 'Volume(mm^3)Mean' in roi_summary.columns:
                section_volume_um3 = (
                    pd.to_numeric(roi_summary['Volume(mm^3)Mean'], errors='coerce')
                    * 1_000_000_000.0
                )
            elif area_mean is not None:
                section_volume_um3 = area_mean * Config.SECTION_THICKNESS_UM

            if section_volume_um3 is None:
                section_volume_um3 = pd.Series(np.nan, index=roi_summary.index, dtype=float)

            roi_summary['ROI_Volume'] = section_volume_um3
            roi_summary['Volume0p1mm3'] = section_volume_um3 / 100000000.0
            roi_summary['CountNormFactor'] = np.where(
                pd.to_numeric(roi_summary['Volume0p1mm3'], errors='coerce') > 0,
                1.0 / pd.to_numeric(roi_summary['Volume0p1mm3'], errors='coerce'),
                np.nan,
            )
            if area_mean is not None:
                roi_summary['ROI_Thickness'] = np.where(
                    pd.to_numeric(area_mean, errors='coerce') > 0,
                    pd.to_numeric(section_volume_um3, errors='coerce') / pd.to_numeric(area_mean, errors='coerce'),
                    np.nan,
                )
            else:
                roi_summary['ROI_Thickness'] = float(Config.SECTION_THICKNESS_UM)
            roi_summary[summed_cols] = roi_summary[summed_cols].div(
                roi_summary['Volume0p1mm3'], axis=0
            )
            for count_col in raw_count_cols:
                raw_col = f"{count_col}Raw"
                if raw_col in roi_summary.columns:
                    roi_summary = roi_summary.drop(columns=[raw_col])
                insert_at = roi_summary.columns.get_loc(count_col) + 1
                roi_summary.insert(insert_at, raw_col, raw_count_df[count_col])
            roi_summary = _add_marker_scores(roi_summary)

            # Mark behavior-only animals as not included for IF columns
            if_animals = set()
            if_columns = set()
            for stain in self.data.values():
                if not isinstance(stain, (objectMarker, cellMarker, Antibody)):
                    continue
                sdf = stain.df
                if "AnimalName" in sdf.columns:
                    if_animals.update(sdf["AnimalName"].dropna().astype(str).tolist())
                marker_prefix = f"{stain.name.split('_ROI')[0]}_"
                for col in roi_summary.columns:
                    if str(col).startswith(marker_prefix):
                        if_columns.add(col)

            if len(if_columns) > 0:
                if "AnimalName" in roi_summary.columns:
                    animal_series = roi_summary["AnimalName"].astype(str)
                else:
                    animal_series = pd.Series(roi_summary.index.astype(str), index=roi_summary.index)
                no_if_mask = ~animal_series.isin(if_animals)
                if no_if_mask.any():
                    cols = list(if_columns)
                    block = _replace_not_included_with_nan(roi_summary.loc[no_if_mask, cols], columns=cols)
                    roi_summary.loc[no_if_mask, cols] = block.where(
                        ~block.isna(),
                        NOT_INCLUDED_SENTINEL,
                    )
            roi_summary = _fill_missing_behavior_with_sentinel(
                roi_summary,
                behavior_summary_cols,
                behavior_animals=behavior_animals,
            )
            roi_summary = _fill_intden_totals_with_zero(roi_summary)
            self.summaries[roi_base] = roi_summary

        total_animals = max((s.shape[0] for s in self.summaries.values()), default=0)
        total_cols = sum(s.shape[1] for s in self.summaries.values())
        self._last_summary_summary = (
            f"{len(self.summaries)} ROI(s) | {total_animals} animals x {total_cols} total columns"
        )
        tracker.close(self._last_summary_summary)
        return self.summaries

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
            for roi_base, summary_df in self.summaries.items():
                summary_df['Condition'] = [
                    ''.join(filter(str.isalpha, n))
                    for n in summary_df.reset_index()['AnimalName'].tolist()
                ]
                summary_df[f] = summary_df['Condition'].str.extract(f'({names})', expand=False)
            for key in self.data:
                df = self.data[key].df
                if 'Condition' in df.columns:
                    df[f] = df['Condition'].str.extract(f'({names})', expand=False)
        if isinstance(getattr(self, "images", None), pd.DataFrame) and not self.images.empty:
            self.images = _attach_image_metadata(self, self.images)
        return self.condition_list

    # ── Region assignment ────────────────────────────────────────────────

    def assign_region(self):
        """Assign Region identifiers and ImageROI labels to all data tables."""
        roi_dfs = [self.data[k].df.copy() for k in self.data if 'ROI Properties' in k]
        if len(roi_dfs) == 0:
            self.master_region = pd.DataFrame(columns=["AnimalName", "Region", "ImageROI"])
            self._last_region_summary = "No ROI Properties tables found"
            return self.master_region

        # Reset index (Region) back to column for all data tables
        failures = []
        for data in self.data.values():
            data.df.reset_index(inplace=True)
            if "Region" not in data.df.columns:
                failures.append(data.name)

        roi_name_map = pd.DataFrame()
        rois_obj = self.data.get("ROIs", None)
        if rois_obj is not None and hasattr(rois_obj, "df") and isinstance(rois_obj.df, pd.DataFrame):
            rois_df = rois_obj.df.copy()
            if {"AnimalName", "Region"}.issubset(rois_df.columns):
                roi_name_map = _finalize_roi_name_labels(rois_df)

        if not roi_name_map.empty:
            self.master_region = (
                roi_name_map[["AnimalName", "Region", "ImageROI"]]
                .drop_duplicates(subset=["AnimalName", "Region"], keep="first")
                .reset_index(drop=True)
            )
            for data in self.data.values():
                if isinstance(getattr(data, "df", None), pd.DataFrame):
                    data.df = _apply_roi_name_map(data.df.copy(), roi_name_map)
        else:
            self.master_region = (
                pd.concat(roi_dfs, ignore_index=True)[["AnimalName", "Region"]]
                .drop_duplicates()
                .sort_values(["AnimalName", "Region"])
                .reset_index(drop=True)
            )
            # Construct ImageROI from Hemisphere + Region if available
            if "Hemisphere" in pd.concat(roi_dfs, ignore_index=True).columns:
                hemi_df = pd.concat(roi_dfs, ignore_index=True)[["AnimalName", "Region", "Hemisphere"]].drop_duplicates(
                    subset=["AnimalName", "Region"], keep="first"
                )
                self.master_region = self.master_region.merge(
                    hemi_df, on=["AnimalName", "Region"], how="left"
                )
                hemi = self.master_region["Hemisphere"].fillna("").astype(str)
                self.master_region["ImageROI"] = hemi + self.master_region["Region"]
                self.master_region = self.master_region.drop(columns=["Hemisphere"], errors="ignore")
            else:
                self.master_region["ImageROI"] = self.master_region["Region"]

        source_order = _source_panel_order_rows(self)
        if not source_order.empty:
            region_order = source_order[["AnimalName", "Region", "__source_order__"]].drop_duplicates(
                subset=["AnimalName", "Region"],
                keep="first",
            )
            self.master_region = self.master_region.merge(
                region_order,
                on=["AnimalName", "Region"],
                how="left",
            )
            self.master_region["__source_missing__"] = self.master_region["__source_order__"].isna().astype(int)
            self.master_region = (
                self.master_region
                .sort_values(
                    ["AnimalName", "__source_missing__", "__source_order__", "ImageROI", "Region"],
                    kind="stable",
                )
                .drop(columns=["__source_order__", "__source_missing__"], errors="ignore")
                .reset_index(drop=True)
            )
        else:
            self.master_region = (
                self.master_region
                .sort_values(["AnimalName", "ImageROI", "Region"], kind="stable")
                .reset_index(drop=True)
            )

        aligned_roi_map = _align_image_roi_to_master_order(self.master_region)
        if not aligned_roi_map.empty:
            self.master_region = (
                self.master_region
                .drop(columns=["ImageROI"], errors="ignore")
                .merge(aligned_roi_map, on=["AnimalName", "Region"], how="left")
                .reset_index(drop=True)
            )
            for data in self.data.values():
                if isinstance(getattr(data, "df", None), pd.DataFrame):
                    data.df = _apply_roi_name_map(data.df.copy(), aligned_roi_map)

        n_animals = self.master_region['AnimalName'].nunique()
        n_regions = len(self.master_region)
        summary = f"{n_animals} animals | {n_regions} regions"
        if len(failures) > 0:
            summary += f" | skipped: {_summarize_name_list(failures)}"
        self._last_region_summary = summary
        # Backward compat aliases
        self.master_scn = self.master_region
        self._last_scn_summary = self._last_region_summary
        return self.master_region

    # Backward compat alias
    assign_scn_number = assign_region

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

    def getDisplaySummary(self, roi_base=None):
        """Return a display-only summary copy with unit-labelled column names."""
        if roi_base is not None and roi_base in getattr(self, "summaries", {}):
            summary = self.summaries[roi_base]
        else:
            summary = getattr(self, "summary", None)
        if not isinstance(summary, pd.DataFrame):
            return summary
        return format_summary_for_display(summary)

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
            _log.confirm(f"{attr_name} data saved to CSV.")

    # ── Lookup helpers ─────────────────────────────────────────────────

    def getRegionDict(self, roi_base=None):
        """Return {roi_base: {condition: {animal: [region_values]}}}.

        If roi_base is given, return just {condition: {animal: [regions]}} for that ROI.
        """
        try:
            df = self.master_region
            result = {}
            # Group master_region by ROI base
            if 'ROI' in df.columns:
                roi_bases = df['ROI'].fillna('').astype(str).apply(extract_region_base).unique()
            else:
                roi_bases = ['SCN']

            for rb in roi_bases:
                if 'ROI' in df.columns:
                    rb_df = df[df['ROI'].fillna('').astype(str).apply(extract_region_base) == rb]
                else:
                    rb_df = df
                summary_df = self.summaries.get(rb, self.summary)
                result[rb] = {
                    cond: {
                        animal: rb_df[rb_df['AnimalName'] == animal]['Region'].unique().tolist()
                        for animal in summary_df[summary_df['Condition'] == cond]['AnimalName'].unique()
                    }
                    for cond in [c.name for c in self.condition_list]
                }
        except (KeyError, AttributeError):
            result = {'SCN': {
                cond: self.summary[self.summary['Condition'] == cond]['AnimalName'].unique().tolist()
                for cond in [c.name for c in self.condition_list]
            }}

        if roi_base is not None:
            return result.get(roi_base, {})
        return result

    def getSCNDict(self):
        """Backward compat alias — returns region dict for SCN ROIs."""
        return self.getRegionDict(roi_base='SCN')

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
