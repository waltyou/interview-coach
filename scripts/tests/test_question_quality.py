from __future__ import annotations

import copy
import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import author_question
import common
import initialize
import question_quality as quality
import validate


def question() -> dict:
    return {
        "schema_version": 3, "id": "q.python.example", "revision": 1,
        "status": "active", "visibility": "private", "topic": "python",
        "kind": "coding", "difficulty": 2, "origin": "manual", "target_roles": [],
        "prompt": "实现整数列表去重，保留首次出现顺序，返回新列表。输入允许为空。",
        "rubric": ["首次出现顺序不变，空输入返回空列表，分析空间成本"],
        "hints": [], "follow_ups": ["数据超内存时如何处理？"],
        "source_refs": [], "evaluation_basis": "rubric",
    }


def reviewed(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["quality_review"] = {
        "version": 1, "content_sha256": quality.content_sha256(result),
        "reviewer": "test-fixture", "reviewed_at": "2026-10-02T12:00:00+08:00",
        "checks": {key: "Synthetic test review evidence" for key in quality.REVIEW_CHECKS},
    }
    return result


class QuestionQualityTests(unittest.TestCase):
    def test_missing_review_and_empty_rubric_are_rejected_before_write(self):
        with patch.object(author_question, "write_json") as write:
            with self.assertRaisesRegex(ValueError, "quality_review is required"):
                author_question.save_question(question())
            invalid = reviewed({**question(), "rubric": []})
            with self.assertRaisesRegex(ValueError, "rubric is required"):
                author_question.save_question(invalid)
            write.assert_not_called()

    def test_each_training_content_change_invalidates_review(self):
        base = reviewed(question())
        self.assertEqual([], quality.review_issues(base, required=True))
        for key, value in {
            "prompt": "解释新的问题？", "rubric": ["new"], "hints": ["new"],
            "follow_ups": ["new"], "coach_notes": ["new"], "visibility": "public",
            "status": "archived", "kind": "concept", "id": "q.python.other",
        }.items():
            with self.subTest(key=key):
                changed = {**base, key: value}
                self.assertTrue(any("stale" in x for x in quality.review_issues(changed)))

    def test_boolean_checklist_is_not_written_semantic_evidence(self):
        value = reviewed(question())
        value["quality_review"]["checks"]["answer_contract"] = True
        self.assertTrue(any("answer_contract" in x for x in quality.review_issues(value)))

    def test_legacy_question_remains_readable_without_fabricated_review(self):
        self.assertEqual([], quality.review_issues(question()))
        self.assertTrue(quality.review_issues(question(), required=True))

    def test_fences_authoring_artifacts_and_open_design_question(self):
        self.assertTrue(quality.content_issues({**question(), "prompt": "解释代码：\n```python\nx=1"}))
        self.assertTrue(quality.content_issues({**question(), "prompt": "请默认使用特定故障回答。"}))
        self.assertEqual([], quality.content_issues({**question(), "prompt": "请设计一个设备租赁分析系统，可以先澄清业务需求。"}))
        self.assertEqual([], quality.content_issues({**question(), "prompt": "How would you ensure data integrity?"}))
        self.assertEqual([], quality.content_issues({**question(), "prompt": "你会从哪里开始？"}))

    def test_multiline_sql_and_code_are_preserved_but_answer_is_excluded(self):
        result = initialize.prompt_from_section("SQL", [
            "Q: 请计算每日访问次数。", "", "events(user_id, event_time)",
            "```sql", "-- Example input", "SELECT 1;", "```", "",
            "Answer: 不应进入题干", "参考答案正文",
        ])
        self.assertIn("events(user_id, event_time)", result)
        self.assertIn("SELECT 1;\n```", result)
        self.assertNotIn("参考答案", result)
        self.assertNotIn("Answer:", result)

    def test_import_is_unselectable_and_preserves_edits_when_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "note.md"
            source.write_text("# note", encoding="utf-8")
            roots = ((root / "library/questions", "public"), (root / "workspace/questions", "private"))
            with patch.object(initialize, "PACK_ROOT", root), patch.object(common, "QUESTION_ROOTS", roots):
                output, status = initialize.stage_question_draft(question(), source)
                self.assertEqual("staged", status)
                envelope = common.load_json(output)
                envelope["draft"]["prompt"] = "人工补充的草稿"
                common.write_json(output, envelope)
                self.assertEqual({}, common.load_questions())
                self.assertEqual("preserved", initialize.stage_question_draft(question(), source)[1])
                source.write_text("# changed", encoding="utf-8")
                self.assertEqual("stale", initialize.stage_question_draft(question(), source)[1])
                self.assertEqual("人工补充的草稿", common.load_json(output)["draft"]["prompt"])

    def test_initialize_main_stages_without_admitting_any_question(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "notes.md"
            source.write_text("## 请实现列表去重？", encoding="utf-8")
            catalog = {"sources": [{"path": "notes.md", "status": "ready", "content_sha256": "changed"}]}
            draft = question()
            draft["source_refs"] = [{"root": "repository", "path": "notes.md", "heading": "请实现列表去重？"}]
            with contextlib.ExitStack() as stack:
                for name, value in {
                    "PACK_ROOT": root, "SOURCE_CATALOG_PATH": root / "catalog.json",
                    "parse_args": lambda: argparse.Namespace(mark_extracted=[]),
                    "resolve_source_list": lambda: ([source], []),
                    "build_catalog": lambda *args: catalog,
                    "repository_relative": lambda path: path.relative_to(root),
                    "existing_source_map": lambda: {},
                    "extract_questions": lambda *args: [draft],
                    "write_question_indexes": lambda *args: None,
                }.items():
                    stack.enter_context(patch.object(initialize, name, value))
                stack.enter_context(patch("build_dashboard.build_dashboard", return_value=(root / "dashboard/index.html", {})))
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    initialize.main()
                self.assertIn("questions_created=0 drafts_staged=1", output.getvalue())
                self.assertIn("pending_source=notes.md", output.getvalue())
                self.assertTrue((root / "workspace/imports/questions/q.python.example.json").is_file())
                self.assertFalse((root / "workspace/questions").exists())

    def test_incomplete_fields_and_escaping_sources_cannot_be_saved(self):
        value = reviewed(question())
        value.pop("hints")
        with patch.object(author_question, "write_json") as write:
            with self.assertRaisesRegex(ValueError, "missing Question fields"):
                author_question.save_question(value)
            value = reviewed(question())
            value["source_refs"] = [{"root": "repository", "path": "../outside.md", "heading": "topic"}]
            with self.assertRaisesRegex(ValueError, "inside its root"):
                author_question.save_question(value)
            write.assert_not_called()

    def test_create_update_stale_draft_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roots = ((root / "public", "public"), (root / "private", "private"))
            with patch.object(common, "QUESTION_ROOTS", roots), patch.object(author_question, "question_root_for_visibility", lambda v: dict((b,a) for a,b in roots)[v]):
                first = reviewed(question())
                first["future_field"] = {"preserve": True}
                path = author_question.save_question(first, check_only=True)
                self.assertFalse(path.exists())
                author_question.save_question(first)
                saved = common.load_json(path)
                self.assertEqual(1, saved["revision"])
                draft = copy.deepcopy(saved)
                draft.pop("future_field")
                draft["prompt"] += "请分析复杂度。"
                draft = reviewed(draft)
                author_question.save_question(draft)
                updated = common.load_json(path)
                self.assertEqual(2, updated["revision"])
                self.assertEqual(saved["created_at"], updated["created_at"])
                self.assertEqual({"preserve": True}, updated["future_field"])
                with self.assertRaisesRegex(ValueError, "stale draft"):
                    author_question.save_question(draft)
                changed_visibility = reviewed({**updated, "visibility": "public"})
                with self.assertRaisesRegex(ValueError, "visibility migration"):
                    author_question.save_question(changed_visibility)

    def test_validator_catches_review_staleness_in_bank(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "q.python.example.json"
            value = reviewed(question())
            value["prompt"] += "现在按降序返回。"
            common.write_json(path, value)
            validation = validate.Validation()
            with patch.object(validate, "QUESTION_ROOTS", ((root, "private"),)):
                validate.load_and_validate_questions({"source_roots": {}}, validation)
            self.assertTrue(any("stale" in x for x in validation.errors))


if __name__ == "__main__":
    unittest.main()
