# 30 More Improvements (v3.6+ backlog)

After v3.5, here are 30 further high-ROI improvements grouped by theme. Each is a 5-30 min code change.

## Theme A — CLI usage & cost intelligence (10)

1. **Real-time cost meter** during run — print `+$0.04` after each sub-agent finishes
2. **Per-skill cost attribution** — `_run.json:agents.<skill>.cost_usd` for ROI analysis
3. **Cost-budget stop** — `--max-cost=$5` aborts run before exceeding
4. **Auto-fallback to cheapest CLI** — when claude pro hits cap, shift to gemini free tier
5. **Cache hit metric** — show prompt-cache hit % per skill (claude pricing relies on this)
6. **Token-per-finding ratio** — find skills that are expensive vs valuable
7. **CLI health check** — pre-flight ping each CLI with 1-token request to verify auth still works
8. **Plan tier auto-detect** — claude max/pro/api distinguishable by `~/.claude/auth.json`
9. **Codex login state** — `codex login --check` before spawning to avoid silent failures
10. **OpenCode model picker** — different models per skill (e.g. `glm-4.6` for d1, `kimi` for d12)

## Theme B — Output ergonomics (10)

11. **Splash-screen on report open** — `dashboard.html` shows the ASCII banner at top
12. **Markdown TOC in REPORT.md** — anchor links for `#critical`, `#high`, `#hot-spots`
13. **Code-fold per dimension** — collapsible `<details>` blocks
14. **Per-finding GitHub link** — auto-generate `https://github.com/<owner>/<repo>/blob/<sha>/<file>#L<line>` if remote detected
15. **Per-finding "claim this" button** — dashboard.html has a button per finding that copies a fix-prompt to clipboard
16. **Diff vs last run inline** — REPORT.compact.txt shows `+2 H, -1 C` deltas next to each dim
17. **Confidence histogram** — ASCII chart of finding confidence distribution
18. **Severity Pareto chart** — top-10 files contributing 80 % of findings
19. **Time-to-fix estimate** — sum of per-finding effort (`30min`, `2h`) for a roadmap
20. **Status badge generator** — `gh-badge.svg` for README ("Code quality: 78/100")

## Theme C — Smarter audit logic (10)

21. **AST-grep mode for d1/d6** — replace regex with structural patterns (zero false positives on swallowed `catch`)
22. **Semantic-diff mode** — when scope is `branch/x`, only audit semantic changes, not formatting
23. **Test-coverage-feedback** — d3 reads coverage report and downgrades tested files in d6's god-file finding
24. **Auth-flow detection** — d4 follows imports from `app/api/auth/*` to find request-validation gaps
25. **Library trust score** — d12 cross-refs OSS Scorecard / Snyk advisories, not just `pnpm audit`
26. **License compatibility matrix** — d12 flags GPL-in-MIT-monorepo cases
27. **Type-narrowing audit** — d2 finds discriminated unions used incorrectly
28. **Effect dependency graph** — d5 builds a graph of useEffect dependencies, finds phantom triggers
29. **Bundle-budget per route** — d5 enforces per-route LFJ budgets from `cqc.config.yaml`
30. **Skill chaining** — if d4 finds a hardcoded secret, automatically trigger d12 to check if dep also has the same secret

## Theme priority for v3.6

Top-5 quick wins:
- #11 ASCII banner in dashboard.html (5 min)
- #16 diff-vs-last-run in REPORT.compact.txt (10 min)
- #1 real-time cost meter (10 min)
- #14 GitHub-link generation (5 min)
- #21 ast-grep for d1 (30 min, removes top false-positive class)

## Submission to skills.sh

Once v3.6 ships, the kit will be ready to submit to:
- [skills.sh](https://skills.sh) — main marketplace
- [claudeskills.info](https://claudeskills.info) — community directory
- [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) — curated list
- [tessl.io/registry/skills](https://tessl.io/registry/skills) — typed skills registry

Submission requires:
- ✅ `LICENSE` (MIT)
- ✅ `README.md`
- ✅ End-to-end tested
- ⏳ Strip ReplyManager-specific examples (replace with generic placeholders)
- ⏳ Add `SKILL.md` in claudeskills.info format
- ⏳ Add `package.json` with `claude-skills` keyword for skills.sh discovery
