# Browser workflow performance pass

## Current status, 2026-10-07

The subsequently finished frozen full workflow draws the example's headline
plots in 4.435 seconds and completes selection in 0.338 seconds, passing both
unchanged example-data budgets. Its real-data startup gate still fails. The
receipt is `isolated-current-alignment-20261007-v1/20261007T104216498316Z/run.json`
under the local evidence directory. The corrected second frozen full workflow
is still running; neither source is substituted for current-source acceptance.

Lightweight actual-app instrumentation records overlapping service import,
snapshot capture and restoration; these spans cannot be added as removable
startup time. Moving the first chart request earlier still misses the startup
limit in both candidate samples. Direct temporary-file capture shows no stable
improvement, and a larger in-memory snapshot is slower in both candidate samples.
All three proposals remain private. Their retained receipts are
`actual-ui-loading-lightweight-spans-20261007-v1`,
`early-chart-only-idle-20261007-v1`,
`direct-large-capture-stream-private-20261007-v1`, and
`bounded-memory-capture-private-20261007-v1`. Concurrent load and retained
objects limit attribution; these are diagnostics, not startup acceptance.

The latest actual installed-source browser trial completes idle/busy selection,
navigation and recovery without errors, with unchanged code/input and a closed
owned server. Cold plotted views take 19.102 seconds under concurrent validation
load and fail the unchanged five-second limit. Idle and busy redraw medians pass
at 0.374 and 0.444 seconds. Receipt:
`atomic-state-read-real-interface-20261007-v1/checks.json` in the local evidence
directory. It is a failed performance result, not proof of a successful startup
optimization or a controlled before/after attribution.

The actual Windows job-state permission failure is retained. A bounded reader
now retries brief access conflicts with at most 75 milliseconds total waiting;
permanent access and malformed/version-invalid state errors remain visible.
All 98 installed state/replay checks and the 441-check targeted release gate pass.


Further diagnostic trials under concurrent complete-workflow load remain over
the startup budget. Moving the mandatory service wait after data restoration
did not meet the five-second limit in either fresh candidate sample (7.085 and
6.947 seconds). The candidate is retained privately and not installed. Both
idle/busy redraw medians pass in every completed baseline/candidate trial.

An earlier baseline trial refused a subject-selection click during fragment
replacement. The browser procedure now requires the visible enabled selector
alongside both headline plots and waits atomically for its click. Three actual
browser DOM checks pass; permanent absence still refuses completion. The
original failed trial, logs and screenshot are retained. This is a stricter
readiness check, not a passing performance correction.


The latest finished full workflow misses the unchanged five-second cold-plot
budget: 5.878 seconds on the example and 5.166 seconds on the saved real
analysis. Real-data selection passes at 0.327 seconds idle and 0.344 seconds
busy, against the unchanged half-second limit. Source and input hashes remain
unchanged. A passing startup correction and coherent current-source full
verification are still required; historical passes below do not certify them.

Receipt: `current-alignment-full-installed-distribution-20261007-v1/20261007T054346562378Z/run.json`
and its `real-data-browser/checks.json` under the local PyFLASH evidence directory.
That full run also fails reference import and test collection; restored evidence
checking now passes 47 focused tests. A coherent frozen source copy is being
checked separately from concurrent verification edits. Budgets are unchanged.

The earlier October 6 full failure at 5.127 seconds example and 7.164 seconds
real data remains in `current-alignment-full-after-repairs-20261006/20261006T175306734374Z`.

Form opening was subsequently optimized on 2026-10-05: matched median
2.042 → 1.033 seconds. See the [form-opening report](ui-form-opening-performance.md)
for source freshness, handler cleanup, per-family timings and remaining limits.

## Historical evidence, 2026-10-04

The latest unchanged-source full workflow passes all browser and layout gates.
The example draws actual plots in 4.586 seconds and completes subject redraw in
0.334 seconds. The real saved analysis draws plots in 4.715 seconds, with idle
and busy redraws in 0.345 and 0.313 seconds. Limits remain five seconds and half
a second. Inputs and source identities remain unchanged and both owned servers
close. Evidence:
`C:/Users/Owner/AppData/Local/PyFLASH/correction-reports-full-20261004/20261004T161936991726Z/run.json`
and its `real-data-browser/checks.json`. Desktop and 800-pixel layouts, native
download naming/help, local appearance, navigation and dependency repair pass.

The following separate browser checks are retained earlier evidence.

The latest source-stable real-data browser check passes all unchanged timing
limits: 4.675 seconds to the actual plots, 0.350 seconds for subject selection
idle and 0.322 seconds during bounded processing. Navigation, input integrity
and owned-server cleanup pass. Its receipt is
`C:/Users/Owner/AppData/Local/PyFLASH/lazy-measurements-browser-20261004/checks.json`.
Mandatory service imports and source hashing overlap the initial shell work;
the closed measurement panel renders its table only when opened.

The actual example-data browser check also passes: 2.792 seconds to plots and
0.294 seconds for subject selection. Both themes, narrow layout, linked chart
selection, independent measurements, reopening the measurement table, preparing
and downloading all 12 subject rows with its replay-script control, saved
selection and every navigation destination pass. Local
appearance editing passes in the same owned server. The receipt is
`C:/Users/Owner/AppData/Local/PyFLASH/download-layout-demo-20261004T152033Z/checks.json`.
Both 1440-by-900 and 800-by-900 audits pass every metric, including actual native
download-button naming. Its visible hover help is verified in the same browser.
These separate receipts precede later cache/path corrections, which also pass
the newer full workflow above.

### Retained earlier failures

An earlier real-data check completes navigation and processing interactions,
preserves its input/source hashes and closes its owned server, but fails the
unchanged timing gates: 8.795 seconds to plots, 0.508 seconds for idle selection
and 0.551 seconds during processing. Its receipt is
`C:/Users/Owner/AppData/Local/PyFLASH/server-readiness-corrected-20261004/checks.json`.
Server preparation is recorded separately. A socket probe verified readiness
after approximately 24 seconds; the old 15-second pre-navigation deadline was
insufficient for that run. The bounded readiness helper does not alter plot or
selection budgets. A complete app-entry profile identifies mandatory measurement
imports and Streamlit's Python-stack inspection on the initial render. The
profile includes instrumentation overhead and is not a passing timing sample.
Evidence is retained under
`C:/Users/Owner/AppData/Local/PyFLASH/current-first-plots-profile-20261004/`.

The earlier passing run below remains historical evidence for its source snapshot.

The source-stable full round measured actual plots on the 287,618,369-byte
saved analysis at 4.743 seconds (5-second limit), linked redraw at 0.334 seconds
idle and 0.342 seconds while processing (0.5-second limits). Two cycles through
all eight navigation destinations while processing also pass. Inputs and code
are unchanged, and the owned server closed. Evidence:
`C:/Users/Owner/AppData/Local/PyFLASH/recovery-circular-full-20261004/20261004T094621870110Z/real-data-browser/checks.json`.

Later recovery and analysis changes require a fresh whole-workflow run. The
historical preparation investigation below remains evidence of its recorded
source snapshot. Current worker and replay launches use the actual interpreter
in `sys.prefix`, preserving its installed dependencies.

## Historical preparation investigation

Keep the bounded worker and display optimizations. Table preparation is about
25 times faster on the real saved analysis, with exact differential agreement.
Processing, figures, image panels, exports and saves leave the browser usable.
This is a UI performance result, not a claim that scientific processing itself
runs 25 times faster.

Measurements are labelled below. The table benchmark passes the configured
relative gate; the browser functional check passes. Browser latency samples are
too few to certify a tail-latency guarantee. Final browser and resource results
are recorded in the local receipt listed below.

## Contract

- Real workload: a local 287,618,369-byte saved analysis, 42 summary rows,
  7,433 columns, 7,333 finite numeric measurement columns, four experiments
  and nine displayed groups. Object columns include missing/exclusion tags
  and nested metadata. The second required case is the frozen 12-row,
  four-column packaged example.
- Completion boundaries: navigation until both actual exploration plots draw;
  subject selection until both plots reflect it; submission until the worker
  is launched; operation completion until its durable status/result is readable.
- Correctness: preserve original measurements, integer precision, floating
  values, tags, identities, column order, available choices and saved inputs.
  Worker selections preserve exact pandas types and labels. Scientific work
  uses existing package functions and parameters; no lower-quality analysis
  or image resolution is selected automatically.
- Existing design targets: first usable plots within five seconds and linked
  redraw within 500 ms. Working assumptions for this pass: admission within
  one second, preparation within three seconds on the real cohort, one active
  operation, no waiting queue, one cached source, and no host-wide tuning.
- Relative gate: normalized elapsed-time speedup at least 0.95 per required
  case; ten paired trials; 10,000 paired bootstrap resamples; 95% family
  confidence with Bonferroni correction across two cases. These are scalar
  timing gates, not memory or request-tail gates.
- Benchmark and rollback owner: the project maintainer. Do not replace the
  preserved baseline merely because a future run regresses.

## Reproduction and scope

Executed on Windows 11 build 26200, Python 3.12.10, pandas 2.2.2, AMD64 Family
25 Model 80, 32 GB host memory. Other research applications remained running.
No global caches were flushed. At the later job boundary, about 12 GB RAM and
162 GB disk space were available. Source files were already local; no large
microscopy folder was downloaded.

Source SHA-256:
`52eb58d9915cfaed946f57bcdf2b433222504c183159eb7ee55cc667af2f4409`.

Preserved baseline workspace module SHA-256:
`dba87db1d8de59f3ccc1c9edaaba2bf6e1c6424de5568e950a5b92294d2c6131`.

The paired run records the candidate module hash. Later additions to that file
handle source caching, small selection snapshots and reference display;
the measured normalization and catalogue algorithm remained unchanged.
The working tree also contains other research changes that predate this pass.
No commit, publication, release or full-suite test was performed.

Raw evidence lives under `%LOCALAPPDATA%/PyFLASH/performance-review/`:

- `baseline_workspace.py`, `baseline.prof`, `baseline-profile.txt`.
- `paired-preparation-10.json`, `comparison-input.json`,
  `comparison-result.json`: all samples, hashes and the relative gate.
- `app-cold.prof`, `app-warm.prof`, `figure-page.prof`: diagnostic profiles.
- `production-worker-check.json`: actual worker-process CSV, save/reopen and
  unsaved registered-figure checks on the frozen example.
- `browser-isolated-final.json`, `real-interface-final.png`: owned-browser
  rendering, navigation, active-worker interactions, alignment and recovery.
  Earlier browser receipts are preserved, including slower and failed trials.
- `check-server.stdout.log`, `check-server.stderr.log`: clean-server checks.

Equivalent reproduction commands, from the checkout, are:

```powershell
cd '<checkout>'
$env:MPLBACKEND = 'Agg'
python scripts/benchmark_ui_preparation.py --source '<local-analysis.pkl>' --baseline-module '<preserved-baseline_workspace.py>' --pairs 10 --output '<private-review>/paired.json'
python scripts/check_ui_responsiveness.py --source '<local-analysis.pkl>' --cdp 'http://127.0.0.1:9333' --tab-id '<only-this-app-tab>' --url 'http://127.0.0.1:8511/' --reloads 3 --output '<private-review>/browser.json'
python -m pytest tests/test_ui_services.py tests/test_ui_conditions.py tests/test_ui_images.py tests/test_ui_plots.py tests/test_ui_workspace.py tests/test_ui_jobs.py -q
```

The earlier launch investigation used a major/minor launcher fallback. That
historical route could select a different installation; current workers and
replays instead use the actual interpreter in `sys.prefix`.
Actual worker logs also exercise UTF-8 output and the noninteractive
Matplotlib backend.

Table preparation includes normalization, numeric-column discovery and display
labels. Pickle reading, imports and garbage collection are outside that paired
timing. The recorded `load_seconds` also includes computing the input hash;
it is not a pure file-read measurement. Alternating AB/BA order limits drift.
Small-example samples average 30 executions each; they are not request tails.
The browser check includes server work and actual SVG drawing. Its processing
fixture runs a bounded, checksum-validated single-CPU workload for 25 seconds,
then calls the real cached factory. It does not reprocess private raw data.

## Diagnosis and changes

**Measured:** the original profiled normalization took 62.17 seconds and
generated roughly 38 million calls. It repeatedly constructed Series, converted
the same cells to strings, built missing-value masks and assigned thousands of
columns individually. The profiler perturbs runtime; the unprofiled paired
samples below are the comparison used for the speedup claim.

**Measured:** rescanning the real figure directory took 6.61 seconds. Compiling
the entire plotting source merely to show function help took 2.67 seconds in
a profile. Backend warm redraw profiling was about 0.3 seconds before reducing
the large menus; browser drawing and application scheduling add further time.

The accepted changes remove unnecessary passes, fragmentation and copies:

- Convert scalar candidates directly, check only failed conversions for known
  missing tags, and build the presentation frame once. Keep the raw table intact.
- Compute choices and labels once; label an empty frame rather than copying
  all values. Cache by dataset identity and region.
- Cache one read-only loaded source and its first-region catalogue. Each session
  gets a separate view object and a separate editable representative table.
  Scientific operations load their own object in the worker.
- Bound large menu payloads to 200 matches plus current selections. Search
  reaches every measurement; no scientific columns are removed.
- Read only a selected function declaration and docstring for help. All registry
  signatures and documentation were compared exactly with the full source AST.
  **Measured:** all registered references take 0.345 seconds together, versus
  seconds spent compiling entire bodies for the previous helper.
- Use the completed worker's known figure paths instead of rescanning the output
  tree on each redraw. Cache at most twelve SVG preview conversions, invalidating
  them when file size or modification time changes.

The ownership boundary is now:

```text
Browser session: read-only measurements + editable selections + current plots
       | immutable source/settings/selection snapshot
       v
One admitted process worker: existing PyFLASH processing/plot/export function
       | atomic status + durable log + result path
       v
Sidebar progress; completed result only for the current dataset
```

The worker has no waiting queue and exits after completion. Numerical-library
thread counts are bounded to one in that worker; no host-wide settings change.
UTF-8 logs, process loss, server restart, retry and cross-session admission are
handled explicitly. Reopening data clears all prior dataset-specific views.
Files changed since opening/submission are rejected before an operation can
silently use different inputs. Completed processing is opened explicitly;
figures and exports become available without discarding the current plots.

## Correctness and measurements

**Measured:** every real and example paired run used exact frame equality,
equal measurement lists and equal display labels. Source SHA-256 stayed
unchanged. Tests cover recognized tags, unknown mixed text, nested values,
large unsigned integers, nonfinite values, nullability, cache invalidation,
lossless selection snapshots, changing source files, stale dataset results,
single admission, crash/retry and bounded log reads.

**Measured:** 159 focused interface/worker checks pass. Actual subprocess checks
produced the same example CSV bytes, saved/reopened an exactly equal summary,
and executed the registered unsaved mean-bar call. Image and workbook paths
retain owning-package parameter forwarding and experiment selection. No private
image rendering or raw experiment reprocessing was performed for this pass.

| Required timing case | Baseline median | Candidate median | Paired speedup | Bootstrap interval | Relative gate |
|---|---:|---:|---:|---:|---|
| Real saved analysis, uncached preparation | 51.07 s | 1.99 s | 24.84× | 20.84–29.39× | pass |
| Frozen example, uncached preparation | 2.25 ms | 1.54 ms | 1.39× | 1.13–1.71× | pass |

The interval is per-case 97.5%, providing the configured family confidence under
the comparator's assumptions. Adjacent pairs on a shared desktop can remain
correlated; this interval is evidence for a large scalar improvement, not a
formal certification of every future workload. Real candidate samples ranged
from 1.36 to 2.81 seconds. Five cached catalogue calls take microseconds.

The final browser receipt separately records first usable plots, four idle
and four busy subject changes, four busy route changes, post-job recovery,
source identity, worker completion and observed memory. Both plot top and bottom
edges match exactly. Busy interaction checks assert that the worker is still
running before every operation, so a shortcut through already-finished work
cannot pass.

**Measured, clean server and owned browser:** the first cold opening takes
9.22 seconds; subsequent complete openings take 2.99 and 2.53 seconds. The
five-second cold target remains unmet. Idle linked redraw has a 502-ms median
(444–534 ms); busy linked redraw has a 491-ms median (433–509 ms), and post-job
recovery takes 446 ms. Individual redraws can still narrowly exceed 500 ms.
Admission takes 25 ms. Navigation while work runs takes 2.09 seconds for
Workspace, 2.31 seconds for Figures, 535 ms for Export and 678 ms for Explore.
The initial package/serialized-object/client startup is still paid on a clean
process; the accepted changes avoid paying source preparation on later opens.
These measurements do not claim that all absolute budgets passed.

**Measured:** the standalone paired run peaked at 652.6 MB resident memory and
retained 593.3 MB after cleanup; this includes its real analysis. The final
worker receipt includes the observed resident peak, approximately 652 MB in the
last pre-clean-server run. Process memory is released on exit. Earlier UI reload
bursts peaked at 2.61 GB in the existing server, which also retained prior live
sessions. The new source cache bounds that duplicated source work to one entry;
the clean server retained 653.0 MB and peaked at 703.8 MB after three opens and
the active-worker navigation test. The worker peak in that test was 649.6 MB.
The two process peaks add to approximately 1.35 GB as a conservative derived
bound for this case; they were not simultaneous samples. RSS is process-resident memory,
not an allocation count, and host-wide peak memory was not certified.

## Remaining limits and prevention

Retain these changes: exact data agreement, useful browser interactions during
work and the large preparation improvement justify the added worker boundary.
The package's scientific algorithms, public numerical API, figure writer and
full-resolution defaults are unchanged.

The five-second startup and 500-ms redraw targets are evaluated as individual
browser samples; few observations do not certify consistent latency under every
desktop load. Raw-image memory, much larger analyses, multiple simultaneous
browser users and long degraded-storage jobs remain unvalidated. A stopped
scientific worker can be retried from its preserved inputs/log, but it cannot
resume midway through the package algorithm. The worker limit prevents an
unbounded queue rather than providing cancellation or distributed execution.

Keep the focused tests in development and rerun the browser/paired checks after
changes to source loading, table preparation, menus, figure display or workers.
Reject changed values, blocked navigation, stale results or a failing required
relative case; investigate absolute budget misses rather than silently widening
the budgets. Larger data and raw-image cohorts need their own resource budgets.

The responsiveness correction is filed as skill-tuner case 0096 (blocking the
interface during scientific work). Existing
software-development guidance already requires responsive updates; no shared
skill wording changed. A tested functional-report validator was installed and
registered with three normal/failure checks. Routine UI maintenance produced no
new biological result or accepted scientific figure, so no Research Gallery
record was added. Full-suite tests and the knowledge-graph refresh were left for
a requested broader audit.

## Function workbench measurements (2026-10-02)

All 450 cards share one component. Search filters existing browser nodes rather
than remounting the editor; selection sends one event and renders one form.
Source contracts, card markup, measurement headers and coverage are cached.
Only Run admits analysis to the existing isolated worker.

On the real 288-MB, 42-subject dataset, event-to-visible search samples were
0.003, 0.005, 0.895, 0.033, 0.006 and 0.007 seconds. Form samples were 0.611,
1.493, 0.511, 0.753 and 0.771 seconds. Driver scroll/retry time is recorded
separately. These samples do not satisfy a consistent 500-ms interaction budget.
An earlier full-driver search during an active analysis took 0.728 seconds;
editing remained available. Three real analyses completed in their workers in
37.24, 17.79 and 21.30 seconds without changing the source dataset.

Evidence and reproducible browser checks are linked in
[ui-function-usability-plan.md](ui-function-usability-plan.md). Performance
claims apply to the sampled forms and this dataset; discovery coverage does not
certify every analysis or a separate cold-start budget.

## Real-analysis budget correction (4 October 2026)

The earlier startup/redraw misses above are retained historical measurements.
The accepted correction preserves every table cell, type, field identity and
display label on the unchanged 287,618,369-byte analysis. Bounded menus keep
all 7,433 measurements searchable, resolve labels only when needed and prepare
the numeric table once. Independent imports overlap the initial source hash;
post-read hashing remains mandatory and changed source bytes reject the load.

The owned-server, actual-browser run at
`%LOCALAPPDATA%/PyFLASH/real-data-budget-20261004-import-overlap/checks.json`
passes the unchanged limits: cold headline plots 4.6927097 seconds; median
linked redraw 0.3268 seconds idle (0.3567, 0.3786, 0.2452, 0.2969) and
0.32215 seconds during active work (0.3672, 0.3329, 0.3114, 0.2934).
The source hash remained unchanged and the owned server closed. The initial
sample alone establishes this run's cold-start budget; warm reloads are kept
separately and never averaged into it. These sampled medians do not claim a
worst-case latency bound across all desktop loads.

Paired automatic-collection settings did not improve the sampled interactions,
so normal Python garbage collection remains enabled. The launcher disables
Streamlit's separate post-script collection by default and preserves an explicit
user override. Subsequent appearance/workspace edits still require a fresh
budget check in the final workflow. Use `python -m reproducibility.run --full
--require-complete --real-data <trusted-pickle>` to retain that check together
with all other required stages.
