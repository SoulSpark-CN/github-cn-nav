#!/usr/bin/env python3
"""
近5日飙升计算器 — 基于 GH Archive 真实 star 增量
用法: python3 compute_surge.py [--days 5] [--top 100]
产出: surge_top100.json → deploy.py 打包时注入 index.html
"""
import json, os, sys, gzip, io, subprocess, re, tempfile, time as time_mod
from datetime import datetime, timedelta, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECTS_FILE = os.path.join(BASE, "projects.json")
OUTPUT_FILE = os.path.join(BASE, "surge_top100.json")
DISCOVERY_FILE = os.path.join(BASE, "discovery_candidates.json")
GH_ARCHIVE_BASE = "https://data.gharchive.org"

def extract_repo_names():
    """从 projects.json 提取所有 owner/repo"""
    with open(PROJECTS_FILE) as f:
        data = json.load(f)
    names = set()
    for p in data:
        url = p.get("url", "")
        # url format: https://github.com/owner/repo
        m = re.search(r'github\.com/([^/]+/[^/\s]+)', url)
        if m:
            names.add(m.group(1).lower())
    print(f"提取 {len(names)} 个仓库名")
    return names

def list_archive_hours(days=5):
    """列出需要下载的 GH Archive 小时文件 URL"""
    now = datetime.now(timezone.utc)
    # GH Archive 有 1-2 小时延迟，用 now - 2h 作为最新
    end = now - timedelta(hours=2)
    # GH Archive 有 1-2 天延迟，加 2 天余量确保有效数据够 5 天
    start = end - timedelta(days=days + 2)
    
    urls = []
    current = start.replace(minute=0, second=0, microsecond=0)
    while current <= end:
        url = f"{GH_ARCHIVE_BASE}/{current.strftime('%Y-%m-%d-%H')}.json.gz"
        urls.append(url)
        current += timedelta(hours=1)
    print(f"需要下载 {len(urls)} 个小时文件 ({start.strftime('%Y-%m-%d %H:00')} → {end.strftime('%Y-%m-%d %H:00')})")
    return urls

def download_and_count(url, target_repos, max_retries=3):
    """下载一个 GH Archive 小时文件，统计目标仓库的 WatchEvent（含重试）"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "surge-compute/1.0"})
            with urlopen(req, timeout=90) as resp:
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
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time_mod.sleep(2 ** attempt)  # 指数退避
    print(f"  ⚠ {url}: {last_err} (重试{max_retries}次均失败)", file=sys.stderr)
    return Counter()

def compute_surge(days=5, top_n=100, workers=20):
    """主流程：下载 → 过滤 → 排序 → 输出"""
    target_repos = extract_repo_names()
    urls = list_archive_hours(days)
    
    # 并行下载统计
    all_counts = Counter()
    completed = 0
    print(f"\n并行下载中 ({workers} 线程)...")
    
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_and_count, u, target_repos): u for u in urls}
        for f in as_completed(futures):
            count = f.result()
            all_counts.update(count)
            completed += 1
            if completed % 10 == 0 or completed == len(urls):
                print(f"  进度: {completed}/{len(urls)} | 累计匹配事件: {sum(all_counts.values())}")
    
    # 排序取 top N
    top = all_counts.most_common(top_n)
    
    # 输出
    print(f"\n=== 近{days}日飙升 Top {top_n} ===")
    total_stars = 0
    result = []
    for i, (repo_full, count) in enumerate(top):
        print(f"  {i+1:3d}. {repo_full:50s} +{count:5d} ⭐")
        result.append({"rank": i+1, "repo": repo_full, "surge_5d": count, "star_increment": count})
        total_stars += count
    
    print(f"\n总 star 增量: {total_stars}, 涉及仓库: {len(all_counts)}")
    
    # 保存（原子写入：先写临时文件再重命名，防止写入中断导致损坏）
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json', dir=BASE)
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, OUTPUT_FILE)  # 原子替换
    except:
        os.unlink(tmp_path)
        raise
    print(f"保存到: {OUTPUT_FILE}")
    
    return result

def discover_rising_stars(target_repos, sample_hours=6, min_velocity=3, workers=10):
    """雷达扫描：最近N小时 GH Archive 中，star 增速快但不在数据库的仓库"""
    now = datetime.now(timezone.utc)
    end = now - timedelta(hours=2)
    start = end - timedelta(hours=sample_hours)
    
    urls = []
    current = start.replace(minute=0, second=0, microsecond=0)
    while current <= end:
        urls.append(f"{GH_ARCHIVE_BASE}/{current.strftime('%Y-%m-%d-%H')}.json.gz")
        current += timedelta(hours=1)
    
    print(f"\n🔭 雷达扫描 {len(urls)} 小时 ({start.strftime('%m-%d %H:00')} → {end.strftime('%m-%d %H:00')})...")
    
    all_watch = Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_count_all_watch, u): u for u in urls}
        for f in as_completed(futures):
            all_watch.update(f.result())
    
    # 过滤：不在 target_repos + 增速 > min_velocity
    candidates = []
    for repo, count in all_watch.most_common(200):
        if repo not in target_repos and count >= min_velocity:
            candidates.append({"repo": repo, "stars_in_window": count, "window_hours": sample_hours})
    
    if candidates:
        print(f"  发现 {len(candidates)} 个候选仓库（不在数据库，{sample_hours}h 内 ≥{min_velocity} ⭐）:")
        for c in candidates[:10]:
            print(f"    {c['repo']:50s} +{c['stars_in_window']:3d}⭐")
        if len(candidates) > 10:
            print(f"    ... 还有 {len(candidates)-10} 个")
        
        # 原子写入
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json', dir=BASE)
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                json.dump(candidates, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, DISCOVERY_FILE)
        except:
            os.unlink(tmp_path)
            raise
        print(f"  保存到: {DISCOVERY_FILE}")
    else:
        print(f"  无候选（{sample_hours}h 内所有活跃仓库已在数据库中）")
        # 清空旧文件
        if os.path.exists(DISCOVERY_FILE):
            os.remove(DISCOVERY_FILE)
    
    return candidates

def _count_all_watch(url, max_retries=2):
    """下载一个 GH Archive 文件，统计所有 WatchEvent（不过滤仓库）"""
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "surge-radar/1.0"})
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
    ap.add_argument("--discover", action="store_true", default=True, help="雷达扫描不在数据库的高增速仓库")
    args = ap.parse_args()
    compute_surge(args.days, args.top, args.workers)
    if args.discover:
        target_repos = extract_repo_names()
        discover_rising_stars(target_repos)
