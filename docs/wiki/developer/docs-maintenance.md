# Docs Maintenance

## Summary

The checklist for keeping the wiki, the generated skill references, and the API
indexes in sync when PyFLASH changes. Two kinds of docs move together: the
**hand-written wiki** under `docs/wiki/` (this reference, maintained by agents)
and the **generated skill reference** under `.claude/skills/pyflash/reference/`
(a live-signature block regenerated from source).

## When You Add Or Change A Documented Behavior

1. **Read the context first.** `docs/wiki/CONTEXT.md` (global conventions) and
   the target folder's `CONTEXT.md` (folder-specific rules). For maintainer
   pages that is `docs/wiki/developer/CONTEXT.md`.
2. **Inspect source and tests**, not function names. Ground every claim in the
   file/symbol (`PyFLASH/spec.py`, `PyFLASH/plotting.py`, `tests/...`). If the
   root `CLAUDE.md`/`AGENTS.md` and the source disagree, trust the source and
   flag it.
3. **Add or update the page** in the most specific folder (function pages in
   `../functions/`, concepts in `../concepts/`, maintainer notes here). Follow
   the [documentation standard](../documentation-standard.md) shape.
4. **Update the indexes.** Add new function pages to
   [api-reference](../api-reference.md); add new entry-point pages or folder
   changes to the wiki [README](../README.md) and the folder's own
   `README.md`. Keep the developer index [README](README.md) accurate when
   adding/removing a developer page.
5. **Refresh gallery snippets when example figures change.** The curated render
   calls live in `../examples/gallery_examples.py`. Run
   `python docs/wiki/examples/update_gallery_snippets.py` after changing them so
   each `plot_*.md` page shows the exact call above the rendered example figure.
6. **Link-check.** Every relative markdown link must resolve to a file that
   exists under `docs/wiki`. Verify each target on disk before finishing.
7. **Run focused tests** if source behavior changed — see
   [Testing Map](testing-map.md).

## The Generated Skill Reference

`scripts/update_pyflash_references.py` owns one generated block — the live
registry snapshot between the `pyflash-auto-reference:start/end` markers in
`.claude/skills/pyflash/reference/plot-functions.md`. It reads
`PLOT_REGISTRY`, resolves each alias's live signature and docstring summary, also
lists public `plot_*` functions that have no short-name, then mirrors the Claude
reference files into `.codex/skills/pyflash/references/`.

- The Claude `PostToolUse` hook runs `python scripts/update_pyflash_references.py
  --if-needed --quiet` after write/edit tools touch trigger paths (`PyFLASH/`,
  `tests/`, the skill dirs, `pyproject.toml`), so the block self-heals.
- Run it manually from the repo root; `--check` fails if the generated files are
  out of date (useful in CI). Do **not** hand-edit inside the generated markers —
  edit the hand-written teaching prose around them instead.

## See Also

- [Adding A Plot](adding-a-plot.md)
- [Testing Map](testing-map.md)
- [Documentation standard](../documentation-standard.md)
- [API reference](../api-reference.md)
