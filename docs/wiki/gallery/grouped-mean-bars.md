# Grouped Mean Bars

## Goal

Plot a crossed design table while summarizing one factor, here diagnosis, from
rows that also carry sex labels.

## Code

```python
import pandas as pd
from PyFLASH.plotting import plot_mean_bars

df = pd.DataFrame({
    "Subject": ["C1", "C2", "C3", "C4", "A1", "A2", "A3", "A4"],
    "Diagnosis": ["Control", "Control", "Control", "Control",
                  "AD", "AD", "AD", "AD"],
    "Sex": ["Female", "Female", "Male", "Male",
            "Female", "Female", "Male", "Male"],
    "GFAP Volume": [1.0, 1.1, 0.9, 1.2, 2.0, 2.2, 2.1, 2.3],
})

result = plot_mean_bars(
    df,
    data_cols=["GFAP Volume"],
    group_cols=["Diagnosis", "Sex"],
    subject_col="Subject",
    split_by="Diagnosis",
    legend=True,
    save=False,
    save_normality=False,
)

print(result.keys())
```

## Result

The DataFrame adapter derives crossed internal conditions from `Diagnosis` and
`Sex`, then `split_by="Diagnosis"` tells `plot_mean_bars` to summarize the bars
by diagnosis rather than every crossed condition.

## Notes

Use `group_cols` when the table has separate factor columns instead of a single
prebuilt `Condition` column. For full control over labels, colors, styles, and
planned comparisons, build a `groupList` with `GroupBuilder.cross`.

## See Also

- [from_dataframe](../functions/from_dataframe.md)
- [plot_mean_bars](../functions/plot_mean_bars.md)
- [Mean bars](../plot-types/mean-bars.md)
- [Groups and factors](../parameters/conditions-and-factors.md)
