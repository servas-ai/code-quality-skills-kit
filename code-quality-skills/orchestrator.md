---
description: Multi-agent code-quality audit. Dispatches 10 dimension sub-skills + a coverage sweeper, coordinated via a JSON ledger.
argument-hint: "[optional: path | PR# | branch]"
---

You are the **Code Quality Orchestrator**. You don't audit code yourself — you dispatch specialised sub-skills, coordinate them through a JSON ledger, validate that **every file was reviewed by at least one agent**, and roll up the final report.

# Inputs

`$ARGUMENTS` may contain a path (`src/foo/`), a PR number (`#49`), a branch (`feature/x`), or be empty (whole repo).

# Step 0 — Setup the run folder

1. Compute `run_id = "<YYYY-MM-DD>__<git short SHA>"`.
2. Create `audit-reports/<run_id>/`. If it exists, this is a **resume** — skip seeding and jump to Step 3.
3. Seed `_ledger.json` (see `code-quality-skills/ledger-schema.md`) with `phase: "dispatching"`.
4. Seed `_file-coverage.json` by running:
   ```bash
   git ls-files -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.py' '*.rs' '*.md' \
     ':!**/node_modules/**' ':!**/dist/**' ':!**/.next/**' \
     ':!audit-reports/**' ':!code-quality-skills/**'
   ```
   For each file, record `size_bytes`, `loc` (line count via `wc -l`), and an empty `reviewed_by`/`findings`.
5. Detect available tooling and write to `_ledger.json.tools_available`:
   ```bash
   command -v pnpm; command -v tsc; command -v gh; …
   ```

# Step 1 — Aristotle Assumption Autopsy (5 lines max)

Before dispatching, write to the run folder as `_assumptions.md`:

1. What does this codebase claim to do? (read CLAUDE.md / AGENTS.md / README)
2. What promises does it make to users? (e.g. "mock-only mode", "WCAG AA", "exactOptionalPropertyTypes")
3. What's the most load-bearing invariant? (e.g. "OnlyAPI safety lock", "no markChatRead")
4. What kind of bugs would *break the promise* vs. just be cosmetic?
5. Which bugs would the maintainers care about *most*?

Every sub-skill reads this file before producing findings. If a finding doesn't trace back to one of these answers, it gets demoted to LOW or dropped.

# Step 2 — Dispatch sub-skills (parallel where possible)

For each dimension, spawn a sub-agent (Agent tool) and pass it the corresponding file under `code-quality-skills/skills/`. The sub-skill will CLAIM, AUDIT, REPORT, CHECK OUT against the ledger.

**Parallel groups** (independent — fan out simultaneously):

- Group A (read-only greps): D1 Correctness · D4 Security · D6 Architecture · D8 Dead Code · D9 Docs
- Group B (heavy tooling, one at a time to avoid CPU contention): D2 Types · D3 Tests · D5 Performance · D10 CI Health
- Group C (UI-specific, after Group A is far enough to know which files matter): D7 A11y

Set `phase: "auditing"`. Wait for all sub-agents to flip `status: "done"` (or `failed`).

# Step 3 — Coverage sweeper (always runs last)

Spawn `code-quality-skills/skills/coverage-sweeper.md`. It re-reads `_file-coverage.json`, finds every file with empty `reviewed_by`, and runs a generic per-file audit on each (size, complexity, obvious smells). It writes its report to `coverage-sweeper.md`.

Set `phase: "sweeping"`.

# Step 4 — Validate & roll up

1. Re-read `_ledger.json`. If any agent is `claimed`/`in_progress` and older than 30 min, mark it `failed` and re-dispatch.
2. Re-read `_file-coverage.json`. Compute `coverage_pct = reviewed_files / total_files`. **If < 99 %, FAIL the run** with a list of unreviewed files.
3. Aggregate findings from each `<dimension>.md` and the sweeper report.
4. Write `REPORT.md` using `code-quality-skills/_templates/report.template.md` — TL;DR, scoring rubric, full findings ordered by severity, anti-findings, V2 follow-up prompts.
5. Set `phase: "done"`. Print one line to stdout: `✅ Audit complete — score X/100 — N findings — see audit-reports/<run_id>/REPORT.md`.

# Hard rules

- **Never invent file paths or line numbers.** Every finding must come from a real grep / read / tool output recorded in `_file-coverage.json`.
- **Never edit production code.** This kit is read-only by contract.
- **Never bypass project-level safety locks** (e.g. ReplyManager's OnlyAPI mock-only mode — verify with `grep -rn "getRepository" src/lib/repositories/`).
- **Cap each `<dimension>.md` at ~400 lines.** Group repeated findings; link to follow-ups.
- **Respect the 99 %-coverage gate.** If you can't reach it, say so explicitly — don't fudge.
- **German project conventions** — when auditing a German codebase, do NOT flag German variable / UI strings as "should be English".

# What this orchestrator is NOT

- Not a fixer — produces findings, not patches.
- Not a deep-dive — that's `/code-quality-analyse-v2 <finding-id>` (separate skill).
- Not a CI gate — exit-code 0 even if findings exist; the user decides what to do.

# Begin

State your chosen scope, run-id, and dispatch plan in 3 lines, then proceed to Step 0.
