"""Every saved figure records what produced it, beside the figure itself."""

import json
import sys
import types

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from PyFLASH import provenance, utils  # noqa: E402


@pytest.fixture
def plotting_module():
    """A public plot function calling a private helper, as real plotting does."""
    module = types.ModuleType("PyFLASH.fake_plotting")
    source = """
from PyFLASH import utils


def _draw(figure, save_path, name):
    utils.save_fig(figure, save_path, name, verbose=False)


def plot_marker_counts(figure, save_path, name, marker=None, by=None, data=None, batch=None):
    _draw(figure, save_path, name)
"""
    exec(compile(source, "<fake_plotting>", "exec"), module.__dict__)
    sys.modules["PyFLASH.fake_plotting"] = module
    yield module
    sys.modules.pop("PyFLASH.fake_plotting", None)


@pytest.fixture
def figure():
    fig = plt.figure()
    plt.plot([0, 1], [0, 1])
    yield fig
    plt.close(fig)


def _manifest(directory):
    with open(directory / provenance.MANIFEST_NAME, encoding="utf-8") as stream:
        return json.load(stream)


def test_observer_is_registered_on_import():
    assert provenance._observer in utils._FIG_SAVED_OBSERVERS


def test_saving_a_figure_records_its_producer(tmp_path, plotting_module, figure):
    data = pd.DataFrame({"count": [1, 2, 3], "genotype": ["a", "b", "c"]})
    plotting_module.plot_marker_counts(
        figure, str(tmp_path), "MOAB2_Count", marker="MOAB-2", by="genotype", data=data, batch="8wk"
    )

    entry = _manifest(tmp_path)["figures"]["MOAB2_Count.svg"]
    assert entry["function"] == "PyFLASH.fake_plotting.plot_marker_counts"
    assert entry["args"]["marker"] == "MOAB-2"
    assert entry["args"]["by"] == "genotype"
    assert entry["batch"] == "8wk"
    assert len(entry["sha256"]) == 64
    assert entry["saved_at"]


def test_the_public_call_is_recorded_not_the_private_helper(tmp_path, plotting_module, figure):
    plotting_module.plot_marker_counts(figure, str(tmp_path), "probe")
    entry = _manifest(tmp_path)["figures"]["probe.svg"]
    assert entry["function"].endswith(".plot_marker_counts")
    assert "_draw" not in entry["function"]


def test_dataframes_are_summarised_never_serialised(tmp_path, plotting_module, figure):
    data = pd.DataFrame({"value": range(5000), "group": ["x"] * 5000})
    plotting_module.plot_marker_counts(figure, str(tmp_path), "big", data=data)

    entry = _manifest(tmp_path)["figures"]["big.svg"]
    assert entry["args"]["data"].startswith("DataFrame(5000x2)")
    assert (tmp_path / provenance.MANIFEST_NAME).stat().st_size < 4096


def test_plumbing_arguments_are_left_out(tmp_path, plotting_module, figure):
    plotting_module.plot_marker_counts(figure, str(tmp_path), "probe", marker="Iba1")
    args = _manifest(tmp_path)["figures"]["probe.svg"]["args"]
    assert args == {"marker": "Iba1"}


def test_several_figures_share_one_manifest(tmp_path, plotting_module, figure):
    for name in ("one", "two", "three"):
        plotting_module.plot_marker_counts(figure, str(tmp_path), name, marker=name)

    figures = _manifest(tmp_path)["figures"]
    assert sorted(figures) == ["one.svg", "three.svg", "two.svg"]
    assert figures["two.svg"]["args"]["marker"] == "two"


def test_resaving_replaces_that_entry_and_keeps_the_others(tmp_path, plotting_module, figure):
    plotting_module.plot_marker_counts(figure, str(tmp_path), "keep", marker="GFAP")
    plotting_module.plot_marker_counts(figure, str(tmp_path), "redraw", marker="first")
    plotting_module.plot_marker_counts(figure, str(tmp_path), "redraw", marker="second")

    figures = _manifest(tmp_path)["figures"]
    assert figures["redraw.svg"]["args"]["marker"] == "second"
    assert figures["keep.svg"]["args"]["marker"] == "GFAP"


def test_an_armed_request_is_recorded_as_the_exact_producer(tmp_path, plotting_module, figure):
    provenance.arm({"plot": "marker_counts", "marker": "CK1d"}, batch="batch1")
    try:
        plotting_module.plot_marker_counts(figure, str(tmp_path), "armed")
    finally:
        provenance.disarm()

    entry = _manifest(tmp_path)["figures"]["armed.svg"]
    assert entry["request"] == {"plot": "marker_counts", "marker": "CK1d"}
    assert entry["batch"] == "batch1"
    assert not provenance.is_active()


def test_record_for_reads_one_figure_back(tmp_path, plotting_module, figure):
    plotting_module.plot_marker_counts(figure, str(tmp_path), "probe", marker="Iba1")
    entry = provenance.record_for(tmp_path / "probe.svg")
    assert entry["args"]["marker"] == "Iba1"
    assert provenance.record_for(tmp_path / "absent.svg") is None


def test_a_corrupt_manifest_is_replaced_rather_than_crashing(tmp_path, plotting_module, figure):
    (tmp_path / provenance.MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    plotting_module.plot_marker_counts(figure, str(tmp_path), "probe", marker="Iba1")
    assert _manifest(tmp_path)["figures"]["probe.svg"]["args"]["marker"] == "Iba1"


def test_provenance_never_raises_into_the_save_path(tmp_path, plotting_module, figure, monkeypatch):
    monkeypatch.setattr(provenance, "_sha256", lambda path: 1 / 0)
    plotting_module.plot_marker_counts(figure, str(tmp_path), "probe")
    assert (tmp_path / "probe.svg").is_file()


def test_summarise_bounds_every_kind_of_argument():
    assert provenance.summarise(None) is None
    assert provenance.summarise(True) is True
    assert provenance.summarise("short") == "short"
    assert provenance.summarise("x" * 500).endswith("...")
    assert provenance.summarise(list(range(50))) == "list[50]"
    assert provenance.summarise([1, "a"]) == [1, "a"]
    assert provenance.summarise(pd.Series([1, 2, 3])) == "Series(3)"
    assert provenance.summarise({"a": 1}) == {"a": 1}


def test_the_producer_is_embedded_in_the_svg_itself(tmp_path, plotting_module, figure):
    plotting_module.plot_marker_counts(figure, str(tmp_path), "embedded", marker="CK1d", by="genotype")

    svg = tmp_path / "embedded.svg"
    assert "<dc:description>" in svg.read_text(encoding="utf-8"), (
        "the canvas normaliser must not strip the metadata element"
    )
    record = provenance.embedded_record(svg)
    assert record["function"].endswith(".plot_marker_counts")
    assert record["args"] == {"marker": "CK1d", "by": "genotype"}
    assert record["pyflash_version"] != "unknown"
    assert "sha256" not in record, "a file cannot carry its own hash"


def test_embedded_and_manifest_records_agree(tmp_path, plotting_module, figure):
    plotting_module.plot_marker_counts(figure, str(tmp_path), "both", marker="Iba1")
    svg = tmp_path / "both.svg"
    embedded = provenance.embedded_record(svg)
    listed = provenance.record_for(svg)
    assert embedded["function"] == listed["function"]
    assert embedded["args"] == listed["args"]


def test_column_names_stay_out_of_the_figure_file(tmp_path, plotting_module, figure):
    data = pd.DataFrame({"count": [1, 2], "unpublished_marker": [3, 4]})
    plotting_module.plot_marker_counts(figure, str(tmp_path), "leaky", data=data)

    svg = (tmp_path / "leaky.svg").read_text(encoding="utf-8")
    assert "unpublished_marker" not in svg, "column names are data and must not travel inside a figure"
    assert provenance.embedded_record(tmp_path / "leaky.svg")["args"]["data"] == "DataFrame(2x2)"
    listed = _manifest(tmp_path)["figures"]["leaky.svg"]["args"]["data"]
    assert "unpublished_marker" in listed, "the manifest sits beside the data, so it keeps the detail"


def test_a_renamed_figure_keeps_its_embedded_producer(tmp_path, plotting_module, figure):
    plotting_module.plot_marker_counts(figure, str(tmp_path), "before", marker="GFAP")
    moved = tmp_path / "presentation"
    moved.mkdir()
    (tmp_path / "before.svg").rename(moved / "Figure 3b.svg")

    assert provenance.record_for(moved / "Figure 3b.svg") is None
    assert provenance.embedded_record(moved / "Figure 3b.svg")["args"] == {"marker": "GFAP"}


def test_embedded_record_ignores_a_file_without_provenance(tmp_path):
    plain = tmp_path / "plain.svg"
    plain.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
    assert provenance.embedded_record(plain) is None
    assert provenance.embedded_record(tmp_path / "absent.svg") is None


def test_embedding_survives_special_characters(tmp_path, plotting_module, figure):
    plotting_module.plot_marker_counts(figure, str(tmp_path), "greek", marker="CK1<d> & β")
    record = provenance.embedded_record(tmp_path / "greek.svg")
    assert record["args"]["marker"] == "CK1<d> & β"
