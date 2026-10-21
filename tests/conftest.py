"""Keep the local invariant/reference loop separate from complete verification."""
import pytest
from reproducibility.check_bootstrap import native_windows_information

# Plain declared pytest subprocesses need the same verification-only metadata
# fallback as the outer launcher; otherwise JUnit teardown can stall in WMI.
# This touches no product launch, input, numerical routine or performance budget.
native_windows_information()

# The unfiltered suite always includes every test. This list defines the cheap
# iteration loop, not scientific-completeness evidence or the release gate.
FAST_MODULES = frozenset({
    'test_independent_references.py', 'test_extended_references.py',
    'test_bootstrap_reference.py', 'test_state_atomicity.py',
    'test_describe_coverage.py',
    'test_scalar_contract_references.py',
    'test_cauchy_contract_reference.py',
    'test_bounded_cache.py',
    'test_association_specs_contract.py', 'test_effect_magnitude_contract.py',
})


def pytest_ignore_collect(collection_path, config):
    # Every test in these modules would receive the slow marker below. Avoid
    # importing them at all for the exact documented development command.
    # Unfiltered verification and other marker expressions still collect all.
    if (config.option.markexpr.strip() == 'not slow'
            and collection_path.is_file()
            and collection_path.name.startswith('test_')
            and collection_path.suffix == '.py'
            and collection_path.name not in FAST_MODULES):
        return True
    return None


def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name not in FAST_MODULES:
            item.add_marker(pytest.mark.slow)
