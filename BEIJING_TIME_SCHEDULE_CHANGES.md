# 北京时间调度修改说明

## 修改概述

将项目中的工作流调度从UTC时间改为北京时间，以便更好地适应中国时区的使用需求。

## 修改内容

### 1. 修改 `update_workflow_schedule.py` 脚本

**修改前：**
- 使用UTC时间进行调度计算
- 关键词处理：UTC 17点（北京时间1点）
- 文章生成：UTC 2点（北京时间10点）

**修改后：**
- 使用北京时间进行调度计算，然后转换为UTC时间
- 关键词处理：北京时间0点（UTC 16点）
- 文章生成：北京时间1点（UTC 17点）

**关键代码变更：**
```python
# 使用北京时间计算重试时间
beijing_tz = timezone(timedelta(hours=8))
future_time_beijing = datetime.now(beijing_tz) + timedelta(minutes=delay_minutes)
# 转换为UTC时间用于cron表达式
future_time_utc = future_time_beijing.astimezone(timezone.utc)
```

### 2. 修改文章生成工作流 `.github/workflows/generate-articles.yml`

**修改前：**
```yaml
schedule:
  # 每天早上10点执行 (UTC时间，中国时间18点)
  - cron: '33 5 9 10 *'
```

**修改后：**
```yaml
schedule:
  # 每天北京时间1点执行 (UTC时间17点)
  - cron: '0 17 * * *'
```

### 3. 修改关键词处理工作流 `.github/workflows/process-keywords.yml`

**修改前：**
```yaml
# 定时触发（每周一0点）
# schedule:
# - cron: '27 15 30 9 *'
```

**修改后：**
```yaml
# 定时触发（每天北京时间0点）
schedule:
- cron: '0 16 * * *'
```

## 时间对照表

| 任务类型 | 北京时间 | UTC时间 | Cron表达式 |
|---------|---------|---------|-----------|
| 关键词处理 | 00:00 | 16:00 | `0 16 * * *` |
| 文章生成 | 01:00 | 17:00 | `0 17 * * *` |

## 重试机制

重试机制现在基于北京时间计算：
1. 获取当前北京时间
2. 加上延迟时间（如30分钟）
3. 转换为UTC时间用于cron表达式
4. 确保重试时间准确对应北京时间

## 验证结果

通过测试脚本验证，时间转换逻辑正确：
- 关键词处理：UTC 16:00 = 北京时间 00:00 ✓
- 文章生成：UTC 17:00 = 北京时间 01:00 ✓
- 重试机制：基于北京时间计算，转换为UTC时间 ✓

### 4. 修改所有时间判断逻辑

**修改的文件：**
- `publish_manager.py`：统计今天已发布文章数量时使用北京时间
- `process_articles.py`：查找KV数据时使用北京时间
- `process_keywords.py`：创建日志目录和查找数据时使用北京时间
- `repo_manager.py`：生成目标路径和上传时间时使用北京时间
- `update_workflow_schedule.py`：日志记录时使用北京时间
- `parallel_article_generator.py`：统计信息时使用北京时间
- `article_generator.py`：所有时间相关操作使用北京时间
- `api_manager.py`：API使用统计时使用北京时间
- `.github/workflows/generate-articles.yml`：创建目录时使用北京时间

**关键修改：**
```python
# 修改前
now = datetime.now()

# 修改后
from datetime import timezone, timedelta
beijing_tz = timezone(timedelta(hours=8))
now = datetime.now(beijing_tz)
```

**工作流修改：**
```bash
# 修改前
YEAR=$(date +%Y)

# 修改后
export TZ='Asia/Shanghai'
YEAR=$(date +%Y)
```

## 使用说明

1. **关键词处理**：每天北京时间0点开始处理关键词和标题生成
2. **文章生成**：每天北京时间1点开始生成文章
3. **重试机制**：如果任务失败，会基于北京时间计算重试时间
4. **时间判断**：所有"今天"的判断都基于北京时间，确保一致性

这样的调度安排确保了：
- 关键词处理在每天开始时进行
- 文章生成在关键词处理完成后进行
- 所有时间都基于北京时间，便于理解和维护
- 文章统计和目录创建都使用统一的时间标准
