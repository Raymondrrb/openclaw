"""JSON Schema guard — validates LLM output and generates repair prompts.

Validates LLM responses against a simple schema specification.
When validation fails, generates a targeted repair prompt instead of
regenerating from scratch (saving ~60-80% tokens on retries).

Stdlib only — no jsonschema dependency (simple field-level validation).

Usage:
    from tools.lib.json_schema_guard import validate_output, build_repair_prompt

    schema = {
        "type": "object",
        "required": ["hook", "cta", "facts"],
        "properties": {
            "hook": {"type": "string", "maxLength": 200},
            "cta": {"type": "string"},
            "facts": {"type": "array", "minItems": 3},
        },
    }

    errors = validate_output(llm_result, schema)
    if errors:
        repair_prompt = build_repair_prompt(llm_result, schema, errors)
        # Send repair_prompt to LLM (much cheaper than full regeneration)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class SchemaValidationError:
    """A single validation error with path and description."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message

    def __repr__(self) -> str:
        return f"SchemaValidationError({self.path!r}, {self.message!r})"

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def _validate_type(value: Any, expected: str) -> bool:
    """Check if value matches expected JSON type."""
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    expected_type = type_map.get(expected)
    if expected_type is None:
        return True  # unknown type — accept
    return isinstance(value, expected_type)


def validate_output(
    output: Any,
    schema: Dict[str, Any],
    *,
    path: str = "$",
) -> List[SchemaValidationError]:
    """Validate LLM output against a simple schema.

    Supports:
    - type checking (string, number, integer, boolean, array, object, null)
    - required fields
    - maxLength / minLength for strings
    - minItems / maxItems for arrays
    - properties (recursive validation for nested objects)
    - items (recursive validation for array items)
    - enum (allowed values)

    Returns list of SchemaValidationError (empty = valid).
    """
    errors: List[SchemaValidationError] = []

    # Type check
    expected_type = schema.get("type")
    if expected_type and not _validate_type(output, expected_type):
        errors.append(SchemaValidationError(
            path, f"Expected type '{expected_type}', got '{type(output).__name__}'"
        ))
        return errors  # can't validate further if type is wrong

    # Enum check
    enum_values = schema.get("enum")
    if enum_values is not None and output not in enum_values:
        errors.append(SchemaValidationError(
            path, f"Value must be one of {enum_values}, got {output!r}"
        ))

    # Object-specific checks
    if isinstance(output, dict):
        # Required fields
        required = schema.get("required", [])
        for field in required:
            if field not in output:
                errors.append(SchemaValidationError(
                    f"{path}.{field}", f"Required field missing"
                ))

        # Property validation (recursive)
        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key in output:
                sub_errors = validate_output(
                    output[key], prop_schema, path=f"{path}.{key}"
                )
                errors.extend(sub_errors)

    # String-specific checks
    if isinstance(output, str):
        max_len = schema.get("maxLength")
        if max_len is not None and len(output) > max_len:
            errors.append(SchemaValidationError(
                path, f"String too long: {len(output)} chars (max {max_len})"
            ))
        min_len = schema.get("minLength")
        if min_len is not None and len(output) < min_len:
            errors.append(SchemaValidationError(
                path, f"String too short: {len(output)} chars (min {min_len})"
            ))

    # Array-specific checks
    if isinstance(output, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(output) < min_items:
            errors.append(SchemaValidationError(
                path, f"Array too short: {len(output)} items (min {min_items})"
            ))
        max_items = schema.get("maxItems")
        if max_items is not None and len(output) > max_items:
            errors.append(SchemaValidationError(
                path, f"Array too long: {len(output)} items (max {max_items})"
            ))

        # Items validation (recursive)
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(output):
                sub_errors = validate_output(
                    item, items_schema, path=f"{path}[{i}]"
                )
                errors.extend(sub_errors)

    return errors


# ---------------------------------------------------------------------------
# Repair prompt builder
# ---------------------------------------------------------------------------

def build_repair_prompt(
    broken_output: Any,
    schema: Dict[str, Any],
    errors: List[SchemaValidationError],
    *,
    max_broken_chars: int = 2000,
) -> str:
    """Build a repair prompt from validation errors.

    Instead of regenerating from scratch, this asks the LLM to fix
    specific issues — typically 3-5x cheaper in tokens.

    Args:
        broken_output: The invalid LLM output.
        schema: The schema it should match.
        errors: List of validation errors from validate_output().
        max_broken_chars: Truncate broken output in prompt (token control).

    Returns:
        Repair prompt string.
    """
    broken_str = json.dumps(broken_output, ensure_ascii=False)
    if len(broken_str) > max_broken_chars:
        broken_str = broken_str[:max_broken_chars] + "... [truncated]"

    error_lines = "\n".join(f"- {e}" for e in errors)
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)

    return f"""### REPAIR REQUEST
The following JSON output has validation errors. Fix ONLY the errors listed below.
Do NOT change anything else. Return the complete fixed JSON.

### ERRORS
{error_lines}

### TARGET SCHEMA
{schema_str}

### BROKEN OUTPUT
{broken_str}

### RULES
- Return ONLY the fixed JSON. No explanations, no markdown.
- Fix exactly the errors listed. Do not change valid fields.
- If a required field is missing, add it with a reasonable default.
""".strip()


# ---------------------------------------------------------------------------
# Parse helper — try to extract JSON from LLM response
# ---------------------------------------------------------------------------

def parse_llm_json(
    raw: str,
    schema: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[Dict[str, Any]], List[SchemaValidationError]]:
    """Parse LLM response as JSON, optionally validate against schema.

    Handles common LLM quirks:
    - Leading/trailing whitespace
    - Markdown code fences (```json ... ```)
    - Single-line preamble before JSON

    Returns:
        (parsed_dict, errors) — errors is empty if valid or schema is None.
        Returns (None, [parse_error]) if JSON parsing fails entirely.
    """
    text = raw.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        elif lines[0].strip().startswith("```"):
            lines = lines[1:]
        text = "\n".join(lines).strip()

    # Try direct parse
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Try finding JSON object in the text
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None, [SchemaValidationError("$", "Could not parse JSON from LLM response")]
        else:
            return None, [SchemaValidationError("$", "No JSON object found in LLM response")]

    if not isinstance(obj, dict):
        return None, [SchemaValidationError("$", f"Expected JSON object, got {type(obj).__name__}")]

    if schema:
        errors = validate_output(obj, schema)
        return obj, errors

    return obj, []
