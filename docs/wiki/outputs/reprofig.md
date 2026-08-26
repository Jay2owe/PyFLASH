# ReproFig: self-describing and publication-safe figures

Think of a master SVG as a labelled specimen box: the visible figure is on top,
and the exact values, results, and origin record travel inside it.

## What a master records

- stable figure identifier and creation time
- PyFLASH version, Git revision, Python version, and creating function
- exact run request and reproduction script when invoked through the PyFLASH runner
- exact post-filter data tables used for graphical marks and statistics
- test names, exact raw and adjusted p-values, effects, confidence intervals,
  group sample sizes, and the definition of the independent sample unit
- project-relative source files, optional durable links, and SHA-256 fingerprints

The master remains usable if it is renamed or separated from `figures.json`.
Use `pyflash-figure extract Figure.svg --output Figure-bundle` to regenerate
source-data CSV, statistics CSV, provenance JSON, caption Markdown, and the
reproduction script when present.

## Publication workflow

```text
master SVG
    |
    +-- inspect and validate
    +-- approve public columns and source links
    `-- publish --> public SVG + CSV files + manifest + validation report
```

Use `public` when approved row-level values may remain inside the SVG. Use
`minimal_public` when row-level values should exist only in the accompanying
public CSV; statistics and data fingerprints stay embedded. Conversion is
one-way and never overwrites the master.

```python
from PyFLASH import publish_figures

result = publish_figures(
    "Results",
    output_dir="Submission",
    figure_profile="public",
    safe_columns={
        "Figure 1.svg": ["group", "metric", "value"],
        "Figure 2.svg": ["group", "x", "y"],
    },
    public_sources={
        "source_csv": "https://repository.example/dataset.csv",
    },
)
assert result.valid
```

Upload only the generated submission folder. The exporter fails before moving
any output into place if an unapproved column, private path, credential-shaped
string, linked image, script, filename collision, or validation error remains.

The same conversion is available without Python code:

```text
pyflash-figure publish Figure.svg --output-dir Submission \
  --profile minimal-public --safe-columns group,value \
  --public-source source_csv=https://repository.example/dataset.csv
```

## Finding and checking old figures

`pyflash-figure scan Results --csv figures.csv` rebuilds a disposable catalogue
from the SVG files. New records report `complete`, `incomplete`, or
`not_applicable` data/statistics status. Older Dublin Core-only SVG files remain
readable as producer provenance, but PyFLASH never invents missing observations
or tests; rerun the recorded request to create a complete master when possible.

Ordinary Inkscape SVG saves are expected to retain the namespaced metadata.
Plain-SVG, optimizer, bitmap, and Portable Document Format (PDF) exports may
remove it, so retain the master SVG separately.
