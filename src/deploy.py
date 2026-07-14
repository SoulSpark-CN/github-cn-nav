#!/usr/bin/env python3
"""
部署包生成器 - 生成 deploy/ 静态站点
用法: python3 deploy.py
产出: deploy/ 目录，内含 index.html + surge_rising_top100.json + standalone.html
"""
import json, os, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEPLOY = str(BASE / "deploy")
HTML_SRC = str(BASE / "deploy" / "index.html")
SURGE_SRC = str(BASE / "data" / "surge_rising_top100.json")

os.makedirs(DEPLOY, exist_ok=True)

# 1. Copy data
if os.path.exists(SURGE_SRC):
    shutil.copy2(SURGE_SRC, os.path.join(DEPLOY, "surge_rising_top100.json"))
else:
    print("⚠️  surge_rising_top100.json 不存在，请先运行 surge_rising.py")

# 2. Self-contained standalone.html
print("生成 standalone.html...")
with open(HTML_SRC, encoding="utf-8") as f:
    html = f.read()

if os.path.exists(SURGE_SRC):
    with open(SURGE_SRC, encoding="utf-8") as f:
        surge_json = f.read()
    surge_safe = json.dumps(surge_json).replace('</', '<\\/')
    old_fetch = "const resp = await fetch('surge_rising_top100.json');"
    new_fetch = f"const resp = new Response({surge_safe});"
    html = html.replace(old_fetch, new_fetch)

standalone_path = os.path.join(DEPLOY, "standalone.html")
with open(standalone_path, "w", encoding="utf-8") as f:
    f.write(html)

# 3. Stats
total_size = sum(os.path.getsize(os.path.join(DEPLOY, f)) for f in os.listdir(DEPLOY))
print(f"✅ deploy/: {total_size//1024}KB")
for f in sorted(os.listdir(DEPLOY)):
    size = os.path.getsize(os.path.join(DEPLOY, f))
    print(f"   {f:30s} {size//1024:>4}KB")
