# AI多平台文章生成器 - 配置说明

## 概述

本程序支持多个AI平台，包括Groq、OpenAI、Google Gemini、Anthropic Claude等。所有配置都通过 `config.json` 文件进行管理。

## 配置文件说明

### 基本结构

```json
{
  "default_platform": "groq",
  "platforms": {
    "平台名称": {
      "配置项": "值"
    }
  },
  "settings": {
    "全局设置": "值"
  }
}
```

### 平台配置项

每个平台需要配置以下项目：

- `name`: 平台显示名称
- `base_url`: 原始API地址
- `proxy_url`: 代理API地址（可选）
- `models`: 模型配置
  - `default`: 默认模型
  - `available`: 可用模型列表
- `api_keys`: API密钥列表
- `headers`: 请求头
- `auth_type`: 认证类型（bearer、x-api-key、api_key）
- `timeout`: 超时时间（秒）
- `max_retries`: 最大重试次数

### 全局设置

- `use_proxy`: 是否使用代理（true/false）
- `temperature`: 生成温度（0.0-1.0）
- `max_tokens`: 最大生成token数
- `top_p`: Top-p采样参数
- `stream`: 是否流式输出

## 支持的平台

### 1. Groq
```json
"groq": {
  "name": "Groq",
  "base_url": "https://api.groq.com/openai/v1/chat/completions",
  "proxy_url": "https://m3u8-player.5yxy5.com/api/forward/https://api.groq.com/openai/v1/chat/completions",
  "models": {
    "default": "deepseek-r1-distill-llama-70b",
    "available": [
      "deepseek-r1-distill-llama-70b",
      "llama-3.1-70b-versatile",
      "llama-3.1-8b-instant",
      "mixtral-8x7b-32768"
    ]
  },
  "api_keys": [
    "你的Groq API密钥1",
    "你的Groq API密钥2"
  ],
  "headers": {
    "Content-Type": "application/json"
  },
  "auth_type": "bearer",
  "timeout": 60,
  "max_retries": 20
}
```

### 2. OpenAI
```json
"openai": {
  "name": "OpenAI",
  "base_url": "https://api.openai.com/v1/chat/completions",
  "proxy_url": "https://m3u8-player.5yxy5.com/api/forward/https://api.openai.com/v1/chat/completions",
  "models": {
    "default": "gpt-3.5-turbo",
    "available": [
      "gpt-3.5-turbo",
      "gpt-3.5-turbo-16k",
      "gpt-4",
      "gpt-4-turbo",
      "gpt-4o",
      "gpt-4o-mini"
    ]
  },
  "api_keys": [
    "你的OpenAI API密钥"
  ],
  "headers": {
    "Content-Type": "application/json"
  },
  "auth_type": "bearer",
  "timeout": 60,
  "max_retries": 20
}
```

### 3. Google Gemini
```json
"gemini": {
  "name": "Google Gemini",
  "base_url": "https://generativelanguage.googleapis.com/v1beta/models",
  "proxy_url": "https://m3u8-player.5yxy5.com/api/forward/https://generativelanguage.googleapis.com/v1beta/models",
  "models": {
    "default": "gemini-1.5-flash",
    "available": [
      "gemini-1.5-flash",
      "gemini-1.5-pro",
      "gemini-1.0-pro"
    ]
  },
  "api_keys": [
    "你的Gemini API密钥"
  ],
  "headers": {
    "Content-Type": "application/json"
  },
  "auth_type": "api_key",
  "timeout": 60,
  "max_retries": 20
}
```

### 4. Anthropic Claude
```json
"claude": {
  "name": "Anthropic Claude",
  "base_url": "https://api.anthropic.com/v1/messages",
  "proxy_url": "https://m3u8-player.5yxy5.com/api/forward/https://api.anthropic.com/v1/messages",
  "models": {
    "default": "claude-3-sonnet-20240229",
    "available": [
      "claude-3-sonnet-20240229",
      "claude-3-opus-20240229",
      "claude-3-haiku-20240307"
    ]
  },
  "api_keys": [
    "你的Claude API密钥"
  ],
  "headers": {
    "Content-Type": "application/json",
    "anthropic-version": "2023-06-01"
  },
  "auth_type": "x-api-key",
  "timeout": 60,
  "max_retries": 20
}
```

## 使用方法

### 1. 配置API密钥

编辑 `config.json` 文件，在对应平台的 `api_keys` 数组中添加你的API密钥：

```json
"api_keys": [
  "sk-your-actual-api-key-here",
  "sk-another-api-key-here"
]
```

### 2. 设置默认平台

修改 `default_platform` 字段：

```json
"default_platform": "openai"
```

### 3. 运行程序

```bash
python aigen.py
```

程序会自动：
1. 加载配置文件
2. 显示可用的AI平台
3. 让你选择要使用的平台
4. 使用选中的平台生成文章

## 功能特性

### 多平台支持
- 支持多个AI平台同时配置
- 运行时动态切换平台
- 统一的API接口

### 负载均衡
- 支持多个API密钥
- 自动轮换密钥
- 失败时自动切换

### 错误处理
- 智能重试机制
- 详细的错误信息
- 使用统计显示

### 配置管理
- JSON格式配置文件
- 热重载配置
- 平台信息显示

## 注意事项

1. **API密钥安全**: 不要将包含真实API密钥的配置文件提交到版本控制系统
2. **代理设置**: 如果在中国大陆使用，建议开启 `use_proxy` 选项
3. **模型选择**: 不同平台的模型名称和参数可能不同，请参考各平台文档
4. **配额限制**: 注意各平台的API调用限制和费用

## 故障排除

### 常见问题

1. **平台不可用**: 检查API密钥是否正确配置
2. **网络错误**: 尝试开启代理模式
3. **模型错误**: 检查模型名称是否正确
4. **认证失败**: 验证API密钥是否有效

### 调试信息

程序会显示详细的调试信息，包括：
- 当前使用的平台和模型
- API密钥使用统计
- 错误详情和建议

## 扩展新平台

要添加新的AI平台，只需在 `config.json` 中添加新的平台配置：

```json
"new_platform": {
  "name": "新平台名称",
  "base_url": "API地址",
  "models": {
    "default": "默认模型",
    "available": ["模型列表"]
  },
  "api_keys": ["密钥列表"],
  "headers": {"请求头"},
  "auth_type": "认证类型",
  "timeout": 60,
  "max_retries": 20
}
```

然后在 `api_manager.py` 的 `_extract_content_from_response` 方法中添加对应的响应解析逻辑。