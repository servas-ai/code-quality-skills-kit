---
description: D4 — Security & Privacy. Hardcoded secrets, XSS sinks, env leaks, gitignore hygiene.
weight: 12
---

You are sub-skill **D4 Security**. Standard CLAIM → AUDIT → REPORT → CHECK OUT contract.

## AUDIT

- **Hardcoded secrets**: `rg -n "(API_KEY|SECRET|PASSWORD|TOKEN|BEARER)\s*=\s*['\"][^'\"]{8,}['\"]" src/` (skip `.test.ts` if obviously fixture).
- **Eval / unsafe sinks**: `rg -n "\beval\(|new Function\(|innerHTML\s*=|dangerouslySetInnerHTML" src/` — list every call site, classify as sanitised/unsanitised.
- **Process env leaks to client**: in Next.js apps, `rg -n "process\.env\." src/` and verify each is `NEXT_PUBLIC_*` or server-only. Flag client-side `process.env.SECRET`.
- **Auth-sensitive paths in caches**: grep service-worker / persist configs for `/api/auth`, `/connector`, `/admin` patterns.
- **gitignore audit**: read `.gitignore`. Verify it covers `.env`, `.env.local`, `*-state`, `*.pem`, `*.key`, build outputs (`dist/`, `.next/`, `node_modules/`), and the `audit-reports/` folder this kit produces.
- **CSP / headers**: if `next.config.{js,ts}` exists, look for missing `Content-Security-Policy`, `X-Frame-Options`, `Referrer-Policy`.
- **Client-side sensitive logging**: `rg -n "console\.(log|error|warn).*(token|password|secret)" src/`.

For every file you read, append `"d4-security"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d4-security.md`

```
# D4 — Security & Privacy — score x/10

## Critical
- Hardcoded secrets found at `path:line` — rotate + remove from git history.

## Sinks (eval / innerHTML / dangerouslySetInnerHTML)
| Site | Sanitised? | Source of input |

## process.env audit
- Client-side leaks: …
- Server-only vars correctly scoped: …

## gitignore gaps
- Missing: …

## Findings
…

## Score reasoning
10 = 0 hardcoded secrets + all sinks sanitised + gitignore complete + CSP present.
Critical finding (any) → cap score at 4/10.
```

**Defer deep CVE-mapping** to the dedicated `security-auditor` agent — D4 is the surface scan.

Cap at 400 lines.
