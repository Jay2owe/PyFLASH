# Colocalisation, Contains, and Combo Columns

## Why two association types?

There are two different ways a marker can be spatially associated with another marker: **coloc** and **contains**. They answer slightly different biological questions and are not interchangeable.

## What coloc means

Coloc is the classical direct-overlap measurement. Two objects are considered colocalised when they share enough physical overlap to pass a percentage threshold.

In plain terms: "This MarkerA object directly overlaps with MarkerB enough to count as colocalised."

This works well when the two objects are roughly similar in size. The overlap percentage is meaningful from both directions.

## What contains means

Contains is an asymmetric, directional measurement designed for situations where direct overlap alone is misleading.

This matters most when one object is much larger than the other. A small object can sit clearly inside a large object, but the large object may still fail a high percentage-overlap threshold simply because it has so much total area -- the small object only covers a tiny fraction of it.

In plain terms: "This larger object genuinely harbours that smaller object inside it, even though the direct overlap percentage from the large object's perspective would be too low to pass the coloc threshold."

Contains is a rescue for biologically real associations that would otherwise be missed due to size asymmetry.

## How they relate

Coloc and contains are related but independent. The same object can be:

1. Neither coloc nor contains -- no association
2. Coloc only -- enough direct overlap to pass the threshold
3. Contains only -- the other marker is inside this object, but the direct overlap percentage is too low (size mismatch)
4. Both coloc and contains -- passes both criteria

## Plain-language summary

Coloc means two objects directly overlap enough to pass a threshold -- this works well when objects are similar sizes. Contains is an asymmetric rescue for when a small object sits inside a large one but the large object's overlap percentage is too low to pass the coloc threshold on its own.
