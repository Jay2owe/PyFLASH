"""Independent automatic choice is evaluated on the declared two-factor fitted-row scope."""
from copy import deepcopy
from reproducibility.comparison_parent_routing_reference import report as routing


def report(case):
    parameters=deepcopy(case['parameters']);child=case['parent']['child']
    return routing({'parameters':parameters,'groups':case['parent']['groups'],'two_way_child':child,'names':case['parent']['names']})
