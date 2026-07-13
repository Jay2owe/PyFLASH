# ROI Selection

## Summary

`roi` chooses which ROI base summary to analyse, such as `"SCN"` or `"CTX"`.
It selects from `experiment.summaries`, not from individual rows in a single
summary table.

Use [`filter_by`](specificity.md) for row-level filters such as `Region`, `ROI`,
`ImageROI`, or `Hemisphere`. `specificity` is the legacy/internal alias.

## Used By

- ROI-aware summary plots such as [`plot_mean_bars`](../functions/plot_mean_bars.md),
  [`plot_matrices`](../functions/plot_matrices.md),
  [`plot_regressions`](../functions/plot_regressions.md),
  [`plot_radar`](../functions/plot_radar.md),
  [`plot_volcano`](../functions/plot_volcano.md),
  [`plot_superplot`](../functions/plot_superplot.md),
  [`plot_effect_forest`](../functions/plot_effect_forest.md), and
  [`plot_group_matrix`](../functions/plot_group_matrix.md).
- Pipelines such as [`correlation`](../functions/correlation.md),
  [`adjusted_correlation`](../functions/adjusted_correlation.md),
  [`data_overview`](../functions/data_overview.md),
  [`group_comparison`](../functions/group_comparison.md), and
  [`linear_model`](../functions/linear_model.md).
- Location and colocalisation plots that need an ROI context.
- Exclusion helpers that apply manual or detected exclusions to one ROI base.

## Accepted Values

| Option | Behavior |
|---|---|
| `None` | Use the function's default ROI behavior. Many standalone summary plots queue over all ROI bases in `experiment.summaries`; pipelines and exclusion helpers usually resolve only the first available ROI base. If no summaries are available, PyFLASH falls back to `"SCN"`. |
| String | Use one ROI base, for example `roi="SCN"`. |
| Iterable of strings | Queue over several ROI bases, for example `roi=["SCN", "CTX"]`, in functions that support ROI queues. |

For functions that read ROI-specific summary tables, the useful ROI base is a
key in `experiment.summaries`. The shared resolver currently accepts any string
as an ROI name; some summary helpers fall back to `experiment.summary` when that
string is not present in `experiment.summaries`. Check available keys before
assuming a mistyped ROI will raise an error. Raw DataFrame inputs created
through the adapter usually have one default ROI base, `"SCN"`, unless the
caller supplies a different `roi_base` or `summaries`.

## Examples

Run one ROI base:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(batch, data_cols=["GFAP_Count"], roi="SCN", save=False)
```

Run multiple ROI bases where queue mode is supported:

```python
figures = plot_mean_bars(
    batch,
    data_cols=["GFAP_Count"],
    roi=["SCN", "CTX"],
    save=False,
)
```

Filter rows within an ROI base:

```python
from PyFLASH import data_overview

result = data_overview(
    batch,
    data_cols=["GFAP_Count"],
    roi="SCN",
    filter_by={"Hemisphere": "LH"},
    save=False,
)
```

## Interactions

`roi` chooses the table; `filter_by` filters rows inside the chosen table.
Combining them is valid when the selected ROI summary still contains the
row-level column you filter on. `specificity` remains supported for older code.

Many standalone summary plots queue over every ROI base when `roi=None` and
`experiment.summaries` contains more than one base. Current high-level
pipelines and exclusion helpers usually resolve one ROI base by taking the
first resolved value. Check the function page before assuming `roi=None` means
"all bases" or before passing an ROI list.

When there is more than one ROI base, saved figures usually include the ROI
base as a top-level subfolder or filename context so outputs from different
bases do not overwrite each other.

## Common Errors

- Passing `roi="SCN1"` when the ROI base key is `"SCN"`. Current helpers may
  accept the string and fall back to the default summary instead of raising.
  Row-level region names such as `SCN1` belong in
  `filter_by={"Region": "SCN1"}` if that column exists.
- Expecting `roi` to filter marker-level image ROIs. Image-specific functions
  may use parameters such as `roi_filter`; check the function page.
- Passing a list of ROI bases to a helper that only handles one base.
- Using a raw DataFrame without supplying `summaries` and expecting several ROI
  bases to exist.

## See Also

- [ROI tables](../data-structures/roi-tables.md)
- [Summary table](../data-structures/summary-table.md)
- [Filter By and row filters](specificity.md)
- [Image table](../data-structures/image-table.md)
