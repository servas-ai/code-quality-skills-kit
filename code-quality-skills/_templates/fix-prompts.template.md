# Fix Prompts — {{run_id}}

One paste-able Claude Code prompt per CRITICAL + HIGH finding. Skip MEDIUM / LOW (see `REPORT.md`).

> **How to use:** copy a fix prompt below, open a new Claude Code session, paste it. The prompt is self-contained — no further context needed.

---

{{#each findings_critical_high}}

## Fix #{{id}} — `{{path}}:{{line}}` — {{title}}

**Severity:** {{severity_emoji}} {{severity_upper}} · **Dimension:** D{{dimension}} {{dimension_name}} · **Tags:** {{tags}}

**Context (excerpt, ≤5 lines):**

```{{lang}}
{{excerpt}}
```

**Why this matters:** {{why}}

**Fix prompt — paste into Claude Code:**

```
Fix the {{dimension_short}} finding in {{path}}:{{line}} — {{problem}}.

Constraints:
- Do not break the existing API surface (keep public exports unchanged).
- Add a regression test in {{test_path_suggestion}}.
- Verify project invariants are still intact after the change:
{{#each invariants}}
  - {{this.name}} (verify with: `{{this.verify}}`)
{{/each}}
- Honour project language policy: ui_strings = {{language_policy.ui_strings}}.
- Open a separate PR titled "fix({{dimension_short}}): {{short_title}}".

Acceptance criteria:
- {{acceptance_1}}
- {{acceptance_2}}
- {{acceptance_3}}
```

---

{{/each}}

## Skipped severities

- 🟡 MEDIUM: {{counts.medium}} findings — see `REPORT.md` § Findings.
- 🟢 LOW: {{counts.low}} findings — see `REPORT.md` § Findings.

These don't get individual prompts to keep this file under control. Group-fix them with `/code-quality-batch-fix --severity=medium`.
