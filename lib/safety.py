"""合规自检清单（个人责任提醒，非工程化拦截器）。"""

COMPLIANCE_ITEMS = [
    "不涉及真实政治人物 / 公众人物 / 名人脸部特征",
    "不涉及色情、露点、性暗示",
    "不涉及血腥、自残、暴力、恐怖元素",
    "不涉及他人肖像 / 商标 / 受版权保护 IP",
    "不涉及政治敏感、民族 / 宗教 / 性别歧视",
    "不涉及违法物品（毒品 / 武器 / 赌博）",
    "已确认按抖音指引在提审时标注 AI 生成",
]


def render_checklist_text() -> str:
    """返回一段控制台 / chat 用的文案，让自己逐项确认。"""
    lines = [
        "=" * 50,
        "合规自检清单（请逐项确认 y/n）：",
        "=" * 50,
    ]
    for i, item in enumerate(COMPLIANCE_ITEMS, 1):
        lines.append(f"  [{i}] {item}")
    return "\n".join(lines)


def interactive_confirm() -> bool:
    """命令行交互：全部 y 才返回 True。"""
    print(render_checklist_text())
    for i, item in enumerate(COMPLIANCE_ITEMS, 1):
        ans = input(f"[{i}] 确认？(y/n): ").strip().lower()
        if ans != "y":
            print(f"✗ 第 {i} 项未确认，取消导出。")
            return False
    print("✓ 合规自检全部通过。")
    return True
