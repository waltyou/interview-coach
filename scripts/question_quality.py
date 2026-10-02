"""Deterministic checks and content-bound evidence for semantic question review.

The evidence records an Agent's review; hashes do not prove semantic correctness.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from common import question_completeness_issues

REVIEW_CHECKS = (
    "standalone", "answer_contract", "interview_voice", "scope",
    "followup_context", "evaluation_alignment", "factual_basis",
)
CONTENT_FIELDS = (
    "id", "visibility", "status", "topic", "kind", "difficulty", "target_roles",
    "prompt", "rubric", "hints", "follow_ups", "coach_notes",
)


def content_sha256(question: dict[str, Any]) -> str:
    content = {key: question.get(key) for key in CONTENT_FIELDS}
    raw = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def review_issues(question: dict[str, Any], *, required: bool = False) -> list[str]:
    review = question.get("quality_review")
    if review is None:
        return ["quality_review is required before admission"] if required else []
    if not isinstance(review, dict):
        return ["quality_review must be an object"]
    issues = []
    if review.get("version") != 1:
        issues.append("unsupported quality_review version")
    if review.get("content_sha256") != content_sha256(question):
        issues.append("quality_review is stale: review changed content again")
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        issues.append("quality_review reviewer is required")
    try:
        reviewed_at = datetime.fromisoformat(review.get("reviewed_at", ""))
        if reviewed_at.utcoffset() is None:
            raise ValueError("timezone missing")
    except (TypeError, ValueError):
        issues.append("quality_review reviewed_at must include a timezone")
    checks = review.get("checks")
    if not isinstance(checks, dict):
        return issues + ["quality_review checks must contain review evidence"]
    for name in REVIEW_CHECKS:
        if not isinstance(checks.get(name), str) or not checks[name].strip():
            issues.append(f"quality_review needs written evidence for {name}")
    return issues


def content_issues(question: dict[str, Any]) -> list[str]:
    """High-confidence failures only; missing SQL semantics need semantic review."""
    issues = []
    prompt = question.get("prompt")
    if not isinstance(prompt, str):
        return ["prompt must be a string"]
    issues.extend(question_completeness_issues(prompt))
    for name in ("rubric", "hints", "follow_ups", "coach_notes"):
        values = question.get(name, [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            issues.append(f"{name} must be a list of nonempty strings")
    if not question.get("rubric"):
        issues.append("a self-contained rubric is required before admission")
    texts = [prompt] + (question.get("follow_ups") if isinstance(question.get("follow_ups"), list) else [])
    for i, value in enumerate(texts):
        if not isinstance(value, str):
            continue
        label = "prompt" if i == 0 else f"follow_ups[{i - 1}]"
        # Match fenced blocks, not inline backticks or natural punctuation.
        fence = None
        for line in value.splitlines():
            match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
            if not match:
                continue
            marker, rest = match.groups()
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not rest.strip():
                fence = None
        if fence is not None:
            issues.append(f"{label} has an unclosed code fence")
        if re.search(r"默认使用.+(?:案例|故障|故事).*回答|保留原题样例用于验证|主问保持原样|替换第.+追问如下", value):
            issues.append(f"{label} contains authoring instructions instead of an interview question")
    return issues
