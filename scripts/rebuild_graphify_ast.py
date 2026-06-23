"""Rebuild the local graphify graph from PyFLASH code ASTs only.

This deliberately avoids graphify's broad corpus detector and all semantic
extraction. It scans only the Python package and tests, then writes the local
agent graph artifacts under graphify-out/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.export import to_json
from graphify.extract import collect_files, extract
from graphify.report import generate


ROOT = Path(__file__).resolve().parents[1]
CODE_ROOTS = (Path("PyFLASH"), Path("tests"))
OUT_DIR = Path("graphify-out")


def _code_files() -> list[Path]:
    files: set[Path] = set()
    for code_root in CODE_ROOTS:
        if code_root.exists():
            files.update(path for path in collect_files(code_root) if path.suffix.lower() == ".py")
    return sorted(files, key=lambda path: str(path).lower())


def _word_count(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += len(path.read_text(encoding="utf-8", errors="ignore").split())
        except OSError:
            continue
    return total


def main() -> int:
    os.chdir(ROOT)
    code_files = _code_files()
    if not code_files:
        print("[graphify ast] No Python files found under PyFLASH/ or tests/.")
        return 1

    extraction = extract(code_files)
    extraction["input_tokens"] = 0
    extraction["output_tokens"] = 0

    graph = build_from_json(extraction)
    communities = cluster(graph)
    cohesion = score_all(graph, communities)
    community_labels = {cid: f"Community {cid}" for cid in communities}
    suggested_questions = suggest_questions(graph, communities, community_labels)

    detection = {
        "files": {
            "code": [str(path) for path in code_files],
            "document": [],
            "paper": [],
            "image": [],
        },
        "total_files": len(code_files),
        "total_words": _word_count(code_files),
    }
    token_cost = {"input": 0, "output": 0}

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / ".graphify_root").write_text(str(ROOT), encoding="utf-8")
    to_json(graph, communities, str(OUT_DIR / "graph.json"))

    report = generate(
        graph,
        communities,
        cohesion,
        community_labels,
        god_nodes(graph),
        surprising_connections(graph, communities),
        detection,
        token_cost,
        str(ROOT),
        suggested_questions=suggested_questions,
    )
    (OUT_DIR / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    (OUT_DIR / "cost.json").write_text(
        json.dumps({"mode": "ast-only", **token_cost}, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "ast-only",
                "roots": [str(path) for path in CODE_ROOTS if path.exists()],
                "files": [str(path) for path in code_files],
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "communities": len(communities),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "[graphify ast] Rebuilt "
        f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges, "
        f"{len(communities)} communities from {len(code_files)} files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
