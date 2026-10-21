"""Verify the real one-page function editor on one explicitly selected CDP tab."""
import argparse
import base64
import json
from pathlib import Path
import time
import urllib.request
from urllib.parse import urlsplit

from check_ui_responsiveness import Browser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tab-id", required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9333")
    parser.add_argument("--url", default="http://127.0.0.1:8511/functions")
    parser.add_argument("--output", required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--run", action="store_true", help="Run four real owning-package analyses on explicitly chosen available inputs.")
    parser.add_argument("--resume", action="store_true", help="Keep completed runs from this review's existing receipt.")
    parser.add_argument('--verify-busy-result',action='store_true',help='Repeat the recorded histogram inputs and verify that draft edits retain the previous figure during a real job.')
    parser.add_argument("--horizontal", help="Verified display label for a summary measurement.")
    parser.add_argument("--vertical", help="Verified display label for the second summary measurement.")
    parser.add_argument("--marker", help="Verified object-table marker.")
    parser.add_argument("--object-measurement", help="Verified numeric object measurement.")
    args = parser.parse_args()
    if args.run and not all((args.horizontal, args.vertical, args.marker, args.object_measurement)):
        parser.error("Real runs require all four explicitly verified input labels.")
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    browser = Browser(args.cdp, args.tab_id)
    from playwright.sync_api import sync_playwright
    playwright = sync_playwright().start()
    connection = playwright.chromium.connect_over_cdp(args.cdp, timeout=15000)
    # Match the explicitly authorized target identity; never select a user's
    # other tab by its position in the window.
    page = None
    target_url = browser.js('location.href')
    for context_ in connection.contexts:
        for candidate in context_.pages:
            if candidate.url != target_url:
                continue
            session = context_.new_cdp_session(candidate)
            identity = session.send("Target.getTargetInfo")["targetInfo"]["targetId"]
            session.detach()
            if identity == args.tab_id:
                page = candidate
                break
        if page is not None:
            break
    if page is None:
        raise ValueError("The explicitly selected browser tab is unavailable.")
    browser.call("Page.bringToFront")
    before = browser.call("Page.captureScreenshot", format="png")
    (output / "before.png").write_bytes(base64.b64decode(before["data"]))
    idle = "document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state')==='notRunning'"
    root_url = urlsplit(args.url)._replace(path="/", query="", fragment="").geturl()
    deadline = time.perf_counter() + 120
    while True:
        try:
            urllib.request.urlopen(root_url + "_stcore/health", timeout=1).close()
            break
        except OSError:
            if time.perf_counter() >= deadline:
                raise
            time.sleep(.1)
    # Bootstrap the canonical router after a server restart. Visiting an
    # auto-discovered page first otherwise bypasses the shared dataset loader.
    page.goto(root_url, wait_until="domcontentloaded")
    browser.wait("Boolean(document.querySelector('h1#explore'))", timeout=35)
    browser.wait(idle, timeout=35)
    page.goto(args.url, wait_until="domcontentloaded")
    browser.wait("Boolean(document.querySelector('input[aria-label=\"Find a plot or pipeline\"]'))", timeout=35)
    browser.wait(idle, timeout=35)
    if args.inspect:
        print(browser.js("document.querySelector('[data-testid=stMain]').innerText.slice(0,6000)"), flush=True)
        print(browser.js("({cards:document.querySelectorAll('.pf-function-card:not([hidden])').length,inputs:[...document.querySelectorAll('input')].map(e=>({label:e.getAttribute('aria-label'),value:e.value}))})"), flush=True)
        screenshot_data = browser.call("Page.captureScreenshot", format="png")
        (output / "inspect.png").write_bytes(base64.b64decode(screenshot_data["data"]))
        playwright.stop()
        browser.ws.close()
        return
    def screenshot(name):
        page.mouse.move(0,0)
        page.wait_for_timeout(100)
        data = browser.call("Page.captureScreenshot", format="png")
        (output / name).write_bytes(base64.b64decode(data["data"]))
    def open_fold(label):
        control=page.get_by_text(label,exact=True)
        if not control.evaluate("e=>e.closest('details').open"):
            control.click()
        browser.wait(idle)
    def click(expression):
        browser.wait("Boolean(" + expression + ")", timeout=25)
        element = page.evaluate_handle(expression).as_element()
        if element.get_attribute("role") != "option":
            element.evaluate("e => e.scrollIntoView({block:'center'})")
        element.click(timeout=25000)
    def type_input(expression, value):
        browser.wait("Boolean(" + expression + ")", timeout=25)
        element = page.evaluate_handle(expression).as_element()
        element.fill(value)
        element.press("Enter")
        element.press("Tab")
    def select(label, value, multi=False):
        widget = "[...document.querySelectorAll('[data-testid=" + ("stMultiSelect" if multi else "stSelectbox") + "]')].find(e=>e.querySelector('label')?.innerText.trim()===" + json.dumps(label) + ")"
        combo = "(" + widget + ").querySelector('[role=combobox]')"
        current = ("[...(" + widget + ").querySelectorAll('[data-baseweb=tag]')].some(e=>e.innerText.includes(" + json.dumps(value) + "))" if multi else
                   "(" + combo + ").getAttribute('aria-label')?.startsWith(" + json.dumps("Selected " + value + ". ") + ")")
        if browser.js(current):
            return
        click(combo)
        page.evaluate_handle(combo).as_element().fill(value)
        option = "[...document.querySelectorAll('[role=option]')].find(e=>e.innerText.trim()===" + json.dumps(value) + ")"
        browser.wait("Boolean(" + option + ")")
        click(option)
        browser.wait(current)
        if multi:
            page.keyboard.press("Escape")
        browser.wait(idle)
    for label in ("Task",):
        text = browser.js("[...document.querySelectorAll('[data-testid=stSelectbox]')].find(e=>e.querySelector('label')?.innerText.trim()===" + json.dumps(label) + ")?.innerText")
        if text and not text.strip().endswith("All"):
            select(label, "All")
    search_box = "document.querySelector('input[aria-label=\"Find a plot or pipeline\"]')"
    type_input(search_box, "")
    from PyFLASH.ui import function_contracts as fc
    from PyFLASH.ui import function_workflows as flow
    expected_entries = len(flow.checked_homes())
    browser.wait("document.querySelectorAll('.pf-function-card:not([hidden])').length===" + str(expected_entries), timeout=25)
    screenshot("workbench-desktop.png")
    report = {"entries": browser.js("document.querySelectorAll('.pf-function-card:not([hidden])').length"),
              "url": browser.js("location.href"), "search_seconds": [], "selection_seconds": [],
              "search_response_seconds": [], "form_response_seconds": [], "runs": []}
    if args.resume and (output / "report.json").is_file():
        previous = json.loads((output / "report.json").read_text(encoding="utf-8"))
        report["runs"] = [r for r in previous.get("runs", []) if all(Path(p).is_file() for p in r["outputs"])]
        for key in ("search_during_job_seconds", "editing_during_active_job",'prior_result_visible_during_job','previous_figures_retained_during_draft_edit','running_inputs_frozen'):
            if key in previous:
                report[key] = previous[key]
    report["initial_text"] = browser.js("document.querySelector('[data-testid=stMain]').innerText")
    def measure_response(expected, event, selector):
        # Measure from the actual Enter/click event to the next rendered frame;
        # automation scrolling and locator retries are separate driver timings.
        browser.js("""(() => {
            window.__pfResponse?.observer?.disconnect();
            const state = {start:null, milliseconds:null};
            window.__pfResponse = state;
            const selector = """ + json.dumps(selector) + """;
            const begin = e => {
                if (!e.target.closest(selector) || (e.type==='keydown' && e.key!=='Enter')) return;
                state.start = e.timeStamp;
                document.removeEventListener(""" + json.dumps(event) + """, begin, true);
            };
            document.addEventListener(""" + json.dumps(event) + """, begin, true);
            state.observer = new MutationObserver(() => {
                if (state.start!==null && (""" + expected + """)) {
                    state.observer.disconnect();
                    requestAnimationFrame(() => state.milliseconds = performance.now()-state.start);
                }
            });
            state.observer.observe(document.body, {childList:true,subtree:true});
        })()""")
    def response_sample():
        browser.wait("window.__pfResponse?.milliseconds!==null", timeout=20)
        return browser.js("window.__pfResponse.milliseconds") / 1000
    if args.inspect:
        report["controls"] = browser.js("[...document.querySelectorAll('[data-testid=stSelectbox],[data-testid=stMultiSelect],[data-testid=stNumberInput]')].map(e=>e.innerText)")
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
        return
    def choose(action, title):
        from PyFLASH.ui import function_contracts as fc
        title = flow.title(fc.find(action))
        expected_count = len({flow.home(c.entry.action).key for c in fc.search(fc.catalogue_contracts(), action)})
        measure_response("document.querySelectorAll('.pf-function-card:not([hidden])').length===" + str(expected_count),
                         "keydown", 'input[aria-label="Find a plot or pipeline"]')
        start = time.perf_counter()
        type_input(search_box, action)
        browser.wait("document.querySelectorAll('.pf-function-card:not([hidden])').length===" + str(expected_count))
        report["search_response_seconds"].append(response_sample())
        expression = "document.querySelector('.pf-function-card:not([hidden]) button[data-function=\"action:" + action + "\"]')"
        browser.wait("Boolean(" + expression + ")")
        report["search_seconds"].append(time.perf_counter() - start)
        ready = "[...document.querySelector('#function-editor').closest('[data-testid=stColumn]').querySelectorAll('h2,h3')].some(e=>e.innerText===" + json.dumps(title) + ")"
        changed = not browser.js(ready)
        if changed:
            measure_response(ready, "click", '.pf-function-card button')
        start = time.perf_counter()
        click(expression)
        browser.wait(ready, timeout=25)
        browser.wait(idle)
        if changed:
            report["form_response_seconds"].append(response_sample())
        report["selection_seconds"].append(time.perf_counter() - start)
        assert browser.js("location.pathname") == "/functions"
        assert browser.js("document.querySelectorAll('[data-testid=stException]').length") == 0
    choose("mean_bars", "Compare group means")
    if args.run:
        from PyFLASH.ui import jobs, workspace, function_contracts as fc
        from PyFLASH.ui.loading import open_source
        source = workspace.read_recovery(workspace.recovery_path())["source"]
        source_digest = workspace.content_hash(source["path"])
        context = fc.input_context(open_source(source), "SCN")
        report["source_sha256"] = source_digest
        args.horizontal = context["labels"].get(args.horizontal, args.horizontal)
        args.vertical = context["labels"].get(args.vertical, args.vertical)
        def execute(action, title, *, verify_previous=False):
            if not verify_previous and any(r["action"] == action for r in report["runs"]):
                return
            old = jobs.latest_job()
            old_id = old["id"] if old else None
            if verify_previous:
                page.get_by_role('button',name="Restore this run's inputs",exact=True).click()
                browser.wait("!document.querySelector('[data-testid=stMain]').textContent.includes('Inputs changed')")
                browser.wait(idle)
            button = "[...document.querySelectorAll('button')].find(e=>e.innerText.trim().endsWith(" + json.dumps("Run pipeline" if flow.home(action).pipeline else "Create plot") + "))"
            browser.wait("Boolean(" + button + ")")
            previous_images=browser.js("[...document.querySelectorAll('[data-testid=stImage] img')].map(e=>e.src)") if verify_previous else []
            if verify_previous:
                assert previous_images, 'A completed figure must be present before testing retained results.'
            click(button)
            deadline = time.perf_counter() + 600
            started = time.perf_counter()
            state = None
            edit_checked = False
            # This intentionally measures the worker and browser result boundary.
            while time.perf_counter() < deadline:
                state = jobs.latest_job()
                if state and state["id"] != old_id and state["status"] not in jobs.ACTIVE_STATES:
                    break
                if state and state["id"] != old_id and state["status"] in jobs.ACTIVE_STATES and not edit_checked:
                    edit_start = time.perf_counter()
                    type_input(search_box, "histograms")
                    browser.wait("document.querySelectorAll('.pf-function-card:not([hidden])').length<10")
                    browser.wait(idle)
                    report["search_during_job_seconds"] = time.perf_counter() - edit_start
                    assert not browser.js("document.querySelector('[data-testid=stException]')")
                    report["editing_during_active_job"] = jobs.latest_job()["status"] in jobs.ACTIVE_STATES
                    report["prior_result_visible_during_job"] = browser.js("Boolean([...document.querySelectorAll('h2,h3')].find(e=>e.innerText==='Result'))")
                    type_input(search_box, action)
                    browser.wait(idle)
                    if verify_previous:
                        field=page.get_by_role('spinbutton',name='Number of bins',exact=True)
                        changed_bins=int(float(field.input_value() or '30'))+1
                        field.fill(str(changed_bins)); field.press('Enter'); field.press('Tab')
                        browser.wait("document.querySelector('[data-testid=stMain]').textContent.includes('Inputs changed')",timeout=25)
                        browser.wait(idle)
                        assert page.get_by_role('button',name='Create plot',exact=True).is_disabled()
                        assert browser.js("[...document.querySelectorAll('[data-testid=stImage] img')].map(e=>e.src)")==previous_images
                        assert 'Inputs changed' in page.locator('[data-testid=stMain]').inner_text()
                        snapshot=json.loads((jobs.jobs_root()/state['id']/'request.json').read_text())
                        assert snapshot['parameters']['kwargs'].get('bins') != changed_bins
                        report['previous_figures_retained_during_draft_edit']=True
                        report['running_inputs_frozen']=True
                        screenshot('retained-result-during-job.png')
                    edit_checked = True
                    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                time.sleep(.2)
            assert state and state["id"] != old_id and state["status"] == "succeeded", state
            if verify_previous:
                assert edit_checked and report.get('previous_figures_retained_during_draft_edit')
            browser.wait("[...document.querySelectorAll('h2,h3')].some(e=>e.innerText==='Result')", timeout=20)
            screenshot(action + "-result.png")
            request = json.loads((jobs.jobs_root() / state["id"] / "request.json").read_text(encoding="utf-8"))
            result = json.loads((jobs.jobs_root() / state["id"] / "result.json").read_text(encoding="utf-8"))
            assert result["paths"], result
            report["runs"].append({"action": action, "seconds": time.perf_counter() - started,
                                   "job": state["id"], "parameters": request["parameters"], "outputs": result["paths"]})
            (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        # Search the entire dataset rather than guessing from the bounded menu.
        type_input("document.querySelector('input[aria-label=\"Find measurements\"]')", args.horizontal)
        browser.wait(idle)
        select("Measurements", args.horizontal, multi=True)
        execute("mean_bars", "Compare group means")
        choose("regressions", "Relate two measurements")
        type_input("document.querySelector('input[aria-label=\"Find horizontal measurement\"]')", args.horizontal)
        browser.wait(idle)
        select("Horizontal measurement", args.horizontal)
        type_input("document.querySelector('input[aria-label=\"Find vertical measurement\"]')", args.vertical)
        browser.wait(idle)
        select("Vertical measurement", args.vertical)
        execute("regressions", "Relate two measurements")
        choose("histograms", "Inspect measurement distributions")
        select("Object marker", args.marker)
        select("Object measurement", args.object_measurement)
        execute("histograms", "Inspect measurement distributions",verify_previous=args.verify_busy_result)
        import numpy as np
        bar_run = next(r for r in report["runs"] if r["action"] == "mean_bars")
        bar_result = json.loads((jobs.jobs_root() / bar_run["job"] / "result.json").read_text())["value"]
        bar_column = bar_run["parameters"]["kwargs"]["data_cols"][0]
        for group, mean, count in zip(bar_result["condition"], bar_result["mean"], bar_result["n"]):
            data = context["table"].loc[context["table"]["Condition"] == group, bar_column].dropna()
            assert len(data) == count
            np.testing.assert_allclose(mean, data.mean(), rtol=1e-12, atol=1e-12)
        report["group_means_and_subject_counts_match_source"] = True
        report["source_unchanged"] = workspace.content_hash(source["path"]) == source_digest
        assert report["source_unchanged"]
    if args.run:
        choose("group_comparison_pipeline", "Group comparison")
        type_input("document.querySelector('input[aria-label=\"Find measurements\"]')", args.horizontal)
        browser.wait(idle)
        select("Measurements", args.horizontal, multi=True)
        execute("group_comparison_pipeline", "Group comparison")
    choose("model_result_matrix", "View fitted-model results")
    choose("images", "Browse microscopy images")
    type_input(search_box, "no_such_function_12345")
    browser.wait("document.querySelectorAll('.pf-function-card:not([hidden])').length===0")
    type_input(search_box, "")
    browser.wait("document.querySelectorAll('.pf-function-card:not([hidden])').length===" + str(report["entries"]))
    report["no_pagination"] = not browser.js("[...document.querySelectorAll('[data-testid=stSelectbox] label')].some(e=>e.innerText.trim()==='Page')")
    assert browser.js("[...document.querySelectorAll('.pf-picture-card')].map(e=>e.dataset.home)")==[h.key for h in flow.HOMES]
    report['stable_gallery_order']=True
    browser.call("Emulation.setDeviceMetricsOverride", width=800, height=900, deviceScaleFactor=1, mobile=False)
    time.sleep(.3); screenshot("workbench-narrow.png")
    report["narrow_no_overflow"] = browser.js("document.documentElement.scrollWidth<=innerWidth")
    report['narrow_editor_follows_gallery']=browser.js("document.querySelector('#function-editor').getBoundingClientRect().top-document.querySelector('.st-key-function_catalogue').getBoundingClientRect().bottom<100")
    assert report['narrow_editor_follows_gallery']
    report['narrow_inputs_use_full_width']=browser.js("document.querySelector('#function-inputs').closest('[data-testid=stColumn]').getBoundingClientRect().width>=document.querySelector('#function-editor').closest('[data-testid=stColumn]').getBoundingClientRect().width-2")
    assert report['narrow_inputs_use_full_width']
    browser.call("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
    browser.call("Emulation.setEmulatedMedia", features=[{"name":"prefers-color-scheme", "value":"dark"}])
    time.sleep(.3); screenshot("workbench-dark.png")
    report["exceptions"] = browser.js("document.querySelectorAll('[data-testid=stException]').length")
    browser.call("Emulation.setEmulatedMedia", features=[{"name":"prefers-color-scheme", "value":"light"}])
    assert report["entries"] == len(flow.checked_homes())
    keys = browser.js("[...document.querySelectorAll('.pf-function-card')].flatMap(e=>JSON.parse(e.dataset.variants).map(v=>v.key))")
    assert set(keys) == {c.entry.key for c in fc.catalogue_contracts()}
    report["registered_actions"]=len(keys)
    report["only_plotting_and_pipeline_actions"] = True
    # Supporting tools retain a useful home without appearing in the main list.
    page.goto(root_url + "export", wait_until="domcontentloaded")
    browser.wait("Boolean(document.querySelector('h1#export'))", timeout=25)
    browser.wait(idle)
    assert "Excel workbooks" in browser.js("document.querySelector('[data-testid=stMain]').innerText")
    open_fold('Export package reference')
    select("Package function", "Batch.export_all_excel")
    browser.wait("document.querySelector('[data-testid=stMain]').textContent.includes('export_all_excel(')", timeout=25)
    open_fold('Function reference')
    report["excel_export_in_export"] = True
    screenshot("export-reference.png")
    page.goto(root_url + "workspace", wait_until="domcontentloaded")
    browser.wait("Boolean(document.querySelector('h1#workspace'))", timeout=25)
    browser.wait(idle)
    open_fold('House aesthetic')
    page.get_by_role("button", name="Save house aesthetic", exact=True).wait_for(state='visible',timeout=15000)
    report["house_aesthetic_in_workspace"] = True
    screenshot("workspace-house-aesthetic.png")
    open_fold('Other package functions')
    widget = page.locator('[data-testid=stSelectbox]').filter(has=page.locator('label',has_text='Package function')).last
    widget.get_by_role('combobox').click()
    widget.get_by_role('combobox').fill('bonferroni_correction')
    page.get_by_role('option',name='bonferroni_correction',exact=True).click()
    browser.wait("document.querySelector('[data-testid=stMain]').textContent.includes('Correct one p-value')", timeout=25)
    browser.wait(idle)
    report["statistics_helper_in_workspace"] = True
    page.goto(args.url, wait_until="domcontentloaded")
    browser.wait("Boolean(document.querySelector('#function-editor'))", timeout=25)
    browser.wait(idle)
    choose("mean_bars", "Compare group means")
    if report['runs']:
        open_fold('Saved runs')
        select('Completed run', flow.title(fc.find('histograms')))
        page.get_by_role('button',name='Reopen this run',exact=True).click()
        browser.wait("[...document.querySelectorAll('h2,h3')].some(e=>e.innerText==='Histogram')",timeout=25)
        browser.wait(idle)
        assert page.get_by_role('button',name="Restore this run's inputs",exact=True).is_visible()
        report['saved_run_restoration']=True
        choose('mean_bars','Compare group means')
        select('Columns','1')
    type_input(search_box, "")
    browser.wait("document.querySelectorAll('.pf-function-card:not([hidden])').length===" + str(report["entries"]))
    browser.wait(idle)
    browser.js("document.querySelector('h1').scrollIntoView({block:'start'})")
    screenshot("workbench-final.png")
    assert report["no_pagination"] and report["narrow_no_overflow"] and not report["exceptions"]
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "initial_text"}), flush=True)
    # Disconnect automation without closing any of the user's browser tabs.
    playwright.stop()
    browser.ws.close()


if __name__ == "__main__":
    main()
