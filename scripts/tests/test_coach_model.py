from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import coach_model  # noqa: E402


def observation(identifier: str, signal: str, reference: str, *, supersedes: list[str] | None = None) -> dict:
    return {
        "schema_version": 1, "id": identifier, "occurred_at": "2026-09-05T09:00:00+08:00",
        "learner_id": "me", "dimension": "technical", "subject": "Spark shuffle",
        "signal": signal, "claim": f"Signal is {signal}", "confidence": "medium",
        "evidence_refs": [{"kind": "attempt_event", "reference": reference}],
        "supersedes": supersedes or [], "observer": {"agent": "test", "model": None},
    }


class CoachModelTests(unittest.TestCase):
    def test_support_requires_two_distinct_evidence_references(self) -> None:
        first = observation("observation.1", "gap", "event.1")
        emerging = coach_model.build_coach_model([first], generated_at="2026-09-05T10:00:00+08:00")
        supported = coach_model.build_coach_model(
            [first, observation("observation.2", "gap", "event.2")],
            generated_at="2026-09-05T10:00:00+08:00",
        )

        self.assertEqual("emerging", emerging["subjects"][0]["evidence_level"])
        self.assertEqual([], emerging["gaps"])
        self.assertEqual("supported", supported["subjects"][0]["evidence_level"])
        self.assertEqual(["technical:Spark shuffle"], supported["gaps"])

    def test_conflicting_signals_are_mixed(self) -> None:
        model = coach_model.build_coach_model(
            [observation("observation.1", "gap", "event.1"), observation("observation.2", "strength", "event.2")]
        )
        self.assertEqual("mixed", model["subjects"][0]["classification"])
        self.assertEqual([], model["strengths"])
        self.assertEqual([], model["gaps"])

    def test_superseded_observation_is_excluded(self) -> None:
        old = observation("observation.1", "gap", "event.1")
        replacement = observation("observation.2", "strength", "event.2", supersedes=["observation.1"])
        model = coach_model.build_coach_model([old, replacement])
        self.assertEqual(["observation.2"], model["derived_from_observations"])
        self.assertEqual("strength", model["subjects"][0]["classification"])

    def test_status_detects_a_stale_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation_root = root / "workspace/profile/observations"
            model_path = root / "workspace/state/coach-model.json"
            observation_path = observation_root / "2026/09/observation.1.json"
            observation_path.parent.mkdir(parents=True)
            observation_path.write_text(json.dumps(observation("observation.1", "gap", "event.1")), encoding="utf-8")
            model_path.parent.mkdir(parents=True)
            model_path.write_text(json.dumps(coach_model.build_coach_model([])), encoding="utf-8")

            status = coach_model.status_payload(
                observation_root=observation_root,
                model_path=model_path,
                profile_path=root / "workspace/profile/candidate.json",
            )

        self.assertEqual("stale", status["status"])
        self.assertEqual("rebuild_model", status["recommended_action"])


if __name__ == "__main__":
    unittest.main()
