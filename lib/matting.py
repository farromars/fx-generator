"""rembg 抠透明背景。"""

from PIL import Image
from rembg import remove


def remove_background(img: Image.Image) -> Image.Image:
    """rembg 抠透明背景。返回 RGBA。

    失败时退化返回原图（转为 RGBA），并在
    lib._common 日志中记录警告。
    """
    try:
        result = remove(img)
        if result.mode != "RGBA":
            result = result.convert("RGBA")
        return result
    except Exception as e:
        raise RuntimeError(f"rembg 抠图失败: {e}") from e
