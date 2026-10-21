"""Exercise every complete get/set event through the real estimator wrapper."""
from PyFLASH.modelling import _PyFLASHOrdinalLogistic
from reproducibility.ordinal_parameter_reference import observe

def production(case):
    return observe(_PyFLASHOrdinalLogistic,case)
