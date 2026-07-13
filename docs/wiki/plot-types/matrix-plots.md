# Matrix Plots

## Use This When

Use matrix plots when the question is about many pairwise relationships at
once. They are the compact overview for "which markers move together?", "does a
marker relate to a second set of variables?", or "does this relationship change
between groups?".

Matrix plots are exploratory relationship views. For a full correlation run
with tables, significance gates, selected regression plots, manifests, and
montages, use the correlation pipelines linked below.

## Input Data

Matrix plots read numeric columns from the subject-level summary table by
default. They accept a processed `Batch` or experiment-like object with
`.summary`; the main matrix functions also accept a raw `pandas.DataFrame` and
wrap it internally when you pass `group_col` and `subject_col`.

`plot_matrices` can also read a marker-level table through `marker=...`.
`roi=...` selects an ROI summary when the object has ROI-specific summaries.
`filter_by`/`specificity` restricts rows before correlations are calculated.

## Main Functions

| Function | Registry name | Use |
|---|---|---|
| [`plot_matrices`](../functions/plot_matrices.md) | `matrices` | Square correlation heatmaps for one selected column set. |
| [`plot_rect_matrices`](../functions/plot_rect_matrices.md) | `rect_matrices` | Rectangular heatmaps for Y columns against a separate X column set. |
| [`plot_matrix_differences`](../functions/plot_matrix_differences.md) | `matrix_differences` | Difference heatmaps comparing group correlation matrices. |

## Common Options

Use [`data_cols`](../parameters/column-selection.md) for exact summary columns,
or `data_col_contains`, `data_col_regex`, and `data_col_exclude` for discovery.
Rectangular and difference matrices also support `against_data_cols` and the
matching `against_*` discovery options for the second axis.

Use [`split_by`](../parameters/conditions-and-factors.md) or `factor` to choose
whether panels are by condition, by a factor such as `Diagnosis`, or pooled as
`all`. Use [`filter_by`](../parameters/specificity.md) for row filters. The
square and rectangular matrix functions support filter queues; matrix
differences resolve one filter context per call.

`correlation` accepts Pearson, Spearman, or Kendall methods. The aliases
`"pearson"`, `"p"`, `"spearman"`, `"s"`, `"kendall"`, and `"k"` are normalized.

`triangle`, `show_diagonal`, `show_values`, and `value_format` control compact
matrix rendering. `share_columns_across_panels=True` keeps comparable axes
across panels by dropping columns that are not valid in every panel.

## Outputs

The square and rectangular plot functions return dictionaries containing
per-panel correlation statistics. With `save=True`, they write SVG figures below
the input object's figure folder, usually in `Matrices/` or
`Rectangular/Matrices/` subfolders.

`plot_matrix_differences` returns a manifest-style dictionary and an in-memory
`differences` table. With `save=True`, it writes SVG matrices, CSV tables, and a
`manifest.json` into `Matrix Differences/<run_label>/`.

These registry entries are currently marked as describe-layer `unreviewed` in
`PyFLASH.spec`: the figures and return objects contain useful numbers, but they
do not yet emit structured report records.

## Examples

Square correlation matrix:

```python
from PyFLASH.plotting import plot_matrices

matrices = plot_matrices(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count", "NeuN_Count"],
    split_by="Condition",
    correlation="spearman",
    save=False,
)
```

Rectangular marker-vs-behavior view:

```python
from PyFLASH.plotting import plot_rect_matrices

rect = plot_rect_matrices(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    against_data_cols=["Age", "BehaviourScore"],
    split_by="all",
    show_values=True,
    save=False,
)
```

Compare matrices between groups:

```python
from PyFLASH.plotting import plot_matrix_differences

diff = plot_matrix_differences(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count", "NeuN_Count"],
    factor="Diagnosis",
    comparisons=["1-2"],
    run_label="diagnosis_matrix_difference",
)
```

## Interpretation

Correlation cells show association, not causation. A strong coefficient can
come from a biological relationship, shared normalization, a batch effect, or a
small number of influential subjects.

Significance stars in square and rectangular matrices come from the selected
correlation test for each visible pair. Difference matrices use Fisher r-to-z
tests only for Pearson correlations; Spearman and Kendall difference matrices
are descriptive in the current implementation.

When panels use different valid column sets, comparing matrix shape can be
misleading. Keep `share_columns_across_panels=True` for comparable panels, or
set `blank_panel_on_nan=True` in rectangular matrices when retaining the full
requested grid is more important.

## See Also

- [Regression Plots](regression-plots.md)
- [Column selection](../parameters/column-selection.md)
- [Filter By and row filters](../parameters/specificity.md)
- [Correlation statistics](../statistics/correlation.md)
- [`correlation`](../functions/correlation.md)
- [`adjusted_correlation`](../functions/adjusted_correlation.md)
