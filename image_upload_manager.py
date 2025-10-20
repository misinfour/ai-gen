import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
from urllib.parse import urlsplit, urlunsplit, quote, parse_qsl, urlencode

# 定义北京时间时区
beijing_tz = timezone(timedelta(hours=8))

class ImageUploadManager:
    """图片上传管理器，负责将图片上传到图床仓库并返回远程URL"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.repositories = config_manager.config.get('repositories', {})
    
    def _sanitize_url(self, url: str) -> str:
        """对URL进行编码，避免Markdown解析问题（空格、括号等）。"""
        try:
            parts = urlsplit(url)
            # 编码路径，保留斜杠和常见安全字符
            safe_path = quote(parts.path, safe="/@:_-.~%")
            # 编码查询参数
            if parts.query:
                query_pairs = parse_qsl(parts.query, keep_blank_values=True)
                safe_query = urlencode(query_pairs, doseq=True)
            else:
                safe_query = ""
            # 片段不做特殊处理
            return urlunsplit((parts.scheme, parts.netloc, safe_path, safe_query, parts.fragment))
        except Exception:
            return url
        
    def get_image_repo_config(self, repo_id):
        """获取指定仓库的图床配置"""
        repo_config = self.repositories.get(repo_id)
        if not repo_config:
            return None
        
        image_repo = repo_config.get('image_repo')
        if not image_repo or not image_repo.get('enabled', False):
            return None
            
        return image_repo
    
    def generate_image_target_path(self, image_repo_config, article_info):
        """生成图片在图床仓库中的目标路径"""
        path_template = image_repo_config.get('path_template', '{base_path}')
        base_path = image_repo_config.get('base_path', '')
        
        # 获取当前日期（使用北京时间）
        now = datetime.now(beijing_tz)
        year = now.strftime('%Y')
        month = now.strftime('%m')
        day = now.strftime('%d')
        
        # 获取游戏标题，从folder_name中提取
        folder_name = article_info.get('folder_name', 'article')
        game_title = folder_name  # 使用文章文件夹名称作为游戏标题
        
        # 替换路径模板中的变量
        target_path = path_template.format(
            base_path=base_path,
            year=year,
            month=month,
            day=day,
            game_title=game_title,
            folder_name=article_info.get('folder_name', 'article')
        )
        
        # 清理路径中的双斜杠
        target_path = target_path.replace('//', '/')
        
        return target_path
    
    def upload_images_to_repo(self, image_files, repo_id, article_info, is_final_commit=False):
        """将图片上传到指定的图床仓库"""
        try:
            image_repo_config = self.get_image_repo_config(repo_id)
            if not image_repo_config:
                return {
                    'success': False,
                    'error': f'仓库 {repo_id} 没有配置图床仓库或图床仓库未启用'
                }
            
            repo_url = image_repo_config['url']
            branch = image_repo_config.get('branch', 'main')
            auth_token = image_repo_config['auth']['token']
            domain = image_repo_config.get('domain', '')
            
            # 生成目标路径
            target_base_path = self.generate_image_target_path(image_repo_config, article_info)
            
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                repo_path = temp_path / "repo"
                
                # 克隆图床仓库
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
                
                # 创建目标目录
                target_path = repo_path / target_base_path
                target_path.mkdir(parents=True, exist_ok=True)
                
                uploaded_images = []
                
                # 上传每个图片文件
                for image_file in image_files:
                    if not Path(image_file).exists():
                        continue
                    
                    # 获取文件名
                    filename = Path(image_file).name
                    
                    # 复制图片到目标目录
                    target_file = target_path / filename
                    shutil.copy2(image_file, target_file)
                    
                    # 生成远程URL
                    if domain:
                        remote_url = f"https://{domain}/{target_base_path}/{filename}"
                    else:
                        # 如果没有配置域名，使用GitHub raw URL
                        repo_name = repo_url.split('/')[-1].replace('.git', '')
                        owner = repo_url.split('/')[-2]
                        remote_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{target_base_path}/{filename}"
                    
                    uploaded_images.append({
                        'local_path': image_file,
                        'filename': filename,
                        'remote_url': remote_url,
                        'target_path': str(target_file)
                    })
                
                if not uploaded_images:
                    return {
                        'success': False,
                        'error': '没有找到有效的图片文件'
                    }
                
                # 提交更改
                subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
                
                # 检查是否有变更需要提交
                result = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_path, capture_output=True, text=True)
                if not result.stdout.strip():
                    return {
                        'success': True,
                        'repo_id': repo_id,
                        'repo_name': image_repo_config['name'],
                        'uploaded_images': uploaded_images,
                        'message': '没有变更需要提交'
                    }
                
                # 根据是否为最后一次提交生成不同的提交信息
                if is_final_commit:
                    commit_message = f"🤖 上传图片 {len(uploaded_images)} 张"
                    print(f"    🚀 图片上传完成，开启自动部署")
                else:
                    commit_message = f"🤖 上传图片 {len(uploaded_images)} 张 [skip ci]"
                    print(f"    📝 图片上传完成，跳过自动部署")
                
                subprocess.run([
                    'git', 'commit', '-m', commit_message
                ], cwd=repo_path, check=True)
                
                subprocess.run(['git', 'push'], cwd=repo_path, check=True)
                
                return {
                    'success': True,
                    'repo_id': repo_id,
                    'repo_name': image_repo_config['name'],
                    'repo_url': repo_url,
                    'target_base_path': target_base_path,
                    'uploaded_images': uploaded_images,
                    'upload_time': datetime.now(beijing_tz).isoformat()
                }
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Git命令执行失败: {e.stderr.decode() if e.stderr else str(e)}"
            return {
                'success': False,
                'repo_id': repo_id,
                'error': error_msg,
                'upload_time': datetime.now(beijing_tz).isoformat()
            }
        except Exception as e:
            return {
                'success': False,
                'repo_id': repo_id,
                'error': str(e),
                'upload_time': datetime.now(beijing_tz).isoformat()
            }
    
    def batch_upload_articles_images(self, articles_data, repo_id, is_final_commit=False):
        """批量上传多篇文章的图片到图床仓库"""
        try:
            image_repo_config = self.get_image_repo_config(repo_id)
            if not image_repo_config:
                return {
                    'success': False,
                    'error': f'仓库 {repo_id} 没有配置图床仓库或图床仓库未启用'
                }
            
            repo_url = image_repo_config['url']
            branch = image_repo_config.get('branch', 'main')
            auth_token = image_repo_config['auth']['token']
            domain = image_repo_config.get('domain', '')
            
            # 收集所有文章的图片文件
            all_uploaded_images = {}
            total_images = 0
            
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                repo_path = temp_path / "repo"
                
                # 克隆图床仓库
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
                
                # 处理每篇文章的图片
                for article_data in articles_data:
                    article_path = Path(article_data['original_path'])
                    article_info = article_data['article_data']
                    images_dir = article_path / "images"
                    
                    if not images_dir.exists():
                        print(f"      ⚠️  文章 {article_info['folder_name']} 没有图片")
                        continue
                    
                    # 收集图片文件
                    image_files = []
                    for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
                        image_files.extend(images_dir.glob(ext))
                    
                    if not image_files:
                        print(f"      ⚠️  文章 {article_info['folder_name']} 没有找到图片文件")
                        continue
                    
                    print(f"      📸 处理文章 {article_info['folder_name']} 的 {len(image_files)} 张图片...")
                    
                    # 生成目标路径
                    target_base_path = self.generate_image_target_path(image_repo_config, article_info)
                    target_path = repo_path / target_base_path
                    target_path.mkdir(parents=True, exist_ok=True)
                    
                    article_uploaded_images = []
                    
                    # 上传每个图片文件
                    for image_file in image_files:
                        if not image_file.exists():
                            continue
                        
                        # 获取文件名
                        filename = image_file.name
                        
                        # 复制图片到目标目录
                        target_file = target_path / filename
                        shutil.copy2(image_file, target_file)
                        
                        # 生成远程URL
                        if domain:
                            remote_url = f"https://{domain}/{target_base_path}/{filename}"
                        else:
                            # 如果没有配置域名，使用GitHub raw URL
                            repo_name = repo_url.split('/')[-1].replace('.git', '')
                            owner = repo_url.split('/')[-2]
                            remote_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{target_base_path}/{filename}"
                        
                        article_uploaded_images.append({
                            'local_path': str(image_file),
                            'filename': filename,
                            'remote_url': remote_url,
                            'target_path': str(target_file)
                        })
                    
                    if article_uploaded_images:
                        all_uploaded_images[article_info['folder_name']] = article_uploaded_images
                        total_images += len(article_uploaded_images)
                        print(f"      ✅ 文章 {article_info['folder_name']} 图片准备完成: {len(article_uploaded_images)} 张")
                
                if not all_uploaded_images:
                    return {
                        'success': True,
                        'repo_id': repo_id,
                        'repo_name': image_repo_config['name'],
                        'uploaded_images': {},
                        'message': '没有图片需要上传'
                    }
                
                # 提交所有更改
                subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
                
                # 检查是否有变更需要提交
                result = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_path, capture_output=True, text=True)
                if not result.stdout.strip():
                    return {
                        'success': True,
                        'repo_id': repo_id,
                        'repo_name': image_repo_config['name'],
                        'uploaded_images': all_uploaded_images,
                        'message': '没有变更需要提交'
                    }
                
                # 根据是否为最后一次提交生成不同的提交信息
                if is_final_commit:
                    commit_message = f"🤖 批量上传图片 {total_images} 张 (共 {len(articles_data)} 篇文章)"
                    print(f"    🚀 批量图片上传完成，开启自动部署")
                else:
                    commit_message = f"🤖 批量上传图片 {total_images} 张 (共 {len(articles_data)} 篇文章) [skip ci]"
                    print(f"    📝 批量图片上传完成，跳过自动部署")
                
                subprocess.run([
                    'git', 'commit', '-m', commit_message
                ], cwd=repo_path, check=True)
                
                subprocess.run(['git', 'push'], cwd=repo_path, check=True)
                
                return {
                    'success': True,
                    'repo_id': repo_id,
                    'repo_name': image_repo_config['name'],
                    'repo_url': repo_url,
                    'uploaded_images': all_uploaded_images,
                    'total_images': total_images,
                    'articles_count': len(articles_data),
                    'upload_time': datetime.now(beijing_tz).isoformat()
                }
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Git命令执行失败: {e.stderr.decode() if e.stderr else str(e)}"
            return {
                'success': False,
                'repo_id': repo_id,
                'error': error_msg,
                'upload_time': datetime.now(beijing_tz).isoformat()
            }
        except Exception as e:
            return {
                'success': False,
                'repo_id': repo_id,
                'error': str(e),
                'upload_time': datetime.now(beijing_tz).isoformat()
            }

    def replace_images_with_remote_urls(self, text, image_mapping):
        """将文章中的图片路径替换为远程URL"""
        if not image_mapping:
            return text
        
        result_text = text
        replaced_count = 0
        
        # 匹配所有图片路径模式
        patterns = [
            r'!\[([^\]]*)\]\(\./images/([^)]+)\)',  # ![xxx](./images/xxx)
            r'!\[([^\]]*)\]\([^)]*images/([^)]+)\)',  # 任何包含images/的路径
        ]
        
        for pattern in patterns:
            def replace_func(match):
                nonlocal replaced_count
                alt_text = match.group(1)
                filename = match.group(2)
                
                # 查找对应的远程URL
                for img_info in image_mapping:
                    if img_info['filename'] == filename:
                        replaced_count += 1
                        print(f"[REPLACE] 替换图片路径: {filename} -> {img_info['remote_url']}")
                        safe_url = self._sanitize_url(img_info["remote_url"])
                        return f'![{alt_text}]({safe_url})'
                
                # 如果没有找到对应的远程URL，保持原样
                return match.group(0)
            
            result_text = re.sub(pattern, replace_func, result_text)
        
        print(f"[REPLACE] 已替换 {replaced_count} 个图片路径为远程URL")
        return result_text
    
    def process_article_images(self, article_path, repo_id, article_info, is_final_commit=False):
        """处理文章中的所有图片，上传到图床并更新文章内容"""
        try:
            article_path = Path(article_path)
            images_dir = article_path / "images"
            
            if not images_dir.exists():
                print(f"⚠️  文章目录中没有找到images文件夹: {images_dir}")
                return {
                    'success': True,
                    'message': '没有图片需要处理',
                    'updated_content': None
                }
            
            # 收集所有图片文件
            image_files = []
            for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
                image_files.extend(images_dir.glob(ext))
            
            if not image_files:
                print(f"⚠️  images文件夹中没有找到图片文件")
                return {
                    'success': True,
                    'message': '没有图片需要处理',
                    'updated_content': None
                }
            
            print(f"📸 找到 {len(image_files)} 张图片，开始上传到图床仓库...")
            
            # 上传图片到图床仓库
            upload_result = self.upload_images_to_repo(image_files, repo_id, article_info, is_final_commit)
            
            if not upload_result['success']:
                return {
                    'success': False,
                    'error': upload_result['error']
                }
            
            print(f"✅ 图片上传成功: {upload_result['repo_name']}")
            
            # 读取文章内容
            markdown_file = article_path / "README.md"
            if not markdown_file.exists():
                return {
                    'success': False,
                    'error': f'找不到文章文件: {markdown_file}'
                }
            
            with open(markdown_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 替换图片路径为远程URL
            image_mapping = upload_result['uploaded_images']
            updated_content = self.replace_images_with_remote_urls(content, image_mapping)
            
            # 保存更新后的内容
            with open(markdown_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            return {
                'success': True,
                'repo_id': repo_id,
                'repo_name': upload_result['repo_name'],
                'uploaded_images': image_mapping,
                'updated_content': updated_content,
                'upload_time': upload_result['upload_time']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }