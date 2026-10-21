"""Physical units for object surface/volume ratios; supporting controls only."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
ARCHIVE=Path(__file__).with_name('reference-sources')/'surface-volume-unit-semantics/v1'
MANIFEST_SHA256='25c801969d6f3b43d205876ee41344d724b0015cbf5498e5859607ad1a0d93e4'
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={name:('surface-volume-unit.',) for name in (
    'PyFLASH.experiment.Experiment.createSummary','PyFLASH.batch.Batch.export_excel',
    'PyFLASH.batch.Batch.export_all_excel','PyFLASH.batch.Batch.export_IF_summary_excel',
    'PyFLASH.batch.Batch.export_extended_data_excel')}


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    original=json.loads((ARCHIVE/'run.json').read_text(encoding='utf-8'))
    assert original['numerical_controls']==7 and original['numerical_disagreements']==0
    assert original['display_controls']==2 and original['display_disagreements']==2 and not original['source_changes']
    fixture=json.loads((ARCHIVE/'declared-reference.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((ARCHIVE/'declared-reference.json').read_bytes()).hexdigest()==original['fixture_sha256']
    assert hashlib.sha256((ARCHIVE/'native-imagej.json').read_bytes()).hexdigest()==fixture['native_input_sha256']
    assert len(fixture['controls'])==7
    return fixture


def cases():
    fixture=check_identity();rows=[]
    for control in fixture['controls']:
        row=dict(key='surface-volume-unit.'+control['key'],control=deepcopy(control),fixture=deepcopy(fixture))
        row['_case_digest']=hashlib.sha256(json.dumps(row,sort_keys=True).encode('utf-8')).hexdigest()
        rows.append(row)
    return rows


def observe(row,output):
    payload={key:value for key,value in row.items() if key!='_case_digest'}
    assert hashlib.sha256(json.dumps(payload,sort_keys=True).encode('utf-8')).hexdigest()==row['_case_digest'],'Declared surface/volume control changed'
    import pandas as pd
    from PyFLASH import markers,export
    from PyFLASH.experiment import Experiment
    from reproducibility import marker_calibration_contract as calibration
    native=json.loads((ARCHIVE/'native-imagej.json').read_text(encoding='utf-8'))
    fixture,control=row['fixture'],row['control']
    obj=Experiment('declared-surface-volume-units',str(output))
    source=pd.concat([calibration.frame(native['cases'][index]) for index in control['native_indices']],ignore_index=True)
    stain=markers.objectMarker('IBA1',source,obj,None);obj.data={'IBA1':stain};obj.createSummary(progress=False)
    summary=obj.summaries['SCN'];assert len(summary)==1
    actual=dict(raw_ratios=stain.df['IBA1_SAtoVolumeRatio'].tolist(),mean=float(summary.iloc[0]['IBA1_SAtoVolumeRatioMean']),
        labels={case['column']:(export.convert_name(case['column'],truncate=False) if case['mapping']=='IF_NAME_MAP'
            else export.convert_raw_name(case['column']))[0] for case in fixture['rows']})
    expected=dict(raw_ratios=control['expected_ratios'],mean=control['expected_mean'],
        labels={case['column']:case['expected_label'] for case in fixture['rows']})
    return actual,expected


def agrees(row,actual,expected):
    import numpy as np
    tol=dict(atol=row['fixture']['atol'],rtol=row['fixture']['rtol'])
    return bool(actual['labels']==expected['labels'] and len(actual['raw_ratios'])==len(expected['raw_ratios'])
        and np.allclose(actual['raw_ratios'],expected['raw_ratios'],**tol) and np.isclose(actual['mean'],expected['mean'],**tol))


def required_keys(capability):
    return {row['key'] for row in cases()} if capability in CAPABILITY_PREFIXES else set()


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    rows,paired=[],[]
    for row in cases():
        actual=expected=None;error=None
        try:actual,expected=observe(row,Path(output)/row['key'])
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        matches=error is None and agrees(row,actual,expected)
        rows.append(comparison(row['key'],'Authenticated archived ImageJ surface/volume inputs and predeclared dimensional/mean truth; no fresh geometric engine',
            'supporting-surface-volume-units/no-independent-estimator-or-whole-summary-vote',actual,expected,matches,True,
            'all-object-ratios-summary-means-and-both-physical-unit-labels',row['fixture']['rtol'],row['fixture']['atol']))
        paired.append(dict(case=row,actual=actual,expected=expected,error=error,agrees=matches))
    write_json(Path(output)/'surface-volume-unit-paired.json',dict(schema_version=1,complete_contract=False,rows=paired))
    return rows
