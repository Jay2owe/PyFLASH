# Plot From Python

## Goal

Call PyFLASH plot functions directly from a Python script, notebook, or
interactive session.

Use this workflow when you want a few explicit plots. Use
[plot from a spec](plot-from-spec.md) when you want a reusable batch of many
plots.

## Inputs

- A loaded `Batch`, `Experiment`, `MiniExperiment`, or `DataFrameExperiment`.
- Or a raw `pandas.DataFrame` for summary-first plots that support direct table
  input.
- Real summary-table column names for `data_cols`.
- Optional grouping metadata such as `group_col`, `group_cols`, and
  `subject_col` when using raw DataFrames.

## Minimal Path

```python
from PyFLASH import load_state
from PyFLASH.plotting import plot_mean_bars

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")

result = plot_mean_bars(
    batch,
    data_cols=["GFAP Volume"],
    save=False,
)
```

## Full Workflow

1. Load or create the data object:

```python
from PyFLASH import load_state

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")
print(batch.summary.columns.tolist())
```

2. Start with `save=False`. This lets you confirm columns, groups, and return
   values without writing files.

```python
from PyFLASH.plotting import plot_mean_bars

bars = plot_mean_bars(
    batch,
    data_cols=["GFAP Volume", "IBA1 Volume"],
    save=False,
)
```

3. Try a matrix or regression plot using exact column names:

```python
from PyFLASH.plotting import plot_matrices, plot_regressions

matrix = plot_matrices(
    batch,
    data_cols=["GFAP Volume", "IBA1 Volume", "DAPI Count"],
    split_by="Diagnosis",
    save=False,
)

regression = plot_regressions(
    batch,
    x="GFAP Volume",
    y="IBA1 Volume",
    factor="Diagnosis",
    save=False,
)
```

4. Filter rows when needed. A mapping is one AND filter; a list of mappings is
   queue mode for functions that support it.

```python
bars_scn_female = plot_mean_bars(
    batch,
    data_cols=["GFAP Volume"],
    filter_by={"Region": "SCN", "Sex": "Female"},
    save=False,
)
```

5. Save final figures once the preview is correct:

```python
plot_mean_bars(
    batch,
    data_cols=["GFAP Volume"],
    save=True,
)
```

6. For a raw table, pass grouping and subject columns explicitly:

```python
import pandas as pd
from PyFLASH.plotting import plot_mean_bars

df = pd.read_csv(r"C:\path\to\summary.csv")

plot_mean_bars(
    df,
    data_cols=["GFAP Volume"],
    group_col="Diagnosis",
    subject_col="Subject ID",
    save=False,
)
```

## Outputs

Most plot functions return a plot-specific Python object, often a dictionary of
tables, statistics, or paths. Do not assume every plot returns a Matplotlib
figure.

With `save=True`, figures are usually written below:

```text
<batch.fig_path>/
```

Specific plot families create subfolders such as `Bars`, `Matrices`,
`Regressions`, `Images`, or plot-specific output folders. Some plots also write
CSV statistics or PNG diagnostics next to the figure.

With `save=False`, no figure file should be written, but the computation still
runs and returns Python results.

## Troubleshooting

- Missing columns: inspect `batch.summary.columns` and use internal column
  names, not display labels from Excel.
- Raw DataFrame grouping fails: pass `group_col` and `subject_col`, or wrap the
  table with [`from_dataframe`](../functions/from_dataframe.md).
- No files appear: confirm `save=True` and inspect `batch.fig_path`.
- Unexpected row subset: check `filter_by` forms in
  [Filter By and row filters](../parameters/specificity.md).
- Image/location plots need imported image or coordinate metadata; summary-only
  batches may not have those tables.

## Next Steps

- [Plot from a spec](plot-from-spec.md)
- [plot_mean_bars reference](../functions/plot_mean_bars.md)
- [plot_matrices reference](../functions/plot_matrices.md)
- [plot_regressions reference](../functions/plot_regressions.md)
- [Plot types](../plot-types/README.md)
- [Figure folders](../outputs/figure-folders.md)
- [Saving and run labels](../parameters/saving.md)
