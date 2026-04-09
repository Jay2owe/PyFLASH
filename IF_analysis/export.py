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
_PER_VOL = "normalized per 0.1 mm^3 of tissue/ROI volume"
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

IF_NAME_MAP.update({
    "<ab>_VolColoc_<ab2>_Mean": {
        "label": "<ab2> Vol Overlap per <ab>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The mean volumetric % voxel overlap of each segmented <ab> object by <ab2> {_QUANTIFIED}.",
    },
    "<ab>_VolColoc_<ab2>_Count": {
        "label": "<ab> volumetric coloc with <ab2> per 0.1mmÂ³",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects positive for volumetric colocalisation with <ab2> was summed and {_PER_VOL}.",
    },
    "<ab>_VolColoc_<ab2>_CountRaw": {
        "label": "<ab> raw volumetric coloc with <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects positive for volumetric colocalisation with <ab2> was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_VolColoc_<ab2>_Count%": {
        "label": "% <ab> volumetric coloc with <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The percentage of segmented <ab> objects positive for volumetric colocalisation with <ab2> {_QUANTIFIED}.",
    },
    "<ab>_VolContains_<ab2>_Count": {
        "label": "<ab> volumetric contains <ab2> per 0.1mmÂ³",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects volumetrically containing <ab2> was summed and {_PER_VOL}.",
    },
    "<ab>_VolContains_<ab2>_CountRaw": {
        "label": "<ab> raw volumetric contains <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects volumetrically containing <ab2> was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_VolContains_<ab2>_Count%": {
        "label": "% <ab> volumetric contains <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The percentage of segmented <ab> objects volumetrically containing <ab2> {_QUANTIFIED}.",
    },
    "<ab>_VolAny_<ab2>_Count": {
        "label": "<ab> volumetric assoc with <ab2> per 0.1mmÂ³",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects that either volumetrically colocalised with or volumetrically contained <ab2> was summed and {_PER_VOL}.",
    },
    "<ab>_VolAny_<ab2>_CountRaw": {
        "label": "<ab> raw volumetric assoc with <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The number of segmented <ab> objects that either volumetrically colocalised with or volumetrically contained <ab2> was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_VolAny_<ab2>_Count%": {
        "label": "% <ab> volumetric assoc with <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The percentage of segmented <ab> objects that either volumetrically colocalised with or volumetrically contained <ab2> {_QUANTIFIED}.",
    },
    "<ab>_VolNumColoc_<ab2>Mean": {
        "label": "<ab> Mean # Vol Internal <ab2>",
        "desc": f"{_OBJ_COUNTER}{_MULTICOLOC}The mean number of volumetrically internalised <ab2> objects per <ab> object was then quantified.",
    },
    "<ab>_CPCColoc_<ab2>_Mean": {
        "label": "<ab2> CPC per <ab>",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the mean CPC association of each segmented <ab> object by <ab2> {_QUANTIFIED}.",
    },
    "<ab>_CPCColoc_<ab2>_Count": {
        "label": "<ab> CPC coloc with <ab2> per 0.1mmÂ³",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the number of segmented <ab> objects positive for <ab2> was summed and {_PER_VOL}.",
    },
    "<ab>_CPCColoc_<ab2>_CountRaw": {
        "label": "<ab> raw CPC coloc with <ab2>",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the number of segmented <ab> objects positive for <ab2> was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_CPCColoc_<ab2>_Count%": {
        "label": "% <ab> CPC coloc with <ab2>",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the percentage of segmented <ab> objects positive for <ab2> {_QUANTIFIED}.",
    },
    "<ab>_CPCContains_<ab2>_Count": {
        "label": "<ab> CPC contains <ab2> per 0.1mmÂ³",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the number of segmented <ab> objects classified as containing <ab2> was summed and {_PER_VOL}.",
    },
    "<ab>_CPCContains_<ab2>_CountRaw": {
        "label": "<ab> raw CPC contains <ab2>",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the number of segmented <ab> objects classified as containing <ab2> was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_CPCContains_<ab2>_Count%": {
        "label": "% <ab> CPC contains <ab2>",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the percentage of segmented <ab> objects classified as containing <ab2> {_QUANTIFIED}.",
    },
    "<ab>_CPCAny_<ab2>_Count": {
        "label": "<ab> CPC assoc with <ab2> per 0.1mmÂ³",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the number of segmented <ab> objects that either CPC-colocalised with or CPC-contained <ab2> was summed and {_PER_VOL}.",
    },
    "<ab>_CPCAny_<ab2>_CountRaw": {
        "label": "<ab> raw CPC assoc with <ab2>",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the number of segmented <ab> objects that either CPC-colocalised with or CPC-contained <ab2> was summed and averaged across sections before tissue-volume normalization.",
    },
    "<ab>_CPCAny_<ab2>_Count%": {
        "label": "% <ab> CPC assoc with <ab2>",
        "desc": f"{_OBJ_COUNTER}Using centre-particle coincidence, the percentage of segmented <ab> objects that either CPC-colocalised with or CPC-contained <ab2> {_QUANTIFIED}.",
    },
})

RAW_NAME_MAP.update({
    "<ab>_VolColoc_<ab2>": {"label": "<ab2> vol overlap (%)", "desc": "Volumetric voxel-overlap of <ab2> with each <ab> object."},
    "<ab>_VolColocCount<ab2>": {"label": f"<ab2>+ vol (<{threshold}% overlap)", "desc": "Binary volumetric colocalisation classification per <ab> object for <ab2>."},
    "<ab>_VolNumColoc_<ab2>": {"label": "# vol internal <ab2>", "desc": "Number of <ab2> objects volumetrically classified as internalised/contained per <ab> object."},
    "<ab>_VolContains_<ab2>": {"label": "vol contains <ab2>", "desc": "Binary volumetric indicator per <ab> object: whether it contains ≥1 <ab2> object."},
    "<ab>_VolAny_<ab2>": {"label": "vol coloc or contains <ab2>", "desc": "Binary volumetric indicator per <ab> object: whether it either volumetrically colocalises with or contains ≥1 <ab2> object."},
    "<ab>_CPCColoc_<ab2>": {"label": "<ab2> CPC", "desc": "Centre-particle coincidence association of <ab2> with each <ab> object."},
    "<ab>_CPCColocCount<ab2>": {"label": "<ab2>+ CPC", "desc": "Binary CPC association classification per <ab> object for <ab2>."},
    "<ab>_CPCContains_<ab2>": {"label": "CPC contains <ab2>", "desc": "Binary CPC indicator per <ab> object: whether it contains ≥1 <ab2> object."},
    "<ab>_CPCAny_<ab2>": {"label": "CPC coloc or contains <ab2>", "desc": "Binary CPC indicator per <ab> object: whether it either coincides with or contains ≥1 <ab2> object."},
})

# Legacy unprefixed coloc names are volumetric by definition. Keep them
# resolvable, but surface the explicit volumetric wording in labels.
IF_NAME_MAP.update({
    "<ab>_Coloc_<ab2>_Mean": IF_NAME_MAP["<ab>_VolColoc_<ab2>_Mean"],
    "<ab>_Coloc<ab2>Mean": IF_NAME_MAP["<ab>_VolColoc_<ab2>_Mean"],
    "<ab>_Coloc_<ab2>_Count": IF_NAME_MAP["<ab>_VolColoc_<ab2>_Count"],
    "<ab>_Coloc_<ab2>_CountRaw": IF_NAME_MAP["<ab>_VolColoc_<ab2>_CountRaw"],
    "<ab>_Coloc_<ab2>_Count%": IF_NAME_MAP["<ab>_VolColoc_<ab2>_Count%"],
    "<ab>_Contains_<ab2>_Count": IF_NAME_MAP["<ab>_VolContains_<ab2>_Count"],
    "<ab>_Contains_<ab2>_CountRaw": IF_NAME_MAP["<ab>_VolContains_<ab2>_CountRaw"],
    "<ab>_Contains_<ab2>_Count%": IF_NAME_MAP["<ab>_VolContains_<ab2>_Count%"],
    "<ab>_Any_<ab2>_Count": IF_NAME_MAP["<ab>_VolAny_<ab2>_Count"],
    "<ab>_Any_<ab2>_CountRaw": IF_NAME_MAP["<ab>_VolAny_<ab2>_CountRaw"],
    "<ab>_Any_<ab2>_Count%": IF_NAME_MAP["<ab>_VolAny_<ab2>_Count%"],
    "<ab>_NumColoc_<ab2>Mean": IF_NAME_MAP["<ab>_VolNumColoc_<ab2>Mean"],
})

RAW_NAME_MAP.update({
    "<ab>_Coloc_<ab2>": RAW_NAME_MAP["<ab>_VolColoc_<ab2>"],
    "<ab>_Coloc<ab2>": RAW_NAME_MAP["<ab>_VolColoc_<ab2>"],
    "<ab>_ColocCount<ab2>": RAW_NAME_MAP["<ab>_VolColocCount<ab2>"],
    "<ab>_NumColoc_<ab2>": RAW_NAME_MAP["<ab>_VolNumColoc_<ab2>"],
    "<ab>_Contains_<ab2>": RAW_NAME_MAP["<ab>_VolContains_<ab2>"],
    "<ab>_Any_<ab2>": RAW_NAME_MAP["<ab>_VolAny_<ab2>"],
})

# ── Pattern matching ───────────────────────────────────────────────────

def _pattern_to_regex(pattern):
    s = re.escape(pattern)
    s = s.replace(r"<ab>", r"(?P<ab>[A-Za-z0-9_-]+)")
    s = s.replace(r"<ab2>", r"(?P<ab2>[A-Za-z0-9_-]+)")
    return re.compile(f"^{s}$")


EXCEL_MAX = 31
_EXP_SUFFIX_RE = re.compile(r"\.exp(\d+)$")
_COMBO_METRIC_RE = re.compile(
    r"^(?P<ab>.+?)_"
    r"(?P<family>VolComboAny|VolCombo|CPCComboAny|CPCCombo)_"
    r"(?P<state>.+?)_"
    r"(?P<metric>CountRaw|Count|IntDenTotal|MeanIntDen|burdenScore|fragmentationScore)$"
)
_COMPACT_SHEET_RULES = [
    (
        re.compile(r"^(?P<ab>.+?)_CPCColoc_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawCPCColoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_CPCColoc_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} CPCColoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_CPCColoc_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} CPCColoc {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_CPCContains_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawCPCCont {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_CPCContains_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} CPCCont {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_CPCContains_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} CPCCont {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_CPCAny_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawCPCAssoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_CPCAny_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} CPCAssoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_CPCAny_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} CPCAssoc {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolColoc_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawVolColoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolColoc_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} VolColoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolColoc_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} VolColoc {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolContains_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawVolCont {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolContains_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} VolCont {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolContains_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} VolCont {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolAny_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawVolAssoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolAny_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} VolAssoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_VolAny_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} VolAssoc {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Coloc_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawVolColoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Coloc_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} VolColoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Coloc_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} VolColoc {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Contains_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawVolCont {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Contains_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} VolCont {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Contains_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} VolCont {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Any_(?P<ab2>.+?)_CountRaw$"),
        lambda g: f"{g['ab']} RawVolAssoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Any_(?P<ab2>.+?)_Count%$"),
        lambda g: f"%{g['ab']} VolAssoc {g['ab2']}",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_Any_(?P<ab2>.+?)_Count$"),
        lambda g: f"{g['ab']} VolAssoc {g['ab2']} Dens",
    ),
    (
        re.compile(r"^(?P<ab>.+?)_IntDenTotal$"),
        lambda g: f"{g['ab']} IntDenDens",
    ),
]

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


def _abbrev_combo_token(token: str, body_len: int) -> str:
    token_s = str(token)
    prefix = "w" if token_s.startswith("w") else ""
    suffix = "+" if token_s.endswith("+") else ""
    body = token_s[1:] if prefix else token_s
    body = body[:-1] if suffix else body
    body = body[:body_len] if len(body) > body_len else body
    return f"{prefix}{body}{suffix}"


def _compact_combo_state(state: str, budget: int | None = None) -> str:
    state_s = str(state)
    if state_s == "None":
        return "None"

    tokens = [str(t) for t in state_s.split("_") if str(t)]
    trials = [
        ",".join(tokens),
        ",".join(_abbrev_combo_token(t, 4) for t in tokens),
        ",".join(_abbrev_combo_token(t, 3) for t in tokens),
        "".join(_abbrev_combo_token(t, 3) for t in tokens),
        "".join(_abbrev_combo_token(t, 2) for t in tokens),
    ]

    if budget is None:
        return trials[0]
    for trial in trials:
        if len(trial) <= budget:
            return trial
    return trials[-1][:budget]


def _combo_metric_label(metric: str) -> str:
    return {
        "Count": "Dens",
        "CountRaw": "RawCount",
        "IntDenTotal": "IntDen",
        "MeanIntDen": "MeanPxIntDen",
        "burdenScore": "Burden",
        "fragmentationScore": "Frag",
    }.get(str(metric), str(metric))


def _combo_family_label(family: str) -> str:
    return {
        "VolCombo": "VCmb",
        "CPCCombo": "CCmb",
        "VolComboAny": "VAny",
        "CPCComboAny": "CAny",
    }.get(str(family), str(family))


def _combo_family_desc(family: str) -> str:
    return {
        "VolCombo": "detailed volumetric combo subset",
        "CPCCombo": "detailed CPC combo subset",
        "VolComboAny": "pooled volumetric Any combo subset",
        "CPCComboAny": "pooled CPC Any combo subset",
    }.get(str(family), "combo subset")


def _combo_state_desc(state: str) -> str:
    state_s = str(state)
    if state_s == "None":
        return "no coloc-positive or contains/with partner-marker state"

    parts = []
    for token in state_s.split("_"):
        token_s = str(token)
        if token_s.endswith("+"):
            parts.append(f"{token_s[:-1]} coloc-positive")
        elif token_s.startswith("w"):
            parts.append(f"contains/with {token_s[1:]}")
        else:
            parts.append(token_s)
    return ", ".join(parts)


def _combo_description(ab: str, family: str, state: str, metric: str) -> str:
    marker = str(ab)
    family_desc = _combo_family_desc(family)
    state_desc = _combo_state_desc(state)
    notation = 'Combo notation: "marker+" = coloc-positive, "wMarker" = contains/with marker.'

    if metric == "Count":
        return (
            f"{_OBJ_COUNTER}"
            f"The number of segmented {marker} objects in the {family_desc} "
            f"state ({state_desc}) was summed and {_PER_VOL}.\n"
            f"{notation}"
        )
    if metric == "CountRaw":
        return (
            f"{_OBJ_COUNTER}"
            f"The number of segmented {marker} objects in the {family_desc} "
            f"state ({state_desc}) was summed and averaged across sections "
            f"before tissue-volume normalization.\n"
            f"{notation}"
        )
    if metric == "IntDenTotal":
        return (
            f"{_OBJ_COUNTER}"
            f"The total integrated density of segmented {marker} objects in "
            f"the {family_desc} state ({state_desc}) was summed and {_PER_VOL}.\n"
            f"{notation}"
        )
    if metric == "MeanIntDen":
        return (
            f"{_OBJ_COUNTER}"
            f"The mean per-object pixel integrated density of segmented {marker} "
            f"objects in the {family_desc} state ({state_desc}) {_QUANTIFIED}.\n"
            f"{notation}"
        )
    if metric == "burdenScore":
        return (
            f"Composite burden score computed only across segmented {marker} "
            f"objects in the {family_desc} state ({state_desc}).\n"
            f"{notation}"
        )
    if metric == "fragmentationScore":
        return (
            f"Composite fragmentation score computed only across segmented {marker} "
            f"objects in the {family_desc} state ({state_desc}).\n"
            f"{notation}"
        )
    return f"{family_desc} state ({state_desc}) for {marker}."


def convert_summary_sheet_name(colname: str):
    label, desc = convert_name(colname, truncate=False)
    base, exp_tag = _strip_exp_suffix(str(colname))

    combo_match = _COMBO_METRIC_RE.match(base)
    if combo_match is not None:
        groups = combo_match.groupdict()
        family_label = _combo_family_label(groups["family"])
        metric_label = _combo_metric_label(groups["metric"])
        state_label = _compact_combo_state(groups["state"])
        compact = f"{groups['ab']} {family_label} {state_label} {metric_label}".strip()
        if len(compact) > EXCEL_MAX:
            budget = max(4, EXCEL_MAX - len(f"{groups['ab']} {family_label}  {metric_label}"))
            state_label = _compact_combo_state(groups["state"], budget=budget)
            compact = f"{groups['ab']} {family_label} {state_label} {metric_label}".strip()
        if len(compact) > EXCEL_MAX:
            marker_short = _abbrev_combo_token(groups["ab"], 4)
            budget = max(4, EXCEL_MAX - len(f"{marker_short} {family_label}  {metric_label}"))
            state_label = _compact_combo_state(groups["state"], budget=budget)
            compact = f"{marker_short} {family_label} {state_label} {metric_label}".strip()
        label = compact
        desc = _combo_description(
            groups["ab"],
            groups["family"],
            groups["state"],
            groups["metric"],
        )
    else:
        for rx, formatter in _COMPACT_SHEET_RULES:
            m = rx.match(base)
            if m is not None:
                label = formatter(m.groupdict())
                break

    if exp_tag:
        label = f"{label} ({exp_tag.lstrip('.')})"
    return label, desc

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
    if "_VolComboAny_" in base:
        return base.split("_VolComboAny_", 1)[0]
    if "_VolCombo_" in base:
        return base.split("_VolCombo_", 1)[0]
    if "_CPCComboAny_" in base:
        return base.split("_CPCComboAny_", 1)[0]
    if "_CPCCombo_" in base:
        return base.split("_CPCCombo_", 1)[0]
    if "_ComboAny_" in base:
        return base.split("_ComboAny_", 1)[0]
    if "_Combo_" in base:
        return base.split("_Combo_", 1)[0]

    groups = _groups_for_column(colname)
    marker = groups.get("ab")
    if marker:
        return normalize_marker_name(marker)
    raise KeyError(colname)


def _exp_rank_for_column(colname: str) -> int:
    _base, exp_tag = _strip_exp_suffix(str(colname))
    if not exp_tag:
        return 0
    try:
        return int(exp_tag.lstrip(".exp"))
    except ValueError:
        return 0


def _summary_metric_sort_key(base: str):
    combo_match = _COMBO_METRIC_RE.match(base)
    if combo_match is not None:
        family_rank = {
            "VolCombo": 0,
            "CPCCombo": 1,
            "VolComboAny": 2,
            "CPCComboAny": 3,
        }.get(combo_match.group("family"), 9)
        metric_rank = {
            "Count": 0,
            "CountRaw": 1,
            "IntDenTotal": 2,
            "MeanIntDen": 3,
            "burdenScore": 4,
            "fragmentationScore": 5,
        }.get(combo_match.group("metric"), 9)
        return (5, family_rank, metric_rank, combo_match.group("state"))

    if base.endswith("_burdenScore"):
        return (4, 0, 0, "")
    if base.endswith("_fragmentationScore"):
        return (4, 1, 0, "")

    quant_order = [
        ("_Count", 0),
        ("_CountRaw", 1),
        ("_IntDenTotal", 2),
        ("_VolumeTotal", 3),
        ("_SurfaceTotal", 4),
        ("_IntDenMean", 5),
        ("_MeanIntDenMean", 6),
        ("_VolumeMean", 7),
        ("_SurfaceMean", 8),
        ("_SAtoVolumeRatioMean", 9),
        ("_ROI_IntDenMean", 10),
        ("_ROI_%AreaMean", 11),
    ]
    if not any(
        token in base
        for token in (
            "_VolColoc_",
            "_VolContains_",
            "_VolAny_",
            "_CPCColoc_",
            "_CPCContains_",
            "_CPCAny_",
            "_Coloc_",
            "_Contains_",
            "_Any_",
        )
    ):
        for suffix, rank in quant_order:
            if base.endswith(suffix):
                return (0, rank, 0, "")

    if base.endswith("_RawXMMean"):
        return (1, 0, 0, "")
    if base.endswith("_RawYMMean"):
        return (1, 1, 0, "")
    if "_DistToClosest_" in base:
        return (1, 2, 0, base.split("_DistToClosest_", 1)[1].removesuffix("Mean"))
    if base.endswith("_DistToVentricle"):
        return (1, 3, 0, "")

    family_rules = [
        ("_VolColoc_", "_Mean", 0),
        ("_CPCColoc_", "_Mean", 1),
        ("_VolColoc_", "_Count", 2),
        ("_VolColoc_", "_CountRaw", 3),
        ("_VolColoc_", "_Count%", 4),
        ("_VolContains_", "_Count", 5),
        ("_VolContains_", "_CountRaw", 6),
        ("_VolContains_", "_Count%", 7),
        ("_VolAny_", "_Count", 8),
        ("_VolAny_", "_CountRaw", 9),
        ("_VolAny_", "_Count%", 10),
        ("_CPCColoc_", "_Count", 11),
        ("_CPCColoc_", "_CountRaw", 12),
        ("_CPCColoc_", "_Count%", 13),
        ("_CPCContains_", "_Count", 14),
        ("_CPCContains_", "_CountRaw", 15),
        ("_CPCContains_", "_Count%", 16),
        ("_CPCAny_", "_Count", 17),
        ("_CPCAny_", "_CountRaw", 18),
        ("_CPCAny_", "_Count%", 19),
        ("_Coloc_", "_Mean", 20),
        ("_Coloc_", "_Count", 21),
        ("_Coloc_", "_CountRaw", 22),
        ("_Coloc_", "_Count%", 23),
        ("_Contains_", "_Count", 24),
        ("_Contains_", "_CountRaw", 25),
        ("_Contains_", "_Count%", 26),
        ("_Any_", "_Count", 27),
        ("_Any_", "_CountRaw", 28),
        ("_Any_", "_Count%", 29),
        ("_NumColoc_", "Mean", 30),
        ("_VolNumColoc_", "Mean", 31),
    ]
    for token, suffix, rank in family_rules:
        if token in base and base.endswith(suffix):
            target = base.split(token, 1)[1].removesuffix(suffix).strip("_")
            return (2, rank, 0, target)

    return (3, 99, 0, base)


def sort_if_summary_columns(columns):
    cols = [str(col) for col in columns]
    marker_order = {}
    for col in cols:
        try:
            marker = _summary_marker_for_column(col)
        except KeyError:
            marker = str(col)
        if marker not in marker_order:
            marker_order[marker] = len(marker_order)

    def _key(col: str):
        base, _exp_tag = _strip_exp_suffix(col)
        try:
            marker = _summary_marker_for_column(col)
        except KeyError:
            marker = col
        return (
            marker_order.get(marker, len(marker_order)),
            _exp_rank_for_column(col),
            *_summary_metric_sort_key(base),
            col,
        )

    return sorted(cols, key=_key)

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
    visible_order = None if visible_columns is None else {str(col): idx for idx, col in enumerate(visible_columns)}
    visible_set = None if visible_columns is None else set(visible_order)

    for exp_idx, exp in enumerate(experiment_list, start=1):
        exp_name = f"Experiment {exp_idx}"
        base_path = Path(exp.filePath)
        bucket = {}

        summary_cols = [str(col) for col in exp.summary.columns]
        if visible_order is not None:
            def _visible_rank(col_s: str):
                return min(
                    visible_order.get(col_s, float("inf")),
                    visible_order.get(f"{col_s}.exp{exp_idx}", float("inf")),
                )
            summary_cols = sorted(summary_cols, key=_visible_rank)

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
                bucket[key] = {"labels": [], "seen_labels": set(), "filter": "", "analysis": ""}

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

            if label not in bucket[key]["seen_labels"]:
                bucket[key]["seen_labels"].add(label)
                bucket[key]["labels"].append(label)


        for (marker, analysis), info in bucket.items():
            rows.append({
                "Experiment": exp_name,
                "Marker": marker,
                "Analysis": analysis,
                "Data": ", ".join(info['labels']),
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
