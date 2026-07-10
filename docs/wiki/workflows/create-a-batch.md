# Create A Batch

## Goal

Import one or more FLASH/ImageJ experiment folders into a processed `Batch`
that can be plotted, pipelined, exported, and saved.

Use this workflow when your data is still in experiment-folder form. If you
already have a clean table, use [`from_dataframe`](../functions/from_dataframe.md)
instead.

## Inputs

- A parent folder containing experiment subfolders, or a dictionary that maps
  experiment names to folder paths.
- A built `groupList` from [`GroupBuilder`](../functions/condition-builder.md).
- A `batch_path` output folder.
- Optional `pickle_path` for cache files.
- Optional image-import choice. Use `import_images=False` for faster
  summary-only analysis.

## Minimal Path

```python
from PyFLASH import GroupBuilder, create_batch

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="grey")
    .add("AD", short="AD", color="red")
    .compare("Control", "AD")
    .build()
)

batch = create_batch(
    "SCN_Diagnosis",
    groups,
    batch_path=r"C:\path\to\analysis-output",
    experiments=r"C:\path\to\experiment-parent",
    pickle_path=r"C:\path\to\pickles",
)
```

## Full Workflow

1. Check the experiment folder layout. PyFLASH accepts current FLASH folders and
   supported legacy layouts when they contain importable tables.
2. Build groups before import. The group short names should match the values
   PyFLASH will see in the data, such as `Control`, `MCI`, or `AD`.
3. Choose explicit output folders. Keep `batch_path` for analysis outputs and
   `pickle_path` for reusable `.pkl` cache files.
4. Run `create_batch`. If a matching pickle already exists and `rerun=False`,
   PyFLASH returns the cached object instead of reprocessing.
5. Inspect the loaded object before plotting:

```python
print(batch.name)
print(batch.summary.shape)
print(batch.fig_path)
print(batch.export_path)
print([group.name for group in batch.condition_list])
```

6. Force a rebuild when source data or group definitions changed:

```python
batch = create_batch(
    "SCN_Diagnosis",
    groups,
    batch_path=r"C:\path\to\analysis-output",
    experiments=r"C:\path\to\experiment-parent",
    pickle_path=r"C:\path\to\pickles",
    rerun=True,
)
```

7. Save time on table-only work by skipping image discovery:

```python
batch = create_batch(
    "SCN_Diagnosis",
    groups,
    batch_path=r"C:\path\to\analysis-output",
    experiments=r"C:\path\to\experiment-parent",
    import_images=False,
)
```

## Outputs

`create_batch` returns a `Batch` in Python. The object contains `summary`,
`summaries`, `condition_list`, `data`, `fig_path`, `data_path`, and
`export_path`.

When `pickle_path` is provided, PyFLASH writes or reuses:

```text
<pickle_path>/<name>.pkl
```

The returned batch also records standard output roots below `batch_path`, such
as `Results/Python Figures`, `Results/Data and Stats`, `Results/Separate CSVs`,
and `Exports`. Those folders may be created lazily when plots or exports run.

## Troubleshooting

- `No experiment folders found`: pass the parent folder that contains
  experiment subfolders, or pass a dictionary of explicit experiment paths.
- Cached results look stale: run with `rerun=True`.
- Image workflows have no images: rebuild with `import_images=True`, or use the
  UI/image workflows to inspect image-table availability.
- Group labels do not match: check the values in `batch.summary["Condition"]`
  and the factor columns created by the group list.
- A moved cache loads but output paths are wrong: use
  [load and rebase a pickle](load-and-rebase-a-pickle.md).

## Next Steps

- [Build groups](build-conditions.md)
- [First plot](../getting-started/first-plot.md)
- [Plot from Python](plot-from-python.md)
- [Export Excel workbooks](export-excel-workbooks.md)
- [create_batch reference](../functions/create_batch.md)
- [Batch object type](../object-types/batch.md)
- [Where results go](../getting-started/where-results-go.md)
