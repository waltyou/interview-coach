from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import REPO_ROOT, repository_relative
from source_readers import SourceReadError, extract_source_text, inspect_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect or extract text from one Interview Coach Source"
    )
    parser.add_argument("path", help="Repository-relative Source path")
    parser.add_argument(
        "--metadata",
        action="store_true",
        help="Print format, title, status and unit count as JSON",
    )
    parser.add_argument(
        "--unit",
        type=int,
        help="Extract one 1-based PDF page, PPTX slide or XMind sheet",
    )
    return parser.parse_args()


def source_path(value: str) -> Path:
    candidate = (REPO_ROOT / value).resolve()
    repository_relative(candidate)
    if not candidate.is_file():
        raise SourceReadError(f"Source does not exist: {value}")
    return candidate


def main() -> None:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        path = source_path(args.path)
        if args.metadata:
            metadata = inspect_source(path)
            metadata["path"] = repository_relative(path).as_posix()
            print(json.dumps(metadata, ensure_ascii=False, indent=2))
            return
        print(extract_source_text(path, unit=args.unit), end="")
    except (OSError, SourceReadError, UnicodeDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
