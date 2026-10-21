"""Bounded server preparation, separate from navigation-to-plot measurements."""
import time
import urllib.request


def wait_for_server(url, *, timeout=45, process=None):
    if timeout <= 0:
        raise ValueError('Server readiness timeout must be positive.')
    started = time.perf_counter()
    deadline = started + timeout
    samples = []
    while True:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f'The diagnostic server exited before readiness: {process.returncode}')
        remaining = deadline-time.perf_counter()
        if remaining <= 0:
            error = samples[-1].get('error', 'no successful health response') if samples else 'no health attempt'
            raise TimeoutError(f'Server health did not become ready within {timeout:g} seconds: {error}')
        began = time.perf_counter()
        try:
            with urllib.request.urlopen(url.rstrip('/')+'/_stcore/health', timeout=min(3, remaining)) as response:
                if response.status != 200 or response.read().strip() != b'ok':
                    raise OSError('Unexpected server health response.')
            samples.append({'seconds':time.perf_counter()-began, 'status':200})
            return {'seconds':time.perf_counter()-started, 'samples':samples,
                    'boundary':'owned server launch preparation; excluded from navigation timing'}
        except OSError as exc:
            samples.append({'seconds':time.perf_counter()-began, 'error':f'{type(exc).__name__}: {exc}'})
            time.sleep(min(.1, max(0, deadline-time.perf_counter())))
