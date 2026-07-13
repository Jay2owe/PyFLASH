"""Insert gallery render snippets above function-page example figures."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from gallery_examples import gallery_examples


ROOT = Path(__file__).resolve().parents[3]
FUNCTIONS_DIR = ROOT / "docs" / "wiki" / "functions"
START = "<!-- gallery-example-code:start -->"
END = "<!-- gallery-example-code:end -->"
INTRO = (
    "Gallery render call (after `ex = build_example_data(fig_path=TMP)`, "
    "`exp = ex.experiment`, and `P = PyFLASH.plotting`):"
)


def build_block(code: str) -> str:
    return f"{START}\n{INTRO}\n\n```python\n{code}\n```\n{END}\n"


def updated_text(path: Path, plot_name: str, code: str) -> str:
    text = path.read_text(encoding="utf-8")
    block = build_block(code)
    marker_pattern = re.compile(
        rf"{re.escape(START)}.*?{re.escape(END)}\n*", flags=re.DOTALL
    )
    if marker_pattern.search(text):
        return marker_pattern.sub(block + "\n", text, count=1)

    heading = "## Example figure\n\n"
    if heading not in text:
        raise ValueError(f"{path} has no '## Example figure' section")
    image = f"![{plot_name} example figure]"
    heading_index = text.index(heading)
    if image not in text[heading_index:]:
        raise ValueError(f"{path} has no matching example image for {plot_name}")
    return text.replace(heading, heading + block + "\n", 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if gallery snippets are missing or out of date.",
    )
    args = parser.parse_args(argv)

    changed: list[Path] = []
    missing: list[Path] = []
    for example in gallery_examples():
        path = FUNCTIONS_DIR / f"{example.name}.md"
        if not path.exists():
            missing.append(path)
            continue
        new_text = updated_text(path, example.name, example.code)
        old_text = path.read_text(encoding="utf-8")
        if new_text != old_text:
            changed.append(path)
            if not args.check:
                path.write_text(new_text, encoding="utf-8")

    if missing:
        for path in missing:
            print(f"missing function page: {path}", file=sys.stderr)
        return 1

    if args.check and changed:
        for path in changed:
            print(f"out of date: {path}", file=sys.stderr)
        return 1

    action = "would update" if args.check else "updated"
    print(f"{action} {len(changed)} gallery snippet page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
