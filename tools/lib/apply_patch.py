"""JSON Patch applicator — minimal RFC 6902-style patching for LLM diffs.

Supports a subset of JSON Patch operations (replace, add, remove)
for applying LLM-generated diffs to existing objects. This is far more
robust than text-based "line X" diffing.

Stdlib only — no external deps.

Usage:
    from tools.lib.apply_patch import apply_patch, PatchError

    base = {"script": {"hook": "old hook", "cta": "Buy now"}, "facts": {"price": 99}}
    ops = [
        {"op": "replace", "path": "/script/hook", "value": "This changed everything"},
        {"op": "replace", "path": "/facts/price", "value": 199},
    ]
    result = apply_patch(base, ops)
    # result["script"]["hook"] == "This changed everything"
    # result["facts"]["price"] == 199

LLM integration:
    The LLM returns {"status":"ok","patch_ops":[...]} in patch mode.
    Your code does: result = apply_patch(base_object, response["patch_ops"])
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List


class PatchError(ValueError):
    """Raised when a patch operation fails."""
    pass


def _resolve_path(obj: Any, path: str) -> tuple[Any, str]:
    """Resolve a JSON Pointer path to (parent, final_key).

    Path format: "/key/subkey/0/deep" (RFC 6901 JSON Pointer).
    Returns the parent container and the final key/index.
    """
    if not path.startswith("/"):
        raise PatchError(f"Path must start with '/': {path}")

    parts = path[1:].split("/")
    if not parts or parts == [""]:
        raise PatchError(f"Empty path: {path}")

    # Unescape JSON Pointer escapes (~1 = /, ~0 = ~)
    parts = [p.replace("~1", "/").replace("~0", "~") for p in parts]

    current = obj
    for part in parts[:-1]:
        if isinstance(current, dict):
            if part not in current:
                raise PatchError(f"Key not found: '{part}' in path '{path}'")
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                raise PatchError(f"List index must be integer: '{part}' in path '{path}'")
            if idx < 0 or idx >= len(current):
                raise PatchError(f"List index out of range: {idx} in path '{path}'")
            current = current[idx]
        else:
            raise PatchError(f"Cannot traverse into {type(current).__name__} at '{part}' in path '{path}'")

    return current, parts[-1]


def _apply_one(obj: Any, op: Dict[str, Any]) -> Any:
    """Apply a single patch operation to obj (mutates in place)."""
    operation = op.get("op", "")
    path = op.get("path", "")

    if not operation:
        raise PatchError(f"Missing 'op' in patch operation: {op}")
    if not path:
        raise PatchError(f"Missing 'path' in patch operation: {op}")

    if operation == "replace":
        if "value" not in op:
            raise PatchError(f"'replace' requires 'value': {op}")
        parent, key = _resolve_path(obj, path)
        if isinstance(parent, dict):
            if key not in parent:
                raise PatchError(f"Key '{key}' not found for replace at '{path}'")
            parent[key] = op["value"]
        elif isinstance(parent, list):
            idx = int(key)
            if idx < 0 or idx >= len(parent):
                raise PatchError(f"Index {idx} out of range for replace at '{path}'")
            parent[idx] = op["value"]
        else:
            raise PatchError(f"Cannot replace in {type(parent).__name__} at '{path}'")

    elif operation == "add":
        if "value" not in op:
            raise PatchError(f"'add' requires 'value': {op}")
        parent, key = _resolve_path(obj, path)
        if isinstance(parent, dict):
            parent[key] = op["value"]
        elif isinstance(parent, list):
            if key == "-":
                parent.append(op["value"])
            else:
                idx = int(key)
                parent.insert(idx, op["value"])
        else:
            raise PatchError(f"Cannot add to {type(parent).__name__} at '{path}'")

    elif operation == "remove":
        parent, key = _resolve_path(obj, path)
        if isinstance(parent, dict):
            if key not in parent:
                raise PatchError(f"Key '{key}' not found for remove at '{path}'")
            del parent[key]
        elif isinstance(parent, list):
            idx = int(key)
            if idx < 0 or idx >= len(parent):
                raise PatchError(f"Index {idx} out of range for remove at '{path}'")
            del parent[idx]
        else:
            raise PatchError(f"Cannot remove from {type(parent).__name__} at '{path}'")

    else:
        raise PatchError(f"Unsupported operation: '{operation}' (use replace/add/remove)")

    return obj


def apply_patch(
    base: Dict[str, Any],
    ops: List[Dict[str, Any]],
    *,
    strict: bool = True,
    allowed_prefixes: tuple[str, ...] | None = None,
    disallowed_ops: frozenset[str] | None = None,
    max_ops: int = 20,
) -> Dict[str, Any]:
    """Apply a list of JSON Patch operations to a base object.

    Includes guardrails to prevent destructive or unauthorized patches:
    - allowed_prefixes: Only allow paths starting with these prefixes
    - disallowed_ops: Block specific operations (e.g. "remove")
    - max_ops: Maximum number of operations allowed

    Args:
        base: The original object to patch.
        ops: List of patch operations, each with {op, path, value?}.
        strict: If True (default), any failed op raises PatchError.
                If False, failed ops are skipped with a warning in _errors.
        allowed_prefixes: Tuple of allowed path prefixes (e.g. ("/script", "/facts")).
                         None = all paths allowed.
        disallowed_ops: Set of blocked operation types (e.g. frozenset({"remove"})).
                       None = all ops allowed.
        max_ops: Maximum number of operations (default 20).

    Returns:
        A new dict with patches applied (original is not mutated).
    """
    if len(ops) > max_ops:
        raise PatchError(f"Too many patch operations: {len(ops)} > {max_ops}")

    # Pre-validate guardrails before applying any ops
    for i, op in enumerate(ops):
        operation = op.get("op", "")
        path = op.get("path", "")

        if disallowed_ops and operation in disallowed_ops:
            raise PatchError(f"op[{i}]: disallowed operation '{operation}'")

        if allowed_prefixes and path:
            if not any(path.startswith(pfx) for pfx in allowed_prefixes):
                raise PatchError(f"op[{i}]: path '{path}' not in allowed prefixes")

    result = copy.deepcopy(base)
    errors: list[str] = []

    for i, op in enumerate(ops):
        try:
            _apply_one(result, op)
        except PatchError as e:
            if strict:
                raise
            errors.append(f"op[{i}]: {e}")

    if errors:
        result.setdefault("_patch_errors", errors)

    return result


def extract_patch_ops(llm_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract patch_ops from an LLM response.

    Expects: {"status": "ok", "patch_ops": [...]}
    Returns the list of operations, or empty list if not found.
    """
    if not isinstance(llm_response, dict):
        return []
    ops = llm_response.get("patch_ops", [])
    if not isinstance(ops, list):
        return []
    return ops


# ---------------------------------------------------------------------------
# Coercion helpers — cheap fixes before LLM repair
# ---------------------------------------------------------------------------

def coerce_price(text: str) -> float | None:
    """Try to parse a price from text without LLM.

    Handles: "$199.99", "R$ 1.299,90", "199", "US$ 49.00"
    Returns float or None if unparseable.
    """
    import re
    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[A-Za-z$\s]", "", text.strip())
    if not cleaned:
        return None

    # Handle Brazilian format: 1.299,90 → 1299.90
    if "," in cleaned and "." in cleaned:
        # If comma is after last dot, it's decimal separator (BR/EU)
        last_comma = cleaned.rfind(",")
        last_dot = cleaned.rfind(".")
        if last_comma > last_dot:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    # Handle comma-only decimal: "199,99" → "199.99"
    elif "," in cleaned and "." not in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned)
    except ValueError:
        return None


def coerce_rating(text: str) -> float | None:
    """Try to parse a rating from text without LLM.

    Handles: "4.7 out of 5", "4.7/5", "4,7", "4.7"
    Returns float or None.
    """
    import re
    # "4.7 out of 5" or "4.7/5"
    m = re.search(r"(\d+[.,]\d+)\s*(?:out of|/)\s*\d+", text)
    if m:
        return float(m.group(1).replace(",", "."))
    # Plain number
    m = re.search(r"\d+[.,]\d+", text)
    if m:
        return float(m.group(0).replace(",", "."))
    m = re.search(r"\d+", text)
    if m:
        return float(m.group(0))
    return None


def coerce_reviews(text: str) -> int | None:
    """Try to parse review count from text without LLM.

    Handles: "1,234 ratings", "1234", "1.234", "12K"
    Returns int or None.
    """
    import re
    # "12K" or "1.2K"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[Kk]", text)
    if m:
        return int(float(m.group(1).replace(",", ".")) * 1000)
    # "1,234" or "1.234" (thousands separator)
    cleaned = re.sub(r"[^\d.,]", "", text)
    if cleaned:
        # Remove thousands separators
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", "")
        elif "." in cleaned and "," not in cleaned:
            # Could be thousands separator (1.234) if no decimal
            parts = cleaned.split(".")
            if all(len(p) == 3 for p in parts[1:]):
                cleaned = cleaned.replace(".", "")
        try:
            return int(float(cleaned))
        except ValueError:
            pass
    return None
