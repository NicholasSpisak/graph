#!/usr/bin/env python3
"""render_review.py — render review.html, the visual validation surface.

Reads graph.lock.json (run compile_graph.py first) plus the ## Job
paragraph from graph.md, and writes a single self-contained HTML page:
the color-coded routes diagram, every table, the failure map, and the
validation checklist the user signs off against.

Mermaid rendering is dual-path by design:
  - published as a Claude Code Artifact, the <pre class="mermaid">
    block renders natively (the CDN script is blocked by CSP, harmless);
  - opened locally (open review.html), the CDN script renders it.

Usage: render_review.py <graph-dir>
"""

import html
import json
import re
import sys
from pathlib import Path


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def table(headers, rows):
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def job_paragraph(graph_md: Path) -> str:
    if not graph_md.is_file():
        return ""
    m = re.search(r"^## Job$(.*?)(?=^## |\Z)", graph_md.read_text(),
                  re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def mermaid_block(graph_md: Path) -> str:
    m = re.search(r"```mermaid\n(.*?)```", graph_md.read_text(), re.DOTALL)
    return m.group(1).rstrip() if m else ""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: render_review.py <graph-directory>", file=sys.stderr)
        return 1
    graph_dir = Path(sys.argv[1])
    lock_path = graph_dir / "graph.lock.json"
    if not lock_path.is_file():
        print("FAIL  no graph.lock.json — run compile_graph.py first", file=sys.stderr)
        return 1
    lock = json.loads(lock_path.read_text())

    name = lock.get("graph", graph_dir.name)
    job = job_paragraph(graph_dir / "graph.md")
    mermaid = mermaid_block(graph_dir / "graph.md")
    nodes = lock["nodes"]
    gates = lock["gates"]
    human_nodes = [n for n in nodes if n["runs"] == "human"]
    loop_nodes = [n for n in nodes if n["runs"] == "loop"]
    reviewers = [n for n in nodes if n.get("reviewer")]
    codex_nodes = [n for n in nodes if n["executor"]["harness"] == "codex"]
    fable_nodes = [n for n in nodes if n["executor"]["harness"] == "fable"]

    def exec_badge(n):
        e = n["executor"]
        if e["harness"] == "human":
            return '<span class="badge human">human</span>'
        cls = "codex" if e["harness"] == "codex" else "fable"
        return (f'<span class="badge {cls}">{esc(e["harness"])}:{esc(e["tier"])}</span> '
                f'<code>{esc(e["model"])}</code>')

    nodes_rows = [[
        esc(n["n"]), f"<strong>{esc(n['id'])}</strong>", esc(n["responsibility"]),
        f"<code>{esc(n['output_key'])}</code>",
        esc(n["runs"] + (f" (cap {n['cap']})" if n.get("cap") else "")),
        exec_badge(n),
    ] for n in nodes]

    gates_rows = [[
        f"<strong>{esc(g['id'])}</strong>", esc(g["after"]),
        f"<code>{esc(g['check']['raw'])}</code>", esc(g["pass"]), esc(g["fail"]),
    ] for g in gates]

    exec_rows = [[f"<strong>{esc(t)}</strong>", f"<code>{esc(m['fable'])}</code>",
                  f"<code>{esc(m['codex'])}</code>"]
                 for t, m in lock["executors"].items()]

    fail_rows = [[esc(f["failure_class"]), esc(f["surfaces_at"]), esc(f["symptom"])]
                 for f in lock.get("failure_map", [])]

    state_rows = [[f"<code>{esc(s['key'])}</code>", esc(s["type"]),
                   esc(s["written_by"]), esc(", ".join(s["read_by"]))]
                  for s in lock.get("state", [])]

    checklist = [
        ("Every rejection routes to a corrective node, never to __end__",
         "verified mechanically by the compiler (pass and fail targets on every gate)"),
        (f"Every cycle is bounded — max_steps {lock['max_steps']}"
         + (", looping nodes: " + ", ".join(f"{n['id']} (cap {n['cap']})" for n in loop_nodes)
            if loop_nodes else ""),
         "verified mechanically"),
        ("Human nodes are consequential decisions only: "
         + (", ".join(n["id"] for n in human_nodes) if human_nodes else "none in this map"),
         "confirm each is a real decision, not a comfort blanket"),
        ("Side effects (publish, spend, delete) sit after the gate that authorizes them; "
         "anything before a gate is safe to re-run",
         "manual — check the Runtime section and each brief's refusals"),
        ("Repo-editing nodes run sequentially or in isolated worktrees",
         "manual — check the Runtime section"),
        ("Model bindings are right for the work: judgment and review on fable, "
         "code-heavy implementation on codex",
         f"{len(fable_nodes)} fable node(s), {len(codex_nodes)} codex node(s), "
         f"{len(reviewers)} reviewer(s)"),
        ("The failure map names one node per known failure class",
         "read the table below against your failure history"),
    ]
    checklist_html = "".join(
        f'<li><label><input type="checkbox"> <strong>{item}</strong>'
        f'<br><span class="hint">{hint}</span></label></li>'
        for item, hint in checklist)

    approval = lock.get("approval")
    if approval:
        status = (f'<p class="status approved">Approved by {esc(approval["approved_by"])} '
                  f'on {esc(approval["date"])} — hash {esc(approval["graph_hash"][:12])}…</p>')
    else:
        status = ('<p class="status pending">Awaiting validation. When this map is right, '
                  'approve it from the graph directory:</p>'
                  f'<pre class="cmd">python3 &lt;skill&gt;/scripts/compile_graph.py . '
                  f'--approve "&lt;your name&gt;"</pre>'
                  '<p class="hint">To revise instead: say what to change — the drafting '
                  'agent edits graph.md, recompiles, and re-renders this page. Editing '
                  'after approval invalidates the stamp automatically.</p>')

    page = f"""<title>{esc(name)} — graph review</title>
<style>
  :root {{ --bg:#ffffff; --fg:#1a1a1a; --muted:#6a6a6a; --line:#e2e2e2;
          --card:#f7f7f8; --accent:#b58900; --ok:#1a7f37; --warn:#9a3412; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#111214; --fg:#e6e6e6; --muted:#9a9a9a; --line:#2d2f33;
            --card:#1a1c1f; --ok:#3fb950; --warn:#f0883e; }} }}
  :root[data-theme="dark"] {{ --bg:#111214; --fg:#e6e6e6; --muted:#9a9a9a;
    --line:#2d2f33; --card:#1a1c1f; --ok:#3fb950; --warn:#f0883e; }}
  :root[data-theme="light"] {{ --bg:#ffffff; --fg:#1a1a1a; --muted:#6a6a6a;
    --line:#e2e2e2; --card:#f7f7f8; --ok:#1a7f37; --warn:#9a3412; }}
  body {{ background:var(--bg); color:var(--fg);
         font:16px/1.55 -apple-system,'Segoe UI',sans-serif;
         max-width:60rem; margin:0 auto; padding:2rem 1.25rem 4rem; }}
  h1 {{ font-size:1.6rem; }} h2 {{ font-size:1.15rem; margin-top:2.2rem;
        border-bottom:1px solid var(--line); padding-bottom:.3rem; }}
  .meta {{ color:var(--muted); }}
  .tw {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:.92rem; }}
  th,td {{ border:1px solid var(--line); padding:.4rem .6rem; text-align:left;
           vertical-align:top; }}
  th {{ background:var(--card); }}
  code {{ background:var(--card); padding:.1rem .3rem; border-radius:4px;
          font-size:.85em; }}
  .badge {{ display:inline-block; padding:.05rem .45rem; border-radius:999px;
           font-size:.78rem; font-weight:600; }}
  .badge.fable {{ background:#d9720022; color:#d97200; border:1px solid #d9720055; }}
  .badge.codex {{ background:#0969da22; color:#0969da; border:1px solid #0969da55; }}
  .badge.human {{ background:#6f42c122; color:#8a63d2; border:1px solid #6f42c155; }}
  .diagram {{ background:var(--card); border:1px solid var(--line);
             border-radius:8px; padding:1rem; overflow-x:auto; }}
  pre.mermaid {{ margin:0; }}
  ul.check {{ list-style:none; padding:0; }}
  ul.check li {{ margin:.7rem 0; }}
  .hint {{ color:var(--muted); font-size:.88rem; }}
  .status {{ padding:.7rem 1rem; border-radius:8px; font-weight:600; }}
  .status.approved {{ background:#1a7f3722; color:var(--ok); }}
  .status.pending {{ background:#b5890022; color:var(--accent); }}
  pre.cmd {{ background:var(--card); border:1px solid var(--line);
            border-radius:6px; padding:.6rem .8rem; overflow-x:auto;
            font-size:.85rem; }}
</style>

<h1>{esc(name)} — agent graph review</h1>
<p class="meta">owner {esc(lock.get('owner') or '—')} · cadence {esc(lock.get('cadence') or '—')}
 · version {esc(lock.get('version') or '—')} · max_steps {esc(lock['max_steps'])}
 · compiled {esc(lock.get('compiled_at',''))}</p>

{status}

<h2>Job</h2>
<p>{esc(job)}</p>

<h2>Routes — the map</h2>
<div class="diagram"><pre class="mermaid">{esc(mermaid)}</pre></div>
<p class="hint">Boxes are nodes, diamonds are gates, slanted boxes are human
decisions. Every edge drawn is a route the work may take; there are no others.</p>

<h2>Nodes &amp; model bindings</h2>
{table(["#", "node", "responsibility", "output key", "runs", "executor"], nodes_rows)}

<h2>Gates</h2>
{table(["gate", "after", "check", "pass →", "fail →"], gates_rows)}

<h2>Executors — tier to model (the only place model IDs live)</h2>
{table(["tier", "fable (Claude Code)", "codex (Codex CLI)"], exec_rows)}
<p class="hint">gpt-5.6-sol: $5 in / $0.50 cached / $30 out per 1M tokens;
billing doubles past 272K input tokens — briefs keep codex node inputs under that.</p>

<h2>State contract</h2>
{table(["key", "type", "written by", "read by"], state_rows)}

<h2>Failure map</h2>
{table(["failure class", "surfaces at", "what you'll see"], fail_rows)}

<h2>Validation checklist</h2>
<ul class="check">{checklist_html}</ul>

<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  /* Local-file fallback only: when this page is published as a Claude Code
     Artifact the CDN is blocked by CSP and the pre.mermaid block renders
     natively instead. */
  if (window.mermaid) {{
    mermaid.initialize({{ startOnLoad: true, theme:
      matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'default' }});
  }}
</script>
"""
    out = graph_dir / "review.html"
    out.write_text(page)
    print(f"ok    review surface written: {out}")
    print("next  publish it as a Claude Code Artifact, open it locally, or push")
    print("      the branch and review the rendered mermaid in the PR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
