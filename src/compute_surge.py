#!/usr/bin/env python3
"""
近5日飙升计算器 — 基于 GH Archive 真实 star 增量
v2: 添加超时、日志、安全的文件处理。
"""
import json, os, sys, gzip, io, subprocess, re, tempfile, time as time_mod
from datetime import datetime, timedelta, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request, HTTPError
import logging

from utils import setup_logger

logger = setup_logger("compute_surge")

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECTS_FILE = os.path.join(BASE, "projects.json")
OUTPUT_FILE = os.path.join(BASE, "surge_top100.json")
DISCOVERY_FILE = os.path.join(BASE, "discovery_candidates.json")
GH_ARCHIVE_BASE = "https://data.gharchive.org"

USER_AGENT = "surge-compute/2.0"

def extract_repo_names() -> set:
    """从 projects.json 提取所有 owner/repo"""
    with open(PROJECTS_FILE) as f:
        data = json.load(f)
    names = set()
    for p in data:
        url = p.get("url", "")
        m = re.search(r'github\.com/([^/]+/[^/\s]+)', url)
        if m:
            names.add(m.group(1).lower())
    logger.info("提取 %d 个仓库名", len(names))
    return names

def list_archive_hours(days: int = 5) -> list:
    """列出需要下载的 GH Archive 小时文件 URL（去掉冗余偏移）"""
    now = datetime.now(timezone.utc)
    end = now - timedelta(hours=2)  # GH Archive 通常有 1-2h 延迟
    start = end - timedelta(days=days)
    # 对齐到整小时
    start = start.replace(minute=0, second=0, microsecond=0)
    end = end.replace(minute=0, second=0, microsecond=0)

    urls = []
    current = start
    while current <= end:
        urls.append(f"{GH_ARCHIVE_BASE}/{current.strftime('%Y-%m-%d-%H')}.json.gz")
        current += timedelta(hours=1)
    logger.info(
        "需要下载 %d 个小时文件 (%s → %s)",
        len(urls), start.strftime('%Y-%m-%d %H:00'), end.strftime('%Y-%m-%d %H:00'),
    )
    return urls

def download_and_count(url: str, target_repos: set, max_retries: int = 3) -> Counter:
    """下载一个 GH Archive 文件，统计目标仓库 WatchEvent（带超时和重试）"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
            count = Counter()
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        if event.get("type") != "WatchEvent":
                            continue
                        repo_name = event.get("repo", {}).get("name", "").lower()
                        if repo_name in target_repos:
                            count[repo_name] += 1
                    except (json.JSONDecodeError, KeyError):
                        pass
            return count
        except HTTPError as e:
            if e.code < 500:  # 4xx 客户端错误不再重试
                logger.warning("⚠ %s: HTTP %d (不重试)", url, e.code)
                return Counter()
            last_err = e
            if attempt < max_retries:
                sleep_time = 2 ** attempt
                logger.warning("⚠ %s: HTTP %d, 重试 %d/%d (等待 %ds)", url, e.code, attempt, max_retries, sleep_time)
                time_mod.sleep(sleep_time)
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                sleep_time = 2 ** attempt
                logger.warning("⚠ %s: %s, 重试 %d/%d (等待 %ds)", url, e, attempt, max_retries, sleep_time)
                time_mod.sleep(sleep_time)
    logger.error("❌ %s: 已重试 %d 次均失败: %s", url, max_retries, last_err)
    return Counter()

def compute_surge(days: int = 5, top_n: int = 100, workers: int = 20):
    """主流程：下载 → 过滤 → 排序 → 输出"""
    target_repos = extract_repo_names()
    urls = list_archive_hours(days)

    all_counts = Counter()
    completed = 0
    logger.info("并行下载中 (%d 线程)...", workers)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_and_count, u, target_repos): u for u in urls}
        for f in as_completed(futures):
            count = f.result()
            all_counts.update(count)
            completed += 1
            if completed % 10 == 0 or completed == len(urls):
                logger.info("进度: %d/%d | 累计匹配事件: %d", completed, len(urls), sum(all_counts.values()))

    top = all_counts.most_common(top_n)
    logger.info("=== 近%d日飙升 Top %d ===", days, top_n)
    total_stars = sum(count for _, count in top)
    result = []
    for i, (repo_full, count) in enumerate(top):
        logger.info("  %3d. %-50s +%5d ⭐", i+1, repo_full, count)
        result.append({"rank": i+1, "repo": repo_full, "surge_5d": count, "star_increment": count})

    logger.info("总 star 增量: %d, 涉及仓库: %d", total_stars, len(all_counts))

    # 原子写入
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json', dir=BASE)
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, OUTPUT_FILE)
    except Exception:
        os.unlink(tmp_path)
        raise
    logger.info("保存到: %s", OUTPUT_FILE)
    return result

def discover_rising_stars(
    target_repos: set,
    sample_hours: int = 6,
    min_velocity: int = 3,
    workers: int = 10,
):
    """雷达扫描：最近N小时 GH Archive 中，star 增速快但不在数据库的仓库"""
    now = datetime.now(timezone.utc)
    end = now - timedelta(hours=2)
    start = end - timedelta(hours=sample_hours)

    urls = []
    current = start.replace(minute=0, second=0, microsecond=0)
    while current <= end:
        urls.append(f"{GH_ARCHIVE_BASE}/{current.strftime('%Y-%m-%d-%H')}.json.gz")
        current += timedelta(hours=1)

    logger.info("🔭 雷达扫描 %d 小时 (%s → %s)...", len(urls),
                start.strftime('%m-%d %H:00'), end.strftime('%m-%d %H:00'))

    all_watch = Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_count_all_watch, u): u for u in urls}
        for f in as_completed(futures):
            all_watch.update(f.result())

    candidates = []
    for repo, count in all_watch.most_common(200):
        if repo not in target_repos and count >= min_velocity:
            candidates.append({"repo": repo, "stars_in_window": count, "window_hours": sample_hours})

    if candidates:
        logger.info("发现 %d 个候选仓库（不在数据库，%dh 内 ≥%d ⭐）:", len(candidates), sample_hours, min_velocity)
        for c in candidates[:10]:
            logger.info("    %-50s +%3d⭐", c['repo'], c['stars_in_window'])
        if len(candidates) > 10:
            logger.info("    ... 还有 %d 个", len(candidates)-10)

        # 原子写入
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json', dir=BASE)
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                json.dump(candidates, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, DISCOVERY_FILE)
        except Exception:
            os.unlink(tmp_path)
            raise
        logger.info("保存到: %s", DISCOVERY_FILE)
    else:
        logger.info("无候选（%dh 内所有活跃仓库已在数据库中）", sample_hours)
        # 安全删除旧文件
        if os.path.exists(DISCOVERY_FILE):
            os.unlink(DISCOVERY_FILE)

    return candidates

def _count_all_watch(url: str, max_retries: int = 2) -> Counter:
    """下载一个 GH Archive 文件，统计所有 WatchEvent（不过滤仓库）"""
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
            count = Counter()
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        if event.get("type") == "WatchEvent":
                            repo = event.get("repo", {}).get("name", "").lower()
                            if repo:
                                count[repo] += 1
                    except (json.JSONDecodeError, KeyError):
                        pass
            return count
        except Exception:
            if attempt < max_retries:
                time_mod.sleep(2)
    return Counter()

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--discover", action="store_true", default=True,
                    help="雷达扫描不在数据库的高增速仓库")
    args = ap.parse_args()
    compute_surge(args.days, args.top, args.workers)
    if args.discover:
        target_repos = extract_repo_names()
        discover_rising_stars(target_repos)
