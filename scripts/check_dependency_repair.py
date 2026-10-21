"""Verify a real repair button in an isolated interpreter environment."""
import argparse
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import shutil
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright
from PyFLASH.dependencies import check
from PyFLASH._persistence import code_identity
from reproducibility.run import ROOT, sha256


def dependency_view(source, target, *, excluded='pointpats'):
    """Expose unchanged installed dependencies, excluding the repair subject.

    Directory links retain the original installed package ownership. Files in
    the view belong to the trial; .pth files cannot reintroduce the parent site.
    The interpreter's own site precedes this view after the actual repair.
    """
    source, target = Path(source).resolve(), Path(target).resolve()
    target.mkdir(parents=True, exist_ok=False)
    for entry in source.iterdir():
        name = entry.name.lower().replace('_', '-')
        if (name == excluded or name.startswith(excluded + '-')
                or entry.suffix.lower() == '.pth' or entry.name == '__pycache__'):
            continue
        destination = target / entry.name
        if entry.is_dir():
            if os.name == 'nt':
                import _winapi
                _winapi.CreateJunction(str(entry), str(destination))
            else:
                destination.symlink_to(entry, target_is_directory=True)
        elif entry.is_file():
            shutil.copyfile(entry, destination)
    return target


def isolated_trial(output,port=8548):
    """Create an owned interpreter; repair never installs into the user's Python."""
    output = output.resolve()
    parent = next(path for path in (output,*output.parents) if path.exists())
    if shutil.disk_usage(parent).free < 512*1024**2:
        raise RuntimeError('The isolated dependency trial needs 512 MB free space.')
    uv = shutil.which('uv')
    if not uv:
        raise RuntimeError('uv is required to create the isolated repair environment.')
    output.mkdir(parents=True,exist_ok=False)
    environment = output/'venv'
    command = [uv,'venv','--seed','--python',sys.executable,
               '--no-python-downloads',str(environment)]
    result = subprocess.run(command,capture_output=True,text=True,timeout=180)
    (output/'environment.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Could not create the owned repair interpreter; see environment.log.')
    executable = environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    assert executable.resolve().is_relative_to(output), 'The trial interpreter must belong to its output directory.'
    located = subprocess.run([str(executable),'-c','import json,site; print(json.dumps(site.getsitepackages()))'],
                             capture_output=True,text=True,check=True,timeout=20)
    packages = next(Path(path) for path in json.loads(located.stdout)
                    if Path(path).name in {'site-packages','dist-packages'} and Path(path).is_relative_to(environment))
    # The subject must actually be unavailable, including when it is installed
    # in the parent. Borrow the other original dependencies through a filtered
    # view rather than inheriting the parent's complete site-packages directory.
    original_sites = list(dict.fromkeys(Path(path).resolve() for path in sys.path
        if path and Path(path).is_dir() and Path(path).name in {'site-packages','dist-packages'}))
    views = [dependency_view(source, output/'borrowed-dependencies'/str(index)/'site-packages')
             for index, source in enumerate(original_sites)]
    paths = [str(ROOT), *(str(path) for path in views)]
    (packages/'pyflash-trial-paths.pth').write_text('\n'.join(paths)+'\n',encoding='utf-8')
    metadata = {'schema_version':1,'command':command,'executable':str(executable),
                'borrowed_dependency_paths':paths,'original_dependency_paths':list(map(str,original_sites)),
                'excluded_package':'pointpats','output':str(output)}
    (output/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    return run(executable,output/'browser',port)


def run(executable, output, port=8548):
    output.mkdir(parents=True,exist_ok=False)
    constraints = output/'constraints.txt'
    constraints.write_text('\n'.join(row['package']+'=='+row['version'] for row in check('core'))+'\n')
    app = output/'repair_app.py'
    app.write_text("import streamlit as st\nfrom PyFLASH.ui import dependency_controls, job_status\n"
        "st.set_page_config(layout='wide')\nst.title('Dependency repair check')\n"
        "st.session_state.setdefault('_ui_dataset_token','repair-fixture')\n"
        "job_status.consume_completed()\njob_status.show_status()\n"
        "if dependency_controls.render('spatial'):\n    st.success('Feature dependencies available')\n",
        encoding='utf-8')
    env = dict(os.environ,LOCALAPPDATA=str(output/'workspace'),PIP_CONSTRAINT=str(constraints.resolve()),
               PYTHONDONTWRITEBYTECODE='1')
    before = subprocess.run([str(executable),'-c',
        "import json; from PyFLASH.dependencies import check; print(json.dumps(check('spatial')))"],
        capture_output=True,text=True,check=True)
    initial = json.loads(before.stdout)
    assert len(initial) == 1 and not initial[0]['compatible'], initial
    unavailable = subprocess.run([str(executable),'-c',
        "import importlib.util; assert importlib.util.find_spec('pointpats') is None"],
        capture_output=True,text=True,env=env,timeout=20)
    assert unavailable.returncode == 0, unavailable.stderr
    sources = code_identity()
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1',port)) != 0, 'Check port is occupied.'
    report = {'before':initial,'code_sha256':sources, 'isolated_executable':str(executable),
              'constraint_sha256':sha256(constraints), 'errors':[]}
    with (output/'server.log').open('w',encoding='utf-8') as log:
        server = subprocess.Popen([str(executable),'-m','streamlit','run',str(app),
            '--global.developmentMode=false',
            f'--server.port={port}','--server.address=127.0.0.1','--server.headless=true',
            '--server.fileWatcherType=none','--runner.postScriptGC=false','--browser.gatherUsageStats=false'],
            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            url = f'http://127.0.0.1:{port}'
            for attempt in range(120):
                if server.poll() is not None:
                    raise RuntimeError('Repair server exited; inspect server.log.')
                try:
                    urllib.request.urlopen(url+'/_stcore/health',timeout=1).close()
                    break
                except OSError:
                    time.sleep(.25)
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge')
                page = browser.new_page(viewport={'width':1440,'height':900})
                page.goto(url)
                install = page.get_by_role('button',name=re.compile('Install pointpats'))
                install.wait_for(timeout=30000)
                page.screenshot(path=str(output/'missing.png'))
                install.click()
                page.get_by_text('Feature dependencies available',exact=True).wait_for(timeout=300000)
                assert not install.count()
                assert not page.locator('[data-testid="stException"]').count()
                page.screenshot(path=str(output/'repaired.png'))
                browser.close()
            after = subprocess.run([str(executable),'-c',
                "import json,pointpats; from PyFLASH.dependencies import check; print(json.dumps(check('spatial')))"],
                capture_output=True,text=True,encoding='utf-8',env=env,check=True)
            report['after'] = json.loads(after.stdout)
            assert report['after'][0]['compatible']
            report['actual_import_passed'] = True
            results = list((output/'workspace/PyFLASH/ui-jobs').glob('*/run.json'))
            if not results:
                results = list((output/'workspace/PyFLASH').rglob('run.json'))
            assert len(results) == 1, results
            record = json.loads(results[0].read_text())
            assert record['type'] == 'PyFLASH.dependencies.repair'
            report['receipt'] = str(results[0])
            assert all(sha256(row['path']) == row['sha256'] for row in record['outputs'])
        except BaseException as exc:
            report['errors'].append(f'{type(exc).__name__}: {exc}')
            if 'page' in locals() and not page.is_closed():
                page.screenshot(path=str(output/'failure.png'),full_page=True)
                (output/'failure-body.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
            raise
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            report['source_changes'] = [name for name,digest in sources.items() if code_identity().get(name) != digest]
            report['server_closed'] = server.poll() is not None
            (output/'repair-check.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    assert not report['source_changes']
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--python',type=Path)
    modes.add_argument('--isolated',action='store_true',help='Create and retain an owned trial interpreter.')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8548)
    args = parser.parse_args()
    report = (isolated_trial(args.output,args.port) if args.isolated else
              run(args.python.resolve(),args.output.resolve(),args.port))
    print(json.dumps(report['after']),flush=True)
