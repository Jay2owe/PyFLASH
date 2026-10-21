"""Run owned checks using native Windows information instead of stalled probes.

This is a verification launcher, not a PyFLASH import hook. Python's existing
sys.getwindowsversion/environment fallback supplies the same machine's metadata.
Scientific inputs, random generators, dependencies and calculations are unchanged.
"""
from pathlib import Path
import platform
import runpy
import sys


def native_windows_information():
    if sys.platform != 'win32':
        return
    if hasattr(platform, '_wmi_query'):
        def unavailable_wmi(*args, **kwargs):
            raise OSError('Use native Windows information in this owned check')
        platform._wmi_query = unavailable_wmi
    if hasattr(platform, '_syscmd_ver'):
        def native_version_defaults(system='', release='', version='', **kwargs):
            return system, release, version
        platform._syscmd_ver = native_version_defaults


def main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if not arguments:
        raise ValueError('A verification module, expression or script is required')
    native_windows_information()
    # A check may import an authenticated historical reference source. Python
    # must not rewrite the archived bytecode while exercising that source.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if arguments[0] == '-m':
        if len(arguments) < 2:
            raise ValueError('Module name is required after -m')
        sys.argv = arguments[1:]
        runpy.run_module(arguments[1], run_name='__main__', alter_sys=True)
    elif arguments[0] == '-c':
        if len(arguments) < 2:
            raise ValueError('Expression is required after -c')
        sys.argv = ['-c', *arguments[2:]]
        exec(compile(arguments[1], '<owned-verification-expression>', 'exec'),
             {'__name__': '__main__'})
    else:
        sys.argv = arguments
        sys.path.insert(0, str(Path(arguments[0]).resolve().parent))
        runpy.run_path(arguments[0], run_name='__main__')


if __name__ == '__main__':
    main()
