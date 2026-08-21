# 新势力崛起 · github 中文导航站 · 项目 AGENTS.md

> 2026-08-16 由 Project.md 转换（原文保留本目录 `Project.md`）。位置：`C:\Users\63966\dev\github-cn-nav\`（git 仓库 main 分支）。

## 是什么

发现 GitHub 正在快速崛起的技术新势力。1000-30000 星项目，按 10 天涨星数排名 Top 100，DeepSeek 人话解读（one_liner/plain/audience 三条）。

## 现状（2026-08-16 迁移后）

- 线上站点：https://soulspark-cn.github.io/github-cn-nav/（GitHub Pages 自动部署）
- **主更新 100% 在 GitHub Actions**（`update.yml`，每日 14:00 UTC=北京 22:00，数据变化才 commit；2026-08-21 从 08:00 UTC=北京16:00 高峰挪到空闲时段；9 步管道：GH Archive 241h 下载→WatchEvent 统计→验星→筛选→DeepSeek 翻译→写 JSON→deploy→push gh-pages）
- **新鲜度报警已迁 GHA**：`freshness-check.yml` 每日 22:30（北京，2026-08-21 从 09:00 高峰挪到空闲时段）检查线上数据（≤1 项 / updated 超 2 天 → 失败 + PushPlus 微信通知）
- 依赖仅 requests；DeepSeek key 在 GitHub Secrets；本地开发 key 在 `C:\Users\63966\.secrets\credentials\github-cn-nav.md`
- GH Archive 约 40% 小时文件缺失是数据源现状（管道已容错，带 _warning）

## 数据流

GH Archive 241h → 全量 WatchEvent 统计 → 前300候选 → GitHub API 验星(1000-30000) → Top100 → DeepSeek 翻译 → `data/surge_rising_top100.json` → `deploy.py` → deploy/ → GitHub Pages

## 规则（血的教训，2026-07-14~19 五天静默失败事故）

1. 凭证统一存 `.secrets\credentials\github-cn-nav.md`，不归 git
2. 本地运行前先读此文件取 key（GITHUB_TOKEN + DEEPSEEK_API_KEY 环境变量），不让用户手动输入
3. **管道重构后必须端到端验证——本地跑通 + 线上站点检查**
4. **任何外部 API 依赖变更→检查 GitHub Secrets 是否同步**
5. **网站数据不能装死——占位数据是线上事故**（数据 ≤1 项 = 事故）

## 本地开发

```bash
cd C:\Users\63966\dev\github-cn-nav
# 从 .secrets\credentials\github-cn-nav.md 读 GITHUB_TOKEN 和 DEEPSEEK_API_KEY 设环境变量
python src/surge_rising.py --days 10 --top 100 --workers 10
python src/deploy.py
```

## 提问

1. 要不要把 Top 100 扩展成周报/月报推送？
2. 榜单数据能不能做成 API 供其他项目复用？
