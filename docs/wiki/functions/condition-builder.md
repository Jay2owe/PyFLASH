# GroupBuilder

## Summary

`GroupBuilder` builds the group metadata PyFLASH uses for condition order,
labels, colors, styles, factors, and planned comparisons. It is the preferred
user-facing name for the same class still exposed as `ConditionBuilder`.

This page covers the small public family of group helpers and their classic
condition-name aliases:

- `GroupBuilder` / `ConditionBuilder`
- `group` / `condition`
- `multiGroup` / `multiCondition`
- `groupList` / `conditionList`
- `zipGroups` / `zipConditions`
- `zipGroupLists` / `zipConditionLists`

The group names and classic condition names are aliases to the same underlying
objects.

## Signature

```python
from PyFLASH import (
    GroupBuilder,
    group,
    multiGroup,
    groupList,
    zipGroups,
    zipGroupLists,
)

builder = GroupBuilder(factor)

groups = (
    builder
    .add(label, short=None, color=None, style="fill")
    .compare(a, b)
    .compare_all_pairs()
    .compare_to_control(control)
    .compare_sequential()
    .explain(explanation)
    .build()
)

group_obj = group(label, name, color, factor, explanation=None, style="fill")
multi_group_obj = multiGroup(conditionsList, name=None, label=None, color=None, style=None)
groups = groupList(condition_list, comparisons=None, explanation=None)
groups_tuple = zipGroups(condition_labels, condition_names, condition_colors, factor)
crossed_tuple = zipGroupLists(group_list1, group_list2, newColors=None)

crossed = (
    GroupBuilder.cross(group_list1, group_list2, colors=None)
    .compare(a, b, within=None)
    .compare_all_pairs(within_factor=None)
    .compare_to_control(control, within_factor=None)
    .order_by(factor)
    .explain(explanation)
    .build()
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `groupList` | Yes | Used as builder input for crossed designs and as output for downstream functions. Alias object name: `conditionList`. |
| `group` | Yes | Manual low-level objects can be wrapped in `groupList`. Alias object name: `condition`. |
| `Batch` | No | Builders create metadata before a batch exists. |
| `Experiment` | No | Builders do not read measurements. |
| `pandas.DataFrame` | No | Use [`from_dataframe`](from_dataframe.md) to infer groups from `group_col` or `group_cols`. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `factor` | `str` | required | Factor name, such as `"Diagnosis"`, `"Sex"`, or `"Treatment"`. |
| `label` | `str` | required for `.add()` and `group()` | Full display label shown in plots and exports. |
| `short` | `str` or `None` | `None` | Stored short name used for matching data values, filenames, and comparison lookup. Defaults to `label.strip()`. |
| `name` | `str` | required for `group()` | Low-level equivalent of `short`; the value stored in the group object. |
| `color` | color-like or `None` | `None` | In `GroupBuilder.add()`, hex colors, `Config.COLORS` keys, matplotlib color names, and `None` are resolved to a stored color. In low-level `group()` / `condition()`, the value is stored directly. |
| `style` | `str` | `"fill"` | Secondary visual channel. |
| `a`, `b` | `str` | required for `.compare()` | Short names to compare. Builder methods resolve these to one-based comparison strings such as `"1-2"`. |
| `control` | `str` | required for `.compare_to_control()` | Short name of the control group. |
| `explanation` | `str` | required for `.explain()` | Explanation text; `<>` is replaced with each group label. |
| `group_list1`, `group_list2` | `groupList` | required for `.cross()` | Two group lists to cross into compound groups. `conditionList` is accepted as the legacy object name. |
| `colors` | list-like or `None` | `None` | Optional explicit colors for `GroupBuilder.cross(...)`; values are passed into the crossed groups. |
| `within` | `str` or `None` | `None` | Crossed-design disambiguator for `.compare(a, b, within=...)`. |
| `within_factor` | `str` or `None` | `None` | Run all-pair or control comparisons within each level of another factor. |
| `newColors` | list-like or `None` | `None` | Classic `zipConditionLists` argument for explicit crossed-condition colors; values are passed through directly. |

## Parameter Options

### `style` options

| Option | Behavior |
|---|---|
| `"fill"` (default) | Draw the group with the normal filled style. |
| `"hollow"` | Draw the group with hollow markers/bars where supported. |
| Matplotlib hatch string such as `"///"` | Use the hatch pattern as the secondary visual channel. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `groups` | `groupList` / `conditionList` | Ordered group metadata accepted by `create_batch`, `from_dataframe`, plots, and pipelines through the objects that carry it. |
| `group_obj` | `group` / `condition` | Low-level single group object from `group(...)` or `condition(...)`. |
| `crossed_tuple` | `tuple[multiGroup]` / `tuple[multiCondition]` | Output of `zipGroupLists` / `zipConditionLists`; usually wrap it in `groupList(...)`. |

## Saved Outputs

No files are written.

## Examples

### Minimal two-group design

```python
from PyFLASH import GroupBuilder

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="grey")
    .add("AD", short="AD", color="red")
    .compare("Control", "AD")
    .build()
)

print(groups.comparisons)
```

### Use the result to build a batch

```python
from PyFLASH import GroupBuilder, create_batch

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", "Control", color="grey")
    .add("MCI", "MCI", color="blue")
    .add("AD", "AD", color="red")
    .compare_all_pairs()
    .build()
)

batch = create_batch(
    "SCN_Diagnosis",
    groups,
    batch_path="outputs/scn",
    experiments="data/experiments",
)
```

### Cross two factors

```python
from PyFLASH import GroupBuilder

diagnosis = (
    GroupBuilder("Diagnosis")
    .add("Control", "Control", color="grey")
    .add("AD", "AD", color="red")
    .build()
)

sex = (
    GroupBuilder("Sex")
    .add("Female", "Female", style="hollow")
    .add("Male", "Male")
    .build()
)

groups = (
    GroupBuilder.cross(diagnosis, sex)
    .compare("Control", "AD", within="Female")
    .order_by("Sex")
    .build()
)

print([g.name for g in groups])
print(groups.comparisons)
```

### Classic condition names still work

```python
from PyFLASH import condition, conditionList, zipConditionLists, zipConditions

control = condition("Control", "Control", "#787a7c", "Diagnosis")
ad = condition("AD", "AD", "#9f1c1f", "Diagnosis")
diagnosis = conditionList([control, ad], comparisons=["1-2"])

male, female = zipConditions(
    ["Male", "Female"],
    ["Male", "Female"],
    [None, None],
    "Sex",
)
sex = conditionList([male, female])
crossed = conditionList(list(zipConditionLists(diagnosis, sex)))
```

## Notes

- `GroupBuilder` and `ConditionBuilder` are the same class. `groupList` and
  `conditionList` are the same class.
- Planned comparisons are stored as one-based strings such as `"1-2"` in the
  final order of `condition_list`.
- `.compare()` resolves short names and raises `ValueError` when a name is not
  found. The error may include a close-match suggestion.
- `.compare_all_pairs()` expands to every pair in the current order.
- `.compare_to_control(control)` compares the control to every other group.
- `.compare_sequential()` compares adjacent groups in order.
- `GroupBuilder.add()` resolves `None`, `Config.COLORS` keys, matplotlib color
  names, and hex strings. Low-level `group()` / `condition()` and
  `zipGroups()` / `zipConditions()` store the color values they are given.
- In crossed designs, color comes from the primary factor unless an explicit
  crossed color is supplied. Style can carry the secondary factor visually.
- `conditionList` is iterable, indexable, and has a length, so users can unpack
  or inspect it with ordinary Python.

## See Also

- [Groups object type](../object-types/conditions.md)
- [Group and factor parameters](../parameters/conditions-and-factors.md)
- [Group specs](../data-structures/condition-specs.md)
- [Build groups workflow](../workflows/build-conditions.md)
- [create_batch](create_batch.md)
- [from_dataframe](from_dataframe.md)
