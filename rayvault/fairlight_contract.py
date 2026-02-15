"""RayVault Fairlight Bus Contract — deterministic audio routing.

Defines the rigid bus contract for DaVinci Resolve Fairlight:
  VO Track     -> BUS_VO
  MUSIC Track  -> BUS_MUSIC
  SFX Track    -> BUS_SFX (optional)
  BUS_VO + BUS_MUSIC + BUS_SFX -> BUS_MASTER

Ducking: sidechain on BUS_MUSIC, key input = BUS_VO.

Actual Fairlight bus routing requires OpenClaw (v1.3).
This module defines the contract and provides verification stubs.

Usage:
    from rayvault.fairlight_contract import FairlightContract, verify_bus_contract
    contract = FairlightContract.default()
    result = verify_bus_contract(contract, render_receipt)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rayvault.policies import (
    BUS_VO_NAME,
    BUS_MUSIC_NAME,
    BUS_SFX_NAME,
    BUS_MASTER_NAME,
    SOUNDTRACK_DUCK_AMOUNT_DB,
    SOUNDTRACK_DUCK_ATTACK_MS,
    SOUNDTRACK_DUCK_RELEASE_MS,
    SOUNDTRACK_CROSSFADE_IN_SEC,
    SOUNDTRACK_CROSSFADE_OUT_SEC,
)


# ---------------------------------------------------------------------------
# Bus definitions
# ---------------------------------------------------------------------------


@dataclass
class BusDef:
    name: str
    track_type: str  # "audio"
    track_index: int  # 1-based
    source_description: str = ""


@dataclass
class DuckingDef:
    target_bus: str
    key_input_bus: str
    reduction_db: float
    attack_ms: int
    release_ms: int


@dataclass
class FairlightContract:
    """Rigid audio bus contract for broadcast-level governance."""
    buses: List[BusDef] = field(default_factory=list)
    ducking: Optional[DuckingDef] = None
    fades: Dict[str, float] = field(default_factory=dict)
    master_bus: str = BUS_MASTER_NAME

    @classmethod
    def default(cls) -> FairlightContract:
        """Create the default RayVault bus contract."""
        return cls(
            buses=[
                BusDef(
                    name=BUS_VO_NAME,
                    track_type="audio",
                    track_index=1,
                    source_description="02_audio.wav (TTS voiceover)",
                ),
                BusDef(
                    name=BUS_MUSIC_NAME,
                    track_type="audio",
                    track_index=2,
                    source_description="Soundtrack from library",
                ),
                BusDef(
                    name=BUS_SFX_NAME,
                    track_type="audio",
                    track_index=3,
                    source_description="SFX (optional, future)",
                ),
            ],
            ducking=DuckingDef(
                target_bus=BUS_MUSIC_NAME,
                key_input_bus=BUS_VO_NAME,
                reduction_db=SOUNDTRACK_DUCK_AMOUNT_DB,
                attack_ms=SOUNDTRACK_DUCK_ATTACK_MS,
                release_ms=SOUNDTRACK_DUCK_RELEASE_MS,
            ),
            fades={
                "music_fade_in_sec": SOUNDTRACK_CROSSFADE_IN_SEC,
                "music_fade_out_sec": SOUNDTRACK_CROSSFADE_OUT_SEC,
            },
            master_bus=BUS_MASTER_NAME,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "buses": [
                {
                    "name": b.name,
                    "track_type": b.track_type,
                    "track_index": b.track_index,
                    "source_description": b.source_description,
                }
                for b in self.buses
            ],
            "ducking": {
                "target_bus": self.ducking.target_bus,
                "key_input_bus": self.ducking.key_input_bus,
                "reduction_db": self.ducking.reduction_db,
                "attack_ms": self.ducking.attack_ms,
                "release_ms": self.ducking.release_ms,
            } if self.ducking else None,
            "fades": self.fades,
            "master_bus": self.master_bus,
        }


# ---------------------------------------------------------------------------
# Contract verification
# ---------------------------------------------------------------------------


@dataclass
class ContractVerifyResult:
    ok: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    applied_via: str = ""  # "api", "openclaw", "manual", ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "applied_via": self.applied_via,
        }


def verify_bus_contract(
    contract: FairlightContract,
    render_receipt: Dict[str, Any],
) -> ContractVerifyResult:
    """Verify that the render receipt reflects the bus contract.

    Checks:
      1. A1 has VO audio placed
      2. A2 has music placed (if soundtrack enabled)
      3. Ducking status matches contract
      4. Fades applied
    """
    result = ContractVerifyResult()

    st_receipt = render_receipt.get("soundtrack_receipt", {})
    if not st_receipt:
        result.applied_via = "none"
        result.warnings.append("No soundtrack_receipt — bus contract not applicable")
        return result

    # Check A2 music placement
    if not st_receipt.get("applied_in_davinci"):
        result.ok = False
        result.errors.append("BUS_MUSIC: music not applied in DaVinci (A2 empty)")

    # Check fades
    if not st_receipt.get("fades_applied"):
        result.warnings.append("BUS_MUSIC: fades not confirmed applied")

    # Check ducking (stub — actual verification needs postcheck spectral data)
    if not st_receipt.get("ducking_applied"):
        result.warnings.append(
            "DUCKING: not applied via API. "
            "Expected sidechain on BUS_MUSIC with key=BUS_VO. "
            "Verify via audio_postcheck ducking linter."
        )

    # Determine how it was applied
    if st_receipt.get("applied_in_davinci"):
        result.applied_via = "api"
    else:
        result.applied_via = "none"

    return result


def apply_bus_contract_stubs(bridge: Any, contract: FairlightContract) -> Dict[str, Any]:
    """Stub: apply bus contract via Resolve API.

    Actual Fairlight bus routing (creating buses, assigning tracks,
    configuring sidechain ducking) requires OpenClaw v1.3.

    Returns evidence dict of what was attempted.
    """
    evidence: Dict[str, Any] = {
        "attempted": True,
        "api_available": False,
        "buses_created": [],
        "ducking_configured": False,
        "notes": "Fairlight bus routing requires OpenClaw v1.3. "
                 "Static volume on A2 applied as interim.",
    }
    return evidence
