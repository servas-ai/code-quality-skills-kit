---
description: D15 — Feature-flag / experiment hygiene. Stale flags, missing rollout plans, dead branches.
weight: 4
---

You are sub-skill **D15 Feature Flags**. Standard contract.

## AUDIT

- **Stale flags**: list every `useFeatureFlag(...)`, `featureFlags.X`, `getFlag('X')` call site. For each unique flag id, run `git log -1 --format=%cd -- $(rg -l "<flag-id>" src/)` to estimate age. Flag flags >90 days old.
- **Half-rolled-out flags**: search for both `if (flag)` and `if (!flag)` paths still in the codebase — these are technical debt.
- **Sync-wave / experiment branches**: `git branch -r --merged main | grep -E "(experiment|sync-wave|feature)/"` and list those merged but not deleted (>30 days old).
- **Hardcoded `true` flags**: `rg -n "useFeatureFlag\(['\"]\w+['\"]\s*\)\s*\?\s*true" src/` — flags that are now always-true should be removed.
- **TODOs about flag cleanup**: `rg -n "TODO.*flag|FIXME.*flag|remove.*flag" src/` — explicit cleanup notes that haven't happened.

For every file you read, append `"d15-flags"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d15-flags.md`

```
# D15 — Feature Flags — score x/10

## Flag inventory
| Flag id | Age (days) | Call sites | Owner | Cleanup PR open? |

## Half-rolled-out flags
…

## Stale branches (≥30 days, merged)
…

## Cleanup TODOs
…

## Findings
…

## Score reasoning
10 = no flag >90 days + no half-rolled-out + no stale branches + 0 cleanup TODOs.
```

Cap at 400 lines.
