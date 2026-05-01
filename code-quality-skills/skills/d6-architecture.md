---
description: D6 — Architecture & Boundaries. God-files, layer violations, circular deps.
weight: 10
---

You are sub-skill **D6 Architecture**. Standard contract.

## AUDIT

- **God-files**: list files with `wc -l > 300` for components, `> 500` for utils. Top 10. (Per ReplyManager `CLAUDE.md`: <300 LOC for components.)
- **Layer flow**: read the project doc (e.g. `AGENTS.md`) for the import-flow rule (typical: UI → hooks → repo → mock). Use ast-grep / rg to find UI files importing repo internals or repos importing UI.
- **Circular deps**: if `madge` or `dependency-cruiser` is available, run it. Otherwise, do a best-effort grep on a sample of features.
- **Lane ownership**: if `.coordination/lanes.json` (or similar) exists, verify last 50 commits respected lane ownership (`git log --name-only`, cross-reference).
- **Re-export hygiene**: `rg -n "^export \* from" src/` — count barrel re-exports; flag dirs with >1 barrel pointing into deep internals.
- **Cross-package boundary leaks** (monorepo only): `rg -n "from ['\"](\.\./){4,}" src/` — relative imports going up 4+ levels usually indicate a missing package boundary.
- **Feature folder consistency**: if `src/features/<X>/` is the convention, list features missing standard subfolders (`components/`, `hooks/`, `*.store.ts`, `*.types.ts`).

For every file you read, append `"d6-architecture"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d6-architecture.md`

```
# D6 — Architecture & Boundaries — score x/10

## God-files (top 10)
| File | LOC | Type | Suggested split |

## Layer violations
- UI importing repo internals: …
- Hooks importing UI: …

## Lane / ownership violations (last 50 commits)
…

## Feature folder gaps
…

## Findings
…

## Score reasoning
10 = 0 god-files + 0 layer violations + every feature folder complete.
```

Cap at 400 lines.
