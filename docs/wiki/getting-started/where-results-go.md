# Where Results Go

## Goal

Know which PyFLASH calls return Python objects and which calls write files to
disk.

## Before You Start

- Keep `batch_path`, `pickle_path`, and `fig_path` explicit while learning.
- Use placeholder paths in examples, then replace them with your own project
  folders.

## Steps

Inspect the main output roots:

```python
print(batch.fig_path)
print(getattr(batch, "data_path", None))
print(getattr(batch, "export_path", None))
```

Common output locations:

| Output | Where it goes |
|---|---|
| Returned `Batch` or `DataFrameExperiment` | In Python memory. Assign it to a variable such as `batch` or `exp`. |
| Plot files with `save=True` | Below `batch.fig_path`, usually `C:\path\to\batch-output\Results\Python Figures`. |
| Plot calls with `save=False` | No figure file is written. Use this while testing. |
| Pickle cache from `create_batch(..., pickle_path=...)` | `<pickle_path>\<name>.pkl`, such as `C:\path\to\pickles\Example.pkl`. |
| Explicit pickle from `save_state(batch, path)` | The path you pass to `save_state`. |
| Excel exports from `batch.export_all_excel()` | The batch export folder, usually below `Exports`. |
| Pipeline runs | A named folder below `batch.fig_path`, with figures, CSVs, `manifest.json`, and an index file. |

## Check It Worked

After saving a plot, check the figure folder:

```python
from pathlib import Path

for path in Path(batch.fig_path).rglob("*.svg"):
    print(path)
```

If no files appear, confirm that the plot call used `save=True`.

## Next

- [plot_mean_bars](../functions/plot_mean_bars.md)
- [save_state](../functions/save_state.md)
- [Outputs](../outputs/README.md)
- [First plot](first-plot.md)
