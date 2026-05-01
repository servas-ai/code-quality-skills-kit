#!/usr/bin/env bash
# code-quality-skills-kit installer
# One-line install: curl -sSL https://raw.githubusercontent.com/servas-ai/code-quality-skills-kit/main/install.sh | sh
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

echo "📋 Installing into $TARGET …"
cp "$TMP/kit/code-quality-checker.md" .
cp -r "$TMP/kit/code-quality-skills" .

# Install cqc-budget CLI to ~/.local/bin (or /usr/local/bin if writable)
DEST="$HOME/.local/bin"
if [ ! -d "$DEST" ]; then
  mkdir -p "$DEST"
fi
cp "$TMP/kit/bin/cqc-budget" "$DEST/cqc-budget"
chmod +x "$DEST/cqc-budget"
echo "🔧 Installed cqc-budget → $DEST/cqc-budget"
case ":$PATH:" in
  *":$DEST:"*) ;;
  *) echo "    Add to your shell rc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# .gitignore
if ! grep -q "^audit-reports/$" .gitignore 2>/dev/null; then
  echo "" >> .gitignore
  echo "# code-quality-skills-kit" >> .gitignore
  echo "audit-reports/" >> .gitignore
  echo "✏️  Added 'audit-reports/' to .gitignore"
fi

# Stack detect
STACK="unknown"
[ -f package.json ] && STACK="javascript/typescript"
[ -f pyproject.toml ] && STACK="python"
[ -f Cargo.toml ] && STACK="rust"
[ -f go.mod ] && STACK="go"
FILES=$(git ls-files | wc -l)

cat <<NEXT

✅ Installed code-quality-skills-kit
   Stack: $STACK · Files: $FILES

▶ Next:
   1. cqc-budget                   # interactive: set per-CLI % thresholds
   2. /code-quality-checker        # in Claude Code: run audit using config

▶ Or skip cqc-budget and run audit with defaults:
   /code-quality-checker --yes

▶ Output: audit-reports/<date>__<sha>/
   REPORT.md · REPORT.compact.txt · dashboard.html · fix-prompts.md · _findings.jsonl

NEXT
