import matplotlib

matplotlib.use("Agg")

from matplotlib import colors as mcolors
import pandas as pd

import PyFLASH.plotting as plotting
from PyFLASH import from_dataframe


GROUP_COLORS = {
    "Control": "#315a9b",
    "AD": "#b13b36",
}


def _summary_frame():
    return pd.DataFrame({
        "Subject": ["C1", "C2", "C3", "A1", "A2", "A3"],
        "Group": ["Control", "Control", "Control", "AD", "AD", "AD"],
        "Phase": ["Day", "Night", "Day", "Day", "Night", "Day"],
        "X": [1.0, 1.5, 2.0, 4.0, 4.5, 5.0],
        "X2": [2.0, 2.4, 2.8, 6.0, 6.4, 6.8],
        "Y": [1.2, 1.7, 2.1, 3.8, 4.6, 5.2],
    })


def _experiment(tmp_path, *, multi_roi=False):
    frame = _summary_frame()
    kwargs = {}
    if multi_roi:
        kwargs["summaries"] = {
            "SCN": frame,
            "PVN": frame.assign(Y=frame["Y"] + 0.25),
        }
    return from_dataframe(
        frame,
        group_col="Group",
        subject_col="Subject",
        group_order=["Control", "AD"],
        group_colors=GROUP_COLORS,
        fig_path=tmp_path,
        **kwargs,
    )


def _capture_saved_figures(monkeypatch):
    figures = []

    def capture(fig, *_args, **_kwargs):
        figures.append(fig)

    monkeypatch.setattr(plotting, "save_fig", capture)
    return figures


def test_regression_marginals_default_off_keeps_single_axis(tmp_path, monkeypatch):
    experiment = _experiment(tmp_path)
    figures = _capture_saved_figures(monkeypatch)

    plotting.plot_regressions(
        experiment, x="X", y="Y",
        normalize_x=False, normalize_y=False,
    )

    assert len(figures) == 2
    assert [len(fig.axes) for fig in figures] == [1, 1]
    for fig in figures:
        ax = fig.axes[0]
        assert ax.get_box_aspect() == 1
        texts = [t.get_text() for t in ax.texts]
        # All regression stats live on-graph now: one colour-matched line per
        # group (r + significance + p) plus a muted test caption. Nothing is
        # stranded in an outside right-margin block, so every text is anchored
        # to a left/right axes corner (x in {0.02, 0.98}).
        assert any("r =" in t and "p =" in t for t in texts)
        assert any(t.startswith("Test:") for t in texts)
        assert all(t.get_position()[0] in (0.02, 0.98) for t in ax.texts)


def test_regression_square_axes_can_be_disabled(tmp_path, monkeypatch):
    experiment = _experiment(tmp_path)
    figures = _capture_saved_figures(monkeypatch)

    plotting.plot_regressions(
        experiment, x="X", y="Y", combine=True, square=False,
        normalize_x=False, normalize_y=False,
    )

    assert len(figures) == 1
    assert figures[0].axes[0].get_box_aspect() is None


def test_regression_marginals_add_shared_axes_per_group(tmp_path, monkeypatch):
    experiment = _experiment(tmp_path)
    figures = _capture_saved_figures(monkeypatch)

    plotting.plot_regressions(
        experiment, x="X", y="Y", marginal_hist=True,
        normalize_x=False, normalize_y=False,
    )

    assert len(figures) == 2
    for fig in figures:
        assert len(fig.axes) == 3
        main_ax, top_ax, right_ax = fig.axes
        assert main_ax.get_shared_x_axes().joined(main_ax, top_ax)
        assert main_ax.get_shared_y_axes().joined(main_ax, right_ax)
        assert top_ax.patches
        assert right_ax.patches
        texts = [t.get_text() for t in main_ax.texts]
        assert any("r =" in t and "p =" in t for t in texts)
        assert any(t.startswith("Test:") for t in texts)
        assert all(t.get_position()[0] in (0.02, 0.98) for t in main_ax.texts)


def test_combined_regression_marginals_use_group_colours(tmp_path, monkeypatch):
    experiment = _experiment(tmp_path)
    figures = _capture_saved_figures(monkeypatch)

    plotting.plot_regressions(
        experiment, x="X", y="Y", combine=True, marginal_hist=True,
        normalize_x=False, normalize_y=False,
    )

    assert len(figures) == 1
    main_ax, top_ax, right_ax = figures[0].axes
    assert main_ax.get_shared_x_axes().joined(main_ax, top_ax)
    assert main_ax.get_shared_y_axes().joined(main_ax, right_ax)
    texts = [t.get_text() for t in main_ax.texts]
    assert any("r =" in t and "p =" in t for t in texts)
    assert any(t.startswith("Test:") for t in texts)
    expected = {mcolors.to_rgba(color)[:3] for color in GROUP_COLORS.values()}
    top_colors = {patch.get_facecolor()[:3] for patch in top_ax.patches}
    right_colors = {patch.get_facecolor()[:3] for patch in right_ax.patches}
    assert expected <= top_colors
    assert expected <= right_colors


def test_regression_marginals_forward_through_all_queues(tmp_path, monkeypatch):
    experiment = _experiment(tmp_path, multi_roi=True)
    figures = _capture_saved_figures(monkeypatch)

    result = plotting.plot_regressions(
        experiment,
        x=["X", "X2"],
        y="Y",
        specificity=[("Phase", "Day"), ("Phase", "Night")],
        combine=True,
        marginal_hist=True,
        normalize_x=False,
        normalize_y=False,
    )

    assert set(result) == {"SCN", "PVN"}
    for roi_result in result.values():
        assert set(roi_result) == {("X", "Y"), ("X2", "Y")}
        for pair_result in roi_result.values():
            assert set(pair_result) == {
                ("Phase", "Day"),
                ("Phase", "Night"),
            }
    assert len(figures) == 8
    assert all(len(fig.axes) == 3 for fig in figures)
