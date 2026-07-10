# Data

## Summary Table

The subject-level analysis table used by most plots and statistics. See also:
[Summary table](../data-structures/summary-table.md).

## Marker Table

A per-marker table imported from FLASH/ImageJ outputs before summaries are
assembled. See also: [Marker tables](../data-structures/marker-tables.md).

## Image Table

The table of imported image metadata, including marker, subject, ROI, and path
columns. See also: [Image table](../data-structures/image-table.md).

## ROI Table

A table organized by region of interest or ROI-derived measurements. See also:
[ROI tables](../data-structures/roi-tables.md).

## AnimalName

The stable subject identifier column used internally and by most grouped plots.
See also: [Summary table](../data-structures/summary-table.md).

## Condition

The stable internal group label column. See also:
[Groups and factors](../parameters/conditions-and-factors.md).

## Factor Column

A column such as genotype, sex, or timepoint used to build or split groups.
See also: [Groups and factors](../parameters/conditions-and-factors.md).

## Region

A named anatomical or analysis region in imported tables. See also:
[ROI parameters](../parameters/roi.md).

## ROI

A region-of-interest identifier. See also:
[ROI tables](../data-structures/roi-tables.md).

## ImageROI

An image-level ROI identifier used when matching image panels back to imported
metadata. See also: [Image table](../data-structures/image-table.md).

## Sentinel

A special placeholder value, such as an exclusion marker, that should not be
treated as a numeric measurement. See also:
[Exclusion ledgers](../data-structures/exclusion-ledgers.md).

## Exclusion Ledger

A record of excluded or manually flagged values. See also:
[Exclusion ledgers](../data-structures/exclusion-ledgers.md).

## Group Spec

A JSON-like definition of groups, colors, factors, and comparisons. See also:
[Group specs](../data-structures/condition-specs.md).

## Plot Spec

A YAML, TOML, or JSON file describing one or more plots to run. See also:
[Plot spec files](../data-structures/plot-spec-files.md).

## Pipeline Manifest

A saved JSON record of pipeline inputs, options, and outputs. See also:
[Pipeline manifests](../data-structures/pipeline-manifests.md).

## Pickle

A saved Python object state file, usually ending in `.pkl`. See also:
[Pickle files](../outputs/pickle-files.md).

## Excel Workbook

An exported `.xlsx` file containing selected PyFLASH tables. See also:
[Excel workbooks](../outputs/excel-workbooks.md).

## Run Folder

An output folder for one pipeline or modelling run. See also:
[Pipeline run folders](../outputs/pipeline-run-folders.md).

## Report Record

A structured record used by reporting and pipeline outputs. See also:
[Report records](../outputs/report-records.md).
