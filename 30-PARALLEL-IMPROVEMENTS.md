# 30 Parallel-Mode Improvements (v3.13+)

After v3.12 (cqc-parallel + permission-bypass for all CLIs), here are 30 high-ROI improvements grouped by theme.

## Theme A — Crash-Recovery & Watchdog (10)

1. **Heartbeat file per agent** — each CLI writes `<run>/_logs/<cli>.heartbeat` every 10 s. Watchdog kills if stale >60 s.
2. **Resume-from-state** — failed agent's last `_findings.jsonl` line is the resume anchor. Next agent picks up with "skip first N findings".
3. **Partial-commit on SIGTERM** — `trap` writes whatever findings the agent has so far before exit, even if <1.
4. **Detection signals** — match stderr for `429`, `RESOURCE_EXHAUSTED`, `connection refused`, `ECONNRESET`, `OOM` → auto-redispatch.
5. **Per-CLI retry budget** — each agent gets max 2 retries before being marked dead. Tracked in `_run.json:agents.<cli>.retry_count`.
6. **Skill-redistribution on dead CLI** — if claude crashes, its skills (d4 d6 d13) re-assigned to next-best living CLI (gemini for d6, codex for d4 etc.).
7. **Crash report** — separate `_crashes.jsonl` with timestamp + cli + exit_code + last_50_lines_stderr.
8. **Auto-bisect on parse-error** — if Gemini returns malformed JSON, retry with smaller prompt (drop last 5 files).
9. **Pause-resume via signal** — `kill -USR1 <pid>` saves state + exits cleanly. `cqc-parallel --resume <run-id>` continues.
10. **Health-check pre-flight** — 1-token ping per CLI before spawning the heavy audit job. Skip dead-on-arrival CLIs.

## Theme B — Parallelism & Coordination (10)

11. **Lock-free findings append** — use `O_APPEND` write-mode (atomic for ≤PIPE_BUF lines). Currently relies on shell `>>` which IS atomic but not documented.
12. **Skill-level parallelism within a CLI** — each CLI spawns 3-5 sub-tasks in parallel (e.g. claude does d4+d6+d13 in parallel via Task tool, not sequentially).
13. **Cross-CLI work-stealing** — if claude finishes early, it picks up unfinished gemini skills.
14. **Parallel cap** — `--max-parallel=4` limits concurrent CLI count. Prevents OOM on small machines.
15. **Token-quota partition** — split max-token-budget proportional to skill weight: claude (15+10+8=33) gets 33% of budget.
16. **Agent priority** — d4 security spawns FIRST, d14 css-tokens LAST. Within-CLI ordering respects that.
17. **Skill DAG** — d10 (CI health) needs d2 (typecheck) results. Express as YAML dependency graph; runner topo-sorts.
18. **Cooperative scheduling** — when agent A finds a critical, agent B's runtime budget shrinks to "just verify".
19. **Max-cost guard** — if total spend hits `--max-cost=$5`, all running agents receive SIGTERM gracefully.
20. **Fan-in barrier** — orchestrator waits with `wait -n` (race-free) instead of polling `kill -0` in a loop.

## Theme C — Output & Observability (10)

21. **Live progress bar per agent** — replace polling-print with `tput sc/rc` overwrite-in-place. ASCII spinner per CLI.
22. **Cost meter** — `_run.json:agents.<cli>.cost_usd` updated from ccusage real-time.
23. **Findings dedup across CLIs** — if claude reports `eval-sink at api.ts:4` AND gemini also does, dedupe (keep highest conf).
24. **Findings cross-validate** — only emit a finding if 2+ CLIs agree on it (high-confidence mode `--consensus`).
25. **Per-CLI bias detection** — track "which CLI flagged most false-positives historically" → adjust trust score.
26. **Cumulative cost dashboard** — `cqc-ui` shows running spend per CLI in real-time.
27. **Audit replay** — `cqc replay <run-id>` re-runs only the agents that crashed/timed-out, reusing successful agents' findings.
28. **Finding hash** — each finding gets `sha256(file:line:rule)` to detect duplicates across runs.
29. **Diff vs baseline** — `cqc-parallel --against=<run-id>` only reports findings new since baseline.
30. **Streaming JSONL to stdout** — pipe-friendly: `cqc-parallel | jq 'select(.sev=="c")'` lets you grep findings live as they emerge.

## Top-5 v3.13 quick wins

1. **#10** Health-check pre-flight (5 min) — saves wasted timeouts on dead CLIs
2. **#9** Pause-resume via signal (10 min) — most-asked-for feature
3. **#23** Findings dedup across CLIs (15 min) — reduces noise dramatically
4. **#21** Live progress bar overwrite-in-place (20 min) — cleaner UX
5. **#11** Atomic O_APPEND write (5 min) — one-line fix, makes parallelism truly safe

## What v3.12 already ships

✅ All 4 CLIs spawn in parallel (background `&` + `wait`)
✅ Permission-bypass flag per CLI (claude `--dangerously-skip-permissions`, gemini `--yolo`, codex `--dangerously-bypass-approvals-and-sandbox`, opencode `--dangerously-skip-permissions`)
✅ Per-agent timeout (`timeout --kill-after=10 $TIMEOUT`)
✅ Crash detection via exit-code (124=timeout, ≠0=crash)
✅ Partial findings preserved (each agent appends to shared `_findings.jsonl` while alive)
✅ Skill assignment: claude→d4d6d13 · gemini→d12d8d9 · opencode→d1d3d11d14d15 · codex→d2d5d7d10
✅ ID prefixing per CLI (`claude-C1`, `gemini-H1`) — collision-free
✅ Retry-suggestion message: `cqc-parallel --clis=<failed> $SCOPE`
✅ Live status output every 10 s with ✓/⏳/❌/⏰ symbols
✅ `_run.json` records final status per agent (done/timeout/failed/unknown)
