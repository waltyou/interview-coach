from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import PACK_ROOT, REPO_ROOT, load_json, now_iso, write_json


PROFILE_PATH = PACK_ROOT / "workspace" / "profile" / "candidate.json"
DISCOVERY_METHODS = {
    "conversation", "resume", "files", "practice_history", "interview_history"
}
MATERIAL_KINDS = {
    "resume", "private_question_bank", "knowledge_notes", "job_description",
    "interview_feedback", "project_material", "interview_experience", "other",
}
MATERIAL_STATUSES = {"available", "indexed", "reviewed"}
COACHING_STYLES = {"supportive", "balanced", "challenging"}


class DiscoveryError(RuntimeError):
    pass


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def new_profile(timestamp: str | None = None, learner_id: str = "me") -> dict[str, Any]:
    timestamp = timestamp or now_iso()
    return {
        "$schema": "../../protocol/schemas/candidate-profile.schema.json",
        "schema_version": 1,
        "learner_id": learner_id,
        "revision": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
        "last_confirmed_at": None,
        "discovery": {
            "status": "in_progress", "methods_used": [],
            "started_at": timestamp, "completed_at": None,
        },
        "goals": {
            "target_roles": [], "target_levels": [], "target_companies": [],
            "target_date": None, "motivations": [], "constraints": [],
        },
        "background": {
            "summary": None, "years_experience": None, "domains": [],
            "technologies": [], "leadership_scope": None,
        },
        "preferences": {
            "coaching_language": None, "answer_languages": [],
            "session_minutes": None, "coaching_style": None,
        },
        "materials": [],
        "open_questions": [],
    }


def profile_issues(profile: dict[str, Any], pack_root: Path = PACK_ROOT) -> list[str]:
    issues: list[str] = []
    required = {
        "schema_version", "learner_id", "revision", "created_at", "updated_at",
        "last_confirmed_at", "discovery", "goals", "background", "preferences",
        "materials", "open_questions",
    }
    missing = sorted(required - profile.keys())
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    if profile["schema_version"] != 1:
        issues.append(f"unsupported schema_version: {profile['schema_version']}")
    if not isinstance(profile["learner_id"], str) or not profile["learner_id"].strip():
        issues.append("learner_id must be a non-empty string")
    if not isinstance(profile["revision"], int) or profile["revision"] < 1:
        issues.append("revision must be a positive integer")

    discovery = profile.get("discovery")
    if not isinstance(discovery, dict):
        issues.append("discovery must be an object")
    else:
        if discovery.get("status") not in {"in_progress", "complete", "paused"}:
            issues.append("discovery.status is invalid")
        methods = discovery.get("methods_used")
        if not isinstance(methods, list) or any(item not in DISCOVERY_METHODS for item in methods):
            issues.append("discovery.methods_used is invalid")
        elif len(methods) != len(set(methods)):
            issues.append("discovery.methods_used contains duplicates")

    expected_groups = {
        "goals": {"target_roles", "target_levels", "target_companies", "target_date", "motivations", "constraints"},
        "background": {"summary", "years_experience", "domains", "technologies", "leadership_scope"},
        "preferences": {"coaching_language", "answer_languages", "session_minutes", "coaching_style"},
    }
    for group_name, fields in expected_groups.items():
        group = profile.get(group_name)
        if not isinstance(group, dict):
            issues.append(f"{group_name} must be an object")
        elif fields - group.keys():
            issues.append(f"{group_name} is missing: {', '.join(sorted(fields - group.keys()))}")

    arrays = (
        ("goals.target_roles", profile.get("goals", {}).get("target_roles")),
        ("goals.target_levels", profile.get("goals", {}).get("target_levels")),
        ("goals.target_companies", profile.get("goals", {}).get("target_companies")),
        ("goals.motivations", profile.get("goals", {}).get("motivations")),
        ("goals.constraints", profile.get("goals", {}).get("constraints")),
        ("background.domains", profile.get("background", {}).get("domains")),
        ("background.technologies", profile.get("background", {}).get("technologies")),
        ("preferences.answer_languages", profile.get("preferences", {}).get("answer_languages")),
        ("open_questions", profile.get("open_questions")),
    )
    for name, values in arrays:
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            issues.append(f"{name} must be a non-empty string array")
        elif len(values) != len(set(values)):
            issues.append(f"{name} contains duplicates")

    materials = profile.get("materials")
    if not isinstance(materials, list):
        issues.append("materials must be an array")
    else:
        seen_paths: set[tuple[str, str]] = set()
        for index, material in enumerate(materials):
            if not isinstance(material, dict):
                issues.append(f"materials[{index}] must be an object")
                continue
            if material.get("kind") not in MATERIAL_KINDS:
                issues.append(f"materials[{index}].kind is invalid")
            root_name = material.get("root")
            if root_name not in {"context_pack", "repository"}:
                issues.append(f"materials[{index}].root is invalid")
            if material.get("status") not in MATERIAL_STATUSES:
                issues.append(f"materials[{index}].status is invalid")
            path = material.get("path")
            if not isinstance(path, str) or not path.strip():
                issues.append(f"materials[{index}].path is invalid")
            elif (root_name, path) in seen_paths:
                issues.append(f"duplicate material path: {root_name}:{path}")
            else:
                seen_paths.add((root_name, path))
                base = pack_root if root_name == "context_pack" else (
                    REPO_ROOT if pack_root == PACK_ROOT else pack_root
                )
                try:
                    (base / path).resolve().relative_to(base.resolve())
                except ValueError:
                    issues.append(f"material escapes {root_name}: {path}")
    return issues


def load_profile(path: Path = PROFILE_PATH, pack_root: Path = PACK_ROOT) -> dict[str, Any]:
    if not path.is_file():
        raise DiscoveryError(f"CandidateProfile does not exist: {path}")
    try:
        profile = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        raise DiscoveryError(f"Invalid CandidateProfile: {error}") from error
    issues = profile_issues(profile, pack_root)
    if issues:
        raise DiscoveryError(f"Invalid CandidateProfile: {'; '.join(issues)}")
    return profile


def discovery_requirements(profile: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not profile["discovery"]["methods_used"]:
        missing.append("use at least one discovery method")
    if not profile["background"]["summary"] and not profile["materials"]:
        missing.append("add a background summary or material")
    goals = profile["goals"]
    if not (goals["target_roles"] or goals["motivations"] or profile["open_questions"]):
        missing.append("record a current goal, motivation, or open question")
    return missing


def status_payload(path: Path = PROFILE_PATH, pack_root: Path = PACK_ROOT) -> dict[str, Any]:
    if not path.is_file():
        return {
            "status": "missing", "profile_path": path.relative_to(pack_root).as_posix(),
            "recommended_action": "start_candidate_discovery",
        }
    profile = load_profile(path, pack_root)
    missing = discovery_requirements(profile)
    return {
        "status": profile["discovery"]["status"],
        "profile_path": path.relative_to(pack_root).as_posix(),
        "revision": profile["revision"],
        "methods_used": profile["discovery"]["methods_used"],
        "materials_count": len(profile["materials"]),
        "requirements_missing": missing,
        "recommended_action": "normal_coaching" if profile["discovery"]["status"] == "complete" else "continue_candidate_discovery",
    }


def start_profile(path: Path = PROFILE_PATH, *, timestamp: str | None = None, learner_id: str = "me") -> dict[str, Any]:
    if path.is_file():
        return load_profile(path, path.parents[2])
    profile = new_profile(timestamp, learner_id)
    write_json(path, profile)
    return profile


def update_profile(
    *, path: Path = PROFILE_PATH, timestamp: str | None = None,
    confirmed_by_user: bool = False, method: str | None = None,
    background_summary: str | None = None, years_experience: float | None = None,
    target_roles: list[str] | None = None, target_levels: list[str] | None = None,
    target_companies: list[str] | None = None, target_date: str | None = None,
    motivations: list[str] | None = None, constraints: list[str] | None = None,
    domains: list[str] | None = None, technologies: list[str] | None = None,
    leadership_scope: str | None = None, coaching_language: str | None = None,
    answer_languages: list[str] | None = None, session_minutes: int | None = None,
    coaching_style: str | None = None, open_questions: list[str] | None = None,
) -> dict[str, Any]:
    if not confirmed_by_user:
        raise DiscoveryError("CandidateProfile facts require explicit user confirmation")
    profile = load_profile(path, path.parents[2])
    if method:
        if method not in DISCOVERY_METHODS:
            raise DiscoveryError(f"Invalid discovery method: {method}")
        profile["discovery"]["methods_used"] = unique([*profile["discovery"]["methods_used"], method])
    mappings = (
        ("goals", "target_roles", target_roles), ("goals", "target_levels", target_levels),
        ("goals", "target_companies", target_companies), ("goals", "motivations", motivations),
        ("goals", "constraints", constraints), ("background", "domains", domains),
        ("background", "technologies", technologies),
        ("preferences", "answer_languages", answer_languages),
    )
    for group, field, additions in mappings:
        if additions:
            profile[group][field] = unique([*profile[group][field], *additions])
    if open_questions:
        profile["open_questions"] = unique([*profile["open_questions"], *open_questions])
    scalar_values = (
        ("background", "summary", background_summary),
        ("background", "years_experience", years_experience),
        ("background", "leadership_scope", leadership_scope),
        ("goals", "target_date", target_date),
        ("preferences", "coaching_language", coaching_language),
        ("preferences", "session_minutes", session_minutes),
        ("preferences", "coaching_style", coaching_style),
    )
    if coaching_style and coaching_style not in COACHING_STYLES:
        raise DiscoveryError(f"Invalid coaching style: {coaching_style}")
    for group, field, value in scalar_values:
        if value is not None:
            profile[group][field] = value.strip() if isinstance(value, str) else value
    timestamp = timestamp or now_iso()
    profile["revision"] += 1
    profile["updated_at"] = timestamp
    profile["last_confirmed_at"] = timestamp
    issues = profile_issues(profile, path.parents[2])
    if issues:
        raise DiscoveryError(f"CandidateProfile update is invalid: {'; '.join(issues)}")
    write_json(path, profile)
    return profile


def add_material(
    *, kind: str, material_path: str, path: Path = PROFILE_PATH,
    status: str = "available", notes: str | None = None,
    root_name: str = "context_pack", pack_root: Path = PACK_ROOT,
    repository_root: Path = REPO_ROOT, timestamp: str | None = None,
) -> dict[str, Any]:
    if kind not in MATERIAL_KINDS:
        raise DiscoveryError(f"Invalid material kind: {kind}")
    if status not in MATERIAL_STATUSES:
        raise DiscoveryError(f"Invalid material status: {status}")
    if root_name not in {"context_pack", "repository"}:
        raise DiscoveryError(f"Invalid material root: {root_name}")
    base = pack_root if root_name == "context_pack" else repository_root
    resolved = (base / material_path).resolve()
    try:
        relative = resolved.relative_to(base.resolve()).as_posix()
    except ValueError as error:
        raise DiscoveryError(f"Material escapes {root_name}: {material_path}") from error
    if not resolved.is_file():
        raise DiscoveryError(f"Material does not exist: {relative}")
    profile = load_profile(path, pack_root)
    timestamp = timestamp or now_iso()
    item = {"kind": kind, "root": root_name, "path": relative, "status": status, "added_at": timestamp, "notes": notes}
    existing = next((entry for entry in profile["materials"] if entry["root"] == root_name and entry["path"] == relative), None)
    if existing:
        existing.update(item)
    else:
        profile["materials"].append(item)
    method = "resume" if kind == "resume" else "files"
    profile["discovery"]["methods_used"] = unique([*profile["discovery"]["methods_used"], method])
    profile["revision"] += 1
    profile["updated_at"] = timestamp
    write_json(path, profile)
    return profile


def complete_discovery(path: Path = PROFILE_PATH, *, confirmed_by_user: bool = False, timestamp: str | None = None) -> dict[str, Any]:
    if not confirmed_by_user:
        raise DiscoveryError("Completing discovery requires the user's confirmation of the profile summary")
    profile = load_profile(path, path.parents[2])
    missing = discovery_requirements(profile)
    if missing:
        raise DiscoveryError(f"CandidateDiscovery is incomplete: {'; '.join(missing)}")
    timestamp = timestamp or now_iso()
    profile["discovery"]["status"] = "complete"
    profile["discovery"]["completed_at"] = timestamp
    profile["revision"] += 1
    profile["updated_at"] = timestamp
    profile["last_confirmed_at"] = timestamp
    write_json(path, profile)
    return profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain the confirmed CandidateProfile")
    subs = parser.add_subparsers(dest="command")
    subs.add_parser("status")
    start = subs.add_parser("start")
    start.add_argument("--learner", default="me")
    update = subs.add_parser("update")
    update.add_argument("--method", choices=sorted(DISCOVERY_METHODS))
    update.add_argument("--background-summary")
    update.add_argument("--years-experience", type=float)
    for flag in ("target-role", "target-level", "target-company", "motivation", "constraint", "domain", "technology", "answer-language", "open-question"):
        update.add_argument(f"--{flag}", action="append", default=[])
    update.add_argument("--target-date")
    update.add_argument("--leadership-scope")
    update.add_argument("--coaching-language")
    update.add_argument("--session-minutes", type=int)
    update.add_argument("--coaching-style", choices=sorted(COACHING_STYLES))
    update.add_argument("--confirmed-by-user", action="store_true")
    material = subs.add_parser("add-material")
    material.add_argument("--kind", required=True, choices=sorted(MATERIAL_KINDS))
    material.add_argument("--path", required=True)
    material.add_argument("--root", dest="root_name", choices=["context_pack", "repository"], default="context_pack")
    material.add_argument("--status", choices=sorted(MATERIAL_STATUSES), default="available")
    material.add_argument("--notes")
    complete = subs.add_parser("complete")
    complete.add_argument("--confirmed-by-user", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        command = args.command or "status"
        if command == "status":
            value = status_payload()
        elif command == "start":
            value = start_profile(learner_id=args.learner)
        elif command == "update":
            value = update_profile(
                confirmed_by_user=args.confirmed_by_user, method=args.method,
                background_summary=args.background_summary, years_experience=args.years_experience,
                target_roles=args.target_role, target_levels=args.target_level,
                target_companies=args.target_company, target_date=args.target_date,
                motivations=args.motivation, constraints=args.constraint, domains=args.domain,
                technologies=args.technology, leadership_scope=args.leadership_scope,
                coaching_language=args.coaching_language, answer_languages=args.answer_language,
                session_minutes=args.session_minutes, coaching_style=args.coaching_style,
                open_questions=args.open_question,
            )
        elif command == "add-material":
            value = add_material(kind=args.kind, material_path=args.path, root_name=args.root_name, status=args.status, notes=args.notes)
        else:
            value = complete_discovery(confirmed_by_user=args.confirmed_by_user)
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except DiscoveryError as error:
        print(f"candidate discovery failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
