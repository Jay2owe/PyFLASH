"""Exact measured-input dot products and independently evaluated logistic CDF laws.

The supplied-state controls make no claim about estimating model parameters.
Native R corroborates ordinary states; double-dot and subnormal disagreements
remain diagnostics, never agreement votes. High-precision arithmetic shares
mpmath with the stable production response but uses CDF subtraction at 500 digits.
"""
from fractions import Fraction
def report(case):
    import mpmath as mp
    coefficients=list(map(Fraction.from_float,case['coef']))
    theta=list(map(Fraction.from_float,case['theta']))
    predictions=[];probabilities=[]
    with mp.workdps(500):
        for row in case['x']:
            score=sum((Fraction.from_float(v)*w for v,w in zip(row,coefficients)),Fraction(0))
            cumulative=[]
            for cut in theta:
                exact=cut-score;z=mp.mpf(exact.numerator)/exact.denominator
                cumulative.append(1/(1+mp.exp(-z)))
            predictions.append(case['first_label']+sum(score>cut for cut in theta))
            probabilities.append([float(value) for value in [cumulative[0],
                *[cumulative[i]-cumulative[i-1] for i in range(1,len(cumulative))],1-cumulative[-1]]])
    return {'predictions':predictions,'probabilities':probabilities}
