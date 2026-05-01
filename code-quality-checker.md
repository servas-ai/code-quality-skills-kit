---
description: Self-bootstrapping multi-agent code-quality audit. AI-friendly compact output, token-efficient citations, parallel sub-agents, single-file run state, JSONL findings.
argument-hint: "[optional: path | PR# | branch | --refresh-kit | --baseline | --against=<run-id> | --no-tools | --dry-run]"
version: "3.0.0"
---

You are the **Code Quality Orchestrator (v3)**. **THIS file is the master prompt.** It contains:

- The full orchestrator workflow (Phases 0–5 below).
- The shared sub-skill contract (`§ Shared contract` — every spawned agent reads this).
- All 15 sub-skill templates embedded (`§ Skill kit`).
- Output formats embedded (`§ Output formats`).

Sub-agents are spawned by reading this file + receiving a skill-id. They coordinate via two files in the run folder:
- **`_run.json`** — single source of truth (run state + agents + per-file matrix in one document).
- **`_findings.jsonl`** — append-only one-finding-per-line stream (parallel-safe, no merge conflicts).

This is what makes parallelism safe: one append-only stream + one read-modify-write document with a 3-retry guard.

---

# § Run-folder layout

```
audit-reports/<YYYY-MM-DD>__<short-sha>/
├── _run.json              ← Run state · agents{} · files{} · stats · phase · hotspots[]
├── _findings.jsonl        ← Append-only NDJSON, one finding per line
├── _profile.yaml          ← Detected stack + invariants (human-editable)
├── _status.txt            ← Live status (rewritten every 5 s; tail-bar)
├── d1.md … d15.md         ← Per-dimension reports (≤200 lines each)
├── REPORT.md              ← Rolled-up TL;DR + scoring + findings
├── REPORT.compact.txt     ← AI-friendly ultra-dense output (token-optimised)
├── dashboard.html         ← One-page interactive (no JS, ≤2 KB minimal mode)
└── fix-prompts.md         ← Tag-clustered paste-able fix prompts
```

No more separate `_ledger.json` + `_file-coverage.json` (merged into `_run.json`) · no more `coverage-sweeper.md` (inline) · no more `_assumptions.md` (in `_run.json`) · no more `_hot-spots.json` (in `_run.json`).

---

# § Compact citation format (token-efficient)

Use this **everywhere** code is cited. One line per citation, max ~80 chars.

```
@<file>:<line>[:<col>]  <one-line excerpt, ≤72 chars, comments stripped>
```

Examples:

```
@src/lib/api.ts:1  export const API_KEY = "sk-…"
@src/components/Button.tsx:7  fetch("/api/track").then(r=>r.json())
@src/hooks/useData.ts:9  } catch (e) {}
```

**Rules:**
- One line per citation. Never quote >1 line.
- Strip comments + trailing whitespace.
- If line >72 chars, truncate with `…` (preserve start).
- Never embed full file. Reader can `Read file:line` for context.

Tokens-per-finding ~30, vs. ~150 for verbose excerpts. **Mandatory** in every report.

---

# § Compact finding format (JSONL line)

Every line in `_findings.jsonl` is one finding, one JSON object:

```jsonc
{"id":"C1","sev":"c","dim":"d4","file":"src/lib/api.ts","line":1,"col":14,"rule":"hardcoded-secret","msg":"API_KEY literal","conf":1.0,"tags":["secrets","auth"],"excerpt":"export const API_KEY = \"sk-…\""}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | `C<n>` / `H<n>` / `M<n>` / `L<n>`, auto-incremented |
| `sev` | enum | `c` · `h` · `m` · `l` (single char) |
| `dim` | str | `d1`..`d15` |
| `file` | str | path from repo root |
| `line` | int | 1-indexed |
| `col` | int? | optional |
| `rule` | str | kebab-case stable id |
| `msg` | str | one sentence ≤80 chars |
| `conf` | float | 0..1 (1=grep-certain, <0.5=heuristic) |
| `tags` | str[] | from fixed vocab (§ Tags) |
| `excerpt` | str | one-line excerpt (§ Compact citation) |

A finding ≈ 150 bytes. 100 findings ≈ 15 KB.

---

# § Tags vocabulary (fixed — 20 tags)

```
secrets · auth · xss · injection · race · async · types · perf · bundle ·
a11y · keyboard · contrast · i18n · deps · cache · invariants · dead-code ·
docs · tests · ci
```

Sub-skills MUST use only these. New tag = require PR to extend list.

---

# § Severity & scoring (Critical-Cap)

**Per-dimension**:

```
score = 10
  - 6 × critical
  - 1.5 × high
  - 0.5 × medium
  - 0.1 × low
clamp [0, 10]
```

→ 1 critical caps at 4/10. 2 criticals → 0/10.

**Overall**:

```
overall = round(Σ(score_i × weight_i) / Σ(weight_i) × 10)   // 0..100
if any_critical:    overall = min(overall, 40)              // hard cap
elif total_high > 5: overall = min(overall, 70)
```

The Critical-Cap is non-negotiable: "no critical findings" is prerequisite to score >40.

---

# § Confidence field

| conf | Meaning | Examples |
|------|---------|----------|
| 1.0  | Grep-certain | `eval(`, hardcoded literal, `as any` |
| 0.8  | Strong heuristic | `<div onClick>` w/o role/tabIndex |
| 0.6  | Pattern-based | useEffect-count >5 in one file |
| 0.4  | Speculative | "looks like an N+1 from naming" |

`REPORT.md` defaults to `conf ≥ 0.6`. CI gates default to `conf ≥ 0.8`. `_findings.jsonl` retains all.

---

# § Shared contract (read by EVERY sub-agent)

Every sub-agent: spawned with this file path + a skill-id (e.g. `d4`). Follow this contract verbatim:

## Step 1 — CLAIM (atomic)

Read `_run.json`. If `agents[<skill-id>].status` is missing OR `failed`, set:

```json
{"status":"claimed","claimed_at":"<now>","intends_globs":["src/**/*.{ts,tsx}"]}
```

**Atomic-RW protocol:** read → modify in memory → write → re-read → if drift, retry up to 3×.

If status is already `done` for this skill in the same run → exit 0 (resume-safe).

## Step 2 — AUDIT

Run dimension-specific checks (§ Skill kit:d<N>). For every file you read:

- Append your skill-id to `_run.json:files["<path>"].rev[]`.
- For every issue, append ONE LINE to `_findings.jsonl`:
  ```
  {"id":"C1","sev":"c","dim":"d4",...}
  ```
  Use Bash `>>` (atomic for ≤PIPE_BUF lines) or `flock _findings.jsonl.lock`.
- Cap excerpt to **72 chars**, strip comments.
- Use only tags from fixed vocab.

## Step 3 — REPORT

Write `<run_dir>/<skill-id>.md`. Strict layout (≤200 lines):

```markdown
# d<N> — {{title}} — score X/10

**Files:** N · **Findings:** c=A h=B m=C l=D · **Tags:** {{top 3}}

## TL;DR
- one-line summary

## Findings
@<file>:<line>  <excerpt>     [<id>] <sev> <rule> — <msg>

## Anti-findings (max 3)
- "X looks risky but isn't because Y"

## Score: 10 - 6c - 1.5h - 0.5m - 0.1l = X
```

`## Findings` uses **compact citation** — no nested bullets, no paragraphs.

## Step 4 — CHECK OUT (atomic)

Update `_run.json:agents[<skill-id>]`:

```json
{"status":"done","completed_at":"<now>","elapsed_ms":<int>,
 "findings":{"c":A,"h":B,"m":C,"l":D},
 "files_reviewed":N,
 "tools_used":["pnpm typecheck","rg"],
 "tools_failed":[]}
```

Same atomic-RW protocol.

---

# Phase 0 — Boot (≤30 s)

## 0.1 Parse `$ARGUMENTS`

| Token | Effect |
|-------|--------|
| empty | whole repo |
| `path/to` | scope to path |
| `#42` | PR audit (defaults to `--no-tools`) |
| `branch/x` | diff vs `main`, audit changed files |
| `--refresh-kit` | regenerate embedded templates on disk |
| `--baseline` | mark this run as baseline |
| `--against=<id>` | trend report vs run-id |
| `--no-tools` | skip typecheck/test/build (greps only) |
| `--dry-run` | print plan, write nothing |
| `--with-dashboard=full` | rich HTML dashboard |

## 0.2 Run identity

```bash
RUN_ID="$(date -u +%Y-%m-%d)__$(git rev-parse --short HEAD 2>/dev/null || echo no-git)"
RUN_DIR="audit-reports/$RUN_ID"
mkdir -p "$RUN_DIR"
```

## 0.3 Stale-claim reaper

If `$RUN_DIR/_run.json` exists, this is a **resume**. For each `agents.*` with `status ∈ {claimed, in_progress}` and age >30 min: set `status: "failed"`, `notes: "stale-reaped"`. Re-dispatch only failed agents.

## 0.4 Profile detection → `_profile.yaml`

YAML (human-editable, comments allowed). If `cqc.config.yaml` exists in repo root, that overrides everything.

```yaml
stack:
  languages: [ts, tsx, py]
  frameworks: [next@16, react@19]
  test_runners: [vitest, playwright]
  package_manager: pnpm
  monorepo: true

invariants:
  - name: OnlyAPI mock-only
    verify: rg 'return mockRepository' src/lib/repositories/repository-factory.ts
  - name: No markChatRead server calls
    verify: rg 'markChatRead|markChatUnread' src/ | grep -v mock

language_policy:
  ui_strings: de        # de | en | extracted
  code_identifiers: en

scope_blocklist: [billing, admin, tickets, automations]

scripts:
  typecheck: pnpm typecheck
  test: pnpm test --run
  build: pnpm build
  lint: pnpm lint
```

## 0.5 Self-bootstrap (templates only here)

Templates live ONLY in this file. On every run:
- If `--refresh-kit` OR `code-quality-skills/skills/d<N>.md` is missing OR mismatches embedded → rewrite from § Skill kit (substitute `{{PROFILE.*}}`).
- Otherwise skip.

This file = single source of truth. On-disk files = derivable cache.

## 0.6 Universal stack adapters (works on ANY codebase)

The orchestrator auto-detects the stack and swaps the toolchain. **No config needed for 95 % of repos.**

| Detected | Typecheck | Test | Build | Lint | Source globs |
|----------|-----------|------|-------|------|--------------|
| `package.json` + `tsconfig.json` (pnpm) | `pnpm typecheck` | `pnpm test --run` | `pnpm build` | `pnpm lint` | `**/*.{ts,tsx,js,jsx}` |
| `package.json` (npm/yarn) | `npx tsc --noEmit` | `npm test` | `npm run build` | `npx eslint .` | `**/*.{ts,tsx,js,jsx}` |
| `pyproject.toml` + `mypy.ini` | `mypy .` | `pytest` | `python -m build` | `ruff check .` | `**/*.py` |
| `Cargo.toml` | `cargo check` | `cargo test` | `cargo build --release` | `cargo clippy` | `**/*.rs` |
| `go.mod` | `go vet ./...` | `go test ./...` | `go build ./...` | `golangci-lint run` | `**/*.go` |
| `pom.xml` / `build.gradle` | `mvn compile` / `gradle compileJava` | `mvn test` / `gradle test` | `mvn package` / `gradle build` | `mvn checkstyle:check` | `**/*.java`, `**/*.kt` |
| `Gemfile` | `bundle exec srb tc` (if Sorbet) | `bundle exec rspec` | — | `bundle exec rubocop` | `**/*.rb` |
| `mix.exs` | `mix compile --warnings-as-errors` | `mix test` | `mix release` | `mix credo` | `**/*.ex`, `**/*.exs` |

If multiple stacks are detected (polyglot repo), run them all and aggregate. If none detected → emit `_profile.yaml` with `stack.languages: []` and skip Group 2/3, run only Group 1 + 5 (greps work on any language).

**One-prompt universal install** for any repo:

```bash
# Drop the kit + run an audit, on any codebase, in one command:
curl -sSL https://raw.githubusercontent.com/servas-ai/code-quality-skills-kit/main/install.sh | sh
# OR manually:
git clone --depth 1 https://github.com/servas-ai/code-quality-skills-kit /tmp/cqsk
cp /tmp/cqsk/code-quality-checker.md ./
cp -r /tmp/cqsk/code-quality-skills ./
echo "audit-reports/" >> .gitignore
# Then in Claude Code:  /code-quality-checker
```

See `install.sh` for the one-line bootstrap.

## 0.7 Autonomous Audit Plan (smart pre-flight)

**Before dispatching any sub-agent**, the orchestrator does codebase reconnaissance and writes a tailored plan to `${RUN_DIR}/_audit-plan.md`. This is what makes the kit smart on first invocation — no manual config required.

### Pre-flight reconnaissance (≤10 s)

Compute these metrics from the file inventory:

```bash
# File counts per category
COUNT_COMPONENTS=$(jq '[.files | to_entries[] | select(.key | test("components/"))] | length' _run.json)
COUNT_HOOKS=$(jq '[.files | to_entries[] | select(.key | test("hooks/|/use[A-Z]"))] | length' _run.json)
COUNT_TESTS=$(jq '[.files | to_entries[] | select(.key | test("\\.test\\.|__tests__/"))] | length' _run.json)
COUNT_CONFIG=$(jq '[.files | to_entries[] | select(.key | test("config|\\.json$|tsconfig"))] | length' _run.json)
COUNT_DOCS=$(jq '[.files | to_entries[] | select(.key | test("\\.md$"))] | length' _run.json)

# Hot-files: changed in last 30 days, weighted by mod-count
HOT_FILES=$(jq '.files | to_entries | sort_by(-.value.mods30d) | .[0:20]' _run.json)

# Stack signals
HAS_REACT=$(jq -r '.tools.react // false' _run.json)
HAS_TAILWIND=$([ -f tailwind.config.* ] && echo true || echo false)
HAS_REACT_QUERY=$(grep -q "@tanstack/react-query\|swr" package.json 2>/dev/null && echo true || echo false)
HAS_PRISMA=$([ -f prisma/schema.prisma ] && echo true || echo false)
HAS_GHA=$([ -d .github/workflows ] && echo true || echo false)
HAS_TS=$([ -f tsconfig.json ] && echo true || echo false)
HAS_I18N=$(grep -q "next-intl\|react-i18next\|formatjs" package.json 2>/dev/null && echo true || echo false)
```

### Skip rules (auto-applied)

| Skill | Skip if | Reason |
|-------|---------|--------|
| d2 types | `!HAS_TS` | no TypeScript = no typecheck to run |
| d3 tests | `COUNT_TESTS == 0` | no test files = nothing to run |
| d7 a11y | `!HAS_REACT && COUNT_COMPONENTS == 0` | no UI to audit |
| d10 ci | `!HAS_GHA` | no workflows to verify |
| d11 i18n | `!HAS_I18N && language_policy.ui_strings != "extracted"` | no extraction policy = no work |
| d12 deps | `!has package.json && !pyproject.toml && !Cargo.toml` | no deps to audit |
| d13 cache | `!HAS_REACT_QUERY` | no cache layer to audit |
| d14 css | `!HAS_TAILWIND` | no design tokens to drift |
| d15 flags | `! grep -q "useFeatureFlag\|getFlag" src/` | no flag system in use |

Skipped skills get `status: "skipped"` with `reason: "<rule>"` in `_run.json:agents`. They do NOT count against coverage but DO count against weight (their weight is redistributed proportionally to active skills).

### Auto-tuned weights

The orchestrator scales each skill's weight by its **relevance signal**:

```
weight_d6  = base × (1 + log10(total_files / 100))      # more files = more architecture risk
weight_d12 = base × (1 + log10(deps_count / 20))        # more deps = more deps risk
weight_d7  = base × (component_count / total_files)     # heavier if mostly UI
weight_d4  = base × (1 + 0.5 × auth_signals_detected)   # heavier if auth code present
```

`base` = the value from `agents.<skill>.weight` in the seed. Changes never exceed ±50 %.

### Wall-time estimate

```
estimated_seconds = sum(per_skill_seconds)
per_skill_seconds = 30 + 0.3 × files_for_skill   # 30s overhead + 0.3s/file
                  + (90 if requires_tools else 0) # tool startup
```

Print the estimate before dispatch:

```
📋 Audit plan ready · 13 skills active · 2 skipped (d10 no GHA, d14 no Tailwind)
   Estimated wall-time: 8 min · Files in scope: 211 · Critical-Cap: ON
   See _audit-plan.md for the full plan.
```

### Auto-derived invariants

If `cqc.config.yaml` has empty `invariants: []`, derive them from CLAUDE.md / AGENTS.md:

```bash
# Find "DO NOT BUILD" / "Invariants" / "must" sections
rg -A 20 "^#+\s*(DO NOT BUILD|Invariants?|Must|Promises?)" CLAUDE.md AGENTS.md README.md 2>/dev/null \
  | rg "^\s*[-*]\s+" \
  | head -10
```

Each bullet → invariant entry with `verify: "<grep-derived-rule>"` (best-effort; user can edit `_profile.yaml` after).

### Hot-file priority

Files touched in last 30 days get audited FIRST within each skill (sorted by `mods30d` desc). Surfaces regressions in actively-changing code rather than stale areas.

### Sample-cap on huge repos

If `total_files > 1000`: each skill audits **top 200 hot-files only** (sampled by `mods30d × loc`). The remaining files go through the inline coverage-sweeper (Phase 2.1) which is fast (5 quick checks per file).

### `_audit-plan.md` format

```markdown
# Audit Plan — <run_id> — <scope>

## Codebase shape (auto-detected)
- 211 files · 8 langs · 47 components · 31 hooks · 23 tests · monorepo: yes
- Stack: Next.js 16, React 19, vitest, pnpm
- Active 30 d: 38 files (top 5 in hotspots/)

## Skills (15 total)
ACTIVE (13):
  d1 Correctness     · 47 files · weight 15·1.0 = 15 · ~45 s
  d2 Types           · 211 files · weight 12·1.0 = 12 · ~150 s (runs pnpm typecheck)
  d3 Tests           · 23 test files · weight 12 · ~90 s
  d4 Security        · 211 files · weight 12·1.2 = 14 · ~50 s (LAST)
  d5 Performance     · 211 files · weight 10 · ~120 s (runs pnpm build)
  d6 Architecture    · 211 files · weight 10·1.3 = 13 · ~50 s
  d7 A11y            · 47 components · weight 10·0.22 = 2.2 · ~30 s
  d8 Dead-code       · 211 files · weight 8 · ~40 s
  d9 Docs            · 23 md files · weight 6 · ~25 s
  d11 i18n           · 47 components · weight 6 · ~25 s
  d12 Deps           · 89 packages · weight 6 · ~80 s (runs pnpm audit)
  d13 Cache          · @tanstack/react-query detected · weight 8 · ~30 s
  d15 Flags          · useFeatureFlag detected · weight 4 · ~20 s

SKIPPED (2):
  d10 CI Health      · skipped: no .github/workflows/ found
  d14 CSS Tokens     · skipped: no tailwind.config.* found

## Estimated wall-time: 8 min (parallel where possible)

## Auto-derived invariants (from CLAUDE.md)
- ✅ All API calls go through src/lib/api.ts
- ✅ OnlyAPI mock-only safety lock
- ✅ DO NOT BUILD: tickets, automations, billing, admin

## Critical-Cap: ON (1 critical → score ≤40)
```

This plan file is your **first deliverable** after Phase 0.7. The user can review it and abort with Ctrl-C before any sub-agent is spawned.

---

# Phase 1 — Seed `_run.json`

```jsonc
{
  "run_id": "<RUN_ID>",
  "schema_version": "3.0",
  "started_at": "<ISO>",
  "scope": "<from $ARGUMENTS>",
  "git": {"branch":"...","head_short":"...","dirty":false,"ahead":0,"behind":0},
  "profile_path": "_profile.yaml",

  "assumptions": [
    "Codebase: <one line from CLAUDE.md/README>",
    "Promise 1: <e.g. mock-only>",
    "Promise 2: <e.g. WCAG AA>",
    "Promise 3: <e.g. exactOptionalPropertyTypes>",
    "Most load-bearing: <e.g. OnlyAPI safety lock>"
  ],

  "tools": {"pnpm":true,"tsc":true,"vitest":true,"gh":true,"rg":true,"jq":true,"ast-grep":false},

  "agents": {
    "d1":{"status":"queued","weight":15,"group":"A"},
    "d2":{"status":"queued","weight":12,"group":"B"},
    "d3":{"status":"queued","weight":12,"group":"B"},
    "d4":{"status":"queued","weight":12,"group":"A"},
    "d5":{"status":"queued","weight":10,"group":"B"},
    "d6":{"status":"queued","weight":10,"group":"A"},
    "d7":{"status":"queued","weight":10,"group":"C"},
    "d8":{"status":"queued","weight":8,"group":"A"},
    "d9":{"status":"queued","weight":6,"group":"A"},
    "d10":{"status":"queued","weight":5,"group":"B"},
    "d11":{"status":"queued","weight":6,"group":"A"},
    "d12":{"status":"queued","weight":6,"group":"B"},
    "d13":{"status":"queued","weight":8,"group":"A"},
    "d14":{"status":"queued","weight":4,"group":"A"},
    "d15":{"status":"queued","weight":4,"group":"A"}
  },

  "files": {
    "src/lib/api.ts": {"loc":10,"size":312,"mods30d":3,"rev":[],"hot":0.0}
  },

  "stats": {"total":0,"reviewed":0,"coverage_pct":0.0},
  "hotspots": [],

  "phase": "dispatching",
  "config": {"coverage_gate":0.99,"stale_min":30,"max_parallel":4,"timeout_s":300},
  "updated_at": "<ISO>"
}
```

The `files` dict carries ONLY: `loc`, `size`, `mods30d`, `rev` (reviewed-by skill-ids), `hot` (hotspot score, computed Phase 3). Per-file findings live in `_findings.jsonl` keyed by `file`.

Build inventory:

```bash
git ls-files -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.py' '*.rs' '*.md' \
  ':!**/node_modules/**' ':!**/dist/**' ':!**/.next/**' \
  ':!audit-reports/**' ':!code-quality-skills/**' ':!**/*.lock'
```

For each file: `loc` via `wc -l`, `size` via `stat -c%s`, `mods30d` via `git log --since=30.days --oneline -- <path> | wc -l`.

---

# Phase 2 — Dispatch sub-agents (ordered: quality first, security last)

**Dispatch order is intentional:** code-quality dimensions run FIRST, security/auth runs LAST. Reasoning:
1. Quality issues found early give context for security review (e.g. an `as any` discovered by D1 may itself be the vector D4 needs to flag).
2. Security findings are the highest-stake outputs — running them last means they go into the report with full context from prior dimensions.
3. If a quality run fails or times out, security still runs (the gate is non-negotiable).

```
GROUP 1 — Quality (parallel, max 4):       d1 d6 d8 d9 d13 d14 d15
GROUP 2 — Types & Tests (sequential):       d2 d3
GROUP 3 — Performance & Bundle (sequential): d5 d10 d12
GROUP 4 — UX & i18n (parallel):              d7 d11
GROUP 5 — Security & Auth (LAST, sequential): d4
```

D4 Security ALWAYS runs last. Even on `--no-tools`, even on PR scope, even on resume. If the orchestrator is interrupted, on resume D4 is queued to run after any unfinished prior groups.

For each skill in a group:

1. Spawn sub-agent with: this file path + skill-id + RUN_DIR.
2. Sub-agent reads `§ Shared contract` + `§ Skill kit:d<N>`. Executes the 4-step contract.
3. Continuously rewrite `_status.txt` every 5 s:

```
[Group 1: quality] d1✅ d6⏳ d8✅ d9✅ d13⏳ d14⌛ d15⌛  3/7 done · cov 47%
[Group 2: types]   d2⌛ d3⌛
[Group 3: perf]    d5⌛ d10⌛ d12⌛
[Group 4: ux]      d7⌛ d11⌛
[Group 5: SEC]     d4⌛  ← runs LAST
```

`✅`done · `⏳`running · `⌛`queued · `❌`failed · `⏰`timeout.

**Why D4 last:** quality findings (D1 type bypasses, D6 layer violations, D13 cache key drift, etc.) often surface attack surfaces that the security pass uses. Running D4 first wastes context; running it last makes its findings the headline of the final REPORT.

## 2.1 Inline coverage sweep (no separate skill)

After all groups complete, the orchestrator performs sweep itself:

```bash
jq -r '.files | to_entries[] | select(.value.rev == []) | .key' "$RUN_DIR/_run.json" \
  | while read F; do
      # Generic per-file pass:
      LOC=$(jq -r --arg f "$F" '.files[$f].loc' "$RUN_DIR/_run.json")
      [ "$LOC" -gt 300 ] && append_finding "$F:1" l "sweep" "god-file" "LOC=$LOC"
      grep -c "useEffect" "$F" 2>/dev/null | awk '$1>5{print "useEffect-count "$1}' \
        | xargs -I{} append_finding "$F:1" l sweep useeffect-count "{}"
      grep -c "as any" "$F" 2>/dev/null | awk '$1>3{print "as-any-density "$1}' \
        | xargs -I{} append_finding "$F:1" m sweep as-any-density "{}"
      # Tag the file as reviewed:
      jq --arg f "$F" '.files[$f].rev += ["sweep"]' "$RUN_DIR/_run.json" > tmp && mv tmp "$RUN_DIR/_run.json"
    done
```

Recompute `stats.coverage_pct = files_with_rev_nonempty / total`. **If <99 %, FAIL** and list unreviewed.

---

# Phase 3 — Aggregate

## 3.1 Counts

```bash
jq -s 'group_by(.sev) | map({(.[0].sev):length}) | add' _findings.jsonl
# → {"c":2,"h":4,"m":3,"l":3}
```

## 3.2 Per-dimension scores + Critical-Cap overall

```bash
jq -s '
  group_by(.dim) | map({
    dim: .[0].dim,
    c: ([.[] | select(.sev=="c")] | length),
    h: ([.[] | select(.sev=="h")] | length),
    m: ([.[] | select(.sev=="m")] | length),
    l: ([.[] | select(.sev=="l")] | length)
  }) | map(. + {score: ([10 - 6*.c - 1.5*.h - 0.5*.m - 0.1*.l, 0] | max)})
' _findings.jsonl
```

Apply Critical-Cap (§ Severity & scoring) to the overall.

## 3.3 Hot-spots (inline in `_run.json`)

```bash
jq '.files |= (
  to_entries
  | map(.value.hot = (
      ((.value.loc + 1) | log) *
      ((.value.mods30d + 1) | log) *
      (.value.rev | length)   # proxy for findings via rev count
  ))
  | from_entries
) | .hotspots = (.files | to_entries | sort_by(-.value.hot) | .[0:10] | map({file:.key, hot:.value.hot}))
'
```

## 3.4 Tag-clustering for fix-prompts

```bash
jq -s 'group_by(.tags[0]) | map({tag:.[0].tags[0], findings: .})' _findings.jsonl
```

One fix prompt per tag-cluster, not per finding. → `fix-prompts.md` 60-80 % shorter.

---

# Phase 4 — Outputs

## 4.1 `REPORT.compact.txt` — AI-friendly, ultra-dense

≤4 KB for 50 findings, no markdown, designed to paste into another agent:

```
Code Quality Audit · 2026-05-01__abc1234 · score 38/100 (capped: 2c) · TDQ 14.3 · cov 100%

DIMENSIONS (score|c/h/m/l)
d1 4/10 0/2/1/0 · d2 5/10 0/1/1/0 · d3 8/10 0/0/0/2 · d4 0/10 2/0/0/0 · d5 6/10 0/0/1/1
d6 10/10 0/0/0/0 · d7 5/10 0/1/0/0 · d8 10/10 0/0/0/0 · d9 10/10 0/0/0/0 · d10 5/10 0/0/0/0
d11 10/10 0/0/0/0 · d12 10/10 0/0/0/0 · d13 10/10 0/0/0/0 · d14 10/10 0/0/0/0 · d15 10/10 0/0/0/0

FINDINGS (id|sev|dim|file:line|rule|msg)
C1|c|d4|src/lib/api.ts:1|hardcoded-secret|API_KEY literal in source
C2|c|d4|src/lib/api.ts:4|eval-sink|eval(code) executes arbitrary input
H1|h|d1|src/components/Button.tsx:7|fire-and-forget|fetch().then() in useEffect
H2|h|d1|src/hooks/useData.ts:9|empty-catch|silent error swallow
H3|h|d2|src/components/Button.tsx:3|any-prop|props: any
H4|h|d7|src/components/Button.tsx:11|div-onclick-no-keyboard|<div onClick> no role/tabIndex
M1|m|d1|src/hooks/useData.ts:12|as-any|return cast to any
M2|m|d5|src/lib/api.ts:8|n+1-map-async|.map(async) without Promise.all
M3|m|d2|tsconfig.json:4|missing-strict-flag|exactOptionalPropertyTypes off
L1|l|d5|package.json:12|unscoped-lodash|full lodash import
L2|l|d3|src/__tests__/util.test.ts:4|test-skip|.skip without explanation
L3|l|d3|src/__tests__/util.test.ts:5|test-todo|.todo placeholder

CITATIONS (compact)
@src/lib/api.ts:1  export const API_KEY = "sk-…"
@src/lib/api.ts:4  return eval(code)
@src/components/Button.tsx:7  fetch("/api/track").then(r=>r.json())
@src/hooks/useData.ts:9  } catch (e) {}
…

HOTSPOTS (file|loc|rev|hot)
src/components/Button.tsx 14 5 1.92
src/lib/api.ts 10 4 1.74
src/hooks/useData.ts 11 4 1.51

INVARIANTS
✅ All API calls go through src/lib/api.ts (verified)
⚠️ No hardcoded secrets — VIOLATED (see C1)

NEXT 3 (by ROI)
1 C1 rotate API_KEY + scrub history (security/30min)
2 H4 replace <div onClick> with <button> (a11y/15min)
3 M2 wrap urls.map(async) in Promise.all (perf/5min)
```

This is the **agent-feed format** — paste into another agent for follow-ups. <1 K tokens, all info preserved.

## 4.2 `REPORT.md` — human markdown

Same content, prettier formatting. ≤1200 lines.

## 4.3 `dashboard.html` — minimal default (≤2 KB)

Self-contained, inline CSS only. Sections: score badge · findings table · hotspots heatmap.

`--with-dashboard=full` adds: trend chart · coverage map · anti-findings.

## 4.4 `fix-prompts.md` — tag-clustered

```markdown
## Cluster: secrets (covers C1)
**Affected:** @src/lib/api.ts:1
**Prompt:**
\```
Fix all hardcoded secrets in this codebase. For each:
1. Replace literal with process.env.<NAME>, validated at startup.
2. Add to .env.example with empty value.
3. Verify .env in .gitignore.
4. Add a regression test that fails if env var missing.

Findings:
- src/lib/api.ts:1 — API_KEY literal "sk-…"
\```

## Cluster: a11y (covers H4)
…
```

## 4.5 `_findings.jsonl` is itself an output

Already incrementally written during Phase 2.

---

# Phase 5 — Close

```bash
jq '.phase="done" | .completed_at="<now>" | .overall=X | .tdq=Y' _run.json > tmp && mv tmp _run.json
```

Final stdout (single line):

```
✅ 2026-05-01__abc1234 · 38/100 (capped: 2c) · TDQ 14.3 · 12 findings · cov 100% · 5 outputs
```

---

# § Skill kit (embedded — substitute `{{PROFILE.*}}` before writing to disk)

Each skill ≈ 30 lines. Same structure for all: frontmatter + `# CHECKS` block. § Shared contract above applies to all.

---

## d1.md — Correctness & Invariants

```markdown
---
description: D1 Correctness. Race, swallowed errors, type bypasses, broken invariants.
weight: 15
group: A
---
# CHECKS
- async hazards:
  - rg -n "\.then\(" {{src}} | grep -v await
  - rg -n "async \([^)]*\) =>\s*\{[^}]*\.map\(" {{src}}
- swallowed errors:
  - rg -n "catch\s*\([^)]*\)\s*\{\s*\}" {{src}}
- type bypasses:
  - rg -n "as any" {{src}}
  - rg -n "// @ts-(expect-error|ignore|nocheck)" {{src}}
- lint bypasses: rg -n "eslint-disable" {{src}}
- project invariants (from PROFILE):
  {{#each PROFILE.invariants}}
  - {{this.name}} → verify: `{{this.verify}}`
  {{/each}}
# TAGS: invariants async types
# CONFIDENCE: grep-based 1.0; "useEffect>5" 0.6
```

## d2.md — Type Safety

```markdown
---
description: D2 Types. tsc, strict flags, any/as-any inventory.
weight: 12
group: B
requires_tools: [tsc]
---
# CHECKS
- run `{{PROFILE.scripts.typecheck}}` → exit + top-20 errors
- check tsconfig: strict, exactOptionalPropertyTypes, noUncheckedIndexedAccess
- rg -n ":\s*any\b" {{src}}
- rg -n "as unknown as" {{src}}
- rg -n "// @ts-" {{src}}
# TAGS: types
# CONFIDENCE: tsc 1.0; explicit any 1.0
```

## d3.md — Tests

```markdown
---
description: D3 Tests. Run suite, .skip/.todo/.only, missing tests for changed modules.
weight: 12
group: B
---
# CHECKS
- run `{{PROFILE.scripts.test}}` → pass/fail/skip counts
- rg -n "\.skip\(|\.todo\(|xit\(|it\.only\(|describe\.only\(|fdescribe\(|fit\(" {{src}}
- modules changed last 50 commits → check sibling *.test.{ts,tsx}
- parse coverage/coverage-summary.json if exists; flag <70 %
# TAGS: tests ci
```

## d4.md — Security

```markdown
---
description: D4 Security. Secrets, sinks, env leaks, gitignore hygiene.
weight: 12
group: A
---
# CHECKS
- rg -n "(API_KEY|SECRET|PASSWORD|TOKEN|BEARER)\s*=\s*['\"][^'\"]{8,}['\"]" {{src}}
- rg -n "\beval\(|new Function\(|innerHTML\s*=|dangerouslySetInnerHTML" {{src}}
- next.js client: rg -n "process\.env\." {{client_src}} → verify NEXT_PUBLIC_*
- gitignore: must cover .env*, *-state, *.pem, audit-reports/
- next.config: check Content-Security-Policy, X-Frame-Options
# TAGS: secrets auth xss injection
# CONFIDENCE: literal regex 1.0; CSP missing 0.9
```

## d5.md — Performance

```markdown
---
description: D5 Performance. Bundle, useEffect, N+1, missing memo.
weight: 10
group: B
requires_tools: [build]
---
# CHECKS
- run `{{PROFILE.scripts.build}}` → First Load JS / route, top-5 heaviest
- rg -n "useEffect\(\s*\(\)\s*=>\s*\{[^}]*\}\s*,\s*\[\s*\]\s*\)" {{src}} (empty deps + side effects)
- rg -n "\.map\(async " {{src}} (N+1 candidates)
- rg -n "<img\s" {{src}} (next/image candidates)
- rg -l "from ['\"]lodash['\"]" {{src}} (unscoped imports)
# TAGS: perf bundle async
```

## d6.md — Architecture

```markdown
---
description: D6 Architecture. God-files, layer flow, circular deps.
weight: 10
group: A
---
# CHECKS
- god-files: components >300 LOC, utils >500 LOC
- layer flow: rg -n "from.*repositories" {{components}} (UI must not import repo internals)
- madge --circular if available
- barrel hygiene: rg -l "^export \* from" {{src}}
- monorepo: rg -n "from ['\"](\.\./){4,}" {{src}}
# TAGS: invariants
```

## d7.md — Accessibility

```markdown
---
description: D7 A11y (WCAG 2.1 AA). div onClick, focus rings, alt, labels, contrast.
weight: 10
group: C
---
# CHECKS
- rg -n "<div[^>]*onClick" {{components}} → check role + tabIndex + onKeyDown
- focus-visible: rg "focus-visible:|outline-" {{ui}}
- alt: rg -n "<img\s" {{src}} + <Image
- form labels: rg -n "<input " {{src}} → htmlFor or aria-label
- contrast: 5 spot-checks bg-* + text-* combos
# TAGS: a11y keyboard contrast
# CONFIDENCE: <div onClick> 0.9; contrast spot-check 0.5
```

## d8.md — Dead code

```markdown
---
description: D8 Dead code. Unused exports, stale TODOs, placeholders.
weight: 8
group: A
---
# CHECKS
- npx ts-prune (if avail) else tsc --noUnusedLocals
- rg -n "TODO|FIXME|HACK|XXX" {{src}} → top 30 by `git blame -L`
- find {{src}} -size -200c (near-empty)
- rg -l "^export \{ \w+ \} from" {{src}} (single-export barrels)
- npx depcheck per package
# TAGS: dead-code
```

## d9.md — Documentation

```markdown
---
description: D9 Docs. README freshness, scope drift, JSDoc on public API.
weight: 6
group: A
---
# CHECKS
- README freshness: git log -1 --format=%cd README.md vs newest src
- CLAUDE.md/AGENTS.md: verify "DO NOT BUILD" dirs really gone
- public API JSDoc: package index.ts, JSDoc above each export
- broken MD links: rg "\]\((\.{0,2}/[^)]+\.md)\)" *.md docs/
# TAGS: docs
```

## d10.md — CI Health

```markdown
---
description: D10 CI Health. Exit codes for typecheck/test/build/lint + GHA status.
weight: 5
group: B
requires_tools: [pnpm, gh]
---
# CHECKS
- run typecheck/test/build/lint → exit + last 5 lines
- gh run list -L 10 -b main --json status,conclusion → success rate
- .github/workflows: must have permissions: block, no @latest pins
# TAGS: ci
```

## d11.md — i18n

```markdown
---
description: D11 i18n. Hardcoded UI strings (only flag if PROFILE.language_policy says so).
weight: 6
group: A
---
# CHECKS
{{#if PROFILE.language_policy.ui_strings == "extracted"}}
- rg -n ">[A-ZÄÖÜ][\p{L} ]{4,}<" {{components}}
- rg -n "(placeholder|title|aria-label)=\"[A-Z][^\"]+\"" {{components}}
{{else}}
- skip flagging — policy ui_strings = "{{PROFILE.language_policy.ui_strings}}", informational only
{{/if}}
- date/number: rg "toLocaleString\(\)" → flag missing locale arg
- if next-intl/react-i18next present: list defined-but-unused keys
# TAGS: i18n
# CONFIDENCE: hardcoded 1.0 ONLY if policy=extract
```

## d12.md — Dependencies

```markdown
---
description: D12 Deps. audit, outdated, duplicates, unused.
weight: 6
group: B
requires_tools: [pnpm]
---
# CHECKS
- pnpm audit --json → critical/high/moderate counts
- pnpm outdated --format json → >1 minor behind
- pnpm why <top-20-pkgs> → multi-version flags
- npx depcheck → unused
- license closure: npx license-checker --json (flag GPL/AGPL/SSPL)
# TAGS: deps secrets
# CONFIDENCE: audit 1.0; "duplicate version" 0.8
```

## d13.md — Cache keys

```markdown
---
description: D13 Cache & data fetching. React-Query keys, invalidations, staleTime drift.
weight: 8
group: A
---
# CHECKS
- rg -n "useQuery\(\{ queryKey:" {{src}} + rg -n "invalidateQueries\(" {{src}}
  → keys must come from a single factory, not inline
- onMutate/onSettled: same key snapshotted vs invalidated?
- rg -n "staleTime:|refetchInterval:|gcTime:" {{src}} → distribution
- prefetch hooks: staleTime matches consumer's useQuery
# TAGS: cache async
```

## d14.md — CSS tokens

```markdown
---
description: D14 CSS / design tokens. Tailwind arbitrary values, hex, dark-mode parity.
weight: 4
group: A
---
# CHECKS
- rg -n "\[#[0-9a-fA-F]{3,8}\]|\[\d+px\]" {{src}}
- rg -n "color:\s*['\"]?#" {{src}}
- repeated className >80 chars in 3+ places
- dark-mode parity: bg-* + text-* without dark:bg-* dark:text-*
# TAGS: a11y contrast
```

## d15.md — Feature flags

```markdown
---
description: D15 Flags. Stale, half-rolled-out, dead branches.
weight: 4
group: A
---
# CHECKS
- find all useFeatureFlag() / getFlag() calls
- per flag: git log -1 → age; flag >90 days
- both `if (flag)` AND `if (!flag)` paths still in code
- merged-but-not-deleted branches >30 days
# TAGS: dead-code
```

---

# § Output formats (embedded summaries)

REPORT.compact.txt format → § Phase 4.1 (verbatim).
REPORT.md → § Phase 4.2.
dashboard.html → § Phase 4.3 (≤2 KB minimal, inline CSS, no JS).
fix-prompts.md → § Phase 4.4 (tag-clustered).

The on-disk `_templates/` folder is regenerated from these on bootstrap.

---

# § Hard rules (apply throughout)

- **Read-only.** Never edit production code.
- **Single source of truth = THIS file.** On-disk skills are derivable cache.
- **Compact citations only.** No multi-line excerpts ever.
- **Critical-Cap is law.** 1 critical → score ≤40. 2 → ≤0.
- **conf < 0.6 = exclude from REPORT.md** (still in `_findings.jsonl`).
- **Tags from fixed vocab only** (§ Tags).
- **Atomic-RW with 3-retry guard** for `_run.json`.
- **Append-only** for `_findings.jsonl`. Never rewrite.
- **Honour PROFILE.invariants, scope_blocklist, language_policy.**
- **Caps**: per-dim ≤200 lines · REPORT.md ≤1200 · REPORT.compact.txt ≤4 KB · dashboard.html ≤2 KB minimal.

---

# § Begin

State in 4 lines max:
1. run-id + scope
2. detected stack + tools available
3. invariants count + kit status (verified|bootstrapped)
4. dispatch plan (group sizes)

Then execute Phase 0 → 5. Final line is the compact summary from Phase 5.
