"""Dzine image-generation schema: validation, constants, and prompt templates.

Amazon Associates product ranking channel visual system.
Supports multi-variant product images (hero, usage, detail, mood).
Stdlib only — no external deps.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ASSET_TYPES = ("thumbnail", "product", "background", "avatar_base", "product_faithful")

STYLES = (
    "photorealistic",
    "cinematic",
    "studio",
)

# width x height defaults per asset type (all 2048-based for quality)
DEFAULT_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "thumbnail": (2048, 1152),
    "product": (2048, 2048),
    "background": (2048, 1152),
    "avatar_base": (2048, 2048),
    "product_faithful": (2048, 1152),
}

# ---------------------------------------------------------------------------
# Multi-variant image system
# ---------------------------------------------------------------------------

IMAGE_VARIANTS = ("hero", "usage1", "usage2", "detail", "mood")

# Default: 3 images per product (hero, usage1, detail).
# Top-rank hierarchy adds mood for rank #2, usage2 + mood for rank #1.
DZINE_IMAGES_PER_PRODUCT = 3
DZINE_EXTRA_FOR_TOP2 = True

# Base variants every product gets (first DZINE_IMAGES_PER_PRODUCT from this)
_BASE_VARIANTS = ("hero", "usage1", "detail")

VARIANT_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "hero": (2048, 1152),
    "usage1": (2048, 1152),
    "usage2": (2048, 1152),
    "detail": (2048, 2048),
    "mood": (2048, 1152),
}


def variants_for_rank(rank: int) -> tuple[str, ...]:
    """Return the variant list for a given product rank.

    Default: 3 per product (hero, usage1, detail).
    With DZINE_EXTRA_FOR_TOP2:
      - Rank 2: +mood (4 images)
      - Rank 1: +usage2, +mood (5 images)
    """
    base = _BASE_VARIANTS[:DZINE_IMAGES_PER_PRODUCT]
    if not DZINE_EXTRA_FOR_TOP2:
        return base
    if rank == 2:
        return base + ("mood",)
    if rank == 1:
        return base + ("usage2", "mood")
    return base


# ---------------------------------------------------------------------------
# Variant prompt building (data-driven)
# ---------------------------------------------------------------------------

# Shared prefix/suffix for all variant prompts
_VARIANT_PREFIX = (
    "Use the uploaded product image as strict visual reference. "
    "Preserve exact geometry, shape, buttons, ports, branding and color. "
    "Do NOT modify the product in any way."
)
_VARIANT_SUFFIX = "Photorealistic, ultra-detailed, 8K quality. No redesign. No fake features. No logo distortion."
_REF_PRESERVATION_SUFFIX = (
    " Match the real product design accurately from the reference image. "
    "Do not modify shape, color, or branding."
)

# Base negative prompt shared by all variants
_NEGATIVE_BASE = (
    "cartoon, anime style, watermark, extra accessories, wrong shape, "
    "wrong colors, redesigned product, fake features, distorted logo"
)

# Per-variant extra negatives appended to _NEGATIVE_BASE
_NEGATIVE_EXTRAS: dict[str, str] = {
    "hero": ", messy background",
    "usage1": ", messy background, visible faces, identifiable people, brand logos on clothing",
    "usage2": ", messy background, visible faces, identifiable people, brand logos on clothing",
    "detail": ", messy background, blurry",
    "mood": "",
}

VARIANT_NEGATIVES: dict[str, str] = {
    v: _NEGATIVE_BASE + _NEGATIVE_EXTRAS[v] for v in IMAGE_VARIANTS
}


def _build_variant_template(scene: str, lighting: str, camera: str, mood: str) -> str:
    """Build a full variant prompt template from its 4 varying parts."""
    return (
        f"{_VARIANT_PREFIX}\n\n"
        f"Scene: {scene}\n\n"
        f"Lighting: {lighting}\n\n"
        f"Camera: {camera}\n\n"
        f"Mood: {mood}\n\n"
        f"{_VARIANT_SUFFIX}"
    )


# Scene data: (scene, lighting, camera, mood) per category.
# {product_name} is a .format() placeholder substituted at build time.
_USAGE1_SCENES: dict[str, tuple[str, str, str, str]] = {
    "default": (
        "{product_name} in a clean modern environment, natural context of everyday use. Minimal props, tidy setting.",
        "natural window light, soft and even, subtle shadows for depth.",
        "50mm equivalent, medium shot, product clearly visible in context.",
        "approachable, real-world, lifestyle photography.",
    ),
    "audio": (
        "{product_name} on a modern desk setup with subtle neon ambient glow. Clean workspace, minimal tech accessories visible.",
        "soft key light with colored ambient accents, subtle rim light.",
        "50mm equivalent, medium shot, product in natural desk context.",
        "modern tech lifestyle, creative workspace.",
    ),
    "computing": (
        "{product_name} on a modern desk setup with subtle neon ambient glow. Clean workspace, monitor visible in soft background blur.",
        "soft key light with colored ambient accents, subtle rim light.",
        "50mm equivalent, medium shot, product in desk context.",
        "modern tech lifestyle, productive workspace.",
    ),
    "kitchen": (
        "{product_name} on a marble or stone kitchen counter in bright daylight. Clean kitchen background, minimal props.",
        "bright natural daylight from window, soft even illumination.",
        "50mm equivalent, medium shot, product in kitchen context.",
        "fresh, clean, inviting kitchen lifestyle.",
    ),
    "fitness": (
        "{product_name} in a gym environment with matte dark surfaces. Clean workout setting, minimal equipment visible.",
        "overhead gym lighting, directional for definition.",
        "50mm equivalent, medium shot, product in fitness context.",
        "energetic, motivated, fitness lifestyle.",
    ),
    "travel": (
        "{product_name} in an airport lounge setting. Clean modern interior, travel context.",
        "warm ambient indoor light, soft and even.",
        "50mm equivalent, medium shot, product in travel context.",
        "sophisticated, ready-to-go, travel lifestyle.",
    ),
    "office": (
        "{product_name} on a clean white and wood desk surface. Minimal office environment, tidy workspace.",
        "bright natural window light, soft shadows.",
        "50mm equivalent, medium shot, product in office context.",
        "professional, organized, productive workspace.",
    ),
    "camera": (
        "{product_name} in a studio setup environment. Photography studio context, clean professional setting.",
        "studio lighting setup, soft and controlled.",
        "50mm equivalent, medium shot, product in creative context.",
        "creative, professional, studio lifestyle.",
    ),
    "gaming": (
        "{product_name} on an RGB-lit gaming desk setup. Gaming environment, subtle colored lighting accents.",
        "ambient RGB glow, soft key light on product.",
        "50mm equivalent, medium shot, product in gaming context.",
        "immersive, gaming lifestyle, vibrant.",
    ),
    "home": (
        "{product_name} in a modern living room setting. Clean home environment, tasteful decor.",
        "warm natural light, soft and inviting.",
        "50mm equivalent, medium shot, product in home context.",
        "comfortable, homey, modern living.",
    ),
    "outdoor": (
        "{product_name} at a campsite or outdoor setting. Nature environment, clean outdoor context.",
        "natural daylight, golden hour tones.",
        "50mm equivalent, medium shot, product in outdoor context.",
        "adventurous, natural, outdoor lifestyle.",
    ),
    "baby": (
        "{product_name} in a bright clean nursery setting. Soft pastel tones, safe and welcoming environment.",
        "bright soft daylight, even and gentle.",
        "50mm equivalent, medium shot, product in nursery context.",
        "safe, gentle, nurturing.",
    ),
    "streaming": (
        "{product_name} on a streaming desk setup with ambient lighting. Content creator workspace, subtle RGB accents.",
        "soft key light with colored ambient fill.",
        "50mm equivalent, medium shot, product in streaming context.",
        "creative, modern streamer lifestyle.",
    ),
}

_USAGE2_SCENES: dict[str, tuple[str, str, str, str]] = {
    "default": (
        "{product_name} in an alternative everyday context, different from primary usage. Casual indoor or outdoor environment.",
        "natural ambient light, soft and realistic.",
        "50mm equivalent, medium-wide shot, product visible in context.",
        "versatile, everyday, real-life context.",
    ),
    "audio": (
        "{product_name} in an on-the-go context — airport or gym environment. Mobile lifestyle setting.",
        "ambient indoor light, natural feel.",
        "50mm equivalent, medium shot, product in mobile context.",
        "active, portable, on-the-go lifestyle.",
    ),
    "computing": (
        "{product_name} in an on-the-go context — airport lounge or gym setting. Portable use scenario.",
        "ambient indoor light, natural feel.",
        "50mm equivalent, medium shot, product in mobile context.",
        "versatile, portable computing.",
    ),
    "kitchen": (
        "{product_name} on an outdoor patio table or deck. Al fresco cooking or entertaining context.",
        "warm natural outdoor light, golden hour feel.",
        "50mm equivalent, medium shot, product in outdoor kitchen context.",
        "relaxed, outdoor entertaining.",
    ),
    "fitness": (
        "{product_name} on a park trail or outdoor exercise area. Outdoor fitness context, natural setting.",
        "natural daylight, dynamic shadows from trees.",
        "50mm equivalent, medium shot, product in outdoor fitness context.",
        "active, fresh, outdoor fitness.",
    ),
    "travel": (
        "{product_name} in an urban commute setting — subway or city street. Urban travel context.",
        "mixed urban lighting, natural and artificial.",
        "50mm equivalent, medium shot, product in urban context.",
        "urban, practical, city travel.",
    ),
    "office": (
        "{product_name} in a coffee shop or coworking space. Alternative work environment.",
        "warm cafe ambient light, natural tones.",
        "50mm equivalent, medium shot, product in cafe workspace.",
        "creative, relaxed productivity.",
    ),
    "gaming": (
        "{product_name} in a couch or living room gaming setup. Console gaming environment, casual setting.",
        "warm room lighting with subtle screen glow.",
        "50mm equivalent, medium shot, product in casual gaming context.",
        "relaxed, casual gaming session.",
    ),
    "home": (
        "{product_name} in a bedroom or personal space. Private home environment, cozy setting.",
        "warm soft indoor light, gentle and inviting.",
        "50mm equivalent, medium shot, product in bedroom context.",
        "personal, cozy, intimate home.",
    ),
    "outdoor": (
        "{product_name} on a hiking trail or nature path. Active outdoor use scenario.",
        "natural daylight filtering through trees.",
        "50mm equivalent, medium shot, product in trail context.",
        "adventurous, active outdoor.",
    ),
    "camera": (
        "{product_name} in an outdoor photography shoot setting. Field use context, natural environment.",
        "natural outdoor light, golden hour feel.",
        "50mm equivalent, medium shot, product in outdoor shoot context.",
        "creative, field photography.",
    ),
    "baby": (
        "{product_name} in a park or outdoor stroll setting. Outdoor family context.",
        "bright natural daylight, soft and even.",
        "50mm equivalent, medium shot, product in outdoor family context.",
        "joyful, outdoor family time.",
    ),
    "streaming": (
        "{product_name} in an on-the-go mobile setup — cafe or outdoor. Portable content creation context.",
        "natural ambient light, casual setting.",
        "50mm equivalent, medium shot, product in mobile creator context.",
        "flexible, mobile content creation.",
    ),
}

# Build VARIANT_TEMPLATES from scene data tables
VARIANT_TEMPLATES: dict[str, dict[str, str]] = {
    "hero": {
        "default": _build_variant_template(
            "{product_name} on a cinematic dark desk surface with premium studio environment. "
            "Rich dark tones, subtle reflections on the surface.",
            "dramatic key light from upper left, subtle rim light on product edges, "
            "soft shadow underneath. Studio quality.",
            "85mm equivalent, shallow depth of field, product sharp, background softly blurred.",
            "premium, aspirational, high-end commercial photography.",
        ),
    },
    "usage1": {cat: _build_variant_template(*parts) for cat, parts in _USAGE1_SCENES.items()},
    "usage2": {cat: _build_variant_template(*parts) for cat, parts in _USAGE2_SCENES.items()},
    "detail": {
        "default": _build_variant_template(
            "extreme macro close-up of {product_name} showing key texture, "
            "buttons, ports, or material quality. Isolated on clean neutral surface.",
            "strong directional side light for texture definition, "
            "subtle fill from opposite side. High sharpness.",
            "macro lens equivalent, very shallow DOF, razor-sharp focus on detail area.",
            "precision, craftsmanship, premium quality materials.",
        ),
    },
    "mood": {
        "default": _build_variant_template(
            "{product_name} in an atmospheric, cinematic composition. "
            "Dramatic volumetric light rays, subtle haze or fog effect. "
            "Emotional product positioning — the product as centerpiece of a story.",
            "volumetric lighting, strong directional beam with atmospheric scatter. "
            "Cinematic color grading.",
            "85mm equivalent, shallow DOF, dramatic angle slightly below eye level.",
            "aspirational, emotional, cinematic storytelling.",
        ),
    },
}

# ---------------------------------------------------------------------------
# Asset-type negative prompts (non-variant, legacy)
# ---------------------------------------------------------------------------

NEGATIVE_PROMPTS: dict[str, str] = {
    "thumbnail": (
        "blurry, low resolution, cluttered layout, tiny unreadable text, "
        "watermark, distorted product, extra accessories, fake logos, "
        "messy background"
    ),
    "product": (
        "cartoon, anime style, watermark, extra accessories, wrong shape, "
        "wrong colors, messy background"
    ),
    "background": (
        "text, logos, objects, people, watermark, artifacts, "
        "cluttered composition"
    ),
    "avatar_base": (
        "watermark, exaggerated facial features, AI artifacts, "
        "uncanny valley, deformed face, extra limbs, sunglasses, "
        "cartoon style"
    ),
    "product_faithful": (
        "cartoon, anime style, watermark, altered product shape, "
        "wrong colors, extra objects, cluttered background"
    ),
}

# Single combined prompt per asset type (Dzine uses one main prompt box).
# {product_name} and {key_message} are injected at build time.
PROMPT_TEMPLATES: dict[str, str] = {
    "thumbnail": (
        "High-contrast YouTube thumbnail, 2048x1152 resolution.\n\n"
        "Product: {product_name} prominently positioned, occupying ~70% of the frame. "
        "Accurate proportions, realistic materials and sharp detail.\n\n"
        "Dynamic gradient background with strong depth separation. "
        "Subtle glow behind product for visual pop.\n\n"
        "Space reserved on left side for text overlay (no actual text added). "
        "Strong contrast, premium modern aesthetic.\n\n"
        "Cinematic lighting, subtle shadow under product, professional commercial quality.\n\n"
        "Minimal composition, no clutter, no extra objects, no watermarks, no added logos, no text.\n\n"
        "Realistic lighting physics, no AI artifacts."
    ),
    "product": (
        "Studio-quality product photo of {product_name}, 2048x2048.\n\n"
        "Centered composition, accurate shape and proportions, "
        "realistic materials and textures.\n\n"
        "Softbox lighting from two sides, subtle natural shadow under object.\n\n"
        "Neutral white or light gray background.\n\n"
        "Ultra sharp details, clean edges, professional e-commerce photography style.\n\n"
        "No watermark, no additional logos, no extra accessories, no stylization."
    ),
    "product_with_ref": (
        "Studio-quality product photo of {product_name}, 2048x2048.\n\n"
        "Centered composition, accurate shape and proportions, "
        "realistic materials and textures.\n\n"
        "Softbox lighting from two sides, subtle natural shadow under object.\n\n"
        "Neutral white or light gray background.\n\n"
        "Ultra sharp details, clean edges, professional e-commerce photography style.\n\n"
        "No watermark, no additional logos, no extra accessories, no stylization.\n\n"
        "Match the real product design accurately from the reference image. "
        "Do not modify shape or add elements."
    ),
    "background": (
        "Minimal cinematic background for a tech product ranking video, 2048x1152.\n\n"
        "Soft gradient lighting, subtle abstract shapes, smooth depth of field.\n\n"
        "Modern, clean, professional YouTube aesthetic.\n\n"
        "No text, no logos, no objects.\n\n"
        "High resolution, no artifacts."
    ),
    "avatar_base": (
        "High-quality portrait of a confident modern host, 2048x2048.\n\n"
        "Centered framing, clean studio lighting, neutral background.\n\n"
        "Realistic skin texture, natural proportions, cinematic sharpness.\n\n"
        "Friendly but subtle expression.\n\n"
        "No watermark, no exaggerated facial features, no AI artifacts.\n\n"
        "Tech reviewer aesthetic, subtle rim light, modern dark or neutral background."
    ),
    "product_faithful": (
        "Clean white studio backdrop with soft professional lighting, "
        "subtle shadow underneath product. "
        "No extra objects, no watermarks, no text. "
        "Preserve the real product exactly as shown in the reference image."
    ),
}

# Fields required per asset type
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "thumbnail": ("product_name", "key_message"),
    "product": ("product_name",),
    "background": (),
    "avatar_base": (),
    "product_faithful": (),
}

MAX_PROMPT_LENGTH = 3000

# ---------------------------------------------------------------------------
# Model routing — which Dzine model for which asset type
# Based on Phases 91-152 testing + web research (Feb 2026).
# Model names must match exactly what appears in the Dzine style picker.
# ---------------------------------------------------------------------------

MODEL_ROUTING: dict[str, dict[str, str]] = {
    "thumbnail": {
        "primary": "Nano Banana Pro",     # versatile, good text accuracy
        "fallback": "Seedream 4.5",
        "test": "Z-Image Turbo",          # 3-6s, for rapid prompt testing
    },
    "product": {
        "primary": "Nano Banana Pro",     # best product fidelity
        "fallback": "Seedream 4.5",
        "test": "Z-Image Turbo",
    },
    "background": {
        "primary": "Nano Banana Pro",     # versatile, clean gradients
        "fallback": "Dzine General",      # all-purpose default
        "test": "Z-Image Turbo",
    },
    "avatar_base": {
        "primary": "Nano Banana Pro",
        "fallback": "Seedream 4.5",
        "test": "Z-Image Turbo",
    },
    "product_faithful": {
        "primary": None,                  # BG Remove + Expand, not model-dependent
        "fallback": None,
        "test": None,
    },
}

# Per-variant model overrides (more specific than per-asset-type)
VARIANT_MODEL_ROUTING: dict[str, dict[str, str]] = {
    "hero": {
        "primary": "Nano Banana Pro",
        "fallback": "Seedream 4.5",
    },
    "usage1": {
        "primary": "Nano Banana Pro",
        "fallback": "Seedream 4.5",
    },
    "usage2": {
        "primary": "Nano Banana Pro",
        "fallback": "Seedream 4.5",
    },
    "detail": {
        "primary": "Nano Banana Pro",     # excellent for close-ups with text/detail
        "fallback": "Seedream 4.5",
    },
    "mood": {
        "primary": "Nano Banana Pro",
        "fallback": "Seedream 4.5",
    },
}


def recommended_model(
    asset_type: str,
    variant: str = "",
    *,
    testing: bool = False,
) -> str:
    """Return the recommended Dzine model name for an asset/variant.

    Args:
        asset_type: "thumbnail", "product", "background", etc.
        variant: "hero", "usage1", "detail", etc. (overrides asset_type routing)
        testing: if True, return the fast test model instead

    Returns the model name as it appears in the Dzine style picker.
    """
    # Variant-specific routing takes priority
    if variant and variant in VARIANT_MODEL_ROUTING:
        route = VARIANT_MODEL_ROUTING[variant]
        if testing:
            return MODEL_ROUTING.get(asset_type, {}).get("test", "Z-Image Turbo") or "Z-Image Turbo"
        return route.get("primary", "Seedream 4.5") or "Seedream 4.5"

    route = MODEL_ROUTING.get(asset_type, {})
    if testing:
        return route.get("test", "Z-Image Turbo") or "Z-Image Turbo"
    return route.get("primary", "Seedream 4.5") or "Seedream 4.5"

# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------

# Keyword hints for fallback category detection when niche not in NICHE_POOL
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "audio": ["headphone", "earbuds", "speaker", "soundbar", "microphone", "turntable"],
    "computing": ["keyboard", "mouse", "webcam", "monitor", "ssd", "laptop", "usb"],
    "home": ["vacuum", "purifier", "thermostat", "router", "wifi", "lock", "doorbell", "shaver", "toothbrush"],
    "kitchen": ["fryer", "espresso", "coffee", "blender", "mixer", "oven", "kettle", "skillet", "cookware", "knife"],
    "office": ["desk", "chair", "lamp", "monitor arm", "organizer"],
    "fitness": ["fitness", "smartwatch", "running", "yoga", "dumbbell", "gym", "helmet", "hiking"],
    "outdoor": ["camping", "tent", "sleeping bag", "outdoor"],
    "travel": ["luggage", "travel", "backpack", "packing", "portable charger", "power bank", "adapter"],
    "camera": ["camera", "vlog", "dash cam", "ring light", "tripod"],
    "gaming": ["gaming keyboard", "gaming chair", "gaming controller", "gaming mouse", "capture card"],
    "streaming": ["streaming", "stream deck", "green screen"],
    "baby": ["baby", "car seat", "stroller", "monitor baby"],
}

# B-roll search terms per category (used by pipeline broll-plan and notes.md)
CATEGORY_BROLL_TERMS: dict[str, tuple[str, str]] = {
    "audio": ("person listening music", "studio audio equipment"),
    "kitchen": ("cooking kitchen close up", "modern kitchen countertop"),
    "gaming": ("gaming setup RGB", "hands gaming keyboard"),
    "computing": ("person working laptop", "modern workspace technology"),
    "camera": ("photographer shooting", "camera equipment close up"),
    "fitness": ("gym workout equipment", "person exercising"),
}


def detect_category(niche: str) -> str:
    """Detect the visual category for a niche keyword.

    1. Exact match against NICHE_POOL entries.
    2. Keyword heuristic fallback.
    3. Returns "default" if nothing matches.
    """
    niche_lower = niche.lower().strip()
    if not niche_lower:
        return "default"

    # Try exact match from NICHE_POOL
    try:
        from tools.niche_picker import NICHE_POOL
        for entry in NICHE_POOL:
            if entry.keyword.lower() == niche_lower:
                return entry.category
    except ImportError:
        pass

    # Keyword heuristic fallback — check more specific patterns first
    # "gaming" keywords must be checked before generic "keyboard"/"mouse"
    for category in ("gaming", "streaming", "baby", "camera", "travel",
                     "outdoor", "fitness", "kitchen", "office", "home",
                     "computing", "audio"):
        for kw in _CATEGORY_KEYWORDS[category]:
            if kw in niche_lower:
                return category

    return "default"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class DzineRequest:
    asset_type: str
    product_name: str = ""
    key_message: str = ""
    style: str = "photorealistic"
    width: int = 0
    height: int = 0
    prompt_override: str | None = None
    reference_image: str | None = None  # real product photo used as input
    image_variant: str = ""     # "hero", "usage1", "usage2", "detail", "mood"
    niche_category: str = ""    # "audio", "kitchen", etc. from detect_category
    prompt: str = ""            # populated by build_prompts
    negative_prompt: str = ""   # populated by build_prompts


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_request(req: DzineRequest) -> list[str]:
    """Validate a DzineRequest and return a list of error strings (empty = valid)."""
    errors: list[str] = []

    if req.asset_type not in ASSET_TYPES:
        errors.append(
            f"Invalid asset_type {req.asset_type!r}. "
            f"Must be one of: {', '.join(ASSET_TYPES)}"
        )
        return errors  # can't validate further without a valid type

    if req.style not in STYLES:
        errors.append(
            f"Invalid style {req.style!r}. Must be one of: {', '.join(STYLES)}"
        )

    if req.image_variant and req.image_variant not in IMAGE_VARIANTS:
        errors.append(
            f"Invalid image_variant {req.image_variant!r}. "
            f"Must be one of: {', '.join(IMAGE_VARIANTS)}"
        )

    for fname in REQUIRED_FIELDS.get(req.asset_type, ()):
        if not getattr(req, fname, "").strip():
            errors.append(f"Field {fname!r} is required for asset_type={req.asset_type!r}")

    if req.asset_type == "thumbnail" and req.key_message:
        if len(req.key_message.split()) > 4:
            errors.append(
                f"key_message must be 4 words max for thumbnails, got "
                f"{len(req.key_message.split())}: {req.key_message!r}"
            )

    for fname in ("prompt_override", "prompt", "negative_prompt"):
        val = getattr(req, fname, None) or ""
        if len(val) > MAX_PROMPT_LENGTH:
            errors.append(f"{fname} exceeds {MAX_PROMPT_LENGTH} characters ({len(val)})")

    if req.reference_image and not Path(req.reference_image).is_file():
        errors.append(f"Reference image not found: {req.reference_image}")

    if req.width and (req.width < 256 or req.width > 4096):
        errors.append(f"width must be 256-4096, got {req.width}")
    if req.height and (req.height < 256 or req.height > 4096):
        errors.append(f"height must be 256-4096, got {req.height}")

    return errors


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def build_prompts(req: DzineRequest) -> DzineRequest:
    """Render prompt templates and fill in defaults. Returns a new DzineRequest."""
    # Determine resolution
    if req.image_variant and req.image_variant in VARIANT_RESOLUTIONS:
        default_w, default_h = VARIANT_RESOLUTIONS[req.image_variant]
    else:
        default_w, default_h = DEFAULT_RESOLUTIONS.get(req.asset_type, (2048, 2048))

    width = req.width or default_w
    height = req.height or default_h

    fmt_vars = {
        "product_name": req.product_name or "the product",
        "key_message": req.key_message or "",
    }

    # prompt_override bypasses all templates
    if req.prompt_override:
        return replace(
            req, width=width, height=height, prompt_override=None,
            prompt=req.prompt_override,
            negative_prompt=req.negative_prompt or NEGATIVE_PROMPTS.get(req.asset_type, ""),
        )

    # Variant-aware prompt building
    if req.image_variant and req.image_variant in VARIANT_TEMPLATES:
        variant_dict = VARIANT_TEMPLATES[req.image_variant]
        cat = req.niche_category or "default"
        template = variant_dict.get(cat, variant_dict["default"])
        prompt = req.prompt or template.format(**fmt_vars)

        # Append reference preservation suffix if reference image exists
        if req.reference_image and not req.prompt:
            prompt += _REF_PRESERVATION_SUFFIX

        return replace(
            req, width=width, height=height, prompt_override=None,
            prompt=prompt,
            negative_prompt=req.negative_prompt or VARIANT_NEGATIVES.get(req.image_variant, ""),
        )

    # Legacy behavior — no variant set
    template_key = req.asset_type
    if req.asset_type == "product" and req.reference_image:
        template_key = "product_with_ref"

    template = PROMPT_TEMPLATES.get(template_key, "")

    return replace(
        req, width=width, height=height, prompt_override=None,
        prompt=req.prompt or template.format(**fmt_vars),
        negative_prompt=req.negative_prompt or NEGATIVE_PROMPTS.get(req.asset_type, ""),
    )
