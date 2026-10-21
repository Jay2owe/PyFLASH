"""Missing carriers reuse matching cached science, never mix two results."""
import os
import pytest
from reprofig import extract_record
from PyFLASH import provenance, report
from PyFLASH.config import Config
from test_reprofig_integration import _experiment, plot_module


@pytest.fixture
def format_settings(monkeypatch):
    for name, value in {'SAVE_MODE': True, 'SKIP_EXISTING': False,
            'FIGURE_FORMATS': ('svg',), 'FIGURE_COMPANION_CSV': False,
            'FIGURE_PROOF': False, 'FIGURE_PROOF_POLICY': {},
            'FIGURE_WIDTH': None, 'FIGURE_HEIGHT': None}.items():
        monkeypatch.setattr(Config, name, value)
    report.collect(); report.start()
    yield
    report.collect()


@pytest.mark.parametrize('profile', ('master', 'public', 'minimal_public'))
@pytest.mark.parametrize('proof', (False, True))
@pytest.mark.parametrize('formats', (('svg', 'png'), ('png', 'svg')))
def test_completion_preserves_cached_identity_science_and_bytes(tmp_path, plot_module, format_settings, profile, proof, formats):
    experiment, _, _ = _experiment(tmp_path)
    Config.FIGURE_PROOF = proof
    kwargs = {'figure_profile': profile}
    if profile != 'master': kwargs['safe_columns'] = ['group', 'metric', 'value']
    plot_module.plot_group(experiment, str(tmp_path), 'master', **kwargs)
    svg = tmp_path / 'master.svg'; original = svg.read_bytes(); old = extract_record(svg)
    Config.FIGURE_FORMATS = formats; Config.SKIP_EXISTING = True
    report.collect(); report.start()
    plot_module.plot_group(experiment, str(tmp_path), 'master', **kwargs)
    new = extract_record(tmp_path / 'master.png')
    assert svg.read_bytes() == original
    assert new.figure_id == old.figure_id
    assert new.distribution_profile == profile
    assert [t.to_dict() for t in new.data_tables] == [t.to_dict() for t in old.data_tables]
    assert new.statistics == old.statistics
    if proof: assert new.extensions['proof']['root_sha256'] == old.extensions['proof']['root_sha256']


@pytest.mark.parametrize('change', ('data', 'source', 'profile', 'proof', 'corrupt'))
def test_stale_or_incompatible_cache_refuses_before_writing(tmp_path, plot_module, format_settings, monkeypatch, change):
    experiment, _, csv = _experiment(tmp_path)
    plot_module.plot_group(experiment, str(tmp_path), 'master')
    svg = tmp_path / 'master.svg'
    if change == 'data': experiment.summary.loc[:, 'value'] += 100
    elif change == 'source': csv.write_bytes(csv.read_bytes() + b'\n')
    elif change == 'proof': Config.FIGURE_PROOF = True
    elif change == 'corrupt': svg.write_bytes(b'preserved invalid old carrier')
    original = svg.read_bytes()
    key = os.path.normcase(str(svg)); previous = {'owner': 'previous pending write'}
    monkeypatch.setitem(provenance._PENDING, key, previous)
    Config.FIGURE_FORMATS = ('svg', 'png'); Config.SKIP_EXISTING = True
    report.collect(); report.start()
    kwargs = {'figure_profile': 'public', 'safe_columns': ['group', 'metric', 'value']} if change == 'profile' else {}
    with pytest.raises(Exception): plot_module.plot_group(experiment, str(tmp_path), 'master', **kwargs)
    assert not (tmp_path / 'master.png').exists()
    assert svg.read_bytes() == original
    assert provenance._PENDING[key] is previous


def test_disagreeing_cached_identities_refuse_missing_third_format(tmp_path, plot_module, format_settings):
    from reprofig import embed_file
    experiment, _, _ = _experiment(tmp_path)
    Config.FIGURE_FORMATS = ('svg', 'png')
    plot_module.plot_group(experiment, str(tmp_path), 'master')
    png = tmp_path / 'master.png'; record = extract_record(png)
    record.figure_id = 'different-cached-identity'; embed_file(png, record, output_path=png)
    original = png.read_bytes()
    Config.FIGURE_FORMATS = ('svg', 'png', 'pdf'); Config.SKIP_EXISTING = True
    report.collect(); report.start()
    with pytest.raises(ValueError, match='disagree'): plot_module.plot_group(experiment, str(tmp_path), 'master')
    assert png.read_bytes() == original and not (tmp_path / 'master.pdf').exists()


@pytest.mark.parametrize('proof', (False, True))
def test_minimal_completion_uses_full_record_with_published_profile_api(tmp_path, plot_module, format_settings, monkeypatch, proof):
    import reprofig.artifacts
    experiment, _, _ = _experiment(tmp_path); Config.FIGURE_PROOF = proof
    kwargs = {'figure_profile': 'minimal_public', 'safe_columns': ['group', 'metric', 'value']}
    plot_module.plot_group(experiment, str(tmp_path), 'master', **kwargs)
    old = extract_record(tmp_path / 'master.svg')
    previous = reprofig.artifacts.derive_profile
    def older_derivation(record, *args, **options):
        if record.distribution_profile == 'minimal_public': raise ValueError('no embedded contents')
        return previous(record, *args, **options)
    monkeypatch.setattr(reprofig.artifacts, 'derive_profile', older_derivation)
    Config.FIGURE_FORMATS = ('svg', 'png'); Config.SKIP_EXISTING = True
    report.collect(); report.start(); plot_module.plot_group(experiment, str(tmp_path), 'master', **kwargs)
    assert extract_record(tmp_path / 'master.png').figure_id == old.figure_id


@pytest.mark.parametrize('profile', ('public', 'minimal_public'))
def test_completion_keeps_public_companion_tables(tmp_path, plot_module, format_settings, profile):
    experiment, _, _ = _experiment(tmp_path)
    kwargs = {'figure_profile': profile, 'safe_columns': ['group', 'metric', 'value']}
    plot_module.plot_group(experiment, str(tmp_path), 'master', **kwargs)
    Config.FIGURE_FORMATS = ('svg', 'png'); Config.SKIP_EXISTING = True
    report.collect(); report.start()
    plot_module.plot_group(experiment, str(tmp_path), 'master', write_companion_csv=True, **kwargs)
    assert (tmp_path / 'master-plotted-data.csv').is_file()
    assert 'observation_id' not in (tmp_path / 'master-plotted-data.csv').read_text(encoding='utf-8')


def test_changed_proof_geometry_refuses_cached_evidence(tmp_path, plot_module, format_settings, monkeypatch):
    from PyFLASH import utils
    experiment, _, _ = _experiment(tmp_path); Config.FIGURE_PROOF = True
    plot_module.plot_group(experiment, str(tmp_path), 'master')
    delegate = utils.save_fig
    def changed(*args, **kwargs):
        args[0].axes[0].set_ylim(-100, 100)
        return delegate(*args, **kwargs)
    monkeypatch.setattr(utils, 'save_fig', changed)
    Config.FIGURE_FORMATS = ('svg', 'png'); Config.SKIP_EXISTING = True
    report.collect(); report.start()
    with pytest.raises(ValueError, match='evidence differs'): plot_module.plot_group(experiment, str(tmp_path), 'master')
    assert not (tmp_path / 'master.png').exists()
