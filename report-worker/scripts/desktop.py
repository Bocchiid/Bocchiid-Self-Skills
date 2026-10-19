#!/usr/bin/env python3
"""GUI actions for report-worker.

Priority: accessibility tree (Windows UIA), then keyboard/mouse, then a manual
handoff.  Every GUI action is expected to declare what should change; the
caller must verify the after-state instead of assuming a click worked.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _durable

UIA_PS1 = SCRIPT_DIR / "uia.ps1"

VK = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
}


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-16-le", "mbcs", "latin-1"):
        try:
            text = data.decode(enc)
            if text.strip():
                return text
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _read_text_any(path: Path) -> str:
    try:
        return _decode(path.read_bytes())
    except OSError:
        return ""


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        return p.returncode, _decode(p.stdout), _decode(p.stderr)
    except Exception as exc:
        return 127, "", str(exc)


def _powershell(args: list[str], timeout: int = 20) -> dict:
    if not shutil.which("powershell") and not shutil.which("pwsh"):
        return {"ok": False, "error": "PowerShell not found"}
    exe = shutil.which("powershell") or shutil.which("pwsh")
    cmd = [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
           str(UIA_PS1)] + args
    rc, out, err = _run(cmd, timeout=timeout)
    text = out.strip()
    if not text:
        return {"ok": False, "error": err.strip() or "empty UIA output",
                "exit": rc}
    try:
        # PowerShell may prepend a BOM or warnings; take the last JSON line.
        line = [x for x in text.splitlines() if x.strip().startswith("{")][-1]
        return json.loads(line)
    except (IndexError, json.JSONDecodeError):
        return {"ok": False, "error": "cannot parse UIA output", "raw": text[-2000:],
                "stderr": err[-1000:], "exit": rc}


# ---------------------------------------------------------------- windows

def list_windows() -> list[dict]:
    import capture
    return capture.list_windows()


def focus_window(title: str) -> dict:
    import capture
    return capture.focus_window(title)


def foreground_title() -> str:
    if os.name != "nt":
        return ""
    try:
        import win32gui
        return win32gui.GetWindowText(win32gui.GetForegroundWindow())
    except Exception:
        return ""


def uia(action: str, window: str = "", name: str = "",
        automation_id: str = "", timeout: int = 10) -> dict:
    if os.name != "nt":
        return {"ok": False, "error": "UIA is Windows-only"}
    return _powershell([
        "-Action", action,
        "-Window", window,
        "-Name", name,
        "-AutomationId", automation_id,
        "-Timeout", str(max(1, timeout)),
    ], timeout=timeout + 15)


def uia_text_visible(window: str, text: str, timeout: int = 10) -> dict:
    """Wait for a control whose name contains text."""
    result = uia("wait", window=window, name=text, timeout=timeout)
    if result.get("ok"):
        return {"ok": True, "match": result}
    # One last broad look; some apps expose the text only in a child element.
    listing = uia("list", window=window, timeout=max(1, timeout))
    if listing.get("ok"):
        needle = text.lower()
        for item in listing.get("items", []):
            if needle in str(item.get("name", "")).lower():
                return {"ok": True, "match": item}
    return {"ok": False, "detail": result}


# ---------------------------------------------------------------- input

def _clipboard_set(text: str) -> str | None:
    """Set clipboard and return the previous text if possible."""
    if os.name != "nt":
        return None
    try:
        import win32clipboard
    except Exception:
        return None
    old = None
    try:
        win32clipboard.OpenClipboard()
        try:
            old = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        except Exception:
            old = None
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
    except Exception:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
    return old


def _key_down(vk: int) -> None:
    import win32api
    win32api.keybd_event(vk, 0, 0, 0)


def _key_up(vk: int) -> None:
    import win32api
    win32api.keybd_event(vk, 0, 2, 0)


def send_keys(keys: str) -> dict:
    if os.name != "nt":
        if shutil.which("xdotool"):
            rc, out, err = _run(["xdotool", "key", "--clearmodifiers", keys])
            return {"ok": rc == 0, "backend": "xdotool", "error": err.strip()}
        if shutil.which("osascript"):
            rc, out, err = _run(["osascript", "-e",
                                 f'tell application "System Events" to keystroke "{keys}"'])
            return {"ok": rc == 0, "backend": "applescript", "error": err.strip()}
        return {"ok": False, "error": "no keyboard backend"}
    parts = [p.strip().lower() for p in keys.replace(" ", "+").split("+") if p.strip()]
    if not parts:
        return {"ok": False, "error": "empty keys"}
    mods = [p for p in parts[:-1] if p in ("ctrl", "control", "alt", "shift", "win")]
    key = parts[-1]
    if key in VK:
        vk = VK[key]
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    else:
        return {"ok": False, "error": f"unknown key: {key}"}
    try:
        for m in mods:
            _key_down(VK[m])
        _key_down(vk)
        _key_up(vk)
        for m in reversed(mods):
            _key_up(VK[m])
        return {"ok": True, "backend": "win32", "keys": keys}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def type_text(text: str) -> dict:
    if os.name != "nt":
        if shutil.which("xdotool"):
            rc, out, err = _run(["xdotool", "type", "--clearmodifiers",
                                 "--delay", "8", "--", text])
            return {"ok": rc == 0, "backend": "xdotool", "error": err.strip()}
        if shutil.which("osascript"):
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            rc, out, err = _run(["osascript", "-e",
                                 f'tell application "System Events" to keystroke "{escaped}"'])
            return {"ok": rc == 0, "backend": "applescript", "error": err.strip()}
        return {"ok": False, "error": "no text backend"}
    old = _clipboard_set(text)
    try:
        result = send_keys("ctrl+v")
        # Give the target application time to read the clipboard before we
        # restore the previous contents.  Without this, slow consoles paste the
        # old clipboard and the action silently does the wrong thing.
        time.sleep(0.35)
        result["backend"] = "clipboard"
        return result
    finally:
        if old is not None:
            _clipboard_set(old)


def mouse_click(x: int, y: int, button: str = "left", double: bool = False) -> dict:
    if os.name == "nt":
        try:
            import win32api
            import win32con
            win32api.SetCursorPos((int(x), int(y)))
            down = {"left": win32con.MOUSEEVENTF_LEFTDOWN,
                    "right": win32con.MOUSEEVENTF_RIGHTDOWN,
                    "middle": win32con.MOUSEEVENTF_MIDDLEDOWN}.get(button)
            up = {"left": win32con.MOUSEEVENTF_LEFTUP,
                  "right": win32con.MOUSEEVENTF_RIGHTUP,
                  "middle": win32con.MOUSEEVENTF_MIDDLEUP}.get(button)
            if down is None or up is None:
                return {"ok": False, "error": f"unknown button: {button}"}
            clicks = 2 if double else 1
            for _ in range(clicks):
                win32api.mouse_event(down, 0, 0, 0, 0)
                win32api.mouse_event(up, 0, 0, 0, 0)
                if double:
                    time.sleep(0.06)
            return {"ok": True, "backend": "win32", "x": x, "y": y,
                    "button": button, "double": double}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    if shutil.which("xdotool"):
        cmd = ["xdotool", "mousemove", str(x), str(y), "click"]
        cmd.append("1")
        if double:
            cmd += ["click", "1"]
        rc, out, err = _run(cmd)
        return {"ok": rc == 0, "backend": "xdotool", "error": err.strip()}
    return {"ok": False, "error": "no mouse backend (install pyautogui or xdotool)"}


def window_rect(title: str) -> dict | None:
    import capture
    return capture.find_window(title)


def point_from_window(title: str, x_pct: float, y_pct: float) -> dict:
    win = window_rect(title)
    if not win or not win.get("rect"):
        return {"ok": False, "error": f"window not found: {title}"}
    left, top, right, bottom = win["rect"]
    x = int(left + (right - left) * float(x_pct))
    y = int(top + (bottom - top) * float(y_pct))
    return {"ok": True, "x": x, "y": y, "window": win}


# ---------------------------------------------------------------- verify

def screenshot(path: Path, window: str = "") -> dict:
    import capture
    return capture.capture(path, window=window or None)


def image_changed(before: Path, after: Path, threshold: float = 0.005) -> dict:
    if not before.exists() or not after.exists():
        return {"ok": False, "error": "before/after missing"}
    try:
        from PIL import Image, ImageChops, ImageStat
    except Exception:
        return {"ok": True, "changed": before.read_bytes() != after.read_bytes(),
                "backend": "bytes"}
    try:
        a = Image.open(before).convert("RGB")
        b = Image.open(after).convert("RGB")
        if a.size != b.size:
            return {"ok": True, "changed": True, "ratio": 1.0,
                    "reason": "size changed"}
        diff = ImageChops.difference(a, b)
        stat = ImageStat.Stat(diff)
        total = max(1, a.width * a.height * 3 * 255)
        ratio = sum(stat.sum) / total
        return {"ok": True, "changed": ratio >= threshold, "ratio": ratio,
                "threshold": threshold, "backend": "pillow"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _expect_obj(expect: Any) -> dict:
    if isinstance(expect, dict):
        return expect
    if isinstance(expect, str) and expect.strip():
        return {"type": "uia_text", "value": expect.strip()}
    return {"type": "manual", "description": "no expect declared"}


def check_expect(expect: Any, window: str, before: Path, after: Path,
                 workspace: Path) -> dict:
    obj = _expect_obj(expect)
    etype = str(obj.get("type", "manual"))
    timeout = int(obj.get("timeout_s", 10))
    if etype == "uia_text":
        value = str(obj.get("value", ""))
        res = uia_text_visible(window, value, timeout=timeout)
        return {"ok": res.get("ok", False), "type": etype, "value": value,
                "detail": res}
    if etype == "uia_control":
        res = uia("wait", window=window, name=str(obj.get("name", "")),
                  automation_id=str(obj.get("automation_id", "")), timeout=timeout)
        return {"ok": res.get("ok", False), "type": etype, "detail": res}
    if etype == "screenshot_changed":
        threshold = float(obj.get("threshold", 0.005))
        res = image_changed(before, after, threshold=threshold)
        return {"ok": res.get("ok", False) and res.get("changed", False),
                "type": etype, "detail": res}
    if etype == "file_exists":
        p = Path(str(obj.get("path", "")))
        if not p.is_absolute():
            p = workspace / p
        return {"ok": p.exists(), "type": etype, "path": str(p)}
    if etype == "manual":
        return {"ok": False, "type": etype, "needs_user": True,
                "description": obj.get("description", "")}
    return {"ok": False, "type": etype, "error": "unknown expect type"}


# ---------------------------------------------------------------- act

def act(action_file: Path, workspace: Path, confirmed: bool = False) -> dict:
    try:
        action = json.loads(action_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"cannot read action: {exc}"}
    aid = str(action.get("id") or f"GUI{int(time.time()*1000)%1000000:06d}")
    window = str(action.get("window", ""))
    target = action.get("target") if isinstance(action.get("target"), dict) else {}
    kind = str(target.get("kind", "uia"))
    expect = action.get("expect")

    def finish(result: dict) -> dict:
        result.setdefault("id", aid)
        result.setdefault("kind", "gui")
        result.setdefault("step", action.get("step", ""))
        _durable.write_result(workspace, aid, result)
        _durable.append_jsonl(workspace / "_worker" / "actions.jsonl", result)
        _durable.session_event(workspace, "gui_action", id=aid,
                               step=action.get("step", ""),
                               status=result.get("status", ""),
                               ok=bool(result.get("ok")))
        return result

    _durable.write_intent(workspace, aid, {
        "kind": "gui", "step": action.get("step", ""), "window": window,
        "target": target, "action": action.get("action", ""),
        "expect": expect,
    })
    if kind == "point" and not confirmed:
        return finish({"ok": False, "status": "needs_confirmation",
                       "error": "coordinate click requires --confirm"})
    if window:
        focus = focus_window(window)
        if not focus.get("ok"):
            return finish({"ok": False, "status": "wrong_window",
                           "error": focus.get("error", "cannot focus window"),
                           "windows": [w.get("title") for w in list_windows()]})
    before_value = action.get("before")
    if not before_value:
        before = workspace / "_worker" / "actions" / f"{aid}_before.png"
    else:
        before = Path(str(before_value))
        if not before.is_absolute():
            before = workspace / before
    b = screenshot(before, window=window)
    if not b.get("ok"):
        return finish({"ok": False, "status": "capture_failed", "detail": b})

    if kind == "uia":
        res = uia("click", window=window,
                  name=str(target.get("name", "")),
                  automation_id=str(target.get("automation_id", "")),
                  timeout=int(action.get("timeout_s", 10)))
    elif kind == "point":
        pt = point_from_window(window, float(target.get("x_pct", 0)),
                               float(target.get("y_pct", 0)))
        if not pt.get("ok"):
            return finish({"ok": False, "status": "not_found", "detail": pt})
        res = mouse_click(pt["x"], pt["y"],
                          button=str(target.get("button", "left")),
                          double=bool(target.get("double", False)))
    elif kind == "keys":
        res = send_keys(str(target.get("keys", "")))
    elif kind == "text":
        res = type_text(str(target.get("text", "")))
    else:
        return finish({"ok": False, "status": "unsupported_target",
                       "target": target})

    time.sleep(float(action.get("settle_s", 0.5)))
    after_value = action.get("after")
    if not after_value:
        after = workspace / "_worker" / "actions" / f"{aid}_after.png"
    else:
        after = Path(str(after_value))
        if not after.is_absolute():
            after = workspace / after
    a = screenshot(after, window=window)
    checked = check_expect(expect, window, before, after, workspace)
    ok = bool(res.get("ok")) and bool(checked.get("ok"))
    return finish({
        "ok": ok,
        "status": "ok" if ok else ("needs_user" if checked.get("needs_user")
                                   else "no_change"),
        "id": aid,
        "step": action.get("step", ""),
        "action": action.get("action", ""),
        "target": target,
        "action_result": res,
        "expect": checked,
        "before": str(before),
        "after": str(after),
    })


# ---------------------------------------------------------------- terminal

def terminal_run(window: str, command: str, log: Path, shell: str,
                 timeout: int, workspace: Path, clear: bool = False) -> dict:
    """Type a wrapped command into a visible terminal and wait for a marker.

    The command's output is tee'd to ``log`` so the host can tell when it has
    finished without OCR.  The terminal window is captured afterwards, which is
    what the report needs.
    """
    aid = f"TERM{int(time.time()*1000)%1000000:06d}"
    if "\n" in command.strip() or "\r" in command:
        return {"ok": False, "error": "terminal command must be a single line"}
    marker = f"__WORKER_END_{int(time.time()*1000)%1000000:06d}__"
    log_s = str(log).replace("'", "'\\''")

    def finish(result: dict) -> dict:
        result.setdefault("id", aid)
        result.setdefault("kind", "terminal")
        _durable.write_result(workspace, aid, result)
        _durable.append_jsonl(workspace / "_worker" / "actions.jsonl", result)
        _durable.session_event(workspace, "terminal_run", id=aid,
                               status=result.get("status", ""),
                               ok=bool(result.get("ok")))
        return result

    _durable.write_intent(workspace, aid, {
        "kind": "terminal", "window": window, "command": command,
        "log": str(log), "shell": shell,
    })
    if shell == "powershell":
        # Put the marker inside the pipeline so Tee-Object writes it to the log
        # as well as the terminal.  $LASTEXITCODE is empty for cmdlets.
        wrapped = (
            f"& {{ {command}; "
            f"if ($LASTEXITCODE -eq $null) {{ $code = 0 }} else {{ $code = $LASTEXITCODE }}; "
            f"Write-Output \"{marker}:$code\" }} 2>&1 | Tee-Object -FilePath '{log_s}'"
        )
    elif shell == "cmd":
        wrapped = (f"{command} > \"{log_s}\" 2>&1 & "
                   f"echo {marker}:%ERRORLEVEL% >> \"{log_s}\"")
    else:
        # Marker inside the block so tee captures it.
        wrapped = f"{{ {command}; echo '{marker}:'$?; }} 2>&1 | tee '{log_s}'"
    focus = focus_window(window)
    if not focus.get("ok"):
        return finish({"ok": False, "status": "wrong_window",
                       "error": focus.get("error", "cannot focus terminal"),
                       "windows": [w.get("title") for w in list_windows()]})
    if clear:
        clear_cmd = {"powershell": "Clear-Host", "cmd": "cls"}.get(shell, "clear")
        type_text(clear_cmd)
        time.sleep(0.2)
        send_keys("enter")
        time.sleep(0.4)
    typed = type_text(wrapped)
    if not typed.get("ok"):
        return finish({"ok": False, "status": "input_failed",
                       "detail": typed})
    time.sleep(0.25)
    send_keys("enter")
    deadline = time.time() + timeout
    exit_code = None
    while time.time() < deadline:
        if log.exists():
            text = _read_text_any(log)
            m = re.search(re.escape(marker) + r":(-?\d+)", text)
            if m:
                exit_code = int(m.group(1))
                break
        time.sleep(0.5)
    shot = workspace / "_worker" / "actions" / f"terminal_{marker}.png"
    cap = screenshot(shot, window=window)
    return finish({
        "ok": exit_code is not None,
        "status": "ok" if exit_code is not None else "timeout",
        "exit_code": exit_code,
        "marker": marker,
        "log": str(log),
        "screenshot": cap.get("file", ""),
        "capture": cap,
        "command": command,
        "shell": shell,
    })


def main() -> int:
    try:
        import _venv
        required = ["win32api", "win32gui"] if os.name == "nt" else []
        _venv.maybe_reexec(_venv.workspace_from_argv(), required)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="GUI actions")
    ap.add_argument("--workspace", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list-windows")
    p.set_defaults(cmd_name="list")

    p = sub.add_parser("focus")
    p.add_argument("--title", required=True)
    p.set_defaults(cmd_name="focus")

    p = sub.add_parser("type")
    p.add_argument("--text", required=True)
    p.set_defaults(cmd_name="type")

    p = sub.add_parser("keys")
    p.add_argument("--keys", required=True)
    p.set_defaults(cmd_name="keys")

    p = sub.add_parser("click")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)
    p.add_argument("--button", default="left")
    p.add_argument("--double", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(cmd_name="click")

    p = sub.add_parser("uia")
    p.add_argument("--action", required=True,
                   choices=["find", "click", "wait", "list", "focus"])
    p.add_argument("--window", default="")
    p.add_argument("--name", default="")
    p.add_argument("--automation-id", default="")
    p.add_argument("--timeout", type=int, default=10)
    p.set_defaults(cmd_name="uia")

    p = sub.add_parser("act")
    p.add_argument("--file", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(cmd_name="act")

    p = sub.add_parser("terminal-run")
    p.add_argument("--window", required=True)
    p.add_argument("--command", required=True)
    p.add_argument("--log", required=True)
    p.add_argument("--shell", default="powershell",
                   choices=["powershell", "bash", "cmd"])
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--clear", action="store_true",
                   help="clear the terminal before running (cleaner evidence)")
    p.set_defaults(cmd_name="terminal")

    args = ap.parse_args()
    workspace = Path(args.workspace).resolve()
    if args.cmd_name == "list":
        result = {"ok": True, "windows": list_windows()}
    elif args.cmd_name == "focus":
        result = focus_window(args.title)
    elif args.cmd_name == "type":
        result = type_text(args.text)
    elif args.cmd_name == "keys":
        result = send_keys(args.keys)
    elif args.cmd_name == "click":
        if not args.confirm:
            result = {"ok": False, "status": "needs_confirmation",
                      "error": "coordinate click requires --confirm"}
        else:
            result = mouse_click(args.x, args.y, args.button, args.double)
    elif args.cmd_name == "uia":
        result = uia(args.action, window=args.window, name=args.name,
                     automation_id=args.automation_id, timeout=args.timeout)
    elif args.cmd_name == "act":
        result = act(Path(args.file).resolve(), workspace, confirmed=args.confirm)
    elif args.cmd_name == "terminal":
        log = Path(args.log)
        if not log.is_absolute():
            log = workspace / log
        log.parent.mkdir(parents=True, exist_ok=True)
        result = terminal_run(args.window, args.command, log, args.shell,
                              args.timeout, workspace, clear=args.clear)
    else:
        raise SystemExit("unknown command")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
