from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from common import (
    DASHBOARD_ROOT,
    EVENT_ROOT,
    JOB_ROOT,
    INTERVIEW_ROOT,
    PACK_ROOT,
    REPO_ROOT,
    QUESTION_ROOTS,
    CYCLE_REPORT_ROOT,
    REVIEW_INTERVAL_DAYS,
    CYCLE_ROOT,
    SCORE_FIELDS,
    SOURCE_CATALOG_PATH,
    SOURCE_LIST_PATH,
    STATE_ROOT,
    clean_heading,
    iter_json_files,
    knowledge_score,
    load_json,
    effective_attempts,
    question_completeness_issues,
    repository_relative,
    resolve_source_list,
)
from source_readers import SOURCE_UNIT_LABELS, SourceReadError, source_format
from onboard import ONBOARDING_STATE_PATH, state_issues
from discover import PROFILE_PATH, profile_issues
from coach_model import (
    COACH_MODEL_PATH,
    OBSERVATION_ROOT,
    active_observations,
    model_issues,
    observation_issues,
)


QUESTION_STATUSES = {"active", "archived"}
QUESTION_VISIBILITIES = {"public", "private"}
CYCLE_STATUSES = {"planned", "active", "completed", "archived"}
CYCLE_KINDS = {"baseline", "maintenance", "job_targeted", "stage_targeted"}
REVIEW_POLICIES = {"coverage_once", "spaced", "coverage_then_spaced", "mixed"}
JOB_STATUSES = {"considering", "interviewing", "offer", "closed", "withdrawn"}
EXPECTED_PROTOCOL_VERSION = "0.12.0"


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.counts: Counter[str] = Counter()

    def error(self, path: Path, message: str) -> None:
        self.errors.append(f"{display(path)}: {message}")

    def warning(self, path: Path, message: str) -> None:
        self.warnings.append(f"{display(path)}: {message}")


def display(path: Path) -> str:
    try:
        return path.relative_to(PACK_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def safe_load(path: Path, validation: Validation) -> dict[str, Any] | None:
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        validation.error(path, f"invalid JSON: {error}")
        return None


def require_fields(
    value: dict[str, Any],
    required: set[str],
    path: Path,
    validation: Validation,
) -> bool:
    missing = sorted(required - value.keys())
    if missing:
        validation.error(path, f"missing fields: {', '.join(missing)}")
        return False
    return True


def validate_schemas(validation: Validation) -> None:
    schema_root = PACK_ROOT / "protocol" / "schemas"
    for path in sorted(schema_root.glob("*.json")):
        schema = safe_load(path, validation)
        if schema is None:
            continue
        validation.counts["schemas"] += 1
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            validation.error(path, "unexpected or missing JSON Schema draft")
        if "type" not in schema:
            validation.error(path, "schema has no root type")


def validate_manifest(validation: Validation) -> dict[str, Any] | None:
    path = PACK_ROOT / "manifest.json"
    manifest = safe_load(path, validation)
    if manifest is None:
        return None
    required = {
        "protocol",
        "protocol_version",
        "instructions",
        "onboarding",
        "candidate",
        "roots",
        "source_roots",
        "capabilities",
        "default_review_policy",
    }
    if not require_fields(manifest, required, path, validation):
        return manifest
    if manifest["protocol"] != "interview-coach-context-pack":
        validation.error(path, "unexpected protocol name")
    if manifest["protocol_version"] != EXPECTED_PROTOCOL_VERSION:
        validation.error(path, f"unexpected protocol version: {manifest['protocol_version']}")
    required_roots = {
        "source_catalog",
        "source_list",
        "questions",
        "private_questions",
        "jobs",
        "cycles",
    }
    missing_roots = required_roots - manifest.get("roots", {}).keys()
    if missing_roots:
        validation.error(path, f"manifest roots are missing: {', '.join(sorted(missing_roots))}")
    instructions = PACK_ROOT / manifest["instructions"]
    if not instructions.is_file():
        validation.error(path, f"instructions do not exist: {manifest['instructions']}")
    onboarding = manifest.get("onboarding")
    if not isinstance(onboarding, dict):
        validation.error(path, "onboarding configuration must be an object")
    else:
        for field in ("instructions", "guide"):
            relative = onboarding.get(field)
            if not isinstance(relative, str) or not (PACK_ROOT / relative).is_file():
                validation.error(path, f"onboarding {field} does not exist: {relative}")
        state = onboarding.get("state")
        if not isinstance(state, str) or not state.strip():
            validation.error(path, "onboarding state path is missing")
    candidate = manifest.get("candidate")
    if not isinstance(candidate, dict):
        validation.error(path, "candidate configuration must be an object")
    else:
        required_candidate = {"discovery", "profile", "observations", "model"}
        missing_candidate = sorted(required_candidate - candidate.keys())
        if missing_candidate:
            validation.error(path, f"candidate configuration is missing: {', '.join(missing_candidate)}")
        discovery = candidate.get("discovery")
        if not isinstance(discovery, str) or not (PACK_ROOT / discovery).is_file():
            validation.error(path, f"candidate discovery protocol does not exist: {discovery}")
        for field in ("profile", "observations", "model"):
            relative = candidate.get(field)
            if not isinstance(relative, str) or not relative.strip():
                validation.error(path, f"candidate {field} path is missing")
    for name, relative in manifest["roots"].items():
        target = PACK_ROOT / relative
        if name in {"source_catalog", "source_list"}:
            if not target.is_file():
                validation.error(path, f"root file does not exist: {relative}")
        elif not target.exists():
            validation.error(path, f"root directory does not exist: {relative}")
    return manifest


def validate_onboarding(validation: Validation) -> None:
    if not ONBOARDING_STATE_PATH.is_file():
        return
    state = safe_load(ONBOARDING_STATE_PATH, validation)
    if state is None:
        return
    validation.counts["onboarding_states"] += 1
    for issue in state_issues(state):
        validation.error(ONBOARDING_STATE_PATH, issue)


def validate_candidate(validation: Validation) -> None:
    profile: dict[str, Any] | None = None
    if PROFILE_PATH.is_file():
        profile = safe_load(PROFILE_PATH, validation)
        if profile is not None:
            validation.counts["candidate_profiles"] += 1
            for issue in profile_issues(profile):
                validation.error(PROFILE_PATH, issue)

    observations: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in iter_json_files(OBSERVATION_ROOT):
        observation = safe_load(path, validation)
        if observation is None:
            continue
        validation.counts["coach_observations"] += 1
        issues = observation_issues(observation)
        for issue in issues:
            validation.error(path, issue)
        identifier = observation.get("id")
        duplicate = False
        if identifier in seen_ids:
            validation.error(path, f"duplicate CoachObservation id: {identifier}")
            duplicate = True
        elif isinstance(identifier, str):
            seen_ids.add(identifier)
        if not issues and isinstance(identifier, str) and not duplicate:
            observations.append(observation)

    observations.sort(key=lambda item: (item["occurred_at"], item["id"]))
    for observation in observations:
        for superseded_id in observation["supersedes"]:
            if superseded_id not in seen_ids:
                validation.error(
                    observation.get("_path", OBSERVATION_ROOT),
                    f"supersedes unknown CoachObservation: {superseded_id}",
                )
    active_ids = [
        item["id"] for item in active_observations(observations)
        if isinstance(item.get("id"), str)
    ]
    if COACH_MODEL_PATH.is_file():
        model = safe_load(COACH_MODEL_PATH, validation)
        if model is not None:
            validation.counts["coach_models"] += 1
            for issue in model_issues(model):
                validation.error(COACH_MODEL_PATH, issue)
            if model.get("derived_from_observations") != active_ids:
                validation.error(COACH_MODEL_PATH, "projection is stale; rebuild CoachModel")
            expected_revision = profile.get("revision") if profile else None
            if model.get("candidate_profile_revision") != expected_revision:
                validation.error(COACH_MODEL_PATH, "candidate profile revision is stale")
    elif observations:
        validation.warning(COACH_MODEL_PATH, "CoachObservations exist but CoachModel has not been built")


def validate_catalog(
    manifest: dict[str, Any] | None,
    validation: Validation,
) -> None:
    catalog = safe_load(SOURCE_CATALOG_PATH, validation)
    if catalog is None or manifest is None:
        return
    if not require_fields(
        catalog,
        {"schema_version", "root", "sources"},
        SOURCE_CATALOG_PATH,
        validation,
    ):
        return
    if catalog["schema_version"] != 2:
        validation.error(
            SOURCE_CATALOG_PATH,
            f"unsupported Source Catalog schema_version: {catalog['schema_version']}",
        )
    source_root_name = catalog["root"]
    relative_root = manifest.get("source_roots", {}).get(source_root_name)
    if relative_root is None:
        validation.error(SOURCE_CATALOG_PATH, f"unknown source root: {source_root_name}")
        return
    source_root = (PACK_ROOT / relative_root).resolve()
    try:
        selected_files, source_list_warnings = resolve_source_list()
    except (OSError, ValueError) as error:
        validation.error(SOURCE_LIST_PATH, str(error))
        return
    for warning in source_list_warnings:
        validation.warning(SOURCE_LIST_PATH, warning)
    selected_paths = {repository_relative(path).as_posix() for path in selected_files}
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for source in catalog["sources"]:
        validation.counts["sources"] += 1
        source_id = source.get("id")
        source_path = source.get("path")
        if source_id in seen_ids:
            validation.error(SOURCE_CATALOG_PATH, f"duplicate Source id: {source_id}")
        if source_path in seen_paths:
            validation.error(SOURCE_CATALOG_PATH, f"duplicate Source path: {source_path}")
        seen_ids.add(source_id)
        seen_paths.add(source_path)
        if not source_path:
            validation.error(SOURCE_CATALOG_PATH, f"Source {source_id} has no path")
            continue
        target = (source_root / source_path).resolve()
        try:
            target.relative_to(source_root)
        except ValueError:
            validation.error(SOURCE_CATALOG_PATH, f"Source escapes root: {source_path}")
            continue
        if not target.is_file():
            validation.error(SOURCE_CATALOG_PATH, f"Source does not exist: {source_path}")
            continue
        try:
            expected_format = source_format(target)
        except SourceReadError as error:
            validation.error(SOURCE_CATALOG_PATH, str(error))
            continue
        if source.get("format") != expected_format:
            validation.error(
                SOURCE_CATALOG_PATH,
                f"Source format mismatch for {source_path}: "
                f"{source.get('format')} != {expected_format}",
            )
        expected_unit_label = SOURCE_UNIT_LABELS[expected_format]
        if source.get("unit_label") != expected_unit_label:
            validation.error(
                SOURCE_CATALOG_PATH,
                f"Source unit label mismatch for {source_path}: "
                f"{source.get('unit_label')} != {expected_unit_label}",
            )
        current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if current_hash != source.get("content_sha256"):
            validation.warning(SOURCE_CATALOG_PATH, f"Source changed since indexing: {source_path}")
        extracted_hash = source.get("questions_extracted_from_sha256")
        if source.get("status") == "ready" and extracted_hash != source.get("content_sha256"):
            validation.warning(
                SOURCE_CATALOG_PATH,
                f"Source is pending Question extraction: {source_path}",
            )
        if source.get("status") == "empty":
            validation.warning(SOURCE_CATALOG_PATH, f"Source is empty: {source_path}")
    catalog_paths = {source.get("path") for source in catalog["sources"] if source.get("path")}
    for missing in sorted(selected_paths - catalog_paths):
        validation.error(SOURCE_CATALOG_PATH, f"selected Source is missing from catalog: {missing}")
    for stale in sorted(catalog_paths - selected_paths):
        validation.error(SOURCE_CATALOG_PATH, f"catalog contains an unselected Source: {stale}")


def load_and_validate_questions(
    manifest: dict[str, Any] | None,
    validation: Validation,
) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    source_roots = manifest.get("source_roots", {}) if manifest else {}
    for question_root, storage_visibility in QUESTION_ROOTS:
        for path in iter_json_files(question_root, exclude_names={"index.json"}):
            question = safe_load(path, validation)
            if question is None:
                continue
            validation.counts["questions"] += 1
            required = {
                "schema_version",
                "id",
                "revision",
                "status",
                "visibility",
                "topic",
                "kind",
                "prompt",
                "source_refs",
                "evaluation_basis",
            }
            if not require_fields(question, required, path, validation):
                continue
            question_id = question["id"]
            if question_id in questions:
                validation.error(path, f"duplicate Question id: {question_id}")
            questions[question_id] = question
            if question["schema_version"] != 3:
                validation.error(path, f"unsupported Question schema_version: {question['schema_version']}")
            if question["status"] not in QUESTION_STATUSES:
                validation.error(path, f"invalid Question status: {question['status']}")
            if question["visibility"] not in QUESTION_VISIBILITIES:
                validation.error(path, f"invalid Question visibility: {question['visibility']}")
            if question["visibility"] != storage_visibility:
                validation.error(
                    path,
                    f"Question visibility {question['visibility']} does not match "
                    f"storage root {storage_visibility}",
                )
            if not question["prompt"].strip():
                validation.error(path, "Question prompt is empty")
            if question["status"] == "active":
                for issue in question_completeness_issues(question["prompt"]):
                    validation.error(path, f"incomplete Question prompt: {issue}")
            if question.get("evaluation_basis") == "rubric" and not question.get("rubric"):
                validation.error(path, "rubric evaluation requires at least one rubric item")

            for reference in question.get("source_refs", []):
                root_name = reference.get("root")
                source_path = reference.get("path")
                heading = reference.get("heading")
                if root_name not in source_roots:
                    validation.error(path, f"unknown source root: {root_name}")
                    continue
                target = (PACK_ROOT / source_roots[root_name] / source_path).resolve()
                if not target.is_file():
                    validation.error(path, f"source file does not exist: {source_path}")
                    continue
                try:
                    reference_format = source_format(target)
                except SourceReadError as error:
                    validation.error(path, str(error))
                    continue
                unit = reference.get("unit")
                unit_label = reference.get("unit_label")
                if (unit is None) != (unit_label is None):
                    validation.error(
                        path,
                        "SourceRef unit and unit_label must be provided together",
                    )
                if unit_label and unit_label != SOURCE_UNIT_LABELS[reference_format]:
                    validation.error(
                        path,
                        f"SourceRef unit_label {unit_label} does not match "
                        f"{reference_format}",
                    )
                if reference_format != "markdown":
                    continue
                try:
                    text = target.read_text(encoding="utf-8-sig")
                except UnicodeDecodeError:
                    validation.error(path, f"source file is not UTF-8: {source_path}")
                    continue
                headings = {
                    clean_heading(line)
                    for line in text.splitlines()
                    if line.startswith("##")
                }
                if clean_heading(heading) not in headings:
                    validation.warning(path, f"source heading was not found: {heading}")
    return questions


def load_and_validate_jobs(
    questions: dict[str, dict[str, Any]],
    validation: Validation,
) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(JOB_ROOT):
        job = safe_load(path, validation)
        if job is None:
            continue
        validation.counts["jobs"] += 1
        required = {
            "schema_version",
            "id",
            "status",
            "company",
            "role_title",
            "target_roles",
            "brief_path",
            "question_plan",
        }
        if not require_fields(job, required, path, validation):
            continue
        job_id = job["id"]
        if job.get("schema_version") != 1:
            validation.error(path, f"unsupported Job schema_version: {job.get('schema_version')}")
        if not job_id.startswith("job."):
            validation.error(path, f"invalid Job id: {job_id}")
        if path.stem != job_id:
            validation.error(path, f"filename does not match Job id: {job_id}")
        if job_id in jobs:
            validation.error(path, f"duplicate Job id: {job_id}")
        jobs[job_id] = job
        if job["status"] not in JOB_STATUSES:
            validation.error(path, f"invalid Job status: {job['status']}")

        brief_path = REPO_ROOT / job["brief_path"]
        try:
            repository_relative(brief_path)
        except ValueError as error:
            validation.error(path, str(error))
        else:
            if not brief_path.is_file():
                validation.error(path, f"Job brief does not exist: {job['brief_path']}")

        seen_question_ids: set[str] = set()
        for item in job["question_plan"]:
            question_id = item.get("question_id")
            if question_id in seen_question_ids:
                validation.error(path, f"duplicate Question in Job plan: {question_id}")
            seen_question_ids.add(question_id)
            if question_id not in questions:
                validation.error(path, f"unknown Question in Job plan: {question_id}")
            if item.get("priority") not in {"must", "should", "stretch"}:
                validation.error(path, f"invalid Job question priority: {item.get('priority')}")
            target_minutes = item.get("target_minutes")
            if not isinstance(target_minutes, int) or target_minutes < 1:
                validation.error(path, f"invalid target_minutes for {question_id}: {target_minutes}")
            if not str(item.get("rationale", "")).strip():
                validation.error(path, f"empty rationale for Job Question: {question_id}")
    return jobs


def markdown_list_field(text: str, label: str) -> str | None:
    match = re.search(
        rf"^\s*-\s*{re.escape(label)}\s*[：:]\s*(.+?)\s*$",
        text,
        re.MULTILINE,
    )
    if match is None:
        return None
    return match.group(1).strip().strip("`").strip()


def validate_interview_experiences(
    jobs: dict[str, dict[str, Any]],
    validation: Validation,
    *,
    root: Path | None = None,
) -> None:
    experience_root = root or INTERVIEW_ROOT / "experiences"
    if not experience_root.exists():
        return

    for path in sorted(experience_root.rglob("*.md")):
        validation.counts["interview_experiences"] += 1
        text = path.read_text(encoding="utf-8-sig")
        job_id = markdown_list_field(text, "Job ID")
        interview_stage = markdown_list_field(text, "InterviewStage")

        if job_id is None:
            validation.error(path, "InterviewExperience has no Job ID field")
        elif job_id == "unresolved":
            validation.warning(path, "InterviewExperience Job association is unresolved")
        elif job_id != "untracked" and job_id not in jobs:
            validation.error(path, f"InterviewExperience references unknown Job: {job_id}")
        elif job_id in jobs and markdown_list_field(text, "Job Brief") is None:
            validation.error(path, "Job-linked InterviewExperience has no Job Brief field")

        if interview_stage is None:
            validation.error(path, "InterviewExperience has no InterviewStage field")
        elif interview_stage == "unresolved":
            validation.warning(path, "InterviewExperience stage is unresolved")


def load_and_validate_cycles(
    questions: dict[str, dict[str, Any]],
    jobs: dict[str, dict[str, Any]],
    validation: Validation,
) -> dict[str, dict[str, Any]]:
    cycles: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(CYCLE_ROOT):
        cycle = safe_load(path, validation)
        if cycle is None:
            continue
        validation.counts["cycles"] += 1
        required = {
            "schema_version",
            "id",
            "name",
            "kind",
            "learner_id",
            "status",
            "review_policy",
            "question_ids",
        }
        if not require_fields(cycle, required, path, validation):
            continue
        cycle_id = cycle["id"]
        if cycle["schema_version"] != 2:
            validation.error(path, f"unsupported PreparationCycle schema_version: {cycle['schema_version']}")
        if not cycle_id.startswith("cycle."):
            validation.error(path, f"invalid PreparationCycle id: {cycle_id}")
        if path.stem != cycle_id:
            validation.error(path, f"filename does not match PreparationCycle id: {cycle_id}")
        if cycle_id in cycles:
            validation.error(path, f"duplicate PreparationCycle id: {cycle_id}")
        cycles[cycle_id] = cycle
        if cycle["kind"] not in CYCLE_KINDS:
            validation.error(path, f"invalid PreparationCycle kind: {cycle['kind']}")
        job_id = cycle.get("job_id")
        if cycle["kind"] == "job_targeted":
            if not job_id:
                validation.error(path, "job_targeted PreparationCycle has no job_id")
            elif job_id not in jobs:
                validation.error(path, f"unknown Job: {job_id}")
        elif job_id:
            validation.error(path, "job_id is only valid for a job_targeted PreparationCycle")
        if cycle["status"] not in CYCLE_STATUSES:
            validation.error(path, f"invalid PreparationCycle status: {cycle['status']}")
        if cycle["review_policy"] not in REVIEW_POLICIES:
            validation.error(path, f"invalid review policy: {cycle['review_policy']}")
        if cycle["status"] == "completed" and not cycle.get("completed_at"):
            validation.error(path, "completed PreparationCycle has no completed_at")
        if cycle["status"] == "active" and cycle.get("completed_at"):
            validation.error(path, "active PreparationCycle must not have completed_at")
        for question_id in cycle["question_ids"]:
            if question_id not in questions:
                validation.error(path, f"unknown Question in snapshot: {question_id}")
        from diagnostic import snapshot_issues
        for issue in snapshot_issues(cycle):
            validation.error(path, issue)
    return cycles


def validate_events(
    questions: dict[str, dict[str, Any]],
    cycles: dict[str, dict[str, Any]],
    validation: Validation,
) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(EVENT_ROOT):
        event = safe_load(path, validation)
        if event is None:
            continue
        validation.counts["events"] += 1
        required = {
            "schema_version",
            "id",
            "type",
            "occurred_at",
            "learner_id",
            "cycle_id",
            "practice_session_id",
            "question_id",
            "question_revision",
            "answer",
            "hints_used",
            "evaluation",
        }
        if not require_fields(event, required, path, validation):
            continue
        event_id = event["id"]
        if event["schema_version"] != 2:
            validation.error(path, f"unsupported AttemptEvent schema_version: {event['schema_version']}")
        if not event["cycle_id"].startswith("cycle."):
            validation.error(path, f"invalid PreparationCycle id: {event['cycle_id']}")
        if not event["practice_session_id"].startswith("practice-session."):
            validation.error(path, f"invalid PracticeSession id: {event['practice_session_id']}")
        if event_id in events:
            validation.error(path, f"duplicate AttemptEvent id: {event_id}")
        events[event_id] = event
        if event["type"] not in {"attempt.recorded", "attempt.reevaluated"}:
            validation.error(path, f"unsupported Event type: {event['type']}")
        if "assistance" in event and event["assistance"] not in {"independent", "hints", "reference_seen"}:
            validation.error(path, "invalid assistance level")
        if event.get("assistance") == "independent" and event.get("hints_used"):
            validation.error(path, "independent answer cannot have hints_used")
        question_id = event["question_id"]
        cycle_id = event["cycle_id"]
        if question_id not in questions:
            validation.error(path, f"unknown Question: {question_id}")
        if cycle_id not in cycles:
            validation.error(path, f"unknown PreparationCycle: {cycle_id}")
        elif question_id not in cycles[cycle_id]["question_ids"]:
            validation.error(path, "Question is outside the PreparationCycle snapshot")
        if not event.get("answer", {}).get("text", "").strip():
            validation.error(path, "answer text is empty")
        scores = event.get("evaluation", {}).get("scores", {})
        for field in SCORE_FIELDS:
            score = scores.get(field)
            if not isinstance(score, int) or not 0 <= score <= 4:
                validation.error(path, f"invalid score {field}: {score}")
    return events


def validate_state(
    questions: dict[str, dict[str, Any]],
    cycles: dict[str, dict[str, Any]],
    events: dict[str, dict[str, Any]],
    validation: Validation,
) -> None:
    for path in iter_json_files(STATE_ROOT):
        if path == COACH_MODEL_PATH:
            continue
        state = safe_load(path, validation)
        if state is None:
            continue
        validation.counts["state_files"] += 1
        if state.get("schema_version") not in {2, 3}:
            validation.error(path, f"unsupported state schema_version: {state.get('schema_version')}")
        for event_id in state.get("derived_from_events", []):
            if event_id not in events:
                validation.error(path, f"state references unknown Event: {event_id}")
        if "cycle_id" in state and state["cycle_id"] not in cycles:
            validation.error(path, f"state references unknown PreparationCycle: {state['cycle_id']}")
        if "cycle_id" in state:
            required = {"cycle_status", "totals", "statistics", "questions"}
            require_fields(state, required, path, validation)
            if path.stem != state["cycle_id"]:
                validation.error(path, f"filename does not match PreparationCycle id: {state['cycle_id']}")
            question_states = state.get("questions", [])
            totals = state.get("totals", {})
            expected_unseen = sum(item.get("status") == "unseen" for item in question_states)
            expected_due = sum(item.get("status") == "due" for item in question_states)
            expected_covered = len(question_states) - expected_unseen
            expected_totals = {
                "questions": len(question_states),
                "unseen": expected_unseen,
                "covered": expected_covered,
                "due": expected_due,
            }
            if totals != expected_totals:
                validation.error(path, f"inconsistent totals: expected {expected_totals}")
            statistics = state.get("statistics", {})
            if statistics.get("total_attempts") != len(state.get("derived_from_events", [])):
                validation.error(path, "statistics.total_attempts does not match derived events")
        for item in state.get("questions", []):
            if item.get("question_id") not in questions:
                validation.error(path, f"state references unknown Question: {item.get('question_id')}")
            scores = item.get("scores")
            if scores is None:
                expected_interval = 1 if item.get("evidence_status") == "awaiting_independent" else None
                if item.get("knowledge_score") is not None or item.get("review_interval_days") != expected_interval:
                    validation.error(path, f"unscored Question has scheduling data: {item.get('question_id')}")
                continue
            expected_score = knowledge_score(scores)
            if item.get("knowledge_score") != expected_score:
                validation.error(path, f"incorrect knowledge_score: {item.get('question_id')}")
            if item.get("review_interval_days") != REVIEW_INTERVAL_DAYS[expected_score]:
                validation.error(path, f"incorrect review_interval_days: {item.get('question_id')}")


def validate_reports(
    questions: dict[str, dict[str, Any]],
    cycles: dict[str, dict[str, Any]],
    events: dict[str, dict[str, Any]],
    validation: Validation,
) -> None:
    for path in iter_json_files(CYCLE_REPORT_ROOT):
        report = safe_load(path, validation)
        if report is None:
            continue
        validation.counts["cycle_reports"] += 1
        required = {
            "schema_version",
            "cycle_id",
            "generated_at",
            "cycle",
            "totals",
            "statistics",
            "highlights",
            "questions",
            "derived_from_events",
        }
        if not require_fields(report, required, path, validation):
            continue
        cycle_id = report["cycle_id"]
        if report["schema_version"] not in {2, 3}:
            validation.error(path, f"unsupported CycleReport schema_version: {report['schema_version']}")
        if path.stem != cycle_id:
            validation.error(path, f"filename does not match PreparationCycle id: {cycle_id}")
        if report.get("cycle", {}).get("id") != cycle_id:
            validation.error(path, "CycleReport cycle.id differs from cycle_id")
        cycle = cycles.get(cycle_id)
        if cycle is None:
            validation.error(path, f"report references unknown PreparationCycle: {cycle_id}")
        elif cycle["status"] != "completed":
            validation.error(path, "report exists for a PreparationCycle that is not completed")
        elif report.get("cycle", {}).get("completed_at") != cycle.get("completed_at"):
            validation.error(path, "report completed_at differs from PreparationCycle")
        for event_id in report.get("derived_from_events", []):
            event = events.get(event_id)
            if event is None:
                validation.error(path, f"report references unknown Event: {event_id}")
            elif event["cycle_id"] != cycle_id:
                validation.error(path, f"report references Event from another PreparationCycle: {event_id}")
        report_question_ids = [item.get("question_id") for item in report.get("questions", [])]
        if cycle and report_question_ids != cycle["question_ids"]:
            validation.error(path, "report Question order or snapshot differs from PreparationCycle")
        for question_id in report_question_ids:
            if question_id not in questions:
                validation.error(path, f"report references unknown Question: {question_id}")


def validate_dashboard(
    questions: dict[str, dict[str, Any]],
    cycles: dict[str, dict[str, Any]],
    events: dict[str, dict[str, Any]],
    validation: Validation,
) -> None:
    template_path = DASHBOARD_ROOT / "template.html"
    output_path = DASHBOARD_ROOT / "index.html"
    marker = "__INTERVIEW_COACH_DASHBOARD_DATA__"
    if not template_path.is_file():
        validation.error(template_path, "Dashboard template does not exist")
        return
    template = template_path.read_text(encoding="utf-8")
    if template.count(marker) != 1:
        validation.error(template_path, f"expected exactly one {marker} marker")
    if not output_path.is_file():
        validation.error(output_path, "generated Dashboard does not exist")
        return
    output = output_path.read_text(encoding="utf-8")
    if marker in output:
        validation.error(output_path, "generated Dashboard still contains the data marker")
        return
    prefix = "const dashboardData = "
    start = output.find(prefix)
    end = output.find(";\n", start)
    if start < 0 or end < 0:
        validation.error(output_path, "could not locate embedded Dashboard data")
        return
    try:
        data = json.loads(output[start + len(prefix) : end])
    except json.JSONDecodeError as error:
        validation.error(output_path, f"invalid embedded Dashboard data: {error}")
        return
    validation.counts["dashboards"] += 1
    if data.get("protocol_version") != EXPECTED_PROTOCOL_VERSION:
        validation.error(output_path, "Dashboard protocol version is stale")
    if data.get("questions", {}).get("total") != len(questions):
        validation.error(output_path, "Dashboard Question count is stale")
    if len(data.get("questions", {}).get("items", [])) != len(questions):
        validation.error(output_path, "Dashboard Question details are stale")
    if len(data.get("sources", {}).get("items", [])) != data.get("sources", {}).get("total"):
        validation.error(output_path, "Dashboard Source details are stale")
    if len(data.get("cycles", [])) != len(cycles):
        validation.error(output_path, "Dashboard PreparationCycle count is stale")
    if len(data.get("jobs", [])) != validation.counts["jobs"]:
        validation.error(output_path, "Dashboard Job count is stale")
    attempt_ids = {event_id for event_id, event in events.items() if event.get("type") == "attempt.recorded"}
    if data.get("attempts", {}).get("total") != len(attempt_ids):
        validation.error(output_path, "Dashboard AttemptEvent count is stale")

    review_template_path = DASHBOARD_ROOT / "review-template.html"
    review_output_path = DASHBOARD_ROOT / "review.html"
    review_marker = "__INTERVIEW_COACH_REVIEW_DATA__"
    if not review_template_path.is_file():
        validation.error(review_template_path, "answer review template does not exist")
    elif review_template_path.read_text(encoding="utf-8").count(review_marker) != 1:
        validation.error(review_template_path, f"expected exactly one {review_marker} marker")
    if not review_output_path.is_file():
        validation.error(review_output_path, "generated answer review page does not exist")
    else:
        review_output = review_output_path.read_text(encoding="utf-8")
        if review_marker in review_output:
            validation.error(review_output_path, "generated answer review still contains the data marker")
        else:
            review_prefix = "const reviewData = "
            review_start = review_output.find(review_prefix)
            review_end = review_output.find(";\n", review_start)
            if review_start < 0 or review_end < 0:
                validation.error(review_output_path, "could not locate embedded answer review data")
            else:
                try:
                    review_data = json.loads(
                        review_output[review_start + len(review_prefix) : review_end]
                    )
                except json.JSONDecodeError as error:
                    validation.error(
                        review_output_path,
                        f"invalid embedded answer review data: {error}",
                    )
                else:
                    validation.counts["review_pages"] += 1
                    review_event_ids = {
                        attempt.get("id")
                        for group in review_data.get("review_groups", [])
                        for attempt in group.get("attempts", [])
                    }
                    if review_event_ids != attempt_ids:
                        validation.error(
                            review_output_path,
                            "answer review page does not contain every AttemptEvent",
                        )
                    if review_data.get("attempt_count") != len(attempt_ids):
                        validation.error(review_output_path, "answer review count is stale")

    review_notes_path = PACK_ROOT / "workspace" / "reports" / "answer-review.md"
    if not review_notes_path.is_file():
        validation.error(review_notes_path, "generated answer review notebook does not exist")
    else:
        review_notes = review_notes_path.read_text(encoding="utf-8")
        missing_event_ids = [event_id for event_id in events if f"`{event_id}`" not in review_notes]
        if missing_event_ids:
            validation.error(
                review_notes_path,
                f"answer review notebook is missing {len(missing_event_ids)} AttemptEvent(s)",
            )


def main() -> None:
    validation = Validation()
    validate_schemas(validation)
    manifest = validate_manifest(validation)
    validate_onboarding(validation)
    validate_candidate(validation)
    validate_catalog(manifest, validation)
    questions = load_and_validate_questions(manifest, validation)
    jobs = load_and_validate_jobs(questions, validation)
    validate_interview_experiences(jobs, validation)
    cycles = load_and_validate_cycles(questions, jobs, validation)
    events = validate_events(questions, cycles, validation)
    validate_state(questions, cycles, events, validation)
    validate_reports(questions, cycles, events, validation)
    validate_dashboard(questions, cycles, events, validation)

    result = {
        "status": "ok" if not validation.errors else "error",
        "counts": dict(sorted(validation.counts.items())),
        "warnings": validation.warnings,
        "errors": validation.errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if validation.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
