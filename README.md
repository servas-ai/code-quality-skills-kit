# code-quality-skills-kit

Self-bootstrapping multi-agent code-quality audit kit for Claude Code. **Universal — works on any codebase.**

> One prompt. Any language (TS / Python / Rust / Go / Java / Ruby / Elixir / polyglot). 15 audit dimensions running in parallel via sub-agents. Token-optimised compact output. Single source of truth.

## One-line install

```bash
curl -sSL https://raw.githubusercontent.com/servas-ai/code-quality-skills-kit/main/install.sh | sh
```

Or manual:

```bash
git clone --depth 1 https://github.com/servas-ai/code-quality-skills-kit /tmp/cqsk
cp /tmp/cqsk/code-quality-checker.md ./
cp -r /tmp/cqsk/code-quality-skills ./
echo "audit-reports/" >> .gitignore
```

Then in Claude Code:

```
/code-quality-checker            # whole repo
/code-quality-checker src/foo    # scope to a path
/code-quality-checker '#42'      # PR audit
/code-quality-checker --no-tools # greps only, skip typecheck/test/build
```

## What you get

- **15 dimensions** — D1 Correctness · D2 Types · D3 Tests · D4 Security · D5 Performance · D6 Architecture · D7 A11y · D8 Dead Code · D9 Docs · D10 CI Health · D11 i18n · D12 Deps · D13 Cache · D14 CSS Tokens · D15 Feature Flags
- **Parallel sub-agents** in 5 ordered groups (quality first, security last)
- **Token-efficient compact format** — `@file:line  excerpt` (≤72 chars per citation), JSONL findings (~200 bytes/finding)
- **Critical-Cap scoring** — 1 critical → score ≤40 (no security-by-bargaining)
- **Single source of truth** — `_run.json` (state) + `_findings.jsonl` (append-only) — parallel-safe, resumable
- **AI-feed output** — `REPORT.compact.txt` ≤4 KB for 50 findings, paste-able into any other agent
- **Coverage gate** — ≥99 % file coverage enforced; inline sweeper catches unowned files
- **Universal stack adapter** — auto-detects toolchain (8+ stacks); `cqc.config.yaml` for explicit override

## Run output

```
audit-reports/<YYYY-MM-DD>__<short-sha>/
├── _run.json              ← state · agents · files · stats · hotspots
├── _findings.jsonl        ← append-only NDJSON (one finding per line)
├── _profile.yaml          ← detected stack + invariants
├── _status.txt            ← live status (rewritten every 5 s)
├── d1.md … d15.md         ← per-dimension reports (≤200 lines each)
├── REPORT.md              ← human markdown
├── REPORT.compact.txt     ← AI-feed format (~2.5 KB / 50 findings)
├── dashboard.html         ← one-page HTML, no JS, ≤2 KB minimal
└── fix-prompts.md         ← tag-clustered paste-able fix prompts
```

## How it stays simple

- **One file is the single source of truth** — `code-quality-checker.md` at the repo root contains everything: orchestrator workflow, shared sub-skill contract, all 15 skill templates, output formats. The on-disk `code-quality-skills/` folder is a derivable cache regenerated on every run.
- **Two coordination files only** — `_run.json` (atomic read/modify/write with 3-retry guard) + `_findings.jsonl` (append-only, parallel-safe).
- **15 sub-skills, one shared contract** — every sub-agent does CLAIM → AUDIT → REPORT → CHECK OUT against the same two files.
- **No external dependencies** — works with bash + jq + rg + git.

## Dispatch order (intentional)

```
GROUP 1 — Quality (parallel):       d1 d6 d8 d9 d13 d14 d15   ← FIRST
GROUP 2 — Types & Tests (sequential): d2 d3
GROUP 3 — Performance (sequential):   d5 d10 d12
GROUP 4 — UX & i18n (parallel):       d7 d11
GROUP 5 — Security (sequential):      d4                      ← LAST
```

Code-quality runs first to give context. Security runs last so its findings headline the report.

## Universal stack adapter (auto-detect)

| Detected | Typecheck | Test | Build | Lint |
|----------|-----------|------|-------|------|
| `package.json` + pnpm | `pnpm typecheck` | `pnpm test --run` | `pnpm build` | `pnpm lint` |
| `package.json` (npm/yarn) | `npx tsc --noEmit` | `npm test` | `npm run build` | `npx eslint .` |
| `pyproject.toml` | `mypy .` | `pytest` | `python -m build` | `ruff check .` |
| `Cargo.toml` | `cargo check` | `cargo test` | `cargo build --release` | `cargo clippy` |
| `go.mod` | `go vet ./...` | `go test ./...` | `go build ./...` | `golangci-lint run` |
| `pom.xml` / `build.gradle` | `mvn compile` / `gradle compileJava` | `mvn test` / `gradle test` | `mvn package` | `mvn checkstyle:check` |
| `Gemfile` | `bundle exec srb tc` | `bundle exec rspec` | — | `bundle exec rubocop` |
| `mix.exs` | `mix compile --warnings-as-errors` | `mix test` | `mix release` | `mix credo` |

Polyglot repos: all detected stacks run; results aggregate.

## Customise per project (optional)

Drop `cqc.config.yaml` in repo root. See `cqc.config.example.yaml` for the schema.

```yaml
language_policy:
  ui_strings: de        # preserve German UI strings
invariants:
  - name: All API calls go through src/lib/api.ts
    verify: rg "fetch\\(" src/ | grep -v "src/lib/api.ts"
scope_blocklist: [billing, admin]
```

## Inspirations (skills.sh + community)

- [skills.sh](https://skills.sh) — open agent skills marketplace (Vercel, 2026)
- [Anthropic skills](https://github.com/anthropics/skills) — frontmatter convention
- [Trail of Bits skills](https://github.com/trailofbits/skills) — security-domain skill folder layout
- [codeprobe](https://dev.to/nishilbhave/i-built-a-multi-agent-code-review-skill-for-claude-code-heres-how-it-works-366i) — multi-agent orchestrator with per-skill reports
- [code-health-check](https://skillsmp.com/skills/sotayamashita-tauri-acp-kit-claude-skills-code-health-check-skill-md) — universal SKILL.md format
- [Code Auditor (Grade A)](https://www.skillsdirectory.com/skills/mhattingpete-code-auditor) — 6-dimension rubric
- [FlowX audit-completeness](https://www.flowx.ai/ai-agents/audit-trail-completeness-verifier) + [auditable agentic AI (ACM 2025)](https://dl.acm.org/doi/10.1145/3759355.3759356) — 99 %-coverage / hash-linked entry patterns

## Status

v3.2 · End-to-end tested against a real Next.js codebase (211 files, 3 parallel sub-agents, all findings traced to real `file:line` citations, Critical-Cap scoring verified).

## License

MIT — see `LICENSE`.
