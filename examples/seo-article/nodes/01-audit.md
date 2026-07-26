# audit

**Responsibility:** rank + competitor audit for the keyword
**Runs:** once

## Reads

—

## Writes

`audit — JSON: {keyword, ranking_url|null, competitor_gap[], serp_notes}`

## Instructions

(Worked example — in a real graph this section carries the node's full
contract: concrete steps, tools, sources, style. See
references/node-brief-template.md.)

## Done when

The output key exists and matches the Writes shape.

## Refusals

- Does no other node's work; never routes.
