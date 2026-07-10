# Run Model Sweep

## Goal

Run a classifier discovery screen that tests candidate feature subsets and
model families for a categorical target such as diagnosis group.

Use [`iterative_model_sweep`](../functions/iterative_model_sweep.md) to rank
candidate predictors, not to prove biological causality.

## Inputs

- A `Batch`, batch-like object, or raw `pandas.DataFrame`.
- A categorical target column such as `Diagnosis`.
- Candidate predictor columns through `data_cols`, `predictors`, or column-name
  selectors.
- A maximum subset size such as `max_features=2`.
- Optional class order, row filters, and cross-validation settings.

## Minimal Path

```python
from PyFLASH import iterative_model_sweep, load_state

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")

result = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_cols=["GFAP Volume", "IBA1 Volume", "DAPI Count"],
    max_features=2,
    run_label="diagnosis_screen",
    save=True,
    plot=True,
)

print(result["best_family"])
print(result["best_features"])
```

## Full Workflow

1. Start with a small, defensible predictor panel. Remove identifiers, target
   columns, and obvious leakage variables.

```python
candidate_cols = [
    "GFAP Volume",
    "IBA1 Volume",
    "DAPI Count",
    "Period (h)",
]
```

2. Run a compact screen. The default `model_preset="ultra_compact"` is intended
   for fast first passes.

```python
screen = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_cols=candidate_cols,
    class_order=["Control", "MCI", "AD"],
    max_features=2,
    scoring="balanced_accuracy",
    cv="stratified5",
    run_label="diagnosis_screen",
    save=True,
    plot=True,
)
```

3. Inspect the ranked score and recurrence tables:

```python
scores = screen["all_model_scores"]
recurrence = screen["top_feature_recurrence"]

print(scores.head(10))
print(recurrence.head())
```

4. Use row filters when the target question is scoped to one subset:

```python
scn_screen = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_cols=candidate_cols,
    filter_by={"Region": "SCN"},
    max_features=2,
    run_label="scn_diagnosis_screen",
)
```

5. For larger predictor pools, use beam search and checkpoint resume:

```python
larger = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_col_contains=["Volume", "Count", "Intensity"],
    data_col_exclude=["NonColoc"],
    max_features=3,
    model_preset="compact",
    search_strategy="beam",
    beam_width=200,
    n_jobs=-1,
    resume=True,
    run_label="diagnosis_beam_screen",
)
```

6. Reuse the fitted best estimator only for follow-up inspection. Treat it as a
   discovery result until validated independently.

```python
best_features = list(screen["best_features"])
estimator = screen["best_estimator"]

predicted_codes = estimator.predict(batch.summary[best_features])
predicted_labels = [
    screen["class_labels"][int(code)]
    for code in predicted_codes
]
```

## Outputs

With `save=True` and no explicit `output_dir`, the default run folder is:

```text
<batch.fig_path>/Modelling/Model Sweep/<run_label>/
```

Common outputs include:

| Output | Meaning |
|---|---|
| `iterative_model_sweep_scores.csv` | Ranked score table for all valid models. |
| `top_iterative_model_sweep_scores.csv` | Top `top_n` ranked rows. |
| `top_feature_recurrence.csv` | Features recurring among top-ranked models. |
| `top_model_predictions.csv` | Fold-level predictions for the selected top model. |
| `top_model_permutation_test.csv` | Optional label-permutation test for the top model. |
| `iterative_model_sweep_scores_partial.csv` | Checkpoint table for long runs. |
| `iterative_model_sweep_scores_partial.meta.json` | Checkpoint compatibility metadata. |
| `manifest.json` | Run settings and best-model summary. |
| `README.md` | Human-readable run summary. |
| `*.png` | Optional summary plots when `plot=True`. |

The return dictionary includes `best_estimator`, `best_features`,
`best_metrics`, `all_model_scores`, `top_feature_recurrence`,
`top_model_predictions`, and `output_dir`.

## Troubleshooting

- The sweep is slow: lower `max_features`, use `model_preset="ultra_compact"`,
  use `search_strategy="beam"`, or narrow predictors with `data_col_contains`
  and `data_col_exclude`.
- Classes are imbalanced: use `scoring="balanced_accuracy"` and pass
  `class_order` for interpretable ordering.
- Optional model families are skipped: some families need optional packages,
  such as ordinal logistic support.
- Resume did not reuse a checkpoint: the metadata signature must match the new
  request. Changed predictors, target, filters, or model settings start a fresh
  run.
- Saved outputs are missing PNGs: check `plot=True`; tables can still be written
  when plotting is disabled.

## Next Steps

- [iterative_model_sweep reference](../functions/iterative_model_sweep.md)
- [Model sweep outputs](../outputs/model-sweep-outputs.md)
- [Classification statistics](../statistics/classification.md)
- [Model options](../parameters/model-options.md)
- [Saving and run labels](../parameters/saving.md)
- [Slow model sweeps troubleshooting](../troubleshooting/slow-model-sweeps.md)
