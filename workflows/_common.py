"""流水线共用：参数解析 / 交互选图 / 合规自检。"""

from pathlib import Path


def select_candidate(candidates: list[Path]) -> Path:
    """交互式选图。"""
    print(f"\n候选图列表（{len(candidates)} 张）：")
    for i, p in enumerate(candidates, 1):
        print(f"  [{i}] {p.name}")
    while True:
        try:
            idx = int(input("选哪张？(输入序号): ").strip()) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
            print(f"请输入 1-{len(candidates)} 之间的数字。")
        except ValueError:
            print("请输入有效数字。")


def create_output_dirs(out_dir: Path) -> None:
    """创建输出子目录结构。"""
    (out_dir / "candidates").mkdir(parents=True, exist_ok=True)
    (out_dir / "selected").mkdir(exist_ok=True)
    (out_dir / "processed").mkdir(exist_ok=True)
