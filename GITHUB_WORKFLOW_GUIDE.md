# GitHub工作流使用指南

## 概述

本项目已配置GitHub Actions工作流，可以自动运行AI文章生成器。工作流支持多种触发方式和配置选项。

## 工作流特性

### 🚀 触发方式

1. **手动触发** - 通过GitHub界面手动运行
2. **定时触发** - 每天上午9点自动运行
3. **推送触发** - 当特定文件更新时自动运行

### 🎛️ 配置选项

- **关键词输入** - 支持多行关键词，格式：`关键词----自定义尾词----游戏名`
- **AI平台选择** - 支持Groq、OpenAI、Gemini、Claude
- **图片下载** - 可选择是否下载相关图片
- **语言生成** - 支持简体中文、繁体中文或双语

## 快速开始

### 1. 配置GitHub Secrets

在GitHub仓库设置中添加以下Secrets：

#### API密钥配置
```
GROQ_API_KEY_1=你的Groq API密钥1
GROQ_API_KEY_2=你的Groq API密钥2
GROQ_API_KEY_3=你的Groq API密钥3
GROQ_API_KEY_4=你的Groq API密钥4
GROQ_API_KEY_5=你的Groq API密钥5
GROQ_API_KEY_6=你的Groq API密钥6
OPENAI_API_KEY=你的OpenAI API密钥
GEMINI_API_KEY=你的Gemini API密钥
CLAUDE_API_KEY=你的Claude API密钥
```

#### 提示词模板配置
```
ZH_CN_PROMPT_TEMPLATE=你的简体中文提示词模板
ZH_TW_PROMPT_TEMPLATE=你的繁体中文提示词模板
```

### 2. 手动运行工作流

1. 进入GitHub仓库页面
2. 点击"Actions"标签
3. 选择"AI文章生成器工作流"
4. 点击"Run workflow"
5. 填写参数：
   - **关键词**: 输入文章主题，每行一个
   - **AI平台**: 选择要使用的AI平台
   - **是否需要图片**: 选择是否下载图片
   - **生成语言**: 选择生成的语言版本

### 3. 查看运行结果

- 在Actions页面查看工作流运行状态
- 下载生成的文章文件
- 查看错误日志（如有失败）

## 详细配置

### 关键词格式

支持以下格式：

```
# 基本格式
关键词

# 带游戏名
关键词----游戏名

# 完整格式
关键词----自定义尾词----游戏名
```

示例：
```
一念逍遥零氪玩家玩什么职业----无限钻石版----一念逍遥
原神新手攻略----原神
王者荣耀英雄推荐
```

### AI平台配置

#### Groq（推荐）
- 速度快，成本低
- 支持多个模型
- 已配置多个API密钥实现负载均衡

#### OpenAI
- 质量高，稳定性好
- 支持GPT-3.5和GPT-4系列
- 成本相对较高

#### Google Gemini
- Google官方AI模型
- 支持多语言
- 免费额度较大

#### Anthropic Claude
- 高质量输出
- 支持长文本
- 安全性好

### 定时任务配置

工作流默认每天上午9点（UTC时间）自动运行。如需修改时间，编辑`.github/workflows/ai-article-generator.yml`文件中的cron表达式：

```yaml
schedule:
  - cron: '0 9 * * *'  # 每天上午9点
  - cron: '0 */6 * * *'  # 每6小时运行一次
  - cron: '0 0 * * 1'  # 每周一运行
```

### 推送触发配置

当以下文件更新时会自动触发工作流：
- `长尾词.txt` - 长尾词文件
- `aigen.py` - 主程序文件
- `config.json` - 配置文件

## 输出文件

### 生成的文章
- 位置：`assets/`目录
- 格式：Markdown文件
- 结构：按语言和关键词分类

### 错误日志
- 位置：`assets/error_log.txt`
- 格式：JSON格式
- 内容：失败的文章和错误信息

### 使用统计
- API密钥使用情况
- 成功率统计
- 平台性能数据

## 故障排除

### 常见问题

1. **工作流运行失败**
   - 检查GitHub Secrets配置
   - 验证API密钥有效性
   - 查看错误日志

2. **API调用失败**
   - 检查网络连接
   - 验证API配额
   - 尝试切换平台

3. **文章生成失败**
   - 检查关键词格式
   - 验证提示词模板
   - 查看详细错误信息

### 调试模式

启用详细日志输出：

```yaml
- name: 运行AI文章生成器
  run: |
    export PYTHONUNBUFFERED=1
    export DEBUG=1
    python aigen.py
```

### 监控和通知

工作流支持多种通知方式：

1. **GitHub通知** - 自动发送到仓库
2. **邮件通知** - 配置SMTP设置
3. **Slack通知** - 集成Slack webhook
4. **钉钉通知** - 集成钉钉机器人

## 高级配置

### 自定义工作流

可以创建多个工作流文件：

```yaml
# .github/workflows/daily-articles.yml - 每日文章
# .github/workflows/weekly-summary.yml - 每周总结
# .github/workflows/emergency-backup.yml - 紧急备份
```

### 环境变量

支持环境变量配置：

```yaml
env:
  PYTHONPATH: ${{ github.workspace }}
  DEBUG: false
  LOG_LEVEL: INFO
```

### 矩阵策略

支持多平台并行运行：

```yaml
strategy:
  matrix:
    platform: [groq, openai, gemini]
    language: [zh-cn, zh-tw]
```

## 最佳实践

1. **API密钥管理**
   - 使用多个密钥实现负载均衡
   - 定期轮换密钥
   - 监控使用量

2. **错误处理**
   - 设置合理的重试次数
   - 记录详细错误信息
   - 实现优雅降级

3. **性能优化**
   - 使用缓存减少重复请求
   - 并行处理多个任务
   - 优化图片下载策略

4. **安全考虑**
   - 不要在代码中硬编码密钥
   - 使用GitHub Secrets存储敏感信息
   - 定期更新依赖包

## 支持

如果遇到问题，请：

1. 查看GitHub Actions日志
2. 检查配置文件格式
3. 验证API密钥有效性
4. 参考项目文档
5. 提交Issue获取帮助

## 更新日志

- **v1.0.0** - 初始版本，支持基本功能
- **v1.1.0** - 添加多平台支持
- **v1.2.0** - 优化错误处理和重试机制
- **v1.3.0** - 添加图片下载功能
- **v1.4.0** - 支持多语言生成
