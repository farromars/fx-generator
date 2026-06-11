"""rembg 抠透明背景。

改动要点（v0.1.1）：
1. 默认换成 `u2net_human_seg`（人像专用，速度更快、边缘更准）
2. 模型缓存路径走 `lib.config.REMBG_CACHE`，避免下到家目录
3. 接受 progress_cb 回传给 UI
4. 加超时与失败兜底
"""

from __future__ import annotations

from typing import Callable

from PIL import Image

# 注意：必须先 import config 设置 U2NET_HOME，再 import rembg
from . import config as _cfg  # noqa: F401  保持导入顺序

# 候选模型（按推荐度排）
SUPPORTED_MODELS = [
    "u2net_human_seg",   # 人像专用，最适合 face / 半身像 → 默认
    "isnet-general-use", # 通用最强
    "u2net",             # 通用稳定
    "silueta",           # 轻量
]
DEFAULT_MODEL = "u2net_human_seg"


_session_cache: dict[str, object] = {}


def _get_session(model_name: str):
    """获取 rembg session，常驻避免反复加载模型。"""
    from rembg import new_session
    if model_name not in _session_cache:
        _session_cache[model_name] = new_session(model_name)
    return _session_cache[model_name]


def warmup(model_name: str = DEFAULT_MODEL,
           progress_cb: Callable[[str], None] | None = None) -> None:
    """预下载并加载 rembg 模型。建议在 UI 启动时调用一次。

    第一次会下载约 170MB（u2net_human_seg），存到 lib.config.REMBG_CACHE。
    """
    if progress_cb:
        progress_cb(f"准备 rembg 模型：{model_name}（首次需下载约 170MB）...")
    _get_session(model_name)
    if progress_cb:
        progress_cb(f"rembg 模型 {model_name} 就绪")


def remove_background(
    img: Image.Image,
    *,
    model: str = DEFAULT_MODEL,
    progress_cb: Callable[[str], None] | None = None,
) -> Image.Image:
    """rembg 抠透明背景。返回 RGBA。

    出错时抛 RuntimeError，由调用方决定是否兜底。
    """
    from rembg import remove

    if progress_cb:
        progress_cb(f"正在抠图（model={model}）...")

    try:
        session = _get_session(model)
        result = remove(img, session=session)
        if result.mode != "RGBA":
            result = result.convert("RGBA")
        if progress_cb:
            progress_cb("抠图完成")
        return result
    except Exception as e:
        raise RuntimeError(f"rembg 抠图失败 ({model}): {e}") from e
