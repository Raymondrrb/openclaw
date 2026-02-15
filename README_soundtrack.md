# RayVault Soundtrack Control Layer

Broadcast-level soundtrack governance for RayVault v1.2.4.

## Architecture

```
soundtrack_library.py    -- Discover + validate licensed tracks
soundtrack_policy.py     -- Enforce tiers, produce SoundtrackDecision
fairlight_contract.py    -- Bus contract (BUS_VO / BUS_MUSIC / BUS_SFX / BUS_MASTER)
audio_postcheck.py       -- Post-render QA (9 gates: LUFS, true peak, VAD, ducking, clipping...)
davinci_assembler.py     -- A2 placement, receipt, bus contract verification
final_validator.py       -- Gate 14 (soundtrack_compliance) + Gate 15 (audio_postcheck)
policies.py              -- All thresholds (single source of truth)
```

## License Tiers

| Tier | Meaning | Auto-publish? | Policy string |
|------|---------|---------------|---------------|
| GREEN | Proof-of-license on disk (purchased, whitelisted) | YES | `AUTO_PUBLISH` |
| AMBER | Rights uncertain (AI-gen, CC-BY, unclear whitelist) | NO | `BLOCKED_FOR_REVIEW` |
| RED | No proof-of-license, unknown origin | NO | `MANUAL_ONLY` |

GREEN tracks **require** `license_proof_path` + `license_proof_sha1` in `track_meta.json`.
AMBER tracks get **safety jitter** (micro pitch/tempo shift for Content ID avoidance).
RED tracks are **never** auto-selected.

## Library Structure

```
state/library/soundtracks/
  epic_cinematic_01/
    audio.wav              # or audio.aif
    track_meta.json
    license.pdf            # GREEN tier proof file
  chill_ambient_02/
    audio.wav
    track_meta.json
```

### track_meta.json Format

```json
{
  "track_id": "epic_cinematic_01",
  "title": "Epic Cinematic Rise",
  "sha1": "a1b2c3d4e5f6...",
  "license_tier": "GREEN",
  "license_proof_path": "license.pdf",
  "license_proof_sha1": "f6e5d4c3b2a1...",
  "mood_tags": ["epic", "cinematic", "dramatic"],
  "bpm": 128.0,
  "motif_group": "epic",
  "source": "artlist",
  "notes": "Purchased 2025-01-15, perpetual license"
}
```

**Required fields:** `track_id`, `sha1`, `license_tier`

**Optional fields:** `title`, `mood_tags`, `bpm`, `motif_group`, `source`, `license_proof_path`, `license_proof_sha1`, `notes`

**Valid sources:** `artlist`, `epidemic`, `custom`, `suno`, `udio`, `other`

## SoundtrackDecision

Produced by `decide_soundtrack()`. Written to manifest at `audio.soundtrack`.

```json
{
  "enabled": true,
  "track_id": "epic_cinematic_01",
  "audio_path": "state/library/soundtracks/epic_cinematic_01/audio.wav",
  "license_tier": "GREEN",
  "track_sha1": "a1b2c3d4...",
  "bpm": 128.0,
  "motif_group": "epic",
  "source": "artlist",
  "target_duration_sec": 600.0,
  "track_duration_sec": 180.0,
  "loop_count": 4,
  "loop_warning": "",
  "gain_db": -18.0,
  "ducking": {
    "amount_db": 12,
    "attack_ms": 20,
    "release_ms": 250
  },
  "fades": {
    "fade_in_sec": 2.0,
    "fade_out_sec": 2.0,
    "loop_crossfade_sec": 2.5
  },
  "fallback_plan": "loop_with_crossfade",
  "chapter_gain_jitter": [
    {"chapter_id": "intro", "gain_offset_db": 0.73, "seed": "a1b2c3d4"},
    {"chapter_id": "p1", "gain_offset_db": -0.42, "seed": "e5f6a7b8"}
  ],
  "safety_jitter": {
    "applied": false,
    "reason": "tier=GREEN, jitter only for AMBER"
  },
  "ai_music_editor": {
    "attempted": false,
    "success": false,
    "before_duration_sec": 180.0,
    "after_duration_sec": null,
    "target_duration_sec": 600.0,
    "eps_sec": 0.25,
    "proof": null
  },
  "conform_cache_key": "abcdef1234567890",
  "tools_requested": ["ai_music_editor", "ai_audio_assistant"],
  "publish_policy": "AUTO_PUBLISH",
  "skip_reason": ""
}
```

## Soundtrack Receipt

Included in `render_receipt.json` at `soundtrack_receipt` after DaVinci assembly.

```json
{
  "soundtrack_receipt": {
    "track_id": "epic_cinematic_01",
    "license_tier": "GREEN",
    "track_sha1": "a1b2c3d4...",
    "bpm": 128.0,
    "motif_group": "epic",
    "source": "artlist",
    "publish_policy": "AUTO_PUBLISH",
    "applied_in_davinci": true,
    "ai_music_editor": {
      "attempted": false,
      "success": false,
      "proof": null
    },
    "ducking_applied": false,
    "fades_applied": true,
    "safety_jitter": {
      "applied": false,
      "reason": "tier=GREEN, jitter only for AMBER"
    },
    "chapter_gain_jitter": [
      {"chapter_id": "intro", "gain_offset_db": 0.73, "seed": "a1b2c3d4"}
    ],
    "conform_cache_key": "abcdef1234567890",
    "fallback_used": "",
    "loop_count": 4,
    "gain_db": -18.0,
    "bus_contract": {
      "ok": true,
      "errors": [],
      "warnings": ["DUCKING: not applied via API..."],
      "applied_via": "api"
    },
    "post_checks": {
      "ok": true,
      "status": "OK",
      "exit_code": 0,
      "errors": [],
      "warnings": [],
      "metrics": {
        "integrated_lufs": -14.1,
        "true_peak_db": -1.8,
        "lra": 5.2,
        "actual_duration_sec": 600.1,
        "expected_duration_sec": 600.0,
        "vad": {
          "noise_floor_db": -45.0,
          "voice_ratio": 0.72,
          "windows_analyzed": 30,
          "windows_with_voice": 22
        }
      }
    }
  }
}
```

## Audio Postcheck Gates

| Gate | Check | Level | Threshold |
|------|-------|-------|-----------|
| A | Integrated LUFS | FAIL | [-15.0, -13.0] |
| B | True Peak | FAIL / WARN | > -1.0 dBTP FAIL, > -1.3 dBTP WARN |
| C | Duration sync | FAIL | within 0.2s |
| D | VAD (voice activity) | INFO | energy-based, 300Hz-3kHz band |
| E | Ducking linter | WARN | presence band (2k-5kHz) reduction < 70% of target |
| F | Spectral clash | WARN | presence band not dropping during VO |
| G | Breath check | FAIL | silence during expected VO interval |
| H | Click/clipping | WARN/FAIL | > 5 regions near 0 dBFS = FAIL |
| I | Silence gaps | WARN | gaps > 300ms |

Output: `publish/soundtrack_postcheck.json` + patched into `render_receipt.json`.

## Fairlight Bus Contract

```
BUS_VO     (A1)  ->  Voiceover (02_audio.wav)
BUS_MUSIC  (A2)  ->  Soundtrack
BUS_SFX    (A3)  ->  SFX (future)
BUS_MASTER        ->  BUS_VO + BUS_MUSIC + BUS_SFX

Ducking: sidechain on BUS_MUSIC, key input = BUS_VO
  reduction: 12 dB
  attack:    20 ms
  release:   250 ms
```

Actual Fairlight bus routing (creating buses, configuring sidechain ducking) requires OpenClaw v1.3. Current code applies static volume on A2 as interim.

## Cooldown (Anti-Repetition)

- **Track cooldown:** Same `track_id` excluded for 5 runs
- **Motif cooldown:** Same `motif_group` excluded for 8 runs
- Scans recent `00_manifest.json` files in `state/runs/`

## Safety Jitter (AMBER Only)

Applied only to AMBER tier tracks to reduce Content ID false positives:

- Pitch shift: 0.9995x (~-0.05%)
- Tempo shift: 1.001x (~+0.1%)

Imperceptible to listeners, enough to differ from source fingerprint.

## Chapter Gain Jitter

Deterministic per-chapter gain variation seeded by `sha1(run_id:track_id:chapter_id)`:

- Range: +/- 1.5 dB
- Reproducible across re-renders (same seed = same jitter)
- Adds natural loudness variation across video sections

## Conform Cache

Conformed tracks (after AI Music Editor processing) are cached at `state/cache/conformed_tracks/`.

- Key: `sha1(track_sha1 : target_duration : bpm)[:16]`
- Format: `<key>.wav`
- Avoids re-processing the same track for identical target durations

## Deferred to OpenClaw v1.3

These features need UI automation via OpenClaw:

- **AI Music Editor:** extend/shorten track to match video duration
- **AI Audio Assistant:** auto-create professional mix
- **AI Detect Music Beats:** place beat markers for cut alignment
- **Music Remixer FX:** rebalance stems for VO clarity
- **Fairlight bus routing:** create buses, assign tracks, configure sidechain

Current code has stubs (`attempted=False`) in the receipt. When OpenClaw is ready, these become integration points.

## Final Validator Gates

- **Gate 14 (soundtrack_compliance):** Checks tier vs publish_policy consistency. RED+AUTO_PUBLISH = FAIL. AMBER without BLOCKED = FAIL. Enabled without audio_proof = FAIL.
- **Gate 15 (audio_postcheck):** Checks `audio_postcheck.ok` in render receipt. FAIL if postcheck failed, WARN if missing.

## Quick Start

```python
from pathlib import Path
from rayvault.soundtrack_library import SoundtrackLibrary
from rayvault.soundtrack_policy import decide_soundtrack, write_decision_to_manifest

# 1. Scan library
lib = SoundtrackLibrary(Path("state/library/soundtracks"))
lib.scan()

# 2. Decide soundtrack
manifest = {"run_id": "RUN_2026_02_15_A", "metadata": {"mood_tags": ["epic"]}}
render_config = {"audio": {"duration_sec": 600.0}, "segments": [...]}
decision = decide_soundtrack(manifest, render_config, lib)

# 3. Write to manifest
write_decision_to_manifest(Path("state/runs/RUN_2026_02_15_A/00_manifest.json"), decision)

# 4. DaVinci assembler picks up audio.soundtrack and places on A2
# 5. Post-render: audio_postcheck runs 9 gates
# 6. final_validator checks Gate 14 + Gate 15
```
