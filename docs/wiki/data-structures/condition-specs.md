# Group Specs

## Summary

Group specs are JSON-serializable dictionaries that describe experimental
groups without storing live Python objects. The UI project file keeps
these specs under `Project.conditions`, and PyFLASH rebuilds a real
`conditionList` by replaying the spec through `ConditionBuilder`.

Current Python code also exposes group-named aliases such as `GroupBuilder` and
`groupList`, but project files still store the spec under `conditions`.

This keeps project files portable and avoids pickling group objects.

## Where It Appears

- `PyFLASH.ui.project_io.Project.conditions`.
- JSON written by `Project.to_json()` or `save_project()`.
- UI services that build and preview conditions/groups.
- Workflow code that calls `build_condition_list(spec)`.

## Required Fields

Single-factor specs use:

| Key | Meaning |
|---|---|
| `factor` | Factor name, such as `Diagnosis`. |
| `entries` | List of group entries. Each entry needs at least `label`. |

Each `entries` item can contain:

| Key | Meaning |
|---|---|
| `label` | Full group name. Used as the display label and default short name. |
| `short` | Optional short name used in combined/crossed group names. |
| `color` | Optional color name or hex string. Palette names are resolved by PyFLASH. |
| `style` | Optional second visual channel. Defaults to `"fill"`. |

Crossed specs use:

| Key | Meaning |
|---|---|
| `crossed` | `true` for a two-factor crossed design. |
| `factors` | Exactly two single-factor specs. |

## Optional Fields

| Key | Meaning |
|---|---|
| `comparisons` | Comparison mode and its settings. |
| `explanation` | Text template attached to conditions/groups. `<>` is replaced by each name by the builder. |
| `order_by` | Crossed-design factor used to regroup group order. |

Supported comparison shapes are:

```json
{"mode": "pairs", "pairs": [["Control", "AD"]]}
```

```json
{"mode": "all_pairs"}
```

```json
{"mode": "vs_control", "control": "Control"}
```

```json
{"mode": "sequential"}
```

For crossed designs, `pairs` can include a third `within` value, and
`all_pairs` or `vs_control` can include `within_factor`.

The full `Project` JSON contains more than conditions. Stable project keys are:
`name`, `experiment_paths`, `batch_path`, `experiments`, `pickle_path`,
`threshold`, `import_images`, `conditions`, and `schema_version`.

## Example

Single factor:

```json
{
  "factor": "Diagnosis",
  "entries": [
    {"label": "Control", "short": "Control", "color": "grey"},
    {"label": "AD", "short": "AD", "color": "red"}
  ],
  "comparisons": {"mode": "pairs", "pairs": [["Control", "AD"]]},
  "explanation": "Diagnosis group: <>"
}
```

Crossed design:

```json
{
  "crossed": true,
  "factors": [
    {
      "factor": "Diagnosis",
      "entries": [
        {"label": "Control", "short": "C"},
        {"label": "AD", "short": "A"}
      ]
    },
    {
      "factor": "Sex",
      "entries": [
        {"label": "Female", "short": "F", "style": "fill"},
        {"label": "Male", "short": "M", "style": "///"}
      ]
    }
  ],
  "order_by": "Sex",
  "comparisons": {"mode": "all_pairs", "within_factor": "Sex"}
}
```

Rebuild in Python:

```python
from PyFLASH.ui.project_io import build_condition_list

conditions = build_condition_list(spec)
```

## Produced By

- UI group setup and project saving.
- Manual project JSON creation.
- `Project.to_json()` and `save_project()`.

## Consumed By

- `Project.condition_list()`.
- `build_condition_list()` and `build_factor_list()`.
- Streamlit-free UI services such as `build_conditions()` and `preview_conditions()`.
- Batch creation workflows that pass rebuilt conditions into [`create_batch`](../functions/create_batch.md).

## Notes

- Empty `{}` means no conditions have been defined and rebuilds to `None`.
- Unknown extra fields on the top-level project JSON are ignored when loading into `Project`.
- Comparison names are resolved by the underlying condition builder. A misspelled comparison can raise a `ValueError` with a suggestion.
- Use specs for saved UI projects. Use live `conditionList`/`groupList` objects only in Python code.

## See Also

- [Groups](../object-types/conditions.md)
- [ConditionBuilder](../functions/condition-builder.md)
- [Build groups workflow](../workflows/build-conditions.md)
- [Groups and factors parameters](../parameters/conditions-and-factors.md)
