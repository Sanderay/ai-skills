#!/usr/bin/env python3
"""
Gathers local, deterministic data for a periodic AI-tooling usage review:
  - Claude Code token usage + estimated spend, by week and by model
    (parsed from ~/.claude/projects/**/*.jsonl session transcripts)
  - Skill and Agent(subagent) invocation counts from the same transcripts
  - Git commits by the given author across repos under a root directory
  - Devin Local session activity (~/.local/share/devin/cli/sessions.db)

Prints one JSON object to stdout. Never touches the network. Read-only
except for --append-log, which appends one row to a local trend CSV.

Model pricing is hardcoded (see PRICING below) from the rates published at
https://platform.claude.com/docs/en/pricing as of 2026-08. Anthropic
occasionally revises per-model pricing (Claude Sonnet 5 in particular carries
an introductory rate through 2026-08-31) -- if a future run reports
"unknown_models" with a fallback-pricing warning, or dates land after that
cutoff, re-check the current rates before trusting the estimate.
"""
import argparse
import csv
import glob
import json
import os
import sqlite3
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# $ per million tokens: in=input, out=output, cw=cache write (5m ephemeral), cr=cache read
PRICING = {
    "claude-opus-5":            {"in": 5.00, "out": 25.00, "cw": 6.25, "cr": 0.50},
    "claude-opus-4-8":          {"in": 5.00, "out": 25.00, "cw": 6.25, "cr": 0.50},
    "claude-opus-4-7":          {"in": 5.00, "out": 25.00, "cw": 6.25, "cr": 0.50},
    "claude-opus-4-6":          {"in": 5.00, "out": 25.00, "cw": 6.25, "cr": 0.50},
    "claude-opus-4-5-20251101": {"in": 5.00, "out": 25.00, "cw": 6.25, "cr": 0.50},
    "claude-sonnet-4-6":            {"in": 3.00, "out": 15.00, "cw": 3.75, "cr": 0.30},
    "claude-sonnet-4-5-20250929":   {"in": 3.00, "out": 15.00, "cw": 3.75, "cr": 0.30},
    "claude-haiku-4-5":             {"in": 1.00, "out": 5.00,  "cw": 1.25, "cr": 0.10},
    "claude-haiku-4-5-20251001":    {"in": 1.00, "out": 5.00,  "cw": 1.25, "cr": 0.10},
    "claude-fable-5":  {"in": 10.00, "out": 50.00, "cw": 12.50, "cr": 1.00},
    "claude-mythos-5": {"in": 10.00, "out": 50.00, "cw": 12.50, "cr": 1.00},
}
SONNET5_INTRO_CUTOFF = datetime(2026, 8, 31, tzinfo=timezone.utc)
SONNET5_INTRO = {"in": 2.00, "out": 10.00, "cw": 2.50, "cr": 0.20}
SONNET5_STANDARD = {"in": 3.00, "out": 15.00, "cw": 3.75, "cr": 0.30}
FALLBACK_PRICING = SONNET5_STANDARD  # used for any model ID not recognized above


def get_pricing(model_id, when):
    if not model_id:
        return FALLBACK_PRICING, False
    if model_id == "claude-sonnet-5":
        return (SONNET5_INTRO if when <= SONNET5_INTRO_CUTOFF else SONNET5_STANDARD), True
    if model_id in PRICING:
        return PRICING[model_id], True
    return FALLBACK_PRICING, False


def parse_iso(ts):
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def week_start(dt):
    d = dt.date() - timedelta(days=dt.weekday())  # Monday
    return d.isoformat()


def gather_claude(projects_dir, start, end):
    weekly = defaultdict(lambda: defaultdict(lambda: {"in": 0, "out": 0, "cw": 0, "cr": 0, "cost": 0.0}))
    skill_counts = defaultdict(int)
    agent_counts = defaultdict(int)
    sessions_seen = set()
    unknown_models = set()

    pattern = os.path.join(projects_dir, "**", "*.jsonl")
    for path in glob.glob(pattern, recursive=True):
        try:
            with open(path, "r", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts_raw = obj.get("timestamp")
                    if not ts_raw:
                        continue
                    try:
                        ts = parse_iso(ts_raw)
                    except ValueError:
                        continue
                    if not (start <= ts <= end):
                        continue

                    msg = obj.get("message") or {}

                    if obj.get("type") == "assistant" and isinstance(msg, dict):
                        sid = obj.get("sessionId")
                        if sid:
                            sessions_seen.add(sid)
                        model_id = msg.get("model")
                        usage = msg.get("usage") or {}
                        if usage:
                            price, known = get_pricing(model_id, ts)
                            if not known:
                                unknown_models.add(model_id or "(missing)")
                            it = usage.get("input_tokens", 0) or 0
                            ot = usage.get("output_tokens", 0) or 0
                            cw = usage.get("cache_creation_input_tokens", 0) or 0
                            cr = usage.get("cache_read_input_tokens", 0) or 0
                            cost = (it * price["in"] + ot * price["out"] +
                                    cw * price["cw"] + cr * price["cr"]) / 1_000_000
                            wk = weekly[week_start(ts)][model_id or "(unknown)"]
                            wk["in"] += it
                            wk["out"] += ot
                            wk["cw"] += cw
                            wk["cr"] += cr
                            wk["cost"] += cost

                        content = msg.get("content")
                        if isinstance(content, list):
                            for block in content:
                                if not isinstance(block, dict):
                                    continue
                                if block.get("type") == "tool_use":
                                    name = block.get("name")
                                    inp = block.get("input") or {}
                                    if name == "Skill":
                                        skill_counts[inp.get("skill", "(unknown)")] += 1
                                    elif name == "Agent":
                                        agent_counts[inp.get("subagent_type") or "(default)"] += 1
        except OSError:
            continue

    weekly_out = []
    for wk, models in sorted(weekly.items()):
        entry = {"week_start": wk, "by_model": {}, "total_cost": 0.0}
        for model_id, agg in models.items():
            entry["by_model"][model_id] = {
                "input_tokens": agg["in"], "output_tokens": agg["out"],
                "cache_write_tokens": agg["cw"], "cache_read_tokens": agg["cr"],
                "estimated_cost": round(agg["cost"], 2),
            }
            entry["total_cost"] += agg["cost"]
        entry["total_cost"] = round(entry["total_cost"], 2)
        weekly_out.append(entry)

    return {
        "weekly": weekly_out,
        "skill_invocations": dict(sorted(skill_counts.items(), key=lambda kv: -kv[1])),
        "agent_delegations": dict(sorted(agent_counts.items(), key=lambda kv: -kv[1])),
        "session_count": len(sessions_seen),
        "unknown_models": sorted(unknown_models),
    }


def gather_git(repos_root, author, start, end):
    since = start.strftime("%Y-%m-%d")
    until = (end + timedelta(days=1)).strftime("%Y-%m-%d")
    repos = {}
    total = 0
    for git_dir in glob.glob(os.path.join(repos_root, "*", ".git")):
        repo = os.path.dirname(git_dir)
        try:
            out = subprocess.run(
                ["git", "-C", repo, "log", "--all", "--no-merges",
                 f"--author={author}", f"--since={since}", f"--until={until}",
                 "--pretty=format:%H|%aI|%s"],
                capture_output=True, text=True, timeout=15,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            continue
        if not out:
            continue
        commits = []
        for line in out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0][:10], "date": parts[1], "subject": parts[2]})
        if commits:
            repos[os.path.basename(repo)] = commits
            total += len(commits)
    return {"repos": repos, "commit_count": total}


def gather_devin(db_path, start, end):
    if not os.path.exists(db_path):
        return {"available": False}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        start_ts, end_ts = int(start.timestamp()), int(end.timestamp())
        rows = conn.execute(
            "SELECT id, title, working_directory, model, created_at "
            "FROM sessions WHERE created_at BETWEEN ? AND ? ORDER BY created_at",
            (start_ts, end_ts),
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        return {"available": False, "error": str(e)}

    sessions = []
    repos = set()
    for r in rows:
        sessions.append({
            "id": r["id"], "title": r["title"],
            "working_directory": r["working_directory"], "model": r["model"],
            "created_at": datetime.fromtimestamp(r["created_at"], tz=timezone.utc).isoformat(),
        })
        if r["working_directory"]:
            repos.add(os.path.basename(r["working_directory"].rstrip("/")))
    return {"available": True, "session_count": len(sessions), "sessions": sessions,
            "distinct_working_dirs": sorted(repos)}


def append_log(log_path, start, end, claude_data, actual=None):
    """actual: optional dict with real Console figures {total, opus_pct, sonnet_pct,
    haiku_pct} read from user-supplied screenshots. When present, these are logged
    as the source of truth and the local estimate is logged alongside for reference
    only. When absent, the local estimate is logged with cost_source="estimate" so
    it's never confused with a real figure later."""
    total_cost_estimate = sum(w["total_cost"] for w in claude_data["weekly"])
    model_totals = defaultdict(float)
    for w in claude_data["weekly"]:
        for model_id, agg in w["by_model"].items():
            model_totals[model_id] += agg["estimated_cost"]
    opus_cost = sum(v for k, v in model_totals.items() if "opus" in (k or ""))
    sonnet_cost = sum(v for k, v in model_totals.items() if "sonnet" in (k or ""))
    haiku_cost = sum(v for k, v in model_totals.items() if "haiku" in (k or ""))
    pct = lambda v: round(100 * v / total_cost_estimate, 1) if total_cost_estimate else 0.0

    if actual:
        cost_source = "console"
        total_cost = actual["total"]
        opus_pct, sonnet_pct, haiku_pct = actual.get("opus_pct"), actual.get("sonnet_pct"), actual.get("haiku_pct")
    else:
        cost_source = "estimate"
        total_cost = round(total_cost_estimate, 2)
        opus_pct, sonnet_pct, haiku_pct = pct(opus_cost), pct(sonnet_cost), pct(haiku_cost)

    row = {
        "period_start": start.date().isoformat(),
        "period_end": end.date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cost_source": cost_source,
        "total_cost": total_cost,
        "opus_pct": opus_pct,
        "sonnet_pct": sonnet_pct,
        "haiku_pct": haiku_pct,
        "local_estimate_total": round(total_cost_estimate, 2),
        "skill_invocations": sum(claude_data["skill_invocations"].values()),
        "claude_session_count": claude_data["session_count"],
    }
    file_exists = os.path.exists(log_path)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", help="YYYY-MM-DD, default 14 days before --until")
    ap.add_argument("--until", help="YYYY-MM-DD, default today")
    ap.add_argument("--repos-root", default=os.path.expanduser("~/projects"))
    ap.add_argument("--author", default=None, help="git author filter; defaults to `git config user.email`")
    ap.add_argument("--claude-projects-dir", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--devin-db", default=os.path.expanduser("~/.local/share/devin/cli/sessions.db"))
    ap.add_argument("--append-log", default=None, help="path to a CSV trend log; appends one summary row")
    ap.add_argument("--actual-total", type=float, default=None,
                     help="real total $ spend for the period, read from a Console screenshot/export. "
                          "When given (with the --actual-*-pct flags below), the log row uses these "
                          "instead of the local estimate.")
    ap.add_argument("--actual-opus-pct", type=float, default=None)
    ap.add_argument("--actual-sonnet-pct", type=float, default=None)
    ap.add_argument("--actual-haiku-pct", type=float, default=None)
    args = ap.parse_args()

    end = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc) if args.until else datetime.now(timezone.utc)
    end = end.replace(hour=23, minute=59, second=59)
    start = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else end - timedelta(days=14)
    start = start.replace(hour=0, minute=0, second=0)

    author = args.author
    if not author:
        try:
            author = subprocess.run(["git", "config", "--global", "user.email"],
                                     capture_output=True, text=True, timeout=5).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            author = ""

    claude_data = gather_claude(args.claude_projects_dir, start, end)
    git_data = gather_git(args.repos_root, author, start, end)
    devin_data = gather_devin(args.devin_db, start, end)

    result = {
        "period": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "author_filter": author,
        "repos_root": args.repos_root,
        "claude": claude_data,
        "git": git_data,
        "devin": devin_data,
    }

    if args.append_log:
        actual = None
        if args.actual_total is not None:
            actual = {
                "total": args.actual_total,
                "opus_pct": args.actual_opus_pct,
                "sonnet_pct": args.actual_sonnet_pct,
                "haiku_pct": args.actual_haiku_pct,
            }
        result["log_row_appended"] = append_log(args.append_log, start, end, claude_data, actual=actual)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
