"""Explicit grouped Pearson associations and OLS fits for Fig1G/Fig3L-O.

The JSON jobs must name the original groups, columns, filters and exclusions.
Numerical output only. Public PyFLASH correlation and linear-model APIs are
used; plot objects returned by the correlation API are closed without saving.
"""
import argparse
import json
from pathlib import Path
from common import load_summary, require_columns, run_output


def analyze(frame, jobs, subject='AnimalName', bootstrap=100, seed=20260930):
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from PyFLASH.plotting import plot_association_correlations
    from PyFLASH.pipeline import linear_model
    tables = {'correlations':[], 'regression_coefficients':[], 'complete_cases':[]}
    for job in jobs:
        label, x, y, grouping = job['name'], job['x'], job['y'], job['group_column']
        groups = job['groups']
        require_columns(frame, [subject, x, y, grouping, *job.get('filter', {})])
        if 'exclude_subjects' not in job:
            raise ValueError('Explicitly provide exclude_subjects, including an empty list.')
        cohort = frame.copy()
        for name, values in job.get('filter', {}).items():
            cohort = cohort.loc[cohort[name].isin(values if isinstance(values, list) else [values])]
        exclude = [str(value) for value in job['exclude_subjects']]
        if set(exclude) - set(cohort[subject].astype(str)):
            raise ValueError(f'{label}: excluded identifiers are absent.')
        cohort = cohort.loc[cohort[grouping].isin(groups) & ~cohort[subject].astype(str).isin(exclude)]
        for column in [x,y]:
            cohort[column] = pd.to_numeric(cohort[column], errors='coerce')
        cohort = cohort.loc[np.isfinite(cohort[x]) & np.isfinite(cohort[y])].copy()
        if cohort[subject].isna().any() or cohort[subject].duplicated().any():
            raise ValueError(f'{label}: expected one independent row per subject.')
        result = plot_association_correlations(cohort, associations={label:{'x':x,'y':y,'covariates':[]}},
                    factor=grouping, group_col=grouping, subject_col=subject, group_order=groups,
                    reference=groups[0], test='pearsonr', min_n=4, bootstrap_resamples=bootstrap,
                    random_state=seed, save=False, return_data=True, show_stats_summary=False)
        # Bootstrap intervals are an API diagnostic, not a claimed manuscript
        # interval. The paper's association result is the nominal Pearson r/P.
        tables['correlations'].append(result['correlations'])
        plt.close(result['figure'])
        for group in groups:
            one_group = cohort.loc[cohort[grouping].eq(group)].copy()
            fitted = linear_model(one_group, dependent_variables=[y], predictors=[x],
                        subject_col=subject, categorical=[], cov_type=None, adjusted_means=False,
                        plot_adjusted_means=False, plot_raw_values=False, plot_coefficients=False,
                        save=False, write_manifest=False, montage=False, verbose=False)
            coefficients = fitted['coefficients'].copy()
            coefficients.insert(0, 'paper_group', group)
            coefficients.insert(0, 'association', label)
            tables['regression_coefficients'].append(coefficients)
        used = cohort[[subject, grouping, x,y]].copy()
        used.insert(0, 'association', label)
        tables['complete_cases'].append(used)
    if not jobs:
        raise ValueError('Provide at least one approved association job.')
    return {name:pd.concat(values, ignore_index=True) for name,values in tables.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--jobs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--subject-column', default='AnimalName')
    parser.add_argument('--bootstrap', type=int, default=100, help='Diagnostic correlation intervals only; paper r/P do not use these intervals')
    parser.add_argument('--seed', type=int, default=20260930)
    args = parser.parse_args()
    if args.bootstrap < 100:
        parser.error('--bootstrap must be at least 100.')
    import matplotlib
    matplotlib.use('Agg')
    frame = load_summary(args.input)
    jobs = json.loads(args.jobs.read_text(encoding='utf-8'))['associations']
    with run_output(args.out, inputs=[args.input,args.jobs], parameters=vars(args)):
        for name,table in analyze(frame, jobs, args.subject_column, args.bootstrap,args.seed).items():
            table.to_csv(args.out/f'grouped_{name}.csv', index=False)
        print('Grouped correlation and regression tables complete.')


if __name__ == '__main__':
    main()
