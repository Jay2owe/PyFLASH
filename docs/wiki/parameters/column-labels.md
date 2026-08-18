# Column Labels

## Summary

`column_labels` renames the columns/measures a plot *displays* — its legend
entries, axis labels, annotations, and matrix headers — without changing which
columns are analysed. It is the one shared way to override display names across
every plot; do not look for a plot-specific `measure_labels`/`data_labels`.

Renaming is cosmetic: the underlying column identity is untouched. Palette keys,
[structured (describe-layer) records](../statistics/structured-results.md), saved
CSV/data tables, and save filenames all keep the raw column names. Only the text
drawn on the figure changes.

## Accepted Values

| Form | Meaning |
|---|---|
| `{column: label}` dict | Rename individual columns. Keys are the plotted column names (e.g. `"GFAP_Count"`); any column not in the dict keeps its house display name. This is the recommended form. |
| positional list | One label per plotted column, in order. Its length must match the number of plotted columns or a `ValueError` is raised. |
| `None` (default) | No override — the house display-name logic applies. |

Keys match either the raw column name or its `.expN`-suffixed form. Values are
used verbatim (they bypass the house rewrites and the `minimal` shortening).

## Used By

Every plot that renders column-derived text accepts `column_labels` — bars,
regressions, radar, volcano, matrices (`plot_matrices`, `plot_rect_matrices`,
`plot_multivariable_regression_matrix`, `plot_matrix_differences`,
`plot_group_matrix`, `plot_model_result_matrix`), forests
(`plot_effect_forest`, `plot_linear_model_coefficient_forest`),
`plot_correlation_contrast`, `plot_superplot`, `plot_marker_pca`,
`plot_timecourse`, `plot_cosinor`, distribution plots, and the coloc plots.

Pure-visual plots with no column-derived text — raw image panels, the condition
key, spatial location maps — do not take it.

## Examples

Rename specific measures in a slopegraph legend:

```python
from PyFLASH.plotting import plot_correlation_contrast

plot_correlation_contrast(
    batch,
    x="Volumeanterior-inferiorHT",
    y=["Totalcounts", "Amplitude", "Avgactivityactivephase(M10)"],
    factor="Diagnosis",
    reference="Control",
    column_labels={
        "Totalcounts": "Total activity",
        "Amplitude": "Rhythm amplitude",
        "Avgactivityactivephase(M10)": "Active-phase (M10)",
    },
    save=False,
)
```

Positional list on a bar chart (one label per plotted column, in order):

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    column_labels=["Astrocytes", "Microglia"],
    save=False,
)
```

## Interactions

- `column_labels` renames the **columns/measures** a plot draws. To relabel the
  **values** of a categorical axis (e.g. season names in
  [`plot_category_counts`](../functions/plot_category_counts.md)), use that plot's
  `category_labels`; the two are independent.
- Set colours per column with `palette={column: colour}` and names per column with
  `column_labels={column: label}` — both are keyed by the raw column name, so the
  same keys drive both.
- Labels are display-only, so a renamed column still selects, filters, and saves
  under its real name. Use the real column name in `data_cols`, `filter_by`, and
  when reading back saved tables.

## See Also

- [Column selection](column-selection.md)
- [Structured results](../statistics/structured-results.md)
- [Summary table](../data-structures/summary-table.md)
