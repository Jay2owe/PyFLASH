# Structured Results

## Summary

Structured results are machine-readable records that summarize statistical
outputs in a consistent shape. PyFLASH uses them for report digests, pipeline
manifests, and function describe coverage.

## Where PyFLASH Uses It

- Group-comparison, correlation, regression, linear-model, cosinor, and
  acrophase functions can emit report records when the collector is active.
- Pipelines write `manifest.json` files that describe inputs, options, output
  paths, selected results, skipped results, and run metadata.
- The function registry marks which functions have reviewed structured
  descriptions, which are exempt, and which remain unreviewed.
- [Report records](../outputs/report-records.md) describes the output-facing
  record format.

## Inputs

Report records are built from the same objects used to create plots and tables:
group summaries, pairwise test rows, correlation coefficients, model
coefficients, adjusted means, and pipeline result summaries.

The report collector is opt-in. When it is not active, emit calls are inert and
the analysis still runs normally.

## Outputs

Structured output can include:

- `kind`: the record type, such as group comparison, correlation, or linear
  model.
- descriptive statistics and test statistics.
- p-values, q-values, effect-size strings, and pairwise rows.
- direction and headline text generated from numeric results.
- pipeline manifests with saved paths, selected rows, skipped rows, and option
  settings.
- digest text rendered from collected records.

Large tables are summarized before being stored in records. DataFrame payloads
are converted to JSON-safe summaries with shape, columns, and a bounded set of
leading rows.

## Interpretation

Structured records are summaries of the actual tables and figures. Use them to
trace what was run, compare options across runs, or generate a report digest.
For detailed interpretation, open the corresponding CSV tables and read the
specific statistics page for the method.

The describe registry is a coverage tool. `DESCRIBE_COVERED` contains functions
that emit structured report records or return a pipeline manifest. That can
happen through the shared statistics engine, a direct `report.emit(...)` call,
or a pipeline return object.

`DESCRIBE_EXEMPT` contains visual or descriptive functions that do not have an
inferential result to capture. `DESCRIBE_UNREVIEWED` contains functions that do
compute quantitative or inferential results, such as p-values, correlations, or
variance explained, but have not yet been wired into the structured-results
layer. Treat unreviewed entries as tracked coverage gaps, not hidden methods.

## Limitations

Report records are not a complete audit log of every intermediate calculation.
They are intentionally compact and may truncate large DataFrame previews. A
digest is generated text from structured fields; it should not replace checking
sample sizes, filters, skipped rows, and raw output tables.

Manifests describe a run but do not validate that a statistical design is
appropriate. They should be read with the method-specific pages and the original
analysis plan.

## See Also

- [Report records](../outputs/report-records.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [api-reference](../api-reference.md)
- [Group Comparisons](group-comparisons.md)
- [Correlation](correlation.md)
- [Linear Models](linear-models.md)
