"""Generate frontend contracts and validators from Pydantic JSON Schema.

No JavaScript package installation is required. Run from the project directory:
``python scripts/generate_research_contracts.py``; use ``--check`` in CI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research_pipeline.public_schemas import PUBLIC_MODELS

OUTPUT = ROOT / "frontend/src/research/contracts.generated.ts"


def ts_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(ts_type(part) for part in schema["anyOf"])
    kind = schema.get("type")
    if kind == "array":
        return f"Array<{ts_type(schema.get('items', {}))}>"
    if kind == "object":
        additional = schema.get("additionalProperties", {})
        if schema.get("properties"):
            raise ValueError("inline object properties require a named Pydantic model")
        return f"Record<string, {ts_type(additional) if isinstance(additional, dict) else 'unknown'}>"
    return {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}.get(kind, "unknown")


VALIDATOR = '''
type Schema = {
  $ref?: string; anyOf?: Schema[]; const?: unknown; enum?: unknown[];
  type?: string; properties?: Record<string, Schema>; required?: string[];
  items?: Schema; additionalProperties?: boolean | Schema; minimum?: number;
  "x-provenance-rule"?: string; "x-legacy-dossier"?: boolean;
};
const definitions: Record<string, Schema> = contractSchema;

export class ResearchContractError extends Error {
  readonly path: string;
  constructor(path: string, expected: string) {
    super(`Invalid research response at ${path}: ${expected}`);
    this.name = 'ResearchContractError';
    this.path = path;
  }
}

function validate(schema: Schema, value: unknown, path: string): void {
  if (schema.$ref) {
    validate(definitions[schema.$ref.split('/').pop()!], value, path);
    return;
  }
  if (schema.anyOf) {
    let detail: ResearchContractError | undefined;
    for (const option of schema.anyOf) {
      try { validate(option, value, path); return; }
      catch (error) {
        if (!(error instanceof ResearchContractError)) throw error;
        // Keep the substantive branch's diagnostic rather than the null branch.
        if (option.type !== 'null' && (!detail || error.path.length > detail.path.length)) detail = error;
      }
    }
    throw detail ?? new ResearchContractError(path, 'no matching schema branch');
  }
  if ('const' in schema && value !== schema.const) throw new ResearchContractError(path, `expected ${String(schema.const)}`);
  if (schema.enum && !schema.enum.includes(value)) throw new ResearchContractError(path, `expected one of ${schema.enum.join(', ')}`);
  if (schema.type === 'null' && value !== null) throw new ResearchContractError(path, 'expected null');
  if (schema.type === 'string' && typeof value !== 'string') throw new ResearchContractError(path, 'expected string');
  if (schema.type === 'boolean' && typeof value !== 'boolean') throw new ResearchContractError(path, 'expected boolean');
  if (schema.type === 'integer' || schema.type === 'number') {
    if (typeof value !== 'number' || !Number.isFinite(value) || (schema.type === 'integer' && !Number.isInteger(value))) throw new ResearchContractError(path, `expected ${schema.type}`);
    if (schema.minimum !== undefined && value < schema.minimum) throw new ResearchContractError(path, `minimum ${schema.minimum}`);
  }
  if (schema.type === 'array') {
    if (!Array.isArray(value)) throw new ResearchContractError(path, 'expected array');
    value.forEach((item, index) => validate(schema.items ?? {}, item, `${path}[${index}]`));
  }
  if (schema.type === 'object') {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new ResearchContractError(path, 'expected object');
    const object = value as Record<string, unknown>;
    if (schema['x-legacy-dossier'] && ['run_status', 'paper_evidence', 'clinical_trials', 'kg_only_relations'].some(key => Object.hasOwn(object, key))) throw new ResearchContractError(path, 'canonical fields require the canonical dossier contract');
    for (const key of schema.required ?? []) {
      if (!Object.hasOwn(object, key)) throw new ResearchContractError(`${path}.${key}`, 'required field missing');
    }
    for (const [key, item] of Object.entries(object)) {
      const property = schema.properties?.[key];
      if (property) validate(property, item, `${path}.${key}`);
      else if (typeof schema.additionalProperties === 'object') validate(schema.additionalProperties, item, `${path}.${key}`);
      else if (schema.additionalProperties === false) throw new ResearchContractError(`${path}.${key}`, 'unexpected field');
    }
    const rule = schema['x-provenance-rule'];
    const validQuote = object.quote_valid === true || (rule === 'evidence' && object.presentation_state === 'VALIDATED_QUOTE');
    if (rule && validQuote && (object.quote || object.author_claim_quote)) {
      if (!(object.document_id || (rule === 'evidence' && object.paper_id))) throw new ResearchContractError(`${path}.document_id`, 'validated quote requires document_id or paper_id');
      const locator = rule === 'paper' ? 'quote_source_unit_id' : 'source_unit_id';
      if (!object[locator]) throw new ResearchContractError(`${path}.${locator}`, 'validated quote requires source_unit provenance');
      const selected = Array.isArray(object.selected_source_unit_ids) && object.selected_source_unit_ids.length ? object.selected_source_unit_ids : object.selected_source_units;
      if (rule === 'paper' && Array.isArray(selected) && selected.length && !selected.includes(object[locator])) throw new ResearchContractError(`${path}.${locator}`, 'validated quote must reference a selected source unit');
    }
  }
}
'''


def render_contracts() -> str:
    definitions: dict[str, Any] = {}
    for model in PUBLIC_MODELS:
        schema = model.model_json_schema()
        for name, definition in schema.pop("$defs", {}).items():
            if name in definitions and definitions[name] != definition:
                raise ValueError(f"inconsistent schema definition: {name}")
            definitions[name] = definition
        definitions[model.__name__] = schema
    lines = ["// Generated by scripts/generate_research_contracts.py. Do not edit manually.\n"]
    for name, schema in sorted(definitions.items()):
        lines.append(f"export interface {name} {{")
        required = schema.get("required", [])
        for key, prop in schema.get("properties", {}).items():
            lines.append(f"  {key}{'' if key in required else '?'}: {ts_type(prop)};")
        if schema.get("additionalProperties") is True:
            lines.append("  [key: string]: unknown;")
        lines.append("}\n")
    lines.append("const contractSchema = " + json.dumps(definitions, ensure_ascii=False, sort_keys=True, indent=2) + ";\n")
    lines.append(VALIDATOR)
    for model in PUBLIC_MODELS:
        name = model.__name__
        lines.append(f"export function parse{name}(value: unknown): {name} {{\n  validate(definitions.{name}, value, '{name}');\n  return value as {name};\n}}\n")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render_contracts()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print("Frontend research contracts are stale; run scripts/generate_research_contracts.py", file=sys.stderr)
            return 1
    else:
        OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
