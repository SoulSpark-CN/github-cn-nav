# GitHub 中文导航站 — AI 助手指南

> 版本: 1.0 | 最后更新: 2026-06-25
> 项目路径: `~/赚钱现金流项目/github中文导航站/`

## ① 项目定位

> 收录 GitHub 5000+ Star 项目，用中文翻译+人话解读做导航站。

数据量 7402 项目，7070 条人话解读，22 分类。自动更新。当前问题是还没想清楚"谁用、为什么用"——数据够了，缺策展和用户场景。

## ② 目录结构

```
项目根/
├── src/                    # Python 源码
│   ├── auto_update.py      # 自动更新主脚本
│   ├── deploy.py           # 静态站点生成
│   ├── classify_module.py  # 分类引擎
│   ├── phase3_enhanced.py  # 22分类规则
│   ├── compute_surge.py    # 飙升计算
│   ├── compute_surge_v2.py # 飙升计算 v2
│   └── utils.py            # 工具函数
├── data/                   # 数据文件
│   ├── projects.json       # 主数据（7402条，含rh字段）
│   ├── 人话解读.json       # 人话解读（7070条）
│   ├── manifest.json       # 原始元数据
│   ├── surge_top100.json   # 飙升榜
│   └── snapshots/          # 数据快照
├── deploy/                 # 可部署的静态站点
│   ├── index.html          # 在线版
│   ├── standalone.html     # 离线版
│   ├── projects.json       # 数据副本
│   └── serve.sh / serve.bat
├── .github/workflows/update.yml  # CI 自动更新
├── README.md
└── 项目全景/
    └── AGENTS.md           # 本文件
```

## ③ 数据流

```
GitHub API 搜新项目
  ↓
classify_module.py 分类（22类）
  ↓
auto_update.py 翻译+人话解读（DeepSeek API，一次调用搞定4个字段）
  ↓
atomic_write_json → data/人话解读.json (7070条)
  ↓
rebuild_projects_json → data/projects.json (7402条，含rh字段)
  ↓
deploy.py → deploy/ (index.html + projects.json)
  ↓
GitHub Actions → GitHub Pages
```

**成本：** DeepSeek API 几分钱/次，GitHub Actions 免费额度够用。

## ④ 人话解读格式

每条包含 4 个字段：

| 字段 | 含义 | 短格式 | 长格式 |
|------|------|--------|--------|
| 一句话 Slogan | 这是干啥的（事实性，不耍比喻） | `o` | `one_liner` |
| 大白话解释 | 2-3 句讲清楚 | `p` | `plain` |
| 生活类比 | 用日常场景打比方 | `a` | `analogy` |
| 适合谁 | 目标人群+解决什么问题 | `u` | `audience` |

**当前状态：** 438 条长格式 + 6632 条短格式，前端兼容两种。需统一为长格式。

## ⑤ 关键命令

```bash
cd ~/赚钱现金流项目/github中文导航站
python3 src/deploy.py           # 生成 deploy/ 目录
python3 src/auto_update.py      # 触发更新（GitHub API → 翻译 → 合并）
python3 src/compute_surge.py    # 计算飙升榜
```

## ⑥ 待办

- [ ] 人话解读统一格式（短→长，全覆盖）
- [ ] 人话解读质量审核（one-liner 去公式化）
- [ ] 定义策展场景（周报/分类精选/新人指南）
- [ ] 前端优化：主卡展示 one-liner 而非 audience（当前 line 124 逻辑反了）
