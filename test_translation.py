#!/usr/bin/env python3
"""
测试改进的翻译功能
"""

from article_generator import ArticleGenerator

def test_markdown_translation():
    """测试Markdown格式翻译"""
    
    # 创建文章生成器实例
    generator = ArticleGenerator()
    
    # 测试内容
    test_content = """# 游戏攻略指南

这是一个**重要的**游戏攻略，包含以下内容：

## 基本操作

- 移动：使用*WASD*键
- 攻击：点击鼠标左键
- 技能：按数字键1-4

## 高级技巧

1. 连击系统的使用方法
2. 装备强化的**最佳时机**
3. 资源管理策略

[下载游戏](https://example.com)获取更多信息。

> 提示：新手玩家建议先完成教学关卡。

```python
# 这是代码块，不应该被翻译
print("Hello World")
```

普通段落文本，包含一些*斜体*和**粗体**格式。
"""
    
    print("=== 测试智能翻译功能 ===")
    print("\n原文内容:")
    print("-" * 50)
    print(test_content)
    print("-" * 50)
    
    # 测试翻译到繁体中文
    print("\n开始翻译到繁体中文...")
    translated_content = generator.translate_long_content(test_content, 'zh-TW')
    
    print("\n翻译结果:")
    print("-" * 50)
    print(translated_content)
    print("-" * 50)
    
    # 验证格式保持
    print("\n格式验证:")
    original_lines = test_content.split('\n')
    translated_lines = translated_content.split('\n')
    
    print(f"原文行数: {len(original_lines)}")
    print(f"译文行数: {len(translated_lines)}")
    
    # 检查标题格式
    for i, (orig, trans) in enumerate(zip(original_lines, translated_lines)):
        if orig.startswith('#'):
            print(f"行 {i+1} - 标题格式:")
            print(f"  原文: {orig}")
            print(f"  译文: {trans}")
            print(f"  格式保持: {'✅' if trans.startswith('#') else '❌'}")

if __name__ == "__main__":
    test_markdown_translation()
