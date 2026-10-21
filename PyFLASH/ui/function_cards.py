"""Lightweight continuous cards with one Streamlit event channel."""
from functools import lru_cache
from html import escape
import json

from PyFLASH.ui.theme import FUNCTION_CARDS_CSS


JS = r"""
export default function(component) {
    const {data, parentElement, setTriggerValue} = component;
    // A component update can reuse its DOM without calling the previous
    // renderer's returned cleanup. Keep exactly one live set of handlers,
    // including when a fragment redraws or a different page mounts the list.
    window.pyflashFunctionCardsCleanup?.();
    const grid = parentElement.querySelector('.pf-function-grid');
    const settings = typeof data === 'string' ? {html:data} : data;
    if (grid.__source !== settings.html) {
        grid.innerHTML = settings.html;
        grid.__source = settings.html;
    }
    const cards = [...grid.querySelectorAll('.pf-function-card')];
    for (const card of cards) {
        const chosen = card.dataset.functionKey===settings.selected || JSON.parse(card.dataset.variants || '[]').some(v=>v.key===settings.selected);
        card.classList.toggle('pf-function-selected', chosen);
        card.querySelector('button')?.setAttribute('aria-current', String(chosen));
    }
    const control = name => [...document.querySelectorAll('[data-testid=stSelectbox]')].find(e=>e.querySelector('label')?.innerText.trim()===name);
    const selected = (name, fallback) => {
        const text = control(name)?.querySelector('[role=combobox]')?.getAttribute('aria-label') || '';
        return text.startsWith('Selected ') ? text.slice(9, -(name.length+2)) : fallback || 'All';
    };
    const filter = () => {
        if (!grid.isConnected) { cleanup(); return; }
        const query = document.querySelector('input[aria-label="Find a plot or pipeline"],input[aria-label="Find a function or task"]')?.value ?? settings.query ?? '';
        const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
        const exact = query.toLowerCase().trim().replaceAll(' ', '_');
        const task = selected('Task', settings.task), access = selected('Access', settings.access);
        const matches = cards.filter(card => {
            const variants = JSON.parse(card.dataset.variants || '[]');
            if (variants.length) {
                const familyHit = words.every(word => (card.dataset.familySearch || '').includes(word));
                let options = variants.filter(v=>(familyHit || words.every(word=>v.search.includes(word))) && (task==='All' || v.task===task));
                options.sort((a,b)=>Number(!a.exact.includes(exact))-Number(!b.exact.includes(exact)));
                card.hidden = options.length===0;
                const remembered = settings.choices?.[card.dataset.home];
                const picked = query.trim() ? options[0] : options.find(v=>v.key===remembered) || options[0];
                const button = card.querySelector('button[data-function]');
                if (picked && button) button.dataset.function = picked.key;
                card.dataset.visibleActions = options.length;
                return options.length>0;
            }
            const hit = words.every(word => (card.dataset.search || card.innerText.toLowerCase()).includes(word)) &&
                (task==='All' || card.dataset.task===task) &&
                (access==='All' || (card.dataset.access==='form')===(access==='Browser forms'));
            card.hidden = !hit;
            return hit;
        });
        if (!settings.guided) {
            matches.sort((a,b) => Number(!(a.dataset.exact || a.dataset.functionKey).split('|').includes(exact))-Number(!(b.dataset.exact || b.dataset.functionKey).split('|').includes(exact)));
            // Reference cards rank exact names first; picture homes retain
            // their declared order across filtering and recovery.
            for (const card of matches) grid.appendChild(card);
        }
        parentElement.querySelector('.pf-no-functions').hidden = matches.length!==0;
        const count=parentElement.querySelector('.pf-function-count');
        if(count) count.textContent=settings.guided ? `${matches.length} choices · ${matches.reduce((sum,c)=>sum+Number(c.dataset.visibleActions||0),0)} actions` : '';
    };
    const edited = event => {
        if (!grid.isConnected) { cleanup(); return; }
        if (event.target.matches('input[aria-label="Find a function or task"],input[aria-label="Find a plot or pipeline"]')) filter();
    };
    document.addEventListener('input', edited);
    const observers = ['Task','Access'].map(name => {
        const observer = new MutationObserver(filter);
        const node = control(name);
        if (node) observer.observe(node, {subtree:true,childList:true,characterData:true});
        return observer;
    });
    const clicked = event => {
        const button = event.target.closest('button[data-function]');
        if (button && grid.contains(button)) {
            setTriggerValue('selected', {key: button.dataset.function, operation: button.dataset.operation});
        }
    };
    grid.addEventListener('click', clicked);
    function cleanup() {
        grid.removeEventListener('click', clicked);
        document.removeEventListener('input', edited);
        observers.forEach(observer => observer.disconnect());
    }
    window.pyflashFunctionCardsCleanup = cleanup;
    filter();
    return cleanup;
}
"""


SETUP_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 6h18M3 12h18M3 18h18"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="8" cy="18" r="2"/></svg>'

PICTURES = {
    'bars':'<path d="M16 48V29h12v19m12 0V13h12v35m12 0V21h12v27"/><g fill="white" stroke="currentColor"><circle cx="22" cy="25" r="3"/><circle cx="46" cy="10" r="3"/><circle cx="70" cy="17" r="3"/></g>',
    'scatter':'<path d="M14 44 77 10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="19" cy="40" r="3"/><circle cx="32" cy="27" r="3"/><circle cx="44" cy="34" r="3"/><circle cx="58" cy="16" r="3"/><circle cx="71" cy="12" r="3"/>',
    'histogram':'<path d="M13 48V40h10v8m1 0V27h10v21m1 0V12h10v36m1 0V17h10v31m1 0V32h10v16m1 0V42h10v6"/>',
    'paired':'<g fill="none" stroke="currentColor" stroke-width="2"><path d="m18 20 55 16m-55-6 55-8m-55 18 55-26"/></g><circle cx="18" cy="20" r="3"/><circle cx="73" cy="36" r="3"/><circle cx="18" cy="30" r="3"/><circle cx="73" cy="22" r="3"/>',
    'matrix': ''.join(f'<rect x="{15+c*15}" y="{8+r*12}" width="13" height="10" opacity="{.2+(r+c)%4*.2}"/>' for r in range(4) for c in range(4)),
    'forest':'<g stroke="currentColor" stroke-width="2"><path d="M24 14h49M17 27h40M34 40h44"/></g><circle cx="51" cy="14" r="4"/><circle cx="36" cy="27" r="4"/><circle cx="58" cy="40" r="4"/>',
    'contrast':'<g stroke="currentColor" fill="none" stroke-width="2"><path d="m18 14 26 16 27-12m-53 24 26-22 27 16"/></g><circle cx="18" cy="14" r="3"/><circle cx="44" cy="30" r="3"/><circle cx="71" cy="18" r="3"/>',
    'volcano':'<circle cx="17" cy="13" r="3"/><circle cx="25" cy="23" r="3"/><circle cx="35" cy="39" r="3"/><circle cx="44" cy="44" r="3"/><circle cx="55" cy="37" r="3"/><circle cx="65" cy="22" r="3"/><circle cx="75" cy="10" r="3"/>',
    'pie':'<circle cx="45" cy="28" r="21" opacity=".3"/><path d="M45 28V7a21 21 0 0 1 20 28Z"/>',
    'overlap':'<g fill="none" stroke="currentColor" stroke-width="2"><circle cx="35" cy="27" r="18"/><circle cx="55" cy="27" r="18"/></g>',
    'profile':'<g fill="none" stroke="currentColor"><path d="m45 5 30 22-11 25H26L15 27Z" opacity=".3"/><path d="m45 13 23 14-15 19H31L22 27Z" fill="currentColor" fill-opacity=".2" stroke-width="2"/></g>',
    'time':'<path d="M12 35C20 2 32 2 40 30S60 58 68 27 80 8 85 15" fill="none" stroke="currentColor" stroke-width="2"/>',
    'image':'<g fill="none" stroke="currentColor"><rect x="15" y="6" width="62" height="44"/><circle cx="34" cy="21" r="7"/><path d="m18 46 17-15 17 10 13-20 9 23"/></g>',
    'table':'<g fill="none" stroke="currentColor"><rect x="13" y="7" width="66" height="43"/><path d="M13 20h66M13 31h66M13 41h66M36 7v43M59 7v43"/></g>',
    'pipeline':'<g fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="17" width="18" height="23" rx="3"/><path d="M28 28h8m-4-4 4 4-4 4"/><rect x="40" y="17" width="18" height="23" rx="3"/><path d="M60 28h8m-4-4 4 4-4 4"/><rect x="72" y="17" width="12" height="23" rx="3"/></g>',
}


@lru_cache(maxsize=2)
def picture_markup(items):
    from PyFLASH.ui import function_workflows as workflows
    owners = {c.entry.action:c for c in items}
    cards = []
    for home in workflows.checked_homes():
        variants=[]
        for action in home.actions:
            c=owners[action]
            search=' '.join([workflows.title(c), c.task, c.entry.key, c.entry.documentation, *c.entry.aliases,
                             *(f.label+' '+f.name+' '+f.parameter.description for f in c.fields)]).casefold()
            variants.append({'key':c.entry.key, 'task':c.task, 'search':search,
                             'exact':[action, c.entry.name.casefold(), c.entry.key.casefold()]})
        key=escape(owners[home.actions[0]].entry.key, quote=True)
        thumbnail=f'<svg viewBox="0 0 90 56" aria-hidden="true" fill="currentColor">{PICTURES[home.picture]}</svg>'
        cards.append(f'<article class="pf-function-card pf-picture-card" data-home="{home.key}" data-function-key="{key}" data-family-search="{escape((home.title+" "+home.description).casefold(),quote=True)}" data-variants="{escape(json.dumps(variants),quote=True)}"><button type="button" data-function="{key}" data-operation="select" title="Choose {escape(home.title.lower(),quote=True)}; computation starts only with Run">{thumbnail}<span><small>{"Pipeline" if home.pipeline else "Plot"}</small><strong>{escape(home.title)}</strong><span class="pf-picture-description">{escape(home.description)}</span></span></button></article>')
    return ''.join(cards)


def markup(items, selected=None):
    """Escape source-derived text; all matching cards exist in the same grid."""
    cards = []
    for entry in items:
        contract = entry if hasattr(entry, 'entry') else None
        item = contract.entry if contract else entry
        name = item.action or item.name
        title = escape(contract.title if contract else name.replace('_', ' '))
        key = escape(item.key, quote=True)
        summary = item.summary
        summary = escape(summary if len(summary) <= 220 else summary[:217] + '…')
        details = f'<button type="button" data-function="{key}" data-operation="details" title="Inspect signature, parameter defaults, help and Python call template" aria-label="Details for {escape(name, quote=True)}"><span aria-hidden="true">ⓘ</span> Details</button>'
        setup = (f'<button type="button" data-function="{key}" data-operation="setup" title="Open {escape(item.page.capitalize())} with this action selected; processing starts only when you run it there" aria-label="Set up {escape(name, quote=True)}">{SETUP_ICON} Set up</button>' if item.action else '')
        if contract:
            status = 'Browser form' if contract.access == 'form' else 'Python reference'
            operation = 'Use function' if contract.access == 'form' else 'View reference'
            button = f'<button type="button" data-function="{key}" data-operation="select" title="Open inputs and results here; analysis starts only with Run" aria-label="{operation}: {title}">{SETUP_ICON} {operation}</button>'
            chosen = ' pf-function-selected' if item.key == selected else ''
            search = " ".join([contract.title, contract.task, item.key, item.documentation, *item.aliases,
                               *(f.label + " " + f.name + " " + f.parameter.description for f in contract.fields)]).casefold()
            exact = "|".join([item.action or "", item.name.casefold(), item.key.casefold()])
            cards.append(f'<article class="pf-function-card{chosen}" data-function-key="{key}" data-search="{escape(search, quote=True)}" data-exact="{escape(exact, quote=True)}" data-task="{escape(contract.task, quote=True)}" data-access="{contract.access}"><small>{escape(contract.task)} · {status}</small><h3>{title}</h3><p>{summary}</p><div class="pf-function-actions">{button}</div></article>')
        else:
            cards.append(f'<article class="pf-function-card" data-function-key="{key}"><small>{escape(item.kind)} · {escape(item.module)}</small><h3>{title}</h3><p>{summary}</p><div class="pf-function-actions">{details}{setup}</div></article>')
    return ''.join(cards)


@lru_cache(maxsize=1)
def _component():
    import streamlit.components.v2 as components
    return components.component('pyflash_function_cards', html='<div class="pf-function-grid"></div><p class="pf-function-count" aria-live="polite"></p><p class="pf-no-functions" hidden>No functions match. Clear the search or choose All in the filters.</p>',
                                css=FUNCTION_CARDS_CSS, js=JS, isolate_styles=False)


@lru_cache(maxsize=2)
def _cached_markup(items):
    return markup(items)


def render(items, selected=None, *, all_items=None, query="", task="All", access="All", guided=False, choices=None, on_select=None):
    """Return one triggered selection, without hundreds of widget states."""
    source=tuple(items if all_items is None else all_items)
    data = {"html": picture_markup(source) if guided else _cached_markup(source), "selected":selected,
            "query":query, "task":task, "access":access, "guided":guided, "choices":choices or {}}
    def changed():
        if on_select is not None:
            import streamlit as st
            event = st.session_state['function_cards'].selected
            resolved = selection([c.entry if hasattr(c, 'entry') else c for c in source], event)
            if resolved:
                on_select(*resolved)
    result = _component()(data=data, key='function_cards', on_selected_change=changed)
    return result.selected


def selection(items, event):
    """Resolve a card click to an actual entry; never evaluate browser input."""
    if not isinstance(event, dict) or event.get('operation') not in {'details', 'setup', 'select'}:
        return None
    item = next((item for item in items if item.key == event.get('key')), None)
    if item is None or (event['operation'] == 'setup' and not item.action):
        return None
    return item, event['operation']
