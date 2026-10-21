# Export Excel Workbooks

## Goal

Write collaborator-friendly Excel workbooks from a processed `Batch`, including
IF summary, IF extended, behavior, and extra-summary outputs.

Use this workflow after a batch is imported or loaded. Excel exports are for
sharing tables; they are separate from plot and pipeline CSV outputs.

## Inputs

- A processed `Batch`.
- A valid `batch.export_path`, created by the batch save-path setup.
- Optional output folder through `save_path`.
- Optional include/exclude regex filters for each workbook family.
- Optional workbook filename stems.

## Minimal Path

```python
from PyFLASH import load_state

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")
batch.export_all_excel()

print(batch.export_path)
```

## Full Workflow

1. Load or create the batch and confirm it has a summary:

```python
from PyFLASH import load_state

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")
print(batch.summary.shape)
print(batch.export_path)
```

2. Export all default workbook families:

```python
batch.export_all_excel()
```

3. Export to a chosen folder with custom workbook stems:

```python
batch.export_all_excel(
    save_path=r"C:\path\to\analysis-output\exports",
    if_summary_save_name="SCN_IF_Summary",
    if_extended_save_name="SCN_IF_Extended",
    behaviour_save_name="Behaviour",
    unregistered_summary_save_name="Other_Summary",
)
```

4. Disable workbook families you do not need:

```python
batch.export_all_excel(
    if_summary=True,
    if_extended=False,
    behaviour=False,
    unregistered_summary=True,
)
```

5. Filter exported columns by internal PyFLASH column names. Regex filters are
   case-insensitive.

   Supply a pattern string or a collection of patterns. Tuples, one-dimensional
   NumPy arrays, pandas Series/Index objects and sets are also accepted. Collection
   entries are trimmed; empty entries and `None` are ignored. Sets produce reports
   in lexicographic pattern order. Include patterns are applied before exclusions.

```python
batch.export_all_excel(
    if_summary_include=["GFAP", "IBA1"],
    if_summary_exclude=["NonColoc"],
    if_extended_include=["Area", "Intensity"],
    unregistered_summary_exclude=["QC"],
)
```

6. Inspect the matching regex report beside each workbook:

```python
from pathlib import Path

for report in Path(batch.export_path).rglob("*_RegexFilters.txt"):
    print(report)
    print(report.read_text(encoding="utf-8").splitlines()[:8])
```

## Outputs

With `save_path=None`, the default root is:

```text
<batch-output>/Exports/
```

Common outputs include:

| Output | Meaning |
|---|---|
| `<roi>/IF_Summary.xlsx` | Condition-split IF summary metrics with condition and data-summary sheets. |
| `<roi>/IF_Extended.xlsx` | Per-object or ROI-level marker tables from imported experiments. |
| `Behavior_Summary.xlsx` | Behavior metrics when `batch.data["Behaviour"]` exists. |
| `Extra_Summary.xlsx` | Summary columns not covered by standard IF summary mappings. |
| `*_RegexFilters.txt` | Audit report for filters, exported sheets, skipped columns, and notes. |

`batch.export_all_excel()` and `batch.export_excel()` return an ordered list of
workbook and filter-report paths, or an empty list when nothing is exported.

## Troubleshooting

- No export folder appears: all workbook toggles may be disabled, or the
  behavior workbook may be requested when no behavior table exists.
- A regex error stops export: test simpler include/exclude patterns. Unbalanced
  brackets such as `[` are invalid regex. All active families' patterns are
  checked before the request writes its first workbook or filter report.
  Disabled families ignore their filter options.
- Absent optional behavior data produces no behavior workbook. Errors reading
  declared behavior data propagate rather than being reported as absence.
- Expected columns are missing: filters match internal column names, not Excel
  display labels.
- The workbook cannot be overwritten on Windows: close it in Excel and rerun.
- `Extra_Summary.xlsx` excludes standard IF summary columns by design and lists
  them in its regex report.

## Next Steps

- [Excel workbooks](../outputs/excel-workbooks.md)
- [Where results go](../getting-started/where-results-go.md)
- [Summary table](../data-structures/summary-table.md)
- [Saving and run labels](../parameters/saving.md)
- [Use the Streamlit UI](use-the-streamlit-ui.md)
