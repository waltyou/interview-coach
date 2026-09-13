from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import PACK_ROOT, iter_json_files, load_json, now_iso, slugify, write_json
from discover import PROFILE_PATH, load_profile


OBSERVATION_ROOT = PACK_ROOT / "workspace" / "profile" / "observations"
COACH_MODEL_PATH = PACK_ROOT / "workspace" / "state" / "coach-model.json"
DIMENSIONS = {
    "technical", "problem_solving", "system_design", "communication", "behavioral",
    "leadership", "domain", "career_narrative", "interview_strategy", "work_style",
}
SIGNALS = {"strength", "gap", "risk", "neutral"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
EVIDENCE_KINDS = {
    "conversation", "candidate_profile", "resume", "source", "attempt_event",
    "interview_experience", "job", "user_feedback",
}


class CoachModelError(RuntimeError):
    pass


def observation_issues(observation: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required = {
        "schema_version", "id", "occurred_at", "learner_id", "dimension", "subject",
        "signal", "claim", "confidence", "evidence_refs", "supersedes", "observer",
    }
    missing = sorted(required - observation.keys())
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    if observation["schema_version"] != 1:
        issues.append(f"unsupported schema_version: {observation['schema_version']}")
    if not isinstance(observation["id"], str) or not observation["id"].startswith("observation."):
        issues.append("id must start with observation.")
    if observation["dimension"] not in DIMENSIONS:
        issues.append(f"invalid dimension: {observation['dimension']}")
    if observation["signal"] not in SIGNALS:
        issues.append(f"invalid signal: {observation['signal']}")
    if observation["confidence"] not in CONFIDENCE_LEVELS:
        issues.append(f"invalid confidence: {observation['confidence']}")
    for field in ("occurred_at", "learner_id", "subject", "claim"):
        if not isinstance(observation[field], str) or not observation[field].strip():
            issues.append(f"{field} must be a non-empty string")
    evidence = observation["evidence_refs"]
    if not isinstance(evidence, list) or not evidence:
        issues.append("evidence_refs must contain at least one item")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict) or item.get("kind") not in EVIDENCE_KINDS or not isinstance(item.get("reference"), str) or not item["reference"].strip():
                issues.append(f"evidence_refs[{index}] is invalid")
    supersedes = observation["supersedes"]
    if not isinstance(supersedes, list) or any(not isinstance(item, str) or not item.startswith("observation.") for item in supersedes):
        issues.append("supersedes must be an observation ID array")
    observer = observation["observer"]
    if not isinstance(observer, dict) or not isinstance(observer.get("agent"), str) or not observer["agent"].strip():
        issues.append("observer.agent must be a non-empty string")
    return issues


def load_observations(root: Path = OBSERVATION_ROOT) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in iter_json_files(root):
        try:
            observation = load_json(path)
        except (OSError, json.JSONDecodeError) as error:
            raise CoachModelError(f"Invalid observation file {path}: {error}") from error
        issues = observation_issues(observation)
        if issues:
            raise CoachModelError(f"Invalid observation {path}: {'; '.join(issues)}")
        if observation["id"] in seen:
            raise CoachModelError(f"Duplicate observation ID: {observation['id']}")
        observation["_path"] = path
        observations.append(observation)
        seen.add(observation["id"])
    return sorted(observations, key=lambda item: (item["occurred_at"], item["id"]))


def active_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = {
        observation_id
        for observation in observations
        for observation_id in observation.get("supersedes", [])
    }
    return [item for item in observations if item["id"] not in superseded]


def build_coach_model(
    observations: list[dict[str, Any]], profile: dict[str, Any] | None = None,
    *, generated_at: str | None = None, learner_id: str = "me",
) -> dict[str, Any]:
    active = active_observations(observations)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for observation in active:
        grouped[(observation["dimension"], observation["subject"])].append(observation)
    subjects: list[dict[str, Any]] = []
    top_level = {"strength": [], "gap": [], "risk": []}
    for (dimension, subject), items in sorted(grouped.items()):
        signals = {item["signal"] for item in items if item["signal"] != "neutral"}
        classification = next(iter(signals)) if len(signals) == 1 else ("mixed" if signals else "unclassified")
        evidence_map = {
            (ref["kind"], ref["reference"]): {"kind": ref["kind"], "reference": ref["reference"]}
            for item in items for ref in item["evidence_refs"]
        }
        evidence_count = len(evidence_map)
        evidence_level = "well_supported" if evidence_count >= 3 else ("supported" if evidence_count >= 2 else "emerging")
        subject_key = f"{dimension}:{subject}"
        if classification in top_level and evidence_level != "emerging":
            top_level[classification].append(subject_key)
        subjects.append({
            "dimension": dimension,
            "subject": subject,
            "classification": classification,
            "evidence_level": evidence_level,
            "observation_count": len(items),
            "last_observed_at": max(item["occurred_at"] for item in items),
            "claims": [
                {"observation_id": item["id"], "signal": item["signal"], "confidence": item["confidence"], "claim": item["claim"]}
                for item in items
            ],
            "observation_ids": [item["id"] for item in items],
            "evidence_refs": list(evidence_map.values()),
        })
    return {
        "$schema": "../../protocol/schemas/coach-model.schema.json",
        "schema_version": 1,
        "learner_id": profile["learner_id"] if profile else learner_id,
        "generated_at": generated_at or now_iso(),
        "candidate_profile_revision": profile["revision"] if profile else None,
        "subjects": subjects,
        "strengths": top_level["strength"],
        "gaps": top_level["gap"],
        "risks": top_level["risk"],
        "derived_from_observations": [item["id"] for item in active],
    }


def model_issues(model: dict[str, Any]) -> list[str]:
    required = {
        "schema_version", "learner_id", "generated_at", "candidate_profile_revision",
        "subjects", "strengths", "gaps", "risks", "derived_from_observations",
    }
    missing = sorted(required - model.keys())
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    issues: list[str] = []
    if model["schema_version"] != 1:
        issues.append(f"unsupported schema_version: {model['schema_version']}")
    if not isinstance(model["subjects"], list):
        issues.append("subjects must be an array")
    for field in ("strengths", "gaps", "risks", "derived_from_observations"):
        values = model[field]
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            issues.append(f"{field} must be a non-empty string array")
        elif len(values) != len(set(values)):
            issues.append(f"{field} contains duplicates")
    return issues


def rebuild_model(
    *, observation_root: Path = OBSERVATION_ROOT, model_path: Path = COACH_MODEL_PATH,
    profile_path: Path = PROFILE_PATH, generated_at: str | None = None,
) -> dict[str, Any]:
    observations = load_observations(observation_root)
    profile = load_profile(profile_path, profile_path.parents[2]) if profile_path.is_file() else None
    model = build_coach_model(observations, profile, generated_at=generated_at)
    write_json(model_path, model)
    return model


def status_payload(
    *, observation_root: Path = OBSERVATION_ROOT, model_path: Path = COACH_MODEL_PATH,
    profile_path: Path = PROFILE_PATH,
) -> dict[str, Any]:
    observations = load_observations(observation_root)
    active_ids = [item["id"] for item in active_observations(observations)]
    profile_revision = load_profile(profile_path, profile_path.parents[2])["revision"] if profile_path.is_file() else None
    state = "missing"
    issues: list[str] = []
    if model_path.is_file():
        try:
            model = load_json(model_path)
        except (OSError, json.JSONDecodeError) as error:
            raise CoachModelError(f"Invalid CoachModel: {error}") from error
        issues.extend(model_issues(model))
        if model.get("derived_from_observations") != active_ids:
            issues.append("observation projection is stale")
        if model.get("candidate_profile_revision") != profile_revision:
            issues.append("candidate profile revision is stale")
        state = "stale" if issues else "ready"
    return {
        "status": state,
        "observations": len(observations),
        "active_observations": len(active_ids),
        "model_exists": model_path.is_file(),
        "issues": issues,
        "recommended_action": "rebuild_model" if state != "ready" and (observations or profile_revision is not None) else "normal_coaching",
    }


def next_observation_path(root: Path, observation_id: str, timestamp: str) -> tuple[str, Path]:
    folder = root / timestamp[:4] / timestamp[5:7]
    candidate_id = observation_id
    suffix = 2
    while (folder / f"{candidate_id}.json").exists():
        candidate_id = f"{observation_id}-{suffix}"
        suffix += 1
    return candidate_id, folder / f"{candidate_id}.json"


def record_observation(
    *, dimension: str, subject: str, signal: str, claim: str,
    evidence_refs: list[dict[str, str]], confidence: str = "medium",
    supersedes: list[str] | None = None, agent: str = "interview-coach",
    model_name: str | None = None, learner_id: str = "me",
    observation_root: Path = OBSERVATION_ROOT, model_path: Path = COACH_MODEL_PATH,
    profile_path: Path = PROFILE_PATH, timestamp: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    timestamp = timestamp or now_iso()
    compact = timestamp.replace("-", "").replace(":", "").replace("+", "p")
    base_id = f"observation.{compact}.{slugify(subject)}"
    observation_id, path = next_observation_path(observation_root, base_id, timestamp)
    observation = {
        "$schema": "../../../../../protocol/schemas/coach-observation.schema.json",
        "schema_version": 1, "id": observation_id, "occurred_at": timestamp,
        "learner_id": learner_id, "dimension": dimension, "subject": subject.strip(),
        "signal": signal, "claim": claim.strip(), "confidence": confidence,
        "evidence_refs": evidence_refs, "supersedes": supersedes or [],
        "observer": {"agent": agent, "model": model_name},
    }
    issues = observation_issues(observation)
    if issues:
        raise CoachModelError(f"Observation is invalid: {'; '.join(issues)}")
    write_json(path, observation)
    coach_model = rebuild_model(
        observation_root=observation_root, model_path=model_path,
        profile_path=profile_path, generated_at=timestamp,
    )
    return observation, coach_model


def parse_evidence(value: str) -> dict[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("evidence must use kind=reference")
    kind, reference = value.split("=", 1)
    if kind not in EVIDENCE_KINDS or not reference.strip():
        raise argparse.ArgumentTypeError("evidence kind or reference is invalid")
    return {"kind": kind, "reference": reference.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record observations and rebuild CoachModel")
    subs = parser.add_subparsers(dest="command")
    subs.add_parser("status")
    subs.add_parser("rebuild")
    observe = subs.add_parser("observe")
    observe.add_argument("--dimension", required=True, choices=sorted(DIMENSIONS))
    observe.add_argument("--subject", required=True)
    observe.add_argument("--signal", required=True, choices=sorted(SIGNALS))
    observe.add_argument("--claim", required=True)
    observe.add_argument("--confidence", choices=sorted(CONFIDENCE_LEVELS), default="medium")
    observe.add_argument("--evidence", action="append", required=True, type=parse_evidence)
    observe.add_argument("--supersedes", action="append", default=[])
    observe.add_argument("--agent", default="interview-coach")
    observe.add_argument("--model")
    observe.add_argument("--learner", default="me")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        command = args.command or "status"
        if command == "status":
            value = status_payload()
        elif command == "rebuild":
            value = rebuild_model()
        else:
            observation, model = record_observation(
                dimension=args.dimension, subject=args.subject, signal=args.signal,
                claim=args.claim, confidence=args.confidence, evidence_refs=args.evidence,
                supersedes=args.supersedes, agent=args.agent, model_name=args.model,
                learner_id=args.learner,
            )
            value = {"observation": observation, "coach_model": model}
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except CoachModelError as error:
        print(f"coach model failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
