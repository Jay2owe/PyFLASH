"""Complete contingency-table outputs from native R and exact count mathematics."""
from __future__ import annotations
from fractions import Fraction
import json
import math
from pathlib import Path
from reproducibility.reference_runtime import execute_queries, values

FIXTURE = Path(__file__).with_name('fixtures') / 'proportion_contract_reference.json'


def cases():
    tables = [((12,4),(3,11)), ((1,7),(9,1)), ((0,5),(5,0)), ((5,0),(0,5)),
              ((1,9),(11,3)), ((4,4),(4,4)), ((12,8,4),(6,12,9)), ((1,2,4),(4,2,1),(3,2,2))]
    return [{'key':f'proportion.{index}.{force or "auto"}',
             'capability':'PyFLASH.stats_extra.proportion_test',
             'parameters':{'table':[list(row) for row in table], 'force':force}}
            for index, table in enumerate(tables) for force in (None,'chi2','fisher')]


def r_query(row):
    params = row['parameters']
    table = params['table']
    counts = ','.join(str(value) for line in table for value in line)
    force = 'NULL' if params['force'] is None else json.dumps(params['force'])
    return (f'local({{x <- matrix(c({counts}), nrow={len(table)}, byrow=TRUE); force <- {force}; '
        'expected <- outer(rowSums(x), colSums(x))/sum(x); two <- all(dim(x)==2); '
        'use_fisher <- two && (identical(force,"fisher") || (is.null(force) && min(expected)<5)); '
        'if (use_fisher) {answer <- fisher.test(x, alternative="two.sided"); '
        'odds <- (x[1,1]*x[2,2])/(x[1,2]*x[2,1]); '
        'c(1, odds, unname(answer$p.value), NaN, as.vector(t(expected)))} '
        'else {answer <- suppressWarnings(chisq.test(x, correct=two)); '
        'c(0, unname(answer$statistic), unname(answer$p.value), unname(answer$parameter), as.vector(t(expected)))}})')


def mathematical(row):
    import mpmath as mp
    table = row['parameters']['table']
    rows, columns = len(table), len(table[0])
    row_sums = [sum(line) for line in table]
    column_sums = [sum(table[i][j] for i in range(rows)) for j in range(columns)]
    total = sum(row_sums)
    expected = [[Fraction(row_sums[i]*column_sums[j], total) for j in range(columns)] for i in range(rows)]
    two = rows == columns == 2
    force = row['parameters']['force']
    fisher = two and (force == 'fisher' or force is None and min(value for line in expected for value in line) < 5)
    if fisher:
        a,b = table[0]
        c,d = table[1]
        odds = float(Fraction(a*d,b*c)) if b*c else math.inf if a*d else math.nan
        denominator = math.comb(total,row_sums[0])
        def probability(value):
            return Fraction(math.comb(column_sums[0],value)*math.comb(column_sums[1],row_sums[0]-value),denominator)
        observed = probability(a)
        possible = range(max(0,row_sums[0]-column_sums[1]),min(row_sums[0],column_sums[0])+1)
        p_value = sum((probability(value) for value in possible if probability(value) <= observed), Fraction())
        statistic, p, dof = odds, float(p_value), math.nan
    else:
        statistic = Fraction()
        for i in range(rows):
            for j in range(columns):
                difference = abs(Fraction(table[i][j])-expected[i][j])
                if two:
                    difference = max(Fraction(),difference-Fraction(1,2))
                statistic += difference*difference/expected[i][j]
        dof = (rows-1)*(columns-1)
        with mp.workdps(80):
            chi2 = mp.mpf(statistic.numerator)/statistic.denominator
            p = float(mp.gammainc(mp.mpf(dof)/2,chi2/2,mp.inf)/mp.gamma(mp.mpf(dof)/2))
        statistic = float(statistic)
    return [int(fisher),statistic,p,dof]+[float(value) for line in expected for value in line]


def production(row):
    from PyFLASH.stats_extra import proportion_test
    result = proportion_test(**row['parameters'])
    return [int(result['test'] == 'Fisher exact'),result['statistic'],result['p_value'],
            math.nan if result['dof'] is None else result['dof']]+result['expected'].ravel().tolist()


def execute(output):
    return execute_queries([{**row,'code':r_query(row)} for row in cases()],output,name='proportion')


def freeze(output, reason):
    if FIXTURE.exists() or not reason.strip():
        raise ValueError('Preserve existing references; a scientific reason is required.')
    result = execute(output)
    for row in result['rows']:
        answer = mathematical(row)
        row['mathematical_values'] = [value if math.isfinite(value) else None for value in answer]
        row['mathematical_nonfinite'] = ['nan' if math.isnan(value) else 'positive_infinity' if value == math.inf
                                        else 'negative_infinity' if value == -math.inf else None for value in answer]
    result.update(schema_version=1, reason=reason,
        conventions='Native R p-values; Pearson/Yates chi-square; Fisher two-sided probability ordering; sample cross-product odds (not R conditional maximum-likelihood odds). Automatic Fisher only for 2x2 expected counts below 5.',
        fields=['test_is_fisher','statistic','p_value','dof','expected_counts_row_major'],
        sources=['https://stat.ethz.ch/R-manual/R-devel/library/stats/html/chisq.test.html',
                 'https://stat.ethz.ch/R-manual/R-devel/library/stats/html/fisher.test.html'])
    FIXTURE.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reason',required=True)
    freeze(**vars(parser.parse_args()))
