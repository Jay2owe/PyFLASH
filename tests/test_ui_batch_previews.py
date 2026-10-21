"""Hundreds of results remain accessible with bounded preview rendering."""
from PyFLASH.ui.figures import preview_page


def test_every_item_in_a_large_result_is_reachable_without_duplicates():
    paths = [f'figure-{index}.svg' for index in range(501)]
    pages = preview_page(paths)[2]
    visited = []
    for page in range(pages):
        subset, actual, count = preview_page(paths, page)
        assert actual == page and count == pages and len(subset) <= 12
        visited.extend(subset)
    assert visited == paths
    assert preview_page(paths, 999)[0] == paths[-9:]


def test_real_native_preview_uses_the_same_renderer_for_single_and_batch(tmp_path):
    from streamlit.testing.v1 import AppTest
    # These are interface fixture images, without scientific data or inference.
    from PIL import Image
    path = tmp_path/'fixture.png'
    Image.new('RGB',(12,12),'white').save(path)
    paths = []
    payload = path.read_bytes()
    for index in range(501):
        item = tmp_path/f'fixture-{index}.png'
        item.write_bytes(payload)
        paths.append(str(item))
    app = AppTest.from_string('from PyFLASH.ui.figures import embed_figure\n'
        f'embed_figure(None, None, paths={paths!r})', default_timeout=20).run()
    assert not app.exception
    # Only the requested page is loaded, despite retaining every result path.
    assert len(app.get('imgs')) == 12
    page = next(box for box in app.selectbox if box.label == 'Result page')
    assert page.options[-1] == '42 of 42'
    page.set_value(41).run()
    assert not app.exception
    assert len(app.get('imgs')) == 9
