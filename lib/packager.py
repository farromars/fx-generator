"""素材包打包：zip + meta.json 元数据。"""

import json
import zipfile
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field


class GenerationInfo(BaseModel):
    """模型生成信息。"""
    backend: str  # "skill_multimodal_gen" / "local_sdxl_turbo"
    model_id: str | None = None
    prompt: str
    negative_prompt: str = ""
    seed: int = -1
    extra: dict = Field(default_factory=dict)


class AssetItem(BaseModel):
    """单个素材项。"""
    filename: str
    kind: str  # "face_texture" / "sticker_frame" / "lut"
    size: tuple[int, int] | None = None
    generation: GenerationInfo
    postprocess: list[str] = Field(default_factory=list)


class PackMeta(BaseModel):
    """素材包元数据。"""
    tool_version: str = "0.1.0"
    project_name: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    scenario: str  # "S1" / "S2" / "S3"
    ai_generated: bool = True
    items: list[AssetItem]


def pack_project(project_dir: Path, meta: PackMeta) -> Path:
    """把 processed/ 打成 zip + 写 meta.json。"""
    meta_path = project_dir / "meta.json"
    meta_path.write_text(meta.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    zip_name = safe_zip_name(meta.project_name)
    zip_path = project_dir / f"{zip_name}_pack.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        processed_dir = project_dir / "processed"
        if processed_dir.exists():
            for f in sorted(processed_dir.iterdir()):
                if f.is_file():
                    z.write(f, arcname=f.name)
        z.write(meta_path, arcname="meta.json")

    return zip_path


def safe_zip_name(name: str) -> str:
    """将项目名转为安全的 zip 文件名。"""
    import re
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_")[:64]
