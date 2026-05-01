---
description: D9 — Documentation. README freshness, scope drift in CLAUDE.md, JSDoc on public API.
weight: 6
---

You are sub-skill **D9 Docs**. Standard contract.

## AUDIT

- **README freshness**: `git log -1 --format=%cd README.md` vs. `git log -1 --format=%cd src/`. Flag if README is >90 days older.
- **CLAUDE.md / AGENTS.md scope drift**: read the "DO NOT BUILD" or "out-of-scope" lists; verify those dirs really don't exist (`ls`). Flag inconsistencies.
- **Public API JSDoc**: pick the package's `index.ts` (or main barrel). For every exported function/class, check for a JSDoc comment block immediately above. Sample 10 exports; report ratio with docs.
- **Architecture diagrams / ADRs**: `find . -path ./node_modules -prune -o -iname "ADR*" -o -iname "architecture*" -print` — list dated ADRs older than 180 days that may need refresh.
- **Broken internal links**: in MD files, `rg -n "\]\((\.{0,2}/[^)]+\.md)\)" *.md docs/` — check each target exists.
- **Code-snippets**: in README/AGENTS/CLAUDE, find shell-snippets that reference removed scripts (e.g. `pnpm <something-deleted>`). Cross-check `package.json scripts`.

For every file you read, append `"d9-docs"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d9-docs.md`

```
# D9 — Docs — score x/10

## README freshness
- Last touched: <date> · last code change: <date> · gap: N days.

## Scope drift in CLAUDE.md / AGENTS.md
- "DO NOT BUILD" still accurate? List of contradictions.

## Public-API JSDoc coverage
- Sample of 10: docs / no-docs ratio.

## Stale ADRs
…

## Broken internal links
…

## Findings
…

## Score reasoning
10 = README ≤30 days stale + 0 scope drift + ≥80 % JSDoc on public API + no broken links.
```

Cap at 400 lines.
