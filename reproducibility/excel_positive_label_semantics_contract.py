"""Positive binary volume labels must agree with actual requested classification."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ARCHIVE=Path(__file__).with_name('reference-sources')/'excel-positive-label-semantics/v1'
MANIFEST_SHA256='6de3d187a188ef92ccd9f67e1c613c1812e8e8d202693e315fedf8c3e7f1e025'
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={capability:('excel-positive-label-semantics.',) for capability in (
    'PyFLASH.batch.Batch.export_excel','PyFLASH.batch.Batch.export_all_excel',
    'PyFLASH.batch.Batch.export_extended_data_excel','PyFLASH.markers.Antibody.addColocData')}

def check_identity():
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(ARCHIVE/'source-manifest.json')!=MANIFEST_SHA256:
        raise ValueError('Original positive-label semantics manifest changed')
    for name,value in json.loads((ARCHIVE/'source-manifest.json').read_text(encoding='utf-8')).items():
        if sha(ARCHIVE/name)!=value:
            raise ValueError('Original positive-label semantics evidence changed: '+name)
    return json.loads((ARCHIVE/'declared-reference.json').read_text(encoding='utf-8'))

def cases():
    rows=check_identity()['rows']
    for row in rows:
        row['key']='excel-positive-label-semantics.'+row['key']
        row['_case_digest']=hashlib.sha256(json.dumps(row,sort_keys=True).encode('utf-8')).hexdigest()
    return rows

def required_keys(capability):
    return {row['key'] for row in cases()} if capability in CAPABILITY_PREFIXES else set()

def observe(row):
    packet={name:value for name,value in row.items() if name!='_case_digest'}
    assert hashlib.sha256(json.dumps(packet,sort_keys=True).encode('utf-8')).hexdigest()==row['_case_digest'],'Declared positive classification or label changed'
    import pandas as pd
    from PyFLASH import markers,export
    from reproducibility.dataframe_table_protocol import table
    raw='IBA1_Coloc_DAPI' if row['family']=='legacy' else 'IBA1_VolColoc_DAPI'
    obj=object.__new__(markers.Antibody);obj.name='IBA1'
    obj.df=pd.DataFrame({raw:deepcopy(row['values'])})
    before=table(obj.df)
    returned=obj.addColocData(row['threshold'])
    actual=dict(values={name:obj.df[name].tolist() for name in row['expected_labels']},
        labels={name:export.convert_raw_name(name)[0] for name in row['expected_labels']},
        dtypes={name:str(obj.df[name].dtype) for name in row['expected_labels']},
        source_input_unchanged=table(obj.df[[raw]])==before,returned_owned_frame=returned is obj.df)
    actual['agrees']=all(value==row['expected'] for value in actual['values'].values()) and actual['labels']==row['expected_labels'] and all(value=='int8' for value in actual['dtypes'].values()) and actual['source_input_unchanged'] and actual['returned_owned_frame']
    return actual

def check_original_failures():
    check_identity()
    receipt=json.loads((ARCHIVE/'run.json').read_text(encoding='utf-8'))
    original=json.loads((ARCHIVE/'paired.json').read_text(encoding='utf-8'))['rows']
    assert receipt['comparisons']==len(original)==10
    assert receipt['classification_disagreements']==0 and receipt['label_disagreements']==10
    assert not receipt['source_changes'] and not receipt['passed']
    assert all(row['classification_agrees'] and not row['labels_agree'] and row['source_input_unchanged'] for row in original)
    return receipt

def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    paired=[];results=[]
    for row in cases():
        actual=error=None
        try:actual=observe(row)
        except Exception as exception:error=type(exception).__name__+': '+str(exception)
        agrees=error is None and actual['agrees']
        paired.append(dict(case=row,observed=actual,error=error,agrees=agrees))
        results.append(comparison(row['key'],'predeclared-literal-positive-flags/native-pandas-public-marker-consumer',
            'functional-label-truth/no-independent-fitted-estimator-or-whole-marker-vote',
            actual,dict(values=row['expected'],labels=row['expected_labels']),agrees,True,
            'exact-requested-positive-flags-labels-int8-types-and-preserved-source-inputs',0.,0.))
    write_json(Path(output)/'excel-positive-label-semantics-paired.json',
        dict(schema_version=1,complete_contract=False,scope=__doc__,rows=paired))
    return results
