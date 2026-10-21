"""Native percentile/correlation fields only; complete association parents remain open."""
from pathlib import Path
import hashlib
import json
ARCHIVE=Path(__file__).with_name('reference-sources')/'association-intervals'
MANIFEST_SHA256='0c76c14ab162c904564cd4ab85e9f46f39f7d5ca546a24b4ee6b807bd8a966ee'
NARROW_MANIFEST_SHA256='55a343b3e3331092d10297ec4c307c27bf36ad673da7eb237af47f410367a1e1'
CAPABILITY_PREFIXES={'PyFLASH.association_correlations.analyze':('association-confidence.',),'association_correlations':('association-confidence.',)}
COMPLETE_CAPABILITIES=frozenset()
CACHE_CARRIER_SHA256 = '892e720299f21c66904c619c6cdfae546ea67a5e6be02ad6ed681800ae0a829b'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)
    verify_manifest(ARCHIVE, 'narrow-amendment-manifest.json', NARROW_MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)

def cases():
 return [row for version in ('v1','v2') for row in json.loads((ARCHIVE/f'association-interval-native-before-20261007-{version}/frozen-before.json').read_text(encoding='utf-8'))['rows']]
def selected(result):return result['correlations']['estimate'].tolist()+result['correlations'][['ci_low','ci_high']].values.reshape(-1).tolist()+result['contrasts'][['ci_low','ci_high']].values.reshape(-1).tolist()
def encode(value):
 import numpy as np
 import pandas as pd
 if isinstance(value,pd.DataFrame):return {'columns':list(value.columns),'index':value.index.tolist(),'dtypes':list(value.dtypes.astype(str)),'rows':encode(value.values.tolist())}
 if isinstance(value,dict):return {str(k):encode(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [encode(v) for v in value]
 if isinstance(value,(float,np.floating)) and not np.isfinite(value):return 'NaN' if np.isnan(value) else 'Inf' if value>0 else '-Inf'
 if isinstance(value,np.generic):return value.item()
 return value
def production(row, *, include_plot=True):
 import numpy as np
 import pandas as pd
 from PyFLASH.association_correlations import analyze
 case=row['case'];frame=pd.concat([pd.DataFrame(dict(values,Group=label)) for label,values in case['groups'].items()],ignore_index=True)
 frame.index=pd.Index(case['input_index'],name=case['input_index_name']);frame.attrs=case['input_attrs'];snapshot=frame.copy(deep=True)
 result=analyze(frame,group_col='Group',specs=[{'x':'x','y':'y','covariates':[],'label':'Original association'}],group_order=['A','B'],reference='A',test=case['method'],ci_alpha=case['alpha'],bootstrap_resamples=100,random_state=case['seed'])
 actual=selected(result);np.testing.assert_allclose(actual,row['expected'],rtol=1e-12,atol=1e-12)
 full=encode(result);old=row['original_full_result']
 for name in ('schemas','correlations','heterogeneity','bootstrap'):assert full[name]==old[name],name
 contrast=full['contrasts'];previous=old['contrasts'];excluded={contrast['columns'].index(name) for name in ('ci_low','ci_high')}
 assert contrast['columns']==previous['columns'] and contrast['dtypes']==previous['dtypes'] and contrast['index']==previous['index']
 assert [[v for i,v in enumerate(values) if i not in excluded] for values in contrast['rows']]==[[v for i,v in enumerate(values) if i not in excluded] for values in previous['rows']]
 pd.testing.assert_frame_equal(frame,snapshot,check_exact=True);assert frame.attrs==snapshot.attrs
 plotted_values=None
 if include_plot:
  import matplotlib.pyplot as plt
  from PyFLASH.plotting import plot_association_correlations
  plotted_frame=frame.copy(deep=True);plotted_frame['Subject']=['recorded-'+str(i) for i in range(len(frame))]
  before=plotted_frame.copy(deep=True)
  plotted=plot_association_correlations(plotted_frame,associations={'Original association':{'x':'x','y':'y'}},factor='Group',group_col='Group',subject_col='Subject',group_order=['A','B'],reference='A',test=case['method'],ci_alpha=case['alpha'],bootstrap_resamples=100,random_state=case['seed'],save=False,return_data=True)
  try:
   plotted_values=selected(plotted);np.testing.assert_allclose(plotted_values,row['expected'],rtol=1e-12,atol=1e-12)
   from matplotlib.collections import LineCollection
   axis=plotted['figure'].axes[0]
   bars=[artist for artist in axis.collections if isinstance(artist,LineCollection)]
   assert len(bars)==1
   np.testing.assert_allclose([[segment[0][1],segment[1][1]] for segment in bars[0].get_segments()],
       np.asarray(row['expected'][2:6]).reshape(2,2),rtol=1e-12,atol=1e-12)
   np.testing.assert_array_equal(axis.containers[0].lines[0].get_ydata(),plotted['correlations']['estimate'].to_numpy())
   pd.testing.assert_frame_equal(plotted_frame,before,check_exact=True);assert plotted_frame.attrs==before.attrs
  finally:plt.close(plotted['figure'])
 return {'analysis_fields':actual,'public_plot_fields':plotted_values,'inputs_unchanged':True,'other_fields_unchanged':True}
def validate(output):
 from reproducibility.normality_association_validation import comparison
 from PyFLASH._persistence import write_json
 check_identity();output=Path(output);output.mkdir(parents=True,exist_ok=True)
 rows=[];paired=[]
 for case in cases():
  actual=None;error=None
  try:actual=production(case)
  except Exception as exc:error=type(exc).__name__+': '+str(exc)
  scope='Native R original-value correlations and complete group/comparison percentile interval arrays using declared common resample indices. Other fields are retained regression guards. One shared native case covers two interfaces; no extra vote or complete parent certificate.'
  rows.append(comparison(case['key'],'Native R stats::cor and stats::quantile(type=7)','association-intervals',actual,case['expected'],error is None,True,scope,1e-12,1e-12))
  paired.append({'key':case['key'],'case':case['case'],'actual':actual,'native_expected':case['expected'],'error':error,'agrees':error is None,'scope':scope})
  write_json(output/'association-interval-paired.json',{'rows':paired})
 return rows
