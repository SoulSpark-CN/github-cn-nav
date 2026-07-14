# 新势力崛起 — AI 助手指南

> 版本: 3.0 | 最后更新: 2026-07-14
> 路径: `~/赚钱现金流项目/github中文导航站/`

## ① 定位

> 发现 GitHub 上正在快速崛起的技术新势力。1000-30000 星项目，按 10 天涨星数排名 Top 100，DeepSeek 人话解读。

## ② 目录

```
项目根/
├── src/
│   ├── surge_rising.py   # 核心：GH Archive → 验证 → 翻译 → 输出
│   ├── deploy.py         # 生成 deploy/ + standalone.html
│   └── utils.py          # Token、日志、原子写入
├── data/
│   └── surge_rising_top100.json  # 输出数据
├── deploy/
│   ├── index.html        # 前端（简洁列表，~120行）
│   └── standalone.html   # 离线版
└── .github/workflows/update.yml
```

## ③ 数据流

```
GH Archive 241h → 全量 WatchEvent 统计
  → 前300候选 → GitHub API 验星(1000-30000)
  → Top100 → DeepSeek 翻译(one_liner/plain/audience)
  → surge_rising_top100.json
  → deploy.py → deploy/ → GitHub Pages
```

## ④ 命令

```bash
python3 src/surge_rising.py --days 10 --top 100 --workers 10
python3 src/deploy.py
```
