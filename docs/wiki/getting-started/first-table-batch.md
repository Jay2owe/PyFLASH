# First Table-Backed Batch

## Goal

Wrap an already-clean table in a PyFLASH-compatible object.

## Before You Start

- Use this path when you already have a `pandas.DataFrame`.
- The table should include one subject or sample ID column.
- The table should include one group column, or factor columns for a crossed
  design.

## Steps

```python
import pandas as pd
from PyFLASH import GroupBuilder, from_dataframe
from PyFLASH.plotting import plot_mean_bars

df = pd.DataFrame({
    "Subject ID": ["C1", "C2", "A1", "A2"],
    "Diagnosis": ["Control", "Control", "AD", "AD"],
    "GFAP Volume": [1.0, 1.1, 2.0, 2.2],
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
    fig_path=r"C:\path\to\results\Python Figures",
)

plot_mean_bars(exp, data_cols=["GFAP Volume"], save=False)
```

You can also pass a raw DataFrame directly to supported summary plots:

```python
plot_mean_bars(
    df,
    data_cols=["GFAP Volume"],
    group_col="Diagnosis",
    subject_col="Subject ID",
    save=False,
)
```

## Check It Worked

- `exp` is a `DataFrameExperiment`.
- `exp.summary` contains PyFLASH's standard `AnimalName` and `Condition`
  columns.
- The direct DataFrame plot call works without importing raw ImageJ folders.

## Next

- [from_dataframe](../functions/from_dataframe.md)
- [First plot](first-plot.md)
- [plot_mean_bars](../functions/plot_mean_bars.md)
- [Object model](../object-model.md)
