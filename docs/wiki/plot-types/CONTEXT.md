# Plot Types Folder Context

This folder is the visual guide to PyFLASH plot families. It is similar in
spirit to a plotting-library "plot types" section: users should be able to pick
the kind of figure they need before reading a detailed function page.

## What Belongs Here

Add one page per plot family or closely related visual family. Examples:

- `mean-bars.md`
- `matrix-plots.md`
- `regression-plots.md`
- `distribution-plots.md`
- `image-panels.md`
- `location-plots.md`
- `colocalisation-plots.md`
- `model-summary-plots.md`
- `rhythm-plots.md`
- `group-comparison-plots.md`

These pages explain when to use a plot type, what data it expects, and which
function pages to read next. Detailed parameter tables still belong in
`../functions/`.

## Page Shape

Use this shape:

```markdown
# Plot type name

## Use This When
The question this plot answers.

## Input Data
Object types, columns, markers, or image data required.

## Main Functions
Table of relevant functions and registry names.

## Common Options
High-level options users should understand before using the functions.

## Outputs
Figures, tables, and report records commonly produced.

## Examples
Short examples that link to detailed function pages.

## Interpretation
How to read the plot and common mistakes.

## See Also
Related plot types, concepts, and functions.
```

## Registry Source

Use `PyFLASH/spec.py::PLOT_REGISTRY` as the source of truth for registered plot
names. Also inspect the matching `plot_*` function in `PyFLASH/plotting.py` and
tests that exercise it.

If a plot has no rendered example yet, describe the visual result in words and
leave a clear note for a later gallery example.
