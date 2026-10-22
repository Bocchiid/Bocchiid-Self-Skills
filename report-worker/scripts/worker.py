#!/usr/bin/env python3
"""Thin state machine for report-worker.

Eight phases:
ANALYZE -> COLLECT -> ORGANIZE -> PLAN -> PLAN_FREEZE
-> EXECUTE -> WRITE -> REVIEW -> REVISE -> DONE/BLOCKED/WAITING_USER

The worker does not implement planner/writer/reviewer rules; it points at their
SKILL.md, records artifacts, and enforces gates.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _durable

PHASES = [
    "ANALYZE", "COLLECT", "ORGANIZE", "PLAN", "PLAN_FREEZE",
    "EXECUTE", "WRITE", "REVIEW", "REVISE",
    "WAITING_USER", "DONE", "BLOCKED",
]

PROMPTS = {
    "ANALYZE": "prompts/01_planner.md",
    "COLLECT": "prompts/00_conductor.md",
    "ORGANIZE": "prompts/01_planner.md",
    "PLAN": "prompts/01_planner.md",
    "PLAN_FREEZE": None,
    "EXECUTE": "prompts/02_operator.md",
    "WRITE": "prompts/03_writer.md",
    "REVIEW": "prompts/04_reviewer.md",
    "REVISE": "prompts/04_reviewer.md",
    "WAITING_USER": "prompts/00_conductor.md",
    "DONE": None,
    "BLOCKED": None,
}

ALLOWED = {
    "ANALYZE": {"COLLECT", "ORGANIZE", "PLAN", "WAITING_USER", "BLOCKED"},
    "COLLECT": {"ORGANIZE", "PLAN", "WAITING_USER", "BLOCKED"},
    "ORGANIZE": {"PLAN", "WAITING_USER", "BLOCKED"},
    "PLAN": {"PLAN_FREEZE", "WAITING_USER", "BLOCKED"},
    "PLAN_FREEZE": {"EXECUTE", "PLAN", "WAITING_USER", "BLOCKED"},
    "EXECUTE": {"WRITE", "WAITING_USER", "BLOCKED"},
    "WRITE": {"REVIEW", "WAITING_USER", "BLOCKED"},
    "REVIEW": {"REVISE", "DONE", "WAITING_USER", "BLOCKED"},
    "REVISE": {"EXECUTE", "WRITE", "PLAN", "DONE", "WAITING_USER", "BLOCKED"},
    "WAITING_USER": {"ANALYZE", "COLLECT", "ORGANIZE", "PLAN", "EXECUTE",
                     "WRITE", "REVIEW", "REVISE", "BLOCKED"},
    "BLOCKED": {"ANALYZE", "EXECUTE", "WAITING_USER"},
    "DONE": set(),
}

DEFAULT_BUDGETS = {
    "max_report_rounds": 3,
    "max_step_attempts": 3,
    "max_evidence_rounds": 2,
    "max_actions": 500,
    "max_minutes": 240,
    "heartbeat_seconds": 60,
    "max_log_bytes": 50 * 1024 * 1024,
    "max_log_files": 500,
}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def state_path(workspace: Path) -> Path:
    return workspace / "_worker" / "state.json"


def load_state(workspace: Path) -> dict:
    state, source, error = _durable.read_json_with_backup(state_path(workspace))
    if not isinstance(state, dict):
        raise SystemExit(f"no readable state at {state_path(workspace)}: {error}; "
                         f"run doctor --recover")
    if source != str(state_path(workspace)):
        state["_recovered_from"] = source
    return state


def save_state(workspace: Path, state: dict) -> None:
    state["updated_at"] = now()
    state["last_heartbeat"] = now()
    _durable.atomic_write_json(state_path(workspace), state, backup=True)


def log_event(state: dict, event: str, **data: Any) -> None:
    entry = {"at": now(), "event": event, **data}
    state.setdefault("history", []).append(entry)
    try:
        _durable.session_event(Path(state["workspace"]), event, **data)
    except Exception:
        pass


def default_state(workspace: Path, autonomy: str, env_type: str,
                  target: str, task_name: str) -> dict:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    return {
        "run_id": run_id,
        "workspace": str(workspace),
        "created_at": now(),
        "updated_at": now(),
        "last_heartbeat": now(),
        "phase": "ANALYZE",
        "previous_phase": None,
        "autonomy": autonomy,
        "environment": {"type": env_type, "target": target},
        "agent_window": "",
        "decisions": [],
        "task": {"name": task_name, "materials": [], "template": "", "report": ""},
        "plan": {"path": "_worker/plan.json", "version": "", "frozen": False, "gate": None},
        "execution": {"stage": "", "step": "", "attempts": {},
                      "completed": [], "skipped": []},
        "evidence": {"path": "_worker/evidence.json", "l1_total": 0, "l1_pass": 0},
        "report": {"round": 1, "path": "", "review_path": ""},
        "budgets": dict(DEFAULT_BUDGETS),
        "history": [],
    }


def create_dirs(workspace: Path) -> None:
    for rel in ("_worker", "_worker/roles", "_worker/logs", "_worker/logs/crashes",
                "_worker/backups", "_worker/actions", "_worker/rounds",
                "Pictures", "Pictures/_raw", "Data", "报告"):
        (workspace / rel).mkdir(parents=True, exist_ok=True)


def load_plan(workspace: Path, state: dict) -> dict | None:
    return read_json(workspace / state["plan"]["path"])


def steps(state: dict, workspace: Path) -> list[dict]:
    plan = load_plan(workspace, state)
    if not isinstance(plan, dict):
        return []
    return [s for s in plan.get("steps", []) if isinstance(s, dict)]


def next_step(workspace: Path, state: dict) -> dict | None:
    done = set(state["execution"].get("completed", []))
    skipped = set(state["execution"].get("skipped", []))
    for step in steps(state, workspace):
        sid = step.get("id")
        if sid and sid not in done and sid not in skipped:
            return step
    return None


def last_action_for(workspace: Path, step_id: str) -> dict | None:
    path = workspace / "_worker" / "actions.jsonl"
    if not path.exists() or not step_id:
        return None
    last = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("step", "")) == step_id:
            last = row
    return last


def next_action(workspace: Path, state: dict) -> dict:
    phase = state["phase"]
    base = {"phase": phase, "prompt": PROMPTS.get(phase), "workspace": str(workspace),
            "agent_window": state.get("agent_window", "")}
    if phase == "ANALYZE":
        caps = read_json(workspace / "_worker" / "capabilities.json", {})
        skills = caps.get("skills", {}) if isinstance(caps, dict) else {}
        if not skills:
            try:
                import env as env_mod
                skills = env_mod.check_skills(workspace)["skills"]
            except Exception:
                skills = {}
        missing = [k for k, v in skills.items() if not v]
        base.update({
            "title": "分析：盘点材料、列缺口",
            "do": "先看用户已给什么，再列缺口和待确认问题；一次问完，不要先做实验。",
            "expected": ["材料清单.md", "_worker/decisions.json"],
            "skills_missing": missing,
            "gate": "python worker.py gate --name analyze",
            "decide": "python worker.py decide --key materials --value complete/no --note ...",
            "then": "python worker.py advance --to COLLECT 或 PLAN",
        })
        if missing:
            base["warning"] = f"缺依赖 skill：{missing}；先问用户安装/复制，缺依赖不硬跑"
    elif phase == "COLLECT":
        base.update({
            "title": "收集：等用户补材料/数据",
            "do": "把用户补的材料放进任务目录，更新材料清单；用户说没有就用 decide 记录，不追问。",
            "expected": ["材料清单.md", "_worker/decisions.json"],
            "gate": "python worker.py gate --name analyze",
            "then": "python worker.py advance --to ORGANIZE",
        })
    elif phase == "ORGANIZE":
        base.update({
            "title": "整理：证据、数据、来源",
            "do": "按证据 ID 整理 Data/；每个目的至少一条证据；截图只规划核心区域。",
            "expected": ["Data/证据计划.md", "材料清单.md", "_worker/decisions.json"],
            "gate": "python worker.py gate --name analyze",
            "then": "python worker.py advance --to PLAN",
        })
    elif phase == "PLAN":
        base.update({
            "title": "规划：调用 report-planner",
            "do": "按 01_planner.md 调用 planner。**执行卡和实验指导书都要产出**，"
                   "再写 _worker/plan.json；先把方案/大纲发给用户确认。",
            "expected": ["实验执行卡.md", "实验指导书.md", "_worker/plan.json",
                         "_worker/roles/planner.result.json"],
            "gate": "python verify.py --workspace <WS> artifacts",
            "then": "python worker.py record --role planner --file _worker/roles/planner.result.json",
        })
    elif phase == "PLAN_FREEZE":
        base.update({
            "title": "冻结计划",
            "do": "向用户展示实际方案、目的、差异、交付；确认后冻结。",
            "command": "python worker.py gate --name plan",
            "then": "python worker.py freeze --confirm",
        })
    elif phase == "EXECUTE":
        step = next_step(workspace, state)
        base.update({
            "title": "执行下一步",
            "step": step,
            "last_action": last_action_for(workspace, str((step or {}).get("id", ""))),
            "do": "按 02_operator.md 执行；CLI 为主，GUI 补视觉证据；截图只截核心。",
            "heartbeat": "python worker.py heartbeat",
            "then": "python worker.py record --role operator --file _worker/roles/operator.result.json",
        })
        if step is None:
            base["title"] = "执行完成：先做截图验收"
            base["do"] = ("所有步骤完成。先按执行卡的阶段做证据验收，"
                          "把结果写进 截图验收.md；有不通过项就补拍或改执行卡，"
                          "**不要直接进 writer**。L1 全部通过、步骤全部完成/跳过后，"
                          "再 advance --to WRITE。")
            base["gate"] = "python verify.py --workspace <WS> execution"
            base["then"] = "python worker.py advance --to WRITE"
    elif phase == "WRITE":
        base.update({
            "title": "撰写：调用 report-writer",
            "round": state["report"].get("round", 1),
            "do": "按 03_writer.md 调用 writer；模板或自由写作；原子落盘。",
            "expected": [f"报告/报告-v{state['report'].get('round', 1)}.<doc|docx>"],
            "then": "python worker.py record --role writer --file _worker/roles/writer.result.json",
        })
    elif phase == "REVIEW":
        base.update({
            "title": "评审：调用 report-reviewer",
            "round": state["report"].get("round", 1),
            "do": "按 04_reviewer.md 审核；严谨/对比/辩证/全面；产出审核报告。",
            "expected": [f"报告/报告-审核报告-v{state['report'].get('round', 1)}.md"],
            "then": "python worker.py record --role reviewer --file _worker/roles/reviewer.result.json",
        })
    elif phase == "REVISE":
        base.update({
            "title": "修改：核实并路由审核发现",
            "do": "按 04_reviewer.md 的 REVISE 节；只重跑受影响的下游；同一问题 2 轮未修复转 BLOCKED。",
            "expected": ["_worker/roles/reviewer.result.json"],
            "then": "python worker.py advance --to EXECUTE/WRITE/PLAN/DONE",
        })
    elif phase == "WAITING_USER":
        base.update({
            "title": "等待用户",
            "do": "用户补材料/做物理步骤/确认后，resume 继续。",
            "then": "python worker.py resume --back",
        })
    elif phase == "DONE":
        base.update({"title": "完成", "do": "DoD 满足；交付报告、证据、审核记录、动作日志。"})
    elif phase == "BLOCKED":
        base.update({"title": "阻塞", "do": "查看 history/logs，向用户说明阻塞项；不要强行继续。"})
    return base


def advance(state: dict, to_phase: str) -> None:
    current = state["phase"]
    if to_phase not in PHASES:
        raise SystemExit(f"unknown phase: {to_phase}")
    if to_phase not in ALLOWED.get(current, set()):
        raise SystemExit(f"illegal transition: {current} -> {to_phase}")
    if to_phase == "EXECUTE" and not state.get("plan", {}).get("frozen"):
        raise SystemExit("plan is not frozen; run freeze --confirm first")
    if to_phase == "PLAN" and current in ("ANALYZE", "COLLECT", "ORGANIZE"):
        try:
            import verify as verify_mod
            gate = verify_mod.analyze_gate(Path(state["workspace"]), state)
        except Exception as exc:
            raise SystemExit(f"analyze gate failed to run: {exc}")
        if not gate.get("ok"):
            raise SystemExit("analyze gate failed: " + "; ".join(gate.get("errors", [])) +
                             " (run worker.py gate --name analyze; record decisions with decide)")
    if to_phase == "PLAN_FREEZE" and current == "PLAN":
        try:
            import verify as verify_mod
            decisions = verify_mod.decision_gate(Path(state["workspace"]), state)
            artifacts = verify_mod.plan_artifacts_gate(Path(state["workspace"]), state)
        except Exception as exc:
            raise SystemExit(f"plan gate failed to run: {exc}")
        if not decisions.get("ok"):
            raise SystemExit("interaction decision gate failed: " +
                             "; ".join(decisions.get("errors", [])) +
                             " (record code_policy / delivery / template / formula "
                             "decisions with worker.py decide)")
        if not artifacts.get("ok"):
            raise SystemExit("plan artifacts gate failed: " +
                             "; ".join(artifacts.get("errors", [])) +
                             " (PLAN must produce both 实验执行卡.md and 实验指导书.md)")
    if to_phase == "WRITE":
        try:
            import verify as verify_mod
            gate = verify_mod.execution_gate(Path(state["workspace"]), state)
        except Exception as exc:
            raise SystemExit(f"execution gate failed to run: {exc}")
        if not gate.get("ok"):
            raise SystemExit("execution gate failed: " +
                             "; ".join(gate.get("errors", [])) +
                             " (finish steps and screenshot acceptance before WRITE)")
    state["phase"] = to_phase
    log_event(state, "advance", **{"from": current, "to": to_phase})


def record_result(state: dict, role: str, result: dict) -> str:
    status = str(result.get("status", "")).lower()
    state.setdefault("role_results", {})[role] = result
    log_event(state, "role_result", role=role, status=status,
              summary=result.get("summary", ""))
    if status == "blocked":
        state["previous_phase"] = state["phase"]
        return "BLOCKED"
    if status == "needs_user":
        state["previous_phase"] = state["phase"]
        return "WAITING_USER"
    if role == "planner":
        return "PLAN_FREEZE"
    if role == "operator":
        step = str(result.get("step", ""))
        verdict = str(result.get("verdict", "")).lower()
        if step:
            state["execution"]["step"] = step
        if verdict == "pass" and step:
            if step not in state["execution"]["completed"]:
                state["execution"]["completed"].append(step)
        return "EXECUTE"
    if role == "writer":
        return "REVIEW"
    if role == "reviewer":
        nxt = str(result.get("next", "")).upper()
        if nxt in ALLOWED["REVIEW"]:
            return nxt
        verdict = str(result.get("verdict", ""))
        if verdict == "通过" and not result.get("blocking"):
            return "DONE"
        return "REVISE"
    return state["phase"]


def cmd_init(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    path = state_path(workspace)
    if path.exists() and not args.force:
        raise SystemExit(f"state already exists: {path} (use --force to re-init)")
    create_dirs(workspace)
    state = default_state(workspace, args.autonomy, args.env, args.target, args.task_name)
    save_state(workspace, state)
    skills = {}
    try:
        import env as env_mod
        env_mod.write_capabilities(workspace, env_mod.probe())
        skills = env_mod.check_skills(workspace)
    except Exception as exc:
        log_event(state, "env_probe_failed", error=str(exc))
    log_event(state, "init", autonomy=args.autonomy, env=args.env,
              skills_missing=skills.get("missing", []))
    save_state(workspace, state)
    print(json.dumps({"state": str(path), "skills": skills,
                      "next": next_action(workspace, state)},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(f"run:       {state['run_id']}")
        print(f"workspace: {state['workspace']}")
        print(f"phase:     {state['phase']}")
        print(f"autonomy:  {state['autonomy']}")
        print(f"plan:      {state['plan']['path']} (frozen={state['plan']['frozen']})")
        print(f"step:      {state['execution'].get('step') or '-'}")
        print(f"completed: {len(state['execution'].get('completed', []))}")
        print(f"decisions: {len(state.get('decisions', []))}")
        print(f"report:    round {state['report'].get('round', 1)}")
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    print(json.dumps(next_action(workspace, load_state(workspace)),
                     ensure_ascii=False, indent=2))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    path = Path(args.file)
    if not path.is_absolute():
        path = workspace / path
    result = read_json(path)
    if not isinstance(result, dict):
        raise SystemExit(f"result file is not a JSON object: {path}")
    role = args.role
    nxt = record_result(state, role, result)
    try:
        advance(state, nxt)
    except SystemExit as exc:
        # Hard gates must not be bypassed by the "force" fallback: if planner
        # skipped a deliverable, or execution jumped to WRITE early, stop here.
        if nxt in ("PLAN_FREEZE", "WRITE"):
            raise SystemExit(str(exc))
        state["phase"] = nxt
        log_event(state, "recorded", role=role, next=nxt, forced=True)
    save_state(workspace, state)
    notify_if_done(workspace, state)
    print(json.dumps({"recorded": role, "phase": state["phase"],
                      "next": next_action(workspace, state)},
                     ensure_ascii=False, indent=2))
    return 0


def notify_if_done(workspace: Path, state: dict) -> None:
    """Bring the agent window forward when the report is done.

    Telling the user "do not touch the keyboard" and then finishing silently is
    exactly how a finished report goes unnoticed. Best effort; never blocks.
    """
    if state.get("phase") != "DONE":
        return
    title = str(state.get("agent_window", "") or "")
    if not title:
        return
    try:
        import desktop
        desktop.notify(title, "报告已完成，请查看交付文件与审核报告")
    except Exception:
        pass


def cmd_advance(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    advance(state, args.to)
    save_state(workspace, state)
    notify_if_done(workspace, state)
    print(json.dumps({"phase": state["phase"], "next": next_action(workspace, state)},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    if not args.confirm:
        raise SystemExit("freeze requires --confirm after the user approves the plan")
    plan = load_plan(workspace, state)
    if not isinstance(plan, dict):
        raise SystemExit(f"plan not found: {state['plan']['path']}")
    import verify as verify_mod
    result = verify_mod.validate_plan(plan)
    if not result.get("ok"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit("plan gate failed")
    state["plan"].update({"frozen": True, "version": str(plan.get("version", "1.0")),
                          "gate": result})
    if state["phase"] == "PLAN":
        advance(state, "PLAN_FREEZE")
    advance(state, "EXECUTE")
    log_event(state, "plan_frozen", version=state["plan"]["version"])
    save_state(workspace, state)
    print(json.dumps({"frozen": True, "phase": state["phase"],
                      "next": next_action(workspace, state)},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_complete_step(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    if args.step not in state["execution"]["completed"]:
        state["execution"]["completed"].append(args.step)
    state["execution"]["step"] = args.step
    log_event(state, "step_completed", step=args.step)
    save_state(workspace, state)
    nxt = next_step(workspace, state)
    print(json.dumps({"completed": args.step, "next_step": nxt,
                      "all_done": nxt is None}, ensure_ascii=False, indent=2))
    return 0


def cmd_skip_step(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    if args.step not in state["execution"]["skipped"]:
        state["execution"]["skipped"].append(args.step)
    log_event(state, "step_skipped", step=args.step, reason=args.reason)
    save_state(workspace, state)
    print(json.dumps({"skipped": args.step, "next_step": next_step(workspace, state)},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    if args.autonomy:
        if args.autonomy not in ("observe", "assist", "auto", "full"):
            raise SystemExit("autonomy must be observe|assist|auto|full")
        state["autonomy"] = args.autonomy
    if args.env:
        state["environment"]["type"] = args.env
    if args.target is not None:
        state["environment"]["target"] = args.target
    if args.budget:
        for item in args.budget:
            if "=" not in item:
                raise SystemExit(f"budget must be key=value: {item}")
            key, value = item.split("=", 1)
            if key not in state["budgets"]:
                raise SystemExit(f"unknown budget: {key}")
            state["budgets"][key] = int(value)
    if args.task_name:
        state["task"]["name"] = args.task_name
    if args.template:
        state["task"]["template"] = args.template
    if args.report:
        state["task"]["report"] = args.report
    if getattr(args, "review", ""):
        state["report"]["review_path"] = args.review
    if getattr(args, "agent_window", ""):
        state["agent_window"] = args.agent_window
    log_event(state, "settings", **{k: v for k, v in vars(args).items()
                                    if k != "func" and v is not None})
    save_state(workspace, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_round(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    if args.next:
        state["report"]["round"] = int(state["report"].get("round", 1)) + 1
    log_event(state, "report_round", round=state["report"]["round"])
    save_state(workspace, state)
    print(json.dumps({"round": state["report"]["round"]}, ensure_ascii=False))
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    entry = {"at": now(), "key": args.key, "value": args.value,
             "note": args.note or ""}
    state.setdefault("decisions", []).append(entry)
    log_event(state, "decision", **entry)
    save_state(workspace, state)
    _durable.atomic_write_json(workspace / "_worker" / "decisions.json",
                               {"items": state["decisions"]}, backup=True)
    print(json.dumps({"recorded": entry, "count": len(state["decisions"])},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    import verify as verify_mod
    if args.name == "analyze":
        result = verify_mod.analyze_gate(workspace, state)
    elif args.name == "plan":
        result = verify_mod.validate_plan(load_plan(workspace, state))
    elif args.name == "decisions":
        result = verify_mod.decision_gate(workspace, state)
    elif args.name == "artifacts":
        result = verify_mod.plan_artifacts_gate(workspace, state)
    elif args.name == "execution":
        result = verify_mod.execution_gate(workspace, state)
    elif args.name == "step":
        result_path = Path(args.file or "_worker/actions/last.json")
        if not result_path.is_absolute():
            result_path = workspace / result_path
        result = verify_mod.check_step(load_plan(workspace, state) or {},
                                       args.step, read_json(result_path, {}), workspace)
    elif args.name == "evidence":
        path = Path(args.file or state["evidence"]["path"])
        if not path.is_absolute():
            path = workspace / path
        result = verify_mod.check_evidence(read_json(path, {}), workspace)
    elif args.name == "report":
        report = Path(args.file or state["task"].get("report") or "")
        if not report.is_absolute():
            report = workspace / report
        template = Path(state["task"].get("template") or "")
        if str(template) in ("", "."):
            template = None
        elif not template.is_absolute():
            template = workspace / template
        result = verify_mod.check_report(report, template)
    elif args.name == "review":
        review = Path(args.file or state["report"].get("review_path") or "")
        if not review.is_absolute():
            review = workspace / review
        result = verify_mod.check_review(verify_mod.parse_review(review))
        result["parsed"] = verify_mod.parse_review(review)
    elif args.name == "dod":
        result = verify_mod.check_dod(workspace, state)
    else:
        raise SystemExit("gate must be analyze|plan|decisions|artifacts|execution|"
                         "step|evidence|report|review|dod")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _age_seconds(value: str) -> float | None:
    try:
        then = datetime.fromisoformat(value)
        return (datetime.now(then.tzinfo) - then).total_seconds()
    except (TypeError, ValueError):
        return None


def doctor(workspace: Path, state: dict | None = None, recover: bool = False) -> dict:
    issues: list[str] = []
    hints: list[str] = []
    path = state_path(workspace)
    data, source, error = _durable.read_json_with_backup(path)
    if not isinstance(data, dict):
        issues.append(f"state unreadable: {error}")
        data = state or {}
    elif source != str(path):
        issues.append(f"state recovered from backup: {source}")
        if recover:
            _durable.atomic_write_json(path, data, backup=False)
    phase = str(data.get("phase", "")) if isinstance(data, dict) else ""
    for tmp in sorted((workspace / "_worker").glob("*.tmp")):
        issues.append(f"leftover temp file: {tmp.relative_to(workspace)}")
    for folder, patterns in ((workspace, ("*.tmp", "*.tmp.*", "~$*")),
                             (workspace / "报告", ("*.tmp", "*.tmp.*", "~$*"))):
        if not folder.exists():
            continue
        for pattern in patterns:
            for tmp in sorted(folder.glob(pattern)):
                issues.append(f"leftover temp/lock file: {tmp.relative_to(workspace)}")
    intents = _durable.list_intents(workspace)
    for intent in intents:
        issues.append(f"in-flight action {intent.get('id', '?')} "
                      f"step={intent.get('step', '?')} pid={intent.get('pid', '?')}")
    decisions = data.get("decisions", []) if isinstance(data, dict) else []
    if phase not in ("ANALYZE", "") and not decisions:
        issues.append("no user decisions recorded; run worker.py decide before PLAN")
    completed = set(data.get("execution", {}).get("completed", [])) if isinstance(data, dict) else set()
    actions_path = workspace / "_worker" / "actions.jsonl"
    last_by_step: dict[str, dict] = {}
    if actions_path.exists():
        for line in actions_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = str(row.get("step", ""))
            if sid:
                last_by_step[sid] = row
    for sid, row in last_by_step.items():
        if sid not in completed and str(row.get("status", "")).lower() in ("pass", "ok", "done"):
            hints.append(f"step {sid} has a passed action {row.get('id')} but is not completed")
    ev_path = workspace / "_worker" / "evidence.json"
    ev, ev_source, ev_error = _durable.read_json_with_backup(ev_path)
    if ev is None and (ev_path.exists() or phase in ("WRITE", "REVIEW", "REVISE", "DONE")):
        issues.append(f"evidence manifest unreadable: {ev_error}")
    elif ev is not None and ev_source != str(ev_path):
        issues.append(f"evidence manifest recovered from backup: {ev_source}")
    budgets = data.get("budgets", {}) if isinstance(data, dict) else {}
    hb_age = _age_seconds(str(data.get("last_heartbeat", "")))
    if hb_age is not None and hb_age > 2 * int(budgets.get("heartbeat_seconds", 60)) \
            and phase not in ("DONE", "BLOCKED"):
        issues.append(f"stale heartbeat: {int(hb_age)}s (phase={phase})")
    total = _durable.total_log_size(workspace)
    if total > int(budgets.get("max_log_bytes", 50 * 1024 * 1024)):
        issues.append("logs exceed budget; run worker.py logs --rotate")
    report = {"ok": not issues, "phase": phase, "state_source": source,
              "issues": issues, "hints": hints, "in_flight": intents,
              "log_bytes": total}
    if recover:
        crashes = workspace / "_worker" / "logs" / "crashes"
        crashes.mkdir(parents=True, exist_ok=True)
        recovery = {"at": now(), "issues": issues, "in_flight": intents}
        _durable.atomic_write_json(crashes / f"doctor-{datetime.now():%Y%m%d-%H%M%S}.json",
                                   recovery, backup=False)
        _durable.atomic_write_json(workspace / "_worker" / "recovery.json",
                                   recovery, backup=True)
        report["recovery_file"] = str(workspace / "_worker" / "recovery.json")
    return report


def cmd_doctor(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    try:
        state = load_state(workspace)
    except SystemExit:
        state = None
    result = doctor(workspace, state, recover=args.recover)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") or args.recover else 1


def cmd_heartbeat(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    save_state(workspace, state)
    log_event(state, "heartbeat", phase=state["phase"])
    save_state(workspace, state)
    print(json.dumps({"ok": True, "last_heartbeat": state["last_heartbeat"]},
                     ensure_ascii=False))
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    logs = workspace / "_worker" / "logs"
    if args.list:
        print(json.dumps({"logs": _durable.list_logs(workspace),
                          "total_bytes": _durable.total_log_size(workspace)},
                         ensure_ascii=False, indent=2))
        return 0
    if args.rotate:
        state = load_state(workspace)
        max_bytes = int(state.get("budgets", {}).get("max_log_bytes", 50 * 1024 * 1024))
        rotated = []
        for name in ("session.log", "events.jsonl"):
            if _durable.rotate_log(logs / name, max_bytes, keep=3):
                rotated.append(name)
        print(json.dumps({"rotated": rotated, "max_bytes": max_bytes},
                         ensure_ascii=False, indent=2))
        return 0
    session = logs / "session.log"
    if session.exists():
        lines = session.read_text(encoding="utf-8", errors="replace").splitlines()
        print("\n".join(lines[-args.tail:]))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    diag = doctor(workspace, recover=args.recover)
    state = load_state(workspace)
    if state["phase"] == "WAITING_USER" and args.back:
        prev = state.get("previous_phase") or "EXECUTE"
        advance(state, prev)
        save_state(workspace, state)
    print(json.dumps({"phase": state["phase"], "doctor": diag,
                      "next": next_action(workspace, state)},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    if not args.confirm:
        raise SystemExit("cleanup requires --confirm after the user agrees")
    if args.scope == "all":
        targets = [workspace / "_worker"]
    else:
        targets = [
            workspace / "报告" / "_work",
            workspace / "Pictures" / "_raw",
            workspace / "_worker" / "actions",
            workspace / "_worker" / "logs",
            workspace / "_worker" / "backups",
        ]
    removed = []
    for target in targets:
        try:
            target.resolve().relative_to(workspace)
        except ValueError:
            continue
        if target.exists():
            shutil.rmtree(target)
            removed.append(str(target.relative_to(workspace)))
    print(json.dumps({"removed": removed, "scope": args.scope},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    print(json.dumps(load_state(workspace).get("history", []),
                     ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="report-worker state machine")
    ap.add_argument("--workspace", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--autonomy", default="assist",
                   choices=["observe", "assist", "auto", "full"])
    p.add_argument("--env", default="local", choices=["local", "wsl", "ssh"])
    p.add_argument("--target", default="")
    p.add_argument("--task-name", default="")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("next")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("record")
    p.add_argument("--role", required=True,
                   choices=["planner", "operator", "writer", "reviewer"])
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("advance")
    p.add_argument("--to", required=True, choices=PHASES)
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("freeze")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_freeze)

    p = sub.add_parser("complete-step")
    p.add_argument("--step", required=True)
    p.set_defaults(func=cmd_complete_step)

    p = sub.add_parser("skip-step")
    p.add_argument("--step", required=True)
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_skip_step)

    p = sub.add_parser("set")
    p.add_argument("--autonomy", choices=["observe", "assist", "auto", "full"])
    p.add_argument("--env", choices=["local", "wsl", "ssh"])
    p.add_argument("--target")
    p.add_argument("--budget", action="append")
    p.add_argument("--task-name")
    p.add_argument("--template")
    p.add_argument("--report")
    p.add_argument("--review")
    p.add_argument("--agent-window")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("round")
    p.add_argument("--next", action="store_true")
    p.set_defaults(func=cmd_round)

    p = sub.add_parser("decide")
    p.add_argument("--key", required=True)
    p.add_argument("--value", required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("gate")
    p.add_argument("--name", required=True,
                   choices=["analyze", "plan", "decisions", "artifacts",
                            "execution", "step", "evidence", "report", "review", "dod"])
    p.add_argument("--step", default="")
    p.add_argument("--file", default="")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("doctor")
    p.add_argument("--recover", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("heartbeat")
    p.set_defaults(func=cmd_heartbeat)

    p = sub.add_parser("logs")
    p.add_argument("--list", action="store_true")
    p.add_argument("--tail", type=int, default=40)
    p.add_argument("--rotate", action="store_true")
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("resume")
    p.add_argument("--back", action="store_true")
    p.add_argument("--recover", action="store_true")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("cleanup")
    p.add_argument("--scope", choices=["intermediate", "all"], default="intermediate")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_cleanup)

    p = sub.add_parser("history")
    p.set_defaults(func=cmd_history)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
