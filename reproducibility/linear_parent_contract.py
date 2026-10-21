"""Partial public linear-pipeline science against original native libraries.

This checks coefficients, uncertainty, group means/contrasts, model summaries
and corrections on frozen inputs. It does not certify all input domains,
covariances, plots, saved outputs or the complete public pipeline.
"""
from pathlib import Path
import json
import math
import re
from reproducibility.evidence_identity import verify_sources

FIXTURE=Path(__file__).with_name('fixtures')/'linear_parent_native_reference.json'
CAPABILITIES=('PyFLASH.pipeline.linear_model','linear_model_pipeline','PyFLASH.modelling.run_linear_model_pipeline')

def unpack(node):
    if node['type']=='list':return dict(zip(node['names'],map(unpack,node['values']),strict=True))
    return node['values']

def reference_expected(case,native,adjustments):
    if 'expected_domain_error' in case:return {'error':'invalid correction method'}
    answer={}
    for endpoint in case['endpoints']:
        original=native[case['key']+'.'+endpoint]
        co=original['coefficients'];means=original['means'];contrasts=original['contrasts'];model=original['model'];joint=original['joint']
        coeff={}
        for i,term in enumerate(co['term']):
            fields={'estimate':co['estimate'][i],'std_error':co['SE'][i],
                't_value':co['t.ratio' if 't.ratio' in co else 'z.ratio'][i],'p_value':co['p.value'][i],
                'ci_low':co['lower.CL' if 'lower.CL' in co else 'asymp.LCL'][i],
                'ci_high':co['upper.CL' if 'upper.CL' in co else 'asymp.UCL'][i],
                'q_value':None,'reject_fdr':False}
            key=(case['key'],'coefficient',endpoint,term)
            if key in adjustments:
                fields['q_value']=adjustments[key];fields['reject_fdr']=fields['q_value']<=case['alpha']
            coeff[term]=fields
        group_rows={g:dict(adjusted_mean=means['emmean'][i],mean_se=means['SE'][i],
            ci_low=means['lower.CL' if 'lower.CL' in means else 'asymp.LCL'][i],
            ci_high=means['upper.CL' if 'upper.CL' in means else 'asymp.UCL'][i]) for i,g in enumerate(means['g'])}
        comparison_rows={}
        for i,label in enumerate(contrasts['contrast']):
            key=(case['key'],'contrast',endpoint,label)
            # Broader native inputs retain every directed group contrast.
            # Only the declared testing family receives adjusted answers.
            if key not in adjustments:continue
            p=adjustments[key]
            comparison_rows[label]=dict(estimate=contrasts['estimate'][i],std_error=contrasts['SE'][i],
                t_value=contrasts['t.ratio' if 't.ratio' in contrasts else 'z.ratio'][i],p_value=contrasts['p.value'][i],
                p_adjusted=p,reject_adjusted=p<=case['alpha'])
        summary={field:model[field][0] for field in ('nobs','df_model','df_resid','r_squared','adj_r_squared')}
        # Original R includes the fitted Gaussian variance in parameter count.
        # Preserve its raw AIC/BIC in the native source; reconcile that convention.
        summary.update(f_statistic=joint['F.ratio'][0],f_pvalue=joint['p.value'][0],
                       aic=model['aic'][0]-2,bic=model['bic'][0]-math.log(model['nobs'][0]))
        answer[endpoint]=dict(coefficients=coeff,means=group_rows,contrasts=comparison_rows,summary=summary)
    return answer

def _native_expected(root,paths):
    inputs=json.loads((root/paths['inputs']).read_text(encoding='utf-8'))
    raw=json.loads((root/paths['native']).read_text(encoding='utf-8'))
    if not raw['passed'] or any(row['status']!='executed' for row in raw['rows']):raise ValueError('Native model execution incomplete')
    native={row['key']:unpack(row['output']) for row in raw['rows']}
    layout=json.loads((root/paths['layout']).read_text(encoding='utf-8'))
    corrections=json.loads((root/paths['corrections']).read_text(encoding='utf-8'))
    adjustments={}
    for row in corrections['rows']:
        if row['status']!='executed':raise ValueError('Native correction execution incomplete')
        details=layout[row['key']]
        for item,p in zip(details['items'],row['values'],strict=True):
            result=native[details['case_key']+'.'+item['endpoint']]
            table=result['coefficients' if details['kind']=='coefficient' else 'contrasts']
            index=table['term' if details['kind']=='coefficient' else 'contrast'].index(item['label'])
            if table['p.value'][index]!=item['native_p_value']:raise ValueError('Correction input differs from original native probability')
            adjustments[(details['case_key'],details['kind'],item['endpoint'],item['label'])]=p
    return [dict(case=case,expected=reference_expected(case,native,adjustments)) for case in inputs]


def check_HC1_reference(root,fixture):
    """Cross-check retained original fits against original R, without a refit."""
    paths=fixture['HC1_sources']
    protocol=json.loads((root/paths['protocol.json']).read_text(encoding='utf-8'))
    receipt=json.loads((root/paths['run.json']).read_text(encoding='utf-8'))
    original=json.loads((root/paths['original-results.json']).read_text(encoding='utf-8'))
    case_row=next(row for row in fixture['rows'] if row['case']['key']==protocol['case_key'])
    if protocol['input']!=case_row['case'] or (protocol['rtol'],protocol['atol'])!=(1e-9,1e-12) or protocol.get('probability_atol')!=0:
        raise ValueError('HC1 native protocol changed')
    if not receipt['passed'] or receipt['aligned_comparisons']!=receipt['aligned_agreements'] or receipt['aligned_comparisons']!=122:
        raise ValueError('HC1 native qualification incomplete')
    if [row['endpoint'] for row in original]!=case_row['case']['endpoints']:
        raise ValueError('HC1 native endpoint identities changed')
    count=0
    for row in original:
        expected=case_row['expected'][row['endpoint']]
        if not row['HC1']['debiased'] or row['default']['debiased']:
            raise ValueError('HC1 native covariance convention changed')
        # The native fitting family names its intercept without parentheses.
        if {('(Intercept)' if item['label']=='Intercept' else item['label']) for item in row['coefficients']}!=set(expected['coefficients']):
            raise ValueError('HC1 native coefficient identities changed')
        for item in row['coefficients']:
            target=expected['coefficients']['(Intercept)' if item['label']=='Intercept' else item['label']]
            values=item['routes']['aligned-HC1-normal']
            if set(values)!={'estimate','std_error','t_value','p_value','ci_low','ci_high'} or not equal(values,{key:target[key] for key in values}):
                raise ValueError('HC1 native coefficient answers disagree with original R')
            count+=len(values)
        seen=set()
        for item in row['groups']:
            kind,label=item['kind'],item['label']
            if (kind,label) in seen:raise ValueError('HC1 native group identity duplicated')
            seen.add((kind,label));values=item['routes']['aligned-HC1-normal']
            mapping={'estimate':'adjusted_mean','std_error':'mean_se','ci_low':'ci_low','ci_high':'ci_high'} if kind=='mean' else {key:key for key in ('estimate','std_error','t_value','p_value')}
            target=expected['means' if kind=='mean' else 'contrasts'][label]
            if not equal({key:values[key] for key in mapping},{key:target[field] for key,field in mapping.items()}):
                raise ValueError('HC1 native group answers disagree with original R')
            count+=len(mapping)
        if seen!={('mean',label) for label in expected['means']}|{('contrast',label) for label in expected['contrasts']}:
            raise ValueError('HC1 native group identities changed')
        summary=row['HC1']['summary']
        if set(summary)!={'nobs','df_model','df_resid','r_squared','adj_r_squared','f_statistic','f_pvalue'} or not equal(summary,{key:expected['summary'][key] for key in summary}):
            raise ValueError('HC1 native summary answers disagree with original R')
        count+=len(summary)
    if count!=122:raise ValueError('HC1 native field coverage changed')
    return count


def _unpack_native_groups(node):
    if node['type']=='list':
        values=list(map(_unpack_native_groups,node['values']))
        return values if node['names'] is None else dict(zip(node['names'],values,strict=True))
    return node['values']


def check_robust_reference(root,fixture):
    """Compare original compiled estimatr fits, including complete fit arrays."""
    paths=fixture['robust_sources']
    original=json.loads((root/paths['original-native-results.json']).read_text(encoding='utf-8'))
    receipt=json.loads((root/paths['qualification.json']).read_text(encoding='utf-8'))
    prepared=json.loads((root/paths['prepared-receipt.json']).read_text(encoding='utf-8'))
    if not original['passed'] or any(row['status']!='executed' for row in original['rows']) or not receipt['passed'] or receipt['aligned_comparisons']!=receipt['aligned_agreements']:
        raise ValueError('Original robust native qualification incomplete')
    if receipt['aligned_comparisons']!=732 or receipt['aligned_agreements']!=732 or original['library_archive_sha256']!=prepared['archive_sha256']:
        raise ValueError('Original robust native qualification changed')
    cases={row['case']['key']:row for row in fixture['rows'] if row['case']['cov_type'] in ('HC1','HC2','HC3')}
    inputs=json.loads((root/paths['inputs.json']).read_text(encoding='utf-8'))
    if [row['case'] for row in cases.values()]!=inputs:raise ValueError('Robust native input identities changed')
    original_R=json.loads((root/fixture['native_path']).read_text(encoding='utf-8'))
    R={row['key']:unpack(row['output']) for row in original_R['rows']}
    seen=set();count=0
    def require(actual,expected,kind):
        nonlocal count
        if not equal(actual,expected):raise ValueError('Original robust '+kind+' answers disagree with original R')
        count+=len(actual)
    def fields(table,index):
        return {field:table[name][index] for field,name in dict(estimate='estimate',std_error='SE',t_value='z.ratio',
            p_value='p.value',ci_low='asymp.LCL',ci_high='asymp.UCL').items()}
    for row in original['rows']:
        if row['key'] in seen:raise ValueError('Robust native endpoint identity duplicated')
        seen.add(row['key']);key,endpoint=row['key'].rsplit('.',1);case=cases[key]
        expected=case['expected'][endpoint];first=R[row['key']]
        output=_unpack_native_groups(row['output']);raw=output['original'];table=output['coefficients'];names=output['covariance_terms']
        if output['version']!=['1.0.6'] or raw['se_type']!=[case['case']['cov_type']] or set(table['term'])!=set(expected['coefficients']):
            raise ValueError('Robust native fitting convention changed')
        for index,label in enumerate(table['term']):
            values=fields(table,index);require(values,{name:expected['coefficients'][label][name] for name in values},'coefficient')
        groups=set()
        for group in output['groups']:
            kind,label=group['kind'][0],group['label'][0]
            if (kind,label) in groups or kind not in ('mean','contrast') or group['identity_error'][0]>1e-12 or group['rank'][0]!=len(names):
                raise ValueError('Robust native coordinate identity changed')
            groups.add((kind,label));values=fields(group['aligned'],0)
            mapping={'estimate':'adjusted_mean','std_error':'mean_se','ci_low':'ci_low','ci_high':'ci_high'} if kind=='mean' else {name:name for name in ('estimate','std_error','t_value','p_value')}
            target=expected['means' if kind=='mean' else 'contrasts'][label]
            require({name:values[name] for name in mapping},{name:target[field] for name,field in mapping.items()},'group')
        if groups!={('mean',label) for label in expected['means']}|{('contrast',label) for label in expected['contrasts']}:
            raise ValueError('Robust native group identities changed')
        summary=dict(nobs=raw['nobs'][0],df_model=raw['rank'][0]-1,df_resid=raw['df.residual'][0],
            r_squared=raw['r.squared'][0],adj_r_squared=raw['adj.r.squared'][0],f_statistic=raw['fstatistic'][0],f_pvalue=output['joint_tail'][0])
        require(summary,{name:expected['summary'][name] for name in summary},'summary')
        n=len(names);r_names=first['covariance_terms']
        if set(names)!=set(r_names) or len(output['covariance'])!=n*n or len(first['covariance'])!=n*n:
            raise ValueError('Robust native covariance shape changed')
        expected_covariance=[first['covariance'][r_names.index(label)+n*r_names.index(column)] for column in names for label in names]
        if not equal(dict(enumerate(output['covariance'])),dict(enumerate(expected_covariance))):
            raise ValueError('Original robust covariance answers disagree with original R')
        count+=n*n
        if len(raw['fitted.values'])!=len(case['case']['data']) or not equal(dict(enumerate(raw['fitted.values'])),dict(enumerate(first['fitted']))):
            raise ValueError('Original robust fitted answers disagree with original R')
        count+=len(raw['fitted.values'])
    if seen!={key+'.'+endpoint for key,row in cases.items() for endpoint in row['case']['endpoints']} or count!=732:
        raise ValueError('Robust native field coverage changed')
    return count

def check_stable_native_inference(root,fixture):
    """Authenticate complete native fields against the frozen original R answers."""
    paths=fixture['stable_inference_sources']
    protocol=json.loads((root/paths['protocol.json']).read_text(encoding='utf-8'))
    receipt=json.loads((root/paths['run.json']).read_text(encoding='utf-8'))
    original=json.loads((root/paths['original-results.json']).read_text(encoding='utf-8'))
    coordinates=json.loads((root/paths['coordinate-qualification.json']).read_text(encoding='utf-8'))
    cases=[row for row in fixture['rows']+fixture['domain_rows']
           if row['case']['cov_type'] in ('nonrobust','HC0','HC1') and 'expected_domain_error' not in row['case']]
    if (protocol['rtol'],protocol['atol'],protocol['probability_atol'])!=(1e-9,1e-12,0) or protocol['original_library']!='linearmodels 7.0':
        raise ValueError('Stable native inference protocol changed')
    if protocol['cases']!=[row['case'] for row in cases] or len(cases)!=35:
        raise ValueError('Stable native inference input identities changed')
    if not receipt['passed'] or (receipt['cases'],receipt['models'],receipt['native_group_refits'],receipt['comparisons'],receipt['agreements'])!=(35,70,420,6046,6046):
        raise ValueError('Stable native inference qualification incomplete')
    targets={row['case']['key']+'.'+endpoint:(row['case'],row['expected'][endpoint]) for row in cases for endpoint in row['case']['endpoints']}
    seen=set();groups=set();count=0;default_disagreements=0
    for row in original:
        identity=row['key']+'.'+row['endpoint']
        if identity in seen or identity not in targets:
            raise ValueError('Stable native inference endpoint identity changed')
        seen.add(identity);case,expected=targets[identity]
        if row['rows']!=case.get('declared_complete_rows',{}).get(row['endpoint'],list(range(len(case['data'])))):
            raise ValueError('Stable native inference complete rows changed')
        for kind,fields in (('coefficients',('estimate','std_error','t_value','p_value','ci_low','ci_high')),
                            ('means',('adjusted_mean','mean_se','ci_low','ci_high')),
                            ('contrasts',('estimate','std_error','t_value','p_value'))):
            if set(row[kind])!=set(expected[kind]):
                raise ValueError('Stable native inference field identities changed')
            for label,values in row[kind].items():
                if set(values)!=set(fields) or not equal(values,{field:expected[kind][label][field] for field in fields}):
                    raise ValueError('Stable native '+kind+' answers disagree with original R')
                count+=len(fields)
                if kind!='coefficients':groups.add((row['key'],row['endpoint'],'mean' if kind=='means' else 'contrast',label))
        fields=('nobs','df_model','df_resid','r_squared','adj_r_squared','f_statistic','f_pvalue')
        if set(row['summary'])!=set(fields) or not equal(row['summary'],{field:expected['summary'][field] for field in fields}):
            raise ValueError('Stable native summary answers disagree with original R')
        count+=len(fields)
        default_seen=set()
        expected_defaults={('coefficient',label) for label in expected['coefficients']}|{('mean',label) for label in expected['means']}|{('contrast',label) for label in expected['contrasts']}
        for default in row['defaults']:
            key=(default['kind'],default['label'])
            if key in default_seen or key not in expected_defaults:raise ValueError('Stable native default identities changed')
            default_seen.add(key)
            if default['kind']!='mean':
                target=expected['coefficients' if default['kind']=='coefficient' else 'contrasts'][default['label']]['p_value']
                default_disagreements+=not equal({'p_value':default['original_fit_pvalue']},{'p_value':target})
        if default_seen!=expected_defaults:raise ValueError('Stable native defaults incomplete')
        default_disagreements+=not equal({'f_pvalue':row['original_joint_pvalue']},{'f_pvalue':expected['summary']['f_pvalue']})
    coordinate_seen=set()
    for row in coordinates:
        identity=(row['key'],row['endpoint'],row['kind'],row['label'])
        if identity in coordinate_seen or identity not in groups:raise ValueError('Stable native coordinate identity changed')
        coordinate_seen.add(identity)
        n=len(targets[row['key']+'.'+row['endpoint']][1]['coefficients'])
        if row['rank']!=n or row['identity_error']>1e-12 or len(row['vector'])!=n or len(row['matrix'])!=n or any(len(line)!=n for line in row['matrix']) or not 0<=row['pivot']<n:
            raise ValueError('Stable native coordinate qualification changed')
    if seen!=set(targets) or coordinate_seen!=groups or len(groups)!=420 or count!=6046 or default_disagreements!=receipt['original_default_disagreements']:
        raise ValueError('Stable native inference field coverage changed')
    return count


def check_covariance_reference(root,fixture):
    """Authenticate native keyword fits, complete arrays and correction answers."""
    paths=fixture['covariance_sources'];rows=fixture['covariance_rows']
    original_expected=_native_expected(root,paths)
    if [(row['case'],row['expected']) for row in rows]!=[(row['case'],row['expected']) for row in original_expected] or len(rows)!=10:
        raise ValueError('Covariance keyword answers differ from original native evidence')
    original=json.loads((root/paths['native']).read_text(encoding='utf-8'))
    native={row['key']:unpack(row['output']) for row in original['rows']}
    models={row['case']['key']+'.'+endpoint:(row,endpoint) for row in rows for endpoint in row['case']['endpoints']}
    if set(native)!=set(models) or len(original['rows'])!=20:
        raise ValueError('Covariance native endpoint identities changed')
    targets={}
    for identity,(row,endpoint) in models.items():
        expected=row['expected'][endpoint];answer=native[identity];names=answer['covariance_terms'];n=len(names);key=row['case']['key']
        wrapper=dict(covariance={left+' / '+right:answer['covariance'][i+n*j] for i,left in enumerate(names) for j,right in enumerate(names)},
            fitted={str(i):value for i,value in enumerate(answer['fitted'])},residual={str(i):value for i,value in enumerate(answer['residuals'])})
        if row['wrapper_expected'][endpoint]!=wrapper or len(answer['covariance'])!=n*n or len(answer['fitted'])!=len(answer['residuals']) or len(answer['fitted'])!=len(row['case']['data']):
            raise ValueError('Covariance wrapper arrays differ from original native evidence')
        for kind,fields in [('coefficients',('estimate','std_error','t_value','p_value','ci_low','ci_high')),('means',('adjusted_mean','mean_se','ci_low','ci_high')),('contrasts',('estimate','std_error','t_value','p_value'))]:
            for label,values in expected[kind].items():
                for field in fields:targets[(key,endpoint,kind,label,field)]=values[field]
        for field in ('nobs','df_model','df_resid','r_squared','adj_r_squared','f_statistic','f_pvalue'):
            targets[(key,endpoint,'summary',endpoint,field)]=expected['summary'][field]
        for kind,values in wrapper.items():
            for label,value in values.items():targets[(key,endpoint,kind,label,kind)]=value
    receipt=json.loads((root/paths['science']).read_text(encoding='utf-8'))
    comparisons=json.loads((root/paths['comparisons']).read_text(encoding='utf-8'))
    if not receipt['passed'] or (receipt['cases'],receipt['models'],receipt['comparisons'],receipt['agreements'])!=(10,20,6360,6360):
        raise ValueError('Covariance native qualification incomplete')
    seen=set();default_disagreements=0
    for item in comparisons:
        if item['route'] not in ('original-linearmodels','original-fit-default'):continue
        kind='coefficients' if item['kind']=='coefficient' else item['kind']
        identity=(item['key'],item['endpoint'],kind,item['label'],item['field'])
        if identity not in targets:raise ValueError('Covariance native field identity changed')
        expected=targets[identity];agrees=equal({item['field']:item['actual']},{item['field']:expected})
        if item['route']=='original-fit-default':default_disagreements+=not agrees;continue
        if identity in seen:raise ValueError('Covariance native field duplicated')
        seen.add(identity)
        if not agrees or not equal({item['field']:item['expected']},{item['field']:expected}):
            raise ValueError('Covariance native '+kind+' answers disagree with original R')
        if (item['rtol'],item['atol'])!=(1e-9,0 if item['field'] in ('p_value','f_pvalue') else 1e-12):
            raise ValueError('Covariance native allowance changed')
    if seen!=set(targets) or len(seen)!=3160 or default_disagreements!=receipt['original_default_disagreements']:
        raise ValueError('Covariance native field coverage changed')
    correction=json.loads((root/paths['corrections']).read_text(encoding='utf-8'))
    original_correction=json.loads((root/paths['correction_original']).read_text(encoding='utf-8'))
    if not original_correction['passed'] or any(row['status']!='executed' for row in original_correction['rows']):
        raise ValueError('Covariance native correction execution incomplete')
    corrections={row['key']:row['values'] for row in correction['rows']}
    if corrections!={row['key']:unpack(row['output']) for row in original_correction['rows']}:
        raise ValueError('Covariance correction answers differ from original native evidence')
    layout=json.loads((root/paths['layout']).read_text(encoding='utf-8'))
    pingouin=json.loads((root/paths['pingouin']).read_text(encoding='utf-8'))
    corrected=json.loads((root/paths['correction_receipt']).read_text(encoding='utf-8'))
    if not corrected['passed'] or corrected['comparisons']!=corrected['agreements'] or corrected['comparisons']!=560 or len(pingouin)!=30 or len(corrections)!=30:
        raise ValueError('Covariance correction qualification incomplete')
    cases={row['case']['key']:row['case'] for row in rows};seen=set();count=0
    for answer in pingouin:
        if answer['key'] in seen or answer['key'] not in layout:raise ValueError('Covariance correction identity changed')
        seen.add(answer['key']);details=layout[answer['key']];case=cases[details['case_key']]
        if answer['method']!=('fdr_bh' if details['method']=='BH' else details['method']) or answer['alpha']!=case['alpha'] or answer['input_probabilities']!=[item['native_p_value'] for item in details['items']]:
            raise ValueError('Covariance correction request changed')
        for value,decision,target in zip(answer['adjusted'],answer['reject'],corrections[answer['key']],strict=True):
            if not equal({'p_adjusted':value},{'p_adjusted':target}) or target==case['alpha'] or decision!=(target<case['alpha']):
                raise ValueError('Covariance correction native answers disagree with original R')
            count+=2
    if seen!=set(layout) or count!=280:raise ValueError('Covariance correction field coverage changed')
    return dict(native_fields=3160,correction_fields=280)


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    if fixture.get('schema_version')!=1 or fixture.get('contract_kind')!='partial-public-linear-parent-native':
        raise ValueError('Unsupported public linear parent evidence schema')
    if (fixture.get('rtol'),fixture.get('atol'))!=(1e-9,1e-12):raise ValueError('Linear parent allowance changed')
    if fixture.get('probability_atol')!=0:raise ValueError('Linear positive probability allowance changed')
    root=Path(__file__).parent;verify_sources(root,fixture)
    invalid=json.loads((root/fixture['invalid_method_native_path']).read_text(encoding='utf-8'))
    invalid_row=next(row for row in invalid['rows'] if row['key']=='R-invalid-correction')
    if invalid_row['status']!='executed' or invalid_row['values']!=[1]:raise ValueError('Original native invalid-method control changed')
    expected=_native_expected(root,dict(inputs=fixture['inputs_path'],native=fixture['native_path'],layout=fixture['correction_layout_path'],corrections=fixture['correction_answers_path']))
    if fixture['rows']!=expected:raise ValueError('Linear parent answers differ from original native evidence')
    if 'domain_sources' in fixture:
        expected=_native_expected(root,fixture['domain_sources'])
        if fixture['domain_rows']!=expected:raise ValueError('Linear domain answers differ from original native evidence')
    if 'HC1_sources' in fixture:check_HC1_reference(root,fixture)
    if 'robust_sources' in fixture:check_robust_reference(root,fixture)
    if 'stable_inference_sources' in fixture:check_stable_native_inference(root,fixture)
    if 'covariance_sources' in fixture:check_covariance_reference(root,fixture)
    if 'zero_interval_sources' in fixture:
        paths=fixture['zero_interval_sources']
        case=json.loads((root/paths['inputs']).read_text(encoding='utf-8'))
        original_R=json.loads((root/paths['R']).read_text(encoding='utf-8'))['rows'][0]
        original_Pingouin=json.loads((root/paths['Pingouin']).read_text(encoding='utf-8'))
        if original_R['status']!='executed' or original_R['key']!=case['key']:
            raise ValueError('Zero interval native execution changed')
        point_rows={}
        for i,row in enumerate(original_Pingouin):
            values=original_R['values'][i*3:(i+1)*3]
            if values!=[row['estimate'],row['ci_low'],row['ci_high']] or original_R['values'][9+i]!=row['std_error']:
                raise ValueError('Independent zero interval libraries disagree')
            point_rows[row['group']]=dict(adjusted_mean=values[0],mean_se=row['std_error'],ci_low=values[1],ci_high=values[2])
        if fixture['boundary_rows']!=[dict(case=case,expected=point_rows)]:
            raise ValueError('Zero interval answers differ from original native evidence')
    return fixture

def cases():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    return fixture['rows']+fixture.get('domain_rows',[])+fixture.get('covariance_rows',[])

def boundary_cases():return json.loads(FIXTURE.read_text(encoding='utf-8')).get('boundary_rows',[])

def covariance_cases():return json.loads(FIXTURE.read_text(encoding='utf-8')).get('covariance_rows',[])


def observe_covariance_wrapper(case):
    import pandas as pd
    from PyFLASH.dataframe import from_dataframe
    from PyFLASH.modelling import run_linear_model_pipeline
    df=pd.DataFrame(case['data'])
    for name,levels in case['factor_levels'].items():df[name]=pd.Categorical(df[name],categories=levels)
    before=df.copy(deep=True)
    result=run_linear_model_pipeline(from_dataframe(df,group_col=case['group']),case['endpoints'],predictors=[case['group']]+case['predictors'],
        categorical=case['categorical'],reference_levels=case['reference_levels'],cov_type=case['cov_type'],cov_kwds=case['cov_kwds'],alpha=case['alpha'],
        fdr_method=case['fdr_method'],fdr_family=case['fdr_family'],save=False,return_fits=True,verbose=False)
    pd.testing.assert_frame_equal(df,before);answer={}
    for endpoint,fit in result['fits'].items():
        if fit.use_t:raise ValueError('Covariance wrapper inference convention changed')
        names=[_term_name(name) for name in fit.params.index];covariance=fit.cov_params().to_numpy()
        answer[endpoint]=dict(covariance={left+' / '+right:float(covariance[i,j]) for i,left in enumerate(names) for j,right in enumerate(names)},
            fitted={str(i):float(value) for i,value in enumerate(fit.fittedvalues)},residual={str(i):float(value) for i,value in enumerate(fit.resid)})
    return answer

def observe_zero_interval(case):
    import pandas as pd
    from PyFLASH.pipeline import linear_model
    df=pd.DataFrame(case['data']);before=df.copy(deep=True)
    result=linear_model(df,dependent_variables=case['endpoints'],predictors=case['predictors'],group=case['group'],
        categorical=case['categorical'],reference_levels=case['reference_levels'],alpha=case['alpha'],
        save=False,montage=False,plot_coefficients=False,plot_adjusted_means=False,verbose=False)
    pd.testing.assert_frame_equal(df,before)
    return {row['group']:{field:float(row[field]) for field in ('adjusted_mean','mean_se','ci_low','ci_high')}
            for _,row in result['adjusted_means_table'].iterrows()}

def _term_name(term):
    if ':' in term:return ':'.join(_term_name(part) for part in term.split(':'))
    if term=='Intercept':return '(Intercept)'
    if '[T.' in term:return re.match(r'C\((\w+),',term).group(1)+term.rsplit('[T.',1)[1].removesuffix(']')
    if term.replace(' ','')=='I(x**2)':return 'I(x^2)'
    return term

def observe(case):
    import pandas as pd
    from PyFLASH.pipeline import linear_model
    df=pd.DataFrame(case['data'])
    if 'declared_complete_rows' not in case or case['key'].endswith('unused-levels'):
        for name,levels in case['factor_levels'].items():df[name]=pd.Categorical(df[name],categories=levels)
    before=df.copy(deep=True)
    try:
        result=linear_model(df,dependent_variables=case['endpoints'],predictors=case['predictors'],group=case['group'],
            categorical=case['categorical'],reference_levels=case['reference_levels'],interactions=case['interactions'],
            cov_type=case['cov_type'],cov_kwds=case['cov_kwds'],alpha=case['alpha'],fdr_method=case['fdr_method'],fdr_family=case['fdr_family'],
            covariate_profile=case['profile'],adjusted_mean_weights=case['weights'],adjusted_mean_p_adjust=case['adjusted_mean_p_adjust'],
            adjusted_mean_p_family=case['adjusted_mean_p_family'],save=False,montage=False,plot_coefficients=False,plot_adjusted_means=False,verbose=False)
    except ValueError as error:
        if 'expected_domain_error' in case and str(error)=='method not recognized':return {'error':'invalid correction method'}
        raise
    pd.testing.assert_frame_equal(df,before)
    answer={}
    for endpoint in case['endpoints']:
        tables={}
        for name,key,label,fields in [
            ('coefficients','coefficients','term',('estimate','std_error','t_value','p_value','ci_low','ci_high','q_value','reject_fdr')),
            ('means','adjusted_means_table','group',('adjusted_mean','mean_se','ci_low','ci_high')),
            ('contrasts','adjusted_mean_comparisons','comparison',('estimate','std_error','t_value','p_value','p_adjusted','reject_adjusted'))]:
            table=result[key];table=table[table['dependent_variable'].eq(endpoint)]
            tables[name]={_term_name(row[label]) if name=='coefficients' else row['left_group']+' -> '+row['right_group'] if name=='contrasts' and 'declared_complete_rows' in case else row[label]:{
                field:None if pd.isna(row[field]) else bool(row[field]) if field.startswith('reject') else float(row[field]) for field in fields}
                for _,row in table.iterrows()}
        row=result['model_summaries'].set_index('dependent_variable').loc[endpoint]
        tables['summary']={field:float(row[field]) for field in ('nobs','df_model','df_resid','r_squared','adj_r_squared','f_statistic','f_pvalue','aic','bic')}
        answer[endpoint]=tables
    return answer

def equal(actual,expected):
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or actual.keys()!=expected.keys():return False
        for key,value in expected.items():
            if key in ('p_value','f_pvalue','q_value','p_adjusted') and isinstance(value,(int,float)) and not isinstance(value,bool):
                if not isinstance(actual[key],(int,float)) or not math.isclose(actual[key],value,rel_tol=1e-9,abs_tol=0):return False
            elif not equal(actual[key],value):return False
        return True
    if isinstance(expected,(bool,str)) or expected is None:return type(actual)==type(expected) and actual==expected
    return isinstance(actual,(int,float)) and math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-12)

def validate(output):
    import traceback
    from reproducibility.normality_association_validation import comparison
    fixture=check_identity();rows=[];paired=[]
    for row in fixture['rows']+fixture.get('domain_rows',[])+fixture.get('covariance_rows',[]):
        case=row['case'];expected=row['expected'];record=dict(case=case,expected=expected,error=None)
        try:
            actual=observe(case);agrees=equal(actual,expected)
        except Exception as error:actual={'error':type(error).__name__+': '+str(error)};agrees=False;record['error']=traceback.format_exc()
        record['production']=actual;paired.append(record)
        second='; second original linearmodels fitting/group family with explicitly aligned native survival/F inference; shared SciPy tails supply no extra tail vote' if case['cov_type'] in ('nonrobust','HC0','HC1') and 'stable_inference_sources' in fixture and 'expected_domain_error' not in case else ''
        if case['cov_type'] in ('HC1','HC2','HC3') and 'robust_sources' in fixture:
            second+='; independent original estimatr fitting/covariance and coordinate refits; shared emmeans inference supplies no extra inference-library vote'
        if case['cov_type'] in ('HAC','cluster') and 'covariance_sources' in fixture:
            second+='; original linearmodels covariance/group refits and complete wrapper arrays; original R/Pingouin correction families; shared SciPy tails supply no extra tail vote'
        rows.append(comparison('linear-parent-native.'+case['key'],'original-R/emmeans/sandwich/lmtest'+second,
            'partial-public-pipeline/scientific-tables-and-corrections',actual,expected,agrees,True,'named-scientific-fields',1e-9,1e-12))
        if 'wrapper_expected' in row:
            record['wrapper_expected']=row['wrapper_expected']
            try:
                wrapper_actual=observe_covariance_wrapper(case);wrapper_agrees=equal(wrapper_actual,row['wrapper_expected'])
            except Exception as error:
                wrapper_actual={'error':type(error).__name__+': '+str(error)};wrapper_agrees=False;record['wrapper_error']=traceback.format_exc()
            record['wrapper_production']=wrapper_actual
            rows.append(comparison('linear-wrapper-native.'+case['key'],'original-R/sandwich; original-linearmodels fitting/covariance family',
                'partial-public-table-wrapper/complete-covariance-fitted-residual-arrays',wrapper_actual,row['wrapper_expected'],wrapper_agrees,True,
                'complete-named-arrays',1e-9,1e-12))
    for row in fixture.get('boundary_rows',[]):
        case=row['case'];expected=row['expected'];record=dict(case=case,expected=expected,error=None)
        try:actual=observe_zero_interval(case);agrees=equal(actual,expected)
        except Exception as error:actual={'error':type(error).__name__+': '+str(error)};agrees=False;record['error']=traceback.format_exc()
        record['production']=actual;paired.append(record)
        rows.append(comparison('linear-parent-native.'+case['key'],'original-R-predict.lm/original-Pingouin-linear_regression',
            'partial-public-pipeline/zero-outcome-adjusted-mean-point-intervals',actual,expected,agrees,True,'named-zero-interval-fields',1e-9,1e-12))
    (output/'linear-parent-native-paired.json').write_text(json.dumps(paired,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return rows
