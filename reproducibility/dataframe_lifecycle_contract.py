"""Direct functional lifecycle controls; scientific constructors remain open."""
from pathlib import Path
import hashlib
import json

ARCHIVE=Path(__file__).with_name('reference-sources')/'dataframe-lifecycle'
MANIFEST_SHA256='8ce10267e583827e6c31a17549f5138fea91f2fb777651e191da234971e18f8b'
OWNERS=('getRegionDict','processData','createSavePaths','set_condition_list')
COMPLETE_CAPABILITIES=frozenset('PyFLASH.dataframe.DataFrameExperiment.'+name for name in OWNERS)

def check_identity():
 manifest=ARCHIVE/'source-manifest.json'
 if hashlib.sha256(manifest.read_bytes()).hexdigest()!=MANIFEST_SHA256:
  raise ValueError('Lifecycle evidence manifest changed.')
 for name,digest in json.loads(manifest.read_text()).items():
  if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest()!=digest:
   raise ValueError('Lifecycle evidence changed: '+name)

def cases():
 return json.loads((ARCHIVE/'dataframe-lifecycle-functional-before-20261006-v3/frozen-before.json').read_text())['rows']

def required_keys(capability):return {row['key'] for row in cases() if row['capability']==capability}

def bare():
 from PyFLASH.dataframe import DataFrameExperiment
 import pandas as pd
 obj=object.__new__(DataFrameExperiment)
 obj.summary=pd.DataFrame({'AnimalName':['A','B'],'Condition':['F','M'],'value':[1.,3.]})
 obj.summary.attrs={'recorded_input':'literal-lifecycle'}
 obj.aliases={'value':'Recorded value'};obj.data={'recorded':object()}
 return obj

def production(row,output):
 from PyFLASH.conditions import ConditionBuilder
 from types import SimpleNamespace
 obj=bare();owner=row['capability'].rsplit('.',1)[-1];inputs=row['input']
 if owner=='getRegionDict':
  default={'F':{'A':['left','right']},'M':{'B':['left']}}
  other={'F':{'A':['other']}}
  obj.region_dict=default;obj.region_dicts={'SCN':default,'other':other,'7':other}
  query=inputs['query'];snapshot=obj.summary.copy(deep=True)
  result=obj.getRegionDict(query)
  return {'mapping':result,'returned_owned_mapping':result is (other if query is not None and str(query) in ('other','7') else default),
   'summary_unchanged':obj.summary.equals(snapshot) and obj.summary.attrs==snapshot.attrs}
 if owner=='processData':
  state=dict(obj.__dict__);result=obj.processData(*inputs['args'],**inputs['kwargs'])
  return {'returned_original':result is obj,'keys_unchanged':obj.__dict__.keys()==state.keys(),
   'every_field_identity_unchanged':all(obj.__dict__[name] is value for name,value in state.items())}
 if owner=='createSavePaths':
  parent=Path(output)/'lifecycle-scratch'/inputs['pattern'];parent.mkdir(parents=True,exist_ok=False)
  names=('fig_path','data_path','export_path','image_fig_path','representative_path','legend_path')
  relative=inputs['relative_paths']
  for name,value in zip(names,relative):setattr(obj,name,str(parent/value))
  if inputs['pattern']=='existing':(parent/relative[0]).mkdir(parents=True)
  if inputs['pattern']=='collision':(parent/relative[0]).write_text('preserve-source-file',encoding='utf-8')
  snapshot=dict(obj.__dict__)
  try:
   first=obj.createSavePaths();second=obj.createSavePaths()
   return {'returned_original':first is second is obj,'owned_paths_created':all(Path(getattr(obj,name)).is_dir() for name in names),
    'fields_unchanged':all(obj.__dict__[name] is value for name,value in snapshot.items())}
  except FileExistsError:
   return {'refused_collision':True,'original_file_retained':(parent/relative[0]).read_text()=='preserve-source-file',
    'later_paths_absent':all(not Path(getattr(obj,name)).exists() for name in names[1:])}
 if owner=='set_condition_list':
  groups=ConditionBuilder('Sex').add('Female',short='F',color='#123456').add('Male',short='M',color='#654321').build()
  if 'literal_input' in inputs:
   supplied={'none':None,'empty-list':[],'empty-tuple':(),'empty-iterator':iter([]),'integer':7}[inputs['literal_input']]
   obj.condition_list=groups;obj.factor=groups.factor;obj.factorDict=groups.factorDict
   state=dict(obj.__dict__);error=None
   try:obj.set_condition_list(supplied)
   except (ValueError,TypeError) as exc:error=type(exc).__name__
   return {'error_type':error,'every_field_identity_unchanged':all(obj.__dict__[name] is value for name,value in state.items())}
  mode=inputs['mode'];state=dict(obj.__dict__)
  if mode=='existing':supplied=groups
  elif mode=='list':supplied=list(groups.condition_list)
  elif mode=='tuple':supplied=tuple(groups.condition_list)
  elif mode=='iterator':supplied=iter(groups.condition_list)
  elif mode=='duck-with-factors':supplied=SimpleNamespace(condition_list=[],factorDict={'Treatment':['C','D']},factor=['Treatment'])
  elif mode=='duck-no-factor':supplied=SimpleNamespace(condition_list=[],factorDict={})
  elif mode=='duck-none-factor':supplied=SimpleNamespace(condition_list=[],factorDict={},factor=None)
  else:raise ValueError('Unknown lifecycle metadata mode: '+mode)
  returned=obj.set_condition_list(supplied)
  return {'returned_original':returned is obj,'factor':obj.factor,
   'factorDict':{key:[getattr(value,'name',value) for value in values] for key,values in obj.factorDict.items()},
   'unrelated_fields_preserved':all(obj.__dict__[name] is value for name,value in state.items()),
   'existing_metadata_identity':obj.condition_list is supplied if mode=='existing' or mode.startswith('duck') else True,
   'factor_entries_preserved':all(value is original for value,original in zip(obj.factorDict.get('Sex',[]),groups.condition_list)) if not mode.startswith('duck') else obj.factorDict is supplied.factorDict}
 raise ValueError('Unknown lifecycle method: '+owner)

def validate(output):
 from reproducibility.normality_association_validation import comparison
 from PyFLASH._persistence import write_json
 check_identity();output=Path(output);output.mkdir(parents=True,exist_ok=True)
 rows=[];paired=[]
 for row in cases():
  actual=None;error=None
  try:actual=production(row,output)
  except Exception as exc:error=type(exc).__name__+': '+str(exc)
  agrees=error is None and actual==row['expected']
  rows.append(comparison(row['key'],'Literal functional interface and ownership controls','dataframe-lifecycle',
   actual,row['expected'],agrees,True,row['scope'],0.,0.))
  paired.append({'key':row['key'],'input':row['input'],'actual':actual,'expected':row['expected'],
   'agrees':agrees,'error':error,'kind':row['kind'],'scientific_vote':False})
  write_json(output/'dataframe-lifecycle-paired.json',{'rows':paired})
 return rows
