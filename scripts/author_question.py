"""Review and save one complete Question without touching practice history."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import PACK_ROOT, load_json, load_questions, now_iso, question_root_for_visibility, write_json
from question_quality import content_issues, content_sha256, review_issues


def save_question(draft: dict[str, Any], *, check_only: bool = False) -> Path:
    if not isinstance(draft, dict):
        raise ValueError("draft must be a Question object, not an import envelope")
    question = dict(draft)
    required = {"id", "schema_version", "revision", "status", "visibility", "topic", "kind",
                "difficulty", "origin", "prompt", "rubric", "hints", "follow_ups",
                "source_refs", "evaluation_basis", "target_roles"}
    if required - question.keys():
        raise ValueError("missing Question fields: " + ", ".join(sorted(required - question.keys())))
    if any(key.startswith("_") for key in question):
        raise ValueError("internal fields are not allowed in an admission draft")
    if type(question["revision"]) is not int or question["revision"] < 1:
        raise ValueError("revision must be a positive integer")
    identifier, topic = question.get("id", ""), question.get("topic", "")
    if not isinstance(identifier, str) or not re.fullmatch(r"q\.[a-z0-9][a-z0-9.-]+", identifier):
        raise ValueError("invalid Question id")
    if not isinstance(topic, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", topic):
        raise ValueError("invalid Question topic")
    if question.get("schema_version") != 3:
        raise ValueError("Question schema_version must be 3")
    if question.get("status") not in {"active", "archived"}:
        raise ValueError("invalid Question status")
    if question.get("visibility") not in {"public", "private"}:
        raise ValueError("invalid Question visibility")
    if question.get("kind") not in {"concept", "explanation", "scenario", "coding", "system-design", "behavioral"}:
        raise ValueError("invalid Question kind")
    if type(question.get("difficulty")) is not int or not 1 <= question["difficulty"] <= 5:
        raise ValueError("difficulty must be an integer from 1 to 5")
    if question.get("origin") not in {"explicit-heading", "real-interview", "generated", "manual"}:
        raise ValueError("invalid Question origin")
    if question.get("evaluation_basis") not in {"rubric", "source-section", "both"}:
        raise ValueError("invalid evaluation_basis")
    if not isinstance(question.get("source_refs"), list):
        raise ValueError("source_refs must be a list")
    roots = load_json(PACK_ROOT / "manifest.json").get("source_roots", {})
    for reference in question["source_refs"]:
        if not isinstance(reference, dict) or any(
            not isinstance(reference.get(key), str) or not reference[key].strip()
            for key in ("root", "path", "heading")
        ):
            raise ValueError("SourceRef requires root, path and heading")
        if reference["root"] not in roots:
            raise ValueError("unknown SourceRef root")
        source_root = (PACK_ROOT / roots[reference["root"]]).resolve()
        source = (source_root / reference["path"]).resolve()
        if not source.is_relative_to(source_root) or not source.is_file():
            raise ValueError("SourceRef must point to an existing file inside its root")
    if not isinstance(question.get("target_roles"), list) or any(not isinstance(x, str) or not x.strip() for x in question["target_roles"]):
        raise ValueError("target_roles must be a list of nonempty strings")
    issues = content_issues(question) + review_issues(question, required=True)
    if issues:
        raise ValueError("; ".join(issues))
    existing = load_questions().get(identifier)
    if existing:
        if question["visibility"] != existing["visibility"]:
            raise ValueError("visibility migration requires a separate explicit curation operation")
        if question.get("revision") != existing["revision"]:
            raise ValueError("stale draft revision; reload the existing Question")
        if existing.get("quality_review") == question.get("quality_review") and content_sha256(existing) == content_sha256(question):
            return existing["_path"]
        # Keep unknown forward-compatible fields; never replace identity/history.
        result = {key: value for key, value in existing.items() if not key.startswith("_")}
        result.update(question)
        result["created_at"] = existing["created_at"]
        result["revision"] = existing["revision"] + 1
        output = existing["_path"]
    else:
        result = question
        result["revision"] = 1
        result["created_at"] = now_iso()
        output = question_root_for_visibility(question["visibility"]) / topic / f"{identifier}.json"
        if output.exists():
            raise ValueError("refusing to overwrite an unrecognized existing file")
    result["updated_at"] = now_iso()
    # A legacy draft omitting existing optional content must not invalidate its receipt.
    issues = review_issues(result, required=True)
    if issues:
        raise ValueError("; ".join(issues))
    if not check_only:
        write_json(output, result)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("--fingerprint", action="store_true", help="Print content hash for a semantic review; does not approve it")
    parser.add_argument("--check", action="store_true", help="Validate admission without writing")
    args = parser.parse_args()
    try:
        draft = load_json(args.draft)
        if args.fingerprint:
            print(content_sha256(draft))
            return
        output = save_question(draft, check_only=args.check)
        if not args.check:
            from initialize import write_question_indexes
            write_question_indexes(now_iso())
        print(json.dumps({"status": "checked" if args.check else "saved", "path": str(output)}, ensure_ascii=False))
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
