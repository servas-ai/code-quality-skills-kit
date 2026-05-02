# CQC L3 Auto-Fix Flow

L3 closes the loop: **measure → dispatch → validate → PR** — with hard gates so
no untested change reaches `main`.

## Pipeline

```
   ┌─────────────────────────────────────────────────────────────┐
   │  1. cqc-score  --label before                                │
   │     cloc / jscpd / ts-complex / knip   ──►  before.json      │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  2. cqc-orchestrate  (existing L1/L2)                        │
   │     fan-out across CLIs, write findings.jsonl                │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  3. cqc-score  --label after                                 │
   │     cqc-score  --diff before after  ──►  score-delta.json    │
   │     exits 1 on regression (LOC/dup/complexity/dead-exports)  │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  4. cqc-autofix  --findings prefilter/jscpd.json             │
   │      a) pick top-N duplicate clusters (≥ min_duplicate_lines)│
   │      b) for each cluster:                                    │
   │         - git worktree add  (isolation, never edits main)    │
   │         - mco run with refactor prompt                       │
   │         - HARD GATES: typecheck && lint && test              │
   │         - if any gate fails → cleanup, NO PR                 │
   │         - if all pass → push + gh pr create                  │
   └─────────────────────────────────────────────────────────────┘
```

## Safety contract

| Guarantee                                | Enforced by                           |
|------------------------------------------|---------------------------------------|
| Main checkout is never modified          | `git worktree add` per unit            |
| Failing typecheck blocks the PR          | `run_gate typecheck` returns 1         |
| Failing lint blocks the PR               | `run_gate lint` returns 1              |
| Failing tests block the PR               | `run_gate test` returns 1              |
| Worktree is removed on every code path   | `cleanup_worktree` after each unit     |
| Branches are deleted on cleanup          | `git branch -D` in `cleanup_worktree`  |
| LOC regression aborts the loop           | `cqc-score --diff` exits 1             |
| Bash is hardened                         | `set -euo pipefail; umask 077`         |
| Tool delegation only — no homegrown KPI  | cloc / jscpd / ts-complex / knip       |
| Dry-run mode for validation              | `--dry-run` prints intent, no spawn    |
| Caps PR count                            | `--max-prs N` (default 3)              |

## Configuration

`cqc-score.config.yaml` — KPI thresholds (LOC %, dup, complexity, dead).
`mco doctor` — verify provider auth before running autofix.

## Failure modes

- **mco run produces no diff** → unit skipped, worktree cleaned, no PR.
- **Gate fails** → unit skipped, worktree cleaned, no PR, log saved at
  `<wt>/.gate-<name>.log` for diagnosis.
- **gh CLI missing** → branch pushed, PR step is skipped with a warning.
- **No actionable duplicates** → autofix exits 0 with a notice.
