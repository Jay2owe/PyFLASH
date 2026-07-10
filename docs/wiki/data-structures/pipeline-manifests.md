# Pipeline Manifests

## Summary

Pipeline manifests are JSON records that summarize an analysis pipeline run.
Most current pipelines write `manifest.json` inside the run folder and append a
compact row to a sibling `_runs_index.csv`. The manifest is the per-run detail;
the index is the quick overview of many runs.

Manifest payloads differ by pipeline. Use the common fields below for
navigation and provenance, then inspect pipeline-specific keys for the exact
analysis settings and counts.

## Where It Appears

- `Results/Python Figures/<Pipeline Name>/<run_label>/manifest.json` for most analysis pipelines.
- `Results/Python Figures/<Pipeline Name>/_runs_index.csv` beside those run folders.
- `Results/Python Figures/Modelling/Model Sweep/<run_label>/manifest.json` for iterative model sweeps.
- Pipeline return dictionaries, which usually contain the manifest fields plus in-memory DataFrames.

## Required Fields

Common fields in the pipeline run-folder family include:

| Key | Meaning |
|---|---|
| `run_label` | Resolved run folder label. May be user-supplied or auto-slugged from settings. |
| `fig_dir` | Folder where figures are saved. |
| `data_dir` | Folder where data tables and `manifest.json` are saved. In current pipeline I/O, this is usually the same folder as `fig_dir`. |
| `reused` | `true` when an existing manifest was returned because `if_exists="skip"` reused a run. |

Many analysis pipelines also include:

| Key | Meaning |
|---|---|
| `pipeline` | Pipeline identity, such as `adjusted_correlation`, `data_overview`, `group_comparison`, `linear_model`, or `rhythm`. The normal correlation manifest currently omits this key; queued correlation manifests add it at the combined-manifest level. |
| `by`, `factor`, `filter_by` / `specificity`, `roi` | Filters or grouping settings used for the run, when applicable. Manifests may still serialize the legacy/internal `specificity` key. |
| Count fields | Pipeline-specific counts such as `n_rows`, `n_columns`, `n_pairs`, `n_selected`, `n_tests`, `n_significant`, or `n_models`. |

## Optional Fields

Common optional manifest sections include:

| Key | Meaning |
|---|---|
| `columns`, `numeric_columns`, `markers`, `dependent_variables`, `predictors` | Inputs selected for a particular pipeline family. |
| `tests`, `gate`, `alpha`, `min_n` | Statistical settings where relevant. |
| `groups` | Group-level run summaries for non-queued runs. |
| `conditions` | Per-filter records for a filter queue that shares one run folder. |
| `n_conditions` | Number of queued filter records. |
| `plots` | Data-overview plot toggles. |
| `provenance` | Path to a generated `provenance.json` record when written. |
| `sig_audit_bundle` | Path to a significance-audit bundle when created. |

Filter-queue manifests deserve special attention. The combined manifest
uses one shared run folder and records each queued filter in `conditions`, with
fields such as `specificity`, `spec_tag`, `run_label`, `n_rows`, `n_pairs`, and
`n_selected` where those counts apply. The top-level totals are combined across
queued filters. Combined queue manifests also include a top-level `pipeline`
key so the shared run folder can identify which pipeline produced the queued
records.

## Example

```json
{
  "run_label": "scn_correlations",
  "fig_dir": "/path/to/Results/Python Figures/Correlation Pipeline/scn_correlations",
  "data_dir": "/path/to/Results/Python Figures/Correlation Pipeline/scn_correlations",
  "columns": ["GFAP Volume"],
  "against_columns": ["IBA1 Volume"],
  "tests": ["Pearson"],
  "gate": "p",
  "alpha": 0.05,
  "by": "conditions",
  "factor": "Diagnosis",
  "specificity": null,
  "roi": "SCN",
  "n_pairs": 1,
  "n_selected": 1,
  "reused": false
}
```

Runs index row:

```text
| run_label | n_rows | n_pairs | n_selected | by | factor | roi | fig_dir |
|---|---:|---:|---:|---|---|---|---|
| scn_correlations | 24 | 1 | 1 | conditions | Diagnosis | SCN | /path/to/... |
```

## Produced By

- [`correlation`](../functions/correlation.md).
- [`adjusted_correlation`](../functions/adjusted_correlation.md).
- [`data_overview`](../functions/data_overview.md).
- [`group_comparison`](../functions/group_comparison.md).
- [`linear_model`](../functions/linear_model.md).
- [`rhythm`](../functions/rhythm.md).
- [`run_linear_model_pipeline`](../functions/run_linear_model_pipeline.md), which writes an older modelling-oriented manifest under its save directory.
- [`iterative_model_sweep`](../functions/iterative_model_sweep.md), which writes a classifier sweep manifest in the model-sweep output folder.

## Consumed By

- Pipeline `if_exists="skip"` reuse, which reads an existing `manifest.json`.
- `_runs_index.csv` dashboards and quick run history inspection.
- Structured result/report digest code that summarizes pipeline return manifests.
- Users auditing saved results after a run.

## Notes

- Do not assume every pipeline has the same keys. The common fields identify the run; pipeline-specific keys describe the analysis.
- `if_exists` policies are centralized for current pipeline run folders: `overwrite`, `version`, `error`, and `skip`.
- `_runs_index.csv` is deliberately compact and may omit detailed fields present in `manifest.json`.
- Current pipeline output co-locates figures, CSV tables, and the manifest in the same run folder.
- Filter queues use filename tags such as `_Diagnosis.AD` so filter-specific tables and figures can live side-by-side in one folder.
- Model sweep manifests include modelling keys such as `target`, `class_labels`, `class_counts`, `predictors`, `model_preset`, `best_family`, and `best_features` rather than the correlation-style fields.

## See Also

- [Pipeline run folders](../outputs/pipeline-run-folders.md)
- [Model sweep outputs](../outputs/model-sweep-outputs.md)
- [Saving parameters](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
