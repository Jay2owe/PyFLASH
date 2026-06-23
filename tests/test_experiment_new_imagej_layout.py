import os

import pandas as pd

from PyFLASH.experiment import Experiment, resolve_experiment_paths


def _write_csv(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _make_new_export(root):
    tables = os.path.join(root, "Results", "Tables")
    _write_csv(
        os.path.join(tables, "Objects", "GFAP.csv"),
        "\n".join([
            "Region,Atlas Key,Region ID,Region Acronym,Region Name,Hemisphere,ROI,Animal Name,SCN,Label,Volume (micron^3),Surface (micron^2),IntDen,Mean,XM,YM,ZM,Colocalisation with DAPI,GFAP_VolColoc30_DAPI,GFAP_CPCColoc_DAPI,GFAP_CPCContains_DAPI,GFAP_BBColoc_DAPI,run_id",
            "SCN,atlas,286,SCH,Suprachiasmatic nucleus,LH,SCN1,A1,1,1,10,20,100,5,2,3,1,35,1,1,0,12,run-1",
        ]),
    )
    _write_csv(
        os.path.join(tables, "Intensity", "GFAP.csv"),
        "\n".join([
            "Region,Atlas Key,Region ID,Region Acronym,Region Name,Hemisphere,ROI,Animal Name,z,IntDen,Intensity_EdgeCouplingIdx,run_id",
            "SCN,atlas,286,SCH,Suprachiasmatic nucleus,LH,SCN1,A1,1,200,'-0.4,run-1",
        ]),
    )
    _write_csv(
        os.path.join(tables, "Intensity", "GFAP_MIP.csv"),
        "\n".join([
            "Region,Hemisphere,ROI,Animal Name,z,Intensity_PatchinessCV50,GFAP_Pearson_DAPI,run_id",
            "SCN,LH,SCN1,A1,1,0.25,0.9,run-1",
        ]),
    )
    _write_csv(
        os.path.join(tables, "ROIs", "SCN ROI Properties.csv"),
        "\n".join([
            "Animal Name,Region,SCN,Area (pixel),Area (um^2),Volume (micron^3),Volume (mm^3),Width,Height,run_id",
            "A1,LHSCN,1,1000,100,1300,0.0000013,10,20,run-1",
        ]),
    )
    _write_csv(
        os.path.join(tables, "Project Summary", "3D Objects.csv"),
        "AnimalName,ShouldNotImport\nA1,999\n",
    )
    image_dir = os.path.join(root, "Results", "Presentation Images", "Images", "A1")
    os.makedirs(image_dir, exist_ok=True)
    with open(os.path.join(image_dir, "GFAP_LH_SCN.png"), "wb") as handle:
        handle.write(b"")
    return tables


def test_resolve_experiment_paths_accepts_new_results_tables(tmp_path):
    root = str(tmp_path / "FLASH")
    tables = _make_new_export(root)

    resolved = resolve_experiment_paths(root)

    assert resolved["data_path"] == tables
    assert resolved["root_path"] == root
    assert resolved["layout"] == "imagej-results"


def test_import_csvs_maps_new_layout_roles_and_columns(tmp_path):
    root = str(tmp_path / "FLASH")
    _make_new_export(root)

    exp = Experiment("new", root)
    exp.importCSVs(progress=False)

    assert {"GFAP", "GFAP_ROI", "GFAP_MIP_ROI", "SCN ROI Properties"}.issubset(exp.data)
    assert "3D Objects" not in exp.data

    gfap = exp.data["GFAP"].df.reset_index()
    assert gfap.loc[0, "Region"] == "SCN1"
    assert "GFAP_RegionID" not in gfap.columns
    assert "GFAP_run_id" not in gfap.columns
    assert "GFAP_VolColoc30_DAPI" not in gfap.columns
    assert "GFAP_BBColoc_DAPI" in gfap.columns
    assert "GFAP_CPCContains_DAPI" in gfap.columns

    intensity = exp.data["GFAP_ROI"].df.reset_index()
    assert intensity.loc[0, "Region"] == "SCN1"
    assert pd.to_numeric(intensity["GFAP_ROI_Intensity_EdgeCouplingIdx"]).iloc[0] == -0.4

    roi_props = exp.data["SCN ROI Properties"].df
    assert roi_props.loc[0, "Region"] == "SCN1"
    assert roi_props.loc[0, "Hemisphere"] == "LH"
    assert "SCN" not in roi_props.columns


def test_process_data_includes_new_intensity_metrics_without_project_summary(tmp_path):
    root = str(tmp_path / "FLASH")
    _make_new_export(root)

    exp = Experiment("new", root)
    exp.processData(import_images=True, progress=False)

    summary = exp.summaries["SCN"]
    assert "GFAP_ROI_Intensity_EdgeCouplingIdxMean" in summary.columns
    assert "GFAP_MIP_ROI_Intensity_PatchinessCV50Mean" in summary.columns
    assert "ShouldNotImport" not in "".join(summary.columns)
    assert exp.image_root == os.path.join(root, "Results", "Presentation Images", "Images")
    assert len(exp.images) == 1
