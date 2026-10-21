"""Independent full model-parent records and original observation identity."""
from copy import deepcopy
import math
from reproducibility import comparison_parent_inference_reference as parent
from reproducibility import comparison_record_reference as record
from reproducibility import normality_parent_reference as normality
from reproducibility import two_way_mathematical_reference as twa,linear_model_mathematical_reference as model


def nullable(value):
    if isinstance(value,dict):return {k:nullable(v) for k,v in value.items()}
    if isinstance(value,list):return [nullable(v) for v in value]
    return None if isinstance(value,str) and value in ('nan','inf','-inf') else value


def observations(case):
    child=case['child'];p=child['parameters'];names=case['names'];rows=[]
    def source_id(i):
        label=case.get('source_index',[])[i] if 'source_index' in case else i
        return str(tuple(label) if isinstance(label,list) else label)
    if case['family']=='two-way':
        _,factors,_,_,_,_=twa.inputs(child)
        for i,source in enumerate(child['frame']):
            if source.get('Condition') not in names or twa.finite(source.get(case['column'])) is None:continue
            if any(source.get(f) is None or isinstance(source.get(f),float) and not math.isfinite(source[f]) for f in factors):continue
            rows.append({'group':source['Condition'],'metric':case['column'],'value':float(source[case['column']]),'observation_id':source_id(i)})
    else:
        covariates=model.named_list(p.get('covariates'));categorical=model.named_list(p.get('categorical_covariates'));data=child['data']
        for i,value in enumerate(data[p['outcome_col']]):
            try:valid=math.isfinite(float(value))
            except (TypeError,ValueError,OverflowError):valid=False
            group=data[p['group_col']][i]
            if not valid or group is None or str(group) not in names:continue
            omit=False
            for c in covariates:
                if c in categorical:omit=omit or data[c][i] is None
                else:
                    try:omit=omit or not math.isfinite(float(data[c][i]))
                    except (TypeError,ValueError,OverflowError):omit=True
            if omit:continue
            rows.append({'group':str(group),'metric':case['column'],'value':float(value),'observation_id':source_id(i)})
    return [row for name in names for row in rows if row['group']==name]


def report(case):
    returned=parent.report(case);child=parent.child_parameters(case)
    answer=twa.report(child) if case['family']=='two-way' else model.report(child)
    requested=child['parameters']['comparisons'];raw=nullable(returned['results_dict'])
    p={'metric':case['column'],'group_names':case['names'],'group_values':case['groups'],'test':returned['test'],'post_hoc':returned['post_hoc'],
        'normal':normality.report({'parameters':{'df_list':case['groups'],'make_plot':False}})['normal'],
        'overall':nullable(answer['overall']),'comparisons':requested,'pairwise_pvalues':nullable(answer['pvalues']),
        'raw_stats':{k:v for k,v in raw.items() if not k.startswith('_')}}
    if case['family']=='two-way':p['factor_terms']=child['parameters']['factors']+['Interaction','Residual']
    result=record.report({'parameters':p});result['test'].update(raw['_group_test'])
    return {'returned':returned,'records':[result],'plotted_data':observations(case)}
