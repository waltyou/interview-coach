from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import common  # noqa: E402
import initialize  # noqa: E402


class SourceListTests(unittest.TestCase):
    def test_source_list_resolves_includes_excludes_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            # Match the canonical paths returned by resolve_source_list, including
            # macOS temp symlinks and Windows short directory names.
            root = Path(directory).resolve()
            (root / "tech" / "interview" / "nested").mkdir(parents=True)
            (root / "tech" / "interview" / "one.md").write_text("# one", encoding="utf-8")
            (root / "tech" / "interview" / "nested" / "two.md").write_text(
                "# two", encoding="utf-8"
            )
            (root / "tech" / "interview" / "draft.md").write_text(
                "# draft", encoding="utf-8"
            )
            (root / "weekly_share").mkdir()
            (root / "weekly_share" / "deck.pptx").write_bytes(b"pptx")
            (root / "weekly_share" / "paper.pdf").write_bytes(b"pdf")
            (root / "xmind").mkdir()
            (root / "xmind" / "spark.xmind").write_bytes(b"xmind")
            source_list = root / "source-list.txt"
            source_list.write_text(
                "# selected sources\n"
                "tech/interview/**/*.md\n"
                "weekly_share/**/*\n"
                "xmind/spark.xmind\n"
                "!tech/interview/draft.md\n",
                encoding="utf-8",
            )

            files, warnings = common.resolve_source_list(source_list, repo_root=root)

        self.assertEqual([], warnings)
        self.assertEqual(
            [
                "tech/interview/nested/two.md",
                "tech/interview/one.md",
                "weekly_share/deck.pptx",
                "weekly_share/paper.pdf",
                "xmind/spark.xmind",
            ],
            [path.relative_to(root).as_posix() for path in files],
        )

    def test_source_list_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_list = root / "source-list.txt"
            source_list.write_text("../outside.md\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "parent traversal"):
                common.resolve_source_list(source_list, repo_root=root)

    def test_catalog_bootstraps_old_sources_and_detects_later_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "tech" / "interview" / "spark.md"
            path.parent.mkdir(parents=True)
            path.write_text("# Spark\n", encoding="utf-8")
            initial_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            old_catalog = {
                "root": "interview_notes",
                "sources": [
                    {
                        "id": "source.spark.legacy",
                        "path": "spark.md",
                        "content_sha256": initial_hash,
                    }
                ],
            }

            with patch.object(
                initialize,
                "repository_relative",
                side_effect=lambda value: value.resolve().relative_to(root.resolve()),
            ):
                catalog = initialize.build_catalog([path], "2026-08-08T00:00:00+08:00", old_catalog)
                path.write_text("# Spark\nchanged\n", encoding="utf-8")
                changed = initialize.build_catalog(
                    [path], "2026-08-08T00:01:00+08:00", catalog
                )

        source = catalog["sources"][0]
        self.assertEqual("repository", catalog["root"])
        self.assertEqual(2, catalog["schema_version"])
        self.assertEqual("tech/interview/spark.md", source["path"])
        self.assertEqual("markdown", source["format"])
        self.assertEqual(initial_hash, source["questions_extracted_from_sha256"])
        self.assertEqual(["tech/interview/spark.md"], initialize.pending_source_paths(changed))

    def test_mark_extracted_accepts_only_selected_ready_sources(self) -> None:
        catalog = {
            "sources": [
                {
                    "path": "tech/note.md",
                    "status": "ready",
                    "content_sha256": "a" * 64,
                    "questions_extracted_from_sha256": None,
                }
            ]
        }

        marked = initialize.mark_sources_extracted(catalog, ["tech/note.md"])

        self.assertEqual(["tech/note.md"], marked)
        self.assertEqual(
            "a" * 64,
            catalog["sources"][0]["questions_extracted_from_sha256"],
        )
        with self.assertRaisesRegex(ValueError, "unselected"):
            initialize.mark_sources_extracted(catalog, ["tech/other.md"])

    def test_source_list_rejects_unsupported_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_list = root / "source-list.txt"
            source_list.write_text("weekly_share/**/*.docx\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported Source pattern"):
                common.resolve_source_list(source_list, repo_root=root)


if __name__ == "__main__":
    unittest.main()
