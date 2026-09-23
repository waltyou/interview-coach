"""Persist the small amount of conversational state needed by the next Agent."""
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from uuid import uuid4

from common import PACK_ROOT, load_cycles, load_json, load_questions, now_iso, write_json

SESSION_ROOT = PACK_ROOT / "workspace" / "sessions"
STAGES = {"awaiting_answer", "awaiting_followup", "awaiting_retry", "ready", "teaching", "completed"}


def session_issues(session: dict, cycles: dict, questions: dict) -> list[str]:
    from teach import teaching_issues
    issues = teaching_issues(session)
    if session.get("schema_version") != 1:
        issues.append("unsupported session schema_version")
    if not re.fullmatch(r"practice-session\.[A-Za-z0-9.-]+", session.get("id", "")):
        issues.append("invalid session id")
    if session.get("stage") not in STAGES:
        issues.append("invalid session stage")
    if session.get("mode") not in {"learning", "mock"}:
        issues.append("invalid practice mode")
    if type(session.get("time_budget_minutes")) is not int or session["time_budget_minutes"] < 1:
        issues.append("time budget must be a positive integer")
    for field in ("goal", "created_at", "updated_at"):
        if not isinstance(session.get(field), str) or not session[field].strip():
            issues.append(f"missing {field}")
    cycle = cycles.get(session.get("cycle_id"))
    if cycle is None:
        issues.append("unknown session cycle")
    current = session.get("current_question")
    if current is not None and not isinstance(current, dict):
        return issues + ["current_question must be an object or null"]
    if session.get("stage") in {"awaiting_answer", "awaiting_followup", "awaiting_retry"} and not current:
        issues.append("waiting stage requires a current question")
    if current:
        qid = current.get("question_id")
        if qid not in questions or cycle and qid not in cycle["question_ids"]:
            issues.append("session question is outside the cycle")
        if type(current.get("question_revision")) is not int or current["question_revision"] < 1:
            issues.append("missing question revision")
        if not isinstance(current.get("prompt"), str) or not current["prompt"].strip():
            issues.append("missing prompt snapshot")
    if session.get("stage") in {"awaiting_followup", "awaiting_retry"} and not session.get("pending_prompt"):
        issues.append("followup/retry requires pending_prompt")
    hints = session.get("hints_used")
    if session.get("assistance", "unknown") not in {"independent", "hints", "reference_seen", "unknown"}:
        issues.append("invalid session assistance")
    if session.get("assistance") == "independent" and hints:
        issues.append("independent session cannot contain hints")
    seen = session.get("reference_seen_questions", [])
    if not isinstance(seen, list) or any(not isinstance(qid, str) or qid not in questions for qid in seen):
        issues.append("invalid reference_seen_questions")
        seen = []
    if current and current.get("question_id") in seen and session.get("assistance") != "reference_seen":
        issues.append("reference exposure cannot be reset for this question")
    if not isinstance(hints, list):
        issues.append("hints_used must be a list")
    else:
        levels = []
        for hint in hints:
            if not isinstance(hint, dict) or type(hint.get("level")) is not int or hint["level"] < 1 or not hint.get("text"):
                issues.append("hint requires a positive level and text snapshot")
            else:
                levels.append(hint["level"])
        if len(set(levels)) != len(levels):
            issues.append("duplicate hint level")
    return issues


def load_sessions(root=SESSION_ROOT) -> list[dict]:
    return [load_json(path) for path in sorted(root.glob("*.json"))] if root.exists() else []


def resumable(cycle_id: str, root=SESSION_ROOT) -> dict | None:
    matches = [s for s in load_sessions(root) if s.get("cycle_id") == cycle_id and s.get("stage") != "completed"]
    if len(matches) > 1:
        raise ValueError("Multiple unfinished sessions; choose --session-id before continuing")
    return matches[0] if matches else None


def save_session(session: dict, *, cycles=None, questions=None, root=SESSION_ROOT) -> dict:
    issues = session_issues(session, cycles if cycles is not None else load_cycles(),
                            questions if questions is not None else load_questions())
    if issues:
        raise ValueError("; ".join(issues))
    write_json(root / f"{session['id']}.json", session)
    return session


def start_session(cycle: dict, *, goal="完成今天的练习", minutes=None, mode="learning", root=SESSION_ROOT) -> dict:
    if cycle["status"] != "active":
        raise ValueError("Practice requires an active cycle")
    existing = resumable(cycle["id"], root)
    if existing:
        return existing
    if minutes is None:
        from discover import PROFILE_PATH, load_profile
        profile = load_profile() if PROFILE_PATH.is_file() else {}
        from common import practice_budget
        minutes = practice_budget(profile=profile)
    timestamp = now_iso()
    session = {"$schema": "../../protocol/schemas/practice-session.schema.json", "schema_version": 1,
               "id": f"practice-session.{uuid4().hex}", "cycle_id": cycle["id"],
               "created_at": timestamp, "updated_at": timestamp, "mode": mode,
               "goal": goal, "time_budget_minutes": minutes, "stage": "ready",
               "current_question": None, "hints_used": [], "pending_prompt": None,
               "assistance": "unknown", "reference_seen_questions": []}
    return save_session(session, cycles={cycle["id"]: cycle}, questions={}, root=root)


def checkpoint(session: dict, *, selection=None, stage=None, hint=None, pending_prompt=None, reference_seen=False, minutes=None) -> dict:
    if stage == "teaching" or (session.get("stage") == "teaching" and
                              (selection is not None or stage is not None or hint is not None or pending_prompt is not None or reference_seen)):
        raise ValueError("Use teach.py to update or finish the active teaching loop")
    if session["stage"] == "completed" and (selection is not None or hint is not None or stage not in {None, "completed"} or pending_prompt is not None or reference_seen or minutes is not None):
        raise ValueError("A completed session cannot be resumed; start a new session")
    result = deepcopy(session)
    if selection is not None:
        if session["stage"] != "ready":
            raise ValueError("Resolve the pending question before selecting another")
        result["current_question"] = {key: selection[key] for key in ("question_id", "question_revision", "prompt")}
        result["hints_used"] = []
        result["pending_prompt"] = None
        result["stage"] = "awaiting_answer"
        result["assistance"] = "reference_seen" if selection["question_id"] in result.get("reference_seen_questions", []) else "independent"
    if hint is not None:
        if result["stage"] not in {"awaiting_answer", "awaiting_followup", "awaiting_retry"}:
            raise ValueError("Hints require a pending question")
        result["hints_used"].append(hint)
        if result.get("assistance") != "reference_seen":
            result["assistance"] = "hints"
    if reference_seen:
        if result["stage"] not in {"awaiting_answer", "awaiting_followup", "awaiting_retry"} or not result.get("current_question"):
            raise ValueError("Reference exposure requires a pending question")
        result["assistance"] = "reference_seen"
        seen = result.setdefault("reference_seen_questions", [])
        qid = result["current_question"]["question_id"]
        if qid not in seen:
            seen.append(qid)
    if stage is not None:
        result["stage"] = stage
        if stage == "ready":
            result["current_question"] = None
            result["hints_used"] = []
            result["pending_prompt"] = None
    if pending_prompt is not None:
        result["pending_prompt"] = pending_prompt
    if minutes is not None:
        result["time_budget_minutes"] = minutes
    result["updated_at"] = now_iso()
    return result


def resume_result(session: dict, cycle: dict, questions: dict) -> dict | None:
    issues = session_issues(session, {cycle["id"]: cycle}, questions)
    if issues:
        raise ValueError("; ".join(issues))
    if session["stage"] in {"ready", "completed"}:
        return None
    if session["stage"] == "teaching":
        from teach import active_teaching
        current = session.get("current_question")
        return {"status": "resume_teaching", "practice_session_id": session["id"],
                "cycle_id": cycle["id"], "stage": "teaching", "teaching": deepcopy(active_teaching(session)),
                "current_question": current, "mode": session["mode"],
                "time_budget_minutes": session["time_budget_minutes"],
                "question_changed": bool(current and (questions[current["question_id"]]["revision"] != current["question_revision"]
                                          or questions[current["question_id"]]["status"] != "active"))}
    current = session["current_question"]
    question = questions[current["question_id"]]
    return {"status": "resume", "practice_session_id": session["id"], "cycle_id": cycle["id"],
            **current, "stage": session["stage"], "hints_used": session["hints_used"],
            "assistance": answer_context(session).get("assistance", "unknown"),
            "pending_prompt": session.get("pending_prompt"), "mode": session["mode"],
            "goal": session["goal"], "time_budget_minutes": session["time_budget_minutes"],
            "question_changed": question["revision"] != current["question_revision"] or question["status"] != "active"}


def answer_context(session: dict) -> dict:
    """Copy these fields into the next AttemptEvent before changing the checkpoint."""
    if not session.get("current_question") or session["stage"] not in {"awaiting_answer", "awaiting_retry", "awaiting_followup"}:
        raise ValueError("There is no pending answer to record")
    result = {"cycle_id": session["cycle_id"], "practice_session_id": session["id"],
              "question_id": session["current_question"]["question_id"],
              "question_revision": session["current_question"]["question_revision"],
              "hints_used": [hint["level"] for hint in session["hints_used"]]}
    assistance = session.get("assistance", "unknown")
    if result["question_id"] in session.get("reference_seen_questions", []):
        assistance = "reference_seen"
    elif result["hints_used"] and assistance != "reference_seen":
        assistance = "hints"
    if assistance != "unknown":
        result["assistance"] = assistance
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "start", "checkpoint", "finish", "trial", "answer-context"))
    parser.add_argument("--cycle-id")
    parser.add_argument("--session-id")
    parser.add_argument("--goal", default="完成今天的练习")
    parser.add_argument("--minutes", type=int)
    parser.add_argument("--reference-seen", action="store_true")
    parser.add_argument("--mode", choices=("learning", "mock"), default="learning")
    parser.add_argument("--stage", choices=sorted(STAGES))
    parser.add_argument("--hint-level", type=int)
    parser.add_argument("--hint-text")
    parser.add_argument("--pending-prompt")
    args = parser.parse_args()
    try:
        if args.command == "trial":
            public = [q for q in load_questions().values() if q["visibility"] == "public" and q["status"] == "active"]
            if not public:
                raise ValueError("No public question available")
            from select_next import choose
            topic = choose(sorted({q["topic"].split(".")[0] for q in public}), None)
            q = choose([q for q in public if q["topic"].split(".")[0] == topic], None)
            result = {"status": "trial", "question_id": q["id"], "question_revision": q["revision"],
                      "prompt": q["prompt"], "hint_count": len(q["hints"]), "persistence": "none",
                      "notice": "这次先试一道公共题，回答和评价不写入项目。当前聊天平台仍可能保存对话。"}
        elif args.command == "status":
            result = {"sessions": [s for s in load_sessions() if s["stage"] != "completed"
                                   and (not args.cycle_id or s["cycle_id"] == args.cycle_id)]}
        elif args.command == "start":
            cycles = load_cycles()
            if args.cycle_id not in cycles:
                raise ValueError("Choose an existing --cycle-id")
            result = start_session(cycles[args.cycle_id], goal=args.goal, minutes=args.minutes, mode=args.mode)
        else:
            matches = [s for s in load_sessions() if s["id"] == args.session_id]
            if len(matches) != 1:
                raise ValueError("Choose an existing --session-id")
            if args.command == "answer-context":
                print(json.dumps(answer_context(matches[0]), ensure_ascii=False, indent=2))
                return
            hint = None
            if args.hint_level is not None or args.hint_text is not None:
                hint = {"level": args.hint_level, "text": args.hint_text}
            result = save_session(checkpoint(matches[0], stage="completed" if args.command == "finish" else args.stage,
                                             hint=hint, pending_prompt=args.pending_prompt,
                                             reference_seen=args.reference_seen, minutes=args.minutes))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
