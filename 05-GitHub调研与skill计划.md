# 05 - GitHub 调研与 skill 计划

> Project DOUYIN-FX ｜ v0.1（方向 A 配套）
> 文档状态：草案 / 待执行
> 这份文档定义"v0.1 编码前要做的 GitHub 调研动作"，本身**不是结论**，是任务清单 + 模板。

## 0. 这份文档的作用

方向 A 严重依赖两件事：

1. **复用 IDE 的"多模态内容生成"skill** —— 但 skill 的具体能力 / 入口 / 限制要在编码前确认
2. **复用 GitHub 上已有的 AIGC 流水线 / 抠图 / 序列帧 / LUT 项目** —— 避免造轮子

本文档定义这两件事的**调研方法**：搜什么、怎么评分、产出什么。**调研动作本身待执行**（人或 IDE agent 都可以，目前未做）。

> 调研不是"拍脑袋决定"，结果会反过来影响 `02-技术方案.md` §5（具体哪些功能可以直接调 skill / 抄 GitHub，哪些必须自写）。

## 1. 调研范围

### 1.1 三类目标仓库

按 PRD §0 方向 A 的需求，调研聚焦以下三类：

| 类别 | 是什么 | 期望产出 |
|---|---|---|
| **A. Anthropic Agent Skills**（`SKILL.md` 格式） | Claude / CodeBuddy 类 IDE 加载的 agent skill | 借鉴写法 + 评估能否直接 fork |
| **C. ComfyUI custom nodes / workflows** | AIGC 出图主流生态，节点/工作流可直接组合 | 找"face texture / sticker frames / LUT 生成"现成工作流 |
| **D. n8n / Dify / Coze 工作流模板** | 工作流编排预制流程 | 借鉴流程结构，不一定真的接入 |

排除：
- 旧的 PyTorch 训练框架（与 v0.1 出素材诉求不直接相关）
- 整套桌面应用（Foocus / SD WebUI 等，太重）

### 1.2 关键词（中英）

按"垂类匹配优先 / 通用次之"，建议组合搜：

**垂类（先搜）**：
- `tiktok effect generator`
- `tiktok face filter ai`
- `effect house ai assets`
- `face texture generator stable diffusion`
- `sticker pack ai pipeline`
- `LUT generator from image`
- `face uv unwrap stable diffusion`

**通用（再搜）**：
- `comfyui face texture workflow`
- `comfyui sticker workflow`
- `agent skill image generation pipeline`
- `claude skill creative workflow`
- `n8n stable diffusion workflow template`
- `dify image pipeline`
- `aigc asset pipeline`

**反向语义**（找定位接近但范围不同的项目，避免重做）：
- `creative ai workflow tool`
- `prompt to product pipeline`

## 2. 评分维度

每个候选仓库按 6 维度评分，每项 0-5 分，总分 30。

| 维度 | 权重 | 评分细则 |
|---|---|---|
| **与方向 A 匹配度** | × 2 | 5=可直接抄整个流程；3=可抄 1-2 个模块；1=仅借鉴思路；0=无关 |
| **维护活跃度** | × 1 | 5=最近 1 月 commit + issue 有响应；3=半年内活跃；1=> 1 年未更新；0=明显废弃 |
| **License 兼容性** | × 1 | 5=MIT/Apache；3=BSD/MPL；1=GPL/AGPL；0=自定义/不明 |
| **复用粒度** | × 1 | 5=可整体抄；3=抄部分模块；1=仅参考代码片段；0=只能看思路 |
| **学习成本** | × 1 | 5=README 照做半小时跑通；3=半天；1=数天；0=没文档 |
| **生态健康度** | × 1 | 5=star > 1k + 文档完整；3=star 100-1k；1=star < 100；0=只有空仓 |

> 加权总分 = 匹配度×2 + 维护×1 + License×1 + 复用×1 + 学习×1 + 生态×1（满分 35）

## 3. 调研产出（模板）

调研做完后，把结果写到本文档 §4。每个候选填如下表：

| 字段 | 内容 |
|---|---|
| 仓库名 | `org/repo` |
| 链接 | `https://github.com/...` |
| 一句话定位 | "这是个干啥的项目" |
| star / fork / 最近 commit | `1.2k / 230 / 2026-05-12` |
| License | `MIT` |
| 与 douyin-fx 方向 A 的契合点 | 哪段代码 / 哪个 workflow / 哪种思路能用 |
| 不能用的部分 | 范围太大 / license 不友好 / 已停维护 等 |
| 评分明细 | 匹配×2/维护/license/复用/学习/生态 = a/b/c/d/e/f → 总分 G |
| 拟采用方式 | "fork 后裁剪" / "抄 lib/xxx.py 的实现" / "仅参考流程图" / "弃用" |

## 4. 调研结果（待填充）

### 4.1 Top 10 候选清单

> 调研未执行。下面是占位表格，实际执行后填入。

| 排名 | 仓库 | 类别 | 总分 | 拟采用方式 |
|---|---|---|---|---|
| 1 | __待填__ | __A/C/D__ | __/35 | __ |
| 2 | __待填__ | | | |
| 3 | __待填__ | | | |
| 4 | __待填__ | | | |
| 5 | __待填__ | | | |
| 6 | __待填__ | | | |
| 7 | __待填__ | | | |
| 8 | __待填__ | | | |
| 9 | __待填__ | | | |
| 10 | __待填__ | | | |

### 4.2 详细评估（每个候选一节，待填）

#### 4.2.1 __仓库 1__

| 字段 | 内容 |
|---|---|
| 仓库 | __待填__ |
| 链接 | __待填__ |
| ... | ... |

（其余 9 个同结构，调研时按模板补全）

## 5. v0.1 跑通后的 skill 沉淀计划

调研 + v0.1 跑通后，把工作流固化为一个本地 skill：

### 5.1 skill 元数据

```yaml
# .codebuddy/skills/douyin-effect-creator/SKILL.md（前置元数据）
---
name: douyin-effect-creator
description: |
  做一个抖音面部特效。从主题描述（如"赛博朋克金属面具"）开始，
  自动调用多模态内容生成 skill 出 N 张候选 → 帮我挑选 → 抠透明背景 →
  按 Effect Creator 资产规范规范化 → 合规自检 → 输出 zip 素材包。
  最终我手工拖进 Effect Creator 搭工程并提审。
location: user
---
```

### 5.2 触发词

- "做一个 X 主题的抖音面部特效"
- "用 S1 流水线做 X"
- "出一组 X 主题的抖音特效素材"

### 5.3 内部步骤（在 SKILL.md 里写明）

1. 询问主题（如未在用户输入中明确）
2. 调用本仓库 `workflows/s1_face_paint.py`，参数从对话推断
3. 出图后用 `ask_followup_question` 让我选
4. 跑后处理（matting / normalize）
5. 渲染合规自检清单 → 让我逐项确认
6. 打包 zip → 输出路径
7. 提示我下一步去 EC 搭工程

### 5.4 沉淀时机

- v0.1 命令行版至少跑过 3 次成功上架特效后再造 skill
- 不要在 v0.1 编码同时造 skill（会变成抽象错误）

## 6. 与其他文档的联动

- **05 → 02 §5.1**：`skill_bridge.py` 的具体实现策略，等本文档 §4 填完后才能定稿
- **05 → 03 §0.5**：模型权重下载是否还需要工具自己管，取决于"多模态内容生成" skill 是否覆盖
- **05 → README**：v0.1 跑通后，README 的"快速开始"应该改为"在 IDE 里说一句话即可"，而不是 `pip install`

## 7. 调研动作清单（给执行人）

> 不是马上做，是清单。可以人工做，也可以让 IDE agent 一步步做。

- [ ] 1. 用 §1.2 关键词在 GitHub 搜索（先垂类后通用），收集候选 ≥ 30 个
- [ ] 2. 按 §2 评分维度筛到 Top 10，填入 §4.1
- [ ] 3. 对 Top 10 每个详细评估，填入 §4.2
- [ ] 4. 重点关注 Top 3 的代码结构，决定"fork / 抄模块 / 借鉴思路"
- [ ] 5. 把 Top 3 的可用部分**直接更新到 02 §5 的代码骨架**（如发现 `rembg` 有更好替代品，就换）
- [ ] 6. 标记调研完成时间到本文档顶部
- [ ] 7. 如调研中发现"多模态内容生成"skill 不能完全覆盖需求，开启 02 §6 本地兜底实现

## 8. 调研边界 / 风险提示

- ⚠️ **GitHub 搜索结果有 SEO 偏置**：高 star 不一定高质量，要交叉看 commit 频率与 issue 活跃度
- ⚠️ **v0.1 调研不要无限拖**：定个上限（半天到一天），调研到 Top 10 评估完就够，不追求穷尽
- ⚠️ **License 必须看清楚**：CreativeML OpenRAIL-M / GPL / 自定义条款都可能影响后续，做内部工具暂时影响小，但如果以后想分发就回头麻烦
- ⚠️ **"借鉴思路"≠"抄代码"**：抄代码必须保留原作者署名 + license 文件
