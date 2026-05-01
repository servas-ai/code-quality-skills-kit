#!/usr/bin/env bash
# code-quality-skills-kit installer
# curl -sSL https://raw.githubusercontent.com/servas-ai/code-quality-skills-kit/main/install.sh | sh
set -euo pipefail
umask 077

REPO="${CQSK_REPO:-https://github.com/servas-ai/code-quality-skills-kit}"
TARGET="${1:-.}"

[ ! -d "$TARGET" ] && { echo "❌ Target not found: $TARGET"; exit 1; }
cd "$TARGET"
[ ! -d .git ] && { echo "⚠ Not a git repo. Run 'git init' first."; exit 1; }

TMP=$(mktemp -d)
trap "rm -rf '$TMP'" EXIT

echo "📦 Cloning kit (depth 1)…"
git clone --depth 1 --quiet "$REPO" "$TMP/kit"

echo "📋 Installing kit into $TARGET …"
cp "$TMP/kit/code-quality-checker.md" .
cp -r "$TMP/kit/code-quality-skills" .

# Install cqc + cqc-budget + cqc-ui binaries
DEST="$HOME/.local/bin"
mkdir -p "$DEST"
cp "$TMP/kit/bin/cqc" "$DEST/cqc"
cp "$TMP/kit/bin/cqc-budget" "$DEST/cqc-budget"
cp "$TMP/kit/bin/cqc-ui" "$DEST/cqc-ui"
chmod +x "$DEST/cqc" "$DEST/cqc-budget" "$DEST/cqc-ui"
echo "🔧 Installed: cqc + cqc-budget + cqc-ui → $DEST/"

# Register /cqc slash command for Claude Code
if [ -d "$HOME/.claude" ]; then
  mkdir -p "$HOME/.claude/commands"
  cp "$TMP/kit/code-quality-checker.md" "$HOME/.claude/commands/cqc.md"
  echo "⚡ Registered: /cqc slash-command for Claude Code"
fi

# .gitignore
if ! grep -q "^audit-reports/$" .gitignore 2>/dev/null; then
  { echo ""; echo "# code-quality-skills-kit"; echo "audit-reports/"; } >> .gitignore
  echo "✏️  Added 'audit-reports/' → .gitignore"
fi

# PATH check
case ":$PATH:" in
  *":$DEST:"*) ;;
  *) echo ""; echo "  ⚠ Add to your shell:  ${C_CYAN}export PATH=\"\$HOME/.local/bin:\$PATH\"${C_RST}" ;;
esac

# Stack detect
STACK="unknown"
[ -f package.json ] && STACK="javascript/typescript"
[ -f pyproject.toml ] && STACK="python"
[ -f Cargo.toml ] && STACK="rust"
[ -f go.mod ] && STACK="go"
FILES=$(git ls-files | wc -l)

cat <<NEXT

✅ Installed code-quality-skills-kit (Stack: $STACK · Files: $FILES)

▶ Start auditing — pick one:

  cqc                              # auto-run (gemini-3.1-pro-preview, best model)
  cqc --yolo                       # YOLO mode (skip all prompts)
  cqc --gemini-only --yolo         # Gemini only, fastest path
  /cqc                             # in Claude Code (slash command)

▶ Configure:

  cqc set-default default_cli=gemini      # always use gemini
  cqc set-default yolo=true               # always YOLO mode
  cqc budget                              # set %-thresholds interactively

▶ Output: audit-reports/<date>__<sha>/  →  REPORT.md · dashboard.html · fix-prompts.md

NEXT
