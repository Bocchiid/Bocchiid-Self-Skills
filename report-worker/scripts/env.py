#!/usr/bin/env python3
"""Probe the host for capabilities the worker can use.

This script must stay agent-agnostic and dependency-light.  It never installs
anything and never starts GUI applications.  It only answers: what is here?
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _durable

RECOMMENDED_PY = {
    "windows": ["pillow", "pywin32", "pywinauto", "mss", "opencv-python"],
    "linux": ["pillow"],
    "darwin": ["pillow", "pyautogui"],
}
PKG_MODULE = {
    "pillow": "PIL",
    "pywin32": "win32gui",
    "pywinauto": "pywinauto",
    "mss": "mss",
    "opencv-python": "cv2",
    "pyautogui": "pyautogui",
}


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def run_text(cmd: list[str], timeout: int = 8) -> tuple[int, str, str]:
    """Run a probe command, tolerating odd Windows encodings."""
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)
    out, err = p.stdout, p.stderr
    text = ""
    for enc in ("utf-8", "utf-16-le", "mbcs", "latin-1"):
        try:
            text = out.decode(enc)
            if text.strip():
                break
        except (UnicodeDecodeError, LookupError):
            continue
    err_text = ""
    for enc in ("utf-8", "utf-16-le", "mbcs", "latin-1"):
        try:
            err_text = err.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    return p.returncode, text, err_text


def detect_shell(system: str) -> str:
    if system == "windows":
        if which("bash"):
            return "bash"
        if which("powershell") or which("pwsh"):
            return "powershell"
        if which("cmd"):
            return "cmd"
        return "none"
    if which("bash"):
        return "bash"
    if which("sh"):
        return "sh"
    return "none"


def detect_screenshot(system: str) -> tuple[str, list[str]]:
    candidates: list[tuple[str, str]] = []
    if system == "windows":
        if has_module("PIL"):
            candidates.append(("pillow", "PIL.ImageGrab"))
        if has_module("win32gui"):
            candidates.append(("win32", "pywin32"))
        if which("powershell"):
            candidates.append(("powershell", "System.Windows.Forms"))
    elif system == "darwin":
        if which("screencapture"):
            candidates.append(("screencapture", "screencapture"))
    else:
        for name in ("gnome-screenshot", "scrot", "grim", "import"):
            if which(name):
                candidates.append((name, name))
    return (candidates[0][0] if candidates else "none",
            [c[0] for c in candidates])


def detect_desktop(system: str) -> tuple[str, list[str]]:
    candidates: list[str] = []
    if system == "windows":
        if has_module("pywinauto"):
            candidates.append("pywinauto")
        if which("powershell"):
            candidates.append("uia")       # UIAutomationClient via PowerShell
        if has_module("win32gui"):
            candidates.append("win32")
    elif system == "darwin":
        if which("osascript"):
            candidates.append("applescript")
    else:
        for name in ("xdotool", "wmctrl", "ydotool"):
            if which(name):
                candidates.append(name)
        if has_module("pyatspi"):
            candidates.append("at-spi")
    return (candidates[0] if candidates else "none", candidates)


def detect_wsl() -> dict:
    if platform.system().lower() != "windows" or not which("wsl"):
        return {"available": False, "distros": []}
    code, out, err = run_text(["wsl.exe", "-l", "-q"])
    distros = [line.strip() for line in out.splitlines() if line.strip()]
    return {"available": code == 0, "distros": distros, "error": err.strip()}


def detect_word() -> bool:
    if platform.system().lower() != "windows":
        return False
    if not has_module("win32com"):
        return False
    try:
        import win32com.client  # noqa: F401
    except Exception:
        return False
    return True


def probe() -> dict:
    system = platform.system().lower()
    screenshot, screenshot_all = detect_screenshot(system)
    desktop, desktop_all = detect_desktop(system)
    py_pkgs = {
        name: has_module(name)
        for name in (
            "PIL", "win32gui", "win32com", "pywinauto", "pyautogui",
            "mss", "cv2", "docx", "fitz", "pypdf", "pptx", "openpyxl",
        )
    }
    return {
        "os": system,
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "shell": detect_shell(system),
        "shells": {
            "bash": which("bash"),
            "powershell": which("powershell") or which("pwsh"),
            "sh": which("sh"),
        },
        "python_packages": py_pkgs,
        "commands": {
            name: which(name)
            for name in (
                "python", "python3", "pip", "git", "ssh", "scp", "curl",
                "wsl", "soffice", "mn", "ovs-vsctl", "ovs-ofctl",
                "tshark", "dumpcap", "wireshark", "xdotool", "wmctrl",
                "scrot", "gnome-screenshot", "grim", "osascript",
                "screencapture", "powershell",
            )
        },
        "screenshot_backend": screenshot,
        "screenshot_backends": screenshot_all,
        "desktop_backend": desktop,
        "desktop_backends": desktop_all,
        "wsl": detect_wsl(),
        "word_com": detect_word(),
        "libreoffice": which("soffice") is not None,
        "display": os.environ.get("DISPLAY", ""),
        "session": os.environ.get("SESSIONNAME", ""),
    }


def install_plan(info: dict) -> dict:
    system = info["os"]
    missing = [p for p in RECOMMENDED_PY.get(system, [])
               if not has_module(PKG_MODULE.get(p, p.replace("-", "_")))]
    commands: list[str] = []
    notes: list[str] = []
    if system == "windows":
        if missing:
            commands.append("python -m venv .venv")
            commands.append(".venv\\Scripts\\python -m pip install " + " ".join(missing))
        if info["screenshot_backend"] == "none":
            notes.append("没有可用的截图后端；在任务 venv 里安装 Pillow")
        if info["desktop_backend"] == "none":
            notes.append("没有可用的 GUI 后端；在任务 venv 里安装 pywinauto")
    elif system == "darwin":
        if missing:
            commands.append("python3 -m venv .venv")
            commands.append(".venv/bin/python -m pip install " + " ".join(missing))
        notes.append("macOS GUI 自动化需要在“系统设置 → 隐私与安全性 → 辅助功能”授权终端。")
    else:
        if missing:
            commands.append("python3 -m venv .venv")
            commands.append(".venv/bin/python -m pip install " + " ".join(missing))
        needed = []
        for cmd, pkg in (("xdotool", "xdotool"), ("wmctrl", "wmctrl"),
                         ("scrot", "scrot")):
            if not which(cmd):
                needed.append(pkg)
        if needed:
            notes.append("guest 内需要这些系统包（由用户在 VM 内确认安装）：" + " ".join(needed))
    notes.insert(0, "所有 Python 安装都进任务目录的 .venv；不要用全局 pip。")
    return {"missing_python": missing, "commands": commands, "notes": notes,
            "isolated": True}


def write_capabilities(workspace: Path, info: dict) -> Path:
    worker = workspace / "_worker"
    worker.mkdir(parents=True, exist_ok=True)
    caps = {
        "os": info["os"],
        "shell": info["shell"],
        "python": info["python"],
        "file_read": True,
        "file_write": True,
        "image_view": None,          # the host agent fills this in
        "subagents": None,           # the host agent fills this in
        "gui": info["desktop_backend"] != "none",
        "web": None,
        "word_com": info["word_com"],
        "libreoffice": info["libreoffice"],
        "screenshot_backend": info["screenshot_backend"],
        "desktop_backend": info["desktop_backend"],
        "venv": str(workspace / ".venv") if (workspace / ".venv").exists() else "",
        "environment_isolation": {
            "python": "task-local .venv",
            "env_vars": "child process only; no setx/export",
            "global_changes": "not allowed without explicit user confirmation",
        },
        "probe": info,
    }
    path = worker / "capabilities.json"
    _durable.atomic_write_json(path, caps, backup=True)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true", help="print capability JSON")
    ap.add_argument("--install-plan", action="store_true", help="print missing deps")
    ap.add_argument("--write", metavar="WORKSPACE", help="write _worker/capabilities.json")
    args = ap.parse_args()
    info = probe()
    if args.write:
        path = write_capabilities(Path(args.write).resolve(), info)
        print(json.dumps({"written": str(path), "capabilities": info},
                         ensure_ascii=False, indent=2))
    elif args.install_plan:
        print(json.dumps(install_plan(info), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
