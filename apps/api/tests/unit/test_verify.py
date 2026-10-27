from pathlib import Path

from tools.verify import format_command


def test_format_command_removes_machine_specific_paths() -> None:
    rendered = format_command(
        [
            "/Users/alice/FlockEnergy/.venv/bin/python3",
            "tools/verify.py",
            "/Users/alice/FlockEnergy/.venv/bin/ruff",
            "check",
            "/Users/alice/FlockEnergy",
        ],
        root=Path("/Users/alice/FlockEnergy"),
    )

    assert rendered == "python tools/verify.py ruff check ."
    assert not rendered.startswith("/")
    assert "/Users/" not in rendered
    assert str(Path.home()) not in rendered
    assert "alice" not in rendered
