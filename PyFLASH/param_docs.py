"""What each plotting argument means, in units, written down rather than guessed.

A function signature can say that ``alpha`` defaults to ``0.05``. It cannot say
that it is a significance threshold rather than an opacity, that lowering it
makes the test stricter, or that ``exclude`` is the legacy spelling of
``data_col_exclude`` and the two must never both be passed. That knowledge is
what an agent needs before it calls anything, and this is where it lives.

Two layers, on purpose:

**Declared** — the shared vocabulary below. Sixty-odd names that recur across
the registry (``filter_by`` appears in forty of the forty-six entries), each
documented once and reused. These carry the units and the warnings.

**Derived** — everything else, read off the live signature by
:func:`derive`. Four hundred-odd single-use arguments whose type and default a
signature genuinely does state, and hand-copying them would create a second
list to keep in step with the first.

The result is that ``describe`` answers for every argument, the hand-written
part stays small enough to be true, and a new argument appears in the reference
the moment it appears in the signature.

Plain data on purpose: no imports from the agent layer, so ``PyFLASH`` keeps
standing on its own and this stays readable from a notebook. The ``/pyflash``
runner turns these into the kit's ``ParamDoc`` objects.
"""

from __future__ import annotations

import inspect


__all__ = ["PARAM_DOCS", "ALIAS_OF", "doc_for", "derive", "describe_all"]


def _p(type_, description, units="-", required=False, default=None):
    return {
        "type": type_,
        "units": units,
        "required": required,
        "default": default,
        "description": description,
    }


#: The shared vocabulary. Units are given wherever the value is a measurement;
#: "-" means the argument is a name, a flag or a selection rather than a
#: quantity. Descriptions say what changes if you get it wrong, because that is
#: the part a caller cannot work out from the name.
PARAM_DOCS = {
    # ── what to plot from ─────────────────────────────────────────────────
    "experiment": _p(
        "batch | experiment",
        "The loaded batch or experiment object holding the summary table. "
        "Supplied by the runner from the requested pickle; never passed by hand.",
        required=True,
    ),
    "dataframe_kwargs": _p(
        "dict",
        "Extra keyword arguments forwarded to the dataframe builder, for the "
        "rare call that needs to reshape the summary table before plotting.",
    ),
    # ── which columns ─────────────────────────────────────────────────────
    "data_cols": _p(
        "list[str]",
        "Exact column names to plot, in order. The precise form: use it when "
        "you know the columns. Preferred over the legacy `filtered_columns`.",
    ),
    "filtered_columns": _p(
        "list[str]",
        "Legacy spelling of `data_cols`. Still accepted; do not emit it in new "
        "calls. Passing both with different values is refused rather than "
        "silently resolved.",
    ),
    "data_col_contains": _p(
        "list[str]",
        "Substrings selecting columns: any column containing one of these is "
        "included. The usual way to say 'the Iba1 measures' without listing "
        "them. Preferred over the legacy `column_strings`.",
    ),
    "column_strings": _p(
        "list[str]",
        "Legacy spelling of `data_col_contains`.",
    ),
    "data_col_regex": _p(
        "str",
        "Regular expression selecting columns. Use when a substring list would "
        "be long or ambiguous.",
    ),
    "regex_string": _p("str", "Legacy spelling of `data_col_regex`."),
    "data_col_exclude": _p(
        "str | list[str]",
        "Substrings removing columns from the selection, applied after the "
        "include step. The usual companion to a broad `data_col_contains`.",
    ),
    "exclude": _p(
        "str | list[str]",
        "Legacy spelling of `data_col_exclude`. Note the default is an empty "
        "string, not None: passing None is not the same as omitting it.",
        default="",
    ),
    "column_labels": _p(
        "dict[str, str]",
        "Display names for columns, keyed by the real column name. Only "
        "changes what is drawn on the axis; never changes what is measured.",
    ),
    "leading_data_cols": _p(
        "list[str]",
        "Columns to place first in the plotted order, ahead of the rest of the "
        "selection.",
    ),
    "first_columns": _p("list[str]", "Legacy spelling of `leading_data_cols`."),
    # ── which rows ────────────────────────────────────────────────────────
    "filter_by": _p(
        "dict | list[dict]",
        "Row filter. A mapping keeps only rows matching every entry "
        "({'Time':'WeekEight','Sex':'Ma'}); a list of mappings queues one "
        "separate figure per filter; a list value inside a mapping pools those "
        "levels together. Getting the nesting wrong changes whether you get "
        "one pooled figure or several separate ones.",
    ),
    "specificity": _p(
        "tuple | list[tuple]",
        "Legacy spelling of `filter_by`, in tuple form. The runner converts "
        "JSON lists to the tuples the plotting layer expects.",
    ),
    "roi": _p(
        "str | list[str]",
        "Restrict to one or more regions of interest. Omit for all regions.",
    ),
    "conditions": _p(
        "list",
        "Explicit condition objects to plot and their order. Omit to use the "
        "batch's own condition list.",
    ),
    "group_list": _p("list", "Legacy spelling of `conditions`."),
    "groups": _p("list", "Legacy spelling of `conditions`."),
    "animals": _p("list[str]", "Restrict to named subjects."),
    "animal_filter": _p("callable | dict", "Predicate selecting subjects to keep."),
    # ── how to group ──────────────────────────────────────────────────────
    "factor": _p(
        "str",
        "The experimental factor to split and colour by — 'Genotype', 'Sex', "
        "'Drug'. Omit to use the batch's full condition design rather than one "
        "axis of it.",
    ),
    "by": _p(
        "str",
        "What each drawn series represents: 'conditions' for the condition "
        "list, 'all' to pool. Distinct from `factor`, which chooses which "
        "factor the conditions are built from.",
    ),
    "split_by": _p(
        "str",
        "Natural-language grouping shortcut, resolved to `by` or `factor` "
        "depending on which the target function accepts.",
    ),
    "condition_col": _p(
        "str",
        "Column holding the condition label.",
        default="Condition",
    ),
    "group_col": _p("str", "Legacy spelling of `condition_col`."),
    "factor_cols": _p(
        "list[str]",
        "Columns holding the experimental factors of a crossed design.",
    ),
    "group_cols": _p("list[str]", "Legacy spelling of `factor_cols`."),
    "animal_col": _p(
        "str",
        "Column identifying the subject. Drives per-subject point overlays and "
        "paired tests; a wrong value silently makes paired data look unpaired.",
        default="AnimalName",
    ),
    "subject_col": _p("str", "Legacy spelling of `animal_col`."),
    "group_order": _p("list[str]", "Explicit left-to-right order of the groups."),
    "control": _p(
        "str",
        "The reference group every other group is compared against. Omit for "
        "all-pairs comparisons.",
    ),
    "comparisons": _p(
        "list[tuple[str, str]]",
        "Explicit pairs to test and annotate, instead of the automatic set.",
    ),
    # ── statistics ────────────────────────────────────────────────────────
    "alpha": _p(
        "float",
        "Significance threshold. Lowering it makes the test stricter and can "
        "remove annotations from a figure that previously carried them.",
        units="probability",
        default=0.05,
    ),
    "gate": _p(
        "str",
        "Which value decides a hit in a screen: 'p' for raw p-values, 'q' for "
        "FDR-adjusted. 'q' is the honest choice when many tests are run.",
    ),
    "min_n": _p(
        "int",
        "Smallest group size a test will accept. Below this the comparison is "
        "skipped rather than reported on too few subjects.",
        units="subjects",
    ),
    "covariates": _p(
        "list[str]",
        "Columns to adjust for in a linear model. Changes the reported group "
        "means from raw to adjusted.",
    ),
    "random_state": _p(
        "int",
        "Seed for anything resampled. Fix it for a figure that must reproduce "
        "exactly; a bootstrap CI moves slightly without it.",
    ),
    "normalize": _p(
        "bool | str",
        "Rescale each column before plotting. Changes the axis from measured "
        "units to relative ones — never leave it on for a figure whose caption "
        "quotes absolute values.",
    ),
    "show_stats_summary": _p(
        "bool",
        "Draw the text block reporting the test used and its result.",
    ),
    "stats_summary_max_items": _p(
        "int",
        "Longest the statistics summary block may get before it is truncated.",
        units="lines",
    ),
    # ── appearance ────────────────────────────────────────────────────────
    "title": _p("str", "Figure title. Omit to use the generated one."),
    "palette": _p(
        "str | list | dict",
        "Colours for the series. A condition's own declared colour wins over "
        "this; see PyFLASH.palette.declare_conditions.",
    ),
    "auto_style": _p(
        "bool",
        "Give conditions that would otherwise share both a colour and a fill "
        "style distinct styles, so the secondary factor of a crossed design "
        "still reads. On by default.",
    ),
    "style_cycle": _p(
        "list[str]",
        "Order of fill styles used by `auto_style`: 'fill', 'hollow', then "
        "matplotlib hatches such as '///'.",
    ),
    "line_width": _p("float", "Stroke width of drawn lines.", units="points"),
    "point_size": _p(
        "float",
        "Marker diameter. PyFLASH converts to each backend's units, so the "
        "same number means the same size on every plot family.",
        units="points",
    ),
    "marker": _p("str", "Which measured marker to plot, e.g. 'Iba1'."),
    "figsize": _p(
        "tuple[float, float]",
        "Figure size, overriding the house canvas for this call only.",
        units="inches",
    ),
    "tick_label_size": _p("float", "Tick label type size.", units="points"),
    "bottom_ticks": _p("bool", "Draw tick marks on the bottom axis."),
    "bottom_tick_labels": _p("bool", "Label the bottom axis ticks."),
    "share_axes": _p(
        "bool",
        "Give every panel the same limits, so panels can be compared by eye. "
        "Turning it off lets each panel rescale to its own data.",
    ),
    "xmin": _p("float", "Lower x limit.", units="data units"),
    "xmax": _p("float", "Upper x limit.", units="data units"),
    "ymax": _p("float", "Upper y limit.", units="data units"),
    "dpi": _p(
        "int",
        "Raster resolution. Only affects PNG output; SVG is vector regardless.",
        units="dots per inch",
    ),
    # ── output ────────────────────────────────────────────────────────────
    "save": _p(
        "bool",
        "Write the figure to the batch's figure directory. False draws it "
        "without writing anything.",
        default=True,
    ),
    "save_path": _p(
        "str",
        "Directory to write into, overriding the batch's figure directory.",
    ),
    "save_name": _p("str", "Filename stem, without extension."),
    "subfolder": _p("str", "Subdirectory under the figure directory."),
    "return_data": _p(
        "bool",
        "Return the plotted table alongside the figure, for checking numbers "
        "against the drawing.",
    ),
    "run_label": _p("str", "Name for this pipeline run's output folder."),
    "if_exists": _p(
        "str",
        "What to do when the run folder already exists: 'overwrite', or a "
        "variant that keeps the previous run.",
    ),
    "write_manifest": _p(
        "bool",
        "Write the run manifest listing every figure and table produced.",
    ),
    "montage": _p(
        "bool",
        "Assemble the overview montage after a pipeline run — the '! Overview "
        "Montage' file that sorts to the top of the run folder.",
    ),
    "verbose": _p("bool", "Print progress while the run proceeds."),
    # ── choosing and reporting a test ─────────────────────────────────────
    # The arguments most likely to be set wrongly, because the wrong value
    # still produces a figure — one that answers a different question.
    "stats_test": _p(
        "str",
        "Which test to run. 'auto' checks normality, then screens for equal "
        "variance, and routes accordingly. Naming a test skips those checks, so "
        "only do it when you know the assumption holds.",
        default="auto",
    ),
    "force_nonparametric": _p(
        "bool",
        "Skip the normality check and use a rank-based test regardless. Safe "
        "but conservative: it will miss effects a parametric test would find.",
    ),
    "posthoc": _p(
        "str",
        "Pairwise test run after a significant omnibus result — 'Conover', "
        "'Dunn', 'welch'. Only consulted when the omnibus test is significant.",
    ),
    "posthoc_correction": _p(
        "str",
        "Multiple-comparison correction for the pairwise tests. 'auto' picks "
        "one to suit the posthoc test; naming one overrides that.",
        default="auto",
    ),
    "variance_test": _p(
        "str",
        "Equal-variance screen deciding whether the analysis routes to a Welch "
        "variant.",
        default="brown-forsythe",
    ),
    "variance_alpha": _p(
        "float",
        "Threshold for the equal-variance screen. Separate from `alpha`, which "
        "governs the comparison itself.",
        units="probability",
        default=0.05,
    ),
    "auto_welch": _p(
        "bool",
        "Route normal, unequal-variance designs to Welch's test automatically.",
    ),
    "multiple_comparison": _p(
        "str",
        "Design of the omnibus comparison, e.g. 'One-Way'.",
    ),
    "cov_type": _p(
        "str",
        "Covariance estimator for the linear model. 'HC3' is heteroskedasticity-"
        "robust and the default for a reason: it does not assume equal spread.",
        default="HC3",
    ),
    "ns": _p(
        "str",
        "What to print where a comparison is not significant. 'ns' by default; "
        "'p' prints the rounded p-value instead.",
        default="ns",
    ),
    "test": _p("str", "Which statistical test to apply."),
    "correlation": _p(
        "str",
        "Correlation coefficient to compute: 'pearsonr' (linear), 'spearmanr' "
        "(monotonic, rank-based), 'kendalltau' (rank-based, small samples).",
    ),
    "ci_alpha": _p(
        "float",
        "Threshold for the confidence interval, distinct from the test's own "
        "`alpha`.",
        units="probability",
    ),
    "reference": _p("str", "The level other levels are expressed relative to."),
    "predictors": _p("list[str]", "Columns entering the model as predictors."),
    # ── the second axis of a paired selection ─────────────────────────────
    # Every `against_*` mirrors a `data_col*` argument and selects the other
    # side of a correlation grid: rows against columns.
    "against_data_cols": _p(
        "list[str]",
        "Exact column names for the second axis of a paired comparison, the "
        "rows against the `data_cols` columns.",
    ),
    "against_columns": _p("list[str]", "Legacy spelling of `against_data_cols`."),
    "against_data_col_contains": _p(
        "list[str]", "Substrings selecting the second axis of a paired comparison."
    ),
    "against_column_strings": _p(
        "list[str]", "Legacy spelling of `against_data_col_contains`."
    ),
    "against_data_col_regex": _p(
        "str", "Regular expression selecting the second axis."
    ),
    "against_regex_string": _p("str", "Legacy spelling of `against_data_col_regex`."),
    "against_data_col_exclude": _p(
        "str | list[str]", "Substrings removed from the second axis selection."
    ),
    "against_exclude": _p(
        "str | list[str]", "Legacy spelling of `against_data_col_exclude`."
    ),
    # ── axes and drawing ──────────────────────────────────────────────────
    "x_range": _p("tuple[float, float]", "Explicit x limits.", units="data units"),
    "y_range": _p(
        "tuple[float, float]",
        "Explicit y limits. Bars stay anchored at zero, so an explicit range "
        "must include it.",
        units="data units",
    ),
    "ymin": _p("float", "Lower y limit; shortcut for one end of `y_range`.", units="data units"),
    "x": _p("str", "Column drawn on the x axis."),
    "y": _p("str", "Column drawn on the y axis."),
    "x_attr": _p("str", "Per-object attribute drawn on the x axis."),
    "columns": _p("list[str]", "Columns to plot, for calls that name them positionally."),
    "subtitle": _p("str", "Second line under the title."),
    "filename": _p("str", "Output filename stem, without extension."),
    "path": _p("str", "Input path to read from, for calls that take a table directly."),
    "cmap": _p(
        "str",
        "Matplotlib colormap for a continuous scale. Use a diverging map only "
        "when the value has a meaningful midpoint.",
    ),
    "share_columns_across_panels": _p(
        "bool", "Give every panel the same column set, so panels line up."
    ),
    "show_values": _p("bool", "Print the numeric value inside each cell or bar."),
    "show_points": _p("bool", "Overlay the individual data points."),
    "show_ci": _p("bool", "Draw the confidence interval."),
    "merge": _p("bool", "Draw every group into one panel instead of one panel each."),
    "combine": _p("bool", "Overlay the groups on shared axes."),
    "value_format": _p("str", "How a printed value is formatted, e.g. 'p' for p-values."),
    "value_matrices": _p("str", "Which value fills the matrix: 'p' or 'q'."),
    "plot_pvalue_matrices": _p("bool", "Draw the raw p-value matrices."),
    "plot_qvalue_matrices": _p("bool", "Draw the FDR-adjusted q-value matrices."),
    "point_edge": _p(
        "str",
        "Outline colour of an overlaid point: 'group' for the condition's "
        "colour, 'none' for no outline.",
    ),
    "point_linewidth": _p("float", "Outline width of an overlaid point.", units="points"),
    # ── grounding against the data ────────────────────────────────────────
    "column_filter": _p(
        "str",
        "Substring narrowing which columns `inspect` lists. Omit to see the "
        "first `limit` of them.",
    ),
    "limit": _p(
        "int",
        "Longest column list `inspect` will return before truncating. The "
        "reply says whether it truncated.",
        units="columns",
        default=80,
    ),
}


#: Legacy spellings and the current name each stands for. Kept next to the docs
#: because "which of these two do I emit?" is a documentation question: both
#: work, and only one should appear in new calls.
ALIAS_OF = {
    "filtered_columns": "data_cols",
    "column_strings": "data_col_contains",
    "regex_string": "data_col_regex",
    "exclude": "data_col_exclude",
    "specificity": "filter_by",
    "group_list": "conditions",
    "groups": "conditions",
    "group_col": "condition_col",
    "group_cols": "factor_cols",
    "subject_col": "animal_col",
    "first_columns": "leading_data_cols",
}


_TYPE_NAMES = {
    bool: "bool",
    int: "int",
    float: "float",
    str: "str",
    list: "list",
    tuple: "tuple",
    dict: "dict",
    set: "set",
}


def _type_of(parameter):
    """A readable type for one signature parameter.

    The annotation when there is one, otherwise the type of the default, which
    is what PyFLASH's signatures actually carry: `points=True` says bool more
    reliably than any annotation would, because it cannot go stale.
    """

    if parameter.annotation is not inspect.Parameter.empty:
        annotation = parameter.annotation
        return getattr(annotation, "__name__", str(annotation)).strip("'\"")
    default = parameter.default
    if default is inspect.Parameter.empty or default is None:
        return "any"
    return _TYPE_NAMES.get(type(default), type(default).__name__)


def derive(name, parameter=None):
    """Documentation for one parameter: declared if it is, read off the
    signature if it is not.

    *parameter* is an :class:`inspect.Parameter`. Without one only the declared
    entry can be returned, so an undeclared name comes back with an honest
    empty description rather than an invented one.
    """

    declared = PARAM_DOCS.get(name)
    if declared is not None:
        entry = dict(declared)
        if parameter is not None and entry.get("default") is None:
            # The signature is the authority on defaults; the declared default
            # is only there for the handful documented as carrying a surprise
            # (`exclude=""` rather than None).
            if parameter.default is not inspect.Parameter.empty:
                entry["default"] = parameter.default
            entry["required"] = parameter.default is inspect.Parameter.empty
        entry["name"] = name
        return entry

    if parameter is None:
        return {
            "name": name,
            "type": "any",
            "units": "-",
            "required": False,
            "default": None,
            "description": "",
        }

    alias_note = ""
    if name in ALIAS_OF:
        alias_note = f"Legacy spelling of `{ALIAS_OF[name]}`."
    return {
        "name": name,
        "type": _type_of(parameter),
        "units": "-",
        "required": parameter.default is inspect.Parameter.empty,
        "default": None if parameter.default is inspect.Parameter.empty else parameter.default,
        "description": alias_note,
    }


def doc_for(name):
    """The declared entry for one name, or None if it is derived."""

    declared = PARAM_DOCS.get(name)
    return dict(declared, name=name) if declared else None


def describe_all(func):
    """Every parameter of *func*, documented. Returns a list of dicts in
    signature order, skipping private and variadic arguments."""

    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return []
    rows = []
    for parameter in signature.parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.name.startswith("_"):
            continue
        rows.append(derive(parameter.name, parameter))
    return rows
