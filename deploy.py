#!/usr/bin/env python3
"""
部署包生成器 - 把导航页打包成可部署的静态站点
用法: python3 deploy.py
产出: deploy/ 目录，内含 index.html + projects.json + README.txt + serve.sh
"""
import json, os, shutil

BASE = os.path.dirname(os.path.abspath(__file__))  # github目录/ (parent of deploy/)
DEPLOY = os.path.join(BASE, "deploy")
HTML_SRC = os.path.join(DEPLOY, "index.html")  # 轻量版模板(已含 fetch)
JSON_SRC = os.path.join(BASE, "projects.json")

os.makedirs(DEPLOY, exist_ok=True)

# 1. Copy data files
# 注意: index.html 是手动维护的轻量版(15KB), deploy.py 不会覆盖它
shutil.copy2(JSON_SRC, os.path.join(DEPLOY, "projects.json"))

# 2. Create serve.sh (一键启动)
serve_sh = r'''#!/bin/bash
# 一键启动 GitHub 导航站
# 方式1: Python 内置服务器
PORT=${1:-8080}
echo "GitHub 导航站已启动: http://localhost:$PORT"
echo "按 Ctrl+C 停止"
python3 -m http.server $PORT --directory "$(dirname "$0")"
'''

with open(os.path.join(DEPLOY, "serve.sh"), "w") as f:
    f.write(serve_sh)
os.chmod(os.path.join(DEPLOY, "serve.sh"), 0o755)

# 3. Create serve.bat (Windows)
serve_bat = r'''@echo off
REM 一键启动 GitHub 导航站 (Windows)
set PORT=8080
echo GitHub 导航站已启动: http://localhost:%PORT%
echo 按 Ctrl+C 停止
python -m http.server %PORT% --directory "%~dp0"
'''

with open(os.path.join(DEPLOY, "serve.bat"), "w") as f:
    f.write(serve_bat)

# 4. Create README
readme = '''# GitHub 5000+ Star 项目中文导航

6788 个开源项目 · 22 个分类 · 含大白话解读

## 快速启动

### 方式1: 一行命令 (Mac/Linux)
```bash
./serve.sh
```
浏览器打开 http://localhost:8080

### 方式2: 双击 (Windows)
```bat
serve.bat
```
浏览器打开 http://localhost:8080

### 方式3: Python 直接启
```bash
python3 -m http.server 8080
```

### 方式4: 部署到云 (免费)
1. 把 deploy/ 目录上传到 GitHub 仓库
2. 在仓库 Settings → Pages → 选 main 分支 → Save
3. 几分钟后访问 https://你的用户名.github.io/仓库名

支持: GitHub Pages / Netlify / Vercel / Cloudflare Pages / 任何静态托管

## 功能
- 🔍 搜索项目名、描述、人话解读
- 📂 22个分类筛选
- 📖 点击"人话"标签看大白话解读
- ⭐ 按星标数排序
- 📱 手机/电脑自适应

## 数据更新
数据源: GitHub API (5000+ 星标项目)
最后更新: 见 index.html 底部
'''

with open(os.path.join(DEPLOY, "README.txt"), "w", encoding="utf-8") as f:
    f.write(readme)

# 5. Create self-contained single-file version (for file:// double-click)
print("生成自包含单文件版...")
with open(HTML_SRC, encoding="utf-8") as f:
    html = f.read()

with open(JSON_SRC, encoding="utf-8") as f:
    data_json = f.read()

# Inline surge data (may not exist yet — skip if missing)
SURGE_SRC = os.path.join(BASE, "surge_top100.json")
if os.path.exists(SURGE_SRC):
    with open(SURGE_SRC, encoding="utf-8") as f:
        surge_json = f.read()
    surge_safe = json.dumps(surge_json).replace('</', '<\\/')
    old_surge_fetch = "const surgeResp = await fetch('surge_top100.json');"
    new_surge_fetch = f"const surgeResp = new Response({surge_safe});"
    html = html.replace(old_surge_fetch, new_surge_fetch)

# Replace fetch('projects.json') with inline data
# CRITICAL: escape </script> to prevent HTML parser from closing <script> tag
js_safe = json.dumps(data_json).replace('</', '<\\/')
old_fetch = "const resp = await fetch('projects.json');"
new_fetch = f"const resp = new Response({js_safe});"
standalone = html.replace(old_fetch, new_fetch)

# Remove preload hint (no longer needed)
standalone = standalone.replace('<link rel="preload" href="projects.json" as="fetch" crossorigin="anonymous">\n', '')

standalone_path = os.path.join(DEPLOY, "standalone.html")
with open(standalone_path, "w", encoding="utf-8") as f:
    f.write(standalone)

# 6. Stats
total_size = sum(os.path.getsize(os.path.join(DEPLOY, f)) for f in os.listdir(DEPLOY))
print(f"\n✅ 部署包: {os.path.abspath(DEPLOY)}/")
print(f"   总大小: {total_size // 1024 // 1024}MB")
for f in sorted(os.listdir(DEPLOY)):
    size = os.path.getsize(os.path.join(DEPLOY, f))
    print(f"   {f:20s} {size//1024:>5}KB")
print(f"\n部署方式:")
print(f"   本地: cd {DEPLOY} && ./serve.sh")
print(f"   云端: 上传 deploy/ 到 GitHub Pages / Netlify")
print(f"   离线: 浏览器打开 deploy/standalone.html")
