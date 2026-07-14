# 🚀 新势力崛起 · GitHub 10日涨星榜

**发现正在快速崛起的技术新势力——1000-30000 星之间的 GitHub 项目，按最近 10 天涨星数排名。**

🔍 GH Archive 全量扫描 × 🤖 DeepSeek 人话解读 × ⏱️ 每日自动更新

👉 [在线浏览](https://SoulSpark-CN.github.io/github-cn-nav) | [下载离线版](https://github.com/SoulSpark-CN/github-cn-nav/releases/latest/download/standalone.html)

## 怎么算出来的

1. 下载最近 10 天 GH Archive 全部数据（~240 个文件）
2. 全量统计所有仓库的 WatchEvent，取前 300 候选
3. 调 GitHub API 验证实际星数，筛选 1000-30000 星
4. 按 10 天涨星数排名，取 Top 100
5. DeepSeek 生成中文解读：一句话 + 白话解释 + 适合谁

## 每条包含

| 内容 | 说明 |
|------|------|
| 一句话 | 这是干嘛的 |
| 白话解释 | 主要用途、解决什么问题 |
| 适合谁 | 目标人群和使用场景 |

## 自动更新

GitHub Actions 每天 UTC 8:00（北京时间 16:00）自动运行。

成本：DeepSeek API 几分钱/次，GitHub Actions 免费额度够用。
