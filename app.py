"""fx-generator Web UI（v0.2.0）

重构思路：
- 单页响应式，不分 4 步页（实测分页对单人迭代反而更乱）
- 全链路上下文一屏看全：候选 Gallery + 已选图 + 处理后图 始终都在
- 删合规清单（PM 评价：伪安全），改为 prompt 上方一行红色提醒
- 删步骤徽章（单人不需要）
- Prompt 工程化：风格预设按钮 / 品类模板 / negative 模板 / 历史下拉
- smoke test：调试 Tab 一键端到端
- last_session：启动恢复 / 退出保存
- Mac Python 3.9 兼容

不变：
- launch() 签名
- 生产 / 调试双 Tab
- RingLog 纯文本日志
- TimedTask 子线程 + 超时保护
- lib/* 不动
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

import gradio as gr
from PIL import Image

from lib.config import OUTPUT_ROOT, load_providers, ProviderEntry
from lib.matting import (
    DEFAULT_MODEL as DEFAULT_MATTING,
    SUPPORTED_MODELS as MATTING_MODELS,
    remove_background,
    warmup as rembg_warmup,
)
from lib.normalize import normalize_for_ec, safe_filename
from lib.packager import AssetItem, GenerationInfo, PackMeta, pack_project
from lib.providers import ProviderConfig, get_provider
from lib.prompts import (
    STYLE_PRESETS,
    CATEGORY_TEMPLATES,
    NEGATIVE_PRESETS,
    add_history,
    history_choices,
    get_history_record,
    save_last_session,
    load_last_session,
)


# ════════════════════════════════════════════════════════════
# 0. 常量
# ════════════════════════════════════════════════════════════

LOG_MAX_LINES = 200
TIMEOUT_GENERATE = 600
TIMEOUT_MATTING = 300
TIMEOUT_NORMALIZE = 60
TIMEOUT_WARMUP = 300

# Prompt 上方红色提醒（替代 7 条合规清单）
COMPLIANCE_BANNER_HTML = """
<div style="background:#fff3cd;border-left:4px solid #ff6b6b;padding:10px 14px;
            margin:8px 0;border-radius:4px;color:#5c2c2c;font-size:13px;">
  <b>⚠️ 自我提醒</b>：不要做 真人换脸 / 明星 / 政治人物 / 色情 / 血腥 /
  受版权 IP 内容；上架时按抖音指引标"AI 生成"。<b>工具不拦截，由你负责。</b>
</div>
"""


# ════════════════════════════════════════════════════════════
# 1. 日志（沿用 v0.1.2）
# ════════════════════════════════════════════════════════════

class RingLog:
    def __init__(self, max_lines: int = LOG_MAX_LINES):
        self._buf: deque = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def write(self, msg: str, level: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S.") + f"{datetime.now().microsecond // 1000:03d}"
        line = f"[{ts}] {level.upper():5s} | {msg}"
        with self._lock:
            self._buf.append(line)

    def info(self, msg: str) -> None:
        self.write(msg, "info")

    def warn(self, msg: str) -> None:
        self.write(msg, "warn")

    def error(self, msg: str) -> None:
        self.write(msg, "error")

    def exc(self, msg: str, exc: BaseException) -> None:
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tail = "".join(tb_lines).strip().splitlines()[-3:]
        self.write(f"{msg}: {exc}", "error")
        for ln in tail:
            self.write(f"  | {ln.strip()}", "error")

    def render(self) -> str:
        with self._lock:
            return "\n".join(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


LOG_PROD = RingLog()
LOG_DEBUG = RingLog()


# ════════════════════════════════════════════════════════════
# 2. TimedTask：子线程 + 主线程 progress 心跳（沿用）
# ════════════════════════════════════════════════════════════

def _short_tb(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


@dataclass
class TimedTask:
    target: callable
    timeout_s: float
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

    _result: object = None
    _exc: Optional[BaseException] = None
    _done: threading.Event = field(default_factory=threading.Event)

    def _runner(self):
        try:
            self._result = self.target(*self.args, **self.kwargs)
        except BaseException as e:
            self._exc = e
        finally:
            self._done.set()

    def run_sync_with_progress(self, log: RingLog, label: str, progress: gr.Progress):
        t0 = time.monotonic()
        log.info(f"[{label}] 开始")
        thread = threading.Thread(target=self._runner, daemon=True)
        thread.start()
        while not self._done.is_set():
            elapsed = time.monotonic() - t0
            if elapsed > self.timeout_s:
                log.error(f"[{label}] 超时 {self.timeout_s:.0f}s")
                raise TimeoutError(f"{label} 超过 {self.timeout_s:.0f}s 仍未完成")
            ratio = min(0.95, elapsed / self.timeout_s)
            try:
                progress(ratio, desc=f"{label}（已用 {elapsed:.1f}s）")
            except Exception:
                pass
            time.sleep(0.3)

        elapsed = time.monotonic() - t0
        if self._exc is not None:
            log.exc(f"[{label}] 失败（耗时 {elapsed:.2f}s）", self._exc)
            raise self._exc
        log.info(f"[{label}] 完成（耗时 {elapsed:.2f}s）")
        try:
            progress(1.0, desc=f"{label} 完成（{elapsed:.1f}s）")
        except Exception:
            pass
        return self._result


# ════════════════════════════════════════════════════════════
# 3. Provider 缓存
# ════════════════════════════════════════════════════════════

_provider_cache = {}


def _build_provider_config(entry: ProviderEntry) -> ProviderConfig:
    api_key = os.environ.get(entry.api_key_env, "") if entry.api_key_env else ""
    return ProviderConfig(
        endpoint=entry.endpoint,
        api_key=api_key,
        model=entry.default_model,
        extra=entry.extra or {},
    )


def _get_provider_instance(entry: ProviderEntry, log: RingLog):
    if entry.id in _provider_cache:
        return _provider_cache[entry.id]
    cfg = _build_provider_config(entry)
    log.info(f"初始化 Provider {entry.id}（{entry.display_name}）...")
    t0 = time.monotonic()
    prov = get_provider(entry.id, config=cfg)
    log.info(f"Provider {entry.id} 就绪（{time.monotonic() - t0:.2f}s）")
    _provider_cache[entry.id] = prov
    return prov


def _provider_choices():
    return [(p.display_name, p.id) for p in load_providers() if p.enabled]


# ════════════════════════════════════════════════════════════
# 4. 生产：handler
# ════════════════════════════════════════════════════════════

def handle_generate(provider_id: str, prompt: str, negative_prompt: str,
                    seed_text: str, n_candidates: str, size: str,
                    progress=gr.Progress()):
    log = LOG_PROD
    if not prompt.strip():
        log.error("生成: 缺少 prompt")
        raise gr.Error("请输入 prompt")

    providers = load_providers()
    entry = next((p for p in providers if p.id == provider_id), None)
    if entry is None:
        log.error(f"生成: 未知 Provider {provider_id}")
        raise gr.Error(f"未知 Provider: {provider_id}")
    if entry.api_key_env and not os.environ.get(entry.api_key_env):
        log.error(f"生成: 环境变量 {entry.api_key_env} 未设置")
        raise gr.Error(f"环境变量 {entry.api_key_env} 未设置，请设置后重启 app")

    tmp_dir = Path(tempfile.mkdtemp(prefix="fxgen_"))
    seed_val = int(seed_text) if seed_text and seed_text.strip().lstrip("-").isdigit() else None
    n = int(n_candidates)

    log.info(f"生成开始 provider={provider_id} n={n} size={size} seed={seed_val} prompt_len={len(prompt)}")

    try:
        prov = _get_provider_instance(entry, log)
    except Exception as e:
        log.exc("Provider 初始化失败", e)
        raise gr.Error(f"Provider 初始化失败：{_short_tb(e)}")

    def _do():
        try:
            return prov.generate(
                prompt=prompt, n=n, size=size, seed=seed_val,
                negative_prompt=negative_prompt.strip() or None,
                output_dir=tmp_dir, progress_cb=None,
            )
        except TypeError:
            return prov.generate(
                prompt=prompt, n=n, size=size, seed=seed_val,
                negative_prompt=negative_prompt.strip() or None,
                output_dir=tmp_dir,
            )

    task = TimedTask(target=_do, timeout_s=TIMEOUT_GENERATE)
    try:
        paths = task.run_sync_with_progress(log, "生成图片", progress)
    except TimeoutError as e:
        raise gr.Error(str(e))
    except Exception as e:
        raise gr.Error(f"生成失败：{_short_tb(e)}")

    log.info(f"收到 {len(paths)} 张候选")
    images = [Image.open(p) for p in paths]

    # 写历史
    first_path = str(paths[0]) if paths else None
    add_history(prompt, negative_prompt, seed_val, provider_id, size, first_path)

    # 同时保存 last_session
    save_last_session({
        "provider_id": provider_id,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "seed": seed_text,
        "n_candidates": n_candidates,
        "size": size,
    })

    return (
        images,
        log.render(),
        str(tmp_dir),
        prompt,
        negative_prompt,
        str(seed_val) if seed_val is not None else "",
        gr.update(choices=history_choices()),  # 刷新历史下拉
    )


def handle_select_candidate(evt: gr.SelectData, state_dir: str):
    log = LOG_PROD
    if not state_dir:
        raise gr.Error("请先生成候选图")
    src_dir = Path(state_dir)
    candidates = sorted(src_dir.glob("candidate_*.png"))
    idx = evt.index
    if idx < 0 or idx >= len(candidates):
        raise gr.Error("无效选择")
    log.info(f"已选中候选 {idx + 1}: {candidates[idx].name}")
    return Image.open(candidates[idx]), log.render()


def handle_remove_bg(img, matting_model: str, progress=gr.Progress()):
    log = LOG_PROD
    if img is None:
        raise gr.Error("请先选一张候选图")
    log.info(f"抠图开始 model={matting_model} size={img.size}")

    def _do():
        return remove_background(img, model=matting_model, progress_cb=None)

    task = TimedTask(target=_do, timeout_s=TIMEOUT_MATTING)
    try:
        out = task.run_sync_with_progress(log, "抠图", progress)
    except TimeoutError as e:
        raise gr.Error(str(e))
    except Exception as e:
        raise gr.Error(f"抠图失败：{_short_tb(e)}")
    return out, log.render()


def handle_normalize(img, progress=gr.Progress()):
    log = LOG_PROD
    if img is None:
        raise gr.Error("没有可规范化的图")
    log.info(f"规范化开始 from {img.size}")

    def _do():
        return normalize_for_ec(img, (1024, 1024))

    task = TimedTask(target=_do, timeout_s=TIMEOUT_NORMALIZE)
    try:
        out = task.run_sync_with_progress(log, "规范化", progress)
    except Exception as e:
        raise gr.Error(f"规范化失败：{_short_tb(e)}")
    return out, log.render()


def handle_skip_matting(img):
    """跳过抠图，直接走原图（user 想自己用 PS 抠 / 已是透明图）。"""
    log = LOG_PROD
    if img is None:
        raise gr.Error("请先选一张候选图")
    log.info("跳过抠图，使用原图作为处理结果")
    return img, log.render()


def handle_export(img, project_name, provider_id, prompt, negative_prompt, seed):
    log = LOG_PROD
    if img is None:
        raise gr.Error("没有可导出的图")
    if not project_name.strip():
        raise gr.Error("请输入项目名")

    project_safe = safe_filename(project_name)
    out_dir = OUTPUT_ROOT / f"{date.today().isoformat()}-{project_safe}"
    (out_dir / "processed").mkdir(parents=True, exist_ok=True)

    final_name = safe_filename(f"{project_safe}_face_paint_main") + ".png"
    final_path = out_dir / "processed" / final_name
    img.save(final_path, "PNG")
    log.info(f"已保存 {final_path}")

    providers = load_providers()
    entry = next((p for p in providers if p.id == provider_id), None)
    backend_str = provider_id + (f" / {entry.default_model}" if entry and entry.default_model else "")

    meta = PackMeta(
        project_name=project_safe,
        scenario="S1",
        items=[
            AssetItem(
                filename=final_name,
                kind="face_texture",
                size=(1024, 1024),
                generation=GenerationInfo(
                    backend=backend_str,
                    model_id=entry.default_model if entry else None,
                    prompt=prompt or "",
                    negative_prompt=negative_prompt or "",
                    seed=int(seed) if seed and str(seed).strip().lstrip("-").isdigit() else -1,
                ),
                postprocess=["rembg", "resize_1024x1024", "rgba"],
            )
        ],
    )

    try:
        zip_path = pack_project(out_dir, meta)
    except Exception as e:
        log.exc("打包失败", e)
        raise gr.Error(f"打包失败：{_short_tb(e)}")

    log.info(f"导出完成 {zip_path}")
    return str(zip_path), f"✓ 素材包已生成: {zip_path}", log.render()


# ════════════════════════════════════════════════════════════
# 5. Prompt 工程化辅助
# ════════════════════════════════════════════════════════════

def append_style(current_prompt: str, style_text: str) -> str:
    """风格预设：追加到 prompt 末尾（去重）。"""
    if not current_prompt:
        return style_text
    if style_text in current_prompt:
        return current_prompt
    return current_prompt.rstrip(", ") + ", " + style_text


def apply_template(template_text: str) -> str:
    """品类模板：直接覆盖 prompt（用 [THEME] 占位让用户后填）。"""
    return template_text


def restore_from_history(idx: int):
    """从历史记录恢复 prompt / negative / seed。"""
    if idx is None:
        return gr.update(), gr.update(), gr.update()
    rec = get_history_record(idx)
    if rec is None:
        return gr.update(), gr.update(), gr.update()
    return (
        rec.get("prompt", ""),
        rec.get("negative_prompt", ""),
        str(rec.get("seed", -1)) if rec.get("seed", -1) >= 0 else "",
    )


# ════════════════════════════════════════════════════════════
# 6. 调试 handler
# ════════════════════════════════════════════════════════════

def debug_check_env():
    log = LOG_DEBUG
    log.info("调试: 开始环境检测")
    lines = []
    lines.append(f"Python: {sys.version.split()[0]}  ({sys.executable})")

    for pkg in ["PIL", "rembg", "onnxruntime", "openai", "httpx",
                "pydantic", "gradio", "click"]:
        try:
            mod = __import__(pkg if pkg != "PIL" else "PIL")
            ver = getattr(mod, "__version__", "?")
            lines.append(f"  ✓ {pkg:<14} v{ver}")
        except Exception as e:
            lines.append(f"  ✗ {pkg:<14} {e}")

    try:
        import torch
        lines.append(f"\ntorch: v{torch.__version__}")
        cuda_ok = torch.cuda.is_available()
        lines.append(f"  CUDA available: {cuda_ok}")
        if cuda_ok:
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name(i)
                free, total = torch.cuda.mem_get_info(i)
                cap = torch.cuda.get_device_capability(i)
                lines.append(f"  GPU{i}: {name}  sm_{cap[0]}{cap[1]}  显存 {total / 1024**3:.1f}GB（空闲 {free / 1024**3:.1f}GB）")
        if hasattr(torch.backends, "mps"):
            lines.append(f"  MPS available: {torch.backends.mps.is_available()}")
    except ImportError:
        lines.append("\ntorch: 未安装（云 Provider 不影响）")

    lines.append("\n已注册 Provider:")
    for p in load_providers():
        v = os.environ.get(p.api_key_env, "") if p.api_key_env else ""
        key_state = "(key 已设置)" if v else "(key 未设置)" if p.api_key_env else ""
        lines.append(f"  {'✓' if p.enabled else '✗'} {p.id:<12} {p.display_name}  {key_state}")

    from lib.config import RUNTIME_ROOT, MODELS_CACHE, REMBG_CACHE, OUTPUT_ROOT as OR
    lines.append("\n运行时目录:")
    lines.append(f"  RUNTIME_ROOT: {RUNTIME_ROOT}")
    lines.append(f"  MODELS_CACHE: {MODELS_CACHE}")
    lines.append(f"  REMBG_CACHE:  {REMBG_CACHE}  (.onnx 数: {len(list(REMBG_CACHE.glob('*.onnx')))})")
    lines.append(f"  OUTPUT_ROOT:  {OR}")

    out = "\n".join(lines)
    log.info("调试: 环境检测完成")
    return out, LOG_DEBUG.render()


def debug_warmup_rembg(model: str, progress=gr.Progress()):
    log = LOG_DEBUG
    log.info(f"调试: 预热 rembg model={model}")

    def _do():
        rembg_warmup(model, progress_cb=None)
        return True

    task = TimedTask(target=_do, timeout_s=TIMEOUT_WARMUP)
    try:
        task.run_sync_with_progress(log, f"预热 rembg ({model})", progress)
    except Exception as e:
        return f"✗ 失败：{_short_tb(e)}", LOG_DEBUG.render()
    return f"✓ rembg 模型 {model} 已就绪", LOG_DEBUG.render()


def debug_test_generate_one(provider_id: str, progress=gr.Progress()):
    log = LOG_DEBUG
    providers = load_providers()
    entry = next((p for p in providers if p.id == provider_id), None)
    if entry is None:
        return None, f"未知 Provider: {provider_id}", LOG_DEBUG.render()
    if entry.api_key_env and not os.environ.get(entry.api_key_env):
        return None, f"环境变量 {entry.api_key_env} 未设置", LOG_DEBUG.render()

    log.info(f"调试: 单步生成测试 provider={provider_id}")
    try:
        prov = _get_provider_instance(entry, log)
    except Exception as e:
        log.exc("调试: Provider 初始化失败", e)
        return None, f"✗ Provider 初始化失败：{_short_tb(e)}", LOG_DEBUG.render()

    tmp_dir = Path(tempfile.mkdtemp(prefix="fxgen_debug_"))

    def _do():
        try:
            return prov.generate(
                prompt="a simple test pattern, geometric shape, clean background",
                n=1, size="512x512", seed=42, negative_prompt=None,
                output_dir=tmp_dir, progress_cb=None,
            )
        except TypeError:
            return prov.generate(
                prompt="a simple test pattern, geometric shape, clean background",
                n=1, size="512x512", seed=42, negative_prompt=None,
                output_dir=tmp_dir,
            )

    task = TimedTask(target=_do, timeout_s=TIMEOUT_GENERATE)
    try:
        paths = task.run_sync_with_progress(log, "单步生成", progress)
    except Exception as e:
        return None, f"✗ 失败：{_short_tb(e)}", LOG_DEBUG.render()

    if not paths:
        return None, "✗ 返回 0 张图", LOG_DEBUG.render()
    return Image.open(paths[0]), f"✓ 收到 1 张（{paths[0].name}）", LOG_DEBUG.render()


def debug_test_matting(img, model: str, progress=gr.Progress()):
    log = LOG_DEBUG
    if img is None:
        return None, "请先上传一张图", LOG_DEBUG.render()
    log.info(f"调试: 单步抠图 model={model} size={img.size}")

    def _do():
        return remove_background(img, model=model, progress_cb=None)

    task = TimedTask(target=_do, timeout_s=TIMEOUT_MATTING)
    try:
        out = task.run_sync_with_progress(log, f"单步抠图 ({model})", progress)
    except Exception as e:
        return None, f"✗ 失败：{_short_tb(e)}", LOG_DEBUG.render()
    return out, "✓ 抠图完成", LOG_DEBUG.render()


def debug_smoke_test(provider_id: str, progress=gr.Progress()):
    """端到端 smoke test：Provider → 生成 → rembg → 规范化 → 打包，记录每步耗时。"""
    log = LOG_DEBUG
    log.info(f"调试: smoke test 开始 provider={provider_id}")
    timings = []

    try:
        # Step 1
        t0 = time.monotonic()
        progress(0.05, desc="[1/5] 初始化 Provider...")
        providers = load_providers()
        entry = next((p for p in providers if p.id == provider_id), None)
        if entry is None:
            return f"✗ 未知 Provider: {provider_id}", LOG_DEBUG.render()
        if entry.api_key_env and not os.environ.get(entry.api_key_env):
            return f"✗ 环境变量 {entry.api_key_env} 未设置", LOG_DEBUG.render()
        prov = _get_provider_instance(entry, log)
        timings.append(("[1/5] Provider 初始化", time.monotonic() - t0, "✓"))

        # Step 2
        t0 = time.monotonic()
        progress(0.20, desc="[2/5] 生成 1 张测试图...")
        tmp_dir = Path(tempfile.mkdtemp(prefix="fxgen_smoke_"))
        try:
            paths = prov.generate(
                prompt="a simple geometric test pattern, clean white background",
                n=1, size="512x512", seed=42, negative_prompt=None,
                output_dir=tmp_dir,
            )
        except TypeError:
            paths = prov.generate(
                prompt="a simple geometric test pattern, clean white background",
                n=1, size="512x512", seed=42, negative_prompt=None,
                output_dir=tmp_dir,
            )
        if not paths:
            return f"✗ 生成返回 0 张", LOG_DEBUG.render()
        timings.append(("[2/5] 生成 1 张 512×512", time.monotonic() - t0, "✓"))

        # Step 3
        t0 = time.monotonic()
        progress(0.55, desc="[3/5] rembg 抠图...")
        img = Image.open(paths[0])
        try:
            matted = remove_background(img, model=DEFAULT_MATTING)
            timings.append(("[3/5] rembg 抠图", time.monotonic() - t0, "✓"))
        except Exception as e:
            timings.append(("[3/5] rembg 抠图", time.monotonic() - t0, f"✗ {e}"))
            matted = img.convert("RGBA")

        # Step 4
        t0 = time.monotonic()
        progress(0.80, desc="[4/5] 规范化...")
        normalized = normalize_for_ec(matted, (1024, 1024))
        timings.append(("[4/5] 规范化", time.monotonic() - t0, "✓"))

        # Step 5
        t0 = time.monotonic()
        progress(0.95, desc="[5/5] 打包 zip...")
        out_dir = OUTPUT_ROOT / f"smoke_test_{datetime.now().strftime('%H%M%S')}"
        (out_dir / "processed").mkdir(parents=True, exist_ok=True)
        final_path = out_dir / "processed" / "smoke_test.png"
        normalized.save(final_path, "PNG")
        meta = PackMeta(
            project_name="smoke_test",
            scenario="SMOKE",
            items=[AssetItem(
                filename="smoke_test.png", kind="face_texture",
                size=(1024, 1024),
                generation=GenerationInfo(
                    backend=provider_id, model_id=entry.default_model,
                    prompt="smoke", seed=42,
                ),
                postprocess=["rembg", "normalize"],
            )],
        )
        zip_path = pack_project(out_dir, meta)
        timings.append(("[5/5] 打包 zip", time.monotonic() - t0, "✓"))

        progress(1.0, desc="完成")

        report_lines = ["[Smoke Test 报告]", "=" * 50]
        total = 0.0
        for name, t, status in timings:
            report_lines.append(f"  {name:<28} {t:>6.2f}s   {status}")
            total += t
        report_lines.append("-" * 50)
        report_lines.append(f"  {'总耗时':<28} {total:>6.2f}s")
        report_lines.append(f"  产物: {zip_path}")
        report = "\n".join(report_lines)
        log.info(f"smoke test 完成: 总耗时 {total:.2f}s")
        return report, LOG_DEBUG.render()

    except Exception as e:
        log.exc("smoke test 异常", e)
        return f"✗ Smoke test 异常: {_short_tb(e)}", LOG_DEBUG.render()


def prod_clear_log():
    LOG_PROD.clear()
    return ""


def debug_clear_log():
    LOG_DEBUG.clear()
    return ""


def refresh_log_prod():
    return LOG_PROD.render()


def refresh_log_debug():
    return LOG_DEBUG.render()


# ════════════════════════════════════════════════════════════
# 7. UI
# ════════════════════════════════════════════════════════════

CSS = """
.fxgen-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; padding: 14px 20px; border-radius: 10px; margin-bottom: 12px;
}
.fxgen-header h1 { color: white; margin: 0; font-size: 21px; }
.fxgen-header p  { color: #e0e0ff; margin: 6px 0 0; font-size: 13px; }
.fxgen-log textarea {
    background: #1e1e1e !important; color: #d4d4d4 !important;
    font-family: 'SF Mono', Menlo, Consolas, monospace !important;
    font-size: 12px !important; line-height: 1.45 !important;
}
/* 关键：让图片自适应高度，不拖滑块 */
.fxgen-image-block img {
    max-height: 60vh !important; object-fit: contain !important;
}
.fxgen-gallery .grid-wrap {
    max-height: 50vh !important; overflow-y: auto !important;
}
.fxgen-section-title {
    font-size: 14px; font-weight: 600; color: #555;
    margin: 12px 0 6px 0; padding-bottom: 4px;
    border-bottom: 1px solid #e0e0e0;
}
"""


def build_ui() -> gr.Blocks:
    last = load_last_session()

    with gr.Blocks(
        title="fx-generator v0.2.0",
        css=CSS,
        theme=gr.themes.Soft(),
    ) as demo:
        gr.HTML(
            """
            <div class="fxgen-header">
              <h1>fx-generator · 抖音特效素材生成</h1>
              <p>单页流程：写 Prompt → 生成 → 选图 → 抠图/规范化 → 导出 zip · 拖进 Douyin AR 上架</p>
            </div>
            """
        )

        # ─── 顶层 Tabs ───────────────────────────────────────
        with gr.Tabs():
            # ============================================================
            # 生产 Tab：单页响应式
            # ============================================================
            with gr.Tab("🎨 素材生产"):
                state_dir = gr.State("")
                state_prompt = gr.State("")
                state_negative = gr.State("")
                state_seed = gr.State("")

                # 红色合规提醒（替代 7 条勾选）
                gr.HTML(COMPLIANCE_BANNER_HTML)

                # ─── 主区域：左参数 / 右图片（响应式） ───────
                with gr.Row():
                    # ─── 左：参数 / Prompt 工程化 ───
                    with gr.Column(scale=2, min_width=380):
                        gr.HTML('<div class="fxgen-section-title">① Provider</div>')
                        provider_dd = gr.Dropdown(
                            label="Provider",
                            choices=_provider_choices(),
                            value=last.get("provider_id") or (_provider_choices()[0][1] if _provider_choices() else None),
                            show_label=False,
                            container=False,
                        )

                        gr.HTML('<div class="fxgen-section-title">② 品类模板（可选，覆盖 prompt）</div>')
                        category_btns = []
                        with gr.Row():
                            for label, _ in CATEGORY_TEMPLATES[:3]:
                                category_btns.append(gr.Button(label, size="sm"))
                        with gr.Row():
                            for label, _ in CATEGORY_TEMPLATES[3:]:
                                category_btns.append(gr.Button(label, size="sm"))

                        gr.HTML('<div class="fxgen-section-title">③ Prompt</div>')
                        prompt = gr.Textbox(
                            label="Prompt",
                            lines=3,
                            value=last.get("prompt", ""),
                            placeholder="例如：cyberpunk metal mask, frontal symmetric, on transparent background",
                            show_label=False,
                            container=False,
                        )

                        # 风格预设按钮（追加到 prompt 末尾）
                        gr.Markdown("**风格预设**（点击追加到 prompt 末尾）")
                        style_btns = []
                        with gr.Row():
                            for label, _ in STYLE_PRESETS[:4]:
                                style_btns.append(gr.Button(label, size="sm"))
                        with gr.Row():
                            for label, _ in STYLE_PRESETS[4:]:
                                style_btns.append(gr.Button(label, size="sm"))

                        gr.HTML('<div class="fxgen-section-title">④ Negative Prompt</div>')
                        with gr.Row():
                            neg_preset_dd = gr.Dropdown(
                                label="Negative 模板",
                                choices=[(label, label) for label, _ in NEGATIVE_PRESETS],
                                value=NEGATIVE_PRESETS[0][0],
                                show_label=False,
                                container=False,
                                scale=2,
                            )
                            apply_neg_btn = gr.Button("应用", size="sm", scale=1)
                        negative_prompt = gr.Textbox(
                            label="Negative Prompt",
                            lines=2,
                            value=last.get("negative_prompt") or NEGATIVE_PRESETS[0][1],
                            show_label=False,
                            container=False,
                        )

                        gr.HTML('<div class="fxgen-section-title">⑤ 生成参数</div>')
                        with gr.Row():
                            seed = gr.Textbox(label="Seed", value=last.get("seed", ""), placeholder="留空=随机", scale=2)
                            n_candidates = gr.Dropdown(
                                label="候选数",
                                choices=["1", "2", "4", "6"],
                                value=last.get("n_candidates", "4"),
                                scale=1,
                            )
                            size = gr.Dropdown(
                                label="尺寸",
                                choices=["512x512", "768x768", "1024x1024"],
                                value=last.get("size", "1024x1024"),
                                scale=1,
                            )

                        generate_btn = gr.Button("✨ 生成候选图", variant="primary", size="lg")

                        gr.HTML('<div class="fxgen-section-title">📜 历史（最近 20 条，点选可恢复）</div>')
                        with gr.Row():
                            history_dd = gr.Dropdown(
                                label="历史",
                                choices=history_choices(),
                                value=None,
                                show_label=False,
                                container=False,
                                scale=4,
                            )
                            restore_btn = gr.Button("↩️ 恢复", size="sm", scale=1)

                    # ─── 右：候选图 / 选中 / 处理 / 导出（始终显示） ───
                    with gr.Column(scale=3, min_width=400):
                        gr.HTML('<div class="fxgen-section-title">候选图（点选一张作为后续处理对象）</div>')
                        gallery = gr.Gallery(
                            label="候选",
                            columns=2,
                            object_fit="contain",
                            show_label=False,
                            elem_classes=["fxgen-gallery"],
                            height="40vh",
                        )

                        with gr.Row():
                            with gr.Column():
                                gr.HTML('<div class="fxgen-section-title">已选中</div>')
                                selected_img = gr.Image(
                                    label="已选中",
                                    type="pil",
                                    show_label=False,
                                    container=False,
                                    elem_classes=["fxgen-image-block"],
                                )
                            with gr.Column():
                                gr.HTML('<div class="fxgen-section-title">处理后（最终导出）</div>')
                                processed_img = gr.Image(
                                    label="处理后",
                                    type="pil",
                                    show_label=False,
                                    container=False,
                                    elem_classes=["fxgen-image-block"],
                                )

                        gr.HTML('<div class="fxgen-section-title">⑥ 抠图 / 规范化</div>')
                        with gr.Row():
                            matting_model = gr.Dropdown(
                                label="抠图模型",
                                choices=MATTING_MODELS,
                                value=DEFAULT_MATTING,
                                scale=2,
                            )
                            remove_bg_btn = gr.Button("✂️ 抠透明背景", scale=1)
                            skip_matting_btn = gr.Button("↪️ 跳过抠图", size="sm", scale=1)
                        normalize_btn = gr.Button("📐 规范化 1024×1024（必做）", variant="primary")

                        gr.HTML('<div class="fxgen-section-title">⑦ 导出</div>')
                        with gr.Row():
                            project_name = gr.Textbox(
                                label="项目名",
                                placeholder="my-cyberpunk-mask",
                                scale=2,
                            )
                            export_btn = gr.Button("📦 导出 zip", variant="primary", scale=1)
                        export_status = gr.Textbox(label="导出状态", interactive=False)
                        download_file = gr.File(label="下载素材包")

                # ─── 底部日志（默认折叠） ───
                with gr.Accordion("📋 实时日志（生产）", open=False):
                    log_prod_box = gr.Textbox(
                        value="", lines=10, max_lines=20,
                        interactive=False,
                        elem_classes=["fxgen-log"],
                        show_label=False,
                    )
                    with gr.Row():
                        refresh_prod_btn = gr.Button("🔄 刷新", size="sm")
                        clear_prod_btn = gr.Button("🧹 清空", size="sm")

            # ============================================================
            # 调试 Tab
            # ============================================================
            with gr.Tab("🔧 调试工具"):
                gr.Markdown(
                    "**调试页**：环境检查 / 模型预热 / 单步测试 / 端到端 smoke / 完整日志。"
                )

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 1. 环境检测")
                        env_btn = gr.Button("📊 跑一次环境检测")
                        env_output = gr.Textbox(label="环境信息", lines=18, max_lines=30, interactive=False)

                        gr.Markdown("### 2. 预热模型")
                        with gr.Row():
                            debug_matting_model = gr.Dropdown(
                                label="rembg 模型",
                                choices=MATTING_MODELS,
                                value=DEFAULT_MATTING,
                            )
                            warmup_btn = gr.Button("🔥 预热 rembg")
                        warmup_status = gr.Textbox(label="状态", interactive=False)

                    with gr.Column(scale=1):
                        gr.Markdown("### 3. 端到端 Smoke Test")
                        gr.Markdown("一键跑全链路：Provider → 生成 → 抠图 → 规范化 → 打包。打印每步耗时。")
                        smoke_provider_dd = gr.Dropdown(
                            label="Provider",
                            choices=_provider_choices(),
                            value=(_provider_choices()[0][1] if _provider_choices() else None),
                        )
                        smoke_btn = gr.Button("⚡ 跑 Smoke Test", variant="primary")
                        smoke_report = gr.Textbox(label="报告", lines=10, max_lines=20, interactive=False)

                gr.Markdown("---")
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 4. 单步生成测试（512×512, seed=42）")
                        debug_provider_dd = gr.Dropdown(
                            label="Provider",
                            choices=_provider_choices(),
                            value=(_provider_choices()[0][1] if _provider_choices() else None),
                        )
                        debug_gen_btn = gr.Button("⚡ 跑单步生成")
                        debug_gen_status = gr.Textbox(label="状态", interactive=False)
                        debug_gen_img = gr.Image(label="测试图", type="pil", height=240)
                    with gr.Column(scale=1):
                        gr.Markdown("### 5. 单步抠图测试（拖图进去）")
                        debug_matt_input = gr.Image(label="输入图", type="pil", height=200)
                        with gr.Row():
                            debug_matt_model = gr.Dropdown(
                                label="模型", choices=MATTING_MODELS, value=DEFAULT_MATTING,
                            )
                            debug_matt_btn = gr.Button("✂️ 跑单步抠图")
                        debug_matt_status = gr.Textbox(label="状态", interactive=False)
                        debug_matt_out = gr.Image(label="抠图结果", type="pil", height=200)

                gr.Markdown("### 6. 完整日志（始终展开）")
                log_debug_box = gr.Textbox(
                    value="", lines=20, max_lines=40,
                    interactive=False,
                    elem_classes=["fxgen-log"],
                    show_label=False,
                )
                with gr.Row():
                    refresh_debug_btn = gr.Button("🔄 刷新日志", size="sm")
                    clear_debug_btn = gr.Button("🧹 清空日志", size="sm")

        # ═══════════════════════════════════════════════════
        # 事件绑定
        # ═══════════════════════════════════════════════════

        # 生成（同时刷新历史下拉）
        generate_btn.click(
            fn=handle_generate,
            inputs=[provider_dd, prompt, negative_prompt, seed, n_candidates, size],
            outputs=[
                gallery, log_prod_box,
                state_dir, state_prompt, state_negative, state_seed,
                history_dd,
            ],
        )

        # 选图（点 Gallery）
        gallery.select(
            fn=handle_select_candidate,
            inputs=[state_dir],
            outputs=[selected_img, log_prod_box],
        )

        # 抠图
        remove_bg_btn.click(
            fn=handle_remove_bg,
            inputs=[selected_img, matting_model],
            outputs=[processed_img, log_prod_box],
        )

        # 跳过抠图
        skip_matting_btn.click(
            fn=handle_skip_matting,
            inputs=[selected_img],
            outputs=[processed_img, log_prod_box],
        )

        # 规范化
        normalize_btn.click(
            fn=handle_normalize,
            inputs=[processed_img],
            outputs=[processed_img, log_prod_box],
        )

        # 导出
        export_btn.click(
            fn=handle_export,
            inputs=[processed_img, project_name, provider_dd,
                    prompt, negative_prompt, seed],
            outputs=[download_file, export_status, log_prod_box],
        )

        # ─── 风格预设按钮 ────────────────────────────
        for btn, (_, style_text) in zip(style_btns, STYLE_PRESETS):
            btn.click(
                fn=lambda cur, st=style_text: append_style(cur, st),
                inputs=[prompt],
                outputs=[prompt],
                queue=False,
            )

        # ─── 品类模板按钮 ────────────────────────────
        for btn, (_, tmpl) in zip(category_btns, CATEGORY_TEMPLATES):
            btn.click(
                fn=lambda t=tmpl: apply_template(t),
                inputs=None,
                outputs=[prompt],
                queue=False,
            )

        # ─── Negative 模板应用 ───────────────────────
        def _apply_neg(name):
            for n, txt in NEGATIVE_PRESETS:
                if n == name:
                    return txt
            return gr.update()
        apply_neg_btn.click(
            fn=_apply_neg,
            inputs=[neg_preset_dd],
            outputs=[negative_prompt],
            queue=False,
        )

        # ─── 历史恢复 ────────────────────────────────
        restore_btn.click(
            fn=restore_from_history,
            inputs=[history_dd],
            outputs=[prompt, negative_prompt, seed],
            queue=False,
        )

        # ─── 生产日志 ────────────────────────────────
        refresh_prod_btn.click(fn=refresh_log_prod, inputs=None, outputs=[log_prod_box], queue=False)
        clear_prod_btn.click(fn=prod_clear_log, inputs=None, outputs=[log_prod_box], queue=False)

        # ─── 调试 Tab ────────────────────────────────
        env_btn.click(fn=debug_check_env, inputs=None, outputs=[env_output, log_debug_box])
        warmup_btn.click(fn=debug_warmup_rembg, inputs=[debug_matting_model],
                          outputs=[warmup_status, log_debug_box])
        smoke_btn.click(fn=debug_smoke_test, inputs=[smoke_provider_dd],
                         outputs=[smoke_report, log_debug_box])
        debug_gen_btn.click(fn=debug_test_generate_one, inputs=[debug_provider_dd],
                             outputs=[debug_gen_img, debug_gen_status, log_debug_box])
        debug_matt_btn.click(fn=debug_test_matting,
                              inputs=[debug_matt_input, debug_matt_model],
                              outputs=[debug_matt_out, debug_matt_status, log_debug_box])
        refresh_debug_btn.click(fn=refresh_log_debug, inputs=None, outputs=[log_debug_box], queue=False)
        clear_debug_btn.click(fn=debug_clear_log, inputs=None, outputs=[log_debug_box], queue=False)

    return demo


# ════════════════════════════════════════════════════════════
# 8. 启动
# ════════════════════════════════════════════════════════════

def launch():
    """对外暴露的启动入口（fxgen / start.bat / start.sh 都用这个）。"""
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    LOG_PROD.info("fx-generator 启动 (v0.2.0)")
    LOG_DEBUG.info("fx-generator 启动 (v0.2.0)")
    demo = build_ui()
    demo.queue()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True,
        inbrowser=True,
    )


if __name__ == "__main__":
    launch()
