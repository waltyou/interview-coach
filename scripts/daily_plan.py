"""Build read-only practice suggestions from current answer evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import date

from common import knowledge_score, now_iso, practice_budget
from rebuild_state import build_cycle_progress, mastery_evidence, independent_attempt
from select_next import select_result

REASONS = {"due_for_review": "已到复习日期，先巩固上次回答",
           "unseen_topic_coverage": "补充尚未充分练到的能力",
           "unseen_curated_order": "按目标职位的准备优先级练习"}


def daily_plan(cycles: dict, questions: dict, events: list, sessions: list, *, today: date | None = None, minutes=15, profile=None) -> dict:
    today = today or date.today()
    active = [c for c in cycles.values() if c["status"] == "active"]
    minutes = practice_budget(profile=profile, default=minutes)
    base = {"as_of": today.isoformat(), "minutes": minutes, "tasks": [], "gaps": [], "improvement": None, "untested_topics": []}
    if not active:
        return {**base, "message": "先试一道题，或开始 8 题短测。", "command": "先试一道公共题，回答不写入项目。"}
    if len(active) > 1:
        return {**base, "message": "有多个进行中的准备周期，请先选择。", "command": "列出进行中的准备周期，让我选择今天练哪个。"}
    cycle = active[0]
    base["cycle_id"] = cycle["id"]
    current = [s for s in sessions if s.get("cycle_id") == cycle["id"] and s.get("stage") != "completed"]
    if len(current) > 1:
        return {**base, "message": "有多个未完成练习，请先选择需要恢复的一次。", "command": f"列出准备周期 {cycle['id']} 的未完成练习，让我选择。"}
    minutes = practice_budget(session=current[0] if current else None, profile=profile, default=minutes)
    base["minutes"] = minutes
    base["command"] = f"继续准备周期 {cycle['id']}，今天练 {minutes} 分钟；先恢复未完成题目，再按周期策略练习。"
    progress = build_cycle_progress(cycle, events, now_iso(), today)
    preview = deepcopy(progress)
    task_minutes = min(5, minutes)
    capacity = max(1, minutes // task_minutes)
    if current and current[0].get("current_question"):
        session = current[0]
        q = session["current_question"]
        base["tasks"].append({"question_id": q["question_id"], "prompt": q["prompt"], "minutes": task_minutes,
                              "reason": f"继续上次练习，已用 {len(session['hints_used'])} 级提示",
                              "stage": session["stage"], "practice_session_id": session["id"]})
        for item in preview["questions"]:
            if item["question_id"] == q["question_id"]:
                item.update(status="covered", next_due_at=None)
        preview["statistics"]["attempts_today"] += 1
    while len(base["tasks"]) < capacity:
        selection = select_result(cycle, preview, questions, seed=0)
        if selection["status"] != "selected":
            break
        base["tasks"].append({"question_id": selection["question_id"], "prompt": selection["prompt"], "minutes": task_minutes,
                              "reason": REASONS[selection["reason"]]})
        for item in preview["questions"]:
            if item["question_id"] == selection["question_id"]:
                item.update(status="covered", next_due_at=None)
        preview["statistics"]["attempts_today"] += 1
    base["message"] = f"每题约 {task_minutes} 分钟；后续题目会根据实际作答调整。" if base["tasks"] else "当前策略下没有可练题目，可查看历史或调整准备范围。"
    covered_topics = {questions[s["question_id"]]["topic"].split(".")[0] for s in progress["questions"]
                      if s["status"] != "unseen" and s["question_id"] in questions}
    all_topics = set(cycle["diagnostic"]["pool_topics"]) if cycle.get("diagnostic") else {
        questions[qid]["topic"].split(".")[0] for qid in cycle["question_ids"] if qid in questions}
    if cycle.get("diagnostic"):
        covered_topics = {cycle["diagnostic"]["question_topics"][s["question_id"]] for s in progress["questions"] if s["status"] != "unseen"}
    from diagnostic import coverage, capability_label
    base["diagnostic_coverage"] = coverage(cycle, progress)
    base["capability_labels"] = {name: capability_label(name) for name in cycle.get("diagnostic", {}).get("scope_capabilities", [])}
    base["awaiting_independent_question_ids"] = [s["question_id"] for s in progress["questions"] if s.get("evidence_status") == "awaiting_independent"]
    base["untested_topics"] = sorted(all_topics - covered_topics)
    cycle_events = [e for e in events if e["cycle_id"] == cycle["id"]]
    by_question = {}
    for event in sorted(cycle_events, key=lambda e: (e["occurred_at"], e["id"])):
        by_question.setdefault(event["question_id"], []).append(event)
    latest = [evidence for attempts in by_question.values() if (evidence := mastery_evidence(attempts)) is not None]
    for event in sorted(latest, key=lambda e: (knowledge_score(e["evaluation"]["scores"]), e["occurred_at"])):
        if knowledge_score(event["evaluation"]["scores"]) >= 3 or len(base["gaps"]) >= 2:
            continue
        base["gaps"].append({"question_id": event["question_id"], "event_id": event.get("evaluation_event_id", event["id"]),
                            "score": knowledge_score(event["evaluation"]["scores"]),
                            "evidence": event["evaluation"]["missing_points"][:1] or [event["evaluation"].get("feedback", "回顾上次回答")]})
    improvements = []
    for attempts in by_question.values():
        attempts = [event for event in attempts if independent_attempt(event)]
        if len(attempts) < 2:
            continue
        previous, latest = attempts[-2:]
        old, new = knowledge_score(previous["evaluation"]["scores"]), knowledge_score(latest["evaluation"]["scores"])
        if new > old and not latest.get("hints_used") and latest.get("assistance") == "independent":
            improvements.append({"question_id": latest["question_id"], "from": old, "to": new,
                                 "occurred_at": latest["occurred_at"], "evidence": [previous["id"], latest["id"]]})
    if improvements:
        base["improvement"] = max(improvements, key=lambda e: e["occurred_at"])
    return base
