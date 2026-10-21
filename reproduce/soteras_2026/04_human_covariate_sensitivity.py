"""Rerun the human reference-grid covariate sensitivity method (Methods p39).

Input: approved participant summary and JSON profiles naming outcomes and
covariates. Output: estimated marginal means, conventional OLS coefficients,
two-sided uncorrected contrasts and a receipt. Numerical tables only; no
figures. Profile/outcome selections must come from the original analysis.
"""
import argparse
import json
from pathlib import Path
from common import exclude_device_failure, load_summary, require_columns, run_output


def analyze(frame, profiles, subject='AnimalName'):
    import pandas as pd
    from PyFLASH.pipeline import linear_model
    if not profiles:
        raise ValueError('Supply the original covariate profiles.')
    outputs = {'coefficients': [], 'means': [], 'contrasts': []}
    for profile in profiles:
        name, outcomes, covariates = profile['name'], profile['outcomes'], profile['covariates']
        categorical = profile.get('categorical', ['Sex'])
        require_columns(frame, [subject, 'Diagnosis', *outcomes, *covariates])
        result = linear_model(frame, dependent_variables=outcomes, predictors=covariates,
                   group='Diagnosis', group_col='Diagnosis', subject_col=subject,
                   categorical=['Diagnosis', *[c for c in categorical if c in covariates]],
                   reference_levels={'Diagnosis': 'Control'}, cov_type=None,
                   adjusted_means=True, covariate_profile='reference_grid',
                   adjusted_mean_weights='equal', adjusted_mean_p_adjust='none',
                   plot_adjusted_means=False, plot_raw_values=False, plot_coefficients=False,
                   save=False, write_manifest=False, montage=False, verbose=False)
        for key, source in [('coefficients', 'coefficients'), ('means', 'adjusted_means_table'),
                            ('contrasts', 'adjusted_mean_comparisons')]:
            table = result[source].copy()
            table.insert(0, 'profile', name)
            outputs[key].append(table)
    return {key: pd.concat(tables, ignore_index=True) for key, tables in outputs.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--profiles', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--subject-column', default='AnimalName')
    parser.add_argument('--paper-device-failure-subject')
    args = parser.parse_args()
    frame = load_summary(args.input)
    if frame[args.subject_column].isna().any() or frame[args.subject_column].duplicated().any():
        parser.error('Expected one uniquely identified row per participant.')
    frame = exclude_device_failure(frame, args.subject_column, args.paper_device_failure_subject)
    profiles = json.loads(args.profiles.read_text(encoding='utf-8'))['profiles']
    with run_output(args.out, inputs=[args.input, args.profiles], parameters=vars(args)):
        for name, table in analyze(frame, profiles, args.subject_column).items():
            table.to_csv(args.out / f'sensitivity_{name}.csv', index=False)
        print('Covariate sensitivity tables complete.')


if __name__ == '__main__':
    main()
