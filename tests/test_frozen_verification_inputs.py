"""A frozen checkout retains authentic inputs and documentation under any name."""
from pathlib import Path
import pytest
from scripts.freeze_verification_source import selected_sources


def test_declared_archive_cache_and_documentation_assets_are_not_omitted(tmp_path):
    names = ['reproducibility/reference-sources/original/__pycache__/producer.pyc',
             'docs/wiki/gallery/images/chart.svg', 'docs/wiki/.pages',
             '.readthedocs.yaml', 'docs/requirements.txt', 'tests/check.py',
             'PyFLASH/__pycache__/live.pyc', 'demo/output/trial.svg']
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'original bytes')
    selected = selected_sources(tmp_path, [tmp_path / names[0]], ['.readthedocs.yaml'])
    assert {p.relative_to(tmp_path).as_posix() for p in selected} == set(names[:6])


def test_source_snapshot_refuses_an_external_declared_input(tmp_path):
    root = tmp_path / 'arbitrarily-named-checkout'
    root.mkdir()
    external = tmp_path / 'external.py'
    external.write_text('outside source', encoding='utf-8')
    with pytest.raises(ValueError, match='escapes'):
        selected_sources(root, [external], [])
