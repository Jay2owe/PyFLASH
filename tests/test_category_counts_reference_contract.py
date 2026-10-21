"""Independent reference checks for category-count rendering and adapters."""
import json

from reproducibility.category_counts_contract import check
from reproducibility import run


def test_category_counts_contract_agrees_and_is_registered(tmp_path):
    comparisons = check(tmp_path)

    assert len(comparisons) == 20
    assert {row["status"] for row in comparisons} == {"agree"}
    evidence = json.loads(
        (tmp_path / "category-counts-independent-evidence.json")
        .read_text(encoding="utf-8")
    )
    capability = next(
        row for row in run.inventory(row["contract"] for row in comparisons)
        if row["capability"] == "category_counts"
    )
    assert capability["status"] == "partially-validated-contract"
    assert set(capability["executed_subcontracts"].split(";")) == {
        row["contract"] for row in comparisons
    }
    assert len(evidence["comparisons"]) == 20
