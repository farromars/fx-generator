"""S1：抖音面部贴图素材流水线（v0.1 必做）。

用法：
  python -m workflows.s1_face_paint \\
    --prompt "cyberpunk metal mask" \\
    --project cyberpunk-mask-v1 \\
    --n 4

或者在 IDE chat 里说："用 S1 流水线做一个赛博朋克金属面具的特效"
"""

import click
from datetime import date
from pathlib import Path

from lib.skill_bridge import request_images
from lib.matting import remove_background
from lib.normalize import normalize_for_ec, safe_filename
from lib.packager import pack_project, PackMeta, AssetItem, GenerationInfo
from lib.safety import interactive_confirm
from workflows._common import select_candidate, create_output_dirs
from PIL import Image


PROMPT_TEMPLATE = (
    "{{THEME}}, frontal symmetric, on transparent background, "
    "aligned to face uv template, "
    "high detail, 8k, no shadow, no background, "
    "clean edges, suitable for face paint texture"
)

NEGATIVE_PROMPT = (
    "lowres, blurry, asymmetric, watermark, text, logo, "
    "realistic human face, photo of celebrity, photo of public figure, child, "
    "violence, blood, gore, sexual content"
)


@click.command()
@click.option("--prompt", required=True, help="主题描述，例如 'cyberpunk metal mask'")
@click.option("--project", required=True, help="项目名，用作输出目录与 zip 命名")
@click.option("--n", default=4, help="出几张候选")
@click.option("--seed", default=None, type=int)
@click.option("--output-root", default="output", type=click.Path())
def main(prompt: str, project: str, n: int, seed: int | None, output_root: str):
    """S1 面部贴图素材流水线。"""
    project_safe = safe_filename(project)
    out_dir = Path(output_root) / f"{date.today().isoformat()}-{project_safe}"
    create_output_dirs(out_dir)

    # 1. 拼 prompt
    final_prompt = PROMPT_TEMPLATE.replace("{{THEME}}", prompt)
    print(f"[1/6] Prompt: {final_prompt[:120]}...")

    # 2. 调 skill 出 N 张候选
    print(f"[2/6] 请求 {n} 张候选图...")
    candidates = request_images(
        kind="text2img",
        prompt=final_prompt,
        n=n,
        size=(1024, 1024),
        seed=seed,
        output_dir=out_dir / "candidates",
    )
    print(f"      收到 {len(candidates)} 张候选图")

    # 3. 选图
    print("[3/6] 选择候选图...")
    if len(candidates) == 1:
        selected = candidates[0]
        print(f"      自动选择唯一候选图: {selected.name}")
    else:
        selected = select_candidate(candidates)
    selected_dst = out_dir / "selected" / selected.name
    selected_dst.write_bytes(selected.read_bytes())
    print(f"      已选择: {selected_dst}")

    # 4. 抠背景
    print("[4/6] 抠透明背景...")
    try:
        matted = remove_background(Image.open(selected_dst))
        print("      抠图完成")
    except RuntimeError as e:
        print(f"      抠图失败: {e}")
        print("      退化：使用原图作为最终素材")
        matted = Image.open(selected_dst).convert("RGBA")

    # 5. 规范化
    print("[5/6] 规范化为 EC 资产格式...")
    normalized = normalize_for_ec(matted, (1024, 1024))
    final_name = safe_filename(f"{project}_face_paint_main") + ".png"
    final_path = out_dir / "processed" / final_name
    normalized.save(final_path, "PNG")
    print(f"      已保存: {final_path}")

    # 6. 合规自检 → 打包
    print("[6/6] 合规自检...")
    if not interactive_confirm():
        print("自检未通过，未生成 zip。素材仍保留在 processed/ 目录。")
        return

    meta = PackMeta(
        project_name=project_safe,
        scenario="S1",
        items=[
            AssetItem(
                filename=final_name,
                kind="face_texture",
                size=(1024, 1024),
                generation=GenerationInfo(
                    backend="skill_multimodal_gen (Agnes2.0)",
                    prompt=final_prompt,
                    negative_prompt=NEGATIVE_PROMPT,
                    seed=seed if seed is not None else -1,
                ),
                postprocess=["rembg", "resize_1024x1024", "rgba"],
            )
        ],
    )

    zip_path = pack_project(out_dir, meta)
    print(f"\n{'=' * 50}")
    print(f"完成！素材包: {zip_path}")
    print(f"元数据: {out_dir / 'meta.json'}")
    print(f"{'=' * 50}")
    print("下一步：把 zip 解压后的 PNG 拖进 Effect Creator。")
    print(f"       project root: {out_dir}")


if __name__ == "__main__":
    main()
