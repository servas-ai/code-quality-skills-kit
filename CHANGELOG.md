# Changelog

## v3.3 — Autonomous Audit Plan (30 improvement tips applied)

The orchestrator now does codebase reconnaissance and writes a tailored plan BEFORE dispatching any sub-agent. No manual config required.

### Top 10 high-ROI improvements (shipped in v3.3)

1. **Pre-flight reconnaissance** — file counts per category (components/hooks/tests/config/docs) computed before dispatch
2. **Skip-rules per skill** — d2 skipped if no TS, d7 if no React, d10 if no GHA, d12 if no deps file, d13 if no react-query, d14 if no Tailwind, d15 if no flag-system
3. **Auto-tuned weights** — d6 weight scales with file count; d12 with deps count; d7 with component-ratio; d4 with auth-signals
4. **Wall-time estimate** — `30s + 0.3s/file + tool-startup` per skill, summed over groups
5. **`_audit-plan.md`** — first deliverable; user can abort before any sub-agent runs
6. **Auto-derived invariants** — extracts "DO NOT BUILD" / "Must" / "Promise" bullets from CLAUDE.md / AGENTS.md / README.md
7. **Hot-file priority** — files changed in last 30 d audited FIRST within each skill (catches regressions in active code)
8. **Sample-cap on huge repos** — if >1000 files: top 200 hot-files per skill; rest via sweeper
9. **Status `"skipped"` in ledger** — skipped skills tracked with reason; weight redistributed
10. **Stack signal detection** — HAS_REACT, HAS_TAILWIND, HAS_REACT_QUERY, HAS_PRISMA, HAS_GHA, HAS_TS, HAS_I18N detected via simple greps + file checks

### Tier-2 improvements (queued for v3.4)

11. **Per-skill RAM budget** — auto-narrow file lists if mem usage >2 GB
12. **Smart parallelism** — `max_parallel` auto-tunes from `nproc`
13. **Profile cache** — skip detection if `_profile.yaml` checksum unchanged from last run
14. **Confidence threshold per env** — production: ≥0.8 · sandbox: ≥0.4
15. **WIP-mode relaxation** — HEAD commit message has "wip"/"draft" → relax thresholds
16. **Skip-on-clean** — if last run had 0 findings for skill AND files unchanged → skip (incremental audit)
17. **Extra-skill auto-spawn** — `prisma/schema.prisma` → spawn d-prisma-schema; `*.proto` → d-grpc; `*.tf` → d-terraform
18. **Token budget per agent** — split large file lists across multiple invocations of same skill if >100 files
19. **Per-cluster fix-prompts** — already in v3.0, expand to detect overlapping fixes (e.g. one PR for all `as any` in one file)
20. **Live statusline integration** — write to `~/.claude-code-statusline` for cross-session visibility

### Tier-3 quality-of-life (queued for v3.5)

21. **Trend-vs-baseline auto-mode** — diff this run against `_baseline_link.txt` automatically (no `--against` flag)
22. **Per-workspace dispatch** — monorepo: each workspace gets its own _run.json + parallel runs
23. **Detection of disabled tests** — flag tests in `.skip` for >30 days (vs new ones)
24. **Bundled fix-PRs** — group fix prompts that touch the same file
25. **CI integration mode** — `--ci` outputs only critical+high to stdout, exit 1 if any critical
26. **Pre-commit hook** — installer adds optional `.git/hooks/pre-commit` that runs d4 + d1 only
27. **PR-comment generator** — `gh pr comment <n> --body-file REPORT.compact.txt` one-liner
28. **Webhook on completion** — POST `_findings.jsonl` to a configured URL
29. **VSCode/IDE integration** — `_findings.jsonl` is already JSONL → can be loaded as Code Lens
30. **Multi-repo run** — `cqc audit --repos r1,r2,r3` aggregates a portfolio view

## v3.2 — Universal stack adapters + one-line install

- 8+ stack auto-detection (TS/JS/Python/Rust/Go/Java/Ruby/Elixir + polyglot)
- `install.sh` — one-line bootstrap with stack detection
- `cqc.config.example.yaml` — optional override schema
- README v3.2 with marketplace-grade landing page

## v3.1 — Dispatch order: quality first, security last

- Code-quality runs in 4 groups, security (d4) ALWAYS runs last
- Reasoning: quality findings provide context; security as headline finding

## v3.0 — AI-friendly compact format + Top-5 simplifications

- Single `_run.json` (state + agents + files + hotspots in one document)
- Findings as JSONL (append-only, parallel-safe)
- On-disk skills become derivable-cache pointers
- Coverage-sweeper inlined into orchestrator (no separate skill file)
- Critical-Cap scoring: 1 critical → score ≤40
- Confidence field per finding (0..1)
- Compact citation format `@file:line  excerpt` (≤72 chars)
- REPORT.compact.txt: ultra-dense AI-feed format (~2.5 KB / 50 findings)
- `_profile.yaml` (human-editable) replaces `_profile.json`
- Tag-clustered fix-prompts (60-80 % shorter)
- Tags fixed to 20-vocab list

## v2.0 — Initial multi-agent kit

- 16 sub-skills (D1..D15 + coverage-sweeper)
- 6 output templates
- Self-bootstrapping master prompt
- Dashboard.html + REPORT.md + fix-prompts.md
