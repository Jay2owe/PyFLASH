# plot_baseline_characteristics

## Summary

`plot_baseline_characteristics` renders a compact cohort baseline table from
explicitly named summary columns. Registry name: `baseline_characteristics`.

Use it for participant, animal, or sample-level metadata tables where the
columns should be chosen deliberately rather than inferred from project-specific
names.

## Example figure

<!-- gallery-example-code:start -->
Gallery render call (after `ex = build_example_data(fig_path=TMP)`, `exp = ex.experiment`, and `P = PyFLASH.plotting`):

```python
import numpy as np
from PyFLASH import from_dataframe

summary = ex.summary.copy()
summary["AgeYears"] = 70 + 3 * summary["x1"]
summary["Sex"] = np.where(np.arange(len(summary)) % 2, "Female", "Male")
summary["SleepTreatment"] = np.where(summary["Condition"].eq("C"), "Yes", "No")
baseline_exp = from_dataframe(
    summary,
    group_col="Condition",
    subject_col="AnimalName",
    fig_path=TMP,
)
P.plot_baseline_characteristics(
    baseline_exp,
    columns={
        "age": "AgeYears",
        "sex": "Sex",
        "sleep_treatment": "SleepTreatment",
    },
    factor="Condition",
    save=True,
)
```
<!-- gallery-example-code:end -->

![plot_baseline_characteristics example figure](../gallery/images/plot_baseline_characteristics.svg)

*Cohort baseline table across groups A/B/C. Rendered from the [synthetic example dataset](../examples/README.md).*

## Signature

```python
plot_baseline_characteristics(
    experiment,
    columns,
    factor="Diagnosis",
    groups=None,
    specificity=None,
    filter_by=None,
    include_all=True,
    title="Baseline characteristics",
    figsize=(11.5, 4.6),
    save=True,
    roi=None,
    conditions=None,
    condition_col="Condition",
    factor_cols=None,
    animal_col="AnimalName",
    group_list=None,
    group_col=None,
    group_cols=None,
    subject_col=None,
    dataframe_kwargs=None,
)
```

## Parameters

| Parameter | Meaning |
|---|---|
| `experiment` | Batch, experiment-like object, or raw DataFrame. |
| `columns` | Explicit baseline field mapping, such as age, sex, and treatment columns. |
| `factor` | Summary-table column used to split the table into groups. |
| `groups` | Optional group order/subset. |
| `filter_by` / `specificity` | Optional row filter before summarising. |
| `include_all` | Add an all-samples column before group columns. |
| `title`, `figsize`, `save` | Figure title, size, and save behavior. |
| `group_col`, `group_cols`, `subject_col`, `dataframe_kwargs` | DataFrame adapter metadata when passing a raw table. |

## Returns

With `save=True`, returns the saved SVG path. With `save=False`, returns the
Matplotlib figure.

## Example

```python
from PyFLASH.plotting import plot_baseline_characteristics

plot_baseline_characteristics(
    batch,
    columns={
        "age": "AgeYears",
        "sex": "Sex",
        "sleep_treatment": "SleepTreatment",
    },
    factor="Diagnosis",
    groups=["Control", "MCI", "AD"],
)
```

## Notes

This plot is describe-layer exempt because it is a descriptive table and does
not compute inferential statistics.

## See Also

- [Table and categorical summary plots](../plot-types/table-and-categorical-summary-plots.md)
- [Conditions and factors](../parameters/conditions-and-factors.md)
- [Figure folders](../outputs/figure-folders.md)
