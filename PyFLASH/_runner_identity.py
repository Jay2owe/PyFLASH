"""Identify package, runner and editable worker sources before heavy imports."""
from pathlib import Path
import hashlib,json
from importlib.util import find_spec
from importlib.metadata import version

class StaleRuntimeError(RuntimeError):
    pass

def runner_identity(runner_path):
    from PyFLASH._persistence import code_identity
    from PyFLASH._cache_identity import file_hash
    from PyFLASH.dependencies import check
    spec=find_spec('analysis_kit')
    if spec is None or not spec.origin:
        raise ImportError('The PyFLASH agent runner requires analysis-kit.')
    kit_root=Path(spec.origin).parent
    import PyFLASH
    current_sources=code_identity()
    if PyFLASH._LOADED_SOURCE_IDENTITY != current_sources:
        raise StaleRuntimeError('Package source changed after import; restart the runner.')
    identity={'schema_version':1,'pyflash':current_sources,
        'runner':file_hash(runner_path),'analysis_kit':{
            path.relative_to(kit_root).as_posix():file_hash(path)
            for path in sorted(kit_root.rglob('*.py'))},
        'versions':{'PyFLASH-analysis':version('PyFLASH-analysis'),'analysis-kit':version('analysis-kit')},
        'dependencies':{entry['package']:entry['version'] for entry in check()}}
    encoded=json.dumps(identity,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

def guarded_execute(execute, current_identity, loaded_identity):
    def run(request,cache=None):
        def stale():
            return {'ok':False,'error_type':'stale_worker',
                'error':'Installed source or dependencies changed; retry with the current runner.'}
        def current():
            try:return current_identity()==loaded_identity
            except StaleRuntimeError:return False
        if not current():return stale()
        try:
            result=execute(request,cache)
        except Exception:
            if not current():return stale()
            raise
        if not current():return stale()
        return result
    return run
