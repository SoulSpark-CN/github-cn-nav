#!/usr/bin/env python3
"""
新势力崛起榜 — 基于 GH Archive 10 天 WatchEvent + GitHub API 当前星数
用法: python3 surge_rising.py [--dry-run] [--days 10] [--top 100]
输出: data/surge_rising_top100.json

数据流:
  1. 下载最近 10 天 GH Archive 所有小时文件 (240 个)
  2. 统计所有仓库的 WatchEvent 数（不限已知仓库，全量扫描）
  3. 取涨星最多的前 300 个候选
  4. 调 GitHub API 查当前星数、描述、语言等
  5. 筛选 1000 ≤ 星数 ≤ 30000（"新势力"区间）
  6. 按 10 天涨星数排名取 Top 100
  7. 调 DeepSeek 生成中文人话解读
  8. 写入 surge_rising_top100.json
"""
import json, os, sys, gzip, re, tempfile, time as time_mod
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request, HTTPError
from urllib.error import URLError
import logging

from utils import setup_logger, atomic_write_json, get_github_token, get_llm_key, get_llm_config

logger = setup_logger("surge_rising")

BASE = Path(__file__).resolve().parent.parent
OUTPUT_FILE = str(BASE / "data" / "surge_rising_top100.json")
GH_ARCHIVE_BASE = "https://data.gharchive.org"
USER_AGENT = "github-cn-nav/3.0"

# ─── 参数 ───
DEFAULT_DAYS = 10
DEFAULT_TOP = 100
CANDIDATE_POOL = 300  # 初筛候选数
STAR_FLOOR = 1000
STAR_CEILING = 30000

# ─── GH Archive ───
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

GH_TOKEN = get_github_token()
LLM_KEY = get_llm_key()
LLM_CFG = get_llm_config()

GH_HDR = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": USER_AGENT,
    "Authorization": f"token {GH_TOKEN}",
}
LLM_HDR = {
    "Authorization": f"Bearer {LLM_KEY}",
    "Content-Type": "application/json",
}


def list_archive_hours(days: int) -> list:
    """列出需要下载的 GH Archive 小时文件 URL（排除未来 4h 内可能不存在的）"""
    now = datetime.now(timezone.utc)
    end = now - timedelta(hours=4)  # 留 4h 缓冲
    start = end - timedelta(days=days)
    start = start.replace(minute=0, second=0, microsecond=0)
    end = end.replace(minute=0, second=0, microsecond=0)

    urls = []
    current = start
    while current <= end:
        urls.append(f"{GH_ARCHIVE_BASE}/{current.strftime('%Y-%m-%d-%H')}.json.gz")
        current += timedelta(hours=1)
    logger.info("GH Archive: %d 小时文件 (%s → %s)", len(urls),
                start.strftime('%m-%d %H:00'), end.strftime('%m-%d %H:00'))
    return urls


def precheck_archive_hours(urls: list, workers: int = 10) -> tuple:
    """HEAD 预检哪些文件存在。404→跳过，其他→保留"""
    def _check(url):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
            with urlopen(req, timeout=15) as resp:
                return ("ok", url)
        except HTTPError as e:
            return ("missing", url) if e.code == 404 else ("retry", url)
        except (URLError, TimeoutError, OSError):
            return ("retry", url)

    available, skipped = [], []
    retry_later = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_check, u): u for u in urls}
        for f in as_completed(futures):
            status, url = f.result()
            if status == "ok":
                available.append(url)
            elif status == "missing":
                skipped.append(url)
            else:
                retry_later.append(url)

    available.extend(retry_later)
    if skipped:
        logger.warning("跳过 %d/%d 个不存在的文件", len(skipped), len(urls))
    if retry_later:
        logger.warning("%d 个文件预检网络抖动，下载阶段重试", len(retry_later))
    return available, skipped


def count_all_watch(url: str, max_retries: int = 3) -> Counter:
    """下载一个 GH Archive 小时文件，统计所有仓库的 WatchEvent"""
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=120) as resp:
                count = Counter()
                total_events = 0
                watch_events = 0
                with gzip.GzipFile(fileobj=resp) as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            total_events += 1
                            if event.get("type") != "WatchEvent":
                                continue
                            watch_events += 1
                            repo_name = event.get("repo", {}).get("name", "").lower()
                            if repo_name:
                                count[repo_name] += 1
                        except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
                            pass
                if total_events > 0:
                    logger.debug("%s: %d events, %d WatchEvents, %d repos",
                                 url.split("/")[-1], total_events, watch_events, len(count))
            return count
        except HTTPError as e:
            if e.code < 500:
                logger.warning("⚠ %s: HTTP %d", url, e.code)
                return Counter()
            if attempt < max_retries:
                time_mod.sleep(2 ** attempt)
        except Exception as e:
            if attempt < max_retries:
                time_mod.sleep(2 ** attempt)
    logger.error("❌ %s: 全部重试失败", url)
    return Counter()


# ─── GitHub API ───
def fetch_repo_details(candidates: list) -> list:
    """用 GitHub API 逐个查询仓库详情：星数、描述、语言、近 push 时间、fork 数"""
    logger.info("查询 %d 个候选仓库详情...", len(candidates))
    verified = []
    for i, c in enumerate(candidates):
        owner, repo_name = c["repo"].split("/", 1)
        api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
        try:
            req = Request(api_url, headers=GH_HDR)
            with urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    stars = data.get("stargazers_count", 0)
                    verified.append({
                        "repo": c["repo"],
                        "stars": stars,
                        "surge_10d": c["count"],
                        "lang": data.get("language") or "-",
                        "desc": (data.get("description") or "")[:200],
                        "url": data["html_url"],
                        "topics": data.get("topics", []),
                        "forks": data.get("forks_count", 0),
                        "pushed_at": data.get("pushed_at", ""),
                    })
                elif resp.status == 404:
                    logger.debug("✗ %s: 404", c["repo"])
                elif resp.status == 403:
                    logger.warning("GitHub API 限速，已处理 %d/%d", i, len(candidates))
                    break
                else:
                    logger.debug("⚠ %s: HTTP %d", c["repo"], resp.status)
        except Exception as e:
            logger.debug("✗ %s: %s", c["repo"], e)

        time_mod.sleep(0.15)  # 温和限速，避免次级限速

    logger.info("获得 %d 个仓库详情", len(verified))
    return verified


def filter_rising_stars(repos: list, floor: int = 1000, ceiling: int = 30000, top_n: int = 100) -> list:
    """筛选 1000-30000 星之间，按 surge_10d 降序"""
    filtered = [r for r in repos if floor <= r["stars"] <= ceiling]
    logger.info("筛选: %d/%d 在 %d-%d 星范围内", len(filtered), len(repos), floor, ceiling)
    filtered.sort(key=lambda r: -r["surge_10d"])
    return filtered[:top_n]


# ─── DeepSeek 翻译 ───
def translate_rising_stars(repos: list) -> None:
    """批量调用 DeepSeek 为人话解读（5 个一批，减少 API 调用）"""
    if not repos:
        return
    logger.info("翻译 %d 个新势力项目...", len(repos))
    batch_size = 5

    for i in range(0, len(repos), batch_size):
        batch = repos[i:i + batch_size]
        lines = []
        for j, r in enumerate(batch):
            topics_str = ", ".join(r.get("topics", [])[:5])
            lines.append(f"[{j}] {r['repo']} (⭐{r['stars']}, 10天涨{r['surge_10d']}⭐): {r['desc'][:150]} | topics: {topics_str}")

        prompt = f"""你是 GitHub 项目中文解读师。以下项目最近 10 天在 GitHub 上快速涨星，
是新崛起的有潜力项目。请用中文给出简洁解读。

返回严格 JSON 数组:
```json
[
  {{"idx": 0, "one_liner": "一句话说清楚这是干嘛的（20字内）", "plain": "2-3句大白话解释：主要用途、怎么用、解决什么问题", "audience": "适合什么人？什么场景下用？"}}
]
```

规则:
- one_liner 用简洁中文，技术名词保留英文
- plain 要体现实质：不只是"某某框架"，要说清楚具体做什么
- audience 写目标人群和使用场景
- 实事求是，不要吹

项目列表:
{chr(10).join(lines)}"""

        for retry in range(5):
            try:
                r = requests_post(LLM_CFG["api"], LLM_HDR, {
                    "model": LLM_CFG["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 6000,
                    "temperature": 0.3,
                }, timeout=120)

                if r is None:
                    time_mod.sleep(10)
                    continue

                text = r.json()["choices"][0]["message"]["content"]
                items = _parse_llm_json(text)

                if items is None or not isinstance(items, list):
                    logger.warning("batch %d: JSON 解析失败", i // batch_size + 1)
                    time_mod.sleep(5)
                    continue

                for item in items:
                    idx = item.get("idx")
                    if idx is None or idx < 0 or idx >= len(batch):
                        continue
                    repos[i + idx]["one_liner"] = item.get("one_liner", "")
                    repos[i + idx]["plain"] = item.get("plain", "")
                    repos[i + idx]["audience"] = item.get("audience", "")

                logger.info("batch %d: ✓ %d 条", i // batch_size + 1, len(items))
                break

            except Exception as e:
                logger.warning("batch %d: [%s] 重试 %d/5", i // batch_size + 1, e, retry + 1)
                time_mod.sleep(10)

        time_mod.sleep(1)  # DeepSeek 调用间隔


def _parse_llm_json(text: str):
    """尝试多种方式解析 LLM 返回的 JSON"""
    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 提取 ```json ``` 块
    import re
    match = re.search(r'```json\s*(\[.*?\])\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. 提取第一个 [ ... ] 块
    match = re.search(r'(\[.*\])', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


# ─── HTTP helpers ───
import requests

def requests_post(url, headers, json_data, timeout=120):
    """requests 库 POST，带超时和错误处理。非200返回None"""
    try:
        r = requests.post(url, headers=headers, json=json_data, timeout=timeout, verify=False)
        if r.status_code == 200:
            return r
        logger.warning("HTTP %d: %s", r.status_code, r.text[:200])
        return None
    except Exception as e:
        logger.warning("HTTP POST 失败: %s", e)
        return None


# ─── Main ───
def main(days: int = DEFAULT_DAYS, top_n: int = DEFAULT_TOP, workers: int = 10, dry_run: bool = False):
    logger.info("=" * 50)
    logger.info("新势力崛起榜 v1: %d 天窗口, Top %d", days, top_n)
    logger.info("范围: %d - %d 星", STAR_FLOOR, STAR_CEILING)
    logger.info("=" * 50)

    # Phase 1: download GH Archive and count ALL WatchEvents
    logger.info("[1/4] 下载 GH Archive 数据 (%d 天)...", days)
    all_urls = list_archive_hours(days)
    urls, skipped = precheck_archive_hours(all_urls, workers=min(workers, 15))
    if not urls:
        logger.error("没有可用的 GH Archive 文件")
        return []

    all_counts = Counter()
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(count_all_watch, u): u for u in urls}
        for f in as_completed(futures):
            count = f.result()
            all_counts.update(count)
            completed += 1
            if completed % 20 == 0 or completed == len(urls):
                logger.info("  进度: %d/%d | %d 个仓库 | %d 事件",
                            completed, len(urls), len(all_counts),
                            sum(all_counts.values()))

    if not all_counts:
        logger.error("Phase 1: 没有统计到任何 WatchEvent")
        return []

    logger.info("Phase 1 完成: %d 个仓库有 WatchEvent", len(all_counts))

    # Phase 2: top candidates → verify via GitHub API
    logger.info("[2/4] 取前 %d 候选，查 GitHub API...", CANDIDATE_POOL)
    top_candidates = [
        {"repo": repo, "count": count}
        for repo, count in all_counts.most_common(CANDIDATE_POOL)
    ]

    verified = fetch_repo_details(top_candidates)

    if not verified:
        logger.error("Phase 2: 无法获取任何仓库详情")
        return []

    # Phase 3: filter and rank
    logger.info("[3/4] 筛选 %d-%d 星 + 排序...", STAR_FLOOR, STAR_CEILING)
    rising = filter_rising_stars(verified, floor=STAR_FLOOR, ceiling=STAR_CEILING, top_n=top_n)

    if not rising:
        logger.warning("筛选后无结果，扩宽范围试试")
        # 放宽到不设天花板，保留 Top N
        rising = sorted(verified, key=lambda r: -r["surge_10d"])[:top_n]
        logger.info("放宽范围: %d 个项目", len(rising))

    # Phase 4: DeepSeek translation
    if not dry_run:
        logger.info("[4/4] 翻译...")
        translate_rising_stars(rising)

    # 组装结果
    for i, r in enumerate(rising):
        r["rank"] = i + 1

    result = {
        "data": rising,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": days,
        "filter": {"floor": STAR_FLOOR, "ceiling": STAR_CEILING},
        "total_candidates": len(verified),
        "total_archive_hours": len(urls),
    }

    if skipped:
        result["_warning"] = f"GH Archive 部分缺失: {len(skipped)}/{len(all_urls)} 个文件不存在"

    # 写入
    atomic_write_json(result, OUTPUT_FILE, ensure_ascii=False, indent=2)
    logger.info("\n✅ 写入 %s (%d 条)", OUTPUT_FILE, len(rising))

    # 打印榜单
    logger.info("\n═══ 新势力崛起榜 Top %d ═══", min(len(rising), 20))
    for r in rising[:20]:
        oneliner = r.get("one_liner", "")[:40]
        logger.info("  %2d. %-40s ⭐%s +%s  %s",
                    r["rank"], r["repo"], r["stars"], r["surge_10d"], oneliner)

    return rising


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    main(days=args.days, top_n=args.top, workers=args.workers, dry_run=args.dry_run)
