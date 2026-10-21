"""Independent every-cell signed Tukey matrix and finite omission equations."""
from fractions import Fraction as Q
import math
from reproducibility import two_way_mathematical_reference as mathematics
from reproducibility.variance_student_mathematical_reference import sample
from reproducibility.one_way_mathematical_reference import clean

def reference(case):
    try:
        groups=list(map(sample,case['parameters']['groups']));k=len(groups)
        if k<2 or any(len(g)<2 for g in groups):return {'error':'ValueError'}
        means=[sum(g)/len(g) for g in groups];within=sum((sum((v-m)**2 for v in g) for g,m in zip(groups,means)),Q())
        statistics=[];probabilities=[]
        for first in range(k):
            statistics.append([]);probabilities.append([])
            for second in range(k):
                delta=means[first]-means[second];statistics[-1].append(mathematics.float_number(delta))
                if not within:probability=0. if delta else math.nan
                elif first==second:probability=1.
                else:
                    a,b=sorted((first,second));probability=mathematics.RANGE[f'two-way-range.{case["dataset"]}.{a}.{b}']
                probabilities[-1].append(probability)
        return clean({'statistics':statistics,'probabilities':probabilities})
    except (ValueError,TypeError):return {'error':'ValueError'}
