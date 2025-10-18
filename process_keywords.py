import json
import argparse
import os
import time
from datetime import datetime, timezone, timedelta
from kv_manager import kv_read, kv_write
from api_manager import MultiPlatformApiManager, ApiExhaustedRetriesError
from config_manager import ConfigManager

# 定义北京时间时区
beijing_tz = timezone(timedelta(hours=8))

def extract_all_valid_titles(title_text):
    """从AI生成的多个标题中提取所有有效的标题"""
    if not title_text or not isinstance(title_text, str):
        return [], "标题为空或格式错误"
    
    valid_titles = []
    # 按行分割，处理多个标题的情况
    lines = title_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 去除序号（如 "1. "、"2. " 等）
        import re
        line = re.sub(r'^\d+\.\s*', '', line)
        
        # 检查是否包含两个----分隔符
        parts = line.split('----')
        if len(parts) == 3:
            # 检查每个部分是否为空
            title, custom_tail, game_name = parts
            if title.strip() and custom_tail.strip() and game_name.strip():
                valid_titles.append(line)
    
    if valid_titles:
        return valid_titles, f"找到 {len(valid_titles)} 个有效标题"
    else:
        return [], "没有找到格式正确的标题"

def validate_title_format(title_text):
    """验证标题格式是否符合预期结构：标题----自定义尾词----游戏名"""
    valid_titles, message = extract_all_valid_titles(title_text)
    if valid_titles:
        return True, valid_titles
    else:
        return False, message

def generate_title(prompt, keyword, config_manager, api_manager):
    """使用AI生成文章标题"""
    import time
    
    max_retries = 3
    retry_delay = 5  # 秒
    
    for attempt in range(max_retries):
        try:
            # 准备提示词，替换{GameWord}变量
            actual_prompt = prompt.replace('{GameWord}', keyword)
            
            # 使用多平台API管理器生成内容
            print(f"正在为关键词 '{keyword}' 生成标题... (尝试 {attempt + 1}/{max_retries})")
            content = api_manager.make_request(actual_prompt)
            
            # 清理返回的内容，删除<think>标签
            import re
            cleaned_text = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            cleaned_text = cleaned_text.strip()
            
            # 验证标题格式并提取所有有效标题
            is_valid, valid_titles = validate_title_format(cleaned_text)
            if is_valid:
                print(f"✅ 标题格式验证通过: 找到 {len(valid_titles)} 个有效标题")
                for i, title in enumerate(valid_titles[:3], 1):  # 只显示前3个标题
                    print(f"   {i}. {title}")
                if len(valid_titles) > 3:
                    print(f"   ... 还有 {len(valid_titles) - 3} 个标题")
                return valid_titles
            else:
                print(f"⚠️ 标题格式验证失败: {valid_titles}")
                print(f"   生成的原始内容: {cleaned_text[:200]}...")
                if attempt < max_retries - 1:
                    print(f"   将重试生成...")
                    continue
                else:
                    return f"格式验证失败: {valid_titles}"
            
        except ApiExhaustedRetriesError:
            # API重试耗尽异常直接传递，不进行内部重试
            print(f"🔥 生成标题时API重试耗尽，立即终止: {keyword}")
            raise
        except Exception as e:
            error_msg = str(e)
            print(f"❌ 生成标题失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
            
            # 检查是否是熔断相关的异常
            if any(keyword in error_msg for keyword in ['熔断机制', '连续失败', 'ApiExhaustedRetriesError', '🔥']):
                print(f"🔥 检测到熔断相关异常，立即终止")
                raise e
            
            if attempt < max_retries - 1:
                print(f"⏳ 等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                print(f"💥 所有重试都失败了，跳过关键词 '{keyword}'")
                return f"生成失败: {error_msg}"

def find_latest_kv_data(account_id, namespace_id, api_token, max_days_back=30):
    """查找KV存储中最新存在的数据
    
    Args:
        account_id: Cloudflare账户ID
        namespace_id: KV命名空间ID
        api_token: API令牌
        max_days_back: 最多向前查找多少天
    
    Returns:
        tuple: (kv_key, data_str) 或 (None, None)
    """
    from datetime import timedelta, timezone
    
    # 从今天开始向前查找（使用北京时间）
    beijing_tz = timezone(timedelta(hours=8))
    current_date = datetime.now(beijing_tz)
    
    for i in range(max_days_back):
        check_date = current_date - timedelta(days=i)
        date_str = check_date.strftime('%Y-%m-%d')
        kv_key = f"qimai_data_{date_str}"
        
        print(f"🔍 检查日期: {date_str} (key: {kv_key})")
        data_str = kv_read(account_id, namespace_id, api_token, kv_key)
        
        if data_str:
            print(f"✅ 找到数据: {date_str}")
            return kv_key, data_str
        else:
            print(f"❌ 未找到数据: {date_str}")
    
    print(f"⚠️ 向前查找了 {max_days_back} 天，未找到任何数据")
    return None, None

def setup_log_directory():
    """创建日志目录结构，返回日志目录路径"""
    from datetime import timezone
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    log_dir = os.path.join(
        'logs',
        str(now.year),
        f"{now.month:02d}",
        f"{now.day:02d}",
        f"{now.year}{now.month:02d}{now.day:02d}_{now.hour:02d}{now.minute:02d}{now.second:02d}"
    )
    
    # 确保目录存在
    os.makedirs(log_dir, exist_ok=True)
    print(f"📁 创建日志目录: {log_dir}")
    
    return log_dir

def get_current_progress():
    """获取当前处理进度"""
    checkpoint_file = os.path.join('logs', 'process_keywords_checkpoint.json')
    
    try:
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
                print(f"📊 已加载处理进度: {len(checkpoint_data.get('processed_keywords', []))} 个关键词")
                return checkpoint_data
        else:
            print("⚠️ 未找到处理进度文件，将从头开始处理")
            return {"processed_keywords": [], "timestamp": datetime.now(beijing_tz).isoformat()}
    except Exception as e:
        print(f"⚠️ 读取处理进度文件失败: {str(e)}，将从头开始处理")
        return {"processed_keywords": [], "timestamp": datetime.now(beijing_tz).isoformat()}

def update_progress(processed_keywords, log_dir):
    """更新处理进度"""
    checkpoint_file = os.path.join('logs', 'process_keywords_checkpoint.json')
    checkpoint_data = {
        "processed_keywords": processed_keywords,
        "timestamp": datetime.now(beijing_tz).isoformat()
    }
    
    # 更新主进度文件
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
    
    # 同时保存到当前日志目录
    with open(os.path.join(log_dir, 'keywords_progress.json'), 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 已更新处理进度: {len(processed_keywords)} 个关键词")

def process_keywords(max_process_count=None, max_rank_count=None, force_restart=False):
    """处理关键词数据，为每个关键词生成文章标题
    
    Args:
        max_process_count: 最大处理数量，None表示处理所有关键词
        max_rank_count: 最大排行数量，None表示处理所有排行
        force_restart: 是否强制重新开始处理
    """
    # 添加连续失败计数器和熔断机制
    consecutive_failures = 0
    max_consecutive_failures = 5  # 连续失败5次后熔断（与ArticleGenerator保持一致）
    
    # 添加KV保存失败计数器
    kv_save_failures = 0
    max_kv_save_failures = 5  # KV保存连续失败5次后停止
    print("=== 开始处理关键词数据 ===")
    
    # 创建日志目录
    log_dir = setup_log_directory()
    
    # 记录处理详情
    keywords_details = {
        "start_time": datetime.now(beijing_tz).isoformat(),
        "max_process_count": max_process_count,
        "max_rank_count": max_rank_count,
        "force_restart": force_restart,
        "keywords": []
    }
    
    if max_process_count:
        print(f"🔢 关键词限制模式：最多处理 {max_process_count} 个关键词")
    else:
        print("🚀 关键词正式模式：处理所有关键词")
    
    if max_rank_count:
        print(f"📊 排行限制模式：最多处理前 {max_rank_count} 名")
    else:
        print("📊 排行正式模式：处理所有排行")
    
    if force_restart:
        print("🔄 强制重新开始处理模式")
    
    # 初始化配置和API管理器
    config_manager = ConfigManager()
    api_manager = MultiPlatformApiManager(config_manager)
    
    # 设置默认平台（使用配置中的默认平台）
    default_platform = config_manager.config.get("default_platform", "groq")
    api_manager.set_platform(default_platform)
    print(f"使用AI平台: {default_platform}")
    
    # 从配置文件获取Cloudflare KV 凭证
    kv_config = config_manager.config.get('kv_storage', {})
    ACCOUNT_ID = kv_config.get('account_id')
    NAMESPACE_ID = kv_config.get('namespace_id')
    API_TOKEN = kv_config.get('api_token')
    
    if not all([ACCOUNT_ID, NAMESPACE_ID, API_TOKEN]):
        print("❌ KV存储配置不完整，请检查config.json中的kv_storage配置")
        return False
    
    # 获取关键词处理配置
    keyword_config = config_manager.config.get('keyword_processing', {})
    default_max_rank = keyword_config.get('default_max_rank_count', 1000)
    kv_search_days = keyword_config.get('kv_search_days_back', 30)
    
    # 如果没有设置max_rank_count，使用默认值
    if max_rank_count is None:
        max_rank_count = default_max_rank
        print(f"📊 使用默认排行数量限制: {max_rank_count}")
    
    # 查找最新存在的数据（从远程获取所有关键词）
    print("正在从远程查找KV存储中最新存在的数据...")
    kv_key, existing_data_str = find_latest_kv_data(ACCOUNT_ID, NAMESPACE_ID, API_TOKEN, kv_search_days)
    
    if existing_data_str:
        print(f"✅ 找到最新数据，继续处理... (key: {kv_key})")
        processed_data = json.loads(existing_data_str)
    else:
        print("📁 未找到任何KV数据，从JSON文件加载初始数据...")
        with open('qimai_1_100_pages_20250924_161013.json', 'r', encoding='utf-8') as f:
            processed_data = json.load(f)
    
    # 获取当前已处理的关键词列表
    if force_restart:
        print("🔄 强制重新开始，忽略已处理进度")
        current_progress = {"processed_keywords": []}
    else:
        current_progress = get_current_progress()
    
    processed_keywords = current_progress.get("processed_keywords", [])
    
    # 获取zh-tw的标题生成提示词
    title_prompt = config_manager.config['google_seo_article_title_prompt']['zh-tw']['template']
    
    # 统计信息
    total_keywords = 0
    success_count = 0  # 成功处理的关键词数量
    skipped_count = 0
    failed_count = 0
    processed_count = 0  # 已处理的关键词总数（包括跳过、成功、失败）
    processed_ranks = 0  # 已处理的排行数量
    
    # 计算总关键词数，用于显示进度
    all_keywords = []
    for page_key, page in processed_data['pages'].items():
        for item in page['wordRankList']:
            if 'word' in item:
                all_keywords.append(item['word'])
    
    print(f"✅ 远程共获取到 {len(all_keywords)} 个关键词")
    
    # 如果已达到最大处理数量，则直接返回
    if not force_restart and max_process_count and len(processed_keywords) >= max_process_count:
        print(f"🛑 已达到最大关键词处理数量限制 ({max_process_count})，无需处理")
        print(f"   当前已处理关键词数: {len(processed_keywords)}")
        
        # 记录处理结果
        keywords_details["end_time"] = datetime.now(beijing_tz).isoformat()
        keywords_details["status"] = "skipped"
        keywords_details["message"] = f"已达到最大处理数量 ({max_process_count})，无需处理"
        keywords_details["stats"] = {
            "total_keywords": 0,
            "processed_ranks": 0,
            "processed_count": len(processed_keywords),
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": len(processed_keywords)
        }
        
        # 保存处理详情到日志目录
        with open(os.path.join(log_dir, 'keywords_details.json'), 'w', encoding='utf-8') as f:
            json.dump(keywords_details, f, ensure_ascii=False, indent=2)
        
        return True
    
    # 遍历所有页面和关键词
    print("\n开始处理关键词...")
    for page_key, page in processed_data['pages'].items():
        print(f"\n处理页面: {page_key}")
        
        for item in page['wordRankList']:
            # 检查是否已经达到最大处理数量（如果设置了限制）
            if max_process_count and processed_count >= max_process_count:
                print(f"🛑 已达到最大关键词处理数量限制 ({max_process_count})，停止处理")
                break
            
            # 检查是否已经达到最大排行数量（如果设置了限制）
            if max_rank_count and processed_ranks >= max_rank_count:
                print(f"🛑 已达到最大排行数量限制 ({max_rank_count})，停止处理")
                break
            
            total_keywords += 1
            processed_ranks += 1
            
            # 获取关键词
            keyword = item['word']
            rank = item.get('rank', 'N/A')
            
            # 检查是否已经处理过（除非强制重新开始）
            if not force_restart and keyword in processed_keywords:
                skipped_count += 1
                processed_count += 1  # 跳过也要计入总处理数量
                print(f"  [跳过] 关键词 '{keyword}' 已处理过")
                
                # 更新关键词详情
                keyword_detail["status"] = "skipped"
                keyword_detail["reason"] = "已处理过"
                keyword_detail["end_time"] = datetime.now(beijing_tz).isoformat()
                keywords_details["keywords"].append(keyword_detail)
                continue
            
            # 创建关键词详情记录
            keyword_detail = {
                "keyword": keyword,
                "rank": rank,
                "start_time": datetime.now(beijing_tz).isoformat()
            }
            
            # 显示处理进度（使用processed_count + 1表示即将处理的序号）
            if max_process_count and max_rank_count:
                print(f"  [{processed_count + 1}/{max_process_count}] 排行[{processed_ranks}/{max_rank_count}] 处理关键词: {keyword} (排行: {rank})")
            elif max_process_count:
                print(f"  [{processed_count + 1}/{max_process_count}] 处理关键词: {keyword} (排行: {rank})")
            elif max_rank_count:
                print(f"  [{processed_count + 1}] 排行[{processed_ranks}/{max_rank_count}] 处理关键词: {keyword} (排行: {rank})")
            else:
                print(f"  [{processed_count + 1}] 处理关键词: {keyword} (排行: {rank})")
            
            # 检查是否需要生成标题
            need_generation = force_restart or 'titles' not in item or not item['titles']
            
            if need_generation:
                try:
                    # 生成文章标题
                    generated_titles = generate_title(title_prompt, keyword, config_manager, api_manager)
                    
                    # 检查生成的标题是否有效
                    if isinstance(generated_titles, str) and (generated_titles.startswith("生成失败") or generated_titles.startswith("格式验证失败")):
                        print(f"  ❌ 关键词 '{keyword}' 处理失败: {generated_titles}")
                        consecutive_failures += 1
                        print(f"  📊 连续失败计数器更新: {consecutive_failures}/{max_consecutive_failures}")
                        
                        # 检查熔断条件
                        if consecutive_failures >= max_consecutive_failures:
                            print(f"🔥 连续失败 {consecutive_failures} 次，触发熔断机制，停止处理")
                            
                            # 保存当前状态并退出
                            keywords_details["circuit_breaker_triggered"] = True
                            keywords_details["consecutive_failures"] = consecutive_failures
                            keywords_details["end_time"] = datetime.now(beijing_tz).isoformat()
                            keywords_details["status"] = "circuit_breaker"
                            keywords_details["message"] = f"连续失败{consecutive_failures}次，触发熔断机制"
                            
                            # 保存处理详情
                            with open(os.path.join(log_dir, 'keywords_details.json'), 'w', encoding='utf-8') as f:
                                json.dump(keywords_details, f, ensure_ascii=False, indent=2)
                            
                            # 返回字符串表示熔断状态
                            return "circuit_breaker"
                        
                        # 即使失败也要保存状态
                        item['titles'] = []  # 空标题列表
                        item['article_status'] = 'failed'
                        item['error_message'] = generated_titles
                        item['created_at'] = datetime.now(beijing_tz).isoformat()
                        
                        failed_count += 1
                        processed_count += 1  # 失败处理也要计入总处理数量
                        
                        # 更新关键词详情
                        keyword_detail["status"] = "failed"
                        keyword_detail["error"] = generated_titles
                    else:
                        print(f"  ✅ 关键词 '{keyword}' 处理成功，生成了 {len(generated_titles)} 个标题")
                        # 只在确实成功时才重置连续失败计数器
                        if consecutive_failures > 0:
                            print(f"  🔄 重置连续失败计数器: {consecutive_failures} -> 0")
                            consecutive_failures = 0
                        else:
                            print(f"  📊 连续失败计数器保持: {consecutive_failures}")
                        
                        # 创建标题对象列表
                        title_objects = []
                        for title_line in generated_titles:
                            # 解析标题行：文章标题----文章自定义尾词----游戏名称
                            parts = title_line.split('----')
                            if len(parts) == 3:
                                article_title, custom_suffix, game_name = parts
                                
                                # 创建标题对象
                                title_obj = {
                                    "title": article_title.strip(),
                                    "custom_suffix": custom_suffix.strip(),
                                    "game_name": game_name.strip(),
                                    "created_at": datetime.now(beijing_tz).isoformat(),
                                    "last_used_at": None,  # 上次使用时间
                                    "use_count": 0,  # 使用次数
                                    "usage_records": []  # 使用记录对象列表
                                }
                                title_objects.append(title_obj)
                        
                        # 添加新字段到关键词对象
                        item['titles'] = title_objects  # 保存标题对象列表
                        item['article_status'] = 'generated'  # 关键词整体状态
                        item['created_at'] = datetime.now(beijing_tz).isoformat()  # 创建时间
                        success_count += 1  # 只有成功处理才计数
                        processed_count += 1  # 成功处理也要计入总处理数量
                        
                        # 更新关键词详情
                        keyword_detail["status"] = "success"
                        keyword_detail["titles_count"] = len(title_objects)
                        
                        # 更新已处理关键词列表
                        if keyword not in processed_keywords:
                            processed_keywords.append(keyword)
                            # 每处理成功一个关键词就更新进度
                            update_progress(processed_keywords, log_dir)
                    
                    # 每个关键词处理完成后立即保存到KV存储
                    print(f"  💾 立即保存到KV存储...")
                    try:
                        kv_write(ACCOUNT_ID, NAMESPACE_ID, API_TOKEN, kv_key, 
                                json.dumps(processed_data, ensure_ascii=False, indent=2))
                        print(f"  ✅ 保存完成")
                        kv_save_failures = 0  # 成功保存后重置失败计数
                    except Exception as kv_error:
                        kv_save_failures += 1
                        print(f"  ❌ KV存储保存失败 (第{kv_save_failures}次): {str(kv_error)}")
                        
                        if kv_save_failures >= max_kv_save_failures:
                            print(f"💥 KV存储连续失败 {kv_save_failures} 次，停止处理以避免数据丢失")
                            
                            # 保存错误状态并退出
                            keywords_details["kv_save_failures"] = kv_save_failures
                            keywords_details["end_time"] = datetime.now(beijing_tz).isoformat()
                            keywords_details["status"] = "kv_save_failure"
                            keywords_details["message"] = f"KV存储连续失败{kv_save_failures}次"
                            
                            # 保存处理详情
                            with open(os.path.join(log_dir, 'keywords_details.json'), 'w', encoding='utf-8') as f:
                                json.dump(keywords_details, f, ensure_ascii=False, indent=2)
                            
                            return False
                    
                except ApiExhaustedRetriesError as e:
                    print(f"  🔥 关键词 '{keyword}' API重试耗尽，立即触发熔断机制")
                    
                    # 保存当前状态并退出
                    keywords_details["circuit_breaker_triggered"] = True
                    keywords_details["consecutive_failures"] = consecutive_failures + 1
                    keywords_details["end_time"] = datetime.now(beijing_tz).isoformat()
                    keywords_details["status"] = "circuit_breaker"
                    keywords_details["message"] = f"API重试耗尽异常，立即触发熔断机制: {str(e)}"
                    
                    # 保存处理详情
                    with open(os.path.join(log_dir, 'keywords_details.json'), 'w', encoding='utf-8') as f:
                        json.dump(keywords_details, f, ensure_ascii=False, indent=2)
                    
                    return "circuit_breaker"
                except Exception as e:
                    # 检查是否是其他熔断相关异常
                    if any(keyword in str(e) for keyword in ['熔断机制', '连续失败', '🔥']):
                        print(f"  🔥 关键词 '{keyword}' 触发熔断机制")
                        
                        # 保存当前状态并退出
                        keywords_details["circuit_breaker_triggered"] = True
                        keywords_details["consecutive_failures"] = consecutive_failures + 1
                        keywords_details["end_time"] = datetime.now(beijing_tz).isoformat()
                        keywords_details["status"] = "circuit_breaker"
                        keywords_details["message"] = f"API重试耗尽异常，立即触发熔断机制: {str(e)}"
                        
                        # 保存处理详情
                        with open(os.path.join(log_dir, 'keywords_details.json'), 'w', encoding='utf-8') as f:
                            json.dump(keywords_details, f, ensure_ascii=False, indent=2)
                        
                        return "circuit_breaker"
                    
                    print(f"  💥 关键词 '{keyword}' 接口报错: {str(e)}")
                    consecutive_failures += 1
                    print(f"  📊 连续失败计数器更新: {consecutive_failures}/{max_consecutive_failures}")
                    
                    # 检查熔断条件
                    if consecutive_failures >= max_consecutive_failures:
                        print(f"🔥 连续失败 {consecutive_failures} 次，触发熔断机制，停止处理")
                        
                        # 保存当前状态并退出
                        keywords_details["circuit_breaker_triggered"] = True
                        keywords_details["consecutive_failures"] = consecutive_failures
                        keywords_details["end_time"] = datetime.now(beijing_tz).isoformat()
                        keywords_details["status"] = "circuit_breaker"
                        keywords_details["message"] = f"接口异常连续失败{consecutive_failures}次，触发熔断机制"
                        
                        # 保存处理详情
                        with open(os.path.join(log_dir, 'keywords_details.json'), 'w', encoding='utf-8') as f:
                            json.dump(keywords_details, f, ensure_ascii=False, indent=2)
                        
                        return "circuit_breaker"
                    
                    failed_count += 1
                    processed_count += 1  # 异常处理也要计入总处理数量
                    # 保存错误状态
                    item['titles'] = []
                    item['article_status'] = 'failed'
                    item['error_message'] = f"接口报错: {str(e)}"
                    item['created_at'] = datetime.now(beijing_tz).isoformat()
                    
                    # 更新关键词详情
                    keyword_detail["status"] = "error"
                    keyword_detail["error"] = str(e)
                    
                    # 保存到KV存储
                    try:
                        kv_write(ACCOUNT_ID, NAMESPACE_ID, API_TOKEN, kv_key, 
                                json.dumps(processed_data, ensure_ascii=False, indent=2))
                        kv_save_failures = 0  # 成功保存后重置失败计数
                    except Exception as save_error:
                        kv_save_failures += 1
                        print(f"  ❌ KV存储保存失败 (第{kv_save_failures}次): {str(save_error)}")
                        
                        # 更新关键词详情
                        keyword_detail["kv_save_error"] = str(save_error)
                        
                        if kv_save_failures >= max_kv_save_failures:
                            print(f"💥 KV存储连续失败 {kv_save_failures} 次，停止处理")
                            
                            # 保存错误状态并退出
                            keywords_details["kv_save_failures"] = kv_save_failures
                            keywords_details["end_time"] = datetime.now(beijing_tz).isoformat()
                            keywords_details["status"] = "kv_save_failure"
                            keywords_details["message"] = f"KV存储连续失败{kv_save_failures}次"
                            
                            # 保存处理详情
                            with open(os.path.join(log_dir, 'keywords_details.json'), 'w', encoding='utf-8') as f:
                                json.dump(keywords_details, f, ensure_ascii=False, indent=2)
                            
                            return False
            else:
                skipped_count += 1
                processed_count += 1  # 跳过已有标题也要计入总处理数量
                print(f"  [跳过] 关键词 '{keyword}' 已有标题")
                
                # 更新关键词详情
                keyword_detail["status"] = "skipped"
                keyword_detail["reason"] = "已有标题"
            
            # 完成处理时间
            keyword_detail["end_time"] = datetime.now(beijing_tz).isoformat()
            keywords_details["keywords"].append(keyword_detail)
        
        # 如果已达到最大处理数量，跳出外层循环（如果设置了限制）
        if max_process_count and processed_count >= max_process_count:
            break
        
        # 如果已达到最大排行数量，跳出外层循环（如果设置了限制）
        if max_rank_count and processed_ranks >= max_rank_count:
            break
    
    # 输出处理结果统计
    print("\n=== 处理完成 ===")
    print(f"总关键词数: {total_keywords}")
    print(f"已处理排行数: {processed_ranks}")
    print(f"总处理关键词数: {processed_count} (包括成功、失败、跳过)")
    print(f"成功处理关键词: {success_count}")
    print(f"处理失败关键词: {failed_count}")
    print(f"跳过关键词: {skipped_count}")
    if kv_key:
        print(f"数据已保存到KV存储 (key: {kv_key})")
    else:
        print("数据未保存到KV存储（使用本地JSON文件）")
    
    # 显示API使用统计
    api_manager.show_usage_stats()
    
    # 更新处理详情
    keywords_details["end_time"] = datetime.now(beijing_tz).isoformat()
    keywords_details["stats"] = {
        "total_keywords": total_keywords,
        "processed_ranks": processed_ranks,
        "processed_count": processed_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count
    }
    
    # 保存处理详情到日志目录
    with open(os.path.join(log_dir, 'keywords_details.json'), 'w', encoding='utf-8') as f:
        json.dump(keywords_details, f, ensure_ascii=False, indent=2)
    
    # 返回处理结果
    if success_count > 0 or skipped_count > 0:
        print(f"✅ 处理成功：成功处理了 {success_count} 个关键词，跳过了 {skipped_count} 个关键词")
        return True
    else:
        print("❌ 处理失败：没有成功处理任何关键词")
        return False

def test_process_keywords():
    """测试方法：处理少量关键词用于测试"""
    print("🧪 启动测试模式...")
    process_keywords(max_process_count=3, max_rank_count=5)  # 只处理3个关键词，前5名进行测试

def main():
    """主函数，支持命令行参数"""
    parser = argparse.ArgumentParser(description='处理关键词数据，为每个关键词生成文章标题')
    parser.add_argument('--max-count', type=int, help='最大处理关键词数量')
    parser.add_argument('--max-rank', type=int, help='最大处理排行数量（前N名）')
    parser.add_argument('--force-restart', action='store_true', help='强制重新开始处理')
    parser.add_argument('--test', action='store_true', help='测试模式')
    
    args = parser.parse_args()
    
    if args.test:
        test_process_keywords()
    else:
        process_keywords(max_process_count=args.max_count, max_rank_count=args.max_rank, force_restart=args.force_restart)

if __name__ == "__main__":
    main()