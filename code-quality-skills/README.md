# code-quality-skills/ — Multi-Agent Audit Kit

A downloadable, drop-in skills kit for running rigorous, file-by-file code-quality audits with multiple Claude Code sub-agents that **coordinate via a JSON ledger**.

Inspired by:
- [Anthropic skills marketplace](https://github.com/anthropics/skills) — folder convention.
- [codeprobe / multi-agent code review skill](https://dev.to/nishilbhave/i-built-a-multi-agent-code-review-skill-for-claude-code-heres-how-it-works-366i) — orchestrator + parallel sub-skills.
- [Trail of Bits skills](https://github.com/trailofbits/skills) — `plugins/` per-domain layout.
- [skills.sh](https://skills.sh) — open skill ecosystem (v2026.01).
- Multi-agent audit ledger patterns — hash-linked checkin entries, 99 %+ coverage target.

---

## Folder layout

```
code-quality-skills/
├── README.md               ← you are here
├── orchestrator.md         ← master prompt — routes work to sub-skills
├── ledger-schema.md        ← JSON schema for the run-ledger and file-coverage matrix
├── _templates/
│   ├── ledger.template.json
│   ├── file-coverage.template.json
│   └── report.template.md
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
    └── coverage-sweeper.md  ← guarantees every source file is reviewed at least once
```

Outputs land at:

```
audit-reports/
└── <YYYY-MM-DD>__<short-sha>/
    ├── _ledger.json            ← run state — agents check in / out here
    ├── _file-coverage.json     ← file-by-file matrix — “has every file been seen?”
    ├── d1-correctness.md       ← per-dimension finding reports
    ├── d2-types.md
    ├── …
    ├── coverage-sweeper.md     ← gap-filler report (files no other agent touched)
    └── REPORT.md               ← rolled-up summary, written last by the orchestrator
```

`audit-reports/` is meant to be **gitignored by default** (add to `.gitignore`); copy individual reports into PRs as needed.

---

## How agents coordinate

1. **Orchestrator** opens (or creates) the run folder under `audit-reports/<date>__<sha>/`, seeds `_ledger.json` and `_file-coverage.json`, then dispatches sub-skills (in parallel where independent — see `parallel-first.md`).
2. **Each sub-skill** does a 4-step contract:
   - **CLAIM** — atomically mark its dimension `status: "in_progress"`, list which files it intends to inspect.
   - **AUDIT** — run greps, type-checks, builds, etc. Every file it reads MUST be appended to its `files_reviewed[]` array in `_file-coverage.json`.
   - **REPORT** — write `audit-reports/<run>/<dimension>.md` using `_templates/report.template.md`.
   - **CHECK OUT** — flip ledger entry to `status: "done"`, attach finding counts (critical/high/medium/low), elapsed time, and the relative report path.
3. **Coverage sweeper** runs LAST: walks the source tree, diffs against `_file-coverage.json`, and audits every file no other agent touched (catches god-files no specialised dimension owned).
4. **Orchestrator** validates: all ledger entries are `done`, coverage ≥ 99 %, then writes `REPORT.md` (the rolled-up TL;DR + scoring rubric) and prints a one-line summary to the user.

A finding is only valid if it traces back to a real `file:line` reference recorded in `_file-coverage.json`. No phantom citations.

---

## Quick-start (project-level)

```bash
# 1. Drop this folder into the repo root (already there if you cloned ReplyManager).
# 2. Add to .gitignore (once):
echo "audit-reports/" >> .gitignore

# 3. Run the orchestrator from a Claude Code session:
#    /code-quality-checker            ← whole repo
#    /code-quality-checker src/foo    ← scope to a path
#    /code-quality-checker #49        ← scope to PR #49
```

The slash-command at repo root (`code-quality-checker.md`) is a thin wrapper that loads `orchestrator.md`. You can also paste `orchestrator.md` directly into any agent session.

---

## Why a JSON ledger instead of just markdown?

- **Resumability** — if a sub-agent crashes, the next one re-reads `_ledger.json` and only does what's missing.
- **Coverage proof** — `_file-coverage.json` is the source of truth for "has every file been audited?". Without it, agents drift.
- **Parallel safety** — the orchestrator can fan out 4 sub-skills knowing each will claim a different dimension.
- **Compliance shape** — matches the 99 %-coverage / hash-linked-entry patterns from FlowX / OpenTelemetry-style audit tooling, scaled down to a repo-local file.

See `ledger-schema.md` for the full schema.
