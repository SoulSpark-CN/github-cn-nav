#!/usr/bin/env python3
"""
Phase 3 Enhanced: 增强分类引擎 v2
修复：编程语言缺失、中文描述不匹配、关键词覆盖不足
"""
import json, os, sys, re, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE_DIR, "manifest.json")
CLASSIFY_DIR = os.path.join(BASE_DIR, "分类")
NAV_FILE = os.path.join(BASE_DIR, "导航索引.md")

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

def readme_summary(filepath):
    if not os.path.exists(filepath):
        return ""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            content = f.read()
        for line in content.strip().split("\n"):
            line = line.strip()
            if line.startswith("#"):
                continue
            if line and len(line) > 20:
                return line[:200]
        return ""
    except:
        return ""

def main():
    os.makedirs(CLASSIFY_DIR, exist_ok=True)
    
    with open(MANIFEST, encoding="utf-8") as f:
        repos = json.load(f)
    
    print(f"📊 增强分类 {len(repos)} 个项目...", flush=True)
    
    cat_counts = {}
    cat_repos = {}
    
    from collections import defaultdict
    
    for r in repos:
        name = r["name"]
        desc = r.get("desc", "")
        lang = r.get("lang", "")
        topics = r.get("topics", [])
        stars = r.get("stars", 0)
        url = r.get("url", "")
        
        category, confidence = classify_repo(name, desc, lang, topics)
        
        if category not in cat_repos:
            cat_repos[category] = []
        cat_counts[category] = cat_counts.get(category, 0) + 1
        
        readme_file = os.path.join(BASE_DIR, "原始README", name.replace("/", "_") + ".md")
        summary = readme_summary(readme_file)
        
        cat_repos[category].append({
            "name": name, "desc": desc, "stars": stars,
            "url": url, "lang": lang, "summary": summary[:200] if summary else "",
        })
    
    # 排序输出
    print(f"\n{'='*50}", flush=True)
    print(f"增强分类结果:")
    for cat in sorted(cat_counts.keys(), key=lambda c: -cat_counts[c]):
        print(f"  {cat:25s}: {cat_counts[cat]:5d}个", flush=True)
    
    total_classified = sum(cat_counts.values())
    
    # 写入分类文件
    for cat, repos_list in cat_repos.items():
        repos_list.sort(key=lambda r: -r["stars"])
        cat_dir = os.path.join(CLASSIFY_DIR, cat)
        os.makedirs(cat_dir, exist_ok=True)
        
        cat_file = os.path.join(cat_dir, "README.md")
        with open(cat_file, "w", encoding="utf-8") as f:
            f.write(f"# {cat}\n\n")
            f.write(f"> 共 {len(repos_list)} 个项目 | v2 增强分类\n\n")
            f.write("| 项目 | 描述 | ⭐ Stars | 语言 |\n")
            f.write("|------|------|---------|------|\n")
            for r in repos_list:
                desc_short = (r["desc"] or "")[:80].replace("|", "\\|")
                f.write(f"| [{r['name']}]({r['url']}) | {desc_short} | {r['stars']:,} | {r['lang']} |\n")
    
    # 写入导航索引
    print(f"\n📝 生成导航索引...", flush=True)
    with open(NAV_FILE, "w", encoding="utf-8") as f:
        f.write(f"# GitHub 5000+ Star 项目导航索引\n\n")
        f.write(f"> 共 {total_classified} 个开源项目 | v2 增强分类 | ")
        f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("---\n\n")
        
        # 分类汇总
        f.write("## 📋 分类目录\n\n")
        for cat in sorted(cat_counts.keys(), key=lambda c: -cat_counts[c]):
            f.write(f"- [{cat} ({cat_counts[cat]}个)](#{cat.replace('-', '').replace(' ', '-')})\n")
        f.write("\n---\n\n")
        
        for cat in sorted(cat_counts.keys(), key=lambda c: -cat_counts[c]):
            repos_list = cat_repos.get(cat, [])
            repos_list.sort(key=lambda r: -r["stars"])
            
            f.write(f"## {cat} ({cat_counts[cat]}个)\n\n")
            f.write("| # | 项目 | 描述 | ⭐ Stars | 语言 |\n")
            f.write("|---|------|------|---------|------|\n")
            
            for idx, r in enumerate(repos_list[:60], 1):
                desc_short = (r["desc"] or "")[:100].replace("|", "\\|")
                f.write(f"| {idx} | [{r['name']}]({r['url']}) | {desc_short} | {r['stars']:,} | {r['lang']} |\n")
            
            if len(repos_list) > 60:
                f.write(f"| ... | *还有 {len(repos_list)-60} 个* | ... | ... | ... |\n")
            
            f.write(f"\n[查看全部 →](./分类/{cat}/README.md)\n\n")
            f.write("---\n\n")
        
        # 语言分布
        f.write("## 📊 语言分布\n\n")
        lang_counts = {}
        for r in repos:
            l = r.get("lang", "") or "其他"
            lang_counts[l] = lang_counts.get(l, 0) + 1
        max_lang = max(lang_counts.values()) if lang_counts else 1
        for l, c in sorted(lang_counts.items(), key=lambda x: -x[1])[:30]:
            bar = "█" * max(1, c * 50 // max_lang)
            f.write(f"  {l:20s} │ {c:5d} {bar}\n")
    
    file_size = os.path.getsize(NAV_FILE) / 1024
    print(f"\n{'='*50}", flush=True)
    print(f"✅ 增强分类完成!", flush=True)
    print(f"  分类: {len(cat_counts)} 个类别", flush=True)
    print(f"  导航: {NAV_FILE} ({file_size:.0f}KB)", flush=True)
    print(f"  分类目录: {CLASSIFY_DIR}/", flush=True)
    
    # 保存统计
    stats_file = os.path.join(BASE_DIR, "分类统计.json")
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump({
            "total": total_classified,
            "categories": {cat: cat_counts[cat] for cat in sorted(cat_counts.keys(), key=lambda c: -cat_counts[c])}
        }, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
