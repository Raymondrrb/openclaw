"""Dzine image-generation schema: validation, constants, and prompt templates.

Amazon Associates product ranking channel visual system.
Stdlib only — no external deps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ASSET_TYPES = ("thumbnail", "product", "background", "avatar_base")

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
}

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
}

# Single combined prompt per asset type (Dzine uses one main prompt box).
# {product_name} and {key_message} are injected at build time.
PROMPT_TEMPLATES: dict[str, str] = {
    "thumbnail": (
        "High-contrast YouTube thumbnail, 2048x1152 resolution.\n\n"
        "Product: {product_name} prominently positioned on the right side, "
        "accurate proportions, realistic materials and sharp detail.\n\n"
        "Clean dark gradient background with subtle glow behind product for depth.\n\n"
        'Add bold headline text: "{key_message}" (maximum 4 words), '
        "large readable font, strong contrast, positioned on left side.\n\n"
        "Cinematic lighting, subtle shadow under product, premium modern aesthetic.\n\n"
        "Minimal composition, no clutter, no extra objects, no watermarks, no added logos.\n\n"
        "Professional commercial quality, realistic lighting physics, no AI artifacts."
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
}

# Fields required per asset type
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "thumbnail": ("product_name", "key_message"),
    "product": ("product_name",),
    "background": (),
    "avatar_base": (),
}

MAX_PROMPT_LENGTH = 3000

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
    prompt_override: Optional[str] = None
    # Reference image path — real product photo used as input for Dzine
    reference_image: Optional[str] = None
    # Built prompts (populated by build_prompts)
    prompt: str = ""
    negative_prompt: str = ""


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

    # Check required fields for this asset type
    for fname in REQUIRED_FIELDS.get(req.asset_type, ()):
        if not getattr(req, fname, "").strip():
            errors.append(f"Field {fname!r} is required for asset_type={req.asset_type!r}")

    # key_message length (max 4 words for thumbnails)
    if req.asset_type == "thumbnail" and req.key_message:
        word_count = len(req.key_message.split())
        if word_count > 4:
            errors.append(
                f"key_message must be 4 words max for thumbnails, got {word_count}: "
                f"{req.key_message!r}"
            )

    # Length limits on prompt fields
    for fname in ("prompt_override", "prompt", "negative_prompt"):
        val = getattr(req, fname, None) or ""
        if len(val) > MAX_PROMPT_LENGTH:
            errors.append(f"{fname} exceeds {MAX_PROMPT_LENGTH} characters ({len(val)})")

    # Reference image must exist if provided
    if req.reference_image:
        from pathlib import Path
        if not Path(req.reference_image).is_file():
            errors.append(f"Reference image not found: {req.reference_image}")

    # Resolution bounds
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
    # Apply default resolution if not specified
    w, h = DEFAULT_RESOLUTIONS.get(req.asset_type, (2048, 2048))
    width = req.width or w
    height = req.height or h

    # If prompt_override is set, use it directly
    if req.prompt_override:
        return DzineRequest(
            asset_type=req.asset_type,
            product_name=req.product_name,
            key_message=req.key_message,
            style=req.style,
            width=width,
            height=height,
            prompt_override=None,
            reference_image=req.reference_image,
            prompt=req.prompt_override,
            negative_prompt=req.negative_prompt or NEGATIVE_PROMPTS.get(req.asset_type, ""),
        )

    # Pick template — use reference variant for product if reference image exists
    template_key = req.asset_type
    if req.asset_type == "product" and req.reference_image:
        template_key = "product_with_ref"

    template = PROMPT_TEMPLATES.get(template_key, "")
    fmt_vars = {
        "product_name": req.product_name or "the product",
        "key_message": req.key_message or "",
    }

    prompt = req.prompt or template.format(**fmt_vars)
    negative = req.negative_prompt or NEGATIVE_PROMPTS.get(req.asset_type, "")

    return DzineRequest(
        asset_type=req.asset_type,
        product_name=req.product_name,
        key_message=req.key_message,
        style=req.style,
        width=width,
        height=height,
        prompt_override=None,
        reference_image=req.reference_image,
        prompt=prompt,
        negative_prompt=negative,
    )
