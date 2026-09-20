"""Read-only, capability-scoped environment checks. No personal data is read."""
import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def inspect_environment(capability="core"):
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("os", platform.system() in ("Windows", "Darwin", "Linux"), platform.system())
    add("python", sys.version_info >= (3, 10), "Python 3.10+ required; running " + platform.python_version())
    if capability == "pdf-source":
        add("pdf-reader", importlib.util.find_spec("pypdf") is not None or shutil.which("pdftotext"),
            "Install pypdf with the selected Python: -m pip install pypdf (prefer a virtual environment).")
    if capability == "pdf-export":
        node = shutil.which("node")
        add("node", node is not None, "Node.js 22+ required for PDF export only.")
        if node:
            try:
                result = subprocess.run(
                    [node, str(Path(__file__).resolve().parents[1] / "resume/scripts/export-pdf.cjs"), "--check"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                )
                add("pdf-export", result.returncode == 0, (result.stdout + result.stderr).strip())
            except (OSError, subprocess.TimeoutExpired) as error:
                add("pdf-export", False, str(error))
    return {"status": "ok" if all(item["ok"] for item in checks) else "attention",
            "capability": capability, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capability", choices=("core", "pdf-source", "pdf-export"), default="core")
    args = parser.parse_args()
    result = inspect_environment(args.capability)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
