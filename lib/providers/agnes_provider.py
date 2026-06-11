"""Agnes AI Provider（OpenAI 兼容协议 + extra_body 传递特有参数）。"""

from __future__ import annotations

import base64
from pathlib import Path

from openai import OpenAI

from .base import BaseImageProvider, ProviderConfig


class AgnesProvider(BaseImageProvider):
    """Agnes AI 图像生成 Provider。"""

    name = "agnes"
    display_name = "Agnes AI（云 API）"
    supported_models = [
        "agnes-image-2.1-flash",
        "agnes-image-2.0-flash",
        "agnes-t2i-general-model",
    ]

    supports_negative_prompt = True
    supports_seed = True
    supports_size = True
    supports_n = True
    supports_response_format = False

    DEFAULT_ENDPOINT = "https://apihub.agnes-ai.com/v1"

    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        endpoint = self.config.endpoint or self.DEFAULT_ENDPOINT
        self.client = OpenAI(
            base_url=endpoint,
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
        """调用 Agnes 图像生成 API。"""
        model = model or self.config.model or "agnes-image-2.1-flash"

        if progress_cb:
            progress_cb(0, n + 1, f"调用 Agnes（{model}, n={n}, {size}）...")

        extra_body: dict = {}
        if negative_prompt:
            extra_body["negative_prompt"] = negative_prompt

        kwargs: dict = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        if seed is not None:
            kwargs["seed"] = seed

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
