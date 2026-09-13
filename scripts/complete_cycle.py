from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from common import (
    CYCLE_REPORT_ROOT,
    load_cycles,
    load_events,
    load_questions,
    now_iso,
    parse_datetime,
    without_internal_fields,
    write_json,
)
from rebuild_state import build_cycle_progress, latest_event, rebuild


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Complete a PreparationCycle and write its final report"
    )
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument(
        "--require-coverage",
        action="store_true",
        help="Refuse completion while the PreparationCycle still has unseen Questions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report without changing the PreparationCycle or writing files",
    )
    return parser.parse_args()


def report_paths(cycle_id: str) -> tuple[Path, Path]:
    return CYCLE_REPORT_ROOT / f"{cycle_id}.json", CYCLE_REPORT_ROOT / f"{cycle_id}.md"


def build_highlights(question_reports: list[dict[str, Any]]) -> dict[str, Any]:
    missing_points: Counter[str] = Counter()
    for item in question_reports:
        missing_points.update(item["missing_points"])
    return {
        "strong_question_ids": [
            item["question_id"]
            for item in question_reports
            if item["knowledge_score"] is not None and item["knowledge_score"] >= 3
        ],
        "weak_question_ids": [
            item["question_id"]
            for item in question_reports
            if item["knowledge_score"] is not None and item["knowledge_score"] <= 2
        ],
        "recurring_missing_points": [
            {"point": point, "count": count}
            for point, count in sorted(
                missing_points.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    }


def build_report(
    cycle: dict[str, Any],
    progress: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    cycle_events = [event for event in events if event.get("cycle_id") == cycle["id"]]
    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in cycle_events:
        by_question[event["question_id"]].append(event)
    progress_by_id = {item["question_id"]: item for item in progress["questions"]}

    question_reports: list[dict[str, Any]] = []
    for question_id in cycle["question_ids"]:
        question = questions[question_id]
        attempts = by_question.get(question_id, [])
        latest = latest_event(attempts) if attempts else None
        state = progress_by_id[question_id]
        question_reports.append(
            {
                "question_id": question_id,
                "question_revision": latest["question_revision"] if latest else question["revision"],
                "topic": question["topic"],
                "prompt": question["prompt"],
                "status": state["status"],
                "attempt_count": state["attempt_count"],
                "scores": state["scores"],
                "knowledge_score": state["knowledge_score"],
                "review_interval_days": state["review_interval_days"],
                "last_attempt_at": state["last_attempt_at"],
                "next_due_at": state["next_due_at"],
                "last_event_id": state["last_event_id"],
                "missing_points": latest["evaluation"]["missing_points"] if latest else [],
                "event_ids": [event["id"] for event in attempts],
            }
        )

    return {
        "$schema": "../../../protocol/schemas/cycle-report.schema.json",
        "schema_version": 2,
        "cycle_id": cycle["id"],
        "generated_at": generated_at,
        "cycle": {
            "id": cycle["id"],
            "name": cycle["name"],
            "kind": cycle["kind"],
            "learner_id": cycle["learner_id"],
            "status": "completed",
            "created_at": cycle["created_at"],
            "started_at": cycle["started_at"],
            "completed_at": cycle["completed_at"],
            "target_roles": cycle["target_roles"],
            "topics": cycle["topics"],
            "review_policy": cycle["review_policy"],
        },
        "totals": progress["totals"],
        "statistics": progress["statistics"],
        "highlights": build_highlights(question_reports),
        "questions": question_reports,
        "derived_from_events": [event["id"] for event in cycle_events],
    }


def score_text(scores: dict[str, int] | None) -> str:
    if scores is None:
        return "未作答"
    return "/".join(
        str(scores[field])
        for field in ("recall", "correctness", "depth", "communication")
    )


def render_markdown(report: dict[str, Any]) -> str:
    cycle = report["cycle"]
    totals = report["totals"]
    statistics = report["statistics"]
    averages = statistics["score_averages"]
    average_text = "暂无评分"
    if averages:
        average_text = "/".join(
            str(averages[field])
            for field in ("recall", "correctness", "depth", "communication")
        )

    lines = [
        f"# {cycle['name']} 准备周期报告",
        "",
        f"- Cycle ID：`{cycle['id']}`",
        f"- 周期类型：`{cycle['kind']}`",
        f"- 开始时间：{cycle['started_at'] or '未记录'}",
        f"- 结束时间：{cycle['completed_at']}",
        f"- 主题：{', '.join(cycle['topics'])}",
        f"- 策略：`{cycle['review_policy']}`",
        "",
        "## 本周期概览",
        "",
        f"覆盖 {totals['covered']}/{totals['questions']} 道题，覆盖率 {statistics['coverage_rate']:.0%}。"
        f"本周期共完成 {statistics['total_attempts']} 次回答，结束时有 {totals['due']} 道题到期、"
        f"{totals['unseen']} 道题未覆盖。",
        "",
        "评分顺序为 recall / correctness / depth / communication。",
        "",
        f"本周期最近一次评分平均值：{average_text}。",
        "",
        "## 题目记录",
        "",
        "| 题目 | 状态 | 回答次数 | 最近评分 | 知识分 | 下次复习 |",
        "| --- | --- | ---: | --- | ---: | --- |",
    ]
    for item in report["questions"]:
        prompt = " ".join(item["prompt"].split()).replace("|", "\\|")
        lines.append(
            f"| {prompt} | {item['status']} | {item['attempt_count']} | "
            f"{score_text(item['scores'])} | "
            f"{item['knowledge_score'] if item['knowledge_score'] is not None else '-'} | "
            f"{item['next_due_at'] or '-'} |"
        )

    lines.extend(["", "## 主要遗漏", ""])
    recurring = report["highlights"]["recurring_missing_points"]
    if recurring:
        lines.extend(f"- {item['point']}（{item['count']} 次）" for item in recurring)
    else:
        lines.append("本周期没有已记录的遗漏点。")

    lines.extend(["", "## 后续复习", ""])
    if statistics["next_due_at"]:
        lines.append(f"最近的下次复习日期为 {statistics['next_due_at']}。")
    else:
        lines.append("本周期没有已安排的后续复习日期。")
    lines.extend(
        [
            "",
            "原始回答和逐次评价保存在 `workspace/events/`。本报告是 PreparationCycle 结束时的固定快照。",
            "",
        ]
    )
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    cycles = load_cycles()
    cycle = cycles.get(args.cycle_id)
    if cycle is None:
        raise SystemExit(f"Unknown PreparationCycle: {args.cycle_id}")
    if cycle["status"] not in {"active", "completed"}:
        raise SystemExit(
            f"PreparationCycle cannot be completed from status: {cycle['status']}"
        )

    json_path, markdown_path = report_paths(cycle["id"])
    if cycle["status"] == "completed" and json_path.exists() and markdown_path.exists():
        print(f"cycle_id={cycle['id']} status=already_completed report={json_path}")
        return

    completed_at = cycle.get("completed_at") or now_iso()
    completed_cycle = without_internal_fields(cycle)
    completed_cycle["status"] = "completed"
    completed_cycle["completed_at"] = completed_at

    events = load_events()
    questions = load_questions()
    progress = build_cycle_progress(
        completed_cycle,
        events,
        completed_at,
        parse_datetime(completed_at).date(),
    )
    if args.require_coverage and progress["totals"]["unseen"]:
        raise SystemExit(
            f"PreparationCycle still has {progress['totals']['unseen']} unseen Questions; "
            "omit --require-coverage to complete it early"
        )
    report = build_report(completed_cycle, progress, questions, events, completed_at)

    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    write_json(cycle["_path"], completed_cycle)
    rebuild()
    write_json(json_path, report)
    write_text(markdown_path, render_markdown(report))
    from build_dashboard import build_dashboard

    build_dashboard(rebuild_state=False)
    print(
        f"cycle_id={cycle['id']} status=completed "
        f"covered={report['totals']['covered']}/{report['totals']['questions']} "
        f"report={json_path}"
    )


if __name__ == "__main__":
    main()
