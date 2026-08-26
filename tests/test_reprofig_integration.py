from __future__ import annotations

import json
import sys
import types

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from reprofig import extract_record, formats as reprofig_formats, validate_svg  # noqa: E402
from PyFLASH import plotting, provenance, report  # noqa: E402
from PyFLASH.dataframe import from_dataframe  # noqa: E402
from PyFLASH.figure_record import build_pyflash_record  # noqa: E402
from PyFLASH.publication import extract_figure, publish_figures  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_report():
    report.collect()
    yield
    report.collect()


@pytest.fixture
def plot_module():
    module = types.ModuleType("PyFLASH.fake_reprofig_plot")
    source = '''
import types
import matplotlib.pyplot as plt
from PyFLASH import stats, utils


def plot_group(experiment, save_path, name, figure_profile="master",
               safe_columns=None, write_companion_csv=False):
    data = experiment.summary.copy()
    fig, ax = plt.subplots()
    groups = [
        data.loc[data["Condition"].eq(label), "value"]
        for label in ("control", "treated")
    ]
    ax.boxplot(groups)
    stats.multipleComparisons(
        experiment,
        groups,
        ax=ax,
        fig=fig,
        scatter=None,
        bar=None,
        draw=False,
        group_labels=["control", "treated"],
        comparisons=["1-2"],
        save_name="value",
    )
    utils.save_fig(
        fig,
        save_path,
        name,
        verbose=False,
        rasterize=False,
        figure_profile=figure_profile,
        figure_safe_columns=safe_columns,
        write_companion_csv=write_companion_csv,
    )
    plt.close(fig)
'''
    exec(compile(source, "<fake_reprofig_plot>", "exec"), module.__dict__)
    sys.modules[module.__name__] = module
    yield module
    sys.modules.pop(module.__name__, None)


def _experiment(tmp_path):
    csv_path = tmp_path / "measurements.csv"
    frame = pd.DataFrame(
        {
            "AnimalName": ["a1", "a2", "a3", "a4", "a5", "a6"],
            "Condition": ["control"] * 3 + ["treated"] * 3,
            "value": [1.0, 1.5, 2.0, 4.0, 4.5, 5.0],
            "x": [1.0, 2.0, 3.0, 1.5, 2.5, 3.5],
            "y": [1.2, 2.1, 3.4, 1.1, 2.8, 4.0],
            "Time": [0.0, 1.0, 2.0, 0.0, 1.0, 2.0],
        }
    )
    frame.to_csv(csv_path, index=False)
    experiment = from_dataframe(
        frame,
        group_col="Condition",
        subject_col="AnimalName",
        file_path=tmp_path,
        fig_path=tmp_path,
        source_paths=[csv_path],
        source_uri="https://example.org/measurements.csv",
    )
    return experiment, frame, csv_path


def test_master_contains_exact_analysis_rows_stats_and_source(tmp_path, plot_module):
    experiment, frame, csv_path = _experiment(tmp_path)
    plot_module.plot_group(experiment, str(tmp_path), "master")
    svg = tmp_path / "master.svg"
    record = extract_record(svg)

    assert record.distribution_profile == "master"
    assert record.data_status == "complete"
    assert record.statistics_status == "complete"
    assert record.data_tables[0].row_count == len(frame)
    assert set(record.data_tables[0].columns[index].name for index in range(4)) == {
        "group",
        "metric",
        "value",
        "observation_id",
    }
    assert record.statistics[0]["kind"] == "group_comparison"
    assert record.statistics[0]["groups"][0]["n"] == 3
    assert record.statistics[0]["test"]["p"] is not None
    assert any(source.sha256 and source.relative_path == csv_path.name for source in record.sources)
    assert validate_svg(svg).valid
    manifest = provenance.record_for(svg)
    assert manifest["figure_id"] == record.figure_id
    assert manifest["distribution_profile"] == "master"

    extracted = tmp_path / "extracted"
    extract_figure(svg, extracted)
    assert (extracted / "master-plotted-data.csv").read_bytes() == record.data_tables[0].contents.encode("utf-8")
    assert (extracted / "master-statistics.csv").is_file()


@pytest.mark.parametrize("profile,suffix", [("public", "public"), ("minimal_public", "minimal_public")])
def test_direct_public_profiles_fail_closed_and_keep_private_ids_out(
    tmp_path, plot_module, profile, suffix
):
    experiment, _frame, _csv_path = _experiment(tmp_path)
    plot_module.plot_group(
        experiment,
        str(tmp_path),
        suffix,
        figure_profile=profile,
        safe_columns=["group", "metric", "value"],
        write_companion_csv=True,
    )
    svg = tmp_path / f"{suffix}.svg"
    record = extract_record(svg)
    assert record.distribution_profile == profile
    assert "observation_id" not in [column.name for column in record.data_tables[0].columns]
    assert validate_svg(svg, public_safety=True).valid
    readable = suffix.replace("_", "-")
    assert (tmp_path / f"{readable}-plotted-data.csv").is_file()
    assert (tmp_path / f"{readable}-statistics.csv").is_file()
    manifest_entry = json.loads((tmp_path / "figures.json").read_text(encoding="utf-8"))[
        "figures"
    ][f"{suffix}.svg"]
    assert "args" not in manifest_entry
    assert "batch" not in manifest_entry
    assert "request" not in manifest_entry
    if profile == "minimal_public":
        assert record.data_tables[0].contents is None


def test_master_batch_publication_preserves_master_and_writes_manifest(tmp_path, plot_module):
    experiment, _frame, _csv_path = _experiment(tmp_path)
    plot_module.plot_group(experiment, str(tmp_path), "Figure 1")
    master = tmp_path / "Figure 1.svg"
    before = master.read_bytes()
    result = publish_figures(
        [master],
        output_dir=tmp_path / "publication",
        figure_profile="public",
        safe_columns=["group", "metric", "value"],
        public_sources={"source_csv": "https://example.org/measurements.csv"},
    )
    assert result.valid
    assert master.read_bytes() == before
    assert (tmp_path / "publication" / "figure-1-public.svg").is_file()
    validation = json.loads(
        (tmp_path / "publication" / "publication-validation.json").read_text(encoding="utf-8")
    )
    assert validation["valid"] is True


def test_direct_public_failure_does_not_replace_existing_svg(tmp_path, plot_module):
    experiment, _frame, _csv_path = _experiment(tmp_path)
    target = tmp_path / "protected.svg"
    target.write_text("existing master", encoding="utf-8")
    with pytest.raises(ValueError, match="no public columns"):
        plot_module.plot_group(
            experiment,
            str(tmp_path),
            "protected",
            figure_profile="public",
            safe_columns=[],
        )
    assert target.read_text(encoding="utf-8") == "existing master"


def test_descriptive_plot_is_explicitly_statistics_not_applicable(tmp_path):
    fig, _ax = plt.subplots()
    try:
        record = build_pyflash_record(
            fig,
            full_path=tmp_path / "histograms.svg",
            image_name="histograms",
            described={"function": "PyFLASH.plotting.plot_histograms", "args": {}},
        )
    finally:
        plt.close(fig)
    assert record.statistics_status == "not_applicable"


def test_reused_matrix_canvas_keeps_each_groups_data_and_stats_separate(tmp_path):
    experiment, _frame, _source = _experiment(tmp_path)
    plotting.plot_matrices(experiment, filtered_columns=["x", "y"], save=True)
    records = []
    for svg in tmp_path.rglob("*.svg"):
        record = extract_record(svg)
        if str(record.producer.get("function", "")).endswith("plot_matrices"):
            records.append(record)
    assert len(records) == 2
    assert all(record.data_status == "complete" for record in records)
    assert all(record.statistics_status == "complete" for record in records)
    assert all(len(record.statistics) == 1 for record in records)
    assert {record.statistics[0]["group"] for record in records} == {"control", "treated"}


def test_volcano_pca_and_timecourse_attach_their_exact_tables(tmp_path):
    experiment, frame, _source = _experiment(tmp_path)
    plotting.plot_volcano(
        experiment,
        filtered_columns=["value", "x"],
        control="control",
        save=True,
    )
    volcano_records = [
        extract_record(svg)
        for svg in tmp_path.rglob("*.svg")
        if "Volcano" in svg.name
    ]
    assert len(volcano_records) == 1
    assert {table.name for table in volcano_records[0].data_tables} == {
        "plotted_points",
        "analysis_data",
    }
    assert len(volcano_records[0].statistics) == 2

    pca_figure = plotting.plot_marker_pca(
        experiment,
        columns=["x", "y"],
        hue_column="Condition",
        save=True,
        save_path=tmp_path,
        save_name="pca_artifact",
    )
    plt.close(pca_figure)
    pca = extract_record(tmp_path / "pca_artifact.svg")
    assert {table.name for table in pca.data_tables} == {
        "plotted_scores",
        "analysis_features",
        "loadings",
    }
    assert pca.statistics[0]["n"] == len(frame)

    timecourse_figure = plotting.plot_timecourse(
        experiment,
        "value",
        time_col="Time",
        group_col="Condition",
        save=True,
        save_path=tmp_path,
        save_name="timecourse_artifact",
    )
    plt.close(timecourse_figure)
    timecourse = extract_record(tmp_path / "timecourse_artifact.svg")
    assert timecourse.data_tables[0].row_count == len(frame)
    assert {item["group"] for item in timecourse.statistics} == {"control", "treated"}


def test_save_fig_writes_every_available_direct_carrier_with_one_identity(tmp_path):
    from PyFLASH.utils import save_fig

    direct = {"svg", "pdf", "png", "jpeg", "tiff", "webp", "avif", "heif"}
    available = [
        row["format"] for row in reprofig_formats()
        if row["format"] in direct and row["available"]
    ]
    extension = {"jpeg": "jpg", "tiff": "tif", "heif": "heif"}
    suffixes = [extension.get(name, name) for name in available]

    fig, ax = plt.subplots(figsize=(2.0, 1.5))
    ax.plot([0.0, 1.0], [1.0, 2.0])
    try:
        save_fig(
            fig,
            tmp_path,
            "multi",
            figure_formats=suffixes,
            dpi=123,
            rasterize=False,
            verbose=False,
        )
    finally:
        plt.close(fig)

    paths = [tmp_path / f"multi.{suffix}" for suffix in suffixes]
    assert all(path.is_file() for path in paths)
    identities = {extract_record(path).figure_id for path in paths}
    assert len(identities) == 1


def test_pyflash_publication_exposes_all_carrier_operations():
    from PyFLASH import publication

    assert callable(publication.embed_file)
    assert callable(publication.publish_artifacts)
    assert callable(publication.extract_artifact)
    assert callable(publication.validate_artifact)
    assert len(publication.formats()) >= 16
