# Object Types Folder Context

This folder is the object reference for PyFLASH. Use it for pages that explain
the Python objects users create, pass into functions, inspect, or receive back.

## What Belongs Here

Each page should document one object type or a tightly related object family.
Examples:

- `batch.md` for `Batch`
- `experiment.md` for `Experiment`
- `mini-experiment.md` for `MiniExperiment`
- `dataframe-experiment.md` for `DataFrameExperiment`
- `groups.md` for `group`, `multiGroup`, `groupList`, and `GroupBuilder`;
  mention `condition`, `multiCondition`, `conditionList`, and
  `ConditionBuilder` only as legacy aliases where they remain accepted
- `markers.md` for `Attribute`, `Antibody`, `cellMarker`, and `objectMarker`
- `config.md` for `Config` and package-wide settings
- `project.md` for UI `Project` files when documenting developer/user project
  state

The root [Object model](../object-model.md) is the short overview. This folder
is for detailed object pages.

## Page Shape

Use this shape for object pages:

```markdown
# ObjectName

## Summary
What the object represents and when users encounter it.

## How To Create It
Constructors, factory functions, or common loaders.

## Important Attributes
Table of public attributes users are expected to inspect or pass onward.

## Common Methods
Table of methods users are expected to call.

## Accepted By
Important functions that accept this object type.

## Returned By
Functions that return this object type.

## Examples
Short copy-pasteable examples.

## Notes
Lifecycle, caching, mutation, compatibility, or edge cases.

## See Also
Related object, function, workflow, or data-structure pages.
```

## Source Checks

Use these source files before writing:

- `PyFLASH/batch.py`
- `PyFLASH/experiment.py`
- `PyFLASH/dataframe.py`
- `PyFLASH/conditions.py`
- `PyFLASH/markers.py`
- `PyFLASH/config.py`
- `PyFLASH/ui/project_io.py`
- related tests in `tests/`

Do not document every private implementation detail. Focus on the stable
surface a user or future agent needs to understand the library.
