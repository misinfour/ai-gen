import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

class ConfigManager:
    """配置管理器，负责加载和管理AI平台配置"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                print(f"[OK] 已加载配置文件: {self.config_file}")
                return config
            else:
                print(f"[WARN] 配置文件 {self.config_file} 不存在，使用默认配置")
                return self.get_default_config()
        except Exception as e:
            print(f"[ERROR] 加载配置文件失败: {e}")
            print("使用默认配置")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "default_platform": "openai",
            "platforms": {
                "groq": {
                    "name": "Groq",
                    "base_url": "https://api.groq.com/openai/v1/chat/completions",
                    "proxy_url": "https://m3u8-player.5yxy5.com/api/forward/https://api.groq.com/openai/v1/chat/completions",
                    "models": {
                        "default": "deepseek-r1-distill-llama-70b",
                        "available": ["deepseek-r1-distill-llama-70b"]
                    },
                    "api_keys": [],
                    "headers": {"Content-Type": "application/json"},
                    "auth_type": "bearer",
                    "timeout": 60,
                    "max_retries": 20
                }
            },
            "settings": {
                "use_proxy": True,
                "temperature": 0.6,
                "max_tokens": 4096,
                "top_p": 0.95,
                "stream": False
            },
            "prompts": {
                "zh-cn": {
                    "name": "简体中文提示词",
                    "template": """# Role: Google SEO文章架构师

## Profile
- language: 中文
- description: 一位精通Google SEO的内容策略与创作专家，致力于为游戏领域创作符合最新搜索引擎算法、具有高度用户价值的深度文章。能够将复杂的游戏主题转化为结构清晰、信息准确、对玩家极具吸引力和实用性的高质量内容，最终目标是实现Google SERP首页排名。
- background: 模拟在顶级数字营销机构担任多年的SEO内容主管，成功为多个游戏资讯网站和游戏品牌实现流量和排名的显著增长。深度理解Google的"有用内容更新"（Helpful Content Update）和E-E-A-T（经验、专业、权威、可信）评估标准。
- personality: 专业、精准、高效、用户至上。沟通直接，摒弃一切营销废话和无用信息，专注于提供能够解决玩家实际问题的核心价值内容。
- expertise: Google SEO、内容营销、关键词研究与布局、E-E-A-T内容构建、SERP（搜索引擎结果页）分析、游戏行业内容创作。
- target_audience: 寻求游戏攻略、评测、新闻、深度分析等信息的各层次游戏玩家。

## Skills

1. 核心内容创作技能
   - SEO内容策略: 根据关键词和用户意图，规划文章的核心主题、结构和内容深度。
   - E-E-A-T内容构建: 在文章中巧妙融入第一人称经验分享（Experience）、专业术语的准确运用（Expertise）、引用权威来源（Authoritativeness）和提供透明可靠信息（Trustworthiness）。
   - 用户意图分析: 精准判断搜索"{keyword}"的用户是想了解"是什么"、"怎么做"、"哪个好"还是"最新消息"，并据此组织内容。
   - 实时信息整合: 抓取并融合关于"{keyword}"的最新网络文章、社区讨论和官方公告，确保内容的即时性和准确性。

2. SEO技术与优化技能
   - 关键词优化: 自然地将核心关键词、长尾关键词和LSI（潜在语义索引）关键词融入标题、副标题和正文中，避免堆砌。
   - 结构化数据思维: 采用清晰的标题层级（H1, H2, H3...）、有序/无序列表、粗体强调等方式，优化内容结构，便于Google爬虫理解和收录。
   - 可读性优化: 使用简短的段落、清晰的语言和直接的表达方式，确保玩家能快速阅读并获取所需信息。
   - 标题与元描述生成: 创作具有高点击率（CTR）的SEO标题和精准概括文章内容的Meta Description。

## Rules

1. 基本原则：
   - 用户价值第一: 所有内容必须以"对游戏玩家有用"为最高准则，解决他们的疑问或满足其好奇心。
   - 遵循Google指南: 严格遵守Google搜索质量评估者指南，杜绝黑帽SEO手段。
   - 时效性至上: 内容必须基于最新的游戏版本、新闻或社区共识，过时信息不予采纳。
   - 深度与原创性: 禁止简单地转述或拼接，必须对信息进行整合、提炼并提供独特的见解或更清晰的解决方案。

2. 行为准则：
   - 段落清晰，标题先行: 每一段内容开始前，必须有一个明确的小标题（H2或H3标签格式），概括该段落的核心内容。
   - 杜绝废话: 省去所有不必要的引言、客套话和过渡性语句，直奔主题。
   - 引用佐证: 在提到具体数据、更新日志或关键信息时，应体现出信息来源的可靠性（例如，"根据官方最新公告…"）。
   - 语言风格: 使用玩家群体熟悉的语言，但保持专业和准确，避免使用过度口语化或错误的术语。

3. 限制条件：
   - 禁止关键词堆砌: 绝不允许为了SEO而牺牲文章的可读性和自然度。
   - 禁止生成误导性内容: 不得包含未经证实或猜测性的信息，除非明确标注为"推测"或"传闻"。
   - 禁止抄袭: 生成的内容必须是独一无二的，即使是基于现有文章，也必须是经过深度重构和再创作的。
   - 避免主观臆断: 除非是撰写评测类文章，否则应保持客观中立，专注于事实和策略的陈述。

## Workflows

- 目标: 围绕用户提供的"{keyword}"，生成一篇结构清晰、内容详实、对玩家极具价值且完全符合Google SEO最佳实践的高质量文章。
- 步骤 1: 关键词与意图解析。分析"{keyword}"，确定其背后的核心用户意图（例如：是寻求攻略、了解机制、还是比较角色/装备）。
- 步骤 2: 信息搜集与大纲构建。基于最新网络信息源，筛选出最核心、最准确的知识点，并设计出包含主标题和多个逻辑清晰的副标题的文章大纲。
- 步骤 3: 内容填充与SEO优化。按照大纲逐段撰写内容，确保每段都有明确的小标题。在撰写过程中，自然融入关键词，并遵循E-E-A-T原则，优化可读性。同时生成一个吸引点击的SEO标题和Meta描述。
- 预期结果: 一篇可以直接发布在游戏网站或博客上的、专业且SEO友好的文章。文章结构为：一个H1主标题，若干个H2副标题，可能包含H3子标题，每个标题下是精炼、有用的段落内容。

## Initialization
作为Google SEO文章架构师，你必须遵守上述Rules，按照Workflows执行任务。"""
                },
                "zh-tw": {
                    "name": "繁體中文提示詞",
                    "template": """# Role: Google SEO文章架构师

## Profile
- language: 中文
- description: 一位精通Google SEO的内容策略与创作专家，致力于为游戏领域创作符合最新搜索引擎算法、具有高度用户价值的深度文章。能够将复杂的游戏主题转化为结构清晰、信息准确、对玩家极具吸引力和实用性的高质量内容，最终目标是实现Google SERP首页排名。
- background: 模拟在顶级数字营销机构担任多年的SEO内容主管，成功为多个游戏资讯网站和游戏品牌实现流量和排名的显著增长。深度理解Google的"有用内容更新"（Helpful Content Update）和E-E-A-T（经验、专业、权威、可信）评估标准。
- personality: 专业、精准、高效、用户至上。沟通直接，摒弃一切营销废话和无用信息，专注于提供能够解决玩家实际问题的核心价值内容。
- expertise: Google SEO、内容营销、关键词研究与布局、E-E-A-T内容构建、SERP（搜索引擎结果页）分析、游戏行业内容创作。
- target_audience: 寻求游戏攻略、评测、新闻、深度分析等信息的各层次游戏玩家。

## Skills

1. 核心内容创作技能
   - SEO内容策略: 根据关键词和用户意图，规划文章的核心主题、结构和内容深度。
   - E-E-A-T内容构建: 在文章中巧妙融入第一人称经验分享（Experience）、专业术语的准确运用（Expertise）、引用权威来源（Authoritativeness）和提供透明可靠信息（Trustworthiness）。
   - 用户意图分析: 精准判断搜索"{keyword}"的用户是想了解"是什么"、"怎么做"、"哪个好"还是"最新消息"，并据此组织内容。
   - 实时信息整合: 抓取并融合关于"{keyword}"的最新网络文章、社区讨论和官方公告，确保内容的即时性和准确性。

2. SEO技术与优化技能
   - 关键词优化: 自然地将核心关键词、长尾关键词和LSI（潜在语义索引）关键词融入标题、副标题和正文中，避免堆砌。
   - 结构化数据思维: 采用清晰的标题层级（H1, H2, H3...）、有序/无序列表、粗体强调等方式，优化内容结构，便于Google爬虫理解和收录。
   - 可读性优化: 使用简短的段落、清晰的语言和直接的表达方式，确保玩家能快速阅读并获取所需信息。
   - 标题与元描述生成: 创作具有高点击率（CTR）的SEO标题和精准概括文章内容的Meta Description。

## Rules

1. 基本原则：
   - 用户价值第一: 所有内容必须以"对游戏玩家有用"为最高准则，解决他们的疑问或满足其好奇心。
   - 遵循Google指南: 严格遵守Google搜索质量评估者指南，杜绝黑帽SEO手段。
   - 时效性至上: 内容必须基于最新的游戏版本、新闻或社区共识，过时信息不予采纳。
   - 深度与原创性: 禁止简单地转述或拼接，必须对信息进行整合、提炼并提供独特的见解或更清晰的解决方案。

2. 行为准则：
   - 段落清晰，标题先行: 每一段内容开始前，必须有一个明确的小标题（H2或H3标签格式），概括该段落的核心内容。
   - 杜绝废话: 省去所有不必要的引言、客套话和过渡性语句，直奔主题。
   - 引用佐证: 在提到具体数据、更新日志或关键信息时，应体现出信息来源的可靠性（例如，"根据官方最新公告…"）。
   - 语言风格: 使用玩家群体熟悉的语言，但保持专业和准确，避免使用过度口语化或错误的术语。

3. 限制条件：
   - 禁止关键词堆砌: 绝不允许为了SEO而牺牲文章的可读性和自然度。
   - 禁止生成误导性内容: 不得包含未经证实或猜测性的信息，除非明确标注为"推测"或"传闻"。
   - 禁止抄袭: 生成的内容必须是独一无二的，即使是基于现有文章，也必须是经过深度重构和再创作的。
   - 避免主观臆断: 除非是撰写评测类文章，否则应保持客观中立，专注于事实和策略的陈述。

## Workflows

- 目标: 围绕用户提供的"{keyword}"，生成一篇结构清晰、内容详实、对玩家极具价值且完全符合Google SEO最佳实践的高质量文章。
- 步骤 1: 关键词与意图解析。分析"{keyword}"，确定其背后的核心用户意图（例如：是寻求攻略、了解机制、还是比较角色/装备）。
- 步骤 2: 信息搜集与大纲构建。基于最新网络信息源，筛选出最核心、最准确的知识点，并设计出包含主标题和多个逻辑清晰的副标题的文章大纲。
- 步骤 3: 内容填充与SEO优化。按照大纲逐段撰写内容，确保每段都有明确的小标题。在撰写过程中，自然融入关键词，并遵循E-E-A-T原则，优化可读性。同时生成一个吸引点击的SEO标题和Meta描述。
- 预期结果: 一篇可以直接发布在游戏网站或博客上的、专业且SEO友好的文章。文章结构为：一个H1主标题，若干个H2副标题，可能包含H3子标题，每个标题下是精炼、有用的段落内容。

## Initialization
作为Google SEO文章架构师，你必须遵守上述Rules，按照Workflows执行任务。"""
                }
            }
        }
    
    def get_platform_config(self, platform_name: str = None) -> Dict[str, Any]:
        """获取指定平台的配置"""
        if platform_name is None:
            platform_name = self.config.get("default_platform", "groq")
        
        platforms = self.config.get("platforms", {})
        if platform_name not in platforms:
            print(f"⚠️  平台 '{platform_name}' 不存在，使用默认平台 'groq'")
            platform_name = "groq"
        
        return platforms.get(platform_name, {})
    
    def get_available_platforms(self) -> List[str]:
        """获取所有可用的平台列表"""
        return list(self.config.get("platforms", {}).keys())
    
    def get_platform_models(self, platform_name: str = None) -> List[str]:
        """获取指定平台可用的模型列表"""
        platform_config = self.get_platform_config(platform_name)
        return platform_config.get("models", {}).get("available", [])
    
    def get_default_model(self, platform_name: str = None) -> str:
        """获取指定平台的默认模型"""
        platform_config = self.get_platform_config(platform_name)
        return platform_config.get("models", {}).get("default", "")
    
    def get_api_keys(self, platform_name: str = None) -> List[str]:
        """获取指定平台的API密钥列表"""
        platform_config = self.get_platform_config(platform_name)
        api_keys = platform_config.get("api_keys", [])
        
        # 过滤掉空密钥和占位符（允许 OpenAI sk- 前缀）
        valid_keys = [key for key in api_keys if key and not key.startswith("your_")]
        return valid_keys
    
    def get_api_url(self, platform_name: str = None, use_proxy: bool = None) -> str:
        """获取API请求URL"""
        platform_config = self.get_platform_config(platform_name)
        
        if use_proxy is None:
            use_proxy = self.config.get("settings", {}).get("use_proxy", True)
        
        if use_proxy and "proxy_url" in platform_config:
            return platform_config["proxy_url"]
        else:
            return platform_config.get("base_url", "")
    
    def get_headers(self, platform_name: str = None) -> Dict[str, str]:
        """获取请求头"""
        platform_config = self.get_platform_config(platform_name)
        return platform_config.get("headers", {"Content-Type": "application/json"})
    
    def get_auth_type(self, platform_name: str = None) -> str:
        """获取认证类型"""
        platform_config = self.get_platform_config(platform_name)
        return platform_config.get("auth_type", "bearer")
    
    def get_timeout(self, platform_name: str = None) -> int:
        """获取超时时间"""
        platform_config = self.get_platform_config(platform_name)
        return platform_config.get("timeout", 60)
    
    def get_max_retries(self, platform_name: str = None) -> int:
        """获取最大重试次数"""
        platform_config = self.get_platform_config(platform_name)
        return platform_config.get("max_retries", 20)
    
    def get_settings(self) -> Dict[str, Any]:
        """获取全局设置"""
        return self.config.get("settings", {})
    
    def update_platform_api_keys(self, platform_name: str, api_keys: List[str]):
        """更新指定平台的API密钥"""
        if "platforms" not in self.config:
            self.config["platforms"] = {}
        
        if platform_name not in self.config["platforms"]:
            print(f"⚠️  平台 '{platform_name}' 不存在")
            return False
        
        self.config["platforms"][platform_name]["api_keys"] = api_keys
        self.save_config()
        return True
    
    def set_default_platform(self, platform_name: str):
        """设置默认平台"""
        if platform_name in self.get_available_platforms():
            self.config["default_platform"] = platform_name
            self.save_config()
            return True
        else:
            print(f"⚠️  平台 '{platform_name}' 不存在")
            return False
    
    def save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"✅ 配置已保存到: {self.config_file}")
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
    
    def show_platform_info(self, platform_name: str = None):
        """显示平台信息"""
        if platform_name is None:
            platform_name = self.config.get("default_platform", "groq")
        
        platform_config = self.get_platform_config(platform_name)
        api_keys = self.get_api_keys(platform_name)
        
        print(f"\n📋 平台信息: {platform_config.get('name', platform_name)}")
        print(f"🔗 API URL: {self.get_api_url(platform_name)}")
        print(f"🤖 默认模型: {self.get_default_model(platform_name)}")
        print(f"🔑 API密钥数量: {len(api_keys)}")
        print(f"⏱️  超时时间: {self.get_timeout(platform_name)}秒")
        print(f"🔄 最大重试: {self.get_max_retries(platform_name)}次")
        
        if api_keys:
            print("🔐 密钥列表:")
            for i, key in enumerate(api_keys, 1):
                print(f"   {i}. ...{key[-8:]}")
        else:
            print("⚠️  未配置有效的API密钥")
    
    def show_all_platforms(self):
        """显示所有平台信息"""
        print("\n🌐 可用的AI平台:")
        print("=" * 50)
        
        for platform_name in self.get_available_platforms():
            platform_config = self.get_platform_config(platform_name)
            api_keys = self.get_api_keys(platform_name)
            is_default = platform_name == self.config.get("default_platform")
            
            status = "✅ 默认" if is_default else "⚪ 可选"
            key_status = f"({len(api_keys)}个密钥)" if api_keys else "❌ 无密钥"
            
            print(f"{status} {platform_name}: {platform_config.get('name', platform_name)} {key_status}")
        
        print("=" * 50)
    
    def get_prompt_config(self, lang_code: str = "zh-cn") -> Dict[str, Any]:
        """获取指定语言的提示词配置"""
        prompts = self.config.get("prompts", {})
        if lang_code not in prompts:
            print(f"⚠️  语言 '{lang_code}' 的提示词配置不存在")
            return {}
        return prompts.get(lang_code, {})
    
    def get_prompt_template(self, lang_code: str = "zh-cn") -> str:
        """获取指定语言的提示词模板"""
        prompt_config = self.get_prompt_config(lang_code)
        return prompt_config.get("template", "")
    
    def get_available_languages(self) -> List[str]:
        """获取所有可用的语言列表"""
        prompts = self.config.get("prompts", {})
        return list(prompts.keys())
    
    def update_prompt_template(self, lang_code: str, template: str, name: str = None):
        """更新指定语言的提示词模板"""
        if "prompts" not in self.config:
            self.config["prompts"] = {}
        
        if lang_code not in self.config["prompts"]:
            self.config["prompts"][lang_code] = {}
        
        self.config["prompts"][lang_code]["template"] = template
        if name:
            self.config["prompts"][lang_code]["name"] = name
        
        self.save_config()
        return True
    
    def auto_translate_prompt(self, source_lang: str, target_lang: str, api_manager=None) -> str:
        """自动翻译提示词到目标语言"""
        source_template = self.get_prompt_template(source_lang)
        if not source_template:
            print(f"⚠️  源语言 '{source_lang}' 的提示词模板为空")
            return ""
        
        if not api_manager:
            print("⚠️  需要API管理器来进行翻译")
            return ""
        
        try:
            print(f"正在将提示词从 {source_lang} 翻译到 {target_lang}...")
            
            # 构建翻译提示词
            translate_prompt = f"""请将以下中文提示词翻译成繁体中文，保持原有的格式和结构，只翻译文本内容，不要改变Markdown格式：

{source_template}

要求：
1. 保持原有的Markdown格式（#、##、-、*等）
2. 保持原有的占位符（如{{keyword}}）
3. 将简体中文翻译成繁体中文
4. 保持专业术语的准确性
5. 不要添加任何额外的说明或注释"""
            
            # 使用API进行翻译
            translated_template = api_manager.make_request(translate_prompt)
            
            # 清理翻译结果
            import re
            cleaned_template = re.sub(r'<think>.*?</think>', '', translated_template, flags=re.DOTALL)
            cleaned_template = cleaned_template.strip()
            
            print(f"✅ 提示词翻译完成")
            return cleaned_template
            
        except Exception as e:
            print(f"❌ 翻译提示词失败: {e}")
            return ""
    
    def show_prompt_info(self, lang_code: str = None):
        """显示提示词信息"""
        if lang_code:
            prompt_config = self.get_prompt_config(lang_code)
            if prompt_config:
                print(f"\n📝 {lang_code} 提示词信息:")
                print(f"名称: {prompt_config.get('name', '未设置')}")
                template = prompt_config.get('template', '')
                if template:
                    print(f"长度: {len(template)} 字符")
                    print(f"预览: {template[:100]}...")
                else:
                    print("状态: 未配置")
            else:
                print(f"⚠️  语言 '{lang_code}' 的提示词配置不存在")
        else:
            print("\n📝 所有语言的提示词信息:")
            print("=" * 50)
            
            for lang in self.get_available_languages():
                prompt_config = self.get_prompt_config(lang)
                template = prompt_config.get('template', '')
                status = "✅ 已配置" if template else "❌ 未配置"
                print(f"{status} {lang}: {prompt_config.get('name', '未命名')}")
            
            print("=" * 50)
