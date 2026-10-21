"""One script header for captured inputs, configuration, code and dependencies."""
from importlib.metadata import version
from PyFLASH._persistence import code_identity


def input_guard_lines(records):
    lines = []
    for item in records:
        lines += [f"INPUT = Path({item['path']!r})", 'digest = hashlib.sha256()',
                  "with INPUT.open('rb') as stream:",
                  "    for chunk in iter(lambda: stream.read(1024 * 1024), b''):",
                  '        digest.update(chunk)',
                  f"assert digest.hexdigest() == {item['sha256']!r}, 'Input content changed: '+str(INPUT)"]
    return lines


def dependency_guard_lines():
    from PyFLASH.dependencies import check
    return ['from importlib.metadata import PackageNotFoundError',
            f"DEPENDENCIES = { {entry['package']:entry['version'] for entry in check()}!r}",
            'for name, expected in DEPENDENCIES.items():',
            '    try:', '        installed = version(name)',
            '    except PackageNotFoundError:', '        installed = None',
            "    assert installed == expected, f'Dependency changed: {name}'"]


def guard_lines(*, source=None, source_sha256=None, input_records=(), save_mode=None):
    """Build guards before loading data or invoking a result-producing callable."""
    from PyFLASH.config import config_snapshot
    lines = ['import sys', "if hasattr(sys.stdout, 'reconfigure'):",
             "    sys.stdout.reconfigure(encoding='utf-8')",
             'from pathlib import Path', 'import hashlib', 'import PyFLASH',
             'from importlib.metadata import version',
             f"assert version('PyFLASH-analysis') == {version('PyFLASH-analysis')!r}, 'PyFLASH version changed'",
             'from PyFLASH.config import Config']
    if save_mode is not None:
        lines += [f'Config.SAVE_MODE = {save_mode!r}']
    if source is not None:
        if source_sha256 is None:
            from PyFLASH._cache_identity import file_hash
            source_sha256 = file_hash(source)
        lines += [f'SOURCE = Path({str(source)!r})', 'digest = hashlib.sha256()',
                  "with SOURCE.open('rb') as stream:",
                  "    for chunk in iter(lambda: stream.read(1024 * 1024), b''):",
                  '        digest.update(chunk)',
                  f"assert digest.hexdigest() == {source_sha256!r}, 'Input content changed'"]
    lines += [f'CONFIGURATION = {config_snapshot()!r}',
              'for name, value in CONFIGURATION.items():', '    setattr(Config, name, value)',
              f'CODE_IDENTITY = {code_identity()!r}',
              'from PyFLASH._persistence import code_identity as _current_code_identity',
              "assert _current_code_identity() == CODE_IDENTITY, 'Code changed'",
              'PACKAGE = Path(PyFLASH.__file__).parent']
    lines += dependency_guard_lines()
    lines += input_guard_lines(input_records)
    return lines


def source_load_lines(*, target, source_expression, source_sha256,
                      source_kind="pickle", csv_constructor=None):
    """Load only the same bytes captured by the common script guards."""
    if source_sha256 is None:
        raise ValueError('A captured input hash is required to replay a source.')
    if source_kind not in {'pickle', 'csv', 'demo'}:
        raise ValueError('Unknown source kind: ' + str(source_kind))
    if source_kind == "pickle":
        return ['from PyFLASH.serialization import _load_cached_state',
                f'{target} = _load_cached_state({source_expression}, expected_sha256={source_sha256!r})']
    if csv_constructor is None:
        raise ValueError('CSV loading requires the caller-owned dataframe construction.')
    return ['from PyFLASH._cache_identity import read_csv_verified',
            f'_source_frame, _consumed_sha256 = read_csv_verified({source_expression}, expected_sha256={source_sha256!r})',
            csv_constructor]
