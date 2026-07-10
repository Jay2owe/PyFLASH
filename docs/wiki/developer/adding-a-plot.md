# Adding A Plot

## Summary

The operational checklist for adding a new plot or pipeline to PyFLASH so it is
usable from Python, the spec files, and the `/pyflash` runner — and so the
enforcement tests stay green. The authoritative implementation contract lives in
the global **`pyflash-add-plot`** skill; this page is the wiki-side map of the
steps and the files each one touches.

## Checklist

1. **Write the function.** Add `plot_<name>(...)` to `PyFLASH/plotting.py`
   following the signature conventions of neighbouring plots (accept `Batch` /
   `Experiment`, `save=`, `filter_by=`, and public column-selection params such
   as `data_cols`, `data_col_contains`, and `data_col_exclude`). Keep
   `specificity=` only as a legacy/internal compatibility alias. Save figures
   through `PyFLASH.utils.save_fig` so SVG text stays editable.

2. **Register it.** Add a short-name -> callable entry to
   `PyFLASH/spec.py::PLOT_REGISTRY`. Use a bare `'plot_<name>'` for a plotting
   function, or a dotted `'PyFLASH.pipeline.<name>'` for a pipeline callable. See
   [Plot Registry](plot-registry.md).

3. **Classify describe coverage.** Add the short-name to exactly one of
   `DESCRIBE_COVERED`, `DESCRIBE_EXEMPT`, or `DESCRIBE_UNREVIEWED` in `spec.py`.
   If the plot computes a test/correlation/model, route those numbers through the
   shared engine (`stats.multipleComparisons`, `plotting.regression_action`) or
   call `report.emit(...)` with a `build_*_record` from `PyFLASH/report.py`, then
   mark it `DESCRIBE_COVERED`. `tests/test_describe_coverage.py` fails until it is
   classified. See [Structured Results](structured-results.md).

4. **If it is a pipeline**, add the name to `pipeline.__all__`, give it a
   `montage=True` parameter, wear the `@montage_pipeline(...)` decorator, and tag
   headline figures with `save_fig(..., montage=True)` (pull regressions on with
   `capture_secondary(...)`). Otherwise add it to `pipeline.MONTAGE_EXEMPT` with a
   reason. `tests/test_pipeline_montage.py` enforces this.

5. **Document it.** Add a function page under `../functions/` following the
   [documentation standard](../documentation-standard.md), link it from
   [api-reference](../api-reference.md), and add it to the relevant
   `../plot-types/` or `../statistics/` page.

6. **Add tests** under `tests/` (a smoke test that it runs and saves; a describe
   emit test if covered). See [Testing Map](testing-map.md).

7. **Reference refresh.** `scripts/update_pyflash_references.py` regenerates the
   live-signature block in the skill reference and mirrors it to `.codex`; the
   Claude `PostToolUse` hook runs it automatically after edits. You maintain the
   hand-written teaching prose; the generated block self-heals from `discover`.

## See Also

- [Plot Registry](plot-registry.md)
- [Structured Results](structured-results.md)
- [Docs Maintenance](docs-maintenance.md)
- [Documentation standard](../documentation-standard.md)
