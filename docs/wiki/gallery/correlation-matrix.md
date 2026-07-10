# Correlation Matrix

## Goal

Draw a square correlation heatmap for three numeric summary columns.

## Code

```python
import pandas as pd
from PyFLASH.plotting import plot_matrices

df = pd.DataFrame({
    "Subject": [f"S{i:02d}" for i in range(1, 9)],
    "Diagnosis": ["Control"] * 4 + ["AD"] * 4,
    "GFAP Volume": [1.0, 1.2, 1.4, 1.5, 2.0, 2.1, 2.4, 2.5],
    "Iba1 Volume": [0.8, 0.9, 1.1, 1.2, 1.6, 1.7, 1.9, 2.1],
    "DAPI Count": [110, 115, 118, 121, 140, 138, 145, 148],
})

result = plot_matrices(
    df,
    data_cols=["GFAP Volume", "Iba1 Volume", "DAPI Count"],
    group_col="Diagnosis",
    subject_col="Subject",
    split_by="all",
    correlation="spearman",
    show_values=True,
    save=False,
)

combined = result.get("Combined") or next(iter(result.values()))
print(combined["correlations"].keys())
```

## Result

The result dictionary contains a combined matrix panel with pairwise
correlation entries such as `GFAP Volume vs Iba1 Volume`. No SVG is written
because `save=False`.

## Notes

Use `split_by="Diagnosis"` when you want one matrix per diagnosis group. Use
the [`correlation`](../functions/correlation.md) pipeline when you also need
CSV matrices, p/q-value gates, regression plots, and a manifest.

## See Also

- [plot_matrices](../functions/plot_matrices.md)
- [Matrix plots](../plot-types/matrix-plots.md)
- [correlation](../functions/correlation.md)
- [Correlation statistics](../statistics/correlation.md)
