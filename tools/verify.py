from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[1]
PYTHON = ROOT / ".venv/bin/python3"
REPORT = ROOT / "docs/verification.md"


@dataclass
class Result:
    command: str
    status: str
    output: str


def format_command(command: Sequence[str], root: Path = ROOT) -> str:
    """Render a command without leaking local executable paths into reports."""
    formatted: list[str] = []
    for argument in command:
        if argument.endswith("/.venv/bin/python3") or argument.endswith("/.venv/bin/python"):
            formatted.append("python")
            continue
        if argument.endswith("/.venv/bin/ruff"):
            formatted.append("ruff")
            continue
        if argument.endswith("/.venv/bin/mypy"):
            formatted.append("mypy")
            continue
        path = Path(argument)
        if path.is_absolute():
            try:
                argument = str(path.relative_to(root))
            except ValueError:
                argument = path.name
        formatted.append(argument)
    return shlex.join(formatted)


def run_command(command: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> Result:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip()
    return Result(
        command=format_command(command),
        status="pass" if completed.returncode == 0 else f"fail ({completed.returncode})",
        output=output,
    )


def write_report(results: list[Result]) -> None:
    test_result = next((result for result in results if "coverage run" in result.command), None)
    coverage_result = next((result for result in results if "coverage report" in result.command), None)
    vitest_result = next((result for result in results if result.command == "npm run test"), None)
    vitest_repeat_result = next((result for result in results if result.command == "npm run test:repeat"), None)
    playwright_result = next((result for result in results if result.command == "npm run smoke"), None)
    passed_tests = "UNVERIFIED"
    coverage = "UNVERIFIED"
    vitest_tests = "UNVERIFIED"
    vitest_repeat_runs = "UNVERIFIED"
    playwright_tests = "UNVERIFIED"
    if test_result:
        match = re.search(r"(\d+) passed", test_result.output)
        if match:
            passed_tests = match.group(1)
        else:
            passed_lines = re.findall(r"^PASSED\s", test_result.output, re.MULTILINE)
            if passed_lines:
                passed_tests = str(len(passed_lines))
    if coverage_result:
        match = re.search(r"TOTAL\s+.*\s(\d+)%", coverage_result.output)
        if match:
            coverage = f"{match.group(1)}%"
    if vitest_result:
        match = re.search(r"Tests\s+(\d+)\s+passed", vitest_result.output)
        if match:
            vitest_tests = match.group(1)
    if vitest_repeat_result:
        runs = re.findall(r"Tests\s+(\d+)\s+passed", vitest_repeat_result.output)
        if vitest_repeat_result.status == "pass" and len(runs) == 5:
            vitest_repeat_runs = "5/5"
        elif runs:
            vitest_repeat_runs = f"{len(runs)}/5"
    if playwright_result:
        match = re.search(r"(\d+) passed", playwright_result.output)
        if match:
            playwright_tests = match.group(1)

    lines = [
        "# Verification record",
        "",
        f"Generated on **{date.today().isoformat()}** by `make verify`.",
        "",
        f"Python tests passed: **{passed_tests}**.",
        f"Overall Python coverage: **{coverage}**.",
        f"Vitest tests passed: **{vitest_tests}**.",
        f"Repeated Vitest runs passed: **{vitest_repeat_runs}**.",
        f"Playwright tests passed: **{playwright_tests}**.",
        "",
        "## Checks",
        "",
        "| Command | Result |",
        "|---|---|",
    ]
    lines.extend(f"| `{result.command}` | {result.status} |" for result in results)
    lines.extend(
        [
            "",
            "## Live portal status",
            "",
            "The live portal was not tested. Portal-specific routes, fields, session markers, units, timestamps, pagination, and request limits remain `UNVERIFIED` until captured and redacted.",
            "",
            "## Frontend chunk note",
            "",
            "The map route now loads MapLibre in a separate route chunk. The current build reports the route shell and MapLibre dependency separately; MapLibre remains the largest browser dependency.",
            "",
            "## Known limitations",
            "",
            "- Browser smoke requires the local API and frontend development server.",
            "- The product remains single-instance by design, using SQLite and in-process coordination.",
            "- Live portal protocol behavior remains `UNVERIFIED`.",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    results: list[Result] = []
    env = os.environ.copy()
    env.update(
        {
            "DEMO_MODE": "true",
            "API_HOST": "127.0.0.1",
            "API_PORT": "8000",
        }
    )
    try:
        commands = [
            [str(PYTHON.parent / "ruff"), "check", "."],
            [str(PYTHON.parent / "mypy"), "."],
            [str(PYTHON), "-m", "coverage", "erase"],
            [str(PYTHON), "-m", "coverage", "run", "-m", "pytest", "-q", "-rA"],
            [str(PYTHON), "-m", "coverage", "report", "--fail-under=85"],
            [str(PYTHON), "-m", "coverage", "json", "-o", ".coverage.json"],
            [str(PYTHON), "tools/check_coverage.py", ".coverage.json"],
            [
                "uv",
                "pip",
                "compile",
                "requirements.txt",
                "--python-version",
                "3.11",
                "--universal",
                "--output-file",
                "/tmp/flock-requirements.lock",
                "--custom-compile-command",
                "uv pip compile requirements.txt --python-version 3.11 --universal --output-file requirements.lock",
            ],
            ["diff", "-u", "requirements.lock", "/tmp/flock-requirements.lock"],
            [str(PYTHON), "tools/export_openapi/main.py", "--check"],
            ["npm", "run", "test"],
            ["npm", "run", "test:repeat"],
            ["npm", "run", "check:generated-types"],
            ["npm", "run", "lint"],
            ["npm", "run", "build"],
            ["npm", "run", "smoke"],
        ]
        backend_commands = 10
        for command in commands[:backend_commands]:
            result = run_command(command, env=env)
            results.append(result)
            if result.status != "pass":
                return 1

        for command in commands[backend_commands:]:
            result = run_command(command, cwd=ROOT / "apps/web", env=env)
            results.append(result)
            if result.status != "pass":
                return 1
        return 0
    finally:
        write_report(results)


if __name__ == "__main__":
    raise SystemExit(main())
