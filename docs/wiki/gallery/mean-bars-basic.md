# Mean Bars Basic

## Goal

Compare one numeric marker summary between two groups from a small table.

## Code

```python
import pandas as pd
from PyFLASH.plotting import plot_mean_bars

df = pd.DataFrame({
    "Subject": ["C1", "C2", "C3", "A1", "A2", "A3"],
    "Diagnosis": ["Control", "Control", "Control", "AD", "AD", "AD"],
    "GFAP Volume": [1.0, 1.1, 0.9, 2.0, 2.2, 2.1],
})

result = plot_mean_bars(
    df,
    data_cols=["GFAP Volume"],
    group_col="Diagnosis",
    subject_col="Subject",
    points=True,
    save=False,
    save_normality=False,
)

print(result.keys())
```

## Result

PyFLASH wraps the DataFrame internally, draws one bar chart, and returns a
result dictionary. With `save=True`, the SVG and statistics files would be
written below the object's figure folder.

## Notes

For reusable analysis scripts, wrap the table once with
[`from_dataframe`](../functions/from_dataframe.md). Direct DataFrame input is
convenient for quick one-off plots.

## See Also

- [plot_mean_bars](../functions/plot_mean_bars.md)
- [Mean bars](../plot-types/mean-bars.md)
- [Column selection](../parameters/column-selection.md)
- [Saving](../parameters/saving.md)
