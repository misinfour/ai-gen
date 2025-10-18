import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from kv_manager import kv_read, kv_write
from config_manager import ConfigManager
from article_generator import ArticleGenerator
from api_manager import MultiPlatformApiManager, ApiExhaustedRetriesError
from parallel_article_generator import ParallelArticleGenerator

# 定义北京时间时区
beijing_tz = timezone(timedelta(hours=8))

class PublishManager:
    """发布管理器，负责按排名顺序发布文章到不同网站"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = MultiPlatformApiManager(self.config_manager)
        self.article_generator = ArticleGenerator(self.config_manager, self.api_manager)
        
        # 初始化并行文章生成器
        self.parallel_generator = ParallelArticleGenerator(self.config_manager, self.api_manager)
        
        # 获取发布配置
        self.publish_config = self.config_manager.config.get('daily_publish', {})
        self.enabled = self.publish_config.get('enabled', True)
        self.articles_per_site = self.publish_config.get('articles_per_site', 100)
        
        # 动态计算启用的Git仓库数量
        enabled_repos = self.article_generator.repo_manager.get_enabled_repositories()
        git_repos = {k: v for k, v in enabled_repos.items() if v['type'] == 'git'}
        self.total_sites = len(git_repos)
        
        # 如果配置文件中指定了total_sites且大于0，则使用配置文件的值（向后兼容）
        config_total_sites = self.publish_config.get('total_sites', 0)
        if config_total_sites > 0:
            self.total_sites = config_total_sites
            print(f"⚠️  使用配置文件中的total_sites={self.total_sites}，实际启用的Git仓库数量为{len(git_repos)}")
        
        self.start_from_rank = self.publish_config.get('start_from_rank', 1)
        self.max_rank_search = self.publish_config.get('max_rank_search', 10000)
        
        # 获取并行配置
        self.parallel_config = self.publish_config.get('parallel_generation', {})
        self.parallel_enabled = self.parallel_config.get('enabled', True)
        self.batch_size = self.parallel_config.get('batch_size', 4)
        
        # 获取KV存储配置
        kv_config = self.config_manager.config.get('kv_storage', {})
        self.account_id = kv_config.get('account_id')
        self.namespace_id = kv_config.get('namespace_id')
        self.api_token = kv_config.get('api_token')
        
        # 获取仓库配置
        self.repositories = self.config_manager.config.get('repositories', {})
        
        print(f"📋 发布管理器初始化完成")
        print(f"  - 每日发布: {'启用' if self.enabled else '禁用'}")
        print(f"  - 每个网站发布数量: {self.articles_per_site}")
        print(f"  - 总网站数量: {self.total_sites}")
        print(f"  - 开始排名: {self.start_from_rank}")
        print(f"  - 最大搜索排名: {self.max_rank_search}")
        print(f"  - 并行生成: {'启用' if self.parallel_enabled else '禁用'}")
        if self.parallel_enabled:
            print(f"  - 批处理大小: {self.batch_size}")
    
    def find_latest_kv_data(self, max_days_back=30):
        """查找KV存储中最新存在的数据"""
        from datetime import timedelta
        
        current_date = datetime.now(beijing_tz)
        
        for i in range(max_days_back):
            check_date = current_date - timedelta(days=i)
            date_str = check_date.strftime('%Y-%m-%d')
            kv_key = f"qimai_data_{date_str}"
            
            print(f"🔍 检查日期: {date_str} (key: {kv_key})")
            data_str = kv_read(self.account_id, self.namespace_id, self.api_token, kv_key)
            
            if data_str:
                print(f"✅ 找到数据: {date_str}")
                return kv_key, data_str
            else:
                print(f"❌ 未找到数据: {date_str}")
        
        print(f"⚠️ 向前查找了 {max_days_back} 天，未找到任何数据")
        return None, None
    
    def get_keywords_by_rank(self, processed_data):
        """按排名顺序获取关键词列表"""
        keywords_list = []
        
        for page_key, page in processed_data['pages'].items():
            for item in page['wordRankList']:
                # 检查是否有标题且状态为generated
                if ('titles' in item and item['titles'] and 
                    item.get('article_status') == 'generated'):
                    
                    # 获取未使用的标题
                    unused_titles = [title_obj for title_obj in item['titles'] 
                                   if title_obj.get('use_count', 0) == 0]
                    
                    if unused_titles:
                        keywords_list.append({
                            'keyword': item['word'],
                            'rank': item.get('rank', 999999),
                            'titles': unused_titles,
                            'page_key': page_key
                        })
        
        # 按排名排序
        keywords_list.sort(key=lambda x: x['rank'])
        return keywords_list
    
    def get_all_unused_titles_by_rank(self, processed_data):
        """按关键词排名顺序获取所有未使用的标题列表"""
        all_titles = []
        
        for page_key, page in processed_data['pages'].items():
            for item in page['wordRankList']:
                # 检查是否有标题且状态为generated
                if ('titles' in item and item['titles'] and 
                    item.get('article_status') == 'generated'):
                    
                    keyword_rank = item.get('rank', 999999)
                    
                    # 获取未使用的标题
                    unused_titles = [title_obj for title_obj in item['titles'] 
                                   if title_obj.get('use_count', 0) == 0]
                    
                    # 为每个标题添加关键词信息
                    for title_obj in unused_titles:
                        all_titles.append({
                            'title_obj': title_obj,
                            'keyword': item['word'],
                            'keyword_rank': keyword_rank,
                            'page_key': page_key
                        })
        
        # 按关键词排名排序
        all_titles.sort(key=lambda x: x['keyword_rank'])
        return all_titles

    def _count_today_published_by_repo(self, repo_name):
        """从远程仓库统计某个仓库今天已发布的文章数量（按文章文件夹计数）"""
        try:
            # 获取启用的仓库配置
            enabled_repos = self.article_generator.repo_manager.get_enabled_repositories()
            git_repos = {k: v for k, v in enabled_repos.items() if v['type'] == 'git'}
            
            # 查找对应的仓库配置
            target_repo_config = None
            for repo_id, repo_config in git_repos.items():
                if repo_config.get('name') == repo_name:
                    target_repo_config = repo_config
                    break
            
            if not target_repo_config:
                print(f"⚠️ 未找到仓库配置: {repo_name}")
                return 0
            
            # 使用RepositoryManager查询远程仓库文件夹数量
            folder_count = self.article_generator.repo_manager.query_remote_repository_folders(target_repo_config)
            print(f"📊 远程仓库 {repo_name} 今天已发布文章数量: {folder_count}")
            return folder_count
            
        except Exception as e:
            print(f"❌ 查询远程仓库 {repo_name} 失败: {str(e)}")
            return 0

    def _get_today_site_published_counts(self):
        """按网站索引统计今天已发布数量（通过各自仓库名在 logs/backup 下统计）"""
        counts = {}
        try:
            enabled_repos = self.article_generator.repo_manager.get_enabled_repositories()
            # 仅考虑 Git 仓库并按 get_repository_for_site 的排序方式
            git_repos = {k: v for k, v in enabled_repos.items() if v['type'] == 'git'}
            sorted_repos = sorted(git_repos.items())
            for site_index, (repo_id, repo_config) in enumerate(sorted_repos):
                repo_name = repo_config.get('name', str(repo_id))
                counts[site_index] = self._count_today_published_by_repo(repo_name)
        except Exception:
            # 失败则全部置零
            for i in range(self.total_sites):
                counts[i] = 0
        return counts
    
    def determine_target_site(self, rank_index):
        """使用除余方式确定目标网站"""
        # 使用排名索引的除余来确定目标网站
        site_index = rank_index % self.total_sites
        return site_index
    
    def get_repository_for_site(self, site_index):
        """根据网站索引获取对应的仓库配置"""
        enabled_repos = self.article_generator.repo_manager.get_enabled_repositories()
        git_repos = {k: v for k, v in enabled_repos.items() if v['type'] == 'git'}
        
        if not git_repos:
            print("❌ 没有找到启用的Git仓库")
            return None
        
        # 将仓库按ID排序，确保一致性
        sorted_repos = sorted(git_repos.items())
        
        if site_index < len(sorted_repos):
            repo_id, repo_config = sorted_repos[site_index]
            print(f"📁 网站 {site_index} 对应仓库: {repo_config['name']}")
            return repo_id, repo_config
        else:
            print(f"❌ 网站索引 {site_index} 超出范围")
            return None
    
    def publish_daily_articles(self, need_images=True, articles_per_site=None, max_workers=None, batch_size=None):
        """执行每日文章发布 - 支持并行和串行两种模式"""
        if not self.enabled:
            print("❌ 每日发布功能已禁用")
            return False
        
        # 使用传入的参数，如果没有传入则使用配置文件中的默认值
        if articles_per_site is not None:
            actual_articles_per_site = articles_per_site
            print(f"📝 使用工作流指定数量: {articles_per_site}")
        else:
            actual_articles_per_site = self.articles_per_site
            print(f"📝 使用配置文件默认数量: {self.articles_per_site}")
        
        # 处理并行配置参数
        if max_workers is not None:
            print(f"🔧 使用工作流指定线程数: {max_workers}")
        if batch_size is not None:
            print(f"🔧 使用工作流指定批次大小: {batch_size}")
        
        print("=== 开始每日文章发布 ===")
        print(f"🎯 目标: 每个网站发布 {actual_articles_per_site} 篇文章")
        print(f"🌐 总网站数: {self.total_sites}")
        
        # 根据配置选择并行或串行模式
        if self.parallel_enabled:
            print("🚀 使用并行生成模式")
            return self.publish_daily_articles_parallel(need_images, actual_articles_per_site, max_workers, batch_size)
        else:
            print("🔄 使用串行生成模式")
            return self.publish_daily_articles_serial(need_images, actual_articles_per_site)
    
    def publish_daily_articles_parallel(self, need_images=True, articles_per_site=100, max_workers=None, batch_size=None):
        """执行每日文章发布 - 并行版本"""
        # 动态更新并行生成器的配置
        if max_workers is not None:
            self.parallel_generator.max_workers = max_workers
            print(f"🔧 动态设置线程数: {max_workers}")
        
        if batch_size is not None:
            self.parallel_generator.batch_size = batch_size
            self.batch_size = batch_size  # 同时更新PublishManager的batch_size
            print(f"🔧 动态设置批次大小: {batch_size}")
        
        print(f"⚙️ 当前并行配置: {self.parallel_generator.max_workers} 个线程, 批次大小 {self.parallel_generator.batch_size}")
        
        # 查找最新数据
        kv_key, existing_data_str = self.find_latest_kv_data()
        if not existing_data_str:
            print("❌ 未找到任何KV数据")
            return False
        
        processed_data = json.loads(existing_data_str)
        
        # 按排名获取所有未使用的标题，并随机打乱顺序进行发布
        all_titles = self.get_all_unused_titles_by_rank(processed_data)
        import random
        random.shuffle(all_titles)
        print(f"📊 找到 {len(all_titles)} 个可发布的标题（已随机打乱）")
        if not all_titles:
            print("❌ 前500名关键词中没有可发布的未使用标题")
            return False
        
        if len(all_titles) < articles_per_site * self.total_sites:
            print(f"⚠️ 可发布标题数量 ({len(all_titles)}) 少于所需数量 ({articles_per_site * self.total_sites})")
            print("🔄 将继续发布可用的标题")
        
        # 统计信息（从日志目录读取今天已发布数量）
        site_stats = {}
        today_counts = self._get_today_site_published_counts()
        for i in range(self.total_sites):
            already = today_counts.get(i, 0)
            site_stats[i] = {
                'published': already,
                'failed': 0,
                'target': articles_per_site
            }
        print("🗂️ 今日各网站已发布数(来自logs): " + ", ".join([f"site {i}: {site_stats[i]['published']}" for i in range(self.total_sites)]))
        
        # 计算需要发布的总数量
        total_needed = sum(max(0, site_stats[i]['target'] - site_stats[i]['published']) for i in range(self.total_sites))
        if total_needed == 0:
            print("✅ 所有网站均已达到目标发布数量")
            return True
        
        # 选择需要发布的标题
        titles_to_publish = all_titles[:total_needed]
        print(f"📝 将发布 {len(titles_to_publish)} 篇文章")
        
        # 分批并行生成文章
        return self._process_articles_in_batches(titles_to_publish, need_images, kv_key, processed_data, site_stats)
    
    def _process_articles_in_batches(self, titles_to_publish, need_images, kv_key, processed_data, site_stats):
        """分批并行处理文章生成和上传"""
        total_published = 0
        total_failed = 0
        used_titles_today = set()
        circuit_breaker_triggered = False
        
        # 按网站循环处理，而不是按文章总数分批
        while True:
            # 检查是否还有网站需要文章
            available_sites = [i for i in range(self.total_sites) if site_stats[i]['published'] < site_stats[i]['target']]
            if not available_sites:
                print("✅ 所有网站均已达到当日目标")
                break
            
            # 随机选择一个需要文章的网站
            import random
            target_site = random.choice(available_sites)
            
            # 获取目标仓库信息
            repo_info = self.get_repository_for_site(target_site)
            if not repo_info:
                print(f"❌ 无法获取网站 {target_site} 的仓库配置")
                site_stats[target_site]['failed'] += 1
                continue
            
            repo_id, repo_config = repo_info
            
            # 计算该网站还需要多少篇文章
            remaining_articles = site_stats[target_site]['target'] - site_stats[target_site]['published']
            if remaining_articles <= 0:
                print(f"✅ 网站 {target_site} 已达到目标数量")
                continue
            
            # 确定本批次要处理的文章数量（不超过批处理大小和剩余需求）
            batch_size_for_site = min(self.batch_size, remaining_articles)
            
            # 从可用标题中选择本批次要处理的标题
            batch_titles = []
            for title_info in titles_to_publish:
                if len(batch_titles) >= batch_size_for_site:
                    break
                    
                title_text = title_info['title_obj'].get('title', '')
                if title_text not in used_titles_today:
                    batch_titles.append(title_info)
                    used_titles_today.add(title_text)
            
            if not batch_titles:
                print("⏭️ 没有可用的标题")
                break
            
            print(f"\n📦 处理网站 {target_site} ({repo_config['name']}): {len(batch_titles)} 个任务")
            print(f"   目标: {site_stats[target_site]['target']} 篇, 已发布: {site_stats[target_site]['published']} 篇, 剩余: {remaining_articles} 篇")
            
            # 创建并行生成任务
            article_tasks = self.parallel_generator.create_article_tasks(
                batch_titles, 
                need_images, 
                repo_config.get('name'),
                repo_config
            )
            
            print(f"🚀 开始并行生成 {len(article_tasks)} 个文章到网站 {target_site}...")
            
            try:
                # 并行生成文章
                generation_results = self.parallel_generator.generate_articles_parallel(article_tasks)
                
                # 收集成功生成的文章
                successful_articles = []
                failed_count = 0
                
                for result in generation_results:
                    if result['success']:
                        successful_articles.append(result)
                        print(f"   ✅ 文章 #{result['task_id']} 生成成功: {result['keyword']}")
                    else:
                        failed_count += 1
                        print(f"   ❌ 文章 #{result['task_id']} 生成失败: {result.get('error', '未知错误')}")
                        
                        # 检查是否是API重试耗尽错误
                        if result.get('error_type') == 'api_exhausted':
                            print("⛔ 检测到API重试耗尽错误，触发熔断机制")
                            circuit_breaker_triggered = True
                            break
                
                # 如果有成功生成的文章，上传到目标网站
                if successful_articles and not circuit_breaker_triggered:
                    print(f"\n📤 开始上传 {len(successful_articles)} 篇文章到网站 {target_site}...")
                    
                    # 判断是否为该网站的最后一次上传
                    articles_to_publish_count = len(successful_articles)
                    is_final_commit_for_site = (site_stats[target_site]['published'] + articles_to_publish_count >= site_stats[target_site]['target'])
                    
                    if is_final_commit_for_site:
                        print(f"🚀 这是网站 {target_site} 的最后一次提交，将触发自动部署")
                    else:
                        print(f"📝 普通提交到网站 {target_site}，跳过自动部署")
                    
                    # 批量上传所有成功的文章
                    batch_upload_success = self._batch_upload_articles(
                        successful_articles, target_site, repo_id, repo_config, 
                        is_final_commit_for_site, kv_key, processed_data, batch_titles
                    )
                    
                    if batch_upload_success:
                        # 更新统计信息
                        site_stats[target_site]['published'] += len(successful_articles)
                        total_published += len(successful_articles)
                        print(f"✅ 上传成功: {len(successful_articles)} 篇文章已发布到网站 {target_site}")
                        print(f"   网站 {target_site} 进度: {site_stats[target_site]['published']}/{site_stats[target_site]['target']}")
                    else:
                        site_stats[target_site]['failed'] += len(successful_articles)
                        total_failed += len(successful_articles)
                        print(f"❌ 上传失败")
                
                # 更新失败统计
                site_stats[target_site]['failed'] += failed_count
                total_failed += failed_count
                
                # 检查是否触发熔断机制
                if circuit_breaker_triggered:
                    print("⛔ 熔断机制已触发，停止处理")
                    break
                
            except ApiExhaustedRetriesError as e:
                print(f"💥 网站 {target_site} 处理中发生API重试耗尽异常: {str(e)}")
                circuit_breaker_triggered = True
                break
            except Exception as e:
                print(f"❌ 网站 {target_site} 处理异常: {str(e)}")
                site_stats[target_site]['failed'] += len(batch_titles)
                total_failed += len(batch_titles)
                continue
        
        # 检查是否触发了熔断机制
        if circuit_breaker_triggered:
            print("\n🔥 熔断机制已触发，停止文章发布流程")
            # 抛出异常以触发工作流延迟机制
            raise ApiExhaustedRetriesError("🔥 API服务连续失败，触发熔断机制，请稍后重试")
        
        # 输出发布统计
        print("\n=== 按网站分批发布完成 ===")
        print(f"📊 总体统计:")
        print(f"  - 总发布成功: {total_published}")
        print(f"  - 总发布失败: {total_failed}")
        
        print(f"\n📈 各网站统计:")
        for site_index in range(self.total_sites):
            stats = site_stats[site_index]
            repo_info = self.get_repository_for_site(site_index)
            repo_name = repo_info[1]['name'] if repo_info else f"网站{site_index}"
            
            print(f"  - {repo_name}: {stats['published']}/{stats['target']} 成功, {stats['failed']} 失败")
        
        # 检查是否所有网站都达到了目标数量
        all_sites_reached_target = all(site_stats[i]['published'] >= site_stats[i]['target'] for i in range(self.total_sites))
        
        if all_sites_reached_target:
            print("✅ 所有网站均已达到目标发布数量，任务完成")
            return True
        elif total_published > 0:
            print("✅ 部分文章发布成功")
            return True
        else:
            print("❌ 没有文章发布成功")
            return False
    
    def _batch_upload_articles(self, successful_articles, target_site, repo_id, repo_config, 
                              is_final_commit, kv_key, processed_data, valid_titles):
        """批量上传文章到指定网站 - 所有文章一次性提交"""
        try:
            print(f"   📤 准备批量上传 {len(successful_articles)} 篇文章到 {repo_config['name']}")
            
            # 收集所有文章的文件路径，准备批量上传
            all_article_paths = []
            article_infos = []
            
            for result in successful_articles:
                # 收集每篇文章的所有语言版本文件
                for lang_code, lang_result in result['results'].items():
                    if not lang_result['error'] and lang_result['file']:
                        article_path = lang_result['file']
                        all_article_paths.append(article_path)
                        
                        # 准备文章信息
                        article_info = {
                            'title': f'Batch Upload Article #{result["task_id"]}',
                            'keyword': result['keyword'],
                            'game_name': '',
                            'custom_suffix': '',
                            'language': lang_code,
                            'folder_name': Path(article_path).name,
                            'need_images': True,
                            'file_path': article_path,
                            'image_dir': str(Path(article_path) / 'images'),
                            'task_id': result['task_id']
                        }
                        article_infos.append(article_info)
            
            if not all_article_paths:
                print(f"   ❌ 没有有效的文章文件可以上传")
                return False
            
            print(f"   📝 收集到 {len(all_article_paths)} 个文件（包含所有语言版本）")
            
            # 批量上传所有文章文件到指定仓库
            batch_upload_result = self._upload_batch_to_repository(
                all_article_paths, article_infos, repo_id, repo_config, is_final_commit
            )
            
            if batch_upload_result['success']:
                print(f"   ✅ 批量上传成功: {len(successful_articles)} 篇文章已发布到 {repo_config['name']}")
                
                if is_final_commit:
                    print(f"   🚀 已触发自动部署")
                
                # 更新所有文章的标题使用记录
                for result in successful_articles:
                    # 找到对应的标题信息
                    title_info = None
                    for valid_title in valid_titles:
                        if valid_title['title_obj'].get('title', '') in result['keyword']:
                            title_info = valid_title
                            break
                    
                    if title_info:
                        title_obj = title_info['title_obj']
                        title_obj['use_count'] = title_obj.get('use_count', 0) + 1
                        title_obj['last_used_at'] = datetime.now(beijing_tz).isoformat()
                        title_obj['published_to_site'] = target_site
                        title_obj['published_to_repo'] = repo_id
                        title_obj['was_final_commit'] = is_final_commit
                        title_obj['task_id'] = result['task_id']
                        title_obj['batch_upload'] = True  # 标记为批量上传
                        title_obj['batch_size'] = len(successful_articles)  # 记录批次大小
                
                # 保存到KV存储（批量保存一次）
                self.save_to_kv(kv_key, processed_data)
                print(f"   💾 已更新KV存储记录")
                
                return True
            else:
                print(f"   ❌ 批量上传失败: {batch_upload_result.get('error', '未知错误')}")
                return False
            
        except Exception as e:
            print(f"❌ 批量上传异常: {str(e)}")
            return False
    
    def _upload_batch_to_repository(self, all_article_paths, article_infos, repo_id, repo_config, is_final_commit):
        """批量上传多个文章到指定仓库 - 真正的一次性上传"""
        try:
            print(f"   🚀 开始真正的批量上传 {len(all_article_paths)} 个文件到 {repo_config['name']}...")
            
            # 准备批量上传数据
            batch_articles = []
            
            for i, article_path in enumerate(all_article_paths):
                article_info = article_infos[i] if i < len(article_infos) else {}
                
                # 为每个文章文件创建批量上传项
                batch_item = {
                    'path': article_path,
                    'info': {
                        'title': article_info.get('title', f'Article #{article_info.get("task_id", i+1)}'),
                        'keyword': article_info.get('keyword', f'keyword_{i+1}'),
                        'game_name': article_info.get('game_name', ''),
                        'custom_suffix': article_info.get('custom_suffix', ''),
                        'language': article_info.get('language', 'unknown'),
                        'folder_name': Path(article_path).name,
                        'need_images': True,
                        'file_path': article_path,
                        'image_dir': str(Path(article_path) / 'images'),
                        'task_id': article_info.get('task_id', i+1)
                    }
                }
                
                batch_articles.append(batch_item)
                print(f"     📄 准备上传: {Path(article_path).name} (任务#{batch_item['info']['task_id']})")
            
            print(f"   📦 准备一次性提交 {len(batch_articles)} 个文件...")
            
            # 使用仓库管理器的批量上传功能
            upload_result = self.article_generator.repo_manager.upload_to_git_repository(
                source_path=None,  # 批量模式下不需要单个source_path
                repo_config=repo_config,
                article_info={},   # 批量模式下不需要单个article_info
                repo_id=repo_id,
                is_final_commit=is_final_commit,
                batch_articles=batch_articles
            )
            
            if upload_result.get('success', False):
                article_count = len(set(info.get('task_id') for info in article_infos))
                print(f"   ✅ 批量上传成功: {article_count} 篇文章已一次性提交到 {repo_config['name']}")
                if is_final_commit:
                    print(f"   🚀 已触发自动部署")
                else:
                    print(f"   📝 跳过自动部署")
            else:
                print(f"   ❌ 批量上传失败: {upload_result.get('error', '未知错误')}")
            
            return upload_result
                
        except Exception as e:
            return {
                'success': False,
                'error': f'批量上传异常: {str(e)}'
            }
    
    def publish_daily_articles_serial(self, need_images=True, articles_per_site=100):
        """执行每日文章发布 - 串行版本（原有逻辑）"""
        # 查找最新数据
        kv_key, existing_data_str = self.find_latest_kv_data()
        if not existing_data_str:
            print("❌ 未找到任何KV数据")
            return False
        
        processed_data = json.loads(existing_data_str)
        
        # 按排名获取所有未使用的标题，并随机打乱顺序进行发布
        all_titles = self.get_all_unused_titles_by_rank(processed_data)
        import random
        random.shuffle(all_titles)
        print(f"📊 找到 {len(all_titles)} 个可发布的标题（已随机打乱）")
        if not all_titles:
            print("❌ 前500名关键词中没有可发布的未使用标题")
            return False
        
        if len(all_titles) < articles_per_site * self.total_sites:
            print(f"⚠️ 可发布标题数量 ({len(all_titles)}) 少于所需数量 ({articles_per_site * self.total_sites})")
            print("🔄 将继续发布可用的标题")
        
        # 统计信息（从日志目录读取今天已发布数量）
        site_stats = {}
        today_counts = self._get_today_site_published_counts()
        for i in range(self.total_sites):
            already = today_counts.get(i, 0)
            site_stats[i] = {
                'published': already,
                'failed': 0,
                'target': articles_per_site
            }
        print("🗂️ 今日各网站已发布数(来自logs): " + ", ".join([f"site {i}: {site_stats[i]['published']}" for i in range(self.total_sites)]))
        
        total_published = 0
        total_failed = 0
        
        # 确保同一标题不会在多个网站重复发布（本次运行内）
        used_titles_today = set()
        
        # 熔断标志
        circuit_breaker_triggered = False

        # 逐个标题尝试发布（随机分配到有剩余额度的网站）
        for title_index, title_info in enumerate(all_titles):
            # 检查熔断状态
            if circuit_breaker_triggered:
                print("⛔ 熔断机制已触发，停止处理剩余标题")
                break
            # 检查是否已达到目标数量
            if all(site_stats[i]['published'] >= site_stats[i]['target'] for i in range(self.total_sites)):
                print(f"✅ 所有网站已达到目标发布数量")
                break
            
            title_text = title_info['title_obj'].get('title', '')
            # 保证标题在本次运行中不重复到两个平台
            if title_text in used_titles_today:
                continue
            
            # 从尚未达标的网站中随机选择一个
            available_sites = [i for i in range(self.total_sites) if site_stats[i]['published'] < site_stats[i]['target']]
            if not available_sites:
                print("✅ 所有网站均已达到当日目标")
                break
            import random
            target_site = random.choice(available_sites)
            
            # 检查目标网站是否已达到发布数量
            if site_stats[target_site]['published'] >= site_stats[target_site]['target']:
                print(f"⏭️ 网站 {target_site} 已达到目标数量，跳过标题序号 {title_index}")
                continue
            
            # 获取目标仓库
            repo_info = self.get_repository_for_site(target_site)
            if not repo_info:
                print(f"❌ 无法获取网站 {target_site} 的仓库配置")
                continue
            
            repo_id, repo_config = repo_info
            
            # 判断是否为该网站的最后一次上传
            is_final_commit_for_site = (site_stats[target_site]['published'] + 1 == site_stats[target_site]['target'])
            
            print(f"\n📝 发布文章到网站 {target_site} ({repo_config['name']})")
            print(f"   标题序号: {title_index}, 关键词: {title_info['keyword']} (排名: {title_info['keyword_rank']})")
            print(f"   标题: {title_info['title_obj']['title']}")
            print(f"   进度: {site_stats[target_site]['published']}/{site_stats[target_site]['target']}")
            print(f"   部署状态: {'🚀 最后一次提交，将触发自动部署' if is_final_commit_for_site else '📝 普通提交，跳过自动部署'}")
            
            # 使用当前标题
            title_obj = title_info['title_obj']
            
            try:
                
                # 生成文章（只发布到指定仓库）
                result = self.publish_article_to_specific_site(
                    title_obj, repo_id, repo_config, need_images, title_index, is_final_commit_for_site
                )
                
                if result['success']:
                    site_stats[target_site]['published'] += 1
                    total_published += 1
                    used_titles_today.add(title_text)
                    print(f"   ✅ 发布成功")
                    
                    # 更新标题使用记录
                    title_obj['use_count'] = title_obj.get('use_count', 0) + 1
                    title_obj['last_used_at'] = datetime.now(beijing_tz).isoformat()
                    title_obj['published_to_site'] = target_site
                    title_obj['published_to_repo'] = repo_id
                    title_obj['was_final_commit'] = is_final_commit_for_site
                    title_obj['title_index'] = title_index
                    
                    # 保存到KV存储
                    self.save_to_kv(kv_key, processed_data)
                    
                else:
                    site_stats[target_site]['failed'] += 1
                    total_failed += 1
                    print(f"   ❌ 发布失败: {result.get('error', '未知错误')}")
                    
            except ApiExhaustedRetriesError as e:
                site_stats[target_site]['failed'] += 1
                total_failed += 1
                print(f"   💥 达到最大重试次数，提前终止: {str(e)}")
                # 设置熔断标志
                circuit_breaker_triggered = True
                print("⛔ 发布流程提前结束，触发熔断机制")
                print("🔥 熔断机制已触发，停止文章发布流程")
                # 立即跳出循环，不再处理剩余标题
                break
            except Exception as e:
                site_stats[target_site]['failed'] += 1
                total_failed += 1
                print(f"   💥 发布异常: {str(e)}")
        
        # 检查是否触发了熔断机制
        if circuit_breaker_triggered:
            print("\n🔥 熔断机制已触发，停止文章发布流程")
            # 抛出异常以触发工作流延迟机制
            raise ApiExhaustedRetriesError("🔥 API服务连续失败，触发熔断机制，请稍后重试")
        
        # 输出发布统计
        print("\n=== 每日发布完成 ===")
        print(f"📊 总体统计:")
        print(f"  - 总发布成功: {total_published}")
        print(f"  - 总发布失败: {total_failed}")
        
        print(f"\n📈 各网站统计:")
        for site_index in range(self.total_sites):
            stats = site_stats[site_index]
            repo_info = self.get_repository_for_site(site_index)
            repo_name = repo_info[1]['name'] if repo_info else f"网站{site_index}"
            
            print(f"  - {repo_name}: {stats['published']}/{stats['target']} 成功, {stats['failed']} 失败")
        
        # 检查是否所有网站都达到了目标数量
        all_sites_reached_target = all(site_stats[i]['published'] >= site_stats[i]['target'] for i in range(self.total_sites))
        
        if all_sites_reached_target:
            print("✅ 所有网站均已达到目标发布数量，任务完成")
            return True
        elif total_published > 0:
            print("✅ 部分文章发布成功")
            return True
        else:
            print("❌ 没有文章发布成功")
            return False
    
    def publish_article_to_specific_site(self, title_obj, repo_id, repo_config, need_images, rank_index, is_final_commit=False):
        """发布文章到指定网站"""
        try:
            # 构建关键词字符串
            article_title = title_obj.get('title', '')
            custom_suffix = title_obj.get('custom_suffix', '')
            game_name = title_obj.get('game_name', '')
            
            # 使用 sanitize_filename 处理特殊字符，确保标题安全
            article_title = self.article_generator.sanitize_filename(article_title)
            custom_suffix = self.article_generator.sanitize_filename(custom_suffix)
            game_name = self.article_generator.sanitize_filename(game_name)
            
            if custom_suffix and game_name:
                keyword = f"{article_title}----{custom_suffix}----{game_name}"
            elif game_name:
                keyword = f"{article_title}----{game_name}"
            else:
                keyword = article_title
            
            print(f"   正在生成文章: {keyword}")
            
            # 生成文章内容（只生成，不上传到所有仓库），传递仓库名和配置
            results = self.generate_article_content_only(keyword, need_images, repo_config.get('name', repo_id), repo_config)
            
            # 检查生成结果
            success_count = 0
            error_count = 0
            
            for lang_code, result in results.items():
                if result['error']:
                    error_count += 1
                    print(f"     ❌ {lang_code} 版本生成失败: {result['error']}")
                else:
                    success_count += 1
                    print(f"     ✅ {lang_code} 版本生成成功")
            
            if success_count > 0:
                # 上传到指定仓库
                upload_results = self.upload_to_specific_repository(results, repo_id, repo_config, is_final_commit)
                
                return {
                    'success': True,
                    'upload_results': upload_results,
                    'usage_records': []
                }
            else:
                return {
                    'success': False,
                    'error': '所有语言版本生成失败'
                }
                
        except ApiExhaustedRetriesError as e:
            # 重新抛出熔断异常，让上层处理
            raise e
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_article_content_only(self, keyword, need_images=True, repo_name=None, repo_config=None):
        """只生成文章内容，不上传到任何仓库 - 使用翻译模式"""
        results = {}
        primary_content = None
        
        # 获取所有语言代码
        from article_generator import LANGUAGES
        language_codes = list(LANGUAGES.keys())
        
        # 从仓库配置中获取主语言，如果没有配置则使用默认值
        if repo_config and 'primary_language' in repo_config:
            primary_lang = repo_config['primary_language']
            print(f"    使用仓库配置的主语言: {primary_lang}")
        else:
            primary_lang = 'zh-cn'  # 默认主语言
            print(f"    使用默认主语言: {primary_lang}")
        
        # 首先生成主语言版本，获取内容和图片数据
        print(f"    正在生成主语言 {LANGUAGES[primary_lang]} 版本...")
        file_path, error, usage_record, primary_content, shared_image_data = self.article_generator.generate_markdown_for_language_with_content_and_images(
            keyword, need_images, primary_lang, False, repo_name
        )
        
        results[primary_lang] = {
            'file': file_path,
            'error': error,
            'language': LANGUAGES[primary_lang],
            'usage_record': usage_record
        }
        
        if not primary_content or error:
            print(f"    ❌ 主语言版本生成失败，无法继续生成其他语言版本")
            return results
        
        # 为其他语言生成翻译版本
        for lang_code in language_codes:
            if lang_code == primary_lang:
                continue  # 跳过主语言，已经生成了
                
            print(f"    正在生成翻译版本 {LANGUAGES[lang_code]}...")
            
            # 添加延迟避免翻译API限制
            import time
            time.sleep(1)
            
            # 使用共享图片模式生成翻译文章
            file_path, error, usage_record = self.article_generator.generate_translated_markdown_with_shared_images(
                keyword, need_images, lang_code, primary_content, shared_image_data, False, repo_name
            )
            
            results[lang_code] = {
                'file': file_path,
                'error': error,
                'language': LANGUAGES[lang_code],
                'usage_record': usage_record
            }
            
            # 添加延迟避免API限制
            if lang_code != language_codes[-1]:
                time.sleep(1)
        
        return results
    
    def upload_to_specific_repository(self, results, repo_id, repo_config, is_final_commit=False):
        """上传文章到指定仓库（每个语言版本分别上传）"""
        upload_results = []
        
        # 收集所有成功的语言版本
        successful_results = []
        for lang_code, result in results.items():
            if result['error'] or not result['file']:
                continue
            successful_results.append((lang_code, result))
        
        if not successful_results:
            print(f"     ❌ 没有成功的语言版本可以上传")
            return upload_results
        
        if is_final_commit:
            print(f"     📤 上传所有语言版本到 {repo_config['name']} (最后一次提交，将触发自动部署)...")
        else:
            print(f"     📤 上传所有语言版本到 {repo_config['name']} (普通提交，跳过自动部署)...")
        
        # 显示要上传的语言版本
        lang_names = [result['language'] for _, result in successful_results]
        print(f"     📝 包含语言版本: {', '.join(lang_names)}")
        
        # 为每个语言版本分别上传（但使用相同的is_final_commit状态）
        for i, (lang_code, result) in enumerate(successful_results):
            # 只有最后一个语言版本才触发自动部署
            current_is_final_commit = is_final_commit and (i == len(successful_results) - 1)
            
            # 准备文章信息
            article_info = {
                'title': 'Daily Publish Article',
                'keyword': 'Daily Publish',
                'game_name': '',
                'custom_suffix': '',
                'language': lang_code,
                'folder_name': Path(result['file']).name,
                'need_images': True,
                'file_path': result['file'],
                'image_dir': str(Path(result['file']) / 'images')
            }
            
            if current_is_final_commit:
                print(f"     📤 上传 {result['language']} 版本到 {repo_config['name']} (最后一次提交，将触发自动部署)...")
            else:
                print(f"     📤 上传 {result['language']} 版本到 {repo_config['name']} (普通提交，跳过自动部署)...")
            
            # 上传到指定Git仓库
            upload_result = self.article_generator.repo_manager.upload_to_git_repository(
                result['file'], repo_config, article_info, repo_id, current_is_final_commit
            )
            
            upload_results.append(upload_result)
            
            if upload_result['success']:
                if current_is_final_commit:
                    print(f"     ✅ 上传到 {repo_config['name']} 成功 (已触发自动部署)")
                else:
                    print(f"     ✅ 上传到 {repo_config['name']} 成功 (跳过自动部署)")
            else:
                print(f"     ❌ 上传到 {repo_config['name']} 失败: {upload_result['error']}")
        
        return upload_results
    
    def save_to_kv(self, kv_key, processed_data):
        """保存数据到KV存储"""
        try:
            kv_write(self.account_id, self.namespace_id, self.api_token, kv_key, 
                    json.dumps(processed_data, ensure_ascii=False, indent=2))
            print(f"    💾 数据已保存到KV存储")
        except Exception as e:
            print(f"    ❌ 保存到KV存储失败: {str(e)}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='每日文章发布管理器')
    parser.add_argument('--images', type=bool, default=True, help='是否需要下载图片')
    parser.add_argument('--test', action='store_true', help='测试模式')
    
    args = parser.parse_args()
    
    # 初始化发布管理器
    publish_manager = PublishManager()
    
    if args.test:
        print("🧪 启动测试模式...")
        # 测试模式：减少发布数量
        publish_manager.articles_per_site = 2
        publish_manager.total_sites = 2
    
    # 执行每日发布
    success = publish_manager.publish_daily_articles(need_images=args.images)
    
    if success:
        print("✅ 每日发布任务完成")
    else:
        print("❌ 每日发布任务失败")

if __name__ == "__main__":
    main()
