from __future__ import annotations

import argparse
import json
from typing import Any

from common import STATE_ROOT, load_cycles, load_events, load_json, load_questions
from rebuild_state import rebuild


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read PreparationCycle and Question history")
    parser.add_argument("--learner", default="me")
    parser.add_argument("--cycle-id")
    parser.add_argument("--question-id")
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def knowledge_score(scores: dict[str, int]) -> int:
    return min(scores["recall"], scores["correctness"], scores["depth"])


def question_history(question_id: str, learner_id: str) -> dict[str, Any]:
    questions = load_questions()
    question = questions.get(question_id)
    if question is None:
        raise SystemExit(f"Unknown Question: {question_id}")
    attempts = [
        event
        for event in load_events()
        if event["learner_id"] == learner_id and event["question_id"] == question_id
    ]
    return {
        "question_id": question_id,
        "prompt": question["prompt"],
        "attempt_count": len(attempts),
        "attempts": [
            {
                "event_id": event["id"],
                "cycle_id": event["cycle_id"],
                "occurred_at": event["occurred_at"],
                "answer": event["answer"],
                "hints_used": event["hints_used"],
                "evaluation": event["evaluation"],
                "evaluation_event_id": event.get("evaluation_event_id", event["id"]),
                "evaluation_history": event.get("evaluation_history", []),
            }
            for event in attempts
        ],
    }


def cycle_history(cycle_id: str, limit: int) -> dict[str, Any]:
    cycles = load_cycles()
    cycle = cycles.get(cycle_id)
    if cycle is None:
        raise SystemExit(f"Unknown PreparationCycle: {cycle_id}")
    progress_path = STATE_ROOT / "cycles" / f"{cycle_id}.json"
    if not progress_path.exists():
        rebuild()
    progress = load_json(progress_path)
    questions = load_questions()
    attempted = [item for item in progress["questions"] if item["scores"]]
    attempted.sort(key=lambda item: (knowledge_score(item["scores"]), item["question_id"]))
    return {
        "cycle": {
            "id": cycle["id"],
            "name": cycle["name"],
            "kind": cycle["kind"],
            "status": cycle["status"],
            "review_policy": cycle["review_policy"],
            "topics": cycle["topics"],
        },
        "totals": progress["totals"],
        "statistics": progress["statistics"],
        "due_questions": [
            {
                "question_id": item["question_id"],
                "prompt": questions[item["question_id"]]["prompt"],
                "scores": item["scores"],
                "next_due_at": item["next_due_at"],
            }
            for item in progress["questions"]
            if item["status"] == "due"
        ][:limit],
        "unseen_question_ids": [
            item["question_id"]
            for item in progress["questions"]
            if item["status"] == "unseen"
        ],
        "awaiting_independent_question_ids": [item["question_id"] for item in progress["questions"]
                                             if item.get("evidence_status") == "awaiting_independent"],
        "weak_questions": [
            {
                "question_id": item["question_id"],
                "prompt": questions[item["question_id"]]["prompt"],
                "scores": item["scores"],
                "knowledge_score": item["knowledge_score"],
                "attempt_count": item["attempt_count"],
                "next_due_at": item["next_due_at"],
            }
            for item in attempted[:limit]
        ],
    }


def mastery_history(learner_id: str, limit: int) -> dict[str, Any]:
    mastery_path = STATE_ROOT / "mastery" / f"{learner_id}.json"
    if not mastery_path.exists():
        rebuild()
    mastery = load_json(mastery_path)
    questions = load_questions()
    items = list(mastery["questions"])
    items.sort(key=lambda item: (knowledge_score(item["scores"]) if item["scores"] else -1, item["last_attempt_at"]))
    return {
        "learner_id": learner_id,
        "total_questions_attempted": len(items),
        "weak_questions": [
            {
                **item,
                "prompt": questions[item["question_id"]]["prompt"],
            }
            for item in items[:limit]
        ],
    }


def main() -> None:
    args = parse_args()
    if args.question_id:
        result = question_history(args.question_id, args.learner)
    elif args.cycle_id:
        result = cycle_history(args.cycle_id, args.limit)
    else:
        result = mastery_history(args.learner, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
