from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import discover  # noqa: E402


class CandidateDiscoveryTests(unittest.TestCase):
    def test_conversation_can_create_and_complete_confirmed_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "workspace" / "profile" / "candidate.json"
            self.assertEqual("missing", discover.status_payload(path, root)["status"])
            discover.start_profile(path, timestamp="2026-09-05T09:00:00+08:00")
            updated = discover.update_profile(
                path=path, timestamp="2026-09-05T09:01:00+08:00",
                confirmed_by_user=True, method="conversation",
                background_summary="Senior data engineer working on batch and streaming systems.",
                target_roles=["Senior Data Engineer"], technologies=["Spark", "SQL"],
            )
            completed = discover.complete_discovery(
                path, confirmed_by_user=True, timestamp="2026-09-05T09:02:00+08:00"
            )

        self.assertEqual(2, updated["revision"])
        self.assertEqual("complete", completed["discovery"]["status"])
        self.assertEqual([], discover.discovery_requirements(completed))

    def test_profile_facts_require_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspace" / "profile" / "candidate.json"
            discover.start_profile(path)
            with self.assertRaisesRegex(discover.DiscoveryError, "confirmation"):
                discover.update_profile(path=path, target_roles=["Data Engineer"])

    def test_explicit_material_is_registered_and_cannot_escape_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "workspace" / "profile" / "candidate.json"
            resume = root / "workspace" / "resume" / "resume.md"
            resume.parent.mkdir(parents=True)
            resume.write_text("# Resume\n", encoding="utf-8")
            discover.start_profile(path)
            profile = discover.add_material(
                kind="resume", material_path="workspace/resume/resume.md",
                path=path, pack_root=root, repository_root=root,
                timestamp="2026-09-05T09:00:00+08:00",
            )
            with self.assertRaisesRegex(discover.DiscoveryError, "escapes"):
                discover.add_material(
                    kind="other", material_path="../secret.md", path=path,
                    pack_root=root, repository_root=root,
                )

        self.assertEqual(["resume"], profile["discovery"]["methods_used"])
        self.assertEqual("context_pack", profile["materials"][0]["root"])
        self.assertEqual("workspace/resume/resume.md", profile["materials"][0]["path"])


if __name__ == "__main__":
    unittest.main()
