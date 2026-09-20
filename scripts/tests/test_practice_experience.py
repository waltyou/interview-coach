from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import effective_attempts
from daily_plan import daily_plan
from practice import answer_context, checkpoint, load_sessions, resume_result, save_session, session_issues, start_session
from rebuild_state import build_cycle_progress, build_mastery
from reevaluate import correction_event
from select_next import select_result
from start_cycle import balanced_sample
from test_review_flow import attempt, preparation_cycle, question


class PracticeExperienceTests(unittest.TestCase):
    def test_only_assisted_or_legacy_answers_require_independent_check(self):
        for assistance in ("hints", "reference_seen", None):
            with self.subTest(assistance=assistance):
                first = attempt("q.old", 4)
                first.pop("assistance")
                if assistance:
                    first["assistance"] = assistance
                retry = deepcopy(first)
                retry.update(id="attempt.retry", occurred_at="2026-08-08T10:00:00+08:00")
                state = build_mastery("me", [first, retry], "2026-08-08T10:00:00+08:00")["questions"][0]
                self.assertIsNone(state["scores"])
                self.assertEqual("awaiting_independent", state["evidence_status"])
                self.assertEqual("2026-08-06", state["next_due_at"])
                self.assertEqual(4, state["latest_attempt_scores"]["recall"])
                self.assertEqual(4, first["evaluation"]["scores"]["recall"])

    def test_new_independent_answer_after_assistance_can_extend_interval(self):
        first = attempt("q.old", 0)
        assisted = deepcopy(first)
        assisted.update(id="attempt.assisted", assistance="reference_seen", occurred_at="2026-08-06T10:00:00+08:00")
        independent = deepcopy(first)
        independent.update(id="attempt.independent", occurred_at="2026-08-07T10:00:00+08:00")
        independent["evaluation"]["scores"] = {key: 4 for key in independent["evaluation"]["scores"]}
        state = build_mastery("me", [first, assisted, independent], "2026-08-07T10:00:00+08:00")["questions"][0]
        self.assertEqual(4, state["knowledge_score"])
        self.assertEqual("2026-09-06", state["next_due_at"])
        self.assertEqual(independent["id"], state["evidence_event_id"])

    def test_assisted_answer_today_is_not_automatically_repeated(self):
        self.cycle["review_policy"] = "spaced"
        first = attempt("q.old", 0)
        retry = deepcopy(first)
        retry.update(id="attempt.retry", assistance="reference_seen", occurred_at="2026-08-06T10:00:00+08:00")
        progress = build_cycle_progress(self.cycle, [first, retry], "2026-08-06T10:01:00+08:00", date(2026, 8, 6))
        self.assertEqual("due", progress["questions"][0]["status"])
        self.assertEqual("no_question_due", select_result(self.cycle, progress, self.questions)["status"])
        tomorrow = build_cycle_progress(self.cycle, [first, retry], "2026-08-07T10:01:00+08:00", date(2026, 8, 7))
        self.assertEqual("q.old", select_result(self.cycle, tomorrow, self.questions)["question_id"])

    def test_reference_exposure_survives_restart_and_flows_into_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session = start_session(self.cycle, minutes=30, root=root)
            selection = select_result(self.cycle, self.progress, self.questions)
            session = checkpoint(session, selection=selection)
            session = checkpoint(session, reference_seen=True, stage="awaiting_retry", pending_prompt="请重新回答")
            save_session(session, cycles={self.cycle["id"]: self.cycle}, questions=self.questions, root=root)
            loaded = load_sessions(root)[0]
            self.assertEqual("reference_seen", resume_result(loaded, self.cycle, self.questions)["assistance"])
            event = attempt(selection["question_id"], 4)
            event.update(answer_context(loaded))
            state = build_mastery("me", [event], "2026-08-07T10:00:00+08:00")["questions"][0]
            self.assertIsNone(state["knowledge_score"])
            next_question = checkpoint(checkpoint(loaded, stage="ready"), selection=selection)
            self.assertEqual("reference_seen", answer_context(next_question)["assistance"])
            # Old sessions cannot prove whether a complete answer was shown.
            loaded.pop("assistance")
            loaded.pop("reference_seen_questions")
            self.assertNotIn("assistance", answer_context(loaded))

    def test_budget_preference_fallback_and_short_budget(self):
        cycles = {self.cycle["id"]: self.cycle}
        profile = {"preferences": {"session_minutes": 25}}
        self.assertEqual(25, daily_plan(cycles, self.questions, [], [], profile=profile)["minutes"])
        self.assertEqual(15, daily_plan(cycles, self.questions, [], [dict(cycle_id=self.cycle["id"], stage="completed", time_budget_minutes=60)])["minutes"])
        session = dict(cycle_id=self.cycle["id"], stage="ready", time_budget_minutes=2)
        plan = daily_plan(cycles, self.questions, [], [session], profile=profile)
        self.assertEqual(2, plan["minutes"])
        self.assertLessEqual(sum(task["minutes"] for task in plan["tasks"]), 2)

    def test_short_test_reserves_core_capabilities_and_reports_omissions(self):
        from diagnostic import CAPABILITIES, capability, coverage, snapshot
        from complete_cycle import build_report, render_markdown
        questions = {}
        for name, (_, topics) in CAPABILITIES.items():
            qid = f"q.{name}"
            questions[qid] = {**question(qid), "topic": sorted(topics)[0]}
        for i in range(100):
            questions[f"q.sql.{i}"] = {**question(f"q.sql.{i}"), "topic": "sql"}
        for _ in range(25):
            selected = balanced_sample(list(questions), questions, 8)
            self.assertEqual(set(CAPABILITIES), {capability(questions[qid]["topic"]) for qid in selected})
        selected = balanced_sample(list(questions), questions, 3)
        self.assertEqual({"data-modeling", "system-design", "communication"}, {capability(questions[qid]["topic"]) for qid in selected})
        cycle = preparation_cycle(selected)
        cycle["diagnostic"] = snapshot(list(questions), selected, questions)
        events = [attempt(qid, 3) for qid in selected]
        progress = build_cycle_progress(cycle, events, "2026-08-06T10:00:00+08:00", date(2026, 8, 6))
        self.assertEqual(0, progress["totals"]["unseen"])
        self.assertIn("sql", coverage(cycle, progress)["not_included_capabilities"])
        plan = daily_plan({cycle["id"]: cycle}, questions, events, [], today=date(2026, 8, 6))
        self.assertIn("sql", plan["untested_topics"])
        self.assertIn("sql", plan["diagnostic_coverage"]["untested_capabilities"])
        report = build_report(cycle, progress, questions, events, "2026-08-06T10:00:00+08:00")
        self.assertIn("本次未涉及的能力", render_markdown(report))
        self.assertIn("sql", report["diagnostic_coverage"]["not_included_capabilities"])

    def test_missing_capability_is_explicit_even_for_a_narrow_pool(self):
        from diagnostic import coverage, snapshot
        cycle = preparation_cycle(["q.old"])
        cycle["diagnostic"] = snapshot(["q.old"], ["q.old"], self.questions)
        progress = build_cycle_progress(cycle, [attempt("q.old")], "2026-08-06T10:00:00+08:00", date(2026, 8, 6))
        self.assertIn("communication", coverage(cycle, progress)["unavailable_capabilities"])

    def test_reference_retry_preserves_independent_mastery_and_due_date(self):
        first = attempt("q.old", 0)
        first["assistance"] = "independent"
        retry = deepcopy(first)
        retry.update(id="attempt.retry", occurred_at="2026-08-06T10:00:00+08:00", assistance="reference_seen")
        retry["evaluation"]["scores"] = {key: 4 for key in retry["evaluation"]["scores"]}
        progress = build_cycle_progress(self.cycle, [first, retry], "2026-08-07T10:00:00+08:00", date(2026, 8, 7))
        state = progress["questions"][0]
        self.assertEqual(0, state["knowledge_score"])
        self.assertEqual("2026-08-06", state["next_due_at"])
        mastery = build_mastery("me", [first, retry], "2026-08-07T10:00:00+08:00")["questions"][0]
        self.assertEqual(0, mastery["knowledge_score"])
        self.assertEqual(2, mastery["total_attempts"])

    def test_current_session_budget_overrides_default(self):
        session = {"cycle_id": self.cycle["id"], "stage": "ready", "time_budget_minutes": 30}
        plan = daily_plan({self.cycle["id"]: self.cycle}, self.questions, [], [session])
        self.assertEqual(30, plan["minutes"])
        self.assertIn("30 分钟", plan["command"])

    def setUp(self):
        self.cycle = preparation_cycle(["q.old", "q.new", "q.other"])
        self.questions = {qid: question(qid) for qid in self.cycle["question_ids"]}
        self.questions["q.other"]["topic"] = "modeling"
        self.events = [attempt("q.old", 0)]
        self.progress = build_cycle_progress(self.cycle, self.events, "2026-08-06T10:00:00+08:00", date(2026, 8, 6))

    def test_mixed_daily_block_reviews_then_new(self):
        self.cycle["review_policy"] = "mixed"
        for answered, expected in [(0, "due_for_review"), (1, "due_for_review"), (2, "unseen_topic_coverage")]:
            self.progress["statistics"]["attempts_today"] = answered
            self.assertEqual(expected, select_result(self.cycle, self.progress, self.questions)["reason"])

    def test_baseline_balances_topics_and_preserves_coverage_first(self):
        result = select_result(self.cycle, self.progress, self.questions)
        self.assertEqual("q.other", result["question_id"])
        self.assertEqual("unseen_topic_coverage", result["reason"])

    def test_short_sample_covers_rare_topic(self):
        for i in range(30):
            self.questions[f"q.spark.{i}"] = question(f"q.spark.{i}")
        for _ in range(20):
            result = balanced_sample(list(self.questions), self.questions, 2)
            self.assertEqual(2, len(result))
            self.assertIn("q.other", result)

    def test_resume_from_disk_retains_prompt_hint_stage_and_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session = start_session(self.cycle, goal="巩固遗漏", minutes=15, root=root)
            selection = select_result(self.cycle, self.progress, self.questions)
            session = checkpoint(session, selection=selection)
            session = checkpoint(session, hint={"level": 1, "text": "考虑数据粒度"},
                                 stage="awaiting_retry", pending_prompt="请重新解释取舍")
            save_session(session, cycles={self.cycle["id"]: self.cycle}, questions=self.questions, root=root)
            # Reload exactly as another Agent would, without conversation memory.
            loaded = load_sessions(root)[0]
            result = resume_result(loaded, self.cycle, self.questions)
            self.assertEqual(selection["prompt"], result["prompt"])
            self.assertEqual("awaiting_retry", result["stage"])
            self.assertEqual("请重新解释取舍", result["pending_prompt"])
            self.assertEqual([{"level": 1, "text": "考虑数据粒度"}], result["hints_used"])
            self.assertEqual(15, result["time_budget_minutes"])
            self.assertEqual(session["id"], start_session(self.cycle, root=root)["id"])
            self.questions[selection["question_id"]]["revision"] = 2
            self.assertTrue(resume_result(loaded, self.cycle, self.questions)["question_changed"])
            with self.assertRaises(ValueError):
                checkpoint(loaded, selection=selection)
            self.assertIsNone(resume_result(checkpoint(loaded, stage="ready"), self.cycle, self.questions))

    def test_invalid_session_cannot_write_outside_root(self):
        with tempfile.TemporaryDirectory() as folder:
            session = start_session(self.cycle, root=Path(folder))
            session["id"] = "../escape"
            with self.assertRaises(ValueError):
                save_session(session, cycles={self.cycle["id"]: self.cycle}, questions=self.questions, root=Path(folder))

    def test_trial_does_not_write_workspace(self):
        # A clean, standalone package containing only the scripts and public questions.
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = Path(__file__).resolve().parents[1]
            for name in ("practice.py", "common.py", "source_readers.py", "select_next.py", "rebuild_state.py"):
                (root / "scripts").mkdir(exist_ok=True)
                shutil.copyfile(scripts / name, root / "scripts" / name)
            qdir = root / "library" / "questions"
            qdir.mkdir(parents=True)
            q = {k: v for k, v in question("q.example").items() if not k.startswith("_")}
            (qdir / "q.json").write_text(json.dumps(q), encoding="utf-8")
            run = subprocess.run([sys.executable, "-X", "utf8", str(root / "scripts" / "practice.py"), "trial"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, run.returncode, run.stderr)
            self.assertEqual("none", json.loads(run.stdout)["persistence"])
            self.assertFalse((root / "workspace").exists())

    def test_reevaluation_retains_one_attempt_and_original_date(self):
        original = self.events[0]
        evaluation = deepcopy(original["evaluation"])
        evaluation.update(scores={k: 3 for k in evaluation["scores"]}, feedback="原回答包含该要点", evaluator={"agent": "test"})
        correction = correction_event(self.events, original["id"], evaluation, "遗漏识别有误")
        effective = effective_attempts([correction, original])
        self.assertEqual(1, len(effective))
        self.assertEqual(0, original["evaluation"]["scores"]["recall"])
        progress = build_cycle_progress(self.cycle, effective, "2026-08-06T10:00:00+08:00", date(2026, 8, 6))
        self.assertEqual(1, progress["statistics"]["total_attempts"])
        self.assertEqual("2026-08-15", progress["questions"][0]["next_due_at"])
        self.assertEqual(1, build_mastery("me", effective, "2026-08-06T10:00:00+08:00")["questions"][0]["total_attempts"])
        second = correction_event([original, correction], original["id"], evaluation, "补充核对")
        self.assertEqual(correction["id"], second["supersedes"])
        self.assertEqual(2, len(effective_attempts([second, original, correction])[0]["evaluation_history"]))
        correction["question_id"] = "q.other"
        with self.assertRaises(ValueError):
            effective_attempts([original, correction])

    def test_correction_rejects_dangling_reference_and_fork(self):
        evaluation = deepcopy(self.events[0]["evaluation"])
        evaluation.update(feedback="重新评价", evaluator={"agent":"test"})
        first = correction_event(self.events, self.events[0]["id"], evaluation, "核对")
        other = correction_event(self.events, self.events[0]["id"], evaluation, "核对")
        with self.assertRaises(ValueError):
            effective_attempts(self.events + [first, other])
        first["supersedes"] = "attempt.unknown"
        with self.assertRaises(ValueError):
            effective_attempts(self.events + [first])

    def test_daily_plan_is_read_only_and_exposes_untested_separately(self):
        self.cycle["review_policy"] = "mixed"
        before = deepcopy(self.events)
        plan = daily_plan({self.cycle["id"]:self.cycle}, self.questions, self.events, [], today=date(2026, 8, 6))
        self.assertEqual("q.old", plan["tasks"][0]["question_id"])
        self.assertEqual(3, len({t["question_id"] for t in plan["tasks"]}))
        self.assertEqual(["modeling"], plan["untested_topics"])
        self.assertEqual("q.old", plan["gaps"][0]["question_id"])
        self.assertIsNone(plan["improvement"])
        self.assertEqual(before, self.events)

    def test_reference_seen_retry_is_not_presented_as_independent_progress(self):
        retry = deepcopy(self.events[0])
        retry.update(id="attempt.retry", occurred_at="2026-08-06T10:00:00+08:00", assistance="reference_seen", hints_used=[])
        retry["evaluation"]["scores"] = {key: 4 for key in retry["evaluation"]["scores"]}
        for assistance, expected in [("reference_seen", False), ("independent", True)]:
            retry["assistance"] = assistance
            plan = daily_plan({self.cycle["id"]: self.cycle}, self.questions, self.events + [retry], [], today=date(2026, 8, 6))
            self.assertEqual(expected, plan["improvement"] is not None)


if __name__ == "__main__":
    unittest.main()
