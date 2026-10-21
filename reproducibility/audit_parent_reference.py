"""Independent complete application audit using accepted report/null equations."""
from fractions import Fraction
from copy import deepcopy
import math
from reproducibility import rank_report_reference as ranks
from reproducibility.correction_report_contract import ladder
from reproducibility.minp_contract import calibration,mathematical as minp
from reproducibility.one_way_mathematical_reference import pairs,clean
NO_NULL=('Westfall-Young needs a permutation null, which is not available for this test. Rank post-hocs (Dunn, Conover) support it; Welch ANOVA cannot, because permuting values across groups imposes the equal variance Welch exists to avoid.')

def unpack(value):
    if isinstance(value,dict):return {k:unpack(v) for k,v in value.items()}
    if isinstance(value,list):return [unpack(v) for v in value]
    return {'nan':math.nan,'inf':math.inf,'-inf':-math.inf}.get(value,value) if isinstance(value,str) else value

def reference(case):
    parent=case['parent'];answer=unpack(ranks.report(parent))
    if 'error' in answer:return {'error':answer['error']}
    raw=deepcopy(answer['results_dict']);strings={'caller-note':'retained'};observed=raw.get('Posthoc-Uncorrected',[None,None])[1]
    if not observed:return clean({'audit':None,'results_dict':raw,'results_strings':strings})
    inputs=raw.get('_audit_inputs',{});n=len(observed);requested=parent['parameters']['posthoc_correction'];applied=answer['method']
    if ranks.correction(requested,n)=='westfall_young' and 'Westfall-Young' not in applied and 'Correction-Unavailable' not in raw:
        raw['Correction-Unavailable']=[inputs.get('reason') or NO_NULL,math.nan]
    audit={'alpha':.05,**ladder([None if math.isnan(v) else v for v in observed]),'permutation':None};reason=None
    if case.get('tier','cheap') is not False and n>=2:
        if inputs.get('family')=='rank':
            sizes=inputs['group_sizes']
            if min(sizes)<2:reason='a group of one carries no information to permute'
            elif sum(sizes)>200:reason=f'pooled n={sum(sizes)} is above the 200 ceiling for the permutation audit'
            else:
                requested_pairs=pairs(parent['parameters']['comparisons'],len(sizes));selected=[tuple(sorted(p)) for p in requested_pairs]
                if len(set(selected))!=n:reason='reported comparisons do not match the null design'
                else:
                    allpairs,matrix,mode=ranks.null(tuple(sizes),tuple(inputs['ranks']),inputs['statistic'],parent.get('count',20000),parent.get('exact_max',10000))
                    positions=[allpairs.index(p) for p in selected];matrix=[[r[i] for i in positions] for r in matrix]
                    audit['westfall_young']=minp({'parameters':{'pvalues':[None if math.isnan(v) else v for v in observed],'null':{'p':matrix,'mode':mode}}})
                    valid=[i for i,v in enumerate(observed) if math.isfinite(v)]
                    if not valid:reason='no finite observed comparisons to calibrate'
                    else:
                        minima=[min(row[i] for i in valid) for row in matrix];count=len(matrix);k=len(valid)
                        audit['permutation']={'mode':mode,'n_perm':count,'n_arrangements':math.factorial(sum(sizes))//math.prod(math.factorial(v) for v in sizes),
                            'p_resolution':1/(count+int(mode=='sampled')),'p_floor':min(minima),
                            'fwer_if_uncorrected':float(Fraction(sum(v<=.05 for v in minima),count)),
                            'fwer_of_bonferroni':float(Fraction(sum(v<=.05/k for v in minima),count)),
                            'alpha_star':calibration(minima,.05,mode),'alpha_bonferroni':.05/k}
        else:reason=inputs.get('reason')
    if reason and not audit['permutation']:audit['skipped']=reason
    for key,label in [('uncorrected','Correction-Uncorrected'),('holm','Correction-Holm'),('bh_q','Correction-BH-q'),('bonferroni','Correction-Bonferroni'),('sidak','Correction-Sidak'),('westfall_young','Correction-WestfallYoung')]:
        if audit.get(key):raw[label]=[1,audit[key]]
    permutation=audit['permutation']
    if permutation:
        for key,label in [('alpha_star','Correction-AlphaStar'),('alpha_bonferroni','Correction-AlphaBonferroni'),('fwer_if_uncorrected','Correction-FWER-Uncorrected'),('fwer_of_bonferroni','Correction-FWER-Bonferroni'),('p_floor','Correction-pFloor'),('p_resolution','Correction-NullResolution')]:
            if permutation[key] is not None:raw[label]=[float(permutation[key]),math.nan]
        raw['Correction-NullMode']=[f'{permutation["mode"]} ({permutation["n_perm"]} perms)',math.nan]
    elif audit.get('skipped'):raw.setdefault('Correction-Unavailable',[audit['skipped'],math.nan])
    raw['Correction-Basis']=[inputs.get('basis','raw'),math.nan]
    labels=parent['parameters']['comparisons']
    if len(set(labels))!=len(labels):raw['Correction_verdict_error']=['Comparison display labels must be unique in a verdict report.',math.nan]
    else:
        descriptions=[]
        for i,label in enumerate(labels):
            names=[key for key in ('uncorrected','holm','bh_q','bonferroni','sidak','westfall_young') if audit.get(key) and math.isfinite(audit[key][i]) and audit[key][i]<=.05]
            if permutation and permutation['alpha_star'] is not None and math.isfinite(observed[i]) and observed[i]<=permutation['alpha_star']:names.append('calibrated')
            descriptions.append(f'{label}: significant under '+(', '.join(names) if names else 'no convention'))
        if descriptions:strings['Correction audit']=descriptions
    if permutation:
        calibrated=f'{permutation["alpha_star"]:.4f}' if permutation['alpha_star'] is not None else 'unattainable'
        strings['Correction calibration']=(f'calibrated alpha*={calibrated} vs Bonferroni {permutation["alpha_bonferroni"]:.4f}; uncorrected FWER {permutation["fwer_if_uncorrected"]:.3f}; smallest null raw p {permutation["p_floor"]:.4g}')
    raw['_correction_audit']=audit
    return clean({'audit':audit,'results_dict':raw,'results_strings':strings})
