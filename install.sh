#!/usr/bin/env bash
# install.sh — install the graph skill for Claude Code and/or Codex.
#
# Usage:
#   ./install.sh                 # user-level install for both harnesses
#   ./install.sh --claude        # Claude Code only (~/.claude/skills)
#   ./install.sh --codex         # Codex only (~/.agents/skills)
#   ./install.sh --project       # project-level install into the current
#                                # git repo (.claude/skills + .agents/skills)
#   ./install.sh --codex-prompt  # also install /prompts:graph shim
#                                # for Codex (~/.codex/prompts)
#
# Flags combine: ./install.sh --claude --codex-prompt

set -euo pipefail

REPO_DIR=$(cd "$(dirname "$0")" && pwd)
SRC="$REPO_DIR/skills/graph"

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "error: $SRC/SKILL.md not found; run from a full checkout" >&2
  exit 1
fi

DO_CLAUDE=0
DO_CODEX=0
DO_PROJECT=0
DO_CODEX_PROMPT=0

if [ $# -eq 0 ]; then
  DO_CLAUDE=1
  DO_CODEX=1
fi

for arg in "$@"; do
  case "$arg" in
    --claude)       DO_CLAUDE=1 ;;
    --codex)        DO_CODEX=1 ;;
    --project)      DO_PROJECT=1 ;;
    --codex-prompt) DO_CODEX_PROMPT=1 ;;
    -h|--help)      sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "error: unknown flag $arg (try --help)" >&2; exit 1 ;;
  esac
done

# Validate every requested destination before any copy happens.
PROJECT_ROOT=""
if [ "$DO_PROJECT" -eq 1 ]; then
  if ! PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
    echo "error: --project requires running inside a git repository" >&2
    exit 1
  fi
fi

install_to() {
  dest=$1
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -R "$SRC" "$dest"
  chmod +x "$dest/scripts/validate_graph.sh"
  echo "installed: $dest"
}

if [ "$DO_CLAUDE" -eq 1 ]; then
  install_to "$HOME/.claude/skills/graph"
  echo "  Claude Code: restart your session, then run /graph <job to map>"
fi

if [ "$DO_CODEX" -eq 1 ]; then
  install_to "$HOME/.agents/skills/graph"
  echo "  Codex CLI: restart codex, then \$-mention graph or run /skills"
fi

if [ "$DO_PROJECT" -eq 1 ]; then
  install_to "$PROJECT_ROOT/.claude/skills/graph"
  install_to "$PROJECT_ROOT/.agents/skills/graph"
  echo "  Commit .claude/skills and .agents/skills to share with your team."
fi

if [ "$DO_CODEX_PROMPT" -eq 1 ]; then
  mkdir -p "$HOME/.codex/prompts"
  cp "$REPO_DIR/codex/graph.md" "$HOME/.codex/prompts/graph.md"
  echo "installed: $HOME/.codex/prompts/graph.md"
  echo "  Codex CLI: restart codex, then run /prompts:graph <job to map>"
fi

echo "done."
