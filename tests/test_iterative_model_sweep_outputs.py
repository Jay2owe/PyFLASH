from types import SimpleNamespace

import pandas as pd

from PyFLASH.modelling import iterative_model_sweep
from PyFLASH.spec import PLOT_REGISTRY, _resolve_func, describe_status


def test_iterative_model_sweep_registered_and_covered():
    assert "iterative_model_sweep" in PLOT_REGISTRY
    assert _resolve_func(PLOT_REGISTRY["iterative_model_sweep"]) is iterative_model_sweep
    assert describe_status("iterative_model_sweep") == "covered"


def test_iterative_model_sweep_co_locates_tables_and_plots(tmp_path):
    rows = []
    for i in range(12):
        group = "Control" if i % 2 == 0 else "MCI"
        rows.append({
            "Diagnosis": group,
            "FeatureA": float(i % 2) + i * 0.01,
            "FeatureB": float((i // 2) % 3),
        })
    batch = SimpleNamespace(
        summary=pd.DataFrame(rows),
        fig_path=str(tmp_path / "Python Figures"),
    )

    result = iterative_model_sweep(
        batch,
        target="Diagnosis",
        possible_predictors=["FeatureA", "FeatureB"],
        max_features=1,
        model_families=["ridge_multinomial_logistic"],
        cv="stratified2",
        save=True,
        run_label="unit",
        top_n=3,
        checkpoint_every=1,
        plot=True,
        verbose=False,
    )

    out = tmp_path / "Python Figures" / "Modelling" / "Model Sweep" / "unit"
    assert result["output_dir"] == str(out)
    assert (out / "iterative_model_sweep_scores.csv").exists()
    assert (out / "top_iterative_model_sweep_scores.csv").exists()
    assert (out / "top_feature_recurrence.csv").exists()
    assert (out / "top_model_predictions.csv").exists()
    assert (out / "top_model_permutation_test.csv").exists()
    assert (out / "iterative_model_sweep_scores_partial.csv").exists()
    assert (out / "iterative_model_sweep_scores_partial.meta.json").exists()
    assert (out / "top_iterative_model_sweep.png").exists()
    assert (out / "family_by_subset_size_heatmap.png").exists()
    assert (out / "top_feature_recurrence.png").exists()
    assert not (out / "stats").exists()
    assert not (out / "figures").exists()
