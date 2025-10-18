import asyncio
import concurrent.futures
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from article_generator import ArticleGenerator, LANGUAGES
from api_manager import ApiExhaustedRetriesError

# 定义北京时间时区
beijing_tz = timezone(timedelta(hours=8))


class ParallelArticleGenerator:
    """并行文章生成器，支持多个文章同时生成"""
    
    def __init__(self, config_manager=None, api_manager=None):
        """初始化并行文章生成器"""
        self.config_manager = config_manager
        self.api_manager = api_manager
        
        # 获取并行配置
        parallel_config = config_manager.config.get('daily_publish', {}).get('parallel_generation', {})
        self.enabled = parallel_config.get('enabled', True)
        self.max_workers = parallel_config.get('max_workers', 4)
        self.batch_size = parallel_config.get('batch_size', 4)
        
        print(f"🚀 并行文章生成器初始化完成")
        print(f"  - 并行生成: {'启用' if self.enabled else '禁用'}")
        print(f"  - 最大工作线程: {self.max_workers}")
        print(f"  - 批处理大小: {self.batch_size}")
        
        # 线程锁，用于保护共享资源
        self._lock = threading.Lock()
        self._generation_stats = {
            'total_started': 0,
            'total_completed': 0,
            'total_failed': 0,
            'start_time': None,
            'end_time': None
        }
    
    def _create_article_generator(self) -> ArticleGenerator:
        """为每个线程创建独立的文章生成器实例"""
        return ArticleGenerator(self.config_manager, self.api_manager, verbose=False)
    
    def _generate_single_article(self, task_info: Dict[str, Any]) -> Dict[str, Any]:
        """生成单个文章的工作函数"""
        thread_id = threading.current_thread().ident
        task_id = task_info['task_id']
        keyword = task_info['keyword']
        need_images = task_info['need_images']
        repo_name = task_info.get('repo_name')
        repo_config = task_info.get('repo_config')
        
        print(f"🔄 [线程{thread_id}] 开始生成文章 #{task_id}: {keyword}")
        
        try:
            # 为每个线程创建独立的文章生成器
            article_generator = self._create_article_generator()
            
            # 更新统计信息
            with self._lock:
                self._generation_stats['total_started'] += 1
            
            # 生成文章内容
            results = self._generate_article_content_only(
                article_generator, keyword, need_images, repo_name, repo_config
            )
            
            # 检查生成结果
            success_count = sum(1 for result in results.values() if not result['error'])
            error_count = len(results) - success_count
            
            # 更新统计信息
            with self._lock:
                self._generation_stats['total_completed'] += 1
            
            print(f"✅ [线程{thread_id}] 文章 #{task_id} 生成完成: {success_count} 成功, {error_count} 失败")
            
            return {
                'task_id': task_id,
                'keyword': keyword,
                'success': success_count > 0,
                'results': results,
                'success_count': success_count,
                'error_count': error_count,
                'thread_id': thread_id
            }
            
        except ApiExhaustedRetriesError as e:
            # API重试耗尽异常，需要特殊处理
            with self._lock:
                self._generation_stats['total_failed'] += 1
            
            print(f"💥 [线程{thread_id}] 文章 #{task_id} API重试耗尽: {str(e)}")
            return {
                'task_id': task_id,
                'keyword': keyword,
                'success': False,
                'error': str(e),
                'error_type': 'api_exhausted',
                'thread_id': thread_id
            }
            
        except Exception as e:
            # 其他异常
            with self._lock:
                self._generation_stats['total_failed'] += 1
            
            print(f"❌ [线程{thread_id}] 文章 #{task_id} 生成失败: {str(e)}")
            return {
                'task_id': task_id,
                'keyword': keyword,
                'success': False,
                'error': str(e),
                'error_type': 'general',
                'thread_id': thread_id
            }
    
    def _generate_article_content_only(self, article_generator: ArticleGenerator, keyword: str, 
                                     need_images: bool = True, repo_name: str = None, 
                                     repo_config: Dict = None) -> Dict[str, Any]:
        """只生成文章内容，不上传到任何仓库 - 使用翻译模式"""
        results = {}
        primary_content = None
        
        # 获取所有语言代码
        language_codes = list(LANGUAGES.keys())
        
        # 从仓库配置中获取主语言，如果没有配置则使用默认值
        if repo_config and 'primary_language' in repo_config:
            primary_lang = repo_config['primary_language']
        else:
            primary_lang = 'zh-cn'  # 默认主语言
        
        # 首先生成主语言版本，获取内容和图片数据
        file_path, error, usage_record, primary_content, shared_image_data = article_generator.generate_markdown_for_language_with_content_and_images(
            keyword, need_images, primary_lang, False, repo_name
        )
        
        results[primary_lang] = {
            'file': file_path,
            'error': error,
            'language': LANGUAGES[primary_lang],
            'usage_record': usage_record
        }
        
        if not primary_content or error:
            return results
        
        # 为其他语言生成翻译版本
        for lang_code in language_codes:
            if lang_code == primary_lang:
                continue  # 跳过主语言，已经生成了
            
            # 添加短暂延迟避免翻译API限制
            time.sleep(0.5)
            
            # 使用共享图片模式生成翻译文章
            file_path, error, usage_record = article_generator.generate_translated_markdown_with_shared_images(
                keyword, need_images, lang_code, primary_content, shared_image_data, False, repo_name
            )
            
            results[lang_code] = {
                'file': file_path,
                'error': error,
                'language': LANGUAGES[lang_code],
                'usage_record': usage_record
            }
        
        return results
    
    def generate_articles_parallel(self, article_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """并行生成多个文章"""
        if not self.enabled:
            print("⚠️ 并行生成功能已禁用，将使用串行模式")
            return self._generate_articles_serial(article_tasks)
        
        if not article_tasks:
            print("⚠️ 没有文章任务需要处理")
            return []
        
        print(f"🚀 开始并行生成 {len(article_tasks)} 个文章任务")
        print(f"📊 配置: {self.max_workers} 个工作线程, 批处理大小 {self.batch_size}")
        
        # 重置统计信息
        with self._lock:
            self._generation_stats = {
                'total_started': 0,
                'total_completed': 0,
                'total_failed': 0,
                'start_time': datetime.now(beijing_tz),
                'end_time': None
            }
        
        all_results = []
        
        # 分批处理任务
        for batch_start in range(0, len(article_tasks), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(article_tasks))
            batch_tasks = article_tasks[batch_start:batch_end]
            
            print(f"\n📦 处理批次 {batch_start//self.batch_size + 1}: 任务 {batch_start+1}-{batch_end}")
            
            # 使用线程池并行处理当前批次
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_task = {
                    executor.submit(self._generate_single_article, task): task 
                    for task in batch_tasks
                }
                
                # 收集结果
                batch_results = []
                completed_count = 0
                
                for future in concurrent.futures.as_completed(future_to_task):
                    task = future_to_task[future]
                    completed_count += 1
                    
                    try:
                        result = future.result()
                        batch_results.append(result)
                        
                        # 检查是否有API重试耗尽的错误
                        if not result['success'] and result.get('error_type') == 'api_exhausted':
                            print(f"⛔ 检测到API重试耗尽错误，停止当前批次的剩余任务")
                            # 取消剩余的未完成任务
                            for remaining_future in future_to_task:
                                if not remaining_future.done():
                                    remaining_future.cancel()
                            break
                            
                    except Exception as e:
                        print(f"❌ 任务执行异常: {str(e)}")
                        batch_results.append({
                            'task_id': task['task_id'],
                            'keyword': task['keyword'],
                            'success': False,
                            'error': str(e),
                            'error_type': 'execution'
                        })
                
                print(f"📊 批次完成: {completed_count}/{len(batch_tasks)} 个任务处理完成")
                all_results.extend(batch_results)
                
                # 检查是否有API重试耗尽的错误，如果有则停止处理后续批次
                api_exhausted = any(
                    not result['success'] and result.get('error_type') == 'api_exhausted' 
                    for result in batch_results
                )
                
                if api_exhausted:
                    print("⛔ 检测到API重试耗尽错误，停止处理后续批次")
                    break
            
            # 批次间添加短暂延迟
            if batch_end < len(article_tasks):
                print("⏳ 等待2秒后处理下一批次...")
                time.sleep(2)
        
        # 更新结束时间
        with self._lock:
            self._generation_stats['end_time'] = datetime.now(beijing_tz)
        
        # 输出最终统计信息
        self._print_generation_stats()
        
        return all_results
    
    def _generate_articles_serial(self, article_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """串行生成文章（作为并行模式的备选方案）"""
        print("🔄 使用串行模式生成文章")
        
        results = []
        for i, task in enumerate(article_tasks):
            print(f"\n📝 处理任务 {i+1}/{len(article_tasks)}: {task['keyword']}")
            result = self._generate_single_article(task)
            results.append(result)
            
            # 检查是否有API重试耗尽的错误
            if not result['success'] and result.get('error_type') == 'api_exhausted':
                print("⛔ 检测到API重试耗尽错误，停止处理剩余任务")
                break
            
            # 任务间添加延迟
            if i < len(article_tasks) - 1:
                time.sleep(1)
        
        return results
    
    def _print_generation_stats(self):
        """打印生成统计信息"""
        with self._lock:
            stats = self._generation_stats.copy()
        
        if stats['start_time'] and stats['end_time']:
            duration = stats['end_time'] - stats['start_time']
            duration_seconds = duration.total_seconds()
        else:
            duration_seconds = 0
        
        print(f"\n📊 并行生成统计信息:")
        print(f"  - 开始任务数: {stats['total_started']}")
        print(f"  - 完成任务数: {stats['total_completed']}")
        print(f"  - 失败任务数: {stats['total_failed']}")
        print(f"  - 总耗时: {duration_seconds:.1f} 秒")
        
        if stats['total_completed'] > 0 and duration_seconds > 0:
            avg_time = duration_seconds / stats['total_completed']
            print(f"  - 平均每篇文章耗时: {avg_time:.1f} 秒")
    
    def create_article_tasks(self, title_infos: List[Dict[str, Any]], need_images: bool = True, 
                           repo_name: str = None, repo_config: Dict = None) -> List[Dict[str, Any]]:
        """创建文章生成任务列表"""
        tasks = []
        
        for i, title_info in enumerate(title_infos):
            # 构建关键词字符串
            title_obj = title_info['title_obj']
            article_title = title_obj.get('title', '')
            custom_suffix = title_obj.get('custom_suffix', '')
            game_name = title_obj.get('game_name', '')
            
            # 使用 ArticleGenerator 的 sanitize_filename 方法处理特殊字符
            # 这里我们创建一个临时实例来使用这个方法
            temp_generator = self._create_article_generator()
            article_title = temp_generator.sanitize_filename(article_title)
            custom_suffix = temp_generator.sanitize_filename(custom_suffix)
            game_name = temp_generator.sanitize_filename(game_name)
            
            if custom_suffix and game_name:
                keyword = f"{article_title}----{custom_suffix}----{game_name}"
            elif game_name:
                keyword = f"{article_title}----{game_name}"
            else:
                keyword = article_title
            
            task = {
                'task_id': i + 1,
                'keyword': keyword,
                'title_info': title_info,
                'need_images': need_images,
                'repo_name': repo_name,
                'repo_config': repo_config
            }
            
            tasks.append(task)
        
        return tasks
