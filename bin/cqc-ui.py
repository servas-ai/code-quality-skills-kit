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
VERSION = os.environ.get("CQC_VERSION", "v3.13")
CLIS = ("claude", "gemini", "opencode", "codex")

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


def cli_status():
    out = []
    for name in CLIS:
        installed, ver = False, None
        try:
            r = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=2)
            installed = r.returncode == 0
            m = re.search(r"(\d+\.\d+\.\d+)", (r.stdout or "") + (r.stderr or ""))
            ver = m.group(1) if m else None
        except Exception:
            pass
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
        out.append({
            "name": name, "installed": installed, "version": ver,
            "plan": plan, "today_usd": 0.0, "week_pct": 0,
        })
    return out


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
            live_runs.append({
                "id": rid, "phase": "running", "scope": rec["scope"] or ".",
                "started": None, "agents": {c: {"status": "in_progress"} for c in rec["clis"]},
                "findings": 0, "elapsed": elapsed, "live": True, "clis": rec["clis"],
            })
    return live_runs + runs


def get_state():
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
    return {
        "version": VERSION,
        "root": ROOT,
        "clis": cli_status(),
        "active": active,
        "recent": recent,
        "totals": {"runs": len(runs), "findings": total_findings, "spark": spark},
        "ts": now_iso(),
    }


def spawn_run(scope, clis_list):
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d__ui-%H%M%S")
    cmd = ["cqc-parallel"]
    if clis_list:
        cmd.append(f"--clis={','.join(clis_list)}")
    cmd.append(scope or ".")
    try:
        proc = subprocess.Popen(
            cmd, cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:
        return None, "cqc-parallel not found in PATH"
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


CSS = "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.5 'JetBrains Mono','SF Mono',Consolas,monospace;min-width:1280px}.wrap{max-width:1280px;margin:0 auto;padding:20px}header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}header h1{margin:0;font-size:18px;letter-spacing:-.01em}header h1 small{color:var(--muted);font-weight:400;margin-left:8px;font-size:12px}.actions button{background:var(--card);color:var(--fg);border:1px solid var(--border);padding:8px 14px;border-radius:6px;font:inherit;cursor:pointer;margin-left:6px}.actions button:hover{border-color:var(--green)}.actions button.danger:hover{border-color:var(--red)}.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}.tile{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;cursor:pointer}.tile:hover{border-color:var(--violet)}.tile .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.tile .name{font-weight:600;text-transform:lowercase}.dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:var(--slate)}.dot.green{background:var(--green)}.dot.amber{background:var(--amber);animation:pulse 1.4s infinite}.dot.red{background:var(--red)}.dot.slate{background:var(--slate)}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}.tile .meta{color:var(--muted);font-size:11px;line-height:1.7}.tile .meta b{color:var(--fg);font-weight:500}.tile .usd{color:var(--violet);font-weight:600}.bar{height:4px;background:var(--border);border-radius:2px;margin-top:6px;overflow:hidden}.bar>span{display:block;height:100%;background:var(--violet)}section{background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:16px}section h2{margin:0;padding:12px 16px;border-bottom:1px solid var(--border);font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:600}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px 16px;text-align:left;border-bottom:1px solid var(--border)}tr:last-child td{border-bottom:0}tr:hover td{background:rgba(255,255,255,.02)}th{color:var(--muted);font-weight:500;font-size:10px;text-transform:uppercase;letter-spacing:.06em}.row-click{cursor:pointer}.empty{padding:32px 16px;text-align:center;color:var(--muted)}.btn-x{background:transparent;color:var(--muted);border:1px solid var(--border);padding:3px 10px;border-radius:4px;font:inherit;font-size:11px;cursor:pointer}.btn-x:hover{border-color:var(--red);color:var(--red)}.pills{display:flex;gap:6px;padding:14px 16px;flex-wrap:wrap}.pill{padding:6px 12px;border-radius:99px;font-size:11px;background:var(--border);color:var(--muted);cursor:pointer}.pill.green{background:rgba(34,197,94,.18);color:var(--green)}.pill.amber{background:rgba(245,158,11,.18);color:var(--amber)}.pill.red{background:rgba(239,68,68,.18);color:var(--red)}.pill.slate{background:rgba(100,116,139,.18);color:var(--slate)}.split{display:grid;grid-template-columns:1fr 320px;gap:16px;margin-bottom:16px}.spend{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px}.spend .big{font-size:28px;font-weight:700;color:var(--violet);cursor:pointer}.spend .lab{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}.spark{display:flex;gap:3px;align-items:flex-end;height:40px;margin-top:10px}.spark span{flex:1;background:var(--violet);opacity:.7;min-height:2px;border-radius:1px}footer{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;padding:8px 0}.modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:50}.modal.on{display:flex}.modal .box{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;width:420px}.modal h3{margin:0 0 14px;font-size:14px}.modal label{display:block;margin:6px 0;cursor:pointer}.modal input[type=text]{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--fg);padding:8px;border-radius:6px;font:inherit;margin-top:8px}.modal .row{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}.toast{position:fixed;bottom:20px;right:20px;background:var(--card);border:1px solid var(--red);border-radius:8px;padding:10px 14px;font-size:12px;z-index:60;display:none}.toast.on{display:block}.drawer{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:flex-end;justify-content:center;z-index:55}.drawer.on{display:flex}.drawer .panel{background:var(--card);border-top:1px solid var(--border);border-radius:10px 10px 0 0;width:100%;max-width:1280px;max-height:70vh;overflow:auto;padding:16px}.drawer h3{margin:0 0 10px;font-size:13px}.drawer pre{background:var(--bg);border:1px solid var(--border);padding:10px;border-radius:6px;font:12px/1.4 inherit;white-space:pre-wrap;color:var(--muted);max-height:50vh;overflow:auto}.tag{display:inline-block;padding:2px 8px;border-radius:4px;background:var(--border);font-size:10px;color:var(--muted)}"

JS = r"""let STATE=null;const $=(id)=>document.getElementById(id);function fmt(n){return Number(n||0).toLocaleString()}function render(s){STATE=s;$('ver').textContent=s.version;$('foot-l').textContent='connected · '+s.root;$('foot-r').textContent='runs:'+s.totals.runs+' · findings:'+fmt(s.totals.findings)+' · '+s.ts;$('tiles').innerHTML=s.clis.map(c=>{const cls=c.installed?'green':'slate';const pct=Math.min(100,c.week_pct||0);return `<div class="tile" data-cli="${c.name}"><div class="top"><span class="name">${c.name}</span><span class="dot ${cls}"></span></div><div class="meta"><b>${c.version||'—'}</b> · ${c.plan} · today <span class="usd">$${(c.today_usd||0).toFixed(2)}</span><div class="bar"><span style="width:${pct}%"></span></div></div></div>`;}).join('');document.querySelectorAll('.tile').forEach(t=>t.onclick=()=>openCli(t.dataset.cli));if(!s.active.length){$('active').innerHTML='<div class="empty">No active runs. Click ▶ Run Audit.</div>';}else{$('active').innerHTML='<table><thead><tr><th>Run</th><th>Scope</th><th>CLIs</th><th>Elapsed</th><th>Findings</th><th></th></tr></thead><tbody>'+s.active.map(r=>{const clis=Object.keys(r.agents||{}).join(' ')||(r.clis||[]).join(' ')||'all';return `<tr class="row-click" data-id="${r.id}"><td><span class="dot amber"></span> ${r.id}</td><td><span class="tag">${r.scope}</span></td><td>${clis}</td><td>${r.elapsed}</td><td>${fmt(r.findings)}</td><td><button class="btn-x" data-cancel="${r.id}">■ Stop</button></td></tr>`;}).join('')+'</tbody></table>';}document.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=(e)=>{e.stopPropagation();cancelRun(b.dataset.cancel)});document.querySelectorAll('.row-click').forEach(r=>r.onclick=()=>openRun(r.dataset.id));$('recent').innerHTML=s.recent.length?s.recent.map(r=>{const cls={done:'green',failed:'red',timeout:'amber',cancelled:'slate'}[r.phase]||'slate';return `<span class="pill ${cls}" data-rid="${r.id}" title="${r.id}">${r.id.slice(-8)} · ${fmt(r.findings)}f</span>`;}).join(''):'<div class="empty" style="padding:14px">No history yet.</div>';document.querySelectorAll('[data-rid]').forEach(p=>p.onclick=()=>openRun(p.dataset.rid));$('spark').innerHTML=(s.totals.spark.length?s.totals.spark:[0]).map(v=>{const max=Math.max(...s.totals.spark,1);return `<span style="height:${Math.max(2,(v/max)*40)}px"></span>`;}).join('');}async function refresh(){const r=await fetch('/api/state');if(r.ok)render(await r.json());}function startSSE(){const es=new EventSource('/api/stream');es.onmessage=e=>{try{render(JSON.parse(e.data))}catch{}};es.onerror=()=>{$('conn').className='dot red';setTimeout(()=>{es.close();startSSE()},5000);};es.onopen=()=>{$('conn').className='dot green'};}function openModal(){$('cli-checks').innerHTML=(STATE?STATE.clis:[]).map(c=>`<label><input type="checkbox" value="${c.name}" ${c.installed?'checked':'disabled'}> ${c.name}${c.installed?'':' (not installed)'}</label>`).join('');$('modal').classList.add('on');}function closeModal(){$('modal').classList.remove('on')}async function confirmRun(){const clis=[...document.querySelectorAll('#cli-checks input:checked')].map(i=>i.value);const scope=$('scope').value||'.';const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope,clis})});const j=await r.json();closeModal();if(!r.ok){toast('Failed: '+(j.error||'unknown'));return}refresh();}async function cancelRun(id){await fetch('/api/cancel/'+encodeURIComponent(id),{method:'POST'});refresh();}async function pauseAll(){if(!STATE)return;for(const r of STATE.active)await cancelRun(r.id);}async function openRun(id){$('drawer-title').textContent='Run '+id;$('drawer-body').textContent='Loading…';$('drawer').classList.add('on');const clis=(STATE&&STATE.clis||[]).filter(c=>c.installed).map(c=>c.name);let buf='';for(const c of clis){const r=await fetch('/api/log/'+encodeURIComponent(id)+'/'+c);if(r.ok){const t=await r.text();if(t.trim())buf+='── '+c+' ──\n'+t.slice(-2000)+'\n\n';}}$('drawer-body').textContent=buf||'(no logs yet)';}function openCli(name){$('drawer-title').textContent='CLI · '+name;const recent=(STATE.recent||[]).concat(STATE.active||[]).slice(0,20);const lines=recent.map(r=>{const a=(r.agents||{})[name];return r.id+' · '+(a?a.status:'—')}).join('\n');$('drawer-body').textContent=lines||'(no recent invocations)';$('drawer').classList.add('on');}function closeDrawer(){$('drawer').classList.remove('on')}function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('on');setTimeout(()=>t.classList.remove('on'),5000)}$('run').onclick=openModal;$('pause').onclick=pauseAll;refresh();startSSE();"""

BODY = '<div class="wrap"><header><h1>cqc · <span class="dot green" id="conn"></span> live <small id="ver"></small></h1><div class="actions"><button id="run">▶ Run Audit</button><button class="danger" id="pause">⏸ Pause All</button></div></header><div class="tiles" id="tiles"></div><section><h2>Active runs</h2><div id="active"></div></section><div class="split"><section><h2>Recent runs</h2><div class="pills" id="recent"></div></section><div class="spend"><div class="lab">Total spend (7d)</div><div class="big" id="spend-total">$0.00</div><div class="spark" id="spark"></div></div></div><footer><span id="foot-l">connecting…</span><span id="foot-r"></span></footer></div><div class="modal" id="modal"><div class="box"><h3>Run audit</h3><div id="cli-checks"></div><input type="text" id="scope" value="." placeholder="scope (default .)"><div class="row"><button class="btn-x" onclick="closeModal()">Cancel</button><button onclick="confirmRun()">Confirm</button></div></div></div><div class="drawer" id="drawer"><div class="panel"><h3 id="drawer-title"></h3><pre id="drawer-body"></pre><div style="text-align:right;margin-top:10px"><button class="btn-x" onclick="closeDrawer()">Close</button></div></div></div><div class="toast" id="toast"></div>'

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
        if path == "/api/run":
            try:
                body = json.loads(raw.decode() or "{}")
            except Exception:
                _send_json(self, 400, {"error": "invalid json"}); return
            scope = (body.get("scope") or ".").strip()
            if not re.match(r"^[A-Za-z0-9_./\-]{1,200}$", scope):
                _send_json(self, 400, {"error": "invalid scope"}); return
            clis_in = [c for c in (body.get("clis") or []) if c in CLIS]
            run_id, err = spawn_run(scope, clis_in)
            if err: _send_json(self, 500, {"error": err}); return
            _send_json(self, 200, {"run_id": run_id}); return
        m = re.match(r"^/api/cancel/(.+)$", path)
        if m:
            rid = m.group(1)
            if not safe_run_id(rid):
                _send_json(self, 400, {"error": "bad id"}); return
            ok = cancel_run(rid)
            _send_json(self, 200, {"cancelled": ok}); return
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
