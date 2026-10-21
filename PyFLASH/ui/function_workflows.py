"""Explicit picture homes and task inputs; scientific defaults stay in source.

This module is presentation only. New actions must declare their home and input
sections instead of silently receiving a generic parameter form.
"""
from dataclasses import dataclass, replace
from functools import lru_cache

from PyFLASH.ui import function_contracts as fc


@dataclass(frozen=True)
class Home:
    key: str
    title: str
    picture: str
    description: str
    actions: tuple[str, ...]
    pipeline: bool = False


HOMES = (
    Home('bars', 'Bars & subject points', 'bars', 'Group means, region spread or adjusted means',
         ('mean_bars', 'superplot', 'linear_model_adjusted_means')),
    Home('relationships', 'Relationships', 'scatter', 'Two or three measurements', ('regressions', 'scatter_3d')),
    Home('distributions', 'Distributions', 'histogram', 'Histogram, density or cumulative values', ('histograms', 'ridgeline', 'ecdf')),
    Home('paired', 'Paired measurements', 'paired', 'Within-subject change and ratios', ('paired_ratio',)),
    Home('matrices', 'Matrices', 'matrix', 'Correlations, group effects or fitted results',
         ('matrices', 'rect_matrices', 'matrix_differences', 'group_matrix', 'model_result_matrix', 'multivariable_regression_matrix')),
    Home('effects', 'Effects & coefficients', 'forest', 'Effect sizes and adjusted coefficients',
         ('effect_forest', 'linear_model_coefficient_forest', 'association_coefficients')),
    Home('contrasts', 'Compare relationships', 'contrast', 'Relationships across groups',
         ('correlation_contrast', 'coefficient_contrast', 'association_correlations')),
    Home('volcano', 'Volcano', 'volcano', 'Change against statistical evidence', ('volcano',)),
    Home('composition', 'Proportions & counts', 'pie', 'Categories and marker combinations', ('pie_charts', 'combo_pies', 'category_counts')),
    Home('overlap', 'Marker overlap', 'overlap', 'Intersections and conditional flows', ('coloc_upset', 'coloc_sankey')),
    Home('profiles', 'Measurement profiles', 'profile', 'Radar profiles or principal components', ('radar', 'marker_pca')),
    Home('time', 'Time & rhythm', 'time', 'Time courses, rhythmic fits or peak phase', ('timecourse', 'cosinor', 'acrophase_clock')),
    Home('images', 'Images & locations', 'image', 'Microscopy images or object coordinates', ('images', 'representative_images', 'locations')),
    Home('tables', 'Study tables & group key', 'table', 'Participant characteristics and reported tests',
         ('baseline_characteristics', 'significance_audit_table', 'condition_key')),
    Home('power', 'Statistical power', 'time', 'Power against sample size', ('power_curve',)),
    Home('group_pipeline', 'Group comparison', 'pipeline', 'Statistics, effects and output figures', ('group_comparison_pipeline',), True),
    Home('overview_pipeline', 'Dataset overview', 'pipeline', 'Availability, distributions and diagnostics', ('data_overview_pipeline',), True),
    Home('correlation_pipeline', 'Relationships pipeline', 'pipeline', 'Correlations and selected regressions', ('correlation_pipeline',), True),
    Home('adjusted_pipeline', 'Adjusted relationships', 'pipeline', 'Covariate screening and adjusted associations', ('adjusted_correlation_pipeline',), True),
    Home('linear_pipeline', 'Linear models', 'pipeline', 'Outcomes, predictors and adjusted summaries', ('linear_model_pipeline',), True),
    Home('rhythm_pipeline', 'Rhythm analysis', 'pipeline', 'Rhythmic fits and circular summaries', ('rhythm_pipeline',), True),
    Home('model_pipeline', 'Model exploration', 'pipeline', 'Predictor subsets and classifier families', ('iterative_model_sweep',), True),
)

# Sections describe scientific roles, not a heuristic over parameter names.
# The owning contracts supply controls, defaults and exact argument identities.
SECTIONS = {
    'mean_bars': (('Data', ('data_cols',)), ('Comparison', ('stats_test', 'normalize'))),
    'superplot': (('Data', ('data_cols',)),),
    'linear_model_adjusted_means': (('Saved model', ('path', 'dependent_variables')), ('Comparison', ('comparisons_path', 'show_raw'))),
    'regressions': (('Data', ('x', 'y')), ('Association', ('test',)), ('Scale & grouping', ('normalize_x', 'normalize_y', 'combine'))),
    'scatter_3d': (('Data', ('x', 'y', 'z')), ('Scale & grouping', ('normalize_x', 'normalize_y', 'normalize_z', 'combine'))),
    'histograms': (('Data', ('marker', 'x_attr')), ('Distribution', ('bins', 'stat', 'combine'))),
    'ridgeline': (('Data', ('marker', 'x_attr')), ('Distribution', ('bw_adjust',))),
    'ecdf': (('Data', ('marker', 'x_attr')), ('Distribution', ('stat', 'complementary'))),
    'paired_ratio': (('Data', ('numerator_col', 'denominator_col')), ('Comparison', ('log_transform', 'ratio_test'))),
    'matrices': (('Data', ('data_cols',)), ('Association', ('correlation',))),
    'rect_matrices': (('Data', ('data_cols', 'against_data_cols')), ('Association', ('correlation', 'combine_conditions'))),
    'matrix_differences': (('Data', ('data_cols',)), ('Comparison', ('comparisons', 'correlation', 'difference_test'))),
    'group_matrix': (('Data', ('data_cols',)), ('Comparison', ('control',))),
    'model_result_matrix': (('Saved model', ('path',)), ('Matrix values', ('row_col', 'profile_col', 'value_col', 'p_col'))),
    'multivariable_regression_matrix': (('Data', ('data_cols', 'predictors')), ('Model', ('value', 'correction'))),
    'effect_forest': (('Data', ('data_cols',)), ('Comparison', ('control', 'effect_ci'))),
    'linear_model_coefficient_forest': (('Saved model', ('path',)), ('Coefficients', ('dependent_variables', 'terms', 'gate'))),
    'association_coefficients': (('Relationships', ('associations',)), ('Coefficients', ('value', 'reference'))),
    'correlation_contrast': (('Data', ('x', 'data_cols')), ('Comparison', ('test', 'reference', 'covariates'))),
    'coefficient_contrast': (('Data', ('x', 'data_cols')), ('Comparison', ('reference', 'covariates'))),
    'association_correlations': (('Relationships', ('associations',)), ('Association', ('test', 'reference'))),
    'volcano': (('Data', ('data_cols',)), ('Comparison', ('control', 'p_threshold'))),
    'pie_charts': (('Data', ('marker', 'x_attr')), ('Categories', ('threshold', 'plot_format'))),
    'combo_pies': (('Data', ('marker',)), ('Categories', ('family', 'plot_format', 'include_none'))),
    'category_counts': (('Data', ('category',)), ('Counts', ('kind', 'normalize'))),
    'coloc_upset': (('Data', ('marker',)), ('Overlap', ('include_neither', 'min_count'))),
    'coloc_sankey': (('Data', ('marker',)), ('Overlap', ('include_neither', 'min_count'))),
    'radar': (('Data', ('data_cols',)), ('Profile', ('statistic', 'normalize', 'combine'))),
    'marker_pca': (('Data', ('data_cols',)), ('Components', ('hue_column', 'standardize', 'n_components'))),
    'timecourse': (('Data', ('column', 'time_col', 'group_col')), ('Growth model', ('model',))),
    'cosinor': (('Data', ('column', 'time_col', 'group_col')), ('Rhythm', ('period', 'period_free'))),
    'acrophase_clock': (('Data', ('phase_col', 'group_col')), ('Rhythm', ('period',))),
    'images': (('Images', ('markers', 'subject_filter')), ('Layout', ('merge', 'scale_bar'))),
    'representative_images': (('Images', ('markers', 'subject_filter')), ('Layout', ('merge', 'scale_bar'))),
    'locations': (('Objects', ('objects',)), ('Layers', ('merge', 'colocalise', 'overlay_with_images'))),
    'baseline_characteristics': (('Data', ('columns', 'factor')), ('Table', ('include_all',))),
    'significance_audit_table': (('Saved results', ('path',)), ('Table', ('pvalue_cols', 'row_label_col', 'aesthetic'))),
    'condition_key': (('Group key', ('ncol',)),),
    'power_curve': (('Study', ('effect_sizes', 'n_range')), ('Power', ('test', 'alpha', 'target_powers'))),
    'group_comparison_pipeline': (('1 · Data', ('data_cols', 'control')), ('2 · Analysis', ('engine', 'screen', 'gate')),
                                  ('3 · Outputs', ('plot_volcano', 'plot_forest', 'plot_stats_matrix', 'plot_bars', 'plot_superplots'))),
    'data_overview_pipeline': (('1 · Data', ('data_cols',)), ('2 · Diagnostics', ('include_normality', 'include_outliers', 'include_covariation', 'include_significance_audit')),
                               ('3 · Outputs', ('plot_missingness', 'plot_group_counts', 'plot_descriptives', 'plot_scorecard'))),
    'correlation_pipeline': (('1 · Data', ('data_cols', 'against_data_cols')), ('2 · Analysis', ('tests', 'require', 'gate', 'alpha')),
                            ('3 · Outputs', ('max_regressions', 'plot_difference_matrices'))),
    'adjusted_correlation_pipeline': (('1 · Data', ('data_cols', 'candidate_covariates')), ('2 · Adjustment', ('covariates', 'covariate_gate', 'tests', 'require', 'gate')),
                                     ('3 · Outputs', ('max_adjusted_regressions',))),
    'linear_model_pipeline': (('1 · Data', ('dependent_variables', 'predictors', 'group')), ('2 · Model', ('categorical', 'reference_levels', 'interactions')),
                              ('3 · Outputs', ('plot_adjusted_means', 'plot_raw_values', 'plot_coefficients'))),
    'rhythm_pipeline': (('1 · Data', ('data_cols', 'time_col', 'group_col')), ('2 · Rhythm', ('period', 'period_free', 'method')),
                        ('3 · Inference', ('screen', 'gate', 'alpha'))),
    'iterative_model_sweep': (('1 · Data', ('target', 'possible_predictors')), ('2 · Search', ('max_features', 'model_preset', 'cv', 'scoring')),
                            ('3 · Outputs', ('top_n', 'plot'))),
}

TITLES = {
    'mean_bars': 'Group means & subject points', 'superplot': 'Subject & region spread',
    'regressions': 'Two-measurement relationship', 'scatter_3d': 'Three-measurement relationship',
    'histograms': 'Histogram', 'ridgeline': 'Ridgeline density', 'ecdf': 'Cumulative distribution',
    'paired_ratio': 'Paired change & ratios', 'matrices': 'Correlation matrix', 'rect_matrices': 'Two-set correlation matrix',
    'matrix_differences': 'Differences between correlation matrices', 'group_matrix': 'Group effect matrix',
    'model_result_matrix': 'Saved model-result matrix', 'multivariable_regression_matrix': 'Multivariable regression matrix',
    'effect_forest': 'Effect-size forest', 'linear_model_coefficient_forest': 'Saved coefficient forest',
    'linear_model_adjusted_means': 'Saved adjusted group means', 'association_coefficients': 'Adjusted association coefficients',
    'correlation_contrast': 'Correlation contrasts', 'coefficient_contrast': 'Coefficient contrasts',
    'association_correlations': 'Grouped association correlations', 'coloc_upset': 'Marker intersections',
    'coloc_sankey': 'Conditional marker flows', 'radar': 'Radar profile', 'marker_pca': 'Principal components',
    'acrophase_clock': 'Peak-phase clock', 'condition_key': 'Group colour & style key',
}

LABELS = {
    'data_cols': 'Measurements', 'against_data_cols': 'Measurements to compare against',
    'columns': 'Measurements', 'x': 'Horizontal measurement', 'y': 'Vertical measurement', 'z': 'Depth measurement',
    'x_attr': 'Object measurement', 'bins': 'Number of bins', 'stat': 'Vertical axis',
    'control': 'Compare against', 'reference': 'Reference group', 'engine': 'Method',
    'screen': 'Treat endpoints as an exploratory screen', 'gate': 'Significance uses', 'alpha': 'Significance threshold',
    'normalize_x': 'Horizontal scale', 'normalize_y': 'Vertical scale', 'normalize_z': 'Depth scale',
    'combine': 'Overlay groups in one figure', 'n_boot': 'Bootstrap repetitions',
    'plot_volcano': 'Volcano', 'plot_forest': 'Effect-size forest', 'plot_stats_matrix': 'Statistics matrix',
    'plot_bars': 'Per-measurement bars', 'plot_superplots': 'Subject & region points',
    'possible_predictors': 'Candidate predictors', 'time_col': 'Time column', 'group_col': 'Group column',
    'numerator_col': 'Numerator measurement', 'denominator_col': 'Denominator measurement',
}

CHOICES = {
    'engine': ('auto', 'mixed', 'bootstrap'), 'gate': ('p', 'fdr'),
    'require': ('and', 'or'), 'covariate_gate': ('p', 'fdr'),
    'stats_test': fc.CHOICES['stats_test'], 'correlation': fc.CHOICES['correlation'],
    'normalize_x': (False, True, 'Z-score'), 'normalize_y': (False, True, 'Z-score'), 'normalize_z': (False, True, 'Z-score'),
}

VALUE_LABELS = {
    'auto': 'Automatic (default)', 'pearsonr': 'Pearson correlation', 'spearmanr': 'Spearman correlation',
    'kendalltau': 'Kendall correlation', 'mixed': 'Mixed model · region data', 'bootstrap': 'Hierarchical bootstrap',
    'p': 'Raw p-values', 'fdr': 'False-discovery-rate q-values', 'count': 'Object count',
    'probability': 'Probability', 'density': 'Density', 'proportion': 'Proportion',
    'student_t': "Student's t-test", 'welch_t': "Welch's t-test", 'mannwhitney': 'Mann–Whitney',
    'anova': 'One-way analysis of variance', 'welch_anova': 'Welch analysis of variance', 'kruskal': 'Kruskal–Wallis',
    'and': 'All selected tests agree', 'or': 'Any selected test',
}


def home(action):
    return next(h for h in HOMES if action in h.actions)


def title(contract):
    return TITLES.get(contract.entry.action, contract.title)


def primary_names(action):
    return tuple(name for _, names in SECTIONS[action] for name in names)


def field(contract, original):
    """Add only presentation facts, retaining the source parameter object."""
    name = original.name
    role, choices = original.role, original.choices
    if name in CHOICES:
        role, choices = 'choice', CHOICES[name]
    if name in {'control', 'reference', 'audit_control', 'effect_control'}:
        role = 'group'
    if name in {'normalize_x', 'normalize_y', 'normalize_z'}:
        role, choices = 'choice', CHOICES[name]
    if name == 'stat' and contract.entry.action == 'histograms':
        role, choices = 'choice', ('count', 'probability', 'density', 'percent', 'frequency')
    if name == 'stat' and contract.entry.action == 'ecdf':
        role, choices = 'choice', ('proportion', 'count')
    label=LABELS.get(name, original.label)
    if name=='alpha' and contract.entry.action in {'histograms','ridgeline','ecdf','radar'}:
        label='Opacity'
    return replace(original, role=role, choices=choices, label=label)


def value_label(field_, value):
    if field_.name.startswith('normalize_'):
        return 'Original units' if value is False else '0–1 normalized'+(' (default)' if fc.default_value(field_.parameter) is True else '') if value is True else 'Z-scores' if value == 'Z-score' else str(value)
    return VALUE_LABELS.get(str(value), str(value))


def unit(action, values=None):
    values = values or {}
    if action in {'histograms', 'ridgeline', 'ecdf', 'pie_charts', 'combo_pies', 'coloc_upset', 'coloc_sankey'}:
        return 'Observations: individual segmented objects.'
    if action == 'superplot':
        return 'Region-level points are nested within subjects; subject means remain separate.'
    if action in {'images', 'representative_images', 'locations'}:
        return 'Recorded images and object locations from this dataset.'
    if action in {'model_result_matrix', 'linear_model_adjusted_means', 'linear_model_coefficient_forest', 'significance_audit_table'}:
        return 'Reads a saved results table; no model is fitted by this view.'
    if action == 'group_comparison_pipeline':
        return 'Subjects are the independent units. Automatic selects a supported method from the available subject and region data; any fallback is recorded.'
    if action == 'power_curve':
        return 'Study-planning inputs; no subject measurements are required.'
    return 'Observations: subject-level summary measurements.'


def validate_map(contracts=None):
    contracts = fc.catalogue_contracts() if contracts is None else contracts
    owners = {c.entry.action: c for c in contracts}
    declared = [a for h in HOMES for a in h.actions]
    issues = []
    if set(declared) != set(owners) or len(declared) != len(set(declared)) or set(SECTIONS) != set(owners):
        issues.append('Every registered action must have exactly one picture home and explicit input sections.')
    for action, contract in owners.items():
        if action not in SECTIONS:
            continue
        fields = {f.name: f for f in contract.fields}
        names = primary_names(action)
        if len(names) != len(set(names)) or set(names) - fields.keys():
            issues.append(f'{action}: input sections repeat or name unsupported fields.')
        unassigned = [f.name for f in contract.fields if f.parameter.required and f.role not in {'bound', 'managed', 'alias', 'object'} and f.name not in names]
        if unassigned:
            issues.append(f'{action}: required inputs lack task roles: {unassigned}.')
    return issues


@lru_cache(maxsize=1)
def checked_homes():
    issues = validate_map()
    if issues:
        raise ValueError(' '.join(issues))
    return HOMES


def argument_locations(contract):
    """Account for each source field without duplicating its default."""
    primary = {n: section for section, names in SECTIONS[contract.entry.action] for n in names}
    return {f.name: f.role if f.role in {'bound', 'managed', 'alias', 'object'} else
            primary.get(f.name, 'Appearance' if is_appearance(contract,f) else 'Advanced') for f in contract.fields}


def is_appearance(contract,field_):
    return field_.name in fc.APPEARANCE or (field_.name=='alpha' and contract.entry.action in {'histograms','ridgeline','ecdf','radar'})
