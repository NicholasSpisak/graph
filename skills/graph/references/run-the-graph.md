# Running the graph

The map is harness-agnostic. `graph.md` plus the node briefs contain
everything a runtime needs; only the driver changes. State lives on
disk in the graph's directory — `state/<key>.json` (or `.md`) per
state key — so any runtime, and any human, can inspect a run
mid-flight and resume it.

## Claude Code

**Workflow tool (best fit).** Claude Code's Workflow runs a
deterministic script that spawns one subagent per node — the script
is the routes, the agents are the nodes. Ask Claude Code to "run
docs/graphs/<slug>/graph.md as a workflow": each `agent()` call gets
the node's brief as its prompt, reviewer nodes use a JSON `schema`
matching the brief's Writes shape, gates become `if` statements on
the returned object, and the review→fix cycle becomes a bounded
`while` loop honoring `max_steps`. Repo-editing nodes stay
sequential; the runtime disables parallel execution for coding-agent
backends sharing one cwd (use worktree isolation if you fan them
out).

**Chained sessions (the vault-accelerator pattern).** For graphs
whose nodes are entire working sessions, run one session per node in
route order. Each session reads the prior nodes' state files, does
its work (a session may be its own loop internally), and writes its
output key before ending. The gates are the few minutes you spend
reading the verdict between sessions — or a small session of their
own.

**Cadence.** The graph is one run. Put the run on its repeat cadence
with `/loop` (self-paced or fixed interval) or `/schedule` for a cron
routine: each firing feeds the map its next keyword, cohort, or
ticket.

## Codex CLI

Chain headless `codex exec` calls, one per node, in a small driver
script. Each call's prompt is the node brief plus the paths of the
state files it reads; the call must end by writing its output key to
`state/`. Gates are plain shell: parse the reviewer's JSON with `jq`,
branch on `.approved`, count passes against `max_steps`. Put the
driver on cron or CI for the cadence. Codex's completion audit works
in your favor here — a node brief's "Done when" line is exactly the
evidence it looks for.

## n8n and workflow engines

If you have built a workflow in n8n, you have already drawn a graph:
nodes wired together, branches that fire on a condition, a step that
loops until it clears. Port the map one-to-one — each agent node
becomes an agent/LLM node (or an HTTP call to a harness), each gate
an IF node reading the reviewer JSON, the review→fix cycle a loop
with a counter guard for `max_steps`. The graph doc remains the
source of truth; the n8n canvas is a rendering of it.

## LangGraph and code-native runtimes

The map translates directly: state schema → the state object, nodes →
node functions, gates → conditional edges routing on the reviewer
fields, `__end__` → the framework's end sentinel, `max_steps` → the
recursion/step limit. The Nodes and Gates tables are deliberately
shaped so this port is mechanical.

## Whichever runtime: the run contract

1. State on disk, one file per key, written only by the key's owner
   node.
2. Every run halts — gates route to `__end__` or a bounded cycle;
   `max_steps` is enforced by the driver, not by hope.
3. On halt-by-cap, surface the last verdict's `issues` — that is the
   failure point the map promised you.
4. A finished run leaves `state/` intact; it is the run's audit
   trail. Archive or clear it before the next run, never during.
