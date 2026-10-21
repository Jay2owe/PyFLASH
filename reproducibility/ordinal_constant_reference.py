"""Free thresholds absorb a constant score; positive penalty uniquely sets zero coefficients.

This extends the accepted independent count-odds law to identical-row training
data. It adds no new fitting-engine or native-runtime vote.
"""
def report(case):
    from reproducibility.ordinal_zero_reference import report
    return {'returns_self':True,**report({**case,'features':len(case['constant']),'test_rows':len(case['held'])})}
