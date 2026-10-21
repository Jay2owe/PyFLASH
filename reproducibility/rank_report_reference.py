"""Independent complete rank reports, literal request and correction rules."""
from pathlib import Path
from functools import lru_cache
import importlib.util,json,math
from reproducibility.one_way_mathematical_reference import normalize,pairs,clean
from reproducibility.one_way_report_reference import CORRECTIONS,LABELS,adjusted,annotation
from reproducibility import permutation_contract as permutations,minp_contract as minp
from reproducibility import rank_mathematical_reference as maths
inputs=json.loads((Path(__file__).parent/'reference-sources/rank-reports/inputs/inputs.json').read_text())
RANGE=inputs['range_probabilities']
ALIASES={'Dunn':['dunn','dunns','dunns_test','dunn_test'],
         'Conover':['','conover','conover_test'],'Nemenyi':['nemenyi','nemenyi_test'],
         'DSCF':['dscf','dwass_steel_critchlow_fligner','dwass_steel','steel_dwass','dwass_steel_critchlow_flinger']}

def method(value):
    if value is None:return 'Conover'
    if not isinstance(value,str):raise ValueError('A named rank method is required')
    key=normalize(value)
    for name,aliases in ALIASES.items():
        if key in aliases:return name
    raise ValueError('Unknown rank method')

def correction(value,count):
    if value is None or normalize(value)=='auto':return 'bonferroni' if count>3 else 'none'
    key=normalize(value)
    if key=='two_stage_fdr_bky':return 'fdr_tsbky'
    for kind,aliases in CORRECTIONS.items():
        if key in aliases:return kind
    raise ValueError('Unknown correction')

@lru_cache(maxsize=128)
def null(sizes,ranked,statistic,count,exact):
    parameters={'group_sizes':list(sizes),'ranks':list(ranked),'statistic':statistic,
                'n_resamples':count,'exact_max':exact,'seed':0}
    flattened=permutations.mathematical({'parameters':parameters});k=len(sizes)
    allpairs=[(i,j) for i in range(k) for j in range(i+1,k)];offset=5+2*len(allpairs)
    flat=flattened[offset:];matrix=[flat[i:i+len(allpairs)] for i in range(0,len(flat),len(allpairs))]
    return allpairs,matrix,'sampled' if flattened[2] else 'exact'

def westfall(case,design,requested,values,statistic):
    sizes=design['sizes'];count=len(values)
    if case.get('audit','cheap') is False:return None,'Config.CORRECTION_AUDIT is off, so no permutation null was computed'
    if count<2:return None,('no comparisons were requested, so there is nothing to correct' if not count else 'a single comparison is not a family, so there is nothing to correct')
    if min(sizes)<2:return None,'a group of one carries no information to permute'
    if sum(sizes)>200:return None,f'pooled n={sum(sizes)} is above the 200 ceiling for the permutation audit'
    selected=[tuple(sorted(p)) for p in requested]
    if len(set(selected))!=count:return None,'reported comparisons do not match the null design'
    allpairs,matrix,mode=null(tuple(sizes),tuple(float(r) for r in design['ranks']),statistic,case.get('count',20000),case.get('exact_max',10000))
    indices=[allpairs.index(p) for p in selected]
    matrix=[[r[i] for i in indices] for r in matrix]
    return minp.mathematical({'parameters':{'pvalues':[None if math.isnan(v) else v for v in values],
        'null':{'p':matrix,'mode':mode}}}),None

def report(case):
    p=case['parameters'];raw={'caller-note':'retained'}
    try:
        groups=list(map(maths.sample,p['df_list']));name=method(p['posthoc']);requested=pairs(p['comparisons'],len(groups))
        wanted=correction(p['posthoc_correction'],len(requested));design=maths.geometry(groups)
        if not design['identified']:return {'pvalues':[],'annotations':[],'overall':['nan','nan'],'results_dict':raw,'method':name}
        raw['KW']=[design['h'],design['p']];raw['_group_test']={'symbol':'H','df':[len(groups)-1]}
        arrays={}
        for kind in (['Dunn','Conover'] if name in ('Dunn','Conover') else [name]):
            statistics=[];probabilities=[]
            for first,second in requested:
                value,probability,_=maths.pair(design,groups,first,second,kind)
                if kind=='DSCF' and not math.isnan(value):
                    a,b=sorted((first,second));probability=RANGE[f'rank-range.{case["dataset"]}.{a}.{b}']
                statistics.append(value);probabilities.append(probability)
            arrays[kind]=(statistics,probabilities)
        chosen=arrays[name][1];raw['Posthoc-Uncorrected']=[1,chosen]
        if name in ('Nemenyi','DSCF'):
            raw[name]=list(arrays[name]);raw['_audit_inputs']={'basis':'self_adjusted','family':'rank_unsupported',
                'reason':('Nemenyi uses a tie-corrected chi-square approximation; no permutation null is implemented for this method.' if name=='Nemenyi' else 'DSCF re-ranks each pair and uses the Gaussian studentised-range distribution; no permutation null is implemented for this method.')}
            display=name;reported=chosen
        else:
            raw['_audit_inputs']={'basis':'raw','family':'rank','statistic':name.lower(),
                'group_sizes':design['sizes'],'ranks':[float(v) for v in design['ranks']],'pairs':requested}
            correction_name=LABELS[wanted];failure=None;applied={}
            if wanted=='westfall_young':
                for kind in ('Conover','Dunn'):
                    applied[kind],reason=westfall(case,design,requested,arrays[kind][1],kind.lower())
                    if reason:failure=reason;break
                if failure:wanted=correction('auto',len(requested));correction_name=LABELS[wanted];raw['Correction-Unavailable']=[failure,math.nan]
            for kind in ('Conover','Dunn'):
                statistics,probabilities=arrays[kind]
                raw[kind+'-Bonferroni']=[statistics,adjusted(probabilities,'bonferroni')]
                raw[kind+'-Uncorrected']=[statistics,probabilities]
                if wanted!='westfall_young':applied[kind]=adjusted(probabilities,wanted)
                if correction_name not in ('Bonferroni','Uncorrected'):raw[kind+'-'+correction_name]=[statistics,applied[kind]]
            reported=applied[name];display=name+' '+correction_name;raw['_audit_inputs']['correction']=correction_name
        labels=[annotation(v,p['ns']) for v in reported]
        if 'style' in case:
            fallback=p['ns'];style=case['style']
            if fallback is None or fallback=='ns':fallback=style['significance_ns']
            labels=[]
            for probability in reported:
                label=round(probability,3) if fallback=='p' else fallback
                for threshold,symbol in sorted(style['significance_thresholds'].items(),key=lambda item:float(item[0])):
                    if probability<float(threshold):label=symbol;break
                labels.append(label)
        return clean({'pvalues':reported,'annotations':labels,'overall':[design['h'],design['p']],'results_dict':raw,'method':display})
    except (ValueError,TypeError):return {'error':'ValueError'}
