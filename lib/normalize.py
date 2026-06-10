"""按 Effect Creator 资产规范做尺寸 / 命名 / 色彩空间规范化。"""

import re
from PIL import Image


def normalize_for_ec(
    img: Image.Image,
    target_size: tuple[int, int] = (1024, 1024),
) -> Image.Image:
    """按 Effect Creator 资产规范缩放 + 转 RGBA。"""
    if img.size != target_size:
        img = img.resize(target_size, Image.Resampling.LANCZOS)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img


def safe_filename(s: str, max_len: int = 64) -> str:
    """转 ASCII / 去空格，符合 EC 资产命名习惯。"""
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", s)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:max_len]
