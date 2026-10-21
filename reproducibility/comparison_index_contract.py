"""Literal relational checks for the one-based pair-result extraction contract.

These are functional table-selection checks, not a statistical reference.
Each pair's expected row/column is recorded separately from its display token.
"""
import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).with_name('fixtures')/'comparison_index_reference.json'
CAPABILITY = 'PyFLASH.stats.extract_p_and_stats_from_results'


def cases():
    rows = []
    def add(parameters, selected=None):
        rows.append({'key':f'comparison-index.{len(rows)}', 'capability':CAPABILITY,
                     'parameters':parameters, 'selected':selected})
    for size in (1,2,3,5):
        for pairs in ([], [(i,j) for i in range(size) for j in range(size)],
                      [(size-1,0),(0,size-1),(size-1,0)]):
            add({'size':size, 'comparisons':[f'{i+1}-{j+1}' for i,j in pairs]}, pairs)
    add({'size':3, 'comparisons':[' 1 - 3 ','03-02']}, [(0,2),(2,1)])
    for token in ('0-2','2-0','4-1','1-4','-1-2','1.5-2','1-2-3','A-B','1',None,3,'+1-2'):
        add({'size':3, 'comparisons':[token]})
    for shape in ('one-dimensional','different-shapes','rectangular'):
        add({'size':3,'comparisons':['1-2'],'shape':shape})
    return rows


def matrices(parameters):
    size = parameters['size']
    return ([[10*(i+1)+(j+1)+.25 for j in range(size)] for i in range(size)],
            [[(size*i+j+1)/(size*size+1) for j in range(size)] for i in range(size)])


def reference(row):
    if row['selected'] is None:
        return [1]
    import sqlite3
    statistic, probability = matrices(row['parameters'])
    with sqlite3.connect(':memory:') as store:
        store.execute('CREATE TABLE answers (row_index INTEGER, col_index INTEGER, statistic REAL, probability REAL)')
        store.executemany('INSERT INTO answers VALUES (?,?,?,?)',
            [(i,j,statistic[i][j],probability[i][j]) for i in range(len(statistic)) for j in range(len(statistic))])
        selected = [store.execute('SELECT statistic,probability FROM answers WHERE row_index=? AND col_index=?', pair).fetchone()
                    for pair in row['selected']]
    return [0,len(selected)]+[value[0] for value in selected]+[value[1] for value in selected]


def production(row):
    import numpy as np
    from types import SimpleNamespace
    from PyFLASH.stats import extract_p_and_stats_from_results
    statistic, probability = [np.asarray(value) for value in matrices(row['parameters'])]
    shape = row['parameters'].get('shape')
    if shape == 'one-dimensional':
        statistic, probability = statistic[0], probability[0]
    elif shape == 'different-shapes':
        probability = probability[:2,:2]
    elif shape == 'rectangular':
        statistic, probability = statistic[:,:2], probability[:,:2]
    try:
        statistics, probabilities = extract_p_and_stats_from_results(
            SimpleNamespace(statistic=statistic,pvalue=probability), row['parameters']['comparisons'])
    except ValueError:
        return [1]
    return [0,len(statistics),*statistics,*probabilities]


def freeze():
    if FIXTURE.exists():
        raise FileExistsError('Preserve the independently frozen reference.')
    rows = [{**row,'expected':reference(row)} for row in cases()]
    FIXTURE.write_text(json.dumps({'schema_version':1,'rows':rows,
        'reference':'Literal zero-based cell addresses queried by SQLite, independent of the display token parser.',
        'scope':'Complete functional extraction: dimensions, bounds, order, duplicate pairs and empty selections. No statistical inference claim.',
        'reason':'Prevent zero-based wraparound from selecting an unrelated pair when public comparison tokens start at one.',
        'reference_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    freeze()
