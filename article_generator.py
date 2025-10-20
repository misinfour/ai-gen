import os
import random
import re
import requests
import time
import json
from pathlib import Path
from urllib.parse import quote
import sys
from datetime import datetime, timezone, timedelta
from itertools import cycle

# 定义北京时间时区
beijing_tz = timezone(timedelta(hours=8))

# 导入配置和API管理器
from config_manager import ConfigManager
from api_manager import MultiPlatformApiManager, ApiExhaustedRetriesError
from repo_manager import RepositoryManager

# 尝试导入可选依赖，并进行适当的错误处理
try:
    from bing_image_downloader import downloader
except ImportError:
    print("警告: 未找到 bing_image_downloader 包。请使用以下命令安装:")
    print("安装命令: pip install bing-image-downloader")
    downloader = None

# 设置默认参数
DATE = datetime.now(beijing_tz).strftime("%Y-%m-%d")
YEAR = datetime.now(beijing_tz).strftime("%Y")
MONTH = datetime.now(beijing_tz).strftime("%m")
DAY = datetime.now(beijing_tz).strftime("%d")

# 使用备份目录结构，不再使用临时目录
BACKUP_BASE_DIR = "./logs/backup"
ICON = "skin"
ERROR_LOG = f"{BACKUP_BASE_DIR}/error_log.txt"
LONG_TAIL_FILE = "长尾词.txt"

# 语言配置
LANGUAGES = {
    'zh-cn': '简体中文',
    'zh-tw': '繁体中文'
}

class ArticleGenerator:
    """文章生成器，整合了aigen.py的功能"""
    
    def __init__(self, config_manager=None, api_manager=None, verbose=True):
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or MultiPlatformApiManager(self.config_manager)
        self.repo_manager = RepositoryManager(self.config_manager)
        
        # 熔断机制状态
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        
        # 设置熔断检查回调
        self.api_manager.set_circuit_breaker_callback(self._check_circuit_breaker)
        
        # 设置默认平台
        default_platform = self.config_manager.config.get("default_platform", "groq")
        self.api_manager.set_platform(default_platform)
        
        if verbose:
            print(f"文章生成器已初始化，使用AI平台: {default_platform}")
            
            # 显示启用的仓库
            enabled_repos = self.repo_manager.get_enabled_repositories()
            print(f"📁 启用的仓库数量: {len(enabled_repos)}")
            for repo_id, repo_config in enabled_repos.items():
                print(f"  - {repo_config['name']} ({repo_config['type']})")
    
    def get_language_mapping(self, lang_code, repo_name=None):
        """获取语言映射配置"""
        if repo_name:
            # 从指定仓库获取语言映射
            enabled_repos = self.repo_manager.get_enabled_repositories()
            repo_config = enabled_repos.get(repo_name, {})
        else:
            # 从第一个启用的仓库获取语言映射
            enabled_repos = self.repo_manager.get_enabled_repositories()
            repo_config = next(iter(enabled_repos.values()), {}) if enabled_repos else {}
        
        language_mapping = repo_config.get('language_mapping', {})
        return language_mapping.get(lang_code, lang_code)

    def translate_text(self, text, target_lang=None):
        """使用Google翻译API翻译文本"""
        try:
            # 如果没有指定目标语言，使用默认值
            if target_lang is None:
                target_lang = self.get_language_mapping('zh-tw')
            
            # 如果目标语言是简体中文，直接返回原文
            if target_lang == 'zh-CN':
                return text
                
            # 构建翻译API URL
            url = f'https://m3u8-player.5yxy5.com/api/forward/https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl={target_lang}&q={quote(text)}'
            
            # 发送请求
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # 提取翻译结果
            result = response.json()
            translated_text = ''.join([te[0] for te in result[0]])
            
            print(f"翻译: '{text[:50]}...' -> '{translated_text[:50]}...' ({target_lang})")
            return translated_text
            
        except Exception as e:
            print(f"翻译失败 ({target_lang}): {e}")
            # 翻译失败时返回原文
            return text

    def translate_long_content(self, content, target_lang=None):
        """简单可靠的翻译方法，保持Markdown格式"""
        # 如果没有指定目标语言，使用默认值
        if target_lang is None:
            target_lang = self.get_language_mapping('zh-tw')
        
        if target_lang == 'zh-CN':
            return content
        
        try:
            print(f"开始简单可靠翻译，保持Markdown格式...")
            
            lines = content.split('\n')
            translated_lines = []
            in_code_block = False
            
            for i, line in enumerate(lines):
                # 检查代码块
                if line.strip().startswith('```'):
                    in_code_block = not in_code_block
                    translated_lines.append(line)
                    continue
                
                # 代码块内容不翻译
                if in_code_block:
                    translated_lines.append(line)
                    continue
                
                # 空行不翻译
                if not line.strip():
                    translated_lines.append(line)
                    continue
                
                # 特殊行不翻译
                stripped = line.strip()
                if (stripped.startswith('>') or 
                    stripped.startswith('<') or
                    stripped.startswith('---') or
                    stripped.startswith('[图片占位符]') or
                    re.match(r'^[\s|:-]+$', stripped)):
                    translated_lines.append(line)
                    continue
                
                # 翻译这一行
                translated_line = self.translate_single_line(line, target_lang)
                translated_lines.append(translated_line)
                time.sleep(0.3)  # 避免API限制
                
                print(f"已完成 {i+1}/{len(lines)} 行")
            
            result = '\n'.join(translated_lines)
            print(f"✅ 翻译完成，原文 {len(content)} 字符 -> 译文 {len(result)} 字符")
            return result
            
        except Exception as e:
            print(f"❌ 翻译失败: {e}")
            print("🔄 回退使用原文...")
            return content

    def translate_single_line(self, line, target_lang):
        """翻译单行文本，保持基本的Markdown格式"""
        try:
            original_line = line
            
            # 处理标题
            if line.startswith('#'):
                match = re.match(r'^(#+\s+)(.+)$', line)
                if match:
                    prefix = match.group(1)
                    title_text = match.group(2)
                    translated_title = self.translate_text(title_text, target_lang)
                    return f"{prefix}{translated_title}"
            
            # 处理列表项
            elif re.match(r'^\s*[-*+]\s+', line):
                match = re.match(r'^(\s*[-*+]\s+)(.+)$', line)
                if match:
                    prefix = match.group(1)
                    content = match.group(2)
                    translated_content = self.translate_text(content, target_lang)
                    return f"{prefix}{translated_content}"
            
            # 处理数字列表
            elif re.match(r'^\s*\d+\.\s+', line):
                match = re.match(r'^(\s*\d+\.\s+)(.+)$', line)
                if match:
                    prefix = match.group(1)
                    content = match.group(2)
                    translated_content = self.translate_text(content, target_lang)
                    return f"{prefix}{translated_content}"
            
            # 处理链接和图片
            elif '[' in line and '](' in line:
                # 处理图片：![alt](url) 格式
                if line.strip().startswith('!['):
                    def translate_image_alt(match):
                        prefix = match.group(1)  # '!['
                        alt_text = match.group(2)  # alt文本
                        suffix = match.group(3)   # '](url)'
                        translated_alt = self.translate_text(alt_text, target_lang)
                        return f"{prefix}{translated_alt}{suffix}"
                    
                    result = re.sub(r'(!\[)([^\]]+)(\]\([^)]+\))', translate_image_alt, line)
                    return result
                
                # 处理普通链接：[text](url) 格式
                else:
                    def translate_link_text(match):
                        prefix = match.group(1)   # '['
                        link_text = match.group(2)  # 链接文本
                        suffix = match.group(3)   # '](url)'
                        translated_text = self.translate_text(link_text, target_lang)
                        return f"{prefix}{translated_text}{suffix}"
                    
                    result = re.sub(r'(\[)([^\]]+)(\]\([^)]+\))', translate_link_text, line)
                    
                    # 如果链接处理成功，返回结果；否则翻译整行
                    if result != line:
                        return result
                    else:
                        return self.translate_text(line, target_lang)
            
            # 普通文本行
            else:
                return self.translate_text(line, target_lang)
                
        except Exception as e:
            print(f"⚠️ 翻译单行失败: {e}, 返回原文")
            return line

    def translate_content_intelligently(self, content, target_lang):
        """智能翻译内容，逐行处理，保持格式完整"""
        try:
            lines = content.split('\n')
            translated_lines = []
            
            print(f"开始逐行智能翻译，共 {len(lines)} 行...")
            
            i = 0
            in_code_block = False
            
            while i < len(lines):
                line = lines[i]
                
                # 检查代码块状态
                if line.strip().startswith('```'):
                    in_code_block = not in_code_block
                    translated_lines.append(line)  # 代码块标记不翻译
                    i += 1
                    continue
                
                # 在代码块内，不翻译
                if in_code_block:
                    translated_lines.append(line)
                    i += 1
                    continue
                
                # 空行直接保持
                if not line.strip():
                    translated_lines.append(line)
                    i += 1
                    continue
                
                # 跳过特殊行（引用、表格分隔符、HTML标签等）
                stripped = line.strip()
                if (stripped.startswith('>') or 
                    stripped.startswith('<') or
                    re.match(r'^[\s|:-]+$', stripped) or
                    stripped.startswith('---') or
                    stripped.startswith('[图片占位符]') or
                    stripped.startswith('#') and '这是代码块' in stripped):  # 跳过代码注释行
                    translated_lines.append(line)
                    i += 1
                    continue
                
                # 翻译这一行
                translated_line = self.translate_line_smartly(line, target_lang)
                translated_lines.append(translated_line)
                i += 1
                time.sleep(0.3)  # 避免API限制
            
            result = '\n'.join(translated_lines)
            return result
            
        except Exception as e:
            print(f"❌ 智能翻译过程出错: {e}")
            raise
    
    def translate_line_smartly(self, line, target_lang):
        """智能翻译单行，保持Markdown格式"""
        try:
            # 如果是标题
            if line.startswith('#'):
                match = re.match(r'^(#+\s+)(.+)$', line)
                if match:
                    prefix = match.group(1)
                    title_text = match.group(2)
                    translated_title = self.translate_text(title_text, target_lang)
                    return f"{prefix}{translated_title}"
            
            # 如果是列表项
            elif re.match(r'^\s*[-*+]\s+', line):
                match = re.match(r'^(\s*[-*+]\s+)(.+)$', line)
                if match:
                    prefix = match.group(1)
                    list_text = match.group(2)
                    translated_text = self.translate_text(list_text, target_lang)
                    return f"{prefix}{translated_text}"
            
            # 如果是数字列表项
            elif re.match(r'^\s*\d+\.\s+', line):
                match = re.match(r'^(\s*\d+\.\s+)(.+)$', line)
                if match:
                    prefix = match.group(1)
                    list_text = match.group(2)
                    translated_text = self.translate_text(list_text, target_lang)
                    return f"{prefix}{translated_text}"
            
            # 如果是链接行
            elif '[' in line and '](' in line:
                # 使用更精确的正则表达式处理链接
                def translate_link_text(match):
                    link_text = match.group(2)
                    translated_link_text = self.translate_text(link_text, target_lang)
                    return f"{match.group(1)}{translated_link_text}{match.group(3)}"
                
                # 替换所有链接文本
                result = re.sub(r'(\[)([^\]]+)(\]\([^)]+\))', translate_link_text, line)
                
                # 翻译链接外的其他文本
                if result == line:  # 如果没有链接或链接处理失败，翻译整行
                    return self.translate_text(line, target_lang)
                else:
                    # 翻译链接外的文本部分
                    # 简化处理：如果有链接，只翻译非链接部分
                    return result
            
            # 普通段落，处理内联格式
            else:
                return self.translate_text_with_inline_format(line, target_lang)
                
        except Exception as e:
            print(f"⚠️ 翻译行时出错: {e}, 使用原文")
            return line
    
    def translate_text_with_inline_format(self, text, target_lang):
        """翻译文本，保持内联格式（粗体、斜体等）"""
        try:
            # 暂时替换特殊格式，避免被翻译
            placeholders = {}
            placeholder_counter = 0
            
            # 保护粗体格式 **text**
            def replace_bold(match):
                nonlocal placeholder_counter
                placeholder = f"__BOLD_PLACEHOLDER_{placeholder_counter}__"
                inner_text = match.group(2)
                translated_inner = self.translate_text(inner_text, target_lang)
                placeholders[placeholder] = f"**{translated_inner}**"
                placeholder_counter += 1
                return placeholder
            
            text = re.sub(r'(\*\*)([^*]+)(\*\*)', replace_bold, text)
            
            # 保护斜体格式 *text*（但不是**）
            def replace_italic(match):
                nonlocal placeholder_counter
                placeholder = f"__ITALIC_PLACEHOLDER_{placeholder_counter}__"
                inner_text = match.group(2)
                translated_inner = self.translate_text(inner_text, target_lang)
                placeholders[placeholder] = f"*{translated_inner}*"
                placeholder_counter += 1
                return placeholder
            
            text = re.sub(r'(\*)([^*]+)(\*)(?!\*)', replace_italic, text)
            
            # 保护代码格式 `code`
            def replace_code(match):
                nonlocal placeholder_counter
                placeholder = f"__CODE_PLACEHOLDER_{placeholder_counter}__"
                placeholders[placeholder] = match.group(0)  # 代码不翻译
                placeholder_counter += 1
                return placeholder
            
            text = re.sub(r'`[^`]+`', replace_code, text)
            
            # 翻译剩余文本
            if text.strip() and not any(ph in text for ph in placeholders.keys()):
                translated_text = self.translate_text(text, target_lang)
            else:
                translated_text = text
            
            # 恢复占位符
            for placeholder, original in placeholders.items():
                translated_text = translated_text.replace(placeholder, original)
            
            return translated_text
            
        except Exception as e:
            print(f"⚠️ 处理内联格式时出错: {e}")
            return self.translate_text(text, target_lang)

    def extract_translatable_text(self, content):
        """从Markdown内容中提取需要翻译的纯文本"""
        text_blocks = {}
        block_counter = 0
        
        # 使用正则表达式匹配各种Markdown元素中的文本
        patterns = [
            # 标题中的文本 (保留#符号和空格，只提取文本部分)
            (r'^(#+\s+)(.+)$', 'title'),
            # 列表项中的文本 (保留列表符号和缩进，只提取文本部分)  
            (r'^(\s*[-*+]\s+)(.+)$', 'list'),
            # 数字列表项中的文本
            (r'^(\s*\d+\.\s+)(.+)$', 'numbered_list'),
            # 粗体文本中的内容
            (r'(\*\*)([^*]+)(\*\*)', 'bold'),
            # 斜体文本中的内容
            (r'(\*)([^*]+)(\*)', 'italic'),
            # 链接文本中的内容
            (r'(\[)([^\]]+)(\]\([^)]+\))', 'link'),
            # 普通段落文本 (不在其他格式内的文本)
            (r'^([^#*\-+\d\s\[\]`>|].*)$', 'paragraph')
        ]
        
        lines = content.split('\n')
        for line_idx, line in enumerate(lines):
            if not line.strip():  # 跳过空行
                continue
                
            # 跳过代码块
            if line.strip().startswith('```'):
                continue
                
            # 跳过引用块标记符号
            if line.strip().startswith('>'):
                continue
                
            # 跳过表格分隔符
            if re.match(r'^[\s|:-]+$', line):
                continue
            
            for pattern, text_type in patterns:
                matches = list(re.finditer(pattern, line, re.MULTILINE))
                for match in matches:
                    if text_type in ['title', 'list', 'numbered_list', 'paragraph']:
                        # 对于这些类型，提取整个文本内容
                        text_content = match.group(2) if len(match.groups()) >= 2 else match.group(1)
                    elif text_type in ['bold', 'italic', 'link']:
                        # 对于这些类型，提取中间的文本内容
                        text_content = match.group(2)
                    else:
                        continue
                        
                    if text_content.strip():  # 只处理非空文本
                        block_id = f"TEXT_BLOCK_{block_counter}"
                        text_blocks[block_id] = text_content.strip()
                        block_counter += 1
                        break  # 每行只匹配第一个模式
        
        print(f"提取了 {len(text_blocks)} 个文本块进行翻译")
        return text_blocks
    
    def rebuild_content_with_translations(self, original_content, translated_blocks):
        """将翻译后的文本重新组装到原始格式中"""
        result = original_content
        block_counter = 0
        
        # 重新应用相同的模式，但这次是替换
        patterns = [
            (r'^(#+\s+)(.+)$', 'title'),
            (r'^(\s*[-*+]\s+)(.+)$', 'list'),
            (r'^(\s*\d+\.\s+)(.+)$', 'numbered_list'),
            (r'(\*\*)([^*]+)(\*\*)', 'bold'),
            (r'(\*)([^*]+)(\*)', 'italic'),
            (r'(\[)([^\]]+)(\]\([^)]+\))', 'link'),
            (r'^([^#*\-+\d\s\[\]`>|].*)$', 'paragraph')
        ]
        
        lines = result.split('\n')
        for line_idx, line in enumerate(lines):
            if not line.strip():
                continue
                
            if line.strip().startswith('```') or line.strip().startswith('>') or re.match(r'^[\s|:-]+$', line):
                continue
            
            original_line = line
            for pattern, text_type in patterns:
                matches = list(re.finditer(pattern, line, re.MULTILINE))
                for match in matches:
                    block_id = f"TEXT_BLOCK_{block_counter}"
                    if block_id in translated_blocks:
                        if text_type in ['title', 'list', 'numbered_list', 'paragraph']:
                            # 替换整个文本内容，保持格式前缀
                            prefix = match.group(1) if len(match.groups()) >= 1 else ""
                            new_line = prefix + translated_blocks[block_id]
                            lines[line_idx] = new_line
                        elif text_type in ['bold', 'italic', 'link']:
                            # 替换中间的文本内容，保持格式标记
                            prefix = match.group(1)
                            suffix = match.group(3)
                            new_text = prefix + translated_blocks[block_id] + suffix
                            lines[line_idx] = line.replace(match.group(0), new_text)
                        
                        block_counter += 1
                        break
            
        return '\n'.join(lines)

    def is_special_markdown_line(self, line):
        """检查是否是特殊的Markdown行"""
        stripped = line.strip()
        return (stripped.startswith('#') or 
                stripped.startswith('-') or 
                stripped.startswith('*') or 
                stripped.startswith('+') or 
                re.match(r'^\d+\.', stripped) or
                stripped.startswith('```') or
                stripped.startswith('>')  or
                stripped.startswith('|'))

    def translate_markdown_title(self, line, target_lang):
        """翻译Markdown标题，保持格式"""
        # 提取标题级别和内容
        match = re.match(r'^(#+)\s*(.*)', line)
        if match:
            level = match.group(1)
            title_text = match.group(2)
            translated_title = self.translate_text(title_text, target_lang)
            return f"{level} {translated_title}"
        else:
            return self.translate_text(line, target_lang)

    def translate_list_item(self, line, target_lang):
        """翻译列表项，保持格式"""
        # 提取缩进、符号和内容
        match = re.match(r'^(\s*)([-*+])\s*(.*)', line)
        if match:
            indent = match.group(1)
            symbol = match.group(2)
            content = match.group(3)
            translated_content = self.translate_text(content, target_lang)
            return f"{indent}{symbol} {translated_content}"
        else:
            return self.translate_text(line, target_lang)

    def translate_numbered_list_item(self, line, target_lang):
        """翻译数字列表项，保持格式"""
        # 提取缩进、数字和内容
        match = re.match(r'^(\s*)(\d+\.)\s*(.*)', line)
        if match:
            indent = match.group(1)
            number = match.group(2)
            content = match.group(3)
            translated_content = self.translate_text(content, target_lang)
            return f"{indent}{number} {translated_content}"
        else:
            return self.translate_text(line, target_lang)

    def translate_long_paragraph(self, paragraph, target_lang):
        """翻译长段落，按句子分割"""
        sentences = paragraph.split('。')
        translated_sentences = []
        
        for sentence in sentences:
            if sentence.strip():
                translated_sentence = self.translate_text(sentence, target_lang)
                translated_sentences.append(translated_sentence)
                time.sleep(0.3)
        
        return '。'.join(translated_sentences)

    def translate_simple_paragraphs(self, content, target_lang):
        """简单的段落翻译（回退方案）"""
        paragraphs = content.split('\n\n')
        translated_paragraphs = []
        
        for paragraph in paragraphs:
            if paragraph.strip():
                translated_paragraph = self.translate_text(paragraph, target_lang)
                translated_paragraphs.append(translated_paragraph)
                time.sleep(0.5)
            else:
                translated_paragraphs.append(paragraph)
        
        return '\n\n'.join(translated_paragraphs)

    def fix_markdown_format_issues(self, content):
        """修复翻译后常见的Markdown格式问题"""
        try:
            # 修复被错误分割的粗体格式 "* *text**" -> "**text**"
            content = re.sub(r'\*\s+\*([^*]+)\*\*', r'**\1**', content)
            
            # 修复被错误分割的斜体格式 "* text*" -> "*text*"
            content = re.sub(r'\*\s+([^*]+)\*(?!\*)', r'*\1*', content)
            
            # 修复连续的星号问题 "* *" -> "**"
            content = re.sub(r'\*\s+\*', '**', content)
            
            # 修复列表项格式问题，确保列表项后有空格
            content = re.sub(r'^(\s*[-*+])([^\s])', r'\1 \2', content, flags=re.MULTILINE)
            
            # 修复数字列表项格式问题
            content = re.sub(r'^(\s*\d+\.)([^\s])', r'\1 \2', content, flags=re.MULTILINE)
            
            # 修复标题格式问题，确保#后有空格
            content = re.sub(r'^(#+)([^\s#])', r'\1 \2', content, flags=re.MULTILINE)
            
            # 修复下载链接中的格式问题
            content = re.sub(r'\[([^\]]+)，([^\]]+)破解版私服，外挂，修改版下载\]', r'[\1，\2破解版私服，外挂，修改版下载]', content)
            
            print("✅ 已修复常见的Markdown格式问题")
            return content
            
        except Exception as e:
            print(f"⚠️ 修复Markdown格式时出错: {e}")
            return content

    def get_language_specific_long_tail(self, lang_code, repo_name=None):
        """获取语言特定的长尾词"""
        long_tail = self.read_random_long_tail()
        if lang_code == 'zh-tw':
            # 翻译长尾词到对应语言
            target_lang = self.get_language_mapping(lang_code, repo_name)
            return self.translate_text(long_tail, target_lang)
        return long_tail

    def read_random_long_tail(self):
        """从长尾词.txt中随机读取一行"""
        try:
            with open(LONG_TAIL_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            if lines:
                return random.choice(lines)
            else:
                return "无限钻石内置修改器版，无限元宝无限资源内置菜单随便用，内部号修改版无限仙玉，完全零氪金！"
        except FileNotFoundError:
            print(f"警告: 未找到 {LONG_TAIL_FILE} 文件，使用默认长尾词")
            return "无限钻石内置修改器版，无限元宝无限资源内置菜单随便用，内部号修改版无限仙玉，完全零氪金！"
        except Exception as e:
            print(f"读取长尾词文件时出错: {e}")
            return "无限钻石内置修改器版，无限元宝无限资源内置菜单随便用，内部号修改版无限仙玉，完全零氪金！"

    def parse_keyword_and_game_name(self, input_text):
        """解析输入的keyword----自定义尾词----游戏名格式"""
        if "----" in input_text:
            parts = input_text.split("----")
            if len(parts) == 2:
                # 格式：关键词----游戏名
                keyword = parts[0].strip()
                game_name = parts[1].strip()
                custom_tail = ""
            elif len(parts) == 3:
                # 格式：关键词----自定义尾词----游戏名
                keyword = parts[0].strip()
                custom_tail = parts[1].strip()
                game_name = parts[2].strip()
            else:
                # 格式不正确，使用第一个部分作为关键词
                print(f"警告: 输入 '{input_text}' 格式不正确，将第一个部分作为关键词")
                keyword = parts[0].strip()
                custom_tail = ""
                game_name = ""
            return keyword, custom_tail, game_name
        else:
            # 如果没有使用----分隔符，则把整个输入作为keyword，其他留空
            print(f"警告: 输入 '{input_text}' 没有使用 ---- 分隔符，将整个输入作为关键词")
            return input_text.strip(), "", ""

    def ensure_backup_directory(self):
        """确保备份目录存在"""
        Path(BACKUP_BASE_DIR).mkdir(parents=True, exist_ok=True)

    def sanitize_filename(self, filename):
        """
        清理文件名，确保Windows文件系统兼容性
        保留中文、英文字符，移除特殊字符
        """
        if not filename:
            return "untitled"
        
        # Windows文件系统禁用的字符
        forbidden_chars = r'<>:"/\\|?*'
        
        # 移除禁用字符
        sanitized = ""
        for char in filename:
            if char not in forbidden_chars:
                # 保留中文字符（Unicode范围）、英文字母、数字、空格、下划线、连字符
                if (char.isalnum() or 
                    char in " _-" or 
                    '\u4e00' <= char <= '\u9fff' or  # 中文字符范围
                    '\u3400' <= char <= '\u4dbf' or  # 中文扩展A
                    '\u20000' <= char <= '\u2a6df' or  # 中文扩展B
                    '\uf900' <= char <= '\ufaff'):    # 中文兼容字符
                    sanitized += char
        
        # 去掉首尾空格，替换多个连续空格为单个空格
        sanitized = re.sub(r'\s+', ' ', sanitized.strip())
        
        # 如果清理后为空，使用默认名称
        if not sanitized:
            sanitized = "untitled"
        
        # 限制长度（Windows路径有255字符限制）
        if len(sanitized) > 100:
            sanitized = sanitized[:100].rstrip()
        
        return sanitized

    def create_image_directory(self, keyword, lang_code='zh-cn', repo_name=None, repo_config=None):
        """为文章图片创建目录（直接在备份目录中创建，使用配置文件的设置）"""
        # 确保文件名合法，使用新的清理函数
        safe_keyword = self.sanitize_filename(keyword)
        
        # 如果没有指定仓库名，获取第一个可用的仓库名
        if repo_name is None:
            enabled_repos = self.repo_manager.get_enabled_repositories()
            git_repos = {k: v for k, v in enabled_repos.items() if v['type'] == 'git'}
            if git_repos:
                first_repo = list(git_repos.values())[0]
                repo_name = first_repo.get('name', 'default')
            else:
                repo_name = "default"
        
        # 获取分类设置，如果提供了仓库配置则使用配置中的category，否则使用默认值
        if repo_config:
            category = repo_config.get('category', 'strategy')
        else:
            category = 'strategy'  # 默认分类
        
        # 准备文章信息用于生成路径
        article_info = {
            'language': lang_code,
            'folder_name': safe_keyword
        }
        
        # 使用本地备份仓库配置
        local_repo_config = {
            'base_path': './logs',
            'path_template': '{base_path}/backup/{repo_name}/{language_path}/{category}/{year}/{month}/{day}',
            'category': category,
            'name': repo_name,
            'primary_language': repo_config.get('primary_language', 'zh-cn') if repo_config else 'zh-cn',
            'language_mapping': repo_config.get('language_mapping', {}) if repo_config else {}
        }
        
        # 使用repo_manager生成目标路径，避免重复日期
        target_base_path = self.repo_manager.generate_target_path(local_repo_config, article_info)
        
        # 构建最终的图片目录路径
        image_dir = Path(target_base_path) / safe_keyword / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        return image_dir, safe_keyword

    def get_images_bing_with_timeout(self, keyword, output_dir, limit=1, timeout=15):
        """使用线程池和超时来下载图片，避免多进程句柄问题"""
        import threading
        import queue
        
        def download_worker(keyword, output_dir, limit, result_queue):
            """工作线程函数"""
            try:
                if not downloader:
                    result_queue.put(("skip", "图片下载库未安装，跳过图片下载"))
                    return
                
                # 确保输出目录存在
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                
                # 使用Bing下载图片
                downloader.download(
                    keyword, 
                    limit=limit,
                    output_dir=str(output_dir),
                    adult_filter_off=True,
                    force_replace=False,
                    timeout=10  # 库级别的超时
                )
                
                # 获取下载的图片路径
                image_folder = Path(output_dir) / keyword
                if image_folder.exists():
                    image_files = list(image_folder.glob("*.*"))
                    if image_files:
                        result_queue.put(("success", [str(img) for img in image_files]))
                        return
                
                result_queue.put(("empty", "未找到下载的图片文件"))
                
            except Exception as e:
                result_queue.put(("error", str(e)))

        # 创建结果队列
        result_queue = queue.Queue()
        
        # 创建并启动工作线程
        thread = threading.Thread(
            target=download_worker, 
            args=(keyword, output_dir, limit, result_queue),
            daemon=True
        )
        thread.start()
        
        try:
            # 等待结果，带超时
            result = result_queue.get(timeout=timeout)
            thread.join(timeout=2)  # 给线程2秒时间正常结束
            
            status, data = result
            if status == "success":
                print(f"✅ 成功下载 {len(data)} 张图片")
                return data
            elif status == "empty":
                print(f"⚠️ {data}")
                return []
            elif status == "skip":
                print(f"ℹ️ {data}")
                return []
            else:
                print(f"❌ 下载失败: {data}")
                return []
                
        except queue.Empty:
            print(f"⏰ 下载超时 ({timeout}秒)")
            return []
        except Exception as e:
            print(f"❌ 下载过程异常: {e}")
            return []

    def get_images_bing(self, keyword, output_dir, limit=1):
        """使用Bing图片搜索下载图片（带强制超时保护）"""
        if not downloader:
            print("无法获取图片：需要安装bing-image-downloader库")
            return []
        
        max_retries = 1  # 只重试1次
        base_timeout = 15  # 基础超时时间
        
        for attempt in range(max_retries):
            timeout = base_timeout + (attempt * 5)  # 递增超时时间
            print(f"🔄 尝试下载图片 (第{attempt + 1}/{max_retries}次，超时{timeout}秒) - 关键词: {keyword}")
            
            try:
                result = self.get_images_bing_with_timeout(keyword, output_dir, limit, timeout)
                
                if result:
                    return result
                    
                # 清理可能的部分下载文件
                try:
                    image_folder = Path(output_dir) / keyword
                    if image_folder.exists():
                        import shutil
                        shutil.rmtree(image_folder)
                        print("🧹 已清理部分下载文件")
                except:
                    pass
                
                if attempt < max_retries - 1:
                    print(f"⏰ 等待3秒后重试...")
                    time.sleep(3)
                else:
                    print(f"💥 所有重试都失败，跳过此关键词的图片下载")
                    return []
                    
            except Exception as e:
                print(f"❌ 下载过程异常: {e}")
                if attempt < max_retries - 1:
                    print(f"⏰ 等待3秒后重试...")
                    time.sleep(3)
                else:
                    print(f"💥 所有重试都失败，跳过此关键词的图片下载")
                    return []

    def get_main_image(self, keyword: str, image_dir: Path) -> str:
        """获取文章主图"""
        try:
            print(f"正在使用Bing搜索'{keyword}'的主图...")
            # 创建临时下载目录
            temp_download_dir = image_dir.parent / "temp_download"
            image_paths = self.get_images_bing(keyword, str(temp_download_dir), limit=1)
            
            if image_paths:
                img_path = Path(image_paths[0])
                # 将图片移动到所需位置并重命名
                new_filename = f"main_{int(time.time())}{img_path.suffix}"
                new_path = image_dir / new_filename
                
                # 复制图片到新位置
                with open(img_path, "rb") as src_file:
                    with open(new_path, "wb") as dst_file:
                        dst_file.write(src_file.read())
                
                # 清理临时下载文件夹
                self.cleanup_download_folders(str(temp_download_dir), keyword)
                
                # 返回相对于README.md文件的路径（图片在同目录的images文件夹内）
                return f"./images/{new_filename}"
        except Exception as e:
            print(f"获取主图失败: {e}")
        return ""

    def prepare_random_images(self, keyword_base: str, image_dir: Path, n: int = 6):
        """下载通用插图（背景图池）- 带强制超时保护，绝不卡住"""
        image_data = []  # 改为存储图片路径和类型信息
        
        # 严格的超时控制
        MAX_TOTAL_TIME = 30  # 整个图片下载过程最多30秒
        MAX_PER_KEYWORD_TIME = 20  # 每个关键词最多20秒
        
        try:
            keywords_info = [
                (f"{keyword_base} 游戏截图", "游戏截图"), 
                (f"{keyword_base} 职业", "职业介绍"), 
                (f"{keyword_base} 场景", "游戏场景"), 
                (f"{keyword_base} 角色", "游戏角色"),
                (f"{keyword_base} 攻略", "游戏攻略"),
                (f"{keyword_base}", "游戏相关")
            ]
            
            print(f"📸 开始下载 {keyword_base} 相关图片，目标数量: {n}，最大耗时: {MAX_TOTAL_TIME}秒")
            overall_start_time = time.time()
            
            # 对每个关键词，下载图片
            for i, (keyword, img_type) in enumerate(keywords_info):
                # 检查总体超时
                elapsed_total = time.time() - overall_start_time
                if elapsed_total > MAX_TOTAL_TIME:
                    print(f"⏰ 总体超时 ({elapsed_total:.1f}秒 > {MAX_TOTAL_TIME}秒)，强制停止下载")
                    break
                    
                if len(image_data) >= n:
                    print(f"✅ 已达到目标图片数量 ({n})，停止下载")
                    break
                
                remaining_time = MAX_TOTAL_TIME - elapsed_total
                keyword_timeout = min(MAX_PER_KEYWORD_TIME, remaining_time - 5)  # 保留5秒缓冲
                
                if keyword_timeout <= 0:
                    print(f"⏰ 剩余时间不足，跳过后续关键词")
                    break
                    
                print(f"🔍 [{i+1}/{len(keywords_info)}] 搜索'{keyword}'的图片 (限时{keyword_timeout:.0f}秒)...")
                keyword_start_time = time.time()
                
                try:
                    # 创建临时下载目录
                    temp_download_dir = image_dir.parent / "temp_download"
                    # 使用带超时的图片下载
                    img_paths = self.get_images_bing(keyword, str(temp_download_dir), limit=1)
                    
                    if not img_paths:
                        print(f"⚠️ 关键词 '{keyword}' 未找到图片")
                        continue
                    
                    for img_path in img_paths:
                        # 检查关键词级别的超时
                        if time.time() - keyword_start_time > keyword_timeout:
                            print(f"⏰ 关键词 '{keyword}' 处理超时，跳过")
                            break
                            
                        if len(image_data) >= n:
                            break
                            
                        path_obj = Path(img_path)
                        if path_obj.exists() and path_obj.stat().st_size > 1024:  # 确保文件大于1KB
                            try:
                                # 重命名图片
                                new_filename = f"image_{len(image_data)}_{int(time.time())}{path_obj.suffix}"
                                new_path = image_dir / new_filename
                                
                                # 复制图片到新位置
                                with open(path_obj, "rb") as src_file:
                                    with open(new_path, "wb") as dst_file:
                                        dst_file.write(src_file.read())
                                
                                # 验证复制的文件
                                if new_path.exists() and new_path.stat().st_size > 0:
                                    # 使用相对于README.md的路径（图片在同目录的images文件夹内）
                                    image_data.append({
                                        'path': f"./images/{new_filename}",
                                        'type': img_type
                                    })
                                    print(f"✅ 成功保存图片: {new_filename} ({new_path.stat().st_size} 字节)")
                                    
                                    # 清理临时下载文件夹
                                    self.cleanup_download_folders(str(temp_download_dir), keyword)
                                    
                                    break  # 成功获取一张图片就继续下一个关键词
                                else:
                                    print(f"❌ 复制的图片文件无效: {new_filename}")
                                    if new_path.exists():
                                        new_path.unlink()  # 删除无效文件
                                    
                            except Exception as copy_error:
                                print(f"❌ 复制图片失败: {copy_error}")
                                continue
                        else:
                            if not path_obj.exists():
                                print(f"⚠️ 图片文件不存在: {img_path}")
                            else:
                                print(f"⚠️ 图片文件太小: {img_path} ({path_obj.stat().st_size} 字节)")
                        
                except Exception as keyword_error:
                    print(f"❌ 处理关键词 '{keyword}' 时出错: {str(keyword_error)[:100]}...")
                    continue
                
                # 显示关键词处理耗时
                keyword_elapsed = time.time() - keyword_start_time
                print(f"📊 关键词 '{keyword}' 处理完成，耗时 {keyword_elapsed:.1f} 秒")
            
            total_elapsed = time.time() - overall_start_time
            print(f"📊 图片下载完成！成功获取 {len(image_data)} 张图片，总耗时 {total_elapsed:.1f} 秒")
            
            # 如果没有获取到足够图片，给出提示
            if len(image_data) < n:
                print(f"⚠️ 只获取到 {len(image_data)} 张图片，少于目标数量 {n}")
            
        except Exception as e:
            print(f"💥 准备随机图片时发生严重错误: {e}")
            import traceback
            traceback.print_exc()
        
        return image_data

    def cleanup_download_folders(self, output_dir, keyword):
        """清理临时下载文件夹，仅保留最终使用的图片文件"""
        try:
            import shutil
            image_folder = Path(output_dir) / keyword
            if image_folder.exists():
                print(f"🧹 清理临时下载文件夹: {image_folder}")
                shutil.rmtree(image_folder)
                print(f"✅ 已删除临时下载文件夹: {image_folder}")
        except Exception as e:
            print(f"⚠️ 清理临时下载文件夹失败: {e}")

    def generate_download_link_text(self, original_input: str) -> str:
        """根据输入格式生成下载链接文本"""
        if "----" in original_input:
            parts = original_input.split("----")
            if len(parts) == 2:
                # 格式：关键词----游戏名
                keyword = parts[0].strip()
                game_name = parts[1].strip()
                return f"{keyword}，{game_name}破解版私服，外挂，修改版下载"
            elif len(parts) == 3:
                # 格式：关键词----自定义尾词----游戏名
                keyword = parts[0].strip()
                custom_tail = parts[1].strip()
                game_name = parts[2].strip()
                return f"{keyword}，{game_name}破解版私服，外挂，修改版下载"
            else:
                # 格式不正确，使用第一个部分
                return f"{parts[0].strip()}破解版私服，外挂，修改版下载"
        else:
            # 没有分隔符，直接使用原输入
            return f"{original_input.strip()}破解版私服，外挂，修改版下载"

    def add_download_link(self, text: str, original_input: str) -> str:
        """在每个大小标题后面添加下载链接"""
        # 生成下载链接文本
        download_title = self.generate_download_link_text(original_input)
        
        # 使用正则表达式匹配标题（以#开头的行）
        # 匹配 Markdown 标题格式：#, ##, 
        # ###, ####, #####, ######
        title_pattern = r'^(#{1,2})\s+(.+)$'
        
        lines = text.split('\n')
        result = []
        
        for line in lines:
            result.append(line)
            # 检查是否是标题行
            if re.match(title_pattern, line):
                # 在标题后面添加下载链接
                result.append(f"[{download_title}]({{{{siteConfig.jumpDomain}}}})\n\n")
        
        return '\n'.join(result)





    def insert_random_images(self, text: str, random_img_data: list, original_input: str, lang_code='zh-cn', is_primary_language=True, repo_name=None, article_name=None, current_date=None) -> str:
        """在文章中插入随机图片并在标题后面添加下载链接"""
        if not random_img_data:
            return self.add_download_link(text, original_input)
        
        # 生成下载链接文本
        download_title = self.generate_download_link_text(original_input)
        
        # 使用正则表达式匹配标题（以#开头的行）
        title_pattern = r'^(#{1,3})\s+(.+)$'
        
        lines = text.split('\n')
        result = []
        title_count = 0  # 记录标题数量
        
        for line in lines:
            result.append(line)
            # 检查是否是标题行
            if re.match(title_pattern, line):
                # 在标题后面添加下载链接
                result.append(f"[{download_title}]({{{{siteConfig.jumpDomain}}}})\n\n")
                title_count += 1
                
                # 如果还有图片可以插入，在下载链接后面插入图片
                if title_count <= len(random_img_data) and title_count <= 3:  # 最多插入3张图片
                    img_info = random_img_data[title_count - 1]
                    img_path = img_info['path']
                    img_type = img_info['type']
                    
                    # 所有语言版本都使用图床的远程URL
                    img_md = self._generate_primary_language_image_link(img_info, repo_name, article_name, current_date)
                    
                    result.append(img_md)
        
        return '\n'.join(result)

    def _generate_primary_language_image_link(self, img_info, repo_name, article_name, current_date):
        """为主语言版本生成图床的远程URL"""
        try:
            from urllib.parse import urlsplit, urlunsplit, quote

            def _sanitize_url(url: str) -> str:
                try:
                    parts = urlsplit(url)
                    safe_path = quote(parts.path, safe="/@:_-.~%")
                    return urlunsplit((parts.scheme, parts.netloc, safe_path, parts.query, parts.fragment))
                except Exception:
                    return url

            # 获取仓库配置
            if repo_name:
                enabled_repos = self.repo_manager.get_enabled_repositories()
                repo_config = None
                for repo_id, config in enabled_repos.items():
                    if config.get('name') == repo_name:
                        repo_config = config
                        break
                
                if repo_config and repo_config.get('image_repo', {}).get('enabled', False):
                    # 获取图床配置
                    image_repo_config = repo_config['image_repo']
                    domain = image_repo_config.get('domain', '')
                    path_template = image_repo_config.get('path_template', '{base_path}/{year}/{month}/{day}/{game_title}')
                    base_path = image_repo_config.get('base_path', 'images')
                    
                    # 生成图床路径
                    if current_date:
                        year, month, day = current_date.split('/')
                    else:
                        from datetime import datetime, timezone, timedelta
                        beijing_tz = timezone(timedelta(hours=8))
                        now = datetime.now(beijing_tz)
                        year = now.strftime('%Y')
                        month = now.strftime('%m')
                        day = now.strftime('%d')
                    
                    target_path = path_template.format(
                        base_path=base_path,
                        year=year,
                        month=month,
                        day=day,
                        game_title=article_name or 'article'
                    )
                    
                    # 获取文件名
                    filename = img_info['path'].split('/')[-1]
                    
                    # 生成远程URL
                    if domain:
                        remote_url = f"https://{domain}/{target_path}/{filename}"
                    else:
                        # 如果没有配置域名，使用GitHub raw URL
                        repo_url = image_repo_config['url']
                        repo_name = repo_url.split('/')[-1].replace('.git', '')
                        owner = repo_url.split('/')[-2]
                        branch = image_repo_config.get('branch', 'main')
                        remote_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{target_path}/{filename}"
                    
                    safe_url = _sanitize_url(remote_url)
                    return f'![{img_info["type"]}]({safe_url})'
            
            # 如果没有配置图床或配置失败，使用相对路径作为后备
            return f'![{img_info["type"]}]({img_info["path"]})'
            
        except Exception as e:
            print(f"⚠️ 生成主语言图片链接失败: {e}")
            # 使用相对路径作为后备
            return f'![{img_info["type"]}]({img_info["path"]})'

    def _replace_images_with_cdn_urls(self, text: str, shared_image_data: list, repo_name: str, article_name: str, current_date: str) -> str:
        """将文章中的图片路径替换为图床URL"""
        if not shared_image_data:
            return text
        
        import re
        
        # 匹配所有图片路径模式
        patterns = [
            r'!\[([^\]]*)\]\(\./images/[^)]+\)',  # ![xxx](./images/xxx) - 正常格式
            r'!\[([^\]]*)\]\([^)]*images/[^)]+\)',  # 任何包含images/的路径
        ]
        
        result_text = text
        replaced_count = 0
        img_index = 0
        
        for pattern in patterns:
            def replace_func(match):
                nonlocal img_index, replaced_count
                if img_index < len(shared_image_data):
                    img_info = shared_image_data[img_index]
                    
                    # 使用图床URL生成逻辑
                    img_md = self._generate_primary_language_image_link(img_info, repo_name, article_name, current_date)
                    
                    img_index += 1
                    replaced_count += 1
                    print(f"🔧 替换图片路径为图床URL: {img_info['path']} -> {img_md}")
                    return img_md
                else:
                    # 如果图片数据用完了，保持原样
                    return match.group(0)
            
            result_text = re.sub(pattern, replace_func, result_text)
        
        print(f"🔧 已替换 {replaced_count} 个图片路径为图床URL")
        return result_text

    def _record_api_failure(self):
        """记录API失败调用并检查熔断"""
        self.consecutive_failures += 1
        print(f"❌ API 调用失败: ...")
        print(f"❌ 连续失败次数: {self.consecutive_failures}/{self.max_consecutive_failures}")
        print(f"📊 熔断机制状态: {'即将触发' if self.consecutive_failures >= self.max_consecutive_failures - 1 else '正常'}")
        
        if self.consecutive_failures >= self.max_consecutive_failures:
            print(f"🔥 连续失败 {self.consecutive_failures} 次，触发熔断机制！")
            print(f"⛔ 发布流程提前结束，触发熔断机制")
            print(f"🔥 熔断机制已触发，停止文章发布流程")
            # 抛出ApiExhaustedRetriesError确保能被工作流正确识别
            raise ApiExhaustedRetriesError(f"🔥 API服务连续失败{self.consecutive_failures}次，触发熔断机制，请稍后重试")
    
    def _record_api_success(self):
        """记录API成功调用"""
        if self.consecutive_failures > 0:
            print(f"🔄 重置熔断计数器: {self.consecutive_failures} -> 0")
        self.consecutive_failures = 0
    
    def _check_circuit_breaker(self):
        """检查熔断状态（由ApiManager调用）"""
        if self.consecutive_failures >= self.max_consecutive_failures:
            print(f"🔥 熔断检查：连续失败 {self.consecutive_failures} 次，触发熔断机制！")
            print(f"⛔ 发布流程提前结束，触发熔断机制")
            print(f"🔥 熔断机制已触发，停止文章发布流程")
            raise ApiExhaustedRetriesError(f"🔥 API服务连续失败{self.consecutive_failures}次，触发熔断机制，请稍后重试")

    def generate_article_content(self, prompt: str) -> str:
        """生成文章内容"""
        try:
            # 使用多平台API管理器生成内容
            print(f"正在通过 {self.api_manager.current_platform} API 生成文章内容...")
            content = self.api_manager.make_request(prompt)
            
            # 删除 <think>...</think> 标签及其中内容
            cleaned_text = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            
            # 只有核心文章内容生成成功时才重置熔断计数器
            self._record_api_success()
            print(f"✅ 核心文章内容生成成功，重置熔断计数器")
            return cleaned_text.strip()

        except ApiExhaustedRetriesError:
            # API重试耗尽，记录失败并检查熔断
            print(f"❌ API重试耗尽异常，记录失败并检查熔断")
            self.api_manager.show_usage_stats()
            # API重试耗尽，根据重试次数增加失败计数
            max_retries = getattr(self.api_manager, 'max_retries', 3)
            print(f"📊 API重试耗尽，增加 {max_retries} 次失败计数")
            
            # 根据API重试次数增加失败计数
            for _ in range(max_retries):
                self._record_api_failure()
            
            # 重新抛出异常
            raise
        except Exception as e:
            error_msg = str(e)
            print(f"❌ API 调用失败: {error_msg}")
            
            # 显示API密钥使用统计
            self.api_manager.show_usage_stats()
            
            # 记录失败并检查熔断（可能会抛出ApiExhaustedRetriesError）
            self._record_api_failure()
            
            # 重新抛出异常
            raise

    def get_related_keywords(self, keyword: str) -> str:
        """通过AI获取相关联想词"""
        try:
            print(f"正在获取'{keyword}'的联想词...")
            
            prompt = f"""# Role: 游戏推广SEO策略师

## Profile
- language: 中文
- description: 一位专注于游戏行业的资深搜索引擎优化（SEO）策略师。核心任务是基于给定的核心关键词，深度分析玩家的搜索意图和行为习惯，生成一个由**10个**最合适、最可能被用户搜索到的高转化率关键词列表，以有效提升文章曝光率、并最终引导用户下载和注册"游戏盒子"应用。
- background: 拥有多年在大型游戏发行公司或数字营销机构的从业经验，成功主导过多个爆款游戏的SEO推广项目。对各大搜索引擎的排名算法有深入研究，尤其擅长挖掘游戏玩家群体的搜索需求和潜在痛点。
- personality: 数据驱动、结果导向、逻辑严谨、思维敏捷、专注高效。
- expertise: 搜索引擎优化(SEO), 关键词研究与策略, 用户搜索意图分析, 内容营销, 游戏行业市场洞察。
- target_audience: 游戏推广公司市场部、SEO专员、内容运营、新媒体编辑。

## Skills

1. 核心关键词策略
   - 核心词拓展: 基于用户提供的核心关键词 `{keyword}`，进行同义词、近义词、相关词及缩写等多种形式的拓展。
   - 用户意图分析: 精准识别并分类用户搜索意图，包括信息获取型（如"游戏攻略"）、商业调查型（如"游戏盒子哪个好"）、交易行为型（如"游戏免费下载"）等。
   - 长尾关键词挖掘: 生成搜索量相对较低但转化意图极强的长尾关键词组合，精准触达目标用户。
   - 竞争度评估: 模拟评估关键词的竞争激烈程度，优先推荐有较高潜力的蓝海或次蓝海关键词。
   - **关键词精选**: 综合评估搜索潜力、商业价值和竞争度，从众多候选项中筛选出最具转化效果的10个核心关键词。

2. 辅助内容与市场洞察
   - 趋势词汇捕捉: 结合当前游戏热点、新游发布、版本更新等信息，融入具有时效性的关键词。
   - 内容主题关联: 提供的关键词能够直接启发相关文章的选题和创作方向，如"游戏排行榜"、"游戏评测"、"福利礼包领取"等。
   - 用户痛点关联: 挖掘用户在寻找和下载游戏时可能遇到的问题（如"安全无毒的游戏下载平台"、"游戏更新慢怎么办"），并转化为关键词。
   - 格式化输出: 能够严格按照要求，将所有关键词整合为单一文本字符串，并使用逗号进行分隔。

## Rules

1. 基本原则：
   - 最终目标导向: 所有生成的关键词都必须服务于"引导用户下载注册游戏盒子"这一核心商业目标。
   - 强相关性原则: 关键词必须与用户输入的核心关键词 `{keyword}` 及游戏下载场景高度相关，避免无关词汇。
   - 多维度覆盖: 关键词组合应覆盖从泛需求到精准需求的整个用户搜索漏斗，全面拦截潜在流量。
   - 价值优先: 优先生成具有高商业价值和转化潜力的关键词，而非仅仅追求搜索量。

2. 行为准则：
   - 直奔主题: 直接提供最终的关键词列表，不添加任何前缀、后缀、解释或说明性文字。
   - 恪守格式: 严格遵守"一段文本，逗号隔开"的输出格式，不使用任何代码块、列表标记或其他格式化元素。
   - 保持中立: 生成的关键词应保持客观，不包含主观性或夸张性的宣传语。
   - 动态优化: 根据输入关键词 `{keyword}` 的具体内容，动态调整关键词生成的侧重点和方向。

3. 限制条件：
   - **数量限制**: 最终输出的关键词数量必须严格为10个。
   - 纯文本输出: 最终结果必须是纯文本字符串，不包含任何Markdown语法或HTML标签。
   - 无引导词: 禁止在输出的开头使用如"好的，这是您需要的关键词："、"关键词列表如下："等引导性话语。
   - 内容唯一性: 输出内容仅包含关键词列表，不得包含任何其他额外信息。
   - 语言一致性: 输出的关键词语言必须与输入的 `{keyword}` 语言保持一致。

## Workflows

- 目标: 根据用户输入的核心关键词 `{keyword}`，生成一份由**10个**专业、高转化的SEO关键词组成的列表，以逗号分隔的单行文本形式输出。
- 步骤 1: 解析与诊断。接收并分析核心关键词 `{keyword}`，理解其背后的基本用户群体和游戏类型/主题。
- 步骤 2: 发散与拓展。围绕核心关键词，从"需求词"（如下载、免费、最新）、"场景词"（如盒子、平台、App）、"内容词"（如攻略、排行榜、推荐）、"问题词"（如哪个好、怎么玩）等多个维度进行关键词组合与拓展，并挖掘相关的长尾关键词。
- 步骤 3: 筛选与整合。从拓展出的海量关键词中，根据搜索热度、转化潜力及相关性进行综合排序，筛选出**最优的10个关键词**，剔除其他词汇。
- 步骤 4: 格式化输出。将筛选出的10个关键词整合为一份清单，并严格按照"关键词1,关键词2,关键词3,..."的格式生成最终的纯文本结果。
- 预期结果: 一段无任何修饰的、由**恰好10个**逗号分隔的关键词文本，可直接复制用于SEO策略部署。


## Initialization
作为游戏推广SEO策略师，你必须遵守上述Rules，按照Workflows执行任务。"""
            
            # 使用多平台API管理器
            content = self.api_manager.make_request(prompt)
            
            # 删除 <think>...</think> 标签及其中内容
            cleaned_text = re.sub(r'<think>...</think>', '', content, flags=re.DOTALL)
            
            # 处理返回的关键词，提取关键词并与原关键词组合
            keywords_text = cleaned_text.strip()
            
            # 尝试从返回文本中提取关键词（去除多余的文字说明）
            lines = keywords_text.split('\n')
            extracted_keywords = []
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('以下') and not line.startswith('这些') and not line.startswith('希望'):
                    # 移除序号和特殊字符
                    clean_line = re.sub(r'^\d+\.?\s*', '', line)
                    clean_line = re.sub(r'^[-*•]\s*', '', clean_line)
                    if clean_line and len(clean_line) > 2:
                        extracted_keywords.append(clean_line)
            
            if extracted_keywords:
                # 限制关键词数量，避免过长
                selected_keywords = extracted_keywords[:8]
                # 将原关键词放在首位，然后添加联想词
                all_keywords = [keyword] + selected_keywords
                
                # 关键词获取成功，重置熔断计数器
                self._record_api_success()
                print(f"✅ 获取联想词成功，重置熔断计数器")
                return ', '.join(all_keywords)
            else:
                print(f"🔄 使用原始关键词: {keyword}")
                return keyword
                
        except ApiExhaustedRetriesError:
            # 联想词获取失败时使用原始关键词，但需要记录熔断
            print(f"❌ 获取联想词时API重试耗尽，使用原始关键词")
            self.api_manager.show_usage_stats()
            # 联想词获取失败也应该计入熔断，因为这也是API调用
            max_retries = getattr(self.api_manager, 'max_retries', 3)
            print(f"📊 联想词API重试耗尽，增加 {max_retries} 次失败计数")
            
            # 根据API重试次数增加失败计数
            for _ in range(max_retries):
                self._record_api_failure()
            
            # 使用原始关键词，不传播异常
            return keyword
        except Exception as e:
            error_msg = str(e)
            print(f"❌ 获取联想词失败: {error_msg}")
            
            # 显示API密钥使用统计
            self.api_manager.show_usage_stats()
            
            # 对于联想词生成失败，不触发熔断，直接使用原关键词
            print(f"🔄 使用原始关键词: {keyword}")
            return keyword
            
    def generate_markdown_for_language(self, keyword, need_images=True, lang_code='zh-cn', is_final_commit=False, repo_name=None):
        """生成特定语言版本的文章 markdown"""
        try:
            # 解析keyword、自定义尾词和游戏名
            actual_keyword, custom_tail, game_name = self.parse_keyword_and_game_name(keyword)
            
            # 统一使用繁体中文作为文件夹名称
            folder_name_target_lang = self.get_language_mapping('zh-tw', repo_name)
            folder_name_keyword = self.translate_text(actual_keyword, folder_name_target_lang)
            folder_name_game_name = self.translate_text(game_name, folder_name_target_lang) if game_name else ""
            
            # 翻译关键词和游戏名到目标语言（用于文章内容）
            target_lang = self.get_language_mapping(lang_code, repo_name)
            content_keyword = self.translate_text(actual_keyword, target_lang) if lang_code == 'zh-tw' else actual_keyword
            content_game_name = self.translate_text(game_name, target_lang) if game_name and lang_code == 'zh-tw' else game_name
            
            # 创建图片目录（直接在备份目录中创建）
            # 获取仓库配置
            repo_config = None
            if repo_name:
                # 根据仓库名查找对应的配置
                enabled_repos = self.repo_manager.get_enabled_repositories()
                for repo_id, config in enabled_repos.items():
                    if config.get('name') == repo_name:
                        repo_config = config
                        break
                
            # 如果没找到配置，使用默认配置
            if not repo_config:
                repo_config = {'category': 'strategy'}
            
            image_dir, safe_keyword = self.create_image_directory(folder_name_keyword, lang_code, repo_name, repo_config)
            
            # 设置 Markdown 文件路径（直接在备份目录中创建）
            article_dir = image_dir.parent  # 去掉 /images 得到文章目录
            markdown_file = article_dir / "README.md"

            # 确保文章目录存在
            article_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取语言特定的长尾词
            long_tail_text = self.get_language_specific_long_tail(lang_code, repo_name)
            
            # 获取相关联想词
            related_keywords = self.get_related_keywords(content_keyword)
            
            # 获取文章分类信息（用于markdown头部，与配置中的路径分类不同）
            article_category = '攻略'  # 文章内容分类，用于markdown头部
            # 配置中的category用于文件路径，这里的article_category用于文章内容标记
            
            # 生成新格式的标题
            if content_game_name:
                if custom_tail:
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}，{custom_tail}"
                else:
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}"
            else:
                if custom_tail:
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}，{custom_tail}"
                else:
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}"
            
            # 准备 Markdown 头部
            markdown = f"""---
title: {new_title}
icon: {ICON}
date: {DATE}
category: {article_category}
star: false
dir:
  link: true
  collapsible: false
head:
  - - meta
    - name: keywords
      content: {related_keywords}
# 置顶配置
# sticky: 100
---

"""
            
            # 在主图之前添加游戏名下载链接
            if content_game_name:
                # 如果有游戏名，使用游戏名作为下载链接
                download_link_text = f"{content_game_name}破解版私服，外挂，修改版下载"
                download_link_url = "{{siteConfig.jumpDomain}}"
                markdown += f'''<a href="{download_link_url}" style="color:red; font-size:40px;">{download_link_text}</a>\n\n'''
            else:
                # 如果没有游戏名，使用关键词作为下载链接
                download_link_text = f"{content_keyword}破解版私服，外挂，修改版下载"
                download_link_url = "{{siteConfig.jumpDomain}}"
                markdown += f'''<a href="{download_link_url}" style="color:red; font-size:40px;">{download_link_text}</a>\n\n'''

            # 获取主图
            if need_images:
                search_game_name = content_keyword.split(" ")[0] if " " in content_keyword else content_keyword
                print(f"正在下载\"{search_game_name}\"的主图 ({lang_code})...")
                main_img = "/assets/img/download.jpg"
                self.get_main_image(f"{search_game_name} 游戏Logo", image_dir)
                if not main_img:
                    main_img = "/assets/img/download.jpg"  # 如果下载失败，使用默认图片
                
                if main_img:
                    # 将主图改为超链接下拉标签
                    download_link_url = "{{siteConfig.jumpDomain}}"
                    markdown += f'''<a href="{download_link_url}" target="_blank"><img src="{main_img}" alt="{search_game_name}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"></a>\n\n'''
            
            # 获取语言特定的提示词模板
            lang_prompt_template = self.config_manager.get_prompt_template(lang_code)
            if not lang_prompt_template:
                # 如果没有语言特定的提示词，使用默认提示词并翻译
                default_template = self.config_manager.get_prompt_template("zh-cn")
                lang_prompt_template = self.translate_text(default_template, target_lang) if lang_code == 'zh-tw' else default_template
            
            # 准备实际提示词
            actual_prompt = lang_prompt_template.replace("{keyword}", content_keyword).replace("KEYWORD", content_keyword)
            
            # 生成文案内容
            print(f"正在生成关于 '{content_keyword}' 的文案 ({lang_code})...")
            content = self.generate_article_content(actual_prompt)
            
            # 准备通用背景图并插入图片，同时添加下载链接
            if need_images:
                print(f"正在下载相关图片 ({lang_code})...")
                search_game_name = content_keyword.split(" ")[0] if " " in content_keyword else content_keyword
                random_img_data = self.prepare_random_images(search_game_name, image_dir)
                # 使用翻译后的游戏名用于下载链接
                download_game_name = content_game_name if content_game_name else content_keyword
                # 获取当前日期和文章名称
                from datetime import datetime, timezone, timedelta
                beijing_tz = timezone(timedelta(hours=8))
                current_date = datetime.now(beijing_tz).strftime('%Y/%m/%d')
                article_name = safe_keyword
                
                content_with_imgs = self.insert_random_images(
                    content, random_img_data, keyword, lang_code,
                    is_primary_language=True, repo_name=repo_name,
                    article_name=article_name, current_date=current_date
                )
            else:
                # 使用翻译后的游戏名用于下载链接
                download_game_name = content_game_name if content_game_name else content_keyword
                content_with_imgs = self.add_download_link(content, keyword)
            
            markdown += content_with_imgs
            
            # 写入文件
            with open(markdown_file, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"✅ 已生成 {LANGUAGES[lang_code]} markdown 文件：{markdown_file}")
            
            # 准备文章信息用于上传
            article_info = {
                'title': new_title,
                'keyword': content_keyword,
                'game_name': content_game_name,
                'custom_suffix': custom_tail,
                'language': lang_code,
                'folder_name': safe_keyword,
                'need_images': need_images,
                'file_path': str(markdown_file),
                'article_dir': str(article_dir),  # 返回整个文章目录
                'image_dir': str(image_dir)
            }
            
            # 注意：这里不立即上传，而是等待所有语言版本生成完成后统一处理
            # 返回文章目录路径，供后续统一上传使用
            return str(article_dir), None, None
        except ApiExhaustedRetriesError:
            # 提前终止由上层处理
            raise
        except Exception as e:
            error_msg = f"生成 {LANGUAGES.get(lang_code, lang_code)} 文章时出错: {str(e)}"
            print(f"❌ {error_msg}")
            return None, error_msg

    def generate_markdown_for_language_with_content_and_images(self, keyword, need_images=True, lang_code='zh-cn', is_final_commit=False, repo_name=None):
        """生成特定语言版本的文章 markdown 并返回内容和图片数据"""
        try:
            # 解析keyword、自定义尾词和游戏名
            actual_keyword, custom_tail, game_name = self.parse_keyword_and_game_name(keyword)
            
            # 统一使用繁体中文作为文件夹名称
            folder_name_target_lang = self.get_language_mapping('zh-tw', repo_name)
            folder_name_keyword = self.translate_text(actual_keyword, folder_name_target_lang)
            
            # 翻译关键词和游戏名到目标语言
            target_lang = self.get_language_mapping(lang_code, repo_name)
            content_keyword = self.translate_text(actual_keyword, target_lang) if lang_code == 'zh-tw' else actual_keyword
            content_game_name = self.translate_text(game_name, target_lang) if game_name and lang_code == 'zh-tw' else game_name
            
            # 创建图片目录
            repo_config = None
            if repo_name:
                enabled_repos = self.repo_manager.get_enabled_repositories()
                for repo_id, config in enabled_repos.items():
                    if config.get('name') == repo_name:
                        repo_config = config
                        break
                
            if not repo_config:
                repo_config = {'category': 'strategy'}
            
            image_dir, safe_keyword = self.create_image_directory(folder_name_keyword, lang_code, repo_name, repo_config)
            
            # 设置 Markdown 文件路径
            article_dir = image_dir.parent
            markdown_file = article_dir / "README.md"
            article_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取语言特定的长尾词
            long_tail_text = self.get_language_specific_long_tail(lang_code, repo_name)
            
            # 获取相关联想词（翻译后的）
            related_keywords = self.get_related_keywords(content_keyword)
            # 确保关键词完整翻译
            print("🔍 正在翻译关键词...")
            related_keywords = self.translate_text(related_keywords, target_lang)
            
            # 获取文章分类信息（用于markdown头部，与配置中的路径分类不同）
            article_category = '攻略'  # 文章内容分类，用于markdown头部
            # 配置中的category用于文件路径，这里的article_category用于文章内容标记
            
            # 生成翻译后的标题 - 确保所有部分都被翻译
            if content_game_name:
                if custom_tail:
                    translated_custom_tail = self.translate_text(custom_tail, target_lang) if lang_code == 'zh-tw' else custom_tail
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}，{translated_custom_tail}"
                else:
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}"
            else:
                if custom_tail:
                    translated_custom_tail = self.translate_text(custom_tail, target_lang) if lang_code == 'zh-tw' else custom_tail
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}，{translated_custom_tail}"
                else:
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}"
            
            # 确保标题完整翻译
            print(f"🔍 正在完整翻译标题...")
            new_title = self.translate_text(new_title, target_lang)
            
            # 准备 Markdown 头部
            markdown = f"""---
title: {new_title}
icon: {ICON}
date: {DATE}
category: {article_category}
star: false
dir:
  link: true
  collapsible: false
head:
  - - meta
    - name: keywords
      content: {related_keywords}
# 置顶配置
# sticky: 100
---

"""
            
            # 添加翻译后的下载链接
            if content_game_name:
                download_link_text = f"{content_game_name}破解版私服，外挂，修改版下载"
            else:
                download_link_text = f"{content_keyword}破解版私服，外挂，修改版下载"
            
            markdown += f'''<a href="{{{{siteConfig.jumpDomain}}}}" style="color:red; font-size:40px;">{download_link_text}</a>\n\n'''

            # 复制主图（使用与主语言相同的图片）
            if need_images:
                search_game_name = content_keyword.split(" ")[0] if " " in content_keyword else content_keyword
                print(f"正在下载\"{search_game_name}\"的主图 ({lang_code})...")
                main_img = "/assets/img/download.jpg"
                self.get_main_image(f"{search_game_name} 游戏Logo", image_dir)
                if not main_img:
                    main_img = "/assets/img/download.jpg"
                
                if main_img:
                    markdown += f'''<a href="{{{{siteConfig.jumpDomain}}}}" target="_blank"><img src="{main_img}" alt="{search_game_name}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"></a>\n\n'''
            
            # 获取语言特定的提示词模板
            lang_prompt_template = self.config_manager.get_prompt_template(lang_code) if self.config_manager else None
            if not lang_prompt_template:
                # 如果没有语言特定的提示词，使用默认提示词并翻译
                default_prompt = f"请写一篇关于{content_keyword}的详细攻略文章，包含游戏介绍、玩法技巧、角色推荐等内容。"
                lang_prompt_template = self.translate_text(default_prompt, target_lang) if lang_code == 'zh-tw' else default_prompt
            
            # 准备实际提示词
            actual_prompt = lang_prompt_template.replace("{keyword}", content_keyword).replace("KEYWORD", content_keyword)
            
            # 生成文案内容
            print(f"正在生成关于 '{content_keyword}' 的文案 ({lang_code})...")
            content = self.generate_article_content(actual_prompt)
            
            # 准备通用背景图并插入图片，同时添加下载链接
            shared_image_data = None
            if need_images:
                print(f"正在下载相关图片 ({lang_code})...")
                search_game_name = content_keyword.split(" ")[0] if " " in content_keyword else content_keyword
                shared_image_data = self.prepare_random_images(search_game_name, image_dir)
                # 使用翻译后的游戏名用于下载链接
                download_game_name = content_game_name if content_game_name else content_keyword
                # 获取当前日期和文章名称
                from datetime import datetime, timezone, timedelta
                beijing_tz = timezone(timedelta(hours=8))
                current_date = datetime.now(beijing_tz).strftime('%Y/%m/%d')
                article_name = safe_keyword
                
                content_with_imgs = self.insert_random_images(
                    content, shared_image_data, keyword, lang_code, 
                    is_primary_language=True, repo_name=repo_name, 
                    article_name=article_name, current_date=current_date
                )
            else:
                # 使用翻译后的游戏名用于下载链接
                download_game_name = content_game_name if content_game_name else content_keyword
                content_with_imgs = self.add_download_link(content, keyword)
            
            markdown += content_with_imgs
            
            # 写入文件
            with open(markdown_file, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"✅ 已生成 {LANGUAGES[lang_code]} markdown 文件：{markdown_file}")
            
            return str(article_dir), None, None, content_with_imgs, shared_image_data
        except ApiExhaustedRetriesError:
            # 重新抛出熔断异常，让上层处理
            raise
        except Exception as e:
            error_msg = f"生成 {LANGUAGES.get(lang_code, lang_code)} 文章时出错: {str(e)}"
            print(f"❌ {error_msg}")
            return None, error_msg, None, None, None

    def generate_markdown_for_language_with_content(self, keyword, need_images=True, lang_code='zh-cn', is_final_commit=False, repo_name=None):
        """生成特定语言版本的文章 markdown，并返回生成的内容用于翻译"""
        try:
            # 解析keyword、自定义尾词和游戏名
            actual_keyword, custom_tail, game_name = self.parse_keyword_and_game_name(keyword)
            
            # 统一使用繁体中文作为文件夹名称
            folder_name_target_lang = self.get_language_mapping('zh-tw', repo_name)
            folder_name_keyword = self.translate_text(actual_keyword, folder_name_target_lang)
            folder_name_game_name = self.translate_text(game_name, folder_name_target_lang) if game_name else ""
            
            # 对于主语言，不需要翻译关键词
            content_keyword = actual_keyword
            content_game_name = game_name
            
            # 创建图片目录（直接在备份目录中创建）
            repo_config = None
            if repo_name:
                enabled_repos = self.repo_manager.get_enabled_repositories()
                for repo_id, config in enabled_repos.items():
                    if config.get('name') == repo_name:
                        repo_config = config
                        break
                
            if not repo_config:
                repo_config = {'category': 'strategy'}
            
            image_dir, safe_keyword = self.create_image_directory(folder_name_keyword, lang_code, repo_name, repo_config)
            
            # 设置 Markdown 文件路径
            article_dir = image_dir.parent
            markdown_file = article_dir / "README.md"
            article_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取语言特定的长尾词
            long_tail_text = self.get_language_specific_long_tail(lang_code, repo_name)
            
            # 获取相关联想词
            related_keywords = self.get_related_keywords(content_keyword)
            
            # 获取文章分类信息（用于markdown头部，与配置中的路径分类不同）
            article_category = '攻略'  # 文章内容分类，用于markdown头部
            # 配置中的category用于文件路径，这里的article_category用于文章内容标记
            
            # 生成标题
            if content_game_name:
                if custom_tail:
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}，{custom_tail}"
                else:
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}"
            else:
                if custom_tail:
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}，{custom_tail}"
                else:
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}"
            
            # 准备 Markdown 头部
            markdown = f"""---
title: {new_title}
icon: {ICON}
date: {DATE}
category: {article_category}
star: false
dir:
  link: true
  collapsible: false
head:
  - - meta
    - name: keywords
      content: {related_keywords}
# 置顶配置
# sticky: 100
---

"""
            
            # 添加下载链接
            if content_game_name:
                download_link_text = f"{content_game_name}破解版私服，外挂，修改版下载"
            else:
                download_link_text = f"{content_keyword}破解版私服，外挂，修改版下载"
            
            markdown += f'''<a href="{{{{siteConfig.jumpDomain}}}}" style="color:red; font-size:40px;">{download_link_text}</a>\n\n'''

            # 获取主图
            if need_images:
                search_game_name = content_keyword.split(" ")[0] if " " in content_keyword else content_keyword
                print(f"正在下载\"{search_game_name}\"的主图 ({lang_code})...")
                main_img = "/assets/img/download.jpg"
                self.get_main_image(f"{search_game_name} 游戏Logo", image_dir)
                if not main_img:
                    main_img = "/assets/img/download.jpg"
                
                if main_img:
                    markdown += f'''<a href="{{{{siteConfig.jumpDomain}}}}" target="_blank"><img src="{main_img}" alt="{search_game_name}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"></a>\n\n'''
            
            # 获取提示词模板
            lang_prompt_template = self.config_manager.get_prompt_template(lang_code)
            if not lang_prompt_template:
                lang_prompt_template = self.config_manager.get_prompt_template("zh-cn")
            
            actual_prompt = lang_prompt_template.replace("{keyword}", content_keyword).replace("KEYWORD", content_keyword)
            
            # 生成文案内容
            print(f"正在生成关于 '{content_keyword}' 的文案 ({lang_code})...")
            content = self.generate_article_content(actual_prompt)
            
            # 准备背景图并插入
            if need_images:
                print(f"正在下载相关图片 ({lang_code})...")
                search_game_name = content_keyword.split(" ")[0] if " " in content_keyword else content_keyword
                random_img_data = self.prepare_random_images(search_game_name, image_dir)
                # 获取当前日期和文章名称
                from datetime import datetime, timezone, timedelta
                beijing_tz = timezone(timedelta(hours=8))
                current_date = datetime.now(beijing_tz).strftime('%Y/%m/%d')
                article_name = safe_keyword
                
                content_with_imgs = self.insert_random_images(
                    content, random_img_data, keyword, lang_code,
                    is_primary_language=True, repo_name=repo_name,
                    article_name=article_name, current_date=current_date
                )
            else:
                content_with_imgs = self.add_download_link(content, keyword)
            
            markdown += content_with_imgs
            
            # 写入文件
            with open(markdown_file, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"✅ 已生成 {LANGUAGES[lang_code]} markdown 文件：{markdown_file}")
            
            # 返回文章目录路径和生成的内容
            print(f"🔍 主语言内容长度: {len(content_with_imgs)} 字符")
            print(f"🔍 主语言内容预览: {content_with_imgs[:200]}...")
            return str(article_dir), None, None, content_with_imgs
        except ApiExhaustedRetriesError:
            raise
        except Exception as e:
            error_msg = f"生成 {LANGUAGES.get(lang_code, lang_code)} 文章时出错: {str(e)}"
            print(f"❌ {error_msg}")
            return None, error_msg, None, None

    def generate_translated_markdown_with_shared_images(self, keyword, need_images=True, lang_code='zh-tw', primary_content="", shared_image_data=None, is_final_commit=False, repo_name=None):
        """生成翻译版本的文章 markdown - 使用共享图片资源"""
        try:
            # 解析keyword、自定义尾词和游戏名
            actual_keyword, custom_tail, game_name = self.parse_keyword_and_game_name(keyword)
            
            # 统一使用繁体中文作为文件夹名称
            folder_name_target_lang = self.get_language_mapping('zh-tw', repo_name)
            folder_name_keyword = self.translate_text(actual_keyword, folder_name_target_lang)
            
            # 翻译关键词和游戏名到目标语言
            target_lang = self.get_language_mapping(lang_code, repo_name)
            content_keyword = self.translate_text(actual_keyword, target_lang) if lang_code == 'zh-tw' else actual_keyword
            content_game_name = self.translate_text(game_name, target_lang) if game_name and lang_code == 'zh-tw' else game_name
            
            # 创建图片目录
            repo_config = None
            if repo_name:
                enabled_repos = self.repo_manager.get_enabled_repositories()
                for repo_id, config in enabled_repos.items():
                    if config.get('name') == repo_name:
                        repo_config = config
                        break
                
            if not repo_config:
                repo_config = {'category': 'strategy'}
            
            image_dir, safe_keyword = self.create_image_directory(folder_name_keyword, lang_code, repo_name, repo_config)
            
            # 设置 Markdown 文件路径
            article_dir = image_dir.parent
            markdown_file = article_dir / "README.md"
            article_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取语言特定的长尾词
            long_tail_text = self.get_language_specific_long_tail(lang_code, repo_name)
            
            # 获取相关联想词（翻译后的）
            related_keywords = self.get_related_keywords(content_keyword)
            # 确保关键词完整翻译
            print("🔍 正在翻译关键词...")
            related_keywords = self.translate_text(related_keywords, target_lang)
            
            # 获取文章分类信息（用于markdown头部，与配置中的路径分类不同）
            article_category = '攻略'  # 文章内容分类，用于markdown头部
            # 配置中的category用于文件路径，这里的article_category用于文章内容标记
            
            # 生成翻译后的标题 - 确保所有部分都被翻译
            if content_game_name:
                if custom_tail:
                    translated_custom_tail = self.translate_text(custom_tail, target_lang) if lang_code == 'zh-tw' else custom_tail
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}，{translated_custom_tail}"
                else:
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}"
            else:
                if custom_tail:
                    translated_custom_tail = self.translate_text(custom_tail, target_lang) if lang_code == 'zh-tw' else custom_tail
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}，{translated_custom_tail}"
                else:
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}"
            
            # 确保标题完整翻译
            print(f"🔍 正在完整翻译标题...")
            new_title = self.translate_text(new_title, target_lang)
            
            # 准备 Markdown 头部
            markdown = f"""---
title: {new_title}
icon: {ICON}
date: {DATE}
category: {article_category}
star: false
dir:
  link: true
  collapsible: false
head:
  - - meta
    - name: keywords
      content: {related_keywords}
# 置顶配置
# sticky: 100
---

"""
            
            # 添加翻译后的下载链接
            if content_game_name:
                download_link_text = f"{content_game_name}破解版私服，外挂，修改版下载"
            else:
                download_link_text = f"{content_keyword}破解版私服，外挂，修改版下载"
            
            markdown += f'''<a href="{{{{siteConfig.jumpDomain}}}}" style="color:red; font-size:40px;">{download_link_text}</a>\n\n'''

            # 使用共享主图（不下载，直接使用主语言的图片）
            if need_images:
                search_game_name = content_keyword.split(" ")[0] if " " in content_keyword else content_keyword
                print(f"正在使用共享主图 ({lang_code})...")
                # 直接使用默认主图，不下载
                main_img = "/assets/img/download.jpg"
                
                if main_img:
                    markdown += f'''<a href="{{{{siteConfig.jumpDomain}}}}" target="_blank"><img src="{main_img}" alt="{search_game_name}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"></a>\n\n'''
            
            # 翻译主语言的内容
            print(f"正在翻译文章内容到 {LANGUAGES[lang_code]}...")
            print(f"🔍 接收到的主语言内容长度: {len(primary_content) if primary_content else 0} 字符")
            if primary_content:
                print(f"🔍 主语言内容预览: {primary_content[:200]}...")
                
                # 移除下载链接，重新翻译内容部分
                content_without_links = re.sub(r'\[.*?\]\(\{\{siteConfig\.jumpDomain\}\}\)\n\n', '', primary_content)
                print(f"🔍 移除下载链接后内容长度: {len(content_without_links)} 字符")
                
                # 分段翻译长内容，避免API长度限制
                translated_content = self.translate_long_content(content_without_links, target_lang)
                print(f"🔍 翻译后内容长度: {len(translated_content)} 字符")
                
                # 重新添加翻译后的下载链接
                translated_content_with_links = self.add_download_link(translated_content, keyword)
            else:
                translated_content_with_links = "翻译内容为空"
                print("⚠️ 警告: primary_content 为空，无法进行翻译")
            
            # 使用共享的图片数据，替换为图床URL
            if need_images and shared_image_data:
                print(f"正在使用共享图片数据 ({lang_code})...")
                # 获取当前日期和文章名称
                article_name = safe_keyword
                from datetime import datetime
                current_date = datetime.now(beijing_tz).strftime('%Y/%m/%d')
                # 替换图片路径为图床URL
                final_content = self._replace_images_with_cdn_urls(translated_content_with_links, shared_image_data, repo_name, article_name, current_date)
            else:
                final_content = translated_content_with_links
            
            markdown += final_content
            
            # 写入文件
            with open(markdown_file, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"✅ 已生成 {LANGUAGES[lang_code]} 翻译版本 markdown 文件：{markdown_file}")
            
            return str(article_dir), None, None
        except ApiExhaustedRetriesError:
            raise
        except Exception as e:
            error_msg = f"生成 {LANGUAGES.get(lang_code, lang_code)} 翻译版本时出错: {str(e)}"
            print(f"❌ {error_msg}")
            return None, error_msg, None

    def generate_translated_markdown_for_language(self, keyword, need_images=True, lang_code='zh-tw', primary_content="", is_final_commit=False, repo_name=None):
        """生成翻译版本的文章 markdown"""
        try:
            # 解析keyword、自定义尾词和游戏名
            actual_keyword, custom_tail, game_name = self.parse_keyword_and_game_name(keyword)
            
            # 统一使用繁体中文作为文件夹名称
            folder_name_target_lang = self.get_language_mapping('zh-tw', repo_name)
            folder_name_keyword = self.translate_text(actual_keyword, folder_name_target_lang)
            
            # 翻译关键词和游戏名到目标语言
            target_lang = self.get_language_mapping(lang_code, repo_name)
            content_keyword = self.translate_text(actual_keyword, target_lang) if lang_code == 'zh-tw' else actual_keyword
            content_game_name = self.translate_text(game_name, target_lang) if game_name and lang_code == 'zh-tw' else game_name
            
            # 创建图片目录
            repo_config = None
            if repo_name:
                enabled_repos = self.repo_manager.get_enabled_repositories()
                for repo_id, config in enabled_repos.items():
                    if config.get('name') == repo_name:
                        repo_config = config
                        break
                
            if not repo_config:
                repo_config = {'category': 'strategy'}
            
            image_dir, safe_keyword = self.create_image_directory(folder_name_keyword, lang_code, repo_name, repo_config)
            
            # 设置 Markdown 文件路径
            article_dir = image_dir.parent
            markdown_file = article_dir / "README.md"
            article_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取语言特定的长尾词
            long_tail_text = self.get_language_specific_long_tail(lang_code, repo_name)
            
            # 获取相关联想词（翻译后的）
            related_keywords = self.get_related_keywords(content_keyword)
            # 确保关键词完整翻译
            print("🔍 正在翻译关键词...")
            related_keywords = self.translate_text(related_keywords, target_lang)
            
            # 获取文章分类信息（用于markdown头部，与配置中的路径分类不同）
            article_category = '攻略'  # 文章内容分类，用于markdown头部
            # 配置中的category用于文件路径，这里的article_category用于文章内容标记
            
            # 生成翻译后的标题 - 确保所有部分都被翻译
            if content_game_name:
                if custom_tail:
                    translated_custom_tail = self.translate_text(custom_tail, target_lang) if lang_code == 'zh-tw' else custom_tail
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}，{translated_custom_tail}"
                else:
                    new_title = f"{content_keyword}？{content_game_name}破解版私服，外挂，修改版，{long_tail_text}"
            else:
                if custom_tail:
                    translated_custom_tail = self.translate_text(custom_tail, target_lang) if lang_code == 'zh-tw' else custom_tail
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}，{translated_custom_tail}"
                else:
                    new_title = f"{content_keyword}？破解版私服，外挂，修改版，{long_tail_text}"
            
            # 确保标题完整翻译
            print(f"🔍 正在完整翻译标题...")
            new_title = self.translate_text(new_title, target_lang)
            
            # 准备 Markdown 头部
            markdown = f"""---
title: {new_title}
icon: {ICON}
date: {DATE}
category: {article_category}
star: false
dir:
  link: true
  collapsible: false
head:
  - - meta
    - name: keywords
      content: {related_keywords}
# 置顶配置
# sticky: 100
---

"""
            
            # 添加翻译后的下载链接
            if content_game_name:
                download_link_text = f"{content_game_name}破解版私服，外挂，修改版下载"
            else:
                download_link_text = f"{content_keyword}破解版私服，外挂，修改版下载"
            
            markdown += f'''<a href="{{{{siteConfig.jumpDomain}}}}" style="color:red; font-size:40px;">{download_link_text}</a>\n\n'''

            # 使用共享主图（不下载，直接使用主语言的图片）
            if need_images:
                search_game_name = content_keyword.split(" ")[0] if " " in content_keyword else content_keyword
                print(f"正在使用共享主图 ({lang_code})...")
                # 直接使用默认主图，不下载
                main_img = "/assets/img/download.jpg"
                
                if main_img:
                    markdown += f'''<a href="{{{{siteConfig.jumpDomain}}}}" target="_blank"><img src="{main_img}" alt="{search_game_name}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"></a>\n\n'''
            
            # 翻译主语言的内容
            print(f"正在翻译文章内容到 {LANGUAGES[lang_code]}...")
            print(f"🔍 接收到的主语言内容长度: {len(primary_content) if primary_content else 0} 字符")
            if primary_content:
                print(f"🔍 主语言内容预览: {primary_content[:200]}...")
                
                # 移除下载链接，重新翻译内容部分
                content_without_links = re.sub(r'\[.*?\]\(\{\{siteConfig\.jumpDomain\}\}\)\n\n', '', primary_content)
                print(f"🔍 移除下载链接后内容长度: {len(content_without_links)} 字符")
                
                # 分段翻译长内容，避免API长度限制
                translated_content = self.translate_long_content(content_without_links, target_lang)
                print(f"🔍 翻译后内容长度: {len(translated_content)} 字符")
                
                # 重新添加翻译后的下载链接
                translated_content_with_links = self.add_download_link(translated_content, keyword)
            else:
                translated_content_with_links = "翻译内容为空"
                print("⚠️ 警告: primary_content 为空，无法进行翻译")
            
            # 使用共享图片数据（不下载，直接使用主语言的图片）
            if need_images:
                print(f"正在使用共享图片数据 ({lang_code})...")
                # 翻译版本不应该下载图片，应该使用共享的图片数据
                # 这里需要从主语言版本获取图片数据，但当前方法没有接收这个参数
                # 暂时不插入图片，只使用文本内容
                final_content = translated_content_with_links
            else:
                final_content = translated_content_with_links
            
            markdown += final_content
            
            # 写入文件
            with open(markdown_file, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"✅ 已生成 {LANGUAGES[lang_code]} 翻译版本 markdown 文件：{markdown_file}")
            
            return str(article_dir), None, None
        except ApiExhaustedRetriesError:
            raise
        except Exception as e:
            error_msg = f"生成 {LANGUAGES.get(lang_code, lang_code)} 翻译版本时出错: {str(e)}"
            print(f"❌ {error_msg}")
            return None, error_msg, None

    def generate_markdown(self, keyword, need_images=True, is_final_commit=False, default_repo_name=None, repo_config=None):
        """生成多语言版本的文章 markdown - 使用主语言内容翻译模式"""
        results = {}
        all_usage_records = []
        primary_content = None
        
        # 获取所有语言代码
        language_codes = list(LANGUAGES.keys())
        
        # 从仓库配置中获取主语言，如果没有配置则使用默认值
        if repo_config and 'primary_language' in repo_config:
            primary_lang = repo_config['primary_language']
            print(f"使用仓库配置的主语言: {primary_lang}")
        else:
            primary_lang = 'zh-cn'  # 默认主语言
            print(f"使用默认主语言: {primary_lang}")
        
        # 首先生成主语言版本，获取内容和图片数据
        print(f"\n--- 开始生成主语言 {LANGUAGES[primary_lang]} 版本 ---")
        file_path, error, usage_record, primary_content, shared_image_data = self.generate_markdown_for_language_with_content_and_images(
            keyword, need_images, primary_lang, False, default_repo_name
        )
        
        results[primary_lang] = {
            'file': file_path,
            'error': error,
            'language': LANGUAGES[primary_lang],
            'usage_record': usage_record
        }
        
        if usage_record:
            all_usage_records.append(usage_record)
        
        if not primary_content or error:
            print(f"❌ 主语言版本生成失败，无法继续生成其他语言版本")
            return results, all_usage_records
        
        # 为其他语言生成翻译版本
        for lang_code in language_codes:
            if lang_code == primary_lang:
                continue  # 跳过主语言，已经生成了
                
            print(f"\n--- 开始生成翻译版本 {LANGUAGES[lang_code]} ---")
            print("等待2秒后开始翻译...")
            time.sleep(2)
            
            # 使用共享图片模式生成翻译文章
            file_path, error, usage_record = self.generate_translated_markdown_with_shared_images(
                keyword, need_images, lang_code, primary_content, shared_image_data, False, default_repo_name
            )
            
            results[lang_code] = {
                'file': file_path,
                'error': error,
                'language': LANGUAGES[lang_code],
                'usage_record': usage_record
            }
            
            if usage_record:
                all_usage_records.append(usage_record)
            
            # 添加延迟避免翻译API限制
            if lang_code != language_codes[-1]:
                print("等待2秒后处理下一语言...")
                time.sleep(2)
        
        # 所有语言版本生成完成后，统一上传和备份
        print(f"\n📤 所有语言版本生成完成，开始统一上传和备份...")
        usage_records = self.upload_and_backup_article(results, keyword, is_final_commit)
        
        return results, usage_records

    def upload_and_backup_article(self, results, keyword, is_final_commit=False):
        """统一上传和备份文章的所有语言版本"""
        all_upload_results = []
        
        try:
            # 获取启用的远程仓库
            enabled_repos = self.repo_manager.get_enabled_repositories()
            remote_repos = {k: v for k, v in enabled_repos.items() if v['type'] == 'git'}
            local_repos = {k: v for k, v in enabled_repos.items() if v['type'] == 'local'}
            
            if not remote_repos:
                print("❌ 没有启用的远程仓库")
                return []
            
            print(f"📤 开始上传到 {len(remote_repos)} 个远程仓库...")
            
            # 统计Git仓库数量
            if remote_repos and is_final_commit:
                print(f"🚀 这是最后一次提交，{len(remote_repos)} 个Git仓库将开启自动部署")
            
            # 收集所有成功的语言版本
            successful_results = []
            for lang_code, result in results.items():
                if result['error'] or not result['file']:
                    print(f"❌ 跳过 {lang_code} 版本：{result['error']}")
                    continue
                successful_results.append((lang_code, result))
            
            # 为每个语言版本上传到对应的远程仓库
            for i, (lang_code, result) in enumerate(successful_results):
                # 只有最后一个语言版本才触发自动部署
                current_is_final_commit = is_final_commit and (i == len(successful_results) - 1)
                
                if current_is_final_commit:
                    print(f"\n--- 上传 {LANGUAGES[lang_code]} 版本 (最后一次提交，将触发自动部署) ---")
                else:
                    print(f"\n--- 上传 {LANGUAGES[lang_code]} 版本 (普通提交，跳过自动部署) ---")
                
                # 准备文章信息
                article_info = {
                    'title': keyword,
                    'keyword': keyword,
                    'game_name': '',
                    'custom_suffix': '',
                    'language': lang_code,
                    'folder_name': Path(result['file']).parent.name,
                    'need_images': True,
                    'file_path': result['file'],
                    'image_dir': str(Path(result['file']).parent / 'images')
                }
                
                # 收集当前语言版本的所有上传结果
                current_lang_results = []
                
                # 上传到远程仓库
                for repo_id, repo_config in remote_repos.items():
                    if current_is_final_commit:
                        print(f"  📁 上传到 {repo_config['name']} (最后一次提交，将触发自动部署)...")
                    else:
                        print(f"  📁 上传到 {repo_config['name']} (普通提交，跳过自动部署)...")
                    
                    # 上传到远程Git仓库
                    upload_result = self.repo_manager.upload_to_git_repository(
                        str(Path(result['file']).parent), repo_config, article_info, repo_id, current_is_final_commit
                    )
                    
                    current_lang_results.append(upload_result)
                    
                    if upload_result['success']:
                        if current_is_final_commit:
                            print(f"    ✅ 上传成功 (已触发自动部署): {upload_result['target_path']}")
                        else:
                            print(f"    ✅ 上传成功 (跳过自动部署): {upload_result['target_path']}")
                        
                        # 备份到本地仓库
                        if local_repos:
                            local_repo_config = list(local_repos.values())[0]
                            backup_result = self.repo_manager.upload_to_local_repository(
                                str(Path(result['file']).parent), local_repo_config, article_info, repo_config
                            )
                            
                            current_lang_results.append(backup_result)
                            
                            if backup_result['success']:
                                print(f"    📁 备份成功: {backup_result['target_path']}")
                            else:
                                print(f"    ⚠️ 备份失败: {backup_result['error']}")
                    else:
                        print(f"    ❌ 上传失败: {upload_result['error']}")
                
                # 为当前语言版本创建使用记录
                usage_record = self.repo_manager.create_usage_record(current_lang_results, article_info)
                all_upload_results.append(usage_record)
            
            print(f"✅ 文章上传和备份完成")
            return all_upload_results
            
        except Exception as e:
            print(f"❌ 上传和备份过程中出错: {e}")
            return []

    def log_error(self, keyword, error_msg):
        """记录失败的文章信息"""
        try:
            timestamp = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")
            error_entry = {
                "timestamp": timestamp,
                "keyword": keyword,
                "error": error_msg
            }
            
            # 确保日志目录存在
            log_dir = Path("./logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 追加到日志文件
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(error_entry, ensure_ascii=False) + "\n")
                
            print(f"错误已记录到 {ERROR_LOG}")
        except Exception as e:
            print(f"记录错误时出现问题: {e}")

    def process_article_from_title(self, title_data, need_images=True, is_final_commit=False, title_index=None):
        """从标题数据生成文章"""
        try:
            # 从标题数据中提取信息
            article_title = title_data.get('title', '')
            custom_suffix = title_data.get('custom_suffix', '')
            game_name = title_data.get('game_name', '')
            
            # 构建关键词字符串
            # 使用 sanitize_filename 处理特殊字符，确保标题安全
            article_title = self.sanitize_filename(article_title)
            custom_suffix = self.sanitize_filename(custom_suffix)
            game_name = self.sanitize_filename(game_name)
            
            if custom_suffix and game_name:
                keyword = f"{article_title}----{custom_suffix}----{game_name}"
            elif game_name:
                keyword = f"{article_title}----{game_name}"
            else:
                keyword = article_title
            
            print(f"正在为标题生成文章: {keyword}")
            
            # 如果提供了title_index，使用发布管理器的逻辑
            if title_index is not None:
                # 导入发布管理器
                from publish_manager import PublishManager
                publish_manager = PublishManager(self.config_manager)
                
                # 确定目标网站
                target_site = publish_manager.determine_target_site(title_index)
                
                # 获取目标仓库
                repo_info = publish_manager.get_repository_for_site(target_site)
                if not repo_info:
                    raise Exception(f"无法获取网站 {target_site} 的仓库配置")
                
                repo_id, repo_config = repo_info
                
                # 判断是否为该网站的最后一次上传
                is_final_commit_for_site = is_final_commit
                
                print(f"   目标网站: {target_site} ({repo_config['name']})")
                print(f"   部署状态: {'🚀 最后一次提交，将触发自动部署' if is_final_commit_for_site else '📝 普通提交，跳过自动部署'}")
                
                # 生成文章内容（只生成，不上传到所有仓库）
                results = publish_manager.generate_article_content_only(keyword, need_images, repo_config.get('name', repo_id), repo_config)
                
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
                    upload_results = publish_manager.upload_to_specific_repository(results, repo_id, repo_config, is_final_commit_for_site)
                    
                    return {
                        'success': True,
                        'success_count': success_count,
                        'error_count': error_count,
                        'results': results,
                        'usage_records': upload_results,
                        'target_site': target_site,
                        'repo_name': repo_config['name']
                    }
                else:
                    return {
                        'success': False,
                        'success_count': 0,
                        'error_count': error_count,
                        'error': '所有语言版本生成失败',
                        'results': results,
                        'usage_records': []
                    }
            else:
                # 原有的逻辑：生成多语言版本的文章并上传到所有仓库
                # 为了避免使用 "temp" 目录，获取第一个启用的仓库名作为默认值
                enabled_repos = self.repo_manager.get_enabled_repositories()
                git_repos = {k: v for k, v in enabled_repos.items() if v['type'] == 'git'}
                default_repo_name = None
                first_repo_config = None
                if git_repos:
                    first_repo = list(git_repos.values())[0]
                    default_repo_name = first_repo.get('name', 'default')
                    first_repo_config = first_repo
                
                results, all_usage_records = self.generate_markdown(keyword, need_images, is_final_commit, default_repo_name, first_repo_config)
                
                # 处理结果
                success_count = 0
                error_count = 0
                
                for lang_code, result in results.items():
                    if result['error']:
                        self.log_error(f"{keyword} ({result['language']})", result['error'])
                        error_count += 1
                    else:
                        success_count += 1
                
                return {
                    'success': success_count > 0,
                    'success_count': success_count,
                    'error_count': error_count,
                    'results': results,
                    'usage_records': all_usage_records
                }
            
        except ApiExhaustedRetriesError as e:
            error_msg = f"处理文章时达到最大重试次数: {str(e)}"
            print(f"❌ {error_msg}")
            self.log_error(keyword, error_msg)
            # 向上抛出以终止流程
            raise
        except Exception as e:
            error_msg = f"处理文章时出错: {str(e)}"
            print(f"❌ {error_msg}")
            self.log_error(keyword, error_msg)
            return {
                'success': False,
                'success_count': 0,
                'error_count': 1,
                'error': error_msg,
                'usage_records': []
            }
