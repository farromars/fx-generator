"""多模型图像生成 Provider 接口。"""

from .base import BaseImageProvider, ProviderConfig
from .openai_provider import OpenAIProvider
from .agnes_provider import AgnesProvider

__all__ = [
    "BaseImageProvider",
    "ProviderConfig",
    "OpenAIProvider",
    "AgnesProvider",
]

PROVIDER_REGISTRY = {
    "openai": OpenAIProvider,
    "agnes": AgnesProvider,
}


def get_provider(name: str, **kwargs) -> BaseImageProvider:
    """获取指定 Provider 实例。"""
    provider_cls = PROVIDER_REGISTRY.get(name.lower())
    if not provider_cls:
        raise ValueError(f"未知 Provider: {name}。支持: {list(PROVIDER_REGISTRY.keys())}")
    return provider_cls(**kwargs)
