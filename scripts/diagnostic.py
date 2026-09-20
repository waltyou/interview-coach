"""Versioned capability quotas and frozen scope for a short baseline."""
from __future__ import annotations

from collections import defaultdict
import random

CAPABILITIES = {
    "data-modeling": ("数据建模", {"data-modeling", "modeling"}),
    "system-design": ("系统设计", {"system-design", "big-data-architecture"}),
    "communication": ("沟通与 Senior 行为", {"soft-skill", "behavioral", "communication"}),
    "sql": ("SQL", {"sql"}),
    "data-processing": ("数据处理与分布式系统", {"spark", "hadoop", "kafka", "distributed-systems", "flink"}),
    "storage": ("存储与表格式", {"iceberg", "hive", "redis", "elasticsearch"}),
    "reliability": ("数据质量与故障诊断", {"data-quality", "linux"}),
    "coding": ("工程编码", {"java", "python", "algorithm", "scala"}),
}


def capability(topic: str) -> str:
    root = topic.split(".")[0]
    return next((name for name, (_, topics) in CAPABILITIES.items() if root in topics), f"topic:{root}")


def capability_label(name: str) -> str:
    return CAPABILITIES[name][0] if name in CAPABILITIES else name.removeprefix("topic:")


def sample(question_ids: list[str], questions: dict[str, dict], limit: int) -> list[str]:
    groups = defaultdict(list)
    for qid in question_ids:
        groups[capability(questions[qid]["topic"])].append(qid)
    # Reserve a slot for each core capability before filling additional slots.
    # The first three remain mandatory even when the user asks for fewer than 8.
    order = [name for name in CAPABILITIES if name in groups]
    order += sorted(set(groups) - set(CAPABILITIES))
    rng = random.SystemRandom()
    for group in groups.values():
        rng.shuffle(group)
    result = []
    while len(result) < min(limit, len(question_ids)):
        for name in order:
            if groups[name] and len(result) < limit:
                result.append(groups[name].pop())
    return result


def snapshot(pool: list[str], selected: list[str], questions: dict[str, dict]) -> dict:
    available = {capability(questions[qid]["topic"]) for qid in pool}
    return {
        "blueprint_version": 1,
        "scope_capabilities": list(CAPABILITIES) + sorted(available - set(CAPABILITIES)),
        "available_capabilities": sorted(available),
        "pool_topics": sorted({questions[qid]["topic"].split(".")[0] for qid in pool}),
        "question_capabilities": {qid: capability(questions[qid]["topic"]) for qid in selected},
        "question_topics": {qid: questions[qid]["topic"].split(".")[0] for qid in selected},
    }


def coverage(cycle: dict, progress: dict) -> dict | None:
    spec = cycle.get("diagnostic")
    if spec is None:
        return None
    scope = set(spec["scope_capabilities"])
    mapping = spec["question_capabilities"]
    selected = set(mapping.values())
    answered = {mapping[s["question_id"]] for s in progress["questions"]
                if s["question_id"] in mapping and s["status"] != "unseen"}
    verified = {mapping[s["question_id"]] for s in progress["questions"]
                if s["question_id"] in mapping and s.get("evidence_status") == "independent"}
    return {
        "scope_capabilities": sorted(scope),
        "not_included_capabilities": sorted(scope - selected),
        "unavailable_capabilities": sorted(scope - set(spec["available_capabilities"])),
        "untested_capabilities": sorted(scope - answered),
        "unverified_capabilities": sorted(scope - verified),
    }


def snapshot_issues(cycle: dict) -> list[str]:
    spec = cycle.get("diagnostic")
    if spec is None:
        return []
    if not isinstance(spec, dict) or spec.get("blueprint_version") != 1:
        return ["invalid diagnostic blueprint"]
    if cycle.get("kind") != "baseline":
        return ["diagnostic snapshot requires a baseline cycle"]
    for field in ("scope_capabilities", "available_capabilities", "pool_topics"):
        values = spec.get(field)
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            return [f"invalid diagnostic {field}"]
    for field in ("question_capabilities", "question_topics"):
        mapping = spec.get(field)
        if not isinstance(mapping, dict) or set(mapping) != set(cycle["question_ids"]):
            return [f"diagnostic {field} must cover exactly the selected questions"]
        if any(not isinstance(v, str) or not v for v in mapping.values()):
            return [f"invalid diagnostic {field} values"]
    if not set(spec["available_capabilities"]) <= set(spec["scope_capabilities"]):
        return ["available diagnostic capabilities escape the frozen scope"]
    if not set(spec["question_capabilities"].values()) <= set(spec["available_capabilities"]):
        return ["selected diagnostic capabilities were not available"]
    if not set(spec["question_topics"].values()) <= set(spec["pool_topics"]):
        return ["selected diagnostic topics escape the original pool"]
    return []
