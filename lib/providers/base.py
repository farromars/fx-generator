"""Provider 基类和配置。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProviderConfig:
    """Provider 配置。"""

    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    extra: dict = field(default_factory=dict)


class BaseImageProvider(ABC):
    """图像生成 Provider 基类。"""

    name: str = ""
    display_name: str = ""
    supported_models: list = []  # list[str]

    supports_negative_prompt: bool = False
    supports_seed: bool = False
    supports_size: bool = True
    supports_n: bool = True
    supports_response_format: bool = True

    def __init__(self, config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig()

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        n: int = 1,
        size: str = "1024x1024",
        model: Optional[str] = None,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Path] = None,
        progress_cb=None,
    ) -> list:
        """生成图片，返回本地文件路径列表（list[Path]）。"""

    def get_available_models(self) -> list:
        return [{"id": m, "description": ""} for m in self.supported_models]
