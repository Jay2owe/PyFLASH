"""
Excel export functions for IF summary, behaviour summary, and extended data.

These generate formatted .xlsx files from processed Batch objects.
"""

import re
import os
import time
import numpy as np
import pandas as pd
from pathlib import Path

from IF_analysis.config import Config
from IF_analysis.markers import Antibody

# ── Name mapping for Excel column headers ──────────────────────────────

threshold = Config.THRESHOLD

_OBJ_COUNTER = (
    "Using 3D Object Counter, confocal image stacks were segmented "
    "into individual 3D objects based on a threshold.\n"
)
_PER_VOL = "normalized per volume of tissue"
_QUANTIFIED = "was then quantified"
_MULTICOLOC = (
    "Using 3D MultiColoc, the co-occurence colocalization between "
    "segmented <ab> and <ab2> objects was then quantified.\n"
)

IF_NAME_MAP = {
    "<ab>_Count": {
        "label": "<ab> Count per 0.1mm³",
        "desc": f"{_OBJ_COUNTER}The number of segmented <ab> objects was summed and {_PER_VOL}.",
    },
    "<ab>_CountRaw": {
        "label": "<ab> Raw Count",
        "desc": f"{_OBJ_COUNTER}The number of segmented <ab> objects was summed and averaged across sections before tissue-volume normalization.",
    },
    "ROI_Thickness": {
        "label": "ROI Thickness (µm)",
        "desc": "Section thickness used for summary normalization, or the effective thickness inferred from explicit ROI volume and area.",
    },
    "ROI_Volume": {
        "label": "ROI Volume (µm³)",
        "desc": "Tissue volume used for normalization, taken from ROI Properties volume when available or derived from area and fallback section thickness otherwise.",
    },
    "ROI_Area": {
        "label": "ROI Area (µm²)",
        "desc": "ROI area used for summary normalization and thickness sanity checks.",
    },
    "Volume0p1mm3": {
        "label": "Volume (0.1 mm³ units)",
        "desc": "Estimated tissue volume expressed in units of 0.1 mm³.",
    },
    "CountNormFactor": {
        "label": "Count Normalization Factor",
        "desc": "Multiplier that converts CountRaw into normalized count per 0.1 mm³.",
    },
    "<ab>_IntDenTotal": {
        "label": "<ab> IntDen (A.U.) per 0.1mm³",
        "desc": f"{_OBJ_COUNTER}The integrated density across all segmented <ab> objects was summed and {_PER_VOL}.",
    },
    "<ab>_VolumeTotal": {
        "label": "<ab> Volume (µm³) per 0.1mm³",
        "desc": f"{_OBJ_COUNTER}The volume of all segmented <ab> objects was summed and {_PER_VOL}.",
    },
    "<ab>_SurfaceTotal": {
        "label": "<ab> SA (µm²) per 0.1mm³",
        "desc": f"{_OBJ_COUNTER}The surface area of all segmented <ab> objects was summed and {_PER_VOL}.",
    },
    "<ab>_IntDenMean": {
        "label": "<ab> Mean IntDen (A.U.)",
        "desc": f"{_OBJ_COUNTER}The mean integrated density per segmented <ab> object {_QUANTIFIED}.",
    },
    "<ab>_VolumeMean": {
        "label": "<ab> Mean Volume (µm³)",
        "desc": f"{_OBJ_COUNTER}The mean volume per segmented <ab> object {_QUANTIFIED}.",
    },
    "<ab>_SurfaceMean": {
        "label": "<ab> Mean SA (µm²)",
        "desc": f"{_OBJ_COUNTER}The mean surface area per segmented <ab> object {_QUANTIFIED}.",
    },
    "<ab>_SAtoVolumeRatioMean": {
        "label": "<ab> Mean SA-Vol",
        "desc": f"{_OBJ_COUNTER}The mean surface-area-to-volume ratio per segmented <ab> object {_QUANTIFIED}.",
    },
    "<ab>_MeanIntDenMean": {
        "label": "<ab> Mean Pixel IntDen",
        "desc": f"{_OBJ_COUNTER}The mean integrated density of each segmented <ab> object was then normalized by the number of <ab> objects.",
    },
    "<ab>_Coloc_<ab2>_Mean": {
        "label": "<ab2> Overlap per <ab>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The mean % voxel overlap of each segmented <ab> object by <ab2> {_QUANTIFIED}.",
    },
    "<ab>_Coloc<ab2>Mean": {
        "label": "<ab2> Overlap per <ab>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The mean % voxel overlap of each segmented <ab> object by <ab2> {_QUANTIFIED}.",
    },
    "<ab>_Coloc_<ab2>_Count": {
        "label": "<ab> colocalised with <ab2> per 0.1mmÂ³",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects with a greater than {threshold}% overlap by <ab2> objects was summed and {_PER_VOL}.",
    },
    "<ab>_Coloc_<ab2>_CountRaw": {
        "label": "<ab> raw colocalised with <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects with a greater than {threshold}% overlap by <ab2> objects was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_Coloc_<ab2>_Count%": {
        "label": "% <ab> colocalised with <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The percentage of segmented <ab> objects with a greater than {threshold}% overlap by <ab2> objects {_QUANTIFIED}.",
    },
    "<ab>_ColocCount<ab2>": {
        "label": "<ab2>+<ab> per 0.1mm³",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The % of segmented <ab> objects with a greater than {threshold}% overlap by <ab2> objects {_QUANTIFIED}.",
    },
    "<ab>_ColocCount<ab2>%": {
        "label": "% <ab2>+<ab> per <ab>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The % of segmented <ab> objects with a greater than {threshold}% overlap by <ab2> objects {_QUANTIFIED}.",
    },
    "<ab>_DistToClosest_<ab2>Mean": {
        "label": "<ab> Mean Nearest <ab2>",
        "desc": f"{_OBJ_COUNTER}Using euclidean distance calculations and the objects' centre of masses, the closest <ab2> object was identified and the distance calculated.\nThe mean distance for each <ab> object {_QUANTIFIED}.",
    },
    "<ab>_DistToVentricle": {
        "label": "<ab> Mean Ventricle Distance",
        "desc": f"{_OBJ_COUNTER}Using euclidean distance calculations and the centre of mass of <ab> objects, the distance to the ventricular boundary was calculated.\nThe mean distance of each <ab> object to the ventricle {_QUANTIFIED}.",
    },
    "<ab>_Contains_<ab2>_Count": {
        "label": "<ab> contains <ab2> per 0.1mmÂ³",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects containing <ab2> was summed and {_PER_VOL}.",
    },
    "<ab>_Contains_<ab2>_CountRaw": {
        "label": "<ab> raw contains <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects containing <ab2> was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_Contains_<ab2>_Count%": {
        "label": "% <ab> contains <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The percentage of segmented <ab> objects containing <ab2> {_QUANTIFIED}.",
    },
    "<ab>_Contains_<ab2>Mean": {
        "label": "% <ab> w <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The mean number of <ab> objects containing <ab2> {_QUANTIFIED}.",
    },
    "<ab>_Any_<ab2>_Count": {
        "label": "<ab> coloc/contains <ab2> per 0.1mm³",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects that either directly colocalised with or contained <ab2> was summed and {_PER_VOL}.",
    },
    "<ab>_Any_<ab2>_CountRaw": {
        "label": "<ab> raw coloc/contains <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects that either directly colocalised with or contained <ab2> was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_Any_<ab2>_Count%": {
        "label": "% <ab> coloc/contains <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The percentage of segmented <ab> objects that either directly colocalised with or contained <ab2> {_QUANTIFIED}.",
    },
    "<ab>_NumColoc_<ab2>Mean": {
        "label": "<ab> Mean # Internal <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of internalized <ab2> objects per <ab> object was then quantified.",
    },
    "<ab>_ROI_IntDenMean": {
        "label": "<ab> ROI IntDen (A.U.)",
        "desc": "The total integrated density of <ab> signal within the ROI was quantified and then adjusted by the volume of the ROI.",
    },
    "<ab>_ROI_%AreaMean": {
        "label": "<ab> %Area",
        "desc": "The percentage of ROI area occupied by thresholded <ab>-positive signal.",
    },
    "<ab>_RawYMMean": {
        "label": "<ab> Mean YM (µms)",
        "desc": f"{_OBJ_COUNTER}The mean Y-coordinate of <ab> objects was then quantified in physical units.",
    },
    "<ab>_RawXMMean": {
        "label": "<ab> Mean XM",
        "desc": f"{_OBJ_COUNTER}The mean X-coordinate of <ab> objects was then quantified in physical units.",
    },
    "<ab>_burdenScore": {
        "label": "<ab> Burden Score",
        "desc": "Composite score from log-normalized and z-scored IntDenTotal, VolumeTotal, SA/SurfaceTotal, and %AreaMean, averaged per animal.",
    },
    "<ab>_fragmentationScore": {
        "label": "<ab> Fragmentation Score",
        "desc": "Composite score from log-normalized and z-scored Count/VolumeTotal ratio per animal.",
    },
}

BEHAVIOR_NAME_MAP = {
    "Period": {"label": "Circadian period (hours)", "desc": "Duration of one complete circadian cycle."},
    "IV": {"label": "Intradaily variability", "desc": "Measure of rhythm fragmentation within a 24-hour period."},
    "AOE": {"label": "Activity onset error", "desc": "Variability in the timing of daily activity onset."},
    "Arrhythmic": {"label": "Arrhythmic", "desc": "Binary classification indicating absence of significant circadian rhythm."},
    "weightincrement(gr)": {"label": "Weight increase (g)", "desc": "Change in body weight over the experimental period."},
    "LocomotoractivityIR(counts)": {"label": "Locomotor activity (counts)", "desc": "Total recorded locomotor activity events."},
}

RAW_NAME_MAP = {
    # --- Per-object morphology / intensity ---
    "<ab>_Volume":             {"label": "Volume (µm³)",            "desc": "Volume of each segmented <ab> object."},
    "<ab>_Surface":            {"label": "SA (µm²)",                "desc": "Surface area of each segmented <ab> object."},
    "<ab>_IntDen":             {"label": "IntDen",                  "desc": "Integrated density of each segmented <ab> object."},
    "<ab>_MeanIntDen":         {"label": "Mean IntDen (per pixel)", "desc": "Mean intensity per <ab> object (per-object mean intensity)."},
    "<ab>_SAtoVolumeRatio":    {"label": "SA:Vol",                  "desc": "Surface-area-to-volume ratio for each <ab> object."},

    # --- Per-object coordinates ---
    "<ab>_XM":                 {"label": "Display XM (px)",         "desc": "X coordinate (pixels) of the <ab> object centre of mass."},
    "<ab>_YM":                 {"label": "Display YM (px)",         "desc": "Y coordinate (pixels) of the <ab> object centre of mass."},
    "<ab>_RawXM":              {"label": "XM (µm)",                 "desc": "X coordinate (physical units) of the <ab> object centre of mass."},
    "<ab>_RawYM":              {"label": "YM (µm)",                 "desc": "Y coordinate (physical units) of the <ab> object centre of mass."},

    # --- Per-object distances ---
    "<ab>_DistToVentricle":    {"label": "<ab> → ventricle (µm)",        "desc": "Distance from each <ab> object to the ventricular boundary."},
    "<ab>_DistToClosest_<ab2>": {"label": "nearest <ab2> (µm)",     "desc": "Distance from each <ab> object to the closest <ab2> object (centre-to-centre)."},
    "<ab>_ClosestTo_<ab2>":    {"label": "is nearest <ab> to <ab2>",        "desc": "Boolean per <ab> object indicating whether this <ab> object is the nearest <ab> ""(among all <ab> objects) to a given <ab2> object (nearest-neighbour assignment)."},
    "<ab>_NumClosestTo_<ab2>": {"label": "# <ab2> nearest to",       "desc": "Number of <ab2> objects for which this <ab> object is the nearest <ab> "},
    
    # --- Voxel overlap / colocalisation metrics (per object) ---
    "<ab>_Coloc_<ab2>":        {"label": "<ab2> overlap (%)",         "desc": "Voxel-overlap (co-occurrence) of <ab2> with each <ab> object (per-object overlap metric)."},
    "<ab>_Coloc<ab2>":         {"label": "<ab2> overlap (%)",         "desc": "Voxel-overlap (co-occurrence) of <ab2> with each <ab> object (per-object overlap metric)."},
    "<ab>_ColocCount<ab2>":    {"label": f"<ab2>+ (<{threshold}% overlap)",     "desc": "Binary/thresholded co-localisation classification per <ab> object for <ab2> (per-object)."},

    # --- Containment / internalisation (per object) ---
    "<ab>_NumColoc_<ab2>":     {"label": "# internal <ab2>",      "desc": "Number of <ab2> objects classified as internalised/contained per <ab> object (per-object value)."},
    "<ab>_Contains_<ab2>":     {"label": "contains <ab2>",          "desc": "Binary indicator per <ab> object: whether it contains ≥1 <ab2> object under your overlap criterion."},
    "<ab>_Any_<ab2>":          {"label": "coloc or contains <ab2>", "desc": "Binary indicator per <ab> object: whether it either passes the direct colocalisation threshold for <ab2> or contains ≥1 <ab2> object."},

    "<ab>_ROI_IntDen":          {"label": "ROI IntDen (per Z-step)", "desc": "ROI IntDen per Z-Step."},
    "<ab>_ROI_%Area":          {"label": "%Area coverage (per Z-step)", "desc": "ROI IntDen per Z-Step."}
}

# ── Pattern matching ───────────────────────────────────────────────────

def _pattern_to_regex(pattern):
    s = re.escape(pattern)
    s = s.replace(r"<ab>", r"(?P<ab>[A-Za-z0-9_-]+)")
    s = s.replace(r"<ab2>", r"(?P<ab2>[A-Za-z0-9_-]+)")
    return re.compile(f"^{s}$")


EXCEL_MAX = 31
_EXP_SUFFIX_RE = re.compile(r"\.exp(\d+)$")

def _strip_exp_suffix(colname: str):
    """Strip '.expN' disambiguation suffix, returning (base_name, exp_tag_or_empty)."""
    m = _EXP_SUFFIX_RE.search(colname)
    if m:
        return colname[:m.start()], m.group(0)
    return colname, ""

_RULES = sorted(
    ((_pattern_to_regex(p), rule) for p, rule in IF_NAME_MAP.items()),
    key=lambda x: len(x[0].pattern),
    reverse=True,
)


def convert_name(colname: str, truncate: bool = True):
    """Convert a raw column name to (short_label, description)."""
    base, exp_tag = _strip_exp_suffix(colname)
    for rx, rule in _RULES:
        m = rx.match(base)
        if m:
            label, desc = rule["label"], rule["desc"]
            for k, v in m.groupdict().items():
                label = label.replace(f"<{k}>", v)
                desc = desc.replace(f"<{k}>", v)
            if exp_tag:
                label = f"{label} ({exp_tag.lstrip('.')})"
            return (label[:EXCEL_MAX] if truncate else label), desc
    raise KeyError(f"No NAME_MAP rule for column: {colname}")

RAW_RULES = sorted(
    ((_pattern_to_regex(p), rule) for p, rule in RAW_NAME_MAP.items()),
    key=lambda x: len(x[0].pattern),
    reverse=True
)

def convert_raw_name(colname: str):
    base, exp_tag = _strip_exp_suffix(colname)
    for rx, rule in RAW_RULES:
        m = rx.match(base)
        if not m:
            continue
        label = rule["label"]
        desc  = rule["desc"]
        for k, v in m.groupdict().items():
            label = label.replace(f"<{k}>", v)
            desc  = desc.replace(f"<{k}>", v)
        if exp_tag:
            label = f"{label} ({exp_tag.lstrip('.')})"
        return label, desc
    raise KeyError(colname)

def normalize_marker_name(key: str) -> str:
    """Collapse Caspase3_ROI → Caspase3"""
    return key.split("_ROI")[0]

def extract_data_name(col: str, marker: str) -> str:
    """Caspase3_VolumeMean → VolumeMean"""
    prefix = marker + "_"
    return col[len(prefix):] if col.startswith(prefix) else col

def lookup_description(data_name: str) -> str:
    if data_name in BEHAVIOR_NAME_MAP:
        return BEHAVIOR_NAME_MAP[data_name]["desc"]
    for pattern, rule in IF_NAME_MAP.items():
        if pattern.endswith(data_name):
            return rule["desc"]
    return "No description available."

def safe_sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]\:\*\?\/\\]", "-", str(name)).strip()
    base = base[:EXCEL_MAX] if len(base) > EXCEL_MAX else base
    out = base
    n = 1
    while out.lower() in {s.lower() for s in used} or out == "":
        suffix = f"_{n}"
        out = (base[:EXCEL_MAX - len(suffix)] + suffix) if len(base) + len(suffix) > EXCEL_MAX else (base + suffix)
        n += 1
    used.add(out)
    return out

# ── Formatter functions ───────────────────────────────────────────────────

def merge_contiguous_cells(worksheet, df, col_name, col_idx=0, cell_format=None):
    start_row = None
    current_value = None
    for i, value in enumerate(df[col_name], start=1):
        value = "" if value is None else str(value)

        if value and value != current_value:
            # close previous block
            if start_row is not None and i - 1 > start_row:
                worksheet.merge_range(
                    start_row, col_idx,
                    i - 1, col_idx,
                    current_value,
                    cell_format
                )
            # start new block
            current_value = value
            start_row = i

    # close final block
    if start_row is not None and len(df) >= 1 and len(df) > start_row:
        worksheet.merge_range(
            start_row, col_idx,
            len(df), col_idx,
            current_value,
            cell_format
        )

def _groups_for_column(colname: str) -> dict:
    base, _ = _strip_exp_suffix(colname)
    for rx, _rule in _RULES:
        m = rx.match(base)
        if m:
            return m.groupdict()
    raise KeyError(colname)


def _summary_marker_for_column(colname: str) -> str:
    """
    Return the real marker represented by a summary column.

    Combo-derived summary columns are named like
    ``DAPI_Combo_wCK1d_Count`` or ``DAPI_ComboAny_CK1d+_Count``. Those should
    still be documented under the base marker ``DAPI`` in the Excel "Data
    Summary" sheet rather than being treated as standalone markers.
    """
    base, _ = _strip_exp_suffix(colname)
    if "_ComboAny_" in base:
        return base.split("_ComboAny_", 1)[0]
    if "_Combo_" in base:
        return base.split("_Combo_", 1)[0]

    groups = _groups_for_column(colname)
    marker = groups.get("ab")
    if marker:
        return normalize_marker_name(marker)
    raise KeyError(colname)

def autosize_columns(worksheet, df, padding=2, max_width=120):
    for col_idx, col_name in enumerate(df.columns):
        series = df[col_name].astype(str).fillna("")
        max_len = max(len(str(col_name)), series.map(len).max() if len(series) else 0)
        if col_name == "Filter Macro": 
            worksheet.set_column(col_idx, col_idx, 50)
        else: worksheet.set_column(col_idx, col_idx, min(max_len + padding, max_width))

def blank_repeats(df, cols):
    out = df.copy()
    for i, col in enumerate(cols):
        prev_cols = cols[:i]  # higher-level grouping columns
        same_group = True
        for pc in prev_cols:
            same_group = same_group & (out[pc] == out[pc].shift())
        out[col] = out[col].where(~((out[col] == out[col].shift()) & same_group), "")
    return out

def write_formatted_df(writer, df, sheet_name, wrap_cols=None, center_cols=None, small_cols=None, padding=2, max_width=120):
    wrap_cols = set(wrap_cols or [])
    center_cols = set(center_cols or [])
    small_cols = set(small_cols or [])

    df.to_excel(writer, sheet_name=sheet_name, index=False)
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]

    header_fmt = workbook.add_format({
        "bold": True,
        "bg_color": "#F2F2F2",
        "border": 1,
        "valign": "vcenter",
        "align": "center"
    })
    cell_fmt = workbook.add_format({"border": 1, "valign": "vcenter",})
    wrap_fmt = workbook.add_format({"border": 1, "valign": "vcenter", "text_wrap": True})
    center_fmt = workbook.add_format({"border": 1, "valign": "vcenter", "align": "center"})
    small_fmt = cell_fmt = workbook.add_format({"border": 1, "valign": "vcenter", "font_size": 7, "text_wrap": True})
    for col_idx, col_name in enumerate(df.columns):
        worksheet.write(0, col_idx, col_name, header_fmt)

    # Body formatting
    for r in range(1, len(df) + 1):
        for c, col_name in enumerate(df.columns):
            fmt = wrap_fmt if col_name in wrap_cols else center_fmt if col_name in center_cols else small_fmt if col_name in small_cols else cell_fmt
            worksheet.write(r, c, df.iloc[r-1, c], fmt)

    autosize_columns(worksheet, df, padding=padding, max_width=max_width)

    return worksheet  # so you can merge cells afterwards

TAG_RE = re.compile(r"<(?P<tag>[^>]+)>\s*(?P<body>.*?)\s*</(?P=tag)>", re.DOTALL)

def parse_details_file(txt_path: str | Path) -> dict[str, str]:
    """
    Returns a dict like {"Filter Macro": "...", "Analysis Macro": "...", ...}
    based on <Tag>...</Tag> blocks.
    """
    txt_path = Path(txt_path)
    text = txt_path.read_text(encoding="utf-8", errors="ignore")

    blocks = {}
    for m in TAG_RE.finditer(text):
        tag = m.group("tag").strip()
        body = m.group("body").strip()
        blocks[tag] = body

    return blocks

def find_details_file(details_dir: str | Path, marker: str) -> Path | None:
    details_dir = Path(details_dir)
    if not details_dir.exists():
        return None

    marker_norm = marker.lower()

    # 1) exact stem match: Caspase3.txt
    exact = details_dir / f"{marker}.txt"
    if exact.exists():
        return exact

    # 2) case-insensitive stem match
    for p in details_dir.glob("*.txt"):
        if p.stem.lower() == marker_norm:
            return p

    # 3) contains match (fallback)
    for p in details_dir.glob("*.txt"):
        if marker_norm in p.stem.lower():
            return p

    return None

# ── Exporter functions ───────────────────────────────────────────────────

def write_experiment_data_list_sheet(writer, experiment_list, sheet_name="Data overview", visible_columns=None):
    rows = []
    visible_set = None if visible_columns is None else {str(col) for col in visible_columns}

    for exp_idx, exp in enumerate(experiment_list, start=1):
        exp_name = f"Experiment {exp_idx}"
        base_path = Path(exp.filePath)
        bucket = {}

        summary_cols = exp.summary.columns
        for col in summary_cols:
            col_s = str(col)
            if visible_set is not None:
                visible_candidates = {col_s, f"{col_s}.exp{exp_idx}"}
                if not any(candidate in visible_set for candidate in visible_candidates):
                    continue
            try:
                label, _ = convert_name(col)  # SAME logic as export_summary_excel
            except KeyError:
                continue  # not in NAME_MAP → skip

            # Document combo-derived summary columns under their parent marker.
            try:
                marker = _summary_marker_for_column(col)
            except KeyError:
                continue

            analysis = "ROI" if "_ROI" in col else "Object"
            key = (marker, analysis)

            if key not in bucket:
                bucket[key] = {"labels": set(), "filter": "", "analysis": ""}

                # choose the correct Details folder for this analysis type
                details_dir = (
                    base_path / "ROI Intensities" / "Analysis Details"
                    if analysis == "ROI"
                    else base_path / "Objects" / "Analysis Details"
                )

                details_file = find_details_file(details_dir, marker)
                if details_file:
                    blocks = parse_details_file(details_file)
                    bucket[key]["filter"] = blocks.get("Filter Macro", "")
                    bucket[key]["analysis"] = blocks.get("Analysis Macro", "")

            bucket[key]["labels"].add(label)


        for (marker, analysis), info in bucket.items():
            rows.append({
                "Experiment": exp_name,
                "Marker": marker,
                "Analysis": analysis,
                "Data": ", ".join(sorted(info['labels'])),
                "Filter Macro": info['filter'],
                "Analysis Macro": info['analysis']
            })

    df = pd.DataFrame(rows) if rows else pd.DataFrame([{"Experiment": "", "Marker": "", "Analysis": "", "Data": "No documented data found.", "Filter Macro": "", "Analysis Macro": ""}])

    # Sort for stable grouping
    df = df.sort_values(["Experiment", "Marker", "Analysis"], kind="stable")

    # Blank repeated Experiment / Marker for display
    df_display = blank_repeats(df, ["Experiment", "Marker"])

    worksheet = write_formatted_df(writer, df_display, sheet_name=sheet_name, wrap_cols={"Data"}, center_cols={"Analysis"}, small_cols={"Filter Macro", "Analysis Macro"}, max_width=120)

    merge_fmt = writer.book.add_format({"valign": "vcenter", "border": 1, 'align':'center'})
    merge_contiguous_cells(worksheet, df_display, col_name="Experiment", col_idx=0, cell_format=merge_fmt)
    merge_contiguous_cells(worksheet, df_display, col_name="Marker", col_idx=1, cell_format=merge_fmt)

EXCEL_FORBIDDEN = r"\\[a-zA-Z]+\{|\}|\$|\^\{|\}"
def write_conditions_table_sheet(writer, conditions, sheet_name="Conditions", padding=2, max_width=120):
    rows = []
    used = set()

    for c in conditions:
        if c.name in used:
            continue
        used.add(c.name)
        rows.append({
            "Factor": getattr(c, "factor", ""),
            "Name": getattr(c, "name", ""),
            "Explanation": re.sub(EXCEL_FORBIDDEN, "", getattr(c, "factor_explanation", "")),
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame([{"Factor": "", "Name": "", "Explanation": "No conditions found."}])

    df = df.sort_values(["Factor"], kind="stable")
    df_display = blank_repeats(df, ["Factor"])

    worksheet = write_formatted_df(writer, df_display, sheet_name=sheet_name, wrap_cols={"Explanation"}, padding=padding, max_width=max_width)

    merge_fmt = writer.book.add_format({"valign": "top", "border": 1})
    merge_contiguous_cells(worksheet, df_display, "Factor", 0, cell_format=merge_fmt)

def convert_behavior_name(colname: str, truncate: bool = True):
    if colname not in BEHAVIOR_NAME_MAP:
        raise KeyError(f"No BEHAVIOR_NAME_MAP rule for column: {colname}")

    rule = BEHAVIOR_NAME_MAP[colname]
    return (rule["label"][:EXCEL_MAX] if truncate else rule["label"]), rule["desc"]


def _display_label_for_summary_column(colname: str) -> str:
    try:
        return convert_name(colname, truncate=False)[0]
    except KeyError:
        try:
            return convert_behavior_name(colname, truncate=False)[0]
        except KeyError:
            return colname


def format_summary_for_display(summary: pd.DataFrame) -> pd.DataFrame:
    """Return a display-only copy of a summary with human-readable labels."""
    if not isinstance(summary, pd.DataFrame):
        raise TypeError("summary must be a pandas DataFrame")

    out = summary.copy()
    out.columns = [
        _display_label_for_summary_column(str(col))
        for col in out.columns
    ]
    return out

# Additional optimization: Create a cached version of convert_raw_name if called frequently
_raw_name_cache = {}

def convert_raw_name_cached(colname: str):
    """Cached version of convert_raw_name to avoid redundant regex matching."""
    if colname in _raw_name_cache:
        return _raw_name_cache[colname]
    
    result = convert_raw_name(colname)
    _raw_name_cache[colname] = result
    return result
