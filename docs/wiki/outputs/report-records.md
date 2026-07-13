# Report Records

## Summary

Report records are structured results emitted by plots and pipelines while they
run. They capture the numbers behind a figure: group means and sample sizes,
tests, p-values, effect sizes, correlation coefficients, regression summaries,
and bounded pipeline return manifests.

The core `PyFLASH.report` module is an in-memory collector. Persistent report
files are written by the PyFLASH runner when it arms the collector around a
plot or pipeline request.

## Created By

| Function or layer | What it creates |
|---|---|
| `PyFLASH.report.start()` / `emit(...)` / `collect()` | In-memory result records for direct Python use. |
| Plot/statistics paths such as [`plot_mean_bars`](../functions/plot_mean_bars.md), [`plot_regressions`](../functions/plot_regressions.md), and [`plot_multivariable_regression_matrix`](../functions/plot_multivariable_regression_matrix.md) | `group_comparison`, `correlation`, or `multivariable_regression` records when the collector is active. |
| Pipelines such as [`correlation`](../functions/correlation.md), [`adjusted_correlation`](../functions/adjusted_correlation.md), [`linear_model`](../functions/linear_model.md), and [`iterative_model_sweep`](../functions/iterative_model_sweep.md) | Pipeline return summaries that the runner can include in a results manifest. |
| The PyFLASH runner | Persistent `.results.json`, `.results.md`, `index.jsonl`, and optional `lab_notebook.md` entries under `.claude/skills/pyflash/.runtime/results_store/`. |

## Folder Layout

Runner-persisted report records live in the local runtime results store:

```text
.claude/
  skills/
    pyflash/
      .runtime/
        results_store/
          <run_id>.results.json
          <run_id>.results.md
          index.jsonl
          lab_notebook.md
```

The store is separate from `batch.fig_path`. It is a session/project runtime
record, not a figure folder.

Direct Python use does not write these files unless your code writes them. For
example, this is in memory only:

```python
from PyFLASH import report

report.start()
# run a covered plot or pipeline here
records = report.collect()
```

## File Contents

### `<run_id>.results.json`

The JSON manifest is the canonical saved result. It contains:

| Key | Meaning |
|---|---|
| `schema_version` | Report schema version. |
| `run_id` | Sanitized run identifier. |
| `timestamp` | ISO timestamp for the run. |
| `batch` | Batch name or batch alias used by the runner. |
| `plot` | Plot function name, pipeline name, or `run_spec:<path>`. |
| `experiment_index` | Experiment index when a batch sub-experiment was selected. |
| `params` | JSON-coerced plot or pipeline parameters. |
| `metrics` | Structured emitted records. |
| `pipeline` | Optional bounded summary of a pipeline return dictionary. DataFrames are summarized with shape, columns, and up to the configured row cap. |

Metric record kinds include:

| Kind | Common fields |
|---|---|
| `group_comparison` | `metric`, `groups`, `test`, `pairwise`, `effect_sizes`, `normal`, `direction`, `headline`. |
| `correlation` | `x`, `y`, `group`, `n`, `r`, `p`, `method`, `headline`. |
| `multivariable_regression` | `predictor_set`, `predictors`, `y`, `n`, `r2`, `adj_r2`, `p`, `q`, `coefficients`, `headline`. |
| `linear_model` | `dependent_variable`, `formula`, `group`, `predictors`, `n`, `r2`, `adj_r2`, `p`, `coefficients`, `adjusted_means`, `headline`. |

### `<run_id>.results.md`

The Markdown digest is rendered mechanically from the JSON manifest. It is a
human-readable summary for quick inspection, not a separate source of truth.

### `index.jsonl`

The index ledger is append-only. Each line is a JSON object with:

| Field | Meaning |
|---|---|
| `run_id`, `timestamp`, `batch`, `plot` | Run identity and provenance. |
| `params` | Coerced request parameters. |
| `n_metrics` | Number of captured metric records. |
| `metrics` | Compact searchable summaries of each record. |
| `has_pipeline` | Whether the run also stored a pipeline summary. |
| `json`, `md` | Paths to the full JSON and Markdown digest files. |

### `lab_notebook.md`

This file is for human or agent interpretation notes linked to run IDs. It
should not be treated as the canonical numeric result.

## How To Reuse

Capture records directly in Python:

```python
from PyFLASH import report
from PyFLASH.plotting import plot_mean_bars

report.start()
try:
    plot_mean_bars(batch, data_cols=["GFAP_Count"], save=False)
    records = report.collect()
finally:
    if report.is_active():
        report.collect()

print(records[0]["headline"])
```

Read a persisted runner result:

```python
import json
from pathlib import Path

path = Path(".claude/skills/pyflash/.runtime/results_store/run123.results.json")
summary = json.loads(path.read_text(encoding="utf-8"))

for metric in summary.get("metrics", []):
    print(metric.get("headline"))
```

Search recent run summaries through the ledger:

```python
import json
from pathlib import Path

ledger = Path(".claude/skills/pyflash/.runtime/results_store/index.jsonl")
for line in ledger.read_text(encoding="utf-8").splitlines():
    entry = json.loads(line)
    if entry["plot"] == "plot_mean_bars":
        print(entry["run_id"], entry["n_metrics"])
```

## Notes

- `report.emit(...)` is inert unless `report.start()` has armed the collector.
- `report.collect()` returns the records and disarms the collector.
- NaN and infinite values are coerced to JSON `null`.
- DataFrames in pipeline summaries are bounded so very large tables do not
  explode the result JSON.
- If a covered plot captures zero records, the runner can return a
  `describe_note` so the missing structured result is visible.
- Use [Structured results](../statistics/structured-results.md) for statistical
  interpretation of the record shapes.

## See Also

- [Structured results](../statistics/structured-results.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Pipeline run folders](pipeline-run-folders.md)
