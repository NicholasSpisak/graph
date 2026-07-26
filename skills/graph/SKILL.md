---
name: graph
description: Drafts an agent graph — the map of nodes, checkpoints, and routes (a state machine) that a repeatable job travels — from a job description or a stated outcome. Compiles the map to a schema-validated lock file, renders a visual review surface the user must approve before any run, and emits multi-model drivers (Claude Code Workflow + chained Codex CLI). Use when the user says "build a graph", "/graph", "map this pipeline", "turn this outcome into a pipeline", "design the topology", "wire nodes and checkpoints", wants validation gates between agent steps, or asks whether a job needs a loop or a graph.
license: MIT
metadata:
  author: Nick Spisak
  version: "2.0.0"
allowed-tools: Bash Read Write Edit Glob Grep
---

# Graph

A loop and a graph are both ways to run an agent. The difference is
**who decides the path**.

- **Loop** — you set the goal, the brief, and the bar. The agent owns
  the path: draft, self-check, rewrite, circle until it clears.
- **Graph** — you draw the steps and the routes between them ahead of
  time. The agent still decides how to handle each step; it just
  travels the routes you laid down.

The shape has a name: a **state machine**. Every node is a state the
work can be in, and a checkpoint at each one decides where it goes
next — forward when it clears, back to an earlier node when it misses.

A graph is a **map of loops and checkpoints**: some nodes run once,
others are their own loop where an agent works something out, and the
checkpoints between them read the result and route the work. Once the
map works you reuse it — feed it the next cohort and the whole
pipeline runs again.

The practice is **graph engineering**: author the map as text, compile
it to a locked machine form, validate it visually with the user, then
run it across whichever models each node deserves. The layers:

| Artifact | Layer | Carries |
|---|---|---|
| `graph.md` | authored | The map: state schema, nodes + executors, routes, gates, failure map, runtime, `max_steps` |
| `nodes/<NN>-<node>.md` | authored | One brief per node: reads, writes, instructions, done-when, refusals |
| `graph.lock.json` | compiled | Machine-canonical map + content hash + the user's approval stamp |
| `review.html` | rendered | The visual validation surface the user signs off on |
| `drivers/` | generated | Runnable drivers: Claude Code Workflow + chained `codex exec` |
| `state/<key>.*` | runtime | One file per state key, the run's audit trail |

Humans and the drafting agent edit **only the authored layer**. The
compiler regenerates everything else — including the mermaid diagram
inside `graph.md`, which is a projection of the tables, never a
source. Drivers refuse to run a map that is unapproved or has drifted
since approval.

## When to use

A graph earns its extra setup on **jobs you run every week**, with:

- validation gates the work cannot skip
- a fixed set of routes the job can take
- a clear failure point — you see the exact step something broke on

When NOT to use: one-off or exploratory work where you don't know the
path yet. A loop on its own is enough — let the agent find the path.
Say so and stop; offer to write the brief and the bar for the loop
instead. **Prefer the smallest graph that makes the real control flow
visible. Do not turn a simple one-step task into ceremony unless the
user explicitly requested it.**

## Step 0 — Outcome intake

Users arrive two ways. With a **job** ("map our weekly SEO pipeline"),
skip to Step 1. With an **outcome** ("I want to rank for X", "I want
every cohort onboarded without me"), derive the job first — this is
research and judgment work, done by the orchestrator model, not
delegated:

1. Restate the outcome as a measurable end state.
2. Identify the **repeatable job(s)** whose repetition produces that
   outcome — the deliverable one finished run emits, and the cadence.
   An outcome usually hides one core job and several one-off setup
   tasks; only the repeatable job belongs in a graph.
3. Draft the **bar**: the rubric a run's deliverable must clear. If a
   rubric file exists, verify it; if not, drafting one is part of this
   step.
4. Play the derived job back to the user in one paragraph — job,
   deliverable, cadence, bar — before drawing anything.

## Step 1 — Loop-or-graph gate

Before drawing anything, decide the primitive. Ask the user only what
you cannot infer:

1. Will this job run again on a cadence (weekly content pipeline, SEO
   funnel, cohort onboarding)? Or is it a one-off?
2. Are there checks the work must not skip?
3. Is the route set known — could the user sketch it on a napkin?

Mostly "no" → recommend a loop, not a graph. Mostly "yes" → proceed.
An outcome that survived Step 0 still gets this gate — deriving a job
does not entitle it to a graph.

## Step 2 — Gather the map's raw material

Read before you draw. Skip items the project doesn't have:

1. **The job and its deliverable** — what one finished run produces,
   and the cadence it repeats on.
2. **The bar** — the rubric each gate will score against. Verify any
   named rubric file actually exists; a named-but-missing rubric
   counts as none.
3. **The existing route** — an SOP, an n8n workflow, a checklist, or
   the user's description of how they do it by hand. If you have built
   a workflow in n8n, you have already drawn a graph; port it.
4. **Failure history** — where past runs broke. Every recurring
   failure wants a gate in front of it.
5. **Consequential choices** — decisions with real cost that deserve a
   human node.
6. **The execution surface** — does any node edit a repository? Call
   external APIs? Publish anywhere? This drives rules 3 and 9.

If the user can't answer 1–3, the job isn't graph-ready — say so.

## Step 3 — Design the topology

Full rules with rationale in
[references/topology-rules.md](references/topology-rules.md). The
ten rules:

1. Give each node **one clear responsibility and a unique output key**.
2. **Fan out only independent work.** Use a list of sources for an
   all-source join.
3. Keep **repository-editing nodes sequential** unless they operate in
   isolated worktrees.
4. Make reviewers **return JSON merged into state** — normally
   `approved`, `issues`, and `summary`.
5. Route approval to `__end__`; route rejection to a **corrective
   node and back to review**.
6. Add a **human node** only for a consequential choice or when the
   user requests a checkpoint.
7. Set a **finite `max_steps`** for every topology containing a cycle.
8. Prefer the **smallest graph** that makes the real control flow
   visible.
9. **Side effects sit after the gate that authorizes them.** Anything
   before a gate must be safe to re-run.
10. **The graph itself passes a gate.** No driver runs an unapproved
    or drifted map.

Decide per node whether it runs once or is its own loop, and **which
executor it deserves**:

- `fable:<tier>` — Claude Code. Research, synthesis, creative,
  judgment, and **every reviewer node** — the model grading the work
  should not be the model that did it.
- `codex:<tier>` — Codex CLI. Code-heavy implementation: repo edits,
  refactors, test writing, mechanical bulk. Keep a codex node's
  inputs under 272K tokens (billing doubles past it).
- `human` — consequential decisions only (rule 6).

Tiers (`frontier`, `balanced`, `fast`) resolve to model IDs in the
graph's Executors table — the only place model IDs live.

## Step 4 — Draft the map

**Path:** `<project>/docs/graphs/<YYYY-MM-DD>-<slug>/graph.md`. Create
the directory if missing. The slug is the kebab-case job name
(`client-newsletter`, `seo-article`). A redesign of the same job
updates its existing directory and bumps the frontmatter `version`;
a new dated directory means a new graph.

Follow the skeleton and worked example in
[references/graph-template.md](references/graph-template.md).
Frontmatter carries `max_steps`. Section order: `## Job`, `## State`,
`## Nodes` (with the `executor` column), `## Executors`, `## Routes`
(a table of plain edges — gate edges come from the Gates table),
`## Gates`, `## Failure map`, `## Runtime`.

**Do not hand-write the mermaid diagram.** The compiler generates it
from the tables; a placeholder block is enough on the first pass.

## Step 5 — Draft the node briefs

One file per node: `nodes/<NN>-<node>.md`, numbered in route order.
Follow [references/node-brief-template.md](references/node-brief-template.md).
Each brief states: reads (state keys), writes (its one output key),
instructions, done-when, and refusals. Reviewer briefs specify the
exact JSON shape they return.

## Step 6 — Compile and validate

```bash
python3 scripts/compile_graph.py <graph-directory>
```

The compiler parses the tables, regenerates the mermaid projection
inside `graph.md`, checks the topology mechanically (sections, unique
output keys, gate targets, reachability, `__end__`, executor
bindings, briefs), and writes `graph.lock.json` with a content hash.
Fix and re-run until exit 0. The exclusive-writer warning is expected
residue of the fix-node pattern; treat any other warning as a smell.
(`scripts/validate_graph.sh` remains as a python-free fallback for the
structural checks only.)

## Step 7 — The visual validation gate

The map does not run until the user has seen it and approved it.

```bash
python3 scripts/render_review.py <graph-directory>
```

This renders `review.html` — diagram, every table, failure map, and
the validation checklist. Put it in front of the user, best first:

1. **Publish it as a Claude Code Artifact** and share the URL.
2. **Open it locally** (`open review.html`).
3. **Push the branch** — the mermaid in `graph.md` renders natively
   in the GitHub PR; approval = PR review.

Walk the user through the checklist. Three outcomes:

- **Approve** → stamp it:
  `python3 scripts/compile_graph.py <dir> --approve "<name>"`
- **Revise** → edit `graph.md`/briefs per their notes, recompile,
  re-render, present again. Any edit after approval invalidates the
  stamp automatically — this is rule 10 enforced by hash.
- **Abort** → stop; record why in the conversation.

## Step 8 — Emit drivers, commit, hand off

```bash
python3 scripts/emit_drivers.py <graph-directory>
```

This generates from the lock: `drivers/run-codex.sh` (chained
`codex exec`, gates as `jq` branches, resumable, refuses unapproved or
drifted maps), `drivers/workflow.md` (Claude Code Workflow script —
fable nodes as subagents, codex nodes shelling out with the model
pinned), reviewer `--output-schema` files, per-node Codex agent roles,
and the shared `AGENTS.md`. See
[references/run-the-graph.md](references/run-the-graph.md) for how
each driver runs and the cross-harness state contract.

Commit:

```
docs(graphs): add <slug> graph (<one-line job description>)
```

If the project isn't a git repository, skip the commit and say so.
Then tell the user how to run it: the Workflow driver for mixed
multi-model runs, `run-codex.sh` for cron/CI, `/loop` or `/schedule`
for the cadence.

## Discipline checklist

1. One responsibility, one output key, per node — a node described
   with "and" is two nodes.
2. One writer per state key (exclusive fix-node branches are the one
   sanctioned exception); joins read many, write one.
3. Every gate is a JSON verdict (`approved`, `issues`, `summary`) —
   never a vibe. Codex reviewers get it enforced via `--output-schema`.
4. Every cycle is bounded — `max_steps` in frontmatter, caps on
   looping nodes.
5. Rejection routes to a corrective node, then re-enters the flow
   where the same gates re-check the repair — never straight to
   `__end__`. The one exception: a human node may abort the run to
   `__end__` with the decision recorded in state.
6. Repo-editing nodes are sequential unless each has its own worktree.
7. Human nodes are rare and consequential; the graph runs without a
   human everywhere else.
8. The diagram is generated from the tables — if it looks wrong, fix
   the tables and recompile; never edit the mermaid.
9. Side effects only after their authorizing gate; pre-gate work is
   re-runnable.
10. The user approved the rendered map before the first run, and the
    approval hash is fresh — the compiler, not the author, declares
    the map well-formed; the user, not the author, declares it right.

## Anti-patterns

- A god node ("research, draft, and score…") — split it.
- Two nodes writing the same state key.
- A gate with no fail route because "it'll pass".
- A cycle with no `max_steps` — the map must halt.
- Parallel repo-editing nodes sharing one cwd.
- A ceremony graph for a one-step task.
- Subjective gate checks ("better", "cleaner") — gates score against
  the rubric and return JSON.
- A human node at every edge as a comfort blanket.
- Hand-editing the mermaid block or the generated drivers — edit the
  tables and recompile.
- Running an unapproved map "just to test it" — that is what the
  loop-or-graph gate and a loop are for.
- Hardcoding a model ID anywhere but the Executors table.
- A reviewer executed by the same model that produced the work, when
  a cross-vendor reviewer is one column away.

## Additional resources

- [references/topology-rules.md](references/topology-rules.md) — the
  ten topology rules with rationale. Read before designing.
- [references/graph-template.md](references/graph-template.md) — the
  `graph.md` v2 skeleton plus a worked multi-model example. Read
  before drafting the map.
- [references/node-brief-template.md](references/node-brief-template.md)
  — node brief skeleton, reviewer JSON shape, loop-node rules.
- [references/run-the-graph.md](references/run-the-graph.md) — the
  generated drivers, the cross-harness state contract, and running
  the map in Claude Code, Codex CLI, or n8n.
- [scripts/compile_graph.py](scripts/compile_graph.py) — compile,
  validate, `--approve`, `--check`.
- [scripts/render_review.py](scripts/render_review.py) — the visual
  validation surface.
- [scripts/emit_drivers.py](scripts/emit_drivers.py) — driver
  generation.
- [schemas/graph.lock.schema.json](schemas/graph.lock.schema.json) —
  the lock file's formal JSON Schema.
- [scripts/validate_graph.sh](scripts/validate_graph.sh) — python-free
  structural fallback.
