"""Independent end-to-end checks for the public correlation pipeline."""

import json

from reproducibility.correlation_pipeline_contract import check


def test_public_pipeline_matches_independent_reference_and_retains_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    comparisons = check(tmp_path / "evidence")

    assert len(comparisons) == 12
    assert all(row["status"] == "agree" for row in comparisons)
    evidence = json.loads((tmp_path / "evidence" / "correlation-pipeline-independent-evidence.json")
                          .read_text(encoding="utf-8"))
    assert len(evidence["comparisons"]) == 12
    assert evidence["gate"] == "raw p"
