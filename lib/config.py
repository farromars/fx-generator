"""统一配置：Provider 选择、模型路径、输出目录。

启动时自动加载，UI / workflow 都从这里读。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 运行时数据根（Windows: C:\Users\xxx\.fxgen, mac/linux: ~/.fxgen）
RUNTIME_ROOT = Path.home() / ".fxgen"
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

# 输出目录（项目本地）
OUTPUT_ROOT = PROJECT_ROOT / "output"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# 模型权重缓存
MODELS_CACHE = RUNTIME_ROOT / "models"
MODELS_CACHE.mkdir(parents=True, exist_ok=True)

# rembg 模型缓存（U2-Net 等）
REMBG_CACHE = RUNTIME_ROOT / "rembg"
REMBG_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("U2NET_HOME", str(REMBG_CACHE))


# ─────────────────────────────────────────────────────────────
# Provider 配置
# ─────────────────────────────────────────────────────────────

@dataclass
class ProviderEntry:
    """一个图像生成 Provider 的运行时配置。"""

    id: str                                 # "agnes" / "openai" / "local_sdxl"
    display_name: str
    enabled: bool = True
    endpoint: str | None = None
    api_key_env: str | None = None          # 从环境变量读 key 的变量名
    default_model: str | None = None
    extra: dict = field(default_factory=dict)


# 默认 Provider 清单（用户可在 ~/.fxgen/providers.json 覆盖）
DEFAULT_PROVIDERS: list[ProviderEntry] = [
    ProviderEntry(
        id="agnes",
        display_name="Agnes AI（云 API，公共）",
        endpoint="https://apihub.agnes-ai.com/v1",
        api_key_env="AGNES_API_KEY",
        default_model="agnes-image-2.1-flash",
    ),
    ProviderEntry(
        id="local_sdxl",
        display_name="本机 SDXL Turbo（CUDA / mps / cpu）",
        default_model="stabilityai/sdxl-turbo",
        extra={
            "device": "auto",               # auto / cuda / mps / cpu
            "dtype": "fp16",
        },
    ),
    ProviderEntry(
        id="openai",
        display_name="OpenAI 兼容 endpoint（需自填）",
        endpoint="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_model="dall-e-3",
        enabled=False,                      # 默认关闭，用户配置后再开
    ),
]


def load_providers() -> list[ProviderEntry]:
    """加载 Provider 配置。优先 ~/.fxgen/providers.json，否则用默认。"""
    cfg_path = RUNTIME_ROOT / "providers.json"
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            return [ProviderEntry(**item) for item in data]
        except Exception:
            pass
    return DEFAULT_PROVIDERS


def save_providers(providers: list[ProviderEntry]) -> None:
    cfg_path = RUNTIME_ROOT / "providers.json"
    cfg_path.write_text(
        json.dumps([p.__dict__ for p in providers], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────
# CodeBuddy / IDE 集成（向后兼容上一版 lib/api_client.py 的行为）
# ─────────────────────────────────────────────────────────────

_CODEBUDDY_CONFIG_PATHS = [
    Path.home() / ".codebuddy" / "models.json",
    PROJECT_ROOT / ".codebuddy" / "models.json",
]


def auto_load_agnes_from_codebuddy() -> bool:
    """如果用户配置了 CodeBuddy 且其中有 Agnes，自动设置 AGNES_API_KEY。

    返回是否成功加载。仅当 AGNES_API_KEY 当前未设置时才会写入。
    """
    if os.environ.get("AGNES_API_KEY"):
        return False
    for cfg_path in _CODEBUDDY_CONFIG_PATHS:
        if not cfg_path.exists():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            for model in data.get("models", []):
                mid = (model.get("id") or "").lower()
                name = (model.get("name") or "").lower()
                if "agnes" in mid or "agnes" in name:
                    api_key = model.get("apiKey") or ""
                    if api_key:
                        os.environ["AGNES_API_KEY"] = api_key
                        return True
        except Exception:
            continue
    return False


# 启动时自动尝试一次（向后兼容）
auto_load_agnes_from_codebuddy()
