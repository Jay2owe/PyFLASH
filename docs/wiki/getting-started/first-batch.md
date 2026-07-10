# First Batch

## Goal

Create a processed `Batch` from FLASH/ImageJ experiment folders.

## Before You Start

- Install PyFLASH first.
- Put each experiment in a folder that PyFLASH can recognise as a FLASH/ImageJ
  export.
- Know the groups you want to compare, such as `Control` and `AD`.

## Steps

```python
from PyFLASH import GroupBuilder, create_batch

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="blue")
    .add("AD", short="AD", color="red")
    .compare("Control", "AD")
    .build()
)

batch = create_batch(
    "Example",
    groups,
    batch_path=r"C:\path\to\batch-output",
    experiments=r"C:\path\to\experiment-parent",
    pickle_path=r"C:\path\to\pickles",
)

print(batch.summary.head())
print(batch.fig_path)
```

`experiments` can also be a dictionary when your experiments live in separate
folders:

```python
batch = create_batch(
    "Example",
    groups,
    batch_path=r"C:\path\to\batch-output",
    experiments={
        "Cohort_1": r"C:\path\to\Cohort_1",
        "Cohort_2": r"C:\path\to\Cohort_2",
    },
)
```

## Check It Worked

- `batch` is a `Batch` object.
- `batch.summary` is a table with one row per subject or animal.
- `batch.fig_path` points to the folder used by plotting functions.
- If `pickle_path` was set, PyFLASH saves or reuses
  `C:\path\to\pickles\Example.pkl`.

## Next

- [create_batch](../functions/create_batch.md)
- [First plot](first-plot.md)
- [Where results go](where-results-go.md)
- [Object model](../object-model.md)
