"""
Structured results reporting for PyFLASH plots (the "describe" layer).

PyFLASH plotting functions compute rich descriptive *and* inferential statistics
(per-group n/mean/sd, test name, p-values, effect sizes, correlation r/p) but
historically returned only a matplotlib ``Figure`` — the numbers were drawn onto
the image or written to a CSV and then discarded by the caller. That makes an AI
agent reconstruct results by OCR-ing a PNG, which is lossy and unverifiable.

This module stops throwing those numbers away. It provides a lightweight,
in-process **collector** that plotting/stats code pushes structured *result
records* into while a plot runs, plus helpers to JSON-coerce values and render a
deterministic markdown digest. The design has three tiers:

  Tier 1 — the structured JSON record (the canonical source of truth). One per
           metric/comparison/correlation, with provenance + descriptive +
           inferential stats. Built here, persisted by the runner.
  Tier 2 — a deterministic markdown digest rendered mechanically from Tier 1
           (``render_digest``). Cheap for an agent to read; cannot hallucinate
           numbers because it is templated from the record.
  Tier 3 — agent narrative / cross-run storytelling, generated at read time from
           the accumulated Tier-1 store. Not produced here.

The collector is **opt-in and inert by default**: nothing on the core plotting
path changes unless a caller has armed it with ``start()``. ``emit()`` is fully
guarded and never raises into a plot. The /pyflash runner arms it around a run,
then calls ``collect()`` to retrieve the records and disarm.

This module is deliberately dependency-light (only the stdlib at import time;
numpy/pandas are imported lazily) so ``import PyFLASH.report`` is cheap and safe
from anywhere, including ``PyFLASH.stats`` and ``PyFLASH.plotting``.
"""

from __future__ import annotations

import math

SCHEMA_VERSION = "1.0"

# Bound how much of a returned DataFrame we serialise inline, so a pipeline that
# returns a 10k-row correlation table can't blow up the result JSON.
MAX_DF_ROWS = 200


# ── lazy heavy imports ───────────────────────────────────────────────────────
def _np():
    try:
        import numpy as np
        return np
    except Exception:  # pragma: no cover - numpy is a hard dep in practice
        return None


def _pd():
    try:
        import pandas as pd
        return pd
    except Exception:  # pragma: no cover - pandas is a hard dep in practice
        return None


# ── collector state ──────────────────────────────────────────────────────────
# Single-process, single-threaded use (the runner's worker handles one request
# at a time), so a module global is sufficient and avoids thread-local surprises.
_STATE = {"active": False, "records": []}


def start():
    """Arm the collector for a single run, discarding any prior records."""
    _STATE["active"] = True
    _STATE["records"] = []


def is_active() -> bool:
    """True when a caller has armed the collector (plotting code checks this)."""
    return bool(_STATE["active"])


def emit(record) -> None:
    """Append a structured result record if the collector is armed.

    Fully guarded: this is called from inside plotting/stats code and must never
    raise. A malformed record (anything that doesn't coerce to a JSON dict) is
    silently dropped rather than retained — downstream consumers (render_digest,
    the index ledger) assume every record is a dict.
    """
    if not _STATE["active"]:
        return
    try:
        coerced = coerce(record)
    except Exception:
        return
    if isinstance(coerced, dict):
        _STATE["records"].append(coerced)


def collect():
    """Return the collected records and disarm the collector."""
    records = _STATE["records"]
    _STATE["active"] = False
    _STATE["records"] = []
    return records


# ── JSON coercion ────────────────────────────────────────────────────────────
def _is_bad_float(x) -> bool:
    return isinstance(x, float) and (math.isnan(x) or math.isinf(x))


def coerce(obj, _depth: int = 0):
    """Recursively convert numpy/pandas/set/tuple values to JSON-native types.

    NaN/Inf become ``None`` (valid JSON). DataFrames become a bounded summary
    (shape + columns + first ``MAX_DF_ROWS`` rows). Anything unrecognised falls
    back to ``str``. Depth-bounded so a cyclic/huge structure can't run away.
    """
    if _depth > 16:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return None if _is_bad_float(obj) else obj

    np = _np()
    if np is not None:
        if isinstance(obj, np.generic):
            return coerce(obj.item(), _depth + 1)
        if isinstance(obj, np.ndarray):
            return [coerce(v, _depth + 1) for v in obj.tolist()]

    pd = _pd()
    if pd is not None:
        if isinstance(obj, pd.DataFrame):
            return _coerce_dataframe(obj, _depth)
        if isinstance(obj, pd.Series):
            return {str(k): coerce(v, _depth + 1) for k, v in obj.to_dict().items()}
        if isinstance(obj, pd.Index):
            return [coerce(v, _depth + 1) for v in obj.tolist()]

    if isinstance(obj, dict):
        return {str(k): coerce(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [coerce(v, _depth + 1) for v in obj]

    try:
        return str(obj)
    except Exception:
        return None


def _coerce_dataframe(df, _depth: int = 0):
    n = int(df.shape[0])
    out = {
        "_dataframe": True,
        "shape": [n, int(df.shape[1])],
        "columns": [str(c) for c in df.columns],
    }
    head = df.head(MAX_DF_ROWS)
    out["records"] = [
        {str(k): coerce(v, _depth + 1) for k, v in row.items()}
        for row in head.to_dict(orient="records")
    ]
    if n > MAX_DF_ROWS:
        out["truncated"] = True
        out["omitted_rows"] = n - MAX_DF_ROWS
    return out


# ── scalar helpers ───────────────────────────────────────────────────────────
def _f(x):
    """Coerce to a finite float, or None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(v) or math.isinf(v)) else v


def _i(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _s(x):
    if x is None:
        return None
    s = str(x)
    return s if s != "" else None


def _fmt_p(p):
    p = _f(p)
    if p is None:
        return "n/a"
    if p < 0.0001:
        return f"{p:.2e}"
    return f"{p:.4g}"


def significance_stars(p):
    """Star annotation for a p-value (mirrors stats.get_annotation thresholds)."""
    p = _f(p)
    if p is None:
        return "ns"
    if p < 0.0001:
        return "****"
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


# ── descriptive stats ────────────────────────────────────────────────────────
def describe_group(name, values) -> dict:
    """Descriptive statistics for one group's numeric values.

    ``values`` may be a pandas Series, numpy array, or iterable; non-numeric and
    NaN entries are dropped. This is the "what the eye reads off the chart" layer
    — the means and directions a p-value alone can't convey.
    """
    arr = []
    for v in list(values) if values is not None else []:
        fv = _f(v)
        if fv is not None:
            arr.append(fv)
    n = len(arr)
    rec = {"name": _s(name) or "group", "n": n}
    if n == 0:
        return rec
    np = _np()
    if np is not None:
        a = np.asarray(arr, dtype=float)
        sd = float(np.std(a, ddof=1)) if n > 1 else 0.0
        rec.update(
            mean=float(np.mean(a)),
            sd=sd,
            sem=(sd / math.sqrt(n)) if n > 1 else 0.0,
            median=float(np.median(a)),
            min=float(np.min(a)),
            max=float(np.max(a)),
            q25=float(np.percentile(a, 25)),
            q75=float(np.percentile(a, 75)),
        )
    else:  # pragma: no cover - numpy effectively always present
        mean = sum(arr) / n
        var = sum((x - mean) ** 2 for x in arr) / (n - 1) if n > 1 else 0.0
        sd = math.sqrt(var)
        rec.update(mean=mean, sd=sd, sem=(sd / math.sqrt(n)) if n > 1 else 0.0,
                   median=sorted(arr)[n // 2], min=min(arr), max=max(arr))
    return rec


def _parse_comparison(comp):
    """'1-2' -> (0, 1) zero-based indices; tolerant of junk -> (None, None)."""
    try:
        a, b = str(comp).split("-")
        return int(a) - 1, int(b) - 1
    except Exception:
        return None, None


def _direction(groups):
    """Plain-language direction summary from group means."""
    ranked = [g for g in groups if g.get("mean") is not None]
    if len(ranked) < 2:
        return None
    ranked.sort(key=lambda g: g["mean"])
    lo, hi = ranked[0], ranked[-1]
    if len(ranked) == 2:
        a, b = groups[0], groups[1]
        am, bm = a.get("mean"), b.get("mean")
        if am is None or bm is None:
            return None
        if abs(am - bm) < 1e-12:
            return f"{a['name']} ≈ {b['name']}"
        rel = ">" if am > bm else "<"
        return f"{a['name']} {rel} {b['name']}"
    return f"highest: {hi['name']} ({hi['mean']:.4g}); lowest: {lo['name']} ({lo['mean']:.4g})"


# ── record builders ──────────────────────────────────────────────────────────
def build_comparison_record(
    *,
    metric,
    group_names,
    group_values,
    test=None,
    post_hoc=None,
    overall=None,
    comparisons=None,
    pairwise_pvalues=None,
    effect_strings=None,
    raw_stats=None,
    normal=None,
    factor_terms=None,
):
    """Build a Tier-1 record for a group-comparison plot (bars/box/etc.).

    Captures the descriptive layer (per-group n/mean/sd from ``group_values``)
    *and* the inferential layer (test, overall statistic/p, pairwise p-values,
    effect sizes), plus a plain-language ``direction`` and ``headline`` so an
    agent can answer "is X higher in WT?" without seeing the figure.
    """
    names = [_s(n) or f"G{i + 1}" for i, n in enumerate(group_names or [])]
    values = list(group_values or [])
    if len(names) < len(values):
        names += [f"G{i + 1}" for i in range(len(names), len(values))]
    groups = [describe_group(names[i], values[i]) for i in range(len(values))]

    record = {
        "kind": "group_comparison",
        "metric": _s(metric) or "metric",
        "unit": "animal",
        "n_groups": len(groups),
        "groups": groups,
        "test": {"name": _s(test)},
        "post_hoc": _s(post_hoc),
        "normal": (None if normal is None else bool(normal)),
    }
    if overall is not None:
        try:
            stat, p = overall
        except (TypeError, ValueError):
            stat, p = None, None
        if isinstance(p, (list, tuple)):
            # Multi-term overall (e.g. Two-Way ANOVA: factor1/factor2/interaction).
            # Surface each term with its name so the digest/index isn't blank.
            # NB: use a distinct local — do NOT rebind `names`, which is the group
            # label list the pairwise mapping below still depends on.
            stats_list = list(stat) if isinstance(stat, (list, tuple)) else [stat] * len(p)
            term_names = factor_terms or []
            terms = []
            for i, pv in enumerate(p):
                term = {"name": (str(term_names[i]) if i < len(term_names) else f"term{i + 1}"),
                        "p": _f(pv)}
                if i < len(stats_list):
                    term["statistic"] = _f(stats_list[i])
                terms.append(term)
            record["test"]["terms"] = terms
        else:
            record["test"]["statistic"] = _f(stat)
            record["test"]["p"] = _f(p)

    pairwise = []
    if comparisons:
        pvals = pairwise_pvalues
        if pvals is None:
            pvals = []
        elif not isinstance(pvals, (list, tuple)):
            pvals = [pvals]
        for idx, comp in enumerate(comparisons):
            ai, bi = _parse_comparison(comp)
            entry = {"comparison": str(comp)}
            if ai is not None and 0 <= ai < len(names):
                entry["a"] = names[ai]
            if bi is not None and 0 <= bi < len(names):
                entry["b"] = names[bi]
            if idx < len(pvals):
                entry["p"] = _f(pvals[idx])
                entry["sig"] = significance_stars(entry["p"])
            pairwise.append(entry)
    record["pairwise"] = pairwise

    record["direction"] = _direction(groups)
    if effect_strings:
        record["effect_sizes"] = [str(s) for s in effect_strings]
    if raw_stats is not None:
        record["raw_stats"] = coerce(raw_stats)
    record["headline"] = _comparison_headline(record)
    return coerce(record)


def _comparison_headline(record) -> str:
    metric = record.get("metric", "metric")
    test = record.get("test") or {}
    parts = [f"{metric}: {test.get('name') or 'comparison'}"]
    terms = test.get("terms")
    if terms:
        tparts = [f"{t.get('name')} p={_fmt_p(t['p'])} ({significance_stars(t['p'])})"
                  for t in terms if t.get("p") is not None]
        if tparts:
            parts.append("; ".join(tparts))
    else:
        p = test.get("p")
        if p is not None:
            parts.append(f"p={_fmt_p(p)} ({significance_stars(p)})")
    direction = record.get("direction")
    if direction:
        parts.append(direction)
    return "; ".join(parts)


def build_correlation_record(*, x, y, group=None, n=None, r=None, p=None, method=None):
    """Build a Tier-1 record for a single regression/correlation pair."""
    record = {
        "kind": "correlation",
        "x": _s(x),
        "y": _s(y),
        "group": _s(group),
        "n": _i(n),
        "r": _f(r),
        "p": _f(p),
        "method": _s(method),
    }
    record["headline"] = _correlation_headline(record)
    return coerce(record)


def _correlation_headline(record) -> str:
    x, y = record.get("x"), record.get("y")
    grp = record.get("group")
    grp_txt = f" [{grp}]" if grp else ""
    r, p = record.get("r"), record.get("p")
    r_txt = f"r={r:.3g}" if r is not None else "r=n/a"
    p_txt = f"p={_fmt_p(p)} ({significance_stars(p)})" if p is not None else ""
    tail = f"; {p_txt}" if p_txt else ""
    return f"{y} vs {x}{grp_txt}: {r_txt}{tail}"


def summarize_return(ret):
    """Coerce a plot/pipeline return value into a bounded JSON summary, or None.

    Plain plot functions return a matplotlib Figure (no data) -> None. Pipeline
    callables (``correlation``/``adjusted_correlation``) return a rich dict/manifest
    possibly containing DataFrames -> a bounded coerced dict. Lists (e.g. run_spec)
    and other types -> None.
    """
    if ret is None:
        return None
    mod = (getattr(type(ret), "__module__", "") or "")
    if mod.startswith("matplotlib"):
        return None
    if isinstance(ret, dict):
        return coerce(ret)
    return None


# ── deterministic markdown digest (Tier 2) ───────────────────────────────────
def render_digest(summary) -> str:
    """Render a Tier-1 results summary as deterministic, agent-readable markdown.

    Mechanical (no LLM): every number comes straight from the record, so the
    digest can be trusted as ground truth and an agent never has to OCR a PNG.
    """
    lines = []
    plot = summary.get("plot", "plot")
    batch = summary.get("batch", "?")
    lines.append(f"# Results — {plot} ({batch})")
    ts = summary.get("timestamp")
    rid = summary.get("run_id")
    meta = []
    if rid:
        meta.append(f"run `{rid}`")
    if ts:
        meta.append(ts)
    if meta:
        lines.append("_" + " · ".join(meta) + "_")
    params = summary.get("params")
    if params:
        lines.append("")
        lines.append(f"**Params:** `{_compact_params(params)}`")

    # Defensive: only dict records carry the contract; ignore any stray non-dicts.
    metrics = [m for m in (summary.get("metrics") or []) if isinstance(m, dict)]
    comparisons = [m for m in metrics if m.get("kind") == "group_comparison"]
    correlations = [m for m in metrics if m.get("kind") == "correlation"]

    if comparisons:
        lines.append("")
        lines.append("## Group comparisons")
        for m in comparisons:
            lines.extend(_digest_comparison(m))
    if correlations:
        lines.append("")
        lines.append("## Correlations")
        for m in correlations:
            lines.append(f"- {m.get('headline', '')}"
                         + (f"  (n={m['n']})" if m.get("n") is not None else ""))

    other = [m for m in metrics if m.get("kind") not in ("group_comparison", "correlation")]
    if other:
        lines.append("")
        lines.append("## Other records")
        for m in other:
            lines.append(f"- {m.get('headline') or m.get('kind') or 'record'}")

    pipeline = summary.get("pipeline")
    if isinstance(pipeline, dict):
        lines.append("")
        lines.append("## Pipeline summary")
        lines.extend(_digest_pipeline(pipeline))

    if not metrics and not pipeline:
        lines.append("")
        lines.append("_No structured statistics were captured for this run "
                     "(the plot may not compute group tests or correlations)._")

    return "\n".join(lines) + "\n"


def _digest_comparison(m):
    out = [f"### {m.get('metric', 'metric')}"]
    out.append(f"- {m.get('headline', '')}")
    for g in m.get("groups", []):
        if g.get("mean") is not None:
            out.append(
                f"  - **{g['name']}**: n={g.get('n')}, "
                f"mean={g['mean']:.4g} ± {g.get('sd', 0):.3g} (SD), "
                f"median={g.get('median'):.4g}"
            )
        else:
            out.append(f"  - **{g['name']}**: n={g.get('n')} (no numeric values)")
    sig = [p for p in m.get("pairwise", []) if (p.get("p") is not None and p["p"] < 0.05)]
    if sig:
        pairs = ", ".join(
            f"{p.get('a', '?')} vs {p.get('b', '?')} (p={_fmt_p(p['p'])} {p.get('sig', '')})"
            for p in sig
        )
        out.append(f"  - significant pairs: {pairs}")
    for es in m.get("effect_sizes", [])[:6]:
        if not str(es).lower().startswith("effect size"):
            out.append(f"  - effect size: {es}")
    return out


def _digest_pipeline(p):
    out = []
    for key in ("run_label", "n_pairs", "n_selected", "n_regressions", "tests", "gate", "alpha"):
        if key in p and p[key] is not None:
            out.append(f"- **{key}**: {p[key]}")
    groups = p.get("groups")
    if isinstance(groups, list) and groups:
        out.append("- groups:")
        for g in groups[:12]:
            if isinstance(g, dict):
                out.append(f"  - {g.get('group', '?')}: "
                           f"n_rows={g.get('n_rows')}, n_selected={g.get('n_selected')}")
    sel = p.get("selected_pairs")
    if isinstance(sel, list) and sel:
        out.append(f"- top selected pairs ({min(len(sel), 8)} of {len(sel)}):")
        for row in sel[:8]:
            if isinstance(row, dict):
                x, y = row.get("x"), row.get("y")
                r = row.get("r") if "r" in row else row.get("median_abs_r")
                out.append(f"  - {y} vs {x}" + (f" (r≈{r:.3g})" if isinstance(r, (int, float)) else ""))
    return out


def _compact_params(params):
    if not isinstance(params, dict):
        return str(params)
    bits = []
    for k, v in params.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:57] + "..."
        bits.append(f"{k}={sv}")
    return ", ".join(bits)
