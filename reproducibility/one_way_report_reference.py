"""Independent full group reports: exact geometry, frozen external tails and literal options.

No PyFLASH imports or production posthoc calculations. Accepted control references
are common independent inputs; native/mathematical replay checks their owners.
"""
from pathlib import Path
from copy import deepcopy
import json,math
from reproducibility import one_way_mathematical_reference as mathematics
from reproducibility import multiplicity_contract as adjustments
from reproducibility import value_permutation_contract as permutations
from reproducibility import minp_contract as minp
inputs=json.loads((Path(__file__).parent/'reference-sources/one-way/range-inputs/inputs.json').read_text())
range_values=inputs['range_probabilities']
control_fixture=json.loads((Path(__file__).parent/'fixtures/dunnett_reference.json').read_text())

def clean(value):
    if hasattr(value,'tolist'):value=value.tolist()
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    return mathematics.clean(value)


def annotation(probability,ns):
    if not math.isnan(probability):
        for threshold,label in ((.0001,'****'),(.001,'***'),(.01,'**'),(.05,'*')):
            if probability<threshold:return label
    return round(probability,3) if ns=='p' else ns


def control_answer(raw,requested):
    shared=set(requested[0])
    for pair in requested[1:]:shared &= set(pair)
    if len(shared)!=1:raise ValueError('Unidentified common control')
    control=shared.pop()
    candidates=[row for row in control_fixture['rows'] if row['case']['parameters']['groups']==raw
                and row['case']['parameters'].get('control',0)==control
                and row['case']['parameters'].get('alternative','two-sided')=='two-sided']
    if not candidates:raise ValueError('No accepted independent control reference for this input')
    answer=candidates[0]['expected']['rows'];indices=[i for i in range(len(raw)) if i!=control]
    lookup={index:row[1:] for index,row in zip(indices,answer)}
    statistics=[];probabilities=[]
    for first,second in requested:
        other=second if first==control else first
        statistic,probability=lookup[other]
        statistics.append(float(statistic));probabilities.append(float(probability))
    return statistics,probabilities


def canonical_reference(case):
    p=case['parameters'];raw={'caller-note':'retained'}
    try:
        groups=list(map(mathematics.sample,p['df_list']));kind=mathematics.posthoc(p['posthoc'])
        requested=mathematics.pairs(p['comparisons'],len(groups));label=mathematics.LABELS[kind]
        if kind=='dunnett':
            if not requested:raise ValueError('A common control is required')
            shared=set(requested[0])
            for pair in requested[1:]:shared &= set(pair)
            if len(shared)!=1:raise ValueError('A unique common control is required')
        design=mathematics.geometry(groups)
        if not design['identified']:
            return {'pvalues':[],'annotations':[],'overall':['nan','nan'],'results_dict':raw,'method':label}
        raw['OWA']=[design['f'],design['p']]
        raw['_group_test']={'symbol':'F','df':[len(groups)-1,design['df']]}
        statistics=[];probabilities=[]
        if kind=='dunnett':statistics,probabilities=control_answer(p['df_list'],requested)
        else:
            for first,second in requested:
                statistic,probability,q=mathematics.pair_geometry(groups,first,second)
                if kind=='tukey':
                    statistic=float(design['means'][first]-design['means'][second])
                    if math.isnan(q):probability=math.nan
                    elif math.isinf(q):probability=0.
                    else:
                        lo,hi=sorted((first,second));probability=range_values[f'one-way-range.{case["dataset"]}.{lo}.{hi}']
                elif kind=='scheffe':statistic=1;probability=mathematics.scheffe_probability(groups,first,second)
                elif kind=='tamhane':statistic=1;probability=mathematics.tamhane_probability(groups,first,second)
                statistics.append(statistic);probabilities.append(probability)
        raw[label.replace(' ','-')]=[statistics,probabilities]
        raw['Posthoc-Uncorrected']=[1,probabilities]
        if kind=='fisher_lsd':
            raw['_audit_inputs']={'basis':'raw','family':'value','statistic':'lsd',
                'groups':[[float(v) for v in g] for g in groups],'pairs':requested,'correction':'Uncorrected'}
        else:
            raw['_audit_inputs']={'basis':'self_adjusted','family':'value_unsupported',
              'reason':f'{label} already accounts for multiplicity; no permutation null is implemented for this method.'}
        return clean({'pvalues':probabilities,'annotations':[annotation(v,p['ns']) for v in probabilities],
                      'overall':[design['f'],design['p']],'results_dict':raw,'method':label})
    except (ValueError,TypeError):return {'error':'ValueError'}

CORRECTIONS={
 'bonferroni':['bonferroni','bonf','corrected','correction','adjusted','adjust','true','yes','y','on','1'],
 'sidak':['sidak','sidak_correction'], 'holm':['holm','holm_bonferroni'],
 'holm-sidak':['holm_sidak','hs'],'simes-hochberg':['simes_hochberg','hochberg','sh'],
 'hommel':['hommel'],'fdr_bh':['fdr','fdr_bh','bh','bh_q','benjamini_hochberg','benjaminihochberg'],
 'fdr_by':['fdr_by','by','benjamini_yekutieli','benjaminiyekutieli'],
 'fdr_tsbh':['fdr_tsbh','tsbh','two_stage_bh','two_stage_fdr_bh'],'fdr_tsbky':['fdr_tsbky','tsbky','two_stage_bky'],
 'westfall_young':['westfall_young','westfall','wy','permutation','perm','maxt','max_t'],
 'none':['','none','raw','p','uncorrected','unadjusted','no_correction','no_adjustment','false','no','n','off','0']}

LABELS={'none':'Uncorrected','bonferroni':'Bonferroni','sidak':'Sidak','holm':'Holm','holm-sidak':'Holm-Sidak',
 'simes-hochberg':'Simes-Hochberg','hommel':'Hommel','fdr_bh':'FDR-BH','fdr_by':'FDR-BY',
 'fdr_tsbh':'FDR-TSBH','fdr_tsbky':'FDR-TSBKY','westfall_young':'Westfall-Young'}

CORRECTIONS['fdr_bh'].remove('bh_q')

def correction(value):
    if value is None:return 'none'
    key=mathematics.normalize(value)
    if key=='auto':return 'none'
    for method,aliases in CORRECTIONS.items():
        if key in aliases:return method
    raise ValueError('Unknown correction')


def adjusted(raw,method):
    if method=='none':return raw
    cleaned=[None if math.isnan(v) else v for v in raw]
    values=adjustments.reference({'parameters':{'pvalues':cleaned},'canonical':method})
    return values[1+len(raw):]


def sampled(groups,requested,raw,count):
    p={'groups':groups,'n_resamples':count,'seed':0,'statistic':'lsd'}
    numbers=permutations.mathematical({'parameters':p});k=len(groups)
    allpairs=[(a,b) for a in range(k) for b in range(a+1,k)]
    offset=5+2*len(allpairs);flat=numbers[offset:]
    indices=[allpairs.index(tuple(sorted(pair))) for pair in requested]
    matrix=[[flat[start+i] for i in indices] for start in range(0,len(flat),len(allpairs))]
    return minp.mathematical({'parameters':{'pvalues':raw,'null':{'p':matrix,'mode':'sampled'}}})


def reference(case):
    p=case['parameters'];posthoc=p['posthoc']
    try:
        wanted=correction(p['posthoc_correction'])
        try:kind=mathematics.posthoc(posthoc);embedded=False
        except ValueError:
            if mathematics.normalize(posthoc) in ('bonferroni_dunn','dunn_bonferroni'):wanted='bonferroni'
            elif mathematics.normalize(posthoc) in ('sidak_bonferroni','bonferroni_sidak'):wanted='sidak'
            else:wanted=correction(posthoc)
            if wanted=='none':kind='fisher_lsd';embedded=False
            else:kind='fisher_lsd';embedded=True
        base=deepcopy(case);base['parameters']['posthoc']=mathematics.LABELS[kind]
        answer=canonical_reference(base)
        if 'error' in answer or not answer['pvalues'] and 'OWA' not in answer['results_dict']:return answer
        if kind!='fisher_lsd':return answer
        raw=[float(v) for v in answer['pvalues']];reported=raw;method=wanted;failure=None
        if method=='westfall_young':
            if case.get('audit', 'cheap') is False:failure='Config.CORRECTION_AUDIT is off, so no permutation null was computed'
            elif len(raw)<2:failure='a single comparison is not a family, so there is nothing to correct'
            elif len(set(tuple(sorted(pair)) for pair in mathematics.pairs(p['comparisons'],len(p['df_list']))))!=len(raw):
                failure='reported comparisons do not match the null design'
            if failure is not None:method='bonferroni' if len(raw)>3 else 'none'
            else:reported=sampled(p['df_list'],mathematics.pairs(p['comparisons'],len(p['df_list'])),raw,case['count'])
        if wanted!='westfall_young' or failure:reported=adjusted(raw,method)
        label=LABELS[method];display=label if embedded and failure is None else 'Fisher LSD'+(' '+label if label!='Uncorrected' else '')
        result=answer['results_dict'];del result['Fisher-LSD'];result[display.replace(' ','-')]=[result['Posthoc-Uncorrected'][0] if False else [float(v) for v in canonical_reference(base)['results_dict']['Fisher-LSD'][0]],reported]
        result['_audit_inputs']['correction']=label
        if failure:result['Correction-Unavailable']=[failure,'nan']
        answer['method']=display;answer['pvalues']=reported;answer['annotations']=[annotation(v,p['ns']) for v in reported]
        return clean(answer)
    except (ValueError,TypeError):return {'error':'ValueError'}


def report(case):
    answer=reference(case)
    if 'style' not in case or 'error' in answer:return answer
    style=case['style'];labels=[]
    fallback=case['parameters']['ns']
    if fallback is None or fallback=='ns':fallback=style['significance_ns']
    for probability in answer['pvalues']:
        label=round(probability,3) if fallback=='p' else fallback
        for threshold,symbol in sorted(style['significance_thresholds'].items(),key=lambda item:float(item[0])):
            if probability<float(threshold):label=symbol;break
        labels.append(label)
    answer['annotations']=labels
    return clean(answer)
