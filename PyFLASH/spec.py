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

from PyFLASH._logging import logger as _log


# Lazy string references to avoid circular imports
PLOT_REGISTRY = {
    'mean_bars': 'plot_mean_bars',
    'histograms': 'plot_histograms',
    'matrices': 'plot_matrices',
    'radar': 'plot_radar',
    'volcano': 'plot_volcano',
    'ridgeline': 'plot_ridgeline',
    'ecdf': 'plot_ecdf',
    'regressions': 'plot_regressions',
    'pie_charts': 'plot_pie_charts',
    'combo_pies': 'plot_combo_pies',
    'locations': 'plot_locations',
    'images': 'plot_images',
    'representative_images': 'plot_representative_images',
    'rect_matrices': 'plot_rect_matrices',
    'coloc_upset': 'plot_coloc_upset',
    'coloc_sankey': 'plot_coloc_sankey',
}

# Keys consumed by the spec runner, not passed to plot functions
_SPEC_KEYS = {'type', 'batch'}


def _resolve_func(name):
    """Resolve a plot function by name from the plotting module."""
    import PyFLASH.plotting as plotting
    return getattr(plotting, name)


def _convert_specificity(value):
    """Convert YAML/JSON specificity lists to Python tuples.

    Single filter: [Time, WeekEight] -> ('Time', 'WeekEight')
    Queue: [[Time, WeekEight], [Region, CA1]] -> [('Time', 'WeekEight'), ('Region', 'CA1')]
    """
    if value is None:
        return None
    if isinstance(value, list) and len(value) > 0:
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

            for key in entry:
                if key in _SPEC_KEYS:
                    continue
                if key == 'columns' and 'filtered_columns' in valid_params:
                    continue
                if key not in valid_params:
                    warnings.append(
                        f"{prefix}: unknown parameter '{key}' for {plot_type}. "
                        f"Valid: {', '.join(sorted(valid_params - {'experiment', 'source'}))}"
                    )
        except Exception as e:
            warnings.append(f"{prefix}: could not validate params: {e}")

        # Validate column references
        exp = None
        if exp_dict:
            exp = exp_dict.get(batch_name) if batch_name else next(iter(exp_dict.values()), None)
        if exp is not None:
            cols = entry.get('columns') or entry.get('filtered_columns')
            if isinstance(cols, list):
                available = set(exp.summary.columns)
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
            "Fix the errors above and retry."
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
        sig = inspect.signature(func)
        valid_params = set(sig.parameters.keys())

        for key, value in entry.items():
            if key in _SPEC_KEYS:
                continue

            param_key = key
            if (key == 'columns'
                    and key not in valid_params
                    and 'filtered_columns' in valid_params):
                param_key = 'filtered_columns'

            if key == 'specificity':
                value = _convert_specificity(value)

            kwargs[param_key] = value

        try:
            batch_label = f" [{batch_name}]" if batch_name else ""
            _log.status(f"Running {plot_type}{batch_label} ({i + 1}/{len(spec['plots'])})")
            result = func(experiment, **kwargs)
            results.append(result)
        except Exception as e:
            _log.warn(f"Plot {plot_type} failed: {e}")
            results.append(None)

    return results
