"""Legend-only figures must carry evidence that detects changed swatches/text."""
import xml.etree.ElementTree as ET


def test_legend_proof_detects_native_svg_tampering(tmp_path):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from PyFLASH.utils import save_fig
    from reprofig import read_svg
    from reprofig.render.svg_verify import verify_svg
    fig, ax = plt.subplots()
    ax.set_axis_off()
    ax.legend(handles=[Patch(facecolor='#345678', label='Control'),
                       Patch(facecolor='none', edgecolor='#b04a3c', label='Treatment')])
    try:
        path = save_fig(fig, str(tmp_path), 'legend', figure_formats=('svg',),
                        proof=True, rasterize=False, verbose=False)
    finally:
        plt.close(fig)
    record = read_svg(path)
    checks = verify_svg(path, record)
    assert checks and all(check.status == 'pass' for check in checks)
    assert len(record.extensions['render_manifest']['marks']) == 2
    tree = ET.parse(path)
    target = next(node for node in tree.iter() if node.attrib.get('id', '').endswith('swatch-0'))
    target.set('transform', 'translate(20 0)')
    tree.write(path, encoding='utf-8', xml_declaration=True)
    assert any(check.status == 'fail' for check in verify_svg(path, record))


def test_legend_capture_preserves_shared_artist_identity():
    import matplotlib.pyplot as plt
    from PyFLASH._figure_proof import capture_figure
    fig, ax = plt.subplots()
    line, = ax.plot([0, 1], [1, 2], label='Signal')
    ax.legend(title='Groups')
    try:
        first = capture_figure(fig).to_dict()
        second = capture_figure(fig).to_dict()
        assert first == second
        assert line.get_gid() == 'axes-0-line-0'
        assert [row['text'] for row in first['annotations']] == ['Signal', 'Groups']
    finally:
        plt.close(fig)
