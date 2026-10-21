# Executable development checks

PyFLASH's development rules live in `architecture.yaml`. The project-local
runner works without an installed agent skill and leaves scientific settings,
saved projects and plotting defaults unchanged.

## Run

From the repository root:

```powershell
python -m pip install -e ".[dev]" -r scripts/contracts-requirements.txt
python scripts/verify.py
python scripts/verify.py discover
python scripts/verify.py --group release --json
```

The default command checks the import boundaries, required files, locked
developer templates, shared builders, embedded card styles and live catalogue.
Discovery lists the existing controls, saved disclosures, function cards and
scientific figure writer. It fails if their bindings are broken.

The release group additionally runs the declared interface, recovery, replay,
independent scientific-reference, multi-group statistics, rendering and loading
tests. Its test report must contain executed passes; required skips, failures,
empty selections and timeouts fail the check. Individual groups can be selected
using `--check` and their actual names from the contract.

The public pytest configuration disables automatic loading of unrelated
installed extensions; explicit `-p` extensions still run and their failures
still fail verification. Test subprocesses opt into the existing owned Windows
metadata fallback through `tests/conftest.py`, including when the declared
runner starts plain `python -m pytest`. This avoids a stalled WMI metadata query
while writing the final report; product commands and numerical operations are
unchanged. Actual child-process controls verify extension discovery and complete
report output. These changes preserve every declared deadline and pass count.

## Owners and reasons

Adopted on 2026-10-06 following: "skip clockcytepy and do pyflash".
The selected profile covers the existing Streamlit application alongside the
scientific package. No new interface framework or numerical method is introduced.

- Plot capabilities remain owned by `PyFLASH/spec.py`, actions by
  `PyFLASH/actions.py`, and public function metadata by the source-derived
  catalogue. The contract contains no second list of scientific functions.
- Native controls and saved advanced disclosures use `PyFLASH/ui/controls.py`.
  The adapter test walks every interface source file to reject direct native
  control calls that would bypass registered keys, help or icons.
- Scientific modules stay independent of the browser. The existing command,
  action and queue drivers may call headless workspace adapters; those drivers
  are not classified as numerical analysis. These exceptions are named and
  justified in the contract. Every top-level core module, including newly added
  modules, is checked for browser-adapter imports and forbidden Streamlit,
  FastAPI and internal analysis-kit imports. The source root is the repository
  root because this package uses a flat layout, so relative imports retain
  their actual PyFLASH package prefix.
- Figure export retains `PyFLASH.utils.save_fig`, the existing ReproFig writer,
  and `PyFLASH/aesthetics.py`. Numerical arrays, stored condition colours,
  statistical defaults and approved reference answers are unchanged.
  Stored colour names are checked against the existing frozen fixture without
  requiring the optional private analysis-kit conformance module.
- Interface CSS remains in `PyFLASH/ui/theme.py`. An adapter extracts the actual
  constant into a temporary stylesheet and checks adopted card selectors with
  the shared checker. Streamlit owns the five native colour tokens. Existing
  fixed catalogue height and other styles outside those selectors are not
  certified or silently rewritten.

## Build integration

`.github/workflows/project-contracts.yml` runs the release group on pushes,
pull requests and manual runs. The distribution build calls the same workflow
and waits for it before packaging. The existing broader scientific regression
workflow remains an independent check.

Generated tooling is pinned by `architecture.lock.json`. Use the shared
software-development installer with `--update --reason` to update untouched
copies. Do not edit generated runners or their lock hashes to suppress failures.
Project-owned rules and exceptions need a reason recorded here.

## Scope and existing open work

This adoption connects existing behaviour to mandatory checks. It is not a
new whole-package alignment certificate. The wider alignment record at
[software-development-alignment.md](software-development-alignment.md) retains
its own incomplete full-workflow, scientific-coverage and real-data startup
gates; their budgets and expected answers are not relaxed here.

Browser pixel geometry, complete JavaScript dependency analysis, computed
dynamic imports and all legacy styles are outside these static checks.
Streamlit application tests exercise declared interactions but do not establish
browser screenshot geometry or real-data performance. Committed workflows have
not been executed remotely or configured as branch-protection requirements.

## Adoption evidence

The reopening test's reduced navigation fixture now selects the actual
registered functions page rather than assigning its filename to an unrelated
key. Its assertions about recovered drafts and discarded button triggers remain.

The first combined statistics run exceeded the provisional 300-second command
deadline. A diagnostic run passed all 1,021 one-way checks in 93.58 seconds;
its coverage-inventory scan took 59.77 seconds. The aggregate command deadline
is therefore 600 seconds, retaining all three report suites and the correction
suite. Scientific answers, tolerances and application performance budgets are
unchanged. The first failed report is retained locally in
`.runtime/project-contracts-first-run.json`.

See [project-contracts-verification.json](project-contracts-verification.json)
for the executed local release-group report, including test counts and skips.

All seven declared groups passed locally: 4,332 test executions, zero skips.
The combined statistics group passed all 4,001 cases in 312.84 seconds of pytest
execution (321.672 seconds including the launcher). The routine check passed
23 cases in 21.469 seconds including its launcher. Evidence combines the initial
release-group run with focused rechecks of the corrected navigation fixture,
expanded architecture adapters and statistics deadline. Optional full-suite
testing and Graphify refresh were not run for this adoption.

Skill tuning proposal: none needed; the existing installer and verifier provide
the shared implementation.

The direct-utility/lifecycle check added on 2026-10-06 runs all 16 newly
installed regression modules, including altered-evidence and object-ownership
guards. Its minimum count comes from the actual installed test report; its
600-second command deadline covers the retained 295.27-second affected round.
The verification workflow calls this declared check. The full reproduction
workflow also collects these modules in its unfiltered suite; its development
loop runs the separate documented `pytest -m "not slow"` selection.
Native expected answers, scientific tolerances and application
latency budgets are unchanged. The functional lifecycle controls do not provide
scientific inference votes or certify their parent imports/pipelines.

The extended installed gate passes 1,591 tests in 320.438 seconds, with unchanged
source. It includes all 48 native real-plane coordinate/carrier cases, two
altered-coordinate-evidence guards, 153 complete literal experiment metadata
controls and three metadata evidence/failure guards. The verification workflow
selects the release group explicitly. Empty-condition status reporting no longer
crashes; these functional contracts do not certify scientific constructors.

The source-distribution check streams the actual compressed archive once and
compares retained resources byte for byte. Missing, changed and duplicate files
fail release builds and full reproduction. It includes native runtime programs,
binary fixtures, demo browser assets and framework configuration. The temporary
directory regression executes a real framework application collected before
pytest clears its separate output directory. Original failure receipts remain.

The association interval gate passes 42 tests with unchanged source. It includes
28 native confidence-level cases, four altered-evidence guards and ten actual
archive checks. The additional direct export/inference boundary gate passes 45
tests with unchanged source: 23 literal whole-file export cases, 16 native
sample-size cases and their evidence/environment controls. Unavailable Fisher
inference is returned as missing while correlation estimation remains available.

The exact-subject-identifier gate passes 68 tests with unchanged source. Its
66 real constructor calls retain exact large integers and nonintegral names,
measurement rows, original indices, attributes and region identities. Both
constructors' complete option sets remain open; these functional identity
controls are not extra scientific inference votes. The affected installed
table/interface round passes 147 checks.

The spreadsheet source-row and acquired-region gate passes all 148 tests in
266.094 seconds without source changes. It combines 64 group-row controls,
48 region-selector controls, changed-evidence/output guards, all existing CSV
contracts and the prior unregistered-export integration checks. Original native
workbooks retain 48 group-export and 44 region-export failures. Limited workbook
branches remain partial; this gate does not close whole scientific processing.

The outlier-request/binary-fit gate passes 108 checks in 42.734 seconds without
source changes. It includes 62 functional requests and their table/evidence
guards, the actual grouped-overview regression, and 36 complete native R
two-class fit/response cases plus four alteration guards. The corrected focused
round passes 561 checks; 98 fresh installed comparisons agree. Original request,
queue and fit failures remain retained. These conditional families do not close
whole statistical/model parents or relax any tolerance or application budget.

The corrected outlier request/overview queue passes all 3,793 affected checks
in 306.80 seconds. Its additive verification receipt preserves the original
queue installation receipt and first failed regression. Current request/binary
replay executes 98 agreeing controls without source changes. Whole scientific
parents and final workflow verification remain open.

The declared marker-threshold-consumers release gate passes 128 checks in
39.75 seconds with unchanged source. The broader import/processing round passes
526 checks in 68.279 seconds with unchanged source; actual installed family
replay passes 120 literal controls. Original constructor, import and nearest
failures are preserved; whole scientific marker/import parents remain open.

The public-distribution-curves release gate executes 80 checks in 35.297 seconds with unchanged source: 60 native/domain public calls, ten original queue/label controls, three changed-evidence guards, six damaged-output guards and one independently captured caller-table preservation control. All 162 affected plotting checks and 70 installed family comparisons pass without source changes. The finite observation count follows the existing backend admission; native R raw-infinity acceptance and SciPy refusal remain separate retained contracts. Original failures, native answers and tolerances are unchanged. Complete plot options/rendering remain open.

## Region, label and source-download evidence gate, 2026-10-07

`distribution-selection-and-evidence` executes at least 203 selected-region,
legacy-object, finished-label, evidence-authentication, native-expression and
production disk-admission and artifact-consumer registry guards within 300 seconds. It supplements the existing
80-test distribution-curve gate. Its scope preserves original reference inputs,
native curves, labels, returned group/count fields and caller-owned tables;
it supplies no complete whole-plot or performance claim.

The source archive verifier now derives mandatory resources from authenticated
primary input manifests, in addition to the captured build inventory. Original
runtime cache files are losslessly encoded and separately authenticated when
the build excludes executable caches. Missing native data and workbooks cannot
be substituted by those encodings. Saved-output metadata and preserved negative
fixture manifests remain ordinary authenticated files, rather than new resource
inventories. Original failed builds and consumer refusals remain retained.

The full reproducibility workflow also runs `scripts/check_distribution_consumers.py`
after its source-resource gate. It executes both declared distribution test
groups from an actual extracted source download and an actual extracted wheel,
verifies which package supplies every public call, and guards both extracted
code inventories and original artifact hashes. Test selection and required
pass counts come from the same project registry used by the release gates.

## Project test discovery, 8 October 2026

Project tests explicitly disable automatic loading of unrelated third-party
pytest extensions through the public `--disable-plugin-autoload` option.
Install development tools with `pip install -e ".[dev]"`; pytest 8.4 or newer
provides that option. Required extensions, if introduced, must be named explicitly
with `-p` and tested as project dependencies. Ordinary test collection, executed
case counts, assertions, failure handling and deadlines are unchanged. The
locked verifier and its hashes are unchanged.

The controlled release launch passed the original 335-, 193- and 417-test
checks in 90.328, 145.047 and 125.734 seconds, against their unchanged 180-,
240- and 180-second deadlines. That trial also suppressed bytecode writes;
the installed public-option-only route requires its own actual verifier run.
Evidence: `%LOCALAPPDATA%/PyFLASH/native-adapter-and-release-isolation-20261008-v1/release-launch-isolation.log`.

## Complete boundary and categorical assignment gates, 8 October 2026

The direct boundary gate now requires 492 executed tests within 300 seconds.
Fresh native answers, all 466 numerical/input/drawing calls and a separately
saved producer reproduction passed together, followed by 559 affected tests in
122.988 seconds. The extra 60 mixed real/complex averaging comparisons are
supporting arithmetic controls and do not add a scientific implementation vote.
The saved preview uses the public package method and figure writer. Its exact
tables, statistics record, semantic marks and carrier binding reproduce in an
isolated workspace. The retained original extended loader hash was calculated
at run end; its explicit amendment prevents using it as an import-time identity.

The categorical assignment gate requires 875 executed tests within 600 seconds.
Its strict private qualification passed 864 complete tables and 536 existing
controls in 555 seconds, retaining 144 original indexed-image failures and the
first failed candidate. The installed method extracts indexed subject names
without mutating the source summary and preserves canonical missing object
labels. Full current installed replay remains required before its complete
functional assignment obligation can be enabled.

The existing 600-second utility gate retains every former test and adds 250
display-table, 18 exact geometry-storage and 67 mixed averaging controls,
requiring 2,005 passes. The existing 180-second architecture gate requires its
23 previously executed passes plus three real extension-policy child-process
controls. Existing test deadlines, scientific answers and application budgets
are unchanged. No generated verifier or lock file was edited.

The saved preview exposed two shared integration failures. The plot-that
adapter now validates an existing proof before updating its metadata, refreshes
the public evidence graph and supplies canonical reproduction command/output
fields; twelve affected adapter tests pass. ReproFig now copies declared flat
inputs as well as legacy data folders, verifies declared hashes, rejects path
escapes and links, and counts inputs cumulatively before producer execution;
nineteen affected reproduction tests pass. These repairs live in their owning
shared adapter/package. Current complete package, distribution and performance
certification remains required separately.
