"""Append a replacement evaluation, preserving every fact of the original answer."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from uuid import uuid4

from common import EVENT_ROOT, SCORE_FIELDS, effective_attempts, load_events, load_json, now_iso, write_json


def correction_event(events: list[dict], attempt_id: str, evaluation: dict, reason: str) -> dict:
    attempts = effective_attempts(events)
    original = next((e for e in attempts if e["id"] == attempt_id), None)
    if original is None:
        raise ValueError("Choose the original attempt.recorded ID")
    if not reason.strip():
        raise ValueError("A correction reason is required")
    scores = evaluation.get("scores", {})
    if set(scores) != set(SCORE_FIELDS) or any(type(scores[f]) is not int or not 0 <= scores[f] <= 4 for f in SCORE_FIELDS):
        raise ValueError("Evaluation requires four integer scores from 0 to 4")
    if not isinstance(evaluation.get("missing_points"), list) or not evaluation.get("feedback") or not evaluation.get("evaluator", {}).get("agent"):
        raise ValueError("Evaluation requires missing_points, feedback and evaluator.agent")
    result = deepcopy(original)
    for field in ("_path", "evaluation_history", "evaluation_event_id"):
        result.pop(field, None)
    result.update(id=f"attempt.correction.{uuid4().hex}", type="attempt.reevaluated",
                  supersedes=original.get("evaluation_event_id", original["id"]), corrected_at=now_iso(),
                  correction_reason=reason, evaluation=deepcopy(evaluation))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--evaluation", required=True, help="JSON file containing the replacement evaluation object")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    from pathlib import Path
    try:
        events = load_events(raw=True)
        event = correction_event(events, args.attempt_id, load_json(Path(args.evaluation)), args.reason)
        effective_attempts(events + [event])
        timestamp = event["corrected_at"]
        path = EVENT_ROOT / timestamp[:4] / timestamp[5:7] / f"{event['id']}.json"
        write_json(path, event)
        from build_dashboard import build_dashboard
        build_dashboard()
        print(json.dumps({"status": "corrected", "event_id": event["id"], "attempt_id": args.attempt_id}))
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
