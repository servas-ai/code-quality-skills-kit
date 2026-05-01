---
description: D14 — CSS / Design-token hygiene. Tailwind arbitrary-value abuse, class-soup duplication, raw colour hex.
weight: 4
---

You are sub-skill **D14 CSS Tokens**. Standard contract.

## AUDIT

- **Tailwind arbitrary values**: `rg -n "\[#[0-9a-fA-F]{3,8}\]|\[\d+px\]" src/` — every hit means design tokens were bypassed.
- **Raw hex colours in CSS-in-JS / inline styles**: `rg -n "color:\s*['\"]?#" src/` and `style=\"[^\"]*color:" src/`.
- **Class-soup duplication**: scan `.tsx` for repeated `className="..."` strings >80 chars that appear in 3+ places — extract to a `cva` variant or component.
- **Spacing scale violations**: list arbitrary `[7px]` `[13px]` etc. that don't map to the design system's 4-px scale.
- **Dark-mode parity**: for every `bg-* text-*` pair, check there's a matching `dark:bg-* dark:text-*` (or `dark:` is intentionally inherited).
- **Animation duration**: arbitrary `[750ms]` `[1.3s]` not in the easing/duration token table.

For every file you read, append `"d14-css-tokens"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d14-css-tokens.md`

```
# D14 — CSS Tokens — score x/10

## Arbitrary-value hot-spots (top 20)
| File:line | Class | Suggested token |

## Raw hex colours
…

## Repeated class-soup (extract candidates)
…

## Dark-mode gaps
…

## Findings
…

## Score reasoning
10 = 0 arbitrary values + 0 raw hex + every long classname extracted + full dark-mode parity.
```

Cap at 400 lines.
