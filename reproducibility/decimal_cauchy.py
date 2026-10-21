"""A second ACAT benchmark using only decimal series, without mpmath/SciPy."""
from decimal import Decimal as D, localcontext
import math


def _atan_small(x):
    total, power = x, x
    for index in range(1, 500):
        power *= -x*x
        term = power/(2*index+1)
        total += term
        if abs(term) < D('1e-85'):
            return total
    raise ArithmeticError('Decimal arctangent did not converge.')


def reference(row):
    values = [float(v) for v in row['parameters']['pvalues']
              if v is not None and math.isfinite(float(v))]
    if not values:
        return [math.nan]
    with localcontext() as context:
        context.prec = 95
        pi = 16*_atan_small(D(1)/5)-4*_atan_small(D(1)/239)
        transformed = []
        for value in values:
            p = D.from_float(max(1e-15, min(1-1e-15, value)))
            sign = -1 if p > D('.5') else 1
            angle = pi*(1-p if sign == -1 else p)
            sine, cosine = angle, D(1)
            sterm, cterm = angle, D(1)
            for index in range(1, 150):
                sterm *= -angle*angle/((2*index)*(2*index+1))
                cterm *= -angle*angle/((2*index-1)*(2*index))
                sine += sterm
                cosine += cterm
                if max(abs(sterm), abs(cterm)) < D('1e-85'):
                    break
            transformed.append(sign*cosine/sine)
        statistic = sum(transformed)/len(values)
        positive = abs(statistic)
        reciprocal = positive > 1
        x = 1/positive if reciprocal else positive
        multiplier = 1
        while x > D('.1'):
            x = x/(1+(1+x*x).sqrt())
            multiplier *= 2
        angle = multiplier*_atan_small(x)
        if reciprocal:
            angle = pi/2-angle
        if statistic < 0:
            angle = -angle
        return [float(D('.5')-angle/pi)]
