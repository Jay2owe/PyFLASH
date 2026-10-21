"""Independent complete record composition from unchanged accepted correction arrays."""
from copy import deepcopy
import math
from reproducibility import comparison_record_reference as record
from reproducibility.correction_report_contract import decoded
CONVENTIONS=('uncorrected','holm','bh_q','bonferroni','sidak','westfall_young')


def nullable(value):
    if isinstance(value,dict):return {k:nullable(v) for k,v in value.items()}
    if isinstance(value,list):return [nullable(v) for v in value]
    return None if isinstance(value,float) and not math.isfinite(value) else value


def report(case):
    p=deepcopy(case['parameters']);audit=decoded(p.pop('correction_audit'));result=record.report({'parameters':p})
    if not audit:return result
    active=[key for key in CONVENTIONS if audit.get(key)];permutation=audit.get('permutation') or {};cutoff=permutation.get('alpha_star');alpha=audit.get('alpha',.05)
    labels=p.get('comparisons') or [];changes={}
    for i,pv in enumerate(audit.get('uncorrected') or []):
        label=labels[i] if i<len(labels) else str(i+1)
        accepted=[key for key in active if math.isfinite(audit[key][i]) and audit[key][i]<=alpha]
        if cutoff is not None and math.isfinite(pv) and pv<=cutoff:accepted.append('calibrated')
        changes[label]=accepted
    for i,pair in enumerate(result['pairwise']):
        for key in active:
            if i<len(audit[key]):pair['p_'+key]=nullable(audit[key][i])
        pair['significant_under']=changes.get(pair['comparison'],[])
    conventions=active+(['calibrated'] if cutoff is not None else [])
    contested=sorted(label for label,accepted in changes.items() if accepted and len(accepted)<len(conventions))
    result['correction']={'alpha':nullable(audit.get('alpha')),'reported':str(p['correction_reported']) if p.get('correction_reported') else None,
        'conventions':conventions,'contested':contested,'unavailable':audit.get('skipped') or None}
    for key in ('mode','n_perm'):
        if permutation.get(key) is not None:result['correction']['null_mode' if key=='mode' else key]=permutation[key]
    for key in ('alpha_star','alpha_bonferroni','fwer_if_uncorrected','fwer_of_bonferroni','p_floor','p_resolution'):
        if permutation.get(key) is not None:result['correction'][key]=nullable(permutation[key])
    if contested:result['headline']+='; correction-dependent: '+', '.join(contested)
    return result
