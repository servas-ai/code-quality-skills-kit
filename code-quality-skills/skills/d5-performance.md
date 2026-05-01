---
description: D5 — Performance. Bundle size, render hot-paths, N+1, missing memoisation.
weight: 10
---

You are sub-skill **D5 Performance**. Standard contract.

## AUDIT

- Run `pnpm build` (in the relevant artifact). Capture First Load JS / route, total bundle size. List top-5 heaviest routes.
- `rg -n "useEffect\(\s*\(\)\s*=>\s*\{[^}]*\}\s*,\s*\[\s*\]\s*\)" src/` — empty deps with side-effects (often hides logic that should run on every change).
- `rg -n "useEffect\(\s*\(\)\s*=>\s*\{" src/ | wc -l` — total `useEffect` count (high count = imperative code in a declarative app).
- `rg -n "\.map\(async " src/` — N+1 candidates without `Promise.all`.
- `rg -n "useState\(\(\)\s*=>" src/` — lazy initialisers (good); flag ones that call `localStorage` / `JSON.parse` of >100 KB inside.
- `rg -n "<img\s" src/` (Next.js) — should use `next/image` instead.
- `rg -n "React\.memo\(|memo\(" src/ | wc -l` — too few = high re-render risk in lists; flag list-row components without memo.
- `rg -n "import .* from ['\"]lodash['\"]" src/` — unscoped lodash import is a red flag (use `lodash/fn` or native).

For every file you read, append `"d5-performance"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d5-performance.md`

```
# D5 — Performance — score x/10

## Bundle (production build)
| Route | First Load JS | Δ vs. last build |

## Render hot-paths
- Top 10 list-row components without React.memo
- Top 10 .map(async ...) without Promise.all

## useEffect inventory
- Total: N · empty-deps with side-effects: M · suspected dead-effects: K

## Findings
…

## Score reasoning
10 = First Load JS ≤ 200 KB / route + 0 N+1 + list rows memo'd. -1 per route over 250 KB.
```

Cap at 400 lines.
