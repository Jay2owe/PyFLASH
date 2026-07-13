# Example Dataset

`example_data.py` builds one small, **seeded, domain-neutral** synthetic study
used to render the gallery example graphs. It is rich enough to drive 26 of the
28 `PyFLASH.plotting` functions (the two image plots need real image files and
are out of scope).

## Build it

```python
import sys
sys.path.insert(0, "docs/wiki/examples")   # or add the folder to PYTHONPATH
from example_data import build_example_data

ex = build_example_data()          # or build_example_data(fig_path="out") to save figures
exp = ex.experiment                # DataFrameExperiment (summary + .data["Marker1"])
```

## What it contains

| Layer | Shape | Drives |
|---|---|---|
| `ex.summary` | 42 subjects × (group, cohort, 6 marker metrics, `x1`/`x2`/`Signal`, `Acrophase (h)`, `Amplitude`) | bars, matrices, regression, volcano, radar, PCA, forest, group-matrix, 3D scatter, acrophase clock |
| `ex.markers` (`exp.data["Marker1"]`) | 336 objects × (volume, intensity, `XM`/`YM`, coloc + combo flags) | histograms, ridgeline, ECDF, pies, combo pies, superplot, locations, coloc UpSet/Sankey |
| `ex.timecourse` | long: `Response` vs `Timepoint` per group | timecourse |
| `ex.cosinor` | long: `Response` vs `ZT` per group | cosinor |

## Design (structure is baked in, not noise)

- **Groups** `A` (control), `B`, `C` with real, differentiated group means.
- **Group-varying correlation** between `Marker1_Count` and `Marker2_Count`
  (r ≈ +0.86 / +0.19 / −0.86 across A/B/C) so matrix-difference plots have
  signal.
- **Linear predictors** `x1`, `x2` jointly explain `Signal` (r ≈ 0.65–0.68).
- **24 h circadian rhythm** with group-shifted acrophase (peaks ≈ ZT 6 / 10 / 15)
  and amplitude.
- **Longitudinal growth curve** with group-specific slopes.
- **Colocalisation / combo** rates that rise across groups (0.28 → 0.55 → 0.80).

## Regenerating the gallery figures

`render_gallery.py` renders one curated SVG per plot into
`../gallery/images/` (embedded by each `functions/plot_*.md` page and the
[Plot Gallery](../gallery/plot-gallery.md)). Run it from the repo root:

```bash
python docs/wiki/examples/render_gallery.py <tmp-dir> --save
```

`render_gallery.py` clears `<tmp-dir>` before rendering, so use a disposable
folder.

Without `--save` it runs a diagnostic pass (reports what each plot emits and
may write temporary files below the supplied output directory, but does not
update `../gallery/images/`). Set `QC_DIR=<dir>` to also dump PNG previews. It taps
`PyFLASH.utils.save_fig` to capture each figure, picks one representative per
plot, and handles the Sankey (plotly) and `plot_locations` (needs an
image-pixel canvas) specially.

The render calls live in `gallery_examples.py`. The function pages show those
same calls above each example figure. After changing a gallery example, refresh
the visible snippets with:

```bash
python docs/wiki/examples/update_gallery_snippets.py
```

## Coverage notes

- `plot_coloc_upset` needs `upsetplot`; `plot_coloc_sankey` needs `plotly`
  (`kaleido` for static SVG/PNG export).
- `plot_images` and `plot_representative_images` are **not** covered — they
  require real image files on disk.
- `plot_superplot` and `plot_locations` are called with `roi="ROIa"` (the
  dataset's neutral ROI family name).
