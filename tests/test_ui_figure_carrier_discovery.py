"""The UI keeps every supported writer carrier and downloads original bytes."""
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from PyFLASH.ui import figures
from PyFLASH.utils import _DIRECT_FIGURE_EXTENSIONS


def test_every_direct_writer_carrier_is_discovered_and_unknown_files_are_excluded(tmp_path):
    expected = []
    for extension in _DIRECT_FIGURE_EXTENSIONS:
        path = tmp_path / ('original.' + extension.upper())
        path.write_bytes(('original-' + extension).encode())
        expected.append(str(path))
    (tmp_path / 'not-a-figure.json').write_bytes(b'original metadata')
    assert set(figures.locate_saved_figures(tmp_path)) == set(expected)


def test_explicit_carrier_selection_preserves_existing_filter(tmp_path):
    for name in ('original.svg', 'original.png', 'original.pdf'):
        (tmp_path / name).write_bytes(b'original')
    assert set(figures.locate_saved_figures(tmp_path, exts=('.svg', '.png'))) == {
        str(tmp_path / 'original.svg'), str(tmp_path / 'original.png')}


@pytest.mark.parametrize('extension', sorted(_DIRECT_FIGURE_EXTENSIONS))
def test_original_carrier_bytes_are_available_through_the_same_download_control(tmp_path, monkeypatch, extension):
    path = tmp_path / ('original.' + extension)
    data = ('unchanged-' + extension).encode()
    path.write_bytes(data)
    shown, downloads = [], []
    fake = SimpleNamespace(image=lambda *args, **kwargs: shown.append(args[0]))
    monkeypatch.setitem(sys.modules, 'streamlit', fake)
    from PyFLASH.ui import controls
    def download(target, kind, label, **kwargs):
        assert kind == 'download_button'
        downloads.append(kwargs)
    monkeypatch.setattr(controls, 'widget', download)
    assert figures.embed_figure(None, tmp_path, paths=[str(path)]) == [str(path)]
    assert len(downloads) == 1
    assert downloads[0]['file_name'] == path.name and downloads[0]['data'] == data
    assert path.read_bytes() == data
    if extension in {'svg','png','jpg','jpeg','jpe','webp','avif','tif','tiff'}:
        assert shown == [str(path)]
