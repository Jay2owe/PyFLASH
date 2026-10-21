"""Independent exact effect estimates composed with accepted full parent inference."""
from fractions import Fraction as Q
from copy import deepcopy
import math
import mpmath as mp
from reproducibility import comparison_parent_inference_reference as inference,comparison_parent_routing_reference as routing
from reproducibility.normality_parent_reference import finite_groups


def standardized(a,b):
    if min(len(a),len(b))<2:return math.nan
    a,b=[list(map(Q,g)) for g in (a,b)];ma,mb=sum(a)/len(a),sum(b)/len(b)
    variance=(sum((v-ma)**2 for v in a)+sum((v-mb)**2 for v in b))/(len(a)+len(b)-2)
    if not variance:return math.nan
    with mp.workdps(80):
        difference=ma-mb
        value=(mp.mpf(difference.numerator)/difference.denominator)/mp.sqrt(mp.mpf(variance.numerator)/variance.denominator)
        return float(value*(1-mp.mpf(3)/(4*(len(a)+len(b))-9)))


def anova(groups):
    groups=[list(map(Q,g)) for g in groups if g];k=len(groups);n=sum(map(len,groups))
    if k<2:return {}
    means=[sum(g)/len(g) for g in groups];grand=sum(sum(g) for g in groups)/n
    between=sum(len(g)*(m-grand)**2 for g,m in zip(groups,means));within=sum(sum((v-m)**2 for v in g) for g,m in zip(groups,means));total=between+within
    return {'eta_squared':float(between/total) if total else math.nan,
        'omega_squared':float((between-(k-1)*within/(n-k))/(total+within/(n-k))) if n>k and total+within/(n-k) else math.nan}


def epsilon(groups):
    groups=[g for g in groups if g];k=len(groups);n=sum(map(len,groups))
    if k<2 or n<=k:return math.nan
    pool=sorted(v for g in groups for v in g);ranks={};ties=[];index=0
    while index<n:
        end=index+1
        while end<n and pool[end]==pool[index]:end+=1
        ranks[pool[index]]=Q(index+1+end,2);ties.append(end-index);index=end
    correction=1-Q(sum(t**3-t for t in ties),n**3-n)
    if not correction:return math.nan
    h=(Q(12,n*(n+1))*sum(sum(ranks[v] for v in g)**2/len(g) for g in groups)-3*(n+1))/correction
    return float((h-k+1)/(n-k))


def rank(a,b):
    if not a or not b:return math.nan
    return float(Q(sum((x>y)-(x<y) for x in a for y in b),len(a)*len(b)))


def report(case):
    original=case['parent'];owner=case['owner'];answer=deepcopy(inference.report(original) if owner=='inference' else routing.report(original))
    if 'error' in answer or answer['test'] in ('N/A','Error'):return answer
    test=answer['test'];groups=finite_groups(original['groups']);parameters=original['child']['parameters'] if owner=='inference' else original['parameters']
    if test=='Linear Model':return answer
    comparisons=parameters.get('comparisons')
    if comparisons is None:comparisons=original.get('condition_comparisons')
    if comparisons is None:comparisons=inference.default_pairs(len(groups))
    raw=answer['results_dict'];overall=anova(groups) if test=='One-Way ANOVA' else {'epsilon_squared':epsilon(groups)} if test=='Kruskal-Wallis' else {}
    for key,value in overall.items():raw[f'Effect overall ({key})']=[value,math.nan]
    nonparametric=test in ('Kruskal-Wallis','Mann-Whitney U');metric='rank_biserial_r' if nonparametric else 'hedges_g'
    for token in comparisons:
        a,b=map(int,token.split('-'));value=rank(groups[a-1],groups[b-1]) if nonparametric else standardized(groups[a-1],groups[b-1])
        raw[f'Effect {token} ({metric})']=[value,[math.nan,math.nan]]
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
        if isinstance(value,list):return [clean(v) for v in value]
        return str(value) if isinstance(value,float) and not math.isfinite(value) else value
    return clean(answer)
