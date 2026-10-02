from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable

from source_readers import SUPPORTED_SOURCE_FORMATS


PACK_ROOT = Path(__file__).resolve().parents[1]


def configured_source_root(name: str, fallback: Path) -> Path:
    """Resolve a Source root in both embedded and standalone Context Packs."""
    manifest_path = PACK_ROOT / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        relative_path = manifest.get("source_roots", {}).get(name)
        if isinstance(relative_path, str) and relative_path.strip():
            return (PACK_ROOT / relative_path).resolve()
    except (OSError, json.JSONDecodeError):
        pass
    return fallback.resolve()


REPO_ROOT = configured_source_root("repository", PACK_ROOT.parent.parent)
INTERVIEW_ROOT = configured_source_root("interview_notes", PACK_ROOT.parent / "interview")
PUBLIC_QUESTION_ROOT = PACK_ROOT / "library" / "questions"
PRIVATE_QUESTION_ROOT = PACK_ROOT / "workspace" / "questions"
JOB_ROOT = PACK_ROOT / "workspace" / "jobs"
QUESTION_ROOTS = (
    (PUBLIC_QUESTION_ROOT, "public"),
    (PRIVATE_QUESTION_ROOT, "private"),
)
SOURCE_CATALOG_PATH = PACK_ROOT / "library" / "sources" / "catalog.json"
SOURCE_LIST_PATH = PACK_ROOT / "source-list.txt"
CYCLE_ROOT = PACK_ROOT / "workspace" / "cycles"
EVENT_ROOT = PACK_ROOT / "workspace" / "events"
STATE_ROOT = PACK_ROOT / "workspace" / "state"
CYCLE_REPORT_ROOT = PACK_ROOT / "workspace" / "reports" / "cycles"
DASHBOARD_ROOT = PACK_ROOT / "dashboard"

SCORE_FIELDS = ("recall", "correctness", "depth", "communication")
REVIEW_INTERVAL_DAYS = {0: 1, 1: 2, 2: 4, 3: 10, 4: 30}

QUESTION_INTENT_PATTERN = re.compile(
    r"(为什么|为何|如何|怎么|怎样|什么是|是什么|解释|请|能否|是否|哪些|哪种|"
    r"谈谈|讲述|什么|哪里|设计|实现|如果|在什么情况下|区别|对比|比较|阐述|分析|返回|统计|输出|\bvs\.?\b|"
    r"\b(?:how|what|why|when|which|describe|explain|implement|design|could|would|calculate)\b)",
    re.IGNORECASE,
)
DANGLING_REFERENCE_PATTERN = re.compile(
    r"^(?:(?:请|你|能否|说明|解释|阐述|谈谈|分析|回答|如何|怎么|怎样|为什么|为何|"
    r"训练|应用|使用|掌握)\s*){0,8}"
    r"(?:这种|这个|上述|前述|该种?|此)"
    r"(?:思维|方法|方案|做法|问题|技术|机制|过程|系统|设计|架构|能力|内容|概念)",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def iter_json_files(root: Path, *, exclude_names: Iterable[str] = ()) -> list[Path]:
    excluded = set(exclude_names)
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.json")
        if path.name not in excluded and not path.name.endswith(".tmp")
    )


def load_questions() -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    for root, storage_visibility in QUESTION_ROOTS:
        for path in iter_json_files(root, exclude_names={"index.json"}):
            question = load_json(path)
            question_id = question["id"]
            if question_id in questions:
                raise ValueError(f"Duplicate Question id across question roots: {question_id}")
            question["_path"] = path
            question["_storage_visibility"] = storage_visibility
            questions[question_id] = question
    return questions


def question_root_for_visibility(visibility: str) -> Path:
    if visibility == "public":
        return PUBLIC_QUESTION_ROOT
    if visibility == "private":
        return PRIVATE_QUESTION_ROOT
    raise ValueError(f"Unsupported Question visibility: {visibility}")


def load_cycles() -> dict[str, dict[str, Any]]:
    cycles: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(CYCLE_ROOT):
        cycle = load_json(path)
        cycle["_path"] = path
        cycles[cycle["id"]] = cycle
    return cycles


def load_jobs() -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(JOB_ROOT):
        job = load_json(path)
        job_id = job["id"]
        if job_id in jobs:
            raise ValueError(f"Duplicate Job id: {job_id}")
        job["_path"] = path
        jobs[job_id] = job
    return jobs


def load_events(*, raw: bool = False) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in iter_json_files(EVENT_ROOT):
        event = load_json(path)
        event["_path"] = path
        events.append(event)
    events = sorted(events, key=lambda event: (event.get("occurred_at", ""), event.get("id", "")))
    return events if raw else effective_attempts(events)


def effective_attempts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply evaluation changes without manufacturing a new answer or attempt date."""
    from copy import deepcopy

    by_id = {}
    for event in events:
        if event["id"] in by_id:
            raise ValueError(f"Duplicate Event id: {event['id']}")
        by_id[event["id"]] = event
    originals = {e["id"]: deepcopy(e) for e in events if e.get("type", "attempt.recorded") == "attempt.recorded"}
    owners = {event_id: event_id for event_id in originals}
    heads = dict(owners)
    pending = [e for e in events if e.get("type") == "attempt.reevaluated"]
    for event in events:
        if event.get("type", "attempt.recorded") not in {"attempt.recorded", "attempt.reevaluated"}:
            raise ValueError(f"Unsupported Event type: {event.get('type')}")
    while pending:
        ready = [e for e in pending if e.get("supersedes") in owners]
        if not ready:
            raise ValueError("Evaluation correction has an unknown or cyclic supersedes reference")
        for correction in ready:
            target = correction["supersedes"]
            owner = owners[target]
            if heads[owner] != target:
                raise ValueError("Evaluation correction must supersede the latest evaluation")
            original = originals[owner]
            for field in ("occurred_at", "learner_id", "cycle_id", "practice_session_id", "question_id",
                          "question_revision", "answer", "hints_used", "assistance"):
                if correction.get(field) != original.get(field):
                    raise ValueError(f"Evaluation correction changed answer fact: {field}")
            previous = by_id[target]
            if parse_datetime(correction["corrected_at"]) < parse_datetime(previous.get("corrected_at", previous["occurred_at"])):
                raise ValueError("Evaluation correction predates its target")
            if not correction.get("correction_reason", "").strip():
                raise ValueError("Evaluation correction requires a reason")
            original.setdefault("evaluation_history", []).append({"event_id": target, "evaluation": deepcopy(original["evaluation"])})
            original["evaluation"] = deepcopy(correction["evaluation"])
            original["evaluation_event_id"] = correction["id"]
            heads[owner] = correction["id"]
            owners[correction["id"]] = owner
            pending.remove(correction)
    return sorted(originals.values(), key=lambda e: (e["occurred_at"], e["id"]))


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def knowledge_score(scores: dict[str, int]) -> int:
    """Return the conservative score used by the review scheduler."""
    return min(scores["recall"], scores["correctness"], scores["depth"])


def practice_budget(*, session: dict | None = None, profile: dict | None = None, default: int = 15) -> int:
    candidates = [(session or {}).get("time_budget_minutes"),
                  (profile or {}).get("preferences", {}).get("session_minutes"), default]
    return next(value for value in candidates if type(value) is int and value > 0)


def slugify(value: str, fallback: str = "general") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or fallback


def clean_heading(value: str) -> str:
    heading = re.sub(r"^#{1,6}\s+", "", value).strip()
    heading = re.sub(r"^\d+(?:\.\d+)*[.、]?\s+", "", heading)
    heading = re.sub(r"^[一二三四五六七八九十]+[、.]\s*", "", heading)
    return heading.strip()


def question_completeness_issues(prompt: str) -> list[str]:
    """Return reasons why a prompt cannot stand alone outside its source document."""
    normalized = " ".join(prompt.split()).strip()
    if not normalized:
        return ["prompt is empty"]

    issues: list[str] = []
    if DANGLING_REFERENCE_PATTERN.search(normalized):
        issues.append("prompt contains a dangling reference without its source context")
    if not QUESTION_INTENT_PATTERN.search(normalized):
        issues.append("prompt looks like a section label rather than an answerable question")
    return issues


def source_key(path: str, heading: str) -> tuple[str, str]:
    return (Path(path).as_posix().lower(), clean_heading(heading).lower())


def repository_relative(path: Path, *, repo_root: Path = REPO_ROOT) -> Path:
    """Return a resolved path relative to the repository root."""
    resolved_root = repo_root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"Source escapes repository: {path}") from error


def source_reference_location(path: Path) -> tuple[str, Path]:
    """Use the legacy interview root when possible and repository otherwise."""
    try:
        return "interview_notes", path.resolve().relative_to(INTERVIEW_ROOT.resolve())
    except ValueError:
        return "repository", repository_relative(path)


def canonical_source_reference_path(root: str, path: str) -> str:
    """Normalize old and new SourceRef locations to one repository-relative path."""
    normalized = PurePosixPath(path).as_posix()
    if root == "interview_notes":
        return PurePosixPath("tech/interview", normalized).as_posix()
    return normalized


def source_reference_key(root: str, path: str, heading: str) -> tuple[str, str]:
    return source_key(canonical_source_reference_path(root, path), heading)


def _source_list_pattern(line: str, *, line_number: int) -> tuple[bool, str]:
    excluded = line.startswith("!")
    pattern = line[1:].strip() if excluded else line
    pattern = pattern.replace("\\", "/")
    if not pattern:
        raise ValueError(f"source-list.txt line {line_number}: empty pattern")
    pure = PurePosixPath(pattern)
    if pure.is_absolute() or re.match(r"^[A-Za-z]:", pattern):
        raise ValueError(
            f"source-list.txt line {line_number}: absolute paths are not allowed: {pattern}"
        )
    if ".." in pure.parts:
        raise ValueError(
            f"source-list.txt line {line_number}: parent traversal is not allowed: {pattern}"
        )
    suffix = pure.suffix.lower()
    wildcard = any(character in pattern for character in "*?[")
    broad_supported_glob = wildcard and suffix in {"", ".*"}
    if suffix not in SUPPORTED_SOURCE_FORMATS and not broad_supported_glob:
        supported = ", ".join(sorted(SUPPORTED_SOURCE_FORMATS))
        raise ValueError(
            f"source-list.txt line {line_number}: unsupported Source pattern: {pattern}; "
            f"supported extensions: {supported}"
        )
    return excluded, pattern


def resolve_source_list(
    source_list_path: Path = SOURCE_LIST_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[list[Path], list[str]]:
    """Resolve deterministic Source includes and excludes from source-list.txt."""
    if not source_list_path.is_file():
        raise ValueError(f"Source list does not exist: {source_list_path}")

    includes: list[tuple[int, str]] = []
    excludes: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(
        source_list_path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        excluded, pattern = _source_list_pattern(line, line_number=line_number)
        (excludes if excluded else includes).append((line_number, pattern))

    if not includes:
        raise ValueError("source-list.txt contains no include patterns")

    resolved_root = repo_root.resolve()
    warnings: list[str] = []

    def matched_paths(line_number: int, pattern: str) -> set[Path]:
        wildcard = any(character in pattern for character in "*?[")
        candidates = list(resolved_root.glob(pattern)) if wildcard else [resolved_root / pattern]
        matched: set[Path] = set()
        for candidate in candidates:
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            try:
                resolved.relative_to(resolved_root)
            except ValueError as error:
                raise ValueError(
                    f"source-list.txt line {line_number}: source escapes repository: {pattern}"
                ) from error
            if resolved.suffix.lower() not in SUPPORTED_SOURCE_FORMATS:
                continue
            matched.add(resolved)
        if not matched:
            kind = "pattern" if wildcard else "path"
            warnings.append(
                f"source-list.txt line {line_number}: {kind} matched no supported files: {pattern}"
            )
        return matched

    selected: set[Path] = set()
    for line_number, pattern in includes:
        selected.update(matched_paths(line_number, pattern))
    for line_number, pattern in excludes:
        selected.difference_update(matched_paths(line_number, pattern))

    files = sorted(
        selected,
        key=lambda path: repository_relative(path, repo_root=resolved_root).as_posix().lower(),
    )
    return files, warnings


def question_topic(
    relative_path: Path,
    section: str | None = None,
    prompt: str | None = None,
) -> str:
    parts = [part.lower() for part in relative_path.parts]
    if relative_path.name == "questions-in-interviews.md" and section:
        return slugify(section)
    if "system-desgin" in parts:
        return "system-design"
    if "behavioral" in parts:
        return "behavioral"
    if "ai-ml" in parts:
        return "ai-ml"
    context = f"{section or ''} {prompt or ''}".lower()
    if "spark" in context:
        return "spark"
    if any(
        keyword in context
        for keyword in (
            "职业经历",
            "manager",
            "为什么离开",
            "为什么是",
            "看机会",
            "影响力",
            "宽泛方向",
        )
    ):
        return "behavioral"
    if any(keyword in context for keyword in ("system design", "系统设计", "架构设计")):
        return "system-design"
    if len(parts) >= 2 and parts[-2] in {"languages", "libs", "others", "dsa"}:
        return slugify(relative_path.stem)
    return slugify(relative_path.stem)


def without_internal_fields(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if not key.startswith("_")}
