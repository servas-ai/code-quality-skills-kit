#!/usr/bin/env bash
# code-quality-skills-kit installer
# One-line install: curl -sSL https://raw.githubusercontent.com/servas-ai/code-quality-skills-kit/main/install.sh | sh
set -euo pipefail
umask 077

REPO="${CQSK_REPO:-https://github.com/servas-ai/code-quality-skills-kit}"
TARGET="${1:-.}"

if [ ! -d "$TARGET" ]; then
  echo "❌ Target directory does not exist: $TARGET"
  exit 1
fi

cd "$TARGET"

# Sanity: this should be a git repo (the kit assumes it)
if [ ! -d .git ]; then
  echo "⚠️  Not a git repository. The kit needs git for run-id + file inventory."
  echo "    Run 'git init' first, then re-run this installer."
  exit 1
fi

TMP=$(mktemp -d)
trap "rm -rf '$TMP'" EXIT

echo "📦 Cloning kit (depth 1) from $REPO …"
git clone --depth 1 --quiet "$REPO" "$TMP/kit"

echo "📋 Copying master prompt + derivable cache into $TARGET …"
cp "$TMP/kit/code-quality-checker.md" .
cp -r "$TMP/kit/code-quality-skills" .

# Add audit-reports/ to .gitignore if not already present
if ! grep -q "^audit-reports/$" .gitignore 2>/dev/null; then
  echo "" >> .gitignore
  echo "# code-quality-skills-kit run output" >> .gitignore
  echo "audit-reports/" >> .gitignore
  echo "✏️  Added 'audit-reports/' to .gitignore"
fi

# Detect stack and print one-line summary
STACK="unknown"
[ -f package.json ] && STACK="javascript/typescript"
[ -f pyproject.toml ] && STACK="python"
[ -f Cargo.toml ] && STACK="rust"
[ -f go.mod ] && STACK="go"
[ -f pom.xml ] && STACK="java/maven"
[ -f build.gradle ] && [ "$STACK" = "unknown" ] && STACK="java/gradle"
[ -f Gemfile ] && STACK="ruby"
[ -f mix.exs ] && STACK="elixir"
FILES=$(git ls-files | wc -l)

cat <<EOF

✅ Installed code-quality-skills-kit
   Detected stack: $STACK
   Files in repo:  $FILES

▶ Next step (in Claude Code):
   /code-quality-checker            # whole repo
   /code-quality-checker src/foo    # scope to a path
   /code-quality-checker --no-tools # skip typecheck/test/build, greps only

▶ Output goes to:
   audit-reports/<YYYY-MM-DD>__<short-sha>/
     REPORT.compact.txt   (AI-feed, ~2.5 KB / 50 findings)
     REPORT.md            (human)
     dashboard.html       (browser, no JS)
     fix-prompts.md       (paste-able)
     _findings.jsonl      (machine-readable)

▶ Customize: edit cqc.config.yaml in repo root (optional — auto-detect works for most repos).

EOF
