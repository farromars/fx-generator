"""S1：抖音面部贴图素材命令行流水线。

UI 模式优先（python app.py），命令行模式作为备用：

    python -m workflows.s1_face_paint \
        --provider local_sdxl \
        --prompt "cyberpunk metal mask" \
        --project cyberpunk-mask-v1 \
        --n 4
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import click
from PIL import Image

from lib.config import OUTPUT_ROOT, load_providers
from lib.matting import remove_background, warmup as rembg_warmup
from lib.normalize import normalize_for_ec, safe_filename
from lib.packager import AssetItem, GenerationInfo, PackMeta, pack_project
from lib.providers import ProviderConfig, get_provider
from lib.safety import interactive_confirm
from workflows._common import create_output_dirs, select_candidate

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


def _build_provider(provider_id: str):
    providers = load_providers()
    entry = next((p for p in providers if p.id == provider_id), None)
    if entry is None:
        available = [p.id for p in providers]
        raise click.UsageError(f"未知 provider {provider_id}。可用：{available}")
    api_key = os.environ.get(entry.api_key_env, "") if entry.api_key_env else ""
    cfg = ProviderConfig(endpoint=entry.endpoint, api_key=api_key, model=entry.default_model)
    prov = get_provider(entry.id, config=cfg)
    return prov, entry


@click.command()
@click.option("--provider", default="agnes", show_default=True,
              help="provider id：agnes / local_sdxl / openai")
@click.option("--prompt", required=True, help="主题描述")
@click.option("--project", required=True, help="项目名")
@click.option("--n", default=4, show_default=True, help="候选数")
@click.option("--seed", default=None, type=int)
@click.option("--size", default="1024x1024", show_default=True)
@click.option("--matting-model", default="u2net_human_seg", show_default=True)
@click.option("--no-confirm", is_flag=True, help="跳过合规自检（仅供调试，正式上架不可用）")
def main(provider: str, prompt: str, project: str, n: int,
         seed: int | None, size: str, matting_model: str, no_confirm: bool):
    project_safe = safe_filename(project)
    out_dir = OUTPUT_ROOT / f"{date.today().isoformat()}-{project_safe}"
    create_output_dirs(out_dir)

    final_prompt = PROMPT_TEMPLATE.replace("{{THEME}}", prompt)
    print(f"[1/6] Prompt: {final_prompt[:120]}...")
    print(f"[2/6] 准备 rembg 模型...")
    rembg_warmup(matting_model, progress_cb=print)

    print(f"[3/6] 调用 {provider} 生成 {n} 张候选...")
    prov, entry = _build_provider(provider)
    candidates = prov.generate(
        prompt=final_prompt,
        n=n,
        size=size,
        seed=seed,
        negative_prompt=NEGATIVE_PROMPT,
        output_dir=out_dir / "candidates",
    )
    print(f"      收到 {len(candidates)} 张")

    print("[4/6] 选择候选图...")
    selected = candidates[0] if len(candidates) == 1 else select_candidate(candidates)
    selected_dst = out_dir / "selected" / selected.name
    selected_dst.write_bytes(selected.read_bytes())

    print(f"[5/6] 抠图 + 规范化（{matting_model}）...")
    try:
        matted = remove_background(Image.open(selected_dst), model=matting_model)
    except RuntimeError as e:
        print(f"      抠图失败 ({e})，退化为原图")
        matted = Image.open(selected_dst).convert("RGBA")
    normalized = normalize_for_ec(matted, (1024, 1024))
    final_name = safe_filename(f"{project_safe}_face_paint_main") + ".png"
    final_path = out_dir / "processed" / final_name
    normalized.save(final_path, "PNG")

    print("[6/6] 合规自检...")
    if not no_confirm and not interactive_confirm():
        print("自检未通过，未生成 zip。素材仍在 processed/。")
        return

    meta = PackMeta(
        project_name=project_safe,
        scenario="S1",
        items=[AssetItem(
            filename=final_name,
            kind="face_texture",
            size=(1024, 1024),
            generation=GenerationInfo(
                backend=entry.id,
                model_id=entry.default_model,
                prompt=final_prompt,
                negative_prompt=NEGATIVE_PROMPT,
                seed=seed if seed is not None else -1,
            ),
            postprocess=[matting_model, "resize_1024x1024", "rgba"],
        )],
    )
    zip_path = pack_project(out_dir, meta)
    print()
    print("=" * 60)
    print(f"完成：{zip_path}")
    print(f"项目：{out_dir}")
    print("=" * 60)
    print("下一步：解压 zip → 拖进 Douyin AR → 搭工程 → 提审")


if __name__ == "__main__":
    main()
