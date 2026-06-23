from PyFLASH.plotting import get_display_name


def test_plain_human_columns_do_not_use_if_roi_rewrites():
    assert get_display_name("Totalcounts", compact_per=True) == "Total counts"
    assert get_display_name("Volumeanterior-inferiorHT", compact_per=True) == "Volume anterior-inferior HT"

    total_label = get_display_name("Totalcounts", compact_per=True)
    volume_label = get_display_name("Volumeanterior-inferiorHT", compact_per=True)
    assert "ROI" not in total_label
    assert "0.1mm" not in volume_label


def test_structured_if_columns_keep_legacy_metric_labels():
    count_label = get_display_name("Iba1_Count", compact_per=True)
    volume_label = get_display_name("DAPI_VolumeTotal", compact_per=True)

    assert count_label.startswith("Iba1 Count")
    assert "0.1mm" in count_label
    assert volume_label.startswith("DAPI Volume")
    assert "0.1mm" in volume_label


def test_unmapped_structured_columns_still_get_if_fallback_labels():
    assert get_display_name("Iba1_ROI_%AreaMean", compact_per=True) == "Iba1 %Area"

    label = get_display_name("Marker_TotalCount", compact_per=True)
    assert label.startswith("Marker TotalCount")
    assert "0.1mm" in label
