# Small Model Sweep

## Goal

Screen a tiny set of predictors for a categorical target without writing model
outputs to disk.

## Code

```python
import pandas as pd
from PyFLASH import iterative_model_sweep

rows = []
for i in range(12):
    diagnosis = "Control" if i % 2 == 0 else "MCI"
    rows.append({
        "Subject": f"S{i + 1:02d}",
        "Diagnosis": diagnosis,
        "GFAP Volume": float(i % 2) + i * 0.02,
        "Iba1 Volume": float((i // 2) % 3),
    })

df = pd.DataFrame(rows)

result = iterative_model_sweep(
    data=df,
    target="Diagnosis",
    data_cols=["GFAP Volume", "Iba1 Volume"],
    max_features=1,
    model_families=["ridge_multinomial_logistic"],
    cv="stratified2",
    save=False,
    plot=False,
    top_n=3,
    verbose=False,
)

print(result["best_family"])
print(result["best_features"])
print(result["best_metrics"])
```

## Result

The result dictionary includes the best model family, selected feature tuple,
cross-validation metrics, ranked score tables, and the fitted estimator. With
`save=False`, `output_dir` is `None` and no model sweep files are written.

## Notes

This example is deliberately small. For real discovery work, increase the
sample size, review class balance, and save the run so the score tables and
manifest can be audited later.

## See Also

- [iterative_model_sweep](../functions/iterative_model_sweep.md)
- [Model summary plots](../plot-types/model-summary-plots.md)
- [Model sweep outputs](../outputs/model-sweep-outputs.md)
- [Classification](../statistics/classification.md)
