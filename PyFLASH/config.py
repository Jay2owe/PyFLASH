"""
Centralised configuration — paths, thresholds, colors, and display constants.

All the scattered globals from the notebook live here now.
"""

import os
import warnings
import logging
from collections import defaultdict

from PyFLASH.palette import PIPELINE as PIPELINE_COLORS

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.ERROR)
logging.getLogger('matplotlib').setLevel(logging.ERROR)


class Config:
    """
    Global configuration singleton. Modify attributes directly or subclass
    for project-specific overrides.

    Usage:
        from PyFLASH.config import Config
        Config.THRESHOLD = 50
        Config.PIXEL_SIZE = 3.52
    """

    # ── Processing defaults ────────────────────────────────────────────
    THRESHOLD = 30
    PIXEL_SIZE = 3.51998900003   # microns per pixel
    SECTION_THICKNESS_UM = 13.0  # legacy fallback when ROI volume is unavailable

    # ── Directory resolution ───────────────────────────────────────────
    # Optional fallback usernames for resolving shared paths across machines.
    # Override locally if you need cross-user path translation.
    FALLBACK_USERS = []

    # ── Display labels ─────────────────────────────────────────────────
    AB = 'Aβ'
    CK = 'CK1δ'
    TOTAL_LABEL = 'Total Particle Integrated Density / 0.1mm³'
    COUNT_LABEL = 'Count / 0.1mm³'
    CUBED = '³'

    # ── Hex color palette ──────────────────────────────────────────────
    # The values live in PyFLASH.palette, which is the one module allowed to
    # spell a colour out. This name stays because scripts going back years
    # write `Config.COLORS['dark_cyan']`, and it is the same dict either way.
    COLORS = PIPELINE_COLORS

    # ── Save mode ──────────────────────────────────────────────────────
    SAVE_MODE = True   # False to skip saving figures
    # Filename (no extension) of the per-run overview montage every pipeline
    # writes. The leading "!" sorts it above digits and letters in Windows
    # Explorer so it stays the first thing seen in a run folder. Set to
    # "00 - Overview Montage" to restore the historical name.
    MONTAGE_FILENAME = "! Overview Montage"
    SKIP_EXISTING = False  # True to skip saving when output file already exists
    EXPORT_HTML = False  # True to export interactive Altair HTML alongside SVG plots
    STATS_CACHE = False  # True to cache stats results within a session

    # ── Figure aesthetic / layout ──────────────────────────────────────
    # HOUSE_STYLE applies the current set_pyflash_style() house style on first
    # plotting import so every figure shares one uniform aesthetic.
    # USE_PYFLASH_LAYOUT attaches the overlap-safe PyFlashLayout engine at save
    # time (shrinks over-long titles, lifts overlapping suptitles; never shrinks
    # the data axes). Both are on by default; set False to restore raw behaviour.
    HOUSE_STYLE = True
    RECORD_STATS = True  # False to stop recording a figure's statistics in its provenance
    FIGURE_PROFILE = "master"  # master, public, or minimal_public
    # Every requested direct ReproFig carrier receives the same figure identity.
    # Supported values: svg, pdf, png, jpg/jpeg, tif/tiff, webp, avif, heic/heif.
    FIGURE_FORMATS = ("svg",)
    FIGURE_DPI = None  # numeric override; raster defaults come from ReproFig
    FIGURE_DPI_PRESET = None  # screen, continuous_tone, or line_art
    FIGURE_RENDER_PRESET = None  # synonym for FIGURE_DPI_PRESET
    FIGURE_WIDTH = None  # optional rendered width in inches
    FIGURE_HEIGHT = None  # optional rendered height in inches
    FIGURE_FORMAT_OPTIONS = None  # global options or {format: {option: value}}
    FIGURE_ALLOW_REENCODE = False  # needed only for carrier conversions
    FIGURE_SAFE_COLUMNS = None  # explicit allowlist used by direct public saves
    FIGURE_PUBLIC_SOURCES = None  # approved source-id/path -> public URL mapping
    FIGURE_COMPANION_CSV = False  # master already embeds exact CSV bytes
    FIGURE_PROOF = False  # opt in to semantic/statistical proof capture
    FIGURE_PROOF_POLICY = None  # required grades and non-secret key/env references
    USE_PYFLASH_LAYOUT = True

    # ── Effect sizes ───────────────────────────────────────────────────
    EFFECT_SIZES = True        # compute effect sizes alongside p-values
    EFFECT_CI = True           # bootstrap CIs for parametric pairwise effects
    EFFECT_CI_RESAMPLES = 5000  # bootstrap resamples for EFFECT_CI

    # ── Path aliases ──────────────────────────────────────────────────
    # User-defined overrides for specificity/factor abbreviations.
    # Auto-generated aliases are built at batch creation; manual entries
    # here take priority.  Example: {'WeekEight': 'W8', 'Genotype': 'GT'}
    ALIASES = {}


_fast_path_applied = False


def apply_matplotlib_fast_path():
    """Set matplotlib rcParams for faster rendering.

    Idempotent and lazy.  Importing PyFLASH no longer triggers a matplotlib
    import; this runs the first time a plotting/stats/modelling module loads
    (or a figure is saved).  The 'fast' settings aggressively simplify paths
    and chunk the Agg rasteriser, which speeds up saving large SVGs with many
    data-heavy artists, and turn off interactive mode.
    """
    global _fast_path_applied
    if _fast_path_applied:
        return
    try:
        import matplotlib as mpl
        from matplotlib import pyplot as _plt
        mpl.rcParams['path.simplify'] = True
        mpl.rcParams['path.simplify_threshold'] = 1.0
        mpl.rcParams['agg.path.chunksize'] = 10000
        # Keep SVG output editable: emit every string (titles, tick numbers,
        # axis labels, significance stars, p-values, matrix annotations) as a
        # real <text> element instead of vectorised glyph paths, so figures open
        # as editable text in Illustrator/Inkscape. Set globally here — the first
        # time matplotlib is touched — so even ad-hoc ``plt.savefig("x.svg")``
        # inherits it, not only saves routed through ``utils.save_fig``.
        # ``mathtext.default='regular'`` renders any ``$…$`` in the body font as
        # clean upright text rather than fragmented DejaVu-oblique glyphs.
        mpl.rcParams['svg.fonttype'] = 'none'
        mpl.rcParams['mathtext.default'] = 'regular'
        _plt.ioff()
        _fast_path_applied = True
    except Exception:
        pass


# Backwards-compatible private alias (kept for any external references).
_apply_matplotlib_fast_path = apply_matplotlib_fast_path


def generate_palettes(colors=None):
    """Generate blend palette strings from all color pairs."""
    if colors is None:
        colors = Config.COLORS
    palettes = {}
    for k1, v1 in colors.items():
        for k2, v2 in colors.items():
            palettes[f'{k1}-{k2}'] = f'blend:{v1},{v2}'
    return palettes


def check_directory(file_path):
    """
    Resolve a file path across multiple user directories.
    Tries Config.FALLBACK_USERS until one exists.
    """
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) < 3:
        return file_path if os.path.exists(file_path) else None

    curr_dir = parts[2]
    for user in Config.FALLBACK_USERS:
        candidate = file_path.replace(curr_dir, user)
        if os.path.exists(candidate):
            return candidate
    if os.path.exists(file_path):
        return file_path
    return None
