#!/usr/bin/env python3
"""
分类引擎模块（从 phase3_enhanced.py 提取）
提供 classify_repo 函数，供其他模块导入。
"""
import re

# ==============================
# 分类规则引擎 v2
# 策略：多层匹配（标题→描述→语言→主题）
# ==============================
RULES = {
    "编程语言-编译器": {
        "keywords": ["programming language", "compiler", "interpreter", "type system",
                    "language runtime", "bytecode", "vm", "virtual machine"],
        "title_match": ["language", "compiler"],
        "lang_match": [],  # 不做语言过滤
        # 知名编程语言仓库
        "known_repos": [
            "golang/go", "rust-lang/rust", "python/cpython", "microsoft/typescript",
            "julia/julia", "scala/scala", "haskell/haskell", "kotlin/kotlin",
            "elixir-lang/elixir", "clojure/clojure", "nim-lang/nim",
            "ziglang/zig", "ocaml/ocaml", "erlang/otp", "crystal-lang/crystal",
            "dotnet/roslyn", "swiftlang/swift", "ruby/ruby", "php/php-src",
            "nodejs/node", "denoland/deno", "bun/bun", "luau-lang/luau",
            "mojolang/mojo", "vlang/v", "gleam-lang/gleam", "purescript/purescript"
        ]
    },
    "操作系统-底层-内核": {
        "keywords": ["operating system", "kernel", "driver", "filesystem", "bootloader",
                    "firmware", "embedded system", "rtos", "memory management",
                    "scheduler", "system programming", "low-level", "assembly",
                    "boot", "uefi", "bios", "container runtime"],
        "title_match": ["os", "kernel", "boot", "linux"],
        "known_repos": ["ventoy/ventoy", "netdata/netdata", "htop-dev/htop"]
    },
    "大语言模型-LLM": {
        "keywords": ["llm", "large language model", "gpt", "chatgpt", "transformer",
                    "bert", "language model", "text generation", "openai", "deepseek",
                    "qwen", "chatglm", "llama", "mistral", "gemma", "attention",
                    "tokenizer", "prompt", "rag", "instruct", "finetune", "fine-tune",
                    "pretrain", "pre-train", "vllm", "ollama", "lm studio",
                    "langchain", "semantic kernel", "vector database", "embedding"],
        "title_match": ["llm", "gpt", "transformer", "chat"],
    },
    "AI-机器学习": {
        "keywords": ["machine learning", "deep learning", "neural network", "cnn", "rnn",
                    "computer vision", "object detection", "image classification",
                    "segmentation", "yolo", "pytorch", "tensorflow", "keras",
                    "reinforcement learning", "rl", "stable diffusion",
                    "diffusion model", "vae", "gan", "generative",
                    "natural language processing", "nlp", "speech recognition",
                    "asr", "tts", "embedding", "xgboost", "sklearn",
                    "机器学习", "深度学习"],
        "title_match": ["yolo", "pytorch", "tensorflow"],
        "known_repos": ["d2l-ai/d2l-zh", "d2l-ai/d2l-en"]
    },
    "AI应用-Agent": {
        "keywords": ["agent", "autonomous", "coding agent", "ai assistant",
                    "claude", "copilot", "codex", "code generation",
                    "tool use", "function calling", "mcp", "model context",
                    "orchestrator", "multi-agent", "agentic", "skills",
                    "ai-driven", "ai-powered", "devika", "openhands",
                    "swe-agent", "devin", "cline", "aider"],
        "title_match": ["agent", "assistant", "copilot", "skills", "openhands"],
    },
    "内容创作-AIGC-设计": {
        "keywords": ["image generation", "text to image", "text-to-image",
                    "text to video", "text-to-video", "text to speech",
                    "music generation", "content creation",
                    "design system", "slide deck", "presentation",
                    "video generation", "animation", "3d generation",
                    "whiteboard", "diagram", "flowchart",
                    "draw", "illustration", "sketch", "canvas",
                    "photo", "image editor", "video editor",
                    "svg", "icon set", "emoji", "font"],
        "title_match": ["excalidraw", "mermaid", "drawio", "svg"]
    },
    "前端-UI框架": {
        "keywords": ["react", "vue", "angular", "svelte", "solid", "qwik",
                    "next.js", "nuxt", "remix", "gatsby",
                    "ui framework", "component library", "css framework",
                    "tailwind", "bootstrap", "material design", "ant design",
                    "frontend", "web app", "spa", "pwa",
                    "state management", "redux", "zustand", "pinia",
                    "webpack", "vite", "esbuild", "babel", "storybook",
                    "chart", "dashboard ui", "ui kit", "design system",
                    "html5", "webgl", "canvas", "dom",
                    "css", "stylesheet", "responsive"],
        "title_match": ["ui", "react", "vue", "angular", "svelte", "css", "html"],
    },
    "后端-框架-API": {
        "keywords": ["rest api", "graphql", "grpc", "microservice",
                    "spring", "django", "flask", "fastapi", "express",
                    "gin", "echo", "actix", "axum", "tower",
                    "orm", "sqlalchemy", "prisma", "typeorm",
                    "api gateway", "load balancer", "proxy", "reverse proxy",
                    "web framework", "server", "backend",
                    "middleware", "message queue", "rabbitmq", "nats",
                    "websocket", "socket.io", "real-time"],
        "title_match": ["framework", "server", "backend", "api"],
    },
    "开发工具-编辑器-IDE": {
        "keywords": ["ide", "editor", "vscode", "vim", "neovim", "emacs",
                    "plugin", "extension", "syntax highlighting",
                    "linter", "formatter", "debugger", "profiler",
                    "language server", "lsp",
                    "version control", "git", "code review",
                    "testing", "unit test", "mock", "assert",
                    "fuzzy finder", "fzf", "ripgrep", "fd",
                    "terminal emulator", "shell", "tmux"],
        "title_match": ["vim", "neovim", "emacs", "fzf", "ripgrep"],
    },
    "API-工具-命令行": {
        "keywords": ["cli", "command line", "terminal", "tui",
                    "developer tool", "productivity", "utility",
                    "toolkit", "library", "sdk",
                    "package manager", "docker", "docker compose",
                    "monitoring", "logging", "analytics", "search",
                    "http client", "curl", "httpie",
                    "json", "yaml", "toml", "config file",
                    "dotfiles", "homebrew", "choco", "scoop",
                    "nvm", "n", "fnm", "volta", "version manager",
                    "thefuck", "bat", "exa", "lsd", "delta",
                    "converter", "transcoder", "formatter"],
        "title_match": ["cli", "tool", "util", "manager", "ctl"],
    },
    "数据科学-数据库": {
        "keywords": ["database", "sql", "nosql", "big data", "data pipeline",
                    "data warehouse", "olap", "oltp", "timeseries",
                    "data lake", "etl", "data processing", "spark",
                    "hadoop", "kafka", "redis", "mongodb", "postgresql",
                    "clickhouse", "duckdb", "sqlite",
                    "data visualization", "dashboard", "pandas",
                    "numpy", "dataframe", "table"],
        "title_match": ["db", "sql", "database", "data"],
    },
    "安全-网络-代理": {
        "keywords": ["security", "vulnerability", "penetration testing",
                    "exploit", "malware", "antivirus",
                    "encryption", "cryptography", "authentication",
                    "authorization", "oauth", "jwt",
                    "firewall", "network proxy", "vpn", "proxy", "privacy",
                    "reverse engineering", "fuzzing", "scanning",
                    "hacking", "hacker", "hacktool", "cyber",
                    "remote desktop", "rdp", "vnc", "teamviewer",
                    "certificate", "ssl", "tls", "https"],
        "title_match": ["security", "hack", "proxy", "vpn", "rustdesk"],
    },
    "区块链-Web3": {
        "keywords": ["blockchain", "web3", "cryptocurrency", "bitcoin",
                    "ethereum", "solana", "smart contract", "defi",
                    "nft", "solidity", "wallet", "dapp", "consensus",
                    "distributed ledger", "decentralized", "base node"],
        "title_match": ["blockchain", "crypto", "web3", "ethereum"],
    },
    "量化交易-金融": {
        "keywords": ["trading", "quantitative", "algorithmic trading",
                    "backtest", "backtesting", "market data",
                    "stock", "cryptocurrency trading", "finance",
                    "portfolio", "risk management", "option pricing",
                    "technical analysis", "financial", "investment"],
        "title_match": ["trading", "finance", "quant"],
    },
    "移动开发-Android-iOS": {
        "keywords": ["android", "ios", "swift", "kotlin", "mobile app",
                    "flutter", "react native", "cross-platform mobile",
                    "mobile development", "app framework",
                    "xcode", "uikit", "swiftui"],
        "title_match": ["android", "ios", "flutter", "react-native"],
    },
    "自动化-DevOps-部署": {
        "keywords": ["automation", "workflow", "pipeline", "ci/cd",
                    "github action", "jenkins", "deploy", "release",
                    "scheduler", "cron", "task runner",
                    "makefile", "build system", "infrastructure",
                    "terraform", "ansible", "nix", "pulumi",
                    "configuration management", "iac",
                    "syncthing", "file sync", "rsync",
                    "monitoring", "observability", "prometheus",
                    "grafana", "alerting", "incident"],
        "title_match": ["devops", "deploy", "ci", "monitor"],
    },
    "学习资源-教程-书籍": {
        "keywords": ["tutorial", "course", "book", "awesome", "cheatsheet",
                    "learning", "guide", "handbook", "roadmap",
                    "interview", "algorithm", "data structure",
                    "coding challenge", "leetcode", "hackerrank",
                    "curriculum", "education", "practice",
                    "best practices", "design patterns", "clean code",
                    "build your own", "master programming",
                    "programmer should know", "learn",
                    "教程", "指南", "手册", "从新手到大师",
                    "100天", "入门"],
        "title_match": ["awesome", "tutorial", "learn", "book", "guide",
                       "handbook", "roadmap", "100-days", "python-100"],
    },
    "建站-电商-CMS": {
        "keywords": ["cms", "blog", "static site", "website builder",
                    "ecommerce", "shop", "woocommerce", "wordpress",
                    "headless cms", "landing page", "portfolio",
                    "documentation site", "wiki", "forum",
                    "social network", "community", "docusaurus",
                    "vitepress", "mkdocs", "gitbook"],
        "title_match": ["cms", "blog", "shop", "wiki", "website"],
    },
    "游戏-娱乐": {
        "keywords": ["game", "game engine", "godot", "unity", "unreal",
                    "emulator", "retro", "minecraft", "mod",
                    "multiplayer", "gaming", "simulation",
                    "roblox", "sprite", "pixel art"],
        "title_match": ["game", "godot", "minecraft"],
    },
    "爬虫-数据采集": {
        "keywords": ["web scraping", "crawler", "spider", "scrapy",
                    "scraper", "data extraction", "harvest",
                    "downloader", "batch download"],
        "title_match": ["scraper", "crawler", "spider"],
    },
    "媒体-音视频-直播": {
        "keywords": ["audio", "music", "sound", "speech", "voice",
                    "video", "player", "stream", "media",
                    "live streaming", "obs", "broadcast",
                    "ffmpeg", "codec", "transcoding",
                    "podcast", "spotify", "youtube"],
        "title_match": ["media", "player", "stream", "obs", "ffmpeg", "video", "audio"],
    },
}

def classify_repo(name, desc, lang, topics):
    """v2 增强分类"""
    text = f"{name} {desc}".lower()
    repo_name_only = name.split("/")[-1].lower()
    
    # 0. 已知仓库精确匹配
    for cat, rules in RULES.items():
        if name.lower() in rules.get("known_repos", []):
            return cat, 0.99
    
    # 1. 标题关键词匹配（权重最高）
    for cat, rules in RULES.items():
        for kw in rules.get("title_match", []):
            if kw in repo_name_only or kw in name.lower():
                return cat, 0.9
    
    # 2. 关键词分数计算
    scores = {}
    for cat, rules in RULES.items():
        score = 0.0
        keywords = rules.get("keywords", [])
        match_count = sum(1 for kw in keywords if kw in text)
        
        if match_count >= 3:
            score = 0.6 + min(0.3, match_count * 0.05)
        elif match_count == 2:
            score = 0.4
        elif match_count == 1:
            score = 0.25
        
        # 主题加分
        topic_match = sum(1 for t in topics if any(kw in t.lower() for kw in keywords[:10]))
        if topic_match > 0:
            score += min(0.2, topic_match * 0.1)
        
        if score > 0.2:
            scores[cat] = score
    
    if scores:
        best = max(scores, key=scores.get)
        if scores[best] >= 0.4:
            return best, scores[best]
    
    # 3. 低置信度但可以归类的
    if scores:
        best = max(scores, key=scores.get)
        return best, scores[best]
    
    return ("其他", 0.0)
