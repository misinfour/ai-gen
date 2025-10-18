# 每日发布管理功能

## 功能概述

新增的每日发布管理功能可以自动按排名顺序发布文章到不同网站，确保两个网站不会同时发布相同的内容。

## 主要特性

### 1. 智能分配策略
- **按标题序号发布**：按所有标题的顺序（跨关键词）发布文章
- **除余分配**：使用标题序号除余方式确保两个网站不发布相同内容
  - 标题序号0, 2, 4, 6... → 网站0 (5yxy5.com) - 只发布到5yxy5.com
  - 标题序号1, 3, 5, 7... → 网站1 (8kkjj.com) - 只发布到8kkjj.com
- **单网站发布**：每篇文章只发布到一个指定的网站，不会同时发布到两个网站
- **跨关键词分配**：不同关键词的标题会交叉分配到不同网站

### 2. 可配置参数
在 `config.json` 中的 `daily_publish` 配置节：
```json
{
  "daily_publish": {
    "enabled": true,           // 是否启用每日发布
    "articles_per_site": 100, // 每个网站每天发布文章数量（默认值）
    "total_sites": 2,         // 总网站数量
    "start_from_rank": 1,     // 开始排名
    "max_rank_search": 10000  // 最大搜索排名
  }
}
```

**配置优先级**：
- 工作流参数 > 配置文件默认值
- 如果工作流中指定了 `articles_per_site`，使用工作流参数
- 如果工作流中未指定，使用配置文件默认值

### 3. 自动部署控制
- **普通文章**：使用 `[skip ci]` 跳过自动部署
- **最后文章**：自动触发部署
- **独立部署**：每个网站的最后一次提交独立触发部署
  - 5yxy5.com 的第100篇文章触发自动部署
  - 8kkjj.com 的第100篇文章触发自动部署

## 使用方法

### 1. 每日发布模式（推荐）
```bash
# 使用每日发布模式（使用配置文件默认值100）
python process_articles.py --daily-publish

# 指定每个网站发布50篇文章
python process_articles.py --daily-publish --articles-per-site 50

# 指定每个网站发布200篇文章，带图片
python process_articles.py --daily-publish --articles-per-site 200 --images true

# 测试模式：每个网站发布10篇文章
python process_articles.py --daily-publish --articles-per-site 10 --images false
```

### 2. 测试模式
```bash
# 测试发布管理器
python publish_manager.py --test

# 测试功能
python test_publish_manager.py
```

### 3. 手动模式（传统方式）
```bash
# 手动指定处理数量
python process_articles.py --max-count 10 --max-titles 1
```

## GitHub Actions 工作流

### 自动执行
- **定时执行**：每天早上10点（UTC时间）自动运行
- **默认模式**：自动使用每日发布模式
- **手动触发**：支持手动指定参数

### 工作流参数
- `max_process_count`：留空使用每日发布模式
- `max_titles_per_keyword`：留空使用每日发布模式
- `need_images`：是否下载图片（默认true）
- `articles_per_site`：每个网站发布文章数量（留空使用配置文件默认值100）

## 发布流程

### 1. 数据获取
- 自动查找KV存储中最新存在的数据
- 按排名顺序获取可发布的关键词

### 2. 文章分配
- 使用除余算法确定目标网站
- 确保每个网站达到目标发布数量
- **重要**：每篇文章只发布到指定的一个网站

### 3. 文章生成
- 为每个关键词生成多语言版本文章
- 自动下载相关图片
- 生成SEO优化的内容
- **只生成不上传**：先生成所有语言版本，然后只上传到指定网站

### 4. 仓库上传
- 只上传到对应的Git仓库（不会同时上传到两个网站）
- 自动提交和推送
- **智能部署控制**：
  - 前99篇文章：使用 `[skip ci]` 跳过自动部署
  - 第100篇文章：自动触发部署
  - 每个网站独立判断是否为最后一次提交

## 监控和统计

### 发布统计
```
=== 每日发布完成 ===
📊 总体统计:
  - 总发布成功: 200
  - 总发布失败: 0

📈 各网站统计:
  - 5yxy5.com: 100/100 成功, 0 失败
  - 8kkjj.com: 100/100 成功, 0 失败
```

### 错误处理
- 自动记录失败的文章
- 保存到KV存储供后续分析
- 支持重试和恢复

## 配置说明

### 仓库配置
确保 `config.json` 中的仓库配置正确：
```json
{
  "repositories": {
    "repo1": {
      "name": "5yxy5.com",
      "enabled": true,
      "type": "git",
      "url": "https://github.com/guogms/www.5yxy5.com.git",
      "branch": "demo"
    },
    "repo2": {
      "name": "8kkjj.com", 
      "enabled": true,
      "type": "git",
      "url": "https://github.com/guogms/www.8kkjj.com.git",
      "branch": "main"
    }
  }
}
```

### KV存储配置
确保Cloudflare KV存储配置正确：
```json
{
  "kv_storage": {
    "account_id": "your_account_id",
    "namespace_id": "your_namespace_id", 
    "api_token": "your_api_token"
  }
}
```

## 故障排除

### 常见问题

1. **没有找到KV数据**
   - 确保先运行 `process_keywords.py` 生成关键词数据
   - 检查KV存储配置是否正确

2. **仓库上传失败**
   - 检查Git仓库的访问权限
   - 确认仓库URL和分支名称正确

3. **API调用失败**
   - 检查API密钥是否有效
   - 确认网络连接正常

### 调试模式
```bash
# 启用详细日志
python process_articles.py --daily-publish --images true

# 测试少量文章
python publish_manager.py --test
```

## 更新日志

### v1.0.0 (2025-01-25)
- ✅ 新增每日发布管理功能
- ✅ 实现按排名顺序发布
- ✅ 使用除余方式分配文章
- ✅ 支持多网站发布
- ✅ 自动部署控制
- ✅ 完整的错误处理和统计

## 技术支持

如有问题，请检查：
1. 配置文件是否正确
2. API密钥是否有效
3. 网络连接是否正常
4. 仓库权限是否正确

更多详细信息请参考项目文档。
