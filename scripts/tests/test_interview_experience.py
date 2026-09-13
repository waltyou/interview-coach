from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from validate import Validation, validate_interview_experiences  # noqa: E402


class InterviewExperienceTests(unittest.TestCase):
    def validate_text(
        self,
        text: str,
        *,
        jobs: dict[str, dict] | None = None,
    ) -> Validation:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "experience.md").write_text(text, encoding="utf-8")
            validation = Validation()
            validate_interview_experiences(jobs or {}, validation, root=root)
        return validation

    def test_known_job_and_stage_are_valid(self) -> None:
        validation = self.validate_text(
            """# InterviewExperience

- Job ID：`job.example.data-engineer`
- Job Brief：[brief](brief.md)
- InterviewStage：第一轮面试
""",
            jobs={"job.example.data-engineer": {"id": "job.example.data-engineer"}},
        )

        self.assertEqual([], validation.errors)
        self.assertEqual([], validation.warnings)

    def test_unresolved_job_is_persisted_as_a_warning(self) -> None:
        validation = self.validate_text(
            """# InterviewExperience

- Job ID：`unresolved`
- InterviewStage：第一轮面试
"""
        )

        self.assertEqual([], validation.errors)
        self.assertEqual(1, len(validation.warnings))

    def test_missing_job_field_is_an_error(self) -> None:
        validation = self.validate_text(
            """# InterviewExperience

- InterviewStage：第一轮面试
"""
        )

        self.assertTrue(
            any("has no Job ID field" in error for error in validation.errors)
        )


if __name__ == "__main__":
    unittest.main()
