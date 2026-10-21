# Reproduce and verify an analysis

PyFLASH keeps a runnable verification workflow in the repository's
`reproducibility/` directory. From a checkout:

```bash
python -m pip install -e ".[ui]" -r reproducibility/requirements.txt -r reproducibility/requirements-workflow.txt
python -m reproducibility.run --full --require-complete
```

Each pass receives a new timestamped output directory with frozen source copies,
input and output hashes, package versions, parameters, logs, paired reference
values and a human-readable `DIFFERENCES.md`. Failed passes are preserved.
The full workflow also runs the supplied numerical demo, the README example,
the unchanged UI-exported script in a fresh process, every package test,
strict documentation and distribution builds, and real browser and layout checks.
Browser checks require Microsoft Edge and the installed software-development
skill's layout measurement script. Missing prerequisites fail their stage.

## What the scientific checks establish

Independently frozen contracts cover Student/Welch statistics and probabilities,
selected effect sizes, five multiple-testing corrections, fixed-period cosinor
coefficients, uncertainty and full predictions, and analytic bootstrap interval
endpoints with identical retained subject-resampling draws. Comparisons disclose
shared upstream libraries separately from independent implementations and formulas.

These are limited contracts. They do not establish independent correctness for
every plot, pipeline, scientific coordinate, annotation, option or microscopy
processing step. The scientific-completeness gate returns a failing exit code
while any complete contract is missing, even when all executed comparisons agree.
Read `capabilities.csv` and `outcome-grid.csv` beside the differences report.

## Replay and recovery

Browser results export scripts with verified input and scientific-code hashes,
effective configuration and package identity. Subject bootstrap uncertainty uses
a deterministic default seed (`Config.EFFECT_CI_RANDOM_STATE = 0`); callers can
override it explicitly. A changed seed is a changed analysis setting.

`PyFLASH.run_spec_queue(data, spec_path, progress_path)` validates a whole
registered batch before work begins, records successes and isolated failures,
and can retry unfinished entries without rerunning verified completed calls.
It resumes between calls, not inside a statistical algorithm. Preserve the
progress file, result directory and end-of-run summary together. Load only
trusted local saved objects.

The installable `pyflash-run` command exposes `describe`, `doctor`, `validate`,
`run` and `queue` over the same plot and helper registries used by the browser.
Saved analysis states and project descriptions have schema versions; interrupted
atomic writes preserve their previous file, and unsupported future schemas fail
explicitly.
