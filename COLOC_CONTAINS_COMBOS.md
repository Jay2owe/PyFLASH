# Colocalisation, Contains, and Combo Columns

This note explains what the current spatial-analysis columns mean, why both `coloc` and `contains` exist, and what it means to add pooled `Any` and `ComboAny` summaries.

## Why this is needed

There are two related but different ways a marker can be associated with another marker in this pipeline:

1. `coloc`
2. `contains`

They are both valid, but they answer slightly different biological questions. The current combo columns keep them separate. The proposed new logic would add a second combo view where they are pooled together.

## Basic idea

Take one marker as the **base marker**. For example, imagine we are summarising `MarkerA`.

For every other marker, the pipeline can ask:

- does this `MarkerA` object directly colocalise with `MarkerB`?
- does this `MarkerA` object contain `MarkerB`?

Those are not always the same thing.

## What `coloc` means

`coloc` is the classical direct-overlap measurement.

At the per-object level, the pipeline stores the overlap percentage between objects. A thresholded binary version is then used for summaries:

- `MarkerA_Coloc_MarkerB` = overlap percentage
- `MarkerA_ColocCountMarkerB` = 1 if overlap passes the threshold, else 0

So `coloc` means:

"This `MarkerA` object has enough direct overlap with `MarkerB` to count as colocalised by the standard threshold."

## What `contains` means

`contains` is a directional rescue case for situations where direct overlap alone can be misleading.

This is especially useful when one object is much larger than the other. A small object may sit clearly inside or within the boundary of a large object, but the large object may still fail a high percentage-overlap threshold simply because the large object has so much total volume.

So `contains` is used to say:

"This larger/base object should still count as associated with that other marker, even though the classical overlap percentage may not be high enough from the large object's point of view."

In the current spatial workflow, this comes from nearest-neighbour assignment plus an overlap gate. In practice, it is being used as an asymmetric "internalised / contained by this object" readout.

The relevant columns are:

- `MarkerA_NumColoc_MarkerB`
- `MarkerA_Contains_MarkerB`

Where `MarkerA_Contains_MarkerB = 1` means at least one `MarkerB` object has been assigned as contained within that `MarkerA` object under the current logic.

## Important difference between `coloc` and `contains`

`coloc` and `contains` are related, but they are not interchangeable.

Key points:

- `coloc` is a direct overlap call.
- `contains` is directional and asymmetric.
- `contains` is designed to rescue biologically meaningful overlap that a direct percentage threshold may miss for large objects.
- the same object can be positive for both
- the same object can be positive for one but not the other

So for one partner marker, a base object can fall into four states:

1. neither `coloc` nor `contains`
2. `coloc` only
3. `contains` only
4. both `coloc` and `contains`

## What the current combo columns do

The current combo columns treat these binary states as separate pieces of information.

For a base marker such as `MarkerA`:

- `MarkerA_ColocCountMarkerB = 1` contributes a token like `MarkerB+`
- `MarkerA_Contains_MarkerB = 1` contributes a token like `wMarkerB`

These positive tokens are combined into a single signature for each object.

Examples:

- `MarkerA_Combo_None`
  - this object is negative for all detected `coloc` and `contains` indicators
- `MarkerA_Combo_MarkerB+`
  - direct colocalisation with `MarkerB`, but no positive `contains` calls
- `MarkerA_Combo_wMarkerB`
  - contains `MarkerB`, but no positive direct `coloc` call
- `MarkerA_Combo_MarkerB+_wMarkerB`
  - both direct colocalisation and contains are positive for `MarkerB`
- `MarkerA_Combo_MarkerB+_wMarkerC`
  - direct colocalisation with `MarkerB` and contains `MarkerC`

So the current combo columns are a **full partition** of the base-marker objects.

Each object is assigned to exactly one combo signature.

That is why, for one base marker, all current combo percentages add up to 100%.

## Why the current combo view can be hard to read

The current detailed combo view is useful when the distinction between direct overlap and containment matters.

However, it can also fragment biologically similar objects across multiple columns.

For example, if the main question is:

"Is `MarkerA` associated with `MarkerB` in either acceptable way?"

then the current detailed combo view splits that across:

- `MarkerB+`
- `wMarkerB`
- `MarkerB+_wMarkerB`

That makes it harder to read the overall relationship quickly.

## What the pooled combo view would mean

The requested new logic is:

For each partner marker, define a pooled positive state:

`MarkerA associated with MarkerB` = `MarkerA_ColocCountMarkerB OR MarkerA_Contains_MarkerB`

In words:

"Count this base-marker object as positive for MarkerB if it either directly colocalises with MarkerB or contains MarkerB."

This does **not** replace the existing detailed columns. It is a second, simplified interpretation layer.

## Standalone `Any` columns

The pooled logic is used in two ways:

1. **Standalone `Any` summaries**
2. **`ComboAny` summaries**

The standalone `Any` logic asks, for each partner marker separately:

"How many `MarkerA` objects were positive for `MarkerB` by either rule?"

These are reported with count-style names so they follow the same convention as the other count outputs:

- `MarkerA_Any_MarkerB_Count`
- `MarkerA_Any_MarkerB_CountRaw`
- `MarkerA_Any_MarkerB_Count%`

Meaning:

- `Count` = normalized count per tissue volume
- `CountRaw` = section-averaged raw count before tissue-volume normalization
- `Count%` = percentage of `MarkerA` objects positive for `MarkerB` by either rule

The same count-style summary naming is now used for the base `Coloc` and `Contains` families as well:

- `MarkerA_Coloc_MarkerB_Count`
- `MarkerA_Coloc_MarkerB_CountRaw`
- `MarkerA_Coloc_MarkerB_Count%`
- `MarkerA_Contains_MarkerB_Count`
- `MarkerA_Contains_MarkerB_CountRaw`
- `MarkerA_Contains_MarkerB_Count%`

## Why the pooled view is useful

The pooled view answers a simpler biological question:

"Is this object associated with that marker by either accepted rule?"

That is often the more intuitive summary when:

- the exact mechanism (`coloc` vs `contains`) is not the main question
- large objects would otherwise look artificially negative in the direct-overlap-only view
- users want a cleaner combo table with fewer split categories

## Recommended way to implement it

The cleanest implementation is to keep two parallel combo families:

1. **Current detailed combo family**
   - keeps `coloc` and `contains` separate
   - preserves the existing biological detail

2. **New pooled combo family**
   - for each partner marker, first collapse:
     - `pooled_B = ColocCountB OR Contains_B`
   - then build combo signatures from the pooled marker-level positives only

This keeps the current behaviour intact while adding the simpler interpretation that many users will actually want to read first.

## Why the pooled combo percentages can also sum to 100%

If the pooled combo family is built the same way as the current one, each object still gets exactly one pooled signature.

Example with partner markers `B` and `C`:

- object 1: associated with neither -> `None`
- object 2: associated with `B` only -> `B`
- object 3: associated with `C` only -> `C`
- object 4: associated with both -> `B_C`

Again, every object belongs to one pooled combo only.

So the pooled combo percentages can also add up to 100%.

## Worked example

Imagine four `MarkerA` objects and one partner marker `MarkerB`.

Their detailed states are:

1. object 1: `coloc = 1`, `contains = 0`
2. object 2: `coloc = 0`, `contains = 1`
3. object 3: `coloc = 1`, `contains = 1`
4. object 4: `coloc = 0`, `contains = 0`

### Current detailed combo interpretation

- object 1 -> `MarkerB+`
- object 2 -> `wMarkerB`
- object 3 -> `MarkerB+_wMarkerB`
- object 4 -> `None`

Percentages:

- `MarkerB+` = 25%
- `wMarkerB` = 25%
- `MarkerB+_wMarkerB` = 25%
- `None` = 25%

Total = 100%

### Pooled combo interpretation

Now define:

`MarkerB pooled positive = coloc OR contains`

Then:

- object 1 -> `MarkerB`
- object 2 -> `MarkerB`
- object 3 -> `MarkerB`
- object 4 -> `None`

Percentages:

- `MarkerB` = 75%
- `None` = 25%

Total = 100%

This is a much cleaner answer if the biological question is simply whether `MarkerA` is associated with `MarkerB` by either accepted rule.

## Interpretation guide

Use the **detailed combo columns** when you need to know:

- whether the relationship is direct-threshold colocalisation
- whether it is a containment/internalisation-style call
- whether both are true at the same time

Use the **standalone `Any` columns** when you need to know:

- how many objects are positive for one partner marker by either rule
- the raw count, normalized count, or percentage for that one partner marker

Use the **pooled combo columns** when you need to know:

- whether the base marker is associated with another marker in either accepted way
- the overall combined burden of "coloc or contains"
- a simpler combo readout that is easier to explain and compare

## Short plain-language explanation

If you need to explain this quickly to someone else:

"The pipeline currently keeps two kinds of marker association separate. `coloc` means standard direct overlap above threshold. `contains` is an asymmetric rescue case for large objects, where another marker is effectively inside or assigned to that object even if the large object would not pass the direct overlap threshold by percentage alone. The current combo columns keep these separate, so they split into categories like `MarkerB+`, `wMarkerB`, or both. What we want to add is a second combo view where those are pooled together, so an object is counted as positive for MarkerB if it either colocalises with MarkerB or contains MarkerB."`
