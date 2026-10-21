"""Guard the independently calculated adjusted-correlation whole-call witness."""
import json

from reproducibility.adjusted_correlation_pipeline_contract import check
from reproducibility import run


def test_adjusted_correlation_reference_contract_agrees(tmp_path):
    rows = check(tmp_path)

    assert len(rows) == 10
    assert {row["status"] for row in rows} == {"agree"}
    evidence = json.loads(
        (tmp_path / "adjusted-correlation-pipeline-independent-evidence.json")
        .read_text(encoding="utf-8")
    )
    assert evidence["pearson_partial_reference"]["n"] == 24
    assert evidence["reference_packages"]["pingouin"] == "0.5.5"
    capabilities = {row["capability"]: row for row in run.inventory(
        row["contract"] for row in rows
    )}

    for capability in (
        "PyFLASH.pipeline.adjusted_correlation",
        "adjusted_correlation_pipeline",
    ):
        assert capabilities[capability]["status"] == "partially-validated-contract"
        assert set(capabilities[capability]["executed_subcontracts"].split(";")) == {
            row["contract"] for row in rows
        }
