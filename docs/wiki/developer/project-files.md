# Project Files

## Summary

A UI *project* is the small, JSON-serializable description of what a user is
building in the Streamlit app: a name, the experiment folder paths, a threshold,
and the condition definitions. It is defined and (de)serialized by
`PyFLASH/ui/project_io.py` and is deliberately distinct from the in-memory
`Batch` / `Experiment` object — a project can be saved and reloaded without
re-running `create_batch`.

## What Is Persisted

The `Project` dataclass round-trips to JSON via `to_json` / `from_json`. Its
fields:

- `name` — project label.
- `experiment_paths` — ordered experiment folders selected in the UI.
- `batch_path` — root/results folder; `experiments` — an optional
  `{name: folder}` map (manual mode), empty when auto-discovering from
  `batch_path`; `pickle_path` — the cache directory.
- `threshold` — defaults from `Config.THRESHOLD` at construction time.
- `import_images` — whether to load images.
- `conditions` — the condition **spec** (see below), not built condition
  objects.
- `schema_version` — `SCHEMA_VERSION` (currently `1`); bump on schema changes.

`from_dict` accepts only known dataclass fields, so a forward-compatible file
with extra keys loads without crashing.

## The Condition Spec And Rebuild

The house rule is: **never pickle built `condition` objects.** Conditions are
stored as a spec (factor name, entries with `label`/`short`/`color`/`style`,
comparison mode, explanation) and replayed on load through
`PyFLASH.conditions.ConditionBuilder`.

`build_condition_list(spec)` dispatches on `spec["crossed"]`:

- **Simple design** — one factor: `build_factor_list` creates a
  `ConditionBuilder`, `add`s each entry (`style` defaults to `"fill"`), applies
  the comparison mode via `_apply_comparisons`, applies the explanation, and
  returns `builder.build()`.
- **Crossed (factorial) design** — `spec["factors"]` must have exactly two
  factor specs; each is built, crossed via `ConditionBuilder.cross`, then
  `order_by` and `within=`-aware comparisons are applied.

Comparison modes handled by `_apply_comparisons`: `pairs` (rows `[a, b]`, or
`[a, b, within]` when crossed), `all_pairs`, `vs_control` (with `control`), and
`sequential` (simple builder only). Builder `ValueError`s — including difflib
"Did you mean…?" suggestions — propagate to the caller on purpose.

The full JSON shape is documented in the `project_io.py` module docstring and in
[Group specs](../data-structures/condition-specs.md).

## Notes For Maintainers

- Keep this module Streamlit-free (it is imported by `PyFLASH.ui.services`).
- If you add a `Project` field, bump `SCHEMA_VERSION` and keep `from_dict`
  tolerant of older files. Coverage lives in `tests/test_ui_conditions.py`.

## See Also

- [UI Services](ui-services.md)
- [Group specs](../data-structures/condition-specs.md)
- [Testing Map](testing-map.md)
