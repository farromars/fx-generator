"""Agnes API 客户端（OpenAI 兼容格式，不用 response_format）。

TODO(v0.2): 抽成多 Provider 架构，支持 OpenAI DALL-E / Stability / Gemini 等。
详见 docs/多Provider适配计划.md
"""

import json
import base64
import os
from pathlib import Path
from openai import OpenAI

DEFAULT_ENDPOINT = "https://apihub.agnes-ai.com/v1"
DEFAULT_MODEL = "agnes-image-2.1-flash"
ENV_API_KEY = "AGNES_API_KEY"

_CODEBUDDY_CONFIG_PATHS = [
    Path.home() / ".codebuddy" / "models.json",
    Path.cwd() / ".codebuddy" / "models.json",
    Path(__file__).resolve().parent.parent / ".codebuddy" / "models.json",
]


def _load_agnes_config() -> dict:
    """从 CodeBuddy models.json 加载 Agnes 配置。"""
    for config_path in _CODEBUDDY_CONFIG_PATHS:
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                for model in data.get("models", []):
                    mid = model.get("id", "")
                    name = model.get("name", "")
                    if "agnes" in mid.lower() or "agnes" in name.lower():
                        url = model.get("url", "")
                        api_key = model.get("apiKey", "")
                        if "/chat/completions" in url:
                            base_url = url.replace("/chat/completions", "")
                        else:
                            base_url = url.rsplit("/", 1)[0] if url else ""
                        return {"endpoint": base_url, "api_key": api_key}
            except (json.JSONDecodeError, KeyError):
                continue
    return {}


# 导入时自动设置环境变量
_cfg = _load_agnes_config()
if _cfg:
    if not os.environ.get(ENV_API_KEY):
        os.environ[ENV_API_KEY] = _cfg.get("api_key", "")
    ENDPOINT = _cfg.get("endpoint", DEFAULT_ENDPOINT)
else:
    ENDPOINT = DEFAULT_ENDPOINT


def generate_images(
    prompt: str,
    *,
    n: int = 4,
    size: str = "1024x1024",
    model: str = DEFAULT_MODEL,
    seed: int | None = None,
    negative_prompt: str | None = None,
    endpoint: str | None = None,
    api_key: str | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    """调用 Agnes API 生成图片，返回本地文件路径列表。

    Agnes 不支持 response_format 参数，默认返回 b64_json。
    
    TODO(v0.2): 抽成多 Provider 架构，兼容不同 API 的参数差异。
    """
    client = OpenAI(
        base_url=endpoint or ENDPOINT,
        api_key=api_key or os.environ.get(ENV_API_KEY, ""),
    )

    # extra_body 传递 Agnes 特有参数
    extra_body = {}
    if negative_prompt:
        extra_body["negative_prompt"] = negative_prompt

    kwargs = dict(
        model=model,
        prompt=prompt,
        n=n,
        size=size,
        extra_body=extra_body if extra_body else None,
    )
    if seed is not None:
        kwargs["seed"] = seed

    response = client.images.generate(**kwargs)

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
