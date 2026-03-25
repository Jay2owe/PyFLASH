"""
Declarative plot specification — run plot batches from YAML/TOML/JSON files.

Usage:
    from IF_analysis import run_spec
    run_spec(experiment, 'my_plots.yaml')
"""

import os
import json
import inspect
import logging

logger = logging.getLogger(__name__)


# Lazy string references to avoid circular imports
PLOT_REGISTRY = {
    'mean_bars': 'plot_mean_bars',
    'histograms': 'plot_histograms',
    'matrices': 'plot_matrices',
    'volcano': 'plot_volcano',
    'ridgeline': 'plot_ridgeline',
    'ecdf': 'plot_ecdf',
    'regressions': 'plot_regressions',
    'pie_charts': 'plot_pie_charts',
    'locations': 'plot_locations',
    'images': 'plot_images',
    'representative_images': 'plot_representative_images',
    'rect_matrices': 'plot_rect_matrices',
    'coloc_upset': 'plot_coloc_upset',
    'coloc_sankey': 'plot_coloc_sankey',
}


def _resolve_func(name):
    """Resolve a plot function by name from the plotting module."""
    import IF_analysis.plotting as plotting
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
    """Load a plot specification from a YAML, TOML, or JSON file.

    Parameters
    ----------
    path : str
        Path to a .yaml/.yml, .toml, or .json spec file.

    Returns
    -------
    dict
        Parsed specification dictionary.

    Raises
    ------
    ImportError
        If the required parser library is not installed.
    ValueError
        If the file extension is not supported.
    """
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


def validate_spec(spec, experiment=None):
    """Validate a plot specification, returning (errors, warnings) lists.

    Parameters
    ----------
    spec : dict
        Parsed specification from :func:`load_spec`.
    experiment : Experiment or Batch, optional
        If provided, column references are checked against
        ``experiment.summary.columns``.

    Returns
    -------
    tuple[list[str], list[str]]
        ``(errors, warnings)`` — errors are fatal, warnings are advisory.
    """
    errors = []
    warnings = []

    if not isinstance(spec, dict) or 'plots' not in spec:
        errors.append("Spec must be a dict with a 'plots' key")
        return errors, warnings

    plots = spec['plots']
    if not isinstance(plots, list):
        errors.append("'plots' must be a list of plot entries")
        return errors, warnings

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

        # Validate parameter names against function signature
        func_name = PLOT_REGISTRY[plot_type]
        try:
            func = _resolve_func(func_name)
            sig = inspect.signature(func)
            valid_params = set(sig.parameters.keys())

            for key in entry:
                if key == 'type':
                    continue
                # Map 'columns' to 'filtered_columns' for functions that use it
                if key == 'columns' and 'filtered_columns' in valid_params:
                    continue
                if key not in valid_params:
                    warnings.append(
                        f"{prefix}: unknown parameter '{key}' for {plot_type}. "
                        f"Valid: {', '.join(sorted(valid_params - {'experiment', 'source'}))}"
                    )
        except Exception as e:
            warnings.append(f"{prefix}: could not validate params: {e}")

        # Validate column references if experiment provided
        if experiment is not None:
            cols = entry.get('columns') or entry.get('filtered_columns')
            if isinstance(cols, list):
                available = set(experiment.summary.columns)
                for col in cols:
                    if col not in available:
                        warnings.append(
                            f"{prefix}: column '{col}' not found in "
                            "experiment.summary"
                        )

    return errors, warnings


def run_spec(experiment, path):
    """Load, validate, and execute a plot specification file.

    Parameters
    ----------
    experiment : Experiment or Batch
        The data source to plot from.
    path : str
        Path to a .yaml, .toml, or .json spec file.

    Returns
    -------
    list
        Results from each plot call (may contain None for failed entries).

    Raises
    ------
    ValueError
        If the spec contains validation errors.
    """
    spec = load_spec(path)
    errors, warnings = validate_spec(spec, experiment)

    for w in warnings:
        logger.warning("Spec warning: %s", w)
        print(f"  WARNING: {w}")

    if errors:
        for e in errors:
            logger.error("Spec error: %s", e)
            print(f"  ERROR: {e}")
        raise ValueError(
            f"Spec validation failed with {len(errors)} error(s). "
            "Fix the errors above and retry."
        )

    results = []
    for i, entry in enumerate(spec['plots']):
        plot_type = entry['type']
        func_name = PLOT_REGISTRY[plot_type]
        func = _resolve_func(func_name)

        # Build kwargs
        kwargs = {}
        sig = inspect.signature(func)
        valid_params = set(sig.parameters.keys())

        for key, value in entry.items():
            if key == 'type':
                continue

            # Map 'columns' alias to 'filtered_columns'
            param_key = key
            if (key == 'columns'
                    and key not in valid_params
                    and 'filtered_columns' in valid_params):
                param_key = 'filtered_columns'

            # Convert specificity lists to tuples
            if key == 'specificity':
                value = _convert_specificity(value)

            kwargs[param_key] = value

        try:
            print(f"  Running {plot_type} ({i + 1}/{len(spec['plots'])})...")
            result = func(experiment, **kwargs)
            results.append(result)
        except Exception as e:
            logger.error("Plot %s failed: %s", plot_type, e)
            print(f"  FAILED: {plot_type} -- {e}")
            results.append(None)

    return results
