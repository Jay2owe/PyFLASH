from copy import deepcopy
from PyFLASH import report
from reproducibility.correction_report_contract import decoded

def production(case):
    p=deepcopy(case['parameters']);p['correction_audit']=decoded(p['correction_audit'])
    try:return report.build_comparison_record(**p)
    except Exception as error:return {'error':type(error).__name__}
