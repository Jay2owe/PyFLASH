"""Exact-count optimum of the published immediate-threshold logistic loss.

Each threshold separates two neighbouring categories. With zero features its
unconstrained odds are their count ratio. Ordered thresholds pool violating
adjacent ratios; positive regularization uniquely sets every coefficient to
zero. This is a mathematical benchmark, not a second classifier package.
"""
import mpmath as mp


def report(case):
    counts=case['counts'];blocks=[]
    for j in range(len(counts)-1):
        blocks.append(([j],counts[j],counts[j+1]))
        while len(blocks)>1 and blocks[-2][1]*blocks[-1][2]>blocks[-1][1]*blocks[-2][2]:
            right=blocks.pop();left=blocks.pop()
            blocks.append((left[0]+right[0],left[1]+right[1],left[2]+right[2]))
    theta=[None]*(len(counts)-1);cdf=[None]*(len(counts)-1)
    with mp.workdps(80):
        for indices,a,b in blocks:
            for index in indices:theta[index]=float(mp.log(mp.mpf(a)/b));cdf[index]=mp.mpf(a)/(a+b)
        probabilities=[float(value) for value in [cdf[0],*[cdf[i]-cdf[i-1] for i in range(1,len(cdf))],1-cdf[-1]]]
    label=case['first_label']+sum(value<0 for value in theta)
    return {'coef':[0.]*case['features'],'theta':theta,'classes':list(range(case['first_label'],case['first_label']+len(counts))),
        'predictions':[label]*case['test_rows'],'probabilities':[probabilities[: ] for _ in range(case['test_rows'])]}
