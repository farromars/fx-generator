# fx-generator

> 1 个人用的小工具：用 AI 模型生成抖音面部特效素材（贴图 / 序列帧 / LUT），配合 **Douyin AR** 客户端组装并上架特效。

## 是什么 / 不是什么

| 是 | 不是 |
|---|---|
| 一个本地 Python + Gradio Web UI 的素材生成工具 | 桌面应用 / SaaS / 多平台特效平台 |
| 输出"可被 Douyin AR (Effect Creator) 导入的素材包（PNG）" | 抖音工程文件（.dyfx 等）的产出器 |
| 内部使用，单人，不分发 | 商业产品 / 开源公开分发 |
| 配合 Douyin AR 客户端 + 抖音官方审核流程 | 替代 Douyin AR / 绕过审核 |

## 工作流（一句话）

```
我想 prompt → 工具出素材包 → 我在 Douyin AR 里搭工程 → 抖音提审上架
```

工具只覆盖中间那一段。

## v0.1.1 改动要点

相比 v0.1：

- **Provider 架构统一**：删掉重复的 `lib/api_client.py`，全走 `lib/providers/` 注册表
- **新增 `local_sdxl` Provider**：本机跑 SDXL Turbo（CUDA / mps / cpu 自适应），RTX 5060 上 3-6s/张
- **抠图修复**：默认换 `u2net_human_seg`（人像专用），加预热按钮，模型缓存到 `~/.fxgen/rembg/`，不再卡 3 分钟
- **UI 重排（方向 A）**：5 步流程 + 实时日志 + 进度条 + 双图预览
- **环境工具**：`scripts/check_env.py` + `scripts/download_models.py` + `INSTALL-WINDOWS.md`

## 快速开始

### Windows（推荐路径，开机即用）

请按 [`INSTALL-WINDOWS.md`](./INSTALL-WINDOWS.md) 走一遍。

简略版：

```powershell
# 1. 装 PyTorch (CUDA 12.4+，5060 必需)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# 2. 拉代码
git clone https://github.com/farromars/fx-generator.git
cd fx-generator

# 3. 装依赖
pip install -e .[local]

# 4. 设镜像 + 下模型
$env:HF_ENDPOINT = "https://hf-mirror.com"
python scripts/download_models.py all

# 5. 检查环境
python scripts/check_env.py

# 6. 启动
python app.py
```

### macOS（Apple Silicon）

```bash
# PyTorch（mps 后端，官方 wheel）
pip install torch torchvision

git clone https://github.com/farromars/fx-generator.git
cd fx-generator
pip install -e ".[local]"

python scripts/download_models.py all
python app.py
```

## Douyin AR 客户端下载

工具产出 zip 后，需要在 **Douyin AR**（抖音官方特效编辑器）里组装：

> Windows 8.7.0：https://lf3-static.bytednsdoc.com/obj/eden-cn/olfk_ajlmml_zlp/ljhwZthlaukjlkulzlp/Douyin_AR870/Douyin_AR_8.7.0_Setup.exe

具体素材规范（分辨率、序列帧命名、LUT 立方体尺寸等）官方公开文档不全，请装好后实测，把发现填到 `04-EC调研笔记.md` §3。

## 文档清单

| 文档 | 作用 |
|---|---|
| `01-PRD-产品需求文档.md` | 需求 / 范围 / 合规 |
| `02-技术方案.md` | 架构 / 依赖 / 配置（按方向 A） |
| `03-工作流手册.md` | 操作步骤（含上架） |
| `04-EC调研笔记.md` | Douyin AR 资产规范、坑、模板（边用边补） |
| `05-GitHub调研与skill计划.md` | 编码前 GitHub 调研清单 + skill 沉淀计划 |
| `INSTALL-WINDOWS.md` | Windows 5060 部署手把手 |
| `_archive-v0/` | 上一版"平台级"文档（已废弃，备查） |

## 工程目录

```
fx-generator/
├── app.py                       # Gradio UI 入口
├── lib/
│   ├── config.py                # 统一配置
│   ├── matting.py               # rembg 抠图
│   ├── normalize.py             # EC 资产规范化
│   ├── packager.py              # zip + 元数据
│   ├── safety.py                # 合规自检清单
│   └── providers/               # 图像生成 Provider 注册表
│       ├── base.py
│       ├── agnes_provider.py    # Agnes AI 云 API
│       ├── openai_provider.py   # OpenAI / 兼容 endpoint
│       └── local_sdxl.py        # 本机 SDXL Turbo（CUDA/mps/cpu）
├── workflows/                   # 命令行流水线（备用）
│   └── s1_face_paint.py
├── scripts/
│   ├── check_env.py             # 环境检查
│   └── download_models.py       # 模型下载
├── assets/                      # 内置资源（face_uv 模板等）
├── prompts/                     # Prompt 模板
├── output/                      # 产物（gitignore）
└── docs/                        # 5 份设计文档
```

运行时数据放在 `~/.fxgen/`：

```
~/.fxgen/
├── providers.json               # Provider 配置覆写
├── models/                      # 工具自管的模型缓存
└── rembg/                       # rembg 模型（u2net_human_seg.onnx 等）
```

SDXL Turbo 权重默认在 HuggingFace 缓存：`~/.cache/huggingface/hub/`。

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
| v0.1 原始实现（Gradio + Agnes） | ✅ |
| v0.1.1：Provider 整合 + UI 重排 + 本机 SDXL Turbo + 抠图修复 + Win 部署文档 | ✅ |
| Step 0：装 Douyin AR + 摸资产规范 | ⏳ TODO（你这周做） |
| 第一个特效提审 | ⏳ TODO |
| v0.2：序列帧 / LUT 流水线 | ⏳ 计划 |
