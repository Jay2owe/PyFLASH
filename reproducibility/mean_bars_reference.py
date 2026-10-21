"""Exact supplied-input means and high precision standard errors."""
from fractions import Fraction
import math
def finite(values):
    out = []
    for value in values:
        try: parsed = float(value)
        except (ValueError, TypeError, OverflowError): continue
        if math.isfinite(parsed): out.append(Fraction.from_float(parsed))
    return out

def reference(groups, normalize):
    import mpmath as mp
    mp.mp.dps = 300
    bars, points, uncertainty = [], [], []
    for index, group in enumerate(groups):
        values = finite(group)
        if normalize and values and min(values) != max(values):
            low, span = min(values), max(values)-min(values)
            values = [(v-low)*100/span for v in values]
        if not values: continue
        mean = sum(values) / len(values)
        variance = sum((v-mean)**2 for v in values) / (len(values)-1) if len(values)>1 else Fraction(0)
        sem = mp.sqrt(mp.mpf(variance.numerator)/variance.denominator/len(values))
        bars.append({'group': index, 'height': float(mean)})
        points.append({'group': index, 'y': [float(v) for v in values]})
        uncertainty.append({'group': index, 'sem': float(sem), 'tip': float(mp.mpf(mean.numerator)/mean.denominator+sem)})
    return {'bars': bars, 'points': points, 'uncertainty': uncertainty, 'ticks': list(range(len(groups))), 'labels': ['A', 'B']}

def _report(case):
    import mpmath as mp
    result=reference(case['request']['groups'],case['request']['normalize'])
    for bar,interval in zip(result['bars'],result['uncertainty']):
        if bar['height']<0:
            raw=finite(case['request']['groups'][bar['group']]);mean=sum(raw)/len(raw)
            variance=sum((v-mean)**2 for v in raw)/(len(raw)-1) if len(raw)>1 else Fraction(0)
            sem=mp.sqrt(mp.mpf(variance.numerator)/variance.denominator/len(raw))
            interval['tip']=float(mp.mpf(mean.numerator)/mean.denominator-sem)
    return result

def report(case):
    import mpmath as mp
    with mp.workdps(300):
        return _report(case)
