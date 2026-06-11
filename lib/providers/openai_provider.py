"""OpenAI / OpenAI 兼容 endpoint 的 Provider（DALL-E 3 / DALL-E 2 / GPT-image-1 / 兼容服务）。"""

from __future__ import annotations

import base64
from pathlib import Path

from openai import OpenAI

from .base import BaseImageProvider, ProviderConfig


class OpenAIProvider(BaseImageProvider):
    """OpenAI 兼容图像生成 Provider。"""

    name = "openai"
    display_name = "OpenAI 兼容"
    supported_models = ["dall-e-3", "dall-e-2", "gpt-image-1"]

    supports_negative_prompt = False
    supports_seed = False
    supports_size = True
    supports_n = True
    supports_response_format = True

    VALID_SIZES = {
        "dall-e-3": ["1024x1024", "1792x1024", "1024x1792"],
        "dall-e-2": ["256x256", "512x512", "1024x1024"],
        "gpt-image-1": ["1024x1024", "1536x1024", "1024x1536"],
    }

    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self.client = OpenAI(
            base_url=self.config.endpoint or "https://api.openai.com/v1",
            api_key=self.config.api_key or "",
        )

    def generate(
        self,
        prompt: str,
        *,
        n: int = 1,
        size: str = "1024x1024",
        model: str | None = None,
        seed: int | None = None,
        negative_prompt: str | None = None,
        output_dir: Path | None = None,
        progress_cb=None,
    ) -> list[Path]:
        model = model or self.config.model or "dall-e-3"

        # DALL-E 3 限制 n=1
        if model == "dall-e-3":
            n = 1

        # 验证尺寸
        if size not in self.VALID_SIZES.get(model, []):
            size = "1024x1024"

        if progress_cb:
            progress_cb(0, n + 1, f"调用 OpenAI（{model}, n={n}, {size}）...")

        kwargs = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
            "response_format": "b64_json",
        }

        response = self.client.images.generate(**kwargs)

        if output_dir is None:
            output_dir = Path.cwd() / "output" / "temp"
        output_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        for i, item in enumerate(response.data):
            if progress_cb:
                progress_cb(i + 1, n + 1, f"接收第 {i + 1}/{n} 张...")
            if item.b64_json:
                img_data = base64.b64decode(item.b64_json)
                path = output_dir / f"candidate_{i + 1:02d}.png"
                path.write_bytes(img_data)
                paths.append(path)
            elif item.url:
                import httpx
                resp = httpx.get(item.url, timeout=60)
                resp.raise_for_status()
                path = output_dir / f"candidate_{i + 1:02d}.png"
                path.write_bytes(resp.content)
                paths.append(path)

        if progress_cb:
            progress_cb(n + 1, n + 1, f"完成 {len(paths)} 张")
        return paths
