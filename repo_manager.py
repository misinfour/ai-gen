import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
from image_upload_manager import ImageUploadManager

# 定义北京时间时区
beijing_tz = timezone(timedelta(hours=8))

class RepositoryManager:
    """多仓库管理器，负责将文章上传到不同的仓库"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.repositories = config_manager.config.get('repositories', {})
        self.image_upload_manager = ImageUploadManager(config_manager)
        
    def get_enabled_repositories(self):
        """获取所有启用的仓库配置"""
        enabled_repos = {}
        for repo_id, repo_config in self.repositories.items():
            if repo_config.get('enabled', False):
                enabled_repos[repo_id] = repo_config
        return enabled_repos
    
    def generate_target_path(self, repo_config, article_info):
        """根据配置生成目标路径"""
        path_template = repo_config.get('path_template', '{base_path}')
        base_path = repo_config.get('base_path', '')
        
        # 获取当前日期（使用北京时间）
        now = datetime.now(beijing_tz)
        year = now.strftime('%Y')
        month = now.strftime('%m')
        day = now.strftime('%d')
        
        # 语言代码映射
        language_code = article_info.get('language', 'zh-cn')
        language_mapping = repo_config.get('language_mapping', {})
        mapped_language = language_mapping.get(language_code, language_code)
        
        # 获取主语言
        primary_language = repo_config.get('primary_language', 'zh-cn')
        
        # 确定语言路径
        if language_code == primary_language:
            # 主语言不使用语言目录
            language_path = ""
        else:
            # 非主语言使用对应的语言目录
            language_path = mapped_language
        
        # 获取分类
        category = repo_config.get('category', 'articles')
        
        # 获取仓库名称（用于本地临时存储）
        repo_name = repo_config.get('name', 'unknown')
        
        # 替换路径模板中的变量
        target_path = path_template.format(
            base_path=base_path,
            language_code=mapped_language,
            language_path=language_path,
            category=category,
            year=year,
            month=month,
            day=day,
            folder_name=article_info.get('folder_name', 'article'),
            repo_name=repo_name
        )
        
        # 清理路径中的双斜杠
        target_path = target_path.replace('//', '/')
        
        return target_path
    
    def copy_article_without_images(self, source_path, target_path):
        """复制文章文件，但排除images文件夹（因为图片已上传到图床）"""
        try:
            source_path = Path(source_path)
            target_path = Path(target_path)
            
            if source_path.is_file():
                # 如果是单个文件，直接复制
                shutil.copy2(source_path, target_path)
            else:
                # 如果是目录，复制除images文件夹外的所有内容
                for item in source_path.iterdir():
                    if item.name == 'images':
                        # 跳过images文件夹
                        print(f"      📁 跳过images文件夹: {item.name} (图片已上传到图床)")
                        continue
                    
                    target_item = target_path / item.name
                    if item.is_file():
                        shutil.copy2(item, target_item)
                    elif item.is_dir():
                        shutil.copytree(item, target_item, dirs_exist_ok=True)
                        
        except Exception as e:
            print(f"      ❌ 复制文章文件失败: {e}")
            # 如果复制失败，回退到完整复制
            if Path(source_path).is_file():
                shutil.copy2(source_path, target_path)
            else:
                shutil.copytree(source_path, target_path, dirs_exist_ok=True)
    
    def upload_to_local_repository(self, source_path, repo_config, article_info, source_repo_info=None):
        """上传到本地仓库（备份远程仓库内容）"""
        try:
            # 检查是否需要备份远程仓库
            backup_repos = repo_config.get('backup_repos', False)
            
            if backup_repos and source_repo_info:
                # 备份模式：使用源仓库的路径结构
                source_repo_name = source_repo_info.get('name', 'unknown')
                
                # 使用源仓库的路径模板生成备份路径
                source_target_path = self.generate_target_path(source_repo_info, article_info)
                
                # 创建备份目录结构：logs/backup/源仓库名/源仓库路径结构
                backup_base_path = f"{repo_config['base_path']}/backup/{source_repo_name}"
                target_base_path = f"{backup_base_path}/{source_target_path}"
                target_path = Path(target_base_path) / article_info['folder_name']
                
                print(f"    📁 备份到: {target_path}")
                print(f"    📋 源路径: {source_target_path}")
            else:
                # 普通模式：使用原有的路径生成逻辑
                target_base_path = self.generate_target_path(repo_config, article_info)
                target_path = Path(target_base_path) / article_info['folder_name']
            
            # 确保目标目录存在
            target_path.mkdir(parents=True, exist_ok=True)
            
            # 复制文件
            if Path(source_path).is_file():
                shutil.copy2(source_path, target_path)
            else:
                shutil.copytree(source_path, target_path, dirs_exist_ok=True)
            
            return {
                'success': True,
                'repo_id': 'local',
                'repo_name': repo_config['name'],
                'target_path': str(target_path),
                'base_path': target_base_path,
                'backup_mode': backup_repos and source_repo_info is not None,
                'source_repo': source_repo_info.get('name', 'unknown') if source_repo_info else None,
                'upload_time': datetime.now(beijing_tz).isoformat()
            }
        except Exception as e:
            return {
                'success': False,
                'repo_id': 'local',
                'repo_name': repo_config['name'],
                'error': str(e),
                'upload_time': datetime.now(beijing_tz).isoformat()
            }
    
    def upload_to_git_repository(self, source_path, repo_config, article_info, repo_id, is_final_commit=False, batch_articles=None):
        """上传到Git仓库（支持批量上传多篇文章）"""
        try:
            repo_url = repo_config['url']
            branch = repo_config.get('branch', 'main')
            auth_token = repo_config['auth']['token']
            
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                repo_path = temp_path / "repo"
                
                # 克隆仓库
                clone_url = repo_url.replace('https://', f'https://{auth_token}@')
                subprocess.run([
                    'git', 'clone', '--branch', branch, clone_url, str(repo_path)
                ], check=True, capture_output=True)
                
                # 配置Git用户身份
                subprocess.run([
                    'git', 'config', 'user.email', 'ai-generator@github.com'
                ], cwd=repo_path, check=True)
                subprocess.run([
                    'git', 'config', 'user.name', 'Action'
                ], cwd=repo_path, check=True)
                
                uploaded_articles = []
                
                # 如果是批量上传
                if batch_articles:
                    print(f"    📦 批量上传 {len(batch_articles)} 篇文章...")
                    
                    # 先处理所有文章的文件复制，不立即上传图片
                    for batch_item in batch_articles:
                        article_path = batch_item['path']
                        article_data = batch_item['info']
                        
                        # 为每篇文章生成目标路径
                        target_base_path = self.generate_target_path(repo_config, article_data)
                        article_target_path = repo_path / target_base_path / article_data['folder_name']
                        article_target_path.mkdir(parents=True, exist_ok=True)
                        
                        # 复制文章文件（包含images文件夹，图片稍后统一上传）
                        if Path(article_path).is_file():
                            shutil.copy2(article_path, article_target_path)
                        else:
                            shutil.copytree(article_path, article_target_path, dirs_exist_ok=True)
                        
                        uploaded_articles.append({
                            'path': str(article_target_path),
                            'base_path': target_base_path,
                            'folder_name': article_data['folder_name'],
                            'original_path': article_path,
                            'article_data': article_data
                        })
                        
                        print(f"      📄 已添加: {article_data['folder_name']}")
                    
                    # 文章文件复制完成后，统一处理图片上传
                    print(f"    📸 开始统一处理所有文章的图片上传...")
                    for uploaded_article in uploaded_articles:
                        article_path = uploaded_article['original_path']
                        article_data = uploaded_article['article_data']
                        
                        # 处理图片上传到图床（只有最后一次提交才触发自动部署）
                        print(f"      📸 处理文章图片: {article_data['folder_name']}")
                        image_result = self.image_upload_manager.process_article_images(
                            article_path, repo_id, article_data, is_final_commit
                        )
                        
                        if image_result['success'] and image_result.get('uploaded_images'):
                            print(f"      ✅ 图片已上传到图床: {len(image_result['uploaded_images'])} 张")
                            
                            # 更新文章内容中的图片链接
                            markdown_file = Path(uploaded_article['path']) / "README.md"
                            if markdown_file.exists():
                                with open(markdown_file, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                
                                # 替换图片路径为远程URL
                                updated_content = self.image_upload_manager.replace_images_with_remote_urls(
                                    content, image_result['uploaded_images']
                                )
                                
                                # 保存更新后的内容
                                with open(markdown_file, 'w', encoding='utf-8') as f:
                                    f.write(updated_content)
                                
                                print(f"      🔗 已更新文章中的图片链接")
                            
                            # 删除本地images文件夹，因为图片已上传到图床
                            images_dir = Path(uploaded_article['path']) / "images"
                            if images_dir.exists():
                                shutil.rmtree(images_dir)
                                print(f"      🗑️  已删除本地images文件夹")
                                
                        elif image_result['success']:
                            print(f"      ℹ️  文章无图片需要上传")
                        else:
                            print(f"      ⚠️  图片上传失败: {image_result.get('error', '未知错误')}")
                
                else:
                    # 单篇文章上传（修改后的逻辑）
                    target_base_path = self.generate_target_path(repo_config, article_info)
                    article_target_path = repo_path / target_base_path / article_info['folder_name']
                    article_target_path.mkdir(parents=True, exist_ok=True)
                    
                    # 先复制文章文件（包含images文件夹，图片稍后统一上传）
                    if Path(source_path).is_file():
                        shutil.copy2(source_path, article_target_path)
                    else:
                        shutil.copytree(source_path, article_target_path, dirs_exist_ok=True)
                    
                    # 复制其他语言版本文件
                    additional_languages = article_info.get('additional_languages', [])
                    for lang_info in additional_languages:
                        lang_file_path = lang_info['file_path']
                        if Path(lang_file_path).exists():
                            # 为其他语言版本创建子目录
                            lang_dir = article_target_path / lang_info['language']
                            lang_dir.mkdir(parents=True, exist_ok=True)
                            
                            # 复制语言版本文件（包含images文件夹）
                            if Path(lang_file_path).is_file():
                                shutil.copy2(lang_file_path, lang_dir)
                            else:
                                shutil.copytree(lang_file_path, lang_dir, dirs_exist_ok=True)
                    
                    # 文章文件复制完成后，处理图片上传
                    print(f"    📸 处理文章图片: {article_info['folder_name']}")
                    image_result = self.image_upload_manager.process_article_images(
                        source_path, repo_id, article_info, is_final_commit
                    )
                    
                    if image_result['success'] and image_result.get('uploaded_images'):
                        print(f"    ✅ 图片已上传到图床: {len(image_result['uploaded_images'])} 张")
                        
                        # 更新文章内容中的图片链接
                        markdown_file = article_target_path / "README.md"
                        if markdown_file.exists():
                            with open(markdown_file, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            # 替换图片路径为远程URL
                            updated_content = self.image_upload_manager.replace_images_with_remote_urls(
                                content, image_result['uploaded_images']
                            )
                            
                            # 保存更新后的内容
                            with open(markdown_file, 'w', encoding='utf-8') as f:
                                f.write(updated_content)
                            
                            print(f"    🔗 已更新文章中的图片链接")
                        
                        # 删除本地images文件夹，因为图片已上传到图床
                        images_dir = article_target_path / "images"
                        if images_dir.exists():
                            shutil.rmtree(images_dir)
                            print(f"    🗑️  已删除本地images文件夹")
                            
                    elif image_result['success']:
                        print(f"    ℹ️  文章无图片需要上传")
                    else:
                        print(f"    ⚠️  图片上传失败: {image_result.get('error', '未知错误')}")
                    
                    uploaded_articles.append({
                        'path': str(article_target_path),
                        'base_path': target_base_path,
                        'folder_name': article_info['folder_name']
                    })
                
                # 提交更改
                subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
                
                # 检查是否有变更需要提交
                result = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_path, capture_output=True, text=True)
                if not result.stdout.strip():
                    print(f"    ⚠️  没有变更需要提交")
                    return {
                        'success': True,
                        'repo_id': repo_config.get('id', 'unknown'),
                        'repo_name': repo_config['name'],
                        'repo_url': repo_url,
                        'uploaded_articles': uploaded_articles,
                        'upload_time': datetime.now(beijing_tz).isoformat(),
                        'message': '没有变更需要提交'
                    }
                
                # 根据是否为最后一次提交生成不同的提交信息
                if batch_articles:
                    article_count = len(batch_articles)
                    if is_final_commit:
                        commit_message = f"🤖 批量上传 {article_count} 篇文章"
                        print(f"    🚀 批量提交完成，开启自动部署")
                    else:
                        commit_message = f"🤖 批量上传 {article_count} 篇文章 [skip ci]"
                        print(f"    📝 批量提交完成，跳过自动部署")
                else:
                    if is_final_commit:
                        commit_message = "🤖 自动上传文章"
                        print(f"    🚀 最后一次提交，开启自动部署")
                    else:
                        commit_message = "🤖 自动上传文章 [skip ci]"
                        print(f"    📝 普通提交，跳过自动部署")
                
                subprocess.run([
                    'git', 'commit', '-m', commit_message
                ], cwd=repo_path, check=True)
                
                # 推送到远程仓库
                subprocess.run(['git', 'push'], cwd=repo_path, check=True)
                
                # 生成返回结果
                if batch_articles:
                    return {
                        'success': True,
                        'repo_id': repo_id,
                        'repo_name': repo_config['name'],
                        'repo_url': repo_url,
                        'uploaded_articles': uploaded_articles,
                        'batch_size': len(batch_articles),
                        'upload_time': datetime.now(beijing_tz).isoformat()
                    }
                else:
                    # 生成target_url
                    domain = repo_config.get('domain', '')
                    if domain:
                        folder_name = article_info.get('folder_name', '')
                        target_url = f"https://{domain}/{target_base_path}/{folder_name}/"
                    else:
                        target_url = None
                    
                    return {
                        'success': True,
                        'repo_id': repo_id,
                        'repo_name': repo_config['name'],
                        'repo_url': repo_url,
                        'target_path': str(uploaded_articles[0]['path']) if uploaded_articles else '',
                        'base_path': uploaded_articles[0]['base_path'] if uploaded_articles else '',
                        'target_url': target_url,
                        'upload_time': datetime.now(beijing_tz).isoformat()
                    }
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Git命令执行失败: {e.stderr.decode() if e.stderr else str(e)}"
            return {
                'success': False,
                'repo_id': repo_id,  # 使用传入的repo_id
                'repo_name': repo_config['name'],
                'repo_url': repo_config['url'],
                'error': error_msg,
                'upload_time': datetime.now(beijing_tz).isoformat()
            }
        except Exception as e:
            return {
                'success': False,
                'repo_id': repo_id,  # 使用传入的repo_id
                'repo_name': repo_config['name'],
                'repo_url': repo_config['url'],
                'error': str(e),
                'upload_time': datetime.now(beijing_tz).isoformat()
            }
    
    def upload_article_to_all_repositories(self, source_path, article_info, is_final_commit=False):
        """将文章上传到所有启用的仓库"""
        enabled_repos = self.get_enabled_repositories()
        upload_results = []
        
        print(f"📤 开始上传文章到 {len(enabled_repos)} 个仓库...")
        
        # 统计Git仓库数量
        git_repos = [repo for repo in enabled_repos.values() if repo['type'] == 'git']
        if git_repos and is_final_commit:
            print(f"🚀 这是最后一次提交，{len(git_repos)} 个Git仓库将开启自动部署")
        
        for repo_id, repo_config in enabled_repos.items():
            print(f"  📁 上传到 {repo_config['name']} ({repo_config['type']})...")
            
            if repo_config['type'] == 'local':
                # 检查是否有其他Git仓库需要备份
                git_repos = [repo for repo in enabled_repos.values() if repo['type'] == 'git']
                if git_repos:
                    # 如果有Git仓库，本地仓库将作为备份
                    source_repo_info = git_repos[0]  # 使用第一个Git仓库作为源
                    result = self.upload_to_local_repository(source_path, repo_config, article_info, source_repo_info)
                else:
                    # 没有Git仓库时，使用普通模式
                    result = self.upload_to_local_repository(source_path, repo_config, article_info)
            elif repo_config['type'] == 'git':
                result = self.upload_to_git_repository(source_path, repo_config, article_info, repo_id, is_final_commit)
            else:
                result = {
                    'success': False,
                    'repo_id': repo_id,
                    'repo_name': repo_config['name'],
                    'error': f"不支持的仓库类型: {repo_config['type']}",
                    'upload_time': datetime.now(beijing_tz).isoformat()
                }
            
            upload_results.append(result)
            
            if result['success']:
                print(f"    ✅ 上传成功: {result['target_path']}")
            else:
                print(f"    ❌ 上传失败: {result['error']}")
        
        return upload_results
    
    def query_remote_repository_folders(self, repo_config, target_date=None):
        """查询远程仓库指定日期的文件夹数量"""
        try:
            repo_url = repo_config['url']
            branch = repo_config.get('branch', 'main')
            auth_token = repo_config['auth']['token']
            
            # 如果没有指定日期，使用今天
            if target_date is None:
                now = datetime.now(beijing_tz)
                year = now.strftime('%Y')
                month = now.strftime('%m')
                day = now.strftime('%d')
            else:
                year = target_date.strftime('%Y')
                month = target_date.strftime('%m')
                day = target_date.strftime('%d')
            
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                repo_path = temp_path / "repo"
                
                # 克隆仓库
                clone_url = repo_url.replace('https://', f'https://{auth_token}@')
                subprocess.run([
                    'git', 'clone', '--branch', branch, clone_url, str(repo_path)
                ], check=True, capture_output=True)
                
                # 生成目标路径
                base_path = repo_config.get('base_path', '')
                category = repo_config.get('category', 'articles')
                
                # 构建目标路径：base_path/{year}/{month}/{day} 或 base_path/zh-CN/{year}/{month}/{day}
                target_path = Path(repo_path) / base_path
                
                # 查找所有符合日期模式的目录
                day_dirs = []
                for lang_dir in target_path.iterdir():
                    if lang_dir.is_dir():
                        # 检查是否为主语言目录（没有语言前缀）
                        primary_language = repo_config.get('primary_language', 'zh-tw')
                        if lang_dir.name == primary_language or lang_dir.name == '':
                            # 主语言目录
                            day_path = lang_dir / category / year / month / day
                            if day_path.exists():
                                day_dirs.append(day_path)
                        else:
                            # 非主语言目录
                            day_path = lang_dir / category / year / month / day
                            if day_path.exists():
                                day_dirs.append(day_path)
                
                # 收集所有文章标题，去重以避免重复计算多语言版本
                article_titles = set()
                for day_dir in day_dirs:
                    if day_dir.is_dir():
                        # 收集文章目录名称
                        for article_dir in day_dir.iterdir():
                            if article_dir.is_dir():
                                article_titles.add(article_dir.name)
                
                return len(article_titles)
                
        except subprocess.CalledProcessError as e:
            print(f"❌ 查询远程仓库失败: {e.stderr.decode() if e.stderr else str(e)}")
            return 0
        except Exception as e:
            print(f"❌ 查询远程仓库时发生错误: {str(e)}")
            return 0

    def create_usage_record(self, upload_results, article_info):
        """创建使用记录"""
        # 排除本地仓库，只统计远程仓库
        remote_results = [result for result in upload_results if result.get('repo_id') != 'local']
        
        usage_record = {
            'processed_at': datetime.now(beijing_tz).isoformat(),
            'need_images': article_info.get('need_images', True),
            'success': any(result['success'] for result in remote_results),
            'success_count': sum(1 for result in remote_results if result['success']),
            'error_count': sum(1 for result in remote_results if not result['success']),
            'repositories': upload_results  # 包含所有仓库信息（包括本地备份）
        }
        return usage_record
