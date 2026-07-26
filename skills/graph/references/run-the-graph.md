# Running the graph

The map is harness-agnostic; the generated drivers make that
concrete. After compile → user approval → `emit_drivers.py`, the
graph directory carries everything a runtime needs. State lives on
disk in the graph's directory — `state/<key>.json` (or `.md`) per
state key — so any runtime, and any human, can inspect a run
mid-flight and resume it.

**No driver runs an unapproved map.** Both generated drivers verify
the content hash and approval stamp in `graph.lock.json` before the
first node; a drifted or unapproved map exits with a message instead
of running (topology rule 10).

## The multi-model division of labor

- **Fable (Claude Code)** orchestrates and takes the judgment nodes —
  research, synthesis, creative, and every reviewer. The model
  grading the work never wrote it.
- **Codex (`gpt-5.6-sol` and its tiers)** takes implementation nodes
  as headless workers — repo edits, mechanical bulk — invoked per
  node, with the model pinned from the Executors table.
- Gates never live inside either harness: the **driver owns the
  routes**, reads the JSON verdicts, and decides where the work goes.

## Claude Code — drivers/workflow.md (best fit for mixed graphs)

The generated Workflow script is the routes; the node briefs are the
nodes. Tell Claude Code: *"run `<graph-dir>/drivers/workflow.md` as a
workflow."*

- fable nodes run as subagents — one `agent()` per node, the brief as
  the prompt; reviewer nodes carry a JSON `schema` so the verdict
  shape is enforced by the tool layer.
- codex nodes shell out: the subagent runs the exact `codex exec`
  command embedded in the script (model, sandbox, output schema all
  pinned) and returns the result.
- Gates are `if` statements on state; the review→fix cycle is the
  same `while` loop, bounded by `max_steps`.
- Repo-editing nodes stay sequential by construction — the state
  machine is single-threaded; only declared independent fan-outs run
  `parallel()`.

**Cadence.** Put the run on repeat with `/loop` (self-paced or fixed
interval) or `/schedule` for a cron routine: each firing feeds the map
its next keyword, cohort, or ticket.

## Codex CLI — drivers/run-codex.sh (cron/CI fit)

The generated shell driver chains headless `codex exec` calls, one
per node:

- Each call pins the model (`-m gpt-5.6-sol` / `-terra` / `-luna` per
  the node's tier), the sandbox (`read-only` for reviewers,
  `workspace-write` otherwise — tighten per node if you can), and
  captures the final message with `-o`.
- **Reviewer nodes pass `--output-schema drivers/schemas/<node>.json`**
  — Codex is forced to end with JSON matching the verdict shape, so
  the gate's `jq` check always has something to route on.
- Gates are `jq -e` branches; `max_steps` is a counter the driver
  enforces. On halt-by-cap it surfaces the last verdict's `issues` —
  the failure point the map promised you.
- **Resumable:** progress persists in `state/_run.json`; re-running
  the script continues where it parked. A human node parks the run
  (exit 3) until the decision JSON exists, then re-run.
- In this all-Codex driver, fable-tier nodes run on the matching
  codex tier. That sacrifices cross-vendor review — when reviewers
  matter, prefer the Workflow driver.
- For a node that must continue a previous node's context (a fix node
  repairing its own implementation), capture the session id from
  `codex exec --json` and use `codex exec resume <id>` — sessions
  persist under `~/.codex/sessions/`.

Put the driver on cron or CI for the cadence. Codex's completion
audit works in your favor here — a node brief's "Done when" line is
exactly the evidence it looks for.

**Within-node fan-out:** `drivers/codex-agents/<node>.toml` files are
generated for each codex node. Copy them into the project's
`.codex/agents/` if a node's brief calls for Codex-native sub-agents
(one worker per file, etc.). Sub-agents fan out *inside* a node;
routing between nodes stays in the driver.

## Shared instructions — AGENTS.md

`emit_drivers.py` writes an `AGENTS.md` into the graph directory: the
state contract, the node/executor roster, and the five run rules
(follow the brief; one writer per key; JSON verdicts; side effects
after gates; never route). Codex reads it natively; reference it from
the Claude side with `@AGENTS.md` if the project keeps a CLAUDE.md.

## n8n and workflow engines

If you have built a workflow in n8n, you have already drawn a graph.
Port the map one-to-one — each agent node becomes an agent/LLM node
(or an HTTP call to a harness), each gate an IF node reading the
reviewer JSON, the review→fix cycle a loop with a counter guard for
`max_steps`. The graph doc remains the source of truth; the n8n
canvas is a rendering of it.

## LangGraph and code-native runtimes

`graph.lock.json` is deliberately shaped for a mechanical port: state
schema → the state object, nodes → node functions, gates →
conditional edges routing on the verdict fields, `__end__` → the
framework's end sentinel, `max_steps` → the recursion/step limit,
executor tiers → per-node model bindings.

## Whichever runtime: the run contract

1. State on disk, one file per key, written only by the key's owner
   node.
2. Every run halts — gates route to `__end__` or a bounded cycle;
   `max_steps` is enforced by the driver, not by hope.
3. On halt-by-cap, surface the last verdict's `issues` — that is the
   failure point the map promised you.
4. Side effects only downstream of their authorizing gate; everything
   upstream is safe to re-run (rule 9 — resumed runs re-execute the
   current node from the top).
5. A finished run leaves `state/` intact; it is the run's audit
   trail. Archive or clear it before the next run, never during.
6. The map that runs is the map that was approved — hash-checked,
   every run, by the driver.
