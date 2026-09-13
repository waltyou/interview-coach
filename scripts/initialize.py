from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from common import (
    INTERVIEW_ROOT,
    PACK_ROOT,
    QUESTION_ROOTS,
    SOURCE_CATALOG_PATH,
    clean_heading,
    load_json,
    load_questions,
    now_iso,
    question_completeness_issues,
    question_root_for_visibility,
    question_topic,
    repository_relative,
    resolve_source_list,
    slugify,
    source_reference_key,
    source_reference_location,
    without_internal_fields,
    write_json,
)
from source_readers import inspect_source


HEADING_PATTERN = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
BODY_QUESTION_PATTERN = re.compile(r"^\s*(?:Q|Question)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)
QUESTION_PREFIX = re.compile(
    r"^(为什么|为何|如何|怎么|怎样|什么是|解释|请|能否|是否|哪些|谈谈|设计|实现|如果|在什么情况下)",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize selected sources and extract explicit interview questions"
    )
    parser.add_argument(
        "--mark-extracted",
        action="append",
        default=[],
        metavar="REPO_PATH",
        help=(
            "Mark one repository-relative source as fully processed by the Agent. "
            "Repeat for multiple sources."
        ),
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def source_context_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(INTERVIEW_ROOT.resolve())
    except ValueError:
        return repository_relative(path)


def source_topics(path: Path) -> list[str]:
    relative_path = source_context_path(path)
    topic = question_topic(relative_path)
    topics = [topic]
    if relative_path.parts:
        category = slugify(relative_path.parts[0])
        if category not in topics and category not in {"2025"}:
            topics.append(category)
    return sorted(set(topics))


def source_id(relative_path: Path) -> str:
    digest = hashlib.sha256(relative_path.as_posix().encode("utf-8")).hexdigest()[:12]
    return f"source.{slugify(relative_path.stem)}.{digest}"


def previous_sources_by_repository_path(
    previous_catalog: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], bool]:
    if not previous_catalog:
        return {}, False
    root = previous_catalog.get("root")
    sources = previous_catalog.get("sources", [])
    result: dict[str, dict[str, Any]] = {}
    for source in sources:
        path = PurePosixPath(source.get("path", "")).as_posix()
        if root == "interview_notes":
            path = PurePosixPath("tech/interview", path).as_posix()
        result[path.lower()] = source
    legacy_catalog = bool(sources) and all(
        "questions_extracted_from_sha256" not in source for source in sources
    )
    return result, legacy_catalog


def build_catalog(
    markdown_files: list[Path],
    indexed_at: str,
    previous_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous_sources, legacy_catalog = previous_sources_by_repository_path(previous_catalog)
    sources: list[dict[str, Any]] = []
    for path in markdown_files:
        relative_path = repository_relative(path)
        relative_key = relative_path.as_posix().lower()
        previous = previous_sources.get(relative_key)
        raw = path.read_bytes()
        inspection = inspect_source(path, raw)
        status = inspection["status"]
        title = inspection["title"]

        modified_at = (
            datetime.fromtimestamp(path.stat().st_mtime)
            .astimezone()
            .replace(microsecond=0)
            .isoformat()
        )
        content_sha256 = hashlib.sha256(raw).hexdigest()
        extracted_sha256 = (
            previous.get("questions_extracted_from_sha256") if previous else None
        )
        if (
            legacy_catalog
            and previous
            and previous.get("content_sha256") == content_sha256
        ):
            extracted_sha256 = content_sha256

        source = {
                "id": (
                    previous.get("id", source_id(relative_path))
                    if previous
                    else source_id(relative_path)
                ),
                "path": relative_path.as_posix(),
                "title": title,
                "topics": source_topics(path),
                "visibility": "private",
                "format": inspection["format"],
                "unit_label": inspection["unit_label"],
                "content_sha256": content_sha256,
                "questions_extracted_from_sha256": extracted_sha256,
                "size_bytes": len(raw),
                "modified_at": modified_at,
                "status": status,
            }
        if inspection.get("unit_count") is not None:
            source["unit_count"] = inspection["unit_count"]
        sources.append(source)

    return {
        "$schema": "../../protocol/schemas/source-catalog.schema.json",
        "schema_version": 2,
        "generated_at": indexed_at,
        "root": "repository",
        "sources": sources,
    }


def is_explicit_question(path: Path, level: int, heading: str) -> bool:
    if "?" in heading or "？" in heading:
        return True
    if path.name == "questions-in-interviews.md" and level == 3:
        return True
    return bool(QUESTION_PREFIX.match(clean_heading(heading)))


def infer_kind(prompt: str, relative_path: Path) -> str:
    lower = prompt.lower()
    if "behavioral" in [part.lower() for part in relative_path.parts]:
        return "behavioral"
    if any(keyword in lower for keyword in ("为什么离开", "manager", "影响力", "冲突", "领导力")):
        return "behavioral"
    if any(keyword in lower for keyword in ("设计", "system design", "架构", "自动规划")):
        return "system-design"
    if any(keyword in lower for keyword in ("实现", "写代码", "sql返回", "查询", "dataframe")):
        return "coding"
    if lower.startswith(("如果", "在实际", "场景")):
        return "scenario"
    if any(keyword in lower for keyword in ("什么是", "区别", "有哪些")):
        return "concept"
    return "explanation"


def normalized_prompt(heading: str) -> str:
    prompt = clean_heading(heading)
    prompt = re.sub(r"\s*\|\s*[^|]+$", "", prompt).strip()
    if prompt and "?" not in prompt and "？" not in prompt and prompt[-1] not in "。.!！":
        prompt += "？"
    return prompt


def prompt_from_section(heading: str, section_lines: list[str]) -> str:
    """Prefer an explicit Q: paragraph when a heading is only a short label."""
    for line in section_lines:
        match = BODY_QUESTION_PATTERN.match(line)
        if match:
            return normalized_prompt(match.group(1))
    return normalized_prompt(heading)


def question_visibility(relative_path: Path, source_root: str = "interview_notes") -> str:
    """Imported material is private until a maintainer explicitly publishes it."""
    return "private"


def question_id(relative_path: Path, heading: str, topic: str) -> str:
    identity = f"{relative_path.as_posix()}\n{clean_heading(heading)}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"q.{slugify(topic)}.{digest}"


def extract_questions(path: Path, created_at: str) -> list[dict[str, Any]]:
    source_root, reference_path = source_reference_location(path)
    relative_path = source_context_path(path)
    content = read_text(path)
    lines = content.splitlines()
    current_h2: str | None = None
    extracted: list[dict[str, Any]] = []

    for line_index, line in enumerate(lines):
        line_number = line_index + 1
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        level = len(match.group(1))
        heading = match.group(2).strip()
        if level == 2:
            current_h2 = clean_heading(heading)
        if not is_explicit_question(path, level, heading):
            continue

        section_end = len(lines)
        for candidate_index in range(line_index + 1, len(lines)):
            candidate = HEADING_PATTERN.match(lines[candidate_index])
            if candidate and len(candidate.group(1)) <= level:
                section_end = candidate_index
                break
        prompt = prompt_from_section(heading, lines[line_index + 1 : section_end])
        if len(prompt) < 4 or question_completeness_issues(prompt):
            continue
        topic = question_topic(relative_path, current_h2, prompt)
        visibility = question_visibility(relative_path, source_root)
        origin = (
            "real-interview"
            if path.name == "questions-in-interviews.md" or "2025" in relative_path.parts
            else "explicit-heading"
        )
        extracted.append(
            {
                "$schema": "../../../protocol/schemas/question.schema.json",
                "schema_version": 2,
                "id": question_id(relative_path, heading, topic),
                "revision": 1,
                "status": "active",
                "visibility": visibility,
                "topic": topic,
                "kind": infer_kind(prompt, relative_path),
                "difficulty": 3,
                "target_roles": [],
                "origin": origin,
                "prompt": prompt,
                "rubric": [],
                "hints": [],
                "follow_ups": [],
                "source_refs": [
                    {
                        "root": source_root,
                        "path": reference_path.as_posix(),
                        "heading": clean_heading(heading),
                        "line": line_number,
                    }
                ],
                "evaluation_basis": "source-section",
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
    return extracted


def existing_source_map() -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for question in load_questions().values():
        for reference in question.get("source_refs", []):
            result[
                source_reference_key(
                    reference["root"],
                    reference["path"],
                    reference["heading"],
                )
            ] = question
    return result


def pending_source_paths(catalog: dict[str, Any]) -> list[str]:
    return [
        source["path"]
        for source in catalog["sources"]
        if source["status"] == "ready"
        and source.get("questions_extracted_from_sha256") != source["content_sha256"]
    ]


def normalized_repository_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in pure.parts
    ):
        raise ValueError(f"--mark-extracted requires a repository-relative path: {value}")
    return pure.as_posix()


def mark_sources_extracted(
    catalog: dict[str, Any],
    requested_paths: list[str],
) -> list[str]:
    if not requested_paths:
        return []
    sources = {source["path"].lower(): source for source in catalog["sources"]}
    marked: list[str] = []
    for value in requested_paths:
        path = normalized_repository_path(value)
        source = sources.get(path.lower())
        if source is None:
            raise ValueError(f"Cannot mark an unselected Source as extracted: {path}")
        if source["status"] != "ready":
            raise ValueError(f"Cannot mark a non-ready Source as extracted: {path}")
        source["questions_extracted_from_sha256"] = source["content_sha256"]
        marked.append(source["path"])
    return marked


def write_question_indexes(indexed_at: str) -> None:
    questions = load_questions()
    for root, visibility in QUESTION_ROOTS:
        matching = [
            question
            for question in questions.values()
            if question.get("visibility") == visibility
        ]
        index = {
            "schema_version": 2,
            "generated_at": indexed_at,
            "visibility": visibility,
            "questions": [
                {
                    "id": question["id"],
                    "status": question["status"],
                    "visibility": question["visibility"],
                    "topic": question["topic"],
                    "kind": question["kind"],
                    "prompt": question["prompt"],
                    "file": question["_path"].relative_to(root).as_posix(),
                }
                for question in sorted(matching, key=lambda item: item["id"])
            ],
        }
        write_json(root / "index.json", index)


def main() -> None:
    args = parse_args()
    indexed_at = now_iso()
    markdown_files, source_list_warnings = resolve_source_list()
    previous_catalog = (
        load_json(SOURCE_CATALOG_PATH) if SOURCE_CATALOG_PATH.is_file() else None
    )
    catalog = build_catalog(markdown_files, indexed_at, previous_catalog)
    pending_before = set(pending_source_paths(catalog))
    write_json(SOURCE_CATALOG_PATH, catalog)

    known_sources = existing_source_map()
    created = 0
    preserved = 0
    for path in markdown_files:
        if repository_relative(path).as_posix() not in pending_before:
            continue
        if path.suffix.lower() != ".md":
            continue
        try:
            questions = extract_questions(path, indexed_at)
        except UnicodeDecodeError:
            continue
        for question in questions:
            reference = question["source_refs"][0]
            key = source_reference_key(
                reference["root"],
                reference["path"],
                reference["heading"],
            )
            if key in known_sources:
                preserved += 1
                continue
            output_root = question_root_for_visibility(question["visibility"])
            output_path = output_root / question["topic"] / f"{question['id']}.json"
            write_json(output_path, without_internal_fields(question))
            known_sources[key] = question
            created += 1

    marked = mark_sources_extracted(catalog, args.mark_extracted)
    if marked:
        write_json(SOURCE_CATALOG_PATH, catalog)
    write_question_indexes(indexed_at)
    from build_dashboard import build_dashboard

    dashboard_path, _ = build_dashboard()
    pending_after = pending_source_paths(catalog)
    print(
        f"sources={len(markdown_files)} questions_created={created} "
        f"questions_preserved={preserved} "
        f"pending_extraction={len(pending_after)} marked_extracted={len(marked)} "
        f"dashboard={dashboard_path.relative_to(PACK_ROOT).as_posix()}"
    )
    for warning in source_list_warnings:
        print(f"warning={warning}")
    for path in pending_after:
        print(f"pending_source={path}")


if __name__ == "__main__":
    main()
