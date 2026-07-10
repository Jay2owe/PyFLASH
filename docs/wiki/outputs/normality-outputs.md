# Normality Outputs

## Summary

Normality outputs record whether numeric values look compatible with
parametric tests. PyFLASH writes two different normality output families:

- plot-level PNG diagnostics from group-comparison statistics, such as a
  histogram plus Q-Q plot beside a bar chart;
- `data_overview` normality tables and optional summary figures inside a
  pipeline run folder.

These files are diagnostics, not final statistical conclusions by themselves.
Use them with sample sizes, outlier checks, and the selected test reported by
the corresponding plot or pipeline.

## Created By

| Function or workflow | Output |
|---|---|
| [`plot_mean_bars`](../functions/plot_mean_bars.md) and other plots that call `multipleComparisons(..., save_normality=True)` | `<metric>_normality.png` beside the saved plot and plot-statistics CSV. |
| `PyFLASH.stats.test_normality(...)` | In-memory normality decision, test-result dictionary, and optional Matplotlib figure used by the saving path. |
| [`data_overview`](../functions/data_overview.md) with `include_normality=True` | `normality.csv` in the run folder. |
| [`data_overview`](../functions/data_overview.md) with `plot_normality=True` | `Normality Summary.svg` in the run folder. |

## Folder Layout

Plot-level diagnostics are saved beside the plot's own figure/statistics
output, using the same output directory that the plot passed into
`multipleComparisons(...)`:

```text
<fig_path>/Bars/
  Period(h).svg
  Period(h).csv
  Period(h)_normality.png
```

The normality PNG is not written to `batch.data_path` when the plot has routed
statistics into a figure folder.

`data_overview` normality outputs live inside the pipeline run folder:

```text
<fig_path>/Data Overview Pipeline/<run_label>/
  manifest.json
  normality.csv
  Normality Summary.svg
```

Filter queues add a tag:

```text
normality_Diagnosis.AD.csv
Normality Summary_Diagnosis.AD.svg
```

## File Contents

### Plot-Level PNG

`<metric>_normality.png` contains:

| Panel | Meaning |
|---|---|
| Histogram | Distribution of all numeric values pooled across valid groups for that statistical comparison. |
| Q-Q plot | Quantile-quantile plot against a normal reference line. |
| Annotation text | P-values from available normality tests. D'Agostino-Pearson is shown as `n<8` when there are too few observations. |

The underlying test dictionary can include D'Agostino-Pearson (`DA`), modified
Anderson (`A`), Kolmogorov-Smirnov (`KS`), and Shapiro-Wilk (`SW_all`) entries.

### `data_overview` Normality Table

`normality.csv` is one row per group and numeric column. Important columns can
include:

| Column | Meaning |
|---|---|
| `group` | Group label used for the overview run, such as `All`, a condition, or a factor level. |
| `column` | Numeric metric tested. |
| `n` | Number of numeric values used. |
| `shapiro_p` | Shapiro-Wilk p-value when available. |
| `dagostino_p` | D'Agostino-Pearson p-value when sample size supports it. |
| `is_normal` | Boolean normality flag used by downstream overview summaries. |
| `suggested` | Test-family hint, such as parametric or non-parametric. |

The exact columns can evolve with the overview engine. Read the CSV header for
the run you are auditing.

### `Normality Summary.svg`

The overview figure is a heatmap-like summary of Shapiro p-values and suggested
test choices for the plotted subset of metrics.

## How To Reuse

Run a bar plot and save its normality diagnostic:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    batch,
    data_cols=["Period(h)"],
    save=True,
    save_normality=True,
)
```

Read the overview normality table:

```python
import pandas as pd

normality = pd.read_csv(
    "analysis-output/Results/Python Figures/Data Overview Pipeline/qc/normality.csv"
)
print(normality[["group", "column", "shapiro_p", "suggested"]].head())
```

Find all normality PNGs:

```python
from pathlib import Path

for path in Path(batch.fig_path).rglob("*_normality.png"):
    print(path)
```

## Notes

- Plot-level `save_normality=True` writes PNG diagnostics, not SVG.
- `data_overview(include_normality=False)` returns an empty normality table and
  does not write `normality.csv`.
- `data_overview(plot_normality=False)` can still write `normality.csv` if
  `include_normality=True`; it just skips the summary figure.
- Normality checks often have low power with small group sizes. Treat them as
  one input to the test-selection logic, not as a substitute for reading the
  reported test and sample size.

## See Also

- [data_overview](../functions/data_overview.md)
- [plot_mean_bars](../functions/plot_mean_bars.md)
- [Group comparisons](../statistics/group-comparisons.md)
- [Pipeline run folders](pipeline-run-folders.md)
