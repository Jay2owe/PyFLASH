# Docs Maintenance

Keep the public usage guide and API reference consistent with package behavior.
The documentation source is `docs/wiki/`; Read the Docs builds it using
`mkdocs.yml` and `.readthedocs.yaml`.

## When behavior changes

1. Check the implementation and its tests before updating a claim.
2. Add or update the relevant function, concept or workflow page. Follow the
   [documentation standard](../documentation-standard.md).
3. Update the [API reference](../api-reference.md), the main [index](../README.md)
   and the affected folder index when pages are added or removed.
4. Keep examples consistent with the documented arguments and return values.
   Use [the testing map](testing-map.md) to select checks for changed behavior.
5. Check relative links and build the site before submitting changes.

## Build the documentation

From the repository root:

```bash
python -m pip install -r docs/requirements.txt
python -m mkdocs build --strict
```

Generated pages are written to `site/`, which is ignored by Git.
Use `python -m mkdocs serve` to preview changes locally.

## See Also

- [Adding A Plot](adding-a-plot.md)
- [Testing Map](testing-map.md)
- [Documentation standard](../documentation-standard.md)
- [API reference](../api-reference.md)
