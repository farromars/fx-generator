"""fx-generator Web UI（v0.1.1）

布局原则（方向 A：Gradio 内重排）：
- 顶部：标题 + 当前进度条（5 步流程可视）
- 左列：Provider/Prompt 设置 + 实时日志
- 右列：候选图选择 + 处理预览 + 合规自检 + 导出

性能优化：
- rembg 启动时预热（避免首次抠图卡 3 分钟）
- 生成过程通过 yield 流式更新 UI
- Provider 切换不重启，可在 UI 内切

不依赖：
- Tauri / Rust / TS（保持 1 人维护友好）
"""

from __future__ import annotations

import os
import tempfile
import threading
import traceback
from datetime import date, datetime
from pathlib import Path

import gradio as gr
from PIL import Image

from lib.config import OUTPUT_ROOT, load_providers, ProviderEntry
from lib.matting import remove_background, warmup as rembg_warmup, SUPPORTED_MODELS as MATTING_MODELS, DEFAULT_MODEL as DEFAULT_MATTING
from lib.normalize import normalize_for_ec, safe_filename
from lib.packager import pack_project, PackMeta, AssetItem, GenerationInfo
from lib.providers import get_provider, ProviderConfig
from lib.safety import COMPLIANCE_ITEMS

# ────────────────────────────────────────────────────────────
# Provider 实例缓存（避免反复 init）
# ────────────────────────────────────────────────────────────
_provider_cache: dict[str, object] = {}


def _build_provider_config(entry: ProviderEntry) -> ProviderConfig:
    api_key = os.environ.get(entry.api_key_env, "") if entry.api_key_env else ""
    return ProviderConfig(
        endpoint=entry.endpoint,
        api_key=api_key,
        model=entry.default_model,
    )


def _get_provider_instance(entry: ProviderEntry):
    if entry.id not in _provider_cache:
        cfg = _build_provider_config(entry)
        prov = get_provider(entry.id, config=cfg)
        # local_sdxl 支持 extra（device/dtype）
        if entry.id == "local_sdxl" and entry.extra:
            for k, v in entry.extra.items():
                setattr(prov, k, v)
            # 重新探测 device 兼容用户配置
            if entry.extra.get("device") not in (None, "auto"):
                prov.device = entry.extra["device"]
        _provider_cache[entry.id] = prov
    return _provider_cache[entry.id]


# ────────────────────────────────────────────────────────────
# 后台事件
# ────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _append_log(log: str, line: str) -> str:
    return (log or "") + f"[{_now()}] {line}\n"


def on_warmup(matting_model: str, log_text: str, progress=gr.Progress()):
    """启动后立即预热 rembg（一次性约 170MB 下载）。"""
    try:
        progress(0.1, "准备 rembg 模型...")
        log_text = _append_log(log_text, f"开始预热 rembg ({matting_model})")
        yield log_text, gr.update()
        rembg_warmup(matting_model, progress_cb=lambda m: None)
        progress(1.0, "rembg 就绪")
        log_text = _append_log(log_text, f"rembg ({matting_model}) 已就绪")
        yield log_text, gr.update(value="✓ rembg 已就绪")
    except Exception as e:
        log_text = _append_log(log_text, f"rembg 预热失败: {e}")
        yield log_text, gr.update(value="✗ rembg 预热失败，首次抠图会自动下载")


def on_generate(
    provider_id: str,
    prompt: str,
    negative_prompt: str,
    seed_text: str,
    n_candidates: str,
    size: str,
    log_text: str,
    progress=gr.Progress(),
):
    """生成候选图（流式更新 UI）。"""
    if not prompt.strip():
        raise gr.Error("请输入 prompt")

    providers = load_providers()
    entry = next((p for p in providers if p.id == provider_id), None)
    if entry is None:
        raise gr.Error(f"未知 Provider: {provider_id}")

    if entry.api_key_env and not os.environ.get(entry.api_key_env):
        raise gr.Error(
            f"环境变量 {entry.api_key_env} 未设置。\n"
            f"请在终端 export {entry.api_key_env}=... 后重启。"
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="fxgen_"))
    seed_val = int(seed_text) if seed_text and seed_text.strip().lstrip("-").isdigit() else None
    n = int(n_candidates)

    log_text = _append_log(log_text, f"开始生成 ({provider_id}, n={n}, size={size})")
    progress(0.05, f"调用 {entry.display_name}...")
    yield [], log_text, str(tmp_dir), prompt, negative_prompt, str(seed_val or "")

    try:
        prov = _get_provider_instance(entry)

        def _progress_cb(step, total, msg):
            try:
                progress(0.1 + 0.85 * (step / max(total, 1)), msg)
            except Exception:
                pass

        # 不是所有 provider 都接受 progress_cb，做兼容
        try:
            paths = prov.generate(
                prompt=prompt,
                n=n,
                size=size,
                seed=seed_val,
                negative_prompt=negative_prompt.strip() or None,
                output_dir=tmp_dir,
                progress_cb=_progress_cb,
            )
        except TypeError:
            paths = prov.generate(
                prompt=prompt,
                n=n,
                size=size,
                seed=seed_val,
                negative_prompt=negative_prompt.strip() or None,
                output_dir=tmp_dir,
            )
    except Exception as e:
        log_text = _append_log(log_text, f"生成失败: {e}")
        log_text = _append_log(log_text, traceback.format_exc(limit=2))
        yield [], log_text, "", prompt, negative_prompt, str(seed_val or "")
        raise gr.Error(f"生成失败：{e}")

    log_text = _append_log(log_text, f"收到 {len(paths)} 张候选图")
    progress(1.0, "完成")
    images = [Image.open(p) for p in paths]
    yield images, log_text, str(tmp_dir), prompt, negative_prompt, str(seed_val or "")


def on_select_candidate(evt: gr.SelectData, state_dir: str, log_text: str):
    if not state_dir:
        raise gr.Error("请先生成候选图")
    src_dir = Path(state_dir)
    candidates = sorted(src_dir.glob("candidate_*.png"))
    idx = evt.index
    if idx < 0 or idx >= len(candidates):
        raise gr.Error("无效选择")
    log_text = _append_log(log_text, f"已选中候选 {idx + 1}: {candidates[idx].name}")
    return Image.open(candidates[idx]), log_text


def on_remove_bg(img, matting_model: str, log_text: str, progress=gr.Progress()):
    if img is None:
        raise gr.Error("请先选择一张候选图")
    progress(0.1, f"抠图 ({matting_model})...")
    log_text = _append_log(log_text, f"开始抠图 ({matting_model})")
    try:
        out = remove_background(img, model=matting_model, progress_cb=lambda m: None)
        progress(1.0, "完成")
        log_text = _append_log(log_text, "抠图完成")
        return out, log_text
    except Exception as e:
        log_text = _append_log(log_text, f"抠图失败: {e}")
        raise gr.Error(f"抠图失败：{e}")


def on_normalize(img, log_text: str):
    if img is None:
        raise gr.Error("请先抠背景或选图")
    out = normalize_for_ec(img, (1024, 1024))
    log_text = _append_log(log_text, "已规范化为 1024×1024 RGBA")
    return out, log_text


def on_export(
    img,
    project_name,
    provider_id,
    prompt,
    negative_prompt,
    seed,
    log_text,
    *checklist_states,
):
    if img is None:
        raise gr.Error("请先生成并处理图片")
    if not project_name.strip():
        raise gr.Error("请输入项目名")
    if not all(checklist_states):
        raise gr.Error(f"请完成全部 {len(COMPLIANCE_ITEMS)} 项合规自检")

    project_safe = safe_filename(project_name)
    out_dir = OUTPUT_ROOT / f"{date.today().isoformat()}-{project_safe}"
    (out_dir / "processed").mkdir(parents=True, exist_ok=True)

    final_name = safe_filename(f"{project_safe}_face_paint_main") + ".png"
    final_path = out_dir / "processed" / final_name
    img.save(final_path, "PNG")

    providers = load_providers()
    entry = next((p for p in providers if p.id == provider_id), None)
    backend_str = f"{provider_id}" + (f" / {entry.default_model}" if entry and entry.default_model else "")

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

    zip_path = pack_project(out_dir, meta)
    log_text = _append_log(log_text, f"导出完成: {zip_path}")
    return str(zip_path), f"✓ 素材包已生成: {zip_path}", log_text


# ────────────────────────────────────────────────────────────
# UI 布局
# ────────────────────────────────────────────────────────────

CSS = """
.fxgen-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 18px 24px;
    border-radius: 12px;
    margin-bottom: 16px;
}
.fxgen-header h1 { color: white; margin: 0; font-size: 22px; }
.fxgen-header p  { color: #e0e0ff; margin: 6px 0 0; font-size: 13px; }
.fxgen-step {
    background: #f6f8fa;
    border-left: 4px solid #667eea;
    padding: 10px 14px;
    margin: 8px 0;
    border-radius: 4px;
    font-weight: 600;
}
.fxgen-log {
    background: #1e1e1e !important;
    color: #d4d4d4 !important;
    font-family: 'SF Mono', Menlo, Consolas, monospace !important;
    font-size: 12px !important;
}
.gallery {min-height: 320px}
"""


def _provider_choices() -> list[tuple[str, str]]:
    return [(p.display_name, p.id) for p in load_providers() if p.enabled]


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="fx-generator v0.1.1", css=CSS, theme=gr.themes.Soft()) as demo:
        # ─── 顶部 ────────────────────────────────────────────
        gr.HTML(
            """
            <div class="fxgen-header">
              <h1>fx-generator · 抖音面部特效素材生成器</h1>
              <p>1. 选 Provider 出图 →&nbsp; 2. 选一张 →&nbsp; 3. 抠背景 →&nbsp; 4. 规范化 →&nbsp; 5. 导出素材包 → 拖进 Douyin AR 上架</p>
            </div>
            """
        )

        # ─── 状态 ────────────────────────────────────────────
        state_dir = gr.State("")
        state_prompt = gr.State("")
        state_negative = gr.State("")
        state_seed = gr.State("")

        log_text = gr.Textbox(
            label="实时日志",
            value="",
            lines=6,
            max_lines=14,
            interactive=False,
            elem_classes=["fxgen-log"],
        )

        with gr.Row():
            # ─── 左列：参数 ─────────────────────────────────
            with gr.Column(scale=2):
                gr.HTML('<div class="fxgen-step">Step 1 — 选 Provider + 写 Prompt</div>')

                provider_dd = gr.Dropdown(
                    label="生成 Provider",
                    choices=_provider_choices(),
                    value=(_provider_choices()[0][1] if _provider_choices() else None),
                    info="云 API 速度依赖网络；本机 SDXL Turbo 需要先下载权重",
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
                        label="候选数",
                        choices=["1", "2", "4", "6"],
                        value="4",
                        scale=1,
                    )
                    size = gr.Dropdown(
                        label="尺寸",
                        choices=["512x512", "768x768", "1024x1024"],
                        value="1024x1024",
                        scale=1,
                    )

                generate_btn = gr.Button("✨ 生成候选图", variant="primary", size="lg")

                gr.HTML('<div class="fxgen-step">Step 3 — 抠图与规范化</div>')
                matting_model = gr.Dropdown(
                    label="抠图模型",
                    choices=MATTING_MODELS,
                    value=DEFAULT_MATTING,
                    info="u2net_human_seg 速度+人像精度最佳；isnet-general-use 通用更准",
                )
                with gr.Row():
                    remove_bg_btn = gr.Button("✂️ 抠透明背景")
                    normalize_btn = gr.Button("📐 规范化 1024×1024")

                rembg_status = gr.Textbox(
                    label="rembg 状态",
                    value="(尚未预热，首次抠图会自动下载约 170MB)",
                    interactive=False,
                )
                warmup_btn = gr.Button("🔥 预热 rembg（建议启动后点一次）", size="sm")

            # ─── 右列：候选 + 处理 + 导出 ─────────────────
            with gr.Column(scale=3):
                gr.HTML('<div class="fxgen-step">Step 2 — 选一张候选图</div>')
                gallery = gr.Gallery(
                    label="候选",
                    columns=4,
                    object_fit="contain",
                    height=320,
                    show_label=False,
                )

                with gr.Row():
                    selected_img = gr.Image(label="已选中", type="pil", height=300, scale=1)
                    processed_img = gr.Image(label="处理预览", type="pil", height=300, scale=1)

                gr.HTML('<div class="fxgen-step">Step 4 — 合规自检 + Step 5 — 导出</div>')

                with gr.Row():
                    project_name = gr.Textbox(
                        label="项目名（用于目录与 zip 命名）",
                        placeholder="my-cyberpunk-mask",
                        scale=2,
                    )
                    export_btn = gr.Button("📦 导出素材包", variant="primary", scale=1)

                gr.Markdown("**合规自检（全部勾选才能导出）**")
                checkboxes = []
                for item in COMPLIANCE_ITEMS:
                    cb = gr.Checkbox(label=item, value=False)
                    checkboxes.append(cb)

                export_status = gr.Textbox(label="导出状态", interactive=False)
                download_file = gr.File(label="下载素材包")

        # ─── 事件绑定 ───────────────────────────────────────
        warmup_btn.click(
            fn=on_warmup,
            inputs=[matting_model, log_text],
            outputs=[log_text, rembg_status],
        )

        generate_btn.click(
            fn=on_generate,
            inputs=[provider_dd, prompt, negative_prompt, seed, n_candidates, size, log_text],
            outputs=[gallery, log_text, state_dir, state_prompt, state_negative, state_seed],
        )

        gallery.select(
            fn=on_select_candidate,
            inputs=[state_dir, log_text],
            outputs=[selected_img, log_text],
        )

        remove_bg_btn.click(
            fn=on_remove_bg,
            inputs=[selected_img, matting_model, log_text],
            outputs=[processed_img, log_text],
        )

        normalize_btn.click(
            fn=on_normalize,
            inputs=[processed_img, log_text],
            outputs=[processed_img, log_text],
        )

        export_btn.click(
            fn=on_export,
            inputs=[
                processed_img, project_name, provider_dd,
                state_prompt, state_negative, state_seed,
                log_text,
                *checkboxes,
            ],
            outputs=[download_file, export_status, log_text],
        )

    return demo


def launch():
    """对外暴露的启动入口（pyproject.toml 里 fxgen 命令指向这里）。"""
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    demo = build_ui()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True,
        inbrowser=True,
    )


if __name__ == "__main__":
    launch()
