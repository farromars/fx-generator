"""环境检查脚本：Python / GPU / 显存 / 关键依赖 / 模型缓存。

用法：
    python scripts/check_env.py
"""

from __future__ import annotations

import importlib
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK = "✓"
NO = "✗"
WARN = "!"


def check(name: str, cond: bool, detail: str = "", level: str = OK):
    flag = OK if cond else (level if level != OK else NO)
    print(f"  [{flag}] {name}{(' — ' + detail) if detail else ''}")
    return cond


def section(title: str):
    print(f"\n=== {title} ===")


def main() -> int:
    print("fx-generator 环境检查")
    print("=" * 60)

    overall = True

    # ─── Python ───────────────────────────────────────────
    section("Python")
    py_ver = sys.version_info
    ok_py = py_ver >= (3, 11)
    check("Python ≥ 3.11", ok_py, f"当前 {sys.version.split()[0]}")
    overall &= ok_py
    print(f"  · 平台 {platform.system()} {platform.release()} {platform.machine()}")

    # ─── 核心依赖 ─────────────────────────────────────────
    section("核心依赖（必装）")
    for pkg in ["PIL", "rembg", "onnxruntime", "openai", "httpx", "pydantic", "gradio", "click"]:
        try:
            mod = importlib.import_module(pkg if pkg != "PIL" else "PIL")
            ver = getattr(mod, "__version__", "?")
            check(pkg, True, f"v{ver}")
        except Exception as e:
            check(pkg, False, str(e))
            overall = False

    # ─── 本机推理可选依赖 ─────────────────────────────────
    section("本机推理依赖（可选 [local]）")
    has_torch = False
    try:
        import torch
        has_torch = True
        check("torch", True, f"v{torch.__version__}")
    except Exception as e:
        check("torch", False, f"{e}（如不打算本机跑 SDXL Turbo 可忽略）", level=WARN)

    try:
        import diffusers
        check("diffusers", True, f"v{diffusers.__version__}")
    except Exception as e:
        check("diffusers", False, str(e), level=WARN)

    try:
        import transformers
        check("transformers", True, f"v{transformers.__version__}")
    except Exception as e:
        check("transformers", False, str(e), level=WARN)

    # ─── GPU 探测 ─────────────────────────────────────────
    section("GPU / 推理后端")
    if has_torch:
        cuda_ok = torch.cuda.is_available()
        check("CUDA 可用", cuda_ok)
        if cuda_ok:
            n = torch.cuda.device_count()
            for i in range(n):
                name = torch.cuda.get_device_name(i)
                cap = torch.cuda.get_device_capability(i)
                free, total = torch.cuda.mem_get_info(i)
                free_gb = free / 1024 ** 3
                total_gb = total / 1024 ** 3
                print(f"  · GPU{i}: {name}  sm_{cap[0]}{cap[1]}  显存 {total_gb:.1f}GB（空闲 {free_gb:.1f}GB）")
                if total_gb < 6.5:
                    print(f"    {WARN} 显存 < 6.5GB，SDXL Turbo fp16 可能 OOM。可改用 SDXL Turbo + cpu_offload 或换更小模型。")
        if hasattr(torch.backends, "mps"):
            mps_ok = torch.backends.mps.is_available()
            check("MPS 可用 (Apple Silicon)", mps_ok)
    else:
        print("  · 未安装 torch，跳过 GPU 检测")

    # ─── 项目目录 ─────────────────────────────────────────
    section("项目目录")
    from lib.config import RUNTIME_ROOT, MODELS_CACHE, REMBG_CACHE, OUTPUT_ROOT
    check("RUNTIME_ROOT 可写", RUNTIME_ROOT.exists() and shutil.disk_usage(RUNTIME_ROOT).free > 1024**3,
          f"{RUNTIME_ROOT}  剩余空间 {shutil.disk_usage(RUNTIME_ROOT).free / 1024**3:.1f}GB")
    check("MODELS_CACHE", MODELS_CACHE.exists(), str(MODELS_CACHE))
    check("REMBG_CACHE", REMBG_CACHE.exists(), str(REMBG_CACHE))
    check("OUTPUT_ROOT", OUTPUT_ROOT.exists(), str(OUTPUT_ROOT))

    # ─── rembg 模型 ───────────────────────────────────────
    section("rembg 模型")
    rembg_models = list(REMBG_CACHE.glob("*.onnx"))
    if rembg_models:
        for m in rembg_models:
            print(f"  [{OK}] {m.name}  {m.stat().st_size / 1024 / 1024:.1f}MB")
    else:
        print(f"  [{WARN}] 未找到任何 rembg 模型，首次抠图时会自动下载（约 170MB）")
        print(f"        或预先运行：python scripts/download_models.py rembg")

    # ─── SDXL Turbo 模型 ──────────────────────────────────
    section("SDXL Turbo 模型")
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    sdxl_dirs = list(hf_cache.glob("models--stabilityai--sdxl-turbo")) if hf_cache.exists() else []
    if sdxl_dirs:
        size_gb = sum(f.stat().st_size for f in sdxl_dirs[0].rglob("*") if f.is_file()) / 1024**3
        check("sdxl-turbo 已缓存", True, f"{sdxl_dirs[0]}  ~{size_gb:.1f}GB")
    else:
        print(f"  [{WARN}] sdxl-turbo 未下载（如需本机推理请运行）：")
        print(f"        python scripts/download_models.py sdxl-turbo")

    # ─── 环境变量 ─────────────────────────────────────────
    section("环境变量")
    import os
    for env_var, desc in [
        ("AGNES_API_KEY", "Agnes 云 API key（不用 Agnes 可空）"),
        ("OPENAI_API_KEY", "OpenAI key（不用可空）"),
        ("HF_ENDPOINT", "HuggingFace 镜像（中国大陆建议设置 https://hf-mirror.com）"),
    ]:
        v = os.environ.get(env_var, "")
        if v:
            shown = v[:6] + "..." if len(v) > 8 and "KEY" in env_var else v
            print(f"  [{OK}] {env_var}={shown}  ({desc})")
        else:
            print(f"  [ ] {env_var}  ({desc})")

    print()
    print("=" * 60)
    print(f"总体: {'✓ OK' if overall else '✗ 必装项有缺失'}")
    print("=" * 60)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
