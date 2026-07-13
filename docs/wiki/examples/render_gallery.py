"""Render one curated SVG per PyFLASH plot into docs/wiki/gallery/images/.

Strategy: monkeypatch utils.save_fig (the single figure choke point) to capture
the Figure objects a plot creates, plus inspect return values for plots that
hand the figure back directly. Save the first/representative figure per plot.
The plotly Sankey is handled separately. Render calls come from
gallery_examples.py, which also feeds the Markdown snippets above each example
figure.
"""
import os, sys, glob, shutil, traceback
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"   # keep SVG text editable
from matplotlib.figure import Figure

sys.path.insert(0, "docs/wiki/examples")
import example_data as E
from gallery_examples import execute_gallery_code, gallery_examples
import PyFLASH.utils as U
import PyFLASH.plotting as P
from PyFLASH.aesthetics import (
    apply_pyflash_figure_geometry,
    normalize_pyflash_svg_canvas,
    pyflash_savefig_kwargs,
)
from PyFLASH.layout import apply_pyflash_layout

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
            apply_pyflash_layout(fig)
            apply_pyflash_figure_geometry(fig)
            with matplotlib.rc_context({"svg.fonttype": "none", "mathtext.default": "regular"}):
                svg_path = os.path.join(IMG, f"{name}.svg")
                fig.savefig(
                    svg_path,
                    format="svg",
                    **pyflash_savefig_kwargs(transparent=True),
                )
                normalize_pyflash_svg_canvas(svg_path)
            qc = os.environ.get("QC_DIR")
            if qc:
                os.makedirs(qc, exist_ok=True)
                with matplotlib.rc_context({"svg.fonttype": "none", "mathtext.default": "regular"}):
                    fig.savefig(
                        os.path.join(qc, f"{name}.png"),
                        **pyflash_savefig_kwargs(dpi=72, transparent=False),
                    )

def new_exp():
    return E.build_example_data(fig_path=TMP)

ex = new_exp(); exp = ex.experiment
context = {"P": P, "exp": exp, "ex": ex, "TMP": TMP}
sankey = None
for example in gallery_examples():
    if example.plotly_file:
        sankey = example
        continue
    render(
        example.name,
        lambda example=example: execute_gallery_code(example.code, context),
        pick=example.pick,
    )

# --- plotly Sankey: saves its own file; glob it out of the temp dir --------
if sankey is not None:
    print(f"  {sankey.name} (plotly) ...")
    before = set(glob.glob(os.path.join(TMP, "**", "*"), recursive=True))
    try:
        execute_gallery_code(sankey.code, context)
        after = set(glob.glob(os.path.join(TMP, "**", "*"), recursive=True))
        new = [f for f in (after - before) if f.lower().endswith((".svg", ".png", ".html"))]
        print("    sankey new files:", [os.path.basename(f) for f in new])
        if not DIAG and new:
            # prefer the richest group (C), then svg > png > html
            new.sort(key=lambda f: (0 if "_C." in os.path.basename(f) or "Condition_C" in os.path.basename(f) else 1,
                                     {".svg":0,".png":1,".html":2}.get(os.path.splitext(f)[1].lower(),9)))
            ext = os.path.splitext(new[0])[1].lower()
            shutil.copy(new[0], os.path.join(IMG, f"{sankey.name}{ext}"))
    except Exception as e:
        print("    sankey ERR:", type(e).__name__, str(e)[:100])

print("\nMODE:", "DIAGNOSTIC (no files saved)" if DIAG else "SAVED to " + IMG)
if not DIAG:
    print("images:", sorted(os.path.basename(f) for f in glob.glob(os.path.join(IMG, "*"))))
