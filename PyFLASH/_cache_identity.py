"""Content identities for derived batches, without loading image pixels."""
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path


def analysis_value(value, *, allow_opaque=False):
    """Exact JSON-safe choices; never truncate array contents or stringify objects.

    Unsupported state cannot establish cache identity. Callers may still run
    it freshly, but must mark its result unverified for subsequent reuse.
    """
    import math
    from collections.abc import Mapping
    import numpy as np
    import pandas as pd

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {'float': value.hex()}
    if isinstance(value, np.generic):
        return {'numpy_scalar': str(value.dtype), 'value': analysis_value(value.item(), allow_opaque=allow_opaque)}
    if isinstance(value, Mapping):
        # Preserve key types; str(1) and str('1') must not collide.
        import json
        items = [[analysis_value(key, allow_opaque=allow_opaque), analysis_value(item, allow_opaque=allow_opaque)] for key, item in value.items()]
        return {'mapping': sorted(items, key=lambda item: json.dumps(item[0], sort_keys=True))}
    if isinstance(value, (list, tuple)):
        return [analysis_value(item, allow_opaque=allow_opaque) for item in value]
    if isinstance(value, (set, frozenset)):
        import json
        return {'set': sorted((analysis_value(item, allow_opaque=allow_opaque) for item in value),
                              key=lambda item: json.dumps(item, sort_keys=True))}
    if isinstance(value, np.ndarray):
        return {'array': analysis_value(value.tolist(), allow_opaque=allow_opaque), 'shape': list(value.shape),
                'dtype': str(value.dtype)}
    if isinstance(value, (pd.Series, pd.Index)):
        return {'values': analysis_value(value.tolist(), allow_opaque=allow_opaque), 'dtype': str(value.dtype),
                'name': analysis_value(value.name, allow_opaque=allow_opaque),
                'index': analysis_value(value.index, allow_opaque=allow_opaque) if isinstance(value, pd.Series) else None}
    if value is pd.NA or value is pd.NaT:
        return {'missing': type(value).__name__}
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return {'type': type(value).__name__, 'value': value.isoformat()}
    if isinstance(value, Path):
        return {'path': str(value)}
    if allow_opaque:
        description = {'unverified_type': type(value).__module__ + '.' + type(value).__qualname__}
        if callable(value):
            try:
                description['callable'] = value.__module__ + '.' + value.__qualname__
            except AttributeError:
                pass
        return description
    raise TypeError(f'Cannot authenticate analysis choice of type {type(value).__name__}.')


def analysis_identity(frame, parameters, *, context=None):
    """Content, choices and runtime identity for safe reuse of table analyses."""
    import json
    import sys
    import pandas as pd
    from PyFLASH._persistence import code_identity
    from PyFLASH.dependencies import check
    from PyFLASH.config import config_snapshot
    import PyFLASH

    sources = code_identity()
    if PyFLASH._LOADED_SOURCE_IDENTITY != sources:
        raise RuntimeError('Package source changed after import; restart Python before running analyses.')

    digest = sha256()
    def feed(value):
        digest.update(json.dumps(analysis_value(value), sort_keys=True,
                                 separators=(',', ':'), allow_nan=False).encode('utf-8'))
        digest.update(b'\n')
    feed(list(frame.columns))
    feed(list(frame.index.names))
    feed(str(frame.index.dtype))
    feed(frame.index.tolist())
    for _, series in frame.items():
        feed(str(series.dtype))
        if isinstance(series.dtype, pd.CategoricalDtype):
            feed(series.cat.categories)
            feed(series.cat.ordered)
        # Stream cells rather than copying a potentially large input table.
        for item in series:
            feed(item)
    choices = analysis_value(parameters)
    return {'schema_version': 1, 'input_sha256': digest.hexdigest(),
            'parameters': choices, 'context': analysis_value(context),
            'runtime': {'package': version('PyFLASH-analysis'),
                        'python': list(sys.version_info[:3]), 'code': sources,
                        'dependencies': {entry['package']: entry['version'] for entry in check('core')},
                        'config': analysis_value(config_snapshot())}, 'reusable': True}


def file_hash(path):
    digest = sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def condition_identity(conditions):
    def entry(item):
        result = {key: getattr(item, key, None) for key in
                  ('name', 'label', 'color', 'style', 'factor', 'factor_explanation')}
        if hasattr(item, 'conditionsList'):
            result['components'] = [entry(value) for value in item.conditionsList]
        return result
    return {'conditions': [entry(item) for item in conditions],
            'comparisons': conditions.comparisons, 'factor': conditions.factor}


def batch_identity(experiments, conditions, *, threshold, import_images):
    from PyFLASH.config import config_snapshot
    from PyFLASH._persistence import code_identity
    from PyFLASH.experiment import ATTRIBUTE_DICT, _resolve_image_folder, IMAGE_EXTENSIONS
    from PyFLASH.dependencies import check
    sources = []
    for experiment in experiments:
        root = Path(experiment.filePath).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f'Cannot verify cached inputs: {root}')
        paths = []
        for child in sorted(root.iterdir()):
            if child.is_file() and child.suffix.lower() in {'.csv', '.zip'}:
                paths.append(child)
            elif child.is_dir() and child.name in ATTRIBUTE_DICT:
                paths.extend(path for path in sorted(child.iterdir())
                             if path.is_file() and path.suffix.lower() in {'.csv', '.zip'})
        records = [{'path': path.relative_to(root).as_posix(), 'sha256': file_hash(path)} for path in paths]
        images = []
        if import_images:
            image_root = _resolve_image_folder(experiment)
            if image_root:
                image_root = Path(image_root)
                # importImages derives its table from names, not image pixels.
                # Pixels remain on disk and are read afresh by image operations.
                images = [path.relative_to(image_root).as_posix() for path in sorted(image_root.rglob('*'))
                          if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
        sources.append({'name':experiment.name, 'threshold':experiment.threshold, 'root':str(root), 'tables':records,
                        'image_catalogue':images})
    return {'schema_version':1, 'version':version('PyFLASH-analysis'), 'code':code_identity(),
            'dependencies': {entry['package']: entry['version'] for entry in check('core')},
            'sources':sources, 'conditions':condition_identity(conditions),
            'settings':{'threshold':threshold, 'import_images':bool(import_images), 'config':config_snapshot()}}


from contextlib import contextmanager


@contextmanager
def _capture_source(path):
    """Freeze and hash one consumed source, spilling large tables to temp disk."""
    import shutil
    import tempfile
    path = Path(path)
    size = path.stat().st_size
    memory_limit = 8 * 1024**2
    if size > memory_limit and shutil.disk_usage(tempfile.gettempdir()).free < size:
        raise OSError("Insufficient temporary space to capture this source table.")
    with tempfile.SpooledTemporaryFile(max_size=memory_limit, mode="w+b") as snapshot:
        digest = sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                snapshot.write(chunk)
                digest.update(chunk)
        snapshot.seek(0)
        yield snapshot, digest.hexdigest()


def read_csv_verified(path, *, expected_sha256=None, **parameters):
    """Parse captured bytes and refuse a mismatched or subsequently changed input."""
    import pandas as pd
    from pandas.io.common import infer_compression
    path = Path(path)
    expected = file_hash(path) if expected_sha256 is None else expected_sha256
    options = dict(parameters)
    if options.get('compression', 'infer') == 'infer':
        options['compression'] = infer_compression(str(path), 'infer')
    with _capture_source(path) as (snapshot, consumed):
        if consumed != expected:
            raise ValueError('Input content changed while opening: ' + str(path))
        frame = pd.read_csv(snapshot, **options)
    if file_hash(path) != consumed:
        raise ValueError('Input content changed while opening: ' + str(path))
    frame.attrs["_pyflash_consumed_input"] = {
        "path": str(path.resolve()), "sha256": consumed,
    }
    return frame, consumed
