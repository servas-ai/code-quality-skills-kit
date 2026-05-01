# code-quality-skills-kit

Self-bootstrapping multi-agent code-quality audit kit for Claude Code.

## Install (per repo)

```bash
# 1. Drop the kit into your repo root
cp -r /path/to/code-quality-skills-kit/{code-quality-checker.md,code-quality-skills} .
echo "audit-reports/" >> .gitignore
git add code-quality-checker.md code-quality-skills .gitignore
git commit -m "add code-quality-skills-kit"

# 2. Run the orchestrator
#    /code-quality-checker             ← whole repo
#    /code-quality-checker src/foo     ← scope to path
#    /code-quality-checker '#42'       ← scope to PR
#    /code-quality-checker --refresh-kit
#    /code-quality-checker --no-tools  ← greps only, skip typecheck/test/build
```

## What you get

- **15 audit dimensions** (correctness, types, tests, security, performance, architecture, a11y, dead-code, docs, ci-health, i18n, deps, cache-keys, css-tokens, feature-flags) + a coverage-sweeper that guarantees ≥99 % file coverage.
- **JSON ledger** — agents check in / out via `_ledger.json`; per-file matrix in `_file-coverage.json`.
- **Project profile detection** — adapts every check to your stack (Next.js, React, Vue, Python, Rust, …) and your invariants (mock-only locks, language policies, scope blocklists).
- **End-to-end tool execution** — runs your real `pnpm typecheck` / `pnpm test` / `pnpm build` / `pnpm audit` and captures output.
- **Four output formats** per run: `REPORT.md` · `dashboard.html` (one-page interactive, no JS) · `_findings.json` · `fix-prompts.md` (paste-able into Claude Code).
- **Trend mode** — diff this run against a baseline.
- **Resumable** — crashed / timed-out sub-agents resume from the ledger.

## Layout

```
code-quality-checker.md      ← Self-bootstrapping master prompt (drop into repo root)
code-quality-skills/
├── README.md
├── orchestrator.md
├── ledger-schema.md
├── MORE-IDEAS.md            ← 22 more skill ideas
├── _templates/
│   ├── ledger.template.json
│   ├── file-coverage.template.json
│   ├── report.template.md
│   ├── dashboard.template.html
│   ├── hot-spots.template.json
│   └── fix-prompts.template.md
└── skills/
    ├── d1-correctness.md
    ├── d2-types.md
    ├── ... (15 dimensions)
    └── coverage-sweeper.md
```

## Status

v2.0.0 · Tested end-to-end against a sandbox repo (see `/tmp/cq-sandbox` test fixtures).
