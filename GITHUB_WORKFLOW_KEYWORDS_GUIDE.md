# 关键词处理工作流使用指南

## 概述

本项目包含三个GitHub Actions工作流，用于自动化处理关键词文章标题生成：

1. **process-keywords.yml** - 主要的关键词处理工作流
2. **process-keywords-retry.yml** - 重试工作流
3. **notify-completion.yml** - 完成通知工作流

## 工作流详情

### 1. 主要处理工作流 (process-keywords.yml)

**触发方式：**
- 🕐 **定时触发**：每天晚上8点自动执行 (`cron: '0 20 * * *'`)
- 🔧 **手动触发**：可在GitHub Actions页面手动运行

**功能特性：**
- 自动从KV存储获取今日关键词数据
- 使用AI生成文章标题（zh-tw提示词）
- 每个关键词处理完成后立即保存到KV存储
- 支持处理数量限制（测试用）
- 自动重试机制（失败后1小时重试）
- 详细的日志记录和状态跟踪

**手动触发参数：**
- `max_process_count`: 最大处理数量（默认1000）
- `force_restart`: 强制重新开始处理（默认false）

### 2. 重试工作流 (process-keywords-retry.yml)

**触发方式：**
- 🔄 **自动触发**：主工作流失败后自动创建
- 🔧 **手动触发**：可手动创建重试任务

**功能特性：**
- 等待1小时后执行重试
- 最多重试2次
- 保持原始运行ID的关联
- 独立的日志记录

**手动触发参数：**
- `original_run_id`: 原始运行ID（必需）
- `retry_count`: 重试次数（默认1）
- `max_process_count`: 最大处理数量（默认1000）

### 3. 通知工作流 (notify-completion.yml)

**触发方式：**
- 🔔 **自动触发**：主工作流或重试工作流完成后自动执行

**功能特性：**
- 监控所有关键词处理工作流的执行状态
- 发送成功/失败/取消/超时通知
- 可扩展支持多种通知方式（邮件、Slack、钉钉等）

## 配置要求

### GitHub Secrets

需要在GitHub仓库的Settings > Secrets and variables > Actions中配置以下密钥：

#### AI平台API密钥
```
GROQ_API_KEY_1
GROQ_API_KEY_2
GROQ_API_KEY_3
GROQ_API_KEY_4
GROQ_API_KEY_5
GROQ_API_KEY_6
OPENAI_API_KEY
GEMINI_API_KEY
CLAUDE_API_KEY
```

#### 提示词模板
```
ZH_CN_PROMPT_TEMPLATE
ZH_TW_PROMPT_TEMPLATE
GOOGLE_SEO_ARTICLE_TITLE_PROMPT_ZH_CN
GOOGLE_SEO_ARTICLE_TITLE_PROMPT_ZH_TW
```

### Cloudflare KV存储

工作流使用Cloudflare KV存储来：
- 存储每日关键词数据
- 保存处理进度
- 实现断点续传

**KV存储配置：**
- Account ID: `7f568267018e374a7cfdc6cde299e7ee`
- Namespace ID: `c681abe2d69d4e90832414969bf4f459`
- API Token: `xnQ_Roo-hQKnSHuewbI5wyekALaege1HxvOlgztv`

## 使用方法

### 1. 自动执行

工作流会在每天晚上8点自动执行，无需人工干预。

### 2. 手动执行

1. 进入GitHub仓库的Actions页面
2. 选择"关键词文章标题处理工作流"
3. 点击"Run workflow"
4. 设置参数（可选）
5. 点击"Run workflow"开始执行

### 3. 监控执行状态

- 在Actions页面查看工作流执行状态
- 查看详细的日志输出
- 下载处理日志和结果文件

## 数据流程

```
1. 定时触发 (每天20:00)
   ↓
2. 从KV存储获取今日数据
   ↓
3. 处理关键词生成标题
   ↓
4. 立即保存到KV存储
   ↓
5. 检查处理结果
   ↓
6. 成功 → 发送成功通知
   失败 → 创建重试工作流 (1小时后)
   ↓
7. 重试工作流执行
   ↓
8. 最多重试2次
   ↓
9. 最终结果通知
```

## 故障排除

### 常见问题

1. **API密钥无效**
   - 检查GitHub Secrets中的API密钥是否正确
   - 确认API密钥有足够的配额

2. **KV存储连接失败**
   - 检查Cloudflare KV存储配置
   - 确认API Token权限

3. **处理超时**
   - 工作流有2小时超时限制
   - 如果超时，会自动触发重试

4. **重试失败**
   - 最多重试2次
   - 检查日志了解具体失败原因

### 日志查看

- 工作流执行日志：Actions页面
- 处理结果文件：Artifacts下载
- KV存储数据：Cloudflare控制台

## 扩展功能

### 通知集成

可以在`notify-completion.yml`中添加更多通知方式：

```yaml
- name: 发送邮件通知
  uses: dawidd6/action-send-mail@v3
  with:
    server_address: smtp.gmail.com
    server_port: 587
    username: ${{ secrets.MAIL_USERNAME }}
    password: ${{ secrets.MAIL_PASSWORD }}
    subject: 关键词处理完成通知
    body: |
      工作流执行结果: ${{ steps.check-workflow.outputs.conclusion }}
      运行ID: ${{ steps.check-workflow.outputs.run_id }}
```

### 自定义处理逻辑

可以修改`process_keywords.py`来：
- 调整处理数量限制
- 修改标题生成逻辑
- 添加更多验证规则
- 集成其他AI平台

## 注意事项

1. **API配额管理**：注意AI平台的API使用配额
2. **KV存储限制**：Cloudflare KV有读写限制
3. **工作流超时**：单个工作流最长运行2小时
4. **重试机制**：最多重试2次，避免无限重试
5. **日志保留**：日志文件保留7天，结果文件保留30天

## 更新日志

- **v1.0.0** - 初始版本，支持基本的关键词处理功能
- **v1.1.0** - 添加重试机制和通知功能
- **v1.2.0** - 优化错误处理和日志记录
