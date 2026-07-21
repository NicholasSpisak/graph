---
name: graph
description: Drafts an agent graph — the map of nodes, checkpoints, and routes (a state machine) that a repeatable job travels — as a committed graph doc plus one brief per node, mechanically validated. Use when the user says "build a graph", "/graph", "map this pipeline", "turn this job into a graph", "design the topology", "wire nodes and checkpoints", wants validation gates between agent steps, or asks whether a job needs a loop or a graph.
license: MIT
metadata:
  author: Nick Spisak
  version: "1.0.0"
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

This skill drafts that map as two committed artifacts:

| Artifact | Carries |
|---|---|
| `graph.md` | The map: state schema, nodes table, routes diagram, gates table, failure map, runtime notes, `max_steps` |
| `nodes/<NN>-<node>.md` | One brief per node: what it reads, what it writes, its instructions, done-when, refusals |

The pair is harness-agnostic: the same map drives Claude Code
(Workflow or chained sessions), Codex CLI (chained `codex exec`), or a
human walking the steps — see
[references/run-the-graph.md](references/run-the-graph.md).

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

## Step 0 — Loop-or-graph gate

Before drawing anything, decide the primitive. Ask the user only what
you cannot infer:

1. Will this job run again on a cadence (weekly content pipeline, SEO
   funnel, cohort onboarding)? Or is it a one-off?
2. Are there checks the work must not skip?
3. Is the route set known — could the user sketch it on a napkin?

Mostly "no" → recommend a loop, not a graph. Mostly "yes" → proceed.

## Step 1 — Gather the map's raw material

Read before you draw. Skip items the project doesn't have:

1. **The job and its deliverable** — what one finished run produces,
   and the cadence it repeats on.
2. **The bar** — the rubric each gate will score against. Verify any
   named rubric file actually exists; a named-but-missing rubric
   counts as none. If the user has no rubric, drafting one is part
   of this step, not a follow-up.
3. **The existing route** — an SOP, an n8n workflow, a checklist, or
   the user's description of how they do it by hand. If you have built
   a workflow in n8n, you have already drawn a graph; port it.
4. **Failure history** — where past runs broke. Every recurring
   failure wants a gate in front of it.
5. **Consequential choices** — decisions with real cost that deserve a
   human node.
6. **The execution surface** — does any node edit a repository? Call
   external APIs? Publish anywhere? This drives rule 3 below.

If the user can't answer 1–3, the job isn't graph-ready — say so.

## Step 2 — Design the topology

Full rules with rationale in
[references/topology-rules.md](references/topology-rules.md). The
eight rules:

1. Give each node **one clear responsibility and a unique output key**.
2. **Fan out only independent work.** Use a list of sources for an
   all-source join.
3. Keep **repository-editing nodes sequential** unless they operate in
   isolated worktrees. Runtimes disable parallel execution for coding
   agents sharing one cwd.
4. Make reviewers **return JSON merged into state** — normally
   `approved`, `issues`, and `summary`.
5. Route approval to `__end__`; route rejection to a **corrective
   node and back to review**.
6. Add a **human node** only for a consequential choice or when the
   user requests a checkpoint.
7. Set a **finite `max_steps`** for every topology containing a cycle.
8. Prefer the **smallest graph** that makes the real control flow
   visible.

Decide per node whether it runs once or is its own loop (an internal
critic scoring drafts against a rubric until they clear). A node that
loops states its internal bar and cap in its brief.

## Step 3 — Draft the map

**Path:** `<project>/docs/graphs/<YYYY-MM-DD>-<slug>/graph.md`. Create
the directory if missing. The slug is the kebab-case job name
(`client-newsletter`, `seo-article`). A redesign of the same job
updates its existing directory and bumps the frontmatter `version`;
a new dated directory means a new graph.

Follow the skeleton and worked example in
[references/graph-template.md](references/graph-template.md).
Frontmatter carries `max_steps`. Section order:

1. `## Job` — one paragraph: the deliverable, the cadence, the bar.
2. `## State` — table of every state key: key, type, written by,
   read by. One writer per key — with one sanctioned exception: a
   producer and its corrective node (or two exclusive branches) may
   share a key when the routes guarantee only one writes it per
   pass. Mark that cell "exclusive" or the validator fails it.
3. `## Nodes` — table: number, node, responsibility (one clause),
   output key, runs (`once` | `loop (cap N)` | `human`).
4. `## Routes` — a `mermaid` flowchart: entry node through gates to
   `__end__`. Every edge you draw is a route the work may take; draw
   no others.
5. `## Gates` — table: gate, after which node, the JSON check, pass
   target, fail target. Every gate has both.
6. `## Failure map` — where each known failure class surfaces, so a
   broken run points at one node.
7. `## Runtime` — which harness runs it, worktree/isolation notes,
   and the `max_steps` restated with why that number.

## Step 4 — Draft the node briefs

One file per node: `nodes/<NN>-<node>.md`, numbered in route order.
Follow [references/node-brief-template.md](references/node-brief-template.md).
Each brief states: reads (state keys), writes (its one output key),
instructions, done-when, and refusals (what the node must not do).
Reviewer briefs specify the exact JSON shape they return.

## Step 5 — Validate, commit, hand off

Run the bundled validator:

```bash
scripts/validate_graph.sh <graph-directory>
```

Mechanical checks: required sections present; a mermaid routes block;
positive integer `max_steps` in frontmatter; output keys unique across
nodes; every gate has both a pass and a fail target; every gate target
is a declared node or `__end__`; at least one route reaches `__end__`;
one brief per node (warns if missing). Fix and re-run until exit 0.
The exclusive-writer warning is expected residue of the fix-node
pattern; treat any other warning as a smell.

Commit:

```
docs(graphs): add <slug> graph (<one-line job description>)
```

If the project isn't a git repository, skip the commit and say so.

Then tell the user how to run the map in their harness —
[references/run-the-graph.md](references/run-the-graph.md) covers
Claude Code (Workflow, chained sessions, `/loop` for the cadence),
Codex CLI (chained `codex exec` with state on disk), and the n8n
mapping.

## Discipline checklist

1. One responsibility, one output key, per node — a node described
   with "and" is two nodes.
2. One writer per state key (exclusive fix-node branches are the one
   sanctioned exception); joins read many, write one.
3. Every gate is a JSON verdict (`approved`, `issues`, `summary`) —
   never a vibe.
4. Every cycle is bounded — `max_steps` in frontmatter, caps on
   looping nodes.
5. Rejection routes to a corrective node, then re-enters the flow
   where the same gates re-check the repair (upstream re-entry is
   normal) — never straight to `__end__`. The one exception: a
   human node may abort the run to `__end__` with the decision
   recorded in state; abort is a decision, not a failure.
6. Repo-editing nodes are sequential unless each has its own worktree.
7. Human nodes are rare and consequential; the graph runs without a
   human everywhere else.
8. The mermaid diagram and the gates table agree — the diagram is the
   map, not decoration.
9. Failure map names one node per failure class; "somewhere in the
   middle" is not a failure point.
10. Validate mechanically before committing; the validator, not the
    author, declares the map well-formed.

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
- Routes in prose that aren't in the diagram, or vice versa.
- Rebuilding the loop inside every node brief — a node that runs once
  gets instructions, not a critic.

## Additional resources

- [references/topology-rules.md](references/topology-rules.md) — the
  eight topology rules with rationale and examples. Read before
  designing.
- [references/graph-template.md](references/graph-template.md) — full
  `graph.md` skeleton plus a worked SEO-article example. Read before
  drafting the map.
- [references/node-brief-template.md](references/node-brief-template.md)
  — node brief skeleton, reviewer JSON shape, loop-node rules.
- [references/run-the-graph.md](references/run-the-graph.md) — running
  the same map in Claude Code, Codex CLI, or n8n. Read when handing
  off.
- [scripts/validate_graph.sh](scripts/validate_graph.sh) — run it;
  don't re-implement the checks by hand.
