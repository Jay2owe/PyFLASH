"""Physical-distance summary/presentation support; no whole geometry certificate."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ARCHIVE=Path(__file__).with_name('reference-sources')/'excel-distance-presentation/v1'
MANIFEST_SHA256='5918fcfe10b4d907e52eee5b9a1b5a511c8f42d318fdb2e255940ff4af28dbd4'
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={
    'PyFLASH.experiment.Experiment.createSummary':('excel-distance-presentation.summary.',),
    'PyFLASH.batch.Batch.export_excel':('excel-distance-presentation.',),
    'PyFLASH.batch.Batch.export_all_excel':('excel-distance-presentation.',),
    'PyFLASH.batch.Batch.export_IF_summary_excel':('excel-distance-presentation.',),
    'PyFLASH.batch.Batch.export_unregistered_summary_excel':('excel-distance-presentation.label.',),
    'PyFLASH.batch.Batch.export_extra_summary_excel':('excel-distance-presentation.label.',),
}

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    original=json.loads((ARCHIVE/'run.json').read_text(encoding='utf-8'))
    paired=json.loads((ARCHIVE/'paired.json').read_text(encoding='utf-8'))
    assert original['numerical_controls']==1 and original['numerical_disagreements']==0
    assert original['display_controls']==3 and original['display_disagreements']==3
    assert not original['source_changes'] and not original['production_source_edited']
    assert paired['numerical_control']['agrees'] and all(not row['agrees'] for row in paired['display_controls'])
    unit_closure=json.loads((ARCHIVE/'original-unit-closure/run.json').read_text(encoding='utf-8'))
    assert not unit_closure['passed'] and unit_closure['controls']==12 and unit_closure['failed']==5
    return json.loads((ARCHIVE/'amended-reference.json').read_text(encoding='utf-8'))

def cases():
    fixture=check_identity()
    rows=[dict(key='excel-distance-presentation.summary.supplied-micrometres',kind='summary',fixture=deepcopy(fixture))]
    rows.extend(dict(key='excel-distance-presentation.label.'+row['column'],kind='label',fixture=deepcopy(row)) for row in fixture['rows'])
    rows.append(dict(key='excel-distance-presentation.sort.legacy-and-modern',kind='sort',fixture=dict(
        columns=['IBA1_VolumeMean','IBA1_DistToVentricleMean','IBA1_DistToClosest_CD68Mean','IBA1_DistToVentricle'],
        expected=['IBA1_VolumeMean','IBA1_DistToClosest_CD68Mean','IBA1_DistToVentricle','IBA1_DistToVentricleMean'])))
    for row in rows:row['_case_digest']=hashlib.sha256(json.dumps(row,sort_keys=True).encode('utf-8')).hexdigest()
    return rows

def observe(row,folder):
    packet={name:value for name,value in row.items() if name!='_case_digest'}
    assert hashlib.sha256(json.dumps(packet,sort_keys=True).encode('utf-8')).hexdigest()==row['_case_digest'],'Declared distance presentation changed'
    from PyFLASH import export
    fixture=row['fixture']
    if row['kind']=='summary':
        import pandas as pd
        from PyFLASH import markers
        from PyFLASH.experiment import Experiment
        from reproducibility import marker_calibration_contract as calibration
        native=json.loads((ARCHIVE/'native-imagej.json').read_text(encoding='utf-8'))
        assert hashlib.sha256((ARCHIVE/'native-imagej.json').read_bytes()).hexdigest()==fixture['native_input_sha256']
        frame=pd.concat([calibration.frame(native['cases'][0]) for _ in fixture['distances_um']],ignore_index=True)
        frame['DistToVentricle']=fixture['distances_um']
        exp=Experiment('declared-distance-summary',str(folder))
        stain=markers.objectMarker('IBA1',frame,exp,None)
        exp.data={'IBA1':stain};exp.createSummary(progress=False)
        summary=exp.summaries['SCN'];assert len(summary)==1
        column=fixture['expected_summary_column']
        actual=dict(column=column,value=float(summary.iloc[0][column]))
        expected=dict(column=column,value=fixture['expected_mean_um'])
    elif row['kind']=='label':
        label=export.convert_name(fixture['column'],truncate=False)[0]
        actual=dict(label=label,default_label=export.convert_name(fixture['column'])[0])
        expected=dict(label=fixture['expected_label'],default_label=fixture['expected_label'])
    elif row['kind']=='sort':
        actual=export.sort_if_summary_columns(fixture['columns']);expected=fixture['expected']
    else:raise ValueError('Unknown distance presentation control')
    return actual,expected

def required_keys(capability):
    prefixes=CAPABILITY_PREFIXES.get(capability,())
    return {row['key'] for row in cases() if row['key'].startswith(prefixes)}

def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    output=Path(output);paired=[];results=[]
    for row in cases():
        actual=expected=None;error=None
        try:actual,expected=observe(row,output/'distance-presentation-inputs'/row['key'])
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        agrees=error is None and actual==expected
        paired.append(dict(case=row,actual=actual,expected=expected,error=error,agrees=agrees))
        results.append(comparison(row['key'],'declared-physical-distance-mean/registered-units-and-sort-contract',
            'supporting-presentation/no-independent-geometric-engine-or-whole-summary-certificate',
            actual,expected,agrees,True,'exact-all-declared-values-labels-units-and-order',0.,0.))
    write_json(output/'excel-distance-presentation-paired.json',dict(schema_version=1,complete_contract=False,scope=__doc__,rows=paired))
    return results
