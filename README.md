# graph

A portable agent skill that drafts **agent graphs** — the map of
nodes, checkpoints, and routes (a state machine) that a repeatable
job travels — for **Claude Code** and **OpenAI Codex**.

Invoke it as `/graph` in Claude Code, or `$graph` in Codex.

**Documentation site:** https://nicholasspisak.github.io/graph/ — a
plain-language walkthrough of loops vs graphs and the topology rules.

**Learn to run agents like this:** join the
[AI Operator Academy](https://www.skool.com/aioperatoracademy/about)
community — designing loops, briefing agents, and shipping real work.

## Loop vs graph

Both are ways to run an agent. The difference is **who decides the
path**:

- A **loop** starts with you — you set the goal, the brief, and the
  bar it has to clear. The agent owns the path: draft, self-check,
  rewrite, circle until it clears.
- A **graph** is you drawing the steps and the routes between them
  ahead of time. The agent still decides how to handle each step; it
  just travels the routes you laid down.

The shape has a name — a **state machine**. Every node is a state the
work can be in, and a checkpoint at each one decides where it goes
next: forward when it clears, back to an earlier node when it misses.
A graph is a **map of loops and checkpoints** — some nodes run once,
others are their own loop, and the checkpoints between them read the
result and route the work.

A loop is enough for one-off work where you don't know the path yet.
A graph earns its extra setup on the jobs you run every week:
validation gates the work cannot skip, a fixed set of routes, and a
clear failure point — you see the exact step something broke on. Once
the map works you reuse it: feed it the next cohort and the whole
pipeline runs again.

## What the skill drafts

One graph gets one committed directory in your project's
`docs/graphs/`:

| Artifact | Carries |
|---|---|
| `graph.md` | The map: state schema, nodes table, mermaid routes diagram, gates table, failure map, runtime notes, `max_steps` |
| `nodes/<NN>-<node>.md` | One brief per node: reads, writes, instructions, done-when, refusals |

The map is **harness-agnostic**: the same two artifacts drive Claude
Code (Workflow or chained sessions), Codex CLI (chained
`codex exec`), an n8n canvas, or a LangGraph port — see
[references/run-the-graph.md](skills/graph/references/run-the-graph.md).

## The topology rules

The skill designs to eight rules (full rationale in
[references/topology-rules.md](skills/graph/references/topology-rules.md)):

1. One clear responsibility and a unique output key per node.
2. Fan out only independent work; all-source joins take a list of
   sources.
3. Repository-editing nodes stay sequential unless isolated in
   worktrees.
4. Reviewers return JSON merged into state — `approved`, `issues`,
   `summary`.
5. Approval routes to `__end__`; rejection routes to a corrective
   node and back to review.
6. Human nodes only for consequential choices or requested
   checkpoints.
7. A finite `max_steps` for every topology containing a cycle.
8. The smallest graph that makes the real control flow visible — no
   ceremony for one-step tasks.

And before any of that, a **loop-or-graph gate**: if the job is
one-off or exploratory, the skill tells you a loop is enough and
stops.

## Install

**Preferred — the Vercel skills CLI** ([`npx skills`](https://github.com/vercel-labs/skills)):

```bash
npx skills add NicholasSpisak/graph
```

That's the whole onboarding. The CLI detects which agents you have
(Claude Code, Codex, and others), then asks where to put the skill —
this project (into each agent's skills dir, e.g. `.claude/skills/`)
or globally for your local agent — and whether to symlink
(auto-updates) or copy. It reads `SKILL.md` straight from this repo;
nothing to clone.

Skip the prompts for a global, both-harness, non-interactive install:

```bash
npx skills add NicholasSpisak/graph -g -a claude-code -a codex -y
```

Useful flags: `-g` global (user-level) instead of project · `-a <agent>`
target a specific agent · `--copy` copy instead of symlink · `-l` list
skills without installing · `-y` skip confirmation prompts. Full syntax:
[`npx skills add --help`](https://github.com/vercel-labs/skills).

<details>
<summary>Alternative — the bundled <code>install.sh</code></summary>

```bash
git clone https://github.com/NicholasSpisak/graph.git
cd graph
./install.sh              # both harnesses, user-level
```

Options:

```bash
./install.sh --claude         # Claude Code only  → ~/.claude/skills/graph
./install.sh --codex          # Codex only        → ~/.agents/skills/graph
./install.sh --project        # current repo      → .claude/skills + .agents/skills
./install.sh --codex-prompt   # optional /prompts:graph command for Codex
```

Manual install: copy `skills/graph/` to `~/.claude/skills/graph`
(Claude Code) and/or `~/.agents/skills/graph` (Codex). Restart the
harness.

</details>

## Use

**Claude Code**

```
/graph our weekly SEO article pipeline — audit, draft, score against the rubric, publish
```

**Codex CLI**

```
$graph our weekly SEO article pipeline — audit, draft, score against the rubric, publish
```

(or `/skills` to browse; or `/prompts:graph <job>` if you installed
the prompt shim). Codex also auto-selects the skill when a request
matches its description.

The skill gates loop-vs-graph, gathers the job's raw material (the
deliverable, the bar, the failure history), designs the topology,
drafts `graph.md` plus one brief per node into `docs/graphs/`,
validates the map mechanically with the bundled
[`validate_graph.sh`](skills/graph/scripts/validate_graph.sh), and
tells you how to run it in your harness.

## Repository layout

```
skills/graph/
├── SKILL.md                              # the skill (agentskills.io standard)
├── references/
│   ├── topology-rules.md                 # the 8 design rules + rationale
│   ├── graph-template.md                 # graph.md skeleton + worked example
│   ├── node-brief-template.md            # node brief skeleton + reviewer JSON
│   └── run-the-graph.md                  # running the map in each harness
└── scripts/
    └── validate_graph.sh                 # 8 mechanical map checks
codex/graph.md                            # optional Codex custom-prompt shim
install.sh
```

## When not to use it

One-off or exploratory work where you don't know the path yet — let
the agent find it with a loop and a good brief. The graph's setup
cost amortizes only against jobs you'll run again: the content
pipeline, the SEO/AEO funnel, the cohort accelerator. And the skill's
own rule 8 applies to itself: the smallest graph that makes the real
control flow visible, never ceremony for a one-step task.

## Community

Graph is one piece of a bigger practice — designing loops, briefing
agents, and shipping real work. Come build with the community:
**[Join the AI Operator Academy](https://www.skool.com/aioperatoracademy/about).**

## Credits

Skill by Nick Spisak. Companion to
[goal-writer](https://github.com/NicholasSpisak/goal-writer) — past
the loop, the next thing you design is the map it runs inside.

## License

[MIT](LICENSE).
