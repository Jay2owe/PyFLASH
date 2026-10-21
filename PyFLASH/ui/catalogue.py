"""Searchable public callables, read from source without importing renderers.

The action registry owns runnable recipes. Core source definitions own Python
signatures and help; private implementation helpers and UI code are excluded.
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
import re
import io
import tokenize


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Parameter:
    name: str
    kind: str
    required: bool
    default: str
    annotation: str
    description: str


@dataclass(frozen=True)
class Function:
    key: str
    name: str
    module: str
    kind: str
    signature: str
    documentation: str
    parameters: tuple[Parameter, ...]
    source: str
    line: int
    aliases: tuple[str, ...] = ()
    action: str | None = None
    page: str | None = None
    binding: str = "function"

    @property
    def summary(self):
        return self.documentation.split("\n\n", 1)[0].replace("\n", " ")


def _parameter_help(documentation):
    """Read NumPy-style parameter descriptions from the function's own help."""
    result = {}
    active = []
    in_parameters = False
    lines = documentation.splitlines()
    for index, line in enumerate(lines):
        if line.strip() in {"Parameters", "Args", "Arguments"}:
            in_parameters = True
            continue
        if not in_parameters or not line.strip() or set(line.strip()) == {"-"}:
            continue
        if index + 1 < len(lines) and set(lines[index + 1].strip()) == {"-"}:
            break
        header = re.match(r"^([\w*, ]+)\s*:\s*(.*)$", line)
        if header:
            active = [name.strip().lstrip("*") for name in header[1].split(",")]
            for name in active:
                result[name] = ""
        elif line[:1].isspace():
            for name in active:
                result[name] = (result[name] + " " + line.strip()).strip()
    return result


def _parameters(args, documentation, *, drop_receiver=False, shared=False):
    from PyFLASH.param_docs import PARAM_DOCS
    help_text = _parameter_help(documentation)
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    pairs = [(a, d, "positional only" if i < len(args.posonlyargs) else "positional or keyword")
             for i, (a, d) in enumerate(zip(positional, defaults))]
    if drop_receiver and pairs:
        pairs = pairs[1:]
    if args.vararg:
        pairs.append((args.vararg, None, "variable positional"))
    pairs += [(a, d, "keyword only") for a, d in zip(args.kwonlyargs, args.kw_defaults)]
    if args.kwarg:
        pairs.append((args.kwarg, None, "variable keyword"))
    return tuple(Parameter(
        name=a.arg, kind=kind, required=d is None and not kind.startswith("variable"),
        default=ast.unparse(d) if d is not None else "",
        annotation=ast.unparse(a.annotation) if a.annotation else "",
        description=help_text.get(a.arg) or (PARAM_DOCS.get(a.arg, {}).get("description", "") if shared else ""),
    ) for a, d, kind in pairs)


def _definition(module, filename, node, *, parent=None):
    name = f"{parent.name}.{node.name}" if parent else node.name
    doc = ast.get_docstring(node) or "No additional documentation."
    binding = "function"
    if isinstance(node, ast.ClassDef):
        constructor = next((n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "__init__"), None)
        args = constructor.args if constructor else None
        binding = "class"
        kind = "Python class"
    else:
        args = node.args
        kind = "Python method" if parent else "Python function"
        if parent:
            decorators = {ast.unparse(d) for d in node.decorator_list}
            binding = "static" if "staticmethod" in decorators else "class method" if "classmethod" in decorators else "instance"
    drop = binding in {"class", "class method", "instance"}
    params = _parameters(args, doc, drop_receiver=drop, shared=module == "PyFLASH.plotting") if args else ()
    if args:
        # Work on a separate tree: signatures retain '/', '*', annotations and defaults.
        signature_args = copy.copy(args)
        if drop:
            if signature_args.posonlyargs:
                signature_args.posonlyargs = signature_args.posonlyargs[1:]
            else:
                signature_args.args = signature_args.args[1:]
        signature = f"{name}({ast.unparse(signature_args)})"
    else:
        signature = f"{name}(...)"  # inherited/generated constructors are not guessed
    return Function(f"{module}.{name}", name, module, kind, signature, doc, params,
                    str(filename.relative_to(ROOT.parent)).replace("\\", "/"), node.lineno,
                    binding=binding)


@lru_cache(maxsize=2)
def _source_catalogue(fingerprint):
    found = {}
    aliases = []
    exports = []
    for filename, _mtime, _size in fingerprint:
        path = Path(filename)
        module = "PyFLASH" if path.stem == "__init__" else f"PyFLASH.{path.stem}"
        tree = _interface_tree(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                item = _definition(module, path, node)
                found[item.key] = item
                if isinstance(node, ast.ClassDef):
                    for method in node.body:
                        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and not method.name.startswith("_"):
                            if not any(ast.unparse(d) in {"property", f"{method.name}.setter"} for d in method.decorator_list):
                                item = _definition(module, path, method, parent=node)
                                found[item.key] = item
            elif isinstance(node, ast.Assign):
                if module == "PyFLASH" and any(isinstance(t, ast.Name) and t.id == "_LAZY_ATTRS" for t in node.targets):
                    for public, (owner, name) in ast.literal_eval(node.value).items():
                        exports.append((f"PyFLASH.{public}", f"{owner}.{name}"))
                elif isinstance(node.value, ast.Name):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and not target.id.startswith("_"):
                            aliases.append((f"{module}.{target.id}", f"{module}.{node.value.id}"))
            elif module == "PyFLASH" and isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("PyFLASH."):
                exports += [(f"PyFLASH.{n.asname or n.name}", f"{node.module}.{n.name}") for n in node.names]
    # Aliases retain one canonical definition, so synonyms cannot drift apart.
    for public, target in aliases + exports:
        canonical = target if target in found else next((key for key, item in found.items() if target in item.aliases), None)
        if canonical:
            item = found[canonical]
            found[canonical] = replace(item, aliases=tuple(sorted(set(item.aliases) | {public})))
            if item.kind == "Python class":
                for key, method in list(found.items()):
                    if key.startswith(canonical + "."):
                        found[key] = replace(method, aliases=tuple(sorted(set(method.aliases) | {public + key[len(canonical):]})))
    return tuple(found.values())


def _interface_tree(source):
    """Compile declarations and literal help only, never the analysis bodies.

    Regex locates declarations; Python's tokenizer handles multiline headers,
    annotations and string literals. The small tree also contains static aliases.
    """
    declarations = list(re.finditer(r"(?m)^( *)(?:(?:async )?def|class) ([A-Za-z_]\w*)[(:]", source))
    tree = ast.Module(body=[], type_ignores=[])
    parent = None
    for index, match in enumerate(declarations):
        indent, name = len(match[1]), match[2]
        if indent == 0:
            parent = None
        if indent not in {0, 4} or (indent and parent is None):
            continue
        if name.startswith("_") and not (parent and name == "__init__"):
            continue
        end = declarations[index + 1].start() if index + 1 < len(declarations) else len(source)
        excerpt = source[match.start() + indent:end]
        tokens = tokenize.generate_tokens(io.StringIO(excerpt).readline)
        depth = 0
        for token in tokens:
            if token.type == tokenize.OP:
                if token.string in "([{":
                    depth += 1
                elif token.string in ")]}":
                    depth -= 1
                elif token.string == ":" and depth == 0:
                    lines = excerpt.splitlines(keepends=True)
                    row, column = token.end
                    header = "".join(lines[:row - 1]) + lines[row - 1][:column]
                    break
        ignored = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT}
        body = next((t for t in tokens if t.type not in ignored), None)
        statement = "pass"
        if body and body.type == tokenize.STRING:
            parts = [body.string]
            for token in tokens:
                if token.type == tokenize.STRING:
                    parts.append(token.string)
                elif token.type in {tokenize.NEWLINE, tokenize.ENDMARKER}:
                    statement = " ".join(parts)
                    break
                elif token.type not in {tokenize.COMMENT, tokenize.NL}:
                    break
        node = ast.parse(header + "\n    " + statement + "\n").body[0]
        node.lineno = source.count("\n", 0, match.start()) + 1
        # Retain binding/property decorators without parsing any executable body.
        before = source[:match.start()].splitlines()
        decorators = []
        for line in reversed(before):
            if line.lstrip().startswith("@"):
                decorators.insert(0, ast.parse(line.lstrip()[1:], mode="eval").body)
            else:
                break
        node.decorator_list = decorators
        if indent:
            parent.body.append(node)
        else:
            tree.body.append(node)
            if isinstance(node, ast.ClassDef):
                parent = node
    # Root exports and the small lazy mapping are already cheap to compile.
    if "_LAZY_ATTRS =" in source:
        original = ast.parse(source)
        tree.body += [n for n in original.body if isinstance(n, (ast.ImportFrom, ast.Assign))]
    else:
        for match in re.finditer(r"(?m)^([A-Za-z_]\w*) = ([A-Za-z_]\w*)\s*$", source):
            tree.body.append(ast.parse(match[0]).body[0])
    return tree


def functions():
    """All core public definitions and every registered action; no execution."""
    from PyFLASH.spec import PLOT_REGISTRY
    from PyFLASH.ui.services import IMAGE_PLOT_TYPES
    files = sorted(ROOT.glob("*.py"))
    # Include the explicitly exported logging controls, exclude other private modules.
    files = [p for p in files if not p.stem.startswith("_") or p.stem in {"__init__", "_logging"}]
    from PyFLASH.ui.workspace import content_hash
    fingerprint = tuple((str(p), content_hash(p), p.stat().st_size) for p in files)
    definitions = {item.key: item for item in _source_catalogue(fingerprint)}
    actions = []
    for alias, target in PLOT_REGISTRY.items():
        target = target if "." in target else f"PyFLASH.plotting.{target}"
        item = definitions.get(target)
        if item is None:
            raise ValueError(f"Registered action {alias!r} has no source definition: {target}")
        actions.append(replace(item, key=f"action:{alias}", action=alias,
                               kind="Registered analysis" if item.module in {"PyFLASH.pipeline", "PyFLASH.modelling"} else "Registered figure",
                               page="images" if alias in IMAGE_PLOT_TYPES else "figures"))
    targets = {f"{item.module}.{item.name}" for item in actions}
    return tuple(sorted(actions + [item for item in definitions.values() if item.key not in targets],
                        key=lambda item: (item.action is None, item.action or item.key)))


def search(items, query="", *, kind="All", module="All"):
    """Match every query word against names, aliases, help and parameters."""
    words = query.casefold().split()
    matches = [item for item in items if (kind == "All" or item.kind == kind)
                 and (module == "All" or item.module == module)
                 and all(word in (" ".join((item.key, item.name, item.module, item.action or "", item.documentation,
                                            *item.aliases, *(p.name for p in item.parameters)))).casefold() for word in words)]
    normalized = query.strip().casefold().replace(" ", "_")
    def relevance(item):
        names = [item.name.casefold(), (item.action or "").casefold(), item.key.casefold(), *(a.casefold() for a in item.aliases)]
        exact = bool(normalized) and any(normalized == n or normalized == n.rsplit(".", 1)[-1] for n in names)
        name_matches = sum(any(word in name for name in names) for word in words)
        return (not exact, -name_matches)
    return tuple(sorted(matches, key=relevance))


def setup(item):
    """Return the canonical page and preferences; never start a computation."""
    if not item.action:
        return None, {}
    if item.page == "figures":
        return "6_plots.py", {"ui_fig_type": item.action}
    if item.action == "locations":
        return "7_images.py", {"ui_image_open_location": True}
    return "7_images.py", {"ui_image_mode": "Representative images" if item.action == "representative_images" else "Browse images"}


def call_template(item):
    """An explicitly labelled Python template, not a replay of an actual run."""
    owner = item.name.split(".")[0]
    lines = ["# Call template: supply your own inputs before running.", f"from {item.module} import {owner}"]
    if item.binding == "instance":
        lines += ["", "# Create or load this object using the package's documented workflow.", "instance = ..."]
        callable_name = "instance." + item.name.split(".", 1)[1]
    else:
        callable_name = item.name
    arguments = [p.name if p.kind == "positional only" else f"{p.name}={p.name}"
                 for p in item.parameters if p.required]
    if item.binding == "class" and "(...)" in item.signature:
        lines.append("# This class uses an inherited or generated constructor; consult its help.")
        arguments = ["..."]
    lines += ["", f"result = {callable_name}({', '.join(arguments)})"]
    return "\n".join(lines) + "\n"
