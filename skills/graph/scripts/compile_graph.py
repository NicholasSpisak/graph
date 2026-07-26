#!/usr/bin/env python3
"""compile_graph.py — compile a graph.md map into graph.lock.json.

The lock file is the machine-canonical form of the graph (gh-aw
compile-and-lock pattern): schema-shaped JSON, a content hash over
graph.md + node briefs, and an approval stamp written only by
--approve. The compiler also REGENERATES the mermaid block inside
graph.md from the Nodes, Routes, and Gates tables — the diagram is a
projection, never a source.

Usage:
  compile_graph.py <graph-dir>                  compile + validate
  compile_graph.py <graph-dir> --approve NAME   stamp approval (lock must be fresh)
  compile_graph.py <graph-dir> --check          verify freshness + approval (for drivers)

Exit 0 = well-formed (warnings allowed). Exit 1 = fix and re-run.
--check: 0 = approved and fresh, 2 = stale or unapproved.

No third-party dependencies. The formal schema ships alongside at
../schemas/graph.lock.schema.json for external tooling.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_EXECUTORS = {
    "frontier": {"fable": "claude-fable-5", "codex": "gpt-5.6-sol"},
    "balanced": {"fable": "claude-sonnet-5", "codex": "gpt-5.6-terra"},
    "fast": {"fable": "claude-haiku-4-5", "codex": "gpt-5.6-luna"},
}

ERRORS: list[str] = []
WARNINGS: list[str] = []


def err(msg: str) -> None:
    ERRORS.append(msg)
    print(f"FAIL  {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"warn  {msg}")


def ok(msg: str) -> None:
    print(f"ok    {msg}")


# ---------------------------------------------------------------- parsing

def parse_frontmatter(text: str):
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        err("graph.md has no YAML frontmatter block")
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if kv:
            fm[kv.group(1)] = kv.group(2).strip().strip('"')
    return fm, text[m.end():]


def split_sections(body: str) -> dict:
    """Map '## Name' -> section content (up to the next ##)."""
    sections = {}
    matches = list(re.finditer(r"^## (.+)$", body, re.MULTILINE))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[m.group(1).strip()] = body[m.end():end]
    return sections


def norm_header(h: str) -> str:
    h = h.replace("→", "").replace("->", "")
    return re.sub(r"\s+", " ", h.strip().strip("*_`")).lower()


def parse_table(content: str):
    """First markdown table in content -> list of row dicts keyed by header."""
    rows = [l for l in content.splitlines() if l.lstrip().startswith("|")]
    rows = [r for r in rows if not re.match(r"^\s*\|[\s\-:|]+\|\s*$", r)]
    if len(rows) < 2:
        return []
    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]
    headers = [norm_header(c) for c in cells(rows[0])]
    out = []
    for line in rows[1:]:
        c = cells(line)
        if len(c) != len(headers):
            err(f"table row has {len(c)} cells, expected {len(headers)}: {line.strip()}")
            continue
        out.append(dict(zip(headers, c)))
    return out


def strip_cell(v: str) -> str:
    return v.strip().strip("`").strip()


def parse_runs(raw: str):
    v = strip_cell(raw).lower()
    if v == "once":
        return "once", None
    if v == "human":
        return "human", None
    m = re.match(r"loop\s*\(\s*cap\s+(\d+)\s*\)", v)
    if m:
        return "loop", int(m.group(1))
    err(f"runs value '{raw}' is not once / loop (cap N) / human")
    return "once", None


def parse_executor(raw: str, executors: dict):
    v = strip_cell(raw).lower()
    if v == "human":
        return {"harness": "human", "tier": None, "model": None}
    m = re.match(r"(fable|codex):(\w+)$", v)
    if not m:
        err(f"executor '{raw}' is not human, fable:<tier>, or codex:<tier>")
        return {"harness": "fable", "tier": "frontier",
                "model": executors.get("frontier", {}).get("fable")}
    harness, tier = m.group(1), m.group(2)
    if tier not in executors:
        err(f"executor tier '{tier}' not in the Executors table ({', '.join(executors)})")
        return {"harness": harness, "tier": tier, "model": None}
    return {"harness": harness, "tier": tier, "model": executors[tier][harness]}


def parse_check(raw: str):
    """'review.approved == true' -> state key 'review', jq expr '.approved == true'."""
    v = strip_cell(raw)
    m = re.match(r"^(\w[\w-]*)\.(.+)$", v)
    if not m:
        return {"raw": v, "state_key": None, "jq": None}
    return {"raw": v, "state_key": m.group(1), "jq": "." + m.group(2).strip()}


# ---------------------------------------------------------------- mermaid

def mermaid_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name)


def generate_mermaid(nodes, gates, edges) -> str:
    human = {n["id"] for n in nodes if n["runs"] == "human"}
    gate_ids = {g["id"] for g in gates}

    def ref(name: str) -> str:
        if name == "__end__":
            return "END([__end__])"
        if name in gate_ids:
            return f"g_{mermaid_id(name)}{{{name}}}"
        if name in human:
            return f"n_{mermaid_id(name)}[/{name}/]"
        return f"n_{mermaid_id(name)}[{name}]"

    lines = [
        "flowchart TD",
        "  %% generated by compile_graph.py from the Nodes, Routes, and Gates",
        "  %% tables — do not edit by hand; re-run the compiler instead",
    ]
    for e in edges:
        label = f" -- {e['label']} -->" if e.get("label") else " -->"
        lines.append(f"  {ref(e['from'])}{label} {ref(e['to'])}")
    lines += [
        "  classDef gateStyle fill:#fff3cd,stroke:#b58900,color:#333",
        "  classDef humanStyle fill:#e7d8f7,stroke:#6f42c1,color:#333",
    ]
    if gate_ids:
        lines.append("  class " + ",".join(f"g_{mermaid_id(g)}" for g in sorted(gate_ids)) + " gateStyle")
    if human:
        lines.append("  class " + ",".join(f"n_{mermaid_id(h)}" for h in sorted(human)) + " humanStyle")
    return "\n".join(lines)


def replace_mermaid(text: str, mermaid: str) -> str:
    """Replace (or insert) the mermaid block inside the ## Routes section."""
    block = f"```mermaid\n{mermaid}\n```"
    sec = re.search(r"(^## Routes$)(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not sec:
        return text
    body = sec.group(2)
    if "```mermaid" in body:
        new_body = re.sub(r"```mermaid\n.*?```", block, body, count=1, flags=re.DOTALL)
    else:
        new_body = body.rstrip("\n") + "\n\n" + block + "\n\n"
    return text[:sec.start(2)] + new_body + text[sec.end(2):]


# ---------------------------------------------------------------- hashing

def content_hash(graph_dir: Path):
    """Deterministic hash over graph.md + briefs.

    Algorithm (mirrored in generated run-codex.sh): sha256 each file,
    build sorted 'relpath:hex' lines, sha256 the joined lines.
    """
    files = {"graph.md": graph_dir / "graph.md"}
    nodes_dir = graph_dir / "nodes"
    if nodes_dir.is_dir():
        for p in sorted(nodes_dir.glob("*.md")):
            files[f"nodes/{p.name}"] = p
    per_file = {}
    for rel, p in files.items():
        per_file[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    lines = "\n".join(f"{rel}:{per_file[rel]}" for rel in sorted(per_file))
    return hashlib.sha256(lines.encode()).hexdigest(), per_file


# ---------------------------------------------------------------- compile

def compile_graph(graph_dir: Path) -> int:
    graph_path = graph_dir / "graph.md"
    if not graph_path.is_file():
        print(f"FAIL  {graph_path} not found", file=sys.stderr)
        return 1

    text = graph_path.read_text()
    fm, body = parse_frontmatter(text)
    sections = split_sections(body)

    for sec in ["Job", "State", "Nodes", "Routes", "Gates", "Failure map", "Runtime"]:
        if sec in sections:
            ok(f"section: ## {sec}")
        else:
            err(f"missing section: ## {sec}")

    max_steps = fm.get("max_steps", "")
    if re.match(r"^\d+$", max_steps) and int(max_steps) > 0:
        max_steps = int(max_steps)
        ok(f"max_steps: {max_steps}")
    else:
        err("frontmatter needs a positive integer max_steps (every cycle must be bounded)")
        max_steps = 0

    # Executors (optional section; defaults ship with the compiler)
    executors = {}
    if "Executors" in sections:
        for row in parse_table(sections["Executors"]):
            tier = strip_cell(row.get("tier", ""))
            fable = next((strip_cell(v) for k, v in row.items() if k.startswith("fable")), None)
            codex = next((strip_cell(v) for k, v in row.items() if k.startswith("codex")), None)
            if tier and fable and codex:
                executors[tier] = {"fable": fable, "codex": codex}
    if not executors:
        executors = DEFAULT_EXECUTORS
        warn("no Executors table — using compiler defaults "
             "(frontier=claude-fable-5/gpt-5.6-sol, balanced, fast)")

    # Nodes
    nodes = []
    for row in parse_table(sections.get("Nodes", "")):
        name = strip_cell(row.get("node", ""))
        if not name:
            continue
        runs, cap = parse_runs(row.get("runs", ""))
        if "executor" not in row:
            err(f"node '{name}': Nodes table has no executor column "
                "(v2 requires one: fable:<tier> | codex:<tier> | human)")
            executor = {"harness": "fable", "tier": "frontier",
                        "model": executors.get("frontier", {}).get("fable")}
        else:
            executor = parse_executor(row["executor"], executors)
        if (runs == "human") != (executor["harness"] == "human"):
            err(f"node '{name}': runs and executor disagree — "
                "'human' must appear in both columns or neither")
        nodes.append({
            "n": int(strip_cell(row.get("#", "0")) or 0),
            "id": name,
            "responsibility": strip_cell(row.get("responsibility", "")),
            "output_key": strip_cell(row.get("output key", "")),
            "runs": runs,
            "cap": cap,
            "executor": executor,
        })
    if not nodes:
        err("Nodes table is empty or malformed "
            "(| # | node | responsibility | output key | runs | executor |)")
        return finish(1)
    ok(f"nodes declared: {len(nodes)}")
    node_ids = {n["id"] for n in nodes}

    # unique output keys (exclusive branches excepted, declared in State)
    state_section = sections.get("State", "")
    keys = [n["output_key"] for n in nodes if n["output_key"]]
    dupes = {k for k in keys if keys.count(k) > 1}
    for k in sorted(dupes):
        if "exclusive" in state_section.lower():
            warn(f"output key '{k}' has multiple writers — allowed only for "
                 "exclusive branches (declared in State)")
        else:
            err(f"output key '{k}' written by multiple nodes and no 'exclusive' "
                "branch declared in State")
    if not dupes:
        ok("output keys unique")

    # State table
    state = []
    for row in parse_table(state_section):
        state.append({
            "key": strip_cell(row.get("key", "")),
            "type": strip_cell(row.get("type", "")),
            "written_by": strip_cell(row.get("written by", "")),
            "read_by": [s.strip() for s in
                        re.split(r"[,;]", strip_cell(row.get("read by", ""))) if s.strip()],
        })
    state_keys = {s["key"] for s in state}
    for n in nodes:
        if n["output_key"] and n["output_key"] not in state_keys:
            warn(f"node '{n['id']}' writes '{n['output_key']}' but the State table "
                 "has no such key")

    # Gates
    gates = []
    for row in parse_table(sections.get("Gates", "")):
        gid = strip_cell(row.get("gate", ""))
        if not gid:
            continue
        g = {
            "id": gid,
            "after": strip_cell(row.get("after", "")),
            "check": parse_check(row.get("check", "")),
            "pass": strip_cell(row.get("pass", "")),
            "fail": strip_cell(row.get("fail", "")),
        }
        if not g["pass"]:
            err(f"gate '{gid}' has no pass target")
        if not g["fail"]:
            err(f"gate '{gid}' has no fail target — 'it'll pass' is not a route")
        if g["after"] not in node_ids:
            err(f"gate '{gid}' sits after '{g['after']}' — not a declared node")
        if gid in node_ids:
            err(f"gate '{gid}' shares a name with a node — rename one")
        if g["check"]["state_key"] and g["check"]["state_key"] not in state_keys:
            warn(f"gate '{gid}' checks state key '{g['check']['state_key']}' "
                 "which is not in the State table")
        gates.append(g)
    gate_ids = {g["id"] for g in gates}
    ok(f"gates declared: {len(gates)}")

    # Routes table (plain edges: linear steps, fan-out/joins, abort edges)
    edges = []
    seen_edges = set()

    def add_edge(frm, to, label=""):
        if (frm, to) in seen_edges:
            warn(f"duplicate edge {frm} -> {to}")
            return
        seen_edges.add((frm, to))
        edges.append({"from": frm, "to": to, "label": label})

    for g in gates:
        add_edge(g["after"], g["id"])
        if g["pass"]:
            add_edge(g["id"], g["pass"], "pass")
        if g["fail"]:
            add_edge(g["id"], g["fail"], "fail")

    for row in parse_table(sections.get("Routes", "")):
        frm = strip_cell(row.get("from", ""))
        to = strip_cell(row.get("to", ""))
        if not frm or not to:
            continue
        add_edge(frm, to, strip_cell(row.get("label", "")))

    declared = node_ids | gate_ids | {"__end__"}
    for e in edges:
        for endpoint in (e["from"], e["to"]):
            if endpoint not in declared:
                err(f"route {e['from']} -> {e['to']}: '{endpoint}' is not a "
                    "declared node, gate, or __end__")
    for e in edges:
        if e["from"] == "__end__":
            err("__end__ has an outgoing route — the map must halt")

    # every node needs an outgoing edge; everything reachable; __end__ reachable
    outgoing = {}
    for e in edges:
        outgoing.setdefault(e["from"], []).append(e["to"])
    for n in nodes:
        if n["id"] not in outgoing:
            err(f"node '{n['id']}' has no outgoing route — dead end that is not __end__")

    entry = min(nodes, key=lambda n: n["n"])["id"]
    reachable, frontier = {entry}, [entry]
    while frontier:
        cur = frontier.pop()
        for nxt in outgoing.get(cur, []):
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)
    if "__end__" in reachable:
        ok("__end__ reachable from entry")
    else:
        err("no route reaches __end__ from the entry node — the map must halt")
    for name in sorted((node_ids | gate_ids) - reachable):
        err(f"'{name}' is unreachable from entry node '{entry}'")

    # Failure map
    failure_map = [
        {"failure_class": strip_cell(r.get("failure class", "")),
         "surfaces_at": strip_cell(r.get("surfaces at", "")),
         "symptom": strip_cell(r.get("what you'll see", ""))}
        for r in parse_table(sections.get("Failure map", ""))
    ]

    # reviewer nodes: their output key is routed on via .approved
    reviewer_keys = {g["check"]["state_key"] for g in gates
                     if g["check"]["jq"] and ".approved" in g["check"]["jq"]}
    for n in nodes:
        n["reviewer"] = n["output_key"] in reviewer_keys

    # one brief per node
    nodes_dir = graph_dir / "nodes"
    for n in nodes:
        if nodes_dir.is_dir() and list(nodes_dir.glob(f"[0-9][0-9]-{n['id']}.md")):
            ok(f"brief: {n['id']}")
        else:
            warn(f"no brief for node '{n['id']}' (expected nodes/NN-{n['id']}.md)")

    # regenerate the mermaid projection inside graph.md
    mermaid = generate_mermaid(nodes, gates, edges)
    new_text = replace_mermaid(text, mermaid)
    if "## Routes" in text and "```mermaid" not in new_text:
        err("could not place the generated mermaid block in ## Routes")
    if new_text != text:
        graph_path.write_text(new_text)
        ok("mermaid diagram regenerated in graph.md")
    else:
        ok("mermaid diagram up to date")

    if ERRORS:
        return finish(1)

    # lock file
    chash, per_file = content_hash(graph_dir)
    lock_path = graph_dir / "graph.lock.json"
    approval = None
    if lock_path.is_file():
        try:
            old = json.loads(lock_path.read_text())
            if old.get("approval") and old.get("hashes", {}).get("content") == chash:
                approval = old["approval"]
            elif old.get("approval"):
                warn("graph changed since approval — approval stamp invalidated, "
                     "re-validate with the user and re-approve")
        except (json.JSONDecodeError, OSError):
            warn("existing graph.lock.json unreadable — rebuilding")

    lock = {
        "lock_version": 1,
        "graph": fm.get("graph", graph_dir.name),
        "version": fm.get("version", ""),
        "date": fm.get("date", ""),
        "owner": fm.get("owner", ""),
        "cadence": fm.get("cadence", ""),
        "max_steps": max_steps,
        "entry": entry,
        "executors": executors,
        "state": state,
        "nodes": nodes,
        "gates": gates,
        "edges": edges,
        "failure_map": failure_map,
        "hashes": {"content": chash, "files": per_file},
        "compiled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approval": approval,
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    ok(f"lock written: {lock_path.name} (content {chash[:12]}…)")
    if not approval:
        print("\nnext  render the review surface and validate with the user, then:")
        print(f'      compile_graph.py {graph_dir} --approve "<name>"')
    return finish(0)


def finish(code: int) -> int:
    print()
    print("PASS  graph compiled and well-formed" if code == 0
          else "FAIL  fix the items above and re-run")
    return code


# ---------------------------------------------------------------- approve / check

def load_lock(graph_dir: Path):
    lock_path = graph_dir / "graph.lock.json"
    if not lock_path.is_file():
        print("FAIL  no graph.lock.json — run the compiler first", file=sys.stderr)
        return None, lock_path
    return json.loads(lock_path.read_text()), lock_path


def approve(graph_dir: Path, name: str) -> int:
    lock, lock_path = load_lock(graph_dir)
    if lock is None:
        return 1
    chash, _ = content_hash(graph_dir)
    if lock.get("hashes", {}).get("content") != chash:
        print("FAIL  graph.md or briefs changed since last compile — "
              "re-run the compiler, re-validate with the user, then approve",
              file=sys.stderr)
        return 1
    lock["approval"] = {
        "approved_by": name,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graph_hash": chash,
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    print(f"ok    approved by {name} at {lock['approval']['date']} ({chash[:12]}…)")
    return 0


def check(graph_dir: Path) -> int:
    lock, _ = load_lock(graph_dir)
    if lock is None:
        return 2
    chash, _ = content_hash(graph_dir)
    if lock.get("hashes", {}).get("content") != chash:
        print("STALE  graph files changed since last compile — recompile and re-approve")
        return 2
    approval = lock.get("approval")
    if not approval or approval.get("graph_hash") != chash:
        print("UNAPPROVED  the map has not passed its validation gate — "
              "render the review surface and get sign-off")
        return 2
    print(f"ok    approved by {approval['approved_by']} on {approval['date']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("graph_dir", type=Path)
    ap.add_argument("--approve", metavar="NAME",
                    help="stamp approval into a fresh lock")
    ap.add_argument("--check", action="store_true",
                    help="verify freshness + approval (drivers run this)")
    args = ap.parse_args()
    if not args.graph_dir.is_dir():
        print(f"usage: compile_graph.py <graph-directory>", file=sys.stderr)
        return 1
    if args.approve:
        return approve(args.graph_dir, args.approve)
    if args.check:
        return check(args.graph_dir)
    return compile_graph(args.graph_dir)


if __name__ == "__main__":
    sys.exit(main())
