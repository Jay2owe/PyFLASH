# PyFLASH deploy contract

## Scope and baseline

The distribution is `PyFLASH-analysis` and the import package is `PyFLASH`.
The observed source metadata says `0.2.0`; the existing audit and citation
metadata mention older release values, so the next release is blocked until
`pyproject.toml`, `CITATION.cff`, changelog, and documentation agree. The
observed baseline is `master` at `632dd75b07b4894cf4c6912fc34da62900352f94`.

## Artifacts and destinations

- Build and Twine-check one wheel and one source distribution.
- Commit/push `Jay2owe/PyFLASH` and create the exact version tag.
- Publish to PyPI as `PyFLASH-analysis` using the existing release workflow.
- Publish the matching documentation through Read the Docs at
  `https://pyflash.readthedocs.io/` and verify the versioned docs links.
- Verify the exact PyPI version and clean wheel import.

One combined test run must cover the analysis API, CLI/figure commands,
publication artifact generation, and the documented notebook-style install.
Do not publish notebooks, private paths, credentials, or raw lab data.

## Release blockers

The current workflow uses a PyPI API-token secret and skips existing files;
the release record must show which artifacts were uploaded. Resolve the
version mismatch before tagging. No EXE or Zenodo route is currently
documented.

