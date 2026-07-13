# rhythm

## Summary

`rhythm` runs a saved rhythm-analysis pipeline in one of two modes:

- **Cosinor mode** fits rhythmic curves from one or more measurement columns and
  a time column.
- **Parameter mode** analyzes already-estimated circular phase/acrophase values
  and optional rhythmic parameters.

The pipeline writes mode-specific tables and figures, records a manifest, and
creates an overview montage.

Registry name: `rhythm_pipeline`.

## Signature

```python
from PyFLASH import rhythm

rhythm(
    experiment,
    column=None,
    data_col=None,
    columns=None,
    data_cols=None,
    time_col="Time",
    group_col=None,
    group_order=None,
    period=24.0,
    period_free=False,
    method="pooled",
    animal_col=None,
    subject_col=None,
    phase_col=None,
    param_cols=None,
    radius_col=None,
    specificity=None,
    filter_by=None,
    screen=False,
    families="parameter",
    gate="p",
    alpha=0.05,
    palette=None,
    run_label=None,
    if_exists="overwrite",
    save=True,
    write_manifest=True,
    montage=True,
    ...
)
```

Common public arguments are shown. Internal underscore-prefixed queue arguments
are reserved for PyFLASH.

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main input for saved PyFLASH analyses. |
| `Experiment` / `MiniExperiment` | Yes | Works when a summary table and output paths are available. |
| `pandas.DataFrame` | Yes | Accepted for summary-table rhythm analyses when required columns are present. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | `Batch`, `Experiment`, `MiniExperiment`, or `DataFrame` | required | Data source containing a summary table. |
| `data_col` | `str` or `None` | `None` | Single measurement column for cosinor mode. Alias: `column`. |
| `data_cols` | list-like or `None` | `None` | One or more measurement columns for cosinor mode. Alias: `columns`. |
| `time_col` | `str` | `"Time"` | Time axis column for cosinor mode. Values are coerced to numeric time units. |
| `group_col` | `str` or `None` | `None` | Optional grouping column such as `Diagnosis` or `Condition`. |
| `group_order` | list-like or `None` | `None` | Explicit group order for colors, legends, and result tables. `None` uses observed/group-list order. |
| `period` | `float` | `24.0` | Rhythm period in the same units as `time_col`; `24.0` is the default daily cycle. |
| `period_free` | `bool` | `False` | If `True`, fit the period freely instead of holding it fixed at `period`. |
| `method` | `str` | `"pooled"` | Cosinor fit method. |
| `subject_col` | `str` or `None` | `None` | Subject identifier column. Alias: `animal_col`. |
| `phase_col` | `str` or `None` | `None` | Circular phase/acrophase column for parameter mode. Supplying `phase_col` selects parameter mode. |
| `param_cols` | list-like or `None` | `None` | Optional additional rhythmic parameter columns to test in parameter mode, such as amplitude or mesor. |
| `radius_col` | `str` or `None` | `None` | Optional radial column for phase-amplitude plotting. |
| `filter_by` | mapping, tuple, list, or `None` | `None` | Restrict rows before analysis. A list of filters runs queue mode and tags outputs by filter value. Alias: `specificity`. |
| `screen` | `bool` | `False` | Add q-values to parameter tests. Required when `gate="fdr"`. |
| `families` | `str`, list-like, or mapping | `"parameter"` | Multiple-testing family definition for screened parameter tests. |
| `gate` | `str` | `"p"` | Significance gate for mode-specific summaries. |
| `alpha` | `float` | `0.05` | Significance cutoff. |
| `palette` | mapping, sequence, or `None` | `None` | Optional color mapping for groups. `None` uses PyFLASH/group-list colors where available. |
| `run_label` | `str` or `None` | `None` | Run folder name. `None` builds a deterministic slug from settings. |
| `if_exists` | `str` | `"overwrite"` | Run-folder collision policy. |
| `save` | `bool` | `True` | Write run files. `False` computes and returns results without clearing or writing a run folder. |
| `write_manifest` | `bool` | `True` | Write `manifest.json` and update `_runs_index.csv` when saving. |
| `montage` | `bool` | `True` | Create `! Overview Montage.png` in the run folder when saving. |
| `condition_col` | `str` | `"Condition"` | Legacy group column used when wrapping a raw `DataFrame`; prefer `group_col` where possible. |
| `group_cols` | list-like or `None` | `None` | Crossed grouping columns used when wrapping a raw `DataFrame`. Alias: `factor_cols`. |
| `group_list` | `groupList` or `None` | `None` | Optional group metadata for raw `DataFrame` input. Aliases: `groups`, legacy `conditions`. |
| `dataframe_kwargs` | `dict` or `None` | `None` | Advanced options forwarded to the raw `DataFrame` adapter. |

## Parameter Options

### `period_free` options

| Option | Behavior |
|---|---|
| `False` (default) | Hold the rhythm period fixed at `period`. |
| `True` | Fit the period as a free parameter. |

### `method` options

| Option | Behavior |
|---|---|
| `"pooled"` (default) | Fits one curve to all rows in a group. |
| `"population_mean"` | Fits per-subject curves and averages coefficients. Requires `subject_col`/`animal_col` and enough repeated timepoints. |
| `"mixed"` | Fits a mixed-effects cosinor with random subject intercepts. Requires `subject_col`/`animal_col` and enough repeated observations. |

### `families` options

| Option | Behavior |
|---|---|
| `"parameter"` (default) | Treats the parameter panel as one Benjamini-Hochberg family. |
| `"none"` | Treats each parameter separately. |
| `"each"` | Treats each parameter separately. |
| `"per-parameter"` | Treats each parameter separately. |
| Mapping such as `{"Amplitude": "fit"}` | Assigns named parameters to explicit correction families. |

### `gate` options

| Option | Behavior |
|---|---|
| `"p"` (default) | Use raw p-values for significance summaries. |
| `"fdr"` | Use corrected q-values. Requires `screen=True`. |

### `if_exists` options

| Option | Behavior |
|---|---|
| `"overwrite"` (default) | Clear the existing generated run folder, then recompute. |
| `"version"` | Keep the old run and write to the next free suffix such as `_v2`. |
| `"error"` | Raise if the run folder already exists. |
| `"skip"` | Reuse the cached manifest when available instead of recomputing. |

## Returns

The function returns a dictionary. Common keys include:

| Key | Type | Meaning |
|---|---|---|
| `pipeline` | `str` | Always `rhythm`. |
| `mode` | `str` | `cosinor` or `parameter`. |
| `run_label`, `fig_dir`, `data_dir` | `str` | Run name and output folders. Tables and figures are co-located in the run folder. |
| `group_col`, `groups`, `n_groups` | mixed | Resolved grouping information. |
| `period`, `period_free`, `method` | mixed | Rhythm model settings. |
| `screen`, `gate`, `alpha`, `n_significant` | mixed | Testing and gate summary. |
| `specificity`, `conditions`, `n_conditions` | mixed | Row filter and merged filter-queue ledger when applicable. |
| `montage` | `str` | Path to the overview montage when one was written or reused. |
| `reused` | `bool` | True when `if_exists="skip"` returned an existing manifest. |

Cosinor-mode returns also include:

| Key | Type | Meaning |
|---|---|---|
| `columns` | `list[str]` | Measurement columns fitted. |
| `cosinor_parameters` | `pandas.DataFrame` | Fitted mesor, amplitude, acrophase, and related parameters. |
| `cosinor_group_test` | `pandas.DataFrame` | Group-level rhythm comparison table when groups are present. |

Parameter-mode returns also include:

| Key | Type | Meaning |
|---|---|---|
| `phase_col` | `str` | Circular phase column used. |
| `param_cols` | `list[str]` | Additional parameter columns tested. |
| `circular_phase_stats` | `pandas.DataFrame` | Circular phase summary by group. |
| `phase_group_test` | `pandas.DataFrame` | Group comparison for phase values. |
| `parameter_tests` | `pandas.DataFrame` | Optional tests for `param_cols`. |
| `phase_test`, `phase_test_p` | mixed | Summary of the primary phase test. |

When `if_exists="skip"` reuses an existing run, the returned object is the cached
manifest and may not include in-memory DataFrames.

## Saved Outputs

With `save=True`, files are written below:

```text
<fig_path>/Rhythm Pipeline/<run_label>/
```

The run folder is both `fig_dir` and `data_dir`.

Cosinor mode writes:

| Output | Meaning |
|---|---|
| `cosinor_parameters*.csv` | Fitted rhythm parameters by column/group. |
| `cosinor_group_test*.csv` | Group comparison table when groups are present. |
| `Cosinor <column>*.svg` | Cosinor fit figures. |

Parameter mode writes:

| Output | Meaning |
|---|---|
| `circular_phase_stats*.csv` | Circular phase summary table. |
| `phase_group_test*.csv` | Group comparison for phase. |
| `parameter_tests*.csv` | Optional tests for additional rhythm parameter columns. |
| `Acrophase Clock*.svg` | Circular phase clock plot. |
| `Phase-Amplitude*.svg` | Optional phase-amplitude plot when `radius_col` is supplied. |

Both modes write:

| Output | Meaning |
|---|---|
| `manifest.json` | Stable run summary for reuse and reporting. |
| `../_runs_index.csv` | One-row-per-run index for rhythm runs; reruns with the same run label replace the matching index row. |
| `! Overview Montage.png` | Overview montage when `montage=True`. |

## Examples

Cosinor mode:

```python
from PyFLASH import rhythm

result = rhythm(
    batch,
    data_cols=["Activity"],
    time_col="ZT",
    group_col="Diagnosis",
    period=24,
    run_label="activity_cosinor",
)

print(result["mode"])
print(result["cosinor_parameters"].head())
```

Parameter mode:

```python
result = rhythm(
    batch,
    phase_col="Acrophase",
    param_cols=["Amplitude", "Mesor"],
    radius_col="Amplitude",
    group_col="Diagnosis",
    screen=True,
    gate="fdr",
    run_label="acrophase_parameters",
)
```

## Notes

- Supplying `phase_col` selects parameter mode. Without `phase_col`, provide one
  or more measurement columns and `time_col` for cosinor mode.
- `gate="fdr"` requires `screen=True` for parameter-test q-values.
- Use `group_order` to make group colors and table order deterministic across
  runs.

## See Also

- [plot_cosinor](plot_cosinor.md)
- [plot_acrophase_clock](plot_acrophase_clock.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Rhythm statistics](../statistics/rhythm.md)
- [Rhythm plots](../plot-types/rhythm-plots.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
