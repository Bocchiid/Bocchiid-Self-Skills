#!/usr/bin/env python3
"""Run and record experiment actions with a small, portable policy.

The policy is intentionally conservative.  It is not a security boundary (a
determined command can evade regexes), but it catches the obvious destructive,
elevated, outward-facing and credential-handling actions before an agent runs
them without thinking.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _durable

DENY_PATTERNS = [
    r"\brm\s+-rf\s+/(?:\s|$)",
    r"\brm\s+-rf\s+/\*",
    r"\bformat\s+[a-zA-Z]:",
    r"\bmkfs(?:\.|\s)",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bdiskpart\b",
    r"\bbcdedit\b",
    r"\breg\s+delete\b",
    r"\bdel\s+/[fsq].*[a-zA-Z]:\\",
    r"\bRemove-Item\b.*-Recurse.*-Force\s+[a-zA-Z]:\\",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    # Never kill the process that may be hosting the agent or its terminal.
    r"(?i)\btaskkill\b.*\b(?:powershell|pwsh|cmd|bash|python|python3|node|claude|code)\b",
    r"(?i)\bStop-Process\b.*\b(?:powershell|pwsh|cmd|bash|python|python3|node|claude|code)\b",
    r"(?i)\b(?:pkill|killall)\b.*\b(?:powershell|pwsh|bash|python|python3|node|claude)\b",
    # Global environment changes are not the worker's business.
    r"(?i)\bsetx\b",
    r"(?i)\[Environment\]::SetEnvironmentVariable",
    r"(?i)\bSet-ItemProperty\b.*\b(?:Environment|profile)\b",
    r"(?i)>>?\s*[^\s]*(?:\.bashrc|\.zshrc|\.profile|Microsoft\.PowerShell_profile\.ps1)",
    r"(?i)\bpip3?\s+install\b.*--user\b",
]
DESTRUCTIVE_PATTERNS = [
    r"\brm\b", r"\bdel\b", r"\brmdir\b", r"\btruncate\b",
    r"\bmv\b", r"\bcp\b", r">\s*\S+",
]
ELEVATED_PATTERNS = [
    r"\bsudo\b", r"\brunas\b", r"\bStart-Process\b.*-Verb\s+RunAs",
    r"\bpip\s+install\b", r"\bnpm\s+install\s+-g\b",
    r"\bapt(?:-get)?\s+install\b", r"\bchoco\s+install\b",
    r"\bwinget\s+install\b", r"\byum\s+install\b", r"\bdnf\s+install\b",
]
OUTWARD_PATTERNS = [
    r"\bgit\s+push\b", r"\bgit\s+remote\s+(?:add|set-url)\b",
    r"\bgh\s+(?:pr|issue)\s+create\b", r"\bnpm\s+publish\b",
    r"\bdocker\s+push\b", r"\btwine\s+upload\b", r"\bscp\b",
    r"\bcurl\b.*(?:-X\s*(?:POST|PUT|DELETE)|--data|--upload-file)",
    r"\bwget\b", r"\bmail\b", r"\bsendmail\b",
]
CREDENTIAL_PATTERNS = [
    r"(?i)\b(?:password|passwd|token|secret|api[_-]?key|authorization)\b",
]
PROCESS_PATTERNS = [
    r"\btaskkill\b", r"\bStop-Process\b", r"\bkill\b", r"\bpkill\b",
    r"\bkillall\b", r"\bTerminateProcess\b", r"\bwmic\s+process\b",
]
PROTECTED_PROCESS_PATTERNS = [
    r"(?i)\b(?:powershell|pwsh|cmd|bash|WindowsTerminal|wt|python|python3|node|claude|code)\b",
]
READ_PATTERNS = [
    r"^\s*(?:ls|dir|cat|type|head|tail|less|more|find|grep|rg|"
    r"git\s+(?:status|log|diff|show)|python\s+--version|"
    r"pip\s+(?:list|show)|ping|ipconfig|ifconfig|netstat|ss|ps|"
    r"tasklist|whoami|hostname|uname)\b",
]
SAFE_EXEC_PATTERNS = [
    r"^\s*(?:python|python3|echo|printf|mn|ovs-|tshark|tcpdump|"
    r"iperf|ping|git\s+(?:status|diff|log|show)|ls|dir|cat|type|"
    r"head|tail|grep|rg|find)\b",
]
REDACT_RE = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization)"
    r"\s*([=:])\s*([^\s,;]+)"
)


def _matches(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE | re.MULTILINE)]


def classify(command: str) -> dict:
    deny = _matches(DENY_PATTERNS, command)
    destructive = _matches(DESTRUCTIVE_PATTERNS, command)
    elevated = _matches(ELEVATED_PATTERNS, command)
    outward = _matches(OUTWARD_PATTERNS, command)
    credential = _matches(CREDENTIAL_PATTERNS, command)
    process = _matches(PROCESS_PATTERNS, command)
    protected = _matches(PROTECTED_PROCESS_PATTERNS, command) if process else []
    read = _matches(READ_PATTERNS, command)
    safe_exec = _matches(SAFE_EXEC_PATTERNS, command)
    if credential:
        # A credential mention alone is not a credential use, but it deserves
        # a confirmation before it lands in a log.
        credential_confirm = True
    else:
        credential_confirm = False
    if deny:
        category = "deny"
    elif process:
        category = "process"
    elif destructive:
        category = "destructive"
    elif elevated:
        category = "elevated"
    elif outward:
        category = "outward"
    elif credential_confirm:
        category = "credential"
    elif safe_exec:
        category = "execute"
    elif read:
        category = "read"
    else:
        category = "execute"
    return {
        "command": command,
        "category": category,
        "deny": deny,
        "destructive": destructive,
        "elevated": elevated,
        "outward": outward,
        "credential": credential,
        "process": process,
        "protected_process": protected,
        "read": read,
        "safe_exec": safe_exec,
        "warning": ("process control can close the host terminal; "
                    "verify the target PID and never kill the agent") if process else "",
    }


def _parent_pid(pid: int) -> int | None:
    if os.name == "nt":
        try:
            p = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}')"
                 f".ParentProcessId"],
                capture_output=True, text=True, timeout=6, check=False)
            text = (p.stdout or "").strip()
            return int(text) if text.isdigit() else None
        except Exception:
            return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8",
                                                   errors="replace")
        return int(stat.split()[3])
    except Exception:
        return None


def ancestor_pids(limit: int = 12) -> set[int]:
    pids: set[int] = set()
    pid = os.getpid()
    for _ in range(limit):
        pids.add(pid)
        parent = _parent_pid(pid)
        if not parent or parent == pid:
            break
        pid = parent
    return pids


PROTECTED_NAMES = {
    "powershell.exe", "pwsh.exe", "cmd.exe", "bash.exe", "sh.exe",
    "python.exe", "python3.exe", "python", "python3", "node.exe", "node",
    "claude.exe", "claude", "code.exe", "code", "windowsterminal.exe",
    "windows terminal", "wt.exe", "explorer.exe",
}


def process_name(pid: int) -> str:
    if os.name == "nt":
        try:
            p = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="mbcs",
                errors="replace", timeout=6, check=False)
            line = (p.stdout or "").strip().splitlines()
            if line:
                first = line[0]
                if first.startswith('"'):
                    return first.split('","')[0].strip('"').lower()
        except Exception:
            pass
        return ""
    try:
        return Path(f"/proc/{pid}/comm").read_text(
            encoding="utf-8", errors="replace").strip().lower()
    except Exception:
        return ""


def process_guard(command: str) -> dict:
    """Refuse process control that could kill the agent or its host."""
    pids = [int(x) for x in re.findall(
        r"(?:/PID|/pid|-Id|-id|--pid)\s+(\d+)", command)]
    if not pids:
        # kill 1234 / kill -9 1234
        m = re.search(r"\bkill\s+(?:-\w+\s+)*(\d+)", command)
        if m:
            pids = [int(m.group(1))]
    if not pids:
        return {"blocked": True,
                "reason": "process control requires an explicit PID; "
                          "broad kills are not allowed"}
    ancestors = ancestor_pids()
    bad = sorted(set(pids) & ancestors)
    if bad:
        return {"blocked": True,
                "reason": f"target PID is the agent or an ancestor: {bad}"}
    protected = []
    for pid in pids:
        name = process_name(pid)
        if name in PROTECTED_NAMES:
            protected.append({"pid": pid, "name": name})
    if protected:
        return {"blocked": True,
                "reason": f"target is a protected host process: {protected}"}
    return {"blocked": False, "pids": pids}


def decide(command: str, autonomy: str, confirmed: bool = False) -> dict:
    info = classify(command)
    category = info["category"]
    if category == "process":
        guard = process_guard(command)
        info["process_guard"] = guard
        if guard.get("blocked"):
            return {"decision": "deny", "reason": guard.get("reason", ""), **info}
    if category == "deny":
        decision = "deny"
        reason = "hard-denied pattern"
    elif autonomy == "observe" and category not in ("read",):
        decision = "deny"
        reason = "observe mode only allows read-only commands"
    elif autonomy == "full":
        decision = "allow"
        reason = "full mode (sandbox only)"
    elif autonomy == "auto":
        decision = "allow" if category in ("read", "execute") else "confirm"
        reason = "auto mode"
    else:  # assist
        if category == "read":
            decision = "allow"
            reason = "read-only"
        elif category == "execute" and info["safe_exec"]:
            decision = "allow"
            reason = "safe execute allowlist"
        else:
            decision = "confirm"
            reason = "assist mode requires confirmation"
    if decision == "confirm" and confirmed:
        decision = "allow"
        reason += " (user confirmed)"
    return {"decision": decision, "reason": reason, **info}


def redact(text: str) -> str:
    return REDACT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


def venv_python(workspace: Path) -> Path | None:
    for rel in ("Scripts/python.exe", "bin/python", "Scripts/python",
                "bin/python3"):
        p = workspace / ".venv" / rel
        if p.exists():
            return p
    return None


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise SystemExit(f"env file not found: {path}")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        values[key] = value.strip().strip("'\"")
    return values


def build_child_env(workspace: Path, env_vars: list[str] | None = None,
                    env_file: str = "", use_venv: bool = True) -> tuple[dict, dict]:
    env = os.environ.copy()
    meta: dict[str, Any] = {"venv": "", "env_keys": []}
    if use_venv:
        py = venv_python(workspace)
        if py is not None:
            venv_dir = workspace / ".venv"
            env["VIRTUAL_ENV"] = str(venv_dir)
            env["PATH"] = str(py.parent) + os.pathsep + env.get("PATH", "")
            env.pop("PYTHONHOME", None)
            meta["venv"] = str(venv_dir)
    values: dict[str, str] = {}
    if env_file:
        p = Path(env_file)
        if not p.is_absolute():
            p = workspace / p
        values.update(load_env_file(p))
    for item in env_vars or []:
        if "=" not in item:
            raise SystemExit(f"--env-var must be KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        values[key.strip()] = value
    for key, value in values.items():
        env[key] = value
    meta["env_keys"] = sorted(values)
    meta["values"] = values
    return env, meta


def shell_export_prefix(env_vars: dict[str, str]) -> str:
    def q(value: str) -> str:
        return "'" + value.replace("'", "'\\''") + "'"
    return "".join(f"export {key}={q(value)}; " for key, value in env_vars.items())


def _shell_for_local() -> list[str]:
    if os.name == "nt":
        if shutil.which("bash"):
            return [shutil.which("bash"), "-lc"]
        if shutil.which("powershell"):
            return [shutil.which("powershell"), "-NoProfile", "-Command"]
        return [shutil.which("cmd") or "cmd", "/c"]
    if shutil.which("bash"):
        return [shutil.which("bash"), "-lc"]
    return [shutil.which("sh") or "sh", "-c"]


def build_argv(command: str, env_type: str, target: str) -> list[str]:
    if env_type == "wsl":
        if not shutil.which("wsl"):
            raise RuntimeError("wsl not found")
        argv = ["wsl.exe"]
        if target:
            argv += ["-d", target]
        argv += ["--", "bash", "-lc", command]
        return argv
    if env_type == "ssh":
        if not target:
            raise RuntimeError("ssh target is required")
        ssh = shutil.which("ssh") or "ssh"
        return [ssh, "-o", "BatchMode=yes", target, command]
    return _shell_for_local() + [command]


def run_action(command: str, workspace: Path, step: str, env_type: str,
               target: str, timeout: int, confirmed: bool,
               autonomy: str, cwd: str = "",
               env_vars: list[str] | None = None,
               env_file: str = "", use_venv: bool = True) -> dict:
    decision = decide(command, autonomy, confirmed)
    decision = dict(decision)
    decision["command"] = redact(str(decision.get("command", "")))
    child_env, env_meta = build_child_env(workspace, env_vars, env_file, use_venv)
    if env_type in ("wsl", "ssh") and env_meta.get("values"):
        command = shell_export_prefix(env_meta["values"]) + command
    action_id = f"A{int(time.time() * 1000) % 1000000:06d}"
    _durable.write_intent(workspace, action_id, {
        "kind": "command", "step": step, "env": env_type, "target": target,
        "cwd": cwd or str(workspace), "command": redact(command),
        "env_keys": env_meta.get("env_keys", []),
        "venv": env_meta.get("venv", ""),
    })
    _durable.session_event(workspace, "action_start", id=action_id,
                           step=step, category=decision.get("category"),
                           decision=decision.get("decision"))
    action_dir = workspace / "_worker" / "actions"
    log_dir = workspace / "_worker" / "logs"
    action_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    if decision["decision"] != "allow":
        result = {
            "id": action_id, "step": step, "kind": "command",
            "env": env_type, "target": target, "cwd": cwd or str(workspace),
            "command": redact(command), "decision": decision,
            "env_keys": env_meta.get("env_keys", []),
            "venv": env_meta.get("venv", ""),
            "exit_code": None, "status": "blocked",
            "started_at": _now(), "finished_at": _now(),
        }
        _record(workspace, result)
        _durable.session_event(workspace, "action_end", id=action_id,
                               step=step, status="blocked")
        return result

    stdout_path = log_dir / f"{action_id}.stdout.txt"
    stderr_path = log_dir / f"{action_id}.stderr.txt"
    argv = build_argv(command, env_type, target)
    started = _now()
    t0 = time.time()
    timed_out = False
    proc = None
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(workspace),
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        pid_path = workspace / "_worker" / "actions" / f"{action_id}.pid"
        try:
            pid_path.write_text(str(proc.pid), encoding="utf-8")
        except OSError:
            pass
        try:
            out_b, err_b = proc.communicate(timeout=timeout)
            rc = proc.returncode
            out = out_b.decode("utf-8", errors="replace")
            err = err_b.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            timed_out = True
            rc = 124
            proc.kill()
            out_b, err_b = proc.communicate()
            out = out_b.decode("utf-8", errors="replace")
            err = err_b.decode("utf-8", errors="replace")
            err += f"\n[worker] timeout after {timeout}s\n"
    except OSError as exc:
        rc = 127
        out = ""
        err = f"[worker] cannot execute: {exc}"
    out = redact(out)
    err = redact(err)
    stdout_path.write_text(out, encoding="utf-8")
    stderr_path.write_text(err, encoding="utf-8")
    result = {
        "id": action_id, "step": step, "kind": "command",
        "env": env_type, "target": target, "cwd": cwd or str(workspace),
        "command": redact(command), "decision": decision,
        "env_keys": env_meta.get("env_keys", []),
        "venv": env_meta.get("venv", ""),
        "pid": getattr(proc, "pid", None),
        "exit_code": rc, "timed_out": timed_out,
        "status": "pass" if rc == 0 else "fail",
        "stdout_path": str(stdout_path.relative_to(workspace)),
        "stderr_path": str(stderr_path.relative_to(workspace)),
        "stdout_tail": out[-4000:], "stderr_tail": err[-2000:],
        "started_at": started, "finished_at": _now(),
        "duration_ms": int((time.time() - t0) * 1000),
    }
    _record(workspace, result)
    _durable.session_event(workspace, "action_end", id=action_id,
                           step=step, status=result.get("status"),
                           exit_code=rc)
    return result


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _record(workspace: Path, result: dict) -> None:
    action_dir = workspace / "_worker" / "actions"
    action_dir.mkdir(parents=True, exist_ok=True)
    _durable.write_result(workspace, str(result["id"]), result)
    _durable.atomic_write_json(action_dir / "last.json", result, backup=False)
    _durable.append_jsonl(workspace / "_worker" / "actions.jsonl", result)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(workspace: Path, path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"cannot snapshot missing path: {path}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_root = workspace / "_worker" / "backups" / stamp
    dest_root.mkdir(parents=True, exist_ok=True)
    try:
        rel = path.resolve().relative_to(workspace.resolve())
    except ValueError:
        rel = Path(path.name)
    dest = dest_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, dest, dirs_exist_ok=True)
        digest = ""
    else:
        shutil.copy2(path, dest)
        digest = sha256_file(path)
    result = {"source": str(path), "backup": str(dest),
              "sha256": digest, "at": _now()}
    (workspace / "_worker" / "backups" / "index.jsonl").open("a", encoding="utf-8").write(
        json.dumps(result, ensure_ascii=False) + "\n")
    return result


def cmd_venv(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    venv_dir = Path(args.path)
    if not venv_dir.is_absolute():
        venv_dir = workspace / venv_dir
    base_python = args.python or sys.executable or shutil.which("python3") or "python"
    plan = {
        "workspace": str(workspace),
        "venv": str(venv_dir),
        "base_python": base_python,
        "packages": args.packages or [],
        "note": "installs are confined to this workspace venv; no global pip",
    }
    if args.packages and not args.confirm:
        plan["decision"] = "confirm"
        plan["command"] = f"{base_python} -m venv {venv_dir} && " \
                          f"{venv_dir}/Scripts/python -m pip install " \
                          f"{' '.join(args.packages)}"
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 3
    if not venv_dir.exists():
        p = subprocess.run([base_python, "-m", "venv", str(venv_dir)],
                           capture_output=True, text=True, check=False)
        if p.returncode != 0:
            plan["ok"] = False
            plan["error"] = (p.stderr or p.stdout).strip()
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 1
    py = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    installed = []
    if args.packages:
        p = subprocess.run(
            [str(py), "-m", "pip", "install", "--disable-pip-version-check",
             *args.packages],
            capture_output=True, text=True, check=False,
        )
        installed = args.packages
        if p.returncode != 0:
            plan["ok"] = False
            plan["error"] = (p.stderr or p.stdout).strip()[-4000:]
            plan["installed"] = installed
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 1
    env_file = workspace / "_worker" / "env.json"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "venv": str(venv_dir),
        "python": str(py),
        "base_python": base_python,
        "packages": installed,
        "created_at": _now(),
        "isolated": True,
    }
    env_file.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    plan.update({"ok": True, "python": str(py), "installed": installed,
                 "record": str(env_file)})
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def cmd_env(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    child_env, meta = build_child_env(workspace, args.env_var, args.env_file,
                                      use_venv=not args.no_venv)
    keys = sorted(k for k in child_env if k in (meta.get("env_keys") or [])
                  or k in ("VIRTUAL_ENV", "PATH", "PYTHONPATH"))
    shown = {}
    for key in keys:
        value = child_env.get(key, "")
        if key == "PATH":
            shown[key] = value[:500]
        elif key.upper() in ("PASSWORD", "TOKEN", "SECRET", "API_KEY",
                             "AUTHORIZATION"):
            shown[key] = "***"
        else:
            shown[key] = value
    print(json.dumps({"venv": meta.get("venv", ""),
                      "env_keys": meta.get("env_keys", []),
                      "effective": shown,
                      "note": "child-process environment only; global env untouched"},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    print(json.dumps(classify(args.command), ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    command = args.command
    if command is None:
        command = " ".join(args.rest)
    if not command.strip():
        raise SystemExit("empty command")
    result = run_action(
        command=command, workspace=workspace, step=args.step,
        env_type=args.env, target=args.target, timeout=args.timeout,
        confirmed=args.confirm, autonomy=args.autonomy, cwd=args.cwd,
        env_vars=args.env_var, env_file=args.env_file,
        use_venv=not args.no_venv,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["decision"]["decision"] == "deny":
        return 4
    if result["decision"]["decision"] == "confirm":
        return 3
    return 0 if result.get("exit_code") == 0 else 1


def cmd_resolve(args: argparse.Namespace) -> int:
    """Resolve an in-flight action after a crash, without rerunning it."""
    workspace = Path(args.workspace).resolve()
    path = _durable.intent_path(workspace, args.id)
    data, source, error = _durable.read_json_with_backup(path)
    if not isinstance(data, dict):
        raise SystemExit(f"no in-flight action {args.id}: {error}")
    result = {
        "id": args.id,
        "step": data.get("step", ""),
        "kind": data.get("kind", ""),
        "command": data.get("command", ""),
        "status": args.status,
        "resolution": args.note or "resolved after crash",
        "resolved_at": _now(),
        "recovered_from": source,
    }
    _record(workspace, result)
    _durable.session_event(workspace, "action_resolved", id=args.id,
                           status=args.status, note=args.note)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    path = Path(args.path)
    if not path.is_absolute():
        path = workspace / path
    print(json.dumps(snapshot(workspace, path), ensure_ascii=False, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    path = workspace / "_worker" / "actions.jsonl"
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    in_flight = _durable.list_intents(workspace)
    if args.json:
        print(json.dumps({"actions": rows, "in_flight": in_flight},
                         ensure_ascii=False, indent=2))
    else:
        for row in rows[-args.limit:]:
            print(f"{row.get('id')}  {row.get('status'):7}  {row.get('command', '')[:100]}")
        for intent in in_flight:
            print(f"{intent.get('id')}  IN-FLIGHT  {intent.get('command', '')[:100]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="run and record actions")
    ap.add_argument("--workspace", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("classify")
    p.add_argument("--command", required=True)
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("run")
    p.add_argument("--step", default="")
    p.add_argument("--env", default="local", choices=["local", "wsl", "ssh"])
    p.add_argument("--target", default="")
    p.add_argument("--cwd", default="")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--autonomy", default="assist",
                   choices=["observe", "assist", "auto", "full"])
    p.add_argument("--confirm", action="store_true",
                   help="the user approved this action")
    p.add_argument("--env-var", action="append",
                   help="temporary KEY=VALUE for this child process only")
    p.add_argument("--env-file", default="",
                   help="KEY=VALUE file applied to this child process only")
    p.add_argument("--no-venv", action="store_true",
                   help="do not auto-activate <workspace>/.venv")
    p.add_argument("--command", default=None)
    p.add_argument("rest", nargs="*")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("venv")
    p.add_argument("--path", default=".venv")
    p.add_argument("--python", default="")
    p.add_argument("--packages", action="append")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_venv)

    p = sub.add_parser("env")
    p.add_argument("--env-var", action="append")
    p.add_argument("--env-file", default="")
    p.add_argument("--no-venv", action="store_true")
    p.set_defaults(func=cmd_env)

    p = sub.add_parser("resolve")
    p.add_argument("--id", required=True)
    p.add_argument("--status", required=True,
                   choices=["done", "failed", "unknown"])
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("snapshot")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
