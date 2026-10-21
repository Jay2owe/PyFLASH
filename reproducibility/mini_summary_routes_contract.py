"""Group two bounded summary routes into one authenticated independent replay."""
from reproducibility import mini_exclusion_contract, mini_score_contract, mini_nonfinite_score_contract, mini_object_mean_contract

CONTRACTS = (mini_exclusion_contract, mini_score_contract, mini_nonfinite_score_contract, mini_object_mean_contract)
COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {'PyFLASH.experiment.MiniExperiment.createSummary': ('mini-exclusions.', 'mini-scores.', 'mini-nonfinite-scores.', 'mini-object-means.')}


def cases():
    rows = [row for contract in CONTRACTS for row in contract.cases()]
    assert len({row['key'] for row in rows}) == len(rows)
    return rows


def validate(output):
    from pathlib import Path
    return [row for contract in CONTRACTS for row in contract.validate(Path(output) / contract.__name__.rsplit('.', 1)[-1])]
