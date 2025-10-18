import requests
import time
import json
from datetime import datetime, timezone, timedelta
from itertools import cycle
from typing import Dict, List, Optional, Any
from config_manager import ConfigManager

# 定义北京时间时区
beijing_tz = timezone(timedelta(hours=8))


class ApiExhaustedRetriesError(Exception):
    """API重试超过上限时抛出，用于让上层主动终止当前任务"""
    pass

class MultiPlatformApiManager:
    """多平台API管理器，支持多个AI平台"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.current_platform = config_manager.config.get("default_platform", "groq")
        self.api_key_managers = {}
        self.circuit_breaker_callback = None  # 熔断检查回调函数
        self._initialize_platforms()
    
    def _initialize_platforms(self):
        """初始化所有平台的API密钥管理器"""
        for platform_name in self.config_manager.get_available_platforms():
            api_keys = self.config_manager.get_api_keys(platform_name)
            if api_keys:
                self.api_key_managers[platform_name] = ApiKeyManager(api_keys, platform_name)
                print(f"✅ 已初始化平台 '{platform_name}': {len(api_keys)} 个密钥")
            else:
                print(f"⚠️  平台 '{platform_name}' 没有有效的API密钥")
    
    def set_platform(self, platform_name: str) -> bool:
        """设置当前使用的平台"""
        if platform_name in self.api_key_managers:
            self.current_platform = platform_name
            print(f"🔄 已切换到平台: {platform_name}")
            return True
        else:
            print(f"❌ 平台 '{platform_name}' 不可用或没有配置API密钥")
            return False
    
    def get_available_platforms(self) -> List[str]:
        """获取可用的平台列表（有API密钥的）"""
        return list(self.api_key_managers.keys())
    
    def set_circuit_breaker_callback(self, callback):
        """设置熔断检查回调函数"""
        self.circuit_breaker_callback = callback
    
    def make_request(self, prompt: str, platform_name: str = None) -> str:
        """发送API请求"""
        if platform_name is None:
            platform_name = self.current_platform
        
        if platform_name not in self.api_key_managers:
            raise Exception(f"平台 '{platform_name}' 不可用或没有配置API密钥")
        
        # 获取平台配置
        platform_config = self.config_manager.get_platform_config(platform_name)
        api_url = self.config_manager.get_api_url(platform_name)
        headers = self.config_manager.get_headers(platform_name)
        auth_type = self.config_manager.get_auth_type(platform_name)
        timeout = self.config_manager.get_timeout(platform_name)
        max_retries = self.config_manager.get_max_retries(platform_name)
        settings = self.config_manager.get_settings()
        
        # 获取API密钥管理器
        key_manager = self.api_key_managers[platform_name]
        
        # 构建请求数据
        request_data = self._build_request_data(prompt, platform_name, settings)
        
        # 发送请求
        return self._make_api_request_with_retry(
            api_url, headers, request_data, key_manager, 
            auth_type, timeout, max_retries, platform_name
        )
    
    def _build_request_data(self, prompt: str, platform_name: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """构建请求数据"""
        platform_config = self.config_manager.get_platform_config(platform_name)
        model = self.config_manager.get_default_model(platform_name)
        
        # 根据平台类型构建不同的请求格式
        if platform_name == "gemini":
            # Gemini API格式
            return {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": settings.get("temperature", 0.6),
                    "maxOutputTokens": settings.get("max_tokens", 1500),
                    "topP": settings.get("top_p", 0.95)
                }
            }
        elif platform_name == "claude":
            # Claude API格式
            return {
                "model": model,
                "max_tokens": settings.get("max_tokens", 1500),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": settings.get("temperature", 0.6),
                "top_p": settings.get("top_p", 0.95)
            }
        else:
            # OpenAI兼容格式（Groq, OpenAI等）
            return {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": settings.get("temperature", 0.6),
                "max_completion_tokens": settings.get("max_tokens", 1500),
                "top_p": settings.get("top_p", 0.95),
                "stream": settings.get("stream", False),
                "stop": None
            }
    
    def _make_api_request_with_retry(self, url: str, headers: Dict[str, str], 
                                   data: Dict[str, Any], key_manager: 'ApiKeyManager',
                                   auth_type: str, timeout: int, max_retries: int, 
                                   platform_name: str) -> str:
        """带重试机制的API请求"""
        
        if not key_manager or not key_manager.api_keys:
            raise Exception(f"平台 '{platform_name}' 未提供有效的API密钥")
        
        last_error_details = []
        
        for attempt in range(max_retries):
            # 检查熔断状态（在每次重试前）
            if self.circuit_breaker_callback:
                try:
                    self.circuit_breaker_callback()
                except ApiExhaustedRetriesError:
                    # 熔断已触发，立即停止重试
                    print(f"⛔ 熔断机制已触发，停止API重试")
                    raise
            
            # 获取当前使用的API密钥
            current_key = key_manager.get_next_key()
            if not current_key:
                raise Exception(f"平台 '{platform_name}' 没有可用的API密钥")
            
            # 更新请求头中的认证信息
            if auth_type == "bearer":
                headers["Authorization"] = f"Bearer {current_key}"
            elif auth_type == "x-api-key":
                headers["x-api-key"] = current_key
            elif auth_type == "api_key":
                headers["X-Goog-Api-Key"] = current_key
            
            try:
                print(f"尝试第 {attempt + 1} 次API调用 (平台: {platform_name}, 密钥: ...{current_key[-8:]})")
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                
                print(f"📡 API响应状态码: {response.status_code}")
                response.raise_for_status()
                
                # 解析响应
                result = response.json()
                content = self._extract_content_from_response(result, platform_name)
                
                if content:
                    key_manager.mark_key_success(current_key)
                    print(f"✅ API调用成功 (平台: {platform_name}, 密钥: ...{current_key[-8:]})")
                    return content
                else:
                    error_detail = f"API返回格式错误 - 响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}"
                    print(f"❌ {error_detail}")
                    last_error_details.append(error_detail)
                    raise Exception(error_detail)
                    
            except requests.exceptions.HTTPError as e:
                try:
                    error_response = response.json()
                    error_content = json.dumps(error_response, ensure_ascii=False, indent=2)
                except:
                    error_content = response.text if hasattr(response, 'text') else "无法解析响应内容"
                
                error_detail = f"HTTP错误 {response.status_code}: {str(e)}\n响应内容: {error_content}"
                print(f"❌ {error_detail}")
                last_error_details.append(error_detail)
                
                if response.status_code == 429:  # 速率限制
                    key_manager.mark_key_failed(current_key)
                    delay = key_manager.get_retry_delay(attempt)
                    print(f"⏰ 遇到速率限制，等待 {delay} 秒后重试...")
                    time.sleep(delay)
                elif response.status_code in [401, 403]:  # 认证错误
                    key_manager.mark_key_failed(current_key)
                    print(f"🔑 API密钥认证失败，切换到下一个密钥...")
                else:
                    delay = key_manager.get_retry_delay(attempt)
                    print(f"⏰ API调用失败，等待 {delay} 秒后重试...")
                    time.sleep(delay)
                    
            except requests.exceptions.RequestException as e:
                error_detail = f"网络请求错误: {str(e)}"
                print(f"❌ {error_detail}")
                last_error_details.append(error_detail)
                delay = key_manager.get_retry_delay(attempt)
                print(f"⏰ 等待 {delay} 秒后重试...")
                time.sleep(delay)
                
            except Exception as e:
                error_detail = f"其他错误: {str(e)}"
                print(f"❌ {error_detail}")
                last_error_details.append(error_detail)
                delay = key_manager.get_retry_delay(attempt)
                print(f"⏰ 等待 {delay} 秒后重试...")
                time.sleep(delay)
        
        # 汇总所有错误信息
        detailed_error = f"""
🚨 所有重试都失败了 (最大重试次数: {max_retries})

📋 详细错误历史:
{'='*50}
"""
        for i, error in enumerate(last_error_details, 1):
            detailed_error += f"尝试 #{i}: {error}\n{'-'*30}\n"
        
        detailed_error += f"""
🔧 建议解决方案:
1. 检查网络连接是否正常
2. 验证API密钥是否有效
3. 确认API配额是否用完
4. 检查{platform_name}服务状态
5. 稍后再试或联系技术支持
"""
        
        raise ApiExhaustedRetriesError(detailed_error)
    
    def _extract_content_from_response(self, result: Dict[str, Any], platform_name: str) -> str:
        """从响应中提取内容"""
        if platform_name == "gemini":
            # Gemini响应格式
            if "candidates" in result and result["candidates"]:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    if parts and "text" in parts[0]:
                        return parts[0]["text"].strip()
        elif platform_name == "claude":
            # Claude响应格式
            if "content" in result and result["content"]:
                if isinstance(result["content"], list) and len(result["content"]) > 0:
                    return result["content"][0].get("text", "").strip()
        else:
            # OpenAI兼容格式
            if "choices" in result and result["choices"]:
                choice = result["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"].strip()
        
        return ""
    
    def show_usage_stats(self):
        """显示所有平台的使用统计"""
        print("\n📊 所有平台API密钥使用统计:")
        print("=" * 60)
        
        for platform_name, key_manager in self.api_key_managers.items():
            print(f"\n🌐 平台: {platform_name}")
            key_manager.show_usage_stats()
        
        print("=" * 60)


class ApiKeyManager:
    """API密钥管理器（从原代码迁移并优化）"""
    
    def __init__(self, api_keys: List[str], platform_name: str = "unknown"):
        self.api_keys = api_keys if isinstance(api_keys, list) else [api_keys]
        self.key_cycle = cycle(self.api_keys)
        self.current_key = None
        self.failed_keys = set()
        self.retry_count = {}
        self.success_count = {}
        self.usage_stats = {}
        self.platform_name = platform_name
        
        # 初始化统计
        for key in self.api_keys:
            self.success_count[key] = 0
            self.usage_stats[key] = {'success': 0, 'failed': 0, 'last_used': None}
    
    def get_next_key(self):
        """获取下一个可用的API密钥"""
        available_keys = [key for key in self.api_keys if key not in self.failed_keys]
        
        if not available_keys:
            # 如果所有密钥都失败了，重置失败列表
            print(f"🔄 平台 {self.platform_name} 所有API密钥都失败了，重置失败列表并等待30秒...")
            self.show_usage_stats()
            self.failed_keys.clear()
            self.retry_count.clear()
            time.sleep(30)
            available_keys = self.api_keys
        
        # 轮换到下一个密钥
        for _ in range(len(self.api_keys)):
            key = next(self.key_cycle)
            if key in available_keys:
                self.current_key = key
                self.usage_stats[key]['last_used'] = datetime.now(beijing_tz).strftime("%H:%M:%S")
                return key
        
        return self.api_keys[0] if self.api_keys else None
    
    def mark_key_failed(self, key):
        """标记密钥失败"""
        self.failed_keys.add(key)
        self.retry_count[key] = self.retry_count.get(key, 0) + 1
        self.usage_stats[key]['failed'] += 1
        print(f"🔑 平台 {self.platform_name} API密钥 ...{key[-8:]} 失败次数: {self.retry_count[key]}, 已标记为临时失败")
    
    def mark_key_success(self, key):
        """标记密钥成功"""
        self.success_count[key] = self.success_count.get(key, 0) + 1
        self.usage_stats[key]['success'] += 1
        # 如果之前失败过，现在成功了，可以从失败列表中移除
        if key in self.failed_keys:
            self.failed_keys.discard(key)
            print(f"✅ 平台 {self.platform_name} API密钥 ...{key[-8:]} 恢复正常")
    
    def show_usage_stats(self):
        """显示密钥使用统计"""
        print(f"📊 平台 {self.platform_name} API密钥使用统计:")
        for i, key in enumerate(self.api_keys, 1):
            stats = self.usage_stats[key]
            status = "❌ 失败" if key in self.failed_keys else "✅ 正常"
            print(f"  密钥 #{i} (...{key[-8:]}): {status}")
            print(f"    成功: {stats['success']} | 失败: {stats['failed']} | 最后使用: {stats['last_used'] or '未使用'}")
    
    def get_retry_delay(self, attempt):
        """获取重试延迟时间（指数退避）"""
        return min(30, 2 ** attempt)

