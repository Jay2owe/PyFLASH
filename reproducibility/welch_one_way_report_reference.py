"""Independent complete weighted-ANOVA reports and literal unequal-variance options."""
from pathlib import Path
import json,math
from reproducibility import welch_one_way_mathematical_reference as maths
from reproducibility.one_way_mathematical_reference import pairs,normalize,clean
from reproducibility.one_way_report_reference import annotation
from reproducibility.reported_posthoc_statistic_reference import expected_report
inputs=json.loads((Path(__file__).parent/'reference-sources/anova-reports/welch-range-inputs/inputs.json').read_text())
ALIASES={'tamhane':['','auto','default','tamhane','tamhanes','tamhane_t2','tamhanes_t2'],
         'games_howell':['games_howell','games_howells','gh']}

LABELS={'tamhane':'Tamhane T2','games_howell':'Games-Howell'}

def posthoc(value):
    key=normalize('auto' if value is None else value)
    for kind,aliases in ALIASES.items():
        if key in aliases:return kind
    raise ValueError('Unknown unequal-variance posthoc')

def reference(case):
    p=case['parameters'];raw={'caller-note':'retained'}
    try:
        groups=list(map(maths.sample,p['df_list']));kind=posthoc(p['posthoc'])
        requested=pairs(p['comparisons'],len(groups));label=LABELS[kind]
        design=maths.geometry(groups)
        if not design['identified']:return {'pvalues':[],'annotations':[],'overall':['nan','nan'],'results_dict':raw,'method':label}
        raw['Welch ANOVA']=[design['f'],design['p']];raw['_group_test']={'symbol':'F','df':design['df']}
        statistics=[];probabilities=[]
        for first,second in requested:
            q,probability,degrees=maths.pair_geometry(groups,first,second)
            if kind=='games_howell':
                statistic=q
                if math.isnan(q):probability=math.nan
                elif math.isinf(q):probability=0.
                else:
                    lo,hi=sorted((first,second));probability=inputs['range_probabilities'][f'welch-range.{case["dataset"]}.{lo}.{hi}']
            else:
                statistic=1
                if probability==1:probability=1.
                elif math.isfinite(probability):probability=-math.expm1(len(groups)*(len(groups)-1)//2*math.log1p(-probability))
            statistics.append(statistic);probabilities.append(probability)
        raw[label.replace(' ','-')]=[statistics,probabilities];raw['Posthoc-Uncorrected']=[1,probabilities]
        raw['_audit_inputs']={'basis':'self_adjusted','family':'unequal_variance',
            'reason':'Permuting values across groups imposes equal variance, which is the assumption Welch ANOVA is chosen to avoid, so a permutation null here would be wrong rather than approximate. Games-Howell and Tamhane T2 carry their own correction; a studentised bootstrap would be needed for a calibrated alternative.'}
        return clean({'pvalues':probabilities,'annotations':[annotation(v,p['ns']) for v in probabilities],
            'overall':[design['f'],design['p']],'results_dict':raw,'method':label})
    except (ValueError,TypeError):return {'error':'ValueError'}

def report(case):return expected_report(case,reference(case),welch=True)
