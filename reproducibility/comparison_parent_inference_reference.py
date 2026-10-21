"""Independent composition of previously accepted whole numerical report owners."""
from copy import deepcopy
from reproducibility import normality_parent_reference as normality
from reproducibility import variance_student_mathematical_reference as variance
from reproducibility import one_way_report_reference as one_way,welch_one_way_report_reference as welch
from reproducibility import rank_report_reference as rank,two_way_mathematical_reference as two_way
from reproducibility import linear_model_mathematical_reference as model
from reproducibility.reported_posthoc_statistic_reference import expected_report
from reproducibility.one_way_mathematical_reference import clean

def default_pairs(count):return [f'{first+1}-{first+gap+1}' for gap in range(1,count) for first in range(count-gap)]

def child_parameters(case):
    child=deepcopy(case['child']);p=child['parameters'];groups=case['groups'];tokens=p.get('comparisons')
    if tokens is None:p['comparisons']=default_pairs(len(groups))
    child['audit']=False
    if case['family']=='model':p['group_order']=case['names']
    if case['family']=='two-way':p['factors']=p.get('factors') or child.get('default_factors',['FactorA','FactorB'])
    return child

def report(case):
    groups=case['groups'];child=child_parameters(case);family=case['family']
    normal=normality.report({'parameters':{'df_list':groups,'make_plot':False}})
    screened=variance.variance_report({'df_list':groups,'method':'brown-forsythe','alpha':.05})
    if family=='one-way':answer=expected_report(child,one_way.report(child));test='One-Way ANOVA'
    elif family=='welch':answer=welch.report(child);test='Welch ANOVA'
    elif family=='rank':answer=rank.report(child);test='Kruskal-Wallis'
    elif family=='two-way':answer=two_way.report(child);test='Two-Way ANOVA'
    elif family=='model':answer=model.report(child);test='Linear Model'
    else:raise ValueError('Unknown complete report owner')
    if 'error' in answer:return answer
    raw=dict(normal['results_dict'])
    raw.update({key:value for key,value in screened['results_dict'].items() if key!='caller-note'})
    raw.update({key:value for key,value in answer['results_dict'].items() if key!='caller-note'})
    return clean({'test':test,'post_hoc':answer['method'],'annotation_objects':None,'results_dict':raw})
