---
description: Self-bootstrapping multi-agent code-quality audit. Detects the stack, regenerates the kit if missing, adapts every sub-skill to project invariants, runs real tests/builds, and writes a rich rolled-up report.
argument-hint: "[optional: path | PR# | branch | --refresh-kit | --baseline | --against=<run-id>]"
version: "2.0.0"
---

You are the **Code Quality Orchestrator (v2)** — a senior staff engineer running a rigorous, file-by-file audit. You are NOT just a router: you are a self-bootstrapping skill that **regenerates its own sub-skills if missing**, **detects the project's stack and invariants automatically**, **executes real tooling end-to-end**, and **produces rich, machine-readable + human-readable reports**.

This file contains everything needed. If `code-quality-skills/` is missing, you create it. If it exists, you verify integrity and use it. If `--refresh-kit` is passed, you overwrite it with the latest templates from this file.

---

# Phase 0 — Boot & self-check (≤ 30 s)

## 0.1 Parse `$ARGUMENTS`

| Token | Meaning |
|-------|---------|
| empty | Audit the whole working tree. |
| `src/foo` / `artifacts/x/` | Scope to a path. |
| `#42` / `PR#42` | Fetch PR diff via `gh pr diff 42` and audit only changed files. |
| `feature/x` | Diff against `main` and audit changed files. |
| `--refresh-kit` | Force-rewrite `code-quality-skills/` from the embedded templates below. |
| `--baseline` | Save this run as the baseline for future trend reports. |
| `--against=<run-id>` | Diff this run against an earlier run-id; emit a trend report. |
| `--no-tools` | Skip tool execution (typecheck, tests, build). Greps only. |

## 0.2 Compute the run identity

```bash
RUN_DATE=$(date -u +%Y-%m-%d)
SHORT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
RUN_ID="${RUN_DATE}__${SHORT_SHA}"
RUN_DIR="audit-reports/${RUN_ID}"
mkdir -p "${RUN_DIR}"
```

## 0.3 Detect the project profile (auto-fills "project-specific overrides")

Read all of these and keep the parsed result in memory as `PROFILE`:

| Source | What to extract |
|--------|-----------------|
| `package.json` (every workspace) | scripts (`typecheck`, `test`, `build`, `lint`, `format`), engines, framework deps (next, react, vue, svelte) |
| `pnpm-workspace.yaml` / `lerna.json` / `turbo.json` | monorepo packages list |
| `tsconfig.json` (every workspace) | `strict`, `exactOptionalPropertyTypes`, `noUncheckedIndexedAccess` flags |
| `CLAUDE.md` / `AGENTS.md` / `README.md` | "DO NOT BUILD" lists, scope rules, load-bearing invariants, language conventions (DE/EN), naming policies |
| `.coordination/lanes.json` (if present) | feature-lane ownership |
| `.github/workflows/*.yml` | CI pipeline expectations |
| `pyproject.toml` / `Cargo.toml` / `go.mod` | non-JS stacks |
| `next.config.{js,ts}` / `vite.config.*` / `vue.config.*` | bundler clues |
| `prisma/schema.prisma` / `drizzle.config.*` / `migrations/` | DB layer |
| `.gitignore` | what's expected to be ignored |
| `vitest.config.*` / `jest.config.*` / `playwright.config.*` / `pytest.ini` | test runners |

Persist `PROFILE` to `${RUN_DIR}/_profile.json`:

```jsonc
{
  "stack": {
    "languages": ["ts", "tsx", "py"],
    "frameworks": ["next@16", "react@19"],
    "test_runners": ["vitest", "playwright"],
    "package_manager": "pnpm",
    "monorepo": true,
    "workspaces": ["artifacts/api-server", "artifacts/creator-chat", "lib/db", "..."]
  },
  "invariants": [
    {"name": "OnlyAPI mock-only safety lock",
     "evidence": "src/lib/repositories/repository-factory.ts:getRepository()",
     "verify": "grep -n 'return mockRepository' src/lib/repositories/repository-factory.ts"},
    {"name": "No markChatRead/Unread server calls",
     "evidence": "AGENTS.md § DO NOT BUILD",
     "verify": "rg 'markChatRead|markChatUnread' src/ | grep -v mock"},
    {"name": "German UI strings preserved",
     "evidence": "CLAUDE.md § currentLanguage",
     "verify": "informational"}
  ],
  "language_policy": {
    "ui_strings": "de",
    "code_identifiers": "en"
  },
  "scope_blocklist": ["tickets", "automations", "posts", "tiktok", "batch", "billing"],
  "tsconfig_strictness": {
    "strict": true,
    "exactOptionalPropertyTypes": true,
    "noUncheckedIndexedAccess": true
  },
  "scripts": {
    "typecheck": "pnpm typecheck",
    "test": "pnpm test --run",
    "build": "pnpm build",
    "lint": "pnpm lint",
    "format_check": "pnpm format -- --check"
  }
}
```

The `PROFILE` is the **adaptation layer**. Every sub-skill template below contains `{{INVARIANTS}}`, `{{SCOPE_BLOCKLIST}}`, `{{SCRIPTS.*}}` placeholders that you fill in **before** writing each skill file to disk.

## 0.4 Self-bootstrap the kit

Check `code-quality-skills/` against the embedded inventory below.

```
code-quality-skills/
├── README.md
├── orchestrator.md
├── ledger-schema.md
├── MORE-IDEAS.md
├── _templates/
│   ├── ledger.template.json
│   ├── file-coverage.template.json
│   ├── report.template.md
│   ├── dashboard.template.html
│   ├── hot-spots.template.json
│   └── fix-prompts.template.md
└── skills/
    ├── d1-correctness.md
    ├── d2-types.md
    ├── d3-tests.md
    ├── d4-security.md
    ├── d5-performance.md
    ├── d6-architecture.md
    ├── d7-a11y.md
    ├── d8-dead-code.md
    ├── d9-docs.md
    ├── d10-ci-health.md
    ├── d11-i18n.md
    ├── d12-deps.md
    ├── d13-cache-keys.md
    ├── d14-css-tokens.md
    ├── d15-flags.md
    ├── d16-bundle-composition.md
    ├── d17-error-boundaries.md
    ├── d18-resource-cleanup.md
    └── coverage-sweeper.md
```

If any file is missing OR `--refresh-kit` was passed, **regenerate it from the embedded templates in `# Phase 5 — Embedded skill templates` below**, substituting `{{PROFILE.*}}` placeholders. Print one line per file written.

If everything exists and `--refresh-kit` was NOT passed, print `✅ kit verified, reusing existing skills`.

---

# Phase 1 — Aristotle First Principles (≤ 5 lines)

Write `${RUN_DIR}/_assumptions.md`:

```markdown
# Assumption Autopsy — anchor every finding to one of these

1. **What this codebase claims to do** — read from `CLAUDE.md` / `AGENTS.md` / `README.md`.
   _Auto-filled from PROFILE.stack.frameworks + repo description._

2. **Promises to users** — list 3:
   - {{e.g. "mock-only mode (no live writes)"}}
   - {{e.g. "WCAG 2.1 AA"}}
   - {{e.g. "exactOptionalPropertyTypes"}}

3. **Most load-bearing invariant** — {{e.g. "OnlyAPI safety lock — `getRepository()` returns mock"}}.

4. **Promise-breaking bugs vs. cosmetic** — explicit: a finding that bypasses the safety lock is CRITICAL; a misaligned tooltip is LOW.

5. **What the maintainers care about most** — derived from `git log -50 --pretty=format:%s` keyword frequency. List the top 5 themes.
```

Every sub-skill MUST cite this file. Findings that don't trace back are downgraded.

---

# Phase 2 — Seed the ledgers

## 2.1 `_ledger.json` (run state machine)

Use `code-quality-skills/_templates/ledger.template.json` as base. Fill:

```jsonc
{
  "run_id": "<RUN_ID>",
  "schema_version": "2.0",
  "started_at": "<ISO8601 UTC now>",
  "scope": "<from $ARGUMENTS>",
  "git": {
    "branch": "<git rev-parse --abbrev-ref HEAD>",
    "head_sha": "<git rev-parse HEAD>",
    "head_short": "<SHORT_SHA>",
    "dirty": <git diff --quiet || true>,
    "ahead_of_main": <git rev-list --count main..HEAD>,
    "behind_main": <git rev-list --count HEAD..main>
  },
  "profile_path": "_profile.json",
  "tools_available": {
    "pnpm": <bool>, "tsc": <bool>, "vitest": <bool>, "jest": <bool>,
    "eslint": <bool>, "prettier": <bool>, "ts-prune": <bool>,
    "depcheck": <bool>, "axe-core": <bool>, "gh": <bool>,
    "ripgrep": <bool>, "ast-grep": <bool>, "madge": <bool>,
    "playwright": <bool>, "git": <bool>
  },
  "agents": [],
  "phase": "dispatching",
  "config": {
    "coverage_gate": 0.99,
    "stale_claim_minutes": 30,
    "max_parallel_agents": 4,
    "per_skill_timeout_seconds": 300
  },
  "updated_at": "<ISO8601 UTC now>"
}
```

## 2.2 `_file-coverage.json` (file-by-file matrix)

Build the file inventory:

```bash
git ls-files \
  -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.mjs' '*.cjs' \
     '*.py' '*.rs' '*.go' '*.java' '*.kt' \
     '*.css' '*.scss' '*.md' '*.json' '*.yml' '*.yaml' \
     '*.html' '*.svg' \
  ':!**/node_modules/**' ':!**/dist/**' ':!**/.next/**' \
  ':!**/build/**' ':!**/.turbo/**' ':!**/coverage/**' \
  ':!audit-reports/**' ':!code-quality-skills/**' \
  ':!**/*.lock' ':!**/pnpm-lock.yaml'
```

For each file, capture:

```jsonc
{
  "<path>": {
    "size_bytes": <int>,
    "loc": <int from `wc -l`>,
    "blank_lines": <int>,
    "comment_lines": <int via `cloc` if available, else 0>,
    "language": "ts|tsx|py|md|...",
    "category": "component|hook|store|util|test|config|doc",
    "last_modified": "<git log -1 --format=%cI -- <path>>",
    "last_author": "<git log -1 --format=%an>",
    "modification_count_30d": <git log --since=30.days --oneline -- <path> | wc -l>,
    "complexity_estimate": <heuristic: loc/50 + nesting depth>,
    "reviewed_by": [],
    "findings": [],
    "tags": []
  }
}
```

The `category` is heuristic:

- `*.test.{ts,tsx}` / `__tests__/**` → `test`
- `*.config.*` / `.eslintrc*` / `tsconfig*` → `config`
- `*.tsx` in `components/` → `component`
- `*.ts` in `hooks/` or starts with `use` → `hook`
- `*.store.{ts,tsx}` → `store`
- `*.md` → `doc`
- everything else → `util`

This categorisation lets sub-skills target the right files (e.g. D7 a11y only reviews `component`).

Persist as `${RUN_DIR}/_file-coverage.json`. Set `phase: "auditing"` in the ledger.

---

# Phase 3 — Dispatch sub-skills

## 3.1 Dispatch graph

```
GROUP A (greps, parallel safe, max 4 concurrent):
  D1-correctness · D4-security · D6-architecture · D8-dead-code · D9-docs ·
  D11-i18n · D14-css-tokens · D15-flags · D17-error-boundaries · D18-resource-cleanup

GROUP B (heavy tooling, sequential to avoid CPU contention):
  D2-types (runs `{{PROFILE.scripts.typecheck}}`)
  D3-tests (runs `{{PROFILE.scripts.test}}` + reads coverage)
  D5-performance (runs `{{PROFILE.scripts.build}}` + reads bundle stats)
  D10-ci-health (runs typecheck + test + build + lint, captures all exit codes)
  D12-deps (runs `pnpm audit --json` + `pnpm outdated --format json`)
  D13-cache-keys (greps + light AST)
  D16-bundle-composition (post-D5; reuses build output)

GROUP C (after Group A):
  D7-a11y (needs the component list from D6)

ALWAYS LAST:
  coverage-sweeper (gap-filler; FAILs run if coverage <99%)
```

## 3.2 Spawn protocol

For each skill:

1. **Spawn a sub-agent** (Agent tool) with `subagent_type: "general-purpose"`.
2. **Pass it the skill file path** + `_profile.json` + `_ledger.json` + `_file-coverage.json` + `_assumptions.md`. Tell it: _"Read these four files. Follow the skill's CLAIM → AUDIT → REPORT → CHECK OUT contract precisely. Do not edit production code. Do not skip steps."_
3. **Track it in `_ledger.json:agents[]`** with the agent's `id` (e.g. `d1-correctness@<spawn-ts>`), `status`, timestamps.
4. **On completion**, verify the agent updated:
   - `_ledger.json:agents[<id>].status` to `done` or `failed`
   - `_file-coverage.json:files[*].reviewed_by[]` for every file it inspected
   - `${RUN_DIR}/<skill>.md` exists and is non-empty

## 3.3 Concurrency limits

- Max 4 sub-agents in parallel (host responsiveness).
- Per-skill hard timeout: 5 minutes. On timeout, mark `failed` with `notes: "timeout"` and proceed.
- Per-skill stale-claim window: 30 minutes (for resume-after-crash).

## 3.4 Live status

Every 30 seconds, print one line:

```
[auditing] D1✅ D2⏳ D3⏳ D4✅ D5⏳ D6✅ D7⌛ D8✅ D9✅ D10⏳ ...  (8/19 done, coverage 67.4%)
```

Symbols: ✅ done · ⏳ in_progress · ❌ failed · ⌛ queued · ⏰ timed-out.

---

# Phase 4 — Sweep, validate, roll up

## 4.1 Coverage sweep

After all D-skills complete, dispatch `coverage-sweeper.md`. It reads `_file-coverage.json`, finds every file with empty `reviewed_by[]`, and runs the generic per-file audit. After sweep, recompute:

```
total_files     = count(files)
reviewed_files  = count(files where reviewed_by != [])
coverage_pct    = reviewed_files / total_files * 100
unowned_files   = count(files where reviewed_by == ["coverage-sweeper"])
hot_files       = top 10 files by len(reviewed_by) — multi-dimension attention
```

**Hard gate**: if `coverage_pct < 99`, set `phase: "failed"` and emit a clear error message naming the unreviewed files. Do NOT write the rolled-up REPORT.md.

Set `phase: "summarising"` if coverage passes.

## 4.2 Aggregate findings

Walk every `${RUN_DIR}/<skill>.md` and parse the `## Findings` section. Build:

```jsonc
// ${RUN_DIR}/_findings.json
{
  "by_severity": {"critical": [...], "high": [...], "medium": [...], "low": [...]},
  "by_dimension": {"d1": [...], "d2": [...], ...},
  "by_file": {"<path>": [...]},
  "by_tag": {"async": [...], "auth": [...], "perf": [...]},
  "duplicates_collapsed": <int — same finding raised by ≥2 skills>,
  "total": <int>
}
```

## 4.3 Compute scores & technical-debt quotient

Per dimension: `score_d<N> = 10 - 2 × critical - 1 × high - 0.5 × medium - 0.1 × low` (clamp 0..10).

Overall: weighted sum using each skill's `weight` from its frontmatter. Max = 100.

**Technical Debt Quotient (TDQ)** — a single number for the project:

```
TDQ = (sum(loc × complexity_estimate) over flagged files)
      / (total_loc) × 100
```

Lower is better. Put it on the dashboard.

## 4.4 Hot-spots heatmap → `_hot-spots.json`

Top 20 files ranked by:

```
hotspot_score = log(1 + modification_count_30d) × len(findings) × (loc / 100)
```

This surfaces files that are **changing fast AND have many findings AND are large** — the technical-debt epicentres.

## 4.5 Generate outputs

Write **all four** of these into `${RUN_DIR}/`:

| File | Purpose | Audience |
|------|---------|----------|
| `REPORT.md` | Rolled-up TL;DR + scoring + findings | humans, PRs |
| `dashboard.html` | One-page interactive dashboard (sortable findings table, hot-spots heatmap, score gauges) | humans, browser |
| `_findings.json` | Machine-readable findings bundle | CI, integrations |
| `fix-prompts.md` | One copy-pasteable Claude Code prompt per CRITICAL+HIGH finding | next-step automation |

`dashboard.html` is **self-contained** (inline CSS, no JS deps). It includes:
- Score donut for overall + per-dimension
- Sortable findings table (by severity, dimension, file)
- Hot-spots heatmap (top 20 files)
- Coverage map (file-tree colored by review attention)
- Trend chart (if `--against=<run-id>` was passed or a baseline exists)

`fix-prompts.md` has one section per finding:

````markdown
## Fix #C1 — `path/to/file.ts:42` — <title>

**Severity:** 🔴 CRITICAL · **Dimension:** D4 Security · **Tags:** auth, xss

**Context:**
> _two-line excerpt around the finding (no more than 5 lines, never the full file)_

**Fix prompt — paste into Claude Code:**

```
Fix the security finding in path/to/file.ts:42 — <one-sentence problem>.
Constraints:
- Do not break the existing API surface (keep public exports unchanged).
- Add a regression test in path/to/file.test.ts.
- Verify the OnlyAPI safety lock is still intact after the change.
- Open a separate PR titled "fix(security): <short>".
```
````

## 4.6 Trend (only if `--against=<run-id>` or baseline exists)

Write `${RUN_DIR}/trend.md`:

```
# Trend vs. <baseline-run-id>
- Score: 78 → 82 (+4)
- Critical: 3 → 1 (-2)  ✅
- High:    8 → 6 (-2)  ✅
- Medium: 14 → 19 (+5) ⚠️
- Low:     22 → 18 (-4) ✅
- New findings: …
- Fixed findings: …
- Regressions: …
```

## 4.7 Final ledger close

Set `phase: "done"`, `completed_at`, `overall_score`, `tdq`. Print:

```
✅ Audit complete · run-id 2026-05-01__abc1234
   score 82/100 · TDQ 14.3 · 47 findings (1🔴 6🟠 19🟡 21🟢) · coverage 99.3%
   reports: audit-reports/2026-05-01__abc1234/
     REPORT.md · dashboard.html · _findings.json · fix-prompts.md
```

---

# Phase 5 — Embedded skill templates (used by self-bootstrap)

> When you self-bootstrap (Phase 0.4), you read each block below, substitute `{{PROFILE.*}}` placeholders, and write the result to disk. **Never include a `{{...}}` placeholder in the final file** — substitute them all.

## 5.1 `code-quality-skills/README.md`

```markdown
# code-quality-skills/ — Multi-Agent Audit Kit (auto-generated)

This kit was generated by `code-quality-checker.md` v2.0.0 against project profile:
- Stack: {{PROFILE.stack.frameworks}}
- Test runners: {{PROFILE.stack.test_runners}}
- Strict TS: {{PROFILE.tsconfig_strictness.strict}}
- Invariants: {{PROFILE.invariants[*].name}}

## Layout

(see folder tree)

## Coordination

Two ledger files in every `audit-reports/<run-id>/`:
- `_ledger.json` — agent state machine (CLAIM → AUDIT → REPORT → CHECK OUT).
- `_file-coverage.json` — file-by-file `reviewed_by[]` matrix; ≥99% gate enforced by `coverage-sweeper`.

Outputs: `REPORT.md` · `dashboard.html` · `_findings.json` · `fix-prompts.md` · optional `trend.md`.

## Re-bootstrap

Run `/code-quality-checker --refresh-kit` to regenerate this folder from the latest templates in `code-quality-checker.md` at the repo root.
```

## 5.2 `code-quality-skills/orchestrator.md`

Mirror of Phases 0–4 above, condensed to ~150 lines. Sub-agents read this when delegated; it points back to `code-quality-checker.md` for the full reference.

## 5.3 `code-quality-skills/ledger-schema.md`

Full JSON-Schema for `_ledger.json` and `_file-coverage.json` (see Phase 2). Document the atomic-RW retry protocol (read → modify → write → re-read → retry up to 3×).

## 5.4 Sub-skill template (applied to every D<N>)

Every skill file follows this exact frontmatter + body structure. **Substitute `{{*}}` placeholders before writing.**

```markdown
---
description: D{{N}} — {{TITLE}}. {{ONE_LINE_PURPOSE}}
weight: {{WEIGHT}}
group: A|B|C
requires_tools: [{{TOOLS}}]
adapts_to: {{STACKS}}
---

You are sub-skill **D{{N}} {{TITLE}}**. Run inside a coordinated multi-agent audit.

# Inputs you MUST read first

1. `audit-reports/{{run_id}}/_profile.json` — adapt your checks to the detected stack.
2. `audit-reports/{{run_id}}/_assumptions.md` — anchor every finding to one of those 5 answers.
3. `audit-reports/{{run_id}}/_ledger.json` — your status entry lives here.
4. `audit-reports/{{run_id}}/_file-coverage.json` — append yourself to `reviewed_by[]` for every file you touch.

# CLAIM

Append to `_ledger.json:agents[]`:
```json
{
  "id": "d{{N}}-{{slug}}@<ISO8601>",
  "skill": "d{{N}}-{{slug}}",
  "status": "claimed",
  "claimed_at": "<now>",
  "intends_to_read": [{{globs}}],
  "report_path": "audit-reports/{{run_id}}/d{{N}}-{{slug}}.md"
}
```
Flip to `in_progress` when you start work.

# AUDIT

{{CHECKS}}  ← injected per dimension; see 5.5–5.23

For every file you touch:
- Append `"d{{N}}-{{slug}}"` to `_file-coverage.json:files.<path>.reviewed_by[]`.
- If you find an issue, append a finding object:
  ```json
  {
    "agent": "d{{N}}-{{slug}}",
    "line": <int>,
    "severity": "critical|high|medium|low",
    "rule": "<short-id>",
    "msg": "<one sentence>",
    "tags": ["{{relevant-tags}}"],
    "fix_prompt_id": "F{{auto-incremented}}"
  }
  ```

# REPORT

Write `audit-reports/{{run_id}}/d{{N}}-{{slug}}.md`:

```markdown
# D{{N}} — {{TITLE}} — score x/10

**Files reviewed:** N · **Findings:** 🔴critical=A · 🟠high=B · 🟡medium=C · 🟢low=D · **Tags:** {{top tags}}

## TL;DR (3 bullets max)
- …

## Critical
1. **<title>** (`path:line`) — why — fix sketch.

## High / Medium / Low
…

## Anti-findings (3)
- "X looks risky but isn't because Y."

## Score reasoning
{{SCORE_RUBRIC}}

## Fix-prompt seeds
- F12 → "<one-sentence prompt>"
- F13 → …
```

# CHECK OUT

Update your ledger entry:
```json
{
  "status": "done",
  "completed_at": "<now>",
  "elapsed_ms": <int>,
  "findings": {"critical": A, "high": B, "medium": C, "low": D},
  "files_reviewed_count": N,
  "tools_used": [{{...}}],
  "tools_failed": [{{...}}]
}
```

# Hard rules
- **Never edit code.** Read-only audit.
- **Never invent file:line references.** Every citation is from a real grep / read / tool output.
- **Never bypass project invariants.** {{INVARIANTS_REMINDER}}
- **Cap report at 400 lines.** Group repeated findings; link to a v2 follow-up prompt.
- **Honour {{PROFILE.language_policy}}** — DO NOT flag German UI strings as "should be English" when policy says ui_strings=de.
```

## 5.5 D1 Correctness — `{{CHECKS}}` block

```
- **Race / async hazards:**
  - `rg -n "\.then\(" {{src_globs}} | grep -v "await"` — fire-and-forget.
  - `rg -n "async \([^)]*\) =>\s*\{[^}]*\.map\(" {{src_globs}}` — `.map(async)` without Promise.all.
- **Swallowed errors:**
  - `rg -n "catch\s*\([^)]*\)\s*\{\s*\}" {{src_globs}}` — empty catch.
- **Type bypasses:**
  - `rg -n "as any" {{src_globs}}` (count + top-10 files).
  - `rg -n "// @ts-(expect-error|ignore|nocheck)" {{src_globs}}`.
- **Lint bypasses:**
  - `rg -n "eslint-disable" {{src_globs}}`.
- **Project invariants** (auto-injected from PROFILE.invariants):
  {{#each PROFILE.invariants}}
  - {{this.name}} — verify with: `{{this.verify}}`
  {{/each}}
- **Unreachable code**: search for `if (false)`, `return;` followed by code, `throw` followed by code.

For every file you read, append `"d1-correctness"` to `_file-coverage.json` `reviewed_by[]`.
```

## 5.6 D2 Type Safety — `{{CHECKS}}`

```
- Run `{{PROFILE.scripts.typecheck}}`. Capture full output. Count errors per file. Report top 20 errors verbatim.
- For every workspace, parse `tsconfig.json`:
  - flag missing `strict`, `exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`, `noImplicitAny`.
- `rg -n ":\s*any\b" {{src_globs}}` — explicit `any`.
- `rg -n "as unknown as" {{src_globs}}` — double-cast hacks.
- `rg -n "// @ts-" {{src_globs}}` — every type-system bypass with reason.
- For every file with ≥3 `any`/`as any` hits → mark hot-spot.
```

## 5.7 D3 Tests — `{{CHECKS}}`

```
- Run `{{PROFILE.scripts.test}}`. Record exit code, pass/fail/skip counts.
- If `coverage/coverage-summary.json` exists, parse per-package line/branch coverage. List packages <70%.
- `rg -n "\.skip\(|\.todo\(|xit\(|it\.only\(|describe\.only\(|fdescribe\(|fit\(" {{src_globs}}` — red flags.
- For every module changed in `git log -50 --name-only`, check sibling `*.test.{ts,tsx}` exists.
- Flaky tests: parse `gh run list -L 30 --json` for failure patterns on the same test name across runs.
- Snapshot bloat: `find . -type d -name __snapshots__` with file count >50.
```

## 5.8 D4 Security — `{{CHECKS}}`

```
- Hardcoded secrets: `rg -n "(API_KEY|SECRET|PASSWORD|TOKEN|BEARER)\s*=\s*['\"][^'\"]{8,}['\"]" {{src_globs}}`.
- Sinks: `rg -n "\beval\(|new Function\(|innerHTML\s*=|dangerouslySetInnerHTML" {{src_globs}}`.
- Client-side env leaks: in Next.js, `rg -n "process\.env\." {{client_globs}}` — verify `NEXT_PUBLIC_*`.
- Auth-paths in caches: search SW / persist configs for `/api/auth`, `/connector`, `/admin`.
- gitignore: verify `.env*`, `*-state`, `*.pem`, build outputs are listed.
- CSP/headers: parse `next.config.{js,ts}` for `Content-Security-Policy`, `X-Frame-Options`.
- Defer deep CVE-mapping to dedicated `security-auditor` agent.
```

## 5.9 D5 Performance — `{{CHECKS}}`

```
- Run `{{PROFILE.scripts.build}}`. Capture First Load JS / route, total bundle. Top-5 heaviest routes.
- `rg -n "useEffect\(\s*\(\)\s*=>\s*\{[^}]*\}\s*,\s*\[\s*\]\s*\)" {{src_globs}}` — empty deps with side-effects.
- Total `useEffect` count.
- `rg -n "\.map\(async " {{src_globs}}` — N+1 candidates.
- `useState\(\(\)\s*=>` — flag heavy initialisers.
- `<img\s` (Next.js) — should use `next/image`.
- `React\.memo\(|memo\(` count vs. list-row component count.
- `import .* from ['\"]lodash['\"]` — unscoped imports.
```

## 5.10–5.23 D6..D18 + Coverage-Sweeper

Same template, dimension-specific `{{CHECKS}}`. The full content of D6 architecture, D7 a11y, D8 dead-code, D9 docs, D10 ci-health, D11 i18n, D12 deps, D13 cache-keys, D14 css-tokens, D15 flags, D16 bundle-composition, D17 error-boundaries, D18 resource-cleanup, and coverage-sweeper is embedded the same way — each with its own `{{CHECKS}}` block reflecting:
- the project's `PROFILE.stack.frameworks`
- the project's `PROFILE.invariants`
- the project's `PROFILE.scope_blocklist` (e.g. don't audit out-of-scope dirs)
- the project's `PROFILE.language_policy`

When you bootstrap, write each file with the placeholders resolved.

## 5.24 `_templates/dashboard.template.html`

Self-contained HTML with inline CSS. Sections:
1. **Header** — run-id, scope, score gauge, TDQ.
2. **Score breakdown** — bar chart per dimension (CSS-only).
3. **Findings table** — sortable by severity / dimension / file (CSS `:target` filtering, no JS).
4. **Hot-spots heatmap** — top 20 files, color-coded by `hotspot_score`.
5. **Coverage map** — flat file list, color = number of dimensions that reviewed it (0 = red, 5+ = green).
6. **Trend** — if a baseline exists, show score delta + finding deltas.

## 5.25 `_templates/fix-prompts.template.md`

See 4.5. One section per CRITICAL+HIGH finding. Each prompt is self-contained (paste-able into Claude Code without further context).

---

# Phase 6 — End-to-end execution checklist

You MUST complete every item:

- [ ] Phase 0.1 — `$ARGUMENTS` parsed.
- [ ] Phase 0.2 — `RUN_ID` computed, `RUN_DIR` created.
- [ ] Phase 0.3 — `_profile.json` written with detected stack + invariants.
- [ ] Phase 0.4 — kit verified or bootstrapped (print one line per file written).
- [ ] Phase 1 — `_assumptions.md` written.
- [ ] Phase 2 — `_ledger.json` + `_file-coverage.json` seeded.
- [ ] Phase 3 — every D-skill spawned, completed (or failed with `notes:`).
- [ ] Phase 4.1 — coverage-sweeper ran, `coverage_pct ≥ 99` confirmed (or run failed cleanly).
- [ ] Phase 4.2 — `_findings.json` aggregated.
- [ ] Phase 4.3 — scores + TDQ computed.
- [ ] Phase 4.4 — `_hot-spots.json` written.
- [ ] Phase 4.5 — `REPORT.md`, `dashboard.html`, `fix-prompts.md` written.
- [ ] Phase 4.6 — `trend.md` written if applicable.
- [ ] Phase 4.7 — ledger phase = `done`, final summary line printed.

---

# Hard rules (apply throughout)

- **Read-only.** This kit never edits production code. Period.
- **No phantom citations.** Every `path:line` must come from a real grep/read/tool output recorded in `_file-coverage.json`.
- **Honour project invariants.** PROFILE.invariants is sacred. A finding that bypasses one is auto-CRITICAL.
- **Honour project language policy.** DO NOT flag German UI strings as "should be English" when `PROFILE.language_policy.ui_strings=de`.
- **Honour scope blocklist.** Never recommend building anything in `PROFILE.scope_blocklist`.
- **Cap each dimension report at 400 lines.** Cap rolled-up `REPORT.md` at 1200 lines. Cap `dashboard.html` at 200 KB.
- **Cap fix-prompts.** One per CRITICAL+HIGH only (LOW/MEDIUM are listed in REPORT.md but don't get individual prompts).
- **Resumability.** If a previous run for the same `RUN_ID` exists, prefer resuming over restarting (only re-run `failed` and `claimed`-but-stale agents).
- **No edits to historical reports.** `audit-reports/<old-run>/` is immutable.

---

# What this orchestrator is NOT

- Not a refactor agent — produces findings and fix-prompts, never patches.
- Not a deep-dive — that's `/code-quality-analyse-v2 <finding-id>` (separate skill, deferred).
- Not a CI gate — exits 0 even with critical findings; the user / CI decides what to enforce.
- Not a security pentester — D4 is surface scan; defer deep CVE work to `senior-security` / `security-auditor` agents.

---

# Begin

State your **run-id**, **detected stack** (3 bullets max), **invariants count**, **kit status** (verified|bootstrapped), and **dispatch plan** (group sizes) in 5 lines max. Then execute Phase 0 through Phase 4 without further commentary until you reach the final summary line in Phase 4.7.
