# Topology rules

Eight rules for designing an agent graph. Each exists because a real
failure mode punished its absence. Apply all eight; when two collide,
rule 8 (smallest visible graph) wins.

## 1. One responsibility, one output key

Give each node one clear responsibility and a unique output key.

- The responsibility fits in one clause with no "and". "Audit the
  keyword and the competitors ranking for it" is one responsibility
  (produce the audit); "audit the keyword and draft the article" is
  two nodes.
- The output key is where the node's result lands in state
  (`audit`, `draft`, `review`). Exactly one node writes each key.
  When two nodes write the same key, a re-run can't tell whose value
  survived — and neither can you.

## 2. Fan out only independent work

Run nodes in parallel only when neither reads the other's output key.
Research on three separate competitors: fan out. Draft-then-score:
never — the score reads the draft.

For an all-source join (one node that synthesizes many parallel
results), pass the join node a **list of sources** — the explicit
output keys it merges — rather than "everything so far". The list is
the contract; it makes the join testable and the fan-in visible on
the diagram.

## 3. Repository-editing nodes stay sequential

Keep repo-editing nodes sequential unless they operate in isolated
worktrees. Two agents editing one working tree race each other:
half-applied edits, clobbered files, dirty diffs no one authored.
Runtimes that know this (Claude Code's Workflow among them)
automatically disable parallel execution for built-in coding-agent
backends sharing one cwd — design as if yours does not.

If parallel edits genuinely pay for themselves, give each editing node
its own worktree and add an explicit merge node after the join.

## 4. Reviewers return JSON merged into state

A reviewer node returns a machine-readable verdict, normally:

```json
{ "approved": false,
  "issues": ["H2s missing target keyword", "no internal links"],
  "summary": "Draft covers the topic but fails on-page checks." }
```

Merged into state under the reviewer's output key. Gates route on
`approved`; corrective nodes work from `issues`. Prose verdicts
("looks pretty good, maybe tighten the intro") cannot be routed on
and cannot be trended across runs.

## 5. Approval ends; rejection corrects and re-reviews

Route approval to `__end__` (or the next stage). Route rejection to a
**corrective node**, then back to the **same review**. "Back to the
same review" means the same gate ultimately re-checks the repair —
not necessarily a direct edge; re-entering upstream (fix → assemble →
score) is normal and preferred when intermediate nodes must re-process
the repair. The corrective node reads `issues` and fixes exactly
those; the re-review confirms the fix. Two anti-routes to refuse:

- rejection → `__end__` ("ship it anyway") — the gate was decoration;
- rejection → the original producer with no corrective step — the
  producer re-runs from scratch and re-rolls the dice instead of
  fixing the named issues.

## 6. Human nodes are rare and consequential

Add a human node only for a consequential choice (spend money,
publish publicly, delete data, pick between strategies) or when the
user explicitly requests a checkpoint. A human node is a full stop —
the run parks until someone shows up. Sprinkling them everywhere
converts an automated pipeline back into a to-do list.

A human gate is the one gate allowed a **third outcome**: abort —
"skip this issue", "kill this run" — routed to `__end__` with the
decision recorded in state. Abort is a decision, not a failure, so
rule 5's no-rejection-to-`__end__` does not apply to it. Draw the
abort as a labeled edge in the diagram and note it in the gate's
check cell; the validator checks only the pass and fail columns.

## 7. Every cycle gets a finite max_steps

Any topology containing a cycle (every review→correct→review pair is
one) sets a finite `max_steps` in the graph frontmatter, and every
looping node carries its own cap. On hitting the cap the run halts
and surfaces the last verdict — a bounded failure beats an unbounded
bill. A step is **one node execution**; time parked at a human node
does not count. Pick the number from evidence: if drafts historically
clear in two or three passes, cap at five, not fifty.

## 8. The smallest graph that shows the real control flow

Prefer the smallest graph that makes the real control flow visible.
Every node must earn its box: it has a distinct responsibility, a
distinct failure mode, or a gate that needs to sit after it. Do not
turn a simple one-step task into ceremony unless the user explicitly
requested the structure. If the diagram is a straight line with no
gates, it isn't a graph yet — it's a checklist, and a loop with a
good brief may serve better.

## Choosing node granularity

A node can be a single API call, a single agent turn, or an entire
session that is its own loop (a critic scoring drafts against a
rubric until they clear). Split when the checkpoint between two
pieces of work would route them differently on failure. Merge when a
failure in either piece sends you to the same place — a gate that
can't change the route is overhead.
