# Getting Started

## Goal

Get from an installed PyFLASH package to a loaded data object, one plot, and a
clear idea of where saved files go.

## Before You Start

- Use Python 3.9 or newer.
- Decide which data path you have:
  raw FLASH/ImageJ experiment folders, or an already-clean `pandas.DataFrame`.
- Keep local paths as placeholders while learning, then replace them with your
  own paths.

## Steps

| Step | Page | Use it when |
|---|---|---|
| 1 | [Installation](installation.md) | You need to install the package or the optional UI extra. |
| 2A | [First batch](first-batch.md) | You have FLASH/ImageJ export folders. |
| 2B | [First table-backed batch](first-table-batch.md) | You already have a clean table. |
| 3 | [First plot](first-plot.md) | You want one Python plot call. |
| 4 | [First plot spec](first-plot-spec.md) | You want a reusable YAML, TOML, or JSON plot recipe. |
| 5 | [Launch the UI](launch-the-ui.md) | You want the optional point-and-click interface. |
| 6 | [Where results go](where-results-go.md) | You need to find figures, workbooks, pickles, or pipeline runs. |

## Check It Worked

After the first three pages, this kind of script should run without import
errors:

```python
from PyFLASH import GroupBuilder, create_batch
from PyFLASH.plotting import plot_mean_bars

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="blue")
    .add("AD", short="AD", color="red")
    .compare("Control", "AD")
    .build()
)

batch = create_batch(
    "Example",
    groups,
    batch_path=r"C:\path\to\batch-output",
    experiments=r"C:\path\to\experiment-parent",
)

plot_mean_bars(batch, data_cols=["GFAP Volume"], save=False)
```

## Next

- [API reference](../api-reference.md)
- [Object model](../object-model.md)
- [create_batch](../functions/create_batch.md)
- [from_dataframe](../functions/from_dataframe.md)
- [plot_mean_bars](../functions/plot_mean_bars.md)
- [run_spec](../functions/run_spec.md)
