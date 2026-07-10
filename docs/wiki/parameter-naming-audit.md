# Parameter Naming Audit

This audit maps the public-facing parameter names that were most likely to
confuse users as PyFLASH expanded beyond ImageJ-derived animal experiments and
started accepting raw `pandas.DataFrame` input directly.

## Current Status

The first alias pass is implemented. New code and examples should prefer
`data_cols`, `group`, `groupList`, `group_col`, `group_cols`, `subject_col`,
`filter_by`, and `split_by` where a function supports them. Legacy names remain
accepted for compatibility. The remaining items below are a migration record and
future cleanup guide, not a list of aliases still wholly missing.

## Recommendation

Use these names as the new public vocabulary:

| Concept | Preferred public name | Keep as legacy alias |
| --- | --- | --- |
| Any analyzable input object | `data` | `experiment`, `batch`, `source`, `batch_or_df` |
| Biological or sample unit | `subject` / `subject_col` | `animal`, `animals`, `animal_col`, `AnimalName` |
| Grouping column for raw data | `group_col` | `condition_col` |
| Multiple crossed grouping columns | `group_cols` | `factor_cols` |
| Advanced PyFLASH group objects | `group_list` / `groups` | `conditionList`, `conditions` |
| Columns being analyzed | `data_cols` / `data_col` | `filtered_columns`, `columns`, `column` |
| Data-column substring filter | `data_col_contains` | `column_strings` |
| Data-column regex filter | `data_col_regex` | `regex_string` |
| Data-column exclusions during discovery | `data_col_exclude` | `exclude` |
| Split output into panels/groups | `split_by` | `by`, `factor` |
| Filter rows before analysis | `filter_by` | `specificity` |
| Region of interest selector | `roi` | keep |
| Internal summary table | `summary` | keep |
| Model predictors | `predictors` | keep |
| Model target/outcome | `target` or `outcome` | `dependent_variable`, `dependent_variables` |

The strongest recommendation is to rename all public `animal*` parameters to `subject*` before expanding DataFrame support further. Human data will otherwise inherit misleading wording in every direct-call example.

## Why Not Rename Everything Internally Now

`AnimalName` is a deeply embedded internal schema column. It appears in batch merging, experiment import, exclusions, plotting, image matching, exports, tests, and generated docs. A hard internal rename to `SubjectID` would be high risk.

The implemented safer approach is:

1. Add public `subject_col`, `subjects`, and `subject_filter` aliases where supported.
2. Normalize user input internally to the existing `AnimalName` column for compatibility.
3. Update documentation to describe `AnimalName` as the internal subject/sample identifier.
4. Consider an internal `SubjectID` migration later, after the public API is stable.

## Data Input Names

Current names found in signatures:

| Current name | Count | Main use | Recommendation |
| --- | ---: | --- | --- |
| `experiment` | 122 | Most plotting, pipeline, exclusion, iteration APIs | Public alias should be `data`; keep `experiment` internally where it really means a PyFLASH object. |
| `batch` | 18 | Batch-only/stat helper APIs and UI services | Use `data` if DataFrame or Experiment can work; keep `batch` only when a true `Batch` is required. |
| `source` | 51 | Representative image and coloc internals; a few public image/coloc functions | Use `data` for public APIs. |
| `batch_or_df` | 1 | `iterative_model_sweep` | Rename to `data`. |
| `batch_or_dict` | 1 | Spec runner service | Rename to `data` or `datasets`. |
| `df` | 114 | Internal helpers and stats utilities | Keep for private helpers; use `data` or `summary` publicly. |
| `summary` | 11 | DataFrame adapter and display/export helpers | Keep. It is clear. |

Target pattern:

```python
plot_mean_bars(data, data_cols=None, group_col="Condition", subject_col=None)
correlation(data, data_cols=None, split_by="all", filter_by=None)
iterative_model_sweep(data, target, predictors=None)
```

## Subject Names

Current subject/animal names found in signatures and text:

| Current name | Count | Recommended name | Notes |
| --- | ---: | --- | --- |
| `animal_col` | 21 | `subject_col` | Highest priority rename. Add alias everywhere DataFrames are accepted. |
| `animal_column` | 1 | `subject_column` | `MiniExperiment` import edge. Keep `animal_column` as a legacy alias. |
| `animals` | 6 | `subjects` | Used by manual exclusion functions. |
| `animal_filter` | 8 | `subject_filter` | Used by image and representative-image functions. |
| `show_animal_xs` | 2 | `show_subject_points` | Radar overlay option. |
| `animal_x_marker` | 2 | `subject_point_marker` | Radar overlay option. |
| `animal_x_size` | 2 | `subject_point_size` | Radar overlay option. |
| `animal_x_alpha` | 2 | `subject_point_alpha` | Radar overlay option. |
| `animal_x_color` | 2 | `subject_point_color` | Radar overlay option. |
| `animal_min_flags` | 4 | `subject_min_flags` | Outlier exclusion threshold. |
| `exclude_animals()` | public function | `exclude_subjects()` | Add new function, keep old as alias. |
| `mark_animals()` | public function | `mark_subjects()` | Add new function, keep old as alias. |
| `iter_animals()` | internal/public-ish | `iter_subjects()` | Add alias, then migrate callers. |
| `num_animals` | internal/public-ish | `num_subjects` | Add alias property. |
| `animal_df` | internal/public-ish | `subject_df` | Add alias property. |
| `col_animal_means()` | internal/public-ish | `col_subject_means()` | Add alias method. |
| `normalize_animal_name()` | utility | `normalize_subject_id()` | Keep old alias for image/import compatibility. |
| string mode `"animals"` | several plot modes | `"subjects"` | Keep `"animals"` as an accepted alias. |

Recommended public behavior:

```python
plot_mean_bars(
    df,
    data_cols=["GFAP_Count", "IBA1_Count"],
    group_col="Diagnosis",
    subject_col="Participant ID",
)
```

Internally this can still create/expect `AnimalName` until the schema migration is worth doing.

## Grouping And Group Objects

Current names:

| Current name | Count | Meaning today | Recommended name |
| --- | ---: | --- | --- |
| `condition` | class | One named analysis group, with label, color, style, and factor metadata | `group`; keep `condition` alias. |
| `conditionList` | class | Ordered group set plus comparison definitions | `groupList`; keep `conditionList` alias. |
| `multiCondition` | class | Crossed group made from multiple grouping factors | `multiGroup`; keep `multiCondition` alias. |
| `conditions` | 21 | PyFLASH `conditionList` or list of condition/group objects | `group_list` for a full group design, or `groups` for plain group objects; keep `conditions` alias. |
| `condition_col` | 15 | Raw DataFrame column used to infer simple conditions | `group_col`. |
| `factor_cols` | 14 | Raw DataFrame columns used for crossed conditions | `group_cols`. |
| `factor` | 55 | Sometimes condition factor, sometimes paneling column | Split into `group_col` for data definition and `split_by` for output grouping. |
| `by` | 41 | Output grouping/paneling mode | `split_by`. |
| `group` | 9 | Linear model group term | `group_col` or `primary_group`. |
| `group_col` | 23 | Time/rhythm/stats grouping column | Keep and reuse broadly. |
| `hue_column` | 2 | Plot color grouping | `color_by` or `group_col`, depending on function. |
| `split_by` | 3 | Overview split grouping | Keep and expand. |
| `specificity` | 81 | Row filter tuple or queue of filters | `filter_by`. |

Recommended raw DataFrame grouping API:

```python
# One grouping column
from_dataframe(df, group_col="Diagnosis", subject_col="Participant")

# Crossed grouping columns
from_dataframe(df, group_cols=["Diagnosis", "Sex"], subject_col="Participant")

# Advanced style/comparison object
from_dataframe(df, group_list=my_group_list, subject_col="Participant")
```

Recommended plotting grouping API:

```python
# split output by diagnosis groups
plot_matrices(data, data_cols=[...], split_by="Diagnosis")

# analyze only one subgroup
plot_matrices(data, data_cols=[...], filter_by={"Sex": "Female"})
```

Recommended object API:

```python
from PyFLASH import group, groupList

control = group(label="Control", name="Control", color="black", factor="Diagnosis")
ad = group(label="AD", name="AD", color="red", factor="Diagnosis")
groups = groupList([control, ad], comparisons=["1-2"])
```

Keep `MiniExperiment` and `DataFrameExperiment` unchanged. Those names describe
where the data came from, and they do not create the animal/human mismatch.

## Data Column Selection

Current names:

| Current name | Count | Meaning today | Recommended name |
| --- | ---: | --- | --- |
| `filtered_columns` | 23 | Explicit data columns for analysis | `data_cols`. |
| `columns` | 47 | Mixed: export columns, analysis data columns, iteration columns | `data_cols` for analysis; keep `columns` for generic table/export operations. |
| `column` | 10 | Single analysis data column or outcome column | `data_col` or `target`, depending on context. |
| `dependent_variables` | 6 | Linear model outcomes | `outcomes` or `targets`. |
| `target` | 5 | Model target in model sweep | Keep for machine-learning APIs. |
| `x`, `y`, `z` | 27/28/2 | Scatter/regression axis columns | Keep in plotting APIs. |
| `predictors` | 21 | Model predictor columns | Keep. |
| `possible_predictors` | 3 | Candidate predictor columns | Keep for `iterative_best_fit`; `iterative_model_sweep` also accepts `predictors` / `candidate_predictors`. |
| `against_columns` | 5 | Second data-column set for rectangular correlation | `against_data_cols` or `x_data_cols`. |
| `first_columns` | 2 | Columns pinned to front of matrix | `leading_data_cols`. |
| `column_strings` | 28 | Substring data-column discovery | `data_col_contains`. |
| `regex_string` | 27 | Regex data-column discovery | `data_col_regex`. |
| `exclude` | 39 | Data-column-name exclusion in many analysis functions, but also export exclusions | `data_col_exclude` for analysis APIs. |

Recommended data-column selection API:

```python
plot_radar(data, data_cols=["GFAP_Count", "IBA1_Count"])
plot_radar(data, data_col_contains=["Count", "Intensity"], data_col_exclude=["Background"])
plot_radar(data, data_col_regex=r"_(Count|Area)$")
```

For specs, keep accepting `columns` as a friendly alias for `data_cols`.

## Region Names

Current names:

| Current name | Count | Recommendation |
| --- | ---: | --- |
| `roi` | 44 | Keep. It is standard in imaging and shorter than `region_of_interest`. |
| `roi_base` | 15 | Keep internally; consider public alias `region_base` only for DataFrame helper/docs. |
| `region_col` | 2 | Keep for DataFrame input. |
| `roi_filter` | 2 | Keep or alias to `region_filter` in image APIs. |

This is lower priority than subject/group/data-column naming.

## Function Hot Spots

These are the public APIs most affected by a naming cleanup:

| Function area | Current confusing names | Recommended public names |
| --- | --- | --- |
| DataFrame adapter | `conditions`, `condition_col`, `factor_cols`, `animal_col` | `group_list`, `group_col`, `group_cols`, `subject_col` |
| Direct DataFrame plotting | `experiment`, `filtered_columns`, `condition_col`, `factor_cols`, `animal_col` | `data`, `data_cols`, `group_col`, `group_cols`, `subject_col` |
| Correlation/data overview/group comparison pipelines | `experiment`, `filtered_columns`, `by`, `factor`, `specificity`, `animal_col` | `data`, `data_cols`, `split_by`, `group_col`, `filter_by`, `subject_col` |
| Linear model pipeline | `experiment`, `dependent_variables`, `group`, `animal_col` | `data`, `outcomes`, `group_col`, `subject_col` |
| Iterative model APIs | `batch`, `batch_or_df`, `possible_predictors`, `hue_column`, `animal_col` | `data`, `data`, `possible_predictors` or `candidate_predictors` where supported, `color_by`, `subject_col` |
| Image APIs | `animal_filter`, mode `"animals"` | `subject_filter`, mode `"subjects"` |
| Exclusions | `exclude_animals`, `mark_animals`, `animals`, `animal_min_flags` | `exclude_subjects`, `mark_subjects`, `subjects`, `subject_min_flags` |
| Radar overlays | `show_animal_xs`, `animal_x_*` | `show_subject_points`, `subject_point_*` |

## Migration Difficulty

| Change | Difficulty | Reason |
| --- | --- | --- |
| Add `subject_col` aliases to DataFrame-enabled functions | Easy | Centralized through `coerce_dataframe_input` and `from_dataframe`. |
| Add `group_col` / `group_cols` aliases | Easy | Maps directly to existing `condition_col` / `factor_cols`. |
| Add `data_cols` alias for `filtered_columns` | Medium | Many functions call `_resolve_filtered_columns`; doable with a shared alias helper. |
| Add `data_col_contains`, `data_col_regex`, `data_col_exclude` | Medium | Mostly mechanical but touches plotting, pipeline, modelling, exclusions, UI/spec docs. |
| Add `split_by` alias for `by` and `group_col` alias for `factor` | Medium | Needs care because `factor` also has condition-object meaning. |
| Add `filter_by` alias for `specificity` | Medium | Needs support for both tuple/list queues and a friendlier dict syntax. |
| Add `exclude_subjects` / `mark_subjects` | Easy | Thin wrappers over existing functions. |
| Add `"subjects"` mode alias for `"animals"` | Easy | Localized to iteration/location plotting modes. |
| Rename internal `AnimalName` to `SubjectID` | Hard | Touches import, batch merge, summaries, exclusions, plotting, image lookup, export, docs, and tests. |

## Migration Status And Remaining Order

1. Done for the first pass: add new aliases without breaking old calls:
   `subject_col`, `group`, `groupList`, `group_list`, `group_col`,
   `group_cols`, `data_cols`, `data_col_contains`, `data_col_regex`,
   `data_col_exclude`, `split_by`, and `filter_by`.
2. In progress: update docs and examples to prefer the new names while still
   documenting legacy names in signature references.
3. Done for the covered spec path: YAML/JSON specs accept the new names and map
   them to legacy call signatures where needed.
4. Future: add warnings for old public names only after examples and tests use
   the new names consistently.
5. Deferred: internal `AnimalName` rename unless public users specifically need
   exported files to say `SubjectID`.
