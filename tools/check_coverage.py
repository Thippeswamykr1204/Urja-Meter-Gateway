from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_coverage.py COVERAGE_JSON", file=sys.stderr)
        return 2

    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    failures = {
        filename: round(float(data["summary"]["percent_covered"]), 2)
        for filename, data in report["files"].items()
        if data["summary"]["num_statements"] and data["summary"]["percent_covered"] < 75
    }
    if failures:
        for filename, coverage in sorted(failures.items()):
            print(f"{filename}: {coverage}% coverage; minimum is 75%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
