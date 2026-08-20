"""
Experimental condition classes and helpers.
"""

import difflib
from collections import OrderedDict
from functools import reduce

from PyFLASH import palette as _palette


# Okabe-Ito colorblind-safe palette for auto-assignment. The values live in
# PyFLASH.palette; this name is kept because it is what the tests and a few
# scripts reach for.
_AUTO_PALETTE = list(_palette.AUTO_CYCLE)

# A condition's *style* is its second visual channel, alongside ``color``.
# ``"fill"`` is the default solid bar; ``"hollow"`` draws an outline only; any
# other token is treated as a matplotlib hatch pattern (e.g. ``"///"``). Colour
# is the *primary* factor's channel; style lets the *secondary* factor of a
# crossed design read distinctly even when two bars share a colour.
DEFAULT_STYLE = "fill"


def _derive_multi_style(conditions_list):
    """Style for a crossed condition: the first non-default component style.

    Colour comes from the primary (first) component, so style mirrors that by
    taking the first component that *declares* a non-default style. This lets a
    style authored on the **secondary** factor (e.g. ``Female="hollow"``) flow
    through to every cross that contains it, while a fully default design stays
    ``"fill"`` and is differentiated later by collision detection at plot time.
    """
    for cond in conditions_list:
        style = getattr(cond, "style", DEFAULT_STYLE)
        if style and style != DEFAULT_STYLE:
            return style
    return DEFAULT_STYLE


def _resolve_color(color, index=0):
    """Resolve a color name, hex string, or None to a hex color.

    - None → auto-assign from ``_AUTO_PALETTE`` by *index*
    - A name this project declared via ``palette.declare_conditions`` → its value
    - A key in ``Config.COLORS`` (e.g. ``"red"``, ``"dark_cyan"``) → its hex value
    - A CSS/matplotlib color name (e.g. ``"steelblue"``) → converted to hex
    - An existing hex string (e.g. ``"#ff0000"``) → passed through unchanged

    The lookup itself lives in :func:`PyFLASH.palette.condition_colour`, which
    is the public form of this and the one a project overrides.
    """
    return _palette.condition_colour(color, index)


class condition:
    """A single experimental condition (e.g. one genotype or treatment)."""

    def __init__(self, label, name, color, factor, explanation=None,
                 style=DEFAULT_STYLE):
        self.label = label
        self.name = name
        self.color = color
        self.style = style or DEFAULT_STYLE
        self.factor = factor
        self.factor_explanation = (
            explanation.replace("<>", self.label) if explanation is not None else None
        )


class multiCondition:
    """A compound condition formed by crossing two or more single conditions."""

    def __init__(self, conditionsList, name=None, label=None, color=None,
                 style=None):
        self.conditionsList = conditionsList
        self.name = (
            reduce(lambda a, b: a.name + b.name, conditionsList)
            if name is None else name
        )
        self.label = (
            reduce(lambda a, b: a.label + b.label, conditionsList)
            if label is None else label
        )
        self.color = conditionsList[0].color if color is None else color
        # Colour is inherited from the primary (first) component; style mirrors
        # that by deriving from the first component with a non-default style, so
        # the secondary factor can carry the second visual channel.
        self.style = _derive_multi_style(conditionsList) if style is None else style
        self.factor = [c.factor for c in conditionsList]
        self.factor_explanation = [c.factor_explanation for c in conditionsList]


class conditionList:
    """An ordered list of conditions with comparison pairs and factor info."""

    def __init__(self, condition_list, comparisons=None, explanation=None):
        self.condition_list = condition_list
        self.comparisons = comparisons
        self.conditions = []
        for cond in self.condition_list:
            if isinstance(cond, multiCondition):
                self.conditions.extend(cond.conditionsList)
            else:
                self.conditions.append(cond)

        self.factor = condition_list[0].factor
        if not isinstance(self.factor, list):
            self.factor = [self.factor]

        self.factorDict = {f: [] for f in self.factor}
        for cond in self.conditions:
            if cond not in self.factorDict[cond.factor]:
                self.factorDict[cond.factor].append(cond)
            if explanation is not None:
                cond.factor_explanation = explanation.replace("<>", cond.label)

    def __iter__(self):
        return iter(self.condition_list)

    def __getitem__(self, index):
        return self.condition_list[index]

    def __len__(self):
        return len(self.condition_list)


def zipConditionLists(condition_list1, condition_list2, newColors=None):
    """Cross two condition lists into multiCondition tuples."""
    result = []
    i = 0
    for c1 in condition_list1.condition_list:
        for c2 in condition_list2.condition_list:
            color = None if newColors is None else newColors[i]
            result.append(multiCondition([c1, c2], color=color))
            i += 1
    return tuple(result)


def zipConditions(condition_labels, condition_names, condition_colors, factor):
    """Create a tuple of condition objects from parallel lists."""
    return tuple(
        condition(condition_labels[i], name, condition_colors[i], factor)
        for i, name in enumerate(condition_names)
    )


# ── Fluent builder ─────────────────────────────────────────────────────


class ConditionBuilder:
    """Fluent API for building condition lists.

    Usage::

        conditions = (
            ConditionBuilder("Genotype")
            .add("Syn-mCherry", short="Syn", color="red")
            .add("hAPP-mCherry", short="hAPP")          # color auto-assigned
            .compare_all_pairs()
            .explain("WT mice injected with <> at 2 months.")
            .build()
        )
        Syn, hAPP = conditions  # unpack works (conditionList is iterable)

    Produces the same ``conditionList`` / ``condition`` objects the
    pipeline already expects.  The old API (``zipConditions`` etc.) is
    unchanged and still works.
    """

    def __init__(self, factor):
        self._factor = factor
        self._entries = []          # [{label, short, color}, ...]
        self._comparisons = []      # sentinel tuples resolved at build()
        self._explanation = None

    # ── adding conditions ──────────────────────────────────────────

    def add(self, label, short=None, color=None, style=DEFAULT_STYLE):
        """Append a condition.

        Parameters
        ----------
        label : str
            Full display name (appears on plots / stats tables).
        short : str, optional
            Shorthand used in filenames and raw data.  Defaults to
            ``label.strip()``.
        color : str or None
            Hex (``"#ff0000"``), a ``Config.COLORS`` key (``"red"``),
            a matplotlib CSS name (``"steelblue"``), or ``None`` to
            auto-assign from the Okabe-Ito palette.
        style : str
            Second visual channel for bars: ``"fill"`` (default solid),
            ``"hollow"`` (outline only), or any matplotlib hatch pattern
            (e.g. ``"///"``).  Set this on the *secondary* factor of a
            crossed design to distinguish bars that share a colour; left
            at ``"fill"`` it is resolved automatically at plot time.
        """
        if short is None:
            short = label.strip()
        self._entries.append(
            dict(label=label, short=short, color=color, style=style or DEFAULT_STYLE)
        )
        return self

    # ── comparisons ────────────────────────────────────────────────

    def compare(self, a, b):
        """Compare two conditions by shorthand name."""
        self._comparisons.append(('__PAIR__', a, b))
        return self

    def compare_all_pairs(self):
        """Add every pairwise comparison (Tukey-style)."""
        self._comparisons.append(('__ALL_PAIRS__',))
        return self

    def compare_to_control(self, control):
        """Compare every other condition to *control* (Dunnett-style)."""
        self._comparisons.append(('__VS_CONTROL__', control))
        return self

    def compare_sequential(self):
        """Compare each condition to the next (1v2, 2v3, …)."""
        self._comparisons.append(('__SEQUENTIAL__',))
        return self

    # ── explanation ─────────────────────────────────────────────────

    def explain(self, explanation):
        """Set the explanation template (``<>`` is replaced with each label)."""
        self._explanation = explanation
        return self

    # ── build ──────────────────────────────────────────────────────

    def build(self):
        """Return a ``conditionList`` from the accumulated entries."""
        if not self._entries:
            raise ValueError("No conditions added — call .add() before .build()")

        conditions_out = []
        for i, entry in enumerate(self._entries):
            color = _resolve_color(entry['color'], i)
            conditions_out.append(
                condition(entry['label'], entry['short'], color, self._factor,
                          style=entry.get('style', DEFAULT_STYLE))
            )

        names = [e['short'] for e in self._entries]
        comparisons = _resolve_comparisons(self._comparisons, names)

        return conditionList(conditions_out, comparisons,
                             explanation=self._explanation)

    # ── crossing ───────────────────────────────────────────────────

    @classmethod
    def cross(cls, condition_list1, condition_list2, colors=None):
        """Create a crossed (factorial) design from two ``conditionList`` objects.

        Returns a ``_CrossedConditionBuilder`` for further chaining.
        """
        return _CrossedConditionBuilder(condition_list1, condition_list2, colors)


# ── Helpers shared by both builders ────────────────────────────────────


def _find_index(name, name_to_idx):
    """Look up a 1-based index by condition shorthand, with fuzzy suggestions."""
    if name in name_to_idx:
        return name_to_idx[name]
    matches = difflib.get_close_matches(name, name_to_idx.keys(), n=1, cutoff=0.5)
    suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
    raise ValueError(
        f"Condition '{name}' not found.{suggestion} "
        f"Available: {list(name_to_idx.keys())}"
    )


def _resolve_comparisons(comparison_specs, names):
    """Turn sentinel tuples into ``'1-2'`` index strings."""
    if not comparison_specs:
        return None

    name_to_idx = {n: i + 1 for i, n in enumerate(names)}
    resolved = []

    for spec in comparison_specs:
        tag = spec[0]

        if tag == '__ALL_PAIRS__':
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    resolved.append(f'{i + 1}-{j + 1}')

        elif tag == '__VS_CONTROL__':
            ctrl = _find_index(spec[1], name_to_idx)
            for i in range(len(names)):
                if i + 1 != ctrl:
                    resolved.append(f'{ctrl}-{i + 1}')

        elif tag == '__SEQUENTIAL__':
            for i in range(len(names) - 1):
                resolved.append(f'{i + 1}-{i + 2}')

        elif tag == '__PAIR__':
            idx_a = _find_index(spec[1], name_to_idx)
            idx_b = _find_index(spec[2], name_to_idx)
            resolved.append(f'{idx_a}-{idx_b}')

    return resolved if resolved else None


# ── Crossed condition builder ──────────────────────────────────────────


class _CrossedConditionBuilder:
    """Builder for factorial (crossed) condition designs.

    Created via ``ConditionBuilder.cross(cl1, cl2)``.  Not instantiated
    directly.
    """

    def __init__(self, cl1, cl2, colors=None):
        self._cl1 = cl1
        self._cl2 = cl2
        self._colors = colors
        self._comparisons = []
        self._order_factor = None
        self._explanation = None

    # ── comparisons ────────────────────────────────────────────────

    def compare(self, a, b, within=None):
        """Compare two conditions by shorthand name.

        Parameters
        ----------
        a, b : str
            Shorthand names of the sub-conditions to compare.
        within : str, optional
            Restrict the comparison to crossed conditions that also
            contain this shorthand.  E.g.
            ``compare("Syn", "hAPP", within="WeekTwo")``.
        """
        self._comparisons.append(('__PAIR__', a, b, within))
        return self

    def compare_all_pairs(self, within_factor=None):
        """All pairwise comparisons, optionally grouped by a factor.

        Parameters
        ----------
        within_factor : str, optional
            Factor name (e.g. ``"Time"``).  If given, comparisons are
            made within each level of that factor (e.g. all genotype
            pairs at each timepoint).
        """
        self._comparisons.append(('__ALL_PAIRS_WITHIN__', within_factor))
        return self

    def compare_to_control(self, control, within_factor=None):
        """Compare all other conditions to *control*, optionally within a factor."""
        self._comparisons.append(('__VS_CONTROL_WITHIN__', control, within_factor))
        return self

    # ── ordering ───────────────────────────────────────────────────

    def order_by(self, factor):
        """Reorder crossed conditions to group by *factor*.

        By default ``zipConditionLists`` groups by the first factor.
        Use this to regroup, e.g. ``order_by("Time")`` to get all
        genotypes within each timepoint together.
        """
        self._order_factor = factor
        return self

    # ── explanation ─────────────────────────────────────────────────

    def explain(self, explanation):
        """Set the explanation template for the crossed list."""
        self._explanation = explanation
        return self

    # ── build ──────────────────────────────────────────────────────

    def build(self):
        """Return a ``conditionList`` from the crossed design."""
        crossed = list(zipConditionLists(self._cl1, self._cl2, self._colors))

        if self._order_factor:
            crossed = self._reorder(crossed, self._order_factor)

        comparisons = self._resolve(crossed)
        return conditionList(crossed, comparisons, explanation=self._explanation)

    # ── internals ──────────────────────────────────────────────────

    @staticmethod
    def _sub_names(mc):
        """Shorthand names from a multiCondition's sub-conditions."""
        if isinstance(mc, multiCondition):
            return {c.name for c in mc.conditionsList}
        return {getattr(mc, 'name', '')}

    @staticmethod
    def _factor_value(mc, factor):
        """Value of *factor* inside a multiCondition."""
        if isinstance(mc, multiCondition):
            for c in mc.conditionsList:
                if c.factor == factor:
                    return c.name
        return getattr(mc, 'name', None) if getattr(mc, 'factor', None) == factor else None

    def _reorder(self, crossed, factor):
        groups = OrderedDict()
        for mc in crossed:
            key = self._factor_value(mc, factor)
            groups.setdefault(key, []).append(mc)
        return [mc for group in groups.values() for mc in group]

    def _find_crossed_index(self, crossed, name, within=None):
        """1-based index of the crossed condition matching *name* (and *within*)."""
        candidates = []
        for i, mc in enumerate(crossed):
            subs = self._sub_names(mc)
            if name in subs and (within is None or within in subs):
                candidates.append(i + 1)

        if len(candidates) == 1:
            return candidates[0]

        all_names = sorted({n for mc in crossed for n in self._sub_names(mc)})
        if not candidates:
            raise ValueError(
                f"No crossed condition matches '{name}'"
                + (f" within '{within}'" if within else "")
                + f". Available names: {all_names}"
            )
        raise ValueError(
            f"Multiple crossed conditions match '{name}'"
            + (f" within '{within}'" if within else "")
            + f" at positions {candidates}. Use 'within' to disambiguate."
        )

    def _resolve(self, crossed):
        """Resolve named comparisons to index-based strings."""
        if not self._comparisons:
            return None

        resolved = []

        for spec in self._comparisons:
            tag = spec[0]

            if tag == '__PAIR__':
                _, a, b, within = spec
                idx_a = self._find_crossed_index(crossed, a, within)
                idx_b = self._find_crossed_index(crossed, b, within)
                resolved.append(f'{idx_a}-{idx_b}')

            elif tag == '__ALL_PAIRS_WITHIN__':
                _, within_factor = spec
                if within_factor:
                    groups = OrderedDict()
                    for i, mc in enumerate(crossed):
                        key = self._factor_value(mc, within_factor)
                        groups.setdefault(key, []).append(i + 1)
                    for indices in groups.values():
                        for x in range(len(indices)):
                            for y in range(x + 1, len(indices)):
                                resolved.append(f'{indices[x]}-{indices[y]}')
                else:
                    for i in range(len(crossed)):
                        for j in range(i + 1, len(crossed)):
                            resolved.append(f'{i + 1}-{j + 1}')

            elif tag == '__VS_CONTROL_WITHIN__':
                _, control, within_factor = spec
                if within_factor:
                    groups = OrderedDict()
                    for i, mc in enumerate(crossed):
                        key = self._factor_value(mc, within_factor)
                        groups.setdefault(key, []).append((i + 1, mc))
                    for entries in groups.values():
                        ctrl_idx = None
                        for idx, mc in entries:
                            if control in self._sub_names(mc):
                                ctrl_idx = idx
                                break
                        if ctrl_idx is not None:
                            for idx, mc in entries:
                                if idx != ctrl_idx:
                                    resolved.append(f'{ctrl_idx}-{idx}')
                else:
                    ctrl_idx = self._find_crossed_index(crossed, control)
                    for i in range(len(crossed)):
                        if i + 1 != ctrl_idx:
                            resolved.append(f'{ctrl_idx}-{i + 1}')


        return resolved if resolved else None


# Public group-oriented aliases. The original condition names remain supported
# for existing scripts and serialized objects; the aliases are the preferred
# names for new user-facing examples.
group = condition
multiGroup = multiCondition
groupList = conditionList
zipGroups = zipConditions
zipGroupLists = zipConditionLists
GroupBuilder = ConditionBuilder
