import json
import argparse
from datetime import datetime, timedelta
from kv_manager import kv_read, kv_write
from api_manager import MultiPlatformApiManager
from config_manager import ConfigManager
from article_generator import ArticleGenerator
from publish_manager import PublishManager

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
    # 从今天开始向前查找（使用北京时间）
    from datetime import timezone
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


def test_process_articles():
    """测试方法：使用每日发布模式进行测试"""
    print("🧪 启动测试模式...")
    # 使用每日发布模式，但设置较少的文章数量用于测试
    daily_publish_articles(need_images=False, articles_per_site=2)  # 每个网站只发布2篇文章用于测试

def str_to_bool(v):
    """将字符串转换为布尔值"""
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def daily_publish_articles(need_images=True, articles_per_site=None, max_workers=None, batch_size=None):
    """使用发布管理器执行每日文章发布，支持熔断机制"""
    print("=== 使用发布管理器执行每日文章发布 ===")
    
    # 显示并行配置信息
    if max_workers is not None:
        print(f"🔧 指定并行线程数: {max_workers}")
    if batch_size is not None:
        print(f"🔧 指定批处理大小: {batch_size}")
    
    try:
        # 初始化发布管理器
        publish_manager = PublishManager()
        
        # 执行每日发布
        success = publish_manager.publish_daily_articles(
            need_images=need_images, 
            articles_per_site=articles_per_site,
            max_workers=max_workers,
            batch_size=batch_size
        )
        
        if success:
            print("✅ 每日发布任务完成")
            return True
        else:
            print("❌ 每日发布任务失败")
            return False
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 每日发布异常: {error_msg}")
        
        # 检查是否是API重试超限导致的熔断
        circuit_breaker_keywords = [
            "达到最大重试次数",
            "ApiExhaustedRetriesError", 
            "HTTP错误 500",
            "Internal Server Error",
            "所有重试都失败了",
            "连续失败",
            "熔断机制",
            "API重试耗尽异常",
            "API服务连续失败",
            "🔥",
            "⛔",
            "所有API密钥都失败",
            "重试超过上限"
        ]
        
        is_circuit_breaker = any(keyword in error_msg for keyword in circuit_breaker_keywords)
        
        if is_circuit_breaker:
            print("🔥 检测到API服务异常，触发熔断机制")
            print(f"   错误详情: {error_msg[:200]}...")
            return "circuit_breaker"
        
        # 其他异常直接返回False
        return False

def main():
    """主函数，支持命令行参数 - 默认使用每日发布模式"""
    parser = argparse.ArgumentParser(description='每日文章发布管理器')
    parser.add_argument('--images', type=str_to_bool, default=True, help='是否需要下载图片')
    parser.add_argument('--test', action='store_true', help='测试模式')
    parser.add_argument('--articles-per-site', type=int, help='每个网站发布文章数量')
    parser.add_argument('--max-workers', type=int, help='并行生成线程数 (默认4个)')
    parser.add_argument('--batch-size', type=int, help='批处理大小 (默认4个)')
    
    args = parser.parse_args()
    
    if args.test:
        # 测试模式
        test_process_articles()
    else:
        # 默认使用每日发布模式
        daily_publish_articles(
            need_images=args.images, 
            articles_per_site=args.articles_per_site,
            max_workers=args.max_workers,
            batch_size=args.batch_size
        )

if __name__ == "__main__":
    main()
