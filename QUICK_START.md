# AI多平台文章生成器 - 快速开始指南

## 🚀 快速开始

### 1. 配置API密钥

编辑 `config.json` 文件，添加你的API密钥：

```json
{
  "default_platform": "groq",
  "platforms": {
    "groq": {
      "api_keys": [
        "你的Groq API密钥1",
        "你的Groq API密钥2"
      ]
    },
    "openai": {
      "api_keys": [
        "你的OpenAI API密钥"
      ]
    }
  }
}
```

### 2. 运行程序

```bash
python aigen.py
```

### 3. 选择平台

程序会显示可用的AI平台，选择你想使用的平台：

```
可用的AI平台:
  1. ✅ 默认 groq: Groq (6个密钥)
  2. ⚪ 可选 openai: OpenAI (1个密钥)
请选择平台 (1-2, 默认为1): 
```

## 📋 支持的功能

### 多平台支持
- ✅ Groq (已配置)
- ✅ OpenAI
- ✅ Google Gemini
- ✅ Anthropic Claude
- ✅ 自定义平台

### 智能特性
- 🔄 自动负载均衡
- 🔑 多密钥轮换
- ⚡ 失败自动重试
- 📊 使用统计显示
- 🌐 代理支持

## 🛠️ 配置说明

### 基本配置

1. **设置默认平台**：
   ```json
   "default_platform": "groq"
   ```

2. **添加API密钥**：
   ```json
   "api_keys": [
     "sk-your-api-key-here"
   ]
   ```

3. **选择模型**：
   ```json
   "models": {
     "default": "gpt-3.5-turbo",
     "available": ["gpt-3.5-turbo", "gpt-4"]
   }
   ```

### 高级配置

1. **启用代理**：
   ```json
   "settings": {
     "use_proxy": true
   }
   ```

2. **调整生成参数**：
   ```json
   "settings": {
     "temperature": 0.6,
     "max_tokens": 1500,
     "top_p": 0.95
   }
   ```

## 🔧 故障排除

### 常见问题

1. **没有可用平台**
   - 检查 `config.json` 中的API密钥配置
   - 确保API密钥格式正确

2. **API请求失败**
   - 检查网络连接
   - 验证API密钥是否有效
   - 尝试启用代理模式

3. **平台切换失败**
   - 确保目标平台有有效的API密钥
   - 检查平台配置是否正确

### 调试模式

运行测试脚本查看详细状态：

```bash
python test_config.py
```

## 📚 更多信息

- 详细配置说明：`API_KEYS_README.md`
- 使用示例：`example_usage.py`
- 测试脚本：`test_config.py`

## 🎯 使用技巧

1. **多密钥配置**：为同一平台配置多个API密钥实现负载均衡
2. **平台切换**：根据任务需求选择最适合的AI平台
3. **代理模式**：在中国大陆使用时建议启用代理
4. **错误处理**：程序会自动重试和切换密钥，无需手动干预

## 📞 支持

如果遇到问题，请检查：
1. 配置文件格式是否正确
2. API密钥是否有效
3. 网络连接是否正常
4. 查看错误日志获取详细信息
