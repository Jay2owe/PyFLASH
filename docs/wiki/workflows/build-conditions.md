# Build Groups

## Goal

Create the group metadata PyFLASH uses for condition order, labels, colors,
styles, factors, and planned statistical comparisons.

Groups are built before `create_batch`, or supplied to
[`from_dataframe`](../functions/from_dataframe.md) when a table needs explicit
metadata.

## Inputs

- Factor names such as `Diagnosis`, `Sex`, `Treatment`, or `Timepoint`.
- Group labels for plot text.
- Group short names that match values in the data.
- Optional colors and styles.
- Optional planned comparisons.

## Minimal Path

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

## Full Workflow

1. Pick the factor column the groups represent. For a simple design, this is
   usually one column such as `Diagnosis`.
2. Add groups in the display order you want in plots and exports.
3. Use `short=` for the stored value PyFLASH should match in data and filenames.
   When omitted, the label is stripped and reused as the short name.
4. Add comparisons by short name:

```python
groups = (
    GroupBuilder("Diagnosis")
    .add("Control", "Control", color="grey")
    .add("MCI", "MCI", color="blue")
    .add("AD", "AD", color="red")
    .compare_all_pairs()
    .build()
)
```

5. Use a control comparison when the design has a clear baseline:

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

6. Cross two factors when every combination should be a group:

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
    .order_by("Sex")
    .build()
)
```

7. Reuse the same group list when creating or wrapping data:

```python
from PyFLASH import create_batch, from_dataframe

batch = create_batch(
    "SCN_Diagnosis",
    groups,
    batch_path=r"C:\path\to\analysis-output",
    experiments=r"C:\path\to\experiment-parent",
)

exp = from_dataframe(
    summary_df,
    group_list=groups,
    group_cols=["Diagnosis", "Sex"],
    subject_col="Subject ID",
)
```

## Outputs

The builder returns a `groupList` object. It is an ordered collection of group
objects with these important attributes:

| Attribute | Meaning |
|---|---|
| `condition_list` | Ordered simple or crossed groups used by plots. |
| `conditions` | Flattened component groups for crossed designs. |
| `factor` | One factor name or a list of factor names. |
| `factorDict` | Factor-to-level mapping used by grouped plots. |
| `comparisons` | One-based comparison strings such as `"1-2"`. |

No files are written.

## Troubleshooting

- Bad comparison names raise `ValueError` and may include a close-match
  suggestion. Use the group short names, not display labels, in `.compare()`.
- Crossed `.compare("Control", "AD")` can be ambiguous. Add `within="Female"`
  or another short name to identify one crossed pair.
- Colors can be PyFLASH palette keys, hex strings, or matplotlib color names.
  `None` auto-assigns a color.
- In crossed designs, color comes from the primary factor by default. Use
  `style="hollow"` or a hatch pattern on the secondary factor when groups share
  a color.
- If imported data does not land in the expected groups, inspect
  `batch.summary[["Condition", "<factor>"]]` and compare the values with the
  group short names.

## Next Steps

- [Create a batch](create-a-batch.md)
- [from_dataframe reference](../functions/from_dataframe.md)
- [GroupBuilder reference](../functions/condition-builder.md)
- [Groups object type](../object-types/conditions.md)
- [Group specs](../data-structures/condition-specs.md)
- [Group and factor parameters](../parameters/conditions-and-factors.md)
