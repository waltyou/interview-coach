from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from build_review_notes import build_review_groups, fenced_text, render_review_markdown  # noqa: E402


def attempt(event_id: str, occurred_at: str, answer: str, improved: str) -> dict:
    return {
        "id": event_id,
        "occurred_at": occurred_at,
        "cycle_id": "cycle.test",
        "practice_session_id": "practice-session.test",
        "question_id": "q.test.review",
        "question_revision": 1,
        "answer": {"text": answer, "language": "en"},
        "hints_used": [],
        "evaluation": {
            "scores": {
                "recall": 3,
                "correctness": 3,
                "depth": 2,
                "communication": 2,
            },
            "missing_points": ["Explain the trade-off."],
            "feedback": "The result is clear, but the reasoning needs more depth.",
            "improved_answer": improved,
        },
    }


class AnswerReviewTests(unittest.TestCase):
    def test_groups_multiple_attempts_chronologically(self) -> None:
        events = [
            attempt("attempt.second", "2026-08-16T11:00:00+08:00", "second raw", "second improved"),
            attempt("attempt.first", "2026-08-16T10:00:00+08:00", "first raw", "first improved"),
        ]
        questions = {
            "q.test.review": {
                "id": "q.test.review",
                "revision": 2,
                "topic": "behavioral",
                "prompt": "Tell me about the project.",
            }
        }
        cycles = {"cycle.test": {"id": "cycle.test", "name": "Test Cycle"}}

        groups = build_review_groups(events, questions, cycles)

        self.assertEqual(1, len(groups))
        self.assertEqual(2, groups[0]["attempt_count"])
        self.assertEqual(["attempt.first", "attempt.second"], [item["id"] for item in groups[0]["attempts"]])
        self.assertEqual([1, 2], [item["sequence"] for item in groups[0]["attempts"]])
        self.assertEqual(2, groups[0]["current_revision"])

    def test_markdown_contains_all_three_review_layers(self) -> None:
        groups = build_review_groups(
            [attempt("attempt.first", "2026-08-16T10:00:00+08:00", "my raw answer", "coach answer")],
            {
                "q.test.review": {
                    "id": "q.test.review",
                    "revision": 1,
                    "topic": "behavioral",
                    "prompt": "Tell me about the project.",
                }
            },
            {"cycle.test": {"id": "cycle.test", "name": "Test Cycle"}},
        )

        markdown = render_review_markdown(groups, generated_at="2026-08-16T12:00:00+08:00")

        self.assertIn("#### 我的原回答", markdown)
        self.assertIn("my raw answer", markdown)
        self.assertIn("#### 建议的完整表达", markdown)
        self.assertIn("coach answer", markdown)
        self.assertIn("#### 需要注意", markdown)
        self.assertIn("Explain the trade-off.", markdown)
        self.assertIn("`attempt.first`", markdown)

    def test_fenced_text_handles_backticks_in_an_answer(self) -> None:
        block = fenced_text("Use ```sql as an example")

        self.assertTrue(block.startswith("````text\n"))
        self.assertTrue(block.endswith("\n````"))


if __name__ == "__main__":
    unittest.main()
