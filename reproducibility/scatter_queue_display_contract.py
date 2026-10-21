"""Authenticated original 3D queue display requests and complete artists.

Independent SQL supplies selected-region display bounds. This contract makes
no claim about inference, three-dimensional projection or rendered export.
"""
from pathlib import Path
import ast
import json
import sqlite3
ARCHIVE=Path(__file__).with_name('reference-sources')/'scatter-queue-display'
MANIFEST_SHA256='e0c6c5bd17634b89250ad8ef265673f427c88afbcd80bd656a530a4b02bd130f'
ORIGINAL='scatter-queue-display-before-20261007-v1'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)


def original_record():
    return json.loads((ARCHIVE/ORIGINAL/'run.json').read_text(encoding='utf-8'))


def originals():
    return original_record()['rows']


def production(original, output):
    from PyFLASH import plotting as P,from_dataframe,ConditionBuilder
    import pandas as pd
    import numpy as np
    record=original_record();frame=pd.DataFrame(record['input_records'])
    experiment=from_dataframe(frame,
        conditions=ConditionBuilder('Diagnosis').add('Control').add('Case').build(),
        name='scatter-display-contract',condition_col='Diagnosis',animal_col='AnimalName',region_col='Region',
        summaries={roi:frame[frame.Region.str.startswith(roi)].copy() for roi in ('SCN','OC')},
        fig_path=Path(output)/'unsaved',data_path=Path(output)/'data')
    path=ARCHIVE/ORIGINAL/'probe_scatter_queue_display_20261007.py'
    nodes=[n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='production']
    namespace=dict(P=P,experiment=experiment,LABELS=record['labels'],np=np)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    actual=namespace['production'](original['case'])
    assert not list((Path(output)/'unsaved').rglob('*'))
    check_result(original,actual)
    return actual


def check_result(original, actual):
    record=original_record();case=original['case'];assert actual
    strip=lambda rows:[{k:v for k,v in row.items() if k not in ('xlim','ylim','zlim','xlabel','ylabel','zlabel')} for row in rows]
    assert strip(actual)==strip(original['actual']),'Original plotted coordinates or scientific annotation changed'
    if original['outcome']=='agree':assert original['actual']==actual
    with sqlite3.connect(':memory:') as connection:
        import pandas as pd
        pd.DataFrame(record['input_records']).to_sql('measurements',connection,index=False)
        for row in actual:
            if case['labels']:
                assert row['xlabel'] in (record['labels']['A_Volume'],record['labels']['B_Volume'])
                assert row['ylabel']==record['labels']['A_Surface']
                assert row['zlabel']==record['labels']['A_Intensity']
            if case['queued'] and case['share_axes']:
                bounds=connection.execute('SELECT MIN(A_Surface),MAX(A_Surface),MIN(A_Intensity),MAX(A_Intensity) FROM measurements WHERE Region LIKE ?',
                    [row['roi']+'%']).fetchone()
                assert row['ylim']==list(bounds[:2]),'Shared vertical axis mixes acquired regions'
                assert row['zlim']==list(bounds[2:]),'Shared depth axis mixes acquired regions'
