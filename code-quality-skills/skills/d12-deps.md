---
description: D12 — Dependency hygiene. Outdated, duplicated, vulnerable, unused.
weight: 6
---

You are sub-skill **D12 Dependencies**. Standard contract.

## AUDIT

- `pnpm audit --json` → count critical / high / moderate / low. List the 10 highest-severity issues with affected packages.
- `pnpm outdated --format json` (or `--long`) → list packages >1 minor behind, >0 major behind. Highlight breaking-change candidates.
- **Duplicates in monorepo**: `pnpm why <pkg>` for the top 20 most-used packages — flag those resolving to multiple versions.
- **Unused deps**: `npx depcheck` per package — list `dependencies:` entries with 0 usages.
- **Peer-dep conflicts**: parse `pnpm install --frozen-lockfile` output for warnings.
- **Lockfile churn**: `git log -100 --pretty=format: --name-only -- pnpm-lock.yaml | wc -l` — if lockfile changed in >50 of 100 recent commits, flag dependency thrash.
- **Pinning policy**: scan `package.json` files for `"^"` / `"~"` ranges on critical packages (react, next, typescript) — security-sensitive deps should be pinned.
- **License audit** (optional): if `npx license-checker --json` works, list non-permissive (GPL, AGPL, SSPL) licenses in dependency closure.

For every file you read, append `"d12-deps"` to `_file-coverage.json` `reviewed_by[]`. (You'll mostly read `package.json` files and `pnpm-lock.yaml` snippets.)

## REPORT — `d12-deps.md`

```
# D12 — Dependencies — score x/10

## pnpm audit
| Severity | Count | Top package |

## Outdated (top 10)
| Package | Current | Latest | Δ |

## Duplicates (multiple versions resolved)
…

## Unused deps
…

## License risks
…

## Findings
…

## Score reasoning
10 = 0 critical/high vulns + 0 unused + 0 duplicates + critical packages pinned.
```

Cap at 400 lines.
