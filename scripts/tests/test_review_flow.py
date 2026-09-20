from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from common import PACK_ROOT  # noqa: E402
from complete_cycle import build_report, render_markdown  # noqa: E402
from rebuild_state import build_cycle_progress  # noqa: E402
from select_next import select_result  # noqa: E402


CYCLE_ID = "cycle.2026.test.20260805"


def question(question_id: str) -> dict:
    return {
        "id": question_id,
        "revision": 1,
        "status": "active",
        "visibility": "public",
        "topic": "spark",
        "kind": "concept",
        "prompt": f"Prompt for {question_id}",
        "hints": [],
        "_path": PACK_ROOT / "library" / "questions" / "spark" / f"{question_id}.json",
    }


def preparation_cycle(question_ids: list[str]) -> dict:
    return {
        "id": CYCLE_ID,
        "name": "Test Preparation Cycle",
        "kind": "baseline",
        "learner_id": "me",
        "status": "active",
        "created_at": "2026-08-05T09:00:00+08:00",
        "started_at": "2026-08-05T09:00:00+08:00",
        "completed_at": None,
        "target_roles": ["spark-engineer"],
        "topics": ["spark"],
        "review_policy": "coverage_then_spaced",
        "question_ids": question_ids,
    }


def attempt(question_id: str, score: int = 3) -> dict:
    return {
        "assistance": "independent",
        "id": f"attempt.20260805.{question_id}",
        "occurred_at": "2026-08-05T10:00:00+08:00",
        "learner_id": "me",
        "cycle_id": CYCLE_ID,
        "question_id": question_id,
        "question_revision": 1,
        "evaluation": {
            "scores": {
                "recall": score,
                "correctness": score,
                "depth": score,
                "communication": score,
            },
            "missing_points": ["missing detail"] if score < 4 else [],
        },
    }


class ReviewFlowTests(unittest.TestCase):
    def test_spaced_prioritizes_due_even_with_unseen_questions(self) -> None:
        current = preparation_cycle(["q.old", "q.new"])
        current["review_policy"] = "spaced"
        progress = build_cycle_progress(current, [attempt("q.old", 0)],
                                        "2026-08-06T10:00:00+08:00", date(2026, 8, 6))
        result = select_result(current, progress, {qid: question(qid) for qid in current["question_ids"]})
        self.assertEqual("q.old", result["question_id"])

    def test_spaced_does_not_introduce_unseen_questions(self) -> None:
        current = preparation_cycle(["q.new"])
        current["review_policy"] = "spaced"
        progress = build_cycle_progress(current, [], "2026-08-06T10:00:00+08:00", date(2026, 8, 6))
        result = select_result(current, progress, {"q.new": question("q.new")})
        self.assertEqual("no_question_due", result["status"])

    def test_answered_question_is_not_selected_again_before_due(self) -> None:
        question_ids = ["q.spark.first", "q.spark.second"]
        current_cycle = preparation_cycle(question_ids)
        events = [attempt("q.spark.first", 3)]
        progress = build_cycle_progress(
            current_cycle,
            events,
            "2026-08-05T10:01:00+08:00",
            date(2026, 8, 5),
        )
        questions = {question_id: question(question_id) for question_id in question_ids}

        result = select_result(current_cycle, progress, questions, seed=1)

        self.assertEqual("q.spark.second", result["question_id"])
        first = progress["questions"][0]
        self.assertEqual("covered", first["status"])
        self.assertEqual("2026-08-15", first["next_due_at"])
        self.assertEqual(10, first["review_interval_days"])

    def test_cycle_waits_when_every_question_is_covered_but_not_due(self) -> None:
        question_ids = ["q.spark.first", "q.spark.second"]
        current_cycle = preparation_cycle(question_ids)
        events = [attempt(question_id, 4) for question_id in question_ids]
        progress = build_cycle_progress(
            current_cycle,
            events,
            "2026-08-05T10:01:00+08:00",
            date(2026, 8, 5),
        )
        questions = {question_id: question(question_id) for question_id in question_ids}

        result = select_result(current_cycle, progress, questions, seed=1)

        self.assertEqual("no_question_due", result["status"])
        self.assertEqual("2026-09-04", result["next_due_at"])
        self.assertEqual(1.0, progress["statistics"]["coverage_rate"])
        self.assertEqual(2, progress["statistics"]["total_attempts"])

    def test_due_question_reenters_the_selection_pool(self) -> None:
        question_ids = ["q.spark.first", "q.spark.second"]
        current_cycle = preparation_cycle(question_ids)
        events = [attempt(question_id, 0) for question_id in question_ids]
        progress = build_cycle_progress(
            current_cycle,
            events,
            "2026-08-06T10:01:00+08:00",
            date(2026, 8, 6),
        )
        questions = {question_id: question(question_id) for question_id in question_ids}

        result = select_result(current_cycle, progress, questions, seed=1)

        self.assertEqual("due_for_review", result["reason"])
        self.assertIn(result["question_id"], question_ids)
        self.assertEqual(2, progress["totals"]["due"])

    def test_job_targeted_cycle_uses_curated_order_for_unseen_questions(self) -> None:
        question_ids = ["q.spark.first", "q.spark.second"]
        current_cycle = preparation_cycle(question_ids)
        current_cycle["kind"] = "job_targeted"
        current_cycle["job_id"] = "job.example.data-engineer"
        progress = build_cycle_progress(
            current_cycle,
            [],
            "2026-08-05T10:01:00+08:00",
            date(2026, 8, 5),
        )
        questions = {question_id: question(question_id) for question_id in question_ids}

        result = select_result(current_cycle, progress, questions, seed=999)

        self.assertEqual("q.spark.first", result["question_id"])
        self.assertEqual("unseen_curated_order", result["reason"])

    def test_cycle_report_is_a_fixed_structured_summary(self) -> None:
        question_ids = ["q.spark.first"]
        completed_cycle = preparation_cycle(question_ids)
        completed_cycle["status"] = "completed"
        completed_cycle["completed_at"] = "2026-08-05T11:00:00+08:00"
        events = [attempt("q.spark.first", 2)]
        progress = build_cycle_progress(
            completed_cycle,
            events,
            completed_cycle["completed_at"],
            date(2026, 8, 5),
        )
        report = build_report(
            completed_cycle,
            progress,
            {"q.spark.first": question("q.spark.first")},
            events,
            completed_cycle["completed_at"],
        )

        self.assertEqual("completed", report["cycle"]["status"])
        self.assertEqual(1, report["totals"]["covered"])
        self.assertEqual(["q.spark.first"], report["highlights"]["weak_question_ids"])
        self.assertEqual([events[0]["id"]], report["derived_from_events"])
        self.assertIn("本周期概览", render_markdown(report))


if __name__ == "__main__":
    unittest.main()
