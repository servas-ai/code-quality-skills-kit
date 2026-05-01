---
description: D2 — Type Safety. Run typecheck, count escape hatches, verify strict-mode flags.
weight: 12
---

You are sub-skill **D2 Type Safety**. Same CLAIM → AUDIT → REPORT → CHECK OUT contract as D1 (see `d1-correctness.md`).

## AUDIT

- Run `pnpm typecheck` (or `pnpm -r typecheck` for monorepo). Capture the full output. Count errors, group by file.
- Inspect `tsconfig.json` (every package) for: `strict`, `exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`, `noImplicitAny`, `noImplicitOverride`. Flag any package that disables them.
- `rg -n ":\s*any\b" src/` — explicit `any` annotations (excluding `any` inside test mocks).
- `rg -n "as unknown as" src/` — double-cast hacks.
- `rg -n "// @ts-" src/` — type-system bypasses; list all with reason.
- For every file with ≥3 `any` or `as any` hits, mark it as a hot-spot.

For every file you read, append `"d2-types"` to its `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d2-types.md`

```
# D2 — Type Safety — score x/10

**Typecheck:** PASS / FAIL (N errors)
**Strict flags:** strict=Y, exactOptional=Y, noUncheckedIndexedAccess=N (←FLAG)

## Top 10 `any` / `as any` offenders
| File | Hits | Worst line |
|------|------|------------|

## tsc errors (verbatim, top 20)
…

## Findings
…

## Score reasoning
10 = 0 errors + all strict flags on + ≤5 `any` repo-wide. -2 per error category.
```

Cap at 400 lines.
