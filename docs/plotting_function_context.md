# PyFLASH Plotting Function Context

This file summarizes the canonical pattern for adding a new plotting function
to `PyFLASH/plotting.py`. Keep new plotters close to this shape unless the plot
needs a different data source such as marker-level raw object data or images.

## Public wrapper shape

Most summary-level plotters should expose:

```python
def plot_name(experiment, filtered_columns=None,
              by="conditions", factor=None,
              specificity=None, roi=None, save=True,
              combine=False,
              column_strings=None, regex_string=None, exclude="",
              ...plot_specific_options...):
```

Use `filtered_columns` as the explicit list of summary columns. Use
`column_strings`, `regex_string`, and `exclude` as the alternate discovery path
via `_resolve_filtered_columns(...)`. This keeps notebooks, specs, and the UI
consistent with `plot_mean_bars`, `plot_matrices`, and `plot_volcano`.

## Common parameters

`experiment`: Batch, Experiment, or MiniExperiment with `.summary`,
`.condition_list`, and `.fig_path`.

`filtered_columns`: Explicit summary-column names. Resolve with
`_resolve_filtered_columns(...)` so case-insensitive aliases and legacy column
aliases work.

`column_strings`: Substring include filter passed to `get_columns(...)` when
`filtered_columns` is not supplied.

`regex_string`: Regex include filter passed to `get_columns(...)`.

`exclude`: Substring exclusion filter passed to `get_columns(...)`.

`by`: Iteration mode when `factor` is not supplied. For summary plots this is
normally `"conditions"`.

`factor`: Factor-column grouping override, e.g. `"Genotype"`. If set, wrappers
normally use `level = "factors"` and pass `factor=factor` to `run(...)`.

`specificity`: Optional row filter tuple, e.g. `("Time", "WeekEight")`.
Queue mode must also work: `[("Time", "WeekFour"), ("Time", "WeekEight")]`.
Implement queue handling before calling `run(...)`, returning a dict keyed by
specificity tuple.

`roi`: ROI-base selector. Resolve first with `_resolve_roi_bases(...)`. If
multiple bases are returned, recurse once per ROI and return a dict keyed by
ROI base.

`save`: If true, save with `save_fig(...)` into `experiment.fig_path`.

`combine`: Existing convention for overlaying all conditions/factor groups into
one figure. With `combine=False`, save one figure per iterated group. With
`combine=True`, save one combined figure after the last group has been drawn.

## Wrapper control flow

Use this order:

1. Resolve ROI queue with `_resolve_roi_bases(...)`; recurse per ROI.
2. Resolve/filter columns or other queued scalar/list inputs.
3. Resolve specificity queue with `_is_specificity_queue(...)`; recurse per
   specificity tuple. If sibling plots must share scales, compute the shared
   reference before recursion and pass it through an internal `_...` parameter.
4. Choose `level = "factors" if factor else by`.
5. Define `setup(ctx, state)` to create or clear figures/axes and initialize
   progress with `_init_progress_state(...)` and `_progress_start_item(...)`.
6. Define `teardown(ctx, state, results)` to save/close figures and call
   `_progress_finish_item(...)`.
7. Call `run(experiment, over=level, action=your_action, ...)`.
8. Close any shared reusable figure after `run(...)`.

## Action function contract

Action functions should be named `name_action(ctx: Context, state: dict, ...)`.
They draw one panel/group and return a small result dict.

Use:

```python
source_df = ctx.factor_df if ctx.factor_value is not None else ctx.condition_df
group_name, group_color = _resolve_group_label_color(ctx)
```

Always convert data with `_to_numeric_excluding_not_included(...)` so
`NOT_INCLUDED_IN_EXPERIMENT` rows are handled consistently.

Use `_resolve_action_axis(state, idx)` instead of directly indexing axes.

## Saving

Use `build_subfolder(...)` for all saved plots:

```python
subfolder, suffix = build_subfolder(
    plot_type="PlotType",
    marker=marker_key_if_single_marker_plot,
    factor=factor,
    specificity=specificity,
    aliases=getattr(experiment, "aliases", None),
    roi_base=_roi_base,
    multi_roi=_multi_roi,
)
save_fig(fig, experiment.fig_path, save_name + suffix, subfolder=subfolder)
```

`factor` and `specificity` belong in filename suffixes, not folder names.

## Registration

If the plot should be available through specs/UI helpers, add it to
`PyFLASH/spec.py::PLOT_REGISTRY`. Also add parameter descriptions to
`_PARAM_DESCRIPTIONS` in `PyFLASH/plotting.py` so `cheat_sheet(...)` stays
useful.

## Tests

At minimum, add tests for:

- explicit `filtered_columns` path;
- `factor=...` grouping;
- `combine=True` vs separate output;
- specificity queue return shape and saved files;
- missing/non-numeric/`NOT_INCLUDED_IN_EXPERIMENT` handling when relevant.
