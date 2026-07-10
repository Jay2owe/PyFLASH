# Outputs

## Summary

PyFLASH output files fall into a few predictable families: figures, pipeline
run folders, Excel workbooks, normality diagnostics, model-sweep artifacts,
structured report records, and pickles. This section explains which functions
create each family, where files are saved, what is inside them, and how to
reuse them without re-running the full analysis.

Start with [Where Results Go](../getting-started/where-results-go.md) if you
only need the basic folder map. Use these pages when you need output-specific
file names, table meanings, or loading examples.

## Created By

Output files are created by these main routes:

| Route | Common outputs |
|---|---|
| Plot functions with `save=True` | SVG figures under `batch.fig_path`, plus plot-specific CSV or PNG diagnostics when the plot computes statistics. |
| Pipeline functions such as [`correlation`](../functions/correlation.md), [`data_overview`](../functions/data_overview.md), and [`linear_model`](../functions/linear_model.md) | Run folders with figures, CSV tables, `manifest.json`, `_runs_index.csv`, and often `! Overview Montage.png`. |
| `Batch.export_all_excel()` and the `Batch.export_*_excel()` methods | `.xlsx` workbooks and matching `*_RegexFilters.txt` reports under `batch.export_path` or a supplied export folder. |
| [`iterative_model_sweep`](../functions/iterative_model_sweep.md) | Classifier sweep CSVs, PNG summaries, `manifest.json`, and a run README. |
| The PyFLASH runner around `PyFLASH.report` | `.runtime/results_store/<run_id>.results.json`, `.results.md`, and `index.jsonl`. |
| [`save_state`](../functions/save_state.md), [`load_state`](../functions/load_state.md), [`normalize_paths`](../functions/normalize_paths.md), and `create_batch(..., pickle_path=...)` | `.pkl` saved-state files and path-rebased objects. |

## Folder Layout

The default batch output roots are created lazily. A path can be recorded on
the object before the corresponding folder exists on disk.

```text
<batch-output>/
  Exports/
  Results/
    Python Figures/
    Data and Stats/
    Separate CSVs/
    Representative Images/
    Legends/
```

Current pipeline outputs are centered under `Results/Python Figures`, not
`Results/Data and Stats`:

```text
<batch-output>/Results/Python Figures/<Pipeline Name>/<run_label>/
  manifest.json
  *.csv
  *.svg
  ! Overview Montage.png
```

## File Contents

| Page | File family |
|---|---|
| [Figure folders](figure-folders.md) | Saved SVG plots, PNG montages, optional PNG diagnostics, and plot-side CSV statistics. |
| [Pipeline run folders](pipeline-run-folders.md) | Pipeline tables, figure subfolders, manifests, run indexes, and reuse policies. |
| [Excel workbooks](excel-workbooks.md) | IF summary, IF extended, behavior, and extra-summary workbooks plus regex audit reports. |
| [Normality outputs](normality-outputs.md) | Plot-level Q-Q PNGs and `data_overview` normality tables/summary figures. |
| [Model sweep outputs](model-sweep-outputs.md) | Classifier sweep score tables, prediction tables, permutation tests, plots, README, and manifest. |
| [Report records](report-records.md) | Structured JSON result records, deterministic Markdown digests, index ledger, and lab notebook entries. |
| [Pickle files](pickle-files.md) | Saved `Batch` or `Experiment` state, legacy migration, path normalization, and cache reuse. |

## How To Reuse

Inspect a run folder with standard Python tools:

```python
from pathlib import Path
import pandas as pd

run_dir = Path("analysis-output/Results/Python Figures/Correlation Pipeline/scn_run")
manifest = pd.read_json(run_dir / "manifest.json", typ="series").to_dict()
selected = pd.read_csv(run_dir / "selected_pairs.csv")

print(manifest["run_label"])
print(selected.head())
```

Reopen a saved PyFLASH object when you need to make more plots from the same
processed state:

```python
from PyFLASH import load_state

batch = load_state("analysis-output/pickles/scn_batch.pkl")
print(batch.fig_path)
```

## Notes

- `save=False` means plot and pipeline functions should return Python results
  without writing new output files.
- `Config.SAVE_MODE=False` disables figure writes at the shared
  `save_fig(...)` layer.
- Pipeline `if_exists` policies control existing run folders: `overwrite`,
  `version`, `error`, and `skip`.
- Do not use local analysis folders as reusable documentation examples. Use
  placeholder paths and replace them in your own scripts.
