# Performance Optimization Handoff — Remaining Tasks

Read this file fully before doing anything. Then execute the plan at the bottom.

## Context

IF_analysis is a Python package for immunofluorescence confocal microscopy analysis.
A performance optimization pass was completed on 2025-03-25. Tier 1 and most of
tier 2 are done. This file describes the remaining work.

**Constraints (from the user — these are non-negotiable):**
- SVG output is non-negotiable — publication-ready, editable
- No TIFFs loaded in the pipeline — skip image-loading optimizations
- Minimize new dependencies — prefer already-installed or tiny pure-Python packages
- No napari / PyQtGraph / DearPyGui — avoid Qt conflicts and heavy installs
- Parallel plotting should only trigger for large batches
- Skip behaviors default to off (opt-in)
- Must be easy to use and robust

## What was already done

Read the git log for full details. Summary of changes in `config.py`, `utils.py`, `plotting.py`:

1. **Replaced pyimagej** with pure Python percentile clipping (`_enhance_contrast_channel`,
   `_enhance_contrast_rgb`, `_suggest_auto_adjustments` with scipy Powell optimizer).
   All `imagej` imports and JVM code removed.

2. **Edit mode optimized:** preview default bumped 320->512px; persistent
   `FigureCanvasTkAgg` with blitting (rasterizes to RGBA, uses `set_data()` +
   `blit()`); debounce bumped 120->250ms.

3. **Plot caching in `save_fig()`:** `skip_existing` (file existence check) and
   `cache` (content-hash via `.plot_cache.json` sidecar). Both default False,
   controlled by `Config.SKIP_EXISTING` and `Config.PLOT_CACHE`.

4. **Matplotlib fast-path:** `_apply_matplotlib_fast_path()` in config.py sets path
   simplification, Agg chunking, `plt.ioff()` at import. `rasterize_data_artists()`
   applied before SVG saves in `save_fig()`.

5. **Figure reuse:** `plot_mean_bars`, `plot_histograms`, `plot_matrices`,
   `plot_volcano` reuse a shared figure across iterations (ax.clear() + redraw
   instead of plt.subplots() per column).

6. **Parallel infrastructure:** `parallel_map()` in utils.py wraps joblib with
   threshold gating (`Config.PARALLEL_THRESHOLD = 30`). Graceful fallback to
   sequential if joblib not installed.

---

## Task A: Altair interactive HTML export (INDEPENDENT — can run in parallel)

### Goal
Alongside SVG plots, optionally export a single self-contained interactive HTML file
with all results as linked charts. Hover for values, click to filter conditions.
Works offline in any browser. Useful for exploring results and sharing with
collaborators who don't have Python.

### Constraints
- `pip install altair` — ~1MB, pure Python, no Node.js
- Default row limit is 5000 — override with `alt.data_transformers.disable_max_rows()`
  or pre-aggregate
- P-value annotations from stats aren't available in Altair — the HTML version shows
  data without significance brackets. Pre-compute and inject as text layers if needed.
- If altair is not installed, skip silently (try/except ImportError). Never crash.

### Approach
1. Add `Config.EXPORT_HTML = False` to `IF_analysis/config.py`.
2. After each `run()` call completes in the one-liner wrappers, if html export is
   enabled, collect all the per-column DataFrames that were plotted and build an
   Altair chart spec.
3. For bar charts: `alt.Chart(df).mark_bar()` with `color='Condition'` encoding.
   Add stripplot points via `mark_circle()` layered on top.
4. For violin/histogram: use `alt.Chart().transform_density()`.
5. Facet by column using `alt.Chart().facet('column:N')`.
6. Save with `chart.save('results_summary.html')` — embeds Vega-Lite JS inline.
7. One HTML file per `plot_*` call, saved alongside the SVG folder.

### Example structure
```python
import altair as alt

def _export_html_bar(experiment, columns, specificity, save_path):
    charts = []
    for col in columns:
        df = experiment.summary[['AnimalName', 'Condition', col]].dropna()
        bar = alt.Chart(df).mark_bar().encode(
            x='Condition:N',
            y=alt.Y(f'{col}:Q', title=get_display_name(col)),
            color='Condition:N',
        )
        points = alt.Chart(df).mark_circle(size=40, opacity=0.6).encode(
            x='Condition:N',
            y=f'{col}:Q',
            color='Condition:N',
        )
        charts.append((bar + points).properties(title=get_display_name(col)))
    combined = alt.vconcat(*charts).resolve_scale(color='shared')
    combined.save(os.path.join(save_path, 'interactive_summary.html'))
```

### Files to modify
- `IF_analysis/config.py` — add `Config.EXPORT_HTML = False`
- `IF_analysis/plotting.py` — add `_export_html_*` helper functions; call from
  the one-liner wrappers after `run()` returns.
- `IF_analysis/utils.py` — optional: add `save_html()` utility.

---

## Task B: YAML/TOML plot specification DSL (INDEPENDENT — can run in parallel)

### Goal
Let users define entire plot runs in a declarative config file instead of writing
Python. Non-programmer lab members can edit specs. Validation catches typos before
rendering. The spec file is version-controllable.

### Example spec (YAML)
```yaml
plots:
  - type: mean_bars
    columns: [DAPI_Count, Iba1_Volume]
    specificity: [Time, WeekEight]
    points: true
    normalize: false

  - type: histograms
    marker: GFAP
    x_attr: Volume
    by: conditions
    bins: 30

  - type: matrices
    columns: [DAPI_Count, Iba1_Volume, GFAP_IntDen]
    by: conditions
    correlation: pearsonr

  - type: volcano
    columns: [DAPI_Count, Iba1_Volume]
    control: WT
```

### Approach
1. Use TOML (stdlib `tomllib` in 3.11+, `tomli` for 3.9-3.10) or JSON (stdlib).
   If using YAML, require `pip install pyyaml`. JSON is zero-dependency but less
   readable. Recommend: support both JSON and YAML, use whichever is available.
2. Create `IF_analysis/spec.py` (NEW FILE) with:
   - `load_spec(path)` — reads YAML/TOML/JSON, returns a list of plot dicts
   - `validate_spec(spec, experiment)` — checks column names exist, plot types
     are valid, parameters match function signatures
   - `run_spec(experiment, path)` — loads, validates, dispatches to plot functions
3. Map `type` field to plot functions:
   ```python
   PLOT_REGISTRY = {
       'mean_bars': plot_mean_bars,
       'histograms': plot_histograms,
       'matrices': plot_matrices,
       'volcano': plot_volcano,
       'ridgeline': plot_ridgeline,
       'ecdf': plot_ecdf,
       'regressions': plot_regressions,
       'pie_charts': plot_pie_charts,
       'locations': plot_locations,
       'images': plot_images,
       'representative_images': plot_representative_images,
   }
   ```
4. Each spec entry's keys (minus `type`) map directly to the function's kwargs.
   Use `inspect.signature` to validate parameter names at load time.
5. Specificity in the spec should support both single tuple and queue syntax:
   ```yaml
   specificity: [Time, WeekEight]           # single filter
   specificity:                              # queue
     - [Time, WeekEight]
     - [Region, CA1]
   ```
6. Export `run_spec` from `__init__.py`.

### Files to create/modify
- `IF_analysis/spec.py` — NEW FILE with `load_spec`, `validate_spec`, `run_spec`
- `IF_analysis/__init__.py` — export `run_spec`

### Dependency
- None if using JSON
- `tomli` (~50KB, pure Python) for TOML on Python <3.11
- `pyyaml` for YAML support (optional)

---

## Task C: Wire `parallel_map` into plot functions (depends on A and B merging first)

### Goal
When a specificity queue or column list is large enough (>= PARALLEL_THRESHOLD),
dispatch iterations in parallel using the existing `parallel_map` in utils.py.

### Why it was deferred
Experiment objects may not serialize cleanly via pickle/loky. Stats functions write
normality test figures to disk — potential directory race conditions. Each worker
needs its own matplotlib Agg backend. Needs live testing with real data.

### Approach
The safest parallelism boundary is the **specificity queue** level. Each queue entry
produces completely independent outputs (different subfolders/filenames).

In each `plot_*` function, the queue pattern looks like:
```python
if _is_specificity_queue(specificity):
    queued_outputs = {}
    for spec_tuple in _iter_specificities(specificity):
        queued_outputs[spec_tuple] = plot_mean_bars(
            experiment, ..., specificity=spec_tuple, ...
        )
    return queued_outputs
```

Replace the sequential loop with `parallel_map` when the queue is large:
```python
if _is_specificity_queue(specificity):
    specs = list(_iter_specificities(specificity))
    def _run_one(spec_tuple):
        return plot_mean_bars(experiment, ..., specificity=spec_tuple, ...)
    return parallel_map(_run_one, specs)
```

### Key risks to test
- Pickle the experiment object: `import pickle; pickle.dumps(experiment)` — if this
  fails, parallel_map will need shared memory or a different serialization approach.
- Directory creation races: `os.makedirs(exist_ok=True)` should be safe but verify.
- matplotlib worker isolation: each loky worker should call `matplotlib.use('Agg')`
  before any pyplot import. This may need a wrapper function.
- Stats normality figures: verify they don't collide when two workers write to the
  same experiment's fig_path.

### Files to modify
- `IF_analysis/plotting.py` — the `_is_specificity_queue` blocks in: `plot_mean_bars`,
  `plot_histograms`, `plot_matrices`, `plot_volcano`, `plot_ridgeline`, `plot_ecdf`,
  `plot_regressions`, `plot_pie_charts`, `plot_rect_matrices`.
- `IF_analysis/utils.py` — `parallel_map()` may need a worker init function that
  sets `matplotlib.use('Agg')`.

---

## Task D: Stats pre-computation cache + dry_run mode (depends on A and B merging first)

### Goal
Cache statistical test results keyed on `(column, condition_pair, specificity)` within
a single `run()` call so that repeated comparisons aren't recomputed. Add a
`dry_run=True` mode that prints a stats summary table without rendering plots.

### Why it was deferred
The stats functions (`multipleComparisons`, `runITTest`, `mwu_multiple_comparisons`)
in `stats.py` are tightly coupled to matplotlib axes — they draw p-value annotations
directly onto the axes during computation. Caching requires separating the compute
step from the draw step.

### Approach
1. In `stats.py`, refactor `multipleComparisons` to optionally return a results dict
   without drawing when `draw=False` is passed. The results dict should contain:
   test name, p-values, posthoc results, comparison pairs, significance levels.
2. Add a draw function that takes the results dict and annotates axes.
3. In plotting.py's teardown functions, check a cache dict before calling stats.
   Cache key: `(column_name, frozenset(condition_names), specificity_tuple)`.
4. For `dry_run`: add a `dry_run=False` param to the one-liner wrappers. When True,
   run all stats but skip figure creation/saving. Print a pandas DataFrame summary.

### Files to modify
- `IF_analysis/stats.py` — `multipleComparisons`, `runITTest`,
  `mwu_multiple_comparisons`: add `draw=True` parameter, split compute from annotate.
- `IF_analysis/plotting.py` — teardown functions in plot_mean_bars (line ~8700).
- `IF_analysis/iteration.py` — optionally add a `dry_run` pathway to `run()`.

---

## Execution Plan

**IMPORTANT: Tasks A and B are fully independent and touch different files. Run them
in parallel using isolated worktrees to avoid merge conflicts.**

### Step 1: Spawn two parallel agents in worktrees

Spawn Agent 1 (worktree, isolation) for Task A — Altair HTML export:
- Modifies: `config.py` (one line), `plotting.py` (new helper functions + calls in
  one-liner wrappers), optionally `utils.py`
- Creates: nothing new

Spawn Agent 2 (worktree, isolation) for Task B — YAML/TOML DSL:
- Creates: `IF_analysis/spec.py` (new file)
- Modifies: `IF_analysis/__init__.py` (add export)
- Does NOT touch plotting.py, config.py, or utils.py

These two agents run simultaneously. Wait for both to complete.

### Step 2: Merge both worktree branches

After both agents finish, merge their branches into the main branch. There should
be zero conflicts since they touch completely different files (with the exception
of config.py which only gets a one-line addition in Task A).

### Step 3: Sequential — Task C (parallel wiring) then Task D (stats cache)

These both modify `plotting.py` heavily, so run them sequentially on the main
branch after A and B are merged. Task C should be done before D since the parallel
infrastructure may affect how the stats cache is wired.

---

## General notes

- Syntax-check plotting.py with: `python -c "import ast; ast.parse(open('IF_analysis/plotting.py', encoding='utf-8-sig').read())"`
  (the file has a BOM)
- plotting.py is ~12,200 lines. Use grep to navigate, don't read the whole thing.
- All Config settings default to off/conservative — the user opts in.
- The user prefers minimal dependencies and robust fallbacks.
- SVG is the only save format — never switch to PNG default.
- The specificity queue convention: list of tuples = multiple plots, single tuple = one filter. All plot funcs must support this.
- When adding optional dependencies (altair, pyyaml, tomli), always wrap in try/except ImportError and skip silently if not installed. Never make them mandatory.
