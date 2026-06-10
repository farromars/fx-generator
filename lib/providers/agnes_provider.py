"""Agnes AI Provider。"""

import base64
from pathlib import Path

from openai import OpenAI

from .base import BaseImageProvider, ProviderConfig


class AgnesProvider(BaseImageProvider):
    """Agnes AI 图像生成 Provider。"""

    name = "agnes"
    display_name = "Agnes AI (agnes-image-2.x)"
    supported_models = ["agnes-image-2.1-flash", "agnes-image-2.0-flash", "agnes-t2i-general-model"]

    # Agnes 特性
    supports_negative_prompt = True
    supports_seed = True
    supports_size = True
    supports_n = True
    supports_response_format = False  # 不支持 response_format

    # Agnes 默认 endpoint
    DEFAULT_ENDPOINT = "https://apihub.agnes-ai.com/v1"

    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        endpoint = self.config.endpoint or self.DEFAULT_ENDPOINT
        # Agnes 使用 OpenAI 兼容格式
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
    ) -> list[Path]:
        """调用 Agnes 图像生成 API。"""
        model = model or "agnes-image-2.1-flash"

        # 构建 extra_body（Agnes 特有参数通过 extra_body 传递）
        extra_body = {}
        if negative_prompt:
            extra_body["negative_prompt"] = negative_prompt

        kwargs = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
            "extra_body": extra_body,
        }

        if seed is not None:
            kwargs["seed"] = seed

        # Agnes 不支持 response_format，不传递该参数
        # 默认返回的是 base64 格式

        response = self.client.images.generate(**kwargs)

        if output_dir is None:
            output_dir = Path.cwd() / "output" / "temp"
        output_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        for i, item in enumerate(response.data):
            if item.b64_json:
                img_data = base64.b64decode(item.b64_json)
                path = output_dir / f"candidate_{i+1:02d}.png"
                path.write_bytes(img_data)
                paths.append(path)
            elif item.url:
                import httpx
                resp = httpx.get(item.url, timeout=60)
                resp.raise_for_status()
                path = output_dir / f"candidate_{i+1:02d}.png"
                path.write_bytes(resp.content)
                paths.append(path)

        return paths
