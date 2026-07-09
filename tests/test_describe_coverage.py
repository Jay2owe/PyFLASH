"""Forcing function for describe-layer maintenance.

The structured-results ("describe") layer captures the numbers a plot computes so
an agent can answer questions without OCR-ing the figure. Coverage rots silently
as plots are added: a new plot that computes stats inline but never emits to
PyFLASH.report produces a figure with an empty results manifest, and nobody
notices.

These tests make that impossible to miss: every PLOT_REGISTRY entry must be
explicitly classified (covered / exempt / unreviewed) in PyFLASH.spec. A newly
added plot fails `test_every_registered_plot_is_classified` until its author makes
a conscious describe-layer decision. See spec.DESCRIBE_* and CLAUDE.md.
"""

import PyFLASH.spec as spec


def test_every_registered_plot_is_classified():
    registry = set(spec.PLOT_REGISTRY)
    classified = (
        spec.DESCRIBE_COVERED | spec.DESCRIBE_EXEMPT | spec.DESCRIBE_UNREVIEWED
    )
    missing = registry - classified
    assert not missing, (
        f"New plot(s) {sorted(missing)} have no describe-layer status. Add each to "
        "spec.DESCRIBE_COVERED (it emits to PyFLASH.report via the shared stats "
        "engine / report.emit / a pipeline return manifest), DESCRIBE_EXEMPT (a pure "
        "visualisation with no inferential result to capture), or DESCRIBE_UNREVIEWED "
        "(computes a result not yet wired). See CLAUDE.md / the pyflash-add-plot skill."
    )
    stale = classified - registry
    assert not stale, (
        f"describe-status name(s) {sorted(stale)} are not in PLOT_REGISTRY — remove "
        "them or fix the short-name."
    )


def test_describe_sets_are_disjoint():
    c, e, u = spec.DESCRIBE_COVERED, spec.DESCRIBE_EXEMPT, spec.DESCRIBE_UNREVIEWED
    assert not (c & e), f"covered & exempt overlap: {sorted(c & e)}"
    assert not (c & u), f"covered & unreviewed overlap: {sorted(c & u)}"
    assert not (e & u), f"exempt & unreviewed overlap: {sorted(e & u)}"


def test_describe_status_helper():
    assert spec.describe_status('mean_bars') == 'covered'
    assert spec.describe_status('images') == 'exempt'
    assert spec.describe_status('volcano') == 'unreviewed'
    assert spec.describe_status('definitely_not_a_plot') == 'unclassified'


def test_known_covered_plots_stay_covered():
    # These have verified emit paths; guard against silent declassification.
    for name in ('mean_bars', 'regressions',
                 'correlation_pipeline', 'adjusted_correlation_pipeline',
                 'linear_model_pipeline'):
        assert name in spec.PLOT_REGISTRY
        assert spec.describe_status(name) == 'covered'
