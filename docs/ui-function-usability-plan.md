# Make functions straightforward to use

Current decision (2026-10-04): the user rejects the implemented forms as confusing.
The [full workflow rework plan](ui-preset-workflow-rework-plan.md) supersedes this
document's interaction recommendation. Retain the checks below as execution
evidence; they do not establish usability or acceptance of the interface.

Date: 2026-10-02; scope revised 2026-10-03. Status: implementation authorized by "go for it" and
"continue"; forms and three real-data workflows verified. The main catalogue now
contains only registered plotting and pipeline actions; supporting functions have
separate homes in Export and Workspace. The 500-ms form
switching target remains unmet. The sections below retain the researched plan;
the implementation record at the end states what was delivered.

## Recommendation

Keep one continuous Functions workbench. Selecting a function opens its labelled
input form and results in that workbench. Carry the loaded dataset into the form,
offer actual measurements and groups, and keep computation behind an explicit Run
button. Keep all public entries accessible, with accurate execution status.

Think of a tool rack beside a workbench: the rack helps choose a tool, while the
bench provides the inputs and shows what the tool produces.

Start with a working example of three different forms before expanding coverage.
The first round should support group means, relationships between measurements,
and measurement distributions. These exercise shared selections, paired inputs,
and required parameters that the current generic editor misses.

## What already works, and where use breaks down

The existing catalogue finds all 450 entries, searches descriptions and arguments,
shows accurate source signatures, and connects 46 registered actions to existing
controls. Background execution, cached measurement choices and figure replay
scripts already exist. Preserve these foundations.

The current interaction asks users to understand the package before doing a task:

- Entry names and module filters describe Python organization rather than intent.
- Details presents a signature and parameter table, rather than editable inputs.
- Set up leaves the catalogue for Figures or Images; the chosen task loses its
  surrounding explanation and the user must learn another screen.
- Figures provides dedicated measurement controls for only a few actions. Other
  settings require JSON, the structured text format used to pass Python options.
- Required histogram inputs such as the marker and measured attribute do not have
  dedicated controls. More complex actions may need fitted results or predictors
  that a generic measurement picker cannot provide.
- Most of the 404 additional public functions, classes and methods have reference
  information and an unfinished Python call template, with no browser input form.

Evidence inspected: `PyFLASH/ui/pages/9_functions.py`,
`PyFLASH/ui/pages/6_plots.py`, `PyFLASH/ui/catalogue.py`,
`PyFLASH/ui/workspace.py`, `PyFLASH/spec.py` and `PyFLASH/param_docs.py`.
Counts describe the current source; future checks must derive them dynamically.

## Online examples and the patterns to adopt

The following are documented behaviors, not evidence that our proposed interface
has already passed a usability study. The adaptation column is a design proposal.

| Example | Documented behavior | Proposed adaptation here |
| --- | --- | --- |
| QGIS, a geographic analysis application | Searchable algorithms, recent/favourite tools, consistent parameter dialogs, choices drawn from loaded layers and fields, help and equivalent commands | A consistent function editor, inputs drawn from the open dataset, recent actions, and expandable code |
| jamovi, a statistical analysis application | Selecting an analysis opens its options alongside results; variable assignment and options remain editable; an earlier result reopens its settings | Keep selected function, form and result together; reopening a result restores its exact recipe |
| Galaxy, a scientific workflow platform | Declared input types provide compatible dataset selectors, labels, per-field help, numeric validation and conditional parameter sections | Dataset-aware fields; show dependent inputs only when applicable; explain invalid inputs beside the field |
| napari, an image viewer, with magicgui, a function-to-form library | Function annotations can provide image-layer selectors and option menus; declared return types can put results into the viewer | Generate routine controls from the owning function, then add explicit scientific input roles and result handlers |

Sources, accessed 2026-10-02:

- [QGIS processing toolbox and algorithm dialogs](https://doc.qgis.org/3.44/en/docs/user_manual/processing/toolbox.html).
- [jamovi analysis options and results](https://docs.jamovi.org/usermanual/um_3_analyses.html)
  and [equivalent analysis code](https://docs.jamovi.org/usermanual/um_6_jamovi_and_R.html).
- [Galaxy declared tool inputs](https://docs.galaxyproject.org/en/release_26.1/dev/user_defined_tools_authoring.html).
- [napari image arithmetic form example](https://pyapp-kit.github.io/magicgui/generated_examples/napari/napari_img_math/).

Use these interaction patterns within the existing web application. A switch to
another application framework is not needed to implement them. In particular,
do not copy automatic analysis on every option change: that would recreate the
processing freeze. Editing a form must remain separate from starting analysis.

## Proposed one-page interaction

```text
Functions  | loaded dataset / region | search | task filter | jump links

Continuous function list             Selected function: Compare group means
  Plain-language titles              Measurements [search and select]
  Purpose and result type            Groups       [actual dataset groups]
  Ready / missing inputs / Python    Region       [current selection]
  Use function                       [Advanced analysis] [Appearance]
                                     Run comparison

                                     Result / progress / field errors
                                     [Edit inputs] [Export] [Code and run record]
```

At 1440 x 900, use a compact list beside the selected editor/result area. At
800 pixels wide, stack the same elements, with a jump link to the selected form
and back to the selected entry. Preserve search, draft inputs and list position.
One selected form is mounted at a time; keep all matching entries in the same
continuous catalogue. There are no numbered pages, separate function routes or
mandatory detail dialogs.

- Group entries by tasks such as Compare groups, Explore measurements, Examine
  relationships, Fit models, Inspect images, and Import/export. Derive the final
  grouping from the capability audit. Module and function names remain available
  as technical filters and searchable identifiers.
- Default to the full catalogue. Filters and jump links help navigate it; they do
  not silently restrict coverage to popular or currently runnable functions.
- Use one primary action, **Use function**, on browser-supported entries. Opening
  it reveals the form immediately. Keep source signatures and full help behind
  a Reference disclosure in that same editor.
- Give every entry a short explanation of its input and output. Explain missing
  prerequisites with a specific action, such as selecting a fitted result.
- Offer recent functions and saved recipes as shortcuts to the original entries.
  Keep the underlying list order stable and avoid duplicate forms.
- For migrated actions, existing Figures/Images links should open the same
  canonical editor/result location. Share the actual renderer and execution path;
  do not build a second independent plot interface.

## Make the inputs understandable

The source signature remains authoritative for argument names and defaults.
`PyFLASH/param_docs.py`, the shared parameter descriptions, remains authoritative
for existing meanings, units and aliases. Add a small presentation description
only for what the source cannot express: task title, input role, widget choice,
conditional visibility, prerequisites and result type.

Do not infer that every string is free text or every array is a list of
measurements. A fitted-model table, subject identifiers and a list of predictors
need different selectors even if their Python types look similar.

- Supply the loaded analysis object automatically. Select dataset-derived inputs
  from real compatible measurements, markers, groups, subjects and regions.
- Retain a user's previous choices only when they are still compatible with the
  current dataset. Do not silently select the first or last measurement.
- Use labelled numbers, choices, checkboxes, multi-selects and editable rows for
  structured parameters. Normal and advanced workflows require no JSON or Python
  syntax. An optional developer editor may remain available separately.
- Keep the minimum meaningful inputs visible. Whether an argument is optional in
  Python does not determine whether it is important to understanding the analysis.
- Keep defaults from the owning callable. Distinguish an omitted option, an
  explicit None and an empty value when they have different scientific meanings.
- Put less frequent analysis options under Advanced, separate from Appearance.
  Show changed settings and provide a reset to package defaults.
- Add short help beside difficult inputs, with units and the consequences of
  changing them. For example, pooling groups and running one analysis per group
  must be separate explicit choices, because they change the analyzed data.
- Validate required inputs, compatibility and supported relationships before
  submission. Identify the offending field and retain the user's draft on error.
- Where supported by the owning action, show the selected measurements, groups,
  observation counts, exclusions, transformations and sampling unit before Run.
  Keep consequential statistical settings visible; do not guess a test from a
  plain-language question or silently change normalization.

## Coverage and actual execution

All 450 entries remain discoverable. Start execution improvements with the 46
registered actions, then audit the other 404 public definitions and map each to
its appropriate use. A public class or utility method is not automatically an
independent analysis command.

Every entry needs a recorded outcome: a browser form; an existing context-bound
operation such as export; a prerequisite that another step supplies; or Python
reference with a concrete unsupported-input reason. Meaningful public analysis
functions outside the current registry should receive adapters and forms when
their input/output contracts can be supported. Do not leave these as reference
entries solely because they were not already registered.

Do not call arbitrary names from a card or use unrestricted Python evaluation.
Execution must use validated, explicit package adapters. Methods need an actual
compatible instance; returned objects need a result handler. Mutating operations
must identify what they change and use the existing reversible workspace-edit
path where possible. Read-only analysis must preserve source data.

Initial capability-to-view map, proposed:

| User task | Owning action | Inputs and local controls | One result location | Shared selection / cost |
| --- | --- | --- | --- | --- |
| Compare group means | `mean_bars` (plots group means and individual values) | Measurements, groups, documented statistical choices | Active form's figure area | Dataset/region; explicit job |
| Relate two measurements | `regressions` (plots relationships) | Horizontal and vertical measurements, grouping, normalization | Same figure area, relationship geometry | Dataset/region; explicit job |
| Inspect a distribution | `histograms` (plots measurement distributions) | Marker, measured attribute, grouping, bin settings | Same figure area, distribution geometry | Dataset/region; explicit job |
| View an existing fit | `model_result_matrix` (plots a saved model-result table) | Compatible fitted result, statistic and ordering | Same figure area, matrix geometry | Selected saved result; no hidden refit |
| Fit adjusted models | `linear_model_pipeline` (fits models and produces adjusted summaries) | Outcomes, predictors, categorical references, sampling-unit fields | Result summary plus existing output viewer | Dataset/region; explicit long job |
| Inspect representative images | `representative_images` (assembles selected images) | Available subjects, markers and actual image source | Existing image renderer in the active result area | Dataset/subject; explicit loading job |

## Implementation sequence and completion gates

### 1. Audit capabilities and inputs

Produce a machine-checkable coverage map for the live registry and public
catalogue. For each entry record task, callable owner, input roles, required
choices, defaults source, output type, prerequisites, mutation and execution cost.
Record unbound parameters explicitly. No unsupported option may disappear behind
a promise that introspection will generate everything.

Completion: every catalogue entry is accounted for; all 46 registered actions
have identified inputs and result handlers, including delegated image arguments
and arguments whose requiredness depends on other choices. Agree the task groups
and plain-language labels against this evidence.

### 2. Prove one complete interaction

Build the shared editor and the group-means, relationship and histogram forms.
Use the existing loaded dataset and a deterministic small example for regression
checks. Connect forms to real package execution and the existing background
worker; reuse result display and export facilities. Replace the current detail
then setup then page-switch interaction for these actions.

Completion: choose an action, provide compatible inputs and Run without opening
another page or reading a function signature. A result can restore its recipe.
Invalid input is corrected beside its field. Switching actions preserves drafts.

### 3. Extend through distinct input/output families

Add fitted-result selection, image-source selection and pipeline forms before
rolling the shared controls across all remaining registered actions. Provide
conditional fields and row editors for lists, mappings and grouped settings.
Keep complex actions explicit about inputs, transformations and outputs.

Completion: each of the 46 actions has a complete supported form or a specific
missing-prerequisite state. No ordinary argument is available only through JSON.
Every visible run control has a tested adapter and accurate result ownership.

### 4. Cover public helpers and preserve recipes

Use the audit to add supported public operations beyond the registered actions.
Bind existing figures, fitted tables and experiment objects through selectors.
Provide context-bound export/edit actions where those are the meaningful use.
Give remaining reference entries understandable input/output explanations and
usable examples, with their execution limitation stated precisely.

Save form drafts and recipes with stable entry/parameter identifiers, compatible
with old project files and overrides. Preserve omitted values, explicit None,
empty values, tuples and ordered lists without changing package semantics.
An executable replay must record actual inputs and settings; a call template
must never be labelled a replay.

Completion: each public entry has an honest, useful access path; newly supported
helpers cannot bypass validation, job management or source preservation. Old
saved recipes still run or produce a specific recoverable migration message.

### 5. Verify ease of use, correctness and responsiveness

Exercise the complete workflows in the real browser, not only rendered cards.
Use focused adapter, state and browser checks tied to the changed behavior.

Completion checks:

- A user can run each initial example from a loaded dataset without reading
  Python signatures, typing JSON or navigating away from the workbench.
- All matching entries remain on one page, including Python references. Search
  covers task labels, exact names, aliases and parameter meanings.
- Invalid types, missing markers, unavailable fitted results and incompatible
  datasets have understandable recovery instructions; no long job starts.
- Control values serialize to the owning function's exact arguments. Compare
  representative numeric/statistical outputs against direct package calls using
  the same data and settings; replay those runs and compare outputs.
- Drafts, selection, result recipes and appearances survive switching functions
  and reopening a project, without leaking settings between unrelated actions.
- Searching, opening help and changing selections cannot start an analysis.
  During a real long job, search and editing remain available and existing plots
  remain visible. The existing one-active-job limit is explained locally.
- New acceptance targets: search feedback and switching to a cached form within
  500 milliseconds on the documented desktop dataset, including browser and
  server work. Measure cold form opening separately. These are proposed targets,
  not achieved results. Retain the existing figure performance budgets and
  report any remaining cold-start miss rather than lowering scientific fidelity.
- Verify keyboard focus, both themes, 1440 x 900 and 800-pixel layouts. Align
  comparable plot areas vertically; no clipped controls or overlapping labels.
- Preserve canonical result views and the existing figure-save path. All saved
  plots use `PyFLASH.utils.save_fig`, which writes figures and their recorded
  data through the package's export system.

## Optional skill reference

Keep the functions-page experience explicitly invoked. After the interaction is
implemented and verified, update that reference with the tested form pattern and
end-to-end checks. Do not promote a planned interface to an accepted example or
make a catalogue mandatory for unrelated software work.

Proposed lesson: When a functions catalogue is intended for interactive use,
provide an input form, prerequisite guidance and result handling for each supported
action, and verify a complete run rather than only search and setup navigation.
Main skill wording is not changed in this planning round.

## Feedback, verbatim

2026-10-02, referring to the current continuous Functions catalogue:

> it needs to be much easier to use each function, its very confusing right now. lets make a plan for this. look online for how others do this kind of thing

Earlier constraint retained:

> dont have pages it should all just be shown on one page

## Recommended first implementation

Complete stages 1 and 2 first. The histogram is a useful forcing example: the
current screen cannot supply its required marker and measured attribute through
ordinary controls, so a successful complete run proves more than cosmetic change.
Keep the current functioning catalogue available until the replacement workflow
passes its focused checks.

## Implemented and verified (2026-10-02)

- All 450 entries remain on one continuous Functions page. Task/access filters
  and search use the actual catalogue; choosing an entry opens its form or
  reference beside the list. Figures and Images select this same workbench.
- All 46 registered actions and 14 public helpers have browser forms. The other
  390 entries explicitly describe their Python access and required context.
  Downloadable coverage accounts for every source parameter and its input role.
- Controls use actual dataset measurements, metadata, groups, markers, object
  attributes and experiment choices. Structured inputs use editable rows rather
  than JSON. Advanced settings preserve package defaults, explicit None and
  empty values. Appearance remains separate from analysis.
- Drafts and result recipes persist by entry. Old JSON overrides migrate to
  labelled fields or remain downloadable with a specific migration message.
  Existing saved figure specifications run within the same workbench.
- Run alone submits a background job. Search and editing remain available while
  it runs. Results use the package's figure writer, isolated output directories,
  complete table downloads and actual equivalent Python scripts.

The real browser completed group comparison, relationships and histograms on
the unchanged 288-MB, 42-subject dataset. Run durations were 37.24, 17.79 and
21.30 seconds respectively. Group means and valid subject counts match the
source summary table; the chosen measurement has 40 nonmissing values. These
are workflow checks, not new biological conclusions.

106 focused service, worker, workspace, catalogue and workbench checks pass;
36 figure-page checks pass separately. Coverage checks render all 46 action
forms and preserve exact owner arguments. A public-helper replay executes and
matches the direct owning call. This does not certify every scientific action
or replay on the private dataset. Missing images and fitted results have
prerequisite guidance. Both themes and the 800-pixel layout were checked.

Client filtering usually responds in 3-33 ms in the sampled browser, with one
895-ms sample. Click-to-form response was 0.51-1.49 seconds. These measure native
browser events to visible updates, separately from automation-driver time.
An earlier active-job search measured 0.73 seconds. Background execution is
usable, but consistent 500-ms search/form response has not been achieved.

Completed receipt: `C:/Users/Owner/AppData/Local/PyFLASH/functions-review/workbench-runs/report.json`
(SHA256 `f39187611dddd3e2e4f4bfe7ad781207d8e45b0b271eed39b27a1b2e30fda011`).
Reproduce browser checks with `scripts/check_ui_function_workbench.py` using an
explicit tab and dataset inputs; `--resume` retains completed outputs rather
than running the three analyses again. Source SHA256 before and after was
`52eb58d9915cfaed946f57bcdf2b433222504c183159eb7ee55cc667af2f4409`.

The optional functions-page software-development reference now records these
forms and complete runs. Its explicit-invocation boundary remains in place;
main skill instructions were not edited. Skill-tuner case 0110 records the
correction and verified implementation.

## Current catalogue scope (2026-10-03)

User feedback, verbatim:

> it should only show the plotting or pipeline functions. other functions we can put elsewhere, like the excel export function or adjusting the house aesthetic for example

The primary Functions workbench now uses the owning action registry: 46 plotting
and analysis pipeline forms on one continuous page, with task filtering. Low-level
rendering helpers are not additional analysis tasks. The complete 450-entry source
inventory remains available for ownership and coverage checks, separately from
the user-facing list.

- Export keeps its existing Excel/CSV/save-analysis controls and now includes a
  collapsed export package reference, including `Batch.export_all_excel`.
- Workspace contains House aesthetic: saved defaults for dimensions, raster
  resolution, points, lines, labels, fonts and matrix colours. These defaults are
  merged into new plot/pipeline jobs; a function's own saved appearance takes
  priority, and the exact combined settings are recorded and replayed. Existing
  outputs and process-global package defaults are not rewritten.
- Appearance helpers live in the House aesthetic reference. Remaining package
  helpers are searchable in Workspace's collapsed Other package functions.
  Their existing supported adapters and Python references remain available.

Old selections pointing to a helper or obsolete helper-task/access filters are
reset to a valid analysis action. Drafts and results remain keyed to their
original function. The optional software-development experience reference now
requires respecting the requested catalogue scope; main skill text is unchanged.

Browser verification on the loaded real dataset confirms the scoped registry,
Excel export/reference in Export, house appearance in Workspace, and a statistics
helper in the supporting Workspace section. Empty-search recovery, both themes
and the 800-pixel layout pass. An existing adjusted-correlation worker remained
active during these checks; the review submitted no analysis. Search event-to-
visible samples were 6-74 ms; form samples were 1.11-1.54 seconds, still above
the prior 500-ms target.

Receipt: `C:/Users/Owner/AppData/Local/PyFLASH/functions-review/plot-pipeline-scope/report.json`,
SHA256 `5923bb911fd8072de67e6224e0918d1ec255bb5c2c52fb0b65364ecba6234db1`.
Focused checks cover registry scope, every supporting function's home, recovery
from old selections, saved house settings, job argument precedence and inherited
appearance after reopening. These changes are routine interface maintenance;
no new scientific analysis or Research Gallery record was produced.
The initial focused service/workspace/catalogue/workbench/scope run passed 92
checks; 20 workbench/scope checks passed after the final appearance changes.
