"""Server preparation retains a bounded deadline and rejects early failures."""
from types import SimpleNamespace
import pytest
from scripts import ui_readiness as readiness


def test_readiness_waits_for_delayed_health_without_changing_navigation_budget(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(readiness.time, 'perf_counter', lambda:clock[0])
    monkeypatch.setattr(readiness.time, 'sleep', lambda seconds:clock.__setitem__(0, clock[0]+seconds))
    attempts = []
    class Response:
        status = 200
        def read(self): return b'ok'
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def request(url, timeout):
        attempts.append((url, timeout))
        clock[0] += 2
        if len(attempts) < 9:
            raise OSError('Server still starting')
        return Response()
    monkeypatch.setattr(readiness.urllib.request, 'urlopen', request)
    answer = readiness.wait_for_server('http://127.0.0.1:8557/')
    assert 15 < answer['seconds'] < 45
    assert len(answer['samples']) == 9 and answer['samples'][-1]['status'] == 200
    assert all(url.endswith('/_stcore/health') and limit <= 3 for url,limit in attempts)


def test_readiness_deadline_remains_bounded(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(readiness.time, 'perf_counter', lambda:clock[0])
    monkeypatch.setattr(readiness.time, 'sleep', lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    def fail(url, timeout):
        clock[0] += timeout
        raise OSError('No listening socket')
    monkeypatch.setattr(readiness.urllib.request, 'urlopen', fail)
    with pytest.raises(TimeoutError, match='No listening socket'):
        readiness.wait_for_server('http://127.0.0.1:8557', timeout=4)
    assert clock[0] == 4


def test_readiness_rejects_exited_server_before_a_request(monkeypatch):
    monkeypatch.setattr(readiness.urllib.request, 'urlopen', lambda *a, **k:pytest.fail('Requested exited server'))
    with pytest.raises(RuntimeError, match='exited before readiness'):
        readiness.wait_for_server('http://127.0.0.1:8557', process=SimpleNamespace(poll=lambda:1, returncode=1))


@pytest.mark.parametrize('value', [0, -1])
def test_readiness_rejects_invalid_deadline(value):
    with pytest.raises(ValueError, match='positive'):
        readiness.wait_for_server('http://127.0.0.1:8557', timeout=value)
