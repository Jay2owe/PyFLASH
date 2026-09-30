"""Rerun manuscript human coefficient and correlation methods using PyFLASH APIs.

Inputs: participant-level summary CSV or trusted Batch pickle. Outputs: Fig1H
coefficient/bootstrap and directional-test CSVs, Fig1I raw/adjusted Spearman
CSV, cohort counts and receipt. No figures are saved. See README.md for the
distinction between a methods reconstruction and a verified original rerun.
"""
import argparse
from pathlib import Path
from common import compare_reference, exclude_device_failure, load_summary, require_columns, run_output

GROUPS = ['Control', 'MCI', 'AD']
DEFAULT_VOLUME = 'Volumeanterior-inferiorHT'
DEFAULT_M10 = 'Avgactivityactivephase(M10)'
DEFAULT_ACTIVITY = ['Avgactivityactivephase(M10)', 'Avgactivityrestingphase(L5)',
                    'Alphacounts(day)', 'Rhocounts(night)', 'Amplitude',
                    'morningpeakamplitude', 'Eveningpeakamplitude']


def coefficients(frame, *, volume=DEFAULT_VOLUME, m10=DEFAULT_M10, subject='AnimalName', bootstrap=10000, seed=20260930,
                 definition='manuscript_methods'):
    import matplotlib.pyplot as plt
    import pandas as pd
    from PyFLASH.plotting import plot_association_coefficients
    from PyFLASH.stats import interaction_slope_difference
    if definition not in {'manuscript_methods', 'submitted_figure'}:
        raise ValueError('Unknown coefficient definition.')
    # The displayed age coefficients match the unadjusted model, while the
    # written manuscript formula includes sex. Preserve both explicitly.
    age_covariates = ['Sex'] if definition == 'manuscript_methods' else []
    specifications = {'Age-volume': {'x': 'Age', 'y': volume, 'covariates': age_covariates},
                      'Volume-M10': {'x': volume, 'y': m10, 'covariates': ['Age', 'Sex']}}
    tables, tests = [], []
    counts = {}
    for label, spec in specifications.items():
        cohort = frame[['Diagnosis', subject, spec['x'], spec['y'], *spec['covariates']]].copy()
        for column in [spec['x'], spec['y'], *[c for c in spec['covariates'] if c != 'Sex']]:
            cohort[column] = pd.to_numeric(cohort[column], errors='coerce')
        cohort = cohort.replace([float('inf'), -float('inf')], float('nan')).dropna()
        counts[label] = cohort['Diagnosis'].value_counts().to_dict()
        # Separate calls preserve model-specific cohorts; a joint call enforces
        # common complete cases across the two models, which the PDF does not request.
        result = plot_association_coefficients(cohort, associations={label: spec},
                    factor='Diagnosis', group_col='Diagnosis', subject_col=subject,
                    group_order=GROUPS, reference='Control', value='beta', ci_method='bootstrap',
                    ci_alpha=0.05, bootstrap_resamples=bootstrap, random_state=seed,
                    min_n=4, save=False, return_data=True, show_stats_summary=False)
        tables.append(result['coefficients'])
        plt.close(result['figure'])
        for other in GROUPS[1:]:
            pair = cohort.loc[cohort['Diagnosis'].isin(['Control', other])].reset_index(drop=True)
            test = interaction_slope_difference(pair[spec['x']], pair[spec['y']], pair['Diagnosis'],
                      reference='Control', covariates=pair[spec['covariates']],
                      tail='less', standardize=True, rank=False)
            if not pd.notna(test['p']):
                raise ValueError(f'Cannot fit directional {label} Control versus {other} test.')
            tests.append({'association': label, 'alternative': 'patient slope < control slope', **test})
    return pd.concat(tables, ignore_index=True), pd.DataFrame(tests), counts


def correlations(frame, *, volume=DEFAULT_VOLUME, activity=DEFAULT_ACTIVITY, subject='AnimalName', bootstrap=100, seed=20260930):
    import matplotlib.pyplot as plt
    import pandas as pd
    from PyFLASH.plotting import plot_association_correlations
    tables = []
    # Each metric retains its own complete cases, and covariates enter on the
    # raw scale before residual Spearman correlation (Methods p39).
    for metric in activity:
        for mode, covariates in [('Raw', []), ('AgeSexAdjusted', ['Age', 'Sex'])]:
            columns = list(dict.fromkeys(['Diagnosis', subject, volume, metric, *covariates]))
            cohort = frame[columns].copy()
            for column in [volume, metric, *[c for c in covariates if c != 'Sex']]:
                cohort[column] = pd.to_numeric(cohort[column], errors='coerce')
            cohort = cohort.replace([float('inf'), -float('inf')], float('nan')).dropna()
            result = plot_association_correlations(cohort,
                       associations={metric: {'x': volume, 'y': metric, 'covariates': covariates}},
                       factor='Diagnosis', group_col='Diagnosis', subject_col=subject,
                       group_order=GROUPS, reference='Control', test='spearmanr',
                       covariate_adjustment='residual_then_correlation', ci_method='bootstrap',
                       ci_alpha=0.05, bootstrap_resamples=bootstrap, random_state=seed,
                       min_n=4, save=False, return_data=True, show_stats_summary=False)
            table = result['correlations'].copy()
            table.insert(0, 'adjustment', mode)
            tables.append(table)
            plt.close(result['figure'])
    return pd.concat(tables, ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--stage', choices=['coefficients', 'correlations', 'both'], default='both')
    parser.add_argument('--subject-column', default='AnimalName')
    parser.add_argument('--volume-column', default=DEFAULT_VOLUME)
    parser.add_argument('--m10-column', default=DEFAULT_M10)
    parser.add_argument('--activity-columns', nargs='+', default=DEFAULT_ACTIVITY)
    parser.add_argument('--bootstrap', type=int, default=10000)
    parser.add_argument('--coefficient-definition', choices=['manuscript_methods', 'submitted_figure'],
                        default='manuscript_methods', help='Methods adjust age-volume for sex; displayed figure matches the unadjusted age model')
    parser.add_argument('--correlation-bootstrap', type=int, default=100,
                        help='Additional diagnostic intervals only; nominal correlation P values do not use these resamples')
    parser.add_argument('--seed', type=int, default=20260930,
                        help='Explicit reconstruction seed; the manuscript does not state its original seed')
    parser.add_argument('--reference-dir', type=Path, help='Approved original CSVs with the same columns and ordering')
    parser.add_argument('--paper-device-failure-subject', help='Confirmed AnimalName excluded from every analysis after device failure')
    args = parser.parse_args()
    if args.bootstrap < 100:
        parser.error('--bootstrap must be at least 100 (10000 for the manuscript).')
    if args.correlation_bootstrap < 100:
        parser.error('--correlation-bootstrap must be at least 100.')
    import matplotlib
    matplotlib.use('Agg')
    frame = load_summary(args.input)
    required = ['Diagnosis', 'Sex', 'Age', args.volume_column, args.subject_column]
    if args.stage != 'correlations':
        required += [args.m10_column]
    if args.stage != 'coefficients':
        required += args.activity_columns
    require_columns(frame, required)
    unknown = set(frame['Diagnosis'].dropna()) - set(GROUPS)
    if unknown:
        parser.error(f'Diagnosis must use Control/MCI/AD; unexpected labels: {sorted(unknown)}')
    if frame[args.subject_column].isna().any() or frame[args.subject_column].duplicated().any():
        parser.error('Input must have one uniquely identified row per participant.')
    unexpected_sex = set(frame['Sex'].dropna()) - {'Female', 'Male'}
    if unexpected_sex:
        parser.error(f'Sex must use Female/Male; unexpected labels: {sorted(unexpected_sex)}')
    frame = exclude_device_failure(frame, args.subject_column, args.paper_device_failure_subject)
    with run_output(args.out, inputs=[args.input], parameters=vars(args)) as receipt:
        output = args.out.resolve()
        files = {}
        if args.stage != 'correlations':
            beta, directional, counts = coefficients(frame, volume=args.volume_column, m10=args.m10_column,
                       subject=args.subject_column, bootstrap=args.bootstrap, seed=args.seed,
                       definition=args.coefficient_definition)
            files.update({'fig1H_coefficients.csv': beta, 'fig1H_directional_tests.csv': directional})
            receipt['cohort_counts'] = counts
        if args.stage != 'coefficients':
            files['fig1I_correlations.csv'] = correlations(frame, volume=args.volume_column,
                         activity=args.activity_columns, subject=args.subject_column,
                         bootstrap=args.correlation_bootstrap, seed=args.seed)
        for name, table in files.items():
            table.to_csv(output / name, index=False)
            if args.reference_dir:
                compare_reference(table, args.reference_dir / name)
        receipt['reference_comparison'] = 'passed' if args.reference_dir else 'not supplied'
        receipt['participant_rows'] = len(frame)
        receipt['device_failure_exclusion_applied'] = bool(args.paper_device_failure_subject)
        receipt['device_failure_identity_basis'] = 'Caller-supplied identifier; no device incident log checked' if args.paper_device_failure_subject else 'No extra device exclusion applied to the source batch'
        print('Human association tables complete:', ', '.join(files))


if __name__ == '__main__':
    main()
