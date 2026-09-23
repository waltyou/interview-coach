"""Persist a resumable teaching loop inside a private PracticeSession."""
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from uuid import uuid4

from common import load_cycles, load_json, now_iso

PHASES = ("probe", "teach", "transfer")
ASSISTANCE = ("independent", "hints", "reference_seen")


def text_value(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value, *, nonempty=False) -> bool:
    return isinstance(value, list) and (bool(value) or not nonempty) and all(text_value(x) for x in value)


def teaching_issues(session: dict) -> list[str]:
    records = session.get("teaching_sessions", [])
    if not isinstance(records, list):
        return ["teaching_sessions must be a list"]
    issues, ids, active = [], set(), []
    for record in records:
        if not isinstance(record, dict):
            issues.append("TeachingSession must be an object")
            continue
        tid = record.get("id")
        if not isinstance(tid, str) or not re.fullmatch(r"teaching-session\.[A-Za-z0-9.-]+", tid):
            issues.append("invalid teaching id")
        elif tid in ids:
            issues.append("duplicate teaching id")
        else:
            ids.add(tid)
        if record.get("schema_version") != 1:
            issues.append("invalid teaching schema_version")
        if "pending_check" not in record:
            issues.append("teaching requires pending_check")
        for field in ("goal", "gap", "created_at", "updated_at", "next_action"):
            if not text_value(record.get(field)):
                issues.append(f"teaching requires {field}")
        for field in ("evidence", "path", "sources"):
            if not string_list(record.get(field), nonempty=field == "evidence"):
                issues.append(f"invalid teaching {field}")
        path = record.get("path", [])
        step = record.get("current_step")
        if type(step) is not int or step < 0 or not isinstance(path, list) or step >= max(1, len(path)):
            issues.append("invalid teaching current_step")
        if record.get("phase") not in PHASES:
            issues.append("invalid teaching phase")
        if record.get("phase") in ("teach", "transfer") and not path:
            issues.append("teaching requires a local learning path")
        if record.get("status") not in ("active", "completed", "stopped"):
            issues.append("invalid teaching status")
        if record.get("status") == "active":
            active.append(record)
            if record.get("question") != session.get("current_question"):
                issues.append("active teaching question snapshot differs from practice")
        checks = record.get("checks")
        if not isinstance(checks, list):
            issues.append("teaching checks must be a list")
            checks = []
        pending = record.get("pending_check")
        for check in checks + ([pending] if pending is not None else []):
            if not isinstance(check, dict):
                issues.append("teaching check must be an object")
                continue
            for field in ("prompt", "created_at", "step"):
                if not text_value(check.get(field)):
                    issues.append(f"check requires {field}")
            if check.get("phase") not in PHASES or check.get("assistance") not in ASSISTANCE:
                issues.append("invalid check phase or assistance")
            if not isinstance(check.get("explanation"), str):
                issues.append("check explanation must be a string")
            if check.get("explanation") and check.get("assistance") == "independent":
                issues.append("an explanation-assisted check cannot be independent")
            if check is not pending:
                for field in ("answer", "feedback", "answered_at"):
                    if not text_value(check.get(field)):
                        issues.append(f"answered check requires {field}")
                if check.get("outcome") not in ("passed", "gap"):
                    issues.append("invalid check outcome")
        if record.get("status") in ("completed", "stopped"):
            if pending is not None or not text_value(record.get("summary")):
                issues.append("closed teaching requires summary and no pending check")
        if record.get("status") == "completed" and not transfer_passed(record):
            issues.append("completion requires a latest unassisted transfer pass")
        if record.get("status") == "active" and record.get("question"):
            assisted = any(isinstance(check, dict) and
                           (check.get("explanation") or check.get("assistance") in ("hints", "reference_seen"))
                           for check in checks + ([pending] if pending is not None else []))
            if assisted and session.get("assistance") != "reference_seen":
                issues.append("teaching exposure must remain reference_seen")
    if session.get("stage") == "teaching":
        if len(active) != 1 or not records or active[0] is not records[-1]:
            issues.append("teaching stage requires exactly one latest active TeachingSession")
        if session.get("mode") != "learning":
            issues.append("teaching requires learning mode")
    elif active:
        issues.append("active teaching requires teaching stage")
    return issues


def transfer_passed(record: dict) -> bool:
    checks = record.get("checks", [])
    last = checks[-1] if isinstance(checks, list) and checks else {}
    path = record.get("path", [])
    step = record.get("current_step")
    return (record.get("phase") == "transfer" and isinstance(path, list) and type(step) is int
            and 0 <= step < len(path) and isinstance(last, dict) and last.get("step") == path[step]
            and last.get("phase") == "transfer" and last.get("outcome") == "passed"
            and last.get("assistance") == "independent")


def active_teaching(session: dict) -> dict:
    if session.get("stage") != "teaching":
        raise ValueError("There is no active teaching session")
    issues = teaching_issues(session)
    if issues:
        raise ValueError("; ".join(issues))
    return session["teaching_sessions"][-1]


def start_teaching(session: dict, *, goal: str, gap: str, evidence: list[str]) -> dict:
    if session.get("mode") != "learning" or session.get("stage") not in {"ready", "awaiting_answer", "awaiting_followup", "awaiting_retry"}:
        raise ValueError("Start teaching from an unfinished learning practice; finish mock practice first")
    result = deepcopy(session)
    stamp = now_iso()
    result.setdefault("teaching_sessions", []).append({
        "schema_version": 1, "id": f"teaching-session.{uuid4().hex}", "status": "active",
        "goal": goal, "gap": gap, "evidence": evidence, "path": [], "current_step": 0,
        "phase": "probe", "sources": [], "checks": [], "pending_check": None,
        "question": deepcopy(session.get("current_question")),
        "created_at": stamp, "updated_at": stamp, "next_action": "Probe the relevant understanding gap",
    })
    result.update(stage="teaching", updated_at=stamp)
    issues = teaching_issues(result)
    if issues:
        raise ValueError("; ".join(issues))
    return result


def update_teaching(session: dict, command: str, data: dict) -> dict:
    result = deepcopy(session)
    record = active_teaching(result)
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    if command == "plan":
        if record["pending_check"] is not None:
            raise ValueError("Answer the pending check before replanning")
        allowed = {"gap", "evidence", "path", "current_step", "phase", "next_action", "sources"}
        if data.keys() - allowed:
            raise ValueError("Plan contains unsupported fields")
        record.update(data)
    elif command == "ask":
        if record["pending_check"] is not None:
            raise ValueError("Answer the pending check first")
        if data.keys() - {"prompt", "explanation", "assistance"}:
            raise ValueError("Check contains unsupported fields")
        check = {"prompt": data.get("prompt"), "explanation": data.get("explanation", ""),
                 "assistance": data.get("assistance"), "phase": record["phase"],
                 "step": record["path"][record["current_step"]] if record["path"] else "probe",
                 "created_at": now_iso()}
        record["pending_check"] = check
        # Teaching or hints about the parent question contaminate an immediate
        # retry. Preserve exposure through resume and later question selection.
        if result.get("current_question") and (check["explanation"] or check["assistance"] in ("hints", "reference_seen")):
            result["assistance"] = "reference_seen"
            qid = result["current_question"]["question_id"]
            seen = result.setdefault("reference_seen_questions", [])
            if qid not in seen:
                seen.append(qid)
    elif command == "answer":
        if record["pending_check"] is None:
            raise ValueError("There is no pending check to answer")
        if data.keys() - {"answer", "feedback", "outcome", "next_action"}:
            raise ValueError("Answer contains unsupported fields")
        check = deepcopy(record["pending_check"])
        check.update({key: data.get(key) for key in ("answer", "feedback", "outcome")})
        check["answered_at"] = now_iso()
        record["checks"].append(check)
        record["pending_check"] = None
        record["next_action"] = data.get("next_action")
    elif command in {"finish", "stop"}:
        if set(data) != {"summary", "next_action"}:
            raise ValueError("Closing input requires summary and next_action")
        if command == "finish" and (record["pending_check"] is not None or not transfer_passed(record)):
            raise ValueError("Complete a fresh unassisted transfer check before finishing")
        if record["pending_check"] is not None:
            record.setdefault("cancelled_checks", []).append(record["pending_check"])
            record["pending_check"] = None
        record.update(status="completed" if command == "finish" else "stopped", **data)
        result["stage"] = "awaiting_retry" if result.get("current_question") else "ready"
        result["pending_prompt"] = record["next_action"] if result.get("current_question") else None
    else:
        raise ValueError(f"Unknown teaching command: {command}")
    result["updated_at"] = record["updated_at"] = now_iso()
    issues = teaching_issues(result)
    if issues:
        raise ValueError("; ".join(issues))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "start", "plan", "ask", "answer", "finish", "stop"))
    parser.add_argument("--session-id")
    parser.add_argument("--input", help="Private UTF-8 JSON file containing the command payload")
    args = parser.parse_args()
    from pathlib import Path
    from practice import load_sessions, save_session
    try:
        sessions = [s for s in load_sessions() if not args.session_id or s["id"] == args.session_id]
        if args.command == "status":
            result = {"sessions": [s for s in sessions if s.get("stage") == "teaching"]}
        else:
            if not args.session_id or len(sessions) != 1 or not args.input:
                raise ValueError("Choose an existing --session-id and provide --input")
            session = sessions[0]
            cycle = load_cycles().get(session["cycle_id"])
            if not cycle or cycle["status"] != "active":
                raise ValueError("Teaching requires an active PreparationCycle")
            data = load_json(Path(args.input))
            if args.command == "start":
                if not isinstance(data, dict) or set(data) != {"goal", "gap", "evidence"}:
                    raise ValueError("Start input requires goal, gap and evidence")
                result = start_teaching(session, **data)
            else:
                result = update_teaching(session, args.command, data)
            save_session(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
