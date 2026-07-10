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

Only the public arguments are shown. Internal underscore-prefixed queue arguments
are reserved for PyFLASH.

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main input for saved PyFLASH analyses. |
| `Experiment` / `MiniExperiment` | Yes | Works when a summary table and output paths are available. |
| `pandas.DataFrame` | Yes | Accepted for summary-table rhythm analyses when required columns are present. |

## Parameters

| Parameter | Meaning |
|---|---|
| `column`, `data_col` | Single measurement column for cosinor mode. |
| `columns`, `data_cols` | One or more measurement columns for cosinor mode. |
| `time_col` | Time axis column for cosinor mode. Values are coerced to numeric time units. |
| `group_col` | Optional grouping column such as `Diagnosis` or `Condition`. |
| `group_order` | Explicit group order for colors, legends, and result tables. |
| `period` | Rhythm period in the same units as `time_col`; `24.0` is the default daily cycle. |
| `period_free` | If true, fit the period freely instead of holding it fixed. |
| `method` | Cosinor fit method. Public workflows normally use `pooled`. |
| `subject_col`, `animal_col` | Subject identifier column. `animal_col` is the legacy alias. |
| `phase_col` | Circular phase/acrophase column for parameter mode. Supplying `phase_col` selects parameter mode. |
| `param_cols` | Optional additional rhythmic parameter columns to test in parameter mode. |
| `radius_col` | Optional radial column for phase-amplitude plotting. |
| `filter_by`, `specificity` | Restrict rows before analysis. `filter_by` is the preferred public name; `specificity` remains supported for older code. A filter queue writes one combined run folder with tagged files and a `conditions` ledger. |
| `screen` | Add q-values to parameter tests. Required when `gate="fdr"`. |
| `families` | Multiple-testing family definition for screened parameter tests. |
| `gate` | Significance gate for mode-specific summaries: `p` or FDR/q-value aliases. |
| `alpha` | Significance cutoff. |
| `palette` | Optional color mapping for groups. |
| `run_label` | Run folder name. If omitted, PyFLASH builds a deterministic slug. |
| `if_exists` | Run-folder collision policy: `overwrite`, `version`, `error`, or `skip`. |
| `save` | If true, write run files. |
| `write_manifest` | Write `manifest.json` and update `_runs_index.csv` when saving. |
| `montage` | If true and saving, create `! Overview Montage.png`. |

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
| `../_runs_index.csv` | Append-only index of rhythm runs. |
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
