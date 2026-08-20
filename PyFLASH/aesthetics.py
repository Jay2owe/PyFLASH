"""PyFLASH-specific plotting style defaults.

``set_pyflash_style`` is the public front door for PyFLASH plot aesthetics. It
applies both Matplotlib-level defaults (fonts, ticks, spines, legends, editable
SVG text) and PyFLASH semantic defaults (condition style cycles, shared marker
sizes, significance annotations, matrix colour maps, and overview colours).

Colours are named, never spelled: every value below comes from
:mod:`PyFLASH.palette`, which is the one module allowed to write a hex literal.
Override a condition's colour with ``palette.declare_conditions``; override a
figure's look with ``set_pyflash_style``.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from collections.abc import Mapping

from PyFLASH import palette as _palette

_matrix = _palette.matrix_colors()


DEFAULT_PYFLASH_STYLE = {
    # Matplotlib house-style defaults applied by set_pyflash_style(), making
    # this module the single front door for spines, titles, labels, legends,
    # and tick styling.
    "line_width": 2,
    "tick_major_width": 2,
    "tick_major_size": 11,
    "tick_label_size": 20,
    "font_weight": "normal",
    "font_family": "Arial",
    "labelsize": 22,
    "labelweight": "normal",
    "title_size": 20,
    "title_weight": "bold",
    "despine": True,
    "legend_frame": False,
    "legend_fontsize": 15,
    "tick_direction": "out",

    # Export geometry.  These are deliberately PyFLASH-level knobs rather than
    # plot-specific kwargs: a user should be able to set the download canvas
    # once and assemble figures without manually resizing every panel later.
    "figure_size": (7.0, 5.0),
    "figure_orientation": "landscape",
    "save_bbox": "fixed",
    "save_pad_inches": 0.1,
    "save_dpi": 600,
    "fixed_layout": False,
    "fixed_layout_pad": 1.0,

    # Condition/group semantic styling.
    "auto_style": True,
    "condition_style_cycle": ["fill", "hollow", "///", "...", "xxx", "\\\\\\"],

    # Universal marker diameter in points. PyFLASH converts this to each
    # plotting backend's expected units so point markers line up across plot
    # families (Matplotlib scatter APIs receive area = point_size ** 2).
    "point_size": 9,

    # Mean-bar per-subject point overlay.
    "bar_point_fill": "white",
    "bar_point_edge": "group",
    "bar_point_linewidth": 3,

    # Generic strip/scatter action defaults.
    "scatter_alpha": 0.6,
    "scatter_jitter": 0.3,

    # Regression scatter and fit-line defaults.
    "regression_point_alpha": None,
    "regression_point_edge": None,
    "regression_point_linewidth": None,
    "regression_line_width": 6.75,
    "regression_open_marker_linewidth": 1.2,

    # 3D scatter defaults.
    "scatter_3d_alpha": 0.7,
    "scatter_3d_edge": "white",
    "scatter_3d_linewidth": 0.3,

    # Shared matrix defaults.
    "matrix_cmap": "coolwarm",
    "matrix_annotation_color": _matrix["annotation"],
    "matrix_value_color": _matrix["value"],
    "matrix_nan_text_color": _matrix["nan_text"],
    "x_tick_label_rotation": 60,
    "x_tick_label_ha": "right",
    "matrix_x_tick_rotation": 60,
    "matrix_y_tick_rotation": 0,
    "pvalue_cmap": "coolwarm",
    "qvalue_cmap": "viridis_r",

    # Significance annotation defaults.
    "significance_thresholds": {
        0.0001: "****",
        0.001: "***",
        0.01: "**",
        0.05: "*",
    },
    "significance_ns": "ns",

    # Overview/status colours. Integer keys are status codes from plotting.py.
    "audit_status_colors": _palette.audit_status_colors(),
    "scorecard_grade_colors": _palette.scorecard_grade_colors(),
}

_PYFLASH_STYLE = deepcopy(DEFAULT_PYFLASH_STYLE)
_MATPLOTLIB_STYLE_KEYS = {
    "line_width",
    "tick_major_width",
    "tick_major_size",
    "tick_label_size",
    "font_weight",
    "font_family",
    "labelsize",
    "labelweight",
    "title_size",
    "title_weight",
    "despine",
    "legend_frame",
    "legend_fontsize",
    "tick_direction",
    "figure_size",
    "save_bbox",
    "save_pad_inches",
    "save_dpi",
}


def _normalized_key(key):
    key = str(key)
    if key not in DEFAULT_PYFLASH_STYLE:
        valid = ", ".join(sorted(DEFAULT_PYFLASH_STYLE))
        raise KeyError(f"Unknown PyFLASH style key {key!r}. Valid keys: {valid}")
    return key


def _coerce_nested_key(key, nested_key):
    if key == "audit_status_colors":
        try:
            return int(nested_key)
        except (TypeError, ValueError):
            return nested_key
    if key == "significance_thresholds":
        try:
            return float(nested_key)
        except (TypeError, ValueError):
            return nested_key
    return nested_key


def _matplotlib_style_kwargs(style=None):
    style = _PYFLASH_STYLE if style is None else style
    return {key: style[key] for key in _MATPLOTLIB_STYLE_KEYS}


def _coerce_figure_size(value):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("figure_size must be a two-item (width, height) sequence or None")
    width, height = (float(value[0]), float(value[1]))
    if width <= 0 or height <= 0:
        raise ValueError("figure_size values must be positive")
    return (width, height)


def _normalize_orientation(value):
    value = "landscape" if value is None else str(value).strip().lower()
    valid = {"landscape", "portrait", "square", "native"}
    if value not in valid:
        raise ValueError(
            "figure_orientation must be one of "
            + ", ".join(sorted(valid))
        )
    return value


def _normalize_save_bbox(value):
    if value is None:
        return "fixed"
    value = str(value).strip().lower()
    fixed_aliases = {"fixed", "standard", "canvas", "none", "false"}
    if value in fixed_aliases:
        return "fixed"
    if value == "tight":
        return "tight"
    raise ValueError("save_bbox must be 'fixed'/'standard' or 'tight'")


def _rc_save_bbox(value):
    return "tight" if _normalize_save_bbox(value) in {"fixed", "tight"} else "standard"


def _validate_export_style(style):
    _coerce_figure_size(style.get("figure_size"))
    _normalize_orientation(style.get("figure_orientation"))
    _normalize_save_bbox(style.get("save_bbox"))
    pad = float(style.get("save_pad_inches", 0.0))
    if pad < 0:
        raise ValueError("save_pad_inches must be non-negative")
    dpi = float(style.get("save_dpi", 0.0))
    if dpi <= 0:
        raise ValueError("save_dpi must be positive")
    layout_pad = float(style.get("fixed_layout_pad", 0.0))
    if layout_pad < 0:
        raise ValueError("fixed_layout_pad must be non-negative")


def _matplotlib_rc_updates(style=None):
    kwargs = _matplotlib_style_kwargs(style)
    figure_size = _coerce_figure_size(kwargs['figure_size'])
    updates = {
        'axes.linewidth': kwargs['line_width'],
        'xtick.major.width': kwargs['tick_major_width'],
        'ytick.major.width': kwargs['tick_major_width'],
        'xtick.major.size': kwargs['tick_major_size'],
        'ytick.major.size': kwargs['tick_major_size'],
        'xtick.labelsize': kwargs['tick_label_size'],
        'ytick.labelsize': kwargs['tick_label_size'],
        'xtick.direction': kwargs['tick_direction'],
        'ytick.direction': kwargs['tick_direction'],
        'axes.labelsize': kwargs['labelsize'],
        'axes.labelweight': kwargs['labelweight'],
        'axes.titlesize': kwargs['title_size'],
        'axes.titleweight': kwargs['title_weight'],
        'axes.spines.top': not kwargs['despine'],
        'axes.spines.right': not kwargs['despine'],
        'legend.frameon': kwargs['legend_frame'],
        'legend.fontsize': kwargs['legend_fontsize'],
        'legend.title_fontsize': kwargs['legend_fontsize'],
        'font.weight': kwargs['font_weight'],
        'font.family': kwargs['font_family'],
        'savefig.dpi': kwargs['save_dpi'],
        'savefig.bbox': _rc_save_bbox(kwargs['save_bbox']),
        'savefig.pad_inches': kwargs['save_pad_inches'],
        'svg.fonttype': 'none',
        'mathtext.default': 'regular',
    }
    if figure_size is not None:
        updates['figure.figsize'] = figure_size
    return updates


def _validate_pyflash_matplotlib_style(style=None):
    import matplotlib as mpl
    style = _PYFLASH_STYLE if style is None else style
    _validate_export_style(style)
    probe = mpl.rcParams.copy()
    probe.update(_matplotlib_rc_updates(style))


def apply_pyflash_matplotlib_style(style=None):
    """Apply the current PyFLASH style's Matplotlib rcParams."""
    from PyFLASH.utils import rc_params
    rc_params(**_matplotlib_style_kwargs(style))


def get_pyflash_style(key=None):
    """Return a copy of the current PyFLASH style, or one named value."""
    if key is None:
        return deepcopy(_PYFLASH_STYLE)
    key = _normalized_key(key)
    return deepcopy(_PYFLASH_STYLE[key])


def set_pyflash_style(updates=None, **kwargs):
    """Update PyFLASH plotting style defaults and apply Matplotlib rcParams.

    Most mapping values, such as ``audit_status_colors``, are merged into the
    current mapping so callers can override one colour without restating the
    whole table. ``significance_thresholds`` replaces the full threshold table
    so callers do not inherit hidden star tiers.
    """
    merged = {}
    if updates is not None:
        if not isinstance(updates, Mapping):
            raise TypeError("updates must be a mapping or None")
        merged.update(dict(updates))
    merged.update(kwargs)

    candidate = deepcopy(_PYFLASH_STYLE)
    for raw_key, value in merged.items():
        key = _normalized_key(raw_key)
        current = candidate[key]
        if key == "significance_thresholds" and isinstance(value, Mapping):
            candidate[key] = {
                _coerce_nested_key(key, nested_key): nested_value
                for nested_key, nested_value in value.items()
            }
        elif isinstance(current, Mapping) and isinstance(value, Mapping):
            nested = dict(current)
            for nested_key, nested_value in value.items():
                nested[_coerce_nested_key(key, nested_key)] = nested_value
            candidate[key] = nested
        else:
            candidate[key] = deepcopy(value)
    _validate_pyflash_matplotlib_style(candidate)
    previous = deepcopy(_PYFLASH_STYLE)
    try:
        apply_pyflash_matplotlib_style(candidate)
    except Exception:
        apply_pyflash_matplotlib_style(previous)
        raise
    _PYFLASH_STYLE.clear()
    _PYFLASH_STYLE.update(candidate)
    return get_pyflash_style()


def reset_pyflash_style():
    """Restore the built-in PyFLASH plotting style defaults."""
    _PYFLASH_STYLE.clear()
    _PYFLASH_STYLE.update(deepcopy(DEFAULT_PYFLASH_STYLE))
    apply_pyflash_matplotlib_style()
    return get_pyflash_style()


@contextmanager
def pyflash_style_context(updates=None, **kwargs):
    """Temporarily update PyFLASH plotting style defaults."""
    previous = get_pyflash_style()
    try:
        set_pyflash_style(updates, **kwargs)
        yield get_pyflash_style()
    finally:
        _PYFLASH_STYLE.clear()
        _PYFLASH_STYLE.update(previous)
        apply_pyflash_matplotlib_style()


def pyflash_style_value(key, default=None):
    """Internal convenience accessor returning *default* if lookup fails."""
    try:
        return get_pyflash_style(key)
    except KeyError:
        return default


def pyflash_significance_annotation(p, ns=None):
    """Return significance text using the active PyFLASH style thresholds."""
    if ns is None or ns == DEFAULT_PYFLASH_STYLE["significance_ns"]:
        ns = get_pyflash_style("significance_ns")
    if ns == "p":
        ns = round(float(p), 3)
    thresholds = get_pyflash_style("significance_thresholds")
    for threshold, symbol in sorted(thresholds.items(), key=lambda item: float(item[0])):
        try:
            if float(p) < float(threshold):
                return symbol
        except (TypeError, ValueError):
            continue
    return ns


def pyflash_point_size(explicit=None, *, backend="points"):
    """Resolve a marker size for a plotting backend.

    The canonical PyFLASH style ``point_size`` is a marker diameter in points.
    Seaborn categorical plots use point-like marker units, while Matplotlib
    scatter APIs use marker area in points squared.  This helper keeps the
    public size knob linear and converts at the last moment.
    """
    value = get_pyflash_style("point_size") if explicit is None else explicit
    try:
        size = float(value)
    except (TypeError, ValueError):
        size = float(DEFAULT_PYFLASH_STYLE["point_size"])
    if size < 0:
        size = 0.0
    key = str(backend).strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"area", "scatter_area", "matplotlib", "matplotlib_scatter"}:
        return size * size
    return size


def pyflash_figure_size(explicit=None, *, orientation=None):
    """Resolve the canonical PyFLASH download figure size in inches."""
    size = _coerce_figure_size(
        get_pyflash_style("figure_size") if explicit is None else explicit
    )
    if size is None:
        return None
    orient = _normalize_orientation(
        get_pyflash_style("figure_orientation") if orientation is None else orientation
    )
    width, height = size
    if orient == "landscape" and height > width:
        width, height = height, width
    elif orient == "portrait" and width > height:
        width, height = height, width
    elif orient == "square":
        side = max(width, height)
        width, height = side, side
    return (width, height)


def apply_pyflash_figure_geometry(fig, *, figure_size=None, orientation=None,
                                  save_bbox=None):
    """Apply PyFLASH export geometry to *fig* before saving.

    Fixed-canvas exports get the canonical figure size even when the plotting
    function originally requested a custom ``figsize``. Tight exports keep the
    authored figure size and let Matplotlib grow/crop around labels.
    """
    bbox_policy = _normalize_save_bbox(
        get_pyflash_style("save_bbox") if save_bbox is None else save_bbox
    )
    if bbox_policy == "fixed":
        size = pyflash_figure_size(figure_size, orientation=orientation)
        if size is not None:
            fig.set_size_inches(size, forward=True)
        if bool(get_pyflash_style("fixed_layout")):
            try:
                # Fixed-canvas exports cannot rely on bbox_inches='tight' to
                # grow around labels. Let Matplotlib fit labels/titles/legends
                # inside the standard canvas after PyFLASH has normalised size.
                fig.set_layout_engine(None)
            except Exception:
                pass
            try:
                fig.tight_layout(pad=float(get_pyflash_style("fixed_layout_pad")))
            except Exception:
                pass
    return fig


def pyflash_savefig_kwargs(*, dpi=None, bbox_inches=None, pad_inches=None,
                           transparent=True, bbox_extra_artists=None):
    """Return savefig kwargs that honor the active PyFLASH export style."""
    bbox_policy = _normalize_save_bbox(
        get_pyflash_style("save_bbox") if bbox_inches is None else bbox_inches
    )
    resolved_dpi = get_pyflash_style("save_dpi") if dpi is None else dpi
    resolved_pad = get_pyflash_style("save_pad_inches") if pad_inches is None else pad_inches
    kwargs = {
        "dpi": resolved_dpi,
        "transparent": transparent,
        "bbox_inches": "tight" if bbox_policy in {"fixed", "tight"} else None,
    }
    if bbox_policy in {"fixed", "tight"}:
        kwargs["pad_inches"] = resolved_pad
        if bbox_extra_artists is not None:
            kwargs["bbox_extra_artists"] = bbox_extra_artists
    return kwargs


def normalize_pyflash_svg_canvas(path, *, figure_size=None, orientation=None,
                                 save_bbox=None):
    """Stamp a saved SVG with the canonical PyFLASH outer canvas size.

    ``savefig(bbox_inches='tight')`` is still used to avoid clipping labels and
    legends.  This helper then rewrites only the SVG root ``width``/``height`` so
    downloaded files have the same physical size when assembled together.
    """
    bbox_policy = _normalize_save_bbox(
        get_pyflash_style("save_bbox") if save_bbox is None else save_bbox
    )
    if bbox_policy != "fixed" or not str(path).lower().endswith(".svg"):
        return path
    size = pyflash_figure_size(figure_size, orientation=orientation)
    if size is None:
        return path
    width_pt = round(float(size[0]) * 72.0, 6)
    height_pt = round(float(size[1]) * 72.0, 6)
    import re
    try:
        text = open(path, encoding="utf-8").read()
        text = re.sub(
            r'(<svg\b[^>]*?)\swidth="[^"]+"',
            rf'\1 width="{width_pt:g}pt"',
            text,
            count=1,
        )
        text = re.sub(
            r'(<svg\b[^>]*?)\sheight="[^"]+"',
            rf'\1 height="{height_pt:g}pt"',
            text,
            count=1,
        )
        open(path, "w", encoding="utf-8").write(text)
    except Exception:
        pass
    return path
