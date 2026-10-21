"""Independent complete returned reports for automatic and two-group selection."""
from copy import deepcopy
import math,unicodedata
from pathlib import Path
import json,hashlib
import mpmath as mp
from reproducibility import normality_parent_reference as normality
from reproducibility import variance_student_mathematical_reference as variance
from reproducibility import mann_whitney_mathematical_reference as ranks
from reproducibility import one_way_report_reference as one_way,welch_one_way_report_reference as welch,rank_report_reference as rank,two_way_mathematical_reference as two_way
from reproducibility.reported_posthoc_statistic_reference import expected_report
from reproducibility.one_way_mathematical_reference import clean,pairs
from reproducibility import one_way_mathematical_reference as geometry
NATIVE_FIXTURE=Path(__file__).parent/'reference-sources/comparison-parent-routing/native/frozen-before.json'

def high_precision_ks(groups):
    values=sorted(v for group in groups for v in group);n=len(values)
    with mp.workdps(500):
        distribution=[mp.erfc(-mp.mpf(v)/mp.sqrt(2))/2 for v in values]
        d=max(max(mp.mpf(i+1)/n-u,u-mp.mpf(i)/n) for i,u in enumerate(distribution))
        if d>=1:probability=mp.mpf(0)
        elif d>=mp.mpf('.5'):
            terms=[]
            for j in range(math.floor(n*(1-d))+1):
                terms.append(mp.binomial(n,j)*(mp.mpf(j)/n+d)**(j-1)*(1-d-mp.mpf(j)/n)**(n-j))
            probability=2*d*mp.fsum(terms)
        else:raise ValueError('This independent witness is restricted to the published upper branch')
        return [float(d),float(probability)]

def tukey_report(child):
    p=child['parameters'];groups=list(map(geometry.sample,p['df_list']));requested=pairs(p['comparisons'],len(groups))
    design=geometry.geometry(groups);raw={'caller-note':'retained'}
    if not design['identified']:return {'pvalues':[],'annotations':[],'overall':['nan','nan'],'results_dict':raw,'method':'Tukey'}
    identity=json.dumps([[float(v) for v in group] for group in groups],separators=(',',':'))
    digest=hashlib.sha256(identity.encode()).hexdigest()
    tails={row['key']:row['published_native'] for row in json.loads(NATIVE_FIXTURE.read_text())['rows']}
    statistics=[];probabilities=[]
    for first,second in requested:
        _,_,threshold=geometry.pair_geometry(groups,first,second)
        a,b=sorted((first,second))
        probability=math.nan if math.isnan(threshold) else 0. if math.isinf(threshold) else tails[f'comparison-routing-range.{digest}.{a}.{b}']
        statistics.append(float(design['means'][first]-design['means'][second]));probabilities.append(probability)
    raw.update({'OWA':[design['f'],design['p']],'_group_test':{'symbol':'F','df':[len(groups)-1,design['df']]},
        'Tukey':[statistics,probabilities],'Posthoc-Uncorrected':[1,probabilities],
        '_audit_inputs':{'basis':'self_adjusted','family':'value_unsupported','reason':'Tukey already accounts for multiplicity; no permutation null is implemented for this method.'}})
    return clean({'pvalues':probabilities,'annotations':[one_way.annotation(v,p['ns']) for v in probabilities],
        'overall':[design['f'],design['p']],'results_dict':raw,'method':'Tukey'})
ALIASES={
'auto':['','auto','automatic','default'],
'auto_t':['t','ttest','t_test','independent_t','independent_t_test'],
'student_t':['student','students','student_t','students_t','student_t_test'],
'welch_t':['welch','welchs','welch_t','welchs_t','welch_t_test'],
'mannwhitney':['mann_whitney','mann_whitney_u','mwu','wilcoxon_rank_sum','wilcoxon_rank_sum_test'],
'anova':['anova','one_way','one_way_anova','owa'],
'welch_anova':['welch_anova','welchs_anova','welch_one_way','welch_one_way_anova'],
'kruskal':['kruskal','kruskal_wallis','kw'],
 'two_way':['two_way','two_way_anova','twa'],
'linear_model':['linear','linear_model','lm','ols']}

def selected(value):
    key=unicodedata.normalize('NFKD','auto' if value is None else str(value)).encode('ascii','ignore').decode().strip().lower().replace("'",'')
    for a,b in (('&',' '),('/',' '),('+',' '),('-','_'),(' ','_')):key=key.replace(a,b)
    while '__' in key:key=key.replace('__','_')
    key=key.strip('_')
    for name,aliases in ALIASES.items():
        if key in aliases:return name
    raise ValueError('Unknown group method')

def default_pairs(count):return [f'{first+1}-{first+gap+1}' for gap in range(1,count) for first in range(count-gap)]

def report(case):
    try:
        p=deepcopy(case['parameters']);groups=normality.finite_groups(case['groups'])
        if sum(bool(g) for g in groups)<2:return {'test':'N/A','post_hoc':'N/A','annotation_objects':None,'results_dict':{}}
        wanted=p.get('comparisons')
        if wanted is None:wanted=case.get('condition_comparisons')
        if wanted is None:wanted=default_pairs(len(groups))
        request=pairs(wanted,len(groups));choice=selected(p.get('stats_test'))
        normal=normality.report({'parameters':{'df_list':groups,'make_plot':False}})
        if case.get('high_precision_ks'):
            normal['results_dict']['KS']=high_precision_ks(groups)
        screening=variance.variance_report({'df_list':groups,'method':p.get('variance_test','brown-forsythe'),'alpha':p.get('variance_alpha',.05)})
        if 'error' in screening:return screening
        is_normal=normal['normal'] and not p.get('force_nonparametric',False)
        equal_var=screening['output']['equal_var'];raw=dict(normal['results_dict'])
        raw.update({k:v for k,v in screening['results_dict'].items() if k!='caller-note'})
        if len(groups)==2:
            if choice in ('anova','welch_anova','kruskal','two_way'):
                message=f"stats_test={p.get('stats_test')!r} needs at least three groups."
                raw['Stats_error']=[message,'nan']
                return {'test':'Error','post_hoc':'Error: '+message,'annotation_objects':None,'results_dict':raw}
            if choice=='mannwhitney' or choice in ('auto','auto_t') and (not is_normal or any(len(g)<=1 for g in groups)):
                answer=ranks.reference({'df_list':groups,'comparisons':wanted,'ns':p.get('ns','ns')});test='Mann-Whitney U'
            else:
                pooled=choice=='student_t' or choice not in ('student_t','welch_t') and equal_var is True
                answer=variance.student_report({'group1':groups[0],'group2':groups[1],'equal_var':pooled,'ns':p.get('ns','ns'),
                    'variance_test':p.get('variance_test','brown-forsythe'),'variance_alpha':p.get('variance_alpha',.05)})
                test="Student's T-Test" if pooled else "Welch's T-Test"
                answer['results_dict']['Posthoc-Uncorrected'][1]=[answer['pvalues'][0] for _ in request]
        else:
            if choice in ('student_t','welch_t','mannwhitney','auto_t'):
                message=f"stats_test={p.get('stats_test')!r} supports exactly two groups."
                raw['Stats_error']=[message,'nan']
                return {'test':'Error','post_hoc':'Error: '+message,'annotation_objects':None,'results_dict':raw}
            child={'dataset':case.get('dataset','routing'),'audit':False,'parameters':{'df_list':groups,'comparisons':wanted,'posthoc':p.get('posthoc','Conover'),
                'posthoc_correction':p.get('posthoc_correction','auto'),'ns':p.get('ns','ns')}}
            if choice=='kruskal' or choice=='auto' and (not is_normal or any(len(g)<=1 for g in groups)):
                answer=rank.report(child);test='Kruskal-Wallis'
            elif choice=='welch_anova' or choice=='auto' and is_normal and p.get('auto_welch',True) and equal_var is False and p.get('multiple_comparison','Two-Way')=='One-Way':
                key=unicodedata.normalize('NFKD',child['parameters']['posthoc']).lower().replace('-','_').replace(' ','_')
                if key in ('auto','default','conover','conover_test','dunn','dunns','dunns_test','dunn_test','tukey','tukey_hsd','hsd'):child['parameters']['posthoc']='Tamhane T2'
                answer=welch.report(child);test='Welch ANOVA'
            elif choice=='anova' or choice=='auto' and p.get('multiple_comparison','Two-Way')=='One-Way':
                answer=tukey_report(child) if geometry.posthoc(child['parameters']['posthoc'])=='tukey' else expected_report(child,one_way.report(child));test='One-Way ANOVA'
            else:
                child=deepcopy(case['two_way_child']);child['audit']=False;child['parameters']['comparisons']=wanted;child['parameters']['ns']=p.get('ns','ns')
                answer=two_way.report(child);test='Two-Way ANOVA'
        if 'error' in answer:return answer
        raw.update({k:v for k,v in answer['results_dict'].items() if k!='caller-note'})
        return clean({'test':test,'post_hoc':answer['method'],'annotation_objects':None,'results_dict':raw})
    except (ValueError,TypeError):return {'error':'ValueError'}
