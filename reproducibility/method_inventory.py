"""Discover local inherited method exposures in Python's declared C3 order."""
import ast


def method_declarations(tree):
    """Yield each class's effective local methods, including private mixins.

    Imported bases remain outside this local declaration resolver. They cannot
    borrow a local class's scientific evidence. Every overriding declaration,
    including a non-callable assignment, shadows that name on later bases.
    """
    classes={node.name:node for node in tree.body if isinstance(node,ast.ClassDef)}
    memo={}

    def order(name,trail=()):
        if name in memo:return memo[name]
        if name in trail:raise ValueError('Cyclic local class hierarchy: '+name)
        node=classes[name]
        bases=[base.id for base in node.bases if isinstance(base,ast.Name) and base.id in classes]
        sequences=[list(order(base,trail+(name,))) for base in bases]+[bases.copy()]
        result=[name]
        while any(sequences):
            sequences=[sequence for sequence in sequences if sequence]
            head=next((sequence[0] for sequence in sequences
                       if all(sequence[0] not in other[1:] for other in sequences)),None)
            if head is None:raise ValueError('Inconsistent local class hierarchy: '+name)
            result.append(head)
            for sequence in sequences:
                if sequence[0]==head:sequence.pop(0)
        memo[name]=tuple(result)
        return memo[name]

    def bindings(node):
        # Later statements replace earlier bindings within the same class.
        result={}
        for item in node.body:
            if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                result[item.name]=item
            elif isinstance(item,(ast.Assign,ast.AnnAssign)):
                targets=item.targets if isinstance(item,ast.Assign) else [item.target]
                for target in targets:
                    if isinstance(target,ast.Name):result[target.id]=item
        return result

    for owner in classes:
        selected={}
        for base in order(owner):
            for name,node in bindings(classes[base]).items():selected.setdefault(name,(node,base))
        for name,(node,defined_on) in selected.items():
            if not name.startswith('_') and isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                yield owner,node,defined_on
