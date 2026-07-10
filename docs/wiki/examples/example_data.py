"""Synthetic example dataset for the PyFLASH wiki.

Builds ONE small, seeded, domain-neutral study that is rich enough to drive
every data-driven ``PyFLASH.plotting`` plot (26 of the 28 plot functions -- the
two image plots need real image files and are out of scope here).

The structure is deliberately *not* noise. Baked in are:

* a three-group design (``A`` control, ``B``, ``C``) with real group effects,
* inter-marker correlations whose *sign flips by group* (so matrix-difference
  plots have something to show),
* linear predictors ``x1``/``x2`` that jointly explain ``Signal`` (regression,
  multivariable, 3D scatter),
* a 24 h circadian rhythm with group-shifted acrophase (cosinor / clock),
* a longitudinal growth curve across timepoints (timecourse),
* per-object colocalisation and combo indicators (coloc UpSet / Sankey /
  combo pies).

Everything is generated from a single seed, so the dataset is reproducible.

Layers returned by :func:`build_example_data`:

* ``experiment`` -- a ``DataFrameExperiment`` with a subject-level ``.summary``
  (one row per subject) and a rich row-level marker table at
  ``.data["Marker1"]``. Drives the summary, distribution, matrix, regression,
  spatial and colocalisation plots.
* ``timecourse`` -- a long DataFrame (value vs ``Timepoint`` across groups) for
  :func:`PyFLASH.plotting.plot_timecourse`.
* ``cosinor`` -- a long DataFrame (value vs ``ZT`` time-of-day across groups) for
  :func:`PyFLASH.plotting.plot_cosinor`.

Usage::

    from example_data import build_example_data
    ex = build_example_data(fig_path="example_outputs")
    exp = ex.experiment
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from PyFLASH import from_dataframe

# ---------------------------------------------------------------------------
# Study design constants (domain-neutral vocabulary)
# ---------------------------------------------------------------------------
SEED = 20260710
GROUPS = ["A", "B", "C"]          # "A" is the control group
CONTROL = "A"
COHORTS = ["Cohort1", "Cohort2"]  # a second, crossed factor
MARKERS = ["Marker1", "Marker2", "Marker3"]
ROI_BASE = "ROIa"                 # neutral ROI family name (pass roi_base="ROIa")
N_PER_GROUP = 14                  # 42 subjects total
N_OBJECTS = 8                     # row-level objects per subject in .data["Marker1"]

# Per-group additive offsets applied to the subject-level marker metrics.
# Monotonic where useful so bars/volcano/forest read cleanly.
_GROUP_OFFSET = {
    "Marker1_Count":       {"A": 0.0, "B": 6.0,  "C": 12.0},
    "Marker1_IntDenMean":  {"A": 0.0, "B": 18.0, "C": -12.0},
    "Marker2_Count":       {"A": 0.0, "B": -4.0, "C": 3.0},
    "Marker2_IntDenMean":  {"A": 0.0, "B": 10.0, "C": 20.0},
    "Marker3_Count":       {"A": 0.0, "B": 2.5,  "C": -3.0},
    "Marker3_IntDenMean":  {"A": 0.0, "B": -8.0, "C": 6.0},
}
# Group-dependent coupling between Marker1_Count and Marker2_Count. The sign
# flips across groups, which is exactly what plot_matrix_differences visualises.
_M1_M2_COUPLING = {"A": 0.85, "B": 0.05, "C": -0.8}
# Group-shifted circadian acrophase (peak hour) and amplitude.
_ACROPHASE_MEAN = {"A": 6.0, "B": 10.0, "C": 15.0}
_AMPLITUDE_MEAN = {"A": 5.0, "B": 7.5, "C": 4.0}


@dataclass
class ExampleData:
    """Bundle of the synthetic study's tables and the wrapped experiment."""

    experiment: object            # DataFrameExperiment
    summary: pd.DataFrame         # one row per subject
    markers: pd.DataFrame         # row-level objects for Marker1 (.data["Marker1"])
    timecourse: pd.DataFrame      # long: Response vs Timepoint per group
    cosinor: pd.DataFrame         # long: Response vs ZT per group
    control: str = CONTROL
    roi_base: str = ROI_BASE
    groups: tuple = tuple(GROUPS)
    markers_list: tuple = tuple(MARKERS)


def _subject_frame(rng: np.random.Generator) -> pd.DataFrame:
    """One row per subject: group, crossed cohort factor, marker metrics,
    regression predictors/outcome, and per-subject rhythm parameters."""
    subjects, conds, cohorts = [], [], []
    for gi, g in enumerate(GROUPS):
        for k in range(N_PER_GROUP):
            subjects.append(f"S{gi * N_PER_GROUP + k + 1:02d}")
            conds.append(g)
            cohorts.append(COHORTS[k % 2])
    n = len(subjects)
    df = pd.DataFrame({"AnimalName": subjects, "Condition": conds, "Cohort": cohorts})

    # Shared latent per subject drives the Marker1/Marker2 coupling.
    latent = rng.normal(0.0, 1.0, n)
    off = lambda col: np.array([_GROUP_OFFSET[col][g] for g in conds])

    m1_count = 20.0 + off("Marker1_Count") + 4.0 * latent + rng.normal(0, 1.5, n)
    coupling = np.array([_M1_M2_COUPLING[g] for g in conds])
    m2_count = (14.0 + off("Marker2_Count")
                + coupling * 4.0 * latent + rng.normal(0, 1.5, n))

    latent2 = rng.normal(0.0, 1.0, n)
    m1_intden = 100.0 + off("Marker1_IntDenMean") + 8.0 * latent2 + rng.normal(0, 6, n)
    m2_intden = 80.0 + off("Marker2_IntDenMean") + 6.0 * latent2 + rng.normal(0, 6, n)
    m3_count = 8.0 + off("Marker3_Count") + rng.normal(0, 1.2, n)
    m3_intden = 60.0 + off("Marker3_IntDenMean") + rng.normal(0, 5, n)

    df["Marker1_Count"] = np.clip(m1_count, 0, None)
    df["Marker2_Count"] = np.clip(m2_count, 0, None)
    df["Marker3_Count"] = np.clip(m3_count, 0, None)
    df["Marker1_IntDenMean"] = np.clip(m1_intden, 0, None)
    df["Marker2_IntDenMean"] = np.clip(m2_intden, 0, None)
    df["Marker3_IntDenMean"] = np.clip(m3_intden, 0, None)

    # Regression predictors and a jointly-explained outcome.
    x1 = rng.normal(0, 1, n) + 0.4 * (np.array([GROUPS.index(g) for g in conds]))
    x2 = rng.normal(0, 1, n)
    signal = 2.0 * x1 + 1.2 * x2 + 0.5 * latent + rng.normal(0, 0.8, n)
    df["x1"] = x1
    df["x2"] = x2
    df["Signal"] = signal

    # Per-subject circadian summary parameters (for plot_acrophase_clock).
    acro = np.array([_ACROPHASE_MEAN[g] for g in conds]) + rng.normal(0, 1.2, n)
    df["Acrophase (h)"] = np.mod(acro, 24.0)
    amp = np.array([_AMPLITUDE_MEAN[g] for g in conds]) + rng.normal(0, 0.8, n)
    df["Amplitude"] = np.clip(amp, 0.1, None)
    return df


def _marker_frame(summary: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Row-level object table for Marker1: morphology, intensity, coordinates,
    colocalisation flags vs Marker2, and mutually-exclusive combo indicators."""
    rows = []
    # Per-group probabilities so coloc/combo plots show group structure.
    p_coloc = {"A": 0.25, "B": 0.55, "C": 0.8}
    p_contains = {"A": 0.1, "B": 0.3, "C": 0.6}
    combo_choices = ["None", "Marker2", "Marker3"]
    combo_p = {
        "A": [0.6, 0.25, 0.15],
        "B": [0.35, 0.45, 0.20],
        "C": [0.2, 0.35, 0.45],
    }
    for _, s in summary.iterrows():
        g = s["Condition"]
        vol_mean = 10.0 + {"A": 0.0, "B": 3.0, "C": 6.0}[g]
        for j in range(N_OBJECTS):
            vol = max(0.2, rng.normal(vol_mean, 2.2))
            intden = max(0.0, s["Marker1_IntDenMean"] + rng.normal(0, 12))
            # ROI-level count point (subject mean ~ summary Marker1_Count).
            count_pt = max(0.0, s["Marker1_Count"] / N_OBJECTS + rng.normal(0, 0.6))
            xm = rng.uniform(5, 95) + {"A": 0.0, "B": 5.0, "C": -5.0}[g]
            ym = rng.uniform(5, 95) + rng.normal(0, 3)
            coloc = int(rng.random() < p_coloc[g])
            contains = int(rng.random() < p_contains[g])
            closest = int(rng.random() < 0.5)
            combo = rng.choice(combo_choices, p=combo_p[g])
            rows.append({
                "AnimalName": s["AnimalName"],
                "Condition": g,
                "Cohort": s["Cohort"],
                "Region": f"{ROI_BASE}1",
                "ROI": ROI_BASE,
                "Marker1_Volume": vol,
                "Marker1_IntDen": intden,
                "Marker1_Count": count_pt,
                "Marker1_XM": np.clip(xm, 0, 100),
                "Marker1_YM": np.clip(ym, 0, 100),
                "Marker1_ColocCountMarker2": coloc,
                "Marker1_ClosestTo_Marker2": closest,
                "Marker1_Contains_Marker2": contains,
                "Marker1_VolComboAny_None": int(combo == "None"),
                "Marker1_VolComboAny_Marker2": int(combo == "Marker2"),
                "Marker1_VolComboAny_Marker3": int(combo == "Marker3"),
            })
    return pd.DataFrame(rows)


def _timecourse_frame(rng: np.random.Generator) -> pd.DataFrame:
    """Long growth-curve table: several subjects per (group, timepoint)."""
    timepoints = {"T1": 1, "T2": 2, "T3": 4, "T4": 8}
    reps = 5
    rows = []
    for g in GROUPS:
        base = {"A": 5.0, "B": 6.0, "C": 4.0}[g]
        slope = {"A": 0.8, "B": 1.8, "C": 1.1}[g]
        for tp, tval in timepoints.items():
            for r in range(reps):
                val = base + slope * tval + rng.normal(0, 0.9)
                rows.append({"AnimalName": f"{g}_tc{tval}_{r}", "Condition": g,
                             "Timepoint": tp, "Response": val})
    return pd.DataFrame(rows)


def _cosinor_frame(rng: np.random.Generator) -> pd.DataFrame:
    """Long circadian table: several samples per (group, ZT) over a 24 h cycle."""
    zts = [0, 4, 8, 12, 16, 20]
    reps = 5
    rows = []
    for g in GROUPS:
        mesor = 10.0
        amp = _AMPLITUDE_MEAN[g]
        acro = _ACROPHASE_MEAN[g]
        for zt in zts:
            for r in range(reps):
                val = mesor + amp * np.cos(2 * np.pi * (zt - acro) / 24.0) + rng.normal(0, 0.8)
                rows.append({"AnimalName": f"{g}_zt{zt}_{r}", "Condition": g,
                             "ZT": zt, "Response": val})
    return pd.DataFrame(rows)


def build_example_data(fig_path: str | None = None, seed: int = SEED) -> ExampleData:
    """Build the synthetic study.

    Parameters
    ----------
    fig_path:
        Optional output folder set on the experiment (``fig_path`` and
        ``data_path``) so plot functions can save figures. If ``None`` the
        experiment carries no output path and plots should be run with
        ``save=False``.
    seed:
        RNG seed for reproducibility.
    """
    rng = np.random.default_rng(seed)
    summary = _subject_frame(rng)
    markers = _marker_frame(summary, rng)
    timecourse = _timecourse_frame(rng)
    cosinor = _cosinor_frame(rng)

    kwargs = dict(
        group_col="Condition",
        subject_col="AnimalName",
        data={"Marker1": markers},
    )
    if fig_path is not None:
        kwargs["fig_path"] = fig_path
        kwargs["data_path"] = fig_path

    experiment = from_dataframe(summary, **kwargs)
    return ExampleData(
        experiment=experiment,
        summary=summary,
        markers=markers,
        timecourse=timecourse,
        cosinor=cosinor,
    )


if __name__ == "__main__":
    ex = build_example_data()
    print("subjects:", len(ex.summary), "| marker rows:", len(ex.markers))
    print("summary columns:", list(ex.summary.columns))
    print("marker columns:", list(ex.markers.columns))
    print("timecourse rows:", len(ex.timecourse), "| cosinor rows:", len(ex.cosinor))
    print("experiment:", type(ex.experiment).__name__)
