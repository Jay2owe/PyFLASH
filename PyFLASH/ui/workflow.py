"""Cheap, stable workflow catalogue shared by navigation and help."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    section: str
    file: str
    icon: str
    help: str
    canonical_stage: str | None = None


STAGES = (
    Stage("workspace", "Workspace", "", "1_project.py", "folder_open", "Open an analysis, import a subject table, or start a project."),
    Stage("folders", "Folders", "Prepare", "2_experiments.py", "folder_copy", "Validate experiment folders before processing."),
    Stage("groups", "Groups", "Prepare", "3_conditions.py", "group", "Define factors, group colours and comparisons."),
    Stage("process", "Process", "Prepare", "4_process.py", "play_circle", "Build the analysis using saved folder and group choices."),
    Stage("explore", "Explore", "Inspect", "5_summary.py", "query_stats", "Inspect measurements and highlight the same subject in both views."),
    Stage("figures", "Figures", "Inspect", "6_plots.py", "bar_chart", "Run registered PyFLASH figures and download the equivalent script.", "functions"),
    Stage("images", "Images", "Inspect", "7_images.py", "image", "Inspect imported microscopy images and representative selections.", "functions"),
    Stage("export", "Export", "Finish", "8_export.py", "download", "Export workbooks or save a processed analysis."),
    Stage("functions", "Plots & pipelines", "Inspect", "9_functions.py", "functions", "Choose a picture, assign its data, and run the plot or pipeline with recorded results."),
)


def page_heading(key):
    """Return the actual destination heading, including legacy page redirects."""
    stages = {stage.key: stage for stage in STAGES}
    stage = stages[key]
    return stages[stage.canonical_stage or key].label

HELP = {stage.key: stage.help for stage in STAGES}
HELP.update({
    "region": "Choose the region summary to inspect. No processing is rerun.",
    "subject": "Highlight this subject in both exploration plots; other subjects remain visible.",
    "metric": "Choose this view's measurement without changing the other view.",
    "appearance": "Presentation only. These choices do not change measurements or statistical settings.",
    "recipe": "Parameters are sent to the registered package function; unknown options are rejected.",
})
