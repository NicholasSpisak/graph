#!/usr/bin/env python3
"""emit_drivers.py — generate runnable drivers from graph.lock.json.

Reads the compiled lock (run compile_graph.py first) and emits, inside
the graph directory:

  drivers/run-codex.sh          all-Codex driver: chained `codex exec`,
                                gates as jq branches, resumable via
                                state/_run.json, refuses to run an
                                unapproved or drifted map
  drivers/workflow.md           Claude Code Workflow driver: Fable runs
                                fable nodes as subagents, codex nodes
                                shell out to `codex exec`
  drivers/schemas/<node>.json   JSON Schemas for reviewer verdicts,
                                passed to codex via --output-schema
  drivers/codex-agents/<n>.toml custom Codex agent roles for codex
                                nodes (copy into the project's
                                .codex/agents/ if you want within-node
                                sub-agent fan-out)
  AGENTS.md                     shared instruction file for both
                                harnesses (state contract + run rules)

The drivers own the routes. Nodes never route; they produce their one
output key and stop.

Usage: emit_drivers.py <graph-dir>
"""

import json
import re
import sys
from pathlib import Path

REVIEWER_SCHEMA = {
    "type": "object",
    "required": ["approved", "issues", "summary"],
    "properties": {
        "approved": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "additionalProperties": True,
}


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


class Emitter:
    def __init__(self, graph_dir: Path, lock: dict):
        self.dir = graph_dir
        self.lock = lock
        self.nodes = {n["id"]: n for n in lock["nodes"]}
        self.gates = {g["id"]: g for g in lock["gates"]}
        self.state = {s["key"]: s for s in lock["state"]}
        self.outgoing = {}
        for e in lock["edges"]:
            self.outgoing.setdefault(e["from"], []).append(e["to"])

    def ext(self, key: str) -> str:
        s = self.state.get(key)
        return "json" if (s and "json" in s["type"].lower()) else "md"

    def reads(self, node_id: str):
        return [k for k, s in self.state.items() if node_id in s["read_by"]]

    def state_file(self, key: str) -> str:
        return f"state/{key}.{self.ext(key)}"

    def next_of(self, node_id: str):
        outs = self.outgoing.get(node_id, [])
        if len(outs) == 1:
            return outs[0], None
        # fan-out: allowed only when every branch is a plain node whose single
        # successor is one shared join node — drivers serialize the branches.
        branches = outs
        joins = set()
        for b in branches:
            if b in self.gates or b == "__end__":
                return None, f"fan-out from '{node_id}' includes gate/__end__ '{b}'"
            b_outs = self.outgoing.get(b, [])
            if len(b_outs) != 1:
                return None, (f"fan-out from '{node_id}': branch '{b}' does not "
                              "have exactly one successor")
            joins.add(b_outs[0])
        if len(joins) != 1:
            return None, (f"fan-out from '{node_id}' has no single join node "
                          f"(found {sorted(joins)})")
        return {"branches": branches, "join": joins.pop()}, None

    # ------------------------------------------------------------ schemas

    def emit_schemas(self):
        out_dir = self.dir / "drivers" / "schemas"
        written = []
        for n in self.lock["nodes"]:
            if n.get("reviewer"):
                out_dir.mkdir(parents=True, exist_ok=True)
                p = out_dir / f"{n['id']}.json"
                p.write_text(json.dumps(REVIEWER_SCHEMA, indent=2) + "\n")
                written.append(p)
        return written

    # ------------------------------------------------------------ codex roles

    def emit_codex_roles(self):
        out_dir = self.dir / "drivers" / "codex-agents"
        written = []
        for n in self.lock["nodes"]:
            if n["executor"]["harness"] != "codex":
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            brief = self.brief_path(n["id"])
            toml = f'''name = "{n['id']}"
description = "{n['responsibility']}"
developer_instructions = """
Follow the node brief at {brief} exactly — its Reads, Writes,
Done-when, and Refusals are the contract. Produce only this node's
output key. Never route between nodes; the driver owns the routes.
"""
model = "{n['executor']['model']}"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
'''
            p = out_dir / f"{n['id']}.toml"
            p.write_text(toml)
            written.append(p)
        return written

    def brief_path(self, node_id: str) -> str:
        nodes_dir = self.dir / "nodes"
        if nodes_dir.is_dir():
            hits = sorted(nodes_dir.glob(f"[0-9][0-9]-{node_id}.md"))
            if hits:
                return f"nodes/{hits[0].name}"
        return f"nodes/NN-{node_id}.md"

    # ------------------------------------------------------------ run-codex.sh

    def emit_codex_driver(self):
        L = self.lock
        lines = [
            "#!/usr/bin/env bash",
            f"# run-codex.sh — generated driver for the '{L['graph']}' agent graph.",
            "# Generated by emit_drivers.py — regenerate after recompiling; do not hand-edit.",
            "#",
            "# Chains headless `codex exec` calls, one per node. Gates are jq",
            "# branches on state JSON. Resumable: progress persists in",
            "# state/_run.json; re-run the script to continue a parked run.",
            "set -euo pipefail",
            '',
            'GRAPH_DIR="$(cd "$(dirname "$0")/.." && pwd)"',
            'STATE_DIR="$GRAPH_DIR/state"',
            'RUN_FILE="$STATE_DIR/_run.json"',
            'mkdir -p "$STATE_DIR" "$STATE_DIR/.last"',
            'command -v codex >/dev/null || { echo "codex CLI not found" >&2; exit 1; }',
            'command -v jq    >/dev/null || { echo "jq not found" >&2; exit 1; }',
            '',
            '# ---- freshness + approval gate (mirrors compile_graph.py hashing) ----',
            'content_hash() {',
            '  local lines',
            '  lines=$({ printf \'graph.md:%s\\n\' "$(shasum -a 256 "$GRAPH_DIR/graph.md" | cut -d" " -f1)"',
            '    for f in "$GRAPH_DIR"/nodes/*.md; do',
            '      [ -e "$f" ] || continue',
            '      printf \'nodes/%s:%s\\n\' "$(basename "$f")" "$(shasum -a 256 "$f" | cut -d" " -f1)"',
            '    done; } | LC_ALL=C sort)',
            '  printf \'%s\' "$lines" | shasum -a 256 | cut -d" " -f1',
            '}',
            'LOCK="$GRAPH_DIR/graph.lock.json"',
            '[ -f "$LOCK" ] || { echo "no graph.lock.json — compile first" >&2; exit 2; }',
            'CUR_HASH=$(content_hash)',
            'LOCK_HASH=$(jq -r \'.hashes.content\' "$LOCK")',
            'APPROVED_HASH=$(jq -r \'.approval.graph_hash // empty\' "$LOCK")',
            'if [ "$CUR_HASH" != "$LOCK_HASH" ]; then',
            '  echo "STALE: graph files changed since compile — recompile, re-validate, re-approve" >&2; exit 2',
            'fi',
            'if [ "$CUR_HASH" != "$APPROVED_HASH" ]; then',
            '  echo "UNAPPROVED: the map has not passed its validation gate" >&2; exit 2',
            'fi',
            '',
            f'MAX_STEPS={L["max_steps"]}',
            f'ENTRY={sh_quote(L["entry"])}',
            'current="$ENTRY"; step=0',
            'if [ -f "$RUN_FILE" ]; then',
            '  current=$(jq -r .current "$RUN_FILE"); step=$(jq -r .step "$RUN_FILE")',
            '  echo "resuming at node $current (step $step)"',
            'fi',
            '',
            'save_run() { printf \'{"current":"%s","step":%s}\\n\' "$1" "$2" > "$RUN_FILE"; }',
            '',
        ]

        # per-node runner functions
        for n in L["nodes"]:
            lines += self._codex_node_fn(n)

        # main state machine
        lines += ['echo "run: $ENTRY -> __end__ (max_steps $MAX_STEPS)"',
                  'while :; do',
                  '  save_run "$current" "$step"',
                  '  case "$current" in',
                  '    __end__)',
                  '      rm -f "$RUN_FILE"',
                  '      echo "DONE — state/ holds the audit trail"; exit 0 ;;']
        for g in L["gates"]:
            key = g["check"]["state_key"]
            jqx = g["check"]["jq"] or "."
            sfile = self.state_file(key) if key else ""
            lines += [
                f'    {sh_quote(g["id"])})',
                f'      if jq -e {sh_quote(jqx)} "$GRAPH_DIR/{sfile}" >/dev/null 2>&1; then',
                f'        current={sh_quote(g["pass"])}',
                '      else',
                f'        current={sh_quote(g["fail"])}',
                '      fi ;;',
            ]
        for n in L["nodes"]:
            nid = n["id"]
            nxt, fan_err = self.next_of(nid)
            lines += [f'    {sh_quote(nid)})',
                      '      step=$((step + 1))',
                      '      if [ "$step" -gt "$MAX_STEPS" ]; then',
                      '        echo "HALT: max_steps reached — last verdicts:" >&2',
                      '        ls "$STATE_DIR"/*.json >/dev/null 2>&1 && '
                      'grep -l \'"issues"\' "$STATE_DIR"/*.json 2>/dev/null '
                      '| while read -r f; do echo "--- $f"; jq -r \'.issues[]?\' "$f"; done >&2',
                      '        exit 1',
                      '      fi',
                      f'      run_{fn_name(nid)}']
            if fan_err:
                lines.append(f'      echo "NOTE: {fan_err} — drive this graph '
                             f'via drivers/workflow.md instead" >&2; exit 1')
            elif isinstance(nxt, dict):
                for b in nxt["branches"]:
                    lines += [f'      step=$((step + 1))',
                              f'      run_{fn_name(b)}   # fan-out branch, serialized']
                lines.append(f'      current={sh_quote(nxt["join"])} ;;')
                continue
            else:
                lines.append(f'      current={sh_quote(nxt)} ;;')
                continue
            lines.append('      ;;')
        lines += ['    *) echo "unknown state: $current" >&2; exit 1 ;;',
                  '  esac',
                  'done',
                  '']
        out = self.dir / "drivers" / "run-codex.sh"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        out.chmod(0o755)
        return out

    def _codex_node_fn(self, n: dict):
        nid, key = n["id"], n["output_key"]
        brief = self.brief_path(nid)
        sfile = self.state_file(key)
        reads = self.reads(nid)
        read_note = "; ".join(f"{k}: $GRAPH_DIR/{self.state_file(k)}" for k in reads) \
            or "none"

        if n["runs"] == "human":
            return [
                f'run_{fn_name(nid)}() {{  # human decision node',
                f'  if [ ! -s "$GRAPH_DIR/{sfile}" ]; then',
                f'    echo "PARKED: human decision needed — read $GRAPH_DIR/{brief},"',
                f'    echo "write the decision JSON to $GRAPH_DIR/{sfile}, then re-run."',
                '    exit 3',
                '  fi',
                '}',
                '',
            ]

        # in the all-codex driver, fable-tier nodes also run on codex at the
        # matching tier; cross-vendor review needs the workflow driver.
        tier = n["executor"]["tier"] or "frontier"
        model = self.lock["executors"].get(tier, {}).get("codex", "gpt-5.6-sol")
        sandbox = "read-only" if n.get("reviewer") else "workspace-write"
        schema_flag = ""
        if n.get("reviewer"):
            schema_flag = f' \\\n    --output-schema "$GRAPH_DIR/drivers/schemas/{nid}.json"'
        cap_note = f" (internal cap {n['cap']} — the brief carries its own bar)" \
            if n["runs"] == "loop" else ""
        prompt = (
            f"You are node '{nid}' of the {self.lock['graph']} agent graph{cap_note}. "
            f"Follow the brief at $GRAPH_DIR/{brief} exactly. "
            f"State inputs — {read_note}. "
            f"Your final message must be only the '{key}' output the brief's "
            "Writes section specifies. Do not do any other node's work."
        )
        fn = [
            f'run_{fn_name(nid)}() {{',
            f'  echo "node {nid} [{n["executor"]["harness"]}:{tier} -> {model}]"',
            f'  local out="$STATE_DIR/.last/{nid}.out"',
            f'  codex exec \\',
            f'    -m {sh_quote(model)} \\',
            f'    --sandbox {sandbox} \\',
            '    --skip-git-repo-check \\',
            f'    -o "$out"{schema_flag} \\',
            f'    --cd "$GRAPH_DIR" \\',
            f'    "{prompt}" < /dev/null',
        ]
        if self.ext(key) == "json":
            fn += [f'  jq -e . "$out" >/dev/null || {{ echo "node {nid}: output is not '
                   f'valid JSON" >&2; exit 1; }}']
        fn += [f'  cp "$out" "$GRAPH_DIR/{sfile}"', '}', '']
        return fn

    # ------------------------------------------------------------ workflow.md

    def emit_workflow(self):
        L = self.lock
        state_obj = "{}"
        js = [
            "export const meta = {",
            f"  name: '{L['graph']}-run',",
            f"  description: 'Run the {L['graph']} agent graph (generated driver)',",
            "  phases: [{ title: 'Run' }],",
            "}",
            f"const DIR = '{self.dir.as_posix()}'  // path from the project root",
            f"const MAX_STEPS = {L['max_steps']}",
            "const REVIEWER_SCHEMA = " + json.dumps(REVIEWER_SCHEMA),
            f"const state = {state_obj}",
            f"let current = '{L['entry']}', step = 0",
            "",
            "while (current !== '__end__') {",
        ]
        # gates first (no step cost), then nodes
        for g in L["gates"]:
            cond = self._js_check(g)
            js += [
                f"  if (current === '{g['id']}') {{",
                f"    current = ({cond}) ? '{g['pass']}' : '{g['fail']}'",
                "    continue",
                "  }",
            ]
        js += [
            "  if (++step > MAX_STEPS) {",
            "    log(`halted at max_steps ${MAX_STEPS} — surface the last verdict's issues`)",
            "    break",
            "  }",
        ]
        for n in L["nodes"]:
            js += self._js_node(n)
        js += [
            "  }",  # placeholder fixed below — see assembly
        ]
        # assemble node blocks as if/continue chain instead of trailing brace
        js = js[:-1]
        js += ["}", "return { state, halted_at: current }"]

        body = "\n".join(js)
        md = f"""# {L['graph']} — Claude Code Workflow driver

Generated by emit_drivers.py from graph.lock.json — regenerate after
recompiling; do not hand-edit.

**To run:** tell Claude Code
`run {self.dir.as_posix()}/drivers/workflow.md as a workflow`.
The script below is the routes; the node briefs are the nodes. Fable
nodes run as subagents; codex nodes shell out to `codex exec` with the
model pinned. Repo-editing nodes stay sequential (the state machine is
single-threaded by construction).

Before running, Claude must verify the map passed its gate:

```bash
python3 <skill>/scripts/compile_graph.py {self.dir.as_posix()} --check
```

```js
{body}
```

Notes for the operator:
- This is a generated scaffold that mirrors the lock exactly; review it
  once before first run.
- Reviewer nodes return schema-enforced JSON; gates branch on it.
- codex nodes require the Codex CLI to be installed and authenticated.
- Human nodes pause the run: the script asks you to decide and records
  the decision in state.
"""
        out = self.dir / "drivers" / "workflow.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md)
        return out

    def _js_check(self, g: dict) -> str:
        key, jqx = g["check"]["state_key"], g["check"]["jq"]
        if not key or not jqx:
            return f"/* manual check: {g['check']['raw']} */ true"
        return f"state['{key}']{jqx}"

    def _js_node(self, n: dict):
        nid, key = n["id"], n["output_key"]
        brief = self.brief_path(nid)
        reads = self.reads(nid)
        nxt, fan_err = self.next_of(nid)
        read_note = ", ".join(f"{k} (state['{k}'])" for k in reads) or "none"
        is_json = self.ext(key) == "json"

        lines = [f"  if (current === '{nid}') {{"]
        if n["runs"] == "human":
            lines += [
                f"    // human decision node — park the run for the operator",
                f"    log('human decision needed: read ${{DIR}}/{brief} and decide')",
                f"    state['{key}'] = await agent(`Present the decision brief at "
                f"${{DIR}}/{brief} to the user with AskUserQuestion, then return "
                f"their decision as JSON.`, {{label: '{nid}', schema: {{type:'object'}}}})",
            ]
        elif n["executor"]["harness"] == "codex":
            model = n["executor"]["model"]
            sandbox = "read-only" if n.get("reviewer") else "workspace-write"
            schema_arg = f", schema: REVIEWER_SCHEMA" if n.get("reviewer") else ""
            schema_flag = (f" --output-schema ${{DIR}}/drivers/schemas/{nid}.json"
                           if n.get("reviewer") else "")
            lines += [
                f"    state['{key}'] = await agent(`Run this exact command with Bash, "
                f"then return the contents of ${{DIR}}/state/.last/{nid}.out"
                f"{' parsed as JSON' if is_json else ''}:\\n"
                f"codex exec -m {model} --sandbox {sandbox} --skip-git-repo-check "
                f"--cd ${{DIR}}{schema_flag} -o ${{DIR}}/state/.last/{nid}.out "
                f"\"Follow the brief at {brief}. State inputs: {read_note}. Final "
                f"message = only the '{key}' output.\"`, "
                f"{{label: 'codex:{nid}'{schema_arg}}})",
            ]
        else:
            schema_arg = ", schema: REVIEWER_SCHEMA" if n.get("reviewer") else ""
            lines += [
                f"    state['{key}'] = await agent(`You are node '{nid}'. Read and "
                f"follow ${{DIR}}/{brief} exactly. State inputs: {read_note} — also "
                f"on disk under ${{DIR}}/state/. Return only the '{key}' output the "
                f"brief's Writes section specifies.`, {{label: '{nid}'{schema_arg}}})",
            ]
        lines.append(f"    // persist for audit trail + cross-harness resume")
        lines.append(
            f"    await agent(`Write the {'JSON' if is_json else 'markdown'} below to "
            f"${{DIR}}/{self.state_file(key)} with the Write tool, verbatim:\\n"
            f"${{ {'JSON.stringify(' if is_json else 'String('}state['{key}'])}}`, "
            f"{{label: 'persist:{key}', effort: 'low'}})")
        if fan_err:
            lines.append(f"    log('NOTE: {fan_err} — extend this scaffold by hand')")
            lines.append("    break")
        elif isinstance(nxt, dict):
            lines.append("    // fan-out: branches are independent (topology rule 2)")
            branch_calls = ", ".join(
                f"() => agent(`You are node '{b}'. Read and follow ${{DIR}}/"
                f"{self.brief_path(b)} exactly. Return only its output key.`, "
                f"{{label: '{b}'}})" for b in nxt["branches"])
            keys = [self.nodes[b]["output_key"] for b in nxt["branches"]]
            lines.append(f"    const fan = await parallel([{branch_calls}])")
            for i, k in enumerate(keys):
                lines.append(f"    state['{k}'] = fan[{i}]")
            lines.append(f"    step += {len(nxt['branches'])}")
            lines.append(f"    current = '{nxt['join']}'")
        else:
            lines.append(f"    current = '{nxt}'")
        lines.append("    continue")
        lines.append("  }")
        return lines

    # ------------------------------------------------------------ AGENTS.md

    def emit_agents_md(self):
        L = self.lock
        rows = "\n".join(
            f"| `{s['key']}` | {s['type']} | {s['written_by']} | "
            f"{', '.join(s['read_by']) or '—'} |"
            for s in L["state"])
        node_rows = "\n".join(
            f"| {n['id']} | {n['responsibility']} | "
            f"{n['executor']['harness']}"
            f"{':' + n['executor']['tier'] if n['executor']['tier'] else ''} |"
            for n in L["nodes"])
        md = f"""# {L['graph']} — agent instructions

Generated by emit_drivers.py from graph.lock.json. Both harnesses read
this file (Claude Code via `@AGENTS.md`, Codex natively).

You are executing ONE node of a validated agent graph. The driver owns
the routes; you own only your node's output key.

## Run rules

1. Read your node brief in `nodes/` and follow it exactly — Reads,
   Writes, Done-when, Refusals.
2. State lives in `state/`, one file per key, written only by the
   key's owner node. Never write another node's key.
3. Reviewers return JSON exactly as their brief specifies —
   `approved`, `issues`, `summary`. Gates route on it.
4. Side effects (publish, spend, delete) only occur in nodes placed
   after the gate that authorizes them. If your node runs before a
   gate, your work must be safe to re-run.
5. Do not route, skip, or re-order nodes. If you cannot produce your
   output key, say so in your output — the failure map depends on
   failures surfacing at the right node.

## State contract

| key | type | written by | read by |
|---|---|---|---|
{rows}

## Nodes

| node | responsibility | executor |
|---|---|---|
{node_rows}
"""
        out = self.dir / "AGENTS.md"
        out.write_text(md)
        return out


def fn_name(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", node_id)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: emit_drivers.py <graph-directory>", file=sys.stderr)
        return 1
    graph_dir = Path(sys.argv[1])
    lock_path = graph_dir / "graph.lock.json"
    if not lock_path.is_file():
        print("FAIL  no graph.lock.json — run compile_graph.py first", file=sys.stderr)
        return 1
    lock = json.loads(lock_path.read_text())
    em = Emitter(graph_dir, lock)

    for p in em.emit_schemas():
        print(f"ok    reviewer schema: {p.relative_to(graph_dir)}")
    for p in em.emit_codex_roles():
        print(f"ok    codex agent role: {p.relative_to(graph_dir)}")
    p = em.emit_codex_driver()
    print(f"ok    codex driver: {p.relative_to(graph_dir)}")
    p = em.emit_workflow()
    print(f"ok    workflow driver: {p.relative_to(graph_dir)}")
    p = em.emit_agents_md()
    print(f"ok    shared instructions: {p.relative_to(graph_dir)}")
    if not lock.get("approval"):
        print("note  drivers will refuse to run until the map is approved "
              "(compile_graph.py --approve)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
