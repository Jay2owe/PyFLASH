"""Review the real local workflow in Edge and save browser timings/screenshots.

Run with the Streamlit server already running. This performs no processing and
exports no scientific figures. Saved PNGs are screenshots of the interface.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import time
import statistics
import urllib.request

from playwright.sync_api import sync_playwright

if __package__:
    from .ui_readiness import wait_for_server
else:
    from ui_readiness import wait_for_server


def wait_views(page):
    page.wait_for_function("""() => {
        const charts = [...document.querySelectorAll('[data-testid="stVegaLiteChart"]')];
        return charts.length === 2 && charts.every(c => c.querySelector('svg .mark-symbol path'));
    }""", timeout=30000)


def wait_idle(page):
    page.wait_for_function("document.querySelector('[data-testid=stApp]').getAttribute('data-test-script-state') === 'notRunning'", timeout=30000)


def plot_alignment(page, *, stacked=False):
    """Check the data rectangles, rather than their enclosing chart widgets."""
    selector = '[data-testid="stVegaLiteChart"]'
    # Streamlit can publish the updated metric text just before Vega finishes
    # replacing its SVG. Wait for each chart's actual plot rectangle so a
    # transient empty redraw does not become a browser-check failure.
    page.wait_for_function("""selector => {
        const charts = [...document.querySelectorAll(selector)];
        return charts.length === 2 && charts.every(chart => [...chart.querySelectorAll('svg path.background')]
            .some(path => { const r = path.getBoundingClientRect(); return r.width > 100 && r.height > 100; }));
    }""", arg=selector, timeout=30000)
    bounds = page.locator(selector).evaluate_all("""charts => charts.map(chart => {
        const rectangles = [...chart.querySelectorAll('svg path.background')]
            .map(p => p.getBoundingClientRect())
            .filter(r => r.width > 100 && r.height > 100);
        rectangles.sort((a, b) => b.width * b.height - a.width * a.height);
        const r = rectangles[0];
        return r ? {top: r.top, bottom: r.bottom, height: r.height} : null;
    })""")
    assert len(bounds) == 2 and all(bounds), f"Both rendered charts need measurable plot areas: {bounds}"
    delta = abs(bounds[0]['height']-bounds[1]['height']) if stacked else max(abs(bounds[0][edge] - bounds[1][edge]) for edge in ("top", "bottom"))
    assert delta <= 0.5, f"Plot areas are vertically misaligned: {bounds}"
    if stacked:
        assert bounds[1]['top'] > bounds[0]['bottom'], 'Narrow comparison views must not overlap.'
    return {"layout":"stacked" if stacked else "adjacent","bounds": bounds, "maximum_difference_px": delta}


def open_choice(page, label, value):
    # Streamlit virtualises long menus. Searching brings an offscreen option
    # into the DOM and exercises the same keyboard route a user can take.
    box = page.locator('[data-testid="stSelectbox"]').filter(has_text=label).get_by_role("combobox")
    box.click()
    box.fill(value)
    page.get_by_role("option", name=value, exact=True).wait_for()


def _review(url, output, report):
    output.mkdir(parents=True, exist_ok=True)
    report['server_readiness'] = wait_for_server(url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page.on("pageerror", lambda error: report["errors"].append(str(error)))
        started = time.perf_counter()
        page.goto(url)
        wait_views(page)
        report["first_plots_seconds"] = round(time.perf_counter() - started, 3)
        report["vertical_alignment"] = {"default": plot_alignment(page)}
        page.screenshot(path=str(output / "explore-light.png"))
        report["screens"]["light"] = "explore-light.png"
        report["view_bounds"] = page.locator('[data-testid="stVegaLiteChart"]').evaluate_all(
            "els => els.map(e => e.getBoundingClientRect().toJSON())")
        report["chart_marks_before"] = page.locator('[data-testid="stVegaLiteChart"] svg .mark-symbol path').evaluate_all(
            "els => els.map(e => e.getAttribute('opacity'))")
        subject_box = page.locator('[data-testid="stSelectbox"]').filter(has_text="Highlight subject")
        samples = []
        for _ in range(5):
            open_choice(page, "Highlight subject", "All subjects")
            page.get_by_role("option", name="All subjects", exact=True).click()
            page.wait_for_function("""() => ![...document.querySelectorAll('[data-testid="stVegaLiteChart"] svg .mark-symbol path')].some(p => p.getAttribute('opacity') === '0.18')""")
            wait_idle(page)
            open_choice(page, "Highlight subject", "A01")
            # Start at the actual click event, excluding automation's wait for
            # menu animation/stability. Finish only after both SVGs redraw.
            page.evaluate("""() => {
                window.pfClickStarted = null;
                window.pfViewsFinished = null;
                document.addEventListener('click', () => {
                    window.pfClickStarted = performance.now();
                    const observer = new MutationObserver(() => {
                        const charts = [...document.querySelectorAll('[data-testid="stVegaLiteChart"]')];
                        if (charts.length === 2 && charts.every(c =>
                            [...c.querySelectorAll('svg .mark-symbol path')].some(p => p.getAttribute('opacity') === '0.18'))) {
                            observer.disconnect();
                            // The second animation frame follows the first paint
                            // containing both changed charts. Automation polling
                            // otherwise adds up to 100 ms to the measured latency.
                            requestAnimationFrame(() => requestAnimationFrame(() => {
                                window.pfViewsFinished = performance.now();
                            }));
                        }
                    });
                    observer.observe(document.body, {subtree:true, childList:true, attributes:true});
                }, {once: true, capture: true});
            }""")
            page.get_by_role("option", name="A01", exact=True).click()
            try:
                page.wait_for_function("""() => {
                const charts = [...document.querySelectorAll('[data-testid="stVegaLiteChart"]')];
                const done = charts.length === 2 && charts.every(c =>
                    [...c.querySelectorAll('svg .mark-symbol path')].some(p => p.getAttribute('opacity') === '0.18'));
                return done && window.pfViewsFinished !== null;
                }""")
            except Exception:
                report["failed_highlight_marks"] = page.locator('[data-testid="stVegaLiteChart"] svg .mark-symbol path').evaluate_all(
                    "els => els.map(p => ({opacity:p.getAttribute('opacity'), label:p.getAttribute('aria-label')}))")
                page.screenshot(path=str(output / "failed-highlight.png"))
                raise
            samples.append(round(page.evaluate('(window.pfViewsFinished - window.pfClickStarted) / 1000'), 3))
            wait_idle(page)
        report["subject_switch_samples_seconds"] = samples
        report["subject_switch_seconds"] = statistics.median(samples)
        report["selected_subject"] = page.get_by_text("A01", exact=True).count()
        report['point_labels'] = page.locator('[data-testid="stVegaLiteChart"]').nth(1).locator('svg .mark-symbol path').evaluate_all("els => els.map(p => p.getAttribute('aria-label'))")
        page.locator('[data-testid="stVegaLiteChart"]').nth(1).locator('svg path[aria-label*="B01"]').click()
        page.wait_for_function("""() => [...document.querySelectorAll('[data-testid="stVegaLiteChart"]')].every(c =>
            c.querySelector('svg path[aria-label*="B01"][opacity="0.9"]') &&
            c.querySelector('svg path[aria-label*="A01"][opacity="0.18"]'))""")
        report["point_click_links_both_views"] = True
        wait_idle(page)
        open_choice(page, "Highlight subject", "A01")
        page.get_by_role("option", name="A01", exact=True).click()
        wait_idle(page)
        # Metric choice belongs only to its own view.
        open_choice(page, "Distribution measurement", "DAPI Mean Intensity")
        page.get_by_role("option", name="DAPI Mean Intensity", exact=True).click()
        wait_views(page)
        page.wait_for_function("""() => {
            const charts = [...document.querySelectorAll('[data-testid="stVegaLiteChart"]')];
            return charts[0].textContent.includes('DAPI Mean Intensity') && charts[1].textContent.includes('Signal Mean Intensity');
        }""")
        report["independent_metrics"] = True
        report["vertical_alignment"]["different_measurements"] = plot_alignment(page)
        # Closed details do not load the table renderer during startup. Its
        # native disclosure must still reveal the full shown table and export.
        measurement_panels = page.locator('[data-testid=stExpander]').filter(has_text='Measurements and missing values')
        assert measurement_panels.count() >= 1, 'No measurement panel was rendered.'
        # Each chart owns a panel with the same title. The workflow contract
        # exercises the first view and keeps every action inside that panel.
        measurements = measurement_panels.first
        assert measurements.locator('[data-testid=stDataFrame]').count()==0
        summaries = measurements.locator('summary')
        assert summaries.count() >= 1, 'The first measurement panel has no disclosure control.'
        summaries.first.click()
        measurements.locator('[data-testid=stDataFrame]').wait_for()
        prepare = measurements.get_by_role('button',name='Prepare shown table')
        prepare.wait_for()
        prepare.click()
        download_table = measurements.get_by_role('button',name='Download shown table')
        download_table.wait_for(timeout=90000)
        measurements.get_by_role('button',name='Download table script').wait_for()
        with page.expect_download(timeout=30000) as downloaded:
            download_table.click()
        downloaded.value.save_as(str(output/'shown-measurements.csv'))
        with (output/'shown-measurements.csv').open(encoding='utf-8-sig',newline='') as stream:
            exported_rows = list(csv.DictReader(stream))
        assert len(exported_rows)==12
        assert {row['AnimalName'] for row in exported_rows}=={f'{group}{i:02d}' for group in ('A','B') for i in range(1,7)}
        wait_idle(page)
        report['lazy_measurement_panel'] = {'matching_panels':measurement_panels.count(),
            'closed_table_count':0,'open_table_count':measurements.locator('[data-testid="stDataFrame"]').count(),
            'export_available':True,'downloaded_rows':len(exported_rows),'replay_script_available':True}
        summaries.first.click()
        wait_idle(page)
        # Restore canonical metric and highlight before screenshot/recovery checks.
        open_choice(page, "Distribution measurement", "Signal Mean Intensity")
        page.get_by_role("option", name="Signal Mean Intensity", exact=True).click()
        wait_views(page)
        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(250)
        report["vertical_alignment"]["dark"] = plot_alignment(page)
        page.screenshot(path=str(output / "explore-dark.png"))
        report["screens"]["dark"] = "explore-dark.png"
        report["dark_background"] = page.locator('[data-testid="stApp"]').evaluate("e => getComputedStyle(e).backgroundColor")
        page.emulate_media(color_scheme="light")
        page.set_viewport_size({"width": 800, "height": 900})
        page.wait_for_timeout(250)
        page.screenshot(path=str(output / "explore-800.png"))
        report["screens"]["narrow"] = "explore-800.png"
        report["narrow_overflow"] = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        report["vertical_alignment"]["narrow"] = plot_alignment(page,stacked=True)
        page.set_viewport_size({"width": 1440, "height": 900})
        from PyFLASH.ui.workflow import page_heading
        for route in ("workspace", "folders", "groups", "process", "figures", "images", "export", "functions"):
            heading = page_heading(route)
            page.goto(f"{url.rstrip('/')}/{route}")
            page.get_by_role("heading", name=heading, exact=True).wait_for()
            errors = page.locator('[data-testid="stException"]').all_text_contents()
            report["routes"][route] = {"errors": errors}
            report["errors"].extend(errors)
            page.screenshot(path=str(output / f"{route}.png"))
        # A new browser session reopens the same selected subject.
        page.goto(url)
        wait_views(page)
        report["reopened_subject"] = page.locator('[data-testid="stSelectbox"]').filter(has_text="Highlight subject").inner_text()
        open_choice(page, "Highlight subject", "All subjects")
        page.get_by_role("option", name="All subjects", exact=True).click()
        wait_views(page)
        page.wait_for_function("""() => ![...document.querySelectorAll('[data-testid="stVegaLiteChart"] svg .mark-symbol path')].some(p => p.getAttribute('opacity') === '0.18')""")
        wait_idle(page)
        page.screenshot(path=str(output / "explore-light.png"))
        browser.close()
    (output / "browser-checks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["errors"] or report["narrow_overflow"]:
        raise SystemExit(1)


def review(url, output):
    report = {"url":url,"screens":{},"routes":{},"errors":[]}
    try:
        _review(url,output,report)
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        output.mkdir(parents=True,exist_ok=True)
        (output/'browser-checks.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8511")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review(args.url, args.output)
