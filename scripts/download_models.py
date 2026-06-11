"""模型下载脚本：rembg、SDXL Turbo。

用法：
    python scripts/download_models.py rembg            # 下载 u2net_human_seg
    python scripts/download_models.py sdxl-turbo       # 下载 SDXL Turbo（约 7GB）
    python scripts/download_models.py all              # 全下

镜像 fallback：
- 默认走官方 HuggingFace
- 国内可设置 HF_ENDPOINT=https://hf-mirror.com 后再运行
- 实在拉不下来：手动从 ModelScope 下载放到 ~/.cache/huggingface/hub/
  https://www.modelscope.cn/models/AI-ModelScope/sdxl-turbo
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def hint_mirror():
    if not os.environ.get("HF_ENDPOINT"):
        print()
        print("提示：如果在中国大陆且下载缓慢/失败，建议设置 HuggingFace 镜像：")
        print("  Windows PowerShell:  $env:HF_ENDPOINT='https://hf-mirror.com'")
        print("  CMD:                 set HF_ENDPOINT=https://hf-mirror.com")
        print("  bash/zsh:            export HF_ENDPOINT=https://hf-mirror.com")
        print("然后重新运行本脚本。")
        print()


def download_rembg():
    """预下载 rembg 默认模型 u2net_human_seg。"""
    from lib.matting import warmup
    print("→ 下载 rembg 模型（u2net_human_seg）...")
    try:
        warmup(progress_cb=print)
        print("✓ rembg 模型已就绪")
    except Exception as e:
        print(f"✗ rembg 模型下载失败：{e}")
        hint_mirror()
        return 1
    return 0


def download_sdxl_turbo():
    """预下载 SDXL Turbo 权重（约 7GB）。"""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("缺少 huggingface_hub，请先：pip install huggingface_hub")
        return 1
    repo = "stabilityai/sdxl-turbo"
    print(f"→ 下载 {repo}（约 7GB，首次较慢）...")
    print(f"  endpoint: {os.environ.get('HF_ENDPOINT', 'https://huggingface.co (官方)')}")
    try:
        path = snapshot_download(
            repo_id=repo,
            allow_patterns=[
                "*.json", "*.txt",
                "model_index.json",
                "scheduler/*",
                "text_encoder/*.fp16.safetensors", "text_encoder/*.json",
                "text_encoder_2/*.fp16.safetensors", "text_encoder_2/*.json",
                "tokenizer/*", "tokenizer_2/*",
                "unet/*.fp16.safetensors", "unet/*.json",
                "vae/*.fp16.safetensors", "vae/*.json",
            ],
        )
        print(f"✓ SDXL Turbo 下载完成：{path}")
        return 0
    except Exception as e:
        print(f"✗ SDXL Turbo 下载失败：{e}")
        hint_mirror()
        print()
        print("备选：从 ModelScope 手动下载（无需翻墙）：")
        print("  https://www.modelscope.cn/models/AI-ModelScope/sdxl-turbo")
        print("  然后把整个 sdxl-turbo 目录放到：")
        print("  ~/.cache/huggingface/hub/models--stabilityai--sdxl-turbo/snapshots/<commit>/")
        return 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0

    target = sys.argv[1].lower()
    rc = 0
    if target in ("rembg", "all"):
        rc |= download_rembg()
    if target in ("sdxl-turbo", "sdxl", "all"):
        rc |= download_sdxl_turbo()
    if target not in ("rembg", "sdxl-turbo", "sdxl", "all"):
        print(f"未知目标：{target}")
        print(__doc__)
        return 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
