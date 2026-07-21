#!/usr/bin/env bash
# validate_graph.sh — mechanical checks for a drafted agent graph.
#
# Usage: validate_graph.sh <graph-directory>
#   where <graph-directory> contains graph.md and (optionally) nodes/
#
# Checks:
#   1. graph.md exists with required ## sections
#   2. a ```mermaid routes block is present
#   3. frontmatter has a positive integer max_steps
#   4. output keys in the Nodes table are unique
#      (duplicates allowed only if 'exclusive' is declared in State)
#   5. every Gates row has non-empty pass -> and fail -> targets
#   6. every gate target is a declared node or __end__
#   7. some route reaches __end__
#   8. one brief per node in nodes/ (warning only)
#
# Exit 0 = well-formed (warnings allowed). Exit 1 = fix and re-run.

set -euo pipefail

DIR="${1:-}"
if [ -z "$DIR" ] || [ ! -d "$DIR" ]; then
  echo "usage: validate_graph.sh <graph-directory>" >&2
  exit 1
fi

GRAPH="$DIR/graph.md"
FAIL=0
err()  { echo "FAIL  $*"; FAIL=1; }
warn() { echo "warn  $*"; }
ok()   { echo "ok    $*"; }

# 1. file + required sections -------------------------------------------------
if [ ! -f "$GRAPH" ]; then
  echo "FAIL  $GRAPH not found" >&2
  exit 1
fi

for sec in "Job" "State" "Nodes" "Routes" "Gates" "Failure map" "Runtime"; do
  if grep -q "^## $sec" "$GRAPH"; then
    ok "section: ## $sec"
  else
    err "missing section: ## $sec"
  fi
done

# 2. mermaid routes block -----------------------------------------------------
if grep -q '^```mermaid' "$GRAPH"; then
  ok "mermaid routes diagram present"
else
  err "no \`\`\`mermaid block in Routes — the diagram IS the map"
fi

# 3. max_steps ----------------------------------------------------------------
MAX_STEPS=$(awk '/^---$/{f++; next} f==1 && /^max_steps:/{print $2}' "$GRAPH" | tr -d '"' | head -1)
if [[ "${MAX_STEPS:-}" =~ ^[0-9]+$ ]] && [ "$MAX_STEPS" -gt 0 ]; then
  ok "max_steps: $MAX_STEPS"
else
  err "frontmatter needs a positive integer max_steps (every cycle must be bounded)"
fi

# helper: extract body rows of the table under a ## section --------------------
table_rows() { # $1 = section name
  awk -v sec="^## $1" '
    $0 ~ sec {insec=1; next}
    insec && /^## / {insec=0}
    insec && /^\|/ {print}
  ' "$GRAPH" | { grep -v '^|[-| :]*$' || true; } | { tail -n +2 || true; }
}

# 4. unique output keys -------------------------------------------------------
KEYS=$(table_rows "Nodes" | awk -F'|' '{gsub(/[` ]/,"",$5); if ($5!="") print $5}')
NODES=$(table_rows "Nodes" | awk -F'|' '{gsub(/[` ]/,"",$3); if ($3!="") print $3}')
if [ -z "$NODES" ]; then
  err "Nodes table is empty or malformed (| # | node | responsibility | output key | runs |)"
else
  ok "nodes declared: $(echo "$NODES" | wc -l | tr -d ' ')"
fi
DUPES=$(echo "$KEYS" | sort | uniq -d)
if [ -n "$DUPES" ]; then
  for k in $DUPES; do
    if grep -qi "exclusive" "$GRAPH"; then
      warn "output key '$k' has multiple writers — allowed only for exclusive branches (declared)"
    else
      err "output key '$k' written by multiple nodes and no 'exclusive' branch declared in State"
    fi
  done
else
  ok "output keys unique"
fi

# 5+6. gates have pass/fail targets that exist --------------------------------
GATE_ROWS=$(table_rows "Gates")
if [ -z "$GATE_ROWS" ]; then
  err "Gates table is empty or malformed (| gate | after | check | pass -> | fail -> |)"
else
  while IFS= read -r row; do
    gate=$(echo "$row"  | awk -F'|' '{gsub(/^ +| +$/,"",$2); print $2}')
    pass=$(echo "$row"  | awk -F'|' '{gsub(/^ +| +$/,"",$5); print $5}')
    failt=$(echo "$row" | awk -F'|' '{gsub(/^ +| +$/,"",$6); print $6}')
    [ -z "$pass" ]  && err "gate '$gate' has no pass target"
    [ -z "$failt" ] && err "gate '$gate' has no fail target — 'it'll pass' is not a route"
    for tgt in "$pass" "$failt"; do
      t=$(echo "$tgt" | tr -d '` ')
      [ -z "$t" ] && continue
      if [ "$t" != "__end__" ] && ! echo "$NODES" | grep -qx "$t"; then
        err "gate '$gate' targets '$t' — not a declared node or __end__"
      fi
    done
  done <<< "$GATE_ROWS"
  ok "gates checked: $(echo "$GATE_ROWS" | wc -l | tr -d ' ')"
fi

# 7. something reaches __end__ ------------------------------------------------
if grep -q "__end__" "$GRAPH"; then
  ok "__end__ reachable in map"
else
  err "no route reaches __end__ — the map must halt"
fi

# 8. node briefs (warning only) -----------------------------------------------
if [ -d "$DIR/nodes" ]; then
  for n in $NODES; do
    if ls "$DIR/nodes/"[0-9][0-9]-"$n".md >/dev/null 2>&1; then
      ok "brief: $n"
    else
      warn "no brief for node '$n' (expected nodes/NN-$n.md)"
    fi
  done
else
  warn "no nodes/ directory — briefs not drafted yet"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "PASS  graph is well-formed"
else
  echo "FAIL  fix the items above and re-run"
fi
exit "$FAIL"
