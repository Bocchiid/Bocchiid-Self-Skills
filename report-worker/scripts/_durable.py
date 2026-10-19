#!/usr/bin/env python3
"""Durable state/log helpers for report-worker.

A lab machine can crash, reboot, or lose power.  These helpers make the parts
that must survive a crash (state, action intents, evidence manifest, logs)
atomic and fsync'd, and leave enough breadcrumbs for ``worker.py doctor`` to
explain what was in flight.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def atomic_write_json(path: Path, data: Any, backup: bool = True) -> None:
    """Write JSON via tmp + fsync + replace, keeping a .bak of the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2)
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    if backup and path.exists():
        # Only back up a file that is still valid JSON; otherwise keep the
        # previous good .bak instead of overwriting it with corruption.
        try:
            json.loads(path.read_text(encoding="utf-8"))
            valid = True
        except (OSError, json.JSONDecodeError):
            valid = False
        if valid:
            bak = path.with_name(path.name + ".bak")
            bak_tmp = bak.with_name(bak.name + ".tmp")
            try:
                shutil.copy2(path, bak_tmp)
                os.replace(bak_tmp, bak)
            except OSError:
                pass
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def read_json_with_backup(path: Path) -> tuple[Any, str, str]:
    """Return (data, source, error).  Falls back to <path>.bak on corruption."""
    for candidate in (path, path.with_name(path.name + ".bak")):
        if not candidate.exists():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8")), str(candidate), ""
        except (OSError, json.JSONDecodeError) as exc:
            if candidate == path:
                continue
            return None, str(candidate), str(exc)
    return None, "", f"no readable JSON at {path}"


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def append_jsonl(path: Path, obj: dict) -> None:
    append_text(path, json.dumps(obj, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- intents

def action_dir(workspace: Path) -> Path:
    return workspace / "_worker" / "actions"


def intent_path(workspace: Path, action_id: str) -> Path:
    return action_dir(workspace) / f"{action_id}.intent.json"


def result_path(workspace: Path, action_id: str) -> Path:
    return action_dir(workspace) / f"{action_id}.json"


def write_intent(workspace: Path, action_id: str, data: dict) -> Path:
    path = intent_path(workspace, action_id)
    atomic_write_json(path, {"id": action_id, "at": now(), **data})
    return path


def clear_intent(workspace: Path, action_id: str) -> None:
    for p in (intent_path(workspace, action_id),
              action_dir(workspace) / f"{action_id}.pid"):
        try:
            p.unlink()
        except OSError:
            pass


def write_result(workspace: Path, action_id: str, data: dict) -> Path:
    path = result_path(workspace, action_id)
    atomic_write_json(path, {"finished_at": now(), **data})
    clear_intent(workspace, action_id)
    return path


def list_intents(workspace: Path) -> list[dict]:
    out: list[dict] = []
    folder = action_dir(workspace)
    if not folder.exists():
        return out
    for path in sorted(folder.glob("*.intent.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"id": path.name.replace(".intent.json", ""),
                    "error": "unreadable intent"}
        # A result file means the action finished; the intent is just a
        # leftover from a crash between write_result() and clear_intent().
        if (folder / f"{data.get('id', '')}.json").exists():
            continue
        data["_intent_file"] = str(path)
        pid_file = folder / f"{data.get('id', '')}.pid"
        if pid_file.exists():
            try:
                data["pid"] = int(pid_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pass
        out.append(data)
    return out


# ---------------------------------------------------------------- logs

def logs_dir(workspace: Path) -> Path:
    return workspace / "_worker" / "logs"


def session_event(workspace: Path, event: str, **data: Any) -> None:
    entry = {"at": now(), "event": event, **data}
    logs = logs_dir(workspace)
    append_text(logs / "session.log",
                f"{entry['at']} {event} {json.dumps(data, ensure_ascii=False)}\n")
    append_jsonl(logs / "events.jsonl", entry)


def rotate_log(path: Path, max_bytes: int, keep: int = 3) -> bool:
    try:
        if not path.exists() or path.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False
    for i in range(keep - 1, 0, -1):
        src = path.with_name(f"{path.name}.{i}")
        dst = path.with_name(f"{path.name}.{i + 1}")
        if src.exists():
            try:
                os.replace(src, dst)
            except OSError:
                pass
    try:
        os.replace(path, path.with_name(path.name + ".1"))
        return True
    except OSError:
        return False


def list_logs(workspace: Path) -> list[dict]:
    rows: list[dict] = []
    folder = logs_dir(workspace)
    if not folder.exists():
        return rows
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            try:
                rows.append({"path": str(path.relative_to(workspace)),
                             "size": path.stat().st_size,
                             "mtime": datetime.fromtimestamp(
                                 path.stat().st_mtime).astimezone().isoformat(
                                     timespec="seconds")})
            except OSError:
                continue
    return rows


def total_log_size(workspace: Path) -> int:
    return sum(row["size"] for row in list_logs(workspace))
