# Missing Columns

## Symptoms

- A plot raises `No columns matched the provided names: ...`.
- A plot raises `No columns matched the provided filter criteria.`.
- A plot raises `No plottable numeric columns were found after filtering.`.
- `run_spec` warns `column '<name>' not found in experiment.summary`.
- The UI table header shows a readable label, but the same text is not found
  from Python.

## Likely Causes

- The name is a formatted **display label** (for example `GFAP volume total`)
  rather than the raw DataFrame column (`GFAP_VolumeTotal`). Display labels come
  from `format_summary_for_display` and are never valid selectors.
- The ROI prefix differs from the table you selected, such as `SCN` vs `OC`. A
  `Batch` can hold several summary tables in `batch.summaries`.
- `data_cols` uses an exact-name path that resolves a few legacy aliases; a
  typo or renamed column still fails.
- A raw `pandas.DataFrame` input is missing the identifier columns PyFLASH
  expects (`AnimalName`/`subject_col`, `Condition`/`group_col`, or factor
  columns).
- A selected column is present but non-numeric or sentinel-filled, so it is
  dropped before a numeric-only plot.

## Fix

Print the real column names from the exact table being plotted and select from
those:

```python
print(list(batch.summary.columns))
```

Use exact raw names with `data_cols` (the preferred selector):

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(batch, data_cols=["GFAP_Count", "Iba1_Count"], save=False)
```

When exact names are fragile, discover a family by substring or regex and prune
with an exclude term:

```python
plot_mean_bars(
    batch,
    data_col_contains=["_Count"],
    data_col_exclude=["Raw"],
    save=False,
)
```

For a raw DataFrame, name the identifier columns so the adapter can build the
summary:

```python
plot_mean_bars(
    df,
    data_cols=["GFAP_VolumeTotal"],
    group_col="Diagnosis",
    subject_col="Mouse ID",
    save=False,
)
```

## Check

For a `Batch`, inspect which ROI tables exist and the dtypes of the active one:

```python
print(list(batch.summaries.keys()))   # e.g. ['SCN', 'OC']
print(batch.summary.dtypes)
```

If the requested column is `object` dtype, it holds text or sentinels (see
[Data structures](../data-structures/README.md)) and will be dropped for numeric
plots. For a DataFrame input, confirm the identifier columns are present:

```python
print([c for c in ["AnimalName", "Condition"] if c not in df.columns])
```

## Related Pages

- [Column selection](../parameters/column-selection.md)
- [Input objects](../parameters/input-objects.md)
- [Summary table](../data-structures/summary-table.md)
- [Filter by and row filters](../parameters/specificity.md)
- [from_dataframe](../functions/from_dataframe.md)
