"""Source-owned parameter contracts and explicit browser execution adapters.

Discovery never imports analysis engines. Presentation adds input roles, not
scientific defaults. Unknown objects are reported rather than guessed or eval'd.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import lru_cache
import importlib
import json
import math
from pathlib import Path

from PyFLASH.ui import catalogue


@dataclass(frozen=True)
class Field:
    parameter: catalogue.Parameter
    role: str
    label: str
    choices: tuple = ()
    reason: str = ""

    @property
    def name(self):
        return self.parameter.name


@dataclass(frozen=True)
class Contract:
    entry: catalogue.Function
    title: str
    task: str
    output: str
    access: str
    fields: tuple[Field, ...]
    reason: str = ""


TITLES = {
    "mean_bars": "Compare group means", "regressions": "Relate two measurements",
    "histograms": "Inspect measurement distributions", "ecdf": "Compare cumulative distributions",
    "ridgeline": "Compare distribution shapes", "scatter_3d": "Relate three measurements",
    "linear_model_pipeline": "Fit adjusted linear models", "marker_pca": "Explore measurement patterns",
    "model_result_matrix": "View fitted-model results", "paired_ratio": "Compare paired ratios",
    "images": "Browse microscopy images", "representative_images": "View representative images",
    "locations": "Map object locations", "group_comparison_pipeline": "Compare groups with statistics",
    "data_overview_pipeline": "Check dataset quality", "iterative_model_sweep": "Compare predictive models",
    "linear_model_adjusted_means": "View adjusted group means",
    "linear_model_coefficient_forest": "View model coefficients", "power_curve": "Explore statistical power",
    "timecourse": "Compare changes over time", "cosinor": "Fit a rhythmic measurement",
    "condition_key": "Show the group key", "matrices": "Compare measurement correlations",
}

LABELS = {
    "data_cols": "Measurements", "columns": "Measurements", "filtered_columns": "Measurements",
    "x": "Horizontal measurement", "y": "Vertical measurement", "z": "Depth measurement",
    "x_attr": "Object measurement", "marker": "Object marker", "markers": "Image markers",
    "objects": "Object markers", "column": "Measurement", "target": "Class to predict",
    "dependent_variables": "Outcomes", "dependent_variable": "Outcome", "predictors": "Predictors",
    "group_col": "Grouping column", "animal_col": "Subject identity column",
    "subject_col": "Subject identity column", "filter_by": "Include matching rows",
    "normalize_x": "Horizontal measurement normalization", "normalize_y": "Vertical measurement normalization",
    "stats_test": "Statistical test", "posthoc_correction": "Pairwise correction",
    "alpha": "Alpha", "path": "Saved result table", "model_table": "Fitted result table",
    "associations": "Relationships", "reference_levels": "Categorical reference levels",
}

MEASUREMENTS = set("data_cols columns filtered_columns against_data_cols against_columns covariates candidate_covariates predictors possible_predictors candidate_predictors excluded_predictors dependent_variables outcomes endpoints medication_columns categorical_covariates leading_data_cols first_columns pvalue_cols param_cols".split())
COLUMN = set("x y z column data_col dependent_variable numerator_col denominator_col size_by phase_col radius_col raw_value_col".split())
META = set("group_col condition_col animal_col subject_col time_col hue_column factor split_by group factor_cols group_cols id_cols".split())
LISTS = set("data_col_contains column_strings against_column_strings against_data_col_contains data_col_exclude against_data_col_exclude group_order category_order class_order row_order profile_order predictor_order column_order against_order marker_order prefix_order style_cycle tests model_families outlier_methods terms order collapse_markers".split())
MAPPINGS = set("column_labels category_labels group_labels profile_labels reference_levels group_colors group_styles marker_colors time_map scorecard_thresholds cov_kwds dataframe_kwargs image_adjustments significance_markers extra_graph_colors".split())
RANGES = set("x_range y_range z_range bin_range n_range figsize radial_value_radii".split())
NUMBER_LISTS = set("effect_sizes target_powers bin_edges".split())
NUMERIC = set("binwidth xmin xmax ymin ymax zmin zmax vmin vmax min_n max_regressions max_adjusted_regressions max_plot_items max_images ncols point_size point_linewidth point_alpha point_jitter line_width line_alpha raw_point_size stats_summary_max_items observed_n threshold covariate_alpha difference_alpha scale_bar_size image_width_microns pixel_size preview_max_dim image_workers sample_dot_size sample_line_width mean_marker_size elevation azimuth node_size x_axis_width_scale".split())
NULLABLE_BOOL = set("plot_pvalue_matrices plot_qvalue_matrices show_counts show_pct include_n as_counts include_N auto_style show_subject_points show_participant_lines draw_rois".split())
PAIRS = set("comparisons difference_comparisons audit_comparisons primary_comparison interactions".split())
OBJECTS = set("df model_table adjusted_means coefficients audit_table raw_data observed condition_list ax fig scatter bar writer worksheet result_object".split())
FILES = set("path comparisons_path raw_path output_dir save_path".split())
COMMON = set("data_cols columns x y z column marker markers x_attr objects associations dependent_variables predictors target category path time_col numerator_col denominator_col phase_col test stats_test normalize_x normalize_y normalize binwidth bins combine".split())
APPEARANCE = set("figsize title subtitle footer cmap palette point_fill point_edge point_size point_linewidth point_alpha line_width line_alpha tick_label_size y_range x_range z_range ymin ymax xmin xmax zmin zmax value_format vmin vmax legend show_legend labelsize".split())
ALIASES = {
    "filtered_columns": "data_cols", "column_strings": "data_col_contains", "regex_string": "data_col_regex",
    "exclude": "data_col_exclude", "first_columns": "leading_data_cols", "specificity": "filter_by",
    "against_columns": "against_data_cols", "against_column_strings": "against_data_col_contains",
    "against_regex_string": "against_data_col_regex", "against_exclude": "against_data_col_exclude",
    "animal_filter": "subject_filter", "merge": "combine", "group_list": "groups",
}

# These choices are the owning functions' documented alternatives. Any unknown
# option remains a text field rather than silently assuming a scientific enum.
CHOICES = {
    "normalize_x": (False, True, "Z-score"), "normalize_y": (False, True, "Z-score"),
    "normalize_z": (False, True, "Z-score"), "by": ("conditions", "subjects"),
    "stats_test": ("auto", "student_t", "welch_t", "mannwhitney", "anova", "welch_anova", "kruskal", "two_way", "linear_model"),
    "correlation": ("pearsonr", "spearmanr", "kendalltau"),
}

# Public helpers have explicit, tested input bindings; no arbitrary browser name
# ever becomes an import or call. All other entries retain accurate reference.
from PyFLASH.actions import HELPER_ACTIONS as PUBLIC


def default_value(parameter):
    """Read literals without executing symbolic defaults or importing the owner."""
    try:
        return ast.literal_eval(parameter.default)
    except (ValueError, SyntaxError):
        return None


def _role(parameter, item):
    from PyFLASH.param_docs import PARAM_DOCS
    name = parameter.name
    names = {p.name for p in item.parameters}
    if name.startswith("_") or parameter.kind.startswith("variable"):
        return "managed", "Internal or delegated argument; supplied by the owning adapter."
    if name == item.parameters[0].name and item.action and name in {"experiment", "batch", "source", "batch_or_df"}:
        return "bound", "The loaded dataset is supplied automatically."
    if name in {"save", "show"} and item.action:
        return "managed", "The browser saves outputs and does not open a desktop plotting window."
    if name in ALIASES and ALIASES[name] in names:
        return "alias", f"Use {ALIASES[name]} instead; the legacy name remains available in the reference."
    if name in {"conditions", "groups", "group_list"} and item.action:
        return "bound", "Group definitions come from the loaded dataset; select rows with Include matching rows."
    if name in MEASUREMENTS:
        if name in {"predictors", "possible_predictors", "candidate_predictors", "excluded_predictors", "covariates", "candidate_covariates", "categorical_covariates", "medication_columns"}:
            return "metadata_list", "Numeric and categorical dataset columns are both supported."
        return "measurements", ""
    if name in COLUMN:
        return "measurement", ""
    if name in META or name == "category" or name == "target":
        return ("metadata_list" if name.endswith("cols") else "metadata"), ""
    if name in {"marker", "objects"}:
        return ("marker_list" if name == "objects" else "marker"), ""
    if name == "markers":
        return "image_markers", ""
    if name == "x_attr":
        return "object_measurement", ""
    if name in {"subject_filter", "roi_filter"}:
        return "list", ""
    if name == "filter_by":
        return "filters", ""
    if name == "associations":
        return "associations", ""
    if name in PAIRS:
        return "pairs", ""
    if name in RANGES:
        return ("size" if name == "figsize" else "range"), ""
    if name in NUMBER_LISTS or name == "pvalues":
        return "numbers", ""
    if name in MAPPINGS or "dict" in PARAM_DOCS.get(name, {}).get("type", ""):
        return "mapping", ""
    if name in OBJECTS:
        return "object", "Select a saved table through its file input, or use the operation that creates this object."
    if name in FILES or name.endswith("_path"):
        return "file", ""
    if name in LISTS or "list" in parameter.annotation or "Iterable" in parameter.annotation:
        return "list", ""
    if name in CHOICES:
        return "choice", ""
    value = default_value(parameter)
    type_ = parameter.annotation or PARAM_DOCS.get(name, {}).get("type", "")
    if isinstance(value, bool) or type_ == "bool" or name in NULLABLE_BOOL:
        return "boolean", ""
    if isinstance(value, (int, float)) or type_ in {"int", "float"} or name in NUMERIC or name in {"r", "r1", "r2", "n", "n1", "n2", "p", "p_value", "n_tests"}:
        return ("integer" if isinstance(value, int) or type_ == "int" or name in {"n", "n1", "n2", "n_tests"} else "number"), ""
    if isinstance(value, (list, tuple)):
        return ("numbers" if all(isinstance(x, (int, float)) for x in value) else "list"), ""
    if isinstance(value, dict):
        return "mapping", ""
    return "text", ""


def _task(item):
    action = item.action or ""
    if action in {"images", "representative_images", "locations"}:
        return "Inspect images"
    if any(word in action for word in ("model", "regression_matrix", "power")):
        return "Fit models"
    if any(word in action for word in ("correlation", "coefficient", "association", "regressions", "scatter")):
        return "Examine relationships"
    if any(word in action for word in ("rhythm", "cosinor", "acrophase", "timecourse")):
        return "Explore changes over time"
    if any(word in action for word in ("bars", "superplot", "paired", "group", "effect", "volcano", "baseline", "significance", "condition_key")):
        return "Compare groups"
    if action:
        return "Explore measurements"
    if item.module in {"PyFLASH.export", "PyFLASH.serialization", "PyFLASH.publication", "PyFLASH.provenance"}:
        return "Import and export"
    if item.module == "PyFLASH.stats":
        return "Statistics helpers"
    return "Package helpers"


@lru_cache(maxsize=2)
def _contracts(items):
    result = []
    image = next(i for i in items if i.action == "images")
    for item in items:
        parameters = item.parameters
        if item.action == "representative_images":
            names = {p.name for p in parameters}
            parameters += tuple(p for p in image.parameters[1:] if p.name not in names)
        fields = []
        for parameter in parameters:
            role, reason = _role(parameter, item)
            if item.key == "PyFLASH.export.format_summary_for_display" and parameter.name == "summary":
                role, reason = "bound", "The loaded region summary is supplied automatically."
            choices = CHOICES.get(parameter.name, ())
            if parameter.name in {'model_families','model_preset'}:
                from PyFLASH._classifier_registry import CLASSIFIER_FAMILIES, PRESETS
                role, choices = ('list', tuple(CLASSIFIER_FAMILIES)) if parameter.name == 'model_families' else ('choice', PRESETS)
            if parameter.name == "test" and item.action in {"regressions", "correlation_contrast", "association_correlations"}:
                role, choices = "choice", ("pearsonr", "spearmanr", "kendalltau")
            if parameter.name == "test" and item.action == "power_curve":
                role, choices = "choice", ("t-test", "anova")
            fields.append(Field(parameter, role, LABELS.get(parameter.name, parameter.name.replace("_", " ").capitalize()), choices, reason))
        access = "form" if item.action or item.key in PUBLIC else "reference"
        reason = ""
        if access == "reference":
            if item.binding == "class":
                reason = "This creates a Python object. Load data or define its inputs with the package workflow before using its methods."
            elif item.binding == "instance":
                reason = f"This operates on a {item.name.split('.')[0]} object. Its instance and method-specific inputs are required; a browser adapter is not available."
            else:
                required = [p.name for p in parameters if p.required]
                reason = "Python helper: " + ("supply " + ", ".join(required) + " to the call below." if required else "use the documented Python call; this has no browser adapter.")
        title = PUBLIC.get(item.key, (TITLES.get(item.action, (item.action or item.name).replace("_", " ").capitalize()),))[0]
        result.append(Contract(item, title, _task(item), "Figures and recorded outputs" if item.action else "Table or value", access, tuple(fields), reason))
    return tuple(result)


_render_contracts = ContextVar('pyflash_render_contracts', default=None)


@contextmanager
def catalogue_snapshot():
    """Verify source once per render, then share immutable declarations.

    Reset on every exit, including Streamlit reruns. Other sessions and later
    interactions still read current source bytes, including same-stat edits.
    """
    current = _render_contracts.get()
    token = _render_contracts.set(contracts() if current is None else current)
    try:
        yield _render_contracts.get()
    finally:
        _render_contracts.reset(token)


def contracts():
    current = _render_contracts.get()
    return _contracts(catalogue.functions()) if current is None else current


def catalogue_home(contract):
    """Place user-facing analysis actions separately from supporting helpers."""
    if contract.entry.action:
        return "functions"
    if contract.entry.module in {"PyFLASH.aesthetics", "PyFLASH.palette"}:
        return "appearance"
    if contract.entry.module in {"PyFLASH.export", "PyFLASH.publication", "PyFLASH.serialization"} or (
        contract.entry.module == "PyFLASH.batch" and contract.entry.name.startswith("Batch.export")
    ):
        return "export"
    return "workspace"


def catalogue_contracts(home="functions"):
    return tuple(c for c in contracts() if catalogue_home(c) == home)


def find(key):
    return next((c for c in contracts() if c.entry.key == key or c.entry.action == key), None)


def search(items, query="", *, task="All", access="All"):
    words = query.casefold().split()
    selected = [c for c in items if (task == "All" or c.task == task)
                and (access == "All" or (c.access == "form") == (access == "Browser forms"))
                and all(w in (" ".join([c.title, c.task, c.entry.key, c.entry.documentation, *c.entry.aliases,
                                      *(f.label + " " + f.name + " " + f.parameter.description for f in c.fields)])).casefold() for w in words)]
    exact = query.strip().casefold().replace(" ", "_")
    return tuple(sorted(selected, key=lambda c: (not (exact in {c.entry.action, c.entry.name.casefold(), c.entry.key.casefold()}),)))


def input_context(batch, region=None, cache=None):
    """Inspect already-loaded identities/headers; do not load pixels or rescan data."""
    from PyFLASH.ui import workspace, services
    if batch is None:
        return {"table": None, "metrics": [], "labels": {}, "columns": [], "markers": {}, "image_markers": [], "experiments": []}
    cache = {} if cache is None else cache
    table, metrics, labels = workspace.measurement_catalogue(batch, roi_base=region, cache=cache)
    cached = cache.get("function_context")
    if cached is not None and cached[0] is batch and cached[1] == region:
        return cached[2]
    columns = list(table.columns) if table is not None else []
    markers = {}
    from pandas.api.types import is_numeric_dtype
    for name, obj in (getattr(batch, "data", {}) or {}).items():
        frame = getattr(obj, "df", None)
        if frame is not None:
            markers[str(name)] = [str(c) for c, dtype in frame.dtypes.items() if is_numeric_dtype(dtype)
                                  if c not in {"AnimalName", "Condition", "Region", "Hemisphere"}]
    images = services.image_table(batch)
    image_markers = list(images["Marker"].dropna().astype(str).unique()) if images is not None and "Marker" in images else []
    context = {"table": table, "metrics": metrics, "labels": labels, "columns": columns,
               "markers": markers, "image_markers": image_markers,
               "experiments": list(getattr(batch, "experiment_list", []) or [])}
    cache["function_context"] = (batch, region, context)
    return context


def validate(contract, values, context):
    """Cheap field validation before admission; expensive owner validation is in the worker."""
    issues = {}
    fields = {f.name: f for f in contract.fields}
    for name, value in values.items():
        field = fields.get(name)
        if field is None or field.role in {"managed", "bound", "alias"}:
            issues[name] = "This input is supplied by the application or is not part of this function."
            continue
        if value is None:
            continue
        role = field.role
        if role in {"measurements", "metadata_list", "marker_list", "image_markers", "range", "size", "numbers", "list", "pairs"} and not isinstance(value, (list, tuple)):
            issues[name] = "Enter this input as a list using its rows or selections."
            continue
        if role in {"mapping", "filters"} and not isinstance(value, dict):
            issues[name] = "Enter named values using the row editor."
            continue
        if role in {"measurement", "measurements", "metadata", "metadata_list"}:
            available = context["metrics"] if role.startswith("measurement") else context["columns"]
            selections = value if isinstance(value, list) else [value]
            if any(v not in available for v in selections):
                issues[name] = "Choose inputs available in the loaded dataset."
        elif role in {"number", "integer"} and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            issues[name] = "Enter a finite number."
        elif role == "integer" and not isinstance(value, int):
            issues[name] = "Enter a whole number."
        elif role == "range" and (len(value) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in value) or value[0] >= value[1]):
            issues[name] = "Enter two finite values, with the first smaller than the second."
        elif role == "numbers" and any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
            issues[name] = "Enter one finite number per row."
        elif role == "size" and (not isinstance(value, (tuple, list)) or len(value) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in value)):
            issues[name] = "Enter two positive figure dimensions."
        elif role == "associations":
            specs = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
            if not isinstance(value, (dict, list)) or any(not isinstance(s, dict) or s.get("x") not in context["metrics"] or s.get("y") not in context["metrics"] or any(c not in context["metrics"] for c in s.get("covariates", [])) for s in specs):
                issues[name] = "Choose available measurements and covariates for every relationship."
        elif role == "marker" and value not in context["markers"]:
            issues[name] = "Select an imported object marker."
        elif role == "marker_list" and any(v not in context["markers"] for v in value):
            issues[name] = "Select imported object markers."
        elif role == "object_measurement" and value not in context["markers"].get(values.get("marker"), []):
            issues[name] = "Select a measurement recorded for the chosen marker."
        elif role == "image_markers" and any(v not in context["image_markers"] for v in value):
            issues[name] = "Select imported image markers."
        elif role == "file":
            if name in {"path", "comparisons_path", "raw_path"} and not Path(value).is_file():
                issues[name] = "Choose an existing result table file."
    for field in contract.fields:
        if field.parameter.required and field.role not in {"bound", "managed", "alias"} and values.get(field.name) in (None, "", [], {}):
            issues[field.name] = f"Choose {field.label.lower()} before running."
        if field.parameter.required and field.role == "object":
            issues[field.name] = f"This function requires {field.label.lower()} from its Python workflow; it cannot be supplied by this dataset."
    action = contract.entry.action
    if action in {"images", "representative_images"} and not context["image_markers"]:
        issues["markers"] = "This dataset has no imported images. Import its microscopy images first."
    if action in {"mean_bars", "matrices", "volcano", "superplot", "radar", "marker_pca", "group_comparison_pipeline"} and not any(values.get(k) for k in ("data_cols", "columns", "data_col_contains", "data_col_regex")):
        issues["data_cols"] = "Select at least one measurement; no measurement is chosen automatically."
    if action in {"linear_model_pipeline", "iterative_model_sweep"}:
        if not any(values.get(k) for k in ("dependent_variables", "data_cols", "target")):
            issues["dependent_variables" if action == "linear_model_pipeline" else "target"] = "Select the outcome before fitting."
        if not any(values.get(k) for k in ("predictors", "possible_predictors", "candidate_predictors")):
            issues["predictors"] = "Select predictors before fitting."
    if action in {"model_result_matrix", "linear_model_adjusted_means", "linear_model_coefficient_forest"} and not values.get("path"):
        issues["path"] = "Select the saved result table produced by the fitted-model workflow."
    if action == "locations" and not context["experiments"]:
        issues["objects"] = "Select a processed experiment with recorded object coordinates."
    return issues


def prepared_values(contract, values):
    """Keep omission, None and empty values distinct; strip no user overrides."""
    fields = {f.name: f for f in contract.fields}
    unknown = set(values) - fields.keys()
    if unknown:
        raise ValueError("Unknown inputs: " + ", ".join(sorted(unknown)))
    result = {}
    for name, value in values.items():
        field = fields[name]
        if field.role in {"bound", "managed", "alias", "object"}:
            raise ValueError(f"{name} is supplied through its context, not a free-form override.")
        if field.role in {"range", "size"} and value is not None:
            value = tuple(value)
        elif field.role == "pairs" and value is not None:
            value = [tuple(row) for row in value]
        elif isinstance(default_value(field.parameter), tuple) and isinstance(value, list):
            value = tuple(value)
        result[name] = value
    return result


def public_call(contract, batch, values, region=None):
    """Resolve only declared helper adapters and bind real data/instances."""
    if contract.entry.key not in PUBLIC:
        raise ValueError("This public helper does not have a browser execution adapter.")
    kwargs = prepared_values(contract, values)
    entry = contract.entry
    if entry.binding == "instance":
        cls_name, method_name = entry.name.split(".")
        cls = getattr(importlib.import_module(entry.module), cls_name)
        if not isinstance(batch, cls):
            raise ValueError(f"Open a {cls_name} dataset before using this method.")
        return getattr(batch, method_name), kwargs
    func = getattr(importlib.import_module(entry.module), entry.name)
    if PUBLIC[entry.key][1] == "table":
        from PyFLASH.ui.services import summary_table
        kwargs["summary"] = summary_table(batch, roi_base=region, display=False).copy()
    return func, kwargs


def coverage(items=None):
    """Machine-readable accounting for every entry and parameter."""
    return [{"key": c.entry.key, "owner": c.entry.module + "." + c.entry.name,
             "title": c.title, "task": c.task, "access": c.access, "output": c.output,
             "reason": c.reason, "cost": "explicit background job" if c.access == "form" else "reference only",
             "mutation": "source preserved; worker-local result" if c.access == "form" else "see owning function",
             "parameters": [{"name": f.name, "role": f.role, "required": f.parameter.required,
                             "default_source": f.parameter.default, "help": f.parameter.description,
                             "reason": f.reason} for f in c.fields]} for c in (contracts() if items is None else items)]


@lru_cache(maxsize=2)
def _coverage_document(items):
    return json.dumps(coverage(items), indent=2)


def coverage_document(home=None):
    """Reuse the downloadable audit until the owning declarations change."""
    return _coverage_document(contracts() if home is None else catalogue_contracts(home))
