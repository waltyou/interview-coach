from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from start_cycle import snapshot_question_ids  # noqa: E402


def question(question_id: str, topic: str, visibility: str = "private") -> dict:
    return {
        "id": question_id,
        "status": "active",
        "visibility": visibility,
        "topic": topic,
    }


class JobTargetingTests(unittest.TestCase):
    def test_job_plan_order_defines_the_snapshot_order(self) -> None:
        questions = {
            "q.spark.deep": question("q.spark.deep", "spark", "public"),
            "q.behavioral.fit": question("q.behavioral.fit", "behavioral"),
            "q.sql.live": question("q.sql.live", "sql"),
            "q.unrelated": question("q.unrelated", "java", "public"),
        }
        job = {
            "question_plan": [
                {"question_id": "q.behavioral.fit"},
                {"question_id": "q.sql.live"},
                {"question_id": "q.spark.deep"},
            ]
        }

        result = snapshot_question_ids(
            questions,
            topics=["*"],
            visibility="all",
            job=job,
        )

        self.assertEqual(
            ["q.behavioral.fit", "q.sql.live", "q.spark.deep"],
            result,
        )

    def test_job_snapshot_can_be_narrowed_without_importing_unrelated_questions(self) -> None:
        questions = {
            "q.spark.deep": question("q.spark.deep", "spark", "public"),
            "q.sql.live": question("q.sql.live", "sql"),
            "q.sql.other": question("q.sql.other", "sql", "public"),
        }
        job = {
            "question_plan": [
                {"question_id": "q.spark.deep"},
                {"question_id": "q.sql.live"},
            ]
        }

        result = snapshot_question_ids(
            questions,
            topics=["sql"],
            visibility="all",
            job=job,
        )

        self.assertEqual(["q.sql.live"], result)


if __name__ == "__main__":
    unittest.main()
