"""A build must retain native runtime programs and opaque reference inputs."""
import io
import tarfile
import pytest
from scripts.check_reproducibility_distribution import REQUIRED,check,main

def make_source(root):
    files={name:('literal source '+name).encode() for name in REQUIRED}
    files['reproducibility/fixtures/image-inputs/reference.tif']=b'II\x2a\x00literal opaque reference'
    files['reproducibility/reference-sources/native/frozen-before.json']=b'{"original_failure":true}'
    files['tests/test_literal.py']=b'assert 1 == 1\n'
    files['reproducibility/reference-sources/native/output/original.json']=b'{"original":true}'
    files['reproducibility/reference-sources/native/results/original.json']=b'{"failed":true}'
    for name,content in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
    return files

def make_archive(path,files):
    with tarfile.open(path,'w:gz') as archive:
        for name,content in files.items():
            member=tarfile.TarInfo('example-1.0/'+name);member.size=len(content)
            archive.addfile(member,io.BytesIO(content))

def test_actual_tar_members_retain_every_original_resource(tmp_path):
    files=make_source(tmp_path/'source');path=tmp_path/'source.tar.gz';make_archive(path,files)
    result=check(path,tmp_path/'source')
    assert result['passed'] and result['verified_files']==len(files)

@pytest.mark.parametrize('name',['reproducibility/run_native_r.mjs','scripts/verify.py','reproducibility/fixtures/image-inputs/reference.tif'])
def test_missing_runtime_or_binary_evidence_cannot_pass(tmp_path,name):
    files=make_source(tmp_path/'source');del files[name]
    path=tmp_path/'source.tar.gz';make_archive(path,files)
    result=check(path,tmp_path/'source')
    assert not result['passed'] and result['missing']==[name]

def test_changed_retained_failure_is_reported_separately(tmp_path):
    files=make_source(tmp_path/'source');name='reproducibility/reference-sources/native/frozen-before.json'
    files[name]=b'{"original_failure":false}'
    path=tmp_path/'source.tar.gz';make_archive(path,files)
    result=check(path,tmp_path/'source')
    assert not result['passed'] and result['different']==[name] and result['missing']==[]

def test_duplicate_evidence_member_cannot_hide_changed_bytes(tmp_path):
    files=make_source(tmp_path/'source');name='reproducibility/run_native_r.mjs'
    path=tmp_path/'source.tar.gz'
    with tarfile.open(path,'w:gz') as archive:
        for label,content in list(files.items())+[(name,files[name])]:
            member=tarfile.TarInfo('example-1.0/'+label);member.size=len(content)
            archive.addfile(member,io.BytesIO(content))
    result=check(path,tmp_path/'source')
    assert not result['passed'] and result['duplicates']==[name]

@pytest.mark.parametrize('name', ['tests/__pycache__/test_literal.cpython-312.pyc',
                                  'tests/__pycache__/test_literal.cpython-313-pytest-9.0.2.pyc.15400',
                                  'PyFLASH/compiled.pyd', 'scripts/stale.pyo'])
def test_source_distribution_rejects_python_cache_artifacts(tmp_path,name):
    files=make_source(tmp_path/'source')
    files[name]=b'compiled cache must not ship'
    path=tmp_path/'source.tar.gz';make_archive(path,files)
    result=check(path,tmp_path/'source')
    assert not result['passed']
    assert result['forbidden_cache_files']==[name]

def test_nested_native_output_is_required_but_generated_root_is_ignored(tmp_path):
    root=tmp_path/'source';files=make_source(root)
    generated=root/'reproducibility/results/current.json'
    generated.parent.mkdir();generated.write_bytes(b'generated current output')
    name='reproducibility/reference-sources/native/output/original.json'
    del files[name]
    path=tmp_path/'source.tar.gz';make_archive(path,files)
    result=check(path,root)
    assert not result['passed'] and result['missing']==[name]

def test_distribution_directory_selects_one_actual_archive(tmp_path,capsys):
    root=tmp_path/'source';files=make_source(root)
    dist=tmp_path/'dist';dist.mkdir();make_archive(dist/'example.tar.gz',files)
    assert main(['--dist-dir',str(dist),'--source-root',str(root)])==0
    assert '"passed": true' in capsys.readouterr().out

@pytest.mark.parametrize('count',[0,2])
def test_ambiguous_distribution_directory_cannot_pass(tmp_path,count):
    dist=tmp_path/'dist';dist.mkdir()
    for i in range(count):(dist/f'archive-{i}.tar.gz').write_bytes(b'not selected')
    with pytest.raises(SystemExit) as error:main(['--dist-dir',str(dist)])
    assert error.value.code==2
