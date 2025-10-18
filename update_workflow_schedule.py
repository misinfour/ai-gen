#!/usr/bin/env python3
"""
动态更新工作流调度时间的脚本
"""

import json
import os
from datetime import datetime, timedelta, timezone

def update_workflow_schedule(schedule_type="retry", delay_minutes=30, workflow_name="process-keywords", no_push=False):
    """
    更新工作流调度时间
    
    Args:
        schedule_type: "retry" 表示重试模式（半小时后运行），"daily" 表示日常模式（每天运行）
        delay_minutes: 延迟分钟数（仅在retry模式下有效）
        workflow_name: 工作流名称，支持 "process-keywords" 或 "generate-articles"
    """
    workflow_file = f'.github/workflows/{workflow_name}.yml'
    
    if not os.path.exists(workflow_file):
        print(f"❌ 工作流文件不存在: {workflow_file}")
        return False
    
    try:
        # 定义北京时间时区（在所有代码路径中都需要）
        beijing_tz = timezone(timedelta(hours=8))
        
        # 读取工作流文件
        with open(workflow_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 生成新 cron 表达式
        if schedule_type == "retry":
            # 使用北京时间计算重试时间
            future_time_beijing = datetime.now(beijing_tz) + timedelta(minutes=delay_minutes)
            # 转换为UTC时间用于cron表达式
            future_time_utc = future_time_beijing.astimezone(timezone.utc)
            hour = future_time_utc.hour
            minute = future_time_utc.minute
            new_cron_line = f"    - cron: '{minute} {hour} {future_time_utc.day} {future_time_utc.month} *'"
            print(f"[重试模式] 设置重试模式: {delay_minutes} 分钟后运行")
            print(f"   北京时间: {future_time_beijing.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   UTC时间: {future_time_utc.strftime('%Y-%m-%d %H:%M:%S')}")
        else:  # daily
            if workflow_name == "process-keywords":
                new_cron_line = "    - cron: '0 16 * * *'"  # 每天 UTC 16点 = 北京时间0点
                print("[日常模式] 设置日常模式: 每天北京时间0点运行（关键词处理）")
            else:  # generate-articles
                new_cron_line = "    - cron: '0 17 * * *'"  # 每天 UTC 17点 = 北京时间1点
                print("[日常模式] 设置日常模式: 每天北京时间1点运行（文章生成）")
        
        # 查找当前 cron 行
        old_cron_line = None
        for line in content.split('\n'):
            if '- cron:' in line:
                old_cron_line = line.strip()
                break
        
        if not old_cron_line:
            print("[错误] 没有找到cron表达式")
            return False
        
        if old_cron_line.strip() == new_cron_line.strip():
            print(f"[成功] 工作流已经是目标调度模式，无需更新")
            print(f"   当前设置: {old_cron_line}")
        else:
            # 替换 cron
            content = content.replace(old_cron_line, new_cron_line.strip())
            with open(workflow_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[成功] 工作流调度时间已更新")
        
        # 日志记录
        now = datetime.now(beijing_tz)
        log_dir = os.path.join('logs', str(now.year), f"{now.month:02d}", f"{now.day:02d}")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "workflow_schedule_updates.log")
        log_entry = {
            "timestamp": now.isoformat(),
            "schedule_type": schedule_type,
            "delay_minutes": delay_minutes if schedule_type == "retry" else None,
            "new_cron": new_cron_line.strip()
        }
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        
        # Git 提交 & push（从配置文件或环境变量读取token）
        if not no_push:
            try:
                import subprocess
                
                # 1. 优先从配置文件读取（因为需要workflows权限）
                token = None
                repo = None
                
                if os.path.exists("config.json"):
                    try:
                        with open("config.json", 'r', encoding='utf-8') as f:
                            config = json.load(f)
                            github_config = config.get("repositories", {}).get("github", {})
                            token = github_config.get("token")
                            repo = github_config.get("repository")
                    except Exception as e:
                        print(f"[信息] 从配置文件读取token失败: {e}")
                
                # 2. 如果配置文件没有，尝试从环境变量获取
                if not token:
                    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT")
                    repo = os.getenv("GITHUB_REPOSITORY")
                
                if not token or not repo:
                    print("[警告] 未设置 GitHub token 或 repository，跳过 push")
                    print("[提示] 请在 config.json 中添加 github.token 和 github.repository 配置")
                    return True
                
                # 检查是否使用的是GITHUB_TOKEN（可能没有workflows权限）
                if os.getenv("GITHUB_ACTIONS") and token == os.getenv("GITHUB_TOKEN"):
                    print("[警告] 使用的是GITHUB_TOKEN，可能没有workflows权限")
                    print("[建议] 请在GitHub Secrets中设置GH_PAT，或在config.json中配置PAT token")

                subprocess.run(['git', 'config', '--local', 'user.email', 'action@github.com'], check=True)
                subprocess.run(['git', 'config', '--local', 'user.name', 'GitHub Action'], check=True)
                subprocess.run(['git', 'add', workflow_file, log_file], check=True)
                result = subprocess.run(['git', 'diff', '--staged', '--quiet'])
                if result.returncode != 0:
                    commit_msg = f"自动调整工作流为{schedule_type}模式 [skip ci]"
                    subprocess.run(['git', 'commit', '-m', commit_msg], check=True)
                    # 检查是否在GitHub Actions环境中
                    if os.getenv("GITHUB_ACTIONS"):
                        # 在GitHub Actions中，使用token设置remote URL并推送
                        push_url = f"https://x-access-token::{token}@github.com/{repo}.git"
                        subprocess.run(['git', 'remote', 'set-url', 'origin', push_url], check=True)
                        subprocess.run(['git', 'push', 'origin', 'main'], check=True)
                    else:
                        # 在本地环境中，使用github推送
                        subprocess.run(['git', 'push', 'github', 'main'], check=True)
                    print("[成功] 已提交工作流文件更改到Git仓库")
                else:
                    print("[信息] 工作流文件未更改，无需提交")
            except Exception as e:
                print(f"[警告] Git 提交/Push 失败: {e}")
                print("[信息] 工作流文件已更新，但未推送到远程")
        else:
            print("[信息] 跳过Git推送（--no-push参数）")
        
        return True
    
    except Exception as e:
        print(f"[错误] 更新工作流时间失败: {e}")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description='动态更新工作流调度时间')
    parser.add_argument('--type', choices=['retry', 'daily'], default='retry', help='调度类型')
    parser.add_argument('--delay', type=int, default=30, help='延迟分钟数（仅在retry模式下有效）')
    parser.add_argument('--workflow', choices=['process-keywords', 'generate-articles'], default='process-keywords', help='工作流名称')
    parser.add_argument('--no-push', action='store_true', help='只更新文件，不推送到远程仓库')
    args = parser.parse_args()
    success = update_workflow_schedule(args.type, args.delay, args.workflow, args.no_push)
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
