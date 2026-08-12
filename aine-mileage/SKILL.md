---
name: aine-mileage
description: Use when filing daily home-to-GHQ commute mileage for a week of AINE bootcamp facilitation into WWT's internal expense app (expenses.apps.wwt.com), stopping short of submission. Invoked as "/aine-mileage <cohort-number>".
---

# AINE Bootcamp Mileage

## Overview

Automates adding daily commute mileage line items (home ↔ GHQ) to a WWT
expense report for one week of AINE bootcamp facilitation, using browser
automation against `https://expenses.apps.wwt.com/`. It finds or creates the
report and adds line items — **it never clicks Submit**. The user submits
manually after reviewing.

## When to Use

Triggered by `/aine-mileage <cohort-number>` (e.g. `/aine-mileage 7`). If no
cohort number is given, ask for one before doing anything else.

## Prerequisites

- **Chrome browser tools**: load them before starting — `ToolSearch` with
  `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__tabs_close_mcp,mcp__claude-in-chrome__find,mcp__claude-in-chrome__get_page_text`.
- **Home address config**: read `data/config.md` in this skill's directory
  for `home_address`. This file is gitignored (personal data, this repo is
  public) — if it's missing, stop and ask the user for their home address,
  then create `data/config.md` with:
  ```
  home_address: <address>
  ```
  Never put a real home address anywhere else in this repo.

## Fixed constants

These are not personal/sensitive — safe to use directly:

| Field | Value |
|---|---|
| GHQ address | `1 World Wide Way, St. Louis, MO 63146` |
| Trip distance | `20` (miles, every leg) |
| Project | `10034890 - Corporate AI Native Initiative` |
| Task | `01 - Support` |

## Procedure

### 1. Get the week's dates

Always ask the user directly for the Monday date of Cohort `{N}`'s bootcamp
week — there is no reliable cohort→date file in `aine-bootcamp-documentation`
(checked: `cohorts.csv` has location only, no dates; real dates live in an
external registration export, not in the repo). Derive Tue–Fri from that
Monday (bootcamps are confirmed single Mon–Fri weeks).

### 2. Open the expenses app

Navigate to `https://expenses.apps.wwt.com/report`. Assume the existing
Chrome session's SSO is valid. If a login page appears instead of the
reports list, **stop** and tell the user to log in manually, then re-run
the skill.

### 3. Find or create the report

Scan the reports list for a title that reads as this cohort's AINE mileage
report — contains "AINE" plus "Cohort {N}" in some form (the site has used
both "AINE Cohort N Mileage" and "AINE Bootcamp Cohort N Mileage" wording,
so match loosely on meaning, not an exact string).

- **No match** → click "Create report" (this immediately persists an empty
  report — note its ID from the URL), then set **Purpose** to
  `AINE Bootcamp Cohort {N} mileage`. Click elsewhere to blur the field,
  then confirm the title stuck by checking the Reports list shows it — if
  it still reads "Untitled" there, look for a separate save control on the
  report-details section before moving on.
- **One match** → use it. Leave its Purpose exactly as-is, even if it
  doesn't match the naming convention above — do not rename it.
- **Multiple matches** → list them for the user (title + status) and ask
  which one to use.

Then check the matched/created report's status badge. If it is anything
other than **"In Progress"** (e.g. "Ready for Payment", "Paid"), **stop**
and tell the user — never add lines to an already-submitted report.

### 4. Check what's already there

Open the report's **Lines** tab. Each existing line card shows its date
directly (no need to open a line to read it) — record which of the five
target weekdays already have at least one line item.

### 5. Add line items for each day that needs them

For each of Mon–Fri:

- **Date already has ≥1 existing line item** → skip it. Add it to a
  "flagged" list to report at the end. Do not try to guess whether one or
  two legs are missing, and do not match by justification text — some
  existing reports use older wording ("Mileage from home to GHQ") that
  won't text-match the template below, so date-presence is the only safe
  signal to skip on.
- **Date has 0 existing line items** → add both, via the report's
  **Mileage** tab (the dedicated add-mileage form — not "+ Add manual
  expense"):

  | Field | AM leg (commute in) | PM leg (commute home) |
  |---|---|---|
  | Justification | `Coming from home to GHQ to facilitate AINE cohort {N}` | `Going home from GHQ after facilitating AINE Bootcamp {N}` |
  | From | home address | GHQ address |
  | To | GHQ address | home address |
  | Project | `10034890 - Corporate AI Native Initiative` | (same) |
  | Task | `01 - Support` (select after Project — it's disabled until Project is chosen) | (same) |
  | Trip Distance (Miles) | `20` | `20` |

  Click **Save** after each leg. The Project field is a type-ahead — type
  part of the name, then click the matching suggestion; don't rely on
  typing the full value.

  **Date field quirk:** after typing the date, the calendar popover can
  swallow your next click and either reopen/toggle instead of moving focus,
  or (if the click lands on the currently-selected day cell) deselect it
  back to blank. The reliable way to move on is to click the **label text**
  of the next field (e.g. "Justification") rather than the input or
  anywhere inside/near the calendar — clicking a `<label>` focuses its
  input via native browser behavior and doesn't get intercepted by the
  popover. After doing this, take a screenshot to confirm the date held
  before typing further fields.

### 6. Report back and stop

Give the user:
- The report URL: `https://expenses.apps.wwt.com/report/{report_id}`
- Which dates got lines added
- Which dates were skipped/flagged, and why
- An explicit reminder that the report was **not** submitted

**Never click Submit.** That's the user's step.

## Common mistakes

- Clicking "Add manual expense" instead of the **Mileage** tab — it's a
  different, more generic flow. Use the Mileage tab.
- Renaming an existing report's Purpose to match the new title convention —
  don't; only new reports get the new title.
- Treating a day with exactly one existing line as "needs one more leg" —
  don't guess; skip and flag it instead.
- Forgetting Task is disabled until Project is selected — select Project
  first, then Task becomes available.
- Clicking straight into the Justification *input* (or anywhere near the
  calendar) right after typing the Date — click its `<label>` text instead
  (see Date field quirk above), or the date can silently revert.
