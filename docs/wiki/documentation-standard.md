# Documentation Standard

Use this format for new function pages in `docs/wiki/functions/`.

## Page Shape

````markdown
# function_name

## Summary
One short paragraph explaining what the function does and why a user would call it.

## Example figure
For plotting functions with a gallery image, show the gallery render call above
the figure. The call block is generated from `docs/wiki/examples/gallery_examples.py`.

## Signature
```python
function_name(...)
```

## Input Object Types
| Object type | Accepted? | Notes |

## Parameters
| Parameter | Type | Default | Meaning |

## Parameter Options
Separate option tables for parameters with controlled values.

## Returns
| Return value | Type | Meaning |

## Saved Outputs
List files/folders written when `save=True`.

## Examples
Copy-pasteable Python snippets.

## Notes
Important behavior, edge cases, and interpretation guidance.

## See Also
Related functions and concepts.
````

## Type Vocabulary

Use these names consistently:

| Type name | Meaning |
|---|---|
| `Batch` | A processed collection of one or more `Experiment` objects. Most analysis and plotting functions accept this. |
| `Experiment` | One imaging experiment imported from FLASH/ImageJ output folders. |
| `MiniExperiment` | A lightweight object for flat CSV-style data. |
| `pandas.DataFrame` | A table. In PyFLASH docs, usually `batch.summary` unless stated otherwise. |
| `groupList` | Ordered group metadata, including labels, colors, factors, and planned comparisons. Legacy docs and code may also call this `conditionList`. |
| `matplotlib.figure.Figure` | A Matplotlib figure object. |
| `dict` | A structured Python dictionary. Always document important keys. |

## Parameter Wording

Keep the main parameter table focused on what each parameter controls in
general. Do not use the `Meaning` cell to explain every accepted value.

```markdown
| `cv` | `str` | `"stratified5"` | Cross-validation scheme. |
```

When a parameter has a controlled vocabulary, add a separate option table after
the main parameter table. This keeps the parameter definition stable and makes
the behavioral difference between values explicit.

```markdown
### `cv` options

| Option | Behavior |
|---|---|
| `"stratified5"` (default) | Uses up to five stratified folds, capped by the smallest class count. |
| `"stratifiedN"` | Uses `N` stratified folds, for example `"stratified2"` for two folds. |
| `"loo"` / `"leave_one_out"` | Uses leave-one-out cross-validation. |
```

Use this option-table style for string enums, named modes, collision policies,
model presets, test names, gates, and any boolean where `True` and `False`
change the workflow in a way users need to understand. Mark the default option
with `(default)`. Keep aliases in the main parameter table when they are
signature aliases, but document option behavior only once under the preferred
parameter name.

Prefer one row per public concept. When several names resolve to the same
setting, use the preferred public name in the `Parameter` cell and list aliases
inside that row instead of giving each alias its own row.

```markdown
| `data_col_contains` | `str`, list-like, or `None` | `None` | Selects columns whose names contain these text fragments. Aliases: `column_strings`. |
| `subject_col` | `str` or `None` | `None` | Identifies subjects, animals, or samples. Aliases: `animal_col`. |
```

Only use a separate alias row when the alias has different behavior that users
must understand independently. If the only difference is a legacy default, keep
one preferred row and mention the legacy default in the alias note.

Use "Path-like" for values accepted by `pathlib.Path` or plain strings:

```markdown
| `output_dir` | Path-like or `None` | `None` | Folder for saved tables and figures. |
```

## Output Wording

Separate return values from saved files:

- **Returns** are Python objects the caller receives immediately.
- **Saved outputs** are files written to disk, usually when `save=True`.

For result dictionaries, list the most important keys first. Do not try to
document every internal key unless users are expected to use it.

## Example Requirements

Every function page should include at least:

- A minimal example.
- A realistic example.
- One example showing how to inspect or reuse the returned object.

For plotting functions, include one `save=False` example when the function can
return a figure or data without writing files.

For plotting functions with a rendered gallery example, keep the `## Example
figure` code block synchronized by running:

```bash
python docs/wiki/examples/update_gallery_snippets.py
```

## Object Compatibility Table

Include this table on pages where object compatibility matters:

```markdown
| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported input. |
| `Experiment` | Yes | Works when it exposes the same attributes used by the function. |
| `MiniExperiment` | Yes/No | Explain limitations. |
| `pandas.DataFrame` | Yes/No | Explain whether raw tables are accepted. |
```
