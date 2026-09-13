from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import onboard  # noqa: E402
import discover  # noqa: E402


class OnboardingTests(unittest.TestCase):
    def test_status_distinguishes_new_and_existing_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "workspace" / "onboarding.json"

            fresh = onboard.status_payload(state_path, root)
            cycle = root / "workspace" / "cycles" / "cycle.example.json"
            cycle.parent.mkdir(parents=True)
            cycle.write_text("{}\n", encoding="utf-8")
            existing = onboard.status_payload(state_path, root)

        self.assertEqual("new", fresh["status"])
        self.assertEqual("start_onboarding", fresh["recommended_action"])
        self.assertEqual("existing", existing["status"])
        self.assertEqual("offer_optional_onboarding", existing["recommended_action"])

    def test_full_lifecycle_is_persisted_and_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "workspace" / "onboarding.json"
            started = onboard.start_onboarding(
                path, timestamp="2026-09-02T09:00:00+08:00"
            )
            onboard.record_step(
                "privacy",
                path=path,
                privacy_choice="private_remote",
                timestamp="2026-09-02T09:01:00+08:00",
            )
            onboard.record_step(
                "goal",
                path=path,
                entry_path="baseline",
                timestamp="2026-09-02T09:02:00+08:00",
            )
            profile_path = root / "workspace" / "profile" / "candidate.json"
            discover.start_profile(profile_path, timestamp="2026-09-02T09:02:10+08:00")
            discover.update_profile(
                path=profile_path, timestamp="2026-09-02T09:02:20+08:00",
                confirmed_by_user=True, method="conversation",
                background_summary="Senior data engineer.",
                target_roles=["Senior Data Engineer"],
            )
            discover.complete_discovery(
                profile_path, confirmed_by_user=True,
                timestamp="2026-09-02T09:02:30+08:00",
            )
            onboard.record_step(
                "profile",
                path=path,
                candidate_profile_path="workspace/profile/candidate.json",
                timestamp="2026-09-02T09:03:00+08:00",
            )
            onboard.record_step(
                "materials",
                path=path,
                skipped=True,
                timestamp="2026-09-02T09:04:00+08:00",
            )
            onboard.record_step(
                "first_value",
                path=path,
                activation_kind="cycle_started",
                reference="cycle.2026.baseline.20260902",
                timestamp="2026-09-02T09:05:00+08:00",
            )
            completed = onboard.complete_onboarding(
                path, timestamp="2026-09-02T09:06:00+08:00"
            )
            status = onboard.status_payload(path, root)

        self.assertEqual("in_progress", started["status"])
        self.assertEqual("completed", completed["status"])
        self.assertEqual("done", completed["current_step"])
        self.assertEqual("normal_use", status["recommended_action"])
        self.assertEqual(
            "workspace/profile/candidate.json", completed["candidate_profile_path"]
        )
        self.assertEqual("skipped", completed["steps"]["materials"]["status"])
        self.assertEqual([], onboard.state_issues(completed))

    def test_required_steps_cannot_be_skipped_or_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspace" / "onboarding.json"
            onboard.start_onboarding(path, timestamp="2026-09-02T09:00:00+08:00")

            with self.assertRaisesRegex(onboard.OnboardingError, "cannot be skipped"):
                onboard.record_step("privacy", path=path, skipped=True)
            with self.assertRaisesRegex(onboard.OnboardingError, "requires --entry-path"):
                onboard.record_step("goal", path=path)
            with self.assertRaisesRegex(onboard.OnboardingError, "cannot be skipped"):
                onboard.record_step("profile", path=path, skipped=True)
            with self.assertRaisesRegex(onboard.OnboardingError, "requires --candidate-profile"):
                onboard.record_step("profile", path=path)
            with self.assertRaisesRegex(onboard.OnboardingError, "pending steps"):
                onboard.complete_onboarding(path)

    def test_skip_is_terminal_and_does_not_require_a_started_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "workspace" / "onboarding.json"
            state = onboard.skip_onboarding(
                path, timestamp="2026-09-02T09:00:00+08:00"
            )
            status = onboard.status_payload(path, root)

        self.assertEqual("skipped", state["status"])
        self.assertEqual("done", state["current_step"])
        self.assertEqual("normal_use", status["recommended_action"])
        self.assertEqual([], onboard.state_issues(state))

    def test_profile_step_requires_completed_candidate_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "workspace" / "onboarding.json"
            profile_path = root / "workspace" / "profile" / "candidate.json"
            onboard.start_onboarding(path)
            discover.start_profile(profile_path)

            with self.assertRaisesRegex(onboard.OnboardingError, "incomplete"):
                onboard.record_step(
                    "profile", path=path,
                    candidate_profile_path="workspace/profile/candidate.json",
                )

    def test_invalid_step_shape_is_reported_without_crashing(self) -> None:
        state = onboard.new_state("2026-09-02T09:00:00+08:00")
        state["steps"]["privacy"] = "invalid"

        issues = onboard.state_issues(state)

        self.assertIn("step privacy must be an object", issues)


if __name__ == "__main__":
    unittest.main()
