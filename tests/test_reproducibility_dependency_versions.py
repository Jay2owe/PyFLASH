"""Every declared scientific dependency must appear in a workflow receipt."""
from importlib.metadata import PackageNotFoundError
from PyFLASH import dependencies
from reproducibility import run


def test_receipt_includes_declared_installed_and_missing_dependencies(monkeypatch):
    monkeypatch.setattr(dependencies, 'registry', lambda: {
        'owned-core-engine': {'groups': ['core']},
        'owned-optional-engine': {'groups': ['classification']},
    })
    def version(name):
        if name == 'owned-optional-engine':
            raise PackageNotFoundError(name)
        return '3.0'
    monkeypatch.setattr(run, 'version', version)
    result = run.versions()
    assert result['owned-core-engine'] == '3.0'
    assert result['owned-optional-engine'] == 'unavailable'
    assert result['PyFLASH-analysis'] == '3.0'
    assert result['python']
