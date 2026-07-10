# Gallery Folder Context

This folder is for example-driven pages with small, focused snippets and, when
available, rendered figures or output excerpts. It is the PyFLASH equivalent of
a plotting-library examples gallery.

## What Belongs Here

Add pages that demonstrate a complete but narrow example, such as:

- `mean-bars-basic.md`
- `grouped-mean-bars.md`
- `correlation-matrix.md`
- `adjusted-correlation-run.md`
- `image-grid.md`
- `representative-panels.md`
- `model-sweep-small.md`
- `load-table-with-from-dataframe.md`
- `plot-spec-batch.md`

Gallery pages can overlap with workflows, but they should be shorter and more
visual. Workflows explain a full task; gallery examples show a compact pattern.

## Page Shape

Use this shape:

```markdown
# Example title

## Goal
One sentence describing the example.

## Code
Copy-pasteable code.

## Result
Figure, table excerpt, saved files, or returned keys.

## Notes
Small explanation of choices made in the example.

## See Also
Function pages and related plot type pages.
```

## Data Rules

- Use synthetic, public-safe, or deliberately anonymized examples.
- Do not commit private analysis outputs.
- If a rendered image is added later, use a stable relative path and document
  how it was produced.
- Keep examples short enough that users can adapt them quickly.

## Source Checks

When a gallery page demonstrates a function, also verify the detailed function
page and source signature are current.
