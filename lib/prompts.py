"""Prompt 工程化：风格预设、品类模板、历史记录。

简单文件存储（output/_history.json），无 DB 依赖。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import OUTPUT_ROOT

# ════════════════════════════════════════════════════════════
# 风格预设：8 个一键追加的风格关键词
# ════════════════════════════════════════════════════════════

STYLE_PRESETS = [
    ("赛博朋克", "cyberpunk style, neon glow, chrome metallic, electric blue and magenta, futuristic"),
    ("国潮古风", "chinese traditional pattern, gold and red palette, ink wash, ornate, oriental"),
    ("卡通可爱", "cartoon style, cute kawaii, soft pastel colors, big eyes, playful, anime"),
    ("像素风", "8-bit pixel art, retro game style, dithered, sharp pixels, low resolution feel"),
    ("极简扁平", "minimalist flat design, clean lines, simple shapes, limited palette, vector style"),
    ("蒸汽朋克", "steampunk style, brass and copper, gears and pipes, victorian, mechanical"),
    ("梦核虚幻", "dreamcore aesthetic, surreal, soft gradient, ethereal, hazy, liminal space"),
    ("油画质感", "oil painting style, thick brush strokes, classical, rich textures, painterly"),
]


# ════════════════════════════════════════════════════════════
# 品类模板：6 个完整 prompt 模板（覆盖企划书 6 大品类）
# ════════════════════════════════════════════════════════════

CATEGORY_TEMPLATES = [
    (
        "面部贴图（S1）",
        "a [THEME] face paint design, frontal symmetric, centered on face, "
        "on transparent background, clean edges, no shadow, no skin tone, "
        "high detail, suitable as overlay texture, 1:1 aspect ratio",
    ),
    (
        "动态头饰（S2 keyframe）",
        "a [THEME] headpiece floating above head, frontal view, centered, "
        "transparent background, clean cut-out, soft glow, "
        "pose for animation keyframe, no person, only the accessory",
    ),
    (
        "贴纸 / 装饰（贴脸或飘浮）",
        "a [THEME] decorative sticker, kawaii / chibi style, transparent background, "
        "thick clean outline, vibrant colors, single object, no background, no scene",
    ),
    (
        "全屏背景（粒子/光斑）",
        "[THEME] full-screen abstract pattern, seamless tileable, "
        "high contrast, transparent or pure black background, "
        "particles / sparkles / light rays, no person, no foreground object",
    ),
    (
        "节日 IP 主题（春节 / 七夕 / 中秋）",
        "a [THEME] festival decoration in chinese traditional style, "
        "auspicious red and gold, ornate pattern, transparent background, "
        "centered single object, ready for face overlay or decoration",
    ),
    (
        "抽象滤镜参考图（S3 LUT 反算）",
        "a portrait shot with [THEME] color grading style, "
        "moody atmosphere, cinematic lighting, "
        "no special effects, just color tone reference",
    ),
]


# ════════════════════════════════════════════════════════════
# Negative Prompt 预设
# ════════════════════════════════════════════════════════════

NEGATIVE_PRESETS = [
    (
        "通用安全",
        "lowres, blurry, watermark, text, logo, signature, "
        "realistic human face, photo of celebrity, photo of public figure, child, "
        "violence, blood, gore, sexual content, weapon",
    ),
    (
        "面部贴图专用",
        "lowres, blurry, asymmetric, watermark, text, logo, "
        "realistic human face, skin tone, full face photo, celebrity, child, "
        "shadow, harsh edges, scary, horror, violence, blood",
    ),
    (
        "贴纸专用（强调干净背景）",
        "lowres, blurry, watermark, text, multiple objects, complex scene, "
        "person, hands, body parts, photo realistic, dirty edges, "
        "celebrity, child, violence, weapon",
    ),
]


# ════════════════════════════════════════════════════════════
# 历史记录
# ════════════════════════════════════════════════════════════

HISTORY_FILE = OUTPUT_ROOT / "_history.json"
HISTORY_MAX = 20


def load_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history(records: list) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(records[-HISTORY_MAX:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_history(prompt: str, negative_prompt: str, seed,
                provider_id: str, size: str,
                first_image_path: Optional[str] = None) -> None:
    records = load_history()
    records.append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider_id,
        "size": size,
        "seed": seed if seed is not None else -1,
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "first_image": first_image_path,
    })
    save_history(records)


def history_choices() -> list:
    """返回 dropdown 用的 (label, index) 列表。最近的在前面。"""
    records = load_history()
    out = []
    for i, r in enumerate(reversed(records)):
        ts = r.get("ts", "")
        prov = r.get("provider", "?")
        seed = r.get("seed", "?")
        prompt_preview = (r.get("prompt", "")[:50] + "...") if len(r.get("prompt", "")) > 50 else r.get("prompt", "")
        label = f"[{ts}] {prov} seed={seed}  |  {prompt_preview}"
        out.append((label, len(records) - 1 - i))
    return out


def get_history_record(index: int) -> Optional[dict]:
    records = load_history()
    if 0 <= index < len(records):
        return records[index]
    return None


# ════════════════════════════════════════════════════════════
# Last session
# ════════════════════════════════════════════════════════════

LAST_SESSION_FILE = OUTPUT_ROOT.parent / ".fxgen_last_session.json"
# 注意：放在 OUTPUT_ROOT 平级（项目根的 .fxgen_last_session.json），别污染 output/


def save_last_session(state: dict) -> None:
    try:
        LAST_SESSION_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_last_session() -> dict:
    if not LAST_SESSION_FILE.exists():
        return {}
    try:
        return json.loads(LAST_SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
