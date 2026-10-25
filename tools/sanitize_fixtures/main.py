import argparse
import json
import re
from pathlib import Path
from typing import Any

SECRET_KEYS = re.compile(r"(?i)(password|authorization|cookie|token|secret|api[_-]?key)")
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SECRET_KEYS.search(str(key)) else sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return EMAIL.sub("redacted@example.invalid", value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove secrets and personal-looking values from JSON fixtures.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.source.read_text())
    args.destination.write_text(json.dumps(sanitize(payload), indent=2) + "\n")


if __name__ == "__main__":
    main()
