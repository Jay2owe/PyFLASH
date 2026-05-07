"""Regression test: ROI Intensities CSVs with numeric week identifiers
(e.g. 'Week2') must be normalized to written-out form ('WeekTwo') so
they match the Objects/Attributes naming convention and condition system.
"""

import pandas as pd

from PyFLASH.experiment import _standardize_csv_columns


def _roi_csv(animal_names):
    """Build a minimal ROI Intensities–style DataFrame with old-format SCN column."""
    return pd.DataFrame({
        "Region": ["SCN"] * len(animal_names),
        "Hemisphere": ["RH"] * len(animal_names),
        "SCN": [1] * len(animal_names),
        "Animal Name": animal_names,
        "IntDen": [100.0] * len(animal_names),
        "%Area": [1.0] * len(animal_names),
        "RawIntDen": [200.0] * len(animal_names),
    })


def test_numeric_week_in_animal_name_normalized_to_word_form():
    """Bug: ROI Intensities CSVs had 'Week2' while Objects CSVs had 'WeekTwo'.
    The batch outer-join on AnimalName created duplicate rows — one with ROI data
    (NaN for Objects columns) and one with Objects data (NaN for ROI columns).
    Condition matching also failed because alpha-filtering 'Week2' yields 'Week',
    which doesn't contain 'WeekTwo'."""
    df = _roi_csv(["hAPP2Week2", "NLGF10Week8", "Syn1Week4"])
    result = _standardize_csv_columns(df)

    names = result["Animal Name"].tolist()
    assert names == ["hAPP2WeekTwo", "NLGF10WeekEight", "Syn1WeekFour"]


def test_already_normalized_week_names_unchanged():
    """Names already in written-out form must pass through without modification."""
    df = _roi_csv(["hAPP3WeekTwo", "NLGF5WeekFour", "Syn4WeekEight"])
    result = _standardize_csv_columns(df)

    names = result["Animal Name"].tolist()
    assert names == ["hAPP3WeekTwo", "NLGF5WeekFour", "Syn4WeekEight"]


def test_non_week_animal_names_unchanged():
    """Names without week identifiers (e.g. drug experiments) are untouched."""
    df = _roi_csv(["hAPPVeh1", "NLGFDrug5", "WTMa3"])
    result = _standardize_csv_columns(df)

    names = result["Animal Name"].tolist()
    assert names == ["hAPPVeh1", "NLGFDrug5", "WTMa3"]
