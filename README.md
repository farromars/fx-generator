# DOUYIN-FX

> 1 个人用的小工具：用 AI 模型生成抖音面部特效素材，配合 Effect Creator 上架。

## 是什么 / 不是什么

| 是 | 不是 |
|---|---|
| 一个本地 Python + Gradio Web UI 的素材生成工具 | 桌面应用 / SaaS / 多平台特效平台 |
| 输出"可被 Effect Creator 导入的素材包（PNG / 序列帧 / LUT）" | 抖音工程文件（.dfx 等）的产出器 |
| 内部使用，单人，不分发 | 商业产品 / 开源公开分发 |
| 配合 EC 官方编辑器 + 抖音官方审核流程 | 替代 EC / 绕过审核 |

## 工作流（一句话）

```
我想 prompt → 工具出素材包 → 我在 Effect Creator 里搭工程 → 抖音提审上架
```

工具只覆盖中间那一段。

## 快速开始（v0.1）

```bash
git clone <repo> && cd douyin-fx
pip install -e .

# 远程后端用的话先设环境变量
export DOUYINFX_REMOTE_API_KEY="sk-xxx"

# 拉模型权重（一次）
python -m douyinfx download-model sdxl-turbo

# 启动 UI
python -m douyinfx
# 浏览器打开 http://127.0.0.1:7860
```

## 文档清单

| 文档 | 作用 |
|---|---|
| `01-PRD-产品需求文档.md` | 需求 / 范围 / 合规 |
| `02-技术方案.md` | 方向 A：命令行脚本 + 复用 IDE skill，含代码骨架 |
| `03-工作流手册.md` | 我自己用的操作步骤（含 EC 上架） |
| `04-EC调研笔记.md` | 抖音 Effect Creator 资产规范、坑、模板（边用边补） |
| `05-GitHub调研与skill计划.md` | v0.1 编码前的 GitHub 调研清单与 skill 沉淀计划 |
| `_archive-v0/` | 上一版"平台级"文档（已废弃，备查） |

## 范围（v0.1）

- 必做：S1 面部贴图（text2img → 抠背景 → 规范化 → 打包）
- 不做：S2 序列帧 / S3 LUT（v0.2）；多平台 / 节点图 / 工程文件产出（永远不做）

## 红线（自我提醒）

- 不做真人换脸 / 明星 / 政治人物
- 不做色情 / 血腥 / 暴恐 / 未成年不适宜
- 不绕过抖音官方审核
- 上架特效按抖音指引标"AI 生成"

详见 `01-PRD-产品需求文档.md` §8 + §11。

## 状态

| 阶段 | 状态 |
|---|---|
| 文档（6 份） | ✅ 草案 |
| GitHub 调研（v0.1 前置） | ⏳ TODO，详见 `05-GitHub调研与skill计划.md` |
| Step 0：装 EC + 摸资产规范 | ⏳ TODO |
| v0.1 实现（方向 A） | ⏳ TODO |
| 第一个特效提审 | ⏳ TODO |
