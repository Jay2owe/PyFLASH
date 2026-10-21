# Scientific reproducibility checks

Run from the checkout root:

```powershell
python -m pip install -e ".[ui]" -r reproducibility/requirements.txt -r reproducibility/requirements-workflow.txt
python -m reproducibility.run --full --require-complete
```

The numerical comparisons cover Student/Welch tests (statistics, probabilities
and degrees of freedom), Cohen/Hedges effects, pairwise rank effects, five
multiple-testing corrections (full arrays, missingness and rejection decisions),
and fixed-period cosinor (coefficients, uncertainty, significance and complete
predictions on sparse noisy observations). Fixtures are generated only from
independent references and analytic implementations. They never come from PyFLASH.
An additional, separately frozen analytic benchmark checks subject-level BCa
(bias-corrected and accelerated) interval endpoints for two effect sizes, unequal
groups and ties, with two confidence levels and retained identical resampling draws.

The extended references also check Pearson/Spearman correlation-difference
probabilities for all four tails, asymmetric correlation-difference intervals,
Cauchy probability combinations, ANOVA effects, intraclass correlation,
finite-value outlier bounds and complete modified-z arrays. Circular comparisons
cover descriptive means/resultants for 12- and 24-unit cycles, rather than
Rayleigh significance. The noisy linear growth fit checks both coefficients,
their standard errors, fit statistics and every prediction against Statsmodels
and an independent 50-digit analytic solver. All 141 comparisons use the original
relative 1e-9 / absolute 1e-12 tolerance. Additional reference fixtures preserve
the earlier fixtures and cannot overwrite them.

The complete scientific-coverage gate currently fails: these subroutines do not
establish complete agreement for every plot, pipeline, option, annotation or
scientific array. The runner inventories public scientific callables and every
registered plot/pipeline with their full signatures and available integration
tests. That inventory and missing coverage are part of every outcome grid.

Each timestamped pass under `results/` retains source snapshots, hashes, exact
paired values, versions, commit and dirty-tree state, stage logs, browser
screenshots, a numerical gate, a workflow gate, and a separate scientific
completeness gate. Start with that pass's `DIFFERENCES.md`, then `run.json`.
Failed and successful passes are preserved side by side. See [WORKFLOW.md](WORKFLOW.md).
The full pass executes the unchanged browser-exported script in a fresh process
and compares every returned cell and every complete statistical report field.

Full browser checks use an installed Microsoft Edge browser. Layout measurement
also uses the software-development skill's `scripts/layout-audit.py` under
`~/.claude/skills/software-development/`; an absent tool is recorded as a failed
unavailable stage. These checks are not claimed portable without those prerequisites.
On Windows Store Python, distribution builds use uv's isolated environment to
avoid the Store activation alias in build-created virtual environments. The
recorded command identifies this packaging route; numerical checks keep the
original interpreter and dependencies.

Browser budgets use the ordinary `pyflash-ui` analysis launch. Its source watcher
is disabled so imported-file scanning cannot block asset delivery. The separate
`pyflash-ui --dev -- --demo` launch enables reload after editing source; its timing
is not substituted for the ordinary launch's measured boundary.

Reference documentation: [Statsmodels independent t-test](https://www.statsmodels.org/stable/generated/statsmodels.stats.weightstats.ttest_ind.html),
[SciPy false-discovery control](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html),
[Pingouin effect sizes](https://pingouin-stats.org/build/html/generated/pingouin.compute_effsize.html).
The exact executed versions are pinned in `requirements.txt` and the frozen
fixture; references are optional verification tools, not production dependencies.

Extended definitions: [NIST modified z-score](https://itl.nist.gov/div898/handbook/eda/section3/eda35h.htm),
[Statsmodels ordinary least squares](https://www.statsmodels.org/stable/regression.html),
[Pingouin circular means](https://pingouin-stats.org/generated/pingouin.circ_mean.html).
