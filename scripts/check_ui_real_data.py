"""Own the browser/server and verify primary interactions on a real saved analysis.

This is a read-only performance diagnostic, not a scientific analysis or plot
producer. It preserves the user's app, preferences and saved source unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from playwright.sync_api import sync_playwright
from reproducibility.run import ROOT, python_command, sha256
from PyFLASH._persistence import write_json
from PyFLASH.ui import workspace


def check(source, output, *, port=8547, cdp_port=9451, reloads=3):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    existing = next(p for p in (output,*output.parents) if p.exists())
    peak = max(2*1024**3,source.stat().st_size*5)
    if shutil.disk_usage(existing).free < peak:
        raise RuntimeError(f'Real-data trial needs {peak} bytes of free local space.')
    for used in (port,cdp_port):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',used)) == 0:
                raise RuntimeError(f'Diagnostic port {used} is occupied.')
    output.mkdir(parents=True,exist_ok=False)
    sources = {p.relative_to(ROOT).as_posix():sha256(p) for p in (ROOT/'PyFLASH').rglob('*.py')}
    report = {'source':str(source),'source_sha256':sha256(source),
              'code_sha256':sources,'estimated_peak_bytes':peak,'errors':[]}
    tools = output/'tool-sources'
    tools.mkdir()
    for producer in (Path(__file__),ROOT/'scripts/check_ui_responsiveness.py'):
        shutil.copyfile(producer,tools/producer.name)
    report['producer_sha256'] = {p.name:sha256(p) for p in tools.iterdir()}
    recovery = output/'workspace'
    identity = workspace.recovery_path().parent.name
    write_json(recovery/'PyFLASH'/identity/'workspace.json',{
        'schema_version':workspace.SCHEMA_VERSION,'layout_version':3,
        'source':{'kind':'pickle','path':str(source)},'preferences':{}})
    env = dict(os.environ,LOCALAPPDATA=str(recovery),
               PYFLASH_UI_PERFORMANCE_TRACE=str(output/'server-timings.jsonl'))
    with (output/'server.log').open('w',encoding='utf-8') as log:
        server_command = python_command()+['-m','streamlit','run','PyFLASH/ui/app.py',
            '--runner.postScriptGC=false','--server.fileWatcherType=none','--server.address=127.0.0.1',
            f'--server.port={port}','--server.headless=true','--browser.gatherUsageStats=false']
        server = subprocess.Popen(server_command,
            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            from scripts.ui_readiness import wait_for_server
            report['server_readiness'] = wait_for_server(f'http://127.0.0.1:{port}/', process=server)
            write_json(output/'readiness.json', report['server_readiness'])
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge',headless=True,
                    args=[f'--remote-debugging-port={cdp_port}','--remote-allow-origins=*'])
                try:
                    page = browser.new_page(viewport={'width':1440,'height':900})
                    import urllib.request
                    targets = json.load(urllib.request.urlopen(f'http://127.0.0.1:{cdp_port}/json/list'))
                    target = next(t['id'] for t in targets if t['type']=='page')
                    started = time.perf_counter()
                    with (output/'responsiveness.log').open('w',encoding='utf-8') as worker_log:
                        result = subprocess.run(python_command()+['-m','scripts.check_ui_responsiveness',
                            '--source',str(source),'--cdp',f'http://127.0.0.1:{cdp_port}',
                            '--tab-id',target,'--url',f'http://127.0.0.1:{port}/',
                            '--reloads',str(reloads),'--output',str(output/'browser.json')],
                            cwd=ROOT,env=env,stdout=worker_log,stderr=subprocess.STDOUT,timeout=150)
                    report['elapsed_seconds'] = time.perf_counter()-started
                    page.screenshot(path=str(output/'real-data-interface.png'),full_page=True)
                    if result.returncode:
                        raise RuntimeError('Real browser check failed; see responsiveness.log.')
                    timings = json.loads((output/'browser.json').read_text(encoding='utf-8'))
                    import statistics
                    idle = [s['seconds'] for s in timings['samples'] if s['phase']=='idle' and s['operation']=='highlight']
                    busy = [s['seconds'] for s in timings['samples'] if s['phase']=='worker_running' and s['operation']=='highlight']
                    report['budgets'] = {
                        'first_plots':{'seconds':timings['first_screen_samples_seconds'][0],'limit_seconds':5},
                        'selection_idle':{'seconds':statistics.median(idle),'samples':idle,'limit_seconds':.5},
                        'selection_busy':{'seconds':statistics.median(busy),'samples':busy,'limit_seconds':.5}}
                    for budget in report['budgets'].values():
                        budget['passed'] = budget['seconds'] <= budget['limit_seconds']
                    report['passed'] = all(b['passed'] for b in report['budgets'].values())
                finally:
                    browser.close()
        except BaseException as exc:
            report['errors'].append(f'{type(exc).__name__}: {exc}')
            raise
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            report['server_closed'] = server.poll() is not None
            report['source_changes'] = [name for name,h in sources.items() if sha256(ROOT/name)!=h]
            report['input_unchanged'] = sha256(source)==report['source_sha256']
            write_json(output/'checks.json',report)
    assert not report['source_changes'] and report['input_unchanged'],report
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8547)
    parser.add_argument('--cdp-port',type=int,default=9451)
    parser.add_argument('--reloads',type=int,default=3)
    report = check(**vars(parser.parse_args()))
    print(json.dumps(report.get('budgets',report['errors'])),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
