"""Gradio Web UI - 抖音面部特效素材生成工具（Agnes AI）。"""

import os
import tempfile
from datetime import date
from pathlib import Path

import gradio as gr
from PIL import Image

from lib.api_client import generate_images, DEFAULT_MODEL
from lib.matting import remove_background
from lib.normalize import normalize_for_ec, safe_filename
from lib.packager import pack_project, PackMeta, AssetItem, GenerationInfo
from lib.safety import COMPLIANCE_ITEMS

OUTPUT_ROOT = Path("output")


def on_generate(prompt, negative_prompt, seed, n_candidates, size):
    """生成候选图。"""
    if not prompt.strip():
        raise gr.Error("请输入 prompt")

    tmp_dir = Path(tempfile.mkdtemp(prefix="douyinfx_"))
    seed_val = int(seed) if seed and seed.strip() else None

    try:
        paths = generate_images(
            prompt=prompt,
            n=int(n_candidates),
            size=size,
            seed=seed_val,
            negative_prompt=negative_prompt.strip() or None,
            output_dir=tmp_dir,
        )
    except Exception as e:
        raise gr.Error(f"API 调用失败: {e}")

    images = [Image.open(p) for p in paths]
    return images, str(tmp_dir), prompt, negative_prompt, str(seed_val or "")


def on_select_candidate(evt: gr.SelectData, state_dir: str):
    """选中某张候选图。"""
    if not state_dir:
        raise gr.Error("请先生成候选图")
    idx = evt.index
    src_dir = Path(state_dir)
    candidates = sorted(src_dir.glob("candidate_*.png"))
    if idx < 0 or idx >= len(candidates):
        raise gr.Error("无效选择")
    return Image.open(candidates[idx])


def on_remove_bg(img):
    if img is None:
        raise gr.Error("请先选择一张候选图")
    return remove_background(img)


def on_normalize(img):
    if img is None:
        raise gr.Error("请先抠背景")
    return normalize_for_ec(img, (1024, 1024))


def on_export(img, project_name, prompt, negative_prompt, seed, *checklist_states):
    """合规自检 + 导出素材包。"""
    if img is None:
        raise gr.Error("请先生成并处理图片")
    if not project_name.strip():
        raise gr.Error("请输入项目名")
    if not all(checklist_states):
        raise gr.Error("请完成全部 7 项合规自检")

    project_safe = safe_filename(project_name)
    out_dir = OUTPUT_ROOT / f"{date.today().isoformat()}-{project_safe}"
    (out_dir / "processed").mkdir(parents=True, exist_ok=True)

    final_name = safe_filename(f"{project_safe}_face_paint_main") + ".png"
    final_path = out_dir / "processed" / final_name
    img.save(final_path, "PNG")

    meta = PackMeta(
        project_name=project_safe,
        scenario="S1",
        items=[
            AssetItem(
                filename=final_name,
                kind="face_texture",
                size=(1024, 1024),
                generation=GenerationInfo(
                    backend="agnes-image-api",
                    model_id=DEFAULT_MODEL,
                    prompt=prompt,
                    negative_prompt=negative_prompt or "",
                    seed=int(seed) if seed and seed.strip() else -1,
                ),
                postprocess=["rembg", "resize_1024x1024", "rgba"],
            )
        ],
    )

    zip_path = pack_project(out_dir, meta)
    return str(zip_path), f"素材包已生成: {zip_path}"


CSS = """
.gallery {min-height: 300px}
"""

with gr.Blocks(title="douyin-fx 素材生成器") as demo:
    gr.Markdown(
        """
        # 🎭 douyin-fx 素材生成器
        
        输入创意主题 → Agnes AI 生成 → 抠背景 → 打包 → 拖进 Effect Creator 上架
        
        > 当前已自动读取 CodeBuddy 中的 Agnes API 配置，可直接使用。
        > 更多模型支持（DALL-E / Stability / Gemini）见 `v0.2 待办`。
        """
    )

    with gr.Row():
        with gr.Column(scale=1):

            prompt = gr.Textbox(
                label="🎨 Prompt",
                lines=3,
                placeholder="例如：cyberpunk metal mask, glowing cyan circuits...",
            )
            negative_prompt = gr.Textbox(
                label="✖️ Negative Prompt（Agnes 支持）",
                lines=2,
                value="lowres, blurry, watermark, text, logo, realistic human face, child, violence",
            )
            with gr.Row():
                seed = gr.Textbox(label="Seed（留空随机, Agnes 支持）", value="", scale=2)
                n_candidates = gr.Dropdown(
                    label="候选数", choices=["2", "4", "6", "8"], value="4", scale=1
                )
                size = gr.Dropdown(
                    label="尺寸",
                    choices=["512x512", "768x768", "1024x1024"],
                    value="1024x1024",
                    scale=1,
                )

            generate_btn = gr.Button("✨ 生成候选图", variant="primary", size="lg")

            state_dir = gr.Textbox(visible=False, value="")
            state_prompt = gr.Textbox(visible=False, value="")
            state_negative = gr.Textbox(visible=False, value="")
            state_seed = gr.Textbox(visible=False, value="")

        with gr.Column(scale=2):

            gr.Markdown("### 🖼️ 候选图（点击选中一张）")
            gallery = gr.Gallery(label="候选", columns=4, object_fit="contain", height=300, show_label=False)

            with gr.Row():
                selected_img = gr.Image(label="已选中的图", type="pil", height=280, scale=1)
                processed_img = gr.Image(label="处理后预览", type="pil", height=280, scale=1)

            with gr.Row():
                remove_bg_btn = gr.Button("✂️ 抠透明背景")
                normalize_btn = gr.Button("📐 规范化 1024×1024")

            gr.Markdown("---")
            gr.Markdown("### 📦 导出素材包")
            with gr.Row():
                project_name = gr.Textbox(label="项目名", placeholder="my-mask-v1", scale=2)
                export_btn = gr.Button("📦 导出素材包 zip", variant="primary", scale=1)

            gr.Markdown("#### ✅ 合规自检清单（全部勾选才能导出）")
            checkboxes = []
            with gr.Column():
                for item in COMPLIANCE_ITEMS:
                    cb = gr.Checkbox(label=item, value=False)
                    checkboxes.append(cb)

            export_status = gr.Textbox(label="导出状态", interactive=False)
            download_file = gr.File(label="下载素材包")

    # ── 事件绑定 ──
    generate_btn.click(
        fn=on_generate,
        inputs=[prompt, negative_prompt, seed, n_candidates, size],
        outputs=[gallery, state_dir, state_prompt, state_negative, state_seed],
    )

    gallery.select(
        fn=on_select_candidate,
        inputs=[state_dir],
        outputs=[selected_img],
    )

    remove_bg_btn.click(
        fn=on_remove_bg, inputs=[selected_img], outputs=[processed_img],
    )

    normalize_btn.click(
        fn=on_normalize, inputs=[processed_img], outputs=[processed_img],
    )

    export_btn.click(
        fn=on_export,
        inputs=[processed_img, project_name, state_prompt, state_negative, state_seed, *checkboxes],
        outputs=[download_file, export_status],
    )


def launch():
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    demo.launch(server_name="127.0.0.1", server_port=7860, show_error=True, css=CSS, theme=gr.themes.Soft())


if __name__ == "__main__":
    launch()
