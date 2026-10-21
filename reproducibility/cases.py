"""Versioned synthetic exam inputs; no PyFLASH-generated expected answers."""
import json
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "reference_results.json"
RTOL = 1e-9
ATOL = 1e-12


def inputs():
    # Literal inputs make random-generator/library upgrades irrelevant.
    return {
        "balanced": [[1.2, 2.4, 2.9, 3.8, 5.1, 6.3], [2.0, 4.2, 5.7, 6.8, 7.0, 8.1]],
        "unequal": [[0.2, 0.8, 1.1, 1.4, 1.9], [0.1, 3.2, 5.1, 8.4, 12.3, 14.9, 20.2]],
        "ties": [[1, 1, 2, 3, 5, 8], [1, 2, 2, 4, 7, 9]],
        "constant_effect": [[1, 1, 1, 1], [2, 2, 2, 2]],
        "missing_ttest": [[1.0, None, 2.5, 3.5, 6.0], [2.5, 3.1, None, 6.8, 8.2]],
        "corrections": [0.002, 0.03, 0.04, 0.12, None, 0.7, 1.0, 0.0, 0.03],
        "cosinor": {"t": [0, 1, 3, 5, 8, 12, 15, 18, 21, 24, 29, 34],
                    "noise": [0.1, -0.2, 0.3, -0.1, 0.2, -0.15, 0.1, 0.3, -0.25, 0.05, 0.2, -0.1],
                    "period": 24.0, "mesor": 10.0, "amplitude": 2.0, "acrophase": 4.0},
    }


def load_expected():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))
