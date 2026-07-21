# Node brief template

One file per node: `nodes/<NN>-<node>.md`, numbered in route order
(`01-audit.md`, `02-draft-new.md`, …). The brief is the node's whole
contract — an agent dropped into the node with only this file and the
state keys it names should produce the output key.

## Skeleton

````markdown
# <node-name>

**Responsibility:** <the one clause from the Nodes table, verbatim>
**Runs:** <once | loop (cap N) | human>

## Reads

| state key | why |
|---|---|
| <key> | <what this node takes from it> |

## Writes

`<output key>` — <type and shape. For JSON, show the exact shape.>

## Instructions

<The how. Written to the agent that will run this node: concrete
steps, tools it may use, sources it must consult, style it must
match. This is the longest section — the node IS this section.>

## Done when

<Observable completion: the output key exists and satisfies <check>.
Not "when the work is good" — the gate decides that.>

## Refusals

- <What this node must not do — the fence. e.g. "Never publishes;
  publish is node 8." "No schema changes." "Does not re-run audit.">
````

## Reviewer nodes

A reviewer's Writes section specifies the exact JSON it returns:

````markdown
## Writes

`review` — JSON, exactly:

```json
{ "approved": <bool>,
  "issues": ["<specific, fixable defect>", ...],
  "summary": "<one sentence>" }
```

- `approved: true` requires zero issues of severity blocker.
- Every issue must name the rubric line it fails and where in the
  artifact it fails it — the fix node repairs from this list alone.
````

Reviewers score against the rubric file named in `## Job`, never
against taste. If no rubric exists, writing one precedes writing the
reviewer.

## Loop nodes

A node that is its own loop (drafts + self-checks until it clears an
internal bar) adds two lines to the skeleton:

```markdown
**Internal bar:** <what the node's own critic checks before emitting>
**Cap:** <N passes; on hitting the cap, emit best-so-far and note it>
```

The internal bar is cheaper and looser than the graph's gates — it
catches obvious misses before spending a gate transition. It never
replaces the gate.

## Human nodes

A human node's brief states the decision, the options, the
information the human needs on screen to decide, and where their
choice lands in state. It is a decision brief, not a task list —
if the human is doing work rather than choosing, that work wanted
its own agent node.

## Corrective (fix) nodes

- Reads the last verdict's `issues` and the artifact.
- Fixes **exactly the named issues** — refusal: no opportunistic
  rewrites, no scope growth.
- Re-enters the graph at the node the Routes diagram says, so the
  same gates re-check the repair.
