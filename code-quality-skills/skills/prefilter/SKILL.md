---
description: L0 static-analysis pre-filter. Runs Semgrep + ast-grep + Knip + jscpd in parallel and produces clean-files.txt for the LLM layer to skip.
weight: pre-llm
---

# prefilter — L0 deterministic gate

The pre-filter runs four off-the-shelf static analyzers in parallel against a
repo and emits machine-readable findings. Files with **zero findings across
all four tools** are written to `clean-files.txt` so the downstream LLM layer
(`cqc-orchestrate`) can skip them entirely.

All detection logic is delegated to the upstream tools — this script is glue
only.

## Run

```bash
bin/cqc-prefilter --repo /path/to/repo --out audit-reports/<run-id>/prefilter
```

Add `--config cqc-prefilter.config.yaml` to override defaults, or `--force`
to re-run (default behaviour is idempotent: skips tools whose output already
exists).

## Tools

| Tool      | Install                                  | Output           | Skipped if missing |
|-----------|------------------------------------------|------------------|--------------------|
| Semgrep   | `pip install semgrep`                    | `semgrep.sarif`  | `semgrep.skipped.json` |
| ast-grep  | `cargo install ast-grep --locked`        | `astgrep.json`   | `astgrep.skipped.json` |
| Knip      | auto via `npx -y knip` (no install)      | `knip.json`      | `knip.skipped.json`    |
| jscpd     | auto via `npx -y jscpd` (no install)     | `jscpd.json`     | `jscpd.skipped.json`   |

Missing tools are warned-and-skipped — the script never aborts on tool absence
(per `--no-install-prompts` policy).

## Outputs

```
<out>/
  semgrep.sarif | semgrep.skipped.json
  astgrep.json  | astgrep.skipped.json
  knip.json     | knip.skipped.json
  jscpd.json    | jscpd.skipped.json
  clean-files.txt   # paths the LLM layer can safely skip
  summary.md        # human-readable: LOC, dup count, dead exports, hotspots
  _meta.json        # tool versions, durations, repo path, exit codes
```

## How `clean-files.txt` is computed

1. Walk `git ls-files` (or `find` fallback) for source files in TS/JS/Py/Rs/Go.
2. Union the set of files mentioned in any tool's findings → `dirty`.
3. `clean = ALL \ dirty` (set difference).

## Idempotency

Re-running the same `--out` dir is a no-op for tools whose output is already
present. Pass `--force` to redo a single tool: delete the relevant
`<tool>.json` / `<tool>.skipped.json` before re-running.

## Wiring into cqc-orchestrate

`cqc-orchestrate` reads `<out>/clean-files.txt` and excludes those paths from
the file-shard plan, cutting LLM token cost roughly in proportion to the
clean-file ratio.
