"""本机 SDXL Turbo Provider（CUDA / mps / cpu 自适应）。

依赖：torch + diffusers + transformers + accelerate（pyproject 的 [local] 可选依赖）

性能预期：
- CUDA RTX 5060 (8GB) / fp16, 4 steps, 1024x1024:   3-6s / 张
- macOS Apple Silicon mps / fp16, 4 steps, 1024x1024: 5-12s / 张
- CPU fp32, 4 steps, 1024x1024:                       60-180s / 张（不推荐）

首次加载 pipeline 需 ~30-60s（从磁盘读 ~7GB 权重到显存）。
"""

from __future__ import annotations

import gc
import os
from pathlib import Path

from PIL import Image

from .base import BaseImageProvider, ProviderConfig

# 权重 ID（HuggingFace Hub）
DEFAULT_MODEL_ID = "stabilityai/sdxl-turbo"


def _detect_device() -> str:
    """自动检测最佳推理设备。"""
    try:
        import torch
    except ImportError:
        raise RuntimeError(
            "未安装 torch。请按 INSTALL-WINDOWS.md 安装可选依赖：\n"
            "  pip install -e .[local]\n"
            "并按平台选择 PyTorch 版本（CUDA / mps）。"
        )
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_dtype(device: str, dtype_hint: str):
    import torch
    if dtype_hint == "fp32" or device == "cpu":
        return torch.float32
    return torch.float16


class LocalSDXLTurboProvider(BaseImageProvider):
    """本机 SDXL Turbo 推理 Provider。"""

    name = "local_sdxl"
    display_name = "本机 SDXL Turbo"
    supported_models = [DEFAULT_MODEL_ID]

    supports_negative_prompt = True   # SDXL Turbo 官方建议不用 negative，但允许
    supports_seed = True
    supports_size = True
    supports_n = True
    supports_response_format = False

    # 模型/管线一次加载常驻（同一进程不重复加载）
    _pipe = None
    _pipe_device: str | None = None

    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self.model_id = self.config.model or DEFAULT_MODEL_ID
        # 用户可在 config.extra 里覆盖 device / dtype
        extra = getattr(self.config, "extra", None) or {}
        device_hint = (extra.get("device") if isinstance(extra, dict) else None) or "auto"
        dtype_hint = (extra.get("dtype") if isinstance(extra, dict) else None) or "fp16"
        self.device = _detect_device() if device_hint == "auto" else device_hint
        self.dtype_hint = dtype_hint

    # ── 管线懒加载 ──────────────────────────────────────────
    def _load_pipe(self, log=print):
        if LocalSDXLTurboProvider._pipe is not None and \
                LocalSDXLTurboProvider._pipe_device == self.device:
            return LocalSDXLTurboProvider._pipe

        try:
            import torch
            from diffusers import AutoPipelineForText2Image
        except ImportError as e:
            raise RuntimeError(
                f"加载 diffusers 失败：{e}\n"
                "请安装本地推理依赖：\n"
                "  pip install -e .[local]\n"
                "并参考 INSTALL-WINDOWS.md 安装匹配的 PyTorch。"
            )

        dtype = _resolve_dtype(self.device, self.dtype_hint)
        log(f"[local_sdxl] 加载管线 model={self.model_id} device={self.device} dtype={dtype} ...")

        pipe = AutoPipelineForText2Image.from_pretrained(
            self.model_id,
            torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
        )
        pipe = pipe.to(self.device)
        try:
            pipe.set_progress_bar_config(disable=True)
        except Exception:
            pass

        LocalSDXLTurboProvider._pipe = pipe
        LocalSDXLTurboProvider._pipe_device = self.device
        log(f"[local_sdxl] 管线就绪")
        return pipe

    @classmethod
    def release(cls):
        """主动释放显存（切 Provider 时调用）。"""
        if cls._pipe is not None:
            del cls._pipe
            cls._pipe = None
            cls._pipe_device = None
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    # ── 推理 ───────────────────────────────────────────────
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
        progress_cb=None,           # callable(step:int, total:int, msg:str) - UI 进度
    ) -> list[Path]:
        log = print if progress_cb is None else (lambda *a: None)

        if progress_cb:
            progress_cb(0, n + 1, "加载管线 / 检查显存...")
        pipe = self._load_pipe(log=log)

        try:
            import torch
        except ImportError as e:
            raise RuntimeError(str(e))

        w, h = (int(x) for x in size.lower().split("x"))
        if output_dir is None:
            output_dir = Path.cwd() / "output" / "temp"
        output_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        for i in range(n):
            if progress_cb:
                progress_cb(i + 1, n + 1, f"生成第 {i + 1}/{n} 张...")

            this_seed = (seed if seed is not None else -1) + i if seed is not None else None
            generator = None
            if this_seed is not None and this_seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(int(this_seed))

            kwargs = dict(
                prompt=prompt,
                num_inference_steps=4,           # SDXL Turbo 推荐 1-4
                guidance_scale=0.0,              # SDXL Turbo 推荐 0
                width=w,
                height=h,
            )
            if negative_prompt:
                kwargs["negative_prompt"] = negative_prompt
            if generator is not None:
                kwargs["generator"] = generator

            with torch.inference_mode():
                result = pipe(**kwargs)
            img: Image.Image = result.images[0]

            path = output_dir / f"candidate_{i + 1:02d}.png"
            img.save(path, "PNG")
            paths.append(path)

        if progress_cb:
            progress_cb(n + 1, n + 1, f"完成 {n} 张")
        return paths
