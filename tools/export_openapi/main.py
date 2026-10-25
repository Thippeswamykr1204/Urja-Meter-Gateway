import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "apps" / "api"))

from app.main import app  # noqa: E402, I001


if __name__ == "__main__":
    output = Path(__file__).parents[2] / "openapi.json"
    output.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(output)
