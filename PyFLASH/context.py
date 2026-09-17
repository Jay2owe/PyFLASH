"""Small offline public usage guide for PyFLASH."""

from __future__ import annotations

import difflib
import re


__version__ = "0.2.0"

_TOPICS = {
    "overview": {
        "title": "Choose a PyFLASH workflow",
        "description": "Orient around the data model, registered plots and reproducible outputs.",
        "keywords": "help start guide plot analysis batch registry runner",
        "content": """PyFLASH is a Python package for turning microscopy experiment data into analysed tables and figures. Its public plotting and analysis functions are the callable surface. The package's live plot registry is `PyFLASH.spec.PLOT_REGISTRY`; the agent runner resolves those names and returns JSON plus an equivalent script. Start by identifying the batch, the question, and the output folder.""",
        "related": ["data", "plotting", "analysis", "outputs", "troubleshooting"],
    },
    "data": {
        "title": "Load and describe experiment data",
        "description": "Use the Batch and Experiment objects or a saved state as the input boundary.",
        "keywords": "batch pickle load_state create_batch conditions markers dataframe input",
        "content": """A normal workflow starts from a `Batch` created with `PyFLASH.create_batch(...)` or loaded with `PyFLASH.load_state(...)`. Keep the input state unchanged while exploring a plot. For a new request, identify the batch path, its conditions and the grouping or filtering needed; do not guess column names when `data_overview` or the runner's live descriptions can establish them.""",
        "related": ["overview", "plotting", "analysis"],
    },
    "plotting": {
        "title": "Choose a registered plot",
        "description": "Map the biological comparison to a registered plotting action and its arguments.",
        "keywords": "bar scatter violin box superplot heatmap regression rhythm group comparison filter",
        "content": """Use the `/pyflash` control skill or its runner to discover registered aliases and inspect their live signatures. The runner accepts an action name plus JSON parameters; it can produce SVG outputs and PNG previews. Prefer a registered plot whose name and reference entry match the question. Shared parameters such as filters, markers, grouping and output location retain the same meaning across plots.""",
        "related": ["data", "outputs", "troubleshooting"],
    },
    "analysis": {
        "title": "Run a statistical or pipeline analysis",
        "description": "Use the pipeline and modelling functions when the request is more than a figure.",
        "keywords": "pipeline modelling correlation adjusted linear model rhythm statistics fit",
        "content": """PyFLASH exposes pipeline and modelling callables such as `data_overview`, `correlation`, `adjusted_correlation`, `linear_model`, and `rhythm`. Choose the analysis from the scientific question, preserve the returned evidence and inspect missing or unsupported estimates. The action layer is the stable boundary for agent calls; it does not replace the package's statistical definitions.""",
        "related": ["overview", "data", "outputs"],
    },
    "outputs": {
        "title": "Read and preserve outputs",
        "description": "Keep figure files, provenance and result metadata together.",
        "keywords": "SVG PNG preview result provenance artifact publication save Results equivalent script",
        "content": """Write outputs under the request's explicit result root. A successful runner response includes structured results, output paths when applicable, provenance or run metadata, and an `equivalent_script`. Treat the script and recorded inputs as part of the result so another agent can reproduce the call. A preview is for inspection; the SVG or data artifact is the durable output.""",
        "related": ["plotting", "analysis", "troubleshooting"],
    },
    "troubleshooting": {
        "title": "Diagnose a rejected or unexpected call",
        "description": "Use live discovery, descriptions and returned errors before retrying.",
        "keywords": "error unknown action bad parameters missing column style dependency failed retry",
        "content": """For an unknown action, run live `discover` and then `describe` the exact alias. For a parameter error, use the live signature and the package reference rather than inventing a spelling. If a figure has the wrong appearance, check the active PyFLASH style, filters, grouping and output metadata before rerunning. A failed call may have created files; inspect the result root before repeating a write.""",
        "related": ["plotting", "analysis", "outputs"],
    },
}


def topics() -> tuple[str, ...]:
    """Return the public topic keys in their documented order."""
    return tuple(_TOPICS)


def _error(message: str, topic=None, suggestions=()) -> dict:
    return {"ok": False, "version": __version__, "topic": topic if isinstance(topic, str) else None,
            "error": message, "suggestions": list(suggestions), "available": list(_TOPICS)}


def read(topic: str = "overview", *, format: str = "text") -> str | dict:
    """Read a public usage topic as text or a JSON-clean record."""
    if format not in ("text", "json"):
        result = _error("format must be 'text' or 'json'.", topic)
    elif not isinstance(topic, str) or topic.casefold() not in _TOPICS:
        key = topic.casefold() if isinstance(topic, str) else topic
        result = _error(f"Unknown topic {key!r}.", key,
                        difflib.get_close_matches(key, _TOPICS, n=3) if isinstance(key, str) else ())
    else:
        key = topic.casefold()
        item = _TOPICS[key]
        result = {"ok": True, "version": __version__, "topic": key,
                  "title": item["title"], "description": item["description"],
                  "content": f"PyFLASH {__version__} - {item['title']}\n\n{item['content']}",
                  "prerequisites": [], "related": list(item["related"])}
        if key == "overview":
            result["topics"] = [{"topic": name, "title": value["title"],
                                 "description": value["description"]}
                                for name, value in _TOPICS.items()]
    return result if format == "json" else (result["content"] if result["ok"]
                                             else result["error"] + " Available: " + ", ".join(result["available"]))


def search(query: str, *, limit: int = 5) -> dict:
    """Find topics by task, argument, output or error wording."""
    if not isinstance(query, str) or not query.strip() or isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return {**_error("query must be non-empty and limit must be a positive integer."), "results": []}
    words = set(re.findall(r"[\w]+", query.casefold()))
    ranked = []
    for key, item in _TOPICS.items():
        terms = set(re.findall(r"[\w]+", (key + " " + item["title"] + " " + item["description"] + " " + item["keywords"] + " " + item["content"]).casefold()))
        matches = sorted(words & terms)
        if matches:
            ranked.append((len(matches), key, {"topic": key, "title": item["title"],
                                               "description": item["description"],
                                               "relevance": "Matches: " + ", ".join(matches)}))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return {"ok": True, "version": __version__, "query": query,
            "results": [row[2] for row in ranked[:limit]], "total": len(ranked),
            "truncated": len(ranked) > limit}
