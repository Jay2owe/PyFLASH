import warnings
from PyFLASH import report
from reproducibility.one_way_contract import clean

def production(case):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore');return clean(report.describe_group(case['name'],case['values']))
    except Exception as error:return {'error':type(error).__name__}
