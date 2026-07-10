# Excel Workbooks

## Summary

Excel workbooks are human-facing exports from a processed `Batch`. They are
useful for sharing summary values, per-object IF measurements, behavior
columns, and extra batch-summary columns with collaborators who do not use
Python.

Each workbook is paired with a `*_RegexFilters.txt` report that records which
include/exclude regex filters were applied and which columns or sheets were
exported or skipped.

## Created By

| Method | Default workbook |
|---|---|
| `batch.export_all_excel(...)` | Delegates to `batch.export_excel(...)` and writes all enabled workbook families. |
| `batch.export_excel(...)` | Coordinates IF summary, IF extended, behavior, and extra-summary exports. |
| `batch.export_IF_summary_excel(...)` | `IF_Summary.xlsx` |
| `batch.export_extended_data_excel(...)` | `IF_Extended.xlsx` |
| `batch.export_behavior_summary_excel(...)` | `Behavior_Summary.xlsx` |
| `batch.export_extra_summary_excel(...)` / `batch.export_unregistered_summary_excel(...)` | `Extra_Summary.xlsx` |

The Streamlit UI export page calls the same `Batch.export_all_excel(...)`
method through the UI service layer.

## Folder Layout

If `save_path=None`, relative export paths resolve below `batch.export_path`,
which defaults to:

```text
<batch-output>/Exports/
```

`export_excel(...)` writes IF workbooks into one subfolder per ROI base and
writes behavior/extra-summary workbooks into the export root:

```text
<batch-output>/Exports/
  scn/
    IF_Summary.xlsx
    IF_Summary_RegexFilters.txt
    IF_Extended.xlsx
    IF_Extended_RegexFilters.txt
  Behavior_Summary.xlsx
  Behavior_Summary_RegexFilters.txt
  Extra_Summary.xlsx
  Extra_Summary_RegexFilters.txt
```

An explicit absolute `save_path` is used as-is. A relative `save_path` is
resolved inside `batch.export_path`.

Custom workbook stems can be supplied without `.xlsx`, for example
`if_summary_save_name="SCN_IF"`. If a supplied stem ends in `.xlsx`, PyFLASH
strips the extension before appending `.xlsx` and `_RegexFilters.txt`.

## File Contents

### IF Summary

`IF_Summary.xlsx` contains:

| Sheet | Contents |
|---|---|
| `Experimental Conditions` | Condition factor, condition name, and explanation. |
| `Data Summary` | Per-experiment marker/analysis overview and any recorded ImageJ macro details found in analysis-detail text files. |
| One sheet per mapped summary metric | Values split into condition columns, with a metric description written below the data. |

Only columns covered by the IF summary name map are exported here.

### IF Extended

`IF_Extended.xlsx` contains:

| Sheet | Contents |
|---|---|
| `Conditions` | Condition table. |
| `Experiment <n>_<marker>` or `Experiment <n>_<marker> ROI` sheets | Per-object or ROI-level rows from each antibody table, including ID columns and mapped metric columns. |

The extended export writes mapped raw metric columns from each experiment's
`Antibody` data tables. Unmapped or regex-skipped columns are reported in the
matching regex text file.

### Behavior Summary

`Behavior_Summary.xlsx` contains:

| Sheet | Contents |
|---|---|
| `Conditions` | Condition table. |
| One sheet per behavior metric in the behavior name map | Values split into condition columns, with a description below the data when available. |

If no `Behaviour` table is present in `batch.data`, the method returns without
creating an export folder.

### Extra Summary

`Extra_Summary.xlsx` contains:

| Sheet | Contents |
|---|---|
| `Experimental Conditions` | Condition table. |
| `Extra Columns` | Index of exported internal column names, display names, and sheet names. |
| One sheet per unregistered summary column | Values split by condition, or an `All` group when no condition split is available. |

Registered IF summary columns are deliberately excluded from `Extra_Summary`
and listed in the regex report.

## How To Reuse

Export all default workbook families:

```python
batch.export_all_excel()
```

Export to an explicit folder with custom names:

```python
batch.export_all_excel(
    save_path="analysis-output/exports",
    if_summary_save_name="SCN_IF_Summary",
    if_extended_save_name="SCN_IF_Extended",
    behaviour_save_name="Behaviour",
    unregistered_summary_save_name="Other_Summary",
)
```

Read one exported sheet back into Python:

```python
import pandas as pd

df = pd.read_excel(
    "analysis-output/exports/scn/IF_Summary.xlsx",
    sheet_name="Experimental Conditions",
)
print(df.head())
```

Inspect an export audit report:

```python
from pathlib import Path

report = Path("analysis-output/exports/scn/IF_Summary_RegexFilters.txt")
print(report.read_text(encoding="utf-8"))
```

## Notes

- Excel sheet names are sanitized for Excel's forbidden characters and 31
  character limit. Duplicate or truncated names get numeric suffixes.
- Include/exclude filters match internal PyFLASH column names, not display
  labels.
- IF summary and IF extended workbooks are written per ROI base when using
  `export_excel(...)`.
- `batch.export_excel(...)` with all output toggles disabled creates no export
  folder.
- On Windows, an open workbook can lock the file and prevent overwriting it.

## See Also

- [Where results go](../getting-started/where-results-go.md)
- [Summary table](../data-structures/summary-table.md)
- [Saving parameters](../parameters/saving.md)
