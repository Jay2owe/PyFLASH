"""Check Figure 1H/I estimates against the supplied manuscript's displayed values.

This checks rounded annotations only, not original confidence intervals,
underlying precision, exclusions, or every figure. Output records discrepancies
and the command exits unsuccessfully when any annotation differs.
"""
import argparse
import json
from pathlib import Path
from common import run_output


def compare(coefficients, correlations, reference):
    import pandas as pd
    rows = []
    def append(figure, association, group, adjustment, expected, table):
        if len(table) != 1:
            raise ValueError(f'Expected exactly one {figure}/{association}/{group}/{adjustment} estimate.')
        observed = float(table.iloc[0]['estimate'])
        rounded = round(observed, reference['precision'])
        rows.append({'figure':figure, 'association':association, 'group':group, 'adjustment':adjustment,
                     'expected_display':expected, 'rerun_estimate':observed, 'rerun_display':rounded,
                     'matches_display':rounded == expected})
    for association, groups in reference['coefficients'].items():
        for group, expected in groups.items():
            selected = coefficients.loc[coefficients.association.eq(association) & coefficients.group.eq(group)]
            append('Fig1H',association,group,'coefficient',expected,selected)
    for association, groups in reference['spearman'].items():
        for group, expected in groups.items():
            for adjustment, value in zip(['Raw','AgeSexAdjusted'],expected):
                selected = correlations.loc[correlations.association.eq(association) & correlations.group.eq(group) & correlations.adjustment.eq(adjustment)]
                append('Fig1I',association,group,adjustment,value,selected)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True, help='Script 02 output directory')
    parser.add_argument('--coefficient-results', type=Path, help='Optional separately recorded script 02 coefficient-mode output; must use the same input and exclusion')
    parser.add_argument('--reference', type=Path, default=Path(__file__).with_name('manuscript_annotations.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    import pandas as pd
    coefficient_root = args.coefficient_results or args.results
    if args.coefficient_results:
        first = json.loads((args.results/'run_receipt.json').read_text(encoding='utf-8'))
        second = json.loads((coefficient_root/'run_receipt.json').read_text(encoding='utf-8'))
        if first['status'] != 'passed' or second['status'] != 'passed' or first['input_sha256'] != second['input_sha256'] or first['parameters'].get('paper_device_failure_subject') != second['parameters'].get('paper_device_failure_subject'):
            parser.error('Both recorded runs must have passed using identical input hashes and device exclusions.')
    beta = coefficient_root/'fig1H_coefficients.csv'
    rho = args.results/'fig1I_correlations.csv'
    with run_output(args.out, inputs=[beta,rho,args.reference], parameters=vars(args)) as receipt:
        table = compare(pd.read_csv(beta),pd.read_csv(rho),json.loads(args.reference.read_text(encoding='utf-8')))
        table.to_csv(args.out/'annotation_comparison.csv',index=False)
        receipt['matched_annotations'] = int(table.matches_display.sum())
        receipt['total_annotations'] = len(table)
        receipt['claim'] = 'Agreement of rounded Figure 1H/I annotations only; original bootstrap intervals and all paper results are not certified.'
        mismatches = len(table) - receipt['matched_annotations']
        print(f"Matched {receipt['matched_annotations']}/{len(table)} displayed annotations.")
        if mismatches:
            raise AssertionError(f'{mismatches} manuscript annotations differ; see annotation_comparison.csv.')


if __name__ == '__main__':
    main()
