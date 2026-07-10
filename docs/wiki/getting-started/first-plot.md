# First Plot

## Goal

Make one summary plot from a loaded PyFLASH object or table.

## Before You Start

- Create a `Batch` with [First batch](first-batch.md), or create a
  `DataFrameExperiment` with [First table-backed batch](first-table-batch.md).
- Know at least one exact column name in `batch.summary` or `exp.summary`.
- Start with `save=False` while you check that the column name is right.

## Steps

```python
from PyFLASH.plotting import plot_mean_bars

print(batch.summary.columns.tolist())

result = plot_mean_bars(
    batch,
    data_cols=["GFAP Volume"],
    save=False,
    save_normality=False,
)

print(type(result))
```

When the plot call works, write figures to the object's figure folder:

```python
plot_mean_bars(
    batch,
    data_cols=["GFAP Volume"],
    save=True,
)
```

## Check It Worked

- With `save=False`, the call returns without creating figure files.
- With `save=True`, figures are written below `batch.fig_path`.
- If the column name is wrong, choose a name printed from
  `batch.summary.columns`.

## Next

- [plot_mean_bars](../functions/plot_mean_bars.md)
- [Mean bars plot type](../plot-types/mean-bars.md)
- [First plot spec](first-plot-spec.md)
- [Where results go](where-results-go.md)
