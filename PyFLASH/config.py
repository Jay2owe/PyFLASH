"""
Centralised configuration — paths, thresholds, colors, and display constants.

All the scattered globals from the notebook live here now.
"""

import os
import warnings
import logging
from collections import defaultdict

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
    COLORS = {
        'red': '#ff0000',
        'cyan': '#42f5f5',
        'dark_cyan': '#0e3231',
        'dark_red': '#240004',
        'orange': '#ff8400',
        'blue': '#40ffff',
        'dark_blue': '#03358c',
        'magenta': '#ff47f0',
        'dark_magenta': '#8a2481',
        'green': '#00ff00',
        'dark_green': '#002404',
        'yellow': '#FFFB83',
        'dark_yellow': '#414100',
        'grey': '#d4d4d4',
        'dark_grey': '#d4d4d4',
        'black': '#000000',
        'purple': '#4d0254',
    }

    # ── Save mode ──────────────────────────────────────────────────────
    SAVE_MODE = True   # False to skip saving figures
    SKIP_EXISTING = False  # True to skip saving when output file already exists
    EXPORT_HTML = False  # True to export interactive Altair HTML alongside SVG plots
    STATS_CACHE = False  # True to cache stats results within a session

    # ── Figure aesthetic / layout ──────────────────────────────────────
    # HOUSE_STYLE applies the notebook's rc_params() house style on first
    # plotting import so every figure shares one uniform aesthetic.
    # USE_PYFLASH_LAYOUT attaches the overlap-safe PyFlashLayout engine at save
    # time (shrinks over-long titles, lifts overlapping suptitles; never shrinks
    # the data axes). Both are on by default; set False to restore raw behaviour.
    HOUSE_STYLE = True
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
