"""Tests for the generic significance-audit table plot."""

from types import SimpleNamespace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
import pandas as pd

from PyFLASH import report
from PyFLASH.plotting import plot_significance_audit_table
from PyFLASH.spec import PLOT_REGISTRY, _resolve_func, describe_status


def _audit_frame():
    return pd.DataFrame(
        {
            "assay_name": ["Metric A", "Metric B", "Metric C"],
            "category": ["activity", "activity", "timing"],
            "sample_count": [12, 12, 10],
            "raw_profile": [0.01, 0.20, 0.049],
            "adjusted_profile": [0.03, 0.80, 0.051],
            "screen_q": [0.04, 0.90, 0.12],
        }
    )


def _experiment(tmp_path):
    return SimpleNamespace(fig_path=str(tmp_path / "figures"), aliases=None)


def test_significance_audit_table_registered_and_describe_covered():
    assert PLOT_REGISTRY["significance_audit_table"] == "plot_significance_audit_table"
    assert _resolve_func(PLOT_REGISTRY["significance_audit_table"]).__name__ == "plot_significance_audit_table"
    assert describe_status("significance_audit_table") == "covered"


def test_significance_audit_table_infers_generic_pvalue_columns(tmp_path):
    path = plot_significance_audit_table(
        _experiment(tmp_path),
        audit_table=_audit_frame(),
        row_label_col="assay_name",
        title="Generic audit",
        save=True,
    )
    output = Path(path)
    assert output.exists()
    assert output.parent.name == "Tables"
    svg = output.read_text(encoding="utf-8")
    assert "<text" in svg
    assert "Metric A" in svg
    assert "raw_profile" in svg
    assert "adjusted_profile" in svg
    assert "screen_q" in svg
    assert "sample_count" not in svg


def test_significance_audit_table_accepts_explicit_columns_and_csv_path(tmp_path):
    csv_path = tmp_path / "audit.csv"
    _audit_frame().to_csv(csv_path, index=False)

    path = plot_significance_audit_table(
        path=csv_path,
        row_label_col="assay_name",
        pvalue_cols=["adjusted_profile", "screen_q"],
        column_labels={"adjusted_profile": "Adjusted", "screen_q": "FDR q"},
        filename="explicit_audit",
        save=True,
    )
    svg = Path(path).read_text(encoding="utf-8")
    assert "Adjusted" in svg
    assert "FDR q" in svg
    assert "raw_profile" not in svg


def test_significance_audit_table_matrix_aesthetic_has_editable_text():
    fig = plot_significance_audit_table(
        audit_table=_audit_frame(),
        row_label_col="assay_name",
        pvalue_cols=["raw_profile", "adjusted_profile"],
        aesthetic="matrix",
        save=False,
    )
    try:
        labels = [text.get_text() for ax in fig.axes for text in ax.texts]
        assert "0.010" in labels
        assert "0.800" in labels
    finally:
        plt.close(fig)


def test_significance_audit_table_emits_report_records():
    report.start()
    fig = plot_significance_audit_table(
        audit_table=_audit_frame(),
        row_label_col="assay_name",
        pvalue_cols=["raw_profile", "adjusted_profile"],
        save=False,
    )
    try:
        records = report.collect()
    finally:
        plt.close(fig)
    assert len(records) == 6
    assert {rec["kind"] for rec in records} == {"significance_audit"}
    first = records[0]
    assert first["metric"] == "Metric A"
    assert first["profile"] == "raw_profile"
    assert first["p"] == 0.01
    assert first["significant"] is True

