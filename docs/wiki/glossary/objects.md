# Objects

## Batch

A multi-experiment PyFLASH object with combined summaries, marker data, images,
conditions, and output paths. See also: [Batch](../object-types/batch.md).

## Experiment

An imported FLASH/ImageJ experiment folder with marker tables, summaries, image
metadata, and save paths. See also: [Experiment](../object-types/experiment.md).

## MiniExperiment

A lightweight experiment created from CSV-style tables instead of a full FLASH
folder export. See also: [MiniExperiment](../object-types/mini-experiment.md).

## DataFrameExperiment

A PyFLASH wrapper around a pandas DataFrame with normalized group and subject
columns. See also: [DataFrameExperiment](../object-types/dataframe-experiment.md).

## group

One named group level with a label, short name, color, and optional explanation.
Classic API name: `condition`. See also: [Groups](../object-types/conditions.md).

## groupList

The ordered collection of groups plus resolved comparisons such as `1-2`.
Classic API name: `conditionList`.
See also: [Condition builder](../functions/condition-builder.md).

## GroupBuilder

The builder API for defining groups and comparisons in Python. See also:
[Build groups](../workflows/build-conditions.md).

## ConditionBuilder

The UI/spec-facing builder layer that turns condition JSON into a `conditionList`.
See also: [Group specs](../data-structures/condition-specs.md).

## multiGroup

A crossed-design group made from more than one factor, such as genotype and
timepoint. Classic API name: `multiCondition`. See also:
[Groups and factors](../parameters/conditions-and-factors.md).

## Marker

A named measurement channel or antibody marker represented in marker tables and
plots. See also: [Markers](../object-types/markers.md).

## Marker objects

The Python wrapper objects stored in `.data`, each exposing its table as `.df`:
`Attribute` (generic tables), `Antibody` (marker intensity tables), `cellMarker`,
and `objectMarker` (segmented object tables). See also:
[Markers](../object-types/markers.md).

## Config

The shared configuration object for defaults such as colors, saving behavior,
and thresholds. See also: [Config](../object-types/config.md).

## PLOT_REGISTRY

The short-name registry that maps spec `type` values to plotting or pipeline
callables. See also: [Plot registry](../developer/plot-registry.md).
