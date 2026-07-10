# Rhythm Plots

## Use This When

Use rhythm plots when the measurement depends on cyclic time, such as zeitgeber
time, clock hour, or month in a seasonal cycle.

`plot_cosinor` fits a cosine rhythm to one value column over time. 
`plot_acrophase_clock` displays per-subject circular phase values, such as
acrophase or activity onset, on a clock.

For full rhythm pipelines that write parameter tables and run-folder manifests,
use the `rhythm` pipeline page rather than these standalone plot pages.

## Input Data

Both standalone rhythm plots read a subject-level `summary` table from a
PyFLASH-like object or use a raw `pandas.DataFrame` directly.

`plot_cosinor` needs:

| Column | Meaning |
|---|---|
| value column | Numeric measurement to fit, passed as `column`. |
| `time_col` | Time variable. Numeric values, mapped labels, and labels with trailing digits are supported. |
| `group_col` | Optional group column for separate fits. |

`plot_acrophase_clock` needs:

| Column | Meaning |
|---|---|
| `phase_col` | Circular time value in the same units as `period`. |
| `group_col` | Optional group column for colour and circular group tests. |
| `radius_col` | Optional numeric radius, such as amplitude. |

## Main Functions

| Function | Registry name | Use |
|---|---|---|
| [`plot_cosinor`](../functions/plot_cosinor.md) | `cosinor` | Plot per-timepoint means and fitted cosinor curves. |
| [`plot_acrophase_clock`](../functions/plot_acrophase_clock.md) | `acrophase_clock` | Plot circular phase values and group-level phase summaries. |

## Common Options

| Option | Meaning |
|---|---|
| `period` | Cycle length in the units of the time or phase column. Use `24.0` for a daily clock. |
| `period_free` | Fit a free-running period in `plot_cosinor`. |
| `time_map` | Map categorical time labels such as `ZT0` or `WeekEight` to numbers. |
| `filter_by` / `specificity` | Filter rows or run a queue of row filters. |
| `palette` | Optional group colour mapping or palette. |
| `return_data` | Return fit or circular statistics alongside the figure. |
| `save_path`, `save_name`, `subfolder`, `montage` | Save-location controls used by standalone plots and pipelines. |

## Outputs

Both functions return a `matplotlib.figure.Figure` by default. With
`return_data=True`, `plot_cosinor` returns `(fig, fits)` and
`plot_acrophase_clock` returns `(fig, stats)`.

The rhythm plots emit structured describe/report records when the report layer
is active. With `save=True`, figures are saved through PyFLASH's standard figure
saving helper. `save_path` can override the base folder.

## Examples

Fit a 24-hour rhythm:

```python
from PyFLASH.plotting import plot_cosinor

fig, fits = plot_cosinor(
    batch,
    column="GFAP_IntDen",
    time_col="ZT",
    group_col="Diagnosis",
    period=24,
    save=False,
    return_data=True,
)
print(fits["Control"]["acrophase"])
```

Plot phase values on a clock:

```python
from PyFLASH.plotting import plot_acrophase_clock

fig, stats = plot_acrophase_clock(
    batch.summary,
    phase_col="Acrophase (h)",
    group_col="Diagnosis",
    radius_col="Amplitude",
    period=24,
    save=False,
    return_data=True,
)
print(stats["groups"])
```

## Interpretation

In a cosinor plot, the curve shows the fitted rhythm and the legend reports
amplitude, peak time, R squared, and a rhythmicity marker based on the
zero-amplitude test. A failed group fit is shown in the legend rather than
silently omitted.

In an acrophase clock without `radius_col`, all subjects sit on one visual ring;
radius is only jitter. Group direction arrows show mean phase and concentration.
With `radius_col`, radius becomes a real numeric value.

Clock times are circular. A phase near 23:30 and a phase near 00:30 are close
together even though their ordinary numeric difference is large.

## See Also

- [plot_cosinor](../functions/plot_cosinor.md)
- [plot_acrophase_clock](../functions/plot_acrophase_clock.md)
- [rhythm pipeline](../functions/rhythm.md)
- [Rhythm statistics](../statistics/rhythm.md)
- [Structured results](../statistics/structured-results.md)
