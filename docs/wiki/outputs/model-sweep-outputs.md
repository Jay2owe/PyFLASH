# Model Sweep Outputs

## Summary

Model sweep outputs are the saved artifacts from
[`iterative_model_sweep`](../functions/iterative_model_sweep.md). The sweep
tests many feature subsets and classifier configurations, ranks them, records
the top model's predictions, and optionally plots summary PNGs.

These outputs are discovery artifacts. They help identify candidate predictors
and model families, but they do not replace independent validation or nested
cross-validation.

## Created By

| Function | Output trigger |
|---|---|
| [`iterative_model_sweep`](../functions/iterative_model_sweep.md) with `save=True` | Creates the run folder and writes CSV, JSON, and README outputs. |
| `iterative_model_sweep(..., plot=True)` | Also writes PNG summary plots. |
| `iterative_model_sweep(..., checkpoint_every=...)` | Writes or updates partial checkpoint files during scoring. |
| `iterative_model_sweep(..., permutations>0)` | Fills `top_model_permutation_test.csv` with label-shuffle results for the selected top model. |

## Folder Layout

If `output_dir` is supplied, PyFLASH writes directly there:

```text
<output_dir>/
  iterative_model_sweep_scores.csv
  top_iterative_model_sweep_scores.csv
  top_feature_recurrence.csv
  top_model_predictions.csv
  top_model_permutation_test.csv
  iterative_model_sweep_scores_partial.csv
  iterative_model_sweep_scores_partial.meta.json
  manifest.json
  README.md
  top_iterative_model_sweep.png
  family_by_subset_size_heatmap.png
  top_feature_recurrence.png
```

If `output_dir` is omitted and the input object has `fig_path`, the default is:

```text
<fig_path>/Modelling/Model Sweep/<run_label>/
```

If neither `output_dir` nor `fig_path` is available, PyFLASH falls back to a
relative folder below the current working directory:

```text
Modelling/Model Sweep/<run_label>/
```

Current sweep outputs are co-located directly in the run folder. They are not
split into `stats/` and `figures/` subfolders.

## File Contents

| File | Contents |
|---|---|
| `iterative_model_sweep_scores.csv` | All valid model scores, ranked. Rows include model family/configuration, subset size, feature list, cross-validation metrics, and scoring fields such as balanced accuracy, macro F1, AUC, or log loss when available. |
| `top_iterative_model_sweep_scores.csv` | Top `top_n` rows from the full score table. |
| `top_feature_recurrence.csv` | Feature recurrence summary among top-ranked models. |
| `top_model_predictions.csv` | Cross-validated predictions for the selected top model, with row index, fold, actual class, predicted class, class codes, and per-class probability columns named `prob_<class>`. |
| `top_model_permutation_test.csv` | Label-shuffle test for the selected top model. Empty when `permutations=0` or no valid permutations are produced. |
| `iterative_model_sweep_scores_partial.csv` | Checkpoint rows flushed during a long run. Used for resume support. |
| `iterative_model_sweep_scores_partial.meta.json` | Signature describing the target, predictors, data hash, model settings, CV settings, specificity, and other resume-critical options. |
| `manifest.json` | Run metadata: target, class labels/counts, predictors, removed empty features, search settings, classifier count, valid score count, best family, best model config, and best features. |
| `README.md` | Human-readable run summary and key-file list written into the output folder. |
| `top_iterative_model_sweep.png` | Bar plot of top ranked models. |
| `family_by_subset_size_heatmap.png` | Best score by model family and subset size. |
| `top_feature_recurrence.png` | Bar plot of recurring top features. |

The Python return value also includes in-memory objects such as
`best_estimator`, `all_model_scores`, `top_feature_recurrence`,
`top_model_predictions`, and paths such as `output_dir`, `stats_dir`, and
`figures_dir`.

## How To Reuse

Run a sweep and save outputs under the batch figure folder:

```python
from PyFLASH.modelling import iterative_model_sweep

result = iterative_model_sweep(
    batch,
    target="Diagnosis",
    possible_predictors=["GFAP_Count", "IBA1_Count", "Period"],
    max_features=2,
    run_label="diagnosis_screen",
    save=True,
    plot=True,
)

print(result["output_dir"])
```

Read the score table and top-model predictions:

```python
from pathlib import Path
import pandas as pd

out = Path("analysis-output/Results/Python Figures/Modelling/Model Sweep/diagnosis_screen")
scores = pd.read_csv(out / "iterative_model_sweep_scores.csv")
predictions = pd.read_csv(out / "top_model_predictions.csv")

print(scores.head(10))
print(predictions.filter(regex="actual|predicted|prob_").head())
```

Resume from a matching checkpoint:

```python
result = iterative_model_sweep(
    batch,
    target="Diagnosis",
    possible_predictors=["GFAP_Count", "IBA1_Count", "Period"],
    max_features=2,
    run_label="diagnosis_screen",
    save=True,
    resume=True,
)
```

## Notes

- `resume=True` only reuses `iterative_model_sweep_scores_partial.csv` when the
  metadata signature matches the new request. If it does not match, PyFLASH
  starts fresh and removes stale checkpoint files.
- `top_model_permutation_test.csv` tests only the selected top model, not the
  whole search process.
- `plot=False` skips PNG summary plots but still writes tables and metadata
  when `save=True`.
- `save=False` returns in-memory results and sets saved path fields to `None`.

## See Also

- [iterative_model_sweep](../functions/iterative_model_sweep.md)
- [Classification](../statistics/classification.md)
- [Pipeline run folders](pipeline-run-folders.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
