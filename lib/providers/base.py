"""Provider 基类和配置。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class ProviderConfig:
    """Provider 配置。"""
    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None


class BaseImageProvider(ABC):
    """图像生成 Provider 基类。"""

    # Provider 元信息
    name: str = ""
    display_name: str = ""
    supported_models: list[str] = []

    # 功能标志
    supports_negative_prompt: bool = False
    supports_seed: bool = False
    supports_size: bool = True
    supports_n: bool = True  # 是否支持一次生成多张
    supports_response_format: bool = True

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    @abstractmethod
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
        """生成图片，返回本地文件路径列表。"""
        pass

    def get_available_models(self) -> list[dict]:
        """返回可用模型列表，每项包含 id 和 description。"""
        return [{"id": m, "description": ""} for m in self.supported_models]
