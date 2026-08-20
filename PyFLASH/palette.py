"""Every colour PyFLASH names, and the only module that spells one out.

    from PyFLASH.palette import colour, condition_colour, declare_conditions

    colour("teal")                  # a house colour, by name
    declare_conditions(WT="teal", KO="#ff00aa")
    condition_colour("WT")          # -> the teal, because the project said so

Four tables, and they mean different things:

**house** are the figure's own colours — the reds, teals and oranges an audit
matrix or a scorecard is drawn in. They belong to the look, not to the data.

**pipeline** is the saturated palette a condition may be named from
(``color="dark_cyan"``). These are deliberately louder than the house colours:
they are read off a bar at a glance, not printed in a caption. Exposed as
``Config.COLORS`` for the fifteen years of scripts that spell it that way.

**auto** is the Okabe-Ito colourblind-safe set, used only when a condition was
never given a colour. A fallback, not a look.

**conditions** is not a table shipped here at all — it is whatever the current
project declares through :func:`declare_conditions`. The house palette is the
default, not a cage: which colour a genotype should be is a decision about the
science, and no package can make it. That override is reachable only through
:func:`condition_colour`, so declaring a condition named ``black`` changes that
condition and leaves every axis label alone.

``tests/test_style_conformance.py`` asserts that the house names here still
agree with ``analysis_kit.style`` where that package is installed, so the copy
the other lab projects share cannot drift away from this one unnoticed.
"""

from __future__ import annotations

from contextlib import contextmanager


__all__ = [
    "HOUSE",
    "PIPELINE",
    "AUTO",
    "AUTO_CYCLE",
    "GROUPS",
    "AUDIT_STATUS",
    "SCORECARD_GRADE",
    "MATRIX",
    "names",
    "colour",
    "color",
    "resolve",
    "audit_status_colors",
    "scorecard_grade_colors",
    "matrix_colors",
    "declare_conditions",
    "conditions",
    "clear_conditions",
    "condition_colour",
    "condition_color",
    "condition_context",
]


# ── the house colours ─────────────────────────────────────────────────────────
# Used by the significance-audit matrix, the readiness scorecard and the text
# drawn over a matrix cell. Muted on purpose: these end up in a figure legend.
HOUSE = {
    "red": "#c0392b",
    "teal": "#0e8f8f",
    "orange": "#d98a17",
    "blue": "#4878A8",
    "dark": "#303030",
    "black": "#000000",
    "white": "#ffffff",
    "blank": "#e6e6e6",       # an audit cell with nothing in it yet
    "nan_text": "#7A7A7A",    # text over an empty matrix cell
    "grade_green": "#2e7d32",
    "grade_grey": "#9e9e9e",
}


# ── the pipeline palette ──────────────────────────────────────────────────────
# Saturated, high-contrast, and named the way a bench scientist names a colour.
# Kept exactly as they have always been: these values are baked into figures
# going back years, and a condition that changes colour between two papers is
# worse than a condition drawn in an unfashionable green.
PIPELINE = {
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


# ── the auto-assignment set ───────────────────────────────────────────────────
# Okabe-Ito: eight colours that stay distinguishable under the common forms of
# colour blindness. Used when nobody named a colour, which is the one case where
# the choice is arbitrary and so should at least be safe.
AUTO = {
    "auto_orange": "#E69F00",
    "auto_sky_blue": "#56B4E9",
    "auto_bluish_green": "#009E73",
    "auto_yellow": "#F0E442",
    "auto_blue": "#0072B2",
    "auto_vermilion": "#D55E00",
    "auto_reddish_purple": "#CC79A7",
    "auto_black": "#000000",
}

AUTO_CYCLE = tuple(AUTO.values())


# Lookup order for `colour()`. House first: `colour("red")` is the figure red,
# the one an audit matrix cell is filled with.
GROUPS = {
    "house": HOUSE,
    "pipeline": PIPELINE,
    "auto": AUTO,
}

# Lookup order for `condition_colour()`, which is deliberately the other way
# round. `condition(..., color="red")` has always meant the loud pipeline red,
# and several thousand figures were drawn on that promise; a condition asking
# for red must not start coming out in the muted matrix red because a second
# table was added underneath it. Four names collide between the two tables —
# red, orange, blue, black — and this line is the whole reason they can.
_CONDITION_ORDER = ("pipeline", "house", "auto")


# Integer keys are status codes from plotting.py. Do not renumber them.
AUDIT_STATUS = {0: "blank", 1: "red", 2: "teal", 3: "orange"}

SCORECARD_GRADE = {
    "green": "grade_green",
    "amber": "orange",
    "red": "red",
    "grey": "grade_grey",
}

MATRIX = {
    "annotation": "black",
    "value": "black",
    "nan_text": "nan_text",
}


def names(group=None):
    """Every colour name, or every name in one group."""
    if group is None:
        return sorted({name for table in GROUPS.values() for name in table})
    if group not in GROUPS:
        raise KeyError(f"unknown colour group {group!r}; try one of {sorted(GROUPS)}")
    return sorted(GROUPS[group])


def colour(name, group=None):
    """The value behind a house colour name.

    Pass *group* to insist on one: ``colour("red", "pipeline")`` will not
    quietly hand back the muted house red.
    """
    if group is not None and group not in GROUPS:
        raise KeyError(f"unknown colour group {group!r}; try one of {sorted(GROUPS)}")
    tables = GROUPS if group is None else {group: GROUPS[group]}
    for table in tables.values():
        if name in table:
            return table[name]
    where = "" if group is None else f" in group {group!r}"
    raise KeyError(f"unknown colour {name!r}{where}; try one of {names(group)}")


#: American spelling, for code whose surrounding style uses it.
color = colour


def resolve(value):
    """A colour name resolved to its value; anything else returned untouched.

    Lets a caller accept either from a user without branching, so
    ``resolve("teal")`` and ``resolve("#0e8f8f")`` both work.
    """
    if isinstance(value, str):
        for table in GROUPS.values():
            if value in table:
                return table[value]
    return value


def _resolved(table):
    return {key: colour(value) for key, value in table.items()}


def audit_status_colors():
    """Overview status colours, keyed by the status code plotting.py uses."""
    return _resolved(AUDIT_STATUS)


def scorecard_grade_colors():
    """Readiness scorecard colours, keyed by grade name."""
    return _resolved(SCORECARD_GRADE)


def matrix_colors():
    """Text colours used over matrix cells."""
    return _resolved(MATRIX)


# ── project condition colours ─────────────────────────────────────────────────
_CONDITIONS = {}


def declare_conditions(mapping=None, **named):
    """Give condition names their colours, overriding the palette's own names.

    Values may be anything :func:`condition_colour` accepts — a palette name, a
    ``#rrggbb`` literal, or a matplotlib colour name — and are resolved once,
    here, so a bad one is caught at declaration rather than halfway through
    drawing a figure.

        declare_conditions({"Syn-mCherry": "dark_cyan", "hAPP": "#ff00aa"})

    Declaring the same name twice replaces it: re-declaring is how a run
    overrides the project default.
    """
    incoming = dict(mapping or {})
    incoming.update(named)
    for name, value in incoming.items():
        _CONDITIONS[str(name)] = _resolve_condition_value(value, str(name))
    return conditions()


def conditions():
    """The declared condition table, as a copy."""
    return dict(_CONDITIONS)


def clear_conditions():
    """Forget every declared condition colour."""
    _CONDITIONS.clear()


@contextmanager
def condition_context(mapping=None, **named):
    """Declare condition colours for one block, then put the table back."""
    previous = conditions()
    try:
        yield declare_conditions(mapping, **named)
    finally:
        _CONDITIONS.clear()
        _CONDITIONS.update(previous)


def _css_colour(value):
    """A matplotlib colour name as hex, or None if it is not one.

    Matplotlib is imported inside the function so importing the palette stays
    free for code that only wants to read a value.
    """
    try:
        from matplotlib import colors as mcolors
    except ImportError:
        return None
    try:
        return mcolors.to_hex(value)
    except (ValueError, TypeError):
        return None


def _resolve_condition_value(value, name):
    """One colour spec resolved without consulting the condition table.

    Separate from :func:`condition_colour` so that declaring a table cannot
    recurse through it: ``{"WT": "teal"}`` is a palette name and must resolve,
    ``{"WT": "WT"}`` must not quietly succeed.
    """
    if isinstance(value, str):
        for group in _CONDITION_ORDER:
            if value in GROUPS[group]:
                return GROUPS[group][value]
        if value.startswith("#"):
            return value
        converted = _css_colour(value)
        if converted is not None:
            return converted
        raise KeyError(
            f"condition {name!r} was given colour {value!r}, which is neither a "
            f"PyFLASH colour name, a #rrggbb value, nor a matplotlib colour name"
        )
    return value


def condition_colour(name, index=0, strict=False):
    """The colour for one experimental condition.

    Resolution order, first hit wins:

    1. ``None`` — auto-assign from the Okabe-Ito set by *index*, so an unnamed
       condition still gets a colour a colourblind reader can tell apart.
    2. A name this project declared through :func:`declare_conditions`.
    3. A palette name — house first, then the pipeline palette.
    4. A ``#rrggbb`` literal, or any matplotlib colour name.

    Anything else is handed back untouched, so a caller may still pass an RGBA
    tuple or a colormap position the palette has no opinion about. Pass
    ``strict=True`` to turn an unrecognised name into a ``KeyError`` instead of
    letting it surface as a matplotlib error much later, with no mention of the
    condition it came from.
    """
    if name is None:
        return AUTO_CYCLE[int(index) % len(AUTO_CYCLE)]

    if isinstance(name, str):
        declared = _CONDITIONS.get(name)
        if declared is not None:
            return declared
        for group in _CONDITION_ORDER:
            if name in GROUPS[group]:
                return GROUPS[group][name]
        if name.startswith("#"):
            return name
        converted = _css_colour(name)
        if converted is not None:
            return converted
        if strict:
            raise KeyError(
                f"unknown condition colour {name!r}; declared conditions are "
                f"{sorted(_CONDITIONS)}, or use a palette name from {names()}"
            )
    return name


#: American spelling, matching :data:`color`.
condition_color = condition_colour
