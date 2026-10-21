"""Run explicit per-animal/participant panel tests through PyFLASH.stats APIs.

Inputs: summary CSV/trusted Batch pickle and JSON panel specifications. Outputs:
panel_statistics.csv, group_summary.csv, complete_cases.csv and receipt. No
automatic outlier detection or figures. Mixed ANOVA/Kruskal-Wallis legends and
Dunn corrections require the approved original per-panel choices in the JSON.
"""
import argparse
import json
from pathlib import Path
from common import compare_reference, load_summary, require_columns, run_output


def analyze(frame, jobs, subject='AnimalName'):
    import numpy as np
    import pandas as pd
    from scipy import stats
    from PyFLASH.stats import runOWA, runKW
    output, summaries, used = [], [], []
    if not jobs or len({job['panel'] for job in jobs}) != len(jobs):
        raise ValueError('Provide at least one uniquely named panel.')
    for job in jobs:
        panel, column, group_column = job['panel'], job['column'], job['group_column']
        groups, method = job['groups'], job['method']
        if method not in {'anova_tukey', 'kruskal_dunn'}:
            raise ValueError(f'{panel}: choose anova_tukey or kruskal_dunn explicitly.')
        if 'exclude_subjects' not in job:
            raise ValueError(f'{panel}: explicitly provide the approved exclude_subjects list (can be empty).')
        require_columns(frame, [subject, column, group_column, *job.get('filter', {})])
        cohort = frame.copy()
        for name, values in job.get('filter', {}).items():
            cohort = cohort.loc[cohort[name].isin(values if isinstance(values, list) else [values])]
        exclusions = [str(value) for value in job['exclude_subjects']]
        unknown = set(exclusions) - set(cohort[subject].astype(str))
        if unknown:
            raise ValueError(f'{panel}: excluded identifiers are absent: {sorted(unknown)}')
        cohort = cohort.loc[~cohort[subject].astype(str).isin(exclusions) & cohort[group_column].isin(groups)]
        cohort[column] = pd.to_numeric(cohort[column], errors='coerce')
        transform = job.get('transform', 'identity')
        if transform == 'reciprocal':
            cohort[column] = 1.0 / cohort[column]
        elif transform != 'identity':
            raise ValueError(f'{panel}: unsupported transform {transform}')
        cohort = cohort.loc[np.isfinite(cohort[column])]
        if cohort[subject].isna().any() or cohort[subject].duplicated().any():
            raise ValueError(f'{panel}: expected one row per animal/participant, not repeated regions.')
        samples = [cohort.loc[cohort[group_column].eq(group), column].to_numpy() for group in groups]
        if len(groups) < 2 or len(set(groups)) != len(groups) or any(len(sample) < 3 for sample in samples):
            raise ValueError(f'{panel}: provide distinct groups with at least three complete subjects each.')
        pairs = job.get('comparisons')
        if not pairs:
            raise ValueError(f'{panel}: explicitly provide the original comparisons, e.g. ["1-2","1-3"].')
        for token in pairs:
            a, b = [int(i) for i in token.split('-')]
            if not (1 <= a <= len(groups) and 1 <= b <= len(groups)) or a == b:
                raise ValueError(f'{panel}: invalid comparison {token}')
        if 'expected_n' in job and [len(sample) for sample in samples] != job['expected_n']:
            raise ValueError(f'{panel}: complete-case counts differ from expected_n.')
        audit = {}
        if method == 'anova_tukey':
            result = runOWA(samples, pairs, audit, posthoc='Tukey', posthoc_correction='none')
        else:
            correction = job.get('dunn_correction')
            if not correction or correction == 'auto':
                raise ValueError(f'{panel}: name the original Dunn multiplicity correction explicitly.')
            result = runKW(samples, pairs, audit, posthoc='Dunn', posthoc_correction=correction)
        pvalues, _, omnibus, _, posthoc = result
        if len(pvalues) != len(pairs) or not np.isfinite(omnibus).all() or not np.isfinite(pvalues).all():
            raise ValueError(f'{panel}: statistical test did not produce finite results: {audit}')
        output.append({'panel': panel, 'column': column, 'test': method,
                       'transform': transform,
                       'comparison': 'omnibus', 'statistic': omnibus[0], 'p': omnibus[1],
                       'posthoc': posthoc})
        for token, p in zip(pairs, pvalues):
            output.append({'panel': panel, 'column': column, 'test': method,
                           'transform': transform,
                           'comparison': token, 'statistic': np.nan, 'p': p, 'posthoc': posthoc})
        for group, sample in zip(groups, samples):
            summaries.append({'panel': panel, 'group': group, 'n': len(sample),
                              'mean': np.mean(sample), 'sem': stats.sem(sample),
                              'shapiro_p': stats.shapiro(sample).pvalue})
        used.extend({'panel': panel, 'subject': row[subject], 'group': row[group_column], 'value': row[column]}
                    for _, row in cohort.iterrows())
    return pd.DataFrame(output), pd.DataFrame(summaries), pd.DataFrame(used)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--panels', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--subject-column', default='AnimalName')
    parser.add_argument('--reference', type=Path, help='Approved original panel_statistics.csv to compare')
    args = parser.parse_args()
    jobs = json.loads(args.panels.read_text(encoding='utf-8'))['panels']
    frame = load_summary(args.input)
    with run_output(args.out, inputs=[args.input, args.panels], parameters=vars(args)) as receipt:
        results, groups, used = analyze(frame, jobs, args.subject_column)
        for name, table in [('panel_statistics.csv', results), ('group_summary.csv', groups), ('complete_cases.csv', used)]:
            table.to_csv(args.out / name, index=False)
        if args.reference:
            compare_reference(results, args.reference)
        receipt['reference_comparison'] = 'passed' if args.reference else 'not supplied'
        print('Panel statistics complete; complete-case subjects recorded.')


if __name__ == '__main__':
    main()
