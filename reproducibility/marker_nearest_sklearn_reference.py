"""Published scikit-learn geometry with independent SQLite row selection.

This reference reads original marker rows. SQL supplies the complete shared-key
eligibility, scikit-learn's own KDTree supplies distances and neighbours, and
the retained literal threshold specification supplies functional attribution.
The composed tables are not another published whole microscopy procedure.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sqlite3

from reproducibility.marker_nearest_reference import GROUP_FIELDS, ORIGINAL


def literal_threshold():
    original=json.loads(ORIGINAL.read_text(encoding='utf-8'))
    path=ORIGINAL.with_name('reference.py')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=original['reference_sha256']:
        raise ValueError('Original literal nearest-marker threshold specification changed.')
    spec=importlib.util.spec_from_file_location('retained_nearest_threshold_spec',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.positive


def answer(case):
    import numpy as np
    from sklearn.neighbors import NearestNeighbors
    left,right=case['left'],case['right']
    shared=[name for name in GROUP_FIELDS if name in case['left_groups'] and name in case['right_groups']]
    valid=lambda row:all(v is not None and math.isfinite(float(v)) for v in row['point']) and row['point'][2]!=0
    with sqlite3.connect(':memory:') as database:
        declarations=', '.join('"'+name+'"' for name in shared)
        for side,rows in (('left',left),('right',right)):
            database.execute(f'CREATE TABLE "{side}" (position INTEGER, valid INTEGER'+
                             (', '+declarations if declarations else '')+')')
            database.executemany(f'INSERT INTO "{side}" VALUES ('+','.join('?' for _ in range(2+len(shared)))+')',
                                 [(i,int(valid(row)),*(row.get(name) for name in shared)) for i,row in enumerate(rows)])
        d=[math.inf]*len(left);flags=[0.]*len(right);coloc=[0.]*len(right);counts=[0.]*len(right)
        positive=literal_threshold()
        where=' AND '.join('"'+name+'" IS ?' for name in shared) or '1'
        for i,query in enumerate(left):
            if not valid(query):continue
            args=[query.get(name) for name in shared]
            positions=[row[0] for row in database.execute(
                'SELECT position FROM "right" WHERE valid=1 AND '+where+' ORDER BY position',args)]
            if not positions:continue
            points=np.asarray([right[j]['point'] for j in positions],dtype=float)
            # Request the complete ranked neighbourhood, retaining exact ties
            # and applying the declared first-original-row policy explicitly.
            distances,indices=NearestNeighbors(n_neighbors=len(positions),algorithm='kd_tree',
                metric='euclidean',leaf_size=17).fit(points).kneighbors(np.asarray([query['point']],dtype=float))
            distance,k=min((float(distance),int(k)) for distance,k in zip(distances[0],indices[0],strict=True))
            j=positions[k];d[i]=distance;flags[j]=1.;counts[j]+=1.
            if case['coloc_column'] is None:coloc[j]+=1.;continue
            group=[row[0] for row in database.execute('SELECT position FROM "left" WHERE '+where+' ORDER BY position',args)]
            coloc[j]+=float(positive([left[k].get('coloc') for k in group],group.index(i),case['threshold']))
    return {'distances':d,'closest_flags':flags,'coloc_counts':coloc,
            'contains':[int(value>=1) for value in coloc],'closest_counts':counts}
