from copy import deepcopy
import warnings
from PyFLASH import report

def production(case):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore');return report.build_comparison_record(**deepcopy(case['parameters']))
    except Exception as error:return {'error':type(error).__name__}
