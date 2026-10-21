"""Actual browser DOM checks for controls replaced during linked-view redraw."""
import pytest
from scripts.check_ui_responsiveness import Browser, SUBJECT_CONTROL_READY, open_subject_control


@pytest.fixture(scope='module')
def browser():
    browser_api=pytest.importorskip('playwright.sync_api',reason='Owned browser verification needs Playwright')
    sync_playwright=browser_api.sync_playwright
    with sync_playwright() as p:
        try:instance=p.chromium.launch(channel='msedge',headless=True)
        except browser_api.Error as exc:
            pytest.skip('Owned Edge verification is unavailable: '+str(exc))
        try:
            page=instance.new_page()
            class Adapter:
                js=staticmethod(page.evaluate)
                wait=Browser.wait
            yield page,Adapter()
        finally:instance.close()


def test_missing_control_can_appear_without_null_click_error(browser):
    page,adapter=browser
    page.set_content('<div class="st-key-ui_explore_subject"></div>')
    assert page.evaluate(SUBJECT_CONTROL_READY) is False
    page.evaluate("""() => {window.clicked=0;setTimeout(() => {
        const e=document.createElement('input');e.setAttribute('role','combobox');
        e.addEventListener('click',()=>window.clicked++);
        document.querySelector('div').appendChild(e);
    },80)}""")
    open_subject_control(adapter,timeout=2)
    assert page.evaluate('window.clicked')==1
    assert page.evaluate("document.activeElement.getAttribute('role')")== 'combobox'
    assert page.evaluate(SUBJECT_CONTROL_READY) is True


def test_disabled_control_waits_until_it_is_usable(browser):
    page,adapter=browser
    page.set_content('<div class="st-key-ui_explore_subject"><input role="combobox" disabled></div>')
    assert page.evaluate(SUBJECT_CONTROL_READY) is False
    page.evaluate("""() => {window.clicked=0;const e=document.querySelector('input');
        e.addEventListener('click',()=>window.clicked++);setTimeout(()=>e.disabled=false,80)}""")
    open_subject_control(adapter,timeout=2)
    assert page.evaluate('window.clicked')==1


def test_permanently_missing_control_refuses_completion(browser):
    page,adapter=browser;page.set_content('<div></div>')
    with pytest.raises(TimeoutError):open_subject_control(adapter,timeout=.05)
