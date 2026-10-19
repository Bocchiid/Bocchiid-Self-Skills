#!/usr/bin/env python3
"""Small GUI helper for a Linux guest (VM or WSLg).

The host calls this over SSH.  It uses X11 tools that are commonly available in
a lab VM: wmctrl, xdotool, scrot / gnome-screenshot / grim.  It deliberately has
no Python dependencies beyond the standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           check=False)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 127, "", str(exc)


def list_windows() -> list[dict]:
    rows: list[dict] = []
    if which("wmctrl"):
        rc, out, err = run(["wmctrl", "-lG"])
        if rc == 0:
            for line in out.splitlines():
                parts = line.split(None, 7)
                if len(parts) < 8:
                    continue
                wid, desk, x, y, w, h, host, title = parts
                rows.append({"id": wid, "title": title,
                             "rect": [int(x), int(y), int(x) + int(w), int(y) + int(h)],
                             "width": int(w), "height": int(h)})
            return rows
    if which("xdotool"):
        rc, out, err = run(["xdotool", "search", "--name", "."])
        if rc == 0:
            for wid in out.split():
                rc2, name, _ = run(["xdotool", "getwindowname", wid])
                rc3, geo, _ = run(["xdotool", "getwindowgeometry", "--shell", wid])
                rect = [0, 0, 0, 0]
                for line in geo.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k == "X":
                            rect[0] = int(v)
                        elif k == "Y":
                            rect[1] = int(v)
                        elif k == "WIDTH":
                            rect[2] = int(v)
                        elif k == "HEIGHT":
                            rect[3] = int(v)
                rows.append({"id": wid, "title": name.strip() if rc2 == 0 else "",
                             "rect": rect, "width": rect[2], "height": rect[3]})
    return rows


def find_window(title: str) -> dict | None:
    title_l = title.lower()
    rows = list_windows()
    exact = [w for w in rows if str(w.get("title", "")).lower() == title_l]
    if exact:
        return exact[0]
    partial = [w for w in rows if title_l in str(w.get("title", "")).lower()]
    return partial[0] if partial else None


def focus_window(title: str) -> dict:
    if which("wmctrl"):
        rc, out, err = run(["wmctrl", "-a", title])
        if rc == 0:
            return {"ok": True, "window": find_window(title)}
    if which("xdotool"):
        win = find_window(title)
        if win:
            rc, out, err = run(["xdotool", "windowactivate", str(win["id"])])
            return {"ok": rc == 0, "window": win, "stderr": err.strip()}
    return {"ok": False, "error": f"window not found or no wmctrl/xdotool: {title}",
            "windows": [w.get("title") for w in list_windows()]}


def type_text(text: str) -> dict:
    if not which("xdotool"):
        return {"ok": False, "error": "xdotool not found"}
    rc, out, err = run(["xdotool", "type", "--clearmodifiers", "--delay", "8", "--", text])
    return {"ok": rc == 0, "error": err.strip()}


def send_keys(keys: str) -> dict:
    if not which("xdotool"):
        return {"ok": False, "error": "xdotool not found"}
    rc, out, err = run(["xdotool", "key", "--clearmodifiers", keys])
    return {"ok": rc == 0, "error": err.strip()}


def mouse_click(x: int, y: int, button: str = "1", double: bool = False) -> dict:
    if not which("xdotool"):
        return {"ok": False, "error": "xdotool not found"}
    cmd = ["xdotool", "mousemove", str(x), str(y), "click", button]
    if double:
        cmd += ["click", button]
    rc, out, err = run(cmd)
    return {"ok": rc == 0, "error": err.strip()}


def screenshot(out: Path, window: str = "") -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    if window:
        focus_window(window)
    if which("scrot"):
        cmd = ["scrot", "-o", str(out)]
        if window:
            cmd.insert(1, "-u")
        rc, _, err = run(cmd)
        if rc == 0:
            return {"ok": True, "backend": "scrot", "file": str(out)}
    if which("gnome-screenshot"):
        rc, _, err = run(["gnome-screenshot", "-f", str(out)])
        if rc == 0:
            return {"ok": True, "backend": "gnome-screenshot", "file": str(out)}
    if which("grim"):
        rc, _, err = run(["grim", str(out)])
        if rc == 0:
            return {"ok": True, "backend": "grim", "file": str(out)}
    if which("import"):
        rc, _, err = run(["import", "-window", "root", str(out)])
        if rc == 0:
            return {"ok": True, "backend": "import", "file": str(out)}
    return {"ok": False, "error": "no screenshot backend (scrot/gnome-screenshot/grim/import)"}


def point_from_window(title: str, x_pct: float, y_pct: float) -> dict:
    win = find_window(title)
    if not win:
        return {"ok": False, "error": f"window not found: {title}"}
    left, top, right, bottom = win["rect"]
    return {"ok": True,
            "x": int(left + (right - left) * x_pct),
            "y": int(top + (bottom - top) * y_pct),
            "window": win}


def act(action_file: Path, confirmed: bool = False) -> dict:
    try:
        action = json.loads(action_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    window = str(action.get("window", ""))
    target = action.get("target") if isinstance(action.get("target"), dict) else {}
    kind = str(target.get("kind", "point"))
    if window:
        f = focus_window(window)
        if not f.get("ok"):
            return {"ok": False, "status": "wrong_window", "detail": f}
    before = Path(str(action.get("before", "") or f"/tmp/{action.get('id','act')}_before.png"))
    b = screenshot(before, window=window)
    if kind == "uia":
        return {"ok": False, "status": "unsupported_target",
                "error": "UIA is Windows-only; use point coordinates or keyboard"}
    if kind == "point":
        if not confirmed:
            return {"ok": False, "status": "needs_confirmation",
                    "error": "coordinate click requires --confirm"}
        pt = point_from_window(window, float(target.get("x_pct", 0)),
                               float(target.get("y_pct", 0)))
        if not pt.get("ok"):
            return {"ok": False, "status": "not_found", "detail": pt}
        res = mouse_click(pt["x"], pt["y"],
                          button=str(target.get("button", "1")),
                          double=bool(target.get("double", False)))
    elif kind == "keys":
        res = send_keys(str(target.get("keys", "")))
    elif kind == "text":
        res = type_text(str(target.get("text", "")))
    else:
        return {"ok": False, "status": "unsupported_target"}
    time.sleep(float(action.get("settle_s", 0.5)))
    after = Path(str(action.get("after", "") or f"/tmp/{action.get('id','act')}_after.png"))
    a = screenshot(after, window=window)
    return {"ok": bool(res.get("ok")), "status": "ok" if res.get("ok") else "no_change",
            "action_result": res, "before": str(before), "after": str(after)}


def probe() -> dict:
    return {
        "ok": True,
        "display": os.environ.get("DISPLAY", ""),
        "wayland": os.environ.get("WAYLAND_DISPLAY", ""),
        "tools": {name: which(name) for name in
                  ("wmctrl", "xdotool", "scrot", "gnome-screenshot", "grim", "import")},
        "windows": list_windows(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Linux guest GUI helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe")
    p.set_defaults(cmd_name="probe")

    p = sub.add_parser("list-windows")
    p.set_defaults(cmd_name="list")

    p = sub.add_parser("focus")
    p.add_argument("--title", required=True)
    p.set_defaults(cmd_name="focus")

    p = sub.add_parser("type")
    p.add_argument("--text", required=True)
    p.set_defaults(cmd_name="type")

    p = sub.add_parser("key")
    p.add_argument("--keys", required=True)
    p.set_defaults(cmd_name="key")

    p = sub.add_parser("click")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)
    p.add_argument("--button", default="1")
    p.add_argument("--double", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(cmd_name="click")

    p = sub.add_parser("shot")
    p.add_argument("--out", required=True)
    p.add_argument("--window", default="")
    p.set_defaults(cmd_name="shot")

    p = sub.add_parser("act")
    p.add_argument("--file", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(cmd_name="act")

    args = ap.parse_args()
    if args.cmd_name == "probe":
        result = probe()
    elif args.cmd_name == "list":
        result = {"ok": True, "windows": list_windows()}
    elif args.cmd_name == "focus":
        result = focus_window(args.title)
    elif args.cmd_name == "type":
        result = type_text(args.text)
    elif args.cmd_name == "key":
        result = send_keys(args.keys)
    elif args.cmd_name == "click":
        if not args.confirm:
            result = {"ok": False, "status": "needs_confirmation"}
        else:
            result = mouse_click(args.x, args.y, args.button, args.double)
    elif args.cmd_name == "shot":
        result = screenshot(Path(args.out), args.window)
    elif args.cmd_name == "act":
        result = act(Path(args.file), confirmed=args.confirm)
    else:
        raise SystemExit("unknown command")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
