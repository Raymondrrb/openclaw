"""RayVault Policy Constants — single source of truth for all thresholds.

Every gate, validator, and assembler imports from here.
Never hardcode thresholds in individual modules.
"""

# ---------------------------------------------------------------------------
# Duration targets (8-12 minute videos)
# ---------------------------------------------------------------------------

TARGET_MIN_SEC = 480          # 8 minutes minimum
TARGET_MAX_SEC = 720          # 12 minutes maximum
DURATION_TOLERANCE_SEC = 0.2  # ffprobe vs audio duration mismatch tolerance

# ---------------------------------------------------------------------------
# Pacing / editorial
# ---------------------------------------------------------------------------

MAX_STATIC_SECONDS = 18       # No segment may exceed this without visual change
BEAT_MIN_SEC = 6              # Minimum beat (filler segment) duration
BEAT_MAX_SEC = 12             # Maximum beat duration
MIN_SEGMENT_TYPE_VARIETY = 2  # At least N distinct visual modes in product segments

# Motion hygiene
MIN_MOTION_SCALE = 0.06       # Minimum delta_scale to count as visual change
MIN_MOTION_POS_FRAC = 0.04   # Minimum delta_pos as fraction of frame dimension
MOTION_MAX_CONSECUTIVE_SAME = 2  # Max same motion group in a row

# Chapter duration ranges (seconds)
INTRO_SEC_RANGE = (12, 20)
CTA_SEC_RANGE = (10, 20)
RECAP_SEC_RANGE = (30, 60)
PRODUCT_BLOCK_SEC_RANGE = (45, 75)  # Per product (sum of subsegments)
FILLER_CHAPTER_SEC_RANGE = (35, 70)

# ---------------------------------------------------------------------------
# Audio / loudness
# ---------------------------------------------------------------------------

LUFS_TARGET = -14.0
LUFS_TOLERANCE = 1.5
TRUE_PEAK_MAX = -0.5
AUDIO_SAMPLE_RATE = 48000

# ---------------------------------------------------------------------------
# Product truth
# ---------------------------------------------------------------------------

MIN_TRUTH_PRODUCTS = 4        # Minimum products with truth visuals
FIDELITY_SCORE_MIN = 80       # Minimum fidelity score (0-100)

# ---------------------------------------------------------------------------
# Render output
# ---------------------------------------------------------------------------

OUTPUT_W = 1920
OUTPUT_H = 1080
OUTPUT_FPS = 30
OUTPUT_CRF = 18
OUTPUT_PRESET = "slow"

# ---------------------------------------------------------------------------
# Disk space
# ---------------------------------------------------------------------------

MIN_CACHE_FREE_GB = 80
MIN_EXPORT_HEADROOM_MULTIPLIER = 2
MIN_EXPORT_HEADROOM_BASE_GB = 20

# ---------------------------------------------------------------------------
# Stability / identity
# ---------------------------------------------------------------------------

STABILITY_CRITICAL_THRESHOLD = 40

# ---------------------------------------------------------------------------
# Black frame / media offline detection
# ---------------------------------------------------------------------------

BLACK_LUMA_THRESHOLD = 16         # Pixel value 0-255; below = black
BLACK_FRAME_MIN_RATIO = 0.95      # 95%+ dark pixels = black frame
RED_CHANNEL_DOMINANCE = 0.6       # R / (R+G+B) > 60% = "offline" red

# ---------------------------------------------------------------------------
# Render watchdog
# ---------------------------------------------------------------------------

STALL_TIMEOUT_SEC = 120       # No output growth for this long = stall
RENDER_POLL_SEC = 10          # Poll render status every N seconds
RENDER_TIMEOUT_SEC = 3600     # Max 1 hour render
MAX_RETRY = 1                 # Max retries after stall

# ---------------------------------------------------------------------------
# Motion groups (for hygiene validation)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Soundtrack
# ---------------------------------------------------------------------------

SOUNDTRACK_MUSIC_GAIN_DB = -18.0
SOUNDTRACK_DUCK_AMOUNT_DB = 12
SOUNDTRACK_DUCK_ATTACK_MS = 20
SOUNDTRACK_DUCK_RELEASE_MS = 250
SOUNDTRACK_CROSSFADE_IN_SEC = 2.0
SOUNDTRACK_CROSSFADE_OUT_SEC = 2.0
SOUNDTRACK_LOOP_CROSSFADE_SEC = 2.5
SOUNDTRACK_CHAPTER_GAIN_JITTER_DB = 1.5
SOUNDTRACK_MAX_LOOP_RATIO = 2.0
SOUNDTRACK_MIN_VIDEO_SEC = 30
SOUNDTRACK_AI_EDITOR_EPS_SEC = 0.25
SOUNDTRACK_LICENSE_TIERS = {"GREEN", "AMBER", "RED"}
SOUNDTRACK_LUFS_RANGE = (-15.0, -13.0)
SOUNDTRACK_DURATION_EPS_SEC = 0.2
SOUNDTRACK_TRUE_PEAK_MAX = -1.0
SOUNDTRACK_TRUE_PEAK_WARN = -1.3        # WARN if close to limit
SOUNDTRACK_MAX_SILENCE_GAP_MS = 300
SOUNDTRACK_TRACK_COOLDOWN_RUNS = 5
SOUNDTRACK_MOTIF_COOLDOWN_RUNS = 8      # Cooldown by motif_group
SOUNDTRACK_VALID_SOURCES = {
    "artlist", "epidemic", "custom", "suno", "udio", "other",
}

# Broadcast QA — VAD + Ducking + Spectral
VAD_VOICE_BAND_HZ = (300, 3000)         # Bandpass for voice activity detection
VAD_WINDOW_MS = 200                      # Analysis window size
VAD_NOISE_FLOOR_PERCENTILE = 10          # Bottom N% windows = noise floor estimate
VAD_THRESHOLD_ABOVE_FLOOR_DB = 10.0      # VO detected if RMS > floor + this
DUCKING_PRESENCE_BAND_HZ = (2000, 5000)  # Presence band for masking check
DUCKING_MIN_REDUCTION_RATIO = 0.7        # Must duck at least 70% of target amount
DUCKING_SPECTRAL_CLASH_BAND_HZ = (2000, 5000)  # Same as presence for clarity

# Clipping / click detection
CLIPPING_PEAK_RATIO = 0.99               # Sample value >= 99% of max = clip
CLIPPING_MAX_CONSECUTIVE_SAMPLES = 3     # Consecutive clipped samples = true clip

# Safety jitter (AMBER tier only)
SAFETY_JITTER_PITCH_RATIO = 0.9995       # ~-0.05% pitch shift
SAFETY_JITTER_TEMPO_RATIO = 1.001        # ~+0.1% tempo shift

# Fairlight bus contract
BUS_VO_NAME = "BUS_VO"
BUS_MUSIC_NAME = "BUS_MUSIC"
BUS_SFX_NAME = "BUS_SFX"
BUS_MASTER_NAME = "BUS_MASTER"

# Conform cache
CONFORM_CACHE_DIR = "state/cache/conformed_tracks"

MOTION_GROUPS = {
    "zoom_in": {"zoom_in_center", "slow_push_in", "push_in"},
    "zoom_out": {"zoom_out_center", "pull_out"},
    "pan_lr": {"pan_left_to_right"},
    "pan_rl": {"pan_right_to_left"},
    "pan_ud": {"slow_push_up", "push_up"},
    "diagonal": {"diagonal_drift"},
}


def motion_group_for_preset(preset_name: str) -> str:
    """Return the motion group a preset belongs to."""
    for group, presets in MOTION_GROUPS.items():
        if preset_name in presets:
            return group
    return "other"
