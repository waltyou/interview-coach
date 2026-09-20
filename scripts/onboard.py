from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import PACK_ROOT, load_json, now_iso, write_json
from discover import DiscoveryError, discovery_requirements, load_profile


ONBOARDING_STATE_PATH = PACK_ROOT / "workspace" / "onboarding.json"
ONBOARDING_STEPS = ("privacy", "goal", "profile", "materials", "first_value")
REQUIRED_STEPS = {"privacy", "goal", "profile", "first_value"}
STEP_STATUSES = {"pending", "completed", "skipped"}
LIFECYCLE_STATUSES = {"in_progress", "completed", "skipped"}
ENTRY_PATHS = {
    "baseline",
    "job_targeted",
    "knowledge_import",
    "resume",
    "interview_retro",
    "explore",
}
PRIVACY_CHOICES = {"private_remote", "local_only", "no_personal_data"}
ACTIVATION_KINDS = {
    "cycle_started",
    "source_indexed",
    "resume_initialized",
    "interview_experience_captured",
    "guide_reviewed",
    "candidate_discovery_completed",
}
EVIDENCE_GLOBS = (
    "workspace/sessions/**/*.json",
    "workspace/jobs/**/*.json",
    "workspace/cycles/**/*.json",
    "workspace/events/**/*.json",
    "workspace/questions/**/*.json",
    "workspace/sources/**/*",
    "workspace/resume/Markdown/**/*.md",
)


class OnboardingError(RuntimeError):
    pass


def required_steps(state: dict[str, Any]) -> set[str]:
    return REQUIRED_STEPS - {"profile"} if state.get("entry_path") == "explore" else REQUIRED_STEPS


def empty_step() -> dict[str, Any]:
    return {"status": "pending", "completed_at": None}


def new_state(timestamp: str | None = None) -> dict[str, Any]:
    timestamp = timestamp or now_iso()
    return {
        "$schema": "../protocol/schemas/onboarding.schema.json",
        "schema_version": 2,
        "status": "in_progress",
        "started_at": timestamp,
        "updated_at": timestamp,
        "completed_at": None,
        "skipped_at": None,
        "current_step": "privacy",
        "entry_path": None,
        "privacy_choice": None,
        "candidate_profile_path": None,
        "activation": {"kind": None, "reference": None},
        "steps": {step: empty_step() for step in ONBOARDING_STEPS},
    }


def state_issues(state: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required = {
        "schema_version",
        "status",
        "started_at",
        "updated_at",
        "completed_at",
        "skipped_at",
        "current_step",
        "entry_path",
        "privacy_choice",
        "candidate_profile_path",
        "activation",
        "steps",
    }
    missing = sorted(required - state.keys())
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    if state["schema_version"] != 2:
        issues.append(f"unsupported schema_version: {state['schema_version']}")
    if state["status"] not in LIFECYCLE_STATUSES:
        issues.append(f"invalid status: {state['status']}")
    valid_current_steps = set(ONBOARDING_STEPS) | {"done"}
    if state["current_step"] not in valid_current_steps:
        issues.append(f"invalid current_step: {state['current_step']}")
    if state["entry_path"] is not None and state["entry_path"] not in ENTRY_PATHS:
        issues.append(f"invalid entry_path: {state['entry_path']}")
    if (
        state["privacy_choice"] is not None
        and state["privacy_choice"] not in PRIVACY_CHOICES
    ):
        issues.append(f"invalid privacy_choice: {state['privacy_choice']}")

    steps = state["steps"]
    if not isinstance(steps, dict):
        issues.append("steps must be an object")
    else:
        missing_steps = sorted(set(ONBOARDING_STEPS) - steps.keys())
        if missing_steps:
            issues.append(f"missing steps: {', '.join(missing_steps)}")
        unexpected_steps = sorted(steps.keys() - set(ONBOARDING_STEPS))
        if unexpected_steps:
            issues.append(f"unexpected steps: {', '.join(unexpected_steps)}")
        for step in ONBOARDING_STEPS:
            item = steps.get(step)
            if not isinstance(item, dict):
                issues.append(f"step {step} must be an object")
                continue
            step_status = item.get("status")
            if step_status not in STEP_STATUSES:
                issues.append(f"invalid {step} status: {step_status}")
            completed_at = item.get("completed_at")
            if step_status in {"completed", "skipped"} and not completed_at:
                issues.append(f"step {step} has no completed_at")
            if step_status == "pending" and completed_at is not None:
                issues.append(f"pending step {step} has completed_at")

    candidate_profile_path = state["candidate_profile_path"]
    if candidate_profile_path is not None and (
        not isinstance(candidate_profile_path, str) or not candidate_profile_path.strip()
    ):
        issues.append("candidate_profile_path must be a non-empty string or null")

    activation = state["activation"]
    if not isinstance(activation, dict):
        issues.append("activation must be an object")
    else:
        missing_activation = sorted({"kind", "reference"} - activation.keys())
        if missing_activation:
            issues.append(f"activation is missing: {', '.join(missing_activation)}")
        kind = activation.get("kind")
        reference = activation.get("reference")
        if kind is not None and kind not in ACTIVATION_KINDS:
            issues.append(f"invalid activation kind: {kind}")
        if reference is not None and (
            not isinstance(reference, str) or not reference.strip()
        ):
            issues.append("activation reference must be a non-empty string or null")

    if isinstance(steps, dict):
        def recorded_status(step: str) -> str | None:
            item = steps.get(step)
            return item.get("status") if isinstance(item, dict) else None

        privacy = recorded_status("privacy")
        goal = recorded_status("goal")
        profile_step = recorded_status("profile")
        first_value = recorded_status("first_value")
        if privacy == "completed" and state["privacy_choice"] is None:
            issues.append("completed privacy step has no privacy_choice")
        if goal == "completed" and state["entry_path"] is None:
            issues.append("completed goal step has no entry_path")
        if profile_step == "completed" and state["candidate_profile_path"] is None:
            issues.append("completed profile step has no candidate_profile_path")
        if first_value == "completed" and isinstance(activation, dict):
            if activation.get("kind") is None or activation.get("reference") is None:
                issues.append("completed first_value step has no activation result")
        if state["status"] == "completed":
            if state["current_step"] != "done" or not state["completed_at"]:
                issues.append("completed onboarding must be at done with completed_at")
            for step in required_steps(state):
                if recorded_status(step) != "completed":
                    issues.append(f"completed onboarding requires completed step: {step}")
            pending = [
                step
                for step in ONBOARDING_STEPS
                if recorded_status(step) == "pending"
            ]
            if pending:
                issues.append(f"completed onboarding has pending steps: {', '.join(pending)}")
        if state["status"] == "skipped":
            if state["current_step"] != "done" or not state["skipped_at"]:
                issues.append("skipped onboarding must be at done with skipped_at")
        if state["status"] == "in_progress":
            if state["completed_at"] is not None or state["skipped_at"] is not None:
                issues.append("in-progress onboarding cannot have a terminal timestamp")
    return issues


def load_state(path: Path = ONBOARDING_STATE_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise OnboardingError(f"Onboarding has not started: {path}")
    try:
        state = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        raise OnboardingError(f"Invalid onboarding state: {path}: {error}") from error
    issues = state_issues(state)
    if issues:
        raise OnboardingError(f"Invalid onboarding state: {'; '.join(issues)}")
    return state


def workspace_evidence(pack_root: Path = PACK_ROOT) -> list[str]:
    evidence: set[str] = set()
    for pattern in EVIDENCE_GLOBS:
        for path in pack_root.glob(pattern):
            if not path.is_file() or path.name in {".gitkeep", "README.md", "index.json"}:
                continue
            evidence.add(path.relative_to(pack_root).as_posix())
    return sorted(evidence)


def next_pending_step(state: dict[str, Any]) -> str:
    for step in ONBOARDING_STEPS:
        if state["steps"][step]["status"] == "pending":
            return step
    return "done"


def status_payload(
    state_path: Path = ONBOARDING_STATE_PATH,
    pack_root: Path = PACK_ROOT,
) -> dict[str, Any]:
    evidence = workspace_evidence(pack_root)
    if not state_path.is_file():
        status = "existing" if evidence else "new"
        return {
            "status": status,
            "current_step": None if evidence else "privacy",
            "state_path": state_path.relative_to(pack_root).as_posix(),
            "existing_workspace": bool(evidence),
            "evidence_count": len(evidence),
            "recommended_action": (
                "offer_optional_onboarding" if evidence else "start_onboarding"
            ),
        }
    state = load_state(state_path)
    return {
        "status": state["status"],
        "current_step": state["current_step"],
        "state_path": state_path.relative_to(pack_root).as_posix(),
        "existing_workspace": bool(evidence),
        "evidence_count": len(evidence),
        "entry_path": state["entry_path"],
        "privacy_choice": state["privacy_choice"],
        "recommended_action": (
            f"continue_{state['current_step']}"
            if state["status"] == "in_progress"
            else "normal_use"
        ),
    }


def start_onboarding(
    path: Path = ONBOARDING_STATE_PATH,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if path.is_file():
        state = load_state(path)
        if state["status"] == "in_progress":
            return state
        raise OnboardingError(
            f"Onboarding is already {state['status']}; start does not reset user state"
        )
    state = new_state(timestamp)
    write_json(path, state)
    return state


def record_step(
    step: str,
    *,
    path: Path = ONBOARDING_STATE_PATH,
    skipped: bool = False,
    timestamp: str | None = None,
    privacy_choice: str | None = None,
    entry_path: str | None = None,
    candidate_profile_path: str | None = None,
    activation_kind: str | None = None,
    reference: str | None = None,
) -> dict[str, Any]:
    if step not in ONBOARDING_STEPS:
        raise OnboardingError(f"Unknown onboarding step: {step}")
    state = load_state(path)
    if skipped and step in required_steps(state):
        raise OnboardingError(f"Required onboarding step cannot be skipped: {step}")
    if state["status"] != "in_progress":
        raise OnboardingError(f"Cannot update onboarding with status {state['status']}")
    if skipped and (
        any(
            value is not None
            for value in (
                privacy_choice,
                entry_path,
                candidate_profile_path,
                activation_kind,
                reference,
            )
        )
    ):
        raise OnboardingError("Skipped step cannot record a step result")

    if privacy_choice is not None:
        if privacy_choice not in PRIVACY_CHOICES:
            raise OnboardingError(f"Invalid privacy choice: {privacy_choice}")
        state["privacy_choice"] = privacy_choice
    if entry_path is not None:
        if entry_path not in ENTRY_PATHS:
            raise OnboardingError(f"Invalid entry path: {entry_path}")
        state["entry_path"] = entry_path
    if candidate_profile_path is not None:
        if step != "profile":
            raise OnboardingError("--candidate-profile can only be recorded for the profile step")
        normalized = candidate_profile_path.strip().replace("\\", "/")
        pack_root = path.parent.parent
        resolved = (pack_root / normalized).resolve()
        try:
            resolved.relative_to(pack_root.resolve())
        except ValueError as error:
            raise OnboardingError(
                f"CandidateProfile escapes Context Pack: {candidate_profile_path}"
            ) from error
        if not resolved.is_file():
            raise OnboardingError(f"CandidateProfile does not exist: {normalized}")
        try:
            profile = load_profile(resolved, pack_root)
        except DiscoveryError as error:
            raise OnboardingError(str(error)) from error
        missing_requirements = discovery_requirements(profile)
        if profile["discovery"]["status"] != "complete" or missing_requirements:
            details = "; ".join(missing_requirements) or "discovery status is not complete"
            raise OnboardingError(f"CandidateDiscovery is incomplete: {details}")
        state["candidate_profile_path"] = normalized

    if activation_kind is not None:
        if activation_kind not in ACTIVATION_KINDS:
            raise OnboardingError(f"Invalid activation kind: {activation_kind}")
        state["activation"]["kind"] = activation_kind
    if reference is not None:
        state["activation"]["reference"] = reference.strip() or None

    if not skipped:
        if step == "privacy" and state["privacy_choice"] is None:
            raise OnboardingError("privacy step requires --privacy-choice")
        if step == "goal" and state["entry_path"] is None:
            raise OnboardingError("goal step requires --entry-path")
        if step == "profile":
            if state["candidate_profile_path"] is None:
                raise OnboardingError("profile step requires --candidate-profile")
        if step == "first_value" and (
            state["activation"]["kind"] is None
            or state["activation"]["reference"] is None
        ):
            raise OnboardingError(
                "first_value step requires --activation-kind and --reference"
            )

    timestamp = timestamp or now_iso()
    state["steps"][step] = {
        "status": "skipped" if skipped else "completed",
        "completed_at": timestamp,
    }
    state["updated_at"] = timestamp
    state["current_step"] = next_pending_step(state)
    issues = state_issues(state)
    if issues:
        raise OnboardingError(f"Onboarding update is invalid: {'; '.join(issues)}")
    write_json(path, state)
    return state


def complete_onboarding(
    path: Path = ONBOARDING_STATE_PATH,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    state = load_state(path)
    if state["status"] != "in_progress":
        raise OnboardingError(f"Onboarding is already {state['status']}")
    pending = [
        step
        for step in ONBOARDING_STEPS
        if state["steps"][step]["status"] == "pending"
    ]
    if pending:
        raise OnboardingError(f"Onboarding still has pending steps: {', '.join(pending)}")
    incomplete = [
        step
        for step in required_steps(state)
        if state["steps"][step]["status"] != "completed"
    ]
    if incomplete:
        raise OnboardingError(
            f"Onboarding required steps are incomplete: {', '.join(sorted(incomplete))}"
        )
    timestamp = timestamp or now_iso()
    state["status"] = "completed"
    state["current_step"] = "done"
    state["updated_at"] = timestamp
    state["completed_at"] = timestamp
    issues = state_issues(state)
    if issues:
        raise OnboardingError(f"Completed onboarding is invalid: {'; '.join(issues)}")
    write_json(path, state)
    return state


def skip_onboarding(
    path: Path = ONBOARDING_STATE_PATH,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    timestamp = timestamp or now_iso()
    if path.is_file():
        state = load_state(path)
        if state["status"] == "completed":
            raise OnboardingError("Completed onboarding cannot be changed to skipped")
        if state["status"] == "skipped":
            return state
    else:
        state = new_state(timestamp)
    state["status"] = "skipped"
    state["current_step"] = "done"
    state["updated_at"] = timestamp
    state["skipped_at"] = timestamp
    issues = state_issues(state)
    if issues:
        raise OnboardingError(f"Skipped onboarding is invalid: {'; '.join(issues)}")
    write_json(path, state)
    return state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect and persist the Interview Coach onboarding lifecycle"
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show lifecycle state without changing it")
    subparsers.add_parser("start", help="Start or resume onboarding")
    subparsers.add_parser("complete", help="Complete onboarding after first value")
    subparsers.add_parser("skip", help="Skip onboarding at the user's request")

    record = subparsers.add_parser("record", help="Record one onboarding step")
    record.add_argument("step", choices=ONBOARDING_STEPS)
    record.add_argument("--skip", action="store_true")
    record.add_argument("--privacy-choice", choices=sorted(PRIVACY_CHOICES))
    record.add_argument("--entry-path", choices=sorted(ENTRY_PATHS))
    record.add_argument("--candidate-profile")
    record.add_argument("--activation-kind", choices=sorted(ACTIVATION_KINDS))
    record.add_argument("--reference")
    return parser.parse_args()


def print_state(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()
    command = args.command or "status"
    try:
        if command == "status":
            print_state(status_payload())
        elif command == "start":
            print_state(start_onboarding())
        elif command == "complete":
            print_state(complete_onboarding())
        elif command == "skip":
            print_state(skip_onboarding())
        elif command == "record":
            print_state(
                record_step(
                    args.step,
                    skipped=args.skip,
                    privacy_choice=args.privacy_choice,
                    entry_path=args.entry_path,
                    candidate_profile_path=args.candidate_profile,
                    activation_kind=args.activation_kind,
                    reference=args.reference,
                )
            )
    except OnboardingError as error:
        print(f"onboarding failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
