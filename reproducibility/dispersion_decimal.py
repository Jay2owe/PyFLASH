"""Separate decimal Taylor-series geometry, exact ranks and native R inference.

No mpmath, numpy or PyFLASH geometry generates these answers.
"""
from decimal import Decimal as D, localcontext
from fractions import Fraction
import math

PI = D('3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534211706798214808651')


def sincos(x):
    x %= 2*PI
    if x > PI: x -= 2*PI
    sine, cosine, st, ct = x, D(1), x, D(1)
    for j in range(1, 250):
        st *= -x*x/((2*j)*(2*j+1))
        ct *= -x*x/((2*j-1)*(2*j))
        previous = (sine, cosine)
        sine += st
        cosine += ct
        if previous == (sine, cosine): break
    else: raise ArithmeticError('Decimal Taylor series did not converge')
    return sine, cosine


def atan(x):
    negative = x < 0
    x = abs(x)
    reciprocal = x > 1
    if reciprocal: x = 1/x
    halvings = 0
    while x > D('0.1'):
        x = x/(1+(1+x*x).sqrt())
        halvings += 1
    term, answer = x, x
    for j in range(1, 250):
        term *= -x*x
        before = answer
        answer += term/(2*j+1)
        if before == answer: break
    else: raise ArithmeticError('Decimal atan series did not converge')
    answer *= 2**halvings
    if reciprocal: answer = PI/2-answer
    return -answer if negative else answer


def atan2(y,x):
    if x == 0: return PI/2 if y > 0 else -PI/2
    result = atan(y/x)
    if x < 0: result += PI if y >= 0 else -PI
    return result


def geometry(row):
    with localcontext() as ctx:
        ctx.prec = 100
        period = D(row['parameters']['period'])
        groups = [[D(float(v)%float(period)) for v in g
                   if v is not None and math.isfinite(float(v))]
                  for g in row['parameters']['groups']]
        groups = [g for g in groups if len(g) >= 2]
        deviations, spreads, valid = [], [], True
        for group in groups:
            angles = [v*2*PI/period for v in group]
            vectors = [sincos(a) for a in angles]
            s,c = sum(v[0] for v in vectors), sum(v[1] for v in vectors)
            if (s*s+c*c).sqrt()/len(group) <= D(2.0**-52):
                valid = False
                spreads.append(math.nan)
                continue
            center = atan2(s,c)
            distances = []
            for angle in angles:
                distance = (angle-center) % (2*PI)
                if distance < 0: distance += 2*PI
                if distance > PI: distance = 2*PI-distance
                distances.append(distance)
            deviations.append(distances)
            spreads.append(float(sum(distances)/len(group)*period/(2*PI)))
        if not valid: return groups, None, spreads
        pooled = sorted(x for g in deviations for x in g)
        # Resolve only the final-digit uncertainty of 100-place arithmetic.
        clusters = []
        for x in pooled:
            if clusters and abs(x-clusters[-1][-1]) < D('1e-90'):
                clusters[-1].append(x)
            else: clusters.append([x])
        ranks = []
        for group in deviations:
            current = []
            for x in group:
                before = sum(x > y+D('1e-90') for y in pooled)
                count = sum(abs(x-y) < D('1e-90') for y in pooled)
                current.append(Fraction(2*before+count+1,2))
            ranks.append(current)
        return groups, ranks, spreads


def native_query(row):
    groups, ranks, spreads = geometry(row)
    k,n = len(groups),sum(map(len,groups))
    vector = lambda v:'c('+','.join('NaN' if math.isnan(float(x)) else repr(float(x)) for x in v)+')'
    if ranks is None or k < 2:
        return vector([math.nan,math.nan,k,n,*spreads])
    # R receives exact half-integer ranks, not lossy converted deviations.
    # Its independent tie correction and chi-square tail remain native.
    return ('local({ d<-list('+','.join(vector(v) for v in ranks)+'); '
            'h<-tryCatch({ z<-kruskal.test(d); c(unname(z$statistic),z$p.value) },'
            'error=function(e) c(NaN,NaN)); c(h,'+str(k)+','+str(n)+','+
            ','.join('NaN' if math.isnan(x) else repr(x) for x in spreads)+') })')
