import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
OPENAPI = ROOT / "openapi.json"
OUTPUT = ROOT / "apps" / "web" / "src" / "lib" / "generated-api.ts"
SCHEMA_NAMES = (
    "QualityFlag",
    "Provenance",
    "QualitySummary",
    "Meter",
    "ConsumptionPoint",
    "ConsumptionSummary",
    "ConsumptionResponse",
    "HierarchyNode",
    "DataQualityReport",
    "SyncRun",
    "Signal",
    "PageMeta",
)


def type_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def schema_to_ts(schema: dict[str, Any], indent: int = 0) -> str:
    if "$ref" in schema:
        return type_name(str(schema["$ref"]))
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(schema_to_ts(item, indent) for item in schema["anyOf"])
    if "oneOf" in schema:
        return " | ".join(schema_to_ts(item, indent) for item in schema["oneOf"])
    if schema.get("type") == "array":
        return f"Array<{schema_to_ts(schema.get('items', {}), indent)}>"
    if schema.get("type") == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", [])) | set(properties)
        if not properties:
            additional = schema.get("additionalProperties")
            return f"Record<string, {schema_to_ts(additional, indent)}>" if isinstance(additional, dict) else "Record<string, unknown>"
        lines = ["{"]
        for name, child in properties.items():
            optional = "" if name in required else "?"
            lines.append(f"{' ' * (indent + 2)}{name}{optional}: {schema_to_ts(child, indent + 2)};")
        lines.append(" " * indent + "}")
        return "\n".join(lines)
    if schema.get("type") == "integer" or schema.get("type") == "number":
        return "number"
    if schema.get("type") == "boolean":
        return "boolean"
    if schema.get("type") == "null":
        return "null"
    return "string"


def render() -> str:
    document = json.loads(OPENAPI.read_text())
    schemas = document["components"]["schemas"]
    blocks = [
        "// Generated from openapi.json. Do not edit by hand.",
        "",
        "export type ApiEnvelope<T> = { data: T; provenance: Provenance; meta: Record<string, unknown> }",
        "",
    ]
    for name in SCHEMA_NAMES:
        schema = schemas.get(name)
        if schema is None:
            continue
        blocks.append(f"export type {name} = {schema_to_ts(schema)}")
        if name == "QualityFlag" and isinstance(schema.get("enum"), list):
            values = ", ".join(json.dumps(value) for value in schema["enum"])
            blocks.append(f"export const QUALITY_FLAGS = [{values}] as const")
        blocks.append("")
    blocks.append("export type ProblemDetails = { type?: string; title?: string; status?: number; detail?: string; code?: string; request_id?: string }")
    return "\n".join(blocks) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render()
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != rendered:
            raise SystemExit("generated-api.ts is out of date; run npm run generate:types")
        return
    OUTPUT.write_text(rendered)
    print(OUTPUT)


if __name__ == "__main__":
    main()
