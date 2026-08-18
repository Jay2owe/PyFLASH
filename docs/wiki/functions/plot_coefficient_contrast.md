# plot_coefficient_contrast

## Summary

`plot_coefficient_contrast` contrasts how the **regression coefficient** of an
anchor variable `x` on each of several measures `y` changes across an ordered
grouping factor — the slope counterpart of
[`plot_correlation_contrast`](plot_correlation_contrast.md). Every non-reference
group is tested against the reference with the **OLS `x * group` interaction**.
It is registered as `coefficient_contrast` in `PyFLASH.spec.PLOT_REGISTRY`, and
shares its renderer with the correlation contrast so the two plots stay visually
identical apart from the y-axis quantity.

Use it when the claim you want to make is about **slopes** ("volume declines with
age more steeply in AD than in controls") rather than about **correlations**
("volume predicts activity in controls but not in AD").

## Which contrast plot do I want?

The two plots answer different questions and can legitimately disagree.

| | `plot_correlation_contrast` | `plot_coefficient_contrast` |
|---|---|---|
| Node value | correlation (r / rho / tau) | coefficient (standardized beta or raw slope) |
| Between-group test | Fisher r-to-z | OLS `x * group` interaction |
| Estimated | within each group separately | one model over both groups |
| Residual variance | per group | pooled across the two groups |
| Covariates | residualised into a partial correlation | additive model terms |
| Claim it supports | "the association is present here, absent there" | "the slope is steeper here than there" |

They disagree when groups differ in spread: a correlation is scale-free, a slope
is not. If one group has a compressed outcome range, its correlation can collapse
while its slope barely moves (or vice versa). Report whichever matches the
sentence you are writing, and say which one you used.

With **no covariates**, `value="beta"` equals Pearson's r exactly, so the two
plots put their nodes on the same axis and are directly comparable. Adding
covariates separates them: a partial correlation divides by residual SDs, a
standardized coefficient by total SDs.

## Signature

```python
plot_coefficient_contrast(
    experiment,
    x,
    y=None,
    filtered_columns=None,
    data_cols=None,
    by="conditions",
    factor=None,
    reference=None,
    control=None,
    value="beta",
    covariates=None,
    tail="two",
    rank=False,
    group_order=None,
    significance="lines",
    min_n=4,
    palette=None,
    column_labels=None,
    x_axis_width_scale=0.8,
    node_size=10.0,
    show_ci=True,
    ci_alpha=0.05,
    show_stats_summary=True,
    stats_summary_max_items=10,
    specificity=None,
    split_by=None,
    filter_by=None,
    roi=None,
    save=True,
    column_strings=None,
    regex_string=None,
    exclude="",
    ...dataframe adapter arguments...
)
```

## Key parameters

| Parameter | Meaning |
|---|---|
| `x` | Anchor column regressed against every measure (one column). |
| `y` | Measure column(s). If `None`, discovered from `filtered_columns` / `column_strings` / `regex_string`. |
| `factor` | Grouping factor whose ordered levels form the x-axis (e.g. `"Diagnosis"`). |
| `reference` / `control` | Baseline group for every contrast. Defaults to the first group. |
| `value` | `"beta"` (standardized coefficient, default) or `"slope"` (raw y-per-x units). |
| `covariates` | Additive adjustment columns. Numeric used as-is, categorical one-hot encoded. |
| `tail` | `"two"` (default), `"greater"`/`"less"` for a pre-specified direction, or `"one"` to halve in the observed direction. |
| `rank` | Rank-transform x and y first, for a monotonic (Spearman-flavoured) contrast. |
| `significance` | `"lines"` (default; one comparison line per significant measure per group), `"stars"`, `"omnibus"`, or `None`. |
| `x_axis_width_scale` | Multiplier for the plotted x-axis/data-region width only. Lower values pull group ticks closer together without changing the figure size; `1.0` restores the original spacing. |
| `node_size` | Marker diameter for the group nodes, in points (default `10.0`). |
| `show_ci` | Draw per-node confidence intervals with short horizontal caps (default `True`). |
| `ci_alpha` | Alpha level for confidence intervals; `0.05` draws 95% intervals. |
| `show_stats_summary` | Draw the removable right-side block with exact numbers (default `True`). |
| `stats_summary_max_items` | Cap on listed rows in that block (default `10`). |

### A note on `tail`

One-sided tests are only valid when the direction was chosen **before** seeing
the data. `"greater"` and `"less"` name that direction explicitly and are the
honest form; `"one"` simply halves the two-sided p-value in whichever direction
was observed, and should only be used when you can state the prediction you made
in advance. The chosen tail is recorded in the stats side-summary so the figure
carries its own provenance.

## Stats side-summary

Following the PyFLASH side-summary contract, the graph itself carries only
compact marks (stars, comparison lines, or omnibus brackets) while the exact
numbers live in a removable right-side block:

- test name (`OLS x*group interaction`) and tail
- value mode (standardized beta / raw slope, and whether ranked)
- reference group, contrast count, and how many reached p < 0.05
- per-group ACAT omnibus p-values
- per-contrast rows: both coefficients with their confidence intervals, `n`, the
  difference with its standard error, and the exact p-value

Set `show_stats_summary=False` for a clean graph, or lower
`stats_summary_max_items` to cap the listed rows.

## Node confidence intervals

By default, each node carries a confidence interval for the plotted coefficient.
For `value="slope"` this is in raw y-per-x units; for `value="beta"` the same
within-group OLS interval is scaled into standardized beta units. The caps are
kept short so the interval reads clearly without making the horizontal handles
too wide. Set `show_ci=False` to hide them.

## Plot width

This plot shares its renderer with
[`plot_correlation_contrast`](plot_correlation_contrast.md), so it shares its
geometry: the figure canvas is the standard one, but the plotted data region is
deliberately narrow — sized from the x-span so the gap between group ticks stays
the same whether there are two groups or five. The legend and stats block sit in
the space this frees on the right. Use `x_axis_width_scale` to tune that plotted
x-axis width without changing the total figure size.

## Examples

Slopes across a disease spectrum, contrasted against controls:

```python
P.plot_coefficient_contrast(
    exp,
    x="Age",
    y=["HypothalamicVolume"],
    factor="Diagnosis",
    reference="Control",
    value="slope",
    significance="lines",
)
```

Standardized, covariate-adjusted, with a pre-specified direction:

```python
P.plot_coefficient_contrast(
    exp,
    x="Age",
    y=["HypothalamicVolume"],
    factor="Diagnosis",
    reference="Control",
    covariates=["Sex"],
    tail="less",           # predicted a priori: steeper decline in disease
)
```

## Describe layer

Registered as `DESCRIBE_COVERED`. Each finite per-group coefficient is emitted as
a correlation record (`x`, `y`, `group`, `n`, `r`, `method`) when the
`PyFLASH.report` collector is armed, so the numbers behind the figure are
recoverable without re-reading the image.

## Related

- [`plot_correlation_contrast`](plot_correlation_contrast.md) — the correlation counterpart.
- [`plot_regressions`](plot_regressions.md) — the underlying per-group scatter and fit.
- `plot_linear_model_coefficient_forest` — coefficients with confidence intervals
  from a fitted model. Pass `terms=":"` to draw interaction terms only, which
  keeps main effects on a different scale from flattening them.
