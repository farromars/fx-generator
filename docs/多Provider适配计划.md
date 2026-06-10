# 多 Provider 适配计划（v0.2 待办）

> 当前 v0.1 只支持 Agnes AI。后续应支持用户选择不同的图像生成服务。

## 背景

用户场景：输入一个提示词，选择不同的大模型来生成素材图。
不同模型的 API 在参数格式、支持的能力上有差异，需要做抽象层统一接口。

## 目标

让用户在 UI 中可切换以下 Provider：

| Provider | 模型 | 特点 |
|----------|------|------|
| **Agnes AI** | agnes-image-2.1-flash | 免费，支持 negative_prompt / seed |
| **OpenAI** | dall-e-3, gpt-image-1 | 质量高，不支持 negative_prompt / seed |
| **Stability AI** | stable-diffusion-3.5 | 支持 negative_prompt / seed |
| **Google Gemini** | gemini-2.0-flash-exp-image | 原生多模态 |

## 架构设计

```
用户选择 Provider
        │
        ▼
┌──────────────────────┐
│   BaseImageProvider  │  ← 抽象接口
│   (abstract class)   │
└──────────────────────┘
        │
        ├── AgnesProvider
        │   ├── supports_negative_prompt = True
        │   ├── supports_seed = True
        │   └── supports_response_format = False
        │
        ├── OpenAIProvider
        │   ├── supports_negative_prompt = False
        │   ├── supports_seed = False
        │   └── (extra_body 无)
        │
        ├── StabilityProvider
        │   └── (调用 stability.ai REST API)
        │
        └── GeminiProvider
            └── (调用 Google AI API)
```

## 各 Provider 参数差异

| 参数 | Agnes | OpenAI | Stability | Gemini |
|------|-------|--------|-----------|--------|
| endpoint | ✅ base_url | ✅ base_url | ❌ | ❌ |
| api_key | ✅ header | ✅ header | ✅ header | ✅ header |
| negative_prompt | ✅ extra_body | ❌ 不支持 | ✅ | ❌ |
| seed | ✅ | ❌ 不支持 | ✅ | ✅ |
| response_format | ❌ 不支持 | ✅ | ✅ | ❌ |
| n (多张) | ✅ | DALL-E3 限1 | ✅ | ✅ |
| size | ✅ | ✅ | ✅ | ✅ |

## UI 交互

- Provider 切换时，根据 `supports_*` 标志动态显示/隐藏 UI 控件
- 例如选 OpenAI 时隐藏 negative_prompt 和 seed 输入框

## 参考实现

`lib/providers/` 目录下已有半成品骨架：
- `base.py` - 抽象基类
- `agnes_provider.py` - Agnes 实现（已验证可用）
- `openai_provider.py` - OpenAI 实现（待测试）
- `__init__.py` - Provider 注册

v0.2 编码前先确认各 Provider 的实际 API 文档，防止参数不匹配。
