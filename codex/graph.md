---
description: Draft an agent graph — the map of nodes, checkpoints, and routes a repeatable job travels — plus one brief per node
argument-hint: "<the job to map>"
---

Use the graph skill for this task. Read
`.agents/skills/graph/SKILL.md` in the current repository if it
exists, otherwise `~/.agents/skills/graph/SKILL.md`, in full and
follow it exactly — including its loop-or-graph gate, the topology
rules and templates it references, and its validation script — to
draft an agent graph for:

$ARGUMENTS

If neither skill file exists, tell the user to install it:
https://github.com/NicholasSpisak/graph (`./install.sh --codex`).
