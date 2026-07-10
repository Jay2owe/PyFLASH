# Run Correlation Pipeline

## Goal

Run the full correlation-discovery workflow: pairwise correlations, p/q-value
matrices, gate selection, optional regression plots, a manifest, and an
overview montage.

Use [`correlation`](../functions/correlation.md) when you want a complete run
folder instead of one standalone matrix figure.

## Inputs

- A `Batch`, experiment-like object, `DataFrameExperiment`, or raw DataFrame.
- Numeric summary columns for `data_cols`.
- Optional second-axis columns for `against_data_cols`.
- Optional group or split column such as `Diagnosis`.
- Optional row filter through `filter_by`.

## Minimal Path

```python
from PyFLASH import correlation, load_state

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")

result = correlation(
    batch,
    data_cols=["GFAP Volume", "IBA1 Volume", "DAPI Count"],
    tests=("pearsonr", "spearmanr"),
    require="or",
    gate="p",
    max_regressions=0,
    save=False,
)

print(result["n_selected"])
```

## Full Workflow

1. Confirm the columns are numeric and present:

```python
columns = ["GFAP Volume", "IBA1 Volume", "DAPI Count"]
print(batch.summary[columns].dtypes)
```

2. Run a dry analysis first. Use `max_regressions=0` to focus on matrix
   selection before drawing regression plots.

```python
dry = correlation(
    batch,
    data_cols=columns,
    tests=("pearsonr", "spearmanr", "kendalltau"),
    require="or",
    gate="p",
    min_n=3,
    max_regressions=0,
    save=False,
)

print(dry["selected"][["x", "y", "method", "r", "p"]].head())
```

3. Save a named run when the settings are right:

```python
saved = correlation(
    batch,
    data_cols=columns,
    factor="Diagnosis",
    regression_factor="Diagnosis",
    tests=("pearsonr", "spearmanr"),
    require="or",
    gate="fdr",
    value_matrices="both",
    max_regressions=8,
    run_label="diagnosis_marker_correlations",
    if_exists="version",
    save=True,
)

print(saved["fig_dir"])
print(saved.get("montage"))
```

4. Use rectangular mode when you want one set of metrics against another:

```python
rect = correlation(
    batch,
    data_cols=["GFAP Volume", "IBA1 Volume"],
    against_data_cols=["Age", "Period (h)"],
    tests=("pearsonr",),
    run_label="markers_against_covariates",
)
```

5. Use a filter queue for the same analysis across row subsets. Pipelines write
   one shared run folder with tagged files and one combined manifest.

```python
queued = correlation(
    batch,
    data_cols=columns,
    filter_by=[
        {"Diagnosis": "Control"},
        {"Diagnosis": "AD"},
    ],
    tests=("pearsonr",),
    max_regressions=0,
    run_label="diagnosis_queue",
)

print(queued["n_conditions"])
print(queued["conditions"])
```

6. Reuse a saved manifest without recomputing:

```python
cached = correlation(
    batch,
    data_cols=columns,
    run_label="diagnosis_marker_correlations",
    if_exists="skip",
    save=True,
)

print(cached["reused"])
```

## Outputs

With `save=True`, the run folder is:

```text
<batch.fig_path>/Correlation Pipeline/<run_label>/
```

Common outputs include:

| Output | Meaning |
|---|---|
| `pairwise_correlations.csv` | Long table of every tested pair and method. |
| `selected_pairs.csv` | Pairs passing the configured `gate` and `require` rule. |
| `Matrices/*.csv` | Coefficient, raw p-value, q-value, and gate matrices. |
| `Matrices/*.svg` | Matrix heatmaps. |
| `Regressions/**/*.svg` | Optional regression plots for selected pairs. |
| `Matrix Differences/*` | Optional grouped matrix-difference outputs. |
| `manifest.json` | Stable run summary. |
| `../_runs_index.csv` | One-row-per-run index for correlation runs. |
| `! Overview Montage.png` | Contact-sheet summary when montage capture has panels. |

The Python result dictionary also includes `pairwise` and `selected`
DataFrames for fresh runs. Cached `if_exists="skip"` returns the saved manifest
and may not include those in-memory tables.

## Troubleshooting

- No selected pairs: try `require="or"`, lower `alpha`, use `gate="p"` instead
  of `gate="fdr"`, or check whether columns have enough complete observations.
- Many underpowered pairs: raise data completeness or lower `min_n` only if it
  is scientifically defensible.
- Existing run was overwritten: use `if_exists="version"` while exploring.
- Saved p/q matrix CSVs appear even when heatmaps are disabled. This is
  expected; `value_matrices` controls plotted heatmaps, not all tables.
- Queue filters collide after filename sanitizing: use clearer group names or
  aliases so filter tags differ.

## Next Steps

- [correlation reference](../functions/correlation.md)
- [Correlation statistics](../statistics/correlation.md)
- [Multiple testing](../statistics/multiple-testing.md)
- [Pipeline run folders](../outputs/pipeline-run-folders.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Filter By](../parameters/specificity.md)
- [plot_regressions reference](../functions/plot_regressions.md)
