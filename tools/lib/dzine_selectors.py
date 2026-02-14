"""Dzine canvas editor — stable selectors and positions.

All positions calibrated for 1440x900 viewport on the Dzine canvas editor.
Confirmed through Phases 91-146 of hands-on exploration.

Usage:
    from tools.lib.dzine_selectors import SIDEBAR_Y, PANEL, SEL, RESULTS_ACTIONS
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Sidebar icon Y positions (x is always 40)
# ---------------------------------------------------------------------------

SIDEBAR_X = 40

SIDEBAR_Y: dict[str, int] = {
    "upload": 81,
    "assets": 136,
    "txt2img": 197,
    "img2img": 252,
    "character": 306,
    "ai_video": 361,
    "lip_sync": 425,
    "video_editor": 490,
    "motion_control": 551,
    "enhance_upscale": 628,
    "image_editor": 698,
    "storyboard": 766,
}

# ---------------------------------------------------------------------------
# Panel classes
# ---------------------------------------------------------------------------

PANEL: dict[str, str] = {
    # Generation config panels (Txt2Img, Img2Img, CC, AI Video)
    "gen_config": ".c-gen-config.show",
    # Overview panels (Character menu, Assets, Enhance, Motion, Storyboard)
    "panels": ".panels.show",
    # Specific panel identifiers
    "txt2img": ".c-gen-config.show:not(.img2img-config-panel)",
    "img2img": ".img2img-config-panel",
    "lip_sync": ".lip-sync-config-panel",
    "ai_video": ".ai-video-panel",
}

# ---------------------------------------------------------------------------
# CSS selectors
# ---------------------------------------------------------------------------

SEL: dict[str, str] = {
    # --- Login state ---
    "avatar_button": "button.avatar",
    "login_button": 'button:has-text("Log in")',

    # --- Canvas ---
    "canvas_lower": "canvas.lower-canvas",
    "canvas_upper": "canvas.upper-canvas",
    "canvas_container": ".canvas-container",
    "tool_groups": ".tool-group",

    # --- Txt2Img panel ---
    "txt2img_style": "button.style",
    "txt2img_prompt": ".gen-config-form textarea, .base-prompt textarea",
    "txt2img_generate": "#txt2img-generate-btn",
    "txt2img_ratio_canvas": ".c-aspect-ratio .item.canvas",
    "txt2img_ratio_1_1": '.c-aspect-ratio button:has-text("1:1")',
    "txt2img_mode_fast": '.gen-config-body button:has-text("Fast")',
    "txt2img_mode_normal": '.gen-config-body button:has-text("Normal")',
    "txt2img_mode_hq": '.gen-config-body button:has-text("HQ")',

    # --- Img2Img panel ---
    "img2img_prompt": "TEXTAREA.len-1800",
    "img2img_prompt_wrapper": "div.prompt-textarea",
    "img2img_negative": ".negative-prompt textarea",
    "img2img_describe_canvas": ".autoprompt.visible",

    # --- Consistent Character ---
    "cc_character_list": ".c-character-list",
    "cc_gen_config_header": ".gen-config-header",
    "cc_description": ".character-description textarea",
    "cc_scene_prompt": ".custom-textarea",

    # --- Chat Editor (bottom bar) ---
    "chat_prompt": "[contenteditable='true'].custom-textarea.len-5000",
    "chat_generate": "#chat-editor-generate-btn",
    "chat_model_btn": "button.option-btn",
    "chat_model_list": "div.option-list",
    "chat_model_item": "div.option-item",
    "chat_ref_upload": "button.upload-image-btn.image-item",

    # --- Results panel ---
    "results_tab": ".header-item.item-result",
    "layers_tab": ".header-item.item-layers",
    "result_item": ".result-item",
    "result_preview": "#result-preview",

    # --- Style picker ---
    "style_picker_overlay": ".style-picker",
    "style_name": ".style-name",
    "style_search": ".style-picker input",

    # --- Export ---
    "export_btn": "button.export",

    # --- Top bar tools ---
    "ai_eraser": 'button:has-text("AI Eraser")',
    "hand_repair": 'button:has-text("Hand Repair")',
    "expression": 'button:has-text("Expression")',
    "bg_remove": 'button:has-text("BG Remove")',

    # --- Lip Sync ---
    "lip_sync_pick_face": 'button.pick-image:not(.pick-video)',
    "lip_sync_pick_video": "button.pick-image.pick-video",
    "lip_sync_generate": ".gen-config-body button.generative",

    # --- Dialogs ---
    "pick_panel": ".pick-panel",
    "pick_panel_upload": ".pick-panel button.upload",
    "pick_panel_images": ".pick-panel .images",

    # --- Enhance & Upscale ---
    "upscale_btn": "button.generative.ready",

    # --- Results panel action buttons ---
    # NOTE: Y positions shift ~28px depending on sidebar panel state.
    # Use JS click (el.click()) instead of mouse coordinates for reliability.
    "results_btn_class": ".btn-container .btn",  # numbered buttons [1-4]
    "results_selected_btn_class": ".selected-btn",  # icon/label btn -- DO NOT click
    "results_btn_1_x": "1291",
    "results_btn_2_x": "1328",
    "results_btn_3_x": "1366",
    "results_btn_4_x": "1403",

    # --- Enhance & Upscale popup dialog ---
    "enhance_popup_upscale_btn": 'button:has-text("Upscale")',

    # --- AI Video panel (P140-P146) ---
    "ai_video_panel": ".ai-video-panel",
    "ai_video_model_selector": ".custom-selector-wrapper",
    "ai_video_selector_panel": ".selector-panel",
    "ai_video_selector_body": ".selector-panel .panel-body",
    "ai_video_start_frame": "button.pick-image.has-guide",
    "ai_video_prompt": "textarea.len-1800",
    "ai_video_generate": ".generative.ready",
    "ai_video_result": ".result-item.image-to-video-result",

    # --- Video Editor panel (P149) ---
    "video_editor_panel": ".c-gen-config.show.float-video-editor",
    "video_editor_upload": "button.upload-image-btn.image-item",
    "video_editor_prompt": ".custom-textarea.len-1000",
    "video_editor_advanced": "button.advanced-btn",
    "video_editor_generate": "button.generative.ready",

    # --- Motion Control panel (P149) ---
    "motion_control_panel": ".c-gen-config.show.float-motion-trans",
    "motion_control_prompt": ".custom-textarea.len-1800",
    "motion_control_orient_video": "button.option.selected",
    "motion_control_orient_image": "button.option:not(.selected)",
    "motion_control_generate": "button.generative.ready",

    # --- Instant Storyboard panel (P149) ---
    "storyboard_panel": ".c-gen-config.show.float-storyboard-g",
    "storyboard_v1": "button.options:not(.selected)",
    "storyboard_v2": "button.options.selected",
    "storyboard_ref_upload": "button.upload-image-btn.image-item",
    "storyboard_prompt": ".custom-textarea.len-1000",
    "storyboard_generate": "button.generative.ready",
}

# ---------------------------------------------------------------------------
# Results panel action row positions (P138 confirmed)
# All label positions: x=1120, width=146px, height=16px
# Y values are for sidebar panels OPEN; subtract ~28px if panels closed.
# ---------------------------------------------------------------------------

RESULTS_ACTIONS: dict[str, dict[str, int]] = {
    "chat_editor":       {"label_y": 649, "center_y": 657},
    "image_editor":      {"label_y": 685, "center_y": 693},
    "ai_video":          {"label_y": 721, "center_y": 729},
    "lip_sync":          {"label_y": 757, "center_y": 765},
    "expression_edit":   {"label_y": 793, "center_y": 801},
    "face_swap":         {"label_y": 829, "center_y": 837},
    "enhance_upscale":   {"label_y": 865, "center_y": 873},
}

RESULTS_ACTIONS_LABEL_X = 1120
RESULTS_ACTIONS_LABEL_W = 146
RESULTS_ACTIONS_LABEL_H = 16

# Numbered button X positions (same for all action rows)
RESULTS_BTN_X: dict[int, int] = {1: 1291, 2: 1328, 3: 1366, 4: 1403}

# ---------------------------------------------------------------------------
# Result image URL patterns
# ---------------------------------------------------------------------------

RESULT_IMAGE_HOST = "static.dzine.ai/stylar_product/p/"

RESULT_URL_TYPES: dict[str, str] = {
    "txt2img": "faltxt2img",
    "cc": "characterchatfal",
    "gemini": "gemini2text2image",
    "img2img": "img2imgv2",
    "ai_video": "wanimage2video",
}

# ---------------------------------------------------------------------------
# Dialog dismiss button texts
# ---------------------------------------------------------------------------

DIALOG_DISMISS_TEXTS = (
    "Not now", "Close", "Never show again",
    "Got it", "Skip", "Later",
)

# ---------------------------------------------------------------------------
# Generation timing defaults (seconds)
# ---------------------------------------------------------------------------

GEN_TIMEOUT_S = 120
GEN_POLL_S = 3

# Credit costs
CREDITS: dict[str, int] = {
    "txt2img_fast": 2,
    "txt2img_normal": 4,
    "txt2img_hq": 8,
    "chat_editor": 20,
    "cc_generate": 4,
    "lip_sync_normal": 36,
    "lip_sync_pro": 72,
    "insert_character": 28,
    "character_sheet": 4,
    "video_360": 6,
    "enhance_image": 9,
    "bg_remove": 0,
    "expand_8": 8,
    "enhance_upscale": 4,
    # AI Video (model-dependent, showing base/min credits)
    "ai_video_wan_2_1": 6,
    "ai_video_wan_2_5": 7,
    "ai_video_seedance_pro_fast": 7,
    "ai_video_dzine_v1": 10,
    "ai_video_seedance_1_5_pro": 12,
    "ai_video_dzine_v2": 20,
    "ai_video_kling_2_5_turbo": 30,
    "ai_video_runway_gen4_turbo": 46,
    "ai_video_minimax_hailuo_2_3": 56,
    "ai_video_sora_2": 100,
    "ai_video_google_veo_3_1_fast": 200,
    # Video Editor (P149)
    "video_editor_runway_gen4": 30,
    # Motion Control (P149)
    "motion_control_kling_2_6": 28,
    # Storyboard (P149)
    "storyboard": 6,
    # Face Swap (P147)
    "face_swap": 4,
    # Expression Edit (P147)
    "expression_edit": 4,
}
