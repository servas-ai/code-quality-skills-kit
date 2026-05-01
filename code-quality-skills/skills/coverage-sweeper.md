---
description: Coverage sweeper — runs LAST. Walks every source file no other agent touched, runs a generic per-file audit, guarantees 99%+ coverage.
weight: 0
---

You are sub-skill **Coverage Sweeper**. You always run **after** D1..D10 and you exist for one reason: **no source file gets forgotten**.

# Contract

## CLAIM
- Read `audit-reports/<run_id>/_ledger.json`. Append your record with `skill: "coverage-sweeper"`, `status: "claimed"`.
- Read `audit-reports/<run_id>/_file-coverage.json`.

## AUDIT

1. Build the **gap list**: every key in `files` whose `reviewed_by[]` is empty. Sort by `loc` descending (review the largest unseen files first).
2. For each gap file, run a fast generic per-file pass:

   - **First 100 LOC + last 50 LOC** read (`Read` with `limit:100`, then `offset:loc-50`).
   - **Heuristic checks** (no greps — work from the file content directly):
     - File ≥300 LOC for components / ≥500 LOC for utils → flag as god-file.
     - More than 5 `useEffect` in one file → flag.
     - More than 3 `as any` / `as unknown` in one file → flag.
     - Top-of-file lacks any docstring/comment AND filename is non-trivial → low-severity finding.
     - Default export without explicit type → low-severity finding (TS only).
     - File contains `TODO` / `FIXME` from `git blame` >30 days → list.
   - **Tag the file**: append `"coverage-sweeper"` to its `reviewed_by[]`. If you found anything, append a finding to `findings[]`.

3. After the loop, recompute `stats` in `_file-coverage.json`:
   ```
   reviewed_files = count of files with non-empty reviewed_by[]
   coverage_pct   = reviewed_files / total_files * 100
   ```

4. **If coverage_pct < 99 %** after sweeping, list which files still have empty `reviewed_by[]` and mark `status: "failed"` in the ledger with a reason (probably they were excluded by the source-roots glob). Otherwise `status: "done"`.

## REPORT — `coverage-sweeper.md`

```
# Coverage Sweeper — score n/a (gap-filler)

## Files swept (no other agent owned them)
| File | LOC | Findings |

## God-files among swept
…

## Files with TODOs >30 days (from sweep)
…

## Final coverage
- Total source files: T
- Reviewed by D1..D10: R
- Reviewed only by sweeper: S
- Reviewed by both: O
- Coverage: ((R+S) / T * 100) %

## Recommended re-attribution
- Top 5 files that should have been owned by a specialised dimension (and which one).
```

## CHECK OUT

- Update ledger: `status: "done"`, `findings`, `elapsed_ms`, `report_path`.
- Re-write `_file-coverage.json` with final stats.

# Hard rules
- **Read-only.**
- **Never silently widen** the source-roots glob to fake coverage. If files are excluded on purpose, leave them excluded and reach 99 % via reviewed-files-among-included.
- **Never duplicate** a finding already raised by D1..D10 — diff against existing findings before appending.
