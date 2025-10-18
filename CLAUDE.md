# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 高层架构

本项目是一个基于 Python 的 AI 文章生成器，支持多个平台，包括 Groq、OpenAI、Google Gemini 和 Anthropic Claude。核心逻辑由以下几个关键文件协调：

-   `aigen.py`: 应用程序的主入口点。它处理用户交互、平台选择，并启动文章生成过程。
-   `config.json`: 一个中央配置文件，用于管理所有平台详情、API 密钥和全局设置。这使得在不修改代码的情况下轻松扩展新平台成为可能。
-   `api_manager.py`: 管理与各种 AI 平台 API 的所有交互。它处理 API 密钥轮换以实现负载均衡、请求/响应逻辑以及带重试的错误处理。
-   `config_manager.py`: 负责加载和验证 `config.json` 文件。
-   `kv_manager.py`: 一个简单的键值存储，可能用于持久化状态或统计数据。

该应用程序设计为可扩展的。添加新的 AI 平台主要涉及在 `config.json` 中添加其配置，并可能需要更新 `api_manager.py` 中的响应解析逻辑。

## 常用命令

以下是本代码库中用于开发的常用命令：

-   **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
-   **运行应用**:
    ```bash
    python aigen.py
    ```
-   **运行测试**: 项目配置了 pytest。
    ```bash
    pytest
    ```
-   **代码检查 (Linting)**: 使用 flake8 检查代码风格问题。
    ```bash
    flake8 .
    ```
-   **代码格式化**: 使用 black 格式化代码。
    ```bash
    black .
    ```
-   **类型检查**: 使用 mypy 运行静态类型检查。
    ```bash
    mypy .
    ```

## GitHub Actions 工作流

该代码库配备了 GitHub Actions 工作流 (`.github/workflows/ai-article-generator.yml`) 以自动生成文章。

-   **触发器**: 工作流可以通过三种方式触发：
    1.  **手动**: 通过 GitHub Actions 界面。
    2.  **定时**: 按 cron 计划运行 (例如，每天)。
    3.  **推送时**: 当 `长尾词.txt`、`aigen.py` 或 `config.json` 文件有改动被推送时。

-   **配置**: 工作流使用 GitHub Secrets 安全地存储各个 AI 平台的 API 密钥 (例如, `GROQ_API_KEY_1`, `OPENAI_API_KEY`)。它还接受关键词、期望的 AI 平台和其他选项作为输入。

-   **输出**: 生成的文章存储在 `assets/` 目录中。在此过程中发生的任何错误都会记录到 `assets/error_log.txt`。
