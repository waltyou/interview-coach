from __future__ import annotations

import argparse
from datetime import datetime

from common import (
    CYCLE_ROOT,
    PACK_ROOT,
    load_jobs,
    load_questions,
    now_iso,
    slugify,
    write_json,
)


CYCLE_KINDS = ("baseline", "maintenance", "job_targeted", "stage_targeted")


def comma_values(value: str) -> list[str]:
    return sorted({item.strip().lower() for item in value.split(",") if item.strip()})


def matches_topics(question_topic: str, requested_topics: list[str]) -> bool:
    if not requested_topics or "*" in requested_topics:
        return True
    return any(
        question_topic == topic
        or question_topic.startswith(topic + ".")
        or topic.startswith(question_topic + ".")
        for topic in requested_topics
    )


def default_cycle_id(name: str) -> str:
    now = datetime.now().astimezone()
    return f"cycle.{now:%Y}.{slugify(name, 'review')}.{now:%Y%m%d}"


def snapshot_question_ids(
    questions: dict[str, dict],
    *,
    topics: list[str],
    visibility: str,
    job: dict | None = None,
) -> list[str]:
    if job is not None:
        candidates = [item["question_id"] for item in job["question_plan"]]
    else:
        candidates = sorted(questions)

    return [
        question_id
        for question_id in candidates
        if question_id in questions
        and questions[question_id]["status"] == "active"
        and (visibility == "all" or questions[question_id]["visibility"] == visibility)
        and matches_topics(questions[question_id]["topic"], topics)
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a PreparationCycle snapshot")
    parser.add_argument("--name", required=True)
    parser.add_argument("--cycle-id")
    parser.add_argument("--kind", choices=CYCLE_KINDS, default="baseline")
    parser.add_argument(
        "--job-id",
        help="Required for job_targeted cycles; snapshots the Job question plan in curated order",
    )
    parser.add_argument("--learner", default="me")
    parser.add_argument("--topics", default="*")
    parser.add_argument("--roles", default="")
    parser.add_argument(
        "--visibility",
        choices=("all", "public", "private"),
        default="all",
        help="Select both public and private Questions by default",
    )
    parser.add_argument(
        "--policy",
        choices=("coverage_once", "spaced", "coverage_then_spaced", "mixed"),
        default=None,
    )
    parser.add_argument("--limit", type=int, help="Short baseline: balanced sample across topics (for example 8)")
    parser.add_argument("--planned", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    created_at = now_iso()
    cycle_id = args.cycle_id or default_cycle_id(args.name)
    output_path = CYCLE_ROOT / f"{cycle_id}.json"
    if output_path.exists():
        raise SystemExit(f"PreparationCycle already exists: {output_path}")

    topics = comma_values(args.topics) or ["*"]
    roles = comma_values(args.roles)
    questions = load_questions()
    jobs = load_jobs()
    job = None
    if args.kind == "job_targeted":
        if not args.job_id:
            raise SystemExit("--job-id is required for a job_targeted PreparationCycle")
        job = jobs.get(args.job_id)
        if job is None:
            raise SystemExit(f"Unknown Job: {args.job_id}")
        roles = roles or list(job.get("target_roles", []))
    elif args.job_id:
        raise SystemExit("--job-id can only be used with --kind job_targeted")

    question_ids = snapshot_question_ids(
        questions,
        topics=topics,
        visibility=args.visibility,
        job=job,
    )
    if not question_ids:
        raise SystemExit("No active Question matches the requested topics")
    diagnostic = None
    if args.limit is not None:
        if args.limit < 1 or args.kind != "baseline":
            raise SystemExit("--limit must be positive and is only supported for baseline cycles")
        pool = question_ids
        question_ids = balanced_sample(pool, questions, args.limit)
        from diagnostic import snapshot
        diagnostic = snapshot(pool, question_ids, questions)
    if job is not None and topics == ["*"]:
        topics = sorted({questions[question_id]["topic"] for question_id in question_ids})

    status = "planned" if args.planned else "active"
    cycle = {
        "$schema": "../../protocol/schemas/preparation-cycle.schema.json",
        "schema_version": 2,
        "id": cycle_id,
        "name": args.name,
        "kind": args.kind,
        "learner_id": args.learner,
        "status": status,
        "created_at": created_at,
        "started_at": None if args.planned else created_at,
        "completed_at": None,
        "target_roles": roles,
        "topics": topics,
        "question_set_policy": "snapshot",
        "review_policy": args.policy or ("mixed" if args.kind == "maintenance" else "coverage_then_spaced"),
        "same_day_repeat": False,
        "question_ids": question_ids,
    }
    if job is not None:
        cycle["job_id"] = job["id"]
    if diagnostic is not None:
        cycle["diagnostic"] = diagnostic
    write_json(output_path, cycle)
    from build_dashboard import build_dashboard

    dashboard_path, _ = build_dashboard()
    print(
        f"cycle_id={cycle_id} kind={args.kind} status={status} "
        f"visibility={args.visibility} questions={len(question_ids)} "
        f"path={output_path.relative_to(PACK_ROOT).as_posix()} "
        f"dashboard={dashboard_path.relative_to(PACK_ROOT).as_posix()}"
    )


def balanced_sample(question_ids: list[str], questions: dict[str, dict], limit: int) -> list[str]:
    from diagnostic import sample
    return sample(question_ids, questions, limit)


if __name__ == "__main__":
    main()
