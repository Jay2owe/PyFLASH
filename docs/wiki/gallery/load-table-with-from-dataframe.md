# Load Table With from_dataframe

## Goal

Wrap a clean subject-level table as a `DataFrameExperiment` so several PyFLASH
plots can reuse the same group definitions and output paths.

## Code

```python
import pandas as pd
from PyFLASH import GroupBuilder, from_dataframe
from PyFLASH.plotting import plot_mean_bars

df = pd.DataFrame({
    "Subject ID": ["C1", "C2", "C3", "A1", "A2", "A3"],
    "Diagnosis": ["Control", "Control", "Control", "AD", "AD", "AD"],
    "GFAP Volume": [1.0, 1.1, 0.9, 2.0, 2.2, 2.1],
    "Iba1 Volume": [0.8, 0.7, 0.9, 1.4, 1.5, 1.3],
})

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="grey")
    .add("AD", short="AD", color="red")
    .compare("Control", "AD")
    .build()
)

exp = from_dataframe(
    df,
    group_list=groups,
    group_col="Diagnosis",
    subject_col="Subject ID",
    fig_path="Results/Python Figures",
)

result = plot_mean_bars(
    exp,
    data_cols=["GFAP Volume", "Iba1 Volume"],
    save=False,
    save_normality=False,
)

print(exp.summary[["AnimalName", "Condition"]])
print(result.keys())
```

## Result

`from_dataframe` returns a PyFLASH-compatible object with a normalized
`summary`, a `condition_list`, and figure/data output paths. `plot_mean_bars`
returns the normal plot-run result dictionary and writes no files because
`save=False`.

## Notes

Use `group_col` and `subject_col` when the table uses project-specific column
names. The normalized object stores those as `Condition` and `AnimalName` for
the rest of PyFLASH.

## See Also

- [from_dataframe](../functions/from_dataframe.md)
- [plot_mean_bars](../functions/plot_mean_bars.md)
- [DataFrameExperiment](../object-types/dataframe-experiment.md)
- [Summary table](../data-structures/summary-table.md)
