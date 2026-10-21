"""Independent whole-call witnesses for the public correlation pipeline."""
from fractions import Fraction
from itertools import permutations
import json
import math
from pathlib import Path

import mpmath as mp
import pandas as pd

from PyFLASH.pipeline import correlation


VALUES = {
    "x": [1, 2, 3, 4, 5, 6, 7],
    "y": [1, 2, 4, 3, 5, 7, 6],
    "z": [3, 6, 1, 7, 2, 5, None],
}
METHODS = {"pearsonr": "Pearson", "spearmanr": "Spearman", "kendalltau": "Kendall"}
CAPABILITY_PREFIXES = {
    "PyFLASH.pipeline.correlation": ("correlation.pipeline.",),
}


def _pearson_fraction(x, y):
    x, y = [Fraction(value) for value in x], [Fraction(value) for value in y]
    n = len(x)
    dx = [n * value - sum(x) for value in x]
    dy = [n * value - sum(y) for value in y]
    numerator = sum(a * b for a, b in zip(dx, dy))
    denominator = mp.sqrt(int(sum(a * a for a in dx) * sum(b * b for b in dy)))
    return mp.mpf(numerator.numerator) / numerator.denominator / denominator


def _ranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [None] * len(values)
    for rank, index in enumerate(order, 1):
        ranks[index] = rank
    return ranks


def _t_probability(r, n):
    if abs(r) == 1:
        return mp.mpf(0)
    degrees = n - 2
    squared_t = r * r * degrees / (1 - r * r)
    return mp.betainc(degrees / 2, mp.mpf("0.5"), 0,
                      degrees / (degrees + squared_t), regularized=True)


def _kendall_counts(x, y):
    concordant = discordant = 0
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            product = (x[i] - x[j]) * (y[i] - y[j])
            concordant += product > 0
            discordant += product < 0
    return concordant, discordant


def _kendall_exact(x, y):
    concordant, discordant = _kendall_counts(x, y)
    observed = abs(concordant - discordant)
    denominator = len(x) * (len(x) - 1) // 2
    more_extreme = sum(
        abs(_kendall_counts(x, candidate)[0] - _kendall_counts(x, candidate)[1]) >= observed
        for candidate in permutations(y)
    )
    return Fraction(concordant - discordant, denominator), Fraction(more_extreme, math.factorial(len(y)))


def _bh(pvalues):
    ordered = sorted(enumerate(pvalues), key=lambda pair: pair[1])
    adjusted = [None] * len(pvalues)
    running = 1.0
    count = len(ordered)
    for reverse_index in range(count - 1, -1, -1):
        original_index, pvalue = ordered[reverse_index]
        running = min(running, pvalue * count / (reverse_index + 1))
        adjusted[original_index] = min(1.0, running)
    return adjusted


def reference_rows():
    columns = list(VALUES)
    pairs = []
    with mp.workdps(50):
        for i, first in enumerate(columns):
            for second in columns[i + 1:]:
                x, y = [], []
                for left, right in zip(VALUES[first], VALUES[second]):
                    if left is None or right is None:
                        continue
                    x.append(left)
                    y.append(right)
                n = len(x)
                pearson = _pearson_fraction(x, y)
                spearman = _pearson_fraction(_ranks(x), _ranks(y))
                kendall, kendall_p = _kendall_exact(x, y)
                pairs.append({
                    "x": first, "y": second, "n": n,
                    "pearsonr": (float(pearson), float(_t_probability(pearson, n))),
                    "spearmanr": (float(spearman), float(_t_probability(spearman, n))),
                    "kendalltau": (float(kendall), float(kendall_p)),
                })
    for method in METHODS:
        qvalues = _bh([pair[method][1] for pair in pairs])
        for pair, qvalue in zip(pairs, qvalues):
            pair.setdefault("q", {})[method] = qvalue
    return pairs


def _frame():
    frame = pd.DataFrame({"AnimalName": [f"S{i}" for i in range(7)],
                          "Condition": ["A"] * 7, **VALUES},
                         index=pd.Index([3, 8, 15, 22, 31, 42, 55], name="source-row"))
    frame.attrs["source-note"] = "retain exactly"
    return frame


def check(output):
    """Execute independent scientific and whole-call output checks, retaining evidence."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frame = _frame()
    original = frame.copy(deep=True)
    result = correlation(
        frame, filtered_columns=list(VALUES), tests=tuple(METHODS), gate="p",
        require="or", alpha=0.05, min_n=3, max_regressions=0, save=False,
        write_manifest=False, run_label="independent-correlation-contract",
    )
    references = reference_rows()
    actual = result["pairwise"]
    comparisons = []
    expected_selected = set()
    for pair in references:
        for method, display in METHODS.items():
            match = actual[(actual["x"] == pair["x"])
                           & (actual["y"] == pair["y"])
                           & (actual["method"] == display)]
            if len(match) != 1:
                raise AssertionError(f"Expected one {display} row for {pair['x']} vs {pair['y']}; got {len(match)}")
            row = match.iloc[0]
            coefficient, pvalue = pair[method]
            expected = {"n": pair["n"], "r": coefficient, "p": pvalue,
                        "q": pair["q"][method], "passes": pvalue < 0.05}
            observed = {"n": int(row["n"]), "r": float(row["r"]), "p": float(row["p"]),
                        "q": float(row["q"]), "passes": bool(row["passes"])}
            agrees = (observed["n"] == expected["n"]
                      and observed["passes"] is expected["passes"]
                      and all(math.isclose(observed[key], expected[key], rel_tol=1e-12,
                                           abs_tol=1e-12 if key == "r" else 1e-14)
                              for key in ("r", "p", "q")))
            comparisons.append({"contract": f"correlation.pipeline.{pair['x']}.{pair['y']}.{method}",
                                "reference": "exact-fractions-50-digit-beta-exact-kendall-independent-BH",
                                "family": "independent-whole-public-pipeline",
                                "status": "agree" if agrees else "disagree",
                                "shape": "n-r-p-q-gate-row", "missingness_equal": agrees,
                                "max_absolute_error": "", "rtol": 1e-12, "atol": 1e-14,
                                "pyflash_nonfinite": "none",
                                "frozen_reference_agrees": True,
                                "pyflash_values": json.dumps(observed, sort_keys=True),
                                "reference_values": json.dumps(expected, sort_keys=True)})
            if expected["passes"]:
                expected_selected.add((pair["x"], pair["y"]))
    selected = result["selected"]
    selected_pairs = set(zip(selected["x"], selected["y"]))
    selected_agrees = selected_pairs == expected_selected
    counts_agree = (result["n_pairs"] == len(references)
                    and result["n_selected"] == len(expected_selected))
    ownership_agrees = frame.equals(original) and frame.attrs == original.attrs
    for key, expected, actual_value in (
        ("selected-pairs", sorted(expected_selected), sorted(selected_pairs)),
        ("summary-counts", [len(references), len(expected_selected)],
         [result["n_pairs"], result["n_selected"]]),
        ("source-ownership", {"index": list(original.index), "attrs": original.attrs},
         {"index": list(frame.index), "attrs": frame.attrs}),
    ):
        agrees = selected_agrees if key == "selected-pairs" else counts_agree if key == "summary-counts" else ownership_agrees
        comparisons.append({"contract": f"correlation.pipeline.{key}",
                            "reference": "literal-independent-input-and-selected-pair-contract",
                            "family": "independent-whole-public-pipeline",
                            "status": "agree" if agrees else "disagree",
                            "shape": key, "missingness_equal": agrees,
                            "max_absolute_error": "", "rtol": 0.0, "atol": 0.0,
                            "pyflash_nonfinite": "none", "frozen_reference_agrees": True,
                            "pyflash_values": json.dumps(actual_value, default=str, sort_keys=True),
                            "reference_values": json.dumps(expected, default=str, sort_keys=True)})
    evidence = {"case": "three metrics, seven rows, one pairwise missing value",
                "methods": list(METHODS), "gate": "raw p", "require": "or",
                "reference": "exact rational coefficients, 50-digit Student tails, exact Kendall permutation, independent BH",
                "comparisons": comparisons}
    (output / "correlation-pipeline-independent-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    failed = [row["contract"] for row in comparisons if row["status"] != "agree"]
    if failed:
        raise AssertionError("Correlation pipeline disagreements: " + ", ".join(failed))
    return comparisons

