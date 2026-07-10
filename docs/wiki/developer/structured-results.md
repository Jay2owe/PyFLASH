# Structured Results

## Summary

`PyFLASH/report.py` (the "describe" layer) is a guarded, opt-in collector that
captures the descriptive and inferential numbers a plot already computes — per
group n/mean/SD, test name, p-values, effect sizes, correlation r/p, model
coefficients — instead of drawing them onto a PNG and discarding them. This lets
an agent answer questions from structured facts rather than OCR-ing an image.
This page is the maintainer view; the reader-facing versions are
[report records](../outputs/report-records.md) and
[statistics/structured results](../statistics/structured-results.md).

## Inert By Default

The collector is a single module-global state (`_STATE`). Nothing on the core
plotting path changes unless a caller arms it:

- `report.start()` arms it and clears prior records.
- `report.is_active()` is what plotting/stats code checks before doing any work.
- `report.emit(record)` appends a record — but only when armed, and it is fully
  guarded so it can never raise into a plot; a non-dict/malformed record is
  silently dropped.
- `report.collect()` returns the records and disarms.

Because it is inert unless armed, `import PyFLASH.report` is cheap (stdlib only;
numpy/pandas are lazy) and core plotting is unchanged.

## How Producers Emit

- **Group comparisons** — `stats.py::multipleComparisons` builds a record with
  `build_comparison_record` and emits it (feeds `plot_mean_bars` and friends).
- **Regressions / correlations** — `plotting.py::regression_action` and the
  correlation plots emit `build_multivariable_regression_record` /
  `build_correlation_record`.
- **Pipelines** — `correlation`, `adjusted_correlation`, `linear_model`,
  `data_overview`, and the rhythm pipeline emit records and/or return a manifest
  dict that `summarize_return` coerces into a bounded JSON summary.

The `build_*_record` helpers also compute a plain-language `headline` so a digest
is human-readable.

## The Runner's results_store Tiers

The `/pyflash` runner arms the collector per run, then persists three tiers under
`.runtime/results_store/`:

- **Tier 1** — `<run_id>.results.json`: the canonical structured manifest.
- **Tier 2** — `<run_id>.results.md`: a deterministic markdown digest rendered
  mechanically by `render_digest` (no LLM, so numbers cannot be hallucinated).
- **Ledger** — an append-only `index.jsonl` with one compact row per run.
- **Tier 3** — `lab_notebook.md`: agent interpretations, written at read time.

Drive the rundown with the runner's `runs` / `result` / `note` subcommands.

## Coverage Is Enforced

Every `PLOT_REGISTRY` entry must be classified `DESCRIBE_COVERED` /
`DESCRIBE_EXEMPT` / `DESCRIBE_UNREVIEWED` in `spec.py`;
`tests/test_describe_coverage.py` fails otherwise, and `tests/test_report.py`
covers the collector and record builders. When you add a stats-bearing plot,
emit into `report` and mark it `DESCRIBE_COVERED`.

## See Also

- [Plot Registry](plot-registry.md)
- [Report records](../outputs/report-records.md)
- [Statistics: structured results](../statistics/structured-results.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
