"""JSON Schema guard — validates LLM output and generates repair prompts.

Validates LLM responses against a simple schema specification.
When validation fails, generates a targeted repair prompt instead of
regenerating from scratch (saving ~60-80% tokens on retries).

Two-tier validation:
  1. Schema validation — structural correctness (type, required, length)
  2. Quality gates — semantic correctness (price > 0, confidence >= 0.4)

Repair strategy:
  - Schema errors → repair prompt (max 2 attempts)
  - Quality gate failures → needs_human (no repair — avoids infinite loop)
  - After MAX_REPAIR_ATTEMPTS → spool + llm_output_invalid event

Stdlib only — no jsonschema dependency (simple field-level validation).

Usage:
    from tools.lib.json_schema_guard import validate_output, build_repair_prompt
    from tools.lib.json_schema_guard import validate_and_gate, LLMOutputResult

    # Simple validation
    errors = validate_output(llm_result, schema)
    if errors:
        repair_prompt = build_repair_prompt(llm_result, schema, errors)

    # Full pipeline with quality gates
    result = validate_and_gate(llm_result, schema, quality_gate_fn)
    if result.needs_repair:
        prompt = result.repair_prompt
    elif result.needs_human:
        spool_for_review(result)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


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


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_REPAIR_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# Validation result (two-tier: schema + quality gate)
# ---------------------------------------------------------------------------

@dataclass
class LLMOutputResult:
    """Result of two-tier validation: schema check + quality gate.

    Possible states:
    - valid=True: passed both schema and quality gate
    - needs_repair=True: schema failed, repair prompt ready (attempt < MAX)
    - needs_human=True: quality gate failed OR repairs exhausted
    """
    valid: bool = False
    parsed: Optional[Dict[str, Any]] = None
    schema_errors: List[SchemaValidationError] = field(default_factory=list)
    quality_issues: List[str] = field(default_factory=list)
    needs_repair: bool = False
    needs_human: bool = False
    repair_prompt: str = ""
    attempt: int = 0
    reason: str = ""

    @property
    def spool_payload(self) -> Dict[str, Any]:
        """Payload for spool/run_event when validation fails permanently."""
        return {
            "event_type": "llm_output_invalid",
            "severity": "WARN",
            "reason": self.reason,
            "attempt": self.attempt,
            "schema_errors": [str(e) for e in self.schema_errors],
            "quality_issues": self.quality_issues,
        }


def validate_and_gate(
    raw_output: str,
    schema: Dict[str, Any],
    quality_gate: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
    *,
    attempt: int = 1,
) -> LLMOutputResult:
    """Two-tier validation: schema check → quality gate.

    Strategy:
    1. Parse JSON from LLM output (handles markdown, preamble).
    2. Validate against schema.
       - If schema fails AND attempt <= MAX_REPAIR_ATTEMPTS: generate repair prompt.
       - If schema fails AND attempt > MAX_REPAIR_ATTEMPTS: needs_human + spool.
    3. If schema passes, run quality gate (if provided).
       - Quality gate failures → needs_human immediately (no repair — avoids loop).
    4. If both pass → valid.

    Args:
        raw_output: Raw LLM response string.
        schema: JSON schema to validate against.
        quality_gate: Optional function(dict) -> list[str] for semantic checks.
        attempt: Current attempt number (1-indexed).

    Returns:
        LLMOutputResult with state and repair prompt if applicable.
    """
    result = LLMOutputResult(attempt=attempt)

    # Step 1: Parse
    parsed, parse_errors = parse_llm_json(raw_output, schema=None)
    if parsed is None:
        if attempt <= MAX_REPAIR_ATTEMPTS:
            result.needs_repair = True
            result.schema_errors = parse_errors
            result.repair_prompt = build_repair_prompt(
                raw_output, schema, parse_errors,
            )
            result.reason = "json_parse_failed"
        else:
            result.needs_human = True
            result.schema_errors = parse_errors
            result.reason = f"json_parse_failed_after_{attempt}_attempts"
        return result

    result.parsed = parsed

    # Step 2: Schema validation
    schema_errors = validate_output(parsed, schema)
    if schema_errors:
        result.schema_errors = schema_errors
        if attempt <= MAX_REPAIR_ATTEMPTS:
            result.needs_repair = True
            result.repair_prompt = build_repair_prompt(
                parsed, schema, schema_errors,
            )
            result.reason = "schema_validation_failed"
        else:
            result.needs_human = True
            result.reason = f"schema_failed_after_{attempt}_attempts"
        return result

    # Step 3: Quality gate (if provided)
    if quality_gate:
        quality_issues = quality_gate(parsed)
        if quality_issues:
            result.quality_issues = quality_issues
            result.needs_human = True
            result.reason = "quality_gate_failed"
            return result

    # Step 4: Both passed
    result.valid = True
    return result
