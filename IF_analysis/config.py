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
        from IF_analysis.config import Config
        Config.THRESHOLD = 50
        Config.PIXEL_SIZE = 3.52
    """

    # ── Processing defaults ────────────────────────────────────────────
    THRESHOLD = 30
    PIXEL_SIZE = 3.51998900003   # microns per pixel

    # ── Directory resolution ───────────────────────────────────────────
    # Fallback usernames to try when resolving OneDrive/Dropbox paths
    FALLBACK_USERS = ['jamie', 'Owner', 'jm3923']

    # ── Display labels ─────────────────────────────────────────────────
    AB = 'Aβ'
    CK = 'CK1δ'
    TOTAL_LABEL = 'Total Particle Integrated Density / micron³'
    COUNT_LABEL = 'Count / 1000000 microns³'
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
    PLOT_CACHE = False  # True to enable content-hash caching (skip unchanged plots)
    EXPORT_HTML = False  # True to export interactive Altair HTML alongside SVG plots
    PARALLEL_THRESHOLD = 30  # Min plot count before enabling parallel rendering (0=off)

    # ── Path aliases ──────────────────────────────────────────────────
    # User-defined overrides for specificity/factor abbreviations.
    # Auto-generated aliases are built at batch creation; manual entries
    # here take priority.  Example: {'WeekEight': 'W8', 'Genotype': 'GT'}
    ALIASES = {}


def _apply_matplotlib_fast_path():
    """Set matplotlib rcParams for faster rendering.

    Called once at import time.  The 'fast' style aggressively simplifies
    paths and chunks the Agg rasteriser, which speeds up saving large SVGs
    with many data-heavy artists.
    """
    try:
        import matplotlib as mpl
        from matplotlib import pyplot as _plt
        mpl.rcParams['path.simplify'] = True
        mpl.rcParams['path.simplify_threshold'] = 1.0
        mpl.rcParams['agg.path.chunksize'] = 10000
        _plt.ioff()
    except Exception:
        pass


_apply_matplotlib_fast_path()


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
