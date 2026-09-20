from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import date, timedelta
from typing import Any, TypeVar

from common import PACK_ROOT, STATE_ROOT, load_cycles, load_json, load_questions
from rebuild_state import rebuild


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select the next Question for a PreparationCycle")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--seed", type=int)
    return parser.parse_args()


def choose(items: list[dict[str, Any]], seed: int | None) -> dict[str, Any]:
    generator = random.Random(seed) if seed is not None else random.SystemRandom()
    return generator.choice(items)


def progress_summary(progress: dict[str, Any]) -> dict[str, Any]:
    return {
        "totals": progress["totals"],
        "statistics": progress["statistics"],
    }


def public_question(
    question: dict[str, Any],
    reason: str,
    cycle_id: str,
    progress: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "selected",
        "cycle_id": cycle_id,
        "question_id": question["id"],
        "question_revision": question["revision"],
        "visibility": question["visibility"],
        "topic": question["topic"],
        "kind": question["kind"],
        "prompt": question["prompt"],
        "hint_count": len(question["hints"]),
        "reason": reason,
        "cycle_progress": progress_summary(progress),
        "question_file": question["_path"].relative_to(PACK_ROOT).as_posix(),
    }


def select_result(
    cycle: dict[str, Any],
    progress: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    seed: int | None = None,
) -> dict[str, Any]:
    progress_by_id = {item["question_id"]: item for item in progress["questions"]}

    eligible: list[dict[str, Any]] = []
    for question_id in cycle["question_ids"]:
        question = questions.get(question_id)
        if question and question["status"] == "active":
            eligible.append(question)

    unseen = [
        question
        for question in eligible
        if progress_by_id.get(question["id"], {}).get("status") == "unseen"
    ]
    policy = cycle["review_policy"]
    today = progress.get("generated_at", "")[:10]
    due = [question for question in eligible
           if progress_by_id.get(question["id"], {}).get("status") == "due"
           and (cycle.get("same_day_repeat", False)
                or (progress_by_id[question["id"]].get("last_attempt_at") or "")[:10] != today)]
    # A daily block starts with two reviews, then introduces one new question.
    introduce_new = (not due or progress["statistics"]["attempts_today"] % 3 == 2)
    if unseen and (policy in {"coverage_once", "coverage_then_spaced"}
                   or policy == "mixed" and introduce_new):
        if cycle.get("kind") in {"job_targeted", "stage_targeted"}:
            selected = unseen[0]
            reason = "unseen_curated_order"
        else:
            covered_topics = Counter(
                question["topic"].split(".")[0] for question in eligible
                if progress_by_id.get(question["id"], {}).get("status") != "unseen"
            )
            topics = sorted({question["topic"].split(".")[0] for question in unseen})
            least = min(covered_topics[topic] for topic in topics)
            topic = choose([topic for topic in topics if covered_topics[topic] == least], seed)
            selected = choose([question for question in unseen
                               if question["topic"].split(".")[0] == topic], seed)
            reason = "unseen_topic_coverage"
        return public_question(selected, reason, cycle["id"], progress)

    if policy == "coverage_once":
        return {
            "status": "cycle_coverage_complete",
            "cycle_id": cycle["id"],
            "cycle_progress": progress_summary(progress),
        }

    if due:
        due.sort(
            key=lambda question: (
                progress_by_id[question["id"]]["next_due_at"],
                progress_by_id[question["id"]].get("knowledge_score")
                if progress_by_id[question["id"]].get("knowledge_score") is not None else -1,
            )
        )
        first = progress_by_id[due[0]["id"]]
        tied = [question for question in due
                if progress_by_id[question["id"]]["next_due_at"] == first["next_due_at"]
                and progress_by_id[question["id"]]["scores"] == first["scores"]]
        selected = choose(tied, seed)
        return public_question(selected, "due_for_review", cycle["id"], progress)

    future_dates = sorted(
        item["next_due_at"]
        for item in progress["questions"]
        if item["next_due_at"] and item["next_due_at"] > today
        and item["question_id"] in {q["id"] for q in eligible}
    )
    if today and any(progress_by_id[q["id"]].get("status") == "due"
                     and (progress_by_id[q["id"]].get("last_attempt_at") or "")[:10] == today
                     for q in eligible):
        future_dates.append((date.fromisoformat(today) + timedelta(days=1)).isoformat())
        future_dates.sort()
    return {
        "status": "no_question_due",
        "cycle_id": cycle["id"],
        "next_due_at": future_dates[0] if future_dates else None,
        "cycle_progress": progress_summary(progress),
    }


def main() -> None:
    args = parse_args()
    cycles = load_cycles()
    cycle = cycles.get(args.cycle_id)
    if cycle is None:
        raise SystemExit(f"Unknown PreparationCycle: {args.cycle_id}")
    if cycle["status"] != "active":
        raise SystemExit(f"PreparationCycle is not active: {cycle['status']}")

    # AttemptEvent is the source of truth. Always rebuild before selection so a
    # stale projection can never cause the previous question to be selected again.
    rebuild()
    progress_path = STATE_ROOT / "cycles" / f"{cycle['id']}.json"
    progress = load_json(progress_path)
    result = select_result(cycle, progress, load_questions(), args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
