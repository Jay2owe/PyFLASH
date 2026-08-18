# Table And Categorical Summary Plots

## Use This When

Use these plots when the output is a compact table or categorical summary rather
than a continuous marker chart. They are useful for cohort description,
precomputed p-value audits, and checking how metadata levels are distributed
across groups.

## Main Functions

| Function | Registry name | Best for |
|---|---|---|
| [`plot_baseline_characteristics`](../functions/plot_baseline_characteristics.md) | `baseline_characteristics` | Clinical or cohort baseline table from explicit age/sex/treatment-style columns. |
| [`plot_significance_audit_table`](../functions/plot_significance_audit_table.md) | `significance_audit_table` | Generic precomputed p-value audit as a table or matrix. |
| [`plot_category_counts`](../functions/plot_category_counts.md) | `category_counts` | Grouped or stacked counts/proportions for one categorical metadata column. |

## Data Requirements

`plot_baseline_characteristics` and `plot_category_counts` read a summary table
from a `Batch`, experiment-like object, or raw `pandas.DataFrame` wrapped through
the DataFrame adapter.

`plot_significance_audit_table` is intentionally generic. It can read an
in-memory DataFrame, a CSV/Excel path, or a table-like object. Pass
`pvalue_cols` to choose exact p-value columns, or leave it unset to infer numeric
columns whose finite values look like p-values.

## Outputs

Baseline and significance-audit table outputs are saved under the standard
`Tables/` figure subfolder when `save=True`. Category counts are saved under a
categorical-counts plot subfolder. All saved SVGs use editable text through
PyFLASH's shared `save_fig` path.

`baseline_characteristics` and `category_counts` are describe-layer exempt
because they are descriptive summaries. `significance_audit_table` is
describe-layer covered because it emits structured p-value audit records when
the report collector is active.

## Examples

Baseline table:

```python
from PyFLASH.plotting import plot_baseline_characteristics

plot_baseline_characteristics(
    batch,
    columns={"age": "Age", "sex": "Sex", "sleep_treatment": "SleepTreatment"},
    factor="Diagnosis",
)
```

Generic p-value audit:

```python
from PyFLASH.plotting import plot_significance_audit_table

plot_significance_audit_table(
    audit_table=audit_df,
    row_label_col="metric",
    pvalue_cols=["p_age", "p_sex", "p_treatment"],
    aesthetic="table",
)
```

Categorical counts:

```python
from PyFLASH.plotting import plot_category_counts

plot_category_counts(
    batch,
    category="Sex",
    factor="Diagnosis",
    kind="stacked",
    normalize=True,
)
```

## See Also

- [Mean bars](mean-bars.md)
- [Column selection](../parameters/column-selection.md)
- [Conditions and factors](../parameters/conditions-and-factors.md)
- [Figure folders](../outputs/figure-folders.md)
