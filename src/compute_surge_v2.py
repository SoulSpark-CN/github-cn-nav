#!/usr/bin/env python3
"""
近5日 star 增量 — 基于 GitHub API 快照的精确计算。
替换 GH Archive 方案：消除数据缺口，得到净 star 增量，不依赖第三方数据源。

原理：
  1. 每天调用 GitHub API 获取 repos 的 stargazers_count → 快照存档
  2. 比较今天快照 vs 5天前快照 → 精确 5 日净增量
  3. 优先级刷新：只刷新可能上榜的 repos（昨天 top 200 + 7 天未更新的）
  4. 其余 repos 沿用缓存值（它们不会进 top 50）

首次运行：全量刷新 ~7100 repos（需 ~2h，一次性成本）
后续运行：刷新 ~500 repos（~5min），其余用缓存
"""

import json, os, sys, time, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request, HTTPError
from collections import defaultdict
import logging

from utils import setup_logger

logger = setup_logger("compute_surge_v2")

BASE = Path(__file__).resolve().parent.parent
PROJECTS_FILE = BASE / "data" / "projects.json"
SNAPSHOT_DIR = BASE / "data" / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = BASE / "data" / "surge_top100.json"
TOP_N = 50

USER_AGENT = "surge-compute/3.0"

# ── GitHub API ────────────────────────────────────────────────────

def _get_token() -> str:
    """优先 GH_PAT（个人 token，5000 req/h），回退 GITHUB_TOKEN（Actions，1000 req/h）"""
    return os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""


def _api_headers() -> dict:
    h = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.v3+json"}
    token = _get_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_star_count(owner: str, repo_name: str) -> int | None:
    """获取单个 repo 的 stargazers_count。返回 None 表示失败（跳过该 repo）。"""
    url = f"https://api.github.com/repos/{owner}/{repo_name}"
    try:
        req = Request(url, headers=_api_headers())
        with urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                return data.get("stargazers_count", 0)
            elif resp.status == 404:
                logger.debug("  ⚠ %s/%s: 404 (repo deleted/private)", owner, repo_name)
                return 0
            elif resp.status == 403:
                _check_rate_limit(resp)
                return None
            else:
                logger.debug("  ⚠ %s/%s: HTTP %d", owner, repo_name, resp.status)
                return None
    except HTTPError as e:
        if e.code == 403:
            _check_rate_limit(e)
        elif e.code == 404:
            return 0
        else:
            logger.debug("  ⚠ %s/%s: HTTP %d", owner, repo_name, e.code)
        return None
    except Exception as e:
        logger.debug("  ⚠ %s/%s: %s", owner, repo_name, e)
        return None


def _check_rate_limit(resp):
    """检查 rate limit，如果耗尽则 sleep 到 reset 时间。"""
    remaining = resp.headers.get("X-RateLimit-Remaining")
    reset_ts = resp.headers.get("X-RateLimit-Reset")
    if remaining is not None and int(remaining) == 0 and reset_ts:
        wait = max(0, int(reset_ts) - int(time.time()) + 5)
        logger.warning("⏳ Rate limit exhausted, sleeping %ds...", wait)
        time.sleep(wait)


# ── Repo list ──────────────────────────────────────────────────────

def load_repo_list() -> list[tuple[str, str]]:
    """从 projects.json 提取 owner/repo 对。"""
    with open(PROJECTS_FILE) as f:
        data = json.load(f)
    repos = []
    seen = set()
    for p in data:
        url = p.get("url", "")
        # Extract owner/repo from github.com URL
        import re
        m = re.search(r'github\.com/([^/]+/[^/\s#]+)', url)
        if m:
            full = m.group(1).lower().rstrip("/")
            if full not in seen:
                seen.add(full)
                parts = full.split("/")
                if len(parts) == 2:
                    repos.append((parts[0], parts[1]))
    logger.info("加载 %d 个仓库", len(repos))
    return repos


# ── Snapshot management ────────────────────────────────────────────

def _snapshot_path(date_str: str) -> Path:
    return SNAPSHOT_DIR / f"{date_str}.json"


def load_snapshot(date_str: str) -> dict:
    """加载某一天的快照 {repo_full: stars}"""
    path = _snapshot_path(date_str)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_snapshot(date_str: str, data: dict):
    """保存快照（原子写入）。"""
    path = _snapshot_path(date_str)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=str(SNAPSHOT_DIR))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def _load_top_repos(limit: int = 200) -> set[str]:
    """从上次的 surge_top100.json 读取上榜 repos。"""
    if not OUTPUT_FILE.exists():
        return set()
    try:
        with open(OUTPUT_FILE) as f:
            prev = json.load(f)
        items = prev.get("data", prev) if isinstance(prev, dict) else prev
        return {item["repo"].lower() for item in items[:limit]}
    except Exception:
        return set()


def get_priority_repos(
    repos: list[tuple[str, str]],
    today: str,
    max_calls: int = 900,
) -> list[tuple[str, str]]:
    """确定今天需要刷新的 repos。

    渐进式引导（bootstrap）：首次运行时快照为空，每次刷新最多 max_calls 个，
    优先覆盖昨天上榜的 repos + 尚未缓存的新 repos。
    ~8 天后全部 repos 覆盖完毕，此后每天只需刷新 ~500 个高优先级 repos。
    """
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_snapshot = load_snapshot(yesterday)

    # ── 第一阶段：bootstrap（快照尚未全量覆盖）──
    coverage = len(yesterday_snapshot) / max(len(repos), 1)
    if coverage < 0.8:
        # 昨天上榜的 repos（优先保证榜单准确性）
        top_repos = _load_top_repos(limit=100)
        priority = []
        seen = set()
        for owner, name in repos:
            full = f"{owner}/{name}"
            if full in top_repos and full not in yesterday_snapshot:
                priority.append((owner, name))
                seen.add(full)

        # 其余未缓存的 repos（按顺序补齐）
        for owner, name in repos:
            full = f"{owner}/{name}"
            if full not in yesterday_snapshot and full not in seen:
                priority.append((owner, name))
                if len(priority) >= max_calls:
                    break

        logger.info(
            "🔰 引导模式 (%d/%d repos 已覆盖, %d%%): 候选 %d 个, 本次刷新 %d 个",
            len(yesterday_snapshot), len(repos),
            int(coverage * 100), len(priority), min(len(priority), max_calls),
        )
        return priority[:max_calls]

    # ── 第二阶段：稳态运行（只刷新高优先级 repos）──
    top_repos = _load_top_repos(limit=200)
    priority = []
    seen = set()

    # 昨天上榜的 repos → 必须刷新
    for owner, name in repos:
        full = f"{owner}/{name}"
        if full in top_repos:
            priority.append((owner, name))
            seen.add(full)

    # 7 天未更新的 repos → 刷新
    week_ago = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    week_snapshot = load_snapshot(week_ago)
    for owner, name in repos:
        full = f"{owner}/{name}"
        if full not in seen and full not in week_snapshot and len(priority) < max_calls:
            priority.append((owner, name))
            seen.add(full)

    logger.info(
        "稳态刷新: %d 个 (top上榜=%d, 缓存过期=%d)",
        len(priority),
        len([r for r in priority if f"{r[0]}/{r[1]}" in top_repos]),
        len(priority) - len([r for r in priority if f"{r[0]}/{r[1]}" in top_repos]),
    )
    return priority[:max_calls]


# ── Main logic ─────────────────────────────────────────────────────

def compute_surge(days: int = 5, top_n: int = TOP_N, max_api_calls: int = 900):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    repos = load_repo_list()
    priority = get_priority_repos(repos, today_str, max_calls=max_api_calls)

    # ── 刷新优先级 repos ──
    yesterday_snapshot = load_snapshot(
        (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    )

    current = dict(yesterday_snapshot)  # 继承昨天的快照
    refreshed = 0
    failed = 0
    for i, (owner, name) in enumerate(priority):
        stars = fetch_star_count(owner, name)
        if stars is not None:
            current[f"{owner}/{name}"] = stars
            refreshed += 1
        else:
            failed += 1

        if (i + 1) % 100 == 0:
            logger.info("  进度: %d/%d (刷新=%d, 失败=%d)", i + 1, len(priority), refreshed, failed)

    logger.info("刷新完成: %d 更新, %d 失败, %d 沿用缓存", refreshed, failed, len(current) - refreshed)

    # ── 保存今天的快照 ──
    save_snapshot(today_str, current)
    logger.info("快照已保存: %s (%d repos)", _snapshot_path(today_str), len(current))

    # ── 计算 5 日增量 ──
    old_snapshot = load_snapshot(target_date)
    if not old_snapshot:
        logger.warning("⚠️  无 %s 的快照，无法计算 %d 日增量（需至少运行 %d 天后才有历史数据）",
                       target_date, days, days)
        # 尝试用最早可用的快照
        available = sorted(
            [p.stem for p in SNAPSHOT_DIR.glob("*.json")],
            reverse=True,
        )
        if available:
            target_date = available[-1]  # 最早的
            old_snapshot = load_snapshot(target_date)
            logger.warning("⚠️  回退到最早快照: %s (%d 天前)", target_date,
                           (datetime.now(timezone.utc) - datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days)

    deltas = []
    no_history = []
    for repo_full, current_stars in current.items():
        old_stars = old_snapshot.get(repo_full, 0)
        delta = current_stars - old_stars
        if delta > 0:
            entry = {
                "repo": repo_full,
                "surge_5d": delta,
                "star_increment": delta,
            }
            # 标记是否有真实历史数据（防止新入库仓库的虚高增量）
            if repo_full in old_snapshot:
                entry["_has_history"] = True
                deltas.append(entry)
            else:
                no_history.append(entry)  # 无历史数据，单独记录

    # 无历史数据的仓库：仅保留 delta >= 500 的，并标记警告
    if no_history:
        warning_repos = [e for e in no_history if e["surge_5d"] >= 500]
        if warning_repos:
            logger.warning(
                "⚠️ %d 个仓库无 %d 天前快照（新入库），增量可能虚高：%s",
                len(warning_repos), days,
                ", ".join(f"{e['repo']}(+{e['surge_5d']}⭐)" for e in warning_repos[:5])
            )
            # 新入库且增量大的仓库仍进主榜单，但页面会展示警告
            deltas.extend(warning_repos)
        tiny = [e for e in no_history if e["surge_5d"] < 500]
        if tiny:
            deltas.extend(tiny)  # 少量增量也放行，影响不大

    deltas.sort(key=lambda x: -x["surge_5d"])
    for i, d in enumerate(deltas[:top_n]):
        d["rank"] = i + 1

    result = deltas[:top_n]

    # ── 输出（带警告标记）──
    # 检查是否有新入库仓库在结果中，添加警告
    no_history_in_result = [e for e in result if not e.get("_has_history")]
    _warning = None
    if no_history_in_result:
        _warning = (
            f"{len(no_history_in_result)}/{len(result)} 个仓库无5天前历史数据，"
            f"增量可能包含了积累多月的star数，仅供参考。"
        )
        logger.warning("⚠️ %s", _warning)

    output = {"data": result}
    if _warning:
        output["_warning"] = _warning

    logger.info("=== 近%d日 star 增量 Top %d ===", days, top_n)
    for item in result[:10]:
        logger.info("  #%3d %-45s +%5d⭐", item["rank"], item["repo"], item["surge_5d"])

    total = sum(d["surge_5d"] for d in result)
    logger.info("Top %d 总增量: %d⭐ | 涉及 %d 仓库", top_n, total, len(deltas))

    # 原子写入
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=str(BASE / "data"))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, OUTPUT_FILE)
    except Exception:
        os.unlink(tmp_path)
        raise

    logger.info("保存到: %s (%d entries)", OUTPUT_FILE, len(result))

    # 清理 7 天前的旧快照
    cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
    for f in SNAPSHOT_DIR.glob("*.json"):
        if f.stem < cutoff:
            f.unlink()
            logger.debug("  清理旧快照: %s", f.name)

    return result


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="近5日 star 增量 — GitHub API 快照方案")
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--top", type=int, default=TOP_N)
    ap.add_argument("--max-calls", type=int, default=900,
                    help="单次最大 API 调用数 (GITHUB_TOKEN=1000/h, GH_PAT=5000/h)")
    ap.add_argument("--dry-run", action="store_true", help="只显示优先级，不实际刷新")
    ap.add_argument("--shadow", action="store_true",
                    help="影子模式：只更新快照，不写 output 文件（用于 bootstrap）")
    args = ap.parse_args()

    if args.dry_run:
        repos = load_repo_list()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        priority = get_priority_repos(repos, today, max_calls=args.max_calls)
        print(f"优先级刷新: {len(priority)} repos")
        for owner, name in priority[:20]:
            print(f"  {owner}/{name}")
        sys.exit(0)

    if args.shadow:
        # 影子模式：更新快照。如果已有 >=5 天历史 → 自动升格为正常模式
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        repos = load_repo_list()
        priority = get_priority_repos(repos, today_str, max_calls=args.max_calls)
        yesterday_snapshot = load_snapshot(
            (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"))
        current = dict(yesterday_snapshot)
        for owner, name in priority:
            stars = fetch_star_count(owner, name)
            if stars is not None:
                current[f"{owner}/{name}"] = stars
        save_snapshot(today_str, current)

        # 检查是否有 5 天历史 → 自动升格
        snapshots_available = sorted(
            [p.stem for p in SNAPSHOT_DIR.glob("*.json")],
            reverse=True,
        )
        days_of_history = 0
        if snapshots_available:
            newest = datetime.strptime(snapshots_available[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            oldest = datetime.strptime(snapshots_available[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_of_history = (newest - oldest).days + 1

        if days_of_history >= args.days:
            logger.info("🎉 已有 %d 天历史 → 自动升格为正常模式，产出榜单", days_of_history)
            # 继续执行正常 compute_surge（下面会走到）
        else:
            logger.info("影子模式: 快照已更新 (%d repos), 还需 %d 天引导",
                        len(current), args.days - days_of_history)
            sys.exit(0)

    compute_surge(days=args.days, top_n=args.top, max_api_calls=args.max_calls)
