"""
Declarative plot specification — run plot batches from YAML/TOML/JSON files.

Usage:
    from PyFLASH import run_spec

    # Single experiment
    run_spec(batch1, 'path/to/plots.yaml')

    # Multiple batches - reference by name in the YAML
    run_spec({'batch1': batch1, 'batch2': batch2}, 'path/to/plots.yaml')
"""

import os
import json
import inspect
import importlib

from PyFLASH._logging import logger as _log
from PyFLASH.aliases import _same_value


# Lazy string references to avoid circular imports
PLOT_REGISTRY = {
    'mean_bars': 'plot_mean_bars',
    'condition_key': 'plot_condition_key',
    'histograms': 'plot_histograms',
    'matrices': 'plot_matrices',
    'matrix_differences': 'plot_matrix_differences',
    'radar': 'plot_radar',
    'volcano': 'plot_volcano',
    'ridgeline': 'plot_ridgeline',
    'ecdf': 'plot_ecdf',
    'regressions': 'plot_regressions',
    'scatter_3d': 'plot_scatter_3d',
    'pie_charts': 'plot_pie_charts',
    'combo_pies': 'plot_combo_pies',
    'locations': 'plot_locations',
    'images': 'plot_images',
    'representative_images': 'plot_representative_images',
    'rect_matrices': 'plot_rect_matrices',
    'multivariable_regression_matrix': 'plot_multivariable_regression_matrix',
    'coloc_upset': 'plot_coloc_upset',
    'coloc_sankey': 'plot_coloc_sankey',
    'power_curve': 'plot_power_curve',
    'marker_pca': 'plot_marker_pca',
    'timecourse': 'plot_timecourse',
    'superplot': 'plot_superplot',
    'effect_forest': 'plot_effect_forest',
    'group_matrix': 'plot_group_matrix',
    'cosinor': 'plot_cosinor',
    'acrophase_clock': 'plot_acrophase_clock',
    'correlation_pipeline': 'PyFLASH.pipeline.correlation',
    'adjusted_correlation_pipeline': 'PyFLASH.pipeline.adjusted_correlation',
    'data_overview_pipeline': 'PyFLASH.pipeline.data_overview',
    'group_comparison_pipeline': 'PyFLASH.pipeline.group_comparison',
    'linear_model_pipeline': 'PyFLASH.pipeline.linear_model',
    'rhythm_pipeline': 'PyFLASH.pipeline.rhythm',
    'iterative_model_sweep': 'PyFLASH.modelling.iterative_model_sweep',
}

# ── Describe-layer coverage (the structured-results / "describe" feature) ────
# Every plot in PLOT_REGISTRY MUST be classified into exactly one set below, so a
# newly-added plot cannot silently ship without a structured-results decision.
# This is the forcing function that keeps the describe layer (PyFLASH.report)
# maintained as plots are added — enforced by tests/test_describe_coverage.py and
# surfaced by the runner's `discover` command.
#
#   DESCRIBE_COVERED    — emits structured records into PyFLASH.report: via the
#                         shared stats engine (multipleComparisons / regression_action),
#                         a direct report.emit(...), or a pipeline return manifest.
#   DESCRIBE_EXEMPT     — a pure visualisation / purely descriptive plot with no
#                         inferential result to capture (raw images, proportions,
#                         distributions, ordination glyphs, method curves).
#   DESCRIBE_UNREVIEWED — computes a quantitative/inferential result (p-values,
#                         correlations, fold-changes, variance explained) that is
#                         NOT yet captured. A tracked backlog: wire it into
#                         PyFLASH.report and move it to COVERED, or justify EXEMPT.
#
# When you add a plot: route its stats through the shared engine or call
# report.emit, then add its short-name to COVERED; or add it to EXEMPT/UNREVIEWED
# with intent. See CLAUDE.md and the pyflash-add-plot skill.
DESCRIBE_COVERED = {
    'mean_bars',
    'regressions',
    'multivariable_regression_matrix',
    'correlation_pipeline',
    'adjusted_correlation_pipeline',
    'group_comparison_pipeline',
    'linear_model_pipeline',
    'iterative_model_sweep',
    # data_overview's significance-audit section runs the auto-selected test per
    # marker through multipleComparisons, which emits a structured record when
    # PyFLASH.report is armed (default-off section; inert otherwise).
    'data_overview_pipeline',
    # Rhythm module: cosinor fits and circular tests emit structured records via
    # report.emit (plots) and the pipeline return manifest.
    'cosinor',
    'acrophase_clock',
    'rhythm_pipeline',
}
DESCRIBE_EXEMPT = {
    'condition_key', 'images', 'representative_images', 'locations',
    'coloc_upset', 'coloc_sankey', 'pie_charts', 'combo_pies',
    'histograms', 'ridgeline', 'ecdf', 'radar', 'power_curve',
    'scatter_3d',
    # Descriptive group-comparison views (raw points / effect sizes, no test).
    # The inferential capture lives in the group_comparison pipeline (COVERED).
    'superplot', 'effect_forest', 'group_matrix',
}
DESCRIBE_UNREVIEWED = {
    'matrices', 'rect_matrices', 'matrix_differences',
    'volcano', 'marker_pca', 'timecourse',
}


def describe_status(short_name):
    """Return the describe-layer status of a registry short-name.

    One of: 'covered', 'exempt', 'unreviewed', or 'unclassified' (registered but
    not assigned to any set — a maintenance gap the coverage test fails on).
    """
    if short_name in DESCRIBE_COVERED:
        return 'covered'
    if short_name in DESCRIBE_EXEMPT:
        return 'exempt'
    if short_name in DESCRIBE_UNREVIEWED:
        return 'unreviewed'
    return 'unclassified'


# Keys consumed by the spec runner, not passed to plot functions
_SPEC_KEYS = {'type', 'batch'}

_SPEC_PARAM_ALIASES = {
    "columns": "filtered_columns",
    "data_cols": "filtered_columns",
    "data_col_contains": "column_strings",
    "data_col_regex": "regex_string",
    "data_col_exclude": "exclude",
    "against_data_cols": "against_columns",
    "against_data_col_contains": "against_column_strings",
    "against_data_col_regex": "against_regex_string",
    "against_data_col_exclude": "against_exclude",
    "leading_data_cols": "first_columns",
    "filter_by": "specificity",
    "group_list": "conditions",
    "groups": "conditions",
    "group_col": "condition_col",
    "group_cols": "factor_cols",
    "subject_col": "animal_col",
    "subject_filter": "animal_filter",
    "subjects": "animals",
    "subject_min_flags": "animal_min_flags",
    "show_subject_points": "show_animal_xs",
    "subject_point_marker": "animal_x_marker",
    "subject_point_size": "animal_x_size",
    "subject_point_alpha": "animal_x_alpha",
    "subject_point_color": "animal_x_color",
}


def _resolve_param_alias(key, valid_params, value=None):
    if key == "split_by" and key not in valid_params:
        split_text = str(value)
        if split_text in {"group", "groups", "condition"} and "by" in valid_params:
            return "by"
        if split_text in {"all", "conditions"} and "by" in valid_params:
            return "by"
        if "factor" in valid_params:
            return "factor"
        if "by" in valid_params:
            return "by"
    if key in valid_params:
        return key
    alias = _SPEC_PARAM_ALIASES.get(key)
    if alias in valid_params:
        return alias
    return key


def _normalize_spec_param_value(key, param_key, value):
    if key == 'split_by' and param_key == 'by':
        split_text = str(value)
        if split_text in {'group', 'groups', 'condition'}:
            return 'conditions'
    if param_key in {'specificity', 'filter_by'}:
        return _convert_specificity(value)
    return value


def _set_resolved_kwarg(kwargs, sources, param_key, value, source_key):
    """Assign a resolved spec/UI kwarg, rejecting conflicting aliases."""

    if param_key in kwargs:
        if _same_value(kwargs[param_key], value):
            return
        previous = sources.get(param_key, param_key)
        raise ValueError(
            f"Use either {source_key}= or {previous}=, not both with different values."
        )
    kwargs[param_key] = value
    sources[param_key] = source_key


def _resolve_func(name):
    """Resolve a plot function by name from the plotting module."""
    if "." in name:
        module_name, attr = name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, attr)

    import PyFLASH.plotting as plotting
    return getattr(plotting, name)


def _convert_specificity(value):
    """Convert YAML/JSON specificity lists to Python tuples.

    Single filter: [Time, WeekEight] -> ('Time', 'WeekEight')
    Queue: [[Time, WeekEight], [Region, CA1]] -> [('Time', 'WeekEight'), ('Region', 'CA1')]
    """
    if value is None:
        return None
    if isinstance(value, dict):
        items = list(value.items())
        if len(items) != 1:
            return dict(items)
        key, val = items[0]
        if isinstance(val, list):
            return tuple([key, *val])
        return (key, val)
    if isinstance(value, list) and len(value) > 0:
        if isinstance(value[0], dict):
            return [_convert_specificity(v) for v in value]
        if isinstance(value[0], list):
            return [tuple(v) for v in value]
        return tuple(value)
    return value


def load_spec(path):
    """Load a plot specification from a YAML, TOML, or JSON file."""
    ext = os.path.splitext(path)[1].lower()

    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    if ext in ('.yaml', '.yml'):
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required to load .yaml spec files. "
                "Install it with: pip install pyyaml"
            )
        return yaml.safe_load(text)

    elif ext == '.toml':
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                raise ImportError(
                    "tomllib (Python 3.11+) or tomli is required for .toml specs. "
                    "Install with: pip install tomli"
                )
        return tomllib.loads(text)

    elif ext == '.json':
        return json.loads(text)

    else:
        raise ValueError(
            f"Unsupported spec format '{ext}'. Use .yaml, .toml, or .json"
        )


def validate_spec(spec, experiments=None):
    """Validate a plot specification, returning (errors, warnings) lists."""
    errors = []
    warnings = []

    if not isinstance(spec, dict) or 'plots' not in spec:
        errors.append("Spec must be a dict with a 'plots' key")
        return errors, warnings

    plots = spec['plots']
    if not isinstance(plots, list):
        errors.append("'plots' must be a list of plot entries")
        return errors, warnings

    # Normalise experiments to a dict
    if experiments is not None and not isinstance(experiments, dict):
        exp_dict = {'default': experiments}
    else:
        exp_dict = experiments

    for i, entry in enumerate(plots):
        prefix = f"plots[{i}]"

        if not isinstance(entry, dict):
            errors.append(f"{prefix}: must be a dict")
            continue

        plot_type = entry.get('type')
        if plot_type is None:
            errors.append(f"{prefix}: missing 'type' field")
            continue

        if plot_type not in PLOT_REGISTRY:
            errors.append(
                f"{prefix}: unknown plot type '{plot_type}'. "
                f"Available: {', '.join(sorted(PLOT_REGISTRY))}"
            )
            continue

        # Check batch reference
        batch_name = entry.get('batch')
        if batch_name and exp_dict and batch_name not in exp_dict:
            errors.append(
                f"{prefix}: batch '{batch_name}' not found. "
                f"Available: {', '.join(sorted(exp_dict.keys()))}"
            )

        # Validate parameter names against function signature
        func_name = PLOT_REGISTRY[plot_type]
        try:
            func = _resolve_func(func_name)
            sig = inspect.signature(func)
            valid_params = set(sig.parameters.keys())
            resolved_params = {}
            resolved_sources = {}

            for key in entry:
                if key in _SPEC_KEYS:
                    continue
                param_key = _resolve_param_alias(key, valid_params, entry.get(key))
                if param_key not in valid_params:
                    warnings.append(
                        f"{prefix}: unknown parameter '{key}' for {plot_type}. "
                        f"Valid: {', '.join(sorted(valid_params - {'experiment', 'source'}))}"
                    )
                    continue
                value = _normalize_spec_param_value(key, param_key, entry.get(key))
                try:
                    _set_resolved_kwarg(resolved_params, resolved_sources, param_key, value, key)
                except ValueError as e:
                    errors.append(f"{prefix}: {e}")
        except Exception as e:
            warnings.append(f"{prefix}: could not validate params: {e}")

        # Validate column references
        exp = None
        if exp_dict:
            exp = exp_dict.get(batch_name) if batch_name else next(iter(exp_dict.values()), None)
        if exp is not None:
            cols = entry.get('data_cols') or entry.get('columns') or entry.get('filtered_columns')
            if isinstance(cols, list):
                summary = exp if hasattr(exp, "columns") else getattr(exp, "summary", None)
                if summary is None:
                    continue
                available = set(summary.columns)
                for col in cols:
                    if col not in available:
                        warnings.append(
                            f"{prefix}: column '{col}' not found in experiment.summary"
                        )

    return errors, warnings


def run_spec(experiments, path):
    """Load, validate, and execute a plot specification file.

    Parameters
    ----------
    experiments : Experiment, Batch, or dict
        A single data source, or a dict mapping names to sources, e.g.
        ``{'batch1': batch1, 'CK1I': batch_CK1I, 'NLGFKI': batch_NLGFKI}``.
        When a dict is passed, each spec entry can use ``batch: name`` to
        select which source to plot from.
    path : str
        Path to a .yaml, .toml, or .json spec file.

    Returns
    -------
    list
        Results from each plot call (may contain None for failed entries).
    """
    spec = load_spec(path)

    # Normalise to dict
    if isinstance(experiments, dict):
        exp_dict = experiments
    else:
        exp_dict = {'default': experiments}

    errors, warnings = validate_spec(spec, exp_dict)

    for w in warnings:
        _log.warn(f"Spec warning: {w}")

    if errors:
        for e in errors:
            _log.warn(f"Spec error: {e}")
        raise ValueError(
            f"Spec validation failed with {len(errors)} error(s). "
            "Fix the errors above and retry.\n" + "\n".join(errors)
        )

    results = []
    for i, entry in enumerate(spec['plots']):
        plot_type = entry['type']
        func_name = PLOT_REGISTRY[plot_type]
        func = _resolve_func(func_name)

        # Resolve which experiment to use
        batch_name = entry.get('batch')
        if batch_name:
            experiment = exp_dict[batch_name]
        elif len(exp_dict) == 1:
            experiment = next(iter(exp_dict.values()))
        else:
            experiment = next(iter(exp_dict.values()))
            _log.warn(f"plots[{i}] has no 'batch' key, using first experiment")

        # Build kwargs
        kwargs = {}
        kwargs_sources = {}
        sig = inspect.signature(func)
        valid_params = set(sig.parameters.keys())

        for key, value in entry.items():
            if key in _SPEC_KEYS:
                continue

            param_key = _resolve_param_alias(key, valid_params, value)
            value = _normalize_spec_param_value(key, param_key, value)
            _set_resolved_kwarg(kwargs, kwargs_sources, param_key, value, key)

        try:
            batch_label = f" [{batch_name}]" if batch_name else ""
            _log.status(f"Running {plot_type}{batch_label} ({i + 1}/{len(spec['plots'])})")
            result = func(experiment, **kwargs)
            results.append(result)
        except Exception as e:
            _log.warn(f"Plot {plot_type} failed: {e}")
            results.append(None)

    return results
