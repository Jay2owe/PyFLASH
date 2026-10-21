"""A real repair trial must not inherit the package it is meant to install."""
from pathlib import Path
import subprocess
import sys
from scripts.check_dependency_repair import dependency_view


def test_filtered_environment_retains_other_original_packages_and_hides_target(tmp_path):
    source = tmp_path / 'original-site'
    source.mkdir()
    for package in ('pointpats', 'unrelated_backend'):
        folder = source / package
        folder.mkdir()
        (folder / '__init__.py').write_text('VALUE = 17\n', encoding='utf-8')
        metadata = source / (package + '-2.5.5.dist-info')
        metadata.mkdir()
        (metadata / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {package}\nVersion: 2.5.5\n', encoding='utf-8')
    (source / 'parent.pth').write_text(str(source), encoding='utf-8')
    view = dependency_view(source, tmp_path / 'view')
    code = (
        'import sys, importlib.util; from importlib.metadata import distributions; '
        f'sys.path.insert(0, {str(view)!r}); '
        'import unrelated_backend; assert unrelated_backend.VALUE == 17; '
        "assert importlib.util.find_spec('pointpats') is None; "
        f"assert [d.metadata['Name'] for d in distributions(path=[{str(view)!r}])] == ['unrelated_backend']"
    )
    completed = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code],
        capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
    assert not (view / 'parent.pth').exists()
    assert (source / 'pointpats' / '__init__.py').read_text(encoding='utf-8') == 'VALUE = 17\n'
    assert (view / 'unrelated_backend').resolve() == (source / 'unrelated_backend').resolve()
