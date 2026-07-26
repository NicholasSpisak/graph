# Topology rules

Ten rules for designing an agent graph. Each exists because a real
failure mode punished its absence. Apply all ten; when two collide,
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

## 9. Side effects sit after the gate that authorizes them

A node that publishes, spends money, or deletes data runs only
downstream of the gate that authorizes it; anything upstream of a gate
must be safe to re-execute. Two forces make this a rule, not a
preference: a rejected run re-enters upstream nodes (rule 5), and
every serious runtime — LangGraph interrupts, Temporal replay, a
re-run `codex exec` chain — re-executes a node from the top when a
paused run resumes. A side effect placed before its gate fires twice
the first time a draft misses the rubric.

If a node mixes safe work and a side effect, split it: the safe half
before the gate, the effect after. The failure map gets clearer for
free — "charged twice" now surfaces at exactly one node.

## 10. The graph itself passes a gate

The map is validated twice, by different judges. The **compiler**
declares it well-formed: sections present, output keys unique, every
gate double-routed, everything reachable, `__end__` reachable,
executors resolvable. The **user** declares it right: they see the
rendered map — diagram, tables, failure map, checklist — and approve
it, which stamps the content hash into `graph.lock.json`.

Drivers check the stamp before every run and refuse a map that is
unapproved or has changed since approval. Editing `graph.md` or a
brief after sign-off invalidates the stamp automatically; recompile,
re-render, re-approve. This is the plan-gate: it fires once per map
version, not once per run, so it costs nothing on the cadence — and it
is the difference between "the pipeline we agreed on" and "whatever
the drafting agent last wrote".

## Choosing an executor per node

Every node names its executor: `fable:<tier>`, `codex:<tier>`, or
`human`. Tiers — `frontier`, `balanced`, `fast` — resolve to model IDs
in the graph's Executors table, the only place a model ID may appear.

- **fable (Claude Code)** takes research, synthesis, creative work,
  judgment calls, and every reviewer node. Cross-vendor review is the
  point: the model grading the work should not be the model that did
  it, and with two harnesses on the map that independence costs one
  table cell.
- **codex (Codex CLI)** takes code-heavy implementation: repo edits,
  refactors, test writing, mechanical bulk. Keep a codex node's input
  under 272K tokens — past that boundary input billing doubles.
- **human** appears exactly where rule 6 already allows.

Match tier to stakes, not habit: a `fast`-tier model adding internal
links is a win; a `fast`-tier model deciding what to publish is a
failure mode with a discount.

## Choosing node granularity

A node can be a single API call, a single agent turn, or an entire
session that is its own loop (a critic scoring drafts against a
rubric until they clear). Split when the checkpoint between two
pieces of work would route them differently on failure. Merge when a
failure in either piece sends you to the same place — a gate that
can't change the route is overhead.
