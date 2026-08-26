"""PyFLASH-facing figure inspection and publication helpers.

The implementation lives in the reusable ReproFig (``reprofig``) distribution;
this module preserves a discoverable PyFLASH import and command entry point.
"""

from reprofig import (
    ArtifactPublicationResult,
    PublicationResult,
    bundle_artifacts,
    build_publication_workbook,
    caption_for,
    classify_figure,
    embed_file,
    export_fsb,
    export_rocrate,
    extract_artifact,
    extract_figure,
    extract_record,
    formats,
    inspect_artifact,
    inspect_figure,
    publish_artifacts,
    publish_figures,
    verify_proof,
    save_figure,
    scan_artifacts,
    scan_figures,
    validate_artifact,
    validate_svg,
)
from reprofig.cli import main as _reprofig_main


def main(argv=None):
    """Run the ReproFig command set under the PyFLASH entry-point name."""

    return _reprofig_main(argv, prog="pyflash-figure")

__all__ = [
    "ArtifactPublicationResult",
    "PublicationResult",
    "bundle_artifacts",
    "build_publication_workbook",
    "caption_for",
    "classify_figure",
    "embed_file",
    "export_fsb",
    "export_rocrate",
    "extract_artifact",
    "extract_figure",
    "extract_record",
    "formats",
    "inspect_artifact",
    "inspect_figure",
    "main",
    "publish_artifacts",
    "publish_figures",
    "save_figure",
    "scan_artifacts",
    "scan_figures",
    "validate_artifact",
    "validate_svg",
    "verify_proof",
]


if __name__ == "__main__":
    raise SystemExit(main())
