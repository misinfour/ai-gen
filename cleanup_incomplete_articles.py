#!/usr/bin/env python3
"""
清理不完整的文章目录工具

这个脚本会查找logs/backup目录中没有README.md文件的文章目录并删除它们。
这些目录通常是由于图片下载失败或文章生成失败而产生的不完整文章。
"""

import os
import shutil
from pathlib import Path

def cleanup_incomplete_articles(backup_dir="./logs/backup"):
    """清理没有README.md文件的不完整文章目录和临时下载文件夹"""
    backup_path = Path(backup_dir)
    
    if not backup_path.exists():
        print(f"❌ 备份目录 {backup_dir} 不存在")
        return
    
    print(f"🧹 开始清理不完整的文章目录: {backup_dir}")
    
    deleted_count = 0
    
    # 遍历所有包含images目录的文章目录
    for images_dir in backup_path.rglob("images"):
        if images_dir.is_dir():
            article_dir = images_dir.parent
            readme_file = article_dir / "README.md"
            
            if not readme_file.exists():
                print(f"🗑️  删除不完整的文章目录: {article_dir}")
                try:
                    shutil.rmtree(article_dir)
                    deleted_count += 1
                except Exception as e:
                    print(f"❌ 删除失败 {article_dir}: {e}")
    
    # 清理空的日期目录
    empty_dirs_count = 0
    for root, dirs, files in os.walk(backup_path, topdown=False):
        for dir_name in dirs:
            dir_path = Path(root) / dir_name
            try:
                # 尝试删除空目录（如果不为空会抛出异常）
                dir_path.rmdir()
                print(f"🗑️  删除空目录: {dir_path}")
                empty_dirs_count += 1
            except OSError:
                # 目录不为空，跳过
                pass
    
    print(f"🧹 开始清理临时下载文件夹...")
    
    # 清理临时下载文件夹
    temp_download_count = 0
    for temp_dir in backup_path.rglob("temp_download"):
        if temp_dir.is_dir():
            print(f"🗑️  删除临时下载文件夹: {temp_dir}")
            try:
                shutil.rmtree(temp_dir)
                temp_download_count += 1
            except Exception as e:
                print(f"❌ 删除临时下载文件夹失败 {temp_dir}: {e}")
    
    # 清理bing-image-downloader创建的下载文件夹
    download_folders_count = 0
    for root, dirs, files in os.walk(backup_path, topdown=False):
        for dir_name in dirs:
            dir_path = Path(root) / dir_name
            # 检查是否是下载文件夹（包含图片文件但没有README.md）
            if (dir_path.is_dir() and 
                not (dir_path / "README.md").exists() and 
                not (dir_path.parent / "README.md").exists()):
                # 检查是否包含图片文件
                image_files = list(dir_path.glob("*.jpg")) + list(dir_path.glob("*.jpeg")) + \
                             list(dir_path.glob("*.png")) + list(dir_path.glob("*.gif")) + \
                             list(dir_path.glob("*.webp"))
                if image_files:
                    print(f"🗑️  删除临时下载文件夹: {dir_path}")
                    try:
                        shutil.rmtree(dir_path)
                        download_folders_count += 1
                    except Exception as e:
                        print(f"❌ 删除临时下载文件夹失败 {dir_path}: {e}")
    
    print(f"✅ 清理完成:")
    print(f"   - 删除不完整文章目录: {deleted_count}")
    print(f"   - 删除空目录: {empty_dirs_count}")
    print(f"   - 删除临时下载文件夹: {temp_download_count}")
    print(f"   - 删除下载文件夹: {download_folders_count}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='清理不完整的文章目录')
    parser.add_argument('--backup-dir', default='./logs/backup', 
                       help='备份目录路径 (默认: ./logs/backup)')
    parser.add_argument('--dry-run', action='store_true',
                       help='只显示将要删除的目录，不实际删除')
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("🔍 预览模式 - 只显示将要删除的目录")
        # TODO: 实现预览模式
    
    cleanup_incomplete_articles(args.backup_dir)

if __name__ == "__main__":
    main()
