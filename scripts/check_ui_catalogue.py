"""Inspect the sibling catalogue or verify PyFLASH's real functions page.

Uses an explicitly selected local browser tab; writes screenshots and a small
receipt, never runs an analysis. Requires websocket-client and CDP on port 9333.
"""
import argparse
import base64
import json
from pathlib import Path
import time

from check_ui_responsiveness import Browser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tab-id", required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9333")
    parser.add_argument("--output", required=True)
    parser.add_argument("--sibling", action="store_true")
    args = parser.parse_args()
    if not args.sibling:
        import subprocess
        import sys
        subprocess.run([sys.executable, str(Path(__file__).with_name("check_ui_function_workbench.py")),
                        "--tab-id", args.tab_id, "--cdp", args.cdp, "--output", args.output], check=True)
        return
    browser = Browser(args.cdp, args.tab_id)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    def screenshot(name):
        capture = browser.call("Page.captureScreenshot", format="png")
        (output / name).write_bytes(base64.b64decode(capture["data"]))

    def click(expression):
        rectangle = browser.js(f"({expression}).getBoundingClientRect().toJSON()")
        browser.call("Input.dispatchMouseEvent", type="mousePressed", x=rectangle["x"] + rectangle["width"] / 2,
                     y=rectangle["y"] + rectangle["height"] / 2, button="left", clickCount=1)
        browser.call("Input.dispatchMouseEvent", type="mouseReleased", x=rectangle["x"] + rectangle["width"] / 2,
                     y=rectangle["y"] + rectangle["height"] / 2, button="left", clickCount=1)

    browser.call("Page.bringToFront")
    screenshot("before.png")
    if args.sibling:
        browser.js("document.querySelector('[data-workspace=micro]').click()")
        browser.wait("Boolean([...document.querySelectorAll('button')].find(e=>e.textContent==='All methods'))")
        click("[...document.querySelectorAll('button')].find(e=>e.textContent==='All methods')")
        browser.wait("Boolean(document.querySelector('.method-search'))")
        screenshot("pymicroglia-all-methods.png")
        report = browser.js("({title:document.querySelector('#page-title').textContent,cards:document.querySelectorAll('[data-search]').length,sections:[...document.querySelectorAll('#micro-content h2')].map(e=>e.textContent),setup_buttons:[...document.querySelectorAll('#micro-content button')].filter(e=>e.textContent.includes('Set up')).length})")
    else:
        browser.call("Page.navigate", url="http://127.0.0.1:8511/functions")
        idle = "document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state')==='notRunning'"
        browser.wait("Boolean([...document.querySelectorAll('h1')].find(e=>e.textContent==='Functions'))", timeout=30)
        browser.wait(idle, timeout=30)
        browser.wait("Boolean(document.querySelector('input[aria-label=\"Search functions\"]'))", timeout=30)
        for label in ("Access", "Module"):
            control = "[...document.querySelectorAll('[data-testid=stSelectbox]')].find(e=>e.innerText.startsWith(" + json.dumps(label) + "))"
            if not browser.js("(" + control + ").innerText.trim().endsWith('All')"):
                click(control + ".querySelector('[data-baseweb=select]')")
                browser.js("(" + control + ").querySelector('[role=combobox]').focus()")
                browser.call("Input.dispatchKeyEvent", type="keyDown", key="a", code="KeyA", windowsVirtualKeyCode=65, modifiers=2)
                browser.call("Input.dispatchKeyEvent", type="keyUp", key="a", code="KeyA", windowsVirtualKeyCode=65, modifiers=2)
                browser.call("Input.insertText", text="All")
                option = "[...document.querySelectorAll('[role=option]')].find(e=>e.innerText.trim()==='All')"
                browser.wait("Boolean(" + option + ")")
                browser.js("(" + option + ").click()")
                browser.wait("(" + control + ").innerText.trim().endsWith('All')")
                time.sleep(.3)
                browser.wait(idle)
        assert browser.js("document.querySelectorAll('[data-testid=stException]').length") == 0
        screenshot("pyflash-functions.png")
        report = {"initial_text": browser.js("document.querySelector('[data-testid=stMain]').innerText")}
        input_expression = "document.querySelector('input[aria-label=\"Search functions\"]')"
        def search(value):
            browser.call("Page.bringToFront")
            browser.wait("Boolean(" + input_expression + ")", timeout=30)
            click(input_expression)
            browser.js("(" + input_expression + ").focus()")
            browser.call("Input.dispatchKeyEvent", type="keyDown", key="a", code="KeyA", windowsVirtualKeyCode=65, modifiers=2)
            browser.call("Input.dispatchKeyEvent", type="keyUp", key="a", code="KeyA", windowsVirtualKeyCode=65, modifiers=2)
            if value:
                browser.call("Input.insertText", text=value)
            else:
                browser.call("Input.dispatchKeyEvent", type="keyDown", key="Backspace", code="Backspace", windowsVirtualKeyCode=8)
                browser.call("Input.dispatchKeyEvent", type="keyUp", key="Backspace", code="Backspace", windowsVirtualKeyCode=8)
            # Allow React to receive the typed value. A frame callback can stall
            # indefinitely if another task backgrounds this shared browser tab.
            time.sleep(.08)
            # Enter needs its text payload to emit the keypress used by text inputs.
            browser.call("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
            browser.call("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
            click("document.querySelector('h1')")  # commits on blur as a real user click does
        started = time.perf_counter()
        search("mean_bars")
        browser.wait("document.querySelector('.pf-function-card h3')?.textContent==='mean bars'", timeout=30)
        browser.wait(idle)
        report["search_seconds"] = time.perf_counter() - started
        assert browser.js("[...document.querySelectorAll('[data-testid=stMain] button')].some(e=>e.textContent.includes('Set up'))")
        screenshot("pyflash-functions-search.png")
        click("[...document.querySelectorAll('button')].find(e=>e.textContent.includes('Details'))")
        browser.wait("document.body.innerText.includes('plot_mean_bars(')")
        screenshot("pyflash-functions-details.png")
        browser.js("document.querySelector('[role=dialog] [aria-label=Close]').click()")
        browser.wait("!document.querySelector('[role=dialog]')")
        click("[...document.querySelectorAll('button')].find(e=>e.textContent.includes('Set up'))")
        browser.wait("Boolean([...document.querySelectorAll('h1')].find(e=>e.textContent==='Figures'))")
        browser.wait(idle)
        report["figure_handoff"] = browser.js("[...document.querySelectorAll('[data-testid=stSelectbox]')].find(e=>e.innerText.includes('Figure type')).innerText")
        assert "Mean bars" in report["figure_handoff"]
        assert browser.js("document.querySelectorAll('[data-testid=stException]').length") == 0
        # Return to the catalogue; make the complete index available to the user.
        click("[...document.querySelectorAll('a')].find(e=>e.getAttribute('href')==='functions')")
        browser.wait("Boolean([...document.querySelectorAll('h1')].find(e=>e.textContent==='Functions'))")
        browser.wait(idle)
        search("save_fig")
        browser.wait("document.querySelector('.pf-function-card h3')?.textContent==='save fig'")
        browser.wait(idle)
        click("[...document.querySelectorAll('button')].find(e=>e.textContent.includes('Details'))")
        browser.wait("document.body.innerText.includes('save_fig(')")
        assert not browser.js("document.querySelector('[role=dialog]').innerText.includes('Set up in Figures')")
        browser.js("document.querySelector('[role=dialog] [aria-label=Close]').click()")
        browser.wait("!document.querySelector('[role=dialog]')")
        report["python_access"] = True
        search("no_such_function_12345")
        browser.wait("document.querySelector('[data-testid=stMain]').innerText.includes('No functions match')")
        report["empty_search"] = True
        search("")
        browser.wait("/([0-9]+) of \\1 entries/.test(document.querySelector('[data-testid=stMain]').innerText)")
        expected = browser.js("Number(document.querySelector('[data-testid=stMain]').innerText.match(/([0-9]+) of ([0-9]+) entries/)[2])")
        browser.wait("[...document.querySelectorAll('[data-testid=stMain] button')].filter(e=>e.textContent.includes('Details')).length === " + str(expected), timeout=30)
        report["visible_entries"] = browser.js("[...document.querySelectorAll('[data-testid=stMain] button')].filter(e=>e.textContent.includes('Details')).length")
        report["no_pagination"] = not browser.js("[...document.querySelectorAll('[data-testid=stSelectbox] label')].some(e=>e.textContent==='Page')")
        assert report["no_pagination"]
        report["exceptions"] = browser.js("document.querySelectorAll('[data-testid=stException]').length")
        assert report["exceptions"] == 0
        browser.call("Emulation.setDeviceMetricsOverride", width=800, height=900, deviceScaleFactor=1, mobile=False)
        time.sleep(.3)
        screenshot("pyflash-functions-narrow.png")
        report["narrow_horizontal_overflow"] = browser.js("document.documentElement.scrollWidth > innerWidth")
        assert not report["narrow_horizontal_overflow"]
        browser.call("Emulation.clearDeviceMetricsOverride")
        browser.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
        time.sleep(.3)
        screenshot("pyflash-functions-dark.png")
        report["dark_background"] = browser.js("getComputedStyle(document.querySelector('[data-testid=stApp]')).backgroundColor")
        browser.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
        time.sleep(.3)
        report["light_background"] = browser.js("getComputedStyle(document.querySelector('[data-testid=stApp]')).backgroundColor")
        report["theme_switch"] = report["dark_background"] != report["light_background"]
        assert report["theme_switch"]
        screenshot("pyflash-functions.png")
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "initial_text"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
