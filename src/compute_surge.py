#!/usr/bin/env python3
"""
近5日飙升计算器 — 基于 GH Archive 真实 star 增量
v2: 添加超时、日志、安全的文件处理。
"""
import json, os, sys, gzip, re, tempfile, time as time_mod
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request, HTTPError
import logging

from utils import setup_logger

logger = setup_logger("compute_surge")

BASE = Path(__file__).resolve().parent.parent
PROJECTS_FILE = str(BASE / "data" / "projects.json")
OUTPUT_FILE = str(BASE / "data" / "surge_top100.json")
DISCOVERY_FILE = str(BASE / "data" / "discovery_candidates.json")
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
    """列出需要下载的 GH Archive 小时文件 URL"""
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


def precheck_archive_hours(urls: list, workers: int = 10) -> tuple[list, list]:
    """HEAD 预检哪些 archive 文件实际存在。返回 (available, skipped)。

    只跳过确认 404 的文件。网络超时/5xx/连接错误 → 不跳过（下载阶段再重试），
    避免因 CDN 抖动误丢数据。
    """
    from urllib.error import URLError as _URLError

    def _check(url):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
            with urlopen(req, timeout=15) as resp:
                return ("ok", url) if resp.status == 200 else ("retry", url)
        except HTTPError as e:
            if e.code == 404:
                return ("missing", url)  # 确认不存在 → 安全跳过
            return ("retry", url)        # 4xx/5xx 不确定 → 照常下载
        except (_URLError, TimeoutError, OSError):
            return ("retry", url)        # 网络抖动 → 不跳过

    available = []
    skipped = []
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

    # retry_later files go back to available → will be attempted in download phase
    available.extend(retry_later)

    if skipped:
        logger.warning(
            "⚠️  %d/%d archive files confirmed missing (HTTP 404): %s ...",
            len(skipped), len(urls), skipped[0] if skipped else "",
        )
    if retry_later:
        logger.warning(
            "⚠️  %d/%d files had transient errors during precheck — will retry in download phase",
            len(retry_later), len(urls),
        )
    if not skipped and not retry_later:
        logger.info("✅ 全部 %d 个 archive 文件可用", len(available))
    return available, skipped

def download_and_count(url: str, target_repos: set, max_retries: int = 3) -> Counter:
    """下载一个 GH Archive 文件，统计目标仓库 WatchEvent（带超时和重试）"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=60) as resp:
                count = Counter()
                # Stream-decompress to avoid buffering entire archive in memory.
                # Individual .json.gz files can be 50–200 MB → 500 MB–2 GB decompressed.
                with gzip.GzipFile(fileobj=resp) as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            etype = event.get("type")
                            # NOTE: GH Archive records ALL WatchEvents. If a user
                            # star→unstar→star the same repo, each action produces
                            # an event. This overcounts relative to net star delta.
                            # For 5000+ star repos the noise is <3% — acceptable.
                            if etype != "WatchEvent":
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

def compute_surge(days: int = 5, top_n: int = 100, workers: int = 10):
    """主流程：预检 → 下载 → 过滤 → 排序 → 输出"""
    target_repos = extract_repo_names()
    all_urls = list_archive_hours(days)
    urls, skipped = precheck_archive_hours(all_urls, workers=min(workers, 10))

    all_counts = Counter()
    completed = 0
    logger.info("并行下载 %d 个文件 (%d 线程)...", len(urls), workers)

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
        result.append({"rank": i+1, "repo": repo_full, "surge_5d": count})

    logger.info("总 star 增量: %d, 涉及仓库: %d", total_stars, len(all_counts))

    # Guard: empty/small result indicates GH Archive data gap
    output = {"data": result}
    expected_files = len(all_urls)
    actual_files = len(urls)
    if len(result) < 10:
        output["_warning"] = (
            f"Low signal: only {len(result)} repos found from "
            f"{actual_files}/{expected_files} expected archive files. "
            f"GH Archive may be incomplete or delayed."
        )
        logger.warning("⚠️  %s", output["_warning"])
    elif actual_files < expected_files * 0.9:
        output["_warning"] = (
            f"GH Archive partial: {actual_files}/{expected_files} files available "
            f"({expected_files - actual_files} missing). Results may undercount."
        )
        logger.warning("⚠️  %s", output["_warning"])

    # 原子写入
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json', dir=str(BASE / 'data'))
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, OUTPUT_FILE)
    except Exception:
        os.unlink(tmp_path)
        raise
    logger.info("保存到: %s (%d entries)", OUTPUT_FILE, len(result))
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
        # Verify which candidates actually have 5000+ stars via GitHub API
        candidates = _verify_star_threshold(candidates)

    if candidates:
        logger.info("发现 %d 个候选仓库（不在数据库，%dh 内 ≥%d ⭐）:", len(candidates), sample_hours, min_velocity)
        for c in candidates[:10]:
            logger.info("    %-50s +%3d⭐", c['repo'], c['stars_in_window'])
        if len(candidates) > 10:
            logger.info("    ... 还有 %d 个", len(candidates)-10)

        # 原子写入
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json', dir=str(BASE / 'data'))
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


def _verify_star_threshold(candidates: list, min_stars: int = 5000) -> list:
    """Call GitHub API to verify that candidates actually have >= min_stars.
    Rate limit: 5000 req/hr with GITHUB_TOKEN; without token ~60 req/hr.
    Accepts partial results if rate-limited mid-batch.

    IMPORTANT: On API failure (timeout, 5xx, network error), the candidate is
    RETAINED with ``api_verified: false`` rather than dropped.  This prevents
    transient API outages from silently killing legitimate new stars.
    """
    import os as _os
    token = _os.environ.get("GITHUB_TOKEN") or _os.environ.get("GH_TOKEN") or ""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    verified = []
    for i, c in enumerate(candidates):
        owner, repo_name = c["repo"].split("/", 1)
        api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
        try:
            req = Request(api_url, headers=headers)
            with urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    stars = data.get("stargazers_count", 0)
                    c["actual_stars"] = stars
                    c["api_verified"] = True
                    if stars >= min_stars:
                        verified.append(c)
                    else:
                        logger.debug("  ✗ %s: %d⭐ < %d threshold", c["repo"], stars, min_stars)
                elif resp.status == 403:
                    remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                    logger.warning("⚠️  GitHub API rate limit hit (remaining=%s) at candidate %d/%d",
                                   remaining, i + 1, len(candidates))
                    # Keep remaining candidates unverified rather than dropping them
                    for remaining_c in candidates[i:]:
                        remaining_c["api_verified"] = False
                        verified.append(remaining_c)
                    break
                elif resp.status == 404:
                    logger.debug("  ✗ %s: repo not found (deleted/private)", c["repo"])
                else:
                    # 5xx or unexpected status → retain unverified
                    c["api_verified"] = False
                    verified.append(c)
                    logger.debug("  ⚠ %s: HTTP %d, retained unverified", c["repo"], resp.status)
        except Exception as e:
            # Network timeout / DNS / connection error → retain unverified
            c["api_verified"] = False
            verified.append(c)
            logger.debug("  ⚠ %s verify failed: %s — retained unverified", c["repo"], e)

    unverified = sum(1 for c in verified if not c.get("api_verified", True))
    if unverified:
        logger.info("验证完成: %d/%d 候选 ≥%d⭐ (%d 未验证，已保留)",
                    len(verified) - unverified, len(verified), min_stars, unverified)
    return verified


def _count_all_watch(url: str, max_retries: int = 2) -> Counter:
    """下载一个 GH Archive 文件，统计所有 WatchEvent（不过滤仓库）"""
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=60) as resp:
                count = Counter()
                # Stream-decompress to avoid buffering entire archive in memory.
                # Individual .json.gz files can be 50–200 MB → 500 MB–2 GB decompressed.
                with gzip.GzipFile(fileobj=resp) as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            etype = event.get("type")
                            # NOTE: GH Archive records ALL WatchEvents. If a user
                            # star→unstar→star the same repo, each action produces
                            # an event. This overcounts relative to net star delta.
                            # For 5000+ star repos the noise is <3% — acceptable.
                            if etype != "WatchEvent":
                                continue
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
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--discover", action="store_true", default=True,
                    help="雷达扫描不在数据库的高增速仓库")
    args = ap.parse_args()
    compute_surge(args.days, args.top, args.workers)
    if args.discover:
        target_repos = extract_repo_names()
        discover_rising_stars(target_repos)
