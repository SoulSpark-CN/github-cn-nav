# 新势力崛起 — AI 助手指南

> 版本: 3.1 | 最后更新: 2026-07-19
> 路径: `~/赚钱现金流项目/github中文导航站/`
> 凭证: `~/.hermes/identity/github-cn-nav.md`

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
│   ├── index.html        # 前端
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
# 本地跑
cd ~/赚钱现金流项目/github中文导航站
export GITHUB_TOKEN="ghp_..."     # 见 ~/.hermes/identity/github-cn-nav.md
export DEEPSEEK_API_KEY="sk-..."  # 见 ~/.hermes/identity/github-cn-nav.md
python3 src/surge_rising.py --days 10 --top 100 --workers 10
python3 src/deploy.py
```

## ⑤ 监控与报警（血的教训）<!-- 2026-07-19 -->

**2026-07-14 重构 v3 后 → 07-19 整整 5 天 CI 静默失败，网站显示占位数据，无人知晓。根因：重构后加了 DeepSeek 翻译步骤但没配 key，CI 无报警机制。**

### CI 失败报警规则

| 规则 | 措施 |
|------|------|
| **CI 连续 2 天未产生新 commit** | Hermes 发 Telegram 报警："github中文导航站 CI 可能挂了，最后更新 N 天前" |
| **surge_rising_top100.json 数据 ≤ 1 项** | 立即报警——占位数据在线上 |
| **重构 pipeline 后** | 必须端到端验证一次（本地跑通 + 看线上站点） |
| **新增外部 API 依赖（DeepSeek/GitHub）** | 必须验证 key 在 CI 环境可用（GitHub Secrets 已配 + API 可连通） |

### 监控 cron

需要在 Hermes 里建一个 cron job：每天检查 `https://soulspark-cn.github.io/github-cn-nav/` 的数据项数，≤1 项就报警。

## ⑥ 规则

1. 凭证统一存 `~/.hermes/identity/github-cn-nav.md`，700 权限，不归 git
2. 本地运行前先读此文件取 key——不要让用户手动输入
3. **管道重构后必须端到端验证——本地跑通 + 线上站点检查**<!-- 2026-07-19 -->
4. **任何外部 API 依赖变更→检查 GitHub Secrets 是否同步**<!-- 2026-07-19 -->
5. **网站数据不能装死——占位数据是线上事故**<!-- 2026-07-19 -->
