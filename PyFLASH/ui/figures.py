"""Figure embedding helpers for the UI (stub).

PyFLASH ``plot_*`` functions save high-DPI SVG/PNG to disk under
``batch.fig_path`` (gated by ``Config.SAVE_MODE``). The UI strategy is to run a
plot with saving enabled and then embed the saved file rather than assume a
``Figure`` object is returned.

TODO (Stage 07): implement embedding — locate the latest saved figure for a
plot, render SVG/PNG inline (e.g. ``st.image`` for PNG, raw SVG markup for
SVG), and expose a download button. Kept Streamlit-free where possible so the
file-resolution logic stays unit-testable; any ``streamlit`` import added later
belongs in the rendering helper only.
"""

__all__: list = []

# Intentionally empty until Stage 07.
