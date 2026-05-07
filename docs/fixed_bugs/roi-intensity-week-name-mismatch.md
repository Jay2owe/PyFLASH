# ROI Intensity CSV numeric week names cause duplicate batch rows and broken exports
**Date**: 2026-04-13
**Files changed**: `PyFLASH/experiment.py`
**Guard**: `tests/test_roi_week_normalization.py` — 3 tests

## What went wrong
ROI Intensities CSVs (from the `ROI Intensities/` subfolder) contained animal names with numeric week identifiers like `hAPP2Week2`, while Objects and Attributes CSVs used written-out names like `hAPP2WeekTwo`. When the batch merged experiment summaries via an outer join on `AnimalName`, these were treated as different animals, creating duplicate rows — one with ROI intensity data and NaN for object columns, the other with object data and NaN for ROI columns. Additionally, the condition-matching system (which strips digits to build a `Condition` column) produced `hAPPWeek` from `hAPP2Week2`, which couldn't match any condition name like `hAPPWeekTwo`, causing `NOT_INCLUDED_IN_EXPERIMENT` in exports.

## The broken pattern
```python
# _standardize_csv_columns in experiment.py
# Normalized Region/Hemisphere/ROI columns but left "Animal Name" values
# as-is from the CSV — no week-format normalization was applied.
def _standardize_csv_columns(df):
    ...
    return df  # "Animal Name" kept raw: "hAPP2Week2" instead of "hAPP2WeekTwo"
```

## The fix
Added `replace_week_int` normalization of the `Animal Name` column at the end of `_standardize_csv_columns`, after all format-specific processing. This converts `Week2` → `WeekTwo`, `Week4` → `WeekFour`, `Week8` → `WeekEight`. The function is a no-op on names already in written-out form, so it's safe for all CSV formats.

```python
if 'Animal Name' in df.columns:
    df['Animal Name'] = df['Animal Name'].fillna('').astype(str).map(replace_week_int)
```

## Why it matters
Without this normalization, any ROI Intensities CSV generated with numeric week identifiers will produce duplicate animals in batch summaries, NaN values in ROI columns for the "correct" animal name, and empty/NOT_INCLUDED cells in condition-based Excel exports. The condition system fundamentally requires written-out week names because it strips digits to build condition strings.
