# Exclusion Ledgers

## Summary

An exclusion ledger is a table that records which cells or subjects should be
excluded from downstream analysis. The ledger is attached to a cleaned copy as
`.exclusions`. It is an audit trail: it records the original value, reason,
kind of exclusion, and fill value used when exclusions are applied.

The original experiment or batch is not modified. Exclusion helpers return a
shallow copy with copied summary tables and shared heavy raw data.

## Where It Appears

- `cleaned.exclusions` after calling exclusion helpers.
- `marked.exclusions` after calling mark-only helpers.
- Optional CSV files under an `Exclusions` folder when exclusion helpers are run with `save=True`.
- `cleaned.exclusion_summary`, a compact dictionary summarizing the action.

## Required Fields

Ledger tables use these columns:

| Column | Meaning |
|---|---|
| `AnimalName` | Subject affected by the exclusion. |
| `column` | Summary metric column affected. |
| `group` | Group label when known, especially for outlier-derived records. |
| `original_value` | Value before the exclusion fill was written. |
| `kind` | Exclusion family, commonly `manual` or `outlier`. |
| `reason` | User reason or outlier rule label. |
| `scope` | Ledger-row scope, usually `cell` or `animal`, describing whether the record applies to one metric cell or an expanded subject-level set of metric cells. The `animal` value is retained for compatibility. |
| `fill` | Actual fill value to write when exclusions are applied. |

## Optional Fields

The ledger columns are fixed, but values can be empty when a field is not known.
For example, manual cell exclusions may not have a group label, and mark-only
outlier ledgers can later be realized with the recorded `fill`.

`exclusion_summary` is separate from the ledger. Common keys include:

| Key | Meaning |
|---|---|
| `action` | `mark` or `exclude`. |
| `scope` | Scope used for the operation. This summary-level value can be `manual` for explicit manual calls or `ledger` when a previously marked ledger is applied. |
| `roi` | ROI base affected. |
| `methods` | Outlier methods for automatic exclusions. |
| `n_excluded_cells` | Number of affected cells. |
| `n_animals_affected` | Number of unique subjects affected. The key name is retained for compatibility. |
| `reasons` | Manual reasons, when available. |

## Example

```text
| AnimalName | column | group | original_value | kind | reason | scope | fill |
|---|---|---|---:|---|---|---|---|
| Mouse_04 | GFAP Volume | AD | 500.0 | outlier | mad | cell | EXCLUDED_OUTLIER:mad |
| Mouse_07 | IBA1 Volume |  | 42.1 | manual | damaged section | animal | EXCLUDED_MANUAL:damaged section |
```

Mark, inspect, then apply:

```python
from PyFLASH.exclusions import apply_exclusions, mark_subjects

marked = mark_subjects(batch, "Mouse_07", reason="damaged section")
print(marked.exclusions)

cleaned = apply_exclusions(marked)
```

## Produced By

- [`mark_outliers`](../functions/exclusions.md) and [`exclude_outliers`](../functions/exclusions.md).
- [`mark_subjects`](../functions/exclusions.md), [`exclude_subjects`](../functions/exclusions.md), and their legacy animal aliases.
- [`mark_exclusions`](../functions/exclusions.md) and [`apply_exclusions`](../functions/exclusions.md) when explicit cells or subjects are supplied.

## Consumed By

- `apply_exclusions()` when called on a marked object with no explicit cells or subjects.
- Downstream plots, pipelines, and modelling helpers through the cleaned summary tables.
- [`data_overview`](../functions/data_overview.md), which counts excluded cells separately from missing values in its quality-control outputs.

## Notes

- Automatic outlier fills use `EXCLUDED_OUTLIER` or `EXCLUDED_OUTLIER:<rule>`.
- Manual fills use `EXCLUDED_MANUAL` or `EXCLUDED_MANUAL:<reason>`.
- Every `EXCLUDED_` sentinel is treated as analysis-missing by numeric coercion paths.
- Passing `fill` can override the sentinel. For example, `fill=np.nan` records and applies plain missing values.
- `scope="cell"` excludes only flagged cells. `scope="animal"` expands to multiple metric columns for affected subjects; the scope value is retained for compatibility.
- `clear_exclusions()` returns a cleaned copy with an empty ledger.

## See Also

- [Exclusions functions](../functions/exclusions.md)
- [Summary Table](summary-table.md)
- [Statistics look wrong](../troubleshooting/statistics-look-wrong.md)
