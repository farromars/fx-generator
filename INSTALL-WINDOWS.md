# Windows 部署指南（fx-generator v0.1.1）

> 目标：Windows 笔记本（如宏碁暗影骑士 16，RTX 5060 8GB，32GB 内存）开机即用。
> 假设你已装：Git、Python 3.11+、git-lfs（可选）、显卡驱动。

---

## 0. 一图全览

```
[一次性配置]
  装 Python 3.11+ → 装 PyTorch (CUDA) → git clone → pip install → 下模型
                             ↓
[日常使用]
  python app.py  →  浏览器  →  生成 → 抠图 → 导出 zip → 拖进 Douyin AR
```

预计一次性配置时间：30-60 分钟（取决于网速）。

---

## 1. 装 Python 3.11+ 和 Git

如果还没装：

- Python：https://www.python.org/downloads/windows/  下载 3.11 或 3.12 的 64-bit 安装包，**勾选 "Add Python to PATH"**
- Git：https://git-scm.com/download/win

验证：

```powershell
python --version    # 应显示 Python 3.11.x 或更新
git --version
```

---

## 2. 装 PyTorch（CUDA 12.4+，5060 必需）

> **重要**：RTX 5060 是 50 系（Blackwell），需要 PyTorch 2.5+ 且 CUDA 12.4+，旧版本会报 `CUDA error: no kernel image is available for execution on the device`。

PowerShell 执行：

```powershell
# 1. 升级 pip
python -m pip install --upgrade pip

# 2. 安装 PyTorch（CUDA 12.4 wheel；如果官方更新到 12.6/12.8 请改 cu126/cu128）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

验证：

```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no cuda')"
```

应输出类似：

```
2.5.1+cu124 True NVIDIA GeForce RTX 5060 Laptop GPU
```

如果 `False`：
- 检查显卡驱动版本（NVIDIA 控制面板 → 系统信息）需要 ≥ 552.x
- 重启电脑后再试

---

## 3. 拉代码 + 装依赖

```powershell
cd 选一个工作目录，例如：C:\Users\你\projects
git clone https://github.com/farromars/fx-generator.git
cd fx-generator

# 装核心依赖（必装）
pip install -e .

# 装本机推理依赖（可选，如果想用 SDXL Turbo 本机跑）
pip install -e .[local]
```

---

## 4. 下载模型权重

### 4.1 设置 HuggingFace 国内镜像（强烈推荐）

```powershell
# 当前会话生效
$env:HF_ENDPOINT = "https://hf-mirror.com"

# 永久生效（写入用户环境变量）
[System.Environment]::SetEnvironmentVariable("HF_ENDPOINT", "https://hf-mirror.com", "User")
```

### 4.2 下载 rembg 模型（约 170MB）

```powershell
python scripts/download_models.py rembg
```

### 4.3 下载 SDXL Turbo 权重（约 7GB，最慢的一步）

```powershell
python scripts/download_models.py sdxl-turbo
```

如果中途失败：
1. 重新运行命令（断点续传）
2. 或从 ModelScope 手动下载（无需翻墙）：
   - https://www.modelscope.cn/models/AI-ModelScope/sdxl-turbo
   - 把整个 sdxl-turbo 目录放到：
     `C:\Users\你\.cache\huggingface\hub\models--stabilityai--sdxl-turbo\snapshots\<commit_id>\`

---

## 5. 配置 API Key（如要用云端 Provider）

### 5.1 Agnes（如果你已经有 key）

```powershell
$env:AGNES_API_KEY = "你的-agnes-key"

# 永久
[System.Environment]::SetEnvironmentVariable("AGNES_API_KEY", "你的-agnes-key", "User")
```

### 5.2 OpenAI / 其他 OpenAI 兼容（火山方舟 / 硅基流动 / 阿里）

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

然后在 `~/.fxgen/providers.json` 里把 `openai` 的 `enabled` 改 `true`，并把 `endpoint` 改成你的 endpoint（默认 `https://api.openai.com/v1`）。

---

## 6. 检查环境

```powershell
python scripts/check_env.py
```

应输出：

```
=== Python === [✓] Python ≥ 3.11
=== 核心依赖（必装）=== 全 [✓]
=== 本机推理依赖（可选）=== 全 [✓]
=== GPU / 推理后端 === [✓] CUDA 可用 GPU0: NVIDIA GeForce RTX 5060 ... 8.0GB
=== rembg 模型 === [✓] u2net_human_seg.onnx ~167MB
=== SDXL Turbo 模型 === [✓] sdxl-turbo 已缓存 ~7.0GB
总体: ✓ OK
```

---

## 7. 启动 UI

```powershell
python app.py
```

浏览器自动打开 `http://127.0.0.1:7860`。第一次进 UI 后**点一次"🔥 预热 rembg"按钮**（如果模型已经下载好就只是加载到内存，秒级；否则会下载约 170MB）。

---

## 8. 装抖音 Douyin AR（特效编辑器）

工具产出的 zip 解压后是 PNG 素材，需要在 **Douyin AR** 客户端里组装成最终特效再上架。

下载：

> **Windows**：https://lf3-static.bytednsdoc.com/obj/eden-cn/olfk_ajlmml_zlp/ljhwZthlaukjlkulzlp/Douyin_AR870/Douyin_AR_8.7.0_Setup.exe

装好后用抖音号登录。具体素材规范（贴图分辨率、序列帧命名等）官网公开文档不全，**首次使用请实测确认**：

1. 新建 face effect 工程
2. 拖一张 fx-generator 产出的 PNG 进去
3. 看是否需要特定尺寸 / 通道 / 命名
4. 把发现的实际规范填到 `04-EC调研笔记.md` §3，工具可以反过来按规范输出

---

## 9. 日常工作流

```powershell
# 启动
cd C:\Users\你\projects\fx-generator
python app.py

# 浏览器：
# 1. 选 Provider（推荐"本机 SDXL Turbo"，3-6s/张）
# 2. 写 Prompt 例如：cyberpunk metal mask, frontal symmetric, transparent bg
# 3. 点"生成候选图"
# 4. 点选一张
# 5. 点"抠透明背景"
# 6. 点"规范化 1024×1024"
# 7. 填项目名、勾选合规清单
# 8. 点"导出素材包"

# 拿到 zip → 解压 → 拖进 Douyin AR → 搭工程 → 提审
```

---

## 10. 常见问题

### Q：CUDA 不可用 / `False`
检查显卡驱动版本（`nvidia-smi` 看 Driver Version 是否 ≥ 552）；PyTorch 是否真装的 cu124；重启 PowerShell 重试。

### Q：SDXL Turbo OOM（显存不够）
5060 笔记本是 8GB 显存，跑 SDXL Turbo fp16 单图刚好够。如果和其他显存大户（游戏、Chrome 多 tab）抢占会爆。
- 关掉占显存的程序后重启 app
- 或在 `~/.fxgen/providers.json` 里把 `local_sdxl.extra.dtype` 改成 `"fp16"` 已经是最省，无法再省
- 改尺寸 `768x768` 或 `512x512` 也能省一些

### Q：rembg 抠图非常慢（>30s）
- 第一次确实会下载模型，看 `~/.fxgen/rembg/` 里有没有 `.onnx` 文件
- 装了 `onnxruntime` 是 CPU 版，没问题但不会用 GPU；本任务模型小，CPU 足够
- 如果想走 GPU 抠图：`pip install onnxruntime-gpu`（注意会和 CPU 版冲突，要先卸 CPU 版）

### Q：HuggingFace 镜像也连不上
1. 检查公司/学校代理（很多代理拦 HF）
2. 走 ModelScope（见 §4.3）
3. 实在不行就只用 Agnes 云 API，跳过 SDXL Turbo

### Q：Agnes API 提示 401 / 余额不足
检查 `AGNES_API_KEY` 是否正确设置；是否走错了 endpoint。

### Q：Douyin AR 装不上 / 不会用
工具不替代 Douyin AR，关于客户端使用问题请查抖音特效创作者中心或社区。

---

## 11. 留好的扩展口（v0.2+）

后续如果要加新功能，按下面顺序可平滑接入，**不会破坏现状**：

| 扩展 | 改哪里 |
|---|---|
| 新增图像生成 Provider（火山 / 硅基 / Replicate） | `lib/providers/<name>.py` 继承 `BaseImageProvider`，在 `lib/providers/__init__.py` 注册 |
| 新增抠图模型（SAM / BiRefNet） | `lib/matting.py:SUPPORTED_MODELS` 加 |
| 新增"序列帧"流水线（S2） | `workflows/s2_*.py`，UI 加新 tab |
| 新增"LUT"流水线（S3） | `workflows/s3_*.py` |
| 新增 CLI 入口 | `pyproject.toml` 的 `[project.scripts]` 加 |
| 切换 UI 框架（Streamlit / 自定义前端） | 重写 `app.py`，core 不动 |

---

最后核心原则：
- **核心依赖** 写在 `pyproject.toml` 的 `dependencies`
- **可选依赖** 写在 `[project.optional-dependencies]`
- **运行时下载的东西**（模型权重）走 `scripts/download_models.py`
- **平台特定的安装步骤**（CUDA wheel）写在本文档

新增依赖时按这套规则放，就不会到处零散。
