# IF_analysis — Project Context

## Overview

**IF_analysis** is a Python package for processing and analyzing immunofluorescence (IF) confocal microscopy data from ImageJ. It was built for the Brancaccio Lab at the UK Dementia Research Institute. The pipeline takes CSV exports from ImageJ's 3D Object Counter and other plugins, processes them into structured experiment/batch objects, performs statistical analysis, generates publication-quality plots, and exports formatted Excel summaries.

**Package name:** `IF-analysis` (v0.1.0)
**Python:** >=3.9
**Build:** setuptools

### Key Dependencies
pandas, numpy, matplotlib, seaborn, scipy, statsmodels, scikit-posthocs, openpyxl, read-roi, Pillow

### Optional Dependencies
pywin32 (Windows), tifffile, cv2, imageio, roifile, patsy, tqdm, altair (interactive HTML), pyyaml/tomli (spec DSL)

---

## Architecture

The package is a single flat Python package (`IF_analysis/`) with these modules:

```
IF_analysis/
├── __init__.py          # Public API exports
├── config.py            # Global configuration singleton (Config class)
├── conditions.py        # Experimental condition classes
├── markers.py           # Data marker classes (Attribute, Antibody, cellMarker, objectMarker)
├── experiment.py        # Experiment class — CSV import, ROI processing, summary building
├── batch.py             # Batch class — combines multiple Experiments
├── factory.py           # create_batch() — high-level batch creation with caching
├── iteration.py         # Context + run() — iteration framework for analysis actions
├── plotting.py          # Plotting action functions and one-liner wrappers (~480KB, largest file)
├── stats.py             # Statistical testing (t-test, ANOVA, KW, Tukey, MWU, normality)
├── spec.py              # Declarative plot specification DSL (YAML/TOML/JSON)
├── modelling.py         # Model selection (iterative best-fit with LOO cross-validation)
├── export.py            # Excel export with name mapping and formatting
├── serialization.py     # Pickle-based save/load with path normalization
├── image_io.py          # Image loading with multiple backend support
├── _logging.py          # Unified output system (IFLogger, Verbosity, silent/verbose)
└── utils.py             # Shared utilities (string, DataFrame, geometry, plotting helpers)
```

---

## Core Classes

### `Config` (config.py)
Global configuration singleton with class-level attributes:
- `THRESHOLD = 30` — colocalisation threshold percentage
- `PIXEL_SIZE = 3.51998900003` — microns per pixel
- `FALLBACK_USERS` — list of usernames for cross-machine path resolution
- `COLORS` — hex color palette dictionary
- `SAVE_MODE = True` — whether to save figures
- `SKIP_EXISTING = False` — skip saving when output file already exists (opt-in)
- `EXPORT_HTML = False` — export interactive Altair HTML alongside SVG plots (opt-in)
- `STATS_CACHE = False` — cache stats results within a session (opt-in)
- `ALIASES = {}` — user-defined abbreviations for specificity/factor values
- Display labels: `AB = 'Aβ'`, `CK = 'CK1δ'`, unit labels

Also contains `check_directory()` for resolving paths across different user directories (important for Dropbox shared paths).

### `condition` / `multiCondition` / `conditionList` (conditions.py)
- `condition(label, name, color, factor, explanation)` — single experimental condition (e.g., genotype, treatment)
- `multiCondition(conditionsList)` — compound condition from crossing two+ conditions
- `conditionList(condition_list, comparisons, explanation)` — ordered list with comparison pairs and factor info
- `zipConditions()` / `zipConditionLists()` — helpers for creating condition tuples (still supported)

### `ConditionBuilder` (conditions.py) — fluent builder DSL
Alternative to the raw constructors above. Produces the same objects with a friendlier API:

```python
conditions = (
    ConditionBuilder("Genotype")
    .add("Syn-mCherry", short="Syn", color="red")   # color name or hex
    .add("hAPP-mCherry", short="hAPP")               # color auto-assigned
    .compare_all_pairs()                              # or .compare("Syn", "hAPP")
    .explain("WT mice injected with <> at 2 months.")
    .build()                                          # → conditionList
)
```

Key features:
- **Color resolution:** accepts `Config.COLORS` keys (`"red"`), CSS names (`"steelblue"`), hex (`"#ff0000"`), or `None` (auto-assigns from Okabe-Ito colorblind-safe palette)
- **Named comparisons:** `.compare("Syn", "hAPP")` instead of `'1-2'`. Also `.compare_all_pairs()`, `.compare_to_control("Syn")`, `.compare_sequential()`
- **Fuzzy error messages:** typo `"hApp"` → `"Did you mean 'hAPP'?"`
- **Crossed/factorial designs:** `ConditionBuilder.cross(cl1, cl2, colors=)` returns a `_CrossedConditionBuilder` with `.compare("Veh", "Drug", within="hAPP")`, `.compare_all_pairs(within_factor="Time")`, `.order_by("Time")`
- **Backward compatible:** old `condition()`, `zipConditions()`, `conditionList()` are unchanged

### Marker Classes (markers.py)
Hierarchy: `Attribute` → `Antibody` → `cellMarker` / `objectMarker`

- **`Attribute`** — generic data attribute wrapping a DataFrame. Cleans column names, maps animal labels, derives `Condition` from `AnimalName`.
- **`Antibody`** — adds spatial data processing (coordinate adjustment), ROI analysis, ventricle distance calculation, and inter-marker distance computation.
- **`cellMarker`** — intracellular marker (no colocalisation data)
- **`objectMarker`** — intra/extracellular marker WITH colocalisation data. Adds coloc count columns based on threshold.

Key methods on `Antibody`:
- `clean_df()` — cleans columns, adjusts coordinates, adds coloc data
- `find_distance_to_ventricle(rois)` — calculates distance from each object to ventricular boundary
- `find_closest_distances_between_markers(other_marker)` — euclidean nearest-neighbor distances between two marker types
- `analyse_roi(roi, points)` — polyline distance analysis with optional visualization

`stainColors` — default stain-to-color mapping (defaultdict), e.g., `'GFAP': 'red'`, `'Iba1': 'cyan'`

### `Experiment` (experiment.py)
Core data container. Initialized with `(name, filePath, threshold)`.

**Data structure expectations:**
- `filePath` points to a "Data Analysis" directory containing subdirectories:
  - `Objects/` — CSV files for objectMarker data
  - `Cells/` — CSV files for cellMarker data
  - `ROI Intensities/` — CSV files for ROI-level Antibody data
  - `Attributes/` — CSV files for generic Attribute data
  - `ROIs/` — ImageJ ROI zip files
  - `Images/` — microscopy image files organized by animal/marker

**Key methods:**
- `processData(import_images=True)` — main pipeline: imports CSVs, creates markers, builds summary, imports images
- `importImages()` — scans image directories, builds image table with metadata
- `createSummary()` — aggregates per-object data to per-animal summary (means, totals, counts per volume)
- `set_condition_list(cond_list)` — assigns conditions and factor columns
- `getSCNDict()` — returns nested dict: `{condition: {animal: [scn_list]}}`
- `assign_scn_number()` — assigns SCN numbering
- `save_csvs()` — saves processed data to CSV files

**Summary building:** The summary DataFrame is per-animal with columns like:
- `AnimalName`, `Condition`, factor columns
- `<marker>_Count`, `<marker>_IntDenTotal`, `<marker>_VolumeMean`, `<marker>_SurfaceMean`
- `<marker>_Coloc_<other>_Mean`, `<marker>_ColocCount<other>`, `<marker>_ColocCount<other>%`
- `<marker>_DistToClosest_<other>Mean`, `<marker>_Contains_<other>Mean`
- `<marker>_burdenScore`, `<marker>_fragmentationScore`
- ROI intensity columns: `<marker>_ROI_IntDenMean`, `<marker>_ROI_%AreaMean`

**ROI handling:** Uses `read-roi` and optionally `roifile` to parse ImageJ ROI zip files. ROIs define ventricle boundaries and SCN regions (LHSCN, RHSCN naming convention).

**Combo colocalisation:** `_build_coloc_combo_summaries()` creates combination indicators from multiple colocalisation channels (e.g., "CK1d+_wIba1" for objects positive for both).

**Marker scores:**
- `burdenScore` — composite from log-normalized, z-scored IntDenTotal, VolumeTotal, SurfaceTotal, %AreaMean
- `fragmentationScore` — from log-normalized, z-scored Count/VolumeTotal ratio

### `Batch` (batch.py)
Extends `Experiment`. Groups multiple experiments under shared conditions.

**Key methods:**
- `processData()` — processes all child experiments, merges summaries, imports images
- `_create_batch_summary()` — outer-joins experiment summaries on AnimalName, handles sentinel values (`NOT_INCLUDED_IN_EXPERIMENT`) for animals absent from specific experiments, labels duplicate metric columns with `.expN` suffixes
- `export_IF_summary_excel(save_path)` — formatted Excel with one sheet per metric
- `export_behavior_summary_excel(save_path)` — behavioral data export
- `export_extended_data_excel(save_path)` — per-object extended data export
- `export_all_excel()` — runs all three exports

**Serialization:** Custom `__getstate__`/`__setstate__` — excludes image arrays from pickle, rebuilds `imagesDict` on load.

### `create_batch()` (factory.py)
High-level batch creation with pickle caching and progress tracking.

```python
batch = create_batch(
    name="My Batch",
    conditions=my_condition_list,
    batch_path="/path/to/output",
    experiments={"Exp1": "/path1", "Exp2": "/path2"},  # or auto-discover
    threshold=30,
    pickle_path="/cache/dir",
    rerun=False,
    import_images=True,
)
```

Features:
- Auto-discovers experiments from directory structure if `experiments=None`
- Loads from pickle cache if available (unless `rerun=True`)
- Carries over representative image selections and saved image edits from previous pickle on rerun
- Shows progress with `ProgressTracker`

---

## Iteration Framework (iteration.py)

Two-layer design for composable analysis:

### `Context` (dataclass)
Carries current position in the data hierarchy:
- `experiment`, `condition`, `condition_obj`, `animal`, `scn`, `column`, `factor`
- Properties: `summary`, `condition_df`, `factor_df`, `animal_df`, `color`, `label`
- Methods: `col_values(by)`, `col_animal_means(by)`, `marker_df(marker_name)`
- Iterators: `iter_conditions()`, `iter_animals()`, `iter_scns()`, `iter_columns(columns)`, `iter_factors(factor_name)`

### `run()` — single entry point
```python
run(experiment, over=['columns', 'conditions'], action=my_action,
    columns=cols, specificity=('Time', 'WeekEight'),
    setup=make_fig, teardown=save_fig)
```
- `over` — iteration levels: `'columns'`, `'conditions'`, `'animals'`, `'scns'`, `'factors'`
- `action(ctx, state, **kwargs)` — called at innermost level, returns dict of results
- `setup/teardown` — called at outermost level boundaries
- `specificity` — tuple `(column_name, value1, ...)` to filter summary before iteration

---

## Plotting (plotting.py)

The largest module (~480KB). Contains action functions and one-liner wrappers.

### Display Name System
`get_display_name(name, minimal, compact_per)` — converts raw column names to human-readable labels using the export name maps. Handles units, abbreviations, and formatting.

### Key Plot Functions (one-liners that wrap `run()`):
- `plot_mean_bars()` — bar charts with swarm points, SEM error bars, and statistical annotations. Supports `dry_run=True` to compute stats without rendering.
- `plot_matrices()` — correlation heatmaps
- `plot_rect_matrices()` — rectangular correlation matrices (y vs x columns)
- `plot_histograms()` — histogram distributions by condition
- `plot_ridgeline()` — ridgeline density plots
- `plot_ecdf()` — empirical CDF plots
- `plot_regressions()` — regression scatter plots with correlation stats
- `plot_volcano()` — volcano plots of fold-change vs significance
- `plot_pie_charts()` — pie/stacked bar charts for categorical distributions
- `plot_locations()` — spatial location plots of marker objects on microscopy images
- `plot_images()` — multi-panel microscopy image grids
- `plot_representative_images()` — representative image selection and display
- `plot_coloc_upset()` — UpSet plots of marker colocalisation
- `plot_coloc_sankey()` — Sankey diagrams of colocalisation flow

### Cheat Sheet
`cheat_sheet()` — lists all plot functions. `cheat_sheet('mean_bars')` — shows all parameters with descriptions and defaults.

### Interactive HTML Export
When `Config.EXPORT_HTML = True` and altair is installed, `plot_mean_bars`, `plot_histograms`, `plot_matrices`, and `plot_volcano` also save an interactive HTML file alongside the SVG plots. Always opt-in; skips silently if altair is not available.

### Image Panel System
- Supports multi-marker merge panels (overlaying channels)
- ROI overlay drawing from ImageJ ROI files
- Representative image selection with persistent metadata
- Image loading with multiple backends (tifffile, cv2, imageio, PIL)
- Downsampling and preview for performance

---

## Plot Specification DSL (spec.py)

Run entire plot batches from a YAML/TOML/JSON file instead of writing Python.

### Usage
```python
from IF_analysis import run_spec

# Single batch
run_spec(batch1, 'plots.yaml')

# Multiple batches — reference by name in the YAML
run_spec({
    'batch1':  batch1,
    'CK1I':    batch_CK1I,
    'NLGFKI':  batch_NLGFKI,
}, 'plots.yaml')
```

### YAML format
```yaml
plots:
  - type: mean_bars
    batch: batch1
    column_strings: [IntDen, Count, '%Area']
    exclude: Combo
    specificity:
      - [Time, WeekEight]
      - [Time, WeekFour]

  - type: histograms
    batch: batch1
    marker: CK1d
    x_attr: Volume
    factor: Genotype
    combine: true
```

### Features
- `batch: name` selects which data source each entry uses
- `columns` is aliased to `filtered_columns` automatically
- Specificity lists are converted to Python tuples
- Validates plot types, parameter names, and column references before running
- Supports YAML (pyyaml), TOML (tomllib/tomli), and JSON (stdlib)

---

## Statistics (stats.py)

### Normality Testing
`test_normality(df_list)` — runs D'Agostino-Pearson, Anderson-Darling, Kolmogorov-Smirnov, and Shapiro-Wilk tests. Returns majority-vote normality boolean.

### Group Comparisons
- `runITTest()` — independent t-test with F-test for equal variance
- `runOWA()` — one-way ANOVA with Tukey post-hoc
- `runKW()` — Kruskal-Wallis with Dunn/Conover post-hoc (Bonferroni correction)
- `runTWA()` — two-way ANOVA with Tukey post-hoc
- `mwu_multiple_comparisons()` — Mann-Whitney U for multiple pairs

### `multipleComparisons()`
Master function that:
1. Tests normality
2. Auto-selects appropriate test (parametric vs non-parametric)
3. Runs group test + post-hoc comparisons
4. Saves results to CSV
5. Optionally annotates plot with significance brackets and summary text (`draw=True` by default)
6. Supports result caching via `cache_key` when `Config.STATS_CACHE` is enabled

### Stats Cache
When `Config.STATS_CACHE = True`, stats results are cached in a module-level dict keyed on `(column, conditions, specificity)`. Call `clear_stats_cache()` between independent analysis runs.

### Annotation
`plot_comparison_lines_from_figdata()` — draws SEM error bars and significance brackets with `*`, `**`, `***`, `****`, or `ns` annotations on bar plots.

---

## Modelling (modelling.py)

`iterative_best_fit()` — iterative feature-subset search using:
- Leave-one-out cross-validation
- OLS linear regression (statsmodels)
- Forward selection: starts with best single predictor, adds features that improve adjusted R²
- Generates correlation heatmaps, scatter plots, and model summary figures
- Handles sentinel values and specificity filtering

---

## Export (export.py)

### Name Maps
- `IF_NAME_MAP` — maps raw column patterns (with `<ab>`, `<ab2>` placeholders) to human-readable labels and descriptions
- `BEHAVIOR_NAME_MAP` — behavioral metric mappings
- `RAW_NAME_MAP` — per-object raw data mappings

### Key Functions
- `convert_name(colname)` → `(short_label, description)` using regex pattern matching
- `export_IF_summary_excel()` — one sheet per metric, data organized by condition
- `write_conditions_table_sheet()` — conditions metadata sheet
- `write_experiment_data_list_sheet()` — data overview with filter/analysis macros from Analysis Details files
- Formatting: `autosize_columns()`, `merge_contiguous_cells()`, `blank_repeats()`

---

## Serialization (serialization.py)

- `save_state(obj, filename)` — pickle with highest protocol, removes legacy image caches
- `load_state(filename)` — loads pickle, normalizes stale paths across machines/users, strips legacy inline image arrays
- `normalize_paths(obj)` — rebases `filePath` using `check_directory()` for cross-machine compatibility

---

## Image I/O (image_io.py)

Multi-backend image loading system:
- Priority order: tifffile (for TIFFs) → cv2 → imageio → PIL
- `read_image_array(path, backend, fast_loading, preview_max_dim)` — loads and normalizes images
- Downsampling support for preview/performance
- LRU-cached `get_image_shape()` for dimension queries

---

## Utilities (utils.py)

### String Helpers
- `strip_name()` — sanitize strings for filenames
- `clean_column_name()` — standardize ImageJ CSV column names
- `normalize_image_roi_name()` — normalize ROI labels (e.g., "SCN-1" → "RHSCN")
- `normalize_animal_name()` — normalize animal IDs for matching
- `replace_week_int()` — "Week2" → "WeekTwo" (for consistent naming)

### DataFrame Helpers
- `get_columns(df, column_strings, regex_string, exclude)` — flexible column selection
- `adjust_for_volumemm()` — normalize metrics per tissue volume (0.1 mm³)
- `add_coloc_percentages()` — derive percentage colocalisation columns

### Specificity Helpers
- `is_specificity_queue(specificity)` — True when specificity is a list of 2+ tuples
- `iter_specificities(specificity)` — yield individual specificity tuples
- `filter_df_by_specificity(df, specificity)` — filter DataFrame by factor values

### Geometry
- `trace_downward_nearest(x, y)` — trace a downward path through points by nearest-neighbor
- `moving_average(a, w)` — padded moving average for smoothing
- `points_to_polyline_distance(px, py, x_line, y_line)` — vectorized minimum distance from points to polyline

### Plotting
- `rc_params()` — set matplotlib rcParams for publication quality
- `save_fig()` — save as SVG with optional skip-existing check and long-path handling on Windows
- `plot_legend_separately()` — extract legend into its own figure
- `build_subfolder()` — construct output subfolder paths from specificity/marker context

### Progress
- `ProgressTracker` — notebook/terminal-friendly progress display with timing and ETA, supports IPython rich display

---

## Output System (_logging.py)

All package output is routed through a unified `IFLogger` singleton instead of bare `print()` calls. This enables global verbosity control and silencing.

### Verbosity Levels
`Verbosity` IntEnum with 5 levels:
- `error (0)` — only errors
- `warning (1)` — + warnings
- `info (2)` — + file confirmations, status updates, progress (default)
- `hint (3)` — + diagnostic detail (row counts, backend choices, skipped columns)
- `debug (4)` — + per-item trace

### Logger Methods (categories, not severity)
- `status(msg)` — progress updates, stage names (level >= info)
- `confirm(msg)` — file-saved / export-done messages (level >= info), prefixed `[OK]`
- `timing(msg)` — elapsed time, ETA summaries (level >= info), prefixed `[T]`
- `hint(msg)` — diagnostic detail (level >= hint)
- `debug(msg)` — per-item trace (level >= debug)
- `warn(msg)` — unexpected but non-fatal situations (level >= warning), prefixed `[!]`

### User-Facing API
```python
import IF_analysis

IF_analysis.set_verbosity('debug')    # or int 0-4, or Verbosity enum
IF_analysis.set_verbosity(0)          # silent

with IF_analysis.silent():
    batch.export_all_excel()          # no output

with IF_analysis.verbose():
    batch.processData()               # maximum detail
```

### Integration
- All modules import `from IF_analysis._logging import logger as _log`
- `ProgressTracker` (utils.py) handles live-updating progress bars independently
- `modelling.py`'s iterative_best_fit uses `ProgressTracker` for its model search loop
- Genuine warnings (missing data, fallback behavior) use `warnings.warn()` with typed categories
- User-invoked display functions (`cheat_sheet()`, `Experiment.info()`) still use `print()` directly

---

## Data Flow

```
1. Raw Data (ImageJ CSV exports + ROI zips + images)
        ↓
2. Experiment.__init__(name, filePath, threshold)
        ↓
3. experiment.processData()
   ├── Import CSVs from Objects/, Cells/, ROI Intensities/, Attributes/
   ├── Create marker objects (objectMarker, cellMarker, Antibody, Attribute)
   ├── Clean DataFrames, adjust coordinates, compute colocalisation
   ├── Build per-animal summary (means, totals, counts per volume)
   ├── Import images (scan directories, build image table)
   └── Assign SCN numbers
        ↓
4. Batch.__init__(name, experiment_list, conditions, filePath)
        ↓
5. batch.processData()
   ├── Process each child experiment
   ├── Merge summaries (outer join on AnimalName)
   ├── Handle NOT_INCLUDED_IN_EXPERIMENT sentinels
   ├── Label duplicate metric columns with .expN
   ├── Create save paths
   └── Import/merge images
        ↓
6. Analysis & Visualization
   ├── plot_mean_bars(batch, columns, specificity=...)
   ├── plot_matrices(batch, columns, ...)
   ├── plot_locations(batch, markers, ...)
   ├── stats.multipleComparisons(...)
   ├── iterative_best_fit(batch, y_col, ...)
   ├── run_spec({'batch1': batch1, ...}, 'plots.yaml')
   └── batch.export_all_excel()
        ↓
7. Persistence
   ├── save_state(batch, "batch.pkl")
   └── load_state("batch.pkl")
```

---

## Important Conventions

1. **Column naming:** `<MarkerName>_<Metric>` (e.g., `CK1d_Count`, `Iba1_VolumeMean`, `H31L21_ColocCountCK1d`)
2. **SCN naming:** `LHSCN`, `RHSCN`, `LHSCN2`, `RHSCN2` — left/right suprachiasmatic nucleus regions
3. **Sentinel values:** `NOT_INCLUDED_IN_EXPERIMENT` marks animals absent from specific experiments in batch summaries
4. **Factor system:** Conditions have a `factor` attribute for grouping (e.g., "Genotype", "Time"). Used for ANOVA and plot organization.
5. **Comparisons:** Legacy: string pairs like `"1-2"` (1-indexed positions). Preferred: named via `ConditionBuilder` — `.compare("Syn", "hAPP")`, `.compare_all_pairs()`, `.compare_to_control("Syn")`
6. **Path resolution:** `check_directory()` tries multiple usernames to resolve Dropbox/OneDrive paths across machines
7. **Image ROI mapping:** ROI zip keys are parsed to derive AnimalName, SCN name, and ImageROI labels. The system handles both cropped and uncropped ROIs.
8. **Specificity filtering:** `specificity=('Time', 'WeekEight')` filters the summary to specific factor levels before analysis
9. **Specificity queues:** `[('Time', 'WeekEight'), ('Time', 'WeekFour')]` — list of tuples produces multiple plots, one per entry
10. **SVG output:** All figures are saved as SVG for publication-ready, editable output

---

## Typical Usage (from a Jupyter notebook)

```python
from IF_analysis import *
from IF_analysis import plotting
from IF_analysis.utils import rc_params

# Set up display
rc_params()

# Define conditions — fluent builder (preferred)
conditions = (
    ConditionBuilder("Genotype")
    .add("WT", short="WT", color="blue")
    .add("KO", short="KO", color="red")
    .compare("WT", "KO")
    .explain("<> mice")
    .build()
)

# Or the classic API (still works):
# WT = condition('WT', 'WT', Config.COLORS['blue'], 'Genotype', '<> mice')
# KO = condition('KO', 'KO', Config.COLORS['red'], 'Genotype', '<> mice')
# conditions = conditionList([WT, KO], comparisons=['1-2'])

# Create or load batch
batch = create_batch(
    "My Experiment",
    conditions,
    batch_path="path/to/output",
    experiments={"Cohort1": "path/to/data1", "Cohort2": "path/to/data2"},
    pickle_path="path/to/cache",
)

# Plot individually
plotting.plot_mean_bars(batch, column_strings=['IntDen', 'Count'],
                        specificity=('Time', 'WeekEight'))

# Or run all plots from a YAML spec
run_spec(batch, 'plots.yaml')

# Check available parameters
from IF_analysis import cheat_sheet
cheat_sheet('mean_bars')

# Export
batch.export_all_excel()

# Save state
save_state(batch, "my_batch.pkl")
```
