---
description: D3 — Test Coverage & Quality. Run the suite, find skipped/todo/.only, list modules without tests.
weight: 12
---

You are sub-skill **D3 Tests**. Standard CLAIM → AUDIT → REPORT → CHECK OUT contract.

## AUDIT

- Run `pnpm test --run` (or `vitest run` / `pytest`). Record exit code, pass/fail/skip counts.
- `rg -n "\.skip\(|\.todo\(|xit\(|it\.only\(|describe\.only\(|fdescribe\(|fit\(" src/` — red flags. Count + list top 20.
- For every module changed in the last 50 commits (`git log -50 --name-only --pretty=format:`), check if a sibling `*.test.{ts,tsx}` or `__tests__/*.test.*` exists. List the missing-tests files.
- If `@vitest/coverage-v8` ran, parse `coverage/coverage-summary.json` and extract per-package line/branch coverage. List packages below 70 %.
- Check for snapshot bloat: `find . -name "__snapshots__" -type d` — note any folders with >50 snapshot files (often stale).

For every file you read or run tests against, append `"d3-tests"` to its `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d3-tests.md`

```
# D3 — Tests — score x/10

**Suite:** PASS / FAIL · Tests: P passed, F failed, S skipped
**Coverage:** X % lines / Y % branches (from coverage-summary.json)
**.only / .skip / .todo:** N hits

## Modules without tests (last 50 commits)
- src/foo.ts
- …

## Top 20 .skip / .todo / .only hits
…

## Snapshot hot-spots
…

## Findings
…

## Score reasoning
10 = green suite + ≥80 % coverage + 0 .only + ≤5 .skip with explanation comment.
```

Cap at 400 lines.
