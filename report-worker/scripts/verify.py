#!/usr/bin/env python3
"""Deterministic gates for report-worker.

The worker agent makes judgments; this file makes the boring checks repeatable:
plan shape, step acceptance, evidence files, report existence, review verdict,
and the definition of done.  It never calls a model.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PHASES = {
    "INIT", "PLAN", "PLAN_FREEZE", "EXECUTE", "STEP_VERIFY",
    "EVIDENCE_REVIEW", "RECAPTURE", "WRITE", "REVIEW", "TRIAGE",
    "WAITING_USER", "DONE", "BLOCKED",
}
ACTION_KINDS = {"command", "gui", "file_edit", "manual", "analysis"}
ACCEPTANCE_TYPES = {
    "exit_code", "stdout_regex", "stderr_regex", "file_exists",
    "file_contains", "json_field", "visual", "manual",
}
PASS_WORDS = {"pass", "passed", "ok", "通过"}
FAIL_WORDS = {"fail", "failed", "不通过", "需人工复核", "partial", "部分通过"}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_plan(plan: Any) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(plan, dict):
        return {"ok": False, "errors": ["plan is not a JSON object"], "warnings": []}

    if not _nonempty(str(plan.get("version", ""))):
        errors.append("missing version")

    purposes = _as_list(plan.get("purposes"))
    stages = _as_list(plan.get("stages"))
    steps = _as_list(plan.get("steps"))
    evidence = _as_list(plan.get("evidence"))

    if not purposes:
        errors.append("purposes must be a non-empty list")
    if not stages:
        errors.append("stages must be a non-empty list")
    if not steps:
        errors.append("steps must be a non-empty list")
    if not evidence:
        warnings.append("evidence list is empty; a report may still be text-only, "
                        "but confirm the guide does not require screenshots")

    purpose_ids: set[str] = set()
    stage_ids: set[str] = set()
    step_ids: set[str] = set()
    evidence_ids: set[str] = set()

    for i, p in enumerate(purposes):
        if not isinstance(p, dict):
            errors.append(f"purposes[{i}] is not an object")
            continue
        pid = str(p.get("id", ""))
        if not pid:
            errors.append(f"purposes[{i}] missing id")
        elif pid in purpose_ids:
            errors.append(f"duplicate purpose id: {pid}")
        purpose_ids.add(pid)
        if not _nonempty(str(p.get("text", ""))):
            errors.append(f"purpose {pid or i} missing text")
        if not _as_list(p.get("steps")):
            errors.append(f"purpose {pid or i} has no steps")
        if not _as_list(p.get("evidence")):
            errors.append(f"purpose {pid or i} has no evidence")

    for i, st in enumerate(stages):
        if not isinstance(st, dict):
            errors.append(f"stages[{i}] is not an object")
            continue
        sid = str(st.get("id", ""))
        if not sid:
            errors.append(f"stages[{i}] missing id")
        elif sid in stage_ids:
            errors.append(f"duplicate stage id: {sid}")
        stage_ids.add(sid)
        if not _nonempty(str(st.get("name", ""))):
            errors.append(f"stage {sid or i} missing name")
        if not _as_list(st.get("steps")):
            errors.append(f"stage {sid or i} has no steps")

    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            errors.append(f"steps[{i}] is not an object")
            continue
        sid = str(s.get("id", ""))
        if not sid:
            errors.append(f"steps[{i}] missing id")
        elif sid in step_ids:
            errors.append(f"duplicate step id: {sid}")
        step_ids.add(sid)
        if not _nonempty(str(s.get("goal", ""))):
            errors.append(f"step {sid or i} missing goal")
        stage = str(s.get("stage", ""))
        if stage and stage not in stage_ids:
            errors.append(f"step {sid or i} references unknown stage: {stage}")
        action = s.get("action")
        if not isinstance(action, dict):
            errors.append(f"step {sid or i} missing action object")
        else:
            kind = str(action.get("kind", ""))
            if kind not in ACTION_KINDS:
                errors.append(f"step {sid or i} has invalid action.kind: {kind}")
            if kind == "command" and not (_as_list(action.get("commands"))
                                          or _nonempty(str(action.get("instruction", "")))):
                errors.append(f"step {sid or i} command action has no commands/instruction")
            if kind == "gui" and not (_nonempty(str(action.get("app", "")))
                                      or _nonempty(str(action.get("window", "")))
                                      or _nonempty(str(action.get("instruction", "")))):
                errors.append(f"step {sid or i} gui action has no app/window/instruction")
        acceptance = _as_list(s.get("acceptance"))
        if not acceptance:
            errors.append(f"step {sid or i} has no acceptance checks")
        for j, a in enumerate(acceptance):
            if not isinstance(a, dict):
                errors.append(f"step {sid or i} acceptance[{j}] is not an object")
                continue
            atype = str(a.get("type", ""))
            if atype not in ACCEPTANCE_TYPES:
                errors.append(f"step {sid or i} acceptance[{j}] invalid type: {atype}")
            if atype == "stdout_regex" and not _nonempty(str(a.get("pattern", ""))):
                errors.append(f"step {sid or i} stdout_regex missing pattern")
            if atype == "exit_code" and not isinstance(a.get("value"), int):
                errors.append(f"step {sid or i} exit_code missing integer value")
            if atype in ("file_exists", "file_contains") and not _nonempty(str(a.get("path", ""))):
                errors.append(f"step {sid or i} {atype} missing path")
        if not _as_list(s.get("evidence")):
            warnings.append(f"step {sid or i} has no evidence; confirm it is text-only")

    for i, e in enumerate(evidence):
        if not isinstance(e, dict):
            errors.append(f"evidence[{i}] is not an object")
            continue
        eid = str(e.get("id", ""))
        if not eid:
            errors.append(f"evidence[{i}] missing id")
        elif eid in evidence_ids:
            errors.append(f"duplicate evidence id: {eid}")
        evidence_ids.add(eid)
        if not _nonempty(str(e.get("step", ""))):
            errors.append(f"evidence {eid or i} missing step")
        elif str(e.get("step")) not in step_ids:
            errors.append(f"evidence {eid or i} references unknown step: {e.get('step')}")
        if not _nonempty(str(e.get("type", ""))):
            errors.append(f"evidence {eid or i} missing type")
        if not _nonempty(str(e.get("filename", ""))):
            warnings.append(f"evidence {eid or i} has no filename")

    for p in purposes:
        if not isinstance(p, dict):
            continue
        pid = p.get("id", "?")
        for sid in _as_list(p.get("steps")):
            if sid not in step_ids:
                errors.append(f"purpose {pid} references unknown step: {sid}")
        for eid in _as_list(p.get("evidence")):
            if eid not in evidence_ids:
                errors.append(f"purpose {pid} references unknown evidence: {eid}")
    for st in stages:
        if not isinstance(st, dict):
            continue
        for sid in _as_list(st.get("steps")):
            if sid not in step_ids:
                errors.append(f"stage {st.get('id', '?')} references unknown step: {sid}")
    for s in steps:
        if not isinstance(s, dict):
            continue
        for eid in _as_list(s.get("evidence")):
            if eid not in evidence_ids:
                errors.append(f"step {s.get('id', '?')} references unknown evidence: {eid}")

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "counts": {"purposes": len(purposes), "stages": len(stages),
                       "steps": len(steps), "evidence": len(evidence)}}


def _get_stdout(result: dict, workspace: Path) -> str:
    if isinstance(result.get("stdout"), str):
        return result["stdout"]
    path = result.get("stdout_path")
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = workspace / p
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    return ""


def _get_stderr(result: dict, workspace: Path) -> str:
    if isinstance(result.get("stderr"), str):
        return result["stderr"]
    path = result.get("stderr_path")
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = workspace / p
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    return ""


def _dotted(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def check_step(plan: dict, step_id: str, result: dict, workspace: Path) -> dict:
    steps = [s for s in _as_list(plan.get("steps")) if isinstance(s, dict)]
    step = next((s for s in steps if s.get("id") == step_id), None)
    if step is None:
        return {"ok": False, "status": "fail", "errors": [f"unknown step: {step_id}"]}
    checks: list[dict] = []
    failed: list[str] = []
    needs_visual: list[str] = []
    needs_user: list[str] = []
    stdout = _get_stdout(result, workspace)
    stderr = _get_stderr(result, workspace)
    for a in _as_list(step.get("acceptance")):
        if not isinstance(a, dict):
            continue
        atype = a.get("type")
        passed = False
        detail = ""
        if atype == "exit_code":
            actual = result.get("exit_code")
            passed = actual == a.get("value")
            detail = f"exit={actual}, expected={a.get('value')}"
        elif atype == "stdout_regex":
            pattern = str(a.get("pattern", ""))
            passed = re.search(pattern, stdout, re.MULTILINE) is not None
            detail = f"pattern={pattern!r}"
        elif atype == "stderr_regex":
            pattern = str(a.get("pattern", ""))
            passed = re.search(pattern, stderr, re.MULTILINE) is not None
            detail = f"pattern={pattern!r}"
        elif atype == "file_exists":
            p = Path(str(a.get("path", "")))
            if not p.is_absolute():
                p = workspace / p
            passed = p.exists()
            detail = str(p)
        elif atype == "file_contains":
            p = Path(str(a.get("path", "")))
            if not p.is_absolute():
                p = workspace / p
            pattern = str(a.get("pattern", ""))
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                passed = re.search(pattern, text, re.MULTILINE) is not None
            except OSError:
                passed = False
            detail = f"{p} pattern={pattern!r}"
        elif atype == "json_field":
            p = Path(str(a.get("path", "")))
            if not p.is_absolute():
                p = workspace / p
            data = read_json(p)
            passed = _dotted(data, str(a.get("field", ""))) == a.get("value")
            detail = f"{p} field={a.get('field')}"
        elif atype == "visual":
            needs_visual.append(str(a.get("description", "")))
            detail = "visual check deferred to screenshot reviewer"
        elif atype == "manual":
            needs_user.append(str(a.get("description", "")))
            detail = "manual check requires user"
        if atype not in ("visual", "manual") and not passed:
            failed.append(f"{atype}: {detail}")
        checks.append({"type": atype, "passed": passed, "detail": detail})
    if failed:
        status = "fail"
    elif needs_visual or needs_user:
        status = "partial"
    else:
        status = "pass"
    return {
        "ok": status == "pass",
        "status": status,
        "step": step_id,
        "checks": checks,
        "failed": failed,
        "needs_visual": needs_visual,
        "needs_user": needs_user,
        "action_status": result.get("status"),
    }


def check_evidence(manifest: Any, workspace: Path) -> dict:
    items = manifest.get("items") if isinstance(manifest, dict) else manifest
    items = _as_list(items)
    errors: list[str] = []
    l1_total = 0
    l1_pass = 0
    results: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("id", "?"))
        level = str(item.get("level", "L1")).upper()
        file_path = item.get("file", "")
        p = Path(str(file_path))
        if not p.is_absolute():
            p = workspace / p
        exists = bool(file_path) and p.exists()
        status = str(item.get("status", "")).lower()
        sha_ok = True
        if exists and item.get("sha256"):
            import hashlib
            try:
                actual = hashlib.sha256(p.read_bytes()).hexdigest()
                sha_ok = actual == str(item["sha256"])
            except OSError:
                sha_ok = False
        passed = exists and sha_ok and status in PASS_WORDS
        if level == "L1":
            l1_total += 1
            if passed:
                l1_pass += 1
        if not exists:
            errors.append(f"{eid}: file missing: {p}")
        if not sha_ok:
            errors.append(f"{eid}: sha256 mismatch: {p}")
        if status not in PASS_WORDS:
            errors.append(f"{eid}: status is {status or 'empty'}")
        results.append({"id": eid, "level": level, "file": str(p),
                        "exists": exists, "sha_ok": sha_ok,
                        "status": status, "passed": passed})
    return {
        "ok": not errors and l1_total > 0 and l1_pass == l1_total,
        "errors": errors,
        "l1_total": l1_total,
        "l1_pass": l1_pass,
        "items": results,
    }


def parse_review(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": str(exc), "verdict": "", "score": "",
                "sections": {}, "blocking": ["review file not found"]}
    verdict = ""
    m = re.search(r"审核结论\s*[:：]\s*(通过|有条件通过|不通过)", text)
    if m:
        verdict = m.group(1)
    score = ""
    m = re.search(r"总分区间\s*[:：]\s*([0-9.]+\s*[~\-–—]\s*[0-9.]+)", text)
    if m:
        score = m.group(1)
    def is_placeholder(item: str) -> bool:
        cleaned = re.sub(r"^\s*(?:[-*+]|\d+[.)、])\s*", "", item).strip()
        if re.match(r"^(?:无|没有|none|n/a)(?:[。.!！,，;；:：]|$)",
                    cleaned, re.IGNORECASE):
            return True
        return cleaned.lower() in ("", "无", "没有", "无问题", "none", "n/a", "—", "-")

    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        hm = re.match(r"^#{2,4}\s*[【\[]?([^】\]]+)[】\]]?\s*$", line)
        if hm:
            current = hm.group(1).strip()
            sections.setdefault(current, [])
            continue
        if current and re.match(r"^\s*(?:[-*+]|\d+[.)、])\s+", line):
            if not is_placeholder(line):
                sections[current].append(line.strip())
    blocking_categories = ["正确性错误", "要求未满足", "模板保护问题"]
    blocking: list[str] = []
    for cat in blocking_categories:
        for name, items in sections.items():
            if cat in name and items:
                blocking.extend(f"{cat}: {x}" for x in items)
    if verdict == "不通过":
        blocking.append("审核结论：不通过")
    return {
        "ok": bool(verdict),
        "verdict": verdict,
        "score": score,
        "sections": sections,
        "blocking": blocking,
        "path": str(path),
    }


def check_review(parsed: dict) -> dict:
    verdict = parsed.get("verdict", "")
    blocking = parsed.get("blocking", [])
    ok = verdict in ("通过", "有条件通过") and not blocking
    return {"ok": ok, "verdict": verdict, "score": parsed.get("score", ""),
            "blocking": blocking, "sections": parsed.get("sections", {})}


def check_report(report: Path, template: Path | None = None) -> dict:
    errors: list[str] = []
    if template is not None and str(template) in ("", "."):
        template = None
    if not str(report) or str(report) == ".":
        return {"ok": False, "errors": ["no report path"]}
    if not report.exists():
        return {"ok": False, "errors": [f"report missing: {report}"]}
    if report.stat().st_size == 0:
        errors.append("report is empty")
    suffix = report.suffix.lower()
    if suffix == ".docx":
        if not zipfile.is_zipfile(report):
            errors.append("not a valid .docx (zip) file")
        else:
            try:
                import docx  # noqa: F401
                docx.Document(str(report))
            except Exception as exc:
                errors.append(f"python-docx cannot open report: {exc}")
    elif suffix == ".doc":
        try:
            head = report.read_bytes()[:8]
            if head != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                errors.append("not a classic .doc (OLE) file")
        except OSError as exc:
            errors.append(str(exc))
    else:
        errors.append(f"unexpected report extension: {suffix}")
    if template is not None and str(template) and template.exists():
        if template.suffix.lower() != suffix:
            errors.append(f"delivery format mismatch: template {template.suffix}, "
                          f"report {suffix}")
    return {"ok": not errors, "errors": errors, "report": str(report),
            "size": report.stat().st_size if report.exists() else 0}


def check_state(state: Any) -> dict:
    if not isinstance(state, dict):
        return {"ok": False, "errors": ["state is not an object"]}
    errors = []
    if state.get("phase") not in PHASES:
        errors.append(f"invalid phase: {state.get('phase')}")
    if state.get("autonomy") not in ("observe", "assist", "auto", "full"):
        errors.append(f"invalid autonomy: {state.get('autonomy')}")
    if not isinstance(state.get("execution"), dict):
        errors.append("missing execution")
    return {"ok": not errors, "errors": errors}


def check_dod(workspace: Path, state: dict) -> dict:
    reasons: list[str] = []
    plan = read_json(workspace / state.get("plan", {}).get("path", "_worker/plan.json"))
    plan_result = validate_plan(plan)
    if not plan_result.get("ok"):
        reasons.append("plan gate failed")
    if not state.get("plan", {}).get("frozen"):
        reasons.append("plan is not frozen")
    evidence_path = Path(state.get("evidence", {}).get("path", "_worker/evidence.json"))
    if not evidence_path.is_absolute():
        evidence_path = workspace / evidence_path
    evidence_result = check_evidence(read_json(evidence_path, {}), workspace)
    if not evidence_result.get("ok"):
        reasons.append("evidence gate failed")
    report_path = Path(state.get("task", {}).get("report", ""))
    if not str(report_path) or str(report_path) == ".":
        reasons.append("report path is not set")
    else:
        if not report_path.is_absolute():
            report_path = workspace / report_path
        template = Path(state.get("task", {}).get("template", "") or "")
        if str(template) in ("", "."):
            template = None
        elif not template.is_absolute():
            template = workspace / template
        report_result = check_report(report_path, template)
        if not report_result.get("ok"):
            reasons.append("report gate failed")
    review_path = Path(state.get("report", {}).get("review_path", ""))
    if str(review_path) and str(review_path) != "." and not review_path.is_absolute():
        review_path = workspace / review_path
    if not str(review_path) or str(review_path) == "." or not review_path.exists():
        reasons.append("review file is not set or missing")
    else:
        review_result = check_review(parse_review(review_path))
        if not review_result.get("ok"):
            reasons.append("review gate failed")
    return {
        "ok": not reasons,
        "reasons": reasons,
        "plan": plan_result,
        "evidence": evidence_result,
    }


def _workspace_arg(value: str) -> Path:
    return Path(value).resolve()


def main() -> int:
    try:
        import _venv
        _venv.maybe_reexec(_venv.workspace_from_argv(), ["docx"])
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="report-worker gates")
    ap.add_argument("--workspace", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--file", default="_worker/plan.json")
    p.set_defaults(cmd_name="plan")

    p = sub.add_parser("state")
    p.add_argument("--file", default="_worker/state.json")
    p.set_defaults(cmd_name="state")

    p = sub.add_parser("step")
    p.add_argument("--step", required=True)
    p.add_argument("--plan", default="_worker/plan.json")
    p.add_argument("--result", required=True)
    p.set_defaults(cmd_name="step")

    p = sub.add_parser("evidence")
    p.add_argument("--file", default="_worker/evidence.json")
    p.set_defaults(cmd_name="evidence")

    p = sub.add_parser("report")
    p.add_argument("--report", required=True)
    p.add_argument("--template", default="")
    p.set_defaults(cmd_name="report")

    p = sub.add_parser("review")
    p.add_argument("--review", required=True)
    p.set_defaults(cmd_name="review")

    p = sub.add_parser("dod")
    p.set_defaults(cmd_name="dod")

    args = ap.parse_args()
    workspace = _workspace_arg(args.workspace)

    if args.cmd_name == "plan":
        path = Path(args.file)
        if not path.is_absolute():
            path = workspace / path
        result = validate_plan(read_json(path))
    elif args.cmd_name == "state":
        path = Path(args.file)
        if not path.is_absolute():
            path = workspace / path
        result = check_state(read_json(path))
    elif args.cmd_name == "step":
        plan_path = Path(args.plan)
        if not plan_path.is_absolute():
            plan_path = workspace / plan_path
        result_path = Path(args.result)
        if not result_path.is_absolute():
            result_path = workspace / result_path
        result = check_step(read_json(plan_path, {}), args.step,
                            read_json(result_path, {}), workspace)
    elif args.cmd_name == "evidence":
        path = Path(args.file)
        if not path.is_absolute():
            path = workspace / path
        result = check_evidence(read_json(path, {}), workspace)
    elif args.cmd_name == "report":
        report = Path(args.report)
        if not report.is_absolute():
            report = workspace / report
        template = Path(args.template) if args.template else None
        if template is not None and not template.is_absolute():
            template = workspace / template
        result = check_report(report, template)
    elif args.cmd_name == "review":
        path = Path(args.review)
        if not path.is_absolute():
            path = workspace / path
        result = check_review(parse_review(path))
        result["parsed"] = parse_review(path)
    elif args.cmd_name == "dod":
        state_path = workspace / "_worker" / "state.json"
        state = read_json(state_path, {})
        result = check_dod(workspace, state)
    else:
        raise SystemExit("unknown command")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
