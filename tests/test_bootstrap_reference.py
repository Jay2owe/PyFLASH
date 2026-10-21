"""Independent analytic equations lock seeded subject-level uncertainty."""
import json
import numpy as np
import pytest
from PyFLASH import stats_extra
from reproducibility.bootstrap_reference import FIXTURE

FROZEN = json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("row",FROZEN["rows"],ids=lambda r:f"{r['case']}/{r['kind']}/{r['confidence']}")
def test_effect_interval_matches_frozen_analytic_bca(row):
    a,b = FROZEN["inputs"][row["case"]]
    actual = stats_extra.effect_ci(a,b,eftype=row["kind"],n_resamples=row["resamples"],
                                  confidence=row["confidence"],random_state=row["seed"])
    np.testing.assert_allclose(actual,row["expected"],rtol=FROZEN["rtol"],atol=FROZEN["atol"])


def test_effect_interval_references_detect_changed_endpoint():
    values = FROZEN["rows"][0]["expected"]
    with pytest.raises(AssertionError):
        np.testing.assert_allclose([values[0]+.001,values[1]],values,rtol=1e-9,atol=1e-12)
