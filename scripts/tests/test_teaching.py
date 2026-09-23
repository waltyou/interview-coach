from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from daily_plan import daily_plan
from practice import answer_context, checkpoint, load_sessions, resume_result, save_session, session_issues, start_session
from rebuild_state import build_mastery
from teach import active_teaching, start_teaching, update_teaching
from test_review_flow import attempt, preparation_cycle, question


class TeachingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cycle = preparation_cycle(["q.iterator"])
        self.questions = {"q.iterator": question("q.iterator")}
        self.session = start_session(self.cycle, minutes=15, root=self.root)
        self.session = checkpoint(self.session, selection={"question_id": "q.iterator", "question_revision": 1,
                                                          "prompt": "Explain iterator exhaustion"})

    def start(self, session=None):
        return start_teaching(session or self.session, goal="Handle iterator exhaustion", gap="State ownership",
                              evidence=["User: I cannot explain repeated iteration"])

    def plan(self, session, phase="teach"):
        return update_teaching(session, "plan", {"path": ["Trace iterator state"], "current_step": 0,
                                                 "phase": phase, "next_action": "Trace a new example"})

    def ask(self, session, independent=False):
        return update_teaching(session, "ask", {"prompt": "What does the next call return?",
                                                "explanation": "" if independent else "Trace state after each call.",
                                                "assistance": "independent" if independent else "reference_seen"})

    def answer(self, session, outcome="passed"):
        return update_teaching(session, "answer", {"answer": "It continues from the saved position.",
                                                   "feedback": "State ownership is explicit.", "outcome": outcome,
                                                   "next_action": "Try a new consumption pattern"})

    def close(self, session, command="finish"):
        return update_teaching(session, command, {"summary": "Immediate check complete; delayed check pending.",
                                                  "next_action": "Explain the original question again"})

    def test_resume_retains_pending_explanation_question_and_original_answer(self):
        lesson = self.answer(self.ask(self.plan(self.start())))
        lesson = self.ask(self.plan(lesson, "transfer"), independent=True)
        save_session(lesson, cycles={self.cycle["id"]: self.cycle}, questions=self.questions, root=self.root)
        resumed = resume_result(load_sessions(self.root)[0], self.cycle, self.questions)
        self.assertEqual("resume_teaching", resumed["status"])
        self.assertEqual(lesson["teaching_sessions"][-1], resumed["teaching"])
        self.assertEqual("reference_seen", load_sessions(self.root)[0]["assistance"])
        self.assertEqual(self.session["current_question"], resumed["current_question"])
        changed = deepcopy(self.questions)
        changed["q.iterator"]["revision"] = 2
        self.assertTrue(resume_result(lesson, self.cycle, changed)["question_changed"])

    def test_finish_returns_to_parent_without_extending_mastery(self):
        lesson = self.answer(self.ask(self.plan(self.start())))
        lesson = self.answer(self.ask(self.plan(lesson, "transfer"), independent=True))
        finished = self.close(lesson)
        self.assertEqual("awaiting_retry", finished["stage"])
        self.assertEqual("completed", finished["teaching_sessions"][-1]["status"])
        retry = attempt("q.iterator", 4)
        retry.update(answer_context(finished), id="attempt.retry", occurred_at="2026-08-06T10:00:00+08:00")
        original = attempt("q.iterator", 0)
        state = build_mastery("me", [original, retry], "2026-08-06T11:00:00+08:00")["questions"][0]
        self.assertEqual(0, state["knowledge_score"])
        self.assertEqual("2026-08-06", state["next_due_at"])
        self.assertEqual(original["id"], state["evidence_event_id"])
        self.assertEqual(2, state["total_attempts"])
        retry_only = build_mastery("me", [retry], "2026-08-06T11:00:00+08:00")["questions"][0]
        self.assertEqual("awaiting_independent", retry_only["evidence_status"])
        next_day = attempt("q.iterator", 4)
        next_day.update(id="attempt.delayed", occurred_at="2026-08-07T10:00:00+08:00")
        state = build_mastery("me", [original, retry, next_day], "2026-08-07T11:00:00+08:00")["questions"][0]
        self.assertEqual("2026-09-06", state["next_due_at"])
        self.assertEqual(next_day["id"], state["evidence_event_id"])

    def test_pending_teaching_cannot_be_bypassed_or_written_as_attempt(self):
        lesson = self.ask(self.plan(self.start()))
        for action in (lambda: checkpoint(lesson, stage="ready"), lambda: checkpoint(lesson, stage="completed"),
                       lambda: answer_context(lesson), lambda: self.ask(lesson), lambda: self.plan(lesson),
                       lambda: self.close(lesson), lambda: self.start(lesson)):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(30, checkpoint(lesson, minutes=30)["time_budget_minutes"])

    def test_completion_requires_latest_unassisted_transfer_success(self):
        for phase, independent, outcome in (("teach", False, "passed"), ("transfer", False, "passed"),
                                             ("transfer", True, "gap")):
            lesson = self.answer(self.ask(self.plan(self.start(), phase), independent), outcome)
            with self.assertRaises(ValueError):
                self.close(lesson)

    def test_replanning_preserves_checked_step_and_answers(self):
        lesson = self.answer(self.ask(self.plan(self.start())))
        checks = deepcopy(active_teaching(lesson)["checks"])
        revised = update_teaching(lesson, "plan", {"path": ["New prerequisite", "Trace iterator state"], "current_step": 0})
        self.assertEqual(checks, active_teaching(revised)["checks"])
        with self.assertRaises(ValueError):
            update_teaching(revised, "plan", {"checks": []})
        with self.assertRaises(ValueError):
            update_teaching(revised, "plan", {"current_step": 9})
        self.assertEqual(0, active_teaching(revised)["current_step"])

    def test_topic_teaching_resumes_without_question_and_is_next_daily_task(self):
        ready = checkpoint(self.session, stage="ready")
        lesson = self.start(ready)
        result = resume_result(lesson, self.cycle, self.questions)
        self.assertIsNone(result["current_question"])
        plan = daily_plan({self.cycle["id"]: self.cycle}, self.questions, [], [lesson], today=date(2026, 8, 6))
        self.assertEqual(1, len(plan["tasks"]))
        self.assertEqual("teaching", plan["tasks"][0]["stage"])
        self.assertIn(active_teaching(lesson)["id"], plan["command"])
        self.assertEqual("ready", self.close(lesson, "stop")["stage"])

    def test_stop_keeps_cancelled_prompt_and_new_lesson_keeps_history(self):
        lesson = self.ask(self.plan(self.start()))
        stopped = self.close(lesson, "stop")
        self.assertEqual(lesson["teaching_sessions"][0]["pending_check"], stopped["teaching_sessions"][0]["cancelled_checks"][0])
        new = self.start(stopped)
        self.assertEqual(stopped["teaching_sessions"][0], new["teaching_sessions"][0])
        self.assertEqual(2, len(new["teaching_sessions"]))

    def test_invalid_answer_is_not_persisted(self):
        lesson = self.ask(self.plan(self.start()))
        save_session(lesson, cycles={self.cycle["id"]: self.cycle}, questions=self.questions, root=self.root)
        before = (self.root / f"{lesson['id']}.json").read_bytes()
        with self.assertRaises(ValueError):
            update_teaching(lesson, "answer", {"answer": "", "feedback": "ok", "outcome": "passed", "next_action": "Next"})
        self.assertEqual(before, (self.root / f"{lesson['id']}.json").read_bytes())
        for data in ({"phase": []}, {"path": "invalid"}, {"current_step": True}):
            with self.assertRaises(ValueError):
                update_teaching(self.start(), "plan", data)

    def test_mock_completed_and_forged_assistance_are_rejected(self):
        for field, value in (("mode", "mock"), ("stage", "completed")):
            session = {**self.session, field: value}
            with self.assertRaises(ValueError):
                self.start(session)
        lesson = self.ask(self.plan(self.start()))
        lesson["assistance"] = "independent"
        lesson["reference_seen_questions"] = []
        self.assertTrue(session_issues(lesson, {self.cycle["id"]: self.cycle}, self.questions))
        with self.assertRaises(ValueError):
            update_teaching(self.plan(self.start()), "ask", {"prompt": "Try", "explanation": "Here is how", "assistance": "independent"})

    def test_probe_only_preserves_assistance_and_legacy_sessions_still_work(self):
        self.assertEqual([], session_issues(self.session, {self.cycle["id"]: self.cycle}, self.questions))
        lesson = self.ask(self.start(), independent=True)
        stopped = self.close(lesson, "stop")
        self.assertEqual("independent", answer_context(stopped)["assistance"])
        lesson["future_field"] = {"keep": True}
        self.assertEqual({"keep": True}, self.answer(lesson)["future_field"])


if __name__ == "__main__":
    unittest.main()
