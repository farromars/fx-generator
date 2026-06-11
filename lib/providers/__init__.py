"""图像生成 Provider 注册表。"""

from .base import BaseImageProvider, ProviderConfig
from .openai_provider import OpenAIProvider
from .agnes_provider import AgnesProvider
from .local_sdxl import LocalSDXLTurboProvider

__all__ = [
    "BaseImageProvider",
    "ProviderConfig",
    "OpenAIProvider",
    "AgnesProvider",
    "LocalSDXLTurboProvider",
    "PROVIDER_REGISTRY",
    "get_provider",
]


PROVIDER_REGISTRY = {
    "openai": OpenAIProvider,
    "agnes": AgnesProvider,
    "local_sdxl": LocalSDXLTurboProvider,
}


def get_provider(name: str, **kwargs) -> BaseImageProvider:
    """获取指定 Provider 实例。"""
    cls = PROVIDER_REGISTRY.get(name.lower())
    if not cls:
        raise ValueError(
            f"未知 Provider: {name}。可用: {list(PROVIDER_REGISTRY.keys())}"
        )
    return cls(**kwargs)
