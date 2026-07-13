"""Public API name aliases.

These helpers let PyFLASH accept clearer public names while preserving the
older argument names that existing scripts and internal code still use.
"""

from __future__ import annotations

from collections.abc import Mapping


def _same_value(left, right):
    if left is right:
        return True
    try:
        return left == right
    except Exception:
        return False


def prefer_alias(current, alias, *, current_name, alias_name, default=None):
    """Resolve one old/new argument pair.

    The new alias is accepted when the old argument is unset or still at its
    default. If both are supplied with different non-default values, raise a
    clear error instead of guessing.
    """

    if alias is None:
        return current
    if current is None or (default is not None and _same_value(current, default)):
        return alias
    if _same_value(current, alias):
        return current
    raise ValueError(
        f"Use either {alias_name}= or {current_name}=, not both with different values."
    )


def normalize_filter_by(filter_by):
    """Convert friendly filter mappings to PyFLASH row-filter objects."""

    if filter_by is None:
        return None
    if isinstance(filter_by, Mapping):
        items = list(filter_by.items())
        if len(items) != 1:
            return dict(items)
        key, value = items[0]
        if isinstance(value, (list, tuple, set)):
            return tuple([key, *list(value)])
        return (key, value)
    if isinstance(filter_by, list) and filter_by and all(isinstance(v, Mapping) for v in filter_by):
        return [normalize_filter_by(v) for v in filter_by]
    return filter_by


def resolve_data_column_aliases(
    *,
    filtered_columns=None,
    column_strings=None,
    regex_string=None,
    exclude="",
    data_cols=None,
    data_col_contains=None,
    data_col_regex=None,
    data_col_exclude=None,
):
    """Resolve new data-column names to the existing column-selection names."""

    filtered_columns = prefer_alias(
        filtered_columns,
        data_cols,
        current_name="filtered_columns",
        alias_name="data_cols",
    )
    column_strings = prefer_alias(
        column_strings,
        data_col_contains,
        current_name="column_strings",
        alias_name="data_col_contains",
    )
    regex_string = prefer_alias(
        regex_string,
        data_col_regex,
        current_name="regex_string",
        alias_name="data_col_regex",
    )
    exclude = prefer_alias(
        exclude,
        data_col_exclude,
        current_name="exclude",
        alias_name="data_col_exclude",
        default="",
    )
    return filtered_columns, column_strings, regex_string, exclude


def resolve_dataframe_aliases(
    *,
    conditions=None,
    condition_col="Condition",
    factor_cols=None,
    animal_col="AnimalName",
    group_list=None,
    groups=None,
    group_col=None,
    group_cols=None,
    subject_col=None,
):
    """Resolve new table/group/subject names to existing DataFrame adapter names."""

    conditions = prefer_alias(
        conditions,
        group_list,
        current_name="conditions",
        alias_name="group_list",
    )
    conditions = prefer_alias(
        conditions,
        groups,
        current_name="conditions/group_list",
        alias_name="groups",
    )
    condition_col = prefer_alias(
        condition_col,
        group_col,
        current_name="condition_col",
        alias_name="group_col",
        default="Condition",
    )
    factor_cols = prefer_alias(
        factor_cols,
        group_cols,
        current_name="factor_cols",
        alias_name="group_cols",
    )
    animal_col = prefer_alias(
        animal_col,
        subject_col,
        current_name="animal_col",
        alias_name="subject_col",
        default="AnimalName",
    )
    return conditions, condition_col, factor_cols, animal_col


def resolve_group_style_aliases(
    *,
    condition_order=None,
    condition_labels=None,
    condition_colors=None,
    condition_styles=None,
    condition_comparisons=None,
    condition_comparison_mode=None,
    condition_control=None,
    group_order=None,
    group_labels=None,
    group_colors=None,
    group_styles=None,
    group_comparisons=None,
    group_comparison_mode=None,
    group_control=None,
):
    """Resolve public group styling/comparison aliases."""

    condition_order = prefer_alias(
        condition_order, group_order,
        current_name="condition_order", alias_name="group_order",
    )
    condition_labels = prefer_alias(
        condition_labels, group_labels,
        current_name="condition_labels", alias_name="group_labels",
    )
    condition_colors = prefer_alias(
        condition_colors, group_colors,
        current_name="condition_colors", alias_name="group_colors",
    )
    condition_styles = prefer_alias(
        condition_styles, group_styles,
        current_name="condition_styles", alias_name="group_styles",
    )
    condition_comparisons = prefer_alias(
        condition_comparisons, group_comparisons,
        current_name="condition_comparisons", alias_name="group_comparisons",
    )
    condition_comparison_mode = prefer_alias(
        condition_comparison_mode, group_comparison_mode,
        current_name="condition_comparison_mode", alias_name="group_comparison_mode",
    )
    condition_control = prefer_alias(
        condition_control, group_control,
        current_name="condition_control", alias_name="group_control",
    )
    return (
        condition_order,
        condition_labels,
        condition_colors,
        condition_styles,
        condition_comparisons,
        condition_comparison_mode,
        condition_control,
    )


def resolve_split_filter_aliases(
    *,
    by,
    factor=None,
    specificity=None,
    split_by=None,
    filter_by=None,
    default_by="conditions",
):
    """Resolve split/filter aliases for plot and pipeline functions."""

    specificity = prefer_alias(
        specificity,
        normalize_filter_by(filter_by),
        current_name="specificity",
        alias_name="filter_by",
    )
    if split_by is None:
        return by, factor, specificity

    split_text = str(split_by)
    if split_text in {"groups", "group"}:
        split_text = "conditions"

    if split_text in {"all", "conditions", "condition"}:
        new_by = "conditions" if split_text == "condition" else split_text
        by = prefer_alias(
            by,
            new_by,
            current_name="by",
            alias_name="split_by",
            default=default_by,
        )
        if factor is not None:
            raise ValueError("Use either split_by= or factor=, not both.")
        return by, None, specificity

    factor = prefer_alias(
        factor,
        split_by,
        current_name="factor",
        alias_name="split_by",
    )
    return by, factor, specificity
