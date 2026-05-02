#!/usr/bin/env python3
"""cqc-ui — local live dashboard for code-quality-skills-kit.

Pure Python stdlib HTTP server with SSE for live progress.
Endpoints:
  GET  /                        inline HTML page
  GET  /api/state               JSON: {clis, runs, totals}
  GET  /api/stream              SSE: state every 3s
  POST /api/run                 body {scope, clis} -> {run_id}
  POST /api/cancel/<run_id>     terminates background subprocess
  GET  /api/log/<run_id>/<cli>  raw log file
"""
import base64
import glob
import http.server
import json
import os
import re
import signal
import socketserver
import subprocess
import threading
import time
from datetime import datetime, timezone

ROOT = os.environ.get("CQC_ROOT", os.getcwd())
PORT = int(os.environ.get("CQC_PORT", "4020"))
VERSION = os.environ.get("CQC_VERSION", "v3.19")
CLIS = ("claude", "gemini", "opencode", "codex", "qwen")
BUDGET_FILE = os.path.expanduser("~/.cqc/budget.json")
USAGE_FILE  = os.path.expanduser("~/.cqc/usage.json")


def load_budget():
    defaults = {"caps_pct": {"claude":0,"codex":50,"gemini":100,"opencode":0,"qwen":0},
                "models": {"opencode_model":"opencode-go/glm-5.1",
                           "gemini_primary":"gemini-3.1-pro-preview",
                           "gemini_fallback":"gemini-3-flash-preview"},
                "parallel_max": 20, "shard_max_files": 25,
                "max_run_seconds": 1800, "stall_timeout_seconds": 240}
    try:
        with open(BUDGET_FILE) as f: data = json.load(f)
        # Backfill new keys for backward compat
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return defaults


def load_usage():
    try:
        with open(USAGE_FILE) as f: return json.load(f)
    except Exception:
        return {"by_cli": {c: {"today_usd":0.0,"today_tokens":0,"calls_today":0} for c in CLIS}}


# Gemini local usage tracker — parses ~/.gemini/tmp/<project>/chats/session-*.jsonl.
# OAuth-personal Ultra cap: 2000 prompts/day; weekly extrapolation = 14000.
gemini_usage_cache = {"ts": 0, "data": None}
gemini_usage_lock = threading.Lock()
GEMINI_DAILY_CAP = 2000
GEMINI_WEEKLY_CAP = 14000


def get_gemini_local_usage():
    """Aggregate gemini calls/tokens from local CLI session JSONLs.

    Caches result for 60s. Reads ALL session files (capped at 1000 newest by mtime),
    dedupes events by `id`, sums tokens.total, buckets by today / last 7 days.

    Lock-protected: concurrent callers wait for the first to populate the cache
    instead of each doing their own multi-second parse over GBs of JSONL.
    """
    now = time.time()
    if gemini_usage_cache["data"] and (now - gemini_usage_cache["ts"]) < 60:
        return gemini_usage_cache["data"]
    with gemini_usage_lock:
        # Re-check under lock — another thread may have populated while we waited.
        now = time.time()
        if gemini_usage_cache["data"] and (now - gemini_usage_cache["ts"]) < 60:
            return gemini_usage_cache["data"]
        cutoff_24h = now - 86400
        cutoff_7d  = now - 7 * 86400
        today_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pattern = os.path.expanduser("~/.gemini/tmp/*/chats/session-*.jsonl")
        files = glob.glob(pattern)
        # Sort by mtime desc, cap at 1000 newest
        files = sorted(files, key=lambda p: os.path.getmtime(p) if os.path.isfile(p) else 0, reverse=True)[:1000]
        seen = set()
        calls_today = calls_7d = 0
        tokens_today = tokens_7d = 0
        for fp in files:
            try:
                mtime = os.path.getmtime(fp)
            except OSError:
                continue
            if mtime < cutoff_7d:
                continue
            try:
                with open(fp, "r", errors="ignore") as fh:
                    for line in fh:
                        if '"type":"gemini"' not in line:
                            continue
                        try:
                            ev = json.loads(line)
                        except Exception:
                            continue
                        if ev.get("type") != "gemini":
                            continue
                        ts = ev.get("timestamp") or ""
                        tk = ev.get("tokens") or {}
                        total = tk.get("total")
                        if total is None:
                            total = (tk.get("input") or 0) + (tk.get("output") or 0)
                        eid = ev.get("id")
                        if eid:
                            if eid in seen:
                                continue
                            seen.add(eid)
                        # Parse ISO timestamp -> epoch
                        t_epoch = None
                        if ts:
                            try:
                                t_epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                            except Exception:
                                t_epoch = None
                        if t_epoch is None:
                            t_epoch = mtime  # best-effort fallback
                        if t_epoch >= cutoff_7d:
                            calls_7d += 1
                            tokens_7d += int(total or 0)
                        # Today bucket: prefer date-string match if ts present
                        is_today = False
                        if ts and ts[:10] == today_str:
                            is_today = True
                        elif t_epoch >= cutoff_24h:
                            is_today = True
                        if is_today:
                            calls_today += 1
                            tokens_today += int(total or 0)
            except Exception:
                continue
        daily_pct = round(min(100.0, (calls_today / GEMINI_DAILY_CAP) * 100), 1) if GEMINI_DAILY_CAP else 0
        weekly_pct = round(min(100.0, (calls_7d / GEMINI_WEEKLY_CAP) * 100), 1) if GEMINI_WEEKLY_CAP else 0
        data = {
            "calls_today": calls_today,
            "calls_7d": calls_7d,
            "tokens_today": tokens_today,
            "tokens_7d": tokens_7d,
            "used_pct_daily": daily_pct,
            "weekly_used_pct": weekly_pct,
            "daily_cap": GEMINI_DAILY_CAP,
            "weekly_cap": GEMINI_WEEKLY_CAP,
            "files_scanned": len(files),
        }
        gemini_usage_cache["ts"] = now
        gemini_usage_cache["data"] = data
        return data


def jwt_payload(token):
    """Decode JWT payload (NO signature verify — read-only display)."""
    if not token or "." not in token: return None
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload).decode())
    except Exception:
        return None


def fmt_age(secs):
    if secs < 0: return f"expired {fmt_age(-secs)} ago"
    if secs < 60: return f"{int(secs)}s"
    if secs < 3600: return f"{int(secs/60)}m"
    if secs < 86400: return f"{int(secs/3600)}h"
    return f"{int(secs/86400)}d"


def get_account_info(cli):
    """Pull account info from each CLI's auth file. Returns {email, plan, expires, scopes, auth_path, error}."""
    info = {"email": None, "plan": None, "expires_at": None, "expires_in": None,
            "auth_path": None, "scopes": None, "providers": None, "auth_type": None,
            "account_id": None, "error": None}
    if cli == "codex":
        p = os.path.expanduser("~/.codex/auth.json")
        info["auth_path"] = p
        if not os.path.isfile(p):
            info["error"] = "auth.json missing — run `codex login`"; return info
        try:
            with open(p) as f: a = json.load(f)
            info["auth_type"] = a.get("auth_mode", "unknown")
            tok = a.get("tokens", {})
            payload = jwt_payload(tok.get("id_token") or tok.get("access_token"))
            if payload:
                info["email"] = payload.get("email")
                info["account_id"] = (payload.get("https://api.openai.com/auth", {}) or {}).get("chatgpt_account_id")
                auth_meta = payload.get("https://api.openai.com/auth", {}) or {}
                info["plan"] = auth_meta.get("chatgpt_plan_type") or info["auth_type"]
                until = auth_meta.get("chatgpt_subscription_active_until")
                if until:
                    info["expires_at"] = until
                    try:
                        t = datetime.fromisoformat(until.replace("Z", "+00:00"))
                        info["expires_in"] = fmt_age((t - datetime.now(timezone.utc)).total_seconds())
                    except Exception: pass
                # Token expiry (access_token exp claim)
                if payload.get("exp"):
                    info["token_exp"] = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat()
        except Exception as e:
            info["error"] = f"parse error: {e}"
    elif cli == "claude":
        p = os.path.expanduser("~/.claude/.credentials.json")
        info["auth_path"] = p
        if not os.path.isfile(p):
            info["error"] = ".credentials.json missing — run `claude /login`"; return info
        try:
            with open(p) as f: a = json.load(f)
            oa = a.get("claudeAiOauth", {})
            info["scopes"] = oa.get("scopes")
            info["auth_type"] = "oauth"
            exp_ms = oa.get("expiresAt")
            if exp_ms:
                t = datetime.fromtimestamp(exp_ms/1000, tz=timezone.utc)
                info["expires_at"] = t.isoformat()
                info["expires_in"] = fmt_age((t - datetime.now(timezone.utc)).total_seconds())
            # Try to read settings for plan/email
            sp = os.path.expanduser("~/.claude/auth.json")
            if os.path.isfile(sp):
                try:
                    with open(sp) as f: ad = json.load(f)
                    info["email"] = ad.get("email")
                    info["plan"]  = ad.get("subscription_type") or ad.get("plan")
                except Exception: pass
        except Exception as e:
            info["error"] = f"parse error: {e}"
    elif cli == "gemini":
        ga = os.path.expanduser("~/.gemini/google_accounts.json")
        info["auth_path"] = ga
        if os.path.isfile(ga):
            try:
                with open(ga) as f: a = json.load(f)
                info["email"] = a.get("active")
            except Exception: pass
        st = os.path.expanduser("~/.gemini/settings.json")
        if os.path.isfile(st):
            try:
                with open(st) as f: s = json.load(f)
                info["auth_type"] = (s.get("security", {}).get("auth", {}) or {}).get("selectedType")
                info["plan"] = "free (oauth-personal)" if info["auth_type"] == "oauth-personal" else info["auth_type"]
            except Exception: pass
        # OAuth creds expiry
        oc = os.path.expanduser("~/.gemini/oauth_creds.json")
        if os.path.isfile(oc):
            try:
                with open(oc) as f: o = json.load(f)
                exp_ms = o.get("expiry_date") or o.get("expiry")
                if exp_ms and exp_ms > 1e10: exp_ms = exp_ms / 1000
                if exp_ms:
                    t = datetime.fromtimestamp(exp_ms, tz=timezone.utc)
                    info["expires_at"] = t.isoformat()
                    info["expires_in"] = fmt_age((t - datetime.now(timezone.utc)).total_seconds())
            except Exception: pass
        if not info["email"]:
            info["error"] = "no active account — run `gemini /auth`"
    elif cli == "opencode":
        p = os.path.expanduser("~/.local/share/opencode/auth.json")
        info["auth_path"] = p
        if not os.path.isfile(p):
            info["error"] = "auth.json missing — run `opencode auth login`"; return info
        try:
            with open(p) as f: a = json.load(f)
            providers = []
            for prov, meta in a.items():
                providers.append({"name": prov, "type": meta.get("type"), "has_key": bool(meta.get("key"))})
            info["providers"] = providers
            info["plan"] = ", ".join(p["name"] for p in providers) if providers else "no providers"
        except Exception as e:
            info["error"] = f"parse error: {e}"
    elif cli == "qwen":
        # qwen quota tracking not implemented yet — show tile honestly with stub
        info["auth_type"] = "unknown"
        info["error"] = "qwen quota tracking not implemented yet"
    return info


def extract_limits(subscription):
    """Pull human-readable daily/weekly limit strings from `subscription.limits`.

    `limits` is a free-form dict (str -> str) that varies per CLI, e.g.
      Codex:    "5h GPT-5.4": "...", "Weekly": "..."
      Claude:   "5h messages": "...", "Weekly": "...", "Monthly est.": "..."
      OpenCode: "5h rolling": "...", "Free tier": "..."
      Gemini:   "Gemini CLI requests": "1k req/day...", "Deep Research": "..."
    Returns {"daily": <str|None>, "weekly": <str|None>} — caller decides how to render.
    """
    if not isinstance(subscription, dict): return {"daily": None, "weekly": None}
    limits = subscription.get("limits") or {}
    daily = weekly = None
    for k, v in limits.items():
        kl = str(k).lower()
        # Daily-ish: "5h", "rolling", "/day", "daily", "msgs/5h"
        if daily is None and any(t in kl for t in ("5h", "/day", "daily", "rolling", "cli requests")):
            daily = f"{k}: {v}"
        # Weekly-ish: "weekly", "7d", "7-day", "week"
        if weekly is None and any(t in kl for t in ("weekly", "7d", "7-day", "week")):
            weekly = f"{k}: {v}"
    return {"daily": daily, "weekly": weekly}


def get_metrics():
    b = load_budget()
    u = load_usage()
    out = {"caps_pct": b.get("caps_pct", {}),
           "models":   b.get("models", {}),
           "parallel_max": b.get("parallel_max", 20),
           "by_cli": {}}
    for cli in CLIS:
        cap = b.get("caps_pct", {}).get(cli, 0)
        usage = (u.get("by_cli", {}).get(cli) or {})
        used_pct = usage.get("used_pct", 0)
        lim = extract_limits(usage.get("subscription"))
        out["by_cli"][cli] = {
            "cap_pct":      cap,
            "used_pct":     used_pct,
            "today_usd":    usage.get("today_usd", 0.0),
            "calls_today":  usage.get("calls_today", 0),
            "remaining_pct": max(0, cap - used_pct),
            "blocked":      cap == 0,
            "daily_limit":  lim["daily"],
            "weekly_limit": lim["weekly"],
            "model":        b.get("models", {}).get(f"{cli}_model") or
                            (b.get("models", {}).get("gemini_primary") if cli == "gemini"
                             else b.get("models", {}).get("opencode_model") if cli == "opencode"
                             else None),
        }
    return out

PROCS_LOCK = threading.Lock()
RUNNING_PROCS = {}  # run_id -> {pid, scope, clis, started, proc}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def time_ago(iso):
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = (datetime.now(timezone.utc) - t).total_seconds()
        if delta < 60: return f"{int(delta)}s"
        if delta < 3600: return f"{int(delta/60)}m"
        if delta < 86400: return f"{int(delta/3600)}h"
        return f"{int(delta/86400)}d"
    except Exception:
        return None


# Cache CLI --version probes for 5 min — these are the /api/state hotpath bottleneck.
_cli_version_cache = {}  # name -> (installed, ver, expires_at)


def _probe_cli_version(name):
    now = time.time()
    cached = _cli_version_cache.get(name)
    if cached and cached[2] > now:
        return cached[0], cached[1]
    installed, ver = False, None
    try:
        r = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=2)
        installed = r.returncode == 0
        m = re.search(r"(\d+\.\d+\.\d+)", (r.stdout or "") + (r.stderr or ""))
        ver = m.group(1) if m else None
    except Exception:
        pass
    _cli_version_cache[name] = (installed, ver, now + 300)  # 5 min TTL
    return installed, ver


# Cache get_state() result for 2s — SSE streams call it every 3s per client.
_state_cache = {"ts": 0, "data": None}
_state_lock = threading.Lock()


def cli_status():
    out = []
    metrics = get_metrics()
    usage = load_usage()
    usage_by_cli = usage.get("by_cli", {})
    budget = load_budget()
    for name in CLIS:
        installed, ver = _probe_cli_version(name)
        plan = "—"
        if name == "claude":
            p = os.path.expanduser("~/.claude/auth.json")
            if os.path.isfile(p):
                try:
                    with open(p) as f: a = json.load(f)
                    plan = a.get("subscription_type") or a.get("plan") or "api"
                except Exception: pass
        elif name == "codex":
            p = os.path.expanduser("~/.codex/auth.json")
            if os.path.isfile(p):
                try:
                    with open(p) as f: a = json.load(f)
                    plan = a.get("auth_mode", "chatgpt")
                except Exception: pass
        elif name == "gemini":
            if os.path.isfile(os.path.expanduser("~/.gemini/google_accounts.json")):
                plan = "free"
        m = metrics["by_cli"].get(name, {})
        u = usage_by_cli.get(name, {}) or {}
        acct = get_account_info(name)
        # Gemini: merge local JSONL-derived stats (no public quota API).
        gem_local = None
        if name == "gemini":
            try:
                gem_local = get_gemini_local_usage()
            except Exception:
                gem_local = None
            if gem_local:
                # Override empty/missing fields with local data
                if not u.get("today_tokens"):
                    u["today_tokens"] = gem_local["tokens_today"]
                if not u.get("calls_today"):
                    u["calls_today"] = gem_local["calls_today"]
                if not u.get("used_pct"):
                    u["used_pct"] = gem_local["used_pct_daily"]
        # Real numbers from ccusage take precedence
        real_used_pct = u.get("used_pct", m.get("used_pct", 0))
        real_today_usd = u.get("today_usd", m.get("today_usd", 0.0))
        model_used = u.get("model_used") or m.get("model")
        # Email — Claude email comes from OAuth /profile, override acct
        if name == "claude" and u.get("email"):
            acct["email"] = u["email"]
            acct["plan"] = u.get("plan")
            acct["full_name"] = u.get("full_name")
            acct["org_name"] = u.get("org_name")
            acct["rate_limit_tier"] = u.get("rate_limit_tier")
        display_plan = acct.get("plan") or plan
        # Auth status
        needs_relogin = u.get("needs_relogin", False)
        oauth_error = u.get("oauth_error")
        no_quota_api = u.get("no_quota_api", False)
        out.append({
            "name": name, "installed": installed, "version": ver,
            "plan": display_plan,
            "today_usd": real_today_usd,
            "today_tokens": u.get("today_tokens", 0),
            "calls_today": u.get("calls_today", 0),
            "week_pct": real_used_pct,
            "cap_pct": m.get("cap_pct", 0),
            "used_pct": real_used_pct,
            "blocked": m.get("blocked", False),
            "daily_limit": m.get("daily_limit"),
            "weekly_limit": m.get("weekly_limit"),
            "model": model_used,
            "model_chain": budget.get("model_chains", {}).get(name, []),
            "needs_relogin": needs_relogin,
            "oauth_error": oauth_error,
            "no_quota_api": no_quota_api,
            "five_hour": u.get("five_hour"),
            "seven_day": u.get("seven_day"),
            "ratelimits": u.get("ratelimits"),
            "subscription": u.get("subscription"),
            "sessions_today": u.get("sessions_today"),
            "weekly_used_pct": (gem_local.get("weekly_used_pct") if name == "gemini" and gem_local else None),
            "gemini_local": (gem_local if name == "gemini" else None),
            "account": {
                "email":      acct.get("email"),
                "expires_in": acct.get("expires_in"),
                "expires_at": acct.get("expires_at"),
                "auth_type":  acct.get("auth_type"),
                "auth_path":  acct.get("auth_path"),
                "providers":  acct.get("providers"),
                "scopes":     acct.get("scopes"),
                "error":      acct.get("error"),
            },
        })
    return out


def file_progress(run_dir):
    """Return (files_done, files_total) for a run directory.

    files_total: line count of _dirty.txt (preferred) or _all.txt (fallback).
    files_done: count of completed provider artifacts under mco-output/<provider>/result.json,
                else count of provider.json files at run root. Heuristic; clamped to total.
    """
    total = 0
    for fn in ("_dirty.txt", "_all.txt"):
        p = os.path.join(run_dir, fn)
        if os.path.isfile(p):
            try:
                with open(p) as f: total = sum(1 for line in f if line.strip())
                if total: break
            except Exception: pass
    done = 0
    mco = os.path.join(run_dir, "mco-output")
    if os.path.isdir(mco):
        try:
            for entry in os.listdir(mco):
                sub = os.path.join(mco, entry)
                if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "result.json")):
                    done += 1
        except Exception: pass
    if done == 0:
        # Fallback: count <provider>.json files written to run root (legacy v3 layout).
        try:
            for fn in os.listdir(run_dir):
                if fn.endswith(".json") and not fn.startswith("_"):
                    done += 1
        except Exception: pass
    if total and done > total: done = total
    # Legacy runs without prefilter context: no _dirty.txt/_all.txt → total==0.
    # Force done=0 so UI shows "—" (elapsed only) instead of "1/0".
    if total == 0: done = 0
    return done, total


def list_runs():
    runs_dir = os.path.join(ROOT, "audit-reports")
    runs = []
    if os.path.isdir(runs_dir):
        for d in sorted(os.listdir(runs_dir), reverse=True)[:20]:
            full = os.path.join(runs_dir, d)
            if not os.path.isdir(full):
                continue
            rj = os.path.join(full, "_run.json")
            info = {"id": d, "phase": "?", "scope": ".", "started": None, "agents": {}, "findings": 0}
            if os.path.isfile(rj):
                try:
                    with open(rj) as f: data = json.load(f)
                    info["phase"] = data.get("phase") or "done"
                    info["scope"] = data.get("scope", ".")
                    info["started"] = data.get("started_at")
                    info["agents"] = data.get("agents", {})
                    info["findings"] = (data.get("stats", {}).get("findings", {}) or {}).get("total", 0)
                except Exception:
                    pass
            ff = os.path.join(full, "_findings.jsonl")
            if info["findings"] == 0 and os.path.isfile(ff):
                try:
                    with open(ff) as f: info["findings"] = sum(1 for _ in f)
                except Exception: pass
            info["elapsed"] = time_ago(info["started"]) or "—"
            done, total = file_progress(full)
            info["files_done"] = done
            info["files_total"] = total
            # CLI-launched runs (cqc-orchestrate from terminal) write phase="running"
            # to disk but never appear in RUNNING_PROCS. Treat disk phase as live.
            if info["phase"] in ("running", "in_progress"):
                info["live"] = True
            runs.append(info)
    # Overlay UI-spawned runs as live (prepend, dedup by id)
    seen = {r["id"] for r in runs}
    with PROCS_LOCK:
        live = list(RUNNING_PROCS.items())
    live_runs = []
    for rid, rec in live:
        elapsed_s = int(time.time() - rec["started"])
        elapsed = (f"{elapsed_s}s" if elapsed_s < 60
                   else f"{elapsed_s//60}m" if elapsed_s < 3600
                   else f"{elapsed_s//3600}h")
        if rid in seen:
            for r in runs:
                if r["id"] == rid:
                    r["live"] = True
                    r["phase"] = "running"
                    r["elapsed"] = elapsed
                    break
        else:
            done, total = file_progress(os.path.join(runs_dir, rid))
            live_runs.append({
                "id": rid, "phase": "running", "scope": rec["scope"] or ".",
                "started": None, "agents": {c: {"status": "in_progress"} for c in rec["clis"]},
                "findings": 0, "elapsed": elapsed, "live": True, "clis": rec["clis"],
                "files_done": done, "files_total": total,
            })
    return live_runs + runs


def get_state():
    # 2s response cache — SSE clients hit this every 3s; cli_status() is heavy
    now = time.time()
    with _state_lock:
        if _state_cache["data"] and (now - _state_cache["ts"]) < 2:
            return _state_cache["data"]
    runs = list_runs()
    active = [r for r in runs if r.get("live")]
    recent = [r for r in runs if not r.get("live")][:5]
    total_findings = sum(r["findings"] for r in runs)
    spark = []
    by_day = {}
    for r in runs:
        if not r["started"]: continue
        day = r["started"][:10]
        by_day[day] = by_day.get(day, 0) + r["findings"]
    for day in sorted(by_day)[-7:]:
        spark.append(by_day[day])
    usage = load_usage()
    clis_snapshot = cli_status()  # call once, not twice
    state = {
        "version": VERSION,
        "root": ROOT,
        "clis": clis_snapshot,
        "active": active,
        "recent": recent,
        "totals": {"runs": len(runs), "findings": total_findings, "spark": spark,
                   "usd_today": round(sum((c.get("today_usd") or 0) for c in clis_snapshot), 4)},
        "usage_meta": {
            "updated_at": usage.get("updated_at"),
            "errors": usage.get("errors", []),
        },
        "ts": now_iso(),
    }
    with _state_lock:
        _state_cache["data"] = state
        _state_cache["ts"] = now
    return state


def spawn_run(scope, clis_list, mode="parallel", max_parallel=20):
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d__ui-%H%M%S")
    # v4: cqc-parallel is removed; both modes delegate to cqc-orchestrate (MCO).
    cmd = ["cqc-orchestrate", f"--max-parallel={int(max_parallel)}", scope or "."]
    try:
        proc = subprocess.Popen(
            cmd, cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:
        return None, "cqc-orchestrate not found in PATH"
    with PROCS_LOCK:
        RUNNING_PROCS[run_id] = {
            "pid": proc.pid, "scope": scope, "clis": clis_list,
            "started": time.time(), "proc": proc,
        }
    threading.Thread(target=_reap, args=(run_id,), daemon=True).start()
    return run_id, None


def _reap(run_id):
    with PROCS_LOCK:
        rec = RUNNING_PROCS.get(run_id)
    if not rec: return
    rec["proc"].wait()
    with PROCS_LOCK:
        RUNNING_PROCS.pop(run_id, None)


def cancel_run(run_id):
    with PROCS_LOCK:
        rec = RUNNING_PROCS.get(run_id)
    if not rec:
        return False
    try:
        os.killpg(os.getpgid(rec["pid"]), signal.SIGTERM)
    except ProcessLookupError:
        pass
    return True


def safe_run_id(s):
    return bool(re.match(r"^[A-Za-z0-9_\-:.]{1,64}$", s or ""))


CSS = ".tile-blocked{background:#2a0a0a!important;border:2px solid var(--red)!important;opacity:.7}.tile-blocked .name::after{content:'  ⛔ NICHT NUTZBAR';color:var(--red);font-size:10px;letter-spacing:.05em}.tile-hot{border-color:var(--amber)!important;box-shadow:0 0 0 1px var(--amber)}.tile-full{border-color:var(--red)!important;box-shadow:0 0 0 1px var(--red)}.cap-line{position:absolute;top:-2px;width:2px;height:8px;background:var(--amber);z-index:2}.bar{position:relative}#mp-row label{font-size:11px;color:var(--muted);margin-bottom:4px;display:block}#mp{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--fg);padding:8px;border-radius:6px;font:inherit}#refresh{position:relative}#refresh.spinning::before{content:'';position:absolute;left:8px;top:8px;width:14px;height:14px;border:2px solid var(--violet);border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}.usage-stale{color:var(--amber)!important}.tile-tokens{font-size:10px;color:var(--muted);margin-top:2px}.acct-row{display:flex;justify-content:space-between;align-items:center;font-size:10.5px;margin:4px 0;padding:3px 6px;background:rgba(139,92,246,.06);border-radius:4px}.acct-email{color:var(--fg);font-weight:500;font-family:inherit}.acct-exp{color:var(--muted);font-size:10px}.exp-red{color:var(--red)!important;font-weight:600}.exp-amber{color:var(--amber)!important}.sub-row{display:flex;justify-content:space-between;align-items:center;font-size:10.5px;margin:4px 0;padding:3px 6px;background:rgba(34,197,94,.07);border-radius:4px;border-left:2px solid var(--green)}.sub-plan{color:var(--green);font-weight:600}.sub-renew{color:var(--muted);font-size:10px}.relogin-banner{background:#3a0a0a;color:#fca5a5;border-bottom:2px solid var(--red);padding:6px 10px;font-size:11px;font-weight:600;margin:-14px -14px 8px;border-radius:6px 6px 0 0;text-align:center;letter-spacing:.02em}.relogin-banner code{background:rgba(0,0,0,.4);padding:1px 5px;border-radius:3px;font-size:10.5px;color:#fff}.dual-bar{display:flex;align-items:center;gap:6px;margin-top:4px;font-size:10px}.dual-bar label{min-width:18px;color:var(--muted);font-weight:600}.dual-bar .bar{flex:1;height:5px}.dual-pct{min-width:36px;text-align:right;color:var(--fg);font-weight:500}.no-quota-msg{background:rgba(245,158,11,.12);color:var(--amber);padding:5px 7px;border-radius:4px;font-size:10px;margin-top:6px;line-height:1.4}.kv{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:11.5px}.kv-k{color:var(--muted);min-width:120px}.kv-v{color:var(--fg);text-align:right;word-break:break-all;flex:1;margin-left:12px}.set-section{margin:14px 0;padding:12px;background:rgba(255,255,255,.02);border-radius:6px}.set-h{font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:.06em;margin-bottom:10px;font-weight:600}.set-row{display:flex;align-items:center;gap:10px;margin:8px 0}.set-lbl{min-width:90px;font-size:11px;color:var(--fg);font-weight:500}.set-row input[type=range]{flex:1}.set-row input[type=text],.set-row input[type=number]{background:var(--bg);border:1px solid var(--border);color:var(--fg);padding:6px 8px;border-radius:4px;font:inherit;font-size:11px}#drawer-body{background:var(--bg);border:1px solid var(--border);padding:14px;border-radius:6px;max-height:60vh;overflow:auto}#drawer-body h4:first-child{margin-top:0}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.5 'JetBrains Mono','SF Mono',Consolas,monospace;min-width:1280px}.wrap{max-width:1280px;margin:0 auto;padding:20px}header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}header h1{margin:0;font-size:18px;letter-spacing:-.01em}header h1 small{color:var(--muted);font-weight:400;margin-left:8px;font-size:12px}.actions button{background:var(--card);color:var(--fg);border:1px solid var(--border);padding:8px 14px;border-radius:6px;font:inherit;cursor:pointer;margin-left:6px}.actions button:hover{border-color:var(--green)}.actions button.danger:hover{border-color:var(--red)}.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}.tile{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;cursor:pointer}.tile:hover{border-color:var(--violet)}.tile .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.tile .name{font-weight:600;text-transform:lowercase}.dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:var(--slate)}.dot.green{background:var(--green)}.dot.amber{background:var(--amber);animation:pulse 1.4s infinite}.dot.red{background:var(--red)}.dot.slate{background:var(--slate)}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}.tile .meta{color:var(--muted);font-size:11px;line-height:1.7}.tile .meta b{color:var(--fg);font-weight:500}.tile .usd{color:var(--violet);font-weight:600}.bar{height:4px;background:var(--border);border-radius:2px;margin-top:6px;overflow:hidden}.bar>span{display:block;height:100%;background:var(--violet)}section{background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:16px}section h2{margin:0;padding:12px 16px;border-bottom:1px solid var(--border);font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:600}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px 16px;text-align:left;border-bottom:1px solid var(--border)}tr:last-child td{border-bottom:0}tr:hover td{background:rgba(255,255,255,.02)}th{color:var(--muted);font-weight:500;font-size:10px;text-transform:uppercase;letter-spacing:.06em}.row-click{cursor:pointer}.empty{padding:32px 16px;text-align:center;color:var(--muted)}.btn-x{background:transparent;color:var(--muted);border:1px solid var(--border);padding:3px 10px;border-radius:4px;font:inherit;font-size:11px;cursor:pointer}.btn-x:hover{border-color:var(--red);color:var(--red)}.pills{display:flex;gap:6px;padding:14px 16px;flex-wrap:wrap}.pill{padding:6px 12px;border-radius:99px;font-size:11px;background:var(--border);color:var(--muted);cursor:pointer}.pill.green{background:rgba(34,197,94,.18);color:var(--green)}.pill.amber{background:rgba(245,158,11,.18);color:var(--amber)}.pill.red{background:rgba(239,68,68,.18);color:var(--red)}.pill.slate{background:rgba(100,116,139,.18);color:var(--slate)}.split{display:grid;grid-template-columns:1fr 320px;gap:16px;margin-bottom:16px}.spend{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px}.spend .big{font-size:28px;font-weight:700;color:var(--violet);cursor:pointer}.spend .lab{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}.spark{display:flex;gap:3px;align-items:flex-end;height:40px;margin-top:10px}.spark span{flex:1;background:var(--violet);opacity:.7;min-height:2px;border-radius:1px}footer{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;padding:8px 0}.modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:50}.modal.on{display:flex}.modal .box{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;width:420px}.modal h3{margin:0 0 14px;font-size:14px}.modal label{display:block;margin:6px 0;cursor:pointer}.modal input[type=text]{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--fg);padding:8px;border-radius:6px;font:inherit;margin-top:8px}.modal .row{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}.toast{position:fixed;bottom:20px;right:20px;background:var(--card);border:1px solid var(--red);border-radius:8px;padding:10px 14px;font-size:12px;z-index:60;display:none}.toast.on{display:block}.drawer{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:flex-end;justify-content:center;z-index:55}.drawer.on{display:flex}.drawer .panel{background:var(--card);border-top:1px solid var(--border);border-radius:10px 10px 0 0;width:100%;max-width:1280px;max-height:70vh;overflow:auto;padding:16px}.drawer h3{margin:0 0 10px;font-size:13px}.drawer pre{background:var(--bg);border:1px solid var(--border);padding:10px;border-radius:6px;font:12px/1.4 inherit;white-space:pre-wrap;color:var(--muted);max-height:50vh;overflow:auto}.tag{display:inline-block;padding:2px 8px;border-radius:4px;background:var(--border);font-size:10px;color:var(--muted)}"

JS = r"""let STATE=null;let MODE='parallel';const $=(id)=>document.getElementById(id);function fmt(n){return Number(n||0).toLocaleString()}function fmtTok(n){if(!n)return'0';if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(1)+'k';return String(n)}function render(s){STATE=s;$('ver').textContent=s.version;$('foot-l').textContent='connected · '+s.root;const usdToday=(s.totals.usd_today||0).toFixed(2);$('foot-r').textContent='runs:'+s.totals.runs+' · findings:'+fmt(s.totals.findings)+' · today $'+usdToday+' · '+s.ts;const meta=s.usage_meta||{};if(meta.updated_at){const age=Math.floor((Date.now()-new Date(meta.updated_at).getTime())/1000);const stale=age>600;$('usage-meta').innerHTML=`<span class="${stale?'usage-stale':''}">usage: ${age<60?age+'s':Math.floor(age/60)+'m'} ago${stale?' · stale!':''}</span>`;}else{$('usage-meta').textContent='usage: never pulled — click 🔄';}$('tiles').innerHTML=s.clis.map(c=>{const usedPct=Math.min(100,c.used_pct||0);const capPct=Math.max(0,Math.min(100,c.cap_pct||0));let tileClass='tile';if(c.blocked)tileClass+=' tile-blocked';else if(usedPct>=85)tileClass+=' tile-full';else if(usedPct>=60)tileClass+=' tile-hot';const cls=c.blocked?'red':(usedPct>=85?'red':(usedPct>=60?'amber':(c.installed?'green':'slate')));const capTag=c.cap_pct?`<span class="tag">cap ${c.cap_pct}%</span>`:'';const usedTag=usedPct>0?`<span class="tag" style="color:${usedPct>=85?'var(--red)':usedPct>=60?'var(--amber)':'var(--green)'}">${usedPct}% used</span>`:'';const chain=(c.model_chain||[]).length?'<div class="meta" style="font-size:10px;opacity:.6">chain: '+(c.model_chain||[]).join(' → ')+'</div>':'';const modelLine=c.model?`<div class="meta" style="font-size:10px;opacity:.85">↳ active: <b>${c.model}</b></div>`:'';const tokensLine=(c.today_tokens||c.calls_today)?`<div class="tile-tokens">${c.today_tokens?fmtTok(c.today_tokens)+' tok':''}${c.today_tokens&&c.calls_today?' · ':''}${c.calls_today?c.calls_today+' calls':''}</div>`:'';const limitsLine=(c.daily_limit||c.weekly_limit)?`<div class="tile-tokens" title="Plan limits from subscription metadata">${c.daily_limit?'<div>📅 '+c.daily_limit+'</div>':''}${c.weekly_limit?'<div>🗓 '+c.weekly_limit+'</div>':''}</div>`:'';const acct=c.account||{};const sub=c.subscription||{};const reloginBanner=c.needs_relogin?`<div class="relogin-banner">🔐 RE-LOGIN REQUIRED · run <code>${c.name} ${c.name==='claude'?'/login':c.name==='gemini'?'/auth':'auth login'}</code></div>`:'';const subLine=sub.plan?`<div class="sub-row"><span class="sub-plan">💳 ${sub.plan}</span>${sub.subscription_renews_at_estimated||sub.subscription_active_until?`<span class="sub-renew">renews ${(sub.subscription_renews_at_estimated||sub.subscription_active_until||'').slice(0,10)}</span>`:''}</div>`:'';const acctLine=acct.email?`<div class="acct-row"><span class="acct-email">👤 ${acct.email}</span>${acct.expires_in?`<span class="acct-exp ${acct.expires_in.includes('expired')?'exp-red':acct.expires_in.match(/^\d+m$/)?'exp-amber':''}">expires ${acct.expires_in}</span>`:''}</div>`:(acct.error&&!c.blocked?`<div class="acct-row exp-red">⚠ ${acct.error}</div>`:'');const noQuotaTag=c.no_quota_api?'<span class="tag" style="color:var(--amber);border-color:var(--amber)" title="Provider has no quota API">no quota API</span>':'';const fhBar=c.five_hour?`<div class="dual-bar"><label>5h</label><div class="bar"><span style="width:${c.five_hour.utilization}%;background:${c.five_hour.utilization>=85?'var(--red)':'var(--violet)'}"></span></div><span class="dual-pct">${c.five_hour.utilization}%</span></div>`:'';const sdBar=c.seven_day?`<div class="dual-bar"><label>7d</label><div class="bar"><span style="width:${c.seven_day.utilization}%;background:${c.seven_day.utilization>=85?'var(--red)':'var(--violet)'}"></span></div><span class="dual-pct">${c.seven_day.utilization}%</span></div>`:'';const codexRl=c.ratelimits;const codexRlBars=(codexRl&&codexRl.primary)?`<div class="dual-bar"><label>${(codexRl.primary.window_minutes||0)>=10080?'7d':'5h'}</label><div class="bar"><span style="width:${codexRl.primary.used_percent}%;background:${codexRl.primary.used_percent>=85?'var(--red)':'var(--violet)'}"></span></div><span class="dual-pct">${codexRl.primary.used_percent}%</span></div>`:'';const gl=c.gemini_local;const gDaily=(c.name==='gemini'&&gl)?`<div class="dual-bar" title="Local prompts today / 2000 cap (OAuth-personal Ultra)"><label>1d</label><div class="bar"><span style="width:${Math.min(100,gl.used_pct_daily||0)}%;background:${(gl.used_pct_daily||0)>=85?'var(--red)':(gl.used_pct_daily||0)>=60?'var(--amber)':'var(--violet)'}"></span></div><span class="dual-pct">${gl.calls_today||0}/${gl.daily_cap}</span></div>`:'';const gWeekly=(c.name==='gemini'&&gl)?`<div class="dual-bar" title="Local prompts last 7d / 14000 extrapolated cap"><label>7d</label><div class="bar"><span style="width:${Math.min(100,gl.weekly_used_pct||0)}%;background:${(gl.weekly_used_pct||0)>=85?'var(--red)':(gl.weekly_used_pct||0)>=60?'var(--amber)':'var(--violet)'}"></span></div><span class="dual-pct">${gl.calls_7d||0}/${gl.weekly_cap}</span></div>`:'';return `<div class="${tileClass}" data-cli="${c.name}">${reloginBanner}<div class="top"><span class="name">${c.name} ${capTag}${usedTag}${noQuotaTag}</span><span class="dot ${cls}"></span></div>${acctLine}${subLine}<div class="meta"><b>${c.version||'—'}</b> · ${c.plan||'—'} · today <span class="usd">$${(c.today_usd||0).toFixed(2)}</span>${c.no_quota_api?'<div class="no-quota-msg">⚠ Provider hat keine Quota-API · siehe Drawer für Plan-Limits</div>':`<div class="bar"><span style="width:${usedPct}%;background:${usedPct>=capPct?'var(--red)':usedPct>=60?'var(--amber)':'var(--violet)'}"></span><span class="cap-line" style="left:${capPct}%"></span></div>`}</div>${fhBar}${sdBar}${codexRlBars}${gDaily}${gWeekly}${tokensLine}${limitsLine}${modelLine}${chain}</div>`;}).join('');document.querySelectorAll('.tile').forEach(t=>t.onclick=()=>openCli(t.dataset.cli));if(!s.active.length){$('active').innerHTML='<div class="empty">No active runs. Click ▶ Orchestrate or ▶ Run Audit.</div>';}else{$('active').innerHTML='<table><thead><tr><th>Run</th><th>Mode</th><th>Scope</th><th>CLIs</th><th>Elapsed</th><th>Progress</th><th>Findings</th><th></th></tr></thead><tbody>'+s.active.map(r=>{const clis=Object.keys(r.agents||{}).join(' ')||(r.clis||[]).join(' ')||'all';const mode=(r.id||'').includes('orch')?'<span class="tag" style="color:var(--violet);border-color:var(--violet)">orch</span>':'<span class="tag">par</span>';const ft=Number(r.files_total||0),fd=Math.min(Number(r.files_done||0),ft||0);const pct=ft?Math.round((fd/ft)*100):0;const prog=ft?`<progress value="${fd}" max="${ft}" style="width:90px;vertical-align:middle"></progress> <span style="color:var(--muted);font-size:11px">${fd}/${ft} · ${pct}%</span>`:'<span style="color:var(--muted)">—</span>';return `<tr class="row-click" data-id="${r.id}"><td><span class="dot amber"></span> ${r.id}</td><td>${mode}</td><td><span class="tag">${r.scope}</span></td><td>${clis}</td><td>${r.elapsed}</td><td>${prog}</td><td>${fmt(r.findings)}</td><td><button class="btn-x" data-cancel="${r.id}">■ Stop</button></td></tr>`;}).join('')+'</tbody></table>';}document.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=(e)=>{e.stopPropagation();cancelRun(b.dataset.cancel)});document.querySelectorAll('.row-click').forEach(r=>r.onclick=()=>openRun(r.dataset.id));$('recent').innerHTML=s.recent.length?s.recent.map(r=>{const cls={done:'green',failed:'red',timeout:'amber',cancelled:'slate'}[r.phase]||'slate';return `<span class="pill ${cls}" data-rid="${r.id}" title="${r.id}">${r.id.slice(-8)} · ${fmt(r.findings)}f</span>`;}).join(''):'<div class="empty" style="padding:14px">No history yet.</div>';document.querySelectorAll('[data-rid]').forEach(p=>p.onclick=()=>openRun(p.dataset.rid));$('spark').innerHTML=(s.totals.spark.length?s.totals.spark:[0]).map(v=>{const max=Math.max(...s.totals.spark,1);return `<span style="height:${Math.max(2,(v/max)*40)}px"></span>`;}).join('');}async function refresh(){const r=await fetch('/api/state');if(r.ok)render(await r.json());}function startSSE(){const es=new EventSource('/api/stream');es.onmessage=e=>{try{render(JSON.parse(e.data))}catch{}};es.onerror=()=>{$('conn').className='dot red';setTimeout(()=>{es.close();startSSE()},5000);};es.onopen=()=>{$('conn').className='dot green'};}function openModal(mode){MODE=mode||'parallel';$('modal-title').textContent=MODE==='orchestrate'?'▶ Orchestrate (file-sharded, up to 20 parallel)':'▶ Run Audit (4 CLIs, 1 shard each)';$('mp-row').style.display=MODE==='orchestrate'?'block':'none';$('cli-checks').innerHTML=(STATE?STATE.clis:[]).map(c=>{const dis=(!c.installed||c.blocked);const lbl=c.name+(c.blocked?' (BLOCKED · cap 0%)':(c.installed?'':' (not installed)'));return `<label><input type="checkbox" value="${c.name}" ${dis?'disabled':'checked'}> ${lbl}</label>`;}).join('');$('modal').classList.add('on');}function closeModal(){$('modal').classList.remove('on')}async function confirmRun(){const clis=[...document.querySelectorAll('#cli-checks input:checked')].map(i=>i.value);const scope=$('scope').value||'.';const mp=parseInt($('mp').value||'20');const ep=MODE==='orchestrate'?'/api/orchestrate':'/api/run';const r=await fetch(ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope,clis,max_parallel:mp})});const j=await r.json();closeModal();if(!r.ok){toast('Failed: '+(j.error||'unknown'));return}toast('Started '+j.run_id+' ('+j.mode+')');refresh();}async function cancelRun(id){await fetch('/api/cancel/'+encodeURIComponent(id),{method:'POST'});refresh();}async function pauseAll(){if(!STATE)return;for(const r of STATE.active)await cancelRun(r.id);}async function openRun(id){$('drawer-title').textContent='Run '+id;$('drawer-body').textContent='Loading…';$('drawer').classList.add('on');const clis=(STATE&&STATE.clis||[]).filter(c=>c.installed&&!c.blocked).map(c=>c.name);let buf='';for(const c of clis){const r=await fetch('/api/log/'+encodeURIComponent(id)+'/'+c);if(r.ok){const t=await r.text();if(t.trim())buf+='── '+c+' ──\n'+t.slice(-2000)+'\n\n';}}$('drawer-body').textContent=buf||'(no logs yet)';}async function openCli(name){$('drawer-title').textContent='CLI · '+name;$('drawer-body').innerHTML='Loading…';$('drawer').classList.add('on');const cli=(STATE&&STATE.clis||[]).find(c=>c.name===name)||{};const acct=cli.account||{};const recent=(STATE.recent||[]).concat(STATE.active||[]).slice(0,15);const r=await fetch('/api/usage');const usage=r.ok?await r.json():{};const u=(usage.by_cli||{})[name]||{};const sect=(t,h)=>`<h4 style="margin:14px 0 6px;color:var(--violet);font-size:11px;text-transform:uppercase;letter-spacing:.06em">${t}</h4>${h}`;const kv=(k,v,c)=>`<div class="kv"><span class="kv-k">${k}</span><span class="kv-v ${c||''}">${v||'—'}</span></div>`;const acctHtml=sect('Account',`${kv('Email',acct.email||'(not logged in)',acct.email?'':'exp-red')}${kv('Plan',cli.plan)}${kv('Auth type',acct.auth_type)}${kv('Expires',acct.expires_at?acct.expires_at+' ('+acct.expires_in+')':'—',acct.expires_in&&acct.expires_in.includes('expired')?'exp-red':'')}${acct.account_id?kv('Account ID',acct.account_id):''}${kv('Auth file',acct.auth_path||'—')}${acct.providers?kv('Providers',acct.providers.map(p=>`${p.name} (${p.type}${p.has_key?', has-key':''})`).join(', ')):''}${acct.scopes?kv('Scopes',acct.scopes.join(', ')):''}${acct.error?kv('Error',acct.error,'exp-red'):''}`);const sub=cli.subscription||{};const subHtml=sub.plan?sect('💳 Subscription',`${kv('Plan',sub.plan)}${kv('Tier',sub.tier)}${sub.price_usd_month?kv('Price','$'+sub.price_usd_month+'/mo'):''}${kv('Billing',sub.billing)}${kv('Subscription started',sub.subscription_started_at||sub.subscription_active_start)}${kv('Renews / expires at',sub.subscription_renews_at_estimated?sub.subscription_renews_at_estimated+' (estimated)':sub.subscription_active_until)}${kv('5h reset',sub.reset_5h)}${kv('Weekly reset',sub.reset_weekly)}${sub.limits?kv('Limits','<pre style=\"white-space:pre-wrap;font-size:10.5px;color:var(--fg);margin:0\">'+Object.entries(sub.limits).map(([k,v])=>k+': '+v).join('\\n')+'</pre>'):''}${sub.console_url?kv('Console','<a href=\"'+sub.console_url+'\" target=\"_blank\" style=\"color:var(--violet)\">'+sub.console_url+'</a>'):''}${kv('Source',sub.source)}`):'';const usageHtml=sect('Usage today',`${kv('Used %',cli.used_pct+'%')}${kv('Cap %',cli.cap_pct+'%')}${kv('Today $',`$${(cli.today_usd||0).toFixed(4)}`)}${kv('Tokens',cli.today_tokens?cli.today_tokens.toLocaleString():'—')}${kv('Calls',cli.calls_today||'—')}${kv('Model used',cli.model||'—')}${kv('Model chain',(cli.model_chain||[]).join(' → '))}${u.pulled_at?kv('Pulled at',u.pulled_at+' ('+(u.pull_elapsed_s||'?')+'s)'):''}${u.all_time_usd?kv('All time $',`$${u.all_time_usd}`):''}${u.all_time_tokens?kv('All time tok',u.all_time_tokens.toLocaleString()):''}${u.raw?kv('Raw source',JSON.stringify(u.raw)):''}`);const cliHtml=sect('CLI binary',`${kv('Installed',cli.installed?'yes':'no')}${kv('Version',cli.version||'—')}${kv('Blocked',cli.blocked?'⛔ YES (cap=0)':'no',cli.blocked?'exp-red':'')}`);const recHtml=sect('Recent runs',recent.length?recent.map(r=>{const a=(r.agents||{})[name];const sts=a?(typeof a==='object'?a.status:a):'—';const cls=sts==='done'?'pill green':sts==='failed'?'pill red':sts==='in_progress'?'pill amber':'pill slate';return `<div style="margin:3px 0"><span class="${cls}" style="margin-right:8px">${sts}</span><a href="javascript:openRun('${r.id}')" style="color:var(--fg)">${r.id}</a> · <span style="color:var(--muted)">${r.scope}</span></div>`;}).join(''):'(none)');$('drawer-body').innerHTML=acctHtml+subHtml+usageHtml+cliHtml+recHtml;}
function fmtDuration(s){s=Number(s||0);if(s<60)return s+'s';if(s<3600){const m=Math.floor(s/60),r=s%60;return r?m+'m '+r+'s':m+' min';}const h=Math.floor(s/3600),m=Math.floor((s%3600)/60);return m?h+'h '+m+'m':h+' h';}
async function openSettings(){const r=await fetch('/api/budget');const b=r.ok?await r.json():{};const cli_inputs=Object.keys(b.caps_pct||{}).map(c=>`<div class="set-row"><label class="set-lbl">${c}</label><input type="range" min="0" max="100" step="5" value="${b.caps_pct[c]}" id="cap-${c}" oninput="document.getElementById('cap-v-${c}').textContent=this.value+'%'"><span id="cap-v-${c}" style="min-width:40px;color:var(--violet);font-weight:600">${b.caps_pct[c]}%</span></div>`).join('');const chain_inputs=Object.keys(b.model_chains||{}).map(c=>`<div class="set-row"><label class="set-lbl">${c}</label><input type="text" id="chain-${c}" value="${(b.model_chains[c]||[]).join(', ')}" style="flex:1"></div>`).join('');const mrs=b.max_run_seconds||1800;const sts=b.stall_timeout_seconds||240;$('settings-body').innerHTML=`<div class="set-section"><div class="set-h">Wochenlimit pro CLI (% von voller Quota; 0 = HARD BLOCK)</div>${cli_inputs}</div><div class="set-section"><div class="set-h">⏱ Runtime Limits (Agent Hard-Cap pro Run)</div><div class="set-row" title="Hard cap on the entire audit run; passed to mco --review-hard-timeout"><label class="set-lbl">Max Run</label><input type="range" min="60" max="7200" step="60" value="${mrs}" id="max-run" oninput="document.getElementById('max-run-v').textContent=fmtDuration(this.value)"><span id="max-run-v" style="min-width:60px;color:var(--violet);font-weight:600">${fmtDuration(mrs)}</span></div><div class="set-row" title="Per-provider stall before kill; passed to mco --stall-timeout"><label class="set-lbl">Stall Timeout</label><input type="range" min="60" max="900" step="30" value="${sts}" id="stall-to" oninput="document.getElementById('stall-to-v').textContent=this.value+'s'"><span id="stall-to-v" style="min-width:60px;color:var(--violet);font-weight:600">${sts}s</span></div></div><div class="set-section"><div class="set-h">Model chains (comma-separated, primary → fallback → ...)</div>${chain_inputs}</div><div class="set-section"><div class="set-h">Parallel max</div><div class="set-row"><label class="set-lbl">parallel_max</label><input type="number" id="parallel-max" min="1" max="50" value="${b.parallel_max||20}" style="width:80px"></div></div>`;$('settings-modal').classList.add('on');}
function closeSettings(){$('settings-modal').classList.remove('on')}
async function saveSettings(){const caps={};document.querySelectorAll('[id^=cap-]').forEach(el=>{if(el.id.startsWith('cap-v-'))return;const c=el.id.slice(4);caps[c]=parseInt(el.value);});const chains={};document.querySelectorAll('[id^=chain-]').forEach(el=>{const c=el.id.slice(6);chains[c]=el.value.split(',').map(s=>s.trim()).filter(Boolean);});const pm=parseInt($('parallel-max').value)||20;const mrs=parseInt($('max-run').value)||1800;const sts=parseInt($('stall-to').value)||240;const r=await fetch('/api/budget',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({caps_pct:caps,model_chains:chains,parallel_max:pm,max_run_seconds:mrs,stall_timeout_seconds:sts})});const j=await r.json();if(j.ok){toast('💾 Budget saved · Max Run: '+fmtDuration(mrs)+' · Stall: '+sts+'s');closeSettings();refresh();}else{toast('Save failed: '+(j.error||'unknown'));}}function closeDrawer(){$('drawer').classList.remove('on')}function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('on');setTimeout(()=>t.classList.remove('on'),5000)}async function refreshUsage(){const btn=$('refresh');btn.classList.add('spinning');btn.disabled=true;try{const r=await fetch('/api/usage/refresh',{method:'POST'});const j=await r.json();if(j.ok){toast('✓ Usage refreshed');refresh();}else{toast('Refresh failed: '+(j.error||j.stderr||'unknown'));}}catch(e){toast('Refresh error: '+e.message);}finally{btn.classList.remove('spinning');btn.disabled=false;}}$('refresh').onclick=refreshUsage;$('settings').onclick=openSettings;$('orch').onclick=()=>openModal('orchestrate');$('run').onclick=()=>openModal('parallel');$('pause').onclick=pauseAll;document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal();closeSettings();closeDrawer();}});['modal','settings-modal'].forEach(id=>{const m=$(id);if(m)m.addEventListener('click',e=>{if(e.target===m){if(id==='modal')closeModal();else closeSettings();}});});refresh();startSSE();"""

BODY = '<div class="wrap"><header><h1>cqc · <span class="dot green" id="conn"></span> live <small id="ver"></small> <small id="usage-meta" style="margin-left:12px"></small></h1><div class="actions"><button id="settings" title="Edit caps & model chains">⚙ Settings</button><button id="refresh" title="Pull real ccusage data">🔄 Refresh</button><button id="orch" style="border-color:var(--violet);color:var(--violet)">▶ Orchestrate (20p)</button><button id="run">▶ Run Audit</button><button class="danger" id="pause">⏸ Pause All</button></div></header><div class="tiles" id="tiles"></div><section><h2>Active runs</h2><div id="active"></div></section><div class="split"><section><h2>Recent runs</h2><div class="pills" id="recent"></div></section><div class="spend"><div class="lab">Total spend (7d)</div><div class="big" id="spend-total">$0.00</div><div class="spark" id="spark"></div></div></div><footer><span id="foot-l">connecting…</span><span id="foot-r"></span></footer></div><div class="modal" id="modal"><div class="box"><h3 id="modal-title">Run audit</h3><div id="cli-checks"></div><input type="text" id="scope" value="." placeholder="scope (default .)"><div id="mp-row" style="margin-top:8px;display:none"><label>Max parallel agents</label><input type="number" id="mp" value="20" min="1" max="50"></div><div class="row"><button class="btn-x" onclick="closeModal()">Cancel</button><button onclick="confirmRun()">Confirm</button></div></div></div><div class="drawer" id="drawer"><div class="panel"><h3 id="drawer-title"></h3><div id="drawer-body"></div><div style="text-align:right;margin-top:10px"><button class="btn-x" onclick="closeDrawer()">Close</button></div></div></div><div class="modal" id="settings-modal"><div class="box" style="width:560px;max-height:80vh;overflow:auto"><h3>⚙ Budget &amp; Model Chains</h3><div id="settings-body">Loading…</div><div class="row"><button class="btn-x" onclick="closeSettings()">Cancel</button><button onclick="saveSettings()">💾 Save</button></div></div></div><div class="toast" id="toast"></div>'

VARS = "--green:#22c55e;--amber:#f59e0b;--red:#ef4444;--slate:#64748b;--violet:#8b5cf6;--bg:#0a0d12;--card:#14181f;--border:#2a2f3b;--fg:#e6e8eb;--muted:#8b93a1"

HTML = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>cqc · live</title><style>:root{{{VARS}}}{CSS}</style></head><body>{BODY}<script>{JS}</script></body></html>'


def _send_json(handler, code, payload):
    body = json.dumps(payload).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence stdout
        return

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/state":
            _send_json(self, 200, get_state()); return
        if path == "/api/metrics":
            _send_json(self, 200, get_metrics()); return
        if path == "/api/usage":
            _send_json(self, 200, load_usage()); return
        if path == "/api/budget":
            _send_json(self, 200, load_budget()); return
        m = re.match(r"^/api/account/([a-z]+)$", path)
        if m:
            cli = m.group(1)
            if cli not in CLIS: _send_json(self, 400, {"error":"unknown cli"}); return
            _send_json(self, 200, get_account_info(cli)); return
        if path == "/api/stream":
            self._stream(); return
        m = re.match(r"^/api/log/([^/]+)/([^/]+)$", path)
        if m:
            self._log(m.group(1), m.group(2)); return
        self.send_response(404); self.end_headers()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if path in ("/api/run", "/api/orchestrate"):
            try:
                body = json.loads(raw.decode() or "{}")
            except Exception:
                _send_json(self, 400, {"error": "invalid json"}); return
            scope = (body.get("scope") or ".").strip()
            if not re.match(r"^[A-Za-z0-9_./\-]{1,200}$", scope):
                _send_json(self, 400, {"error": "invalid scope"}); return
            # HARD-BLOCK claude unless cap > 0
            metrics = get_metrics()
            clis_in = []
            for c in (body.get("clis") or []):
                if c not in CLIS: continue
                if c == "claude" and metrics["by_cli"].get("claude", {}).get("blocked"):
                    continue   # silently drop
                clis_in.append(c)
            mode = "orchestrate" if path == "/api/orchestrate" else "parallel"
            mp = int(body.get("max_parallel") or metrics.get("parallel_max", 20))
            run_id, err = spawn_run(scope, clis_in, mode=mode, max_parallel=mp)
            if err: _send_json(self, 500, {"error": err}); return
            _send_json(self, 200, {"run_id": run_id, "mode": mode, "max_parallel": mp}); return
        m = re.match(r"^/api/cancel/(.+)$", path)
        if m:
            rid = m.group(1)
            if not safe_run_id(rid):
                _send_json(self, 400, {"error": "bad id"}); return
            ok = cancel_run(rid)
            _send_json(self, 200, {"cancelled": ok}); return
        if path == "/api/budget":
            try:
                body = json.loads(raw.decode() or "{}")
            except Exception:
                _send_json(self, 400, {"error": "invalid json"}); return
            # Validate
            current = load_budget()
            allowed_keys = {"caps_pct", "models", "model_chains", "parallel_max",
                            "shard_max_files", "max_run_seconds", "stall_timeout_seconds"}
            for k, v in body.items():
                if k in allowed_keys: current[k] = v
            # Validate caps are 0-100 ints
            for cli, cap in (current.get("caps_pct") or {}).items():
                try:
                    cap = int(cap)
                    if cap < 0 or cap > 100:
                        _send_json(self, 400, {"error": f"cap {cli}={cap} out of [0,100]"}); return
                    current["caps_pct"][cli] = cap
                except (TypeError, ValueError):
                    _send_json(self, 400, {"error": f"cap {cli} not numeric"}); return
            # Validate runtime sliders (clamp to safe ranges)
            try:
                mrs = int(current.get("max_run_seconds", 1800))
                if mrs < 60 or mrs > 7200:
                    _send_json(self, 400, {"error": f"max_run_seconds={mrs} out of [60,7200]"}); return
                current["max_run_seconds"] = mrs
            except (TypeError, ValueError):
                _send_json(self, 400, {"error": "max_run_seconds not numeric"}); return
            try:
                sts = int(current.get("stall_timeout_seconds", 240))
                if sts < 60 or sts > 900:
                    _send_json(self, 400, {"error": f"stall_timeout_seconds={sts} out of [60,900]"}); return
                current["stall_timeout_seconds"] = sts
            except (TypeError, ValueError):
                _send_json(self, 400, {"error": "stall_timeout_seconds not numeric"}); return
            current["version"] = current.get("version", 2)
            try:
                tmp = BUDGET_FILE + ".tmp"
                with open(tmp, "w") as f: json.dump(current, f, indent=2)
                os.replace(tmp, BUDGET_FILE)
            except Exception as e:
                _send_json(self, 500, {"error": f"write failed: {e}"}); return
            _send_json(self, 200, {"ok": True, "saved_to": BUDGET_FILE, "budget": current}); return
        if path == "/api/usage/refresh":
            try:
                r = subprocess.run(["cqc-usage-pull"], capture_output=True, text=True, timeout=120)
                ok = r.returncode == 0
                # Parse the JSON the script printed
                summary = None
                try:
                    idx = r.stdout.find("{")
                    if idx >= 0: summary = json.loads(r.stdout[idx:])
                except Exception: pass
                _send_json(self, 200 if ok else 500, {"ok": ok, "summary": summary,
                                                        "stderr": r.stderr[-500:] if r.stderr else None})
            except Exception as e:
                _send_json(self, 500, {"ok": False, "error": str(e)})
            return
        self.send_response(404); self.end_headers()

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            while True:
                data = json.dumps(get_state())
                self.wfile.write(b"data: " + data.encode() + b"\n\n")
                self.wfile.flush()
                time.sleep(3)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _log(self, run_id, cli):
        if not safe_run_id(run_id) or cli not in CLIS:
            self.send_response(400); self.end_headers(); return
        path = os.path.join(ROOT, "audit-reports", run_id, "logs", f"{cli}.log")
        if not os.path.isfile(path):
            self.send_response(404); self.end_headers(); return
        with open(path, "rb") as f: data = f.read()[-50000:]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    bind = os.environ.get("CQC_BIND", "0.0.0.0")
    httpd = ThreadedServer((bind, PORT), Handler)
    print(f"  cqc-ui {VERSION}  bind={bind}:{PORT}  root={ROOT}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        with PROCS_LOCK:
            for rid, rec in list(RUNNING_PROCS.items()):
                try: os.killpg(os.getpgid(rec["pid"]), signal.SIGTERM)
                except Exception: pass


if __name__ == "__main__":
    main()
