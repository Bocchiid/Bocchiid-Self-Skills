#!/usr/bin/env python3
"""Small helper: run a script with the task-local venv if it is needed.

The worker runtime itself is standard-library only.  Screenshot/GUI helpers may
need Pillow/pywin32/pywinauto; if the task has a `.venv`, re-exec the helper with
that interpreter instead of installing anything globally.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def workspace_from_argv(default: str = ".") -> Path:
    for i, arg in enumerate(sys.argv):
        if arg == "--workspace" and i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
        if arg.startswith("--workspace="):
            return Path(arg.split("=", 1)[1]).resolve()
    return Path(default).resolve()


def find_venv_python(workspace: Path) -> Path | None:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python",
                ".venv/bin/python3", ".venv/Scripts/python"):
        p = workspace / rel
        if p.exists():
            return p
    return None


def missing_modules(modules: list[str]) -> list[str]:
    missing = []
    for name in modules:
        try:
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        except (ImportError, ValueError):
            missing.append(name)
    return missing


def maybe_reexec(workspace: Path, modules: list[str]) -> None:
    if not missing_modules(modules):
        return
    venv_py = find_venv_python(workspace)
    if venv_py is None:
        return
    try:
        if Path(sys.executable).resolve() == venv_py.resolve():
            return
    except OSError:
        pass
    argv = [str(venv_py), str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
    os.execv(str(venv_py), argv)
