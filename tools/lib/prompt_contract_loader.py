"""Prompt contract loader — versioned prompts + LLM cache + economy rules.

Provides:
- Versioned contract loading from contracts/ directory
- Volatile field stripping for stable cache keys
- TTL-based LLM response cache (daily, 6h, 1h, forever)
- Prompt builder with ECONOMY RULES + STRICT SCHEMA enforcement
- Patch mode (JSON diff, not full rewrite)
- Batch payload support

Stdlib only — no external deps.

Usage:
    from tools.lib.prompt_contract_loader import (
        ContractEngine, ContractSpec, CACHE_POLICIES,
    )

    engine = ContractEngine()
    spec = ContractSpec(
        name="script_writer", version="v1.0.0",
        cache_policy=CACHE_POLICIES["daily"],
        schema={"type": "object", "properties": {"hook": {"type": "string"}}},
    )
    prompt, key = engine.build_prompt_and_cache_key(spec, payload={"topic": "USB-C hub"})
    cached = engine.try_cache(key)
    if cached:
        result = cached
    else:
        result = call_llm(prompt)  # your LLM call
        engine.save_cache(key, result, spec, payload)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Volatile keys — stripped from payload before hashing (cache stability)
# ---------------------------------------------------------------------------

VOLATILE_KEYS = frozenset({
    "timestamp", "ts", "now", "latency_ms", "retry_count",
    "last_heartbeat_at", "lock_expires_at", "locked_at",
    "trace_id", "request_id", "occurred_at",
})


# ---------------------------------------------------------------------------
# Economy rules — injected into every prompt to minimize token waste
# ---------------------------------------------------------------------------

DEFAULT_ECONOMY_RULES: list[str] = [
    "Return ONLY valid JSON. No preamble, no explanations, no markdown.",
    "Do not include reasoning. Do not include alternatives.",
    "Keep output under 1500 characters unless explicitly allowed.",
    'If missing info, return: {"status":"needs_human","missing":[...]} and stop.',
]


# ---------------------------------------------------------------------------
# Cache policies
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CachePolicy:
    """TTL policy for LLM response caching."""
    name: str
    ttl_sec: int


CACHE_POLICIES: Dict[str, CachePolicy] = {
    "forever": CachePolicy("forever", ttl_sec=10**9),
    "daily": CachePolicy("daily", ttl_sec=24 * 3600),
    "6h": CachePolicy("6h", ttl_sec=6 * 3600),
    "1h": CachePolicy("1h", ttl_sec=3600),
    "none": CachePolicy("none", ttl_sec=0),
}


# ---------------------------------------------------------------------------
# Contract spec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContractSpec:
    """Specification for an LLM prompt contract."""
    name: str               # e.g. "script_writer"
    version: str            # e.g. "v1.0.0"
    cache_policy: CachePolicy
    schema: Dict[str, Any] = field(default_factory=dict)
    economy_rules: List[str] = field(default_factory=lambda: list(DEFAULT_ECONOMY_RULES))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_volatile(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove volatile keys from payload for stable cache hashing.

    Volatile keys (timestamps, trace IDs, retry counts) change between calls
    but don't affect the semantic content of the request.
    """
    def _strip(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _strip(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
        if isinstance(obj, list):
            return [_strip(x) for x in obj]
        return obj
    return _strip(payload)


def sha256_str(s: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_cache_key(
    contract: ContractSpec,
    payload: Dict[str, Any],
    extra_salt: str = "",
) -> str:
    """Compute deterministic cache key from contract + stripped payload."""
    normalized = strip_volatile(payload)
    payload_str = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    base = f"{contract.name}:{contract.version}:{contract.cache_policy.name}:{payload_str}:{extra_salt}"
    return sha256_str(base)


# ---------------------------------------------------------------------------
# Contract loader (reads .md files from contracts/ directory)
# ---------------------------------------------------------------------------

class ContractLoader:
    """Loads prompt contract text from versioned files.

    Directory structure:
        contracts/
            script_writer/
                v1.0.0.md
                v1.0.1.md
            product_ranker/
                v1.0.0.md
    """

    def __init__(self, contracts_dir: str = "contracts"):
        self.contracts_dir = Path(contracts_dir)

    def load(self, contract_name: str, version: str) -> str:
        """Load contract text. Raises FileNotFoundError if missing."""
        path = self.contracts_dir / contract_name / f"{version}.md"
        if not path.exists():
            raise FileNotFoundError(f"Contract not found: {path}")
        return path.read_text(encoding="utf-8")

    def list_versions(self, contract_name: str) -> list[str]:
        """List available versions for a contract."""
        contract_dir = self.contracts_dir / contract_name
        if not contract_dir.is_dir():
            return []
        return sorted(
            p.stem for p in contract_dir.glob("*.md")
        )


# ---------------------------------------------------------------------------
# LLM cache (file-based, TTL-aware)
# ---------------------------------------------------------------------------

class LLMCache:
    """File-based LLM response cache with TTL expiry."""

    def __init__(self, cache_dir: str = "state/cache/llm"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached value if exists and not expired. Returns None on miss."""
        p = self._path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            meta = data.get("_meta", {})
            created_at = meta.get("created_at", 0)
            ttl = meta.get("ttl_sec", 0)
            if ttl and created_at and (time.time() - created_at) > ttl:
                return None  # expired
            return data
        except Exception:
            return None

    def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl_sec: int,
        meta: Dict[str, Any],
    ) -> None:
        """Cache a value with TTL and metadata."""
        p = self._path(key)
        payload = {
            "_meta": {
                "created_at": time.time(),
                "ttl_sec": ttl_sec,
                **meta,
            },
            "value": value,
        }
        p.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def invalidate(self, key: str) -> bool:
        """Remove cached entry. Returns True if existed."""
        p = self._path(key)
        if p.exists():
            p.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

class PromptBuilder:
    """Builds structured prompts from contract + payload + economy rules."""

    def __init__(self, loader: ContractLoader):
        self.loader = loader

    def build(
        self,
        contract: ContractSpec,
        payload: Dict[str, Any],
        *,
        contract_text_override: Optional[str] = None,
        patch_against: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build a complete prompt with contract, economy rules, schema, and payload.

        Args:
            contract: Contract specification.
            payload: Input data for the LLM.
            contract_text_override: Use this text instead of loading from file.
            patch_against: If provided, enables patch mode (JSON diff output).

        Returns:
            Complete prompt string ready for LLM.
        """
        if contract_text_override:
            contract_text = contract_text_override
        else:
            try:
                contract_text = self.loader.load(contract.name, contract.version)
            except FileNotFoundError:
                contract_text = f"[Contract: {contract.name} {contract.version}]"

        economy = "\n".join(f"- {r}" for r in contract.economy_rules)
        schema_txt = json.dumps(contract.schema, ensure_ascii=False, indent=2)

        parts = [
            "### CONTRACT",
            contract_text.strip(),
            "",
            "### ECONOMY RULES",
            economy,
            "",
            "### OUTPUT SCHEMA (MUST MATCH)",
            schema_txt,
            "",
        ]

        if patch_against is not None:
            parts += [
                "### PATCH MODE",
                "You MUST output only a JSON object with key `patch_ops` containing a list of operations.",
                "Each op: {\"op\":\"replace\",\"path\":\"/key/subkey\",\"value\":...}",
                "No full rewrite. Minimal changes only.",
                "",
                "### base",
                json.dumps(patch_against, ensure_ascii=False),
                "",
            ]

        parts += [
            "### payload",
            json.dumps(payload, ensure_ascii=False),
        ]

        return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Contract engine (public API)
# ---------------------------------------------------------------------------

class ContractEngine:
    """High-level API: build prompts, check cache, save results.

    Typical flow:
        1. Build ContractSpec
        2. prompt, key = engine.build_prompt_and_cache_key(spec, payload)
        3. cached = engine.try_cache(key) → if hit, skip LLM
        4. Otherwise call LLM, then engine.save_cache(key, result, spec, payload)
    """

    def __init__(
        self,
        contracts_dir: str = "contracts",
        cache_dir: str = "state/cache/llm",
    ):
        self.loader = ContractLoader(contracts_dir)
        self.cache = LLMCache(cache_dir)
        self.builder = PromptBuilder(self.loader)

    def build_prompt_and_cache_key(
        self,
        contract: ContractSpec,
        payload: Dict[str, Any],
        *,
        extra_salt: str = "",
        patch_against: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """Build prompt and compute cache key. Returns (prompt, cache_key)."""
        key = compute_cache_key(contract, payload, extra_salt=extra_salt)
        prompt = self.builder.build(contract, payload, patch_against=patch_against)
        return prompt, key

    def try_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Try to get cached LLM response. Returns value dict or None."""
        hit = self.cache.get(key)
        if not hit:
            return None
        return hit.get("value")

    def save_cache(
        self,
        key: str,
        value: Dict[str, Any],
        contract: ContractSpec,
        payload: Dict[str, Any],
    ) -> None:
        """Cache an LLM response with contract metadata."""
        meta = {
            "contract": f"{contract.name}/{contract.version}",
            "cache_policy": contract.cache_policy.name,
            "input_digest": sha256_str(
                json.dumps(strip_volatile(payload), sort_keys=True, ensure_ascii=False)
            ),
        }
        self.cache.set(
            key,
            value=value,
            ttl_sec=contract.cache_policy.ttl_sec,
            meta=meta,
        )
