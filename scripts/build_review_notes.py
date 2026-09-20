from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from common import PACK_ROOT, SCORE_FIELDS, load_cycles, load_events, load_questions, now_iso


OUTPUT_PATH = PACK_ROOT / "workspace" / "reports" / "answer-review.md"


def build_review_groups(
    events: list[dict[str, Any]],
    questions: dict[str, dict[str, Any]],
    cycles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[event["question_id"]].append(event)

    groups: list[dict[str, Any]] = []
    for question_id, attempts in grouped.items():
        attempts.sort(key=lambda item: (item.get("occurred_at", ""), item.get("id", "")))
        question = questions.get(question_id, {})
        public_attempts = []
        for sequence, event in enumerate(attempts, start=1):
            evaluation = event.get("evaluation", {})
            cycle = cycles.get(event.get("cycle_id"), {})
            public_attempts.append(
                {
                    "sequence": sequence,
                    "id": event["id"],
                    "evaluation_event_id": event.get("evaluation_event_id", event["id"]),
                    "evaluation_history": event.get("evaluation_history", []),
                    "event_path": (
                        event["_path"].relative_to(PACK_ROOT).as_posix()
                        if event.get("_path")
                        else None
                    ),
                    "occurred_at": event["occurred_at"],
                    "cycle_id": event["cycle_id"],
                    "cycle_name": cycle.get("name", event["cycle_id"]),
                    "practice_session_id": event.get("practice_session_id"),
                    "question_revision": event.get("question_revision"),
                    "answer_text": event.get("answer", {}).get("text", ""),
                    "answer_language": event.get("answer", {}).get("language"),
                    "hints_used": event.get("hints_used", []),
                    "scores": evaluation.get("scores", {}),
                    "missing_points": evaluation.get("missing_points", []),
                    "feedback": evaluation.get("feedback", ""),
                    "improved_answer": evaluation.get("improved_answer", ""),
                }
            )
        groups.append(
            {
                "question_id": question_id,
                "current_revision": question.get("revision"),
                "topic": question.get("topic", "unknown"),
                "prompt": question.get("prompt", question_id),
                "attempt_count": len(public_attempts),
                "latest_at": public_attempts[-1]["occurred_at"],
                "attempts": public_attempts,
            }
        )

    return sorted(
        groups,
        key=lambda item: (item["latest_at"], item["question_id"]),
        reverse=True,
    )


def fenced_text(value: str, *, empty_message: str = "尚未提供") -> str:
    content = value.strip() or empty_message
    longest_run = 0
    current_run = 0
    for character in content:
        if character == "`":
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}text\n{content}\n{fence}"


def render_review_markdown(
    groups: list[dict[str, Any]],
    *,
    generated_at: str,
) -> str:
    attempt_count = sum(group["attempt_count"] for group in groups)
    lines = [
        "# Interview Coach 回答复习册",
        "",
        f"> 生成时间：{generated_at}<br>",
        f"> 共 {len(groups)} 道题、{attempt_count} 次回答。内容由只追加的 AttemptEvent 自动生成；请勿在此文件中直接维护历史。",
        "",
        "这份复习册按题目归组，最近一次回答优先，并保留此前每次尝试。原回答用来恢复真实表达，建议表达用来练习结构，注意点用来决定下一轮重点。",
        "",
    ]

    for question_number, group in enumerate(groups, start=1):
        lines.extend(
            [
                f"## {question_number}. {group['prompt']}",
                "",
                f"- Question ID: `{group['question_id']}`",
                f"- Topic: `{group['topic']}`",
                f"- Attempts: {group['attempt_count']}",
                "",
            ]
        )
        for attempt in reversed(group["attempts"]):
            scores = attempt["scores"]
            score_text = " · ".join(
                f"{field} {scores.get(field, '—')}" for field in SCORE_FIELDS
            )
            lines.extend(
                [
                    f"### 第 {attempt['sequence']} 次回答 · {attempt['occurred_at']}",
                    "",
                    f"{score_text}  ",
                    f"PreparationCycle: {attempt['cycle_name']} (`{attempt['cycle_id']}`)  ",
                    f"AttemptEvent: `{attempt['id']}`",
                    "",
                    "#### 我的原回答",
                    "",
                    fenced_text(attempt["answer_text"]),
                    "",
                    "#### 建议的完整表达",
                    "",
                    fenced_text(attempt["improved_answer"]),
                    "",
                    "#### 需要注意",
                    "",
                ]
            )
            if attempt["missing_points"]:
                lines.extend(f"- {point}" for point in attempt["missing_points"])
            else:
                lines.append("- 当前评价没有记录额外注意点。")
            if attempt.get("evaluation_history"):
                lines.extend(["", f"当前评价依据：`{attempt['evaluation_event_id']}`。评分更正未增加作答次数。", ""])
                for prior in attempt["evaluation_history"]:
                    old_scores = prior["evaluation"]["scores"]
                    lines.append(f"- 此前评价 `{prior['event_id']}`：" + " · ".join(f"{key} {old_scores[key]}" for key in SCORE_FIELDS))
            lines.extend(
                [
                    "",
                    "#### 教练反馈",
                    "",
                    attempt["feedback"].strip() or "尚未提供。",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def write_review_notes(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def build_review_notes(*, generated_at: str | None = None) -> tuple[Path, list[dict[str, Any]]]:
    groups = build_review_groups(load_events(), load_questions(), load_cycles())
    content = render_review_markdown(groups, generated_at=generated_at or now_iso())
    write_review_notes(OUTPUT_PATH, content)
    return OUTPUT_PATH, groups


def main() -> None:
    output_path, groups = build_review_notes()
    attempt_count = sum(group["attempt_count"] for group in groups)
    print(
        f"review_notes={output_path.relative_to(PACK_ROOT).as_posix()} "
        f"questions={len(groups)} attempts={attempt_count}"
    )


if __name__ == "__main__":
    main()
