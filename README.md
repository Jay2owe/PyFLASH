# PyFLASH

[![Documentation Status](https://readthedocs.org/projects/pyflash/badge/?version=latest)](https://pyflash.readthedocs.io/en/latest/)
[![PyPI](https://img.shields.io/pypi/v/PyFLASH-analysis)](https://pypi.org/project/PyFLASH-analysis/)

A Python package for processing and analyzing immunofluorescence (IF) confocal microscopy data exported from the FLASH ImageJ Plugin.

📖 **[Documentation](https://pyflash.readthedocs.io/)**

## What it does

Takes CSV exports from ImageJ's 3D Object Counter and other plugins, processes them into structured experiment/batch objects, performs statistical analysis, generates publication-quality plots, and exports formatted Excel summaries.

## Installation

```bash
pip install PyFLASH-analysis
```

## License

PyFLASH is distributed under the BSD 3-Clause License. See `LICENSE`.

**Requires:** Python ≥ 3.9

**Dependencies:** pandas, numpy, matplotlib, seaborn, scipy, statsmodels, scikit-posthocs, openpyxl, read-roi, Pillow

The PyPI distribution is `PyFLASH-analysis`; the Python import package is `PyFLASH`.
For local development, install from the repository with `pip install -e .`.
For local notebook testing, start Jupyter from this repository and run `pip install -e .`; the editable `PyFLASH-analysis` install points at the local `PyFLASH/` source files while imports stay as `import PyFLASH`.

## Quick start

```python
from PyFLASH import *
from PyFLASH.plotting import plot_mean_bars, plot_matrices, plot_location
from PyFLASH.utils import get_columns

set_pyflash_style()

# Define experimental conditions (fluent builder)
conditions = (
    ConditionBuilder("Genotype")
    .add("WT", short="WT", color="blue")        # color names or hex
    .add("KO", short="KO", color="red")
    .compare("WT", "KO")                         # named, not '1-2'
    .explain("Wild-type vs knockout mice")
    .build()
)

# Or the classic API (still works):
# WT = condition('WT', 'WT', Config.COLORS['blue'], 'Genotype', 'Wild-type mice')
# KO = condition('KO', 'KO', Config.COLORS['red'], 'Genotype', 'Knockout mice')
# conditions = conditionList([WT, KO], comparisons=['1-2'])

# Create or load a batch
batch = create_batch(
    "My Experiment",
    conditions,
    batch_path="path/to/output",
    experiments={"Cohort1": "path/to/data1", "Cohort2": "path/to/data2"},
    pickle_path="path/to/cache",
)

# Analyse
cols = get_columns(batch.summary, column_strings=['Count', 'Volume'], exclude='NonColoc')
plot_mean_bars(batch, cols, specificity=('Time', 'WeekEight'))
plot_matrices(batch, cols)

# Export
batch.export_all_excel()
save_state(batch, "my_batch.pkl")
```

## Self-describing ReproFig figures

Every PyFLASH figure now carries a compressed
figure record: the exact plotted comma-separated values (CSV) table, exact
statistics and sample-size definitions, PyFLASH and Python versions, creating
function, run request, reproduction script, and source-file fingerprints.
The default `master` is self-contained; companion CSV files are optional.

Choose a distribution profile at the shared save point:

```python
from PyFLASH.utils import save_fig

save_fig(
    fig,
    output_dir,
    "Figure 1",
    figure_profile="master",
    figure_formats=("svg", "pdf", "png", "jpg", "tif", "webp", "avif", "heif"),
    dpi=300,
)
save_fig(
    fig,
    output_dir,
    "Figure 1 public",
    figure_profile="public",
    figure_safe_columns=["group", "metric", "value"],
    write_companion_csv=True,
)
```

All direct formats above share one figure identity. For existing PowerPoint,
Word, Excel, HTML, netCDF-4, HDF5, FITS and ZIP/RO-Crate files, use
`PyFLASH.publication.embed_file`.

For publication, derive new files from masters without changing them:

```python
from PyFLASH import publish_artifacts

publish_artifacts(
    ["Figure 1.svg"],
    output_dir="Publication Figures",
    figure_profile="minimal_public",
    safe_columns=["group", "metric", "value"],
)
```

The resulting flat folder contains privacy-validated figure files, public source
data CSV files, exact statistics CSV files, a hashed manifest, and a validation
report. Command-line equivalents start with `pyflash-figure`, for example
`pyflash-figure inspect Figure.svg` and `pyflash-figure publish Figure.svg
--profile public --safe-columns group,value --output-dir Publication`.

## Plot styling

Use `set_pyflash_style()` as the single front door for plot styling. It applies
Matplotlib-level style such as fonts, tick widths, spines, titles, labels, and
legends, plus PyFLASH semantics such as condition hatch cycles, scatter marker
defaults, significance stars, matrix label orientation, colormaps, and overview
status colours:

```python
from PyFLASH import set_pyflash_style, pyflash_style_context

set_pyflash_style(
    point_size=9,
    title_size=20,
    labelsize=22,
    despine=True,
    legend_frame=False,
    significance_thresholds={0.0001: "****", 0.001: "***", 0.01: "**", 0.05: "*"},
    bar_point_fill="group",
    bar_point_edge="none",
    scatter_3d_edge="group",
    matrix_x_tick_rotation=60,
)

with pyflash_style_context(matrix_cmap="viridis"):
    plot_matrices(batch, cols)
```

### Crossed (factorial) designs

```python
genotype = (
    ConditionBuilder("Genotype")
    .add("WT", short="WT", color="blue")
    .add("KO", short="KO", color="red")
    .compare("WT", "KO")
    .build()
)

treatment = (
    ConditionBuilder("Drug")
    .add("Vehicle", short="Veh")
    .add("Drug A", short="DrugA")
    .compare("Veh", "DrugA")
    .build()
)

crossed = (
    ConditionBuilder.cross(genotype, treatment)
    .compare("Veh", "DrugA", within="WT")    # drug effect in WT
    .compare("Veh", "DrugA", within="KO")    # drug effect in KO
    .compare("WT", "KO", within="Veh")       # genotype effect, no drug
    .build()
)
```

## Package structure

| Module | Purpose |
|---|---|
| `config.py` | Global configuration (thresholds, pixel size, colors) |
| `conditions.py` | Experimental conditions, `ConditionBuilder` fluent DSL |
| `markers.py` | Data marker classes (Antibody, cellMarker, objectMarker) |
| `experiment.py` | Single-experiment CSV import, ROI processing, summary building |
| `batch.py` | Multi-experiment batch processing and merging |
| `factory.py` | High-level `create_batch()` with pickle caching |
| `iteration.py` | Composable iteration framework for analysis actions |
| `plotting.py` | Publication-quality plots (bar charts, heatmaps, spatial plots, image panels) |
| `stats.py` | Statistical testing (t-test, ANOVA, Kruskal-Wallis, post-hoc comparisons) |
| `modelling.py` | Iterative best-fit model selection with LOO cross-validation |
| `export.py` | Formatted Excel export with human-readable column names |
| `serialization.py` | Pickle save/load with cross-machine path resolution |
| `image_io.py` | Multi-backend image loading (tifffile, cv2, imageio, PIL) |
| `_logging.py` | Unified output system with verbosity control (`set_verbosity`, `silent()`, `verbose()`) |
| `utils.py` | String, DataFrame, geometry, and plotting helpers |

## Controlling output

```python
import PyFLASH

# Set verbosity: 0=error, 1=warning, 2=info (default), 3=hint, 4=debug
PyFLASH.set_verbosity('debug')

# Silence all output for a block
with PyFLASH.silent():
    batch.export_all_excel()

# Maximize detail for a block
with PyFLASH.verbose():
    batch.processData()
```

## Citation

If you use PyFLASH in academic work, cite the software release you used:

```text
Jamie Malcolm. PyFLASH: ImageJ confocal microscopy data processing and analysis pipeline.
PyPI: https://pypi.org/project/PyFLASH-analysis/
Source: https://github.com/Jay2owe/PyFLASH
```

## Acknowledgements

Developed by Jamie Malcolm in the [Brancaccio Lab](https://www.ukdri.ac.uk/labs/brancaccio-lab)
at the [UK Dementia Research Institute](https://ukdri.ac.uk/centres/imperial),
Imperial College London.

This work was supported by the UK Dementia Research Institute,
which receives its core funding from the UK Medical Research Council,
the Alzheimer's Society, and Alzheimer's Research UK.

## Data flow

```
Raw ImageJ exports (CSVs, ROI zips, images)
    → Experiment.processData()     — import, clean, compute colocalisation, build summary
    → Batch.processData()          — merge experiments, handle cross-experiment animals
    → Analysis & visualisation     — plot_mean_bars(), plot_matrices(), stats, modelling
    → Export                       — batch.export_all_excel(), save_state()
```

## Expected data layout

```
Data Analysis/
├── Objects/           # CSV files for objectMarker data
├── Cells/             # CSV files for cellMarker data
├── ROI Intensities/   # CSV files for ROI-level Antibody data
├── Attributes/        # CSV files for generic Attribute data
├── ROIs/              # ImageJ ROI zip files
└── Images/            # Microscopy images organized by animal/marker
```
