#!/usr/bin/env python3
"""Cross-platform screenshots and evidence manifest.

Windows is the primary target (Pillow + pywin32, DPI-aware).  Linux and macOS
fall back to their native screenshot tools.  The script never edits or deletes
existing files; duplicate names get a _v2/_v3 suffix.
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
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _durable


def set_dpi_aware() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


set_dpi_aware()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem}_v{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"too many duplicates for {path}")


# ---------------------------------------------------------------- windows

def list_windows() -> list[dict]:
    if os.name == "nt":
        try:
            import win32gui
        except Exception:
            return []
        rows: list[dict] = []

        def cb(hwnd: int, _extra: Any) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title.strip():
                return
            try:
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            except Exception:
                return
            rows.append({"id": hwnd, "title": title,
                         "rect": [left, top, right, bottom],
                         "width": right - left, "height": bottom - top})

        win32gui.EnumWindows(cb, None)
        return rows
    if sys.platform == "darwin":
        try:
            p = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of every process whose visible is true'],
                capture_output=True, text=True, timeout=8, check=False)
            names = [x.strip() for x in p.stdout.split(",") if x.strip()]
            return [{"id": None, "title": n, "rect": None} for n in names]
        except Exception:
            return []
    if shutil.which("wmctrl"):
        try:
            p = subprocess.run(["wmctrl", "-lG"], capture_output=True, text=True,
                               timeout=8, check=False)
            rows = []
            for line in p.stdout.splitlines():
                parts = line.split(None, 7)
                if len(parts) < 8:
                    continue
                wid, desk, x, y, w, h, host, title = parts
                rows.append({"id": wid, "title": title,
                             "rect": [int(x), int(y), int(x) + int(w), int(y) + int(h)],
                             "width": int(w), "height": int(h)})
            return rows
        except Exception:
            return []
    return []


def find_window(title: str) -> dict | None:
    if not title:
        return None
    title_l = title.lower()
    rows = list_windows()
    exact = [w for w in rows if str(w.get("title", "")).lower() == title_l]
    if exact:
        return exact[0]
    partial = [w for w in rows if title_l in str(w.get("title", "")).lower()]
    return partial[0] if partial else None


def focus_window(title: str) -> dict:
    if os.name == "nt":
        import win32con
        import win32gui
        win = find_window(title)
        if not win:
            return {"ok": False, "error": f"window not found: {title}",
                    "windows": [w["title"] for w in list_windows()]}
        hwnd = win["id"]
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return {"ok": True, "window": win}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "window": win}
    if sys.platform == "darwin":
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'tell application "System Events" to set frontmost of first process whose name contains "{title}" to true'],
                capture_output=True, text=True, timeout=8, check=False)
            return {"ok": True, "window": {"title": title}}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    if shutil.which("wmctrl"):
        p = subprocess.run(["wmctrl", "-a", title], capture_output=True,
                           text=True, timeout=8, check=False)
        return {"ok": p.returncode == 0,
                "stderr": p.stderr.strip(), "window": {"title": title}}
    return {"ok": False, "error": "no window manager tool"}


# ---------------------------------------------------------------- capture

def _capture_windows(out: Path, window: str | None,
                     region: tuple[int, int, int, int] | None,
                     monitor: int | None) -> dict:
    try:
        from PIL import ImageGrab
    except Exception as exc:
        return {"ok": False, "error": f"Pillow not available: {exc}"}
    bbox = None
    meta: dict[str, Any] = {}
    if window:
        win = find_window(window)
        if not win:
            return {"ok": False, "error": f"window not found: {window}",
                    "windows": [w["title"] for w in list_windows()]}
        focus_window(window)
        left, top, right, bottom = win["rect"]
        if right <= left or bottom <= top:
            return {"ok": False, "error": "window has no visible rect", "window": win}
        bbox = (left, top, right, bottom)
        meta["window"] = win
    elif region:
        x, y, w, h = region
        bbox = (x, y, x + w, y + h)
        meta["region"] = [x, y, w, h]
    try:
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, "PNG")
        meta.update({"width": img.width, "height": img.height})
        return {"ok": True, **meta}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "backend": "pillow"}


def _run_tool(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           check=False)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 127, "", str(exc)


def _capture_linux(out: Path, window: str | None,
                   region: tuple[int, int, int, int] | None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    if window and shutil.which("scrot"):
        # scrot -u captures the focused window; focus first.
        focus_window(window)
        rc, _, err = _run_tool(["scrot", "-u", "-o", str(out)])
        if rc == 0:
            return {"ok": True, "backend": "scrot-u"}
        return {"ok": False, "error": err.strip(), "backend": "scrot"}
    if shutil.which("scrot"):
        rc, _, err = _run_tool(["scrot", "-o", str(out)])
        if rc == 0:
            return {"ok": True, "backend": "scrot"}
        return {"ok": False, "error": err.strip(), "backend": "scrot"}
    if shutil.which("gnome-screenshot"):
        rc, _, err = _run_tool(["gnome-screenshot", "-f", str(out)])
        return {"ok": rc == 0, "error": err.strip(), "backend": "gnome-screenshot"}
    if shutil.which("grim"):
        rc, _, err = _run_tool(["grim", str(out)])
        return {"ok": rc == 0, "error": err.strip(), "backend": "grim"}
    if shutil.which("import"):
        rc, _, err = _run_tool(["import", "-window", "root", str(out)])
        return {"ok": rc == 0, "error": err.strip(), "backend": "import"}
    return {"ok": False, "error": "no screenshot backend found"}


def _capture_macos(out: Path, window: str | None,
                   region: tuple[int, int, int, int] | None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["screencapture", "-x"]
    if region:
        x, y, w, h = region
        cmd += ["-R", f"{x},{y},{w},{h}"]
    cmd.append(str(out))
    rc, _, err = _run_tool(cmd)
    return {"ok": rc == 0, "error": err.strip(), "backend": "screencapture"}


def capture(out: Path, window: str | None = None,
            region: tuple[int, int, int, int] | None = None,
            monitor: int | None = None) -> dict:
    out = unique_path(out)
    if os.name == "nt":
        result = _capture_windows(out, window, region, monitor)
    elif sys.platform == "darwin":
        result = _capture_macos(out, window, region)
    else:
        result = _capture_linux(out, window, region)
    if result.get("ok") and out.exists():
        result["file"] = str(out)
        result["sha256"] = sha256_file(out)
        result["captured_at"] = now()
    else:
        result["file"] = str(out)
    return result


# ---------------------------------------------------------------- manifest

def evidence_path(workspace: Path) -> Path:
    return workspace / "_worker" / "evidence.json"


def load_manifest(workspace: Path) -> dict:
    path = evidence_path(workspace)
    data, _source, _error = _durable.read_json_with_backup(path)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data
    return {"items": [], "updated_at": now()}


def save_manifest(workspace: Path, manifest: dict) -> None:
    manifest["updated_at"] = now()
    _durable.atomic_write_json(evidence_path(workspace), manifest, backup=True)


def add_evidence(workspace: Path, eid: str, step: str, file: str,
                 etype: str = "screenshot", level: str = "L1",
                 must_include: list[str] | None = None,
                 status: str = "pending", note: str = "",
                 sha256: str = "") -> dict:
    manifest = load_manifest(workspace)
    items = manifest["items"]
    existing = next((x for x in items if x.get("id") == eid), None)
    entry = {
        "id": eid,
        "step": step,
        "type": etype,
        "level": level.upper(),
        "file": file,
        "must_include": must_include or [],
        "status": status,
        "note": note,
        "updated_at": now(),
    }
    if sha256:
        entry["sha256"] = sha256
    elif file:
        p = Path(file)
        if not p.is_absolute():
            p = workspace / p
        if p.exists() and p.is_file():
            entry["sha256"] = sha256_file(p)
            entry["size"] = p.stat().st_size
    if existing is None:
        items.append(entry)
    else:
        existing.update(entry)
    save_manifest(workspace, manifest)
    _durable.session_event(workspace, "evidence_add", id=eid, step=step,
                           file=file, level=level.upper(), status=status)
    return entry


def set_status(workspace: Path, eid: str, status: str, note: str = "") -> dict:
    manifest = load_manifest(workspace)
    for item in manifest["items"]:
        if item.get("id") == eid:
            item["status"] = status
            item["note"] = note or item.get("note", "")
            item["updated_at"] = now()
            save_manifest(workspace, manifest)
            _durable.session_event(workspace, "evidence_status", id=eid,
                                   status=status, note=note)
            return item
    raise SystemExit(f"evidence not found: {eid}")


# ---------------------------------------------------------------- CLI

def parse_region(value: str) -> tuple[int, int, int, int]:
    parts = [int(x) for x in re.split(r"[,\s]+", value.strip()) if x]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("region must be x,y,w,h")
    return tuple(parts)  # type: ignore[return-value]


def cmd_list_windows(_args: argparse.Namespace) -> int:
    print(json.dumps(list_windows(), ensure_ascii=False, indent=2))
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = workspace / out
    result = capture(out, window=args.window, region=args.region,
                     monitor=args.monitor)
    if result.get("ok") and args.evidence:
        rel = os.path.relpath(result["file"], workspace)
        entry = add_evidence(
            workspace, args.evidence, args.step, rel,
            etype="screenshot", level=args.level,
            must_include=args.must_include or [],
            status="pending", sha256=result.get("sha256", ""),
        )
        result["evidence"] = entry
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_crop(args: argparse.Namespace) -> int:
    try:
        from PIL import Image
    except Exception as exc:
        raise SystemExit(f"Pillow required for crop: {exc}")
    src = Path(args.input)
    dst = Path(args.output)
    if not src.is_absolute():
        src = Path(args.workspace).resolve() / src
    if not dst.is_absolute():
        dst = Path(args.workspace).resolve() / dst
    if not src.exists():
        raise SystemExit(f"input not found: {src}")
    x, y, w, h = args.box
    img = Image.open(src)
    box = (max(0, x), max(0, y), min(img.width, x + w), min(img.height, y + h))
    cropped = img.crop(box)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(dst, "PNG")
    result = {"ok": True, "file": str(dst), "box": list(box),
              "width": cropped.width, "height": cropped.height,
              "sha256": sha256_file(dst)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    entry = add_evidence(
        workspace, args.id, args.step, args.file, etype=args.type,
        level=args.level, must_include=args.must_include or [],
        status=args.status, note=args.note,
    )
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    print(json.dumps(load_manifest(workspace), ensure_ascii=False, indent=2))
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    print(json.dumps(set_status(workspace, args.id, args.status, args.note),
                     ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    try:
        import _venv
        required = ["PIL"] + (["win32gui"] if os.name == "nt" else [])
        _venv.maybe_reexec(_venv.workspace_from_argv(), required)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="screenshots and evidence manifest")
    ap.add_argument("--workspace", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list-windows")
    p.set_defaults(func=cmd_list_windows)

    p = sub.add_parser("shot")
    p.add_argument("--out", required=True)
    p.add_argument("--window", default="")
    p.add_argument("--region", type=parse_region, default=None)
    p.add_argument("--monitor", type=int, default=None)
    p.add_argument("--evidence", default="")
    p.add_argument("--step", default="")
    p.add_argument("--level", default="L1")
    p.add_argument("--must-include", action="append")
    p.set_defaults(func=cmd_shot)

    p = sub.add_parser("crop")
    p.add_argument("--in", dest="input", required=True)
    p.add_argument("--out", dest="output", required=True)
    p.add_argument("--box", type=parse_region, required=True,
                   help="x,y,w,h in pixels")
    p.set_defaults(func=cmd_crop)

    p = sub.add_parser("add")
    p.add_argument("--id", required=True)
    p.add_argument("--step", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--type", default="screenshot")
    p.add_argument("--level", default="L1")
    p.add_argument("--must-include", action="append")
    p.add_argument("--status", default="pending")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("manifest")
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("set-status")
    p.add_argument("--id", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_set_status)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
