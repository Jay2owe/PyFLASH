"""
Figure-producing statistical analyses that complement PyFLASH.plotting.

These live in their own module (rather than the large ``plotting.py``) so they
can be added without colliding with concurrent work on that file.  They follow
the same conventions as the core plot functions — take a batch-like object
exposing ``.summary`` (animal-level), respect ``specificity`` filters, build a
matplotlib figure, and optionally save via ``PyFLASH.utils.save_fig`` — but are
not yet registered in ``spec.PLOT_REGISTRY`` (do that once plotting.py settles,
so the YAML spec runner and the /pyflash discover path pick them up).

Functions
---------
- plot_power_curve     : statistical power vs sample size (statsmodels)
- plot_marker_pca      : PCA biplot of animal-level marker profiles (scikit-learn)
- plot_timecourse      : growth-curve fits across an ordered time factor (lmfit)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from PyFLASH._logging import logger as _log
from PyFLASH.config import apply_matplotlib_fast_path
from PyFLASH.utils import save_fig, get_columns, filter_df_by_specificity, strip_name

apply_matplotlib_fast_path()


# ── shared helpers ───────────────────────────────────────────────────
def _resolve_save_path(batch, save_path):
    if save_path is not None:
        return save_path
    for attr in ("fig_path", "data_path"):
        p = getattr(batch, attr, None)
        if p:
            return p
    return "."


def _categorical_colors(values, palette=None):
    """Map unique categorical values to colors (provided palette or tab10)."""
    uniques = list(dict.fromkeys(values))
    if isinstance(palette, dict):
        return {v: palette.get(v, "grey") for v in uniques}
    cmap = plt.get_cmap("tab10")
    return {v: cmap(i % 10) for i, v in enumerate(uniques)}


def _numeric_feature_matrix(df, columns):
    """Coerce selected columns to a numeric matrix, dropping rows with any NaN."""
    num = df[columns].apply(pd.to_numeric, errors="coerce")
    num = num.replace([np.inf, -np.inf], np.nan)
    keep = num.notna().all(axis=1)
    return num.loc[keep], keep


# ── power analysis ───────────────────────────────────────────────────
def plot_power_curve(effect_sizes=(0.2, 0.5, 0.8), n_range=(2, 30), alpha=0.05,
                     observed=None, observed_n=None, target_powers=(0.8, 0.9),
                     test="t-test", k_groups=2, title=None,
                     save=False, save_path=None, save_name="power_curve",
                     dpi=600, return_data=False):
    """Plot statistical power vs sample size per group.

    One curve per entry in ``effect_sizes`` (plus the ``observed`` effect if
    given).  Vertical line at ``observed_n``; horizontal guides at
    ``target_powers``.  ``test='t-test'`` (two groups) or ``'anova'``
    (``k_groups`` groups).  Returns the figure (or ``(fig, DataFrame)``).
    """
    if str(test).lower() in ("anova", "f", "f-test"):
        from statsmodels.stats.power import FTestAnovaPower
        analysis = FTestAnovaPower()

        def _power(es, n):
            return float(analysis.power(effect_size=es, nobs=n * k_groups,
                                        alpha=alpha, k_groups=k_groups))
        xlabel = "n per group"
    else:
        from statsmodels.stats.power import TTestIndPower
        analysis = TTestIndPower()

        def _power(es, n):
            return float(analysis.power(effect_size=es, nobs1=n, alpha=alpha, ratio=1.0))
        xlabel = "n per group"

    ns = np.arange(int(n_range[0]), int(n_range[1]) + 1)
    effects = list(effect_sizes)
    if observed is not None and np.isfinite(observed):
        effects = effects + [abs(float(observed))]

    fig, ax = plt.subplots(figsize=(8, 6), layout="constrained")
    rows = []
    for es in effects:
        powers = [_power(abs(es), int(n)) for n in ns]
        is_obs = observed is not None and np.isclose(es, abs(float(observed)))
        label = f"observed d={abs(es):.2f}" if is_obs else f"d={es:.2f}"
        ax.plot(ns, powers, lw=2.5 if is_obs else 2,
                ls="-" if not is_obs else "--",
                color="black" if is_obs else None, label=label)
        for n, p in zip(ns, powers):
            rows.append({"effect_size": abs(es), "n_per_group": int(n), "power": p, "observed": is_obs})

    for tp in target_powers:
        ax.axhline(tp, color="grey", lw=1, ls=":")
        ax.text(ns[-1], tp, f" {int(tp * 100)}%", va="center", fontsize=10, color="grey")
    if observed_n is not None:
        ax.axvline(observed_n, color="crimson", lw=1.5, ls="-.")
        ax.text(observed_n, 0.02, f" n={observed_n}", color="crimson", fontsize=10, rotation=90, va="bottom")

    ax.set_xlabel(xlabel)
    ax.set_ylabel("Power")
    ax.set_ylim(0, 1.02)
    ax.set_title(title or f"Power analysis ({test}, alpha={alpha})")
    ax.legend(frameon=False)

    if save:
        save_fig(fig, save_path or ".", strip_name(save_name), verbose=False)
    data = pd.DataFrame(rows)
    return (fig, data) if return_data else fig


# ── PCA of marker profiles ───────────────────────────────────────────
def plot_marker_pca(batch, columns=None, column_strings=None, regex_string=None,
                    exclude='', hue_column="Condition", specificity=None,
                    standardize=True, n_components=2, annotate_loadings=True,
                    max_loadings=12, palette=None, title=None,
                    save=False, save_path=None, save_name=None, dpi=600,
                    return_data=False):
    """PCA biplot of animal-level marker profiles, coloured by ``hue_column``.

    Builds the feature matrix from ``batch.summary`` (one row per animal),
    selecting columns by explicit list or ``column_strings``/``regex_string``/
    ``exclude`` (same semantics as plotting.get_columns).  Standardises per
    column by default (so large-magnitude IntDen columns do not dominate).
    Returns the figure (or ``(fig, {scores, loadings, explained_variance})``).
    """
    from sklearn.decomposition import PCA

    summary = getattr(batch, "summary", None)
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        raise ValueError("batch.summary must be a non-empty DataFrame.")
    df = filter_df_by_specificity(summary, specificity)

    if columns is not None:
        feat_cols = [c for c in columns if c in df.columns]
    else:
        feat_cols = get_columns(df, column_strings=column_strings,
                                regex_string=regex_string, exclude=exclude)
    feat_cols = [c for c in feat_cols if c != hue_column]
    if len(feat_cols) < 2:
        raise ValueError("Need at least 2 numeric feature columns for PCA.")

    X, keep = _numeric_feature_matrix(df, feat_cols)
    if len(X) < 3:
        raise ValueError("Need at least 3 complete rows (animals) for PCA.")
    hue = df.loc[keep, hue_column].astype(str) if hue_column in df.columns else pd.Series(["all"] * len(X), index=X.index)

    Xv = X.to_numpy(dtype=float)
    if standardize:
        mu = Xv.mean(axis=0)
        sd = Xv.std(axis=0, ddof=0)
        sd[sd == 0] = 1.0
        Xv = (Xv - mu) / sd

    n_comp = int(min(n_components, Xv.shape[1], Xv.shape[0] - 1))
    n_comp = max(2, n_comp) if Xv.shape[1] >= 2 and Xv.shape[0] > 2 else 2
    pca = PCA(n_components=min(n_comp, Xv.shape[1]))
    scores = pca.fit_transform(Xv)
    evr = pca.explained_variance_ratio_

    fig, ax = plt.subplots(figsize=(8, 7), layout="constrained")
    color_map = _categorical_colors(list(hue.unique()), palette)
    for level in hue.unique():
        m = (hue == level).to_numpy()
        ax.scatter(scores[m, 0], scores[m, 1], s=70, alpha=0.85,
                   color=color_map[level], edgecolor="black", linewidth=0.5, label=str(level))

    if annotate_loadings:
        load = pca.components_[:2].T  # (features, 2)
        scale = 0.9 * np.abs(scores[:, :2]).max() / (np.abs(load).max() or 1.0)
        order = np.argsort(-(load[:, 0] ** 2 + load[:, 1] ** 2))[:max_loadings]
        for i in order:
            ax.arrow(0, 0, load[i, 0] * scale, load[i, 1] * scale,
                     color="grey", alpha=0.6, head_width=scale * 0.02, length_includes_head=True)
            ax.text(load[i, 0] * scale * 1.08, load[i, 1] * scale * 1.08,
                    str(feat_cols[i]), fontsize=8, color="dimgrey", ha="center", va="center")

    ax.axhline(0, color="lightgrey", lw=0.8, zorder=0)
    ax.axvline(0, color="lightgrey", lw=0.8, zorder=0)
    ax.set_xlabel(f"PC1 ({evr[0] * 100:.1f}%)")
    ax.set_ylabel(f"PC2 ({evr[1] * 100:.1f}%)")
    ax.set_title(title or f"Marker profile PCA (n={len(X)} animals)")
    ax.legend(frameon=False, title=hue_column)

    if save:
        save_fig(fig, _resolve_save_path(batch, save_path),
                 strip_name(save_name or "marker_pca"), verbose=False)

    if return_data:
        scores_df = pd.DataFrame(scores[:, :2], columns=["PC1", "PC2"], index=X.index)
        scores_df[hue_column] = hue
        loadings_df = pd.DataFrame(pca.components_[:2].T, index=feat_cols, columns=["PC1", "PC2"])
        return fig, {"scores": scores_df, "loadings": loadings_df, "explained_variance": evr}
    return fig


# ── timecourse growth curves ─────────────────────────────────────────
def plot_timecourse(batch, column, time_col="Time", group_col="Genotype",
                    model="auto", specificity=None, time_map=None,
                    animal_col="AnimalName", palette=None, show_points=True,
                    title=None, save=False, save_path=None, save_name=None,
                    dpi=600, return_data=False):
    """Fit and plot a growth curve per group across an ordered time factor.

    Fits :func:`PyFLASH.stats_extra.fit_growth_curve` to the animal-level points
    of each ``group_col`` level (x = numeric time, y = ``column``), overlays the
    fitted curve and the per-timepoint mean +/- SEM.  ``time_map`` maps a
    categorical time factor to numbers (e.g. ``{'WeekTwo': 2, 'WeekEight': 8}``).
    Returns the figure (or ``(fig, {group: fit_dict})``).
    """
    from PyFLASH.stats_extra import _resolve_numeric_time, fit_growth_curve

    summary = getattr(batch, "summary", None)
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        raise ValueError("batch.summary must be a non-empty DataFrame.")
    df = filter_df_by_specificity(summary, specificity).copy()
    for needed in (column, time_col):
        if needed not in df.columns:
            raise ValueError(f"column '{needed}' not found in batch.summary.")
    df["_t"] = _resolve_numeric_time(df[time_col], time_map)
    df["_v"] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["_t", "_v"])
    if df.empty:
        raise ValueError("No numeric (time, value) rows after parsing; pass time_map?")

    if group_col in df.columns:
        groups = list(dict.fromkeys(df[group_col].astype(str)))
    else:
        df[group_col] = "all"
        groups = ["all"]

    fig, ax = plt.subplots(figsize=(8, 6), layout="constrained")
    color_map = _categorical_colors(groups, palette)
    fits = {}
    for grp in groups:
        sub = df[df[group_col].astype(str) == grp]
        x = sub["_t"].to_numpy(float)
        y = sub["_v"].to_numpy(float)
        color = color_map[grp]
        if show_points:
            ax.scatter(x, y, s=30, alpha=0.4, color=color, edgecolor="none")
        # per-timepoint mean +/- SEM
        agg = sub.groupby("_t")["_v"].agg(["mean", "sem", "count"]).reset_index()
        ax.errorbar(agg["_t"], agg["mean"], yerr=agg["sem"].fillna(0.0),
                    fmt="o", color=color, capsize=4, lw=2, markersize=7, zorder=3)
        # fit
        try:
            fit = fit_growth_curve(x, y, model=model)
            xs = np.linspace(float(np.min(x)), float(np.max(x)), 100)
            ax.plot(xs, fit["predict"](xs), color=color, lw=2.5,
                    label=f"{grp} ({fit['model']}, R^2={fit['r_squared']:.2f})")
            fits[grp] = fit
        except Exception as e:
            _log.hint(f"[plot_timecourse] fit failed for group '{grp}': {e}")
            ax.plot([], [], color=color, label=f"{grp} (fit failed)")
            fits[grp] = None

    ax.set_xlabel(time_col)
    ax.set_ylabel(str(column))
    ax.set_title(title or f"{column} time-course")
    ax.legend(frameon=False, title=group_col)

    if save:
        save_fig(fig, _resolve_save_path(batch, save_path),
                 strip_name(save_name or f"{column}_timecourse"), verbose=False)
    return (fig, fits) if return_data else fig
