"""Full admission must preserve scratch after copying source and native outputs."""
from pathlib import Path
import pytest
from reproducibility.run import (
    FINALIZATION_RESERVE_NAME,
    differences_with_failure_fallback,
    create_finalization_reserve,
    output_manifest,
    run_space_requirement,
)

@pytest.mark.parametrize('full,browser,reference,scratch', [
    (False,False,2*1024**3,0), (True,False,2*1024**3,8*1024**3),
    (False,True,2*1024**3,0), (True,True,2*1024**3,8*1024**3)])
def test_exact_snapshot_cost_is_additional_to_later_reserves(tmp_path, full, browser, reference, scratch):
    paths = [tmp_path/'a',tmp_path/'b']
    paths[0].write_bytes(b'original-source')
    paths[1].write_bytes(b'native-reference')
    expected = sum(p.stat().st_size for p in paths)
    result = run_space_requirement(paths, full=full, browser_only=browser)
    assert result == dict(source_snapshot_bytes=expected,reference_output_reserve_bytes=reference,
                          test_scratch_reserve_bytes=scratch,finalization_reserve_bytes=8*1024**2,
                          total_bytes=expected+reference+scratch+8*1024**2)
    assert paths[0].read_bytes() == b'original-source'
    assert paths[1].read_bytes() == b'native-reference'

def test_empty_snapshot_still_reserves_native_outputs_and_full_scratch():
    result = run_space_requirement([],full=True)
    assert result['total_bytes'] == 10*1024**3 + 8*1024**2


def test_finalization_reserve_is_owned_and_excluded_from_output_manifest(tmp_path):
    reserve = create_finalization_reserve(tmp_path, size_bytes=4096)
    assert reserve.name == FINALIZATION_RESERVE_NAME
    assert reserve.stat().st_size == 4096
    assert all(row['path'] != FINALIZATION_RESERVE_NAME for row in output_manifest(tmp_path)[0])
    reserve.unlink()


def test_final_report_failure_releases_reserved_space_and_writes_terminal_summary(tmp_path, monkeypatch):
    from reproducibility import run
    create_finalization_reserve(tmp_path, size_bytes=4096)
    def fail_on_disk(*args, **kwargs):
        raise OSError(28, 'No space left on device')
    monkeypatch.setattr(run, 'differences', fail_on_disk)

    rows=[{'contract':'demo.test.a','reference':'Native R stats','status':'agree'}]
    capabilities=[{'capability':'demo.test','status':'partially-validated-contract',
                   'executed_subcontracts':'demo.test.a'}]
    error, report_failed = differences_with_failure_fallback(
        tmp_path, rows, capabilities, [], None)

    assert report_failed is True
    assert 'No space left on device' in error
    assert not (tmp_path / FINALIZATION_RESERVE_NAME).exists()
    report = (tmp_path / 'DIFFERENCES.md').read_text(encoding='utf-8')
    assert 'run is incomplete' in report
    assert 'must not be treated as a passing certification' in report
    assert 'outcome-grid-finalization-fallback.csv' in report
    grid=(tmp_path/'outcome-grid-finalization-fallback.csv').read_text(encoding='utf-8')
    assert 'demo.test,Native R stats,agree,1,demo.test.a' in grid
    assert 'demo.test,required-but-unexecuted,pending,0,demo.test.a' in grid

def test_missing_snapshot_source_refuses_instead_of_underestimating(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_space_requirement([tmp_path/'missing'],full=True)


@pytest.mark.parametrize('mode,available', [(['--full'],11*1024**3), (['--browser-only'],3*1024**3), ([],3*1024**3)])
def test_production_command_refuses_before_source_copy_or_native_execution(tmp_path, monkeypatch, mode, available):
    import sys
    from types import SimpleNamespace
    from reproducibility import run
    class Source:
        def stat(self):
            return SimpleNamespace(st_size=2*1024**3)
    monkeypatch.setattr(run,'verification_sources',lambda:[Source()])
    monkeypatch.setattr(run.shutil,'disk_usage',lambda _:SimpleNamespace(free=available))
    def forbidden(*args, **kwargs):
        pytest.fail('An insufficient-space command reached source copying or scientific execution.')
    monkeypatch.setattr(run.shutil,'copyfile',forbidden)
    monkeypatch.setattr(run.subprocess,'run',forbidden)
    monkeypatch.setattr(run,'execute_requested_checks',forbidden)
    monkeypatch.setattr(sys,'argv',['reproducibility.run','--output',str(tmp_path/'job')]+mode)
    with pytest.raises(RuntimeError,match='Needs estimated'):
        run.main()
