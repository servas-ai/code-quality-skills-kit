# 40 — Simplification Research (post-v3.15)

3 parallel research agents surveyed OSS replacements for the homegrown
Bash + Python stack. Goal: keep the quality, drop boilerplate.

## TL;DR — the 3 highest-leverage moves

| Layer | Today (v3.15) | Replace with | LOC Δ | Risk |
|---|---|---|---|---|
| **Subprocess fan-out + watchdog** | Bash `&` + `kill -0` poll loop in `cqc-orchestrate` | **`pueue`** (single binary, persistent queue, parallelism cap, JSON status) | −150 | Low |
| **Multi-CLI live tail** | Custom log dir + `_findings.jsonl` aggregator | **`mprocs`** (TUI multiplexer, KDL/YAML config) | −80 | Low |
| **Dashboard JS** | 150 LOC vanilla JS for poll + DOM-patch | **htmx + SSE-fragments** (one CDN script-tag) | −150 | Very low |

Conservative target: **−380 LOC across the kit** while gaining: persistent queue
(survives SSH disconnect), per-shard scrollback in TUI, push-not-poll dashboard.

---

## Theme A — Job runner / subprocess supervision

Top picks from agent #1 (15+ tools surveyed):

| # | Tool | Why pick it |
|---|---|---|
| 1 | **pueue** | Persistent queue, parallel groups, `pueue add --group codex`, JSON status — replaces our spawn+poll loop completely |
| 2 | **mprocs** | TUI process multiplexer reading YAML; tab-per-CLI scrollback; kill/restart shortcuts |
| 3 | **gum** (charmbracelet) | Drop-in replacement for our `echo` status lines + spinners + confirm prompts |
| 4 | **rush** | xargs replacement: multi-line commands, retry/timeout, `--immediate-output` (no buffering merge) |
| 5 | **zellij** | KDL layouts spawn N panes per CLI; WASM plugins for live aggregation (heavier than mprocs) |

**Rejected**: GNU parallel (Perl runtime + GPL nag), overmind/hivemind (Procfile-only),
supervisord (Python deps for daemons), nq (no parallelism cap).

### Concrete migration sketch (Phase 1 — replace polling loop)

```bash
pueue group add codex    --parallel 8
pueue group add gemini   --parallel 6
pueue group add opencode --parallel 6
for shard in shards/*; do
  pueue add --group codex -- "codex analyze $shard >> findings.jsonl"
done
pueue wait --group codex      # blocks cleanly, no poll loop
pueue status --json | jq '...' # for budget tracking
```

This deletes `kill -0` + `sleep 5` + the manual subprocess table.

---

## Theme B — LLM orchestration frameworks

Agent #2 evaluated 13 frameworks. Verdict:

> **promptfoo is the only framework with a native `exec:` provider** that shells
> out to arbitrary commands, runs them in parallel with `--max-concurrency`, and
> emits JSONL natively. It would replace our Bash watchdog, Python HTTP/SSE
> dashboard (it ships a web viewer), and the JSONL-append plumbing.

```yaml
# promptfooconfig.yaml — replaces ~600 LOC of cqc kit
providers:
  - id: exec:codex exec --json
    label: codex
  - id: exec:gemini --prompt
    label: gemini
  - id: exec:opencode run --no-tui
    label: opencode
prompts:
  - file://skills/{{skill}}.md
tests: file://tasks.jsonl
outputPath: findings.jsonl
```

```bash
npx promptfoo eval -c promptfooconfig.yaml --max-concurrency 4 --output findings.jsonl
npx promptfoo view   # SSE dashboard, free
```

**Trade-off**: adds Node/npx as a runtime; no Python deps. Stays declarative —
`exec:` is just shell, no framework lock-in.

**Rejected**:
- LangGraph, CrewAI, PydanticAI, AutoGen, agno → API-first, fight subprocess fan-out
- LiteLLM Proxy → solves the wrong problem (it's a gateway)
- Continue/Aider/Plandex → they ARE CLIs, not orchestrators of CLIs

---

## Theme C — Dashboard simplification

Agent #3 verdict:

> **Keep `cqc-ui.py`, simplify by removing ~150 LOC of vanilla JS using the
> htmx + SSE-fragments pattern.**
>
> The real problem with the current 330 LOC isn't Python — it's the vanilla-JS
> poll loop and DOM patching. That's ~150 LOC of imperative JS the htmx
> pattern eliminates entirely.

```html
<div hx-ext="sse" sse-connect="/events">
  <div sse-swap="tiles">…</div>
  <table sse-swap="active-runs">…</table>
  <div sse-swap="logs" hx-swap="beforeend">…</div>
</div>
```

Server emits HTML fragments instead of JSON:
```
event: tiles
data: <div class="tile">…</div>

```

No JSON, no client-side rendering, no diffing.

**Rejected**: Bubble Tea TUI (kills Tailscale browser flow), PocketBase
(20MB binary for a 4-tile dashboard), Datasette (SQL explorer, wrong shape),
NATS/Redis (violates no-deps philosophy).

---

## Recommended adoption order

1. **htmx fragments** (easiest, lowest risk, biggest LOC win in JS):
   - 2-hour refactor
   - Removes ~150 LOC of vanilla JS
   - Single new dep: `<script src="https://unpkg.com/htmx.org@2.x">` (CDN)

2. **gum + spinners** (zero-risk polish):
   - Replace `echo "[INFO] …"` with `gum log --level info`
   - Replace ASCII spinner in cqc-parallel with `gum spin`

3. **pueue** (medium-risk, biggest LOC win in Bash):
   - Migrate cqc-orchestrate's spawn+watch into pueue groups
   - Removes the polling loop, status table, retry budget tracking
   - Persistent queue = orchestrate runs survive SSH disconnect

4. **mprocs** (optional power-user view):
   - YAML config generated from plan.json
   - Tab-per-shard scrollback in terminal
   - Kill/restart shortcuts without curl /api/cancel

5. **promptfoo** (heavy migration, biggest single LOC win) — **only if**:
   - You're OK with a Node runtime
   - You want a declarative YAML model instead of imperative orchestration
   - You're ready to drop both `cqc-orchestrate` AND `cqc-ui.py`

## What we keep regardless

- **Skill matrix** (which CLI gets which dimensions) — domain logic, not boilerplate
- **Budget caps + Flash fallback** — domain policy, not boilerplate
- **JSONL findings format** — works with everything (jq, datasette, sqlite-utils)
- **Plan-first architecture** — `plan.json` before spawning is independent of any tool

## Sources

Each agent provided its own citation list (see PR notes / git log).
Notable: pueue (github.com/Nukesor/pueue), mprocs (github.com/pvolok/mprocs),
gum (github.com/charmbracelet/gum), promptfoo.dev, htmx 4 SSE docs.
