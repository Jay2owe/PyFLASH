"""Meaning controls for intensity/area means; no whole-summary certificate."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ARCHIVE = Path(__file__).with_name('reference-sources')/'excel-mean-wording-semantics/v1'
MANIFEST_SHA256 = '5210391a19acf4cc729dace2fd2e169f119e3489178382d2addf66de62fd8ff9'
COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {
    'PyFLASH.experiment.Experiment.createSummary': ('excel-mean-wording.',),
    'PyFLASH.batch.Batch.export_excel': ('excel-mean-wording.',),
    'PyFLASH.batch.Batch.export_all_excel': ('excel-mean-wording.',),
    'PyFLASH.batch.Batch.export_IF_summary_excel': ('excel-mean-wording.',),
    'PyFLASH.batch.Batch.export_extended_data_excel': ('excel-mean-wording.pixel.',),
}


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    fixture=json.loads((ARCHIVE/'declared-reference.json').read_text(encoding='utf-8'))
    original=json.loads((ARCHIVE/'run.json').read_text(encoding='utf-8'))
    assert original['pixel_disagreements']==0 and original['roi_numerical_disagreements']==0
    assert original['display_controls']==4 and original['display_disagreements']==4
    assert not original['source_changes'] and not original['production_source_edited']
    assert hashlib.sha256((ARCHIVE/'native-imagej.json').read_bytes()).hexdigest()==fixture['native_input_sha256']
    return fixture


def cases():
    fixture=check_identity()
    roi=json.loads((ARCHIVE/'original-roi-controls/declared-reference.json').read_text(encoding='utf-8'))
    rows=[dict(key='excel-mean-wording.pixel.'+str(count),kind='pixel',count=count,
        fixture=deepcopy(fixture)) for count in fixture['object_counts']]
    rows += [dict(key='excel-mean-wording.roi.'+str(index),kind='roi',volume=volume,
        fixture=deepcopy(fixture),roi=deepcopy(roi)) for index,volume in enumerate(roi['volume_controls'])]
    for row in rows:row['_case_digest']=hashlib.sha256(json.dumps(row,sort_keys=True).encode('utf-8')).hexdigest()
    return rows


def observe(row,folder):
    packet={name:value for name,value in row.items() if name!='_case_digest'}
    assert hashlib.sha256(json.dumps(packet,sort_keys=True).encode('utf-8')).hexdigest()==row['_case_digest'], 'Declared mean-wording control changed'
    import pandas as pd
    from PyFLASH import markers,export
    from PyFLASH.experiment import Experiment
    from reproducibility import marker_calibration_contract as calibration
    exp=Experiment('declared-mean-wording',str(folder))
    fixture=row['fixture']
    if row['kind']=='pixel':
        native=json.loads((ARCHIVE/'native-imagej.json').read_text(encoding='utf-8'))
        frame=pd.concat([calibration.frame(native['cases'][0]) for _ in range(row['count'])],ignore_index=True)
        stain=markers.objectMarker('IBA1',frame,exp,None)
        exp.data={'IBA1':stain};exp.createSummary(progress=False)
        summary=exp.summaries['SCN'];assert len(summary)==1
        actual=dict(pixel_mean=float(summary.iloc[0]['IBA1_MeanIntDenMean']),
            per_object_integrated_density=float(summary.iloc[0]['IBA1_IntDenMean']),raw_pixel_means=stain.df['IBA1_MeanIntDen'].tolist())
        expected=dict(pixel_mean=fixture['expected_pixel_mean'],per_object_integrated_density=fixture['expected_per_object_integrated_density'],
            raw_pixel_means=[fixture['expected_pixel_mean']]*row['count'])
        columns={'IBA1_MeanIntDenMean','IBA1_MeanIntDen'}
    elif row['kind']=='roi':
        roi=row['roi'];volume=row['volume']
        stain=markers.Antibody('IBA1_ROI',pd.DataFrame({'Region':['SCN1','SCN2'],'ROI':['SCN','SCN'],
            'Animal Name':['Subject1','Subject1'],'IntDen':roi['input_intden'],'%Area':roi['input_area_percent']}),exp)
        properties=markers.Attribute('SCN ROI Properties',pd.DataFrame({'Region':['SCN1','SCN2'],'ROI':['SCN','SCN'],
            'AnimalName':['Subject1','Subject1'],'Volume(micron^3)':[volume,volume]}),exp)
        exp.data={'IBA1_ROI':stain,'SCN ROI Properties':properties};exp.createSummary(progress=False)
        summary=exp.summaries['SCN'];assert len(summary)==1
        actual={field:float(summary.iloc[0][column]) for field,column in [
            ('intden_mean','IBA1_ROI_IntDenMean'),('area_mean','IBA1_ROI_%AreaMean'),('roi_volume','ROI_Volume')]}
        expected=dict(intden_mean=roi['expected_intden_mean'],area_mean=roi['expected_area_mean'],roi_volume=volume)
        columns={'IBA1_ROI_IntDenMean','IBA1_ROI_%AreaMean'}
    else:raise ValueError('Unknown mean-wording control')
    labels={};expected_labels={}
    for case in fixture['rows']:
        if case['column'] not in columns:continue
        label,description=(export.convert_name(case['column'],truncate=False) if case['mapping']=='IF_NAME_MAP'
            else export.convert_raw_name(case['column']))
        labels[case['column']]={field:value for field,value in [('label',label),('description',description)] if 'expected_'+field in case}
        expected_labels[case['column']]={field:case['expected_'+field] for field in ('label','description') if 'expected_'+field in case}
    actual['display']=labels;expected['display']=expected_labels
    return actual,expected


def required_keys(capability):
    prefixes=CAPABILITY_PREFIXES.get(capability,())
    return {row['key'] for row in cases() if row['key'].startswith(prefixes)}


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    output=Path(output);results=[];paired=[]
    for row in cases():
        actual=expected=None;error=None
        try:actual,expected=observe(row,output/'mean-wording-inputs'/row['key'])
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        agrees=error is None and actual==expected
        results.append(comparison(row['key'],'authenticated-archived-ImageJ-pixel-measurements/declared-mean-and-volume-diagnostics',
            'supporting-mean-presentation-contract/no-independent-fitted-estimator-or-whole-summary-certificate',
            actual,expected,agrees,True,'exact-all-compared-means-volume-and-wording',0.,0.))
        paired.append(dict(case=row,actual=actual,expected=expected,error=error,agrees=agrees))
    write_json(output/'excel-mean-wording-paired.json',dict(schema_version=1,complete_contract=False,scope=__doc__,rows=paired))
    return results
