---
description: D10 — CI Health. Exit codes for typecheck/test/build/lint + GitHub Actions status.
weight: 5
---

You are sub-skill **D10 CI Health**. Standard contract.

## AUDIT

Run each command, capture exit code + last 5 lines of output:

| Command | Exit | Last 5 lines |
|---------|------|--------------|
| `pnpm typecheck` | | |
| `pnpm test --run` | | |
| `pnpm build` | | |
| `pnpm lint` (if script exists) | | |
| `pnpm format -- --check` (if exists) | | |

Then GitHub Actions:

```bash
gh run list -L 10 -b main --json status,conclusion,workflowName,event,createdAt
```

Capture the JSON; report success rate of last 10 runs on `main`. If any required check is failing, list the workflow name + last failing run URL (`gh run view <id> --log-failed | head -50`).

Also verify `.github/workflows/*.yml` files exist and have a `permissions:` block (least-privilege) and that they install pinned tool versions (no `latest`).

For every file you read, append `"d10-ci-health"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d10-ci-health.md`

```
# D10 — CI Health — score x/10

## Local commands
| Command | Exit | Notes |

## GitHub Actions (last 10 on main)
- Success rate: X / 10
- Failing workflows: …

## Workflow hygiene
- Files without `permissions:` block: …
- Files using `@latest`: …

## Findings
…

## Score reasoning
10 = all 4 local commands exit 0 + ≥9/10 GHA runs green + every workflow has permissions + no @latest pins.
```

Cap at 400 lines.
