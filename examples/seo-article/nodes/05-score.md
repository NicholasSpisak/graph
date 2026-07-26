# score

**Responsibility:** score the article against the rubric
**Runs:** once

## Reads

article

## Writes

`review — JSON: {approved, issues[], summary}`

## Instructions

(Worked example — in a real graph this section carries the node's full
contract: concrete steps, tools, sources, style. See
references/node-brief-template.md.)

## Done when

The output key exists and matches the Writes shape.

## Refusals

- Does no other node's work; never routes.
