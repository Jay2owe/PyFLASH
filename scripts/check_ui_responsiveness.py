"""Check real-browser readiness and navigation during bounded CPU processing.

Attach only to the given local app tab. Run a test-only 25-second CPU worker,
then the real saved-analysis reader; never reprocess raw data or export figures.
The JSON report records render completion, request samples, worker resources,
correctness and source identity. Requires websocket-client and psutil locally.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

SUBJECT_CONTROL_READY = """(() => {
    const e=document.querySelector('.st-key-ui_explore_subject [role=combobox]');
    return Boolean(e && !e.disabled && e.getAttribute('aria-disabled')!=='true'
        && e.getClientRects().length);
})()"""


def open_subject_control(browser, *, timeout=15):
    """Find and click in one browser evaluation during fragment replacement.

    Waiting for existence separately still races a subsequent redraw. Keep
    the original click-to-completed-plots timing boundary for option selection.
    """
    browser.wait("""(() => {
        const e=document.querySelector('.st-key-ui_explore_subject [role=combobox]');
        if (!e || e.disabled || e.getAttribute('aria-disabled')==='true'
                || !e.getClientRects().length) return false;
        e.click(); e.focus(); return true;
    })()""", timeout=timeout)


class Browser:
    def __init__(self, endpoint, tab):
        import websocket
        targets = json.load(urllib.request.urlopen(endpoint.rstrip("/") + "/json/list"))
        target = next(t for t in targets if t["id"] == tab)
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=15, suppress_origin=True)
        self.sequence = 0

    def call(self, method, **params):
        self.sequence += 1
        self.ws.send(json.dumps({"id": self.sequence, "method": method, "params": params}))
        while True:
            result = json.loads(self.ws.recv())
            if result.get("id") == self.sequence:
                if "error" in result:
                    raise RuntimeError(result["error"])
                return result.get("result", {})

    def js(self, expression):
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    def wait(self, expression, timeout=15):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            try:
                if self.js(expression):
                    return
            except RuntimeError as exc:
                if "context" not in str(exc).lower():
                    raise
            time.sleep(.02)
        raise TimeoutError(expression)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--tab-id", required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9333")
    parser.add_argument("--url", default="http://127.0.0.1:8511/")
    parser.add_argument("--output", required=True)
    parser.add_argument("--reloads", type=int, default=1,
                        help="Number of complete navigation-to-both-plots samples (cold then warm).")
    args = parser.parse_args()
    if args.reloads < 1:
        parser.error("--reloads must be positive")
    from PyFLASH.ui import jobs, workspace
    from PyFLASH.ui.project_io import Project
    import psutil
    browser = Browser(args.cdp, args.tab_id)
    browser.call("Page.bringToFront")
    # A newly launched server may not have bound its socket yet. A failed
    # navigation otherwise leaves Chrome on its connection-error page.
    from scripts.ui_readiness import wait_for_server
    server_readiness = wait_for_server(args.url)
    report = {"source_sha256": workspace.content_hash(args.source), "samples": [], "fixture": "25 second checksum-validated single CPU, then real saved-analysis reader"}
    report['server_readiness'] = server_readiness
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    def checkpoint(stage):
        from PyFLASH._persistence import write_json
        report['stage'] = stage
        write_json(output,report)
    ready = """(() => {const charts=[...document.querySelectorAll('[data-testid=stVegaLiteChart]')];return document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state')==='notRunning' && charts.length===2 && charts.every(c=>c.querySelector('svg .mark-symbol path'));})()""" + ' && ' + SUBJECT_CONTROL_READY
    idle = "document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state')==='notRunning'"
    report["first_screen_samples_seconds"] = []
    report["navigation_timing"] = []
    for _ in range(args.reloads):
        started = time.perf_counter()
        browser.call("Page.navigate", url=args.url)
        browser.wait(ready, timeout=30)
        report["first_screen_samples_seconds"].append(time.perf_counter() - started)
        report["navigation_timing"].append(browser.js("""(() => {
            const n=performance.getEntriesByType('navigation')[0];
            if (!n) return null;
            return {response_start_ms:n.responseStart, dom_interactive_ms:n.domInteractive,
                dom_content_loaded_ms:n.domContentLoadedEventEnd, load_event_ms:n.loadEventEnd,
                dom_complete_ms:n.domComplete, transfer_bytes:n.transferSize};
        })()"""))
    report["reload_to_both_plots_seconds"] = report["first_screen_samples_seconds"][0]
    checkpoint('initial_views_complete')
    print('Both plots usable',report["reload_to_both_plots_seconds"],flush=True)
    subject_label = browser.js("document.querySelectorAll('[data-testid=stVegaLiteChart]')[1].querySelector('svg path[aria-label*=\"Subject:\"]')?.getAttribute('aria-label')")
    subject = subject_label.split("Subject: ")[1].split(";")[0]
    def select(value):
        browser.call("Page.bringToFront")
        open_subject_control(browser)
        browser.call('Input.dispatchKeyEvent',type='keyDown',key='a',code='KeyA',windowsVirtualKeyCode=65,modifiers=2)
        browser.call('Input.dispatchKeyEvent',type='keyUp',key='a',code='KeyA',windowsVirtualKeyCode=65,modifiers=2)
        browser.call('Input.insertText',text=value)
        option = "[...document.querySelectorAll('[role=option]')].find(e=>e.innerText === " + json.dumps(value) + ")"
        browser.wait("Boolean("+option+")")
        clicked = browser.js("(() => {("+option+").click();return performance.now();})()")
        expected = "true" if value == "All subjects" else "false"
        browser.wait("""(() => {const charts=[...document.querySelectorAll('[data-testid=stVegaLiteChart]')];return charts.length===2 && charts.every(c=>Boolean([...c.querySelectorAll('svg .mark-symbol path')].some(p=>p.getAttribute('opacity')==='0.18')) !== """+expected+");})()")
        elapsed = browser.js('performance.now()') - clicked
        browser.wait(idle)
        return elapsed / 1000
    for value in (subject, "All subjects", subject, "All subjects"):
        report["samples"].append({"phase": "idle", "operation": "highlight", "seconds": select(value)})
    checkpoint('idle_selection_complete')
    source = Path(args.source).resolve()
    project = Project(name=source.stem, batch_path=str(source.parent), pickle_path=str(source.parent), import_images=False,
        conditions={"factor": "Genotype", "entries": [{"label": "WT", "color": "blue"}]})
    fixture = Path(__file__).resolve().parents[1] / 'tests/ui_worker_fixture.py'
    def launch(request_path, stream, env):
        # Explicit fixture launcher; production jobs never expose test callbacks.
        from reproducibility.run import python_command
        command = python_command()
        return subprocess.Popen([*command, '-u', str(fixture), str(request_path)], stdout=stream, stderr=stream,
            stdin=subprocess.DEVNULL, env=env, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    original_launcher=jobs._launch
    try:
        jobs._launch=launch
        started=time.perf_counter()
        identity=jobs.start_processing(project.to_dict())
        report['submit_seconds']=time.perf_counter()-started
    finally:
        jobs._launch=original_launcher
    deadline=time.perf_counter()+15
    while jobs.read_job(identity)['status']=='queued' and time.perf_counter()<deadline:
        time.sleep(.05)
    state=jobs.read_job(identity); assert state['status']=='running',state
    checkpoint('cpu_worker_running')
    browser.call('Page.navigate',url=args.url)
    browser.wait(ready)
    report['worker_pid']=state['worker_pid']
    worker=psutil.Process(state['worker_pid'])
    peak=worker.memory_info().rss
    def worker_memory():
        try:
            return worker.memory_info().rss
        except psutil.NoSuchProcess:
            return 0  # Normal completion can race the resource sampler.
    for value in (subject,"All subjects",subject,"All subjects"):
        assert jobs.read_job(identity)['status']=='running', 'Workload finished before interaction check'
        report['samples'].append({'phase':'worker_running','operation':'highlight','seconds':select(value)})
        peak=max(peak,worker_memory())
    checkpoint('busy_selection_complete')
    # Revisit every destination during the same live workload, including the
    # fragment-driven Explore view. One visit can miss a polling/navigation race.
    for route in ('workspace','figures','export','')*2:
        assert jobs.read_job(identity)['status']=='running'
        started=time.perf_counter()
        browser.call("Page.bringToFront")
        from PyFLASH.ui.workflow import page_heading
        label = page_heading(route or 'explore')
        browser.js("[...document.querySelectorAll('[data-testid=stSidebar] a')].find(a=>a.getAttribute('href') === "+json.dumps(route)+").click()")
        browser.wait("document.querySelector('h1')?.innerText === "+json.dumps(label))
        browser.wait(idle)
        if not route:browser.wait(ready)
        report['samples'].append({'phase':'worker_running','operation':'navigate_'+(route or 'explore'),'seconds':time.perf_counter()-started})
        peak=max(peak,worker_memory())
        assert browser.js("document.querySelectorAll('[data-testid=stException]').length")==0
        checkpoint('navigation_'+(route or 'explore')+'_complete')
    deadline=time.perf_counter()+35
    while jobs.read_job(identity)['status'] in jobs.ACTIVE_STATES and time.perf_counter()<deadline:
        peak=max(peak,worker_memory())
        time.sleep(.1)
    state=jobs.read_job(identity);assert state['status']=='succeeded',state
    report.update(job_state=state,worker_peak_observed_rss=peak,
                  recovery_highlight_seconds=select(subject),source_unchanged=workspace.content_hash(args.source)==report['source_sha256'])
    select('All subjects')
    assert report['source_unchanged']
    report['geometry']=json.loads(browser.js("JSON.stringify([...document.querySelectorAll('[data-testid=stVegaLiteChart]')].map(c=>{const r=[...c.querySelectorAll('svg path.background')].map(p=>p.getBoundingClientRect()).find(r=>r.width>100&&r.height>100);return {top:r.top,bottom:r.bottom}}))"))
    assert report['geometry'][0]==report['geometry'][1]
    browser.call('Page.bringToFront')
    checkpoint('complete')
    print(json.dumps(report,indent=2),flush=True)
    browser.ws.close()


if __name__=='__main__':main()
