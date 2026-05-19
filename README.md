# ⭐ GitHub 5000+ Star 项目中文导航

**你缺的不是技术，是一个用人话告诉你 GitHub 上什么东西能用的导航站。**

🔍 7000 个项目 × 🌐 中文翻译 × 💬 大白话解读 × 🤖 每两天自动更新 × 📖 开源免费

⏱️ 三分钟扫一眼，比你刷三年 Trending 有用。

👉 [在线浏览](https://SoulSpark-CN.github.io/github-cn-nav) | [下载离线版](https://github.com/SoulSpark-CN/github-cn-nav/releases/latest/download/standalone.html)

⚠️ 本仓库不是 GitHub 官方项目，是一个社区维护的中文开源导航站。

---

## 里面有什么

| 数据 | 数量 |
|------|------|
| 收录项目 | 6,788 个（全部 5000+ Star） |
| 分类 | 22 个（前端/后端/AI/安全/量化...） |
| 中文描述 | 6,752 条 |
| 人话解读 | 6,752 条（一句话总结+大白话解释+生活类比+适合人群） |

每条人话解读包含四层：
- **一句话 Slogan** — 这是干嘛的
- **大白话解释** — 2-3 句讲清楚
- **生活类比** — 用一个日常场景打比方
- **适合谁** — 目标人群+解决什么问题

## 三种打开方式

### 1. 在线看（推荐）
直接访问 GitHub Pages：`https://你的用户名.github.io/仓库名`

### 2. 下载离线版
从 [Releases](https://github.com/SoulSpark-CN/github-cn-nav/releases) 下载 `standalone.html`，浏览器双击打开，不需要网络。

### 3. 自己跑
```bash
git clone https://github.com/SoulSpark-CN/github-cn-nav.git
cd github-cn-nav/deploy
python3 -m http.server 8080
# 浏览器打开 http://localhost:8080
```

## 数据怎么来的

```
GitHub API (搜索5000+星项目)
    → 去重
    → AI 分类（22个类别）
    → AI 翻译中文 + 生成人话解读
    → 合并为 projects.json
    → 生成轻量导航页（15KB HTML + 5MB JSON）
```

全自动流水线，**每 2 天跑一次**，自动发现新项目、自动翻译、自动更新站点。

## 自动更新机制

通过 GitHub Actions 定时运行（每 2 天 UTC 8:00）：
1. 搜索 GitHub 上新增的 5000+ 星项目
2. AI 分类 + 翻译 + 人话解读（一次 API 调用搞定）
3. 合并数据，重建导航页
4. 自动部署到 GitHub Pages

成本：DeepSeek API 每次几分钱，GitHub Actions 免费额度完全够用。

## 文件结构

```
├── manifest.json              # 原始项目数据（3.3MB）
├── 人话解读.json              # 人话解读数据（4.2MB）
├── projects.json              # 导航页用的合并数据（5.4MB）
├── translate_batch_*_done.json # 翻译批次结果
├── phase3_enhanced.py         # AI 分类器
├── auto_update.py             # 自动更新主脚本
├── deploy.py                  # 部署打包脚本
├── 导航.html                  # 轻量导航页模板（15KB）
├── browse.sh                  # 一键本地浏览
└── deploy/                    # 可部署的静态站点
    ├── index.html             # 在线版（fetch JSON）
    ├── standalone.html        # 离线版（JSON 内嵌，双击即用）
    ├── projects.json          # 数据文件
    ├── serve.sh               # 一键启动脚本
    └── README.txt
```

## 参与贡献

- 发现漏掉的好项目？提 Issue
- 分类不对？提 PR 改 `phase3_enhanced.py` 的分类规则
- 某条解读不准？直接改 `人话解读.json`

## License

MIT — 数据随便用，代码随便改，署名就行。
