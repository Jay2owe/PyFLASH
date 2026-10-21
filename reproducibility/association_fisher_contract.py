"""Native Fisher-information boundary only; complete association parents stay open."""
from pathlib import Path
import hashlib
import json
ARCHIVE=Path(__file__).with_name('reference-sources')/'association-fisher'
MANIFEST_SHA256='24904b64218b92b6e31ad84bf0d6393e3f13011fe635f1b2d9d26879d2e8900e'
CAPABILITY_PREFIXES={'PyFLASH.association_correlations.analyze':('association-fisher.',),'association_correlations':('association-fisher.',)}
COMPLETE_CAPABILITIES=frozenset()

def check_identity():
    manifest=ARCHIVE/'source-manifest.json'
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=MANIFEST_SHA256:raise ValueError('Fisher evidence manifest changed.')
    for name,digest in json.loads(manifest.read_text(encoding='utf-8')).items():
        if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest()!=digest:raise ValueError('Fisher evidence changed: '+name)

def cases():return json.loads((ARCHIVE/'association-fisher-native-before-20261007-v2/frozen-before.json').read_text(encoding='utf-8'))['rows']

def selected(result):
    row=result['contrasts'].iloc[0]
    return result['correlations']['estimate'].tolist()+[float(row[name]) for name in ('delta','standard_error','z','p')]

def production(row,*,include_plot=True):
    import numpy as np
    import pandas as pd
    from PyFLASH.association_correlations import analyze
    from reproducibility.association_interval_contract import encode
    case=row['case'];frame=pd.concat([pd.DataFrame(dict(data,Group=label)) for label,data in case['groups'].items()],ignore_index=True)
    frame.index=pd.Index(np.arange(len(frame))*7,name='original rows');frame.attrs={'boundary':'native Fisher information'};snapshot=frame.copy(deep=True)
    result=analyze(frame,group_col='Group',specs=[{'x':'x','y':'y','covariates':case['covariates'],'label':'Boundary association'}],group_order=['A','B'],reference='A',test=case['method'],bootstrap_resamples=100,random_state=case['seed'],min_n=3)
    expected=np.asarray([np.nan if value=='NaN' else value for value in row['expected']],dtype=float);actual=selected(result)
    np.testing.assert_allclose(actual,expected[:6],rtol=1e-12,atol=1e-12,equal_nan=True)
    if row['agrees_before']:assert encode(result)==row['original_full_result']
    pd.testing.assert_frame_equal(frame,snapshot,check_exact=True);assert frame.attrs==snapshot.attrs
    if include_plot:
        import matplotlib.pyplot as plt
        from PyFLASH.plotting import plot_association_correlations
        plotted_frame=frame.copy(deep=True);plotted_frame['Subject']=['boundary-'+str(i) for i in range(len(frame))];before=plotted_frame.copy(deep=True)
        plotted=plot_association_correlations(plotted_frame,associations={'Boundary association':{'x':'x','y':'y','covariates':case['covariates']}},factor='Group',group_col='Group',subject_col='Subject',group_order=['A','B'],reference='A',test=case['method'],bootstrap_resamples=100,random_state=case['seed'],min_n=3,save=False,return_data=True)
        try:
            np.testing.assert_allclose(selected(plotted),expected[:6],rtol=1e-12,atol=1e-12,equal_nan=True)
            pd.testing.assert_frame_equal(plotted_frame,before,check_exact=True);assert plotted_frame.attrs==before.attrs
        finally:plt.close(plotted['figure'])
    return {'analysis_fields':encode(actual),'public_plot_agrees':bool(include_plot),'inputs_unchanged':True,'eligible_full_output_unchanged':True if row['agrees_before'] else None}

def validate(output):
    from reproducibility.normality_association_validation import comparison
    from PyFLASH._persistence import write_json
    check_identity();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    comparisons=[];paired=[]
    for row in cases():
        actual=None;error=None
        try:actual=production(row)
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        scope='Native original-value correlations and Fisher contrast inference at positive/zero information, including a numeric covariate. Other eligible full outputs are retained controls. Shared cases cover analysis and plot; no extra vote or complete parent certificate.'
        comparisons.append(comparison(row['key'],'Native R correlation, QR residuals and Fisher inference boundary','association-fisher',actual,row['expected'],error is None,True,scope,1e-12,1e-12))
        paired.append({'key':row['key'],'actual':actual,'native_expected':row['expected'],'error':error,'agrees':error is None,'scope':scope})
        write_json(output/'association-fisher-paired.json',{'rows':paired})
    return comparisons
