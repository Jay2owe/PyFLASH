"""Shared interface tokens; native Streamlit colours follow the chosen OS theme."""

PALETTE = ("#4878A8", "#d98a17", "#0e8f8f", "#c0392b", "#805ba5", "#737373")
FUNCTION_CARDS_CSS = """
.pf-function-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: .5rem; }
.pf-function-card[hidden], .pf-no-functions[hidden] { display: none !important; }
.pf-function-card { border: 1px solid var(--st-border-color); border-radius: .35rem; padding: .65rem; min-width: 0; color: var(--st-text-color); background: var(--st-background-color); }
.pf-function-selected { border-color: var(--st-primary-color); }
.pf-function-card small { opacity: .65; overflow-wrap: anywhere; }
.pf-function-card h3 { font-size: 1.05rem; font-weight: 600; margin: .55rem 0 0; overflow-wrap: anywhere; }
.pf-function-card p { margin: .15rem 0 .6rem; overflow-wrap: anywhere; }
.pf-function-card p { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.pf-function-actions { display: flex; gap: .5rem; flex-wrap: wrap; }
.pf-function-actions button { display: inline-flex; align-items: center; gap: .3rem; color: inherit; font: inherit; font-size: .875rem; background: transparent; border: 1px solid var(--st-border-color); border-radius: .35rem; padding: .4rem .7rem; cursor: pointer; }
.pf-function-actions button:hover { border-color: var(--st-primary-color); color: var(--st-primary-color); }
.pf-function-actions button:focus-visible { outline: 2px solid var(--st-primary-color); outline-offset: 2px; }
.pf-picture-card { padding: 0; }
.pf-picture-card > button { display:flex; align-items:center; gap:.5rem; width:100%; text-align:left; padding:.5rem; border:0; border-radius:inherit; background:transparent; color:inherit; cursor:pointer; font:inherit; }
.pf-picture-card > button:hover { background:var(--st-secondary-background-color); }
.pf-picture-card > button:focus-visible { outline:2px solid var(--st-primary-color); outline-offset:2px; }
.pf-picture-card svg { width:4rem; height:3rem; flex-shrink:0; color:var(--st-primary-color); }
.pf-picture-card strong { display:block; font-size:.86rem; line-height:1.3; }
.pf-picture-card small { display:block; font-size:.68rem; }
.pf-picture-description { display:block; font-size:.72rem; opacity:.8; line-height:1.3; margin-top:.12rem; }
.pf-function-count { font-size:.75rem; margin:.4rem 0 0; opacity:.75; }
@media (max-width: 850px) { .pf-function-grid { grid-template-columns: minmax(0, 1fr); } }
"""
CSS = """
<style>
:root { --pf-gap: .5rem; --pf-radius: .35rem; }
/* The application shares the native body background; it is not a boxed card. */
.stApp { background-color: inherit !important; }
[data-testid="stMainBlockContainer"] { padding: 1.2rem 1.5rem 2rem; max-width: 100%; }
[data-testid="stHeader"] { height: 1rem !important; background: transparent !important; }
/* The empty fixed toolbar must not intercept controls underneath it. */
[data-testid="stHeader"], [data-testid="stToolbar"] { pointer-events: none; }
[data-testid="stToolbar"] button, [data-testid="stHeader"] button { pointer-events: auto; }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stSidebar"] { width: 18rem !important; min-width: 18rem !important; }
[data-testid="stSidebarContent"] { padding-top: .5rem; }
[data-testid="stVerticalBlock"] { gap: var(--pf-gap); }
[data-testid="stHorizontalBlock"] { gap: var(--pf-gap); }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .65rem; }
h1 { font-size: 1.75rem !important; padding: 0 0 .45rem !important; }
h2 { font-size: 1.3rem !important; padding: .25rem 0 !important; }
h3 { font-size: 1.05rem !important; padding: .25rem 0 !important; }
[data-testid="stSidebar"] h3 { line-height: 1.4 !important; margin-bottom: .15rem !important; }
[data-testid="stSidebar"] [data-testid="stPageLink"] p { white-space:normal; overflow:visible; text-overflow:clip; }
[data-testid="stMetricValue"] { font-size: 1.4rem; }
[data-testid="stVegaLiteChart"] { overflow: hidden; }
[data-testid="stVegaLiteChart"] svg { overflow: visible; }
[data-testid="stExpander"] { border-radius: var(--pf-radius); }
/* Closed disclosure contents are absent from layout and accessibility bounds. */
[data-testid="stExpander"] details:not([open]) > div { display: none; }
@media (max-width: 850px) {
  [data-testid="stSidebar"] { width: 11rem !important; min-width: 11rem !important; }
  [data-testid="stSidebarContent"] { padding-left: 0 !important; padding-right: 0 !important; }
  [data-testid="stSidebarUserContent"] { width: 100% !important; }
  [data-testid="stSidebarUserContent"] { padding-left: .5rem !important; padding-right: .5rem !important; }
  [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  [data-testid="stSidebar"] [data-testid="stColumn"] { width: 100%; flex: 1 1 100%; min-width: 0; }
  [data-testid="stMainBlockContainer"] { padding: 1rem .65rem; }
  [data-testid="stHorizontalBlock"]:has([data-testid="stVegaLiteChart"]) { flex-wrap: wrap; }
  [data-testid="stHorizontalBlock"]:has([data-testid="stVegaLiteChart"]) > [data-testid="stColumn"] { width: 100%; flex: 1 1 100%; min-width: 0; }
  [data-testid="stHorizontalBlock"]:has([data-testid="stImage"]) { flex-wrap: wrap; }
  [data-testid="stHorizontalBlock"]:has([data-testid="stImage"]) > [data-testid="stColumn"] { width: 100%; flex: 1 1 100%; min-width: 0; }
  [data-testid="stHorizontalBlock"]:has(#function-list) { flex-wrap: wrap; }
  [data-testid="stHorizontalBlock"]:has(#function-list) > [data-testid="stColumn"] { width: 100%; flex: 1 1 100%; min-width: 0; }
  [data-testid="stHorizontalBlock"]:has(#function-inputs) { flex-wrap:wrap; }
  [data-testid="stHorizontalBlock"]:has(#function-inputs) > [data-testid="stColumn"] { width:100%; flex:1 1 100%; min-width:0; }
  .st-key-function_catalogue { height: 260px !important; max-height: 260px !important; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-function_catalogue) { height:260px !important; max-height:260px !important; }
}
</style>
"""
