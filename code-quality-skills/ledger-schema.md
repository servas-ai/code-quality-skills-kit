# Ledger Schema

Two JSON files live in every run folder. Sub-skills read & update both atomically (read-modify-write with a small staleness check on `updated_at`).

---

## `_ledger.json` — run state

```jsonc
{
  "run_id": "2026-05-01__abc1234",          // <YYYY-MM-DD>__<git-short-sha>
  "started_at": "2026-05-01T08:30:00Z",
  "scope": "whole repo" | "src/foo" | "PR #49",
  "git": {
    "branch": "main",
    "head_sha": "abc1234567",
    "dirty": false
  },
  "tools_available": {
    "tsc": true, "vitest": true, "eslint": false,
    "ts-prune": false, "axe-core": false, "gh": true
  },
  "agents": [
    {
      "id": "d1-correctness@2026-05-01T08:31:02Z",
      "skill": "d1-correctness",
      "status": "claimed" | "in_progress" | "done" | "failed",
      "claimed_at": "2026-05-01T08:31:02Z",
      "completed_at": null,
      "intends_to_read": ["artifacts/creator-chat/src/**/*.{ts,tsx}"],
      "report_path": "audit-reports/2026-05-01__abc1234/d1-correctness.md",
      "findings": { "critical": 0, "high": 0, "medium": 0, "low": 0 },
      "elapsed_ms": null,
      "notes": ""
    }
  ],
  "phase": "dispatching" | "auditing" | "sweeping" | "summarising" | "done",
  "updated_at": "2026-05-01T08:31:02Z"
}
```

Status transitions a sub-skill MUST follow:

```
(missing) → claimed → in_progress → done
                                  ↘ failed   (with `notes` explaining why)
```

Never delete an entry. Append a new agent record if a dimension needs a re-run (use `id` suffix `@<retry-ts>`).

---

## `_file-coverage.json` — file-by-file matrix

```jsonc
{
  "run_id": "2026-05-01__abc1234",
  "source_roots": [
    "artifacts/creator-chat/src",
    "artifacts/api-server/src",
    "lib/db/src"
  ],
  "files": {
    "artifacts/creator-chat/src/components/browser-layout.tsx": {
      "size_bytes": 2104,
      "loc": 67,
      "reviewed_by": ["d1-correctness", "d6-architecture"],
      "findings": [
        { "agent": "d1-correctness", "line": 26, "severity": "low",
          "rule": "module-load-side-effect",
          "msg": "synchronous hydrate runs at import time — document why" }
      ]
    },
    "…": {}
  },
  "stats": {
    "total_files": 142,
    "reviewed_files": 0,
    "coverage_pct": 0.0
  },
  "updated_at": "2026-05-01T08:30:00Z"
}
```

### Coverage rules

- A file counts as **reviewed** when at least **one** sub-skill appends its name to `reviewed_by`.
- The **coverage-sweeper** skill runs last and processes any file with empty `reviewed_by`. It guarantees `coverage_pct ≥ 99 %` at run end.
- The orchestrator FAILS the run with a clear error if `coverage_pct < 99` after the sweeper.

### File seeding

The orchestrator seeds `files` on run start with one entry per file matched by:

```bash
git ls-files -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.py' '*.rs' '*.md' \
  ':!**/node_modules/**' ':!**/dist/**' ':!**/.next/**' \
  ':!audit-reports/**' ':!code-quality-skills/**'
```

Tune the glob list per project; this kit ships with TS/JS/Py/Rs defaults.

---

## Atomic update protocol

Sub-skills coexist on disk, not in shared memory. To avoid clobbering each other:

1. **Read** the file (`Read` tool).
2. **Modify** in memory.
3. **Write** back (`Write` tool).
4. **Re-read** and verify your update is present. If not (another agent wrote between steps 1 and 3), re-merge and retry. Cap at 3 retries; otherwise log to ledger `notes` and proceed.

For ReplyManager's typical scale (≤200 files, ≤10 dimensions), naive read-modify-write is sufficient. For larger repos, switch to one ledger fragment per skill (`_ledger.d1.json`, …) and let the orchestrator merge them — the schema is identical.

---

## Why this shape

- **Hash-linked-ish** — every entry carries a UTC ISO timestamp + skill id. Tampering shows up as a missing transition.
- **Resumable** — re-running the orchestrator finds existing in-progress claims and either resumes them or marks them `failed` (after a 30-min stale window) and re-dispatches.
- **Auditable** — the user can `cat _ledger.json | jq '.agents[] | {skill, status, findings}'` to see at-a-glance what each agent did.
