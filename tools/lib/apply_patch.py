"""JSON Patch applicator — minimal RFC 6902-style patching for LLM diffs.

Supports a subset of JSON Patch operations (replace, add, remove)
for applying LLM-generated diffs to existing objects. This is far more
robust than text-based "line X" diffing.

Includes ScriptPatchPolicy for outline/script patching with:
- Wildcard path matching ({i} placeholders for array indices)
- Forbidden path protection (asin, slot, product_key, versions)
- Post-patch constraint validation (hook chars, point words)
- Patch audit event generation

FinalScriptPatchPolicy for Layer 2 script patching with:
- Allowed paths: intro, segments/{i}/(heading|body|verdict_line|transition), outro
- Forbidden: asin, slot, product_key, versions, computed fields

Patch idempotency (SRE-grade):
- canonical_json() for stable serialization
- compute_base_hash() for document identity
- compute_patch_id() for dedup (base_hash + ops hash)

Stdlib only — no external deps.

Usage:
    from tools.lib.apply_patch import apply_patch, PatchError
    from tools.lib.apply_patch import apply_script_patch, ScriptPatchPolicy
    from tools.lib.apply_patch import apply_final_script_patch, FinalScriptPatchPolicy
    from tools.lib.apply_patch import canonical_json, compute_base_hash, compute_patch_id

    # Basic patching
    base = {"script": {"hook": "old hook"}, "facts": {"price": 99}}
    ops = [{"op": "replace", "path": "/script/hook", "value": "new"}]
    result = apply_patch(base, ops)

    # Script-aware patching with guardrails
    outline = {"outline": {"hook": "old", "products": [...], "cta": "Buy now"}}
    result = apply_script_patch(outline, patch_ops)

    # Final script patching (Layer 2)
    script_doc = {"script": {"intro": "...", "segments": [...], "outro": "..."}}
    result = apply_final_script_patch(script_doc, patch_ops)

LLM integration:
    The LLM returns {"status":"ok","patch_ops":[...]} in patch mode.
    Your code does: result = apply_patch(base_object, response["patch_ops"])
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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


# ---------------------------------------------------------------------------
# Script Patch Policy — wildcard path matching + outline constraints
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScriptPatchPolicy:
    """Policy for patching script outlines with guardrails.

    Uses wildcard path patterns ({i}, {j} for array indices) instead of
    simple prefix matching, providing fine-grained control over what
    the LLM is allowed to modify.
    """
    allowed_ops: tuple[str, ...] = ("replace",)
    max_ops: int = 5

    # Paths with {i}/{j} wildcards for array indices
    allowed_paths: tuple[str, ...] = (
        "/outline/hook",
        "/outline/products/{i}/angle",
        "/outline/products/{i}/points",
        "/outline/products/{i}/points/{j}",
        "/outline/products/{i}/verdict",
        "/outline/cta",
    )

    # Paths that must NEVER be modified (even if allowed_paths has a bug)
    forbidden_paths: tuple[str, ...] = (
        "/outline/products/{i}/asin",
        "/outline/products/{i}/slot",
        "/outline/products/{i}/product_key",
        "/contract_version",
        "/outline_version",
    )

    # Post-patch size limits
    max_hook_chars: int = 160
    max_angle_chars: int = 80
    max_point_words: int = 10
    max_points_per_product: int = 5
    max_verdict_chars: int = 60
    max_cta_chars: int = 120


def _wildcard_match(pattern: str, path: str) -> bool:
    """Match a path against a pattern with {i}/{j} wildcards for numeric indices."""
    p_parts = pattern.strip("/").split("/")
    a_parts = path.strip("/").split("/")
    if len(p_parts) != len(a_parts):
        return False
    for pp, ap in zip(p_parts, a_parts):
        if pp in ("{i}", "{j}"):
            if not ap.isdigit():
                return False
        elif pp != ap:
            return False
    return True


def _is_script_path_allowed(path: str, policy: ScriptPatchPolicy) -> bool:
    """Check if path is in the allowed list (with wildcard matching)."""
    return any(_wildcard_match(pat, path) for pat in policy.allowed_paths)


def _is_script_path_forbidden(path: str, policy: ScriptPatchPolicy) -> bool:
    """Check if path is in the forbidden list (with wildcard matching)."""
    return any(_wildcard_match(pat, path) for pat in policy.forbidden_paths)


def validate_script_patch_ops(
    ops: List[Dict[str, Any]],
    policy: ScriptPatchPolicy,
) -> None:
    """Validate patch operations against ScriptPatchPolicy.

    Raises PatchError if any op violates the policy.
    Checks: allowed ops, max ops, forbidden paths, allowed paths.
    """
    if not isinstance(ops, list) or not ops:
        raise PatchError("Patch must be a non-empty list of operations")

    if len(ops) > policy.max_ops:
        raise PatchError(f"Too many ops: {len(ops)} > {policy.max_ops}")

    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise PatchError(f"op[{i}]: must be an object")

        operation = op.get("op", "")
        if operation not in policy.allowed_ops:
            raise PatchError(f"op[{i}]: operation '{operation}' not allowed")

        path = op.get("path", "")
        if not isinstance(path, str) or not path.startswith("/"):
            raise PatchError(f"op[{i}]: invalid path")

        if _is_script_path_forbidden(path, policy):
            raise PatchError(f"op[{i}]: forbidden path '{path}'")

        if not _is_script_path_allowed(path, policy):
            raise PatchError(f"op[{i}]: path '{path}' not in allowlist")

        if operation == "replace" and "value" not in op:
            raise PatchError(f"op[{i}]: 'replace' requires 'value'")


def validate_outline_constraints(
    doc: Dict[str, Any],
    policy: ScriptPatchPolicy,
) -> None:
    """Validate outline field sizes after patch application.

    Raises PatchError if any field exceeds size limits.
    """
    outline = doc.get("outline", {})
    if not isinstance(outline, dict):
        return

    # Hook length
    hook = outline.get("hook", "")
    if isinstance(hook, str) and len(hook) > policy.max_hook_chars:
        raise PatchError(
            f"hook too long after patch: {len(hook)} chars "
            f"(max {policy.max_hook_chars})"
        )

    # CTA length
    cta = outline.get("cta", "")
    if isinstance(cta, str) and len(cta) > policy.max_cta_chars:
        raise PatchError(
            f"cta too long after patch: {len(cta)} chars "
            f"(max {policy.max_cta_chars})"
        )

    # Products
    products = outline.get("products", [])
    if not isinstance(products, list):
        return

    for i, p in enumerate(products):
        if not isinstance(p, dict):
            continue

        # Angle length
        angle = p.get("angle", "")
        if isinstance(angle, str) and len(angle) > policy.max_angle_chars:
            raise PatchError(
                f"products[{i}].angle too long: {len(angle)} chars "
                f"(max {policy.max_angle_chars})"
            )

        # Verdict length
        verdict = p.get("verdict", "")
        if isinstance(verdict, str) and len(verdict) > policy.max_verdict_chars:
            raise PatchError(
                f"products[{i}].verdict too long: {len(verdict)} chars "
                f"(max {policy.max_verdict_chars})"
            )

        # Points
        points = p.get("points", [])
        if isinstance(points, list):
            if len(points) > policy.max_points_per_product:
                raise PatchError(
                    f"products[{i}]: too many points "
                    f"({len(points)} > {policy.max_points_per_product})"
                )
            for j, pt in enumerate(points):
                if isinstance(pt, str):
                    words = len(pt.split())
                    if words > policy.max_point_words:
                        raise PatchError(
                            f"products[{i}].points[{j}]: "
                            f"{words} words (max {policy.max_point_words})"
                        )


def apply_script_patch(
    base_doc: Dict[str, Any],
    patch_ops: List[Dict[str, Any]],
    policy: Optional[ScriptPatchPolicy] = None,
) -> Dict[str, Any]:
    """Apply a validated script patch with pre- and post-validation.

    1. Validate ops against policy (allowed ops, paths, forbidden paths)
    2. Apply patch (deep copy, no mutation)
    3. Validate outline constraints post-patch (field sizes)

    Args:
        base_doc: The current outline/script document.
        patch_ops: List of JSON Patch operations from LLM.
        policy: ScriptPatchPolicy (uses defaults if None).

    Returns:
        New document with patches applied.

    Raises:
        PatchError if validation fails at any step.
    """
    policy = policy or ScriptPatchPolicy()

    # Pre-validation
    validate_script_patch_ops(patch_ops, policy)

    # Apply
    result = copy.deepcopy(base_doc)
    for op in patch_ops:
        _apply_one(result, op)

    # Post-validation
    validate_outline_constraints(result, policy)

    return result


def make_patch_audit(
    *,
    run_id: str,
    patch_ops: List[Dict[str, Any]],
    scope: str,
    reason: str,
    contract_version: str,
) -> Dict[str, Any]:
    """Build a run_event payload for an applied script patch.

    Args:
        run_id: Current run UUID.
        patch_ops: The operations that were applied.
        scope: What was patched (e.g. "hook", "best_value_block").
        reason: Why (e.g. "too generic", "more punchy").
        contract_version: e.g. "script_writer/v0.1.0".

    Returns:
        Dict ready for insert_event / spool_event.
    """
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "script_patch_applied",
        "severity": "INFO",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "run_id": run_id,
            "scope": scope,
            "reason": reason,
            "contract_version": contract_version,
            "ops_count": len(patch_ops),
            "patch_ops": patch_ops,
        },
    }


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


# ---------------------------------------------------------------------------
# Patch idempotency — canonical hashing + dedup
# ---------------------------------------------------------------------------

def canonical_json(obj: Any) -> str:
    """Produce a canonical JSON string for stable hashing.

    Rules:
    - sort_keys=True (deterministic key order)
    - compact separators (no extra whitespace)
    - ensure_ascii=False (preserve unicode)
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_base_hash(doc: Any) -> str:
    """Compute SHA-256 hash of a document using canonical JSON.

    Use this to stamp a document before patching — the hash uniquely
    identifies the base state that the patch was generated against.
    """
    return hashlib.sha256(canonical_json(doc).encode("utf-8")).hexdigest()


def compute_patch_id(base_hash: str, patch_ops: List[Dict[str, Any]]) -> str:
    """Compute a deterministic patch ID for idempotency.

    patch_id = sha256(base_hash + canonical_json(ops))

    If the same patch is applied to the same base document twice,
    it produces the same patch_id — enabling dedup at the DB layer.
    """
    seed = base_hash + canonical_json(patch_ops)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def validate_base_hash(
    doc: Any,
    expected_hash: str,
) -> bool:
    """Check if a document matches the expected base hash.

    Returns True if hash matches (safe to apply patch).
    Returns False if stale (document changed since patch was generated).
    """
    return compute_base_hash(doc) == expected_hash


# ---------------------------------------------------------------------------
# Final Script Patch Policy — Layer 2 script patching
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FinalScriptPatchPolicy:
    """Policy for patching final scripts (Layer 2) with guardrails.

    Similar to ScriptPatchPolicy but for the rendered script structure:
    - Allowed: intro, heading, body, verdict_line, transition, outro
    - Forbidden: asin, slot, product_key, versions, computed fields
    """
    allowed_ops: tuple[str, ...] = ("replace",)
    max_ops: int = 5

    allowed_paths: tuple[str, ...] = (
        "/script/intro",
        "/script/segments/{i}/heading",
        "/script/segments/{i}/body",
        "/script/segments/{i}/verdict_line",
        "/script/segments/{i}/transition",
        "/script/outro",
    )

    forbidden_paths: tuple[str, ...] = (
        "/script/segments/{i}/asin",
        "/script/segments/{i}/slot",
        "/script/segments/{i}/product_key",
        "/script/segments/{i}/estimated_words",
        "/contract_version",
        "/script_version",
        "/total_word_count",
        "/estimated_duration_sec",
    )

    # Post-patch size limits (from contract)
    max_intro_chars: int = 300
    max_heading_chars: int = 80
    max_body_chars: int = 600
    max_verdict_line_chars: int = 80
    max_transition_chars: int = 80
    max_outro_chars: int = 250


def validate_final_script_patch_ops(
    ops: List[Dict[str, Any]],
    policy: FinalScriptPatchPolicy,
) -> None:
    """Validate patch operations against FinalScriptPatchPolicy.

    Raises PatchError if any op violates the policy.
    """
    if not isinstance(ops, list) or not ops:
        raise PatchError("Patch must be a non-empty list of operations")

    if len(ops) > policy.max_ops:
        raise PatchError(f"Too many ops: {len(ops)} > {policy.max_ops}")

    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise PatchError(f"op[{i}]: must be an object")

        operation = op.get("op", "")
        if operation not in policy.allowed_ops:
            raise PatchError(f"op[{i}]: operation '{operation}' not allowed")

        path = op.get("path", "")
        if not isinstance(path, str) or not path.startswith("/"):
            raise PatchError(f"op[{i}]: invalid path")

        if _is_final_script_path_forbidden(path, policy):
            raise PatchError(f"op[{i}]: forbidden path '{path}'")

        if not _is_final_script_path_allowed(path, policy):
            raise PatchError(f"op[{i}]: path '{path}' not in allowlist")

        if operation == "replace" and "value" not in op:
            raise PatchError(f"op[{i}]: 'replace' requires 'value'")


def _is_final_script_path_allowed(path: str, policy: FinalScriptPatchPolicy) -> bool:
    """Check if path is in the final script allowed list."""
    return any(_wildcard_match(pat, path) for pat in policy.allowed_paths)


def _is_final_script_path_forbidden(path: str, policy: FinalScriptPatchPolicy) -> bool:
    """Check if path is in the final script forbidden list."""
    return any(_wildcard_match(pat, path) for pat in policy.forbidden_paths)


def validate_final_script_constraints(
    doc: Dict[str, Any],
    policy: FinalScriptPatchPolicy,
) -> None:
    """Validate final script field sizes after patch application.

    Raises PatchError if any field exceeds size limits.
    """
    script = doc.get("script", {})
    if not isinstance(script, dict):
        return

    # Intro length
    intro = script.get("intro", "")
    if isinstance(intro, str) and len(intro) > policy.max_intro_chars:
        raise PatchError(
            f"intro too long after patch: {len(intro)} chars "
            f"(max {policy.max_intro_chars})"
        )

    # Outro length
    outro = script.get("outro", "")
    if isinstance(outro, str) and len(outro) > policy.max_outro_chars:
        raise PatchError(
            f"outro too long after patch: {len(outro)} chars "
            f"(max {policy.max_outro_chars})"
        )

    # Segments
    segments = script.get("segments", [])
    if not isinstance(segments, list):
        return

    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue

        heading = seg.get("heading", "")
        if isinstance(heading, str) and len(heading) > policy.max_heading_chars:
            raise PatchError(
                f"segments[{i}].heading too long: {len(heading)} chars "
                f"(max {policy.max_heading_chars})"
            )

        body = seg.get("body", "")
        if isinstance(body, str) and len(body) > policy.max_body_chars:
            raise PatchError(
                f"segments[{i}].body too long: {len(body)} chars "
                f"(max {policy.max_body_chars})"
            )

        verdict = seg.get("verdict_line", "")
        if isinstance(verdict, str) and len(verdict) > policy.max_verdict_line_chars:
            raise PatchError(
                f"segments[{i}].verdict_line too long: {len(verdict)} chars "
                f"(max {policy.max_verdict_line_chars})"
            )

        transition = seg.get("transition", "")
        if isinstance(transition, str) and len(transition) > policy.max_transition_chars:
            raise PatchError(
                f"segments[{i}].transition too long: {len(transition)} chars "
                f"(max {policy.max_transition_chars})"
            )


def apply_final_script_patch(
    base_doc: Dict[str, Any],
    patch_ops: List[Dict[str, Any]],
    policy: Optional[FinalScriptPatchPolicy] = None,
    *,
    expected_base_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply a validated final script patch with pre- and post-validation.

    1. (Optional) Verify base_hash matches — reject stale patches
    2. Validate ops against policy (allowed ops, paths, forbidden paths)
    3. Apply patch (deep copy, no mutation)
    4. Validate script constraints post-patch (field sizes)

    Args:
        base_doc: The current script document.
        patch_ops: List of JSON Patch operations from LLM.
        policy: FinalScriptPatchPolicy (uses defaults if None).
        expected_base_hash: If provided, verify document hasn't changed.

    Returns:
        New document with patches applied.

    Raises:
        PatchError if validation fails at any step.
    """
    policy = policy or FinalScriptPatchPolicy()

    # Stale patch check
    if expected_base_hash and not validate_base_hash(base_doc, expected_base_hash):
        raise PatchError(
            f"Stale patch: base document changed since patch was generated "
            f"(expected hash {expected_base_hash[:12]}...)"
        )

    # Pre-validation
    validate_final_script_patch_ops(patch_ops, policy)

    # Apply
    result = copy.deepcopy(base_doc)
    for op in patch_ops:
        _apply_one(result, op)

    # Post-validation
    validate_final_script_constraints(result, policy)

    return result


# ---------------------------------------------------------------------------
# Voice Script Patch Policy — Layer 3 voice script patching
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VoicePatchPolicy:
    """Policy for patching voice scripts (Layer 3).

    Allowed edits: segment text, lip_sync_hint, duration, stability, style.
    Forbidden: segment_id, kind, product_key, voice_id, model, filenames.
    """
    allowed_ops: tuple[str, ...] = ("replace",)
    max_ops: int = 5

    allowed_paths: tuple[str, ...] = (
        "/segments/{i}/text",
        "/segments/{i}/lip_sync_hint",
        "/segments/{i}/approx_duration_sec",
        "/audio_plan/{i}/stability",
        "/audio_plan/{i}/style",
    )

    forbidden_paths: tuple[str, ...] = (
        "/segments/{i}/segment_id",
        "/segments/{i}/kind",
        "/segments/{i}/product_key",
        "/audio_plan/{i}/segment_id",
        "/audio_plan/{i}/voice_id",
        "/audio_plan/{i}/model",
        "/audio_plan/{i}/output_filename",
        "/contract_version",
        "/total_duration_sec",
    )

    max_text_chars: int = 500
    max_segment_duration_sec: int = 30


def apply_voice_patch(
    base_doc: Dict[str, Any],
    patch_ops: List[Dict[str, Any]],
    policy: Optional[VoicePatchPolicy] = None,
    *,
    expected_base_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply a validated voice script patch with pre- and post-validation.

    Same pattern as apply_final_script_patch but for Layer 3.
    """
    policy = policy or VoicePatchPolicy()

    # Stale patch check
    if expected_base_hash and not validate_base_hash(base_doc, expected_base_hash):
        raise PatchError(
            f"Stale patch: base document changed since patch was generated "
            f"(expected hash {expected_base_hash[:12]}...)"
        )

    # Pre-validation
    if not isinstance(patch_ops, list) or not patch_ops:
        raise PatchError("Patch must be a non-empty list of operations")
    if len(patch_ops) > policy.max_ops:
        raise PatchError(f"Too many ops: {len(patch_ops)} > {policy.max_ops}")

    for i, op in enumerate(patch_ops):
        if not isinstance(op, dict):
            raise PatchError(f"op[{i}]: must be an object")
        operation = op.get("op", "")
        if operation not in policy.allowed_ops:
            raise PatchError(f"op[{i}]: operation '{operation}' not allowed")
        path = op.get("path", "")
        if not isinstance(path, str) or not path.startswith("/"):
            raise PatchError(f"op[{i}]: invalid path")
        if any(_wildcard_match(p, path) for p in policy.forbidden_paths):
            raise PatchError(f"op[{i}]: forbidden path '{path}'")
        if not any(_wildcard_match(p, path) for p in policy.allowed_paths):
            raise PatchError(f"op[{i}]: path '{path}' not in allowlist")
        if operation == "replace" and "value" not in op:
            raise PatchError(f"op[{i}]: 'replace' requires 'value'")

    # Apply
    result = copy.deepcopy(base_doc)
    for op in patch_ops:
        _apply_one(result, op)

    # Post-validation: text length and duration bounds
    for i, seg in enumerate(result.get("segments", [])):
        if not isinstance(seg, dict):
            continue
        text = seg.get("text", "")
        if isinstance(text, str) and len(text) > policy.max_text_chars:
            raise PatchError(
                f"segments[{i}].text too long after patch: {len(text)} chars "
                f"(max {policy.max_text_chars})"
            )
        dur = seg.get("approx_duration_sec", 0)
        if isinstance(dur, int) and dur > policy.max_segment_duration_sec:
            raise PatchError(
                f"segments[{i}].approx_duration_sec too high: {dur}s "
                f"(max {policy.max_segment_duration_sec})"
            )

    return result
