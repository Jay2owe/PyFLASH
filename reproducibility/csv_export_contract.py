"""Complete literal CSV serialization controls; no scientific-method vote."""
from pathlib import Path
from types import SimpleNamespace
import csv
import hashlib
import json
import pandas as pd
from PyFLASH.experiment import Experiment
from PyFLASH.batch import Batch
ARCHIVE=Path(__file__).with_name('reference-sources')/'csv-export'
MANIFEST_SHA256='667f4417003fae79cb1cfdec0a1fae6523d85d2b268b306018373882d53bcfd8'
CAPABILITIES=frozenset(['PyFLASH.experiment.Experiment.'+name for name in ('save_column_csvs','save_attribute_csvs','save_csvs')]+['PyFLASH.batch.Batch.save_csvs'])

def check_identity():
    manifest=ARCHIVE/'source-manifest.json'
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=MANIFEST_SHA256:raise ValueError('CSV evidence manifest changed.')
    for name,digest in json.loads(manifest.read_text(encoding='utf-8')).items():
        if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest()!=digest:raise ValueError('CSV evidence changed: '+name)

def cases():
    rows=json.loads((ARCHIVE/'csv-export-functional-before-20261007-v2/frozen-before.json').read_text(encoding='utf-8'))['rows']
    for row in rows:row['capability']=('PyFLASH.batch.' if row['owner'].startswith('Batch.') else 'PyFLASH.experiment.')+row['owner']
    return rows

def required_keys(capability):return {row['key'] for row in cases() if row['capability']==capability}

def fixture(mode,root,*,experiment_class=None):
    obj=object.__new__(experiment_class or Experiment)
    if mode=='empty-summary':
        summary=pd.DataFrame({'Condition':pd.Series(dtype=str),'AnimalName':pd.Series(dtype=str),'Count':pd.Series(dtype=int)})
    elif mode=='identity-only':
        summary=pd.DataFrame({'Condition':['A','B','A'],'AnimalName':['first','second','third']},index=[11,2,11])
    else:
        summary=pd.DataFrame({'Condition':['A','B','A'],'AnimalName':['first','second','third'],'Count':[2,4,6],'Missing':[float('nan'),5.,7.],'Label':['cell','κ','space']},index=[11,2,11])
    summary.attrs={'original':'CSV ownership'};obj.summaries={'SCN':summary}
    obj.condition_list=[] if mode=='empty-conditions' else [SimpleNamespace(name=name) for name in ('A','B','Absent')]
    raw=pd.DataFrame({'X':[1.25,2.5],'Y':[3,4]},index=pd.Index([9,3],name='raw_row'));raw.attrs={'original':'raw ownership'}
    obj.data={} if mode=='empty-attributes' else {'IBA1':SimpleNamespace(df=raw)}
    obj.csv_path=str(root/'csv');obj.column_path=str(root/'columns');obj.attribute_path=str(root/'attributes');obj._unrelated=object()
    return obj

def production(row,output,*,experiment_class=None):
    directory=Path(output)/row['key'];directory.mkdir(parents=True,exist_ok=True)
    owner=row['owner'];mode=row['mode']
    if owner.startswith('Batch.'):
        names=[] if mode=='empty-batch' else ['first experiment'] if mode=='single-experiment' else ['first experiment','second κ','third experiment'] if mode=='three-experiments' else ['first experiment','second κ']
        obj=object.__new__(Batch);obj.experiment_list=[fixture(mode,directory/name) for name in names];objects=obj.experiment_list
    else:obj=fixture(mode,directory,experiment_class=experiment_class);objects=[obj]
    snapshots=[(item,item.summary.copy(deep=True),{name:attr.df.copy(deep=True) for name,attr in item.data.items()},item._unrelated) for item in objects]
    returned=getattr(obj,owner.split('.')[1])();files={}
    for path in directory.rglob('*.csv'):
        with path.open(encoding='utf-8',newline='') as stream:files[path.relative_to(directory).as_posix()]=list(csv.reader(stream))
    for item,summary,raw,identity in snapshots:
        pd.testing.assert_frame_equal(item.summary,summary,check_exact=True);assert item.summary.attrs==summary.attrs and item._unrelated is identity
        for name,frame in raw.items():pd.testing.assert_frame_equal(item.data[name].df,frame,check_exact=True);assert item.data[name].df.attrs==frame.attrs
    return {'files':files,'inputs_unchanged':True,'returned_none':returned is None}

def validate(output):
    from reproducibility.normality_association_validation import comparison
    from PyFLASH._persistence import write_json
    check_identity();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    comparisons=[];paired=[]
    for row in cases():
        actual=None;error=None
        try:actual=production(row,output)
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        expected={'files':row['expected_files'],'inputs_unchanged':True,'returned_none':True}
        agrees=error is None and actual==expected
        scope='Complete direct literal CSV paths, headers, rows, group/missing-value ordering, all batch-size branches, return and input ownership. Functional serialization; no microscopy or scientific inference vote.'
        comparisons.append(comparison(row['key'],'Literal CSV export contract and independent standard-library reader','csv-export',actual,expected,agrees,True,scope,0,0))
        paired.append({'key':row['key'],'actual':actual,'expected':expected,'error':error,'agrees':agrees,'scope':scope})
        write_json(output/'csv-export-paired.json',{'rows':paired})
    return comparisons
