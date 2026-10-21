"""Independent complete before/after reports for changing two-factor design identity."""
from reproducibility.comparison_parent_inference_reference import report as parent_report


def report(case):
    return {'warm':parent_report(case['warm']),'after':parent_report(case['after'])}
