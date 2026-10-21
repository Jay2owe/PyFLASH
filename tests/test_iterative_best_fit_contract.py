from reproducibility import iterative_best_fit_contract as contract


def test_small_leave_group_out_search_matches_exact_rational_reference(tmp_path):
    rows = contract.validate(tmp_path)
    assert len(rows) == len(contract.cases()) + 3 + len(contract.INVALID_INPUT_CASES) == 21
    failures = [row for row in rows if row["status"] != "agree"]
    assert not failures, failures
    assert "iterative-best-fit.plot-save-and-hue-routes" in contract.required_keys()
