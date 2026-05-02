# Migration: CQC v3 → v4 (MCO-backed)

CQC's L1 orchestrator no longer ships its own xargs/tmux fan-out. It now
delegates to **MCO** (`@tt-a1i/mco`), which already handles multi-provider
parallelism, stall detection, retries, and structured findings.

## What changed

| Area                | v3                                | v4                                     |
|---------------------|-----------------------------------|----------------------------------------|
| `bin/cqc-orchestrate` | ~380 LOC, custom shard planner   | ~200 LOC, thin MCO wrapper             |
| `bin/cqc-parallel`  | 325 LOC, parallel xargs runner    | **Removed** (cqc-orchestrate covers it)|
| Fan-out engine      | bash + python plan.json          | `mco review --max-provider-parallelism`|
| Stall handling      | manual `timeout`+kill            | `mco --stall-timeout` (default 240s)   |
| Findings format     | per-shard NDJSON                 | MCO normalised JSON (strict-contract)  |
| Output dir          | `audit-reports/<run>/shards/…`   | `audit-reports/<run>/mco-output/…`     |

## What you must do

1. Install MCO globally (Builder B has done this on the dev box):
   ```
   npm i -g @tt-a1i/mco
   mco doctor --json     # confirm providers ready
   ```
2. (Optional) Rename `cqc.config.yaml` → `cqc-budget.yaml` if you want the
   user-spec name. Both work; orchestrator searches in this order:
   `./cqc-budget.yaml` → `./cqc.config.yaml` → `~/.cqc/budget.json`.
3. Drop any custom `cqc-parallel` scripts/aliases — invoke `cqc-orchestrate`
   instead. The CLI list (`--clis=…`) is gone; provider selection is now
   driven by `caps_pct` and live `mco doctor` readiness.

## Behavioural notes

- **`--divide files` was requested but does not exist in MCO.** MCO fans out
  per-provider (each provider audits the full target set). File-level
  sharding within a provider is delegated to that provider's own context
  budget. We honour the user's "kontrolliert und hospital" rule: the wrapper
  passes `--max-provider-parallelism` (provider-side concurrency) and never
  fabricates a flag MCO does not implement.
- **Cap enforcement.** A provider is excluded if any of:
  `caps_pct[p] == 0`, `mco doctor.providers[p].ready == false`, or
  `~/.cqc/usage.json:.by_cli[p].used_pct >= caps_pct[p]`.
- **Claude is opt-in.** Pass `--include-claude` AND set `caps_pct.claude > 0`.
- **Prefilter exclusion.** If a `prefilter/clean-files.txt` exists (Builder A
  output), those files are subtracted from the scope before MCO runs.
- **Plan-only.** `--plan-only` prints the resolved `mco review …` command
  without executing — useful for CI dry-runs.

## Rollback

`git revert` of the v4 commit restores cqc-parallel and the bash fan-out.
No state migration is needed; audit-reports/ artefacts are append-only.
