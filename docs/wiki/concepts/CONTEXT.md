# Concepts Folder Context

This folder is for cross-cutting explanations that do not fit a more specific
reference section.

## What Belongs Here

Before adding a page here, check whether it belongs in one of the more specific
reference folders:

- `../object-types/` for Python objects users pass around.
- `../data-structures/` for tables, specs, schemas, ledgers, and manifests.
- `../plot-types/` for visual plot families.
- `../parameters/` for reusable parameters and option vocabularies.
- `../statistics/` for statistical methods and interpretation.
- `../outputs/` for saved files and folders.

Use `concepts/` for explanatory glue that crosses several of those categories.

Good concept pages include:

- what the concept is;
- where users encounter it;
- required columns or object attributes;
- common valid values;
- short examples;
- pitfalls and how to recognize them;
- links to relevant function pages.

## Current Root Concepts

The root wiki already has [Object model](../object-model.md). Do not move it
unless the user asks. New concept pages can link to it.

## Planned Pages

Useful future concept pages that may still belong here:

- `colocalisation.md`: marker combination terms, positive/negative state names,
  family metrics, and exported column labels.
- `crossed-designs.md`: how factors, conditions, labels, colors, comparisons,
  and styles fit together across objects, parameters, and plots.
- `roi-and-region-language.md`: conceptual difference between region, ROI,
  ROI base, hemisphere, image ROI, and `filter_by` row filters.
- `colocalisation-language.md`: plain-language meaning of combo families,
  positive/negative states, any/contains/coloc terms, and exported labels.
- `reproducible-analysis.md`: how pickles, specs, manifests, seeds, and saved
  outputs work together.

## Source Checks

Use these source areas when writing concept pages:

- Conditions: `PyFLASH/conditions.py`
- Summary creation and marker columns: `PyFLASH/experiment.py`,
  `PyFLASH/markers.py`, `PyFLASH/export.py`
- `filter_by` / row-filter and output path helpers: `PyFLASH/utils.py`
- Statistics: `PyFLASH/stats.py`, `PyFLASH/stats_extra.py`
- Exclusions: `PyFLASH/exclusions.py`
- Plot specs and registry: `PyFLASH/spec.py`

Prefer short examples over exhaustive parameter tables. Parameter tables belong
in `../functions/`.
