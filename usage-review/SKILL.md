---
name: usage-review
description: Run a personal, bi-weekly or monthly review of AI-tooling usage (Claude Code, Devin Local) — spend trend, model-selection judgment, skill leverage, and git-history correlation — and publish it as an Artifact. Use when the user asks to review their Claude/AI usage, wants an engineering-practice or continuous-improvement report, or invokes this by name ("usage review", "run my usage review").
---

# Usage Review

A self-review of AI-assisted engineering work over a period (default: last 14
days), in the style of the "Engineering Practice Review" report. Fully
automatic data-gathering — no screenshots, no manual transcription, no
Console access needed. The only manual step is invoking this skill.

## Why this exists / what it replaces

Claude Enterprise's in-app Usage page is the only self-service place to see
exact dollar spend by product/model/skill, and both CSV export and the
Analytics API are admin-only on Enterprise plans — a regular seat can't pull
exact figures without asking WWT's Claude org admin. Instead, this skill
mines **local, already-on-disk data**:

- `~/.claude/projects/**/*.jsonl` — Claude Code session transcripts, which
  carry per-message token usage (`input_tokens`, `output_tokens`,
  `cache_creation_input_tokens`, `cache_read_input_tokens`) and model ID.
  Token counts → an **estimated** dollar figure via a hardcoded pricing table.
- `~/.local/share/devin/cli/sessions.db` — Devin Local's session history
  (working directory, model, timestamps).
- `git log --author=<you>` across repos under `~/projects` — what was
  actually built, to correlate against the spend data.

## ⚠️ The local estimate is not the headline number — screenshots are

Cross-checked against the actual July 2026 Console total ($486.48): the local
token-based estimate came out to **~$873, about 1.8x high** (range
~1.45x–2.1x across individual weeks). That's not close enough to report as
if it were real spend. **Default behavior is therefore to pause mid-run and
ask the user for Console screenshots covering the period, and use those
numbers for every dollar figure in the report.** The local estimate is
computed for internal cross-reference only (sanity-checking which week/model
had a spike) and is never the headline number unless the user explicitly
declines to provide screenshots for this run.

**Do not silently fall back to the estimate.** If the user says they don't
have screenshots handy, ask explicitly whether they want to proceed with the
flagged estimate anyway (reminding them of the ~1.5–2x-high range) — that's
their call to make, not a default.

## Procedure

1. **Determine the period.** Default to the 14 days since the last logged
   run (`data/trend_log.csv` — read the last `period_end`, start the new
   period the day after). No log yet, or no clear cadence signal from the
   user → default to the last 14 days. If the user says "monthly" or gives
   explicit dates, honor that instead.

2. **Run the gathering script** — this is the only step that touches disk
   beyond reading, and don't pass `--append-log` yet (the log append happens
   in step 5, once real figures are known):

   ```
   python3 ~/.claude/skills/usage-review/scripts/gather_stats.py \
     --since <period_start> --until <period_end>
   ```

   This prints one JSON object: Claude weekly token/cost breakdown by model
   (an *internal* estimate — see the calibration-gap warning above), skill
   invocation counts, Agent/subagent delegation counts, session count, git
   commits by you (auto-detected via `git config user.email`) across
   `~/projects`, and Devin Local session activity.

   If `unknown_models` is non-empty in the output, a model ID appeared that
   isn't in the pricing table — note it and flag that `PRICING` in the
   script needs a new entry (check current rates via the `claude-api` skill
   or `shared/live-sources.md` → Pricing).

3. **Pause and ask for Console screenshots covering the period.** Before
   writing anything with a dollar figure in it, ask the user (in chat, or
   via `AskUserQuestion` if a decision is genuinely needed) for:
   - **Settings → Usage**, grouped by **Product**, Weekly view, for the
     period
   - The same screen grouped by **Model**
   - **Top skills** if skill-level cost is worth including

   State the reason briefly — the local estimate runs ~1.5–2x high, so
   screenshots are the real numbers. If the period spans more than what one
   screenshot's date-range picker shows, ask for as many as needed to cover
   it. **Wait for the images before proceeding** — do not draft the spend
   narrative from the local estimate in the meantime.

   If the user says they don't have screenshots available this run, ask
   explicitly whether they want to proceed with the flagged local estimate
   instead (restate the ~1.5–2x-high range) rather than silently substituting
   it — this is their call, not a default fallback.

4. **Read the screenshots directly** (the `Read` tool handles images) and
   extract the exact weekly/model dollar figures — the same way the
   original "Engineering Practice Review" report was built. Cross-reference
   against the script's `weekly`/`by_model` breakdown to sanity-check which
   week/model the script over- or under-counted, but the screenshot numbers
   are what goes in the report and the trend log.

5. **Append the trend-log row with the real figures**, re-running the
   script with `--append-log` plus the actual totals read from the
   screenshots:

   ```
   python3 ~/.claude/skills/usage-review/scripts/gather_stats.py \
     --since <period_start> --until <period_end> \
     --append-log ~/.claude/skills/usage-review/data/trend_log.csv \
     --actual-total <$ from screenshot> \
     --actual-opus-pct <%> --actual-sonnet-pct <%> --actual-haiku-pct <%>
   ```

   If the user opted into the flagged local-estimate fallback instead (step
   3), omit the `--actual-*` flags — the row will log with
   `cost_source=estimate` so it's never later confused with a real figure.

6. **Read the trend log** (`data/trend_log.csv`) for prior periods. If this
   isn't the first run, open the report by naming what changed since last
   time — "Opus % down from X to Y," "spend up/down" — and note if the cost
   source (console vs. estimate) differs from last time, since the two
   aren't directly comparable. If it *is* the first run, just note the
   period covered.

7. **Correlate git commits to spend/model-mix.** For each week where a
   model dominated or spend spiked, read the actual commit subjects returned
   by the script (and `git log -p` / `git show` on specific commits if the
   subject alone doesn't explain the work) to write the same kind of
   evidence-backed narrative as the July report — quote real commit
   messages, don't speculate about what a spike "might have been."

8. **Check personal memory for context** the raw data can't supply — recall
   whether a given week was a cohort week, an infra migration, mandated eval
   grading, etc. (see `~/.claude/projects/*/memory/` conventions this user
   already follows). If something looks anomalous, prefer asking the user
   over guessing (as in the prior conversation, where "why was Opus high
   this week" got a real, evidence-changing answer).

9. **Include Devin Local activity** as its own short section — session
   count, distinct working directories/repos touched, model mix. Devin's
   local DB doesn't expose per-message token costs, so don't force a dollar
   figure for it; report activity volume and correlate to the same git
   commits where relevant (a commit in a repo that also shows Devin session
   activity that week is worth naming).

10. **Write the report as a fresh Artifact, built directly on the
    "Engineering Practice Review — July 2026" artifact as a template.**
    `reference/engineering-practice-review-template.html` in this skill's
    directory is a saved, clean copy of that original July report — reuse
    its CSS and component markup as-is rather than re-deriving a new design
    each run; only the content (numbers, weeks, commit quotes, chip/rec
    text) changes per period. This is a fixed template, not a style
    reference to reinterpret:
    - **Title** the artifact `Engineering Practice Review — <Month> <Year>`
      (both the `<title>` tag and the Artifact `title`/gallery name) — this
      is the series name across every period, not a one-off.
    - **Byline**: every report's meta-row includes `Prepared by: Ray Sanders`
      and `Role: Lead Software Engineer`, alongside `Period` and `Product`,
      exactly as the July template has it.
    - Reuse its exact structure: eyebrow + h1 ("AI-Assisted Workflow,
      \<Month\> \<Year\>") + dek + lens-row (Judgment / Leverage / Risk
      management / Systemization) + meta-row → stat-grid (4 tiles) → weekly
      spend-by-model chart (stacked SVG bar, hover tooltip, a collapsed
      exact-figures table) → narrative tying spend to real commits (bold
      lead line + evidence blockquote with real commit subjects) →
      strength/friction chips → numbered recommendations → footer.
    - Reuse its CSS tokens and type system as-is (Iowan Old Style / system
      sans / system mono, the `--accent` teal) — don't introduce a new
      palette or font pairing per run.
    - Before writing, load the `artifact-design` skill (utilitarian
      treatment — this is a memo/report, not a landing page) and `dataviz`
      skill (for the weekly spend-by-model chart) if either isn't already
      loaded this session — mainly to sanity-check the reused template
      still holds up, not to redesign it.
    - Name the output file with the period end date so each run mints a new
      artifact (a historical series), e.g.
      `usage-review-<period_end>.html` — don't overwrite the previous
      period's artifact.
    - Include a short "since last review" line (styled like the template's
      `.trend-note`) in the intro if a trend log row exists from a prior
      run.

11. **Report back to the user in chat**: period covered, the artifact link,
    and 3-5 sentences of the actual headline findings (don't just say "done,
    see the link" — say what it found).

## Files

- `scripts/gather_stats.py` — the data-gathering script (see its own
  docstring for arguments and output shape). Pricing table lives at the top;
  update it when Anthropic revises rates or a new model ID appears in
  `unknown_models`.
- `data/trend_log.csv` — one row per run, created automatically on first use.
- `reference/engineering-practice-review-template.html` — the fixed design
  template (July 2026's original report, cleaned of artifact-frame
  boilerplate). Reuse its CSS and markup verbatim each run; swap in the
  current period's title, meta-row, stats, chart data, narrative, chips, and
  recommendations. Every report keeps the "Engineering Practice Review —
  \<Month\> \<Year\>" title and the `Prepared by: Ray Sanders` /
  `Role: Lead Software Engineer` byline in its meta-row.
