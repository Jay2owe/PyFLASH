import pandas as pd

from IF_analysis.experiment import _apply_roi_name_map, _normalize_region_key_series


def test_normalize_region_key_series_unifies_numeric_and_string_scn_labels():
    values = pd.Series([2.0, "2", "SCN2", "SCN2.0", "", None])
    out = _normalize_region_key_series(values).tolist()
    assert out == ["SCN2", "SCN2", "SCN2", "SCN2", "", ""]


def test_apply_roi_name_map_handles_mixed_region_dtypes():
    df = pd.DataFrame({
        "AnimalName": ["MouseA", "MouseB"],
        "Region": [2.0, 3.0],
        "Metric": [1, 2],
    })
    roi_name_map = pd.DataFrame({
        "AnimalName": ["MouseA", "MouseB"],
        "Region": ["SCN2", "SCN3"],
        "ImageROI": ["LHSCN2", "RHSCN3"],
    })

    out = _apply_roi_name_map(df, roi_name_map)

    assert out["ImageROI"].tolist() == ["LHSCN2", "RHSCN3"]
    assert out["Region"].tolist() == [2.0, 3.0]
