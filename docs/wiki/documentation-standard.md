# Documentation Standard

Use this format for new function pages in `docs/wiki/functions/`.

## Page Shape

````markdown
# function_name

## Summary
One short paragraph explaining what the function does and why a user would call it.

## Signature
```python
function_name(...)
```

## Input Object Types
| Object type | Accepted? | Notes |

## Parameters
| Parameter | Type | Default | Meaning |

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

Use "Accepted values" when a parameter has a controlled vocabulary:

```markdown
| `cv` | `str` | `"stratified5"` | Cross-validation scheme. Accepted values: `"stratified5"`, `"stratifiedN"`, or `"loo"`. |
```

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
