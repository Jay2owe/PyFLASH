# Glossary Folder Context

This folder is for short definitions of PyFLASH, microscopy, statistics, and
documentation terms. It should make the rest of the wiki easier to search and
read.

## What Belongs Here

Add glossary pages such as:

- `objects.md`: `Batch`, `Experiment`, `MiniExperiment`,
  `DataFrameExperiment`, `conditionList`, marker objects, and config.
- `data.md`: summary table, marker table, image table, ROI table, manifest,
  ledger, plot spec, pickle, and workbook.
- `microscopy.md`: ROI, region, marker, antibody channel, object marker,
  colocalisation, combo, intensity, volume, and count.
- `plots.md`: mean bars, matrix, volcano, regression, ridgeline, ECDF, Sankey,
  UpSet, radar, PCA, superplot, forest plot, and cosinor plot.
- `statistics.md`: p-value, correction, effect size, confidence interval,
  covariate, adjusted mean, cross-validation, AUC, balanced accuracy, and
  permutation test.
- `parameters.md`: `filter_by`, factor, comparison, `data_cols`,
  `data_col_contains`, `data_col_regex`, `data_col_exclude`, `save`,
  `run_label`, and `roi`.

If the glossary grows large, split alphabetically only after the topic pages
become hard to scan.

## Entry Shape

Use concise entries:

```markdown
## Term

Short definition in one or two sentences.

See also: links to deeper pages.
```

For overloaded terms, state the PyFLASH-specific meaning first. For example,
`filter_by` is the public row-filter parameter. `specificity` is the
legacy/internal alias and does not mean statistical specificity.

## Writing Rules

- Keep entries short.
- Prefer plain language over formal definitions.
- Link to detailed pages rather than duplicating their content.
- Include common synonyms or abbreviations when users may search for them.
- Do not use glossary pages as full tutorials.

## Source Checks

Use the relevant reference pages and source files before defining a term:

- `PyFLASH/__init__.py`
- `PyFLASH/experiment.py`
- `PyFLASH/batch.py`
- `PyFLASH/dataframe.py`
- `PyFLASH/conditions.py`
- `PyFLASH/markers.py`
- `PyFLASH/spec.py`
- `PyFLASH/plotting.py`
- `PyFLASH/stats.py`
- `PyFLASH/stats_extra.py`
- `PyFLASH/utils.py`
