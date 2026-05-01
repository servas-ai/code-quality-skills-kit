# More skill ideas — drop-in candidates

Below is a backlog of skill ideas you can copy-paste from `skills/d{1..15}-*.md` as templates and adapt. Each is independent: drop a new `d<N>-<name>.md` file, add it to the orchestrator's dispatch list, ship.

> **Note for agents**: when you adopt one of these, also update `orchestrator.md` Step 2 (dispatch list) and the report template's scoring rubric.

## Tier 1 — High ROI, drop in next

| Slug | What it does | Tools |
|------|--------------|-------|
| `d16-bundle-composition` | Top-10 biggest deps in the bundle, treeshaking gaps. Run `next build --profile` and `webpack-bundle-analyzer` if available. | next build, source-map-explorer |
| `d17-error-boundaries` | Verify React error boundaries exist at route + feature boundaries; flag features without one. | rg, ast-grep |
| `d18-resource-cleanup` | `useEffect` returns a cleanup; `setInterval` cleared; AbortControllers in fetches. | rg `setInterval\(`, `addEventListener\(` |
| `d19-state-mgmt-hygiene` | Zustand stores not overlapping; same data not stored in 2 places. List store keys, find duplicates. | rg `create\<.*\>\(` |
| `d20-mobile-responsive` | Touch targets ≥44 px, breakpoint coverage on key pages, no `hover:` only handlers. | playwright a11y, manual |
| `d21-image-assets` | Unoptimised images >100 KB, missing srcset, no BlurHash. Walk `public/` + check `next/image` props. | sharp, find -size |
| `d22-package-json-hygiene` | Duplicate deps across workspaces, scripts not actually used, peerDeps mismatches. | parse JSON, rg |

## Tier 2 — Specialised

| Slug | What it does |
|------|--------------|
| `d23-api-contract` | OpenAPI / zod schemas vs. actual route handlers — find drift. |
| `d24-db-schema` | Prisma / Drizzle migrations match models, no nullable columns missing default. |
| `d25-logging` | Structured logging consistency, no PII in logs, log-levels appropriate. |
| `d26-observability` | Metrics emitted at hot paths, traces propagated across awaits. |
| `d27-pwa-sw` | Service-worker cache strategy correctness, stale-while-revalidate misuse, auth paths excluded. |
| `d28-deprecations` | `console.warn(/deprecated/)` from libs; deprecated React APIs (`componentWillMount`, `findDOMNode`). |
| `d29-browser-support` | `caniuse` lookups for top 10 newest CSS / JS features used. |
| `d30-determinism` | `npm ci` reproducibility, lockfile drift between dev and CI, no `latest` pins. |

## Tier 3 — Cross-cutting / meta

| Slug | What it does |
|------|--------------|
| `d31-changelog-drift` | CHANGELOG vs. actual commits since last release tag. |
| `d32-secrets-history` | Gitleaks-style sweep of full git history for committed secrets (slow; opt-in). |
| `d33-branch-graveyard` | Stale branches >60 days that never merged. |
| `d34-flaky-tests` | Parse last 50 CI runs; rank tests by flake rate. |
| `d35-perf-budgets` | Compare current bundle to a stored budget JSON; fail if any route regressed >10 %. |
| `d36-dx-friction` | Cold-start dev-server time, typecheck time, hot-reload time — DX SLOs. |
| `d37-ai-coauthor-ratio` | Heuristic for AI-generated code: long generic comments, perfect prettier formatting, missing project conventions. |

## Companion / orchestration skills

| Skill | Purpose |
|-------|---------|
| `code-quality-analyse-v2` | Deep-dive on a **single** finding from a previous run. Loads the run's `_ledger.json` + `_file-coverage.json`, picks the finding by id, traces it to root cause + 3 fix options. |
| `code-quality-fix-suggest` | Generate copy-pasteable fix prompts (one per finding) — does NOT apply them. Output is a `fixes.md` file with one section per finding. |
| `code-quality-trend` | Diff this run's `_ledger.json` against the previous run. Show: score Δ, new findings, regressions, fixed-since-last-time. |
| `code-quality-export-jira` | Convert each finding into a Jira/Linear-ready ticket payload (JSON). |
| `code-quality-export-github` | Open one GitHub issue per CRITICAL+HIGH finding, label `audit/<dimension>`. (Manual confirm; never automatic.) |
| `code-quality-pr-comment` | When run on a PR, post the rolled-up TL;DR as a single PR comment via `gh pr comment`. |
| `code-quality-baseline` | Snapshot the current state as `audit-reports/_baseline.json`. Future runs are graded as "regression" / "improvement" against the baseline. |
| `code-quality-watch` | Re-run only dimensions whose feeder files changed (e.g. `package.json` change → re-run d12-deps). |

## Skill gates (orchestrator-level features to add)

- **Tool-availability gate** — at Step 0, if `pnpm`/`tsc` is missing, mark D2/D3/D5 as `failed` upfront so they don't waste a slot.
- **Time-box per skill** — if a sub-skill runs >5 min, abort it, mark `failed`, log to `notes`, and proceed.
- **Concurrency limit** — fan out at most 4 sub-agents in parallel to keep the host machine responsive.
- **Privacy gate** — never include file *contents* in the ledger; only paths + line numbers + finding metadata. (The dimension reports may quote 1–2 lines of context; flag agents that quote >5 lines.)

## Cross-tool integrations

- **Trail of Bits skills** — chain D4 Security with `tob/codeql` and `tob/semgrep` plug-ins for deeper SAST.
- **agent-browser** — D7 A11y can run `agent-browser open localhost:4020 → snapshot -i` for live DOM-tree contrast checks.
- **Storybook** — if Storybook is present, D7 a11y can run `axe-core` against every story.

## How to publish this kit

1. Strip the ReplyManager-specific examples (markChatRead, OnlyAPI safety lock) from each skill — leave a `# Project-specific overrides` section users fill in.
2. Add `LICENSE` (MIT recommended) and `package.json` style metadata if publishing on **skills.sh** / `claudeskills.info`.
3. Provide a one-line install: `git clone <repo> ~/.claude/skills/code-quality && claude /code-quality-checker`.
4. Publish to:
   - [skills.sh](https://skills.sh)
   - [claudeskills.info](https://claudeskills.info)
   - [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills)
   - [tessl.io/registry/skills](https://tessl.io/registry/skills)
