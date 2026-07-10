# Group Comparison Plots

## Use This When

Use group comparison plots when you want to see group differences across one or
many markers without reading a large table. This family includes raw ROI/subject
views and descriptive effect-size summaries.

Use the standalone functions for quick visual checks. Use the
[`group_comparison`](../functions/group_comparison.md) pipeline when you need
inferential tests, multiple-testing correction, manifests, and structured
results.

## Input Data

`plot_effect_forest` and `plot_group_matrix` use subject-level summary columns.
They need a group column, selected numeric marker columns, and enough complete
subjects in the reference and comparison groups.

`plot_superplot` needs both subject-level summary information and ROI-level
marker data. It resolves each selected summary column back to a marker/ROI
table so it can show technical spread within each subject.

Typical inputs are:

| Input | Used by | Notes |
|---|---|---|
| `summary` rows with `AnimalName` and `Condition` | all functions | Subject-level grouping and effect-size computation. `AnimalName` is the internal subject/sample column. |
| selected numeric `data_cols` | all functions | Markers or measurements to compare. |
| `experiment.data[marker].df` | `plot_superplot` | ROI-level values used for raw points. |
| `group_col` / `subject_col` | DataFrame input | Needed when passing raw summary tables to effect forest or group matrix. |

## Main Functions

| Function | Registry name | Best for |
|---|---|---|
| [`plot_superplot`](../functions/plot_superplot.md) | `superplot` | Showing ROI-level points, subject means, and group means for selected markers. |
| [`plot_effect_forest`](../functions/plot_effect_forest.md) | `effect_forest` | Ranking group-vs-control Hedges g values with optional bootstrap confidence intervals. |
| [`plot_group_matrix`](../functions/plot_group_matrix.md) | `group_matrix` | Scanning marker x comparison effect sizes as a heatmap. |

## Common Options

| Option family | Parameters | Use |
|---|---|---|
| Column selection | `data_cols`, `data_col_contains`, `data_col_regex`, `data_col_exclude` | Choose summary columns to compare. See [column selection](../parameters/column-selection.md). |
| Grouping | `by`, `split_by`, `factor`, `group_col`, `group_cols` | Choose conditions or a factor level as the comparison grouping. |
| Row filtering | `filter_by` / `specificity`, `roi` | Restrict rows or ROI base before computing effects. |
| Reference group | `control` | Reference condition for effect forest and group matrix. Defaults to the first resolved group. |
| Effect calculation | `effect_ci`, `n_resamples`, `min_n`, `max_items` | Control bootstrap intervals, required sample size, and display size. |
| Saving | `save` | Write figures below the object's figure folder. See [saving](../parameters/saving.md). |

## Outputs

`plot_superplot` returns a dictionary keyed by selected marker/column name. Each
value is a Matplotlib figure. Columns without resolvable ROI-level data are
skipped.

`plot_effect_forest` returns one Matplotlib figure, or `None` when no finite
effect sizes are available. It can return a queue dictionary when several ROI
bases or row filters are requested.

`plot_group_matrix` returns one Matplotlib figure, `None`, or a queue
dictionary. The matrix cells show signed Hedges g for each marker and
group-vs-reference comparison.

When `save=True`, figures are written under `SuperPlot`, `Effect Forest`, or
`Group Matrix` subfolders. These standalone registry entries are describe-layer
exempt because they are descriptive views. The inferential capture path is the
[`group_comparison`](../functions/group_comparison.md) pipeline.

## Examples

Effect-size forest from a processed batch:

```python
from PyFLASH.plotting import plot_effect_forest

fig = plot_effect_forest(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    control="Control",
    save=False,
)
```

Effect-size matrix from a raw summary table:

```python
from PyFLASH.plotting import plot_group_matrix

fig = plot_group_matrix(
    df,
    data_cols=["GFAP_Count", "Iba1_Count"],
    group_col="Diagnosis",
    subject_col="Subject ID",
    control="Control",
    min_n=2,
    save=False,
)
```

SuperPlot when ROI-level data are available:

```python
from PyFLASH.plotting import plot_superplot

figures = plot_superplot(
    batch,
    data_cols=["GFAP_VolumeMean"],
    save=False,
)

for marker, fig in figures.items():
    print(marker, fig)
```

## Interpretation

Superplots separate ROI-level spread from subject-level means. Treat the subject
means as the biological unit; dense ROI point clouds do not increase the number
of independent subjects.

Effect forests rank marker/group contrasts by Hedges g. Positive values mean the
comparison group is higher than the reference group; negative values mean it is
lower. Confidence intervals are bootstrap estimates and can be omitted with
`effect_ci=False`.

Group matrices are designed for scanning. They show direction and magnitude, not
statistical significance, in the standalone function. Use the pipeline matrix
when you need p-value or q-value annotations.

## See Also

- [`plot_superplot`](../functions/plot_superplot.md)
- [`plot_effect_forest`](../functions/plot_effect_forest.md)
- [`plot_group_matrix`](../functions/plot_group_matrix.md)
- [`group_comparison`](../functions/group_comparison.md)
- [Mean bars](mean-bars.md)
- [Effect sizes](../statistics/effect-sizes.md)
- [Group comparisons](../statistics/group-comparisons.md)
