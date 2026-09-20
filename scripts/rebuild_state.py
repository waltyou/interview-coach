from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from common import (
    REVIEW_INTERVAL_DAYS,
    SCORE_FIELDS,
    STATE_ROOT,
    knowledge_score,
    load_events,
    load_cycles,
    now_iso,
    parse_datetime,
    write_json,
)


def next_due_at(event: dict[str, Any]) -> str:
    attempted_date = parse_datetime(event["occurred_at"]).date()
    interval = REVIEW_INTERVAL_DAYS[knowledge_score(event["evaluation"]["scores"])] if independent_attempt(event) else 1
    return (attempted_date + timedelta(days=interval)).isoformat()


def independent_attempt(event: dict[str, Any]) -> bool:
    return event.get("assistance") == "independent" and not event.get("hints_used")


def mastery_evidence(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    independent = [event for event in attempts if independent_attempt(event)]
    return latest_event(independent) if independent else None


def mastery_projection(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    latest = latest_event(attempts)
    evidence = mastery_evidence(attempts)
    # Assisted repetition never moves the evidence date forward. With no
    # independent evidence, schedule one check after the first recorded practice.
    first = min(attempts, key=lambda event: (event["occurred_at"], event["id"]))
    scores = evidence["evaluation"]["scores"] if evidence else None
    score = knowledge_score(scores) if scores is not None else None
    return {
        "scores": scores,
        "knowledge_score": score,
        "review_interval_days": REVIEW_INTERVAL_DAYS[score] if score is not None else 1,
        "next_due_at": next_due_at(evidence or first),
        "last_attempt_at": latest["occurred_at"],
        "last_event_id": latest["id"],
        "latest_attempt_scores": latest["evaluation"]["scores"],
        "evidence_event_id": evidence["id"] if evidence else None,
        "evidence_status": "independent" if evidence else "awaiting_independent",
    }


def latest_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    return max(events, key=lambda event: (event["occurred_at"], event["id"]))


def build_statistics(
    question_states: list[dict[str, Any]],
    cycle_events: list[dict[str, Any]],
    today: date,
) -> dict[str, Any]:
    scored = [item["scores"] for item in question_states if item["scores"] is not None]
    score_averages = None
    if scored:
        score_averages = {
            field: round(sum(scores[field] for scores in scored) / len(scored), 2)
            for field in SCORE_FIELDS
        }

    distribution = {str(score): 0 for score in REVIEW_INTERVAL_DAYS}
    for scores in scored:
        distribution[str(knowledge_score(scores))] += 1

    due_dates = sorted(
        item["next_due_at"]
        for item in question_states
        if item["next_due_at"] is not None
    )
    covered = sum(item["status"] != "unseen" for item in question_states)
    question_count = len(question_states)
    return {
        "coverage_rate": round(covered / question_count, 4) if question_count else 0.0,
        "total_attempts": len(cycle_events),
        "attempts_today": sum(
            parse_datetime(event["occurred_at"]).date() == today for event in cycle_events
        ),
        "score_averages": score_averages,
        "knowledge_score_distribution": distribution,
        "next_due_at": due_dates[0] if due_dates else None,
    }


def build_cycle_progress(
    cycle: dict[str, Any],
    events: list[dict[str, Any]],
    generated_at: str,
    today: date,
) -> dict[str, Any]:
    cycle_events = [event for event in events if event.get("cycle_id") == cycle["id"]]
    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in cycle_events:
        by_question[event["question_id"]].append(event)

    question_states: list[dict[str, Any]] = []
    for question_id in cycle["question_ids"]:
        attempts = by_question.get(question_id, [])
        if not attempts:
            question_states.append(
                {
                    "question_id": question_id,
                    "status": "unseen",
                    "attempt_count": 0,
                    "scores": None,
                    "knowledge_score": None,
                    "review_interval_days": None,
                    "last_attempt_at": None,
                    "next_due_at": None,
                    "last_event_id": None,
                }
            )
            continue

        projection = mastery_projection(attempts)
        due_at = projection["next_due_at"]
        status = "due" if date.fromisoformat(due_at) <= today else "covered"
        question_states.append(
            {
                "question_id": question_id,
                "status": status,
                "attempt_count": len(attempts),
                **projection,
            }
        )

    unseen = sum(item["status"] == "unseen" for item in question_states)
    due = sum(item["status"] == "due" for item in question_states)
    covered = len(question_states) - unseen
    return {
        "$schema": "../../../protocol/schemas/cycle-progress.schema.json",
        "schema_version": 3,
        "cycle_id": cycle["id"],
        "learner_id": cycle["learner_id"],
        "cycle_status": cycle["status"],
        "generated_at": generated_at,
        "review_policy": cycle["review_policy"],
        "totals": {
            "questions": len(question_states),
            "unseen": unseen,
            "covered": covered,
            "due": due,
        },
        "statistics": build_statistics(question_states, cycle_events, today),
        "questions": question_states,
        "derived_from_events": [event["id"] for event in cycle_events],
    }


def build_mastery(
    learner_id: str,
    events: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    learner_events = [event for event in events if event.get("learner_id") == learner_id]
    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in learner_events:
        by_question[event["question_id"]].append(event)

    questions: list[dict[str, Any]] = []
    for question_id, attempts in sorted(by_question.items()):
        questions.append(
            {
                "question_id": question_id,
                "total_attempts": len(attempts),
                "cycles_seen": sorted({event["cycle_id"] for event in attempts}),
                **mastery_projection(attempts),
            }
        )

    return {
        "$schema": "../../../protocol/schemas/mastery-state.schema.json",
        "schema_version": 3,
        "learner_id": learner_id,
        "generated_at": generated_at,
        "questions": questions,
        "derived_from_events": [event["id"] for event in learner_events],
    }


def rebuild() -> tuple[int, int]:
    generated_at = now_iso()
    today = parse_datetime(generated_at).date()
    events = load_events()
    cycles = load_cycles()

    for cycle in cycles.values():
        progress = build_cycle_progress(cycle, events, generated_at, today)
        write_json(STATE_ROOT / "cycles" / f"{cycle['id']}.json", progress)

    learner_ids = {cycle["learner_id"] for cycle in cycles.values()}
    learner_ids.update(event["learner_id"] for event in events)
    for learner_id in sorted(learner_ids):
        mastery = build_mastery(learner_id, events, generated_at)
        write_json(STATE_ROOT / "mastery" / f"{learner_id}.json", mastery)

    return len(cycles), len(events)


def main() -> None:
    cycle_count, event_count = rebuild()
    from build_dashboard import build_dashboard

    dashboard_path, _ = build_dashboard(rebuild_state=False)
    print(
        f"cycles_rebuilt={cycle_count} events_applied={event_count} "
        f"dashboard={dashboard_path.relative_to(STATE_ROOT.parent.parent).as_posix()}"
    )


if __name__ == "__main__":
    main()
