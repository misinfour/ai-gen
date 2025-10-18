# 文章生成功能说明

## 概述

本项目新增了完整的文章生成功能，将原本的 `aigen.py` 脚本功能整合到关键词处理流程中，实现了从关键词到完整文章的自动化生成。

## 新增文件

### 1. `article_generator.py`
- **功能**: 文章生成器核心模块
- **特点**: 
  - 整合了 `aigen.py` 的所有功能
  - 支持多语言文章生成（简体中文、繁体中文）
  - 支持图片下载和插入
  - 支持下载链接自动添加
  - 支持相关关键词生成

### 2. `process_articles.py`
- **功能**: 从已处理的关键词数据中生成文章
- **特点**:
  - 读取KV存储中的关键词数据
  - 为每个已生成的标题创建完整文章
  - 支持命令行参数控制
  - 实时保存处理进度

### 3. `.github/workflows/generate-articles.yml`
- **功能**: 文章生成工作流
- **特点**:
  - 每天早上10点自动执行
  - 支持手动触发
  - 支持参数配置
  - 自动上传生成结果

### 4. `.github/workflows/complete-pipeline.yml`
- **功能**: 完整内容生成流水线
- **特点**:
  - 包含关键词处理和文章生成两个步骤
  - 每天早上9点执行关键词处理，10点执行文章生成
  - 支持跳过关键词处理步骤
  - 完整的错误处理和通知机制

### 5. `test_article_generation.py`
- **功能**: 测试文章生成功能
- **特点**:
  - 验证配置是否正确
  - 测试文章生成功能
  - 提供详细的测试报告

## 使用方法

### 1. 本地测试

```bash
# 测试文章生成功能
python test_article_generation.py

# 测试模式运行（处理少量关键词）
python process_articles.py --test

# 限制处理数量
python process_articles.py --max-count 5 --images false
```

### 2. 生产环境

```bash
# 处理所有关键词生成文章
python process_articles.py

# 不下载图片（加快处理速度）
python process_articles.py --images false
```

### 3. GitHub Actions

工作流会自动在以下时间执行：
- **关键词处理**: 每天早上9点（中国时间17点）
- **文章生成**: 每天早上10点（中国时间18点）

## 工作流程

### 完整流程
1. **关键词处理** (`process_keywords.py`)
   - 从JSON文件读取关键词数据
   - 为每个关键词生成多个标题
   - 保存到Cloudflare KV存储

2. **文章生成** (`process_articles.py`)
   - 从KV存储读取已处理的关键词数据
   - 只处理 `use_count` 为 0 的标题（未使用过的标题）
   - 为每个未使用的标题生成完整文章
   - 处理完成后更新 `use_count`、`last_used_at` 和 `usage_records`
   - 支持多语言版本
   - 自动插入图片和下载链接

### 数据流
```
关键词数据 → 标题生成 → KV存储 → 文章生成 → 文件输出
```

### 标题数据结构
每个标题对象包含以下字段：
```json
{
  "title": "文章标题",
  "custom_suffix": "自定义尾词",
  "game_name": "游戏名称",
  "created_at": "创建时间",
  "last_used_at": "最后使用时间",
  "use_count": 0,  // 使用次数，0表示未使用过
  "usage_records": [  // 使用记录数组
    {
      "processed_at": "处理时间",
      "need_images": true,
      "success": true,
      "success_count": 2,
      "error_count": 0
    }
  ]
}
```

## 配置要求

### 1. API密钥配置
确保在 `config.json` 中配置了以下API密钥：
- Groq API Key
- OpenAI API Key
- Claude API Key
- Gemini API Key

### 2. Cloudflare KV配置
确保配置了KV存储的访问凭证：
- `account_id`
- `namespace_id`
- `api_token`

### 3. 必要文件
- `config.json`: 配置文件
- `长尾词.txt`: 长尾词文件
- `qimai_1_100_pages_20250924_161013.json`: 关键词数据文件

## 输出结构

生成的文章会保存在以下目录结构中：
```
assets/
├── zh-cn/
│   └── [关键词文件夹]/
│       ├── README.md
│       └── images/
│           ├── main_*.jpg
│           └── image_*.jpg
└── zh-tw/
    └── [关键词文件夹]/
        ├── README.md
        └── images/
            ├── main_*.jpg
            └── image_*.jpg
```

## 特性说明

### 1. 多语言支持
- 自动生成简体中文和繁体中文版本
- 支持自动翻译功能
- 语言特定的长尾词处理

### 2. 图片处理
- 自动下载相关图片
- 支持主图和插图
- 图片自动重命名和分类

### 3. SEO优化
- 自动生成相关关键词
- 优化文章结构
- 添加下载链接

### 4. 错误处理
- 完整的错误日志记录
- 自动重试机制
- 详细的错误报告

## 监控和通知

### 1. GitHub Actions
- 自动执行状态监控
- 生成结果统计
- 错误日志收集

### 2. Slack通知
- 任务完成通知
- 错误警报
- 统计信息推送

## 故障排除

### 1. 常见问题
- **API密钥无效**: 检查配置文件中的API密钥
- **KV存储连接失败**: 验证Cloudflare KV配置
- **图片下载失败**: 检查网络连接和bing-image-downloader库

### 2. 调试方法
```bash
# 运行测试脚本
python test_article_generation.py

# 查看错误日志
cat assets/error_log.txt

# 检查配置文件
python -c "from config_manager import ConfigManager; cm = ConfigManager(); print(cm.config)"
```

## 性能优化

### 1. 处理速度
- 使用 `--images false` 跳过图片下载
- 限制处理数量进行测试
- 并行处理多个关键词

### 2. 资源使用
- API密钥轮换使用
- 自动重试和退避
- 错误恢复机制

## 更新日志

- **v1.0**: 初始版本，整合aigen.py功能
- **v1.1**: 添加多语言支持
- **v1.2**: 优化错误处理和重试机制
- **v1.3**: 添加GitHub Actions工作流
