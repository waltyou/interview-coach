from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

from common import (
    DASHBOARD_ROOT,
    PACK_ROOT,
    CYCLE_REPORT_ROOT,
    SCORE_FIELDS,
    SOURCE_CATALOG_PATH,
    STATE_ROOT,
    load_events,
    load_jobs,
    load_json,
    load_questions,
    load_cycles,
    now_iso,
)
from rebuild_state import rebuild
from build_review_notes import OUTPUT_PATH as REVIEW_NOTES_PATH, build_review_groups, build_review_notes


TEMPLATE_PATH = DASHBOARD_ROOT / "template.html"
OUTPUT_PATH = DASHBOARD_ROOT / "index.html"
REVIEW_TEMPLATE_PATH = DASHBOARD_ROOT / "review-template.html"
REVIEW_OUTPUT_PATH = DASHBOARD_ROOT / "review.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only Interview Coach dashboard")
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="Use the current state projections without rebuilding them first",
    )
    return parser.parse_args()


def sorted_counts(values: list[str]) -> list[dict[str, Any]]:
    counts = Counter(values)
    return [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def local_href(relative_path: str, *, prefix: str) -> str:
    return f"{prefix}{quote(relative_path, safe='/')}"


def source_file_href(root: str, relative_path: str, manifest: dict[str, Any]) -> str:
    source_root = (PACK_ROOT / manifest["source_roots"][root]).resolve()
    target = (source_root / relative_path).resolve()
    relative = os.path.relpath(target, DASHBOARD_ROOT).replace("\\", "/")
    return quote(relative, safe="/")


def public_sources(
    catalog: dict[str, Any],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "id": source["id"],
                "title": source["title"],
                "path": source["path"],
                "topics": source["topics"],
                "status": source["status"],
                "format": source["format"],
                "unit_label": source["unit_label"],
                "unit_count": source.get("unit_count"),
                "question_extraction_status": (
                    "unavailable"
                    if source["status"] != "ready"
                    else (
                        "synced"
                        if source.get("questions_extracted_from_sha256")
                        == source["content_sha256"]
                        else "pending"
                    )
                ),
                "size_bytes": source["size_bytes"],
                "modified_at": source["modified_at"],
                "file_href": source_file_href(catalog["root"], source["path"], manifest),
            }
            for source in catalog["sources"]
        ),
        key=lambda item: (item["status"] != "ready", item["path"].lower()),
    )


def public_questions(
    questions: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for question in questions.values():
        question_path = question["_path"].relative_to(PACK_ROOT).as_posix()
        source_refs = [
            {
                "path": reference["path"],
                "heading": reference["heading"],
                "unit": reference.get("unit"),
                "unit_label": reference.get("unit_label"),
                "file_href": source_file_href(
                    reference["root"], reference["path"], manifest
                ),
            }
            for reference in question.get("source_refs", [])
        ]
        items.append(
            {
                "id": question["id"],
                "revision": question["revision"],
                "status": question["status"],
                "visibility": question["visibility"],
                "topic": question["topic"],
                "kind": question["kind"],
                "difficulty": question["difficulty"],
                "origin": question["origin"],
                "prompt": question["prompt"],
                "evaluation_basis": question["evaluation_basis"],
                "rubric_count": len(question.get("rubric", [])),
                "hint_count": len(question.get("hints", [])),
                "follow_up_count": len(question.get("follow_ups", [])),
                "source_refs": source_refs,
                "file_href": local_href(question_path, prefix="../"),
            }
        )
    return sorted(items, key=lambda item: (item["topic"], item["id"]))


def public_cycle(
    cycle: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    jobs: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    progress_path = STATE_ROOT / "cycles" / f"{cycle['id']}.json"
    progress = load_json(progress_path)
    progress_by_id = {item["question_id"]: item for item in progress["questions"]}
    question_items = []
    for question_id in cycle["question_ids"]:
        question = questions.get(question_id)
        state = progress_by_id.get(question_id)
        if question is None or state is None:
            continue
        question_items.append(
            {
                "id": question_id,
                "revision": question["revision"],
                "visibility": question["visibility"],
                "topic": question["topic"],
                "prompt": question["prompt"],
                "status": state["status"],
                "attempt_count": state["attempt_count"],
                "scores": state["scores"],
                "knowledge_score": state["knowledge_score"],
                "evidence_status": state.get("evidence_status", "unseen"),
                "review_interval_days": state["review_interval_days"],
                "last_attempt_at": state["last_attempt_at"],
                "next_due_at": state["next_due_at"],
            }
        )
    job = jobs.get(cycle.get("job_id"))
    public_job = None
    if job is not None:
        public_job = {
            "id": job["id"],
            "company": job["company"],
            "role_title": job["role_title"],
            "status": job["status"],
            "target_level": job.get("target_level"),
            "posting_url": job.get("posting_url"),
            "brief_href": source_file_href("repository", job["brief_path"], manifest),
        }
    return {
        "id": cycle["id"],
        "name": cycle["name"],
        "kind": cycle["kind"],
        "status": cycle["status"],
        "created_at": cycle["created_at"],
        "started_at": cycle["started_at"],
        "completed_at": cycle.get("completed_at"),
        "topics": cycle["topics"],
        "target_roles": cycle["target_roles"],
        "review_policy": cycle["review_policy"],
        "job": public_job,
        "totals": progress["totals"],
        "statistics": progress["statistics"],
        "questions": question_items,
    }


def report_summaries() -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(CYCLE_REPORT_ROOT.glob("*.json")) if CYCLE_REPORT_ROOT.exists() else []:
        report = load_json(path)
        reports.append(
            {
                "cycle_id": report["cycle_id"],
                "name": report["cycle"]["name"],
                "completed_at": report["cycle"]["completed_at"],
                "totals": report["totals"],
                "statistics": report["statistics"],
                "markdown_path": f"../workspace/reports/cycles/{path.stem}.md",
            }
        )
    return sorted(reports, key=lambda item: item["completed_at"], reverse=True)


def collect_dashboard_data() -> dict[str, Any]:
    manifest = load_json(PACK_ROOT / "manifest.json")
    catalog = load_json(SOURCE_CATALOG_PATH)
    questions = load_questions()
    jobs = load_jobs()
    cycles = load_cycles()
    events = load_events()

    public_cycles = [
        public_cycle(item, questions, jobs, manifest) for item in cycles.values()
    ]
    public_cycles.sort(
        key=lambda item: (
            item["status"] == "active",
            item["started_at"] or item["created_at"],
        ),
        reverse=True,
    )
    primary_cycle = next(
        (item for item in public_cycles if item["status"] == "active"),
        public_cycles[0] if public_cycles else None,
    )

    source_statuses = sorted_counts([item["status"] for item in catalog["sources"]])
    question_statuses = sorted_counts([item["status"] for item in questions.values()])
    question_visibilities = sorted_counts([item["visibility"] for item in questions.values()])
    topic_counts = sorted_counts([item["topic"] for item in questions.values()])
    source_items = public_sources(catalog, manifest)
    question_items = public_questions(questions, manifest)
    latest_attempts = []
    for event in reversed(events[-8:]):
        question = questions.get(event["question_id"])
        latest_attempts.append(
            {
                "id": event["id"],
                "occurred_at": event["occurred_at"],
                "cycle_id": event["cycle_id"],
                "question_id": event["question_id"],
                "prompt": question["prompt"] if question else event["question_id"],
                "scores": event["evaluation"]["scores"],
                "missing_point_count": len(event["evaluation"]["missing_points"]),
            }
        )

    from daily_plan import daily_plan
    from practice import load_sessions
    from discover import PROFILE_PATH, load_profile
    return {
        "daily_plan": daily_plan(cycles, questions, events, load_sessions(), profile=load_profile() if PROFILE_PATH.is_file() else None),
        "generated_at": now_iso(),
        "protocol_version": manifest["protocol_version"],
        "capabilities": manifest["capabilities"],
        "sources": {
            "total": len(catalog["sources"]),
            "statuses": source_statuses,
            "formats": sorted_counts([item["format"] for item in source_items]),
            "extraction_statuses": sorted_counts(
                [item["question_extraction_status"] for item in source_items]
            ),
            "items": source_items,
        },
        "questions": {
            "total": len(questions),
            "statuses": question_statuses,
            "visibilities": question_visibilities,
            "topics": topic_counts,
            "items": question_items,
        },
        "jobs": [
            {
                "id": job["id"],
                "company": job["company"],
                "role_title": job["role_title"],
                "status": job["status"],
                "target_level": job.get("target_level"),
                "question_count": len(job["question_plan"]),
            }
            for job in sorted(jobs.values(), key=lambda item: item["id"])
        ],
        "cycles": public_cycles,
        "primary_cycle": primary_cycle,
        "attempts": {
            "total": len(events),
            "latest": latest_attempts,
            "review_notes_href": local_href(
                REVIEW_NOTES_PATH.relative_to(PACK_ROOT).as_posix(), prefix="../"
            ),
            "review_page_href": "review.html",
        },
        "reports": report_summaries(),
        "review_intervals": [
            {"score": 0, "days": 1},
            {"score": 1, "days": 2},
            {"score": 2, "days": 4},
            {"score": 3, "days": 10},
            {"score": 4, "days": 30},
        ],
        "score_fields": list(SCORE_FIELDS),
    }


def collect_review_data() -> dict[str, Any]:
    questions = load_questions()
    cycles = load_cycles()
    events = load_events()
    review_groups = build_review_groups(events, questions, cycles)
    for group in review_groups:
        for attempt in group["attempts"]:
            event_path = attempt.pop("event_path", None)
            attempt["event_href"] = (
                local_href(event_path, prefix="../") if event_path else None
            )
    return {
        "generated_at": now_iso(),
        "question_count": len(review_groups),
        "attempt_count": len(events),
        "review_groups": review_groups,
        "review_notes_href": local_href(
            REVIEW_NOTES_PATH.relative_to(PACK_ROOT).as_posix(), prefix="../"
        ),
        "dashboard_href": "index.html#answer-review",
        "score_fields": list(SCORE_FIELDS),
    }


def safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def build_dashboard(*, rebuild_state: bool = True) -> tuple[Path, dict[str, Any]]:
    if rebuild_state:
        rebuild()
    build_review_notes()
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data = collect_dashboard_data()
    marker = "__INTERVIEW_COACH_DASHBOARD_DATA__"
    if template.count(marker) != 1:
        raise RuntimeError(f"Dashboard template must contain exactly one {marker} marker")
    output = template.replace(marker, safe_json(data))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".html.tmp")
    temporary.write_text(output, encoding="utf-8", newline="\n")
    temporary.replace(OUTPUT_PATH)

    review_template = REVIEW_TEMPLATE_PATH.read_text(encoding="utf-8")
    review_data = collect_review_data()
    review_marker = "__INTERVIEW_COACH_REVIEW_DATA__"
    if review_template.count(review_marker) != 1:
        raise RuntimeError(
            f"Review template must contain exactly one {review_marker} marker"
        )
    review_output = review_template.replace(review_marker, safe_json(review_data))
    review_temporary = REVIEW_OUTPUT_PATH.with_suffix(".html.tmp")
    review_temporary.write_text(review_output, encoding="utf-8", newline="\n")
    review_temporary.replace(REVIEW_OUTPUT_PATH)
    return OUTPUT_PATH, data


def main() -> None:
    args = parse_args()
    output_path, data = build_dashboard(rebuild_state=not args.skip_rebuild)
    primary = data["primary_cycle"]
    primary_summary = "none"
    if primary:
        primary_summary = (
            f"{primary['id']} covered={primary['totals']['covered']}/"
            f"{primary['totals']['questions']}"
        )
    print(
        f"dashboard={output_path.relative_to(PACK_ROOT).as_posix()} "
        f"sources={data['sources']['total']} questions={data['questions']['total']} "
        f"attempts={data['attempts']['total']} primary_cycle={primary_summary}"
    )


if __name__ == "__main__":
    main()
