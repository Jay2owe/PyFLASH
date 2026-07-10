# Data Structures

PyFLASH objects are Python wrappers around a few recurring data shapes:
subject-level summary tables, row-level marker tables, image metadata, ROI
tables, JSON-style condition specs, plot spec files, exclusion ledgers, and
pipeline manifests. These pages explain those structures directly, so you can
inspect or prepare data without reading the source code.

Use the object pages for lifecycle questions such as how a [`Batch`](../object-types/batch.md)
is created. Use these data-structure pages when you need to know what columns,
keys, or files a function expects.

| Page | Use It For |
|---|---|
| [Summary Table](summary-table.md) | Columns in `experiment.summary`, `batch.summary`, `batch.summaries`, and table-backed inputs. |
| [Marker Tables](marker-tables.md) | Row-level object, cell, antibody, attribute, behaviour, and colocalisation tables in `.data`. |
| [Image Table](image-table.md) | Image metadata columns, image path lookup, and how summary metadata is attached. |
| [ROI Tables](roi-tables.md) | ROI property tables, ROI zip coordinate records, `master_region`, and `ImageROI` names. |
| [Condition Specs](condition-specs.md) | JSON-serializable condition definitions used by UI projects and `build_condition_list`. |
| [Plot Spec Files](plot-spec-files.md) | YAML, TOML, and JSON files passed to [`run_spec`](../functions/run_spec.md). |
| [Exclusion Ledgers](exclusion-ledgers.md) | The audit table attached by exclusion helpers and optionally saved as CSV. |
| [Pipeline Manifests](pipeline-manifests.md) | `manifest.json` and `_runs_index.csv` records written by analysis pipelines. |

## Stable Identifiers

Most PyFLASH analysis functions expect or create these normalized identifiers:

| Name | Meaning |
|---|---|
| `AnimalName` | Internal subject/sample identifier. DataFrame inputs can map another column to this with `subject_col`; `animal_col` remains a legacy alias. |
| `Condition` | Internal group label used by group-aware plots and pipelines. DataFrame inputs can map another column to this with `group_col`; `condition_col` remains a legacy alias. |
| Factor columns | Extra grouping columns such as `Diagnosis`, `Sex`, or `Time`, usually derived from a group list. |
| `Region` | A concrete ROI instance, such as `SCN1`. |
| `ROI` | ROI label stored on a row. It may be a concrete ROI instance such as `SCN1` or a base/family value such as `SCN`; use ROI-base helpers or parameters when you need family-level selection. |
| `ImageROI` | The image-panel ROI label, such as `LHSCN` or `RHSCN2`. |

## Compatibility Notes

PyFLASH normalizes several input styles into these structures. Folder-backed
experiments come from FLASH/ImageJ CSV and ROI files, while table-backed
experiments come from `pandas.DataFrame` objects. The normalized columns are
stable, but metric columns depend on the markers and ImageJ exports present in
your data.

Missing or deliberately excluded values use explicit sentinel strings in some
tables. Do not treat those sentinels as real measurements; PyFLASH numeric
coercion paths treat them as analysis-missing.
