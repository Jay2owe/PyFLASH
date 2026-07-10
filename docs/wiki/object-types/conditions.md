# Groups

## Summary

Group objects describe experimental groups. They store labels, short names,
colors, optional styles, factors, and planned comparisons. They do not store
measurements.

PyFLASH supports two naming styles:

| Preferred User Name | Classic Name | Meaning |
|---|---|---|
| `group` | `condition` | One group level, such as `Control` or `AD`. |
| `multiGroup` | `multiCondition` | A crossed group such as `ADFemale`. |
| `groupList` | `conditionList` | Ordered group collection with comparisons and factor metadata. |
| `GroupBuilder` | `ConditionBuilder` | Fluent builder for group lists. |
| `zipGroups` | `zipConditions` | Create groups from parallel lists. |
| `zipGroupLists` | `zipConditionLists` | Cross two group lists. |

The aliases point to the same underlying classes. Existing scripts can keep
using the classic names.

## How To Create It

Preferred builder:

```python
from PyFLASH import GroupBuilder

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="grey")
    .add("AD", short="AD", color="red")
    .compare("Control", "AD")
    .build()
)
```

Manual objects:

```python
from PyFLASH import group, groupList

control = group("Control", "Control", "grey", "Diagnosis")
ad = group("AD", "AD", "red", "Diagnosis")
groups = groupList([control, ad], comparisons=["1-2"])
```

Crossed design:

```python
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
    .build()
)
```

## Important Attributes

### `group` / `condition`

| Attribute | Meaning |
|---|---|
| `label` | Full display label. |
| `name` | Short name used in group matching, filenames, and comparisons. |
| `color` | Plot color. Builder colors can be hex strings, keys in `Config.COLORS`, matplotlib color names, or `None` for auto-assignment. |
| `style` | Second visual channel for bars and some keys. `"fill"` is solid, `"hollow"` is outline-only, and other values are matplotlib hatch patterns such as `"///"`. |
| `factor` | Factor name, such as `"Diagnosis"`. |
| `factor_explanation` | Optional explanation text with the label substituted into the template. |

### `multiGroup` / `multiCondition`

| Attribute | Meaning |
|---|---|
| `conditionsList` | Component single groups. Legacy attribute name. |
| `name` | Combined short name, such as `ADFemale`, unless supplied explicitly. |
| `label` | Combined display label, unless supplied explicitly. |
| `color` | Color from the primary component unless supplied explicitly. |
| `style` | First non-default component style, otherwise `"fill"`. This lets a secondary factor carry bar style in crossed designs. |
| `factor` | List of factor names. |
| `factor_explanation` | List of component explanations. |

### `groupList` / `conditionList`

| Attribute | Meaning |
|---|---|
| `condition_list` | Ordered list of group or crossed-group objects. Legacy attribute name. |
| `comparisons` | Planned comparisons as one-based index strings such as `"1-2"`, or `None`. |
| `conditions` | Flattened list of single groups. Crossed groups contribute their component groups. Legacy attribute name. |
| `factor` | List of factor names. |
| `factorDict` | Mapping from each factor to its single-condition levels. |

## Common Methods

### `GroupBuilder` / `ConditionBuilder`

| Method | Use |
|---|---|
| `.add(label, short=None, color=None, style="fill")` | Add one group level. |
| `.compare(a, b)` | Add one planned comparison by short name. |
| `.compare_all_pairs()` | Compare every pair in the built list. |
| `.compare_to_control(control)` | Compare every other group to one control group. |
| `.compare_sequential()` | Compare adjacent groups in order. |
| `.explain(template)` | Add explanation text; `<>` is replaced by each label. |
| `.build()` | Return a `groupList` / `conditionList`. |
| `.cross(list1, list2, colors=None)` | Create a crossed-design builder. |

### Crossed Builder

| Method | Use |
|---|---|
| `.compare(a, b, within=None)` | Compare two component levels, optionally restricted to a third level. |
| `.compare_all_pairs(within_factor=None)` | Compare all pairs, optionally within each level of another factor. |
| `.compare_to_control(control, within_factor=None)` | Compare to a control, optionally within each level of another factor. |
| `.order_by(factor)` | Reorder crossed groups so levels of that factor are grouped together. |
| `.explain(template)` | Add explanation text to the crossed list. |
| `.build()` | Return a crossed `groupList` / `conditionList`. |

`groupList` is iterable, indexable, and has a length, so this works:

```python
control, ad = groups
print(groups[0].name)
print(len(groups))
```

## Accepted By

Group lists are accepted by:

- [`create_batch`](../functions/create_batch.md) as the `conditions` argument
- [`from_dataframe`](../functions/from_dataframe.md) as `conditions`, `groups`, or `group_list`
- `Batch(...)` direct construction
- UI project condition builders
- Plotting and statistics code through the objects that carry `condition_list`

## Returned By

- `GroupBuilder(...).build()`
- `GroupBuilder.cross(...).build()`
- `groupList(...)` / `conditionList(...)`
- `zipGroupLists(...)` / `zipConditionLists(...)`, as tuples that are usually wrapped in a list object
- Legacy equivalents: `ConditionBuilder(...).build()` and
  `ConditionBuilder.cross(...).build()`

## Examples

All-pairs comparisons:

```python
groups = (
    GroupBuilder("Diagnosis")
    .add("Control", "Control", color="grey")
    .add("MCI", "MCI", color="blue")
    .add("AD", "AD", color="red")
    .compare_all_pairs()
    .build()
)

print(groups.comparisons)
```

Control comparisons:

```python
groups = (
    GroupBuilder("Treatment")
    .add("Vehicle", "Vehicle", color="grey")
    .add("Low dose", "Low", color="blue")
    .add("High dose", "High", color="red")
    .compare_to_control("Vehicle")
    .build()
)
```

Crossed comparisons within a factor:

```python
groups = (
    GroupBuilder.cross(diagnosis, sex)
    .compare_all_pairs(within_factor="Sex")
    .order_by("Sex")
    .build()
)
```

Use group aliases with `from_dataframe`:

```python
from PyFLASH import from_dataframe

experiment = from_dataframe(
    df,
    groups=groups,
    subject_col="Subject",
)
```

## Notes

- Planned comparisons are stored as strings such as `"1-2"` using the current
  order of `condition_list`.
- Bad comparison names raise a `ValueError` and may include a close-match
  suggestion.
- Color names are resolved through `Config.COLORS` before matplotlib color
  names, so a PyFLASH palette key such as `"blue"` wins over CSS `"blue"`.
- Blank or `None` colors are auto-assigned from a colorblind-safe palette.
- In crossed designs, color follows the primary factor by default. Style can
  distinguish the secondary factor.

## See Also

- [Build groups workflow](../workflows/build-conditions.md)
- [`condition-builder` function page](../functions/condition-builder.md)
- [Group and factor parameters](../parameters/conditions-and-factors.md)
- [Group specs](../data-structures/condition-specs.md)
- [`plot_condition_key`](../functions/plot_condition_key.md)
