import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "apps" / "api"))

from app.main import app  # noqa: E402, I001


if __name__ == "__main__":
    output = Path(__file__).parents[2] / "openapi.json"
    rendered = json.dumps(app.openapi(), indent=2) + "\n"
    if "--check" in sys.argv:
        if output.read_text() != rendered:
            raise SystemExit("openapi.json is out of date; run make export-openapi")
    else:
        output.write_text(rendered)
        print(output)
