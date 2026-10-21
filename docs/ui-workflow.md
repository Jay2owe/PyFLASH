# PyFLASH workflow interface

## Product contract

Build a local interface for Jamie and colleagues to open saved analyses, set up
FLASH experiment folders, define groups, process deliberately, inspect measurements,
make publication figures and export results. This extends the existing Streamlit
application and its package APIs; no new package, publication or deployment.
The packaged simulated table (12 subjects; two measurements; under 1 KB) is the
first-launch dataset. It is the same table used by `demo/run_demo.py`, whose frozen
numerical expectations remain authoritative. No microscopy images are simulated.

Accepted: redesign the whole workflow; retain package-owned analysis and exports.
Open: visual acceptance and representative private-data performance.
Target: 1440 × 900 desktop; supported narrow review at 800 px.
Budgets: cold load until both exploration plots draw ≤5 s; changing the selected
subject until both plots redraw ≤500 ms. Measure in the browser, including server
work. Large real datasets need separate measurements.

## Capability map

| Task | Owning operation | Canonical home | Controls / selection | Cost |
|---|---|---|---|---|
| Open work | load_state / from_dataframe | Workspace | file path, CSV columns | Explicit load |
| Select inputs | discover_experiments | Folders | root, names, threshold | Folder validation |
| Define comparisons | ConditionBuilder | Groups | factors, colours, comparisons | Live preview |
| Process | create_batch | Process | run, cache, image import | Explicit slow action |
| Inspect values | summary_table | Explore | region, metric, groups, subject | Automatic preview |
| Produce figures | PLOT_REGISTRY | Figures | registered type, parameters, appearance | Explicit run |
| Inspect microscopy | image_table / plot_images | Images | markers, subjects, regions | Explicit image load |
| Save deliverables | export_all_excel / save_state | Export | workbook filters, destination | Explicit write |

```text
Workspace → Folders → Groups → Process
    └────────────────────────────┴→ Explore → Figures / Images → Export
```

Exploration holds one distribution view and one relationship view, with shared
subject highlighting and independent measurement choices. Scientific plots remain
package-rendered on the Figures page. Interface charts are web visualisations;
saved figures leave through PyFLASH.utils.save_fig and ReproFig.

The adjacent exploration views use one shared data-rectangle height and equal
horizontal-axis space. Width adapts to the window; labels and legends no longer
change the height of either plot's drawing area. Browser checks compare the
actual top and bottom edges, including when the measurements differ.
The alignment check is now part of `scripts/check_ui_workflow.py`, so future
changes fail if the two drawing areas differ vertically by over half a pixel.
The final browser check measured zero difference at both edges for the default
views, different measurements, dark mode and an 800-pixel window. Axis titles
and legend rows were also inspected in the real browser screenshot.

Common example (existing APIs, unchanged):

```python
import pandas as pd
from PyFLASH import from_dataframe
from PyFLASH.ui import services
experiment = from_dataframe(pd.read_csv("demo/data/summary.csv"),
                            group_col="Condition", subject_col="AnimalName")
table = services.summary_table(experiment, display=False)
print(table.groupby("Condition")["Signal_MeanIntensity"].mean())
```

## Implementation boundary

The first redesign reuses real processing, image and workbook APIs. It adds shared
navigation, live exploration, CSV import, recoverable UI preferences and replayable
figure recipes. Processing, figures, image panels, workbook exports, CSV
preparation and saves now run in one bounded process worker, with durable status
and logs. Existing plots and navigation stay usable during work. New processing
is opened explicitly; stale dataset results cannot replace current views.
Unattended processing queues, interruption/resume, and full scientific-data
autosave are separate backend work; recovery stores setup and presentation choices,
never silently resaves a private analysis. Existing agent control already dispatches
the plot registry; no second agent backend is introduced.

## Feedback log

- 2026-10-01, requested interface: “lets make a ui for this. $software-development”
- 2026-10-01, workflow scope: “Redesign the whole workflow”
- 2026-10-01, ongoing build: “continue”
- 2026-10-01, redesigned interface at `http://127.0.0.1:8511`: “very nice, make sure plots align vertically”
- 2026-10-01, real-data workflow: “lets load a real dataset”
- 2026-10-01, responsiveness: “its very slow and once processing starts it blocks everything else. we need to do a $performance-engineering pass”
- 2026-10-01, investigation scope: “i wont tell you. be thorough and fix”

## Verification (2026-10-01)

The frozen demo, package adapter checks, recipe replay and recovery checks pass.
The browser review exercises every route, shared subject selection by dropdown
and plotted point, independent metrics, keyboard menu search, both themes,
800-pixel resizing and reopening the selected subject. It saves screenshots
and actual click-to-both-plots timings under the chosen local review folder.
Run it with `python scripts/check_ui_workflow.py --output <local-review-folder>`.

129 focused checks pass (128 in the combined run, plus the new real save/reopen
check; all nine workspace checks pass in the final focused run).
Focused checks: `tests/test_ui_services.py`, `test_ui_conditions.py`,
`test_ui_images.py`, `test_ui_plots.py` and `test_ui_workspace.py`.
The README example and frozen `demo/run_demo.py` pass. The documentation builds
with `mkdocs build --strict`. No private microscopy batch was processed.

Layout audit, 1440 ? 900, two of two views visible, 20 controls:

| Check | Measured | Limit | Result |
|---|---|---|---|
| Image/plot area of first screen | 68% | ?67% | pass |
| Largest gap between neighbouring views | 8 px | ?8 px | pass |
| Worst dead space inside a card | 32% | ?25% | FAIL* |
| Pixels above the first view | 80.1 px | ?120 px | pass |
| Image letterboxing | 0% | ?10% | pass |
| Overlapping text labels | 0 | 0 | pass |
| SVG labels crossing their canvas edge | 0 | 0 | pass |
| Controls without a tooltip | 0 | 0 | pass |

*The generic audit climbs to the full Streamlit application background and
counts the sidebar and heading as card padding. Neither plot has a surrounding
card. The raw failure is retained; this is a functional redesign for review,
not a claim of accepted visual alignment.

Latest browser measurement: 8.258 seconds to both first plots (target ?5 seconds);
0.600 seconds median actual click-to-both-plots redraw across five subject
switches (target ?0.500 seconds). Earlier rounds measured 0.424 seconds, so the
interaction budget is not consistently met. Startup remains over target. A profile
attributes about 2 seconds to package imports, mostly pandas and SciPy through
marker classes. This round avoids changing the analysis package's import
surface. These were measurements from the initial redesign; the subsequent
performance pass is documented below. Mid-operation resume remains unavailable.
Explicit Save analysis retains the existing package serializer; only
project setup and presentation recovery use the new atomic writer.

Skill tune proposal: `/skill-tuner learn` ? record the tested
`scripts/check_ui_workflow.py` as the reusable Streamlit browser-review route,
including virtualised menu search and actual click-to-render timing. No skill
files were changed.

Additional skill tune proposal from the alignment feedback:
`/skill-tuner software-development` - require compared plots to align their
actual data rectangles and axis baselines, rather than checking only outer
widget bounds. The browser geometry check above is the tested example.

## Real saved-analysis compatibility (2026-10-01)

Opened the existing local microscopy batch in the actual browser: 42 summary
rows across nine groups. Older tables store numeric values alongside missing
and exclusion tags in object columns. Exploration now normalises a cached
presentation copy, sends only selected scalar measurements to the plots, and
uses safe internal field names for columns containing dots. Original tags and
values remain in the displayed/downloadable table and in the saved analysis.
Nested metadata is rendered as text when displayed, avoiding mixed-list table
serialisation errors. Figures reuse the same measurement catalogue.

The two real-data plot areas have identical top and bottom edges (0 px
difference). No scientific processing or figure export was run. Two regression
checks cover source preservation, missing tags, nested metadata, safe fields and
cache invalidation. The existing workflow replay check also passes using the
Windows Python launcher for the local Store Python installation.

Alignment feedback is filed as skill-tuner case 0088; the implemented browser
geometry check enforces the lesson. No shared skill file was changed.

## Whole-workflow performance pass

See [the measured performance report](ui-performance.md) for the contract,
profiles, paired comparisons, browser checks and remaining limits. Ten paired
real-data trials preserve every value and measurement choice exactly; median
preparation falls from 51.07 to 1.99 seconds. Both required timing cohorts pass
the uncertainty-aware relative gate. A single source cache preserves read-only
measurements while keeping edited selections separate between sessions, and
invalidates for changed files, settings or relevant code.

The real browser remains usable during bounded CPU work followed by the owning
cached factory call. Both plot rectangles stay aligned exactly. Cold opening is
9.22 seconds; subsequent openings are 2.53–2.99 seconds. Linked redraw is around
half a second, including during processing. Cold startup still exceeds the
five-second target, and some redraw samples narrowly exceed 500 ms.

159 focused checks pass. Actual workers verify CSV bytes, save/reopen and an
unsaved registered figure on the frozen example. Large private image rendering
and raw experiment reprocessing were not run. Skill-tuner case 0096 records the
 responsiveness correction; a tested functional-report validator is registered
with the software-development skill. No shared skill wording changed.

## Opt-in functions catalogue (2026-10-01)

User request, verbatim: "look at the pymicroglia functions page that shows all
the functions that can be accessed. we should add the same here and add it as
a reference in the software skill but one that is specficially evoked and not
just always used"

The actual running PyMicroglia All methods page was inspected: 138 searchable
cards with live setup links, generated from its action/figure inventory.
PyFLASH now has a Functions page with searchable cards, access/module filters,
one continuous list, parameter/help dialogs, Python call templates and setup links to
the existing Figures and Images controls. Catalogue scope is explicit: all 46
registered actions and 404 additional public core functions, classes and
methods; private helpers and browser internals are excluded. Aliases share
the canonical source definition. Reading or searching starts no analysis.

The catalogue compiles declarations and literal help rather than analysis
bodies, importing no rendering engines. First preparation measured 0.63 seconds,
cached preparation 0.005 seconds. All matching cards appear together on one
scrollable page. Inherited constructors are marked unspecified;
downloaded call templates require the user's inputs and are labelled accordingly.

25 focused catalogue/workspace checks pass, including source/registry fidelity,
aliases, invalidation, no-dataset opening and reference dialogs.
Actual browser checks cover search, details, setup into the mean-bars recipe,
Python access, empty-search recovery, light/dark themes and an 800-pixel viewport
without horizontal overflow. No analysis or saved figure was produced.

The software-development skill's existing experience index routes to an
optional functions-page reference only for an explicit functions-page request,
including `$software-development functions-page`. The main skill instructions
are unchanged; this is not a default step for future apps. No skill tune needed.

Correction (2026-10-02), verbatim: "dont have pages it should all just be shown
on one page"

The numbered catalogue pages have been removed. All matching function cards
appear together, with search and filters retained. The optional functions-page
reference now specifies one continuous catalogue; its explicit invocation
requirement and the main software-development skill remain unchanged.

All cards share one component and click handler, avoiding hundreds of separate
Streamlit widget states. Details and setup use the existing Python handlers.
The UI extra now requires the tested Streamlit 1.58 component API. Seven focused
checks pass; actual browser checks verify all 450 entries together, no Page
selector, details/setup, empty-search recovery, both themes and an 800-pixel
viewport. Search measured 0.115 seconds in that browser check. Skill-tuner case
0106 records the correction; no main skill wording change was needed.

### Function usability plan (2026-10-02)

Feedback, verbatim: "it needs to be much easier to use each function, its very
confusing right now. lets make a plan for this. look online for how others do
this kind of thing"

The proposed plan is [ui-function-usability-plan.md](ui-function-usability-plan.md).
It uses official QGIS, jamovi, Galaxy and napari/magicgui examples to propose
one continuous catalogue with an in-place input form and results, actual dataset
selectors and ordinary controls for structured inputs. Start with the live
capability audit and three complete workflows; preserve all entries, package
defaults, existing background jobs and figure provenance. The user subsequently
authorized implementation with "go for it" and "continue".

### In-place function workbench (2026-10-02)

All 450 entries remain together. Search and task/access filters choose an entry;
its labelled inputs and results appear beside the list without changing pages.
All 46 registered actions and 14 additional public helpers have forms. The other
390 entries explicitly explain their Python access. Figures and Images are
shortcuts to the same editor, and saved figure specifications remain available.

Dataset selectors provide actual measurements, metadata, groups, markers and
object attributes. Structured arguments use row editors. Advanced choices
preserve omitted defaults, explicit None and empty lists. Drafts persist per
entry; completed results restore their settings. Legacy JSON recipes migrate or
offer a recoverable download. Missing images/fitted results explain prerequisites.
Only Run starts a background worker; editing and search stay usable during it.

The real browser completed group means, relationships and histograms on the
unchanged 42-subject dataset. Comparison means and nonmissing subject counts
match the source. Results remain visible and downloadable, with the actual
replay script and complete result tables. The owning scientific code and
package figure writer remain responsible for analysis and exports.

106 focused checks and 36 separately run figure-page checks pass. Real browser
checks include all entries, task/access filters, missing inputs, empty search,
both themes and an 800-pixel viewport. Most client search samples were 3-33 ms,
with one 895-ms sample; form opening was 0.51-1.49 seconds, still above the
500-ms target. See the implementation/evidence section of
[ui-function-usability-plan.md](ui-function-usability-plan.md) for measured limits.

The existing optional functions-page software-development reference was updated
with this verified route. It is read only on an explicit catalogue request;
main skill instructions are unchanged. Skill-tuner case 0110 is updated.

### Plotting and pipeline scope (2026-10-03)

Feedback, verbatim:

> it should only show the plotting or pipeline functions. other functions we can put elsewhere, like the excel export function or adjusting the house aesthetic for example

Functions now shows the 46 registered plotting and pipeline actions on one
continuous page. Supporting helpers have moved to their relevant sections:
Excel/CSV/save-analysis controls and export references in Export; House aesthetic
and appearance references in Workspace; other package references in a collapsed
Workspace section. Main-list search covers its scoped actions, and old helper
selections/task filters recover to a valid analysis form.

House aesthetic saves defaults for new figure/pipeline jobs. Per-function
appearance overrides take priority. The combined values are recorded in the
job and replay script, while existing results retain their original settings.
The source inventory and all supporting adapters remain available; this changes
where functions are shown, not their scientific implementation.

Real-browser checks on the loaded dataset pass: 46 analysis entries, correct
supporting sections, search recovery, both themes and 800-pixel layout. An
existing pipeline job continued during the review; no new analysis was run.
The completed receipt and measured limits are in the current-scope section of
[ui-function-usability-plan.md](ui-function-usability-plan.md).
