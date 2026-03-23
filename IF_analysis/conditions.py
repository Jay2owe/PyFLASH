"""
Experimental condition classes and helpers.
"""

from functools import reduce


class condition:
    """A single experimental condition (e.g. one genotype or treatment)."""

    def __init__(self, label, name, color, factor, explanation=None):
        self.label = label
        self.name = name
        self.color = color
        self.factor = factor
        self.factor_explanation = (
            explanation.replace("<>", self.label) if explanation is not None else None
        )


class multiCondition:
    """A compound condition formed by crossing two or more single conditions."""

    def __init__(self, conditionsList, name=None, label=None, color=None):
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
