---
description: D8 — Dead Code & Tech Debt. Unused exports, stale TODOs, placeholder files.
weight: 8
---

You are sub-skill **D8 Dead Code**. Standard contract.

## AUDIT

- **Unused exports**: prefer `npx ts-prune` if available; otherwise rely on tsc's `noUnusedLocals`/`noUnusedParameters` and a grep for `^export ` symbols never imported elsewhere (sample top 20).
- **Stale TODO/FIXME**: `rg -n "TODO|FIXME|HACK|XXX" src/` — for the top 30, run `git blame -L <line>,<line> <file>` to get age. Flag entries older than 30 days.
- **Empty / placeholder files**: `find src -size -200c -name "*.ts*"` — files under 200 bytes are usually re-exports or stubs.
- **Single-export barrels**: `rg -l "^export \{ \w+ \} from" src/` — barrels that only re-export one symbol add noise.
- **Commented-out blocks**: `rg -n "^\s*//\s*[A-Z]\w+\(" src/ | head -30` — heuristic for commented-out code (capitalised function call following `//`).
- **Unused npm deps**: if `npx depcheck` is available, run it on each package. Otherwise list `dependencies` and grep for an import per dep; flag deps with 0 hits.

For every file you read, append `"d8-dead-code"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d8-dead-code.md`

```
# D8 — Dead Code & Tech Debt — score x/10

## Unused exports (top 20)
| Symbol | File:line | Suggested action |

## Stale TODOs (>30 days)
| Age | File:line | Original commit |

## Placeholder files
…

## Single-export barrels
…

## Unused dependencies
…

## Findings
…

## Score reasoning
10 = 0 unused exports + 0 stale TODOs + no placeholder files + no unused deps.
```

Cap at 400 lines.
