import pytest
import pandas as pd

from IF_analysis import plotting
from IF_analysis.batch import Batch
from IF_analysis.conditions import condition, conditionList
from IF_analysis.config import Config
from IF_analysis.experiment import Experiment, _standardize_csv_columns
from IF_analysis.export import convert_name, convert_raw_name, format_summary_for_display
from IF_analysis.markers import Antibody, Attribute, objectMarker


def _build_summary_test_experiment():
    exp = Experiment("toy", ".")

    dapi_df = pd.DataFrame([
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 0.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 1.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN2",
            "Hemisphere": "RH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 0.0,
            "YM": 1.0,
            "ZM": 1.0,
        },
    ])
    roi_props_df = pd.DataFrame([
        {"Animal Name": "Mouse1", "Region": "SCN1", "ROI": "SCN", "Area (um^2)": 1000.0},
        {"Animal Name": "Mouse1", "Region": "SCN2", "ROI": "SCN", "Area (um^2)": 1000.0},
    ])

    exp.data = {
        "DAPI": objectMarker("DAPI", dapi_df, exp, "blue"),
        "ROI Properties": Attribute("ROI Properties", roi_props_df, exp),
    }
    exp.createSummary(progress=False)
    return exp


def _build_summary_test_experiment_with_explicit_roi_volume():
    exp = Experiment("toy_new", ".")

    dapi_df = pd.DataFrame([
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 0.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN2",
            "Hemisphere": "RH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 1.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
    ])
    roi_props_df = pd.DataFrame([
        {
            "Animal Name": "Mouse1",
            "Region": "SCN1",
            "Area (um^2)": 1000.0,
            "Volume (micron^3)": 2000.0,
            "Volume (mm^3)": 0.000002,
            "ROI": "SCN",
        },
        {
            "Animal Name": "Mouse1",
            "Region": "SCN2",
            "Area (um^2)": 1000.0,
            "Volume (micron^3)": 2000.0,
            "Volume (mm^3)": 0.000002,
            "ROI": "SCN",
        },
    ])

    exp.data = {
        "DAPI": objectMarker("DAPI", dapi_df, exp, "blue"),
        "ROI Properties": Attribute("ROI Properties", roi_props_df, exp),
    }
    exp.createSummary(progress=False)
    return exp


def _build_any_combo_test_experiment():
    exp = Experiment("toy_any_combo", ".")

    dapi_df = pd.DataFrame([
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 0.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 1.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 2.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 3.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
    ])
    roi_props_df = pd.DataFrame([
        {"Animal Name": "Mouse1", "Region": "SCN1", "ROI": "SCN", "Area (um^2)": 1000.0},
    ])

    exp.data = {
        "DAPI": objectMarker("DAPI", dapi_df, exp, "blue"),
        "ROI Properties": Attribute("ROI Properties", roi_props_df, exp),
    }

    dapi = exp.data["DAPI"]
    dapi.df["DAPI_ColocCountGFAP"] = [1, 0, 1, 0]
    dapi.df["DAPI_Contains_GFAP"] = [0, 1, 1, 0]
    dapi.df["DAPI_ColocCountmCherry"] = [0, 1, 0, 0]
    dapi.df["DAPI_Contains_mCherry"] = [0, 0, 1, 0]

    exp.createSummary(progress=False)
    return exp


def _build_coloc_mean_summary_test_experiment():
    exp = Experiment("toy_coloc_mean", ".")

    dapi_df = pd.DataFrame([
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 0.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 1.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 2.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "ROI": "SCN",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 1,
            "Mean": 1,
            "XM": 3.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
    ])
    roi_props_df = pd.DataFrame([
        {"Animal Name": "Mouse1", "Region": "SCN1", "ROI": "SCN", "Area (um^2)": 1000.0},
    ])

    exp.data = {
        "DAPI": objectMarker("DAPI", dapi_df, exp, "blue"),
        "ROI Properties": Attribute("ROI Properties", roi_props_df, exp),
    }

    dapi = exp.data["DAPI"]
    dapi.df["DAPI_Coloc_GFAP"] = [10.0, 20.0, 30.0, 40.0]
    dapi.df["DAPI_Coloc_mCherry"] = [0.0, 50.0, 100.0, 25.0]

    exp.createSummary(progress=False)
    return exp


def test_experiment_summary_includes_count_raw_before_area_adjustment():
    exp = _build_summary_test_experiment()
    summary = exp.summary
    expected_volume_um3 = 1000.0 * Config.SECTION_THICKNESS_UM
    expected_volume_0p1mm3 = expected_volume_um3 / 100000000.0
    expected_factor = 1.0 / expected_volume_0p1mm3

    assert "DAPI_CountRaw" in summary.columns
    assert summary.loc[0, "DAPI_CountRaw"] == pytest.approx(1.5)
    assert summary.loc[0, "ROI_Area"] == pytest.approx(1000.0)
    assert summary.loc[0, "ROI_Thickness"] == pytest.approx(Config.SECTION_THICKNESS_UM)
    assert summary.loc[0, "ROI_Volume"] == pytest.approx(expected_volume_um3)
    assert summary.loc[0, "Volume0p1mm3"] == pytest.approx(expected_volume_0p1mm3)
    assert summary.loc[0, "CountNormFactor"] == pytest.approx(expected_factor)
    assert summary.loc[0, "DAPI_Count"] == pytest.approx(1.5 * expected_factor)


def test_explicit_roi_volume_is_preferred_over_area_thickness_fallback():
    exp = _build_summary_test_experiment_with_explicit_roi_volume()
    summary = exp.summary

    expected_volume_um3 = 2000.0
    expected_volume_0p1mm3 = expected_volume_um3 / 100000000.0
    expected_factor = 1.0 / expected_volume_0p1mm3

    assert summary.loc[0, "ROI_Area"] == pytest.approx(1000.0)
    assert summary.loc[0, "ROI_Volume"] == pytest.approx(expected_volume_um3)
    assert summary.loc[0, "ROI_Thickness"] == pytest.approx(2.0)
    assert summary.loc[0, "CountNormFactor"] == pytest.approx(expected_factor)
    assert summary.loc[0, "DAPI_CountRaw"] == pytest.approx(1.0)
    assert summary.loc[0, "DAPI_Count"] == pytest.approx(expected_factor)


def test_legacy_roi_source_columns_are_preserved_for_backward_compatibility():
    exp = _build_summary_test_experiment()
    summary = exp.summary

    assert "Area(um^2)Mean" in summary.columns
    assert summary.loc[0, "Area(um^2)Mean"] == pytest.approx(1000.0)
    assert summary.loc[0, "ROI_Area"] == pytest.approx(summary.loc[0, "Area(um^2)Mean"])


def test_explicit_volume_source_columns_are_preserved_for_backward_compatibility():
    exp = _build_summary_test_experiment_with_explicit_roi_volume()
    summary = exp.summary

    assert "Area(um^2)Mean" in summary.columns
    assert "VolumeMean" in summary.columns
    assert "Volume(mm^3)Mean" in summary.columns
    assert summary.loc[0, "Area(um^2)Mean"] == pytest.approx(1000.0)
    assert summary.loc[0, "VolumeMean"] == pytest.approx(2000.0)
    assert summary.loc[0, "Volume(mm^3)Mean"] == pytest.approx(0.000002)
    assert summary.loc[0, "ROI_Volume"] == pytest.approx(summary.loc[0, "VolumeMean"])


def test_legacy_roi_intensity_columns_survive_with_new_format_object_tables():
    exp = Experiment("toy_mixed_formats", ".")

    object_df = pd.DataFrame([
        {
            "Region": "SCN1",
            "Hemisphere": "LH",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 5,
            "IntDen": 2,
            "Mean": 1,
            "XM": 0.0,
            "YM": 0.0,
            "ZM": 1.0,
        },
        {
            "Region": "SCN2",
            "Hemisphere": "RH",
            "Animal Name": "Mouse1",
            "Volume (micron^3)": 12,
            "Surface (micron^2)": 6,
            "IntDen": 3,
            "Mean": 1.5,
            "XM": 1.0,
            "YM": 1.0,
            "ZM": 1.0,
        },
    ])
    legacy_roi_intensity_df = pd.DataFrame([
        {"SCN": 1, "Animal Name": "Mouse1", "IntDen": 100.0, "%Area": 10.0},
        {"SCN": 2, "Animal Name": "Mouse1", "IntDen": 150.0, "%Area": 12.0},
    ])
    roi_props_df = pd.DataFrame([
        {"Animal Name": "Mouse1", "Region": "SCN1", "ROI": "SCN", "Area (um^2)": 1000.0},
        {"Animal Name": "Mouse1", "Region": "SCN2", "ROI": "SCN", "Area (um^2)": 1000.0},
    ])

    exp.data = {
        "ROI Properties": Attribute(
            "ROI Properties",
            _standardize_csv_columns(roi_props_df),
            exp,
        )
    }
    exp.data["Iba1"] = objectMarker(
        "Iba1",
        _standardize_csv_columns(object_df),
        exp,
        "cyan",
    )
    exp.data["Iba1_ROI"] = Antibody(
        "Iba1_ROI",
        _standardize_csv_columns(legacy_roi_intensity_df),
        exp,
    )

    exp.createSummary(progress=False)
    summary = exp.summary

    assert "Iba1_ROI_IntDenMean" in summary.columns
    assert "Iba1_ROI_%AreaMean" in summary.columns
    assert summary.loc[0, "Iba1_ROI_IntDenMean"] == pytest.approx(125.0)
    assert summary.loc[0, "Iba1_ROI_%AreaMean"] == pytest.approx(11.0)


def test_batch_summary_preserves_count_raw_columns():
    exp = _build_summary_test_experiment()
    conds = conditionList([condition("Mouse", "Mouse", "#000000", "Group")])
    batch = Batch("toy_batch", [exp], conds, ".")
    batch._create_batch_summary()

    assert "DAPI_CountRaw" in batch.summary.columns
    assert "ROI_Volume" in batch.summary.columns
    assert "ROI_Area" in batch.summary.columns
    assert "ROI_Thickness" in batch.summary.columns
    assert "CountNormFactor" in batch.summary.columns
    assert batch.summary.loc[0, "DAPI_CountRaw"] == pytest.approx(1.5)


def test_experiment_summary_builds_any_and_comboany_columns():
    exp = _build_any_combo_test_experiment()
    summary = exp.summary
    raw_df = exp.data["DAPI"].df
    expected_volume_um3 = 1000.0 * Config.SECTION_THICKNESS_UM
    expected_volume_0p1mm3 = expected_volume_um3 / 100000000.0
    expected_factor = 1.0 / expected_volume_0p1mm3

    assert raw_df["DAPI_Any_GFAP"].tolist() == [1, 1, 1, 0]
    assert raw_df["DAPI_Any_mCherry"].tolist() == [0, 1, 1, 0]
    assert raw_df["DAPI_ComboAny_GFAP+"].tolist() == [1, 0, 0, 0]
    assert raw_df["DAPI_ComboAny_GFAP+_mCherry+"].tolist() == [0, 1, 1, 0]
    assert raw_df["DAPI_ComboAny_None"].tolist() == [0, 0, 0, 1]

    assert "DAPI_Coloc_GFAP_Count" in summary.columns
    assert "DAPI_Coloc_GFAP_CountRaw" in summary.columns
    assert "DAPI_Coloc_GFAP_Count%" in summary.columns
    assert "DAPI_Contains_GFAP_Count" in summary.columns
    assert "DAPI_Contains_GFAP_CountRaw" in summary.columns
    assert "DAPI_Contains_GFAP_Count%" in summary.columns
    assert "DAPI_ColocCountGFAP" not in summary.columns
    assert "DAPI_Contains_GFAPMean" not in summary.columns

    assert summary.loc[0, "DAPI_Coloc_GFAP_CountRaw"] == pytest.approx(2.0)
    assert summary.loc[0, "DAPI_Coloc_mCherry_CountRaw"] == pytest.approx(1.0)
    assert summary.loc[0, "DAPI_Contains_GFAP_CountRaw"] == pytest.approx(2.0)
    assert summary.loc[0, "DAPI_Contains_mCherry_CountRaw"] == pytest.approx(1.0)
    assert summary.loc[0, "DAPI_Coloc_GFAP_Count"] == pytest.approx(2.0 * expected_factor)
    assert summary.loc[0, "DAPI_Coloc_mCherry_Count"] == pytest.approx(1.0 * expected_factor)
    assert summary.loc[0, "DAPI_Contains_GFAP_Count"] == pytest.approx(2.0 * expected_factor)
    assert summary.loc[0, "DAPI_Contains_mCherry_Count"] == pytest.approx(1.0 * expected_factor)
    assert summary.loc[0, "DAPI_Coloc_GFAP_Count%"] == pytest.approx(50.0)
    assert summary.loc[0, "DAPI_Coloc_mCherry_Count%"] == pytest.approx(25.0)
    assert summary.loc[0, "DAPI_Contains_GFAP_Count%"] == pytest.approx(50.0)
    assert summary.loc[0, "DAPI_Contains_mCherry_Count%"] == pytest.approx(25.0)

    assert summary.loc[0, "DAPI_Any_GFAP_CountRaw"] == pytest.approx(3.0)
    assert summary.loc[0, "DAPI_Any_mCherry_CountRaw"] == pytest.approx(2.0)
    assert summary.loc[0, "DAPI_Any_GFAP_Count"] == pytest.approx(3.0 * expected_factor)
    assert summary.loc[0, "DAPI_Any_mCherry_Count"] == pytest.approx(2.0 * expected_factor)
    assert summary.loc[0, "DAPI_Any_GFAP_Count%"] == pytest.approx(75.0)
    assert summary.loc[0, "DAPI_Any_mCherry_Count%"] == pytest.approx(50.0)
    assert summary.loc[0, "DAPI_ComboAny_GFAP+_Count%"] == pytest.approx(25.0)
    assert summary.loc[0, "DAPI_ComboAny_GFAP+_mCherry+_Count%"] == pytest.approx(50.0)
    assert summary.loc[0, "DAPI_ComboAny_None_Count%"] == pytest.approx(25.0)
    assert summary.loc[0, [
        "DAPI_ComboAny_GFAP+_Count%",
        "DAPI_ComboAny_GFAP+_mCherry+_Count%",
        "DAPI_ComboAny_None_Count%",
    ]].sum() == pytest.approx(100.0)


def test_batch_summary_preserves_any_and_comboany_columns():
    exp = _build_any_combo_test_experiment()
    conds = conditionList([condition("Mouse", "Mouse", "#000000", "Group")])
    batch = Batch("toy_batch_any", [exp], conds, ".")
    batch._create_batch_summary()
    expected_volume_um3 = 1000.0 * Config.SECTION_THICKNESS_UM
    expected_volume_0p1mm3 = expected_volume_um3 / 100000000.0
    expected_factor = 1.0 / expected_volume_0p1mm3

    assert "DAPI_Coloc_GFAP_Count" in batch.summary.columns
    assert "DAPI_Coloc_GFAP_CountRaw" in batch.summary.columns
    assert "DAPI_Coloc_GFAP_Count%" in batch.summary.columns
    assert "DAPI_Contains_GFAP_Count" in batch.summary.columns
    assert "DAPI_Contains_GFAP_CountRaw" in batch.summary.columns
    assert "DAPI_Contains_GFAP_Count%" in batch.summary.columns
    assert "DAPI_Any_GFAP_Count" in batch.summary.columns
    assert "DAPI_Any_GFAP_Count%" in batch.summary.columns
    assert "DAPI_Any_GFAP_CountRaw" in batch.summary.columns
    assert "DAPI_ComboAny_None_Count%" in batch.summary.columns
    assert batch.summary.loc[0, "DAPI_Coloc_GFAP_CountRaw"] == pytest.approx(2.0)
    assert batch.summary.loc[0, "DAPI_Coloc_GFAP_Count"] == pytest.approx(2.0 * expected_factor)
    assert batch.summary.loc[0, "DAPI_Coloc_GFAP_Count%"] == pytest.approx(50.0)
    assert batch.summary.loc[0, "DAPI_Contains_GFAP_CountRaw"] == pytest.approx(2.0)
    assert batch.summary.loc[0, "DAPI_Contains_GFAP_Count"] == pytest.approx(2.0 * expected_factor)
    assert batch.summary.loc[0, "DAPI_Contains_GFAP_Count%"] == pytest.approx(50.0)
    assert batch.summary.loc[0, "DAPI_Any_GFAP_CountRaw"] == pytest.approx(3.0)
    assert batch.summary.loc[0, "DAPI_Any_GFAP_Count"] == pytest.approx(3.0 * expected_factor)
    assert batch.summary.loc[0, "DAPI_Any_GFAP_Count%"] == pytest.approx(75.0)
    assert batch.summary.loc[0, "DAPI_ComboAny_None_Count%"] == pytest.approx(25.0)


def test_experiment_summary_refactors_coloc_overlap_mean_name():
    exp = _build_coloc_mean_summary_test_experiment()
    summary = exp.summary

    assert "DAPI_Coloc_GFAP_Mean" in summary.columns
    assert "DAPI_Coloc_mCherry_Mean" in summary.columns
    assert "DAPI_ColocGFAPMean" not in summary.columns
    assert "DAPI_ColocmCherryMean" not in summary.columns
    assert summary.loc[0, "DAPI_Coloc_GFAP_Mean"] == pytest.approx(25.0)
    assert summary.loc[0, "DAPI_Coloc_mCherry_Mean"] == pytest.approx(43.75)


def test_batch_summary_preserves_refactored_coloc_overlap_mean_name():
    exp = _build_coloc_mean_summary_test_experiment()
    conds = conditionList([condition("Mouse", "Mouse", "#000000", "Group")])
    batch = Batch("toy_batch_coloc_mean", [exp], conds, ".")
    batch._create_batch_summary()

    assert "DAPI_Coloc_GFAP_Mean" in batch.summary.columns
    assert "DAPI_ColocGFAPMean" not in batch.summary.columns
    assert batch.summary.loc[0, "DAPI_Coloc_GFAP_Mean"] == pytest.approx(25.0)


def test_export_and_plotting_accept_refactored_and_legacy_coloc_overlap_mean_names():
    new_label, new_desc = convert_name("DAPI_Coloc_GFAP_Mean", truncate=False)
    old_label, old_desc = convert_name("DAPI_ColocGFAPMean", truncate=False)
    assert new_label == old_label
    assert new_desc == old_desc

    display_summary = format_summary_for_display(
        pd.DataFrame({"DAPI_Coloc_GFAP_Mean": [25.0]})
    )
    assert "GFAP Overlap per DAPI" in display_summary.columns

    resolved = plotting._resolve_filtered_columns(
        type("ExperimentStub", (), {
            "summary": pd.DataFrame({"DAPI_Coloc_GFAP_Mean": [25.0]}),
        })(),
        filtered_columns=["DAPI_ColocGFAPMean"],
    )
    assert resolved == ["DAPI_Coloc_GFAP_Mean"]


def test_raw_coloc_exports_and_marker_x_resolution_use_canonical_name():
    new_label, new_desc = convert_raw_name("DAPI_Coloc_GFAP")
    old_label, old_desc = convert_raw_name("DAPI_ColocGFAP")
    assert new_label == old_label
    assert new_desc == old_desc

    experiment = type("ExperimentStub", (), {
        "data": {
            "DAPI": type("MarkerStub", (), {
                "df": pd.DataFrame({
                    "DAPI_Coloc_GFAP": [10.0, 20.0],
                    "DAPI_Volume": [1.0, 2.0],
                })
            })()
        }
    })()

    assert plotting._resolve_histogram_x_column(experiment, "DAPI", "Coloc_GFAP") == "DAPI_Coloc_GFAP"
    assert plotting._resolve_histogram_x_column(experiment, "DAPI", "ColocGFAP") == "DAPI_Coloc_GFAP"


def test_display_summary_helper_adds_unit_labels_without_mutating_schema():
    exp = _build_summary_test_experiment()
    conds = conditionList([condition("Mouse", "Mouse", "#000000", "Group")])
    batch = Batch("toy_batch", [exp], conds, ".")
    batch._create_batch_summary()

    display_summary = format_summary_for_display(exp.summary)
    exp_display_summary = exp.getDisplaySummary()
    batch_display_summary = batch.getDisplaySummary()

    assert "ROI_Area" in exp.summary.columns
    assert "ROI_Area" in batch.summary.columns
    assert "ROI Area (\u00b5m\u00b2)" in display_summary.columns
    assert "ROI Volume (\u00b5m\u00b3)" in exp_display_summary.columns
    assert "ROI Thickness (\u00b5m)" in batch_display_summary.columns
    assert display_summary.loc[0, "ROI Area (\u00b5m\u00b2)"] == pytest.approx(1000.0)
    assert exp_display_summary.loc[0, "ROI Volume (\u00b5m\u00b3)"] == pytest.approx(
        exp.summary.loc[0, "ROI_Volume"]
    )
