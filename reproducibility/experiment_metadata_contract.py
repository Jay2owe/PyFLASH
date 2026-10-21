"""Literal direct metadata contracts; no microscopy or inference certificate."""
from pathlib import Path
import contextlib
import hashlib
import io
import json
from types import SimpleNamespace
import pandas as pd
from PyFLASH.experiment import Experiment
from PyFLASH.batch import Batch
ARCHIVE=Path(__file__).with_name('reference-sources')/'experiment-metadata'
MANIFEST_SHA256='b2e8e72438d7d91d32512945377e0c99ef9571bbb9db33e5a83678e3a7b0b653'
CAPABILITIES=frozenset(['PyFLASH.experiment.Experiment.'+name for name in ('summary','createSavePaths','getRegionDict','getSCNDict','info')]+['PyFLASH.batch.Batch.createSavePaths'])
def check_identity():
 manifest=ARCHIVE/'source-manifest.json'
 if hashlib.sha256(manifest.read_bytes()).hexdigest()!=MANIFEST_SHA256:raise ValueError('Metadata evidence manifest changed.')
 for name,digest in json.loads(manifest.read_text()).items():
  if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest()!=digest:raise ValueError('Metadata evidence changed: '+name)
def cases(*, encoding='utf-8'):
 rows=json.loads((ARCHIVE/'experiment-metadata-functional-before-20261006-v2/frozen-before.json').read_text(encoding=encoding))['rows']
 for row in rows:
  row['capability']=('PyFLASH.batch.' if row['owner'].startswith('Batch.') else 'PyFLASH.experiment.')+row['owner']
 return rows
def required_keys(capability):return {row['key'] for row in cases() if row['capability']==capability}

def frame():
 result=pd.DataFrame({'AnimalName':['A','B','A'],'Condition':['Female','Male','Female'],'value':[1.,2.,3.]},index=pd.Index([9,2,9],name='original'))
 result.attrs={'origin':'literal fixture'};return result

def calculate(row, output, *, experiment_class=None):
 owner=row['owner'];inputs=row['input'];kind=owner.split('.')[0]
 obj=object.__new__((experiment_class or Experiment) if kind=='Experiment' else Batch);unrelated=object();obj._literal_unrelated=unrelated
 if owner.endswith('createSavePaths'):
  root=(Path('.runtime')/'uncreated-metadata-inputs' if inputs['root']=='relative' else output/'uncreated-inputs')/inputs['root'];target=root/inputs['pattern'] if inputs['pattern'] else root
  obj.filePath=target if inputs['carrier']=='path' else str(target)
  identity=obj.filePath;root_identity=None
  if kind=='Experiment':
   mode=inputs['source_root_mode']
   if mode=='explicit':
    root_identity=root/'selected-root';root_identity=root_identity if inputs['carrier']=='path' else str(root_identity);obj.source_root=root_identity;root=root/'selected-root'
   elif mode in ('none','empty'):root_identity=None if mode=='none' else '';obj.source_root=root_identity
  result=obj.createSavePaths()
  found={name:Path(getattr(obj,name)).relative_to(root).as_posix() for name in row['expected']['paths']}
  return {'returned_none':result is None,'paths':found,'directories_created':root.exists(),'unrelated_state_retained':obj._literal_unrelated is unrelated,'source_root_retained':obj.filePath is identity and (not hasattr(obj,'source_root') or obj.source_root is root_identity)}
 if owner.endswith('summary'):
  mode=inputs['mode'];source=frame();snapshot=source.copy(deep=True)
  if mode=='empty':obj.summaries={}
  elif mode=='none':obj.summaries=None
  elif mode in ('other','fallback'):obj.summaries={'other':source}
  elif mode=='scn':obj.summaries={'SCN':source}
  elif mode=='prefer-scn':obj.summaries={'other':frame(),'SCN':source}
  if inputs['operation']=='get':
   result=obj.summary
   return {'selected':None if result.empty else 'SCN' if mode=='prefer-scn' else 'other','empty_columns':list(result.columns) if result.empty else None,'other_fields_retained':obj._literal_unrelated is unrelated,'table_input_unchanged':source.equals(snapshot) and source.attrs==snapshot.attrs and (result is source if not result.empty else True)}
  value=source if inputs['value']=='frame' else {'none':None,'integer':7,'text':'ignored'}[inputs['value']]
  obj.summary=value
  return {'stored_input_identity':obj.summaries.get('SCN') is value if inputs['value']=='frame' else False,'stored_keys':list(obj.summaries),'other_fields_retained':obj._literal_unrelated is unrelated,'table_input_unchanged':source.equals(snapshot) and source.attrs==snapshot.attrs}
 if owner.endswith('getRegionDict') or owner.endswith('getSCNDict'):
  obj.condition_list=[SimpleNamespace(name=name) for name in ('Female','Male','Empty')]
  obj.summaries={'SCN':frame(),'ARC':pd.DataFrame({'AnimalName':['A','C'],'Condition':['Female','Male']})}
  master=pd.DataFrame({'AnimalName':['A','A','A','B','A','C'],'ROI':['SCN','SCN','SCN','SCN','ARC','ARC'],'Region':[1,2,1,3,7,8]})
  if inputs['mode']=='no-roi-column':master=master.drop(columns='ROI')
  if inputs['mode']=='missing-region':master=master.drop(columns='Region')
  if inputs['mode']!='missing-master':obj.master_region=master
  summary_before={k:v.copy(deep=True) for k,v in obj.summaries.items()};master_before=master.copy(deep=True)
  mapping=obj.getRegionDict(inputs['query']) if owner.endswith('getRegionDict') else obj.getSCNDict()
  return {'mapping':mapping,'state_unchanged':obj._literal_unrelated is unrelated and master.equals(master_before) and all(obj.summaries[k].equals(v) for k,v in summary_before.items())}
 if owner.endswith('info'):
  obj.name='Literal experiment';obj.filePath='literal/path';obj.data={'first':object(),'second':object()}
  mode=inputs['mode']
  if mode=='empty':obj.summaries={}
  elif mode=='with-conditions':obj.summaries={'SCN':frame()}
  elif mode=='without-condition':obj.summaries={'SCN':frame().drop(columns='Condition')}
  before=dict(obj.__dict__);text=io.StringIO()
  with contextlib.redirect_stdout(text):obj.info()
  return {'text':text.getvalue(),'state_unchanged':obj.__dict__.keys()==before.keys() and all(obj.__dict__[k] is v for k,v in before.items())}
 raise ValueError(owner)

def production(row, output):return calculate(row, Path(output))
def validate(output):
 from reproducibility.normality_association_validation import comparison
 from PyFLASH._persistence import write_json
 check_identity();output=Path(output);output.mkdir(parents=True,exist_ok=True)
 comparisons=[];paired=[]
 for row in cases():
  actual=None;error=None
  try:actual=production(row,output)
  except Exception as exc:error=type(exc).__name__+': '+str(exc)
  agrees=error is None and actual==row['expected']
  scope='Direct literal metadata, complete output paths, region lookup, summary ownership or reporting. No constructor, image-processing or scientific-parent certificate; not an inference vote.'
  comparisons.append(comparison(row['key'],'Literal functional metadata contract','experiment-metadata',actual,row['expected'],agrees,True,scope,0.,0.))
  paired.append({'key':row['key'],'capability':row['capability'],'input':row['input'],'expected':row['expected'],'actual':actual,'error':error,'agrees':agrees,'scientific_vote':False})
  write_json(output/'experiment-metadata-paired.json',{'rows':paired})
 return comparisons
