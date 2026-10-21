"""Execute the README's first Python block unchanged on the shared demo."""
from pathlib import Path
import re


def main():
    root = Path(__file__).resolve().parents[1]
    text = (root/"README.md").read_text(encoding="utf-8")
    snippet = re.search(r"```python\n(.*?)```",text,re.S).group(1)
    if len(snippet.strip().splitlines()) > 10:
        raise AssertionError("Common example must fit in ten lines.")
    namespace = {}
    exec(compile(snippet,"README.md","exec"),namespace)
    import numpy as np
    # The README uses the pixel-truth demo, not the reference balanced fixture.
    import json
    demo = json.loads((root/"demo"/"expected_result.json").read_text())
    np.testing.assert_allclose(namespace["result"][2],[demo["welch_t"],demo["welch_p"]],rtol=1e-8,atol=1e-12)
    print("README example passed unchanged.")


if __name__ == "__main__":
    main()
