"""Render one curated SVG per PyFLASH plot into docs/wiki/gallery/images/.

Strategy: monkeypatch utils.save_fig (the single figure choke point) to capture
the Figure objects a plot creates, plus inspect return values for plots that
hand the figure back directly. Save the first/representative figure per plot.
The plotly Sankey is handled separately.
"""
import os, sys, glob, shutil, traceback
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"   # keep SVG text editable
from matplotlib.figure import Figure

sys.path.insert(0, "docs/wiki/examples")
import example_data as E
import PyFLASH.utils as U
import PyFLASH.plotting as P

IMG = os.path.abspath("docs/wiki/gallery/images")
TMP = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "scratch_render_tmp")
os.makedirs(IMG, exist_ok=True)
if os.path.isdir(TMP):
    shutil.rmtree(TMP)   # fresh temp so the Sankey new-file detection works
os.makedirs(TMP, exist_ok=True)

# --- tap save_fig ---------------------------------------------------------
_captured = []
_orig = U.save_fig
def _patched(figure, save_path, image_name, *a, **k):
    _captured.append((image_name, figure))
    try:
        return _orig(figure, save_path, image_name, *a, **k)
    except Exception:
        return None
U.save_fig = _patched
if getattr(P, "save_fig", None) is not None:
    P.save_fig = _patched

def _figs(o, acc):
    if isinstance(o, Figure): acc.append(o)
    elif isinstance(o, dict):
        for v in o.values(): _figs(v, acc)
    elif isinstance(o, (list, tuple)):
        for v in o: _figs(v, acc)
    elif hasattr(o, "figure") and isinstance(getattr(o, "figure"), Figure):
        acc.append(o.figure)

DIAG = ("--save" not in sys.argv)

def render(name, fn, pick=0):
    _captured.clear()
    try:
        r = fn()
    except Exception as e:
        print(f"  [ERR ] {name}: {type(e).__name__}: {str(e)[:80]}")
        return
    ret = []; _figs(r, ret)
    caps = _captured
    print(f"  {name:38} captured={len(caps)} return_figs={len(ret)}  names={[n for n,_ in caps][:4]}")
    if not DIAG:
        fig = None
        if caps:
            idx = pick if pick < len(caps) else 0
            fig = caps[idx][1]
        elif ret:
            fig = ret[0]
        if fig is not None:
            fig.savefig(os.path.join(IMG, f"{name}.svg"), format="svg", bbox_inches="tight")
            qc = os.environ.get("QC_DIR")
            if qc:
                os.makedirs(qc, exist_ok=True)
                fig.savefig(os.path.join(qc, f"{name}.png"), dpi=72, bbox_inches="tight")

def new_exp():
    return E.build_example_data(fig_path=TMP)

ex = new_exp(); exp = ex.experiment
NUM = ["Marker1_Count","Marker2_Count","Marker3_Count",
       "Marker1_IntDenMean","Marker2_IntDenMean","Marker3_IntDenMean"]

render("plot_mean_bars", lambda: P.plot_mean_bars(exp, filtered_columns=["Marker1_Count"], save=True))
render("plot_matrices", lambda: P.plot_matrices(exp, filtered_columns=NUM, save=True), pick=0)
render("plot_rect_matrices", lambda: P.plot_rect_matrices(exp, filtered_columns=["Marker1_Count","Marker2_Count","Marker3_Count"], against_columns=["x1","x2","Signal"], save=True))
render("plot_matrix_differences", lambda: P.plot_matrix_differences(exp, filtered_columns=NUM, comparisons=[("A","C")], save=True), pick=0)
render("plot_regressions", lambda: P.plot_regressions(exp, x="x1", y="Signal", combine=True, save=True))
render("plot_multivariable_regression_matrix", lambda: P.plot_multivariable_regression_matrix(exp, filtered_columns=["Signal"], predictors={"Predictors":["x1","x2"]}, by="all", save=True))
render("plot_volcano", lambda: P.plot_volcano(exp, filtered_columns=NUM, control="A", save=True), pick=1)
render("plot_radar", lambda: P.plot_radar(exp, filtered_columns=["Marker1_Count","Marker2_Count","Marker3_Count","Marker1_IntDenMean"], combine=True, save=True))
render("plot_scatter_3d", lambda: P.plot_scatter_3d(exp, x="x1", y="x2", z="Signal", combine=True, save=True))
render("plot_marker_pca", lambda: P.plot_marker_pca(exp, columns=NUM, save=True))
render("plot_effect_forest", lambda: P.plot_effect_forest(exp, filtered_columns=NUM[:3], control="A", effect_ci=False, save=True))
render("plot_group_matrix", lambda: P.plot_group_matrix(exp, filtered_columns=NUM[:3], control="A", save=True))
render("plot_histograms", lambda: P.plot_histograms(exp, marker="Marker1", x_attr="Volume", combine=True, save=True))
render("plot_ridgeline", lambda: P.plot_ridgeline(exp, marker="Marker1", x_attr="Volume", save=True))
render("plot_ecdf", lambda: P.plot_ecdf(exp, marker="Marker1", x_attr="Volume", save=True), pick=0)
render("plot_pie_charts", lambda: P.plot_pie_charts(exp, marker="Marker1", x_attr="Volume", threshold=12.0, save=True), pick=1)
render("plot_combo_pies", lambda: P.plot_combo_pies(exp, marker="Marker1", family="comboany", save=True), pick=2)
render("plot_superplot", lambda: P.plot_superplot(exp, filtered_columns=["Marker1_IntDenMean"], by="conditions", roi="ROIa", save=True))
def _locations_example():
    # plot_locations is an image-overlay plot: its points-only mode is invisible
    # on the default 500x800 pixel canvas (inverted y) unless coordinates are
    # scaled to that canvas. Build a clean single-animal spatial map.
    import numpy as _np, pandas as _pd
    from PyFLASH import from_dataframe as _fd
    r = _np.random.default_rng(7); n = 110
    cl = r.integers(0, 2, n)
    xm = _np.where(cl == 0, r.normal(180, 45, n), r.normal(330, 50, n))
    ym = _np.where(cl == 0, r.normal(300, 55, n), r.normal(520, 60, n))
    mk = _pd.DataFrame({
        "AnimalName": ["A1"] * n, "Condition": ["A"] * n,
        "Region": ["ROIa1"] * n, "ROI": ["ROIa"] * n,
        "Marker1_XM": _np.clip(xm, 20, 480), "Marker1_YM": -_np.clip(ym, 20, 780),
        "Marker1_IntDen": _np.clip(r.normal(100, 25, n), 0, None),
        "Marker1_Volume": _np.clip(r.normal(12, 3, n), 1, None)})
    summ = _pd.DataFrame({"AnimalName": ["A1"], "Condition": ["A"], "Marker1_Count": [float(n)]})
    e = _fd(summ, group_col="Condition", subject_col="AnimalName",
            data={"Marker1": mk}, fig_path=TMP)
    return P.plot_locations(e, objects=["Marker1"], roi="ROIa",
                            black_background=True, marker_colors={"Marker1": "#19e6ff"}, save=True)
render("plot_locations", _locations_example, pick=0)
render("plot_coloc_upset", lambda: P.plot_coloc_upset(exp, "Marker1", save=True), pick=2)
render("plot_condition_key", lambda: P.plot_condition_key(exp, save=False))
render("plot_power_curve", lambda: P.plot_power_curve(effect_sizes=(0.2,0.5,0.8), n_range=(2,20), save=False))
render("plot_cosinor", lambda: P.plot_cosinor(ex.cosinor, column="Response", time_col="ZT", group_col="Condition", period=24, save=False))
render("plot_timecourse", lambda: P.plot_timecourse(ex.timecourse, column="Response", time_col="Timepoint", group_col="Condition", time_map={"T1":1,"T2":2,"T3":4,"T4":8}, save=False))
render("plot_acrophase_clock", lambda: P.plot_acrophase_clock(exp, phase_col="Acrophase (h)", group_col="Condition", period=24, radius_col="Amplitude", save=True))

# --- plotly Sankey: saves its own file; glob it out of the temp dir --------
print("  plot_coloc_sankey (plotly) ...")
before = set(glob.glob(os.path.join(TMP, "**", "*"), recursive=True))
try:
    P.plot_coloc_sankey(exp, "Marker1", save=True)
    after = set(glob.glob(os.path.join(TMP, "**", "*"), recursive=True))
    new = [f for f in (after - before) if f.lower().endswith((".svg", ".png", ".html"))]
    print("    sankey new files:", [os.path.basename(f) for f in new])
    if not DIAG and new:
        # prefer the richest group (C), then svg > png > html
        new.sort(key=lambda f: (0 if "_C." in os.path.basename(f) or "Condition_C" in os.path.basename(f) else 1,
                                 {".svg":0,".png":1,".html":2}.get(os.path.splitext(f)[1].lower(),9)))
        ext = os.path.splitext(new[0])[1].lower()
        shutil.copy(new[0], os.path.join(IMG, f"plot_coloc_sankey{ext}"))
except Exception as e:
    print("    sankey ERR:", type(e).__name__, str(e)[:100])

print("\nMODE:", "DIAGNOSTIC (no files saved)" if DIAG else "SAVED to " + IMG)
if not DIAG:
    print("images:", sorted(os.path.basename(f) for f in glob.glob(os.path.join(IMG, "*"))))
