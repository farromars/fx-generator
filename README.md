# fx-generator

> 1 个人用的小工具：用 AI 模型生成抖音面部特效素材，配合 **Douyin AR** 客户端组装上架。

## v0.2.0 改动要点

相比 v0.1.2：

- **UI 大改（单页响应式）**：删 4 步分页（实测分页对单人迭代更乱）；左参右图一屏看全；图片自适应不拖滑块
- **删 7 条合规清单**：改成 prompt 上方红色提醒（PM 评价：勾选式合规是伪安全）
- **删步骤徽章**（单人不需要）
- **Prompt 工程化**：8 个风格预设 + 6 个品类模板 + 3 个 Negative 模板 + 历史下拉（最近 20 条可一键恢复）
- **last_session 自动恢复**：上次的 prompt / negative / seed / 尺寸 等启动时回填
- **Smoke Test**：调试 Tab 一键端到端，打印每步耗时
- **跳过抠图按钮**：手工 PS 抠图场景直接走规范化
- **新增 99-抖音特效市场企划.md**：6 大品类对比 / 起步路径 / v0.2 应该锁哪个品类
- **新增 LEARNINGS.md**：每次跑完特效记 3-5 行，工具迭代的真实依据
- **文档清理**：PRD / 技术方案 / 工作流手册 / GitHub 调研计划 归档到 `_archive-v0.1/`

## 是什么 / 不是什么

| 是 | 不是 |
|---|---|
| 本地 Python + Gradio Web UI | 桌面应用 / SaaS / 多平台特效平台 |
| 输出 Douyin AR (Effect Creator) 可导入素材包 | 抖音工程文件产出器 |
| 内部使用，单人，不分发 | 商业产品 / 开源公开分发 |

## 工作流（一句话）

```
我想 prompt → 工具出素材包 → Douyin AR 里搭工程 → 抖音提审上架
```

## 快速开始

### Mac（Apple Silicon / Intel，跳过本机 SDXL）

```bash
git clone git@github.com:farromars/fx-generator.git
cd fx-generator

# 装核心依赖（不装 [local]，跳过 torch/diffusers）
pip3 install -e .

# 设 Agnes API key（云生成）
export AGNES_API_KEY="你的key"

# 启动
python3 app.py
# 浏览器自动打开 http://127.0.0.1:7860
```

> 抠图模型 (rembg) 首次会自动下载约 170MB；进入"调试工具" Tab 点"🔥 预热 rembg"主动下载。

### Windows（含本机 SDXL Turbo）

按 [`INSTALL-WINDOWS.md`](./INSTALL-WINDOWS.md) 走一遍。简略：

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
git clone git@github.com:farromars/fx-generator.git
cd fx-generator
pip install -e ".[local]"
$env:HF_ENDPOINT = "https://hf-mirror.com"
python scripts/download_models.py all
.\start.bat
```

## Douyin AR 客户端下载

工具产出 zip 后需要在 **Douyin AR**（抖音官方特效编辑器）里组装。

> Windows 8.7.0：https://lf3-static.bytednsdoc.com/obj/eden-cn/olfk_ajlmml_zlp/ljhwZthlaukjlkulzlp/Douyin_AR870/Douyin_AR_8.7.0_Setup.exe

具体素材规范装好后实测，回填到 `04-EC调研笔记.md` §3。

## 文档清单（v0.2.0）

| 文档 | 作用 |
|---|---|
| `README.md` | 入口（本文档） |
| `99-抖音特效市场企划.md` | **必读**：6 大品类对比 / 起步路径 / v0.2 锁什么品类 |
| `04-EC调研笔记.md` | Douyin AR 资产规范、坑、模板（边用边补） |
| `LEARNINGS.md` | 每次跑完特效记的真实经验 |
| `INSTALL-WINDOWS.md` | Windows 5060 部署手把手 |
| `_archive-v0.1/` | v0.1 留下的设计文档（PRD / 技术方案 / 工作流手册 / GitHub 调研计划），备查 |
| `_archive-v0/` | v0 最初"平台级"文档，备查 |

## 工程目录

```
fx-generator/
├── app.py                       # 单页响应式 UI（v0.2.0）
├── lib/
│   ├── config.py                # 统一配置
│   ├── matting.py               # rembg 抠图
│   ├── normalize.py             # EC 资产规范化
│   ├── packager.py              # zip + 元数据
│   ├── safety.py                # 合规清单（仅文案，UI 不再用）
│   ├── prompts.py               # 风格预设 / 品类模板 / 历史 / last_session
│   └── providers/               # 图像生成 Provider 注册表
│       ├── base.py
│       ├── agnes_provider.py    # Agnes AI 云
│       ├── openai_provider.py   # OpenAI / 兼容
│       └── local_sdxl.py        # 本机 SDXL Turbo（CUDA/mps/cpu）
├── workflows/                   # 命令行流水线（备用）
│   └── s1_face_paint.py
├── scripts/
│   ├── check_env.py
│   └── download_models.py
├── assets/, prompts/, output/   # 资源 / 模板 / 产物
└── docs/                        # 设计文档
```

运行时数据：

```
~/.fxgen/                        # 跨项目共享
├── providers.json
├── models/
└── rembg/                       # u2net_human_seg.onnx 等

项目内 output/
├── _history.json                # prompt 历史（最近 20 条）
└── 2026-XX-XX-<project>/        # 单次产出

项目根 .fxgen_last_session.json  # 上次会话状态（自动恢复）
```

## 红线（自我提醒）

UI 顶部红色横幅替代了上版的 7 条勾选清单：

> 不要做：真人换脸 / 明星 / 政治人物 / 色情 / 血腥 / 受版权 IP；
> 上架时按抖音指引标 "AI 生成"。**工具不拦截，由你负责**。

## 状态

| 阶段 | 状态 |
|---|---|
| v0.1.x → v0.2.0（UI 大改 + Prompt 工程化 + smoke test + 文档清理） | ✅ |
| 装 Douyin AR + 摸资产规范 | ⏳ TODO |
| **第一个特效真上架**（v0.2 必做） | ⏳ TODO（PM 强烈建议优先级 P0） |
| v0.3：S2 动态贴纸（图生视频/序列帧） | ⏳ 计划 |
| v0.3：节日 / IP 模板库 | ⏳ 计划 |
