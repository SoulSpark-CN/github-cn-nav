# GitHub 中文导航站 — AI 助手指南

> 版本: 2.0 | 最后更新: 2026-07-14
> 项目路径: `~/赚钱现金流项目/github中文导航站/`

## ① 项目定位

> 收录 GitHub 5000+ Star 项目，用中文翻译+人话解读做导航站。

数据量 7402 项目，7070 条人话解读，22 分类，10天新势力崛起榜。自动更新。

## ② 目录结构

```
项目根/
├── src/                    # Python 源码
│   ├── auto_update.py      # 自动更新主脚本（增量搜项目 + 翻译）
│   ├── surge_rising.py     # 新势力崛起榜（GH Archive 10天数据）
│   ├── deploy.py           # 静态站点生成
│   ├── classify_module.py  # 分类引擎
│   ├── phase3_enhanced.py  # 22分类规则（旧）
│   └── utils.py            # 工具函数
├── data/                   # 数据文件
│   ├── projects.json       # 主数据（7402条）
│   ├── 人话解读.json       # 人话解读（7070条）
│   ├── manifest.json       # 原始元数据
│   ├── surge_rising_top100.json  # 新势力崛起榜 Top100
│   └── snapshots/          # 数据快照
├── deploy/                 # 可部署的静态站点
│   ├── index.html          # 在线版
│   ├── standalone.html     # 离线版
│   └── serve.sh / serve.bat
├── .github/workflows/update.yml  # CI 自动更新
├── README.md
└── 项目全景/
    └── Project.md          # 本文件
```

## ③ 数据流

```
GH Archive (10天WatchEvent) → surge_rising.py → 全量扫描所有仓库
  → GitHub API 验证星数（筛选1000-30000）
  → DeepSeek 翻译人话解读
  → data/surge_rising_top100.json
  → deploy.py → deploy/
  → 前端 "_rising" / "_trending" 分类展示

GitHub API 搜新项目 → classify_module.py 分类
  → auto_update.py 翻译+人话解读（DeepSeek）
  → data/projects.json + data/人话解读.json
  → deploy.py → deploy/
```

**成本：** DeepSeek API 几分钱/次，GitHub Actions 免费额度够用。

## ④ 关键命令

```bash
cd ~/赚钱现金流项目/github中文导航站
python3 src/surge_rising.py --days 10 --top 100    # 生成新势力崛起榜
python3 src/deploy.py          # 生成 deploy/ 目录
python3 src/auto_update.py     # 触发增量更新
```

## ⑤ 待办

- [ ] 人话解读老格式统一为长格式（6632条待转）
- [ ] 新势力榜的前端展示优化
