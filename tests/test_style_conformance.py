"""PyFLASH owns the house style; the shared kit carries a copy. This pins them.

PyFLASH is a published package and must stay installable by someone who has
never heard of ``analysis-kit`` — so it imports nothing from it, and
``PyFLASH.palette`` / ``PyFLASH.aesthetics`` are the real source of truth for
what a figure looks like. The other lab projects (CircadianWorkbench, the
microglia protocols) share a copy of those numbers through ``analysis_kit``.

Two copies of anything drift. That is exactly how the same red ended up typed
into four files three different ways, which is what started this work. These
tests are the thing that makes the copy safe: where both packages are installed
they must agree, key for key and value for value, or this suite goes red.

Every test here skips cleanly when ``analysis-kit`` is absent, because its
absence is a supported way to run PyFLASH rather than a fault.
"""

from __future__ import annotations

import pytest

from PyFLASH import aesthetics, palette


kit_style = pytest.importorskip(
    "analysis_kit.style",
    reason="analysis-kit is an optional extra; PyFLASH stands alone without it",
)


# ── PyFLASH's own palette is internally sound ─────────────────────────────────
def test_only_the_palette_module_spells_a_colour_out():
    """The rule that stops a fifth divergent red appearing.

    Scoped to the modules the palette actually covers. ``plotting.py`` still
    holds per-plot decoration colours and is deliberately not swept here — a
    hundred-odd literals inside f-strings is a separate job with its own
    regression risk, not something to smuggle into a style change.
    """

    import ast
    import re
    from pathlib import Path

    hex_literal = re.compile(r"^#[0-9a-fA-F]{6}$")
    source = Path(aesthetics.__file__).resolve().parent
    covered = ("aesthetics.py", "config.py", "conditions.py")

    def spelled_in_code(path):
        """Hex values in real code, ignoring docstrings.

        Parsed rather than grepped: ``"#ff0000"`` inside a docstring is the
        module *explaining* the convention, and banning that would push the
        documentation out of the module it documents.
        """

        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            node.body[0].value
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        return [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node not in docstrings
            and hex_literal.match(node.value)
        ]

    offenders = {
        name: found
        for name in covered
        if (found := spelled_in_code(source / name))
    }
    assert offenders == {}, f"hard-coded colours outside PyFLASH.palette: {offenders}"


def test_a_condition_named_red_still_gets_the_loud_red():
    """Four names live in both tables. A condition asking for one of them has
    always meant the pipeline value, and thousands of figures were drawn on
    that promise."""

    for name in ("red", "orange", "blue", "black"):
        assert palette.condition_colour(name) == palette.PIPELINE[name]
        assert palette.colour(name) == palette.HOUSE[name]


def test_an_unnamed_condition_gets_a_colourblind_safe_colour():
    assert palette.condition_colour(None, 0) == palette.AUTO_CYCLE[0]
    # Wraps rather than running out: a design with nine groups still draws.
    assert palette.condition_colour(None, len(palette.AUTO_CYCLE)) == palette.AUTO_CYCLE[0]


def test_a_declared_condition_overrides_the_palette_but_not_the_figure():
    """The whole point of the override, and its one limit."""

    with palette.condition_context({"black": "#ff00aa"}):
        assert palette.condition_colour("black") == "#ff00aa"
        # ...and the ink a matrix annotation is drawn in is untouched.
        assert palette.colour("black") == palette.HOUSE["black"]
    assert palette.condition_colour("black") == palette.PIPELINE["black"]


def test_a_condition_colour_that_is_nonsense_can_be_made_loud():
    with pytest.raises(KeyError):
        palette.condition_colour("chartreuseish", strict=True)
    # Non-strict is the default and hands it back, because a caller may pass an
    # RGBA tuple or a colormap position the palette has no opinion about.
    assert palette.condition_colour("chartreuseish") == "chartreuseish"


# ── the pickles' condition colours must never move ────────────────────────────
# The one guarantee that outranks every other thing in this file.
#
# A condition's colour is resolved once, when the condition is built, and then
# pickled onto the object. Twenty-six of the twenty-seven conditions across
# Jamie's five batches are frozen `#rrggbb` and no palette change can reach
# them. One — "black", in CK1I.pkl — is stored as a *name*, and a name is
# re-resolved every time the batch is plotted. So the rule is not "do not
# change the palette"; it is "a name that a pickle may hold must always resolve
# to the value it resolved to when that pickle was written".
#
# These tests are what make that survive somebody tidying the palette in a
# year's time, when nobody remembers CK1I holds a name.
PICKLED_CONDITION_COLOURS = {
    # Exactly as `Config.COLORS` has always been. Any condition ever created
    # from one of these names carries the value on the right.
    "red": "#ff0000",
    "cyan": "#42f5f5",
    "dark_cyan": "#0e3231",
    "dark_red": "#240004",
    "orange": "#ff8400",
    "blue": "#40ffff",
    "dark_blue": "#03358c",
    "magenta": "#ff47f0",
    "dark_magenta": "#8a2481",
    "green": "#00ff00",
    "dark_green": "#002404",
    "yellow": "#FFFB83",
    "dark_yellow": "#414100",
    "grey": "#d4d4d4",
    "dark_grey": "#d4d4d4",
    "black": "#000000",
    "purple": "#4d0254",
}


@pytest.mark.parametrize("name,expected", sorted(PICKLED_CONDITION_COLOURS.items()))
def test_a_condition_colour_name_a_pickle_may_hold_never_moves(name, expected):
    """The guarantee, one name at a time so a failure says which one."""

    assert palette.condition_colour(name) == expected


def test_the_pipeline_palette_is_complete_and_unchanged():
    """A name removed from the table is as bad as one whose value moved: the
    stored name would fall through to a matplotlib colour, or to nothing."""

    assert palette.PIPELINE == PICKLED_CONDITION_COLOURS


def test_the_house_palette_cannot_shadow_a_stored_condition_name():
    """`red`, `orange`, `blue` and `black` exist in both tables. The pickled
    meaning must win for a condition, whatever the house palette does."""

    for name in set(palette.HOUSE) & set(palette.PIPELINE):
        assert palette.condition_colour(name) == palette.PIPELINE[name], (
            f"the house palette has captured {name!r}; a pickled condition "
            "named that would change colour"
        )


def test_a_declared_override_still_cannot_reach_a_stored_name_by_accident():
    """Declaring conditions is deliberate. It should win — that is the point —
    but only for the names actually declared, never as a side effect."""

    with palette.condition_context({"WT": "#00ff00"}):
        assert palette.condition_colour("WT") == "#00ff00"
        assert palette.condition_colour("black") == PICKLED_CONDITION_COLOURS["black"]


# ── PyFLASH and the shared kit still agree ────────────────────────────────────
def test_the_shared_kit_reproduces_this_projects_rcparams_key_for_key():
    """The kit's ``pyflash`` theme is a copy of the numbers in aesthetics.py.
    If either moves without the other, a CircadianWorkbench figure and a
    PyFLASH figure stop looking like each other."""

    ours = aesthetics._matplotlib_rc_updates()
    theirs = kit_style.rcparams("pyflash")

    assert set(ours) == set(theirs), {
        "only in PyFLASH": sorted(set(ours) - set(theirs)),
        "only in the kit": sorted(set(theirs) - set(ours)),
    }

    def same(key):
        left, right = ours[key], theirs[key]
        if key == "figure.figsize":
            return tuple(left) == tuple(right)
        return left == right

    differences = {key: (ours[key], theirs[key]) for key in sorted(ours) if not same(key)}
    assert differences == {}, differences


@pytest.mark.parametrize("name", sorted(palette.HOUSE))
def test_every_house_colour_the_kit_also_names_has_the_same_value(name):
    """Name-by-name rather than as one blob, so a failure says which colour."""

    from analysis_kit.style import palette as kit_palette

    try:
        theirs = kit_palette.colour(name)
    except KeyError:
        pytest.skip(f"the kit does not carry {name!r}")
    assert palette.HOUSE[name] == theirs


def test_the_two_auto_assignment_sets_are_the_same_colours_in_the_same_order():
    """An unnamed condition must land on the same colour in either package, or
    the same experiment plotted through two projects comes out different."""

    from analysis_kit.style import palette as kit_palette

    assert list(palette.AUTO_CYCLE) == kit_palette.cycle("okabe")


def test_the_status_and_grade_tables_match_the_kits():
    from analysis_kit.style import palette as kit_palette

    assert palette.audit_status_colors() == kit_palette.audit_status_colors()
    assert palette.scorecard_grade_colors() == kit_palette.scorecard_grade_colors()
    assert palette.matrix_colors() == kit_palette.matrix_colors()


def test_a_figure_drawn_through_this_project_passes_the_kits_conformance_check():
    """Check the output, not just the constants.

    Every other test here asks whether two tables of numbers still agree. None
    of them asks whether a figure PyFLASH actually draws *comes out* right —
    and that is the failure somebody would notice, because it is the one you
    can see.

    The route matters: the style is applied through PyFLASH's own front door,
    ``apply_pyflash_matplotlib_style``, not through the kit's ``apply``. That
    is what makes this a test of this project rather than of the kit. If
    PyFLASH's application path ever stops setting what its own style declares,
    this goes red even though every value in both tables is still correct.

    Borrowed from PyMicroglia, which had this and the other two consumers did
    not.
    """

    from analysis_kit.style import conformance

    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    from PyFLASH.aesthetics import apply_pyflash_matplotlib_style

    with plt.rc_context():
        apply_pyflash_matplotlib_style()
        figure, axes = plt.subplots()
        try:
            axes.plot([0, 1, 2], [0, 1, 0], color=palette.colour("teal"))
            axes.set_xlabel("weeks")
            axes.set_ylabel("IntDen / 0.1mm3")
            axes.set_title("conformance probe")
            conformance.assert_conformant(figure=figure, name="pyflash")
        finally:
            plt.close(figure)


def test_the_shared_style_is_conformant_in_its_own_right():
    """The kit's own check, run from here so a drift in the shared package
    fails PyFLASH's suite rather than being noticed in a figure months later."""

    from analysis_kit.style import conformance

    report = conformance.run(live=False)
    assert report["ok"], report["problems"]
