"""Shared, read-only input loading and receipts for the manuscript API scripts."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + '\n', encoding='utf-8')


def load_summary(path):
    """CSV or a trusted, locally supplied PyFLASH Batch pickle; no data discovery."""
    import pandas as pd
    path = Path(path).resolve()
    if path.suffix.lower() == '.csv':
        frame = pd.read_csv(path)
    elif path.suffix.lower() in {'.pkl', '.pickle'}:
        from PyFLASH import load_state
        frame = load_state(str(path), verbose=False).summary.copy()
    else:
        raise ValueError('Input must be a summary CSV or a trusted PyFLASH Batch pickle.')
    if frame.empty or frame.columns.duplicated().any():
        raise ValueError('Input has no rows or has duplicate column names.')
    return frame


def require_columns(frame, columns):
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f'Missing required columns: {missing}')


def exclude_device_failure(frame, subject, identifier):
    """Apply the explicitly confirmed participant identifier to every analysis."""
    if identifier is None:
        return frame.copy()
    selected = frame[subject].astype(str).eq(str(identifier))
    if selected.sum() != 1 or frame.loc[selected, 'Diagnosis'].iloc[0] != 'AD':
        raise ValueError('The device-failure identifier must match exactly one AD participant.')
    return frame.loc[~selected].copy()


def compare_reference(actual, reference):
    """Compare the same ordered CSV columns/rows; numeric tolerance 1e-8/1e-10."""
    import pandas as pd
    expected = pd.read_csv(reference)
    pd.testing.assert_frame_equal(actual.reset_index(drop=True), expected,
                                  check_dtype=False, rtol=1e-8, atol=1e-10)


@contextmanager
def run_output(output, *, inputs, parameters):
    """Refuse an existing output directory and preserve success/failure receipts."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'Choose a new output folder: {output}')
    sources = [Path(path).resolve() for path in inputs]
    fingerprints = {str(path): sha256(path) for path in sources}
    output.mkdir(parents=True)
    receipt = {'started_utc': datetime.now(timezone.utc).isoformat(),
               'status': 'running', 'parameters': parameters,
               'input_sha256': fingerprints, 'python': platform.python_version(),
               'reproduction_claim': 'Methods implemented; final-paper identity requires comparison with the approved original results.'}
    receipt['versions'] = {}
    for name in ['PyFLASH-analysis', 'numpy', 'pandas', 'scipy', 'statsmodels']:
        try:
            receipt['versions'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            receipt['versions'][name] = 'not installed'
    receipt['script_sha256'] = {p.name: sha256(p) for p in Path(__file__).parent.glob('*.py')}
    import PyFLASH
    package_root = Path(PyFLASH.__file__).resolve().parent
    receipt['pyflash_source_sha256'] = {p.relative_to(package_root).as_posix(): sha256(p)
                                        for p in package_root.rglob('*.py')}
    try:
        root = Path(__file__).resolve().parents[2]
        receipt['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        receipt['git_worktree_changes'] = subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True, stderr=subprocess.DEVNULL).splitlines()
    except (OSError, subprocess.CalledProcessError):
        receipt['git_commit'] = None
    write_json(output / 'run_receipt.json', receipt)
    try:
        yield receipt
        receipt['status'] = 'passed'
    except BaseException as exc:
        receipt['status'] = 'failed'
        receipt['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        receipt['output_sha256'] = {p.relative_to(output).as_posix(): sha256(p) for p in output.rglob('*.csv')}
        write_json(output / 'run_receipt.json', receipt)
