import matplotlib
matplotlib.use("Agg")

from matplotlib import pyplot as plt

from PyFLASH.layout import apply_pyflash_layout


def test_pyflash_layout_lifts_polar_title_above_top_tick_label():
    fig, ax = plt.subplots(figsize=(4, 4), subplot_kw={"projection": "polar"})
    try:
        ax.set_theta_zero_location("N")
        ax.set_xticks([0])
        ax.set_xticklabels(["00:00"], fontsize=24)
        ax.set_title("Phase x Amplitude\nWatson-Williams p=0.000", pad=0, fontsize=16)

        apply_pyflash_layout(fig)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        title_bb = ax.title.get_window_extent(renderer)
        tick_bb = ax.get_xticklabels()[0].get_window_extent(renderer)

        assert title_bb.y0 > tick_bb.y1
    finally:
        plt.close(fig)
