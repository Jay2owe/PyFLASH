# Pipeline Run Folders

## Summary

Pipeline run folders are self-contained folders for one named analysis run. A
run folder usually contains CSV tables, SVG figures, `manifest.json`, and, for
montage-enabled pipelines, `! Overview Montage.png`.

Current pipeline I/O co-locates figures and data tables in the same run folder
under `batch.fig_path`. Older or legacy code may have used `batch.data_path`,
but current run-folder helpers prefer the figure root so the visual and numeric
artifacts stay together.

## Created By

| Function | Pipeline folder | Common files |
|---|---|---|
| [`correlation`](../functions/correlation.md) | `Correlation Pipeline/<run_label>/` | Pairwise correlation tables, selected pairs, matrix CSVs/SVGs, manifest, run index, montage. |
| [`adjusted_correlation`](../functions/adjusted_correlation.md) | `Adjusted Correlation Pipeline/<run_label>/` | Raw and adjusted correlation outputs, covariate screening, residual models, adjusted regression coefficients, manifest, montage. |
| [`data_overview`](../functions/data_overview.md) | `Data Overview Pipeline/<run_label>/` | Inventory, group counts, normality, outlier, covariation, effect-size, scorecard/readiness tables and figures, provenance, manifest, montage. |
| [`group_comparison`](../functions/group_comparison.md) | `Group Comparison Pipeline/<run_label>/` | Group-comparison results, omnibus tests, descriptives, volcano/forest/matrix figures, optional bar/superplot secondaries, manifest, montage. |
| [`linear_model`](../functions/linear_model.md) | `Linear Model Pipeline/<run_label>/` | Coefficients, summaries, metadata, adjusted means, coefficient forest, adjusted mean plots, manifest, montage. |
| [`rhythm`](../functions/rhythm.md) | `Rhythm Pipeline/<run_label>/` | Rhythm parameter/result tables, rhythm figures from the called mode, manifest, run index. |
| [`run_linear_model_pipeline`](../functions/run_linear_model_pipeline.md) | `Modelling/Linear Models/<run_label>/` or a supplied output folder | Older modelling-oriented coefficients, summaries, metadata, and manifest. |

Classifier sweep outputs from [`iterative_model_sweep`](../functions/iterative_model_sweep.md)
use a related model-sweep folder described in [Model sweep outputs](model-sweep-outputs.md).

## Folder Layout

Default current layout:

```text
<batch-output>/Results/Python Figures/
  <Pipeline Name>/
    _runs_index.csv
    <run_label>/
      manifest.json
      ! Overview Montage.png
      *.csv
      *.svg
      Matrices/
        *.csv
        *.svg
```

The exact files depend on the pipeline and options. For a correlation run:

```text
Correlation Pipeline/scn_correlations/
  manifest.json
  pairwise_correlations.csv
  selected_pairs.csv
  ! Overview Montage.png
  Matrices/
    coef_Pearson.csv
    pvalues_Pearson.csv
    qvalues_Pearson.csv
    gate_matrix.csv
    Pearson Correlation Matrix.svg
    Gate Passing Matrix.svg
```

For a filter queue, the run uses one shared folder. Each queued filter is
distinguished by a filename tag:

```text
Correlation Pipeline/diag_queue/
  manifest.json
  pairwise_correlations_Diagnosis.AD.csv
  pairwise_correlations_Diagnosis.MCI.csv
  Matrices/
    Pearson Correlation Matrix_Diagnosis.AD.svg
    Pearson Correlation Matrix_Diagnosis.MCI.svg
```

## File Contents

| File | Contents |
|---|---|
| `manifest.json` | Run settings, resolved paths, grouping/filter parameters, counts, selected outputs, and reuse status. See [Pipeline manifests](../data-structures/pipeline-manifests.md). |
| `_runs_index.csv` | Compact one-row-per-run index beside run folders. Existing rows with the same `run_label` are replaced. |
| `! Overview Montage.png` | Contact-sheet PNG of the run's headline figures. The name comes from `Config.MONTAGE_FILENAME` and can be changed by configuration. |
| `pairwise_correlations*.csv`, `selected_pairs*.csv` | Long-form correlation results and the subset passing the gate. |
| `Matrices/*.csv` | Matrix forms of coefficients, raw p-values, FDR q-values, and gate masks. |
| `normality*.csv`, `outliers*.csv`, `effect_sizes*.csv`, and related overview tables | `data_overview` quality-control and exploratory analysis tables. |
| `group_comparison_results*.csv`, `omnibus*.csv`, `group_descriptives*.csv` | Group-comparison result tables. |
| `linear_model_coefficients*.csv`, `linear_model_summaries*.csv`, `linear_model_metadata*.csv` | Linear-model result tables. |
| `provenance.json` and `sig_audit/` | Best-effort reproducibility and significance-audit bundle from `data_overview` when those options are enabled. |

## How To Reuse

Load a manifest and selected correlation pairs:

```python
from pathlib import Path
import json
import pandas as pd

run_dir = Path("analysis-output/Results/Python Figures/Correlation Pipeline/scn")

manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
selected = pd.read_csv(run_dir / "selected_pairs.csv")

print(manifest["tests"])
print(selected[["x", "y", "r", "p"]].head())
```

Inspect all runs of a pipeline:

```python
import pandas as pd

index = pd.read_csv(
    "analysis-output/Results/Python Figures/Correlation Pipeline/_runs_index.csv"
)
print(index[["run_label", "n_selected", "fig_dir"]])
```

Reuse an existing run without recomputing:

```python
from PyFLASH.pipeline import correlation

cached = correlation(
    batch,
    data_cols=["GFAP Volume"],
    against_data_cols=["IBA1 Volume"],
    run_label="scn",
    if_exists="skip",
    save=True,
)

print(cached["reused"])
```

## Notes

- `run_label` is sanitized for folder names. If no explicit label is supplied,
  pipelines can derive a deterministic slug from their settings.
- `if_exists="overwrite"` clears a prior generated run folder when `save=True`.
  With `save=False`, pipelines do not clear an existing run.
- `if_exists="version"` preserves an existing run and writes the next free
  suffix, such as `run_v2`.
- `if_exists="skip"` returns the cached `manifest.json` when it exists and marks
  the returned dictionary with `reused=True`.
- `if_exists="error"` raises if the run folder already exists.
- Filter queues are merged into one folder with filename tags and a
  queue-level manifest instead of separate child folders.

## See Also

- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Figure folders](figure-folders.md)
- [Model sweep outputs](model-sweep-outputs.md)
- [Saving parameters](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
