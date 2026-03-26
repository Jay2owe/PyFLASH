"""
Shared utility functions used across the package.
"""

import os
import re
import math
import time
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt


# ── Specificity helpers (canonical versions) ──────────────────────────

def flatten_specificity_values(values):
    """Flatten nested iterables in specificity value lists."""
    out = []
    for v in values:
        if isinstance(v, (list, tuple, set, np.ndarray, pd.Series, pd.Index)):
            out.extend(list(v))
        else:
            out.append(v)
    return out


def is_specificity_queue(specificity):
    """True when specificity is a list of 2+ specificity tuples.

    Example queue: [('Time', 'WeekFour'), ('Time', 'WeekEight')]
    Not a queue:   ('Time', 'WeekFour')
    """
    return (
        isinstance(specificity, (list, tuple))
        and len(specificity) > 0
        and isinstance(specificity[0], (list, tuple))
    )


def iter_specificities(specificity):
    """Yield individual specificity tuples from a queue or single spec."""
    if is_specificity_queue(specificity):
        for item in specificity:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                yield tuple(item)
    else:
        yield specificity


def resolve_column_key(df, key):
    """Resolve column key with case-insensitive/trim matching."""
    if key in df.columns:
        return key
    target = str(key).strip().casefold()
    for col in df.columns:
        if str(col).strip().casefold() == target:
            return col
    return None


def filter_df_by_specificity(df, specificity):
    """Filter a DataFrame by a specificity tuple like ('Time', 'WeekEight')."""
    if specificity is None:
        return df
    if not isinstance(specificity, (list, tuple)) or len(specificity) < 2:
        return df
    spec_key, *raw_vals = specificity
    resolved_key = resolve_column_key(df, spec_key)
    if resolved_key is None:
        return df
    spec_vals = flatten_specificity_values(raw_vals)
    if len(spec_vals) == 0:
        return df
    col = df[resolved_key]
    if (
        pd.api.types.is_object_dtype(col)
        or pd.api.types.is_string_dtype(col)
        or pd.api.types.is_categorical_dtype(col)
    ):
        norm_col = col.astype(str).str.strip().str.casefold()
        norm_vals = {str(v).strip().casefold() for v in spec_vals}
        return df[norm_col.isin(norm_vals)]
    return df[col.isin(spec_vals)]


def specificity_path_parts(specificity):
    """Convert specificity tuple to subfolder path components."""
    if specificity is None:
        return []
    if not isinstance(specificity, (list, tuple)) or len(specificity) < 2:
        return []
    spec_key, *raw_vals = specificity
    flat_vals = flatten_specificity_values(raw_vals)
    parts = [strip_name(str(spec_key))]
    if len(flat_vals) == 1:
        parts.append(strip_name(str(flat_vals[0])))
    elif len(flat_vals) > 1:
        combined = " and ".join([str(v) for v in flat_vals])
        parts.append(strip_name(combined))
    return parts


# ── Alias system ──────────────────────────────────────────────────────

def generate_aliases(vocabulary):
    """Build shortest-unambiguous abbreviations for a set of terms.

    Strategy:
    - Terms <= 3 chars are kept as-is.
    - CamelCase terms use initials first (e.g. WeekEight → WE, WeekFour → WF).
    - Other terms start at first 2 chars.
    - Collisions are resolved by extending until unique.

    Parameters
    ----------
    vocabulary : iterable of str
        The terms to abbreviate (factor names, condition values, etc.)

    Returns
    -------
    dict : {original_term: abbreviation}
    """
    import re as _re
    terms = sorted(set(str(t) for t in vocabulary if t is not None))
    aliases = {}
    for t in terms:
        if len(t) <= 3:
            aliases[t] = t
            continue
        # Try CamelCase initials: WeekEight → WE, WeekFour → WF
        camel_parts = _re.findall(r'[A-Z][a-z]*|[a-z]+|[0-9]+', t)
        if len(camel_parts) >= 2:
            initials = ''.join(p[0].upper() for p in camel_parts)
            aliases[t] = initials
        else:
            aliases[t] = t[:2]

    # Resolve collisions by extending abbreviations
    max_iters = 50
    for _ in range(max_iters):
        seen = {}
        collisions = set()
        for term, abbr in aliases.items():
            if abbr in seen:
                collisions.add(term)
                collisions.add(seen[abbr])
            else:
                seen[abbr] = term
        if not collisions:
            break
        for term in collisions:
            cur = aliases[term]
            if len(cur) < len(term):
                aliases[term] = term[:len(cur) + 1]
    return aliases


def apply_alias(term, aliases=None):
    """Look up a term's alias. Falls back to the full term if no alias."""
    if aliases and term in aliases:
        return aliases[term]
    from IF_analysis.config import Config
    if term in Config.ALIASES:
        return Config.ALIASES[term]
    return str(term)


def build_specificity_alias(specificity, aliases=None):
    """Encode a specificity tuple as a compact filename suffix.

    Examples:
        ('Time', 'WeekEight')           → 'TM.W8'   (with aliases)
        ('Time', 'WeekFour', 'WeekEight') → 'TM.W4+W8'
        None                             → ''
    """
    if specificity is None:
        return ''
    if not isinstance(specificity, (list, tuple)) or len(specificity) < 2:
        return ''
    spec_key, *raw_vals = specificity
    flat_vals = flatten_specificity_values(raw_vals)
    key_alias = apply_alias(spec_key, aliases)
    val_aliases = [apply_alias(str(v), aliases) for v in flat_vals]
    if len(val_aliases) == 0:
        return key_alias
    return f"{key_alias}.{'+'.join(val_aliases)}"


def build_subfolder(plot_type=None, marker=None, factor=None,
                    specificity=None, aliases=None):
    """Build a save subfolder and filename suffix for a plot.

    Returns (subfolder, suffix) where:
    - subfolder: e.g. 'Iba1/Bars' or 'Matrices' (max 2 levels)
    - suffix: e.g. '--GT.W8' or '' (encoded factor + specificity)

    Single-marker plots go under marker/type/.
    Cross-marker plots go under type/.
    Factor and specificity are encoded into the filename suffix, never as folders.
    """
    parts = []
    if marker is not None:
        parts.append(strip_name(str(marker)))
    if plot_type is not None:
        parts.append(strip_name(str(plot_type)))
    subfolder = os.path.join(*parts) if parts else None

    suffix_parts = []
    if factor is not None:
        suffix_parts.append(apply_alias(str(factor), aliases))
    spec_alias = build_specificity_alias(specificity, aliases)
    if spec_alias:
        suffix_parts.append(spec_alias)

    suffix = '--' + '--'.join(suffix_parts) if suffix_parts else ''
    return subfolder, suffix


# ── String helpers ─────────────────────────────────────────────────────

def strip_name(name):
    """Sanitise a string for use as a filename."""
    for ch in ['-', "'", '<', '>', ':', '%', '³', '\n']:
        name = name.replace(ch, '')
    name = name.replace('/', 'per').replace('//', '').replace('\\', '')
    return name


def normalize_image_roi_name(name):
    """Normalize ROI/image labels to the file-style form used in image names."""
    value = str(name).strip()
    if value == "":
        return ""

    compact = re.sub(r"[\s_]+", "", value).upper()

    # Already in image-file form, e.g. LHSCN, RHSCN2
    match = re.fullmatch(r"(LH|RH)SCN(\d*)", compact)
    if match is not None:
        side, idx = match.groups()
        idx = "" if idx in {"", "1"} else idx
        return f"{side}SCN{idx}"

    # ROI zip form, e.g. SCN, SCN-1, SCN2, SCN2-1
    match = re.fullmatch(r"SCN(\d*)(?:-(\d+))?", compact)
    if match is not None:
        idx, side_suffix = match.groups()
        idx = "" if idx in {"", "1"} else idx
        side = "RH" if side_suffix == "1" else "LH"
        return f"{side}SCN{idx}"

    return compact


def normalize_animal_name(name):
    """Normalize animal identifiers for cross-source matching."""
    value = replace_week_int(str(name).strip())
    if value == "":
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def format_elapsed(seconds):
    """Format elapsed seconds as HH:MM:SS."""
    seconds = max(0.0, float(seconds))
    return time.strftime("%H:%M:%S", time.gmtime(int(round(seconds))))


class ProgressTracker:
    """Notebook/terminal-friendly progress display with timing and ETA."""

    def __init__(self, name, total, unit="item", enabled=True):
        self.name = str(name)
        self.total = max(0, int(total))
        self.unit = str(unit)
        self.enabled = bool(enabled)
        self.completed = 0
        self.sum_time = 0.0
        self.run_start = time.perf_counter()
        self.item_start = None
        self.current_item = None
        self.detail = None
        self._closed = False
        self._handle = None

        if self.enabled:
            try:
                from IPython.display import display
                self._handle = display("", display_id=True)
            except Exception:
                self._handle = None

    def start_item(self, item_name=None, detail=None):
        if self._closed:
            return
        self.item_start = time.perf_counter()
        self.current_item = None if item_name is None else str(item_name)
        self.detail = None if detail is None else str(detail)
        self._render(in_progress=True)

    def finish_item(self, item_name=None, detail=None, step=1):
        if self._closed:
            return
        if item_name is not None:
            self.current_item = str(item_name)
        if detail is not None:
            self.detail = str(detail)
        if self.item_start is not None:
            self.sum_time += (time.perf_counter() - self.item_start)
        self.item_start = None
        self.completed = min(self.total, self.completed + int(step)) if self.total > 0 else self.completed + int(step)
        self._render(in_progress=False)

    def close(self, detail=None):
        if self._closed:
            return
        if self.item_start is not None:
            self.sum_time += (time.perf_counter() - self.item_start)
            self.item_start = None
        if detail is not None:
            self.detail = str(detail)
        if self.total > 0:
            self.completed = self.total
        self._render(in_progress=False, completed=True)
        self._closed = True
        if self._handle is None and self.enabled:
            import sys
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _render(self, in_progress=False, completed=False):
        if not self.enabled:
            return

        total = max(1, self.total)
        done = min(self.completed, total)
        shown = min(done + (1 if in_progress and done < total else 0), total)
        pct = 100.0 if self.total == 0 else (shown / total) * 100.0
        bar_width = 28
        fill = bar_width if self.total == 0 else int((shown / total) * bar_width)
        bar = "█" * fill + "." * (bar_width - fill)
        elapsed = time.perf_counter() - self.run_start

        if done > 0:
            avg = (self.sum_time / done) if self.sum_time > 0 else (elapsed / done)
            remaining = max(0, total - done)
            eta_text = format_elapsed(avg * remaining)
            avg_text = f"{avg:.2f}s/{self.unit}"
        else:
            eta_text = "estimating..."
            avg_text = "n/a"

        status = self.current_item or ("Complete" if completed else "Working")
        total_label = self.total if self.total > 0 else 0
        lines = [
            f"[{self.name}] {shown}/{total_label} {self.unit}s: {status}",
            f"[{bar}] {pct:5.1f}%",
            f"Elapsed: {format_elapsed(elapsed)} | ETA: {eta_text} | Avg/{self.unit}: {avg_text}",
        ]
        if self.detail:
            lines.append(str(self.detail))
        msg = "\n".join(lines)

        if self._handle is not None:
            try:
                import html as _html
                from IPython.display import HTML
                self._handle.update(HTML(f"<pre style='margin:0'>{_html.escape(msg)}</pre>"))
            except Exception:
                self._handle.update(msg)
        else:
            import sys
            sys.stdout.write("\r\033[2K")
            sys.stdout.write(msg)
            sys.stdout.flush()


def clean_column_name(name):
    """Standardise column names from ImageJ CSV output."""
    return (name
            .replace("Colocalisation with ", "Coloc")
            .replace(" ", "")
            .replace("(micron^3)", "")
            .replace("(micron^2)", ""))


# ── DataFrame helpers ──────────────────────────────────────────────────

def add_suffix(df, columns, suffix):
    """Append a suffix to specified column names."""
    rename_map = {col: col + suffix for col in columns}
    return df.rename(columns=rename_map)


def get_columns(df, column_strings=None, regex_string=None, exclude=''):
    """
    Select column names by substring match or regex.

    Parameters
    ----------
    df : DataFrame
    column_strings : list of str, optional
        Return columns containing any of these substrings.
    regex_string : str, optional
        Return columns matching this regex.
    exclude : str or list of str
        Exclude columns containing any of these substrings.
    """
    if exclude != "" and isinstance(exclude, str):
        exclude = [exclude]
    if column_strings is not None:
        return [col for col in df.columns
                if any(s in col for s in column_strings)
                and not any(s in col for s in exclude)]
    else:
        return [col for col in df.filter(regex=regex_string).columns.tolist()
                if not any(s in col for s in exclude)]


def get_nonobject_columns(df):
    """Split columns into numeric and non-numeric (object dtype) lists."""
    numeric = [col for col in df.columns if df[col].dtype != 'object']
    other = [col for col in df.columns if df[col].dtype == 'object']
    return numeric, other


def adjust_for_volumemm(df, columns, volume_column):
    """Divide each column by the volume column."""
    for col in columns:
        volume_um_cubed = df[volume_column] * 13
        volume_mm_cubed = volume_um_cubed / 1000000000

        df[col] = df[col] / volume_mm_cubed
    return df


def add_coloc_percentages(df):
    """Add percentage colocalisation columns from count columns."""
    coloc_cols = [c for c in df.columns if 'ColocCount' in c]
    non_cols = [c for c in df.columns if 'NonColocCount' in c]

    suffixes = set()
    for col in coloc_cols + non_cols:
        suffix = col.split('_')[1]
        suffix = suffix.replace('ColocCount', '').replace('Non', '')
        suffixes.add(suffix)

    for suffix in suffixes:
        coloc_col = next((s for s in coloc_cols if suffix in s), None)
        noncoloc_col = next((s for s in non_cols if suffix in s), None)
        if coloc_col and noncoloc_col:
            total = df[coloc_col] + df[noncoloc_col]
            coloc_pct = np.where(total != 0, (df[coloc_col] / total) * 100.0, np.nan)
            df[coloc_col + "%"] = coloc_pct
            df[noncoloc_col + "%"] = 100.0 - coloc_pct
    return df


# ── Numeric helpers ────────────────────────────────────────────────────

def round_up_to_nearest_5(x):
    """Round up to the nearest 5 in the second significant figure."""
    if np.isnan(x) or x == 0:
        return 0
    order = 10 ** (np.floor(np.log10(abs(x))) - 1)
    return math.ceil(x / order / 5) * 5 * order


def flatten(xss):
    """Flatten a list of lists."""
    return [x for xs in xss for x in xs]


def remove_none(data):
    """Remove None values from a list."""
    return [x for x in data if x is not None]


def convert_microns_to_pixels(microns, pixel_size=None):
    """Convert micron measurements to pixel coordinates (or vice versa)."""
    from IF_analysis.config import Config
    if pixel_size is None:
        pixel_size = 1 / Config.PIXEL_SIZE
    return microns / pixel_size


def convert_pixels_to_microns(pixels, pixel_size=None):
    """Convert pixel measurements to microns."""
    from IF_analysis.config import Config
    if pixel_size is None:
        pixel_size = 1 / Config.PIXEL_SIZE
    return pixels * pixel_size


# ── Geometry / ROI helpers ─────────────────────────────────────────────

def trace_downward_nearest(x, y):
    """Trace a downward path through points by nearest-neighbour."""
    x = np.asarray(x)
    y = np.asarray(y)
    y_min = y.min()
    top = np.flatnonzero(y == y_min)
    cur = top[np.argmax(x[top])]

    path_idx = [cur]
    cur_x, cur_y = x[cur], y[cur]
    used = np.zeros(x.shape[0], dtype=bool)
    used[cur] = True
    max_left_slope = -2

    while True:
        mask = (y > cur_y) & (~used)
        if not np.any(mask):
            break
        dx = x[mask] - cur_x
        dy = y[mask] - cur_y
        d2 = dx * dx + dy * dy
        j = np.argmin(d2)
        nxt = np.flatnonzero(mask)[j]
        slope = (x[nxt] - cur_x) / (y[nxt] - cur_y)
        if slope < max_left_slope:
            break
        path_idx.append(nxt)
        used[nxt] = True
        cur_x, cur_y = x[nxt], y[nxt]

    if len(path_idx) <= 1:
        y_min = y.min()
        top = np.flatnonzero(y == y_min)
        cur = top[np.argmax(x[top])]
        x = np.delete(x, cur)
        y = np.delete(y, cur)
        return trace_downward_nearest(x, y)

    path_idx = np.array(path_idx, dtype=int)
    return x[path_idx], y[path_idx], path_idx


def moving_average(a, w=7):
    """Padded moving average."""
    a = np.asarray(a)
    if w < 2:
        return a
    pad = w // 2
    ap = np.pad(a, (pad, pad), mode="edge")
    return np.convolve(ap, np.ones(w) / w, mode="valid")


def points_to_polyline_distance(px, py, x_line, y_line):
    """Vectorised minimum distance from points to a polyline."""
    px = np.asarray(px, dtype=float)[:, None]
    py = np.asarray(py, dtype=float)[:, None]
    x_line = np.asarray(x_line, dtype=float)
    y_line = np.asarray(y_line, dtype=float)

    x0, y0 = x_line[:-1][None, :], y_line[:-1][None, :]
    x1, y1 = x_line[1:][None, :], y_line[1:][None, :]
    dx, dy = x1 - x0, y1 - y0
    seg_len2 = dx * dx + dy * dy
    seg_len2 = np.where(seg_len2 == 0, 1.0, seg_len2)

    t = np.clip(((px - x0) * dx + (py - y0) * dy) / seg_len2, 0.0, 1.0)
    cx, cy = x0 + t * dx, y0 + t * dy
    d2 = (px - cx) ** 2 + (py - cy) ** 2

    distances = np.sqrt(d2.min(axis=1))
    best = d2.argmin(axis=1)
    closest_points = np.array([
        cx[np.arange(len(px)), best],
        cy[np.arange(len(px)), best],
    ]).T
    return distances, closest_points


def filter_dict(my_dict, key_substring):
    """Filter a dict to keys containing a substring."""
    return {k: v for k, v in my_dict.items() if key_substring in k}


# ── Plotting helpers ───────────────────────────────────────────────────

def rc_params(line_width=3, tick_major_width=3, tick_major_size=11.5,
              tick_label_size=25, font_weight='bold', font_family='Arial',
              labelsize=22, labelweight='bold'):
    """Set matplotlib rcParams for publication-quality figures."""
    plt.rcParams.update({
        'axes.linewidth': line_width,
        'xtick.major.width': tick_major_width,
        'ytick.major.width': tick_major_width,
        'xtick.major.size': tick_major_size,
        'ytick.major.size': tick_major_size,
        'xtick.labelsize': tick_label_size,
        'ytick.labelsize': tick_label_size,
        'axes.labelsize': labelsize,
        'axes.labelweight': labelweight,
        'font.weight': font_weight,
        'font.family': font_family,
        'svg.fonttype': 'none',
    })



def rasterize_data_artists(figure, threshold=50):
    """Mark dense data artists as rasterized for faster SVG saving.

    Collections (scatter, violin, strip), patch collections, and images
    with more than *threshold* elements are rasterized.  Text, spines,
    and axes structure remain vector for crisp labels in the SVG.
    """
    for ax in figure.get_axes():
        for coll in ax.collections:
            try:
                if hasattr(coll, 'get_offsets') and len(coll.get_offsets()) > threshold:
                    coll.set_rasterized(True)
            except Exception:
                pass
        for patch in ax.patches:
            try:
                patch.set_rasterized(False)
            except Exception:
                pass


def save_fig(figure, save_path, image_name, extra_artist=None,
             pad_inches=1, subfolder=None, verbose=True,
             skip_existing=None, rasterize=True):
    """Save a figure as SVG with optional subfolder creation.

    Parameters
    ----------
    skip_existing : bool or None
        If True, skip saving when the output file already exists.
        None falls back to ``Config.SKIP_EXISTING``.
    """
    from IF_analysis.config import Config

    image_name = strip_name(image_name)
    if subfolder is not None:
        save_path = os.path.join(save_path, subfolder)
        os.makedirs(save_path, exist_ok=True)

    ext = ".svg"
    full_path = os.path.join(save_path, f"{image_name}{ext}")

    # Warn if path approaches Windows MAX_PATH limit
    if os.name == "nt" and len(full_path) > 245:
        import warnings
        warnings.warn(
            f"Path length ({len(full_path)} chars) exceeds 245. "
            f"Consider setting Config.ALIASES or shortening the base path. "
            f"Path: {full_path}",
            stacklevel=2,
        )

    use_skip = skip_existing if skip_existing is not None else Config.SKIP_EXISTING

    if Config.SAVE_MODE:
        if use_skip and os.path.isfile(full_path):
            if verbose:
                print(f"Skipped (exists): {full_path}")
            return full_path

        if rasterize:
            rasterize_data_artists(figure)

        with plt.rc_context({'svg.fonttype': 'none'}):
            figure.savefig(full_path, bbox_inches='tight',
                           bbox_extra_artists=extra_artist,
                           dpi=600, transparent=True, pad_inches=pad_inches)

    if verbose:
        print(f"Figure saved to {full_path}")
    return full_path


def _parallel_worker_wrapper(func, item):
    """Wrapper that ensures matplotlib uses the Agg backend in worker processes."""
    import matplotlib
    matplotlib.use('Agg')
    return func(item)


def parallel_map(func, items, threshold=None):
    """Run *func* over *items* in parallel when the count exceeds *threshold*.

    Uses ``joblib.Parallel`` with the ``loky`` backend when available.
    Falls back to sequential execution if joblib is not installed or
    the item count is below the threshold.

    Parameters
    ----------
    func : callable
        A function that accepts a single item and returns a result.
    items : list
        Items to map over.
    threshold : int or None
        Minimum item count to trigger parallelism.
        None falls back to ``Config.PARALLEL_THRESHOLD``.

    Returns
    -------
    dict
        Mapping of each item to its result.
    """
    from IF_analysis.config import Config
    if threshold is None:
        threshold = Config.PARALLEL_THRESHOLD
    if threshold <= 0 or len(items) < threshold:
        return {item: func(item) for item in items}
    try:
        from joblib import Parallel, delayed
        results = Parallel(n_jobs=-1, backend='loky')(
            delayed(_parallel_worker_wrapper)(func, item) for item in items
        )
        return dict(zip(items, results))
    except ImportError:
        return {item: func(item) for item in items}


def plot_parallel(*calls):
    """Run multiple plot calls concurrently using threads.

    Each argument should be a zero-argument callable, e.g.::

        plot_parallel(
            lambda: plot_mean_bars(batch1, column_strings=cols),
            lambda: plot_mean_bars(batch2, column_strings=cols),
            lambda: plot_histograms(batch1, marker='Iba1', x_attr='Volume'),
        )

    Uses threads (not processes) so batch/experiment objects don't need
    to be picklable.  Matplotlib's Agg backend + ioff() makes this safe
    as long as each call creates its own figures (which all plot_*
    functions do).

    Returns a list of results in the same order as the input calls.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import matplotlib
    matplotlib.use('Agg')

    n = len(calls)
    if n == 0:
        return []
    if n == 1:
        return [calls[0]()]

    results = [None] * n
    errors = []

    def _run(idx, fn):
        import matplotlib as _mpl
        _mpl.use('Agg')
        return idx, fn()

    with ThreadPoolExecutor(max_workers=min(n, os.cpu_count() or 4)) as pool:
        futures = {pool.submit(_run, i, fn): i for i, fn in enumerate(calls)}
        for future in as_completed(futures):
            try:
                idx, result = future.result()
                results[idx] = result
            except Exception as e:
                idx = futures[future]
                print(f"  plot_parallel: call {idx} failed — {e}")
                errors.append((idx, e))

    if errors:
        print(f"  plot_parallel: {len(errors)}/{n} calls failed")
    else:
        print(f"  plot_parallel: {n} calls completed")
    return results


def plot_legend_separately(ax, n_labels, flat=False):
    """Extract a legend from axes into its own figure."""
    label_params = ax.get_legend_handles_labels()
    figl, axl = plt.subplots()
    axl.axis(False)
    axl.legend(*label_params, loc="center", frameon=False,
               fontsize=20, ncols=n_labels if flat else 1)
    ax.legend().set_visible(False)
    return figl


# ── SCN / name helpers (used during import) ───────────────────────────

def replace_cropped(s):
    s_lower = s.lower()
    if s_lower == "cropped":
        return "1"
    if s_lower.startswith("cropped-"):
        return str(int(s_lower.split("-")[1]) + 1)
    return replace_week_int(s)


def add_scn_num(name, fullname):
    num = int(fullname.split("SCN")[-1].split("_")[0]) if fullname.split("SCN")[-1].split("_")[0] != '' else 0
    return name[:-1] + str(int(name[-1]) + num)


def replace_week_int(s):
    value = str(s)

    def _repl(match):
        num = match.group(1)
        word_map = {"2": "Two", "4": "Four", "8": "Eight"}
        return f"Week{word_map.get(num, num)}"

    return re.sub(r"(?i)week\s*([248])(?!\d)", _repl, value)
