from copy import deepcopy
from PyFLASH import report

def production(case):
    try:return report.render_digest(deepcopy(case['summary']))
    except Exception as error:return {'error':type(error).__name__}
