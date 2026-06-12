"""fx-generator Web UI（v0.1.2）

重构要点（vs v0.1.1）：

1. 日志系统重做：纯文本 + 时间戳（含毫秒）+ 200 行环形缓冲。进度条只走 gr.Progress()
   不混入文本日志，文本日志仅记录关键事件、耗时、错误。
2. 生产 / 调试分离：顶层 gr.Tabs 切「生产」「调试工具」。
3. 生产模式按 4 步分页：Step 1 选模型+Prompt → Step 2 选图 → Step 3 抠图+规范化 →
   Step 4 导出。每步右上角带状态徽章（⏳ 待开始 / 🔄 进行中 / ✅ 完成 / ❌ 失败）。
4. 耗时步骤改造：所有重操作走子线程（threading）+ 心跳进度回调，主线程通过状态推进；
   超过单步上限（300s for 抠图 / 600s for 生成）抛错；模型/管线加载耗时单独打点。

约束：
- 仅本文件改动；lib/ 不动。
- 保持 launch() 签名不变。
- Gradio 5/6 兼容（不用 5.x 之后才加的 API）。
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
from lib.safety import COMPLIANCE_ITEMS

# ════════════════════════════════════════════════════════════
# 0. 常量与状态徽章
# ════════════════════════════════════════════════════════════

LOG_MAX_LINES = 200

# 单步操作的硬超时（秒）
TIMEOUT_GENERATE = 600   # 出图（首次冷启可能 30-60s，4 张 SDXL Turbo 约 20s）
TIMEOUT_MATTING = 300    # rembg 抠图（首次 < 30s，后续秒级）
TIMEOUT_NORMALIZE = 60   # 纯像素操作，不可能慢
TIMEOUT_WARMUP = 300     # rembg / SDXL 模型预热

# 状态徽章
BADGE_PENDING = "⏳ 待开始"
BADGE_RUNNING = "🔄 进行中"
BADGE_DONE = "✅ 已完成"
BADGE_ERROR = "❌ 失败"


# ════════════════════════════════════════════════════════════
# 1. 日志系统
# ════════════════════════════════════════════════════════════

class RingLog:
    """线程安全、固定容量、纯文本带毫秒时间戳的日志缓冲。

    UI 只读最近 LOG_MAX_LINES 行；任何调用都不写入 gr.Progress 信息。
    """

    def __init__(self, max_lines: int = LOG_MAX_LINES):
        self._buf: deque[str] = deque(maxlen=max_lines)
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
        """记录异常 + 截断后的 traceback（最多 3 行）。"""
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        # 取倒数 3 行（最贴近抛出点的内容）
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


# 生产 / 调试 各自独立的日志缓冲（避免相互污染）
LOG_PROD = RingLog()
LOG_DEBUG = RingLog()


# ════════════════════════════════════════════════════════════
# 2. 通用工具
# ════════════════════════════════════════════════════════════

def _short_tb(exc: BaseException) -> str:
    """用于 gr.Error() 显示的简短 trace。"""
    return f"{type(exc).__name__}: {exc}"


@dataclass
class TimedTask:
    """一个带超时的后台任务，主线程轮询其 done 状态以推进 gr.Progress。"""

    target: callable
    timeout_s: float
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

    _result: object = None
    _exc: BaseException | None = None
    _done: threading.Event = field(default_factory=threading.Event)

    def _runner(self):
        try:
            self._result = self.target(*self.args, **self.kwargs)
        except BaseException as e:  # 兜底捕获
            self._exc = e
        finally:
            self._done.set()

    def run_sync_with_progress(self, log: RingLog, label: str, progress: gr.Progress):
        """启动子线程跑 target，主线程驱动进度条。"""
        t0 = time.monotonic()
        log.info(f"[{label}] 开始")
        thread = threading.Thread(target=self._runner, daemon=True)
        thread.start()

        # 心跳：每 0.3s 推一次进度（伪进度，因为 target 多数无法报告真实百分比）
        # 上限走 timeout，进度条用"已用时长 / 超时"近似
        while not self._done.is_set():
            elapsed = time.monotonic() - t0
            if elapsed > self.timeout_s:
                log.error(f"[{label}] 超时 {self.timeout_s:.0f}s，强制放弃")
                # 子线程不能强 kill，只能标记并放弃等待
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
# 3. Provider 实例缓存
# ════════════════════════════════════════════════════════════

_provider_cache: dict[str, object] = {}


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


def _provider_choices() -> list[tuple[str, str]]:
    return [(p.display_name, p.id) for p in load_providers() if p.enabled]


# ════════════════════════════════════════════════════════════
# 4. 生产页：4 步流水线 handler
# ════════════════════════════════════════════════════════════

# 4.1 Step 1：生成候选图 ─────────────────────────────────────

def handle_generate(
    provider_id: str,
    prompt: str,
    negative_prompt: str,
    seed_text: str,
    n_candidates: str,
    size: str,
    progress=gr.Progress(),
):
    """生成候选图（同步阻塞 + 进度条 + 日志）。

    返回顺序匹配 outputs：
      [gallery, log_text, state_dir, state_prompt, state_negative, state_seed,
       step1_badge, step2_badge]
    """
    log = LOG_PROD

    if not prompt.strip():
        log.error("Step1: 缺少 prompt")
        raise gr.Error("请输入 prompt")

    providers = load_providers()
    entry = next((p for p in providers if p.id == provider_id), None)
    if entry is None:
        log.error(f"Step1: 未知 Provider {provider_id}")
        raise gr.Error(f"未知 Provider: {provider_id}")
    if entry.api_key_env and not os.environ.get(entry.api_key_env):
        log.error(f"Step1: 环境变量 {entry.api_key_env} 未设置")
        raise gr.Error(
            f"环境变量 {entry.api_key_env} 未设置。\n"
            f"请设置后重启 app。"
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="fxgen_"))
    seed_val = int(seed_text) if seed_text and seed_text.strip().lstrip("-").isdigit() else None
    n = int(n_candidates)

    log.info(
        f"Step1: 生成开始 provider={provider_id} n={n} size={size} "
        f"seed={seed_val} prompt_len={len(prompt)}"
    )

    try:
        prov = _get_provider_instance(entry, log)
    except Exception as e:
        log.exc("Step1: Provider 初始化失败", e)
        raise gr.Error(f"Provider 初始化失败：{_short_tb(e)}")

    def _do_generate():
        # 不所有 provider 都接受 progress_cb，做兼容
        try:
            return prov.generate(
                prompt=prompt,
                n=n,
                size=size,
                seed=seed_val,
                negative_prompt=negative_prompt.strip() or None,
                output_dir=tmp_dir,
                progress_cb=None,  # 子线程内部不直接驱动 gr.Progress
            )
        except TypeError:
            return prov.generate(
                prompt=prompt,
                n=n,
                size=size,
                seed=seed_val,
                negative_prompt=negative_prompt.strip() or None,
                output_dir=tmp_dir,
            )

    task = TimedTask(target=_do_generate, timeout_s=TIMEOUT_GENERATE)
    try:
        paths = task.run_sync_with_progress(log, "Step1 生成图片", progress)
    except TimeoutError as e:
        raise gr.Error(str(e))
    except Exception as e:
        raise gr.Error(f"生成失败：{_short_tb(e)}")

    log.info(f"Step1: 收到 {len(paths)} 张候选")
    images = [Image.open(p) for p in paths]
    return (
        images,
        log.render(),
        str(tmp_dir),
        prompt,
        negative_prompt,
        str(seed_val) if seed_val is not None else "",
        _badge_html(BADGE_DONE),        # step1_badge
        _badge_html(BADGE_RUNNING),     # step2_badge（候选已就绪，等用户选）
    )


# 4.2 Step 2：选图 ───────────────────────────────────────────

def handle_select_candidate(evt: gr.SelectData, state_dir: str):
    log = LOG_PROD
    if not state_dir:
        log.error("Step2: state_dir 空，未先生成")
        raise gr.Error("请先在 Step 1 生成候选图")

    src_dir = Path(state_dir)
    candidates = sorted(src_dir.glob("candidate_*.png"))
    idx = evt.index
    if idx < 0 or idx >= len(candidates):
        log.error(f"Step2: 越界 idx={idx} total={len(candidates)}")
        raise gr.Error("无效选择")

    log.info(f"Step2: 已选中候选 {idx + 1}: {candidates[idx].name}")
    return (
        Image.open(candidates[idx]),
        log.render(),
        _badge_html(BADGE_DONE),         # step2_badge
        _badge_html(BADGE_RUNNING),      # step3_badge
    )


# 4.3 Step 3：抠图 / 规范化 ─────────────────────────────────

def handle_remove_bg(img, matting_model: str, progress=gr.Progress()):
    log = LOG_PROD
    if img is None:
        log.error("Step3: 没有选中图")
        raise gr.Error("请先在 Step 2 选一张候选图")

    log.info(f"Step3: 抠图开始 model={matting_model} size={img.size}")

    def _do_matting():
        return remove_background(img, model=matting_model, progress_cb=None)

    task = TimedTask(target=_do_matting, timeout_s=TIMEOUT_MATTING)
    try:
        out = task.run_sync_with_progress(log, "Step3 抠图", progress)
    except TimeoutError as e:
        raise gr.Error(str(e))
    except Exception as e:
        raise gr.Error(f"抠图失败：{_short_tb(e)}")

    return out, log.render(), _badge_html(BADGE_RUNNING)


def handle_normalize(img, progress=gr.Progress()):
    log = LOG_PROD
    if img is None:
        log.error("Step3: 没有可规范化的图")
        raise gr.Error("请先抠背景或选图")

    log.info(f"Step3: 规范化开始 from {img.size}")

    def _do_normalize():
        return normalize_for_ec(img, (1024, 1024))

    task = TimedTask(target=_do_normalize, timeout_s=TIMEOUT_NORMALIZE)
    try:
        out = task.run_sync_with_progress(log, "Step3 规范化", progress)
    except TimeoutError as e:
        raise gr.Error(str(e))
    except Exception as e:
        raise gr.Error(f"规范化失败：{_short_tb(e)}")

    return out, log.render(), _badge_html(BADGE_DONE), _badge_html(BADGE_RUNNING)  # step3 完成 → step4 进行中


# 4.4 Step 4：导出 ───────────────────────────────────────────

def handle_export(
    img,
    project_name,
    provider_id,
    prompt,
    negative_prompt,
    seed,
    *checklist_states,
):
    log = LOG_PROD
    if img is None:
        log.error("Step4: 没有可导出的图")
        raise gr.Error("请先完成 Step 3 处理")
    if not project_name.strip():
        log.error("Step4: 项目名为空")
        raise gr.Error("请输入项目名")
    if not all(checklist_states):
        log.error("Step4: 合规自检未全勾选")
        raise gr.Error(f"请完成全部 {len(COMPLIANCE_ITEMS)} 项合规自检")

    project_safe = safe_filename(project_name)
    out_dir = OUTPUT_ROOT / f"{date.today().isoformat()}-{project_safe}"
    (out_dir / "processed").mkdir(parents=True, exist_ok=True)

    final_name = safe_filename(f"{project_safe}_face_paint_main") + ".png"
    final_path = out_dir / "processed" / final_name
    img.save(final_path, "PNG")
    log.info(f"Step4: 已保存 {final_path}")

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
        log.exc("Step4: 打包失败", e)
        raise gr.Error(f"打包失败：{_short_tb(e)}")

    log.info(f"Step4: 导出完成 {zip_path}")
    return (
        str(zip_path),
        f"✓ 素材包已生成: {zip_path}",
        log.render(),
        _badge_html(BADGE_DONE),         # step4_badge
    )


# ════════════════════════════════════════════════════════════
# 5. 调试页 handler
# ════════════════════════════════════════════════════════════

def debug_check_env():
    """收集环境信息（与 scripts/check_env.py 行为一致但简化）。"""
    log = LOG_DEBUG
    log.info("调试: 开始环境检测")
    lines: list[str] = []

    # Python
    lines.append(f"Python: {sys.version.split()[0]}  ({sys.executable})")

    # 关键依赖
    for pkg in ["PIL", "rembg", "onnxruntime", "openai", "httpx",
                "pydantic", "gradio", "click"]:
        try:
            mod = __import__(pkg if pkg != "PIL" else "PIL")
            ver = getattr(mod, "__version__", "?")
            lines.append(f"  ✓ {pkg:<14} v{ver}")
        except Exception as e:
            lines.append(f"  ✗ {pkg:<14} {e}")

    # torch / GPU
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
                lines.append(
                    f"  GPU{i}: {name}  sm_{cap[0]}{cap[1]}  "
                    f"显存 {total / 1024**3:.1f}GB（空闲 {free / 1024**3:.1f}GB）"
                )
        if hasattr(torch.backends, "mps"):
            lines.append(f"  MPS available: {torch.backends.mps.is_available()}")
    except ImportError:
        lines.append("\ntorch: 未安装（不影响云 Provider 使用）")

    # Provider 配置
    lines.append("\n已注册 Provider:")
    for p in load_providers():
        key_state = ""
        if p.api_key_env:
            v = os.environ.get(p.api_key_env, "")
            key_state = "(key 已设置)" if v else "(key 未设置)"
        lines.append(
            f"  {'✓' if p.enabled else '✗'} {p.id:<12} {p.display_name}  {key_state}"
        )

    # 缓存目录
    from lib.config import RUNTIME_ROOT, MODELS_CACHE, REMBG_CACHE, OUTPUT_ROOT as OR
    lines.append(f"\n运行时目录:")
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

    def _do_warmup():
        rembg_warmup(model, progress_cb=None)
        return True

    task = TimedTask(target=_do_warmup, timeout_s=TIMEOUT_WARMUP)
    try:
        task.run_sync_with_progress(log, f"预热 rembg ({model})", progress)
    except Exception as e:
        return f"✗ 失败：{_short_tb(e)}", LOG_DEBUG.render()
    return f"✓ rembg 模型 {model} 已就绪", LOG_DEBUG.render()


def debug_test_generate_one(provider_id: str, progress=gr.Progress()):
    """在调试页快速生成 1 张测试图。"""
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
                n=1,
                size="512x512",
                seed=42,
                negative_prompt=None,
                output_dir=tmp_dir,
                progress_cb=None,
            )
        except TypeError:
            return prov.generate(
                prompt="a simple test pattern, geometric shape, clean background",
                n=1,
                size="512x512",
                seed=42,
                negative_prompt=None,
                output_dir=tmp_dir,
            )

    task = TimedTask(target=_do, timeout_s=TIMEOUT_GENERATE)
    try:
        paths = task.run_sync_with_progress(log, "单步生成测试", progress)
    except Exception as e:
        return None, f"✗ 失败：{_short_tb(e)}", LOG_DEBUG.render()

    if not paths:
        return None, "✗ Provider 返回 0 张图", LOG_DEBUG.render()
    return Image.open(paths[0]), f"✓ 收到 1 张（{paths[0].name}）", LOG_DEBUG.render()


def debug_test_matting(img: Image.Image, model: str, progress=gr.Progress()):
    log = LOG_DEBUG
    if img is None:
        return None, "请先上传或加载一张图", LOG_DEBUG.render()
    log.info(f"调试: 单步抠图测试 model={model} size={img.size}")

    def _do():
        return remove_background(img, model=model, progress_cb=None)

    task = TimedTask(target=_do, timeout_s=TIMEOUT_MATTING)
    try:
        out = task.run_sync_with_progress(log, f"单步抠图 ({model})", progress)
    except Exception as e:
        return None, f"✗ 失败：{_short_tb(e)}", LOG_DEBUG.render()
    return out, "✓ 抠图完成", LOG_DEBUG.render()


def debug_clear_log():
    LOG_DEBUG.clear()
    return ""


def prod_clear_log():
    LOG_PROD.clear()
    return ""


def refresh_log_prod():
    return LOG_PROD.render()


def refresh_log_debug():
    return LOG_DEBUG.render()


# ════════════════════════════════════════════════════════════
# 6. UI 布局
# ════════════════════════════════════════════════════════════

CSS = """
.fxgen-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; padding: 16px 22px; border-radius: 10px; margin-bottom: 14px;
}
.fxgen-header h1 { color: white; margin: 0; font-size: 22px; }
.fxgen-header p  { color: #e0e0ff; margin: 6px 0 0; font-size: 13px; }
.fxgen-step-title {
    background: #f6f8fa; border-left: 4px solid #667eea;
    padding: 10px 14px; margin: 8px 0; border-radius: 4px;
    font-weight: 600; display: flex; justify-content: space-between; align-items: center;
}
.fxgen-log textarea {
    background: #1e1e1e !important; color: #d4d4d4 !important;
    font-family: 'SF Mono', Menlo, Consolas, monospace !important;
    font-size: 12px !important; line-height: 1.45 !important;
}
.gallery { min-height: 340px; }
"""


def _badge_html(text: str) -> str:
    return f'<div style="text-align:right;font-size:13px;color:#666;">{text}</div>'


def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title="fx-generator v0.1.2",
        css=CSS,
        theme=gr.themes.Soft(),
    ) as demo:
        # ── 顶部 banner ─────────────────────────────────────
        gr.HTML(
            """
            <div class="fxgen-header">
              <h1>fx-generator · 抖音面部特效素材生成器</h1>
              <p>分 4 步：选模型+Prompt → 选图 → 抠图+规范化 → 导出 zip · 拖进 Douyin AR 上架</p>
            </div>
            """
        )

        # ─────────────────────────────────────────────────
        # 顶层 Tabs：「生产」/「调试工具」
        # ─────────────────────────────────────────────────
        with gr.Tabs() as top_tabs:
            # =============================================================
            # 生产 Tab
            # =============================================================
            with gr.Tab("素材生产"):
                # 状态
                state_dir = gr.State("")
                state_prompt = gr.State("")
                state_negative = gr.State("")
                state_seed = gr.State("")

                # ── 子 Tabs：4 步 ───────────────────────────
                with gr.Tabs() as step_tabs:
                    # ---- Step 1 ----
                    with gr.Tab("Step 1 · 选模型 + Prompt"):
                        with gr.Row():
                            gr.HTML('<div class="fxgen-step-title"><span>Step 1 — 选 Provider 与 Prompt</span></div>')
                            step1_badge = gr.HTML(_badge_html(BADGE_PENDING))

                        provider_dd = gr.Dropdown(
                            label="生成 Provider",
                            choices=_provider_choices(),
                            value=(_provider_choices()[0][1] if _provider_choices() else None),
                            info="云 API 速度依赖网络；本机 SDXL Turbo 需先下权重",
                        )
                        prompt = gr.Textbox(
                            label="Prompt",
                            lines=3,
                            placeholder="例如：cyberpunk metal mask, glowing cyan circuits, frontal symmetric, on transparent background",
                        )
                        negative_prompt = gr.Textbox(
                            label="Negative Prompt",
                            lines=2,
                            value="lowres, blurry, watermark, text, logo, realistic human face, photo of celebrity, child, violence",
                        )
                        with gr.Row():
                            seed = gr.Textbox(label="Seed（留空=随机）", value="", scale=2)
                            n_candidates = gr.Dropdown(
                                label="候选数", choices=["1", "2", "4", "6"], value="4", scale=1
                            )
                            size = gr.Dropdown(
                                label="尺寸",
                                choices=["512x512", "768x768", "1024x1024"],
                                value="1024x1024", scale=1,
                            )

                        generate_btn = gr.Button("✨ 生成候选图", variant="primary", size="lg")

                    # ---- Step 2 ----
                    with gr.Tab("Step 2 · 选图"):
                        with gr.Row():
                            gr.HTML('<div class="fxgen-step-title"><span>Step 2 — 在候选中点选一张</span></div>')
                            step2_badge = gr.HTML(_badge_html(BADGE_PENDING))

                        gallery = gr.Gallery(
                            label="候选图（点选一张）",
                            columns=4, object_fit="contain",
                            height=340, show_label=False,
                            elem_classes=["gallery"],
                        )
                        selected_img = gr.Image(label="已选中", type="pil", height=320)

                    # ---- Step 3 ----
                    with gr.Tab("Step 3 · 抠图 + 规范化"):
                        with gr.Row():
                            gr.HTML('<div class="fxgen-step-title"><span>Step 3 — 抠透明背景 + 规范化为 EC 资产</span></div>')
                            step3_badge = gr.HTML(_badge_html(BADGE_PENDING))

                        with gr.Row():
                            input_preview = gr.Image(label="选中图（来自 Step 2）", type="pil", height=300)
                            processed_img = gr.Image(label="处理后预览", type="pil", height=300)

                        matting_model = gr.Dropdown(
                            label="抠图模型",
                            choices=MATTING_MODELS,
                            value=DEFAULT_MATTING,
                            info="u2net_human_seg 速度+人像精度最佳；isnet-general-use 通用更准",
                        )
                        with gr.Row():
                            remove_bg_btn = gr.Button("✂️ 抠透明背景", variant="primary")
                            normalize_btn = gr.Button("📐 规范化 1024×1024")

                    # ---- Step 4 ----
                    with gr.Tab("Step 4 · 合规自检 + 导出"):
                        with gr.Row():
                            gr.HTML('<div class="fxgen-step-title"><span>Step 4 — 合规自检 + 导出素材包</span></div>')
                            step4_badge = gr.HTML(_badge_html(BADGE_PENDING))

                        gr.Markdown("**合规自检（全部勾选才能导出）**")
                        checkboxes = []
                        for item in COMPLIANCE_ITEMS:
                            cb = gr.Checkbox(label=item, value=False)
                            checkboxes.append(cb)

                        with gr.Row():
                            project_name = gr.Textbox(
                                label="项目名（用于目录与 zip 命名）",
                                placeholder="my-cyberpunk-mask",
                                scale=2,
                            )
                            export_btn = gr.Button("📦 导出素材包", variant="primary", scale=1)

                        export_status = gr.Textbox(label="导出状态", interactive=False)
                        download_file = gr.File(label="下载素材包")

                # 生产页底部：日志（默认折叠）
                with gr.Accordion("📋 实时日志（生产）", open=False):
                    log_prod_box = gr.Textbox(
                        value="",
                        lines=10, max_lines=20,
                        interactive=False,
                        elem_classes=["fxgen-log"],
                        show_label=False,
                    )
                    with gr.Row():
                        refresh_prod_btn = gr.Button("🔄 刷新", size="sm")
                        clear_prod_btn = gr.Button("🧹 清空", size="sm")

            # =============================================================
            # 调试 Tab
            # =============================================================
            with gr.Tab("调试工具"):
                gr.Markdown(
                    "**调试页**：环境检查 / 模型加载 / 单步测试 / 完整日志。"
                    " 用于排查问题、验证修改后再切回生产页。"
                )

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 1. 环境检测")
                        env_btn = gr.Button("📊 跑一次环境检测")
                        env_output = gr.Textbox(
                            label="环境信息",
                            lines=18, max_lines=30,
                            interactive=False,
                        )

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
                        gr.Markdown("### 3. 单步生成测试（512×512, 1 张, seed=42）")
                        debug_provider_dd = gr.Dropdown(
                            label="Provider",
                            choices=_provider_choices(),
                            value=(_provider_choices()[0][1] if _provider_choices() else None),
                        )
                        debug_gen_btn = gr.Button("⚡ 跑单步生成")
                        debug_gen_status = gr.Textbox(label="状态", interactive=False)
                        debug_gen_img = gr.Image(label="测试图", type="pil", height=240)

                        gr.Markdown("### 4. 单步抠图测试")
                        debug_matt_input = gr.Image(label="输入图（拖入或上一步生成）", type="pil", height=200)
                        with gr.Row():
                            debug_matt_model = gr.Dropdown(
                                label="模型",
                                choices=MATTING_MODELS,
                                value=DEFAULT_MATTING,
                            )
                            debug_matt_btn = gr.Button("✂️ 跑单步抠图")
                        debug_matt_status = gr.Textbox(label="状态", interactive=False)
                        debug_matt_out = gr.Image(label="抠图结果", type="pil", height=200)

                gr.Markdown("### 5. 完整日志（调试模式始终展开）")
                log_debug_box = gr.Textbox(
                    value="",
                    lines=20, max_lines=40,
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

        # ── Step 1：生成 ─────────────────────────────────
        generate_btn.click(
            fn=lambda *a: (
                _badge_html(BADGE_RUNNING),  # step1 in-progress
            ),
            inputs=None,
            outputs=[step1_badge],
            queue=False,
        ).then(
            fn=handle_generate,
            inputs=[provider_dd, prompt, negative_prompt, seed, n_candidates, size],
            outputs=[
                gallery,
                log_prod_box,
                state_dir, state_prompt, state_negative, state_seed,
                step1_badge, step2_badge,
            ],
        )

        # ── Step 2：选图（Gallery 点选）────────────────
        gallery.select(
            fn=handle_select_candidate,
            inputs=[state_dir],
            outputs=[selected_img, log_prod_box, step2_badge, step3_badge],
        ).then(
            fn=lambda img: img,
            inputs=[selected_img],
            outputs=[input_preview],
        )

        # ── Step 3：抠图 ─────────────────────────────────
        remove_bg_btn.click(
            fn=lambda: _badge_html(BADGE_RUNNING),
            inputs=None, outputs=[step3_badge], queue=False,
        ).then(
            fn=handle_remove_bg,
            inputs=[input_preview, matting_model],
            outputs=[processed_img, log_prod_box, step3_badge],
        )

        # ── Step 3：规范化 ──────────────────────────────
        normalize_btn.click(
            fn=handle_normalize,
            inputs=[processed_img],
            outputs=[processed_img, log_prod_box, step3_badge, step4_badge],
        )

        # ── Step 4：导出 ─────────────────────────────────
        export_btn.click(
            fn=lambda: _badge_html(BADGE_RUNNING),
            inputs=None, outputs=[step4_badge], queue=False,
        ).then(
            fn=handle_export,
            inputs=[
                processed_img, project_name, provider_dd,
                state_prompt, state_negative, state_seed,
                *checkboxes,
            ],
            outputs=[download_file, export_status, log_prod_box, step4_badge],
        )

        # ── 生产日志按钮 ────────────────────────────────
        refresh_prod_btn.click(fn=refresh_log_prod, inputs=None, outputs=[log_prod_box], queue=False)
        clear_prod_btn.click(fn=prod_clear_log, inputs=None, outputs=[log_prod_box], queue=False)

        # ── 调试 Tab ────────────────────────────────────
        env_btn.click(fn=debug_check_env, inputs=None, outputs=[env_output, log_debug_box])
        warmup_btn.click(fn=debug_warmup_rembg, inputs=[debug_matting_model],
                          outputs=[warmup_status, log_debug_box])
        debug_gen_btn.click(fn=debug_test_generate_one, inputs=[debug_provider_dd],
                             outputs=[debug_gen_img, debug_gen_status, log_debug_box])
        debug_matt_btn.click(fn=debug_test_matting,
                              inputs=[debug_matt_input, debug_matt_model],
                              outputs=[debug_matt_out, debug_matt_status, log_debug_box])
        refresh_debug_btn.click(fn=refresh_log_debug, inputs=None, outputs=[log_debug_box], queue=False)
        clear_debug_btn.click(fn=debug_clear_log, inputs=None, outputs=[log_debug_box], queue=False)

    return demo


# ════════════════════════════════════════════════════════════
# 7. 启动入口（不可改签名）
# ════════════════════════════════════════════════════════════

def launch():
    """对外暴露的启动入口（pyproject.toml fxgen 命令、start.bat / start.sh 都依赖）。"""
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    LOG_PROD.info("fx-generator 启动")
    LOG_DEBUG.info("fx-generator 启动（调试日志通道就绪）")
    demo = build_ui()
    demo.queue()  # 启用 Gradio 队列，gr.Progress 才能正常工作
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True,
        inbrowser=True,
    )


if __name__ == "__main__":
    launch()
