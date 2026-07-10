# Figure Folders

## Summary

Figure folders contain images written by PyFLASH plotting and pipeline
functions. Most ordinary plots save editable-text SVG files through
`PyFLASH.utils.save_fig(...)`. A few outputs are PNGs: normality Q-Q
diagnostics, pipeline overview montages, and model-sweep summary plots.

Use figure folders when you need publication figures, quick visual inspection,
or a way to locate plot-adjacent CSV statistics.

## Created By

| Function or workflow | What it writes |
|---|---|
| Plot functions such as [`plot_mean_bars`](../functions/plot_mean_bars.md), [`plot_regressions`](../functions/plot_regressions.md), [`plot_matrices`](../functions/plot_matrices.md), and [`plot_images`](../functions/plot_images.md) with `save=True` | SVG figures below `experiment.fig_path` or `batch.fig_path`. |
| `PyFLASH.utils.save_fig(...)` | The shared save helper used by most plot functions. It creates the destination folder only when saving is enabled. |
| Pipeline functions such as [`correlation`](../functions/correlation.md), [`adjusted_correlation`](../functions/adjusted_correlation.md), [`data_overview`](../functions/data_overview.md), [`group_comparison`](../functions/group_comparison.md), [`linear_model`](../functions/linear_model.md), and [`rhythm`](../functions/rhythm.md) | SVG figures inside a named pipeline run folder, plus `! Overview Montage.png` when montage capture is enabled. |
| Statistical plots routed through `multipleComparisons(..., save_normality=True)` | A `<metric>_normality.png` diagnostic beside the figure/stat CSV for that plot. |
| [`iterative_model_sweep`](../functions/iterative_model_sweep.md) with `plot=True` | PNG model-sweep summary figures inside the sweep output folder. |

## Folder Layout

For imported batches, the default figure root is:

```text
<batch-output>/Results/Python Figures/
```

For table-based or custom objects, `fig_path` can point somewhere else, but the
same rules apply.

General plot functions usually create a subfolder from the plot family and, for
single-marker plots, the marker name. The helper that builds plot subfolders
uses patterns such as:

```text
<fig_path>/
  Bars/
    Period(h).svg
    Period(h).csv
    Period(h)_normality.png
  Iba1/
    Bars/
      Iba1_Count.svg
  Matrices/
    Marker Correlation Matrix.svg
```

Pipeline figures are grouped by pipeline and run label:

```text
<fig_path>/
  Correlation Pipeline/
    scn_correlations/
      ! Overview Montage.png
      Matrices/
        Pearson Correlation Matrix.svg
        Pearson PValue Matrix.svg
        gate_matrix.csv
```

Specificity and group labels are encoded into file names rather than deep
folders, for example `Pearson Correlation Matrix_Diagnosis.AD.svg`.

## File Contents

| File type | Contents |
|---|---|
| `.svg` | Vector Matplotlib figure. PyFLASH sets `svg.fonttype='none'` at the save point so labels, ticks, legends, p-value annotations, and matrix text stay editable as text. Dense scatter/collection artists may be rasterized inside the SVG for file size. |
| `.png` | Raster figure. Used for normality diagnostics, pipeline montages, and model-sweep summaries. |
| Plot-side `.csv` | Statistics or data used by a specific plot, when the plot family writes one. For example, bar-chart statistics can sit beside the bar SVG. |
| `Matrices/*.csv` | Matrix values saved by pipeline matrix figures, such as coefficients, p-values, q-values, and gate masks. |

`save_fig(...)` sanitizes image names with `strip_name(...)`, appends `.svg`,
uses the optional `subfolder=...`, and returns the full path it attempted to
save.

## How To Reuse

List saved SVG files after a plotting session:

```python
from pathlib import Path

for path in Path(batch.fig_path).rglob("*.svg"):
    print(path)
```

Find the newest pipeline montage:

```python
from pathlib import Path

montages = sorted(Path(batch.fig_path).rglob("! Overview Montage.png"))
print(montages[-1] if montages else "No montage found")
```

Read a plot-side CSV, if the plot wrote one:

```python
import pandas as pd

stats = pd.read_csv("analysis-output/Results/Python Figures/Bars/Period(h).csv")
print(stats.head())
```

## Notes

- `save=False` on a plot call should avoid writing figures for that call.
- `Config.SAVE_MODE=False` disables writes inside `save_fig(...)`, but the
  function still returns the path it would use.
- `Config.SKIP_EXISTING=True` makes `save_fig(...)` skip an existing file unless
  the caller passes `skip_existing=False`.
- Long Windows paths are handled with an extended-length path prefix. PyFLASH
  warns when the visible figure path is near the usual Windows path-length
  limit.
- Plot functions and pipelines may create additional subfolders, but the shared
  rules are: figures live below `fig_path`, output names are sanitized, and
  row-filter/group tags go into file names.

## See Also

- [Saving parameters](../parameters/saving.md)
- [Pipeline run folders](pipeline-run-folders.md)
- [Normality outputs](normality-outputs.md)
- [Model sweep outputs](model-sweep-outputs.md)
