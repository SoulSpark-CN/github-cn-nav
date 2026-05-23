#!/usr/bin/env python3
"""
GitHub 5000+ Star 项目 增量更新器 v3
改进: 导入分类模块代替 exec；健壮的翻译解析；原子写入；日志统一。
用法: python3 auto_update.py [--dry-run]
"""
import json, os, sys, time, re, requests, subprocess, logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

# 导入工具与分类模块
from utils import (
    get_github_token, get_llm_key, get_llm_config,
    atomic_write_json, setup_logger, is_dry_run
)
from classify_module import classify_repo  # 新建模块，由 phase3_enhanced.py 导出

logger = setup_logger("auto_update")

os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"
import urllib3
urllib3.disable_warnings()

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE, "manifest.json")
RENHUA_PATH = os.path.join(BASE, "人话解读.json")
STATE_PATH = os.path.join(BASE, ".update_state.json")

# ---------- Token & Headers ----------
GH_TOKEN = get_github_token()
LLM_KEY = get_llm_key()
LLM_CFG = get_llm_config()

GH_HDR = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "hermes-updater/3.0",
    "Authorization": f"token {GH_TOKEN}",
}
LLM_HDR = {
    "Authorization": f"Bearer {LLM_KEY}",
    "Content-Type": "application/json",
}

# ---------- State ----------
def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("状态文件损坏，重置: %s", e)
    return {"last_update": None, "total_new": 0, "history": []}

def save_state(s: dict) -> None:
    atomic_write_json(s, STATE_PATH, indent=2)

# ---------- GitHub Discovery ----------
def discover_new_repos() -> List[dict]:
    logger.info("[1/4] 搜索GitHub新项目(5000+⭐)...")
    existing_names = set()
    existing_ids = set()
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, encoding="utf-8") as f:
                for r in json.load(f):
                    existing_names.add(r["name"].lower())
                    existing_ids.add(r.get("id", 0))
        except Exception as e:
            logger.warning("读取 manifest 时出错: %s", e)

    new_repos, seen = [], set()
    star_ranges = [(100000, None), (50000, 99999), (20000, 49999), (10000, 19999), (5000, 9999)]

    for min_s, max_s in star_ranges:
        q = f"stars:{min_s}..{max_s}" if max_s else f"stars:>={min_s}"
        for page in range(1, 4):
            url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=100&page={page}"
            try:
                resp = requests.get(url, headers=GH_HDR, timeout=30, verify=False)
                if resp.status_code == 403 and 'rate limit' in resp.text.lower():
                    logger.warning("Rate limited, waiting 60s...")
                    time.sleep(60)
                    resp = requests.get(url, headers=GH_HDR, timeout=30, verify=False)
                if resp.status_code != 200:
                    logger.warning("GitHub %s, skip", resp.status_code)
                    break
                items = resp.json().get("items", [])
                if not items:
                    break
                for item in items:
                    name = item["full_name"].lower()
                    if name not in existing_names and name not in seen:
                        seen.add(name)
                        new_repos.append({
                            "id": item["id"],
                            "name": item["full_name"],
                            "desc": item.get("description") or "",
                            "stars": item["stargazers_count"],
                            "url": item["html_url"],
                            "lang": item.get("language") or "-",
                            "topics": item.get("topics", []),
                            "created": item["created_at"],
                            "updated": item["updated_at"],
                            "first_seen": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        })
                logger.info("✓ %s p%d: %d results", q, page, len(items))
                time.sleep(2)
            except Exception as e:
                logger.warning("✗ %s: %s", q, e)
                break

    logger.info("发现 %d 个新项目", len(new_repos))
    return new_repos

# ---------- Discovery Radar ----------
def check_discovery_candidates(existing_names: set) -> List[dict]:
    disc_path = os.path.join(BASE, "discovery_candidates.json")
    if not os.path.exists(disc_path):
        return []

    try:
        with open(disc_path, encoding="utf-8") as f:
            candidates = json.load(f)
    except Exception as e:
        logger.warning("读取 discovery_candidates.json 失败: %s", e)
        return []

    if not candidates:
        return []

    logger.info("检查 %d 个雷达候选...", len(candidates))
    new_from_radar = []

    for c in candidates[:30]:  # 最多查 30 个
        repo_full = c["repo"]
        if repo_full.lower() in existing_names:
            continue

        try:
            url = f"https://api.github.com/repos/{repo_full}"
            resp = requests.get(url, headers=GH_HDR, timeout=15, verify=False)
            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                logger.warning("⚠ %s: HTTP %d", repo_full, resp.status_code)
                continue

            info = resp.json()
            stars = info.get("stargazers_count", 0)
            if stars >= 5000:
                logger.info("✅ %s: ⭐%d → 收录!", repo_full, stars)
                new_from_radar.append({
                    "id": info["id"],
                    "name": info["full_name"],
                    "desc": info.get("description") or "",
                    "stars": stars,
                    "url": info["html_url"],
                    "lang": info.get("language") or "-",
                    "topics": info.get("topics", []),
                    "created": info["created_at"],
                    "updated": info["updated_at"],
                    "first_seen": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "_source": "radar",
                })
            else:
                logger.debug("· %s: ⭐%d (未达 5000)", repo_full, stars)
            time.sleep(0.3)
        except Exception as e:
            logger.warning("✗ %s: %s", repo_full, e)

    # 安全删除候选文件
    os.unlink(disc_path) if os.path.exists(disc_path) else None

    if new_from_radar:
        logger.info("雷达贡献: %d 个新项目", len(new_from_radar))
    return new_from_radar

# ---------- 分类 ----------
def classify_repos(repos: List[dict]) -> None:
    """给每个 repo 添加 'cat' 字段"""
    from collections import Counter
    cats = Counter()
    for r in repos:
        cat, _ = classify_repo(r["name"], r.get("desc", ""), r.get("lang", ""), r.get("topics", []))
        r["cat"] = cat
        cats[cat] += 1
    for c, n in cats.most_common():
        logger.info("  %s: %d", c, n)

# ---------- 翻译 + 人话（合并调用） ----------
def translate_and_explain(repos: List[dict]) -> None:
    logger.info("[3/4] 翻译+人话解读(合并调用)...")

    # 加载现有人话
    existing_rh: Dict[str, Any] = {}
    if os.path.exists(RENHUA_PATH):
        try:
            with open(RENHUA_PATH, encoding="utf-8") as f:
                existing_rh = json.load(f)
        except Exception:
            logger.warning("人话文件损坏，重置为空")

    # 筛选需要处理的项目
    to_process = []
    for r in repos:
        has_cn = any('\u4e00' <= c <= '\u9fff' for c in r.get("desc", ""))
        # 检查人话是否存在（使用名称作为键）
        key = r["name"]
        has_rh = key in existing_rh
        if not has_cn or not has_rh:
            to_process.append(r)

    if not to_process:
        logger.info("全部已处理")
        return

    logger.info("需处理 %d 个项目", len(to_process))

    desc_map: Dict[str, str] = {}
    rh_map: Dict[str, dict] = {}
    batch_size = 20

    for i in range(0, len(to_process), batch_size):
        batch = to_process[i:i+batch_size]
        lines = [f"[{j}] {r['name']} ({r['stars']}⭐): {r['desc'][:150]}" for j, r in enumerate(batch)]

        prompt = f"""你是GitHub项目"中文翻译官+人话解读师"。对以下项目同时提供中文描述和人话解读。

返回严格JSON数组格式:
```json
[
  {{"idx": 0, "desc_zh": "中文一句话描述(30字内)", "one_liner": "**项目名** 就是"一句话Slogan"。", "plain": "2-3句大白话解释", "analogy": "一个生活类比", "audience": "适合什么人？解决什么问题？"}}
]
```

规则: desc_zh简洁准确; one_liner用**项目名**开头; plain有实质信息; analogy用日常生活类比; audience写目标人群+解决的问题。实事求是，技术术语保留英文。

项目列表:
{chr(10).join(lines)}"""

        for retry in range(5):
            try:
                r = requests.post(
                    LLM_CFG["api"],
                    headers=LLM_HDR,
                    json={
                        "model": LLM_CFG["model"],
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 10000,
                        "temperature": 0.3,
                    },
                    timeout=180,
                    verify=False,
                )
                if r.status_code == 200:
                    text = r.json()["choices"][0]["message"]["content"]

                    # 尝试直接解析 JSON
                    items = None
                    try:
                        items = json.loads(text)
                        if isinstance(items, dict) and "items" in items:
                            items = items["items"]
                    except json.JSONDecodeError:
                        # 回退：提取 ```json ``` 或 [ ] 内的内容
                        match = re.search(r'```json\s*(\[.*?\])\s*```', text, re.DOTALL)
                        if not match:
                            match = re.search(r'(\[.*?\])', text, re.DOTALL)
                        if match:
                            try:
                                items = json.loads(match.group(1))
                            except json.JSONDecodeError:
                                pass

                    if items is None or not isinstance(items, list):
                        raise ValueError("无法解析 LLM 返回的 JSON")

                    for item in items:
                        idx = item.get("idx")
                        if idx is None or idx < 0 or idx >= len(batch):
                            logger.warning("batch %d: idx %s 超出范围", i//batch_size, idx)
                            continue
                        name = batch[idx]["name"]
                        desc_map[name] = item.get("desc_zh", batch[idx]["desc"])
                        rh_map[name] = {
                            "one_liner": item.get("one_liner", ""),
                            "plain": item.get("plain", ""),
                            "analogy": item.get("analogy", ""),
                            "audience": item.get("audience", ""),
                        }
                    logger.info("batch %d: ✓ %d", i//batch_size + 1, len(items))
                    break
                elif r.status_code == 429:
                    wait = 30 + retry * 10
                    logger.warning("[429] 等待 %ds...", wait)
                    time.sleep(wait)
                else:
                    logger.warning("[HTTP %d] 等待10s...", r.status_code)
                    time.sleep(10)
            except Exception as e:
                logger.warning("[ERR:%s] 等待15s...", e)
                time.sleep(15)
        time.sleep(3)

    # 应用中文描述
    for r in repos:
        if r["name"] in desc_map:
            r["desc"] = desc_map[r["name"]]

    # 合并人话（键统一为仓库名）
    for name, rh in rh_map.items():
        existing_rh[name] = rh

    atomic_write_json(existing_rh, RENHUA_PATH, ensure_ascii=False, indent=2)
    logger.info("翻译: %d 条, 人话: %d 条 (总计 %d)", len(desc_map), len(rh_map), len(existing_rh))

# ---------- 合并 & 重建 ----------
def merge_and_rebuild(new_repos: List[dict]) -> int:
    logger.info("[4/4] 合并数据 + 重建...")

    existing: List[dict] = []
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            logger.warning("manifest.json 读取失败，视为空")

    existing_names = {r["name"].lower() for r in existing}
    existing_ids = {r.get("id", 0) for r in existing}

    added = 0
    for r in new_repos:
        if r["name"].lower() not in existing_names and r.get("id", 0) not in existing_ids:
            existing.append({
                "id": r["id"],
                "name": r["name"],
                "desc": r["desc"],
                "stars": r["stars"],
                "url": r["url"],
                "lang": r["lang"],
                "topics": r.get("topics", []),
                "created": r.get("created", ""),
                "updated": r.get("updated", ""),
                "first_seen": r.get("first_seen", ""),
            })
            added += 1

    if added:
        existing.sort(key=lambda x: -x["stars"])
        atomic_write_json(existing, MANIFEST_PATH, ensure_ascii=False, indent=2)
        logger.info("manifest.json: +%d → %d 项目", added, len(existing))

    # 重建 projects.json
    rebuild_projects_json(existing)

    # 更新状态
    state = load_state()
    state["last_update"] = datetime.now(timezone.utc).isoformat()
    state["total_new"] = state.get("total_new", 0) + added
    state["history"].append({"time": state["last_update"], "new": added, "total": len(existing)})
    state["history"] = state["history"][-20:]
    save_state(state)

    logger.info("✅ 完成: +%d 新项目, 总计 %d 项目", added, len(existing))
    return added

def rebuild_projects_json(repos: List[dict]) -> None:
    """重建 projects.json，直接使用 r.get('cat') 避免重复分类"""
    logger.info("重建 projects.json...")

    # 加载翻译（所有 batch 文件合并）
    desc_zh: Dict[str, str] = {}
    for bf in ["translate_batch_0_done.json", "translate_batch_1_done.json",
                "translate_batch_2_done.json", "translate_batch_3_done.json"]:
        fp = os.path.join(BASE, bf)
        if os.path.exists(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    for item in json.load(f):
                        if item.get("desc_zh"):
                            desc_zh[item["name"]] = item["desc_zh"]
            except Exception:
                continue

    # 加载人话（统一使用仓库名作为键）
    renhua: Dict[str, Any] = {}
    if os.path.exists(RENHUA_PATH):
        try:
            with open(RENHUA_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in raw.items():
                if isinstance(v, dict) and "/" in k:
                    renhua[k] = v
        except Exception:
            pass

    projects = []
    for i, r in enumerate(repos):
        name = r["name"]
        cat = r.get("cat") or classify_repo(name, r.get("desc", ""), r.get("lang", ""), r.get("topics", []))[0]
        desc = desc_zh.get(name) or r.get("desc", "")
        rh = renhua.get(name, "")
        projects.append({
            "id": i + 1,
            "cat": cat,
            "name": name,
            "desc": desc[:200],
            "stars": r["stars"],
            "lang": r.get("lang", "") or "-",
            "url": r["url"],
            "rh": rh if isinstance(rh, str) else rh,
            "first_seen": r.get("first_seen", "")[:10],
        })

    projects_path = os.path.join(BASE, "projects.json")
    atomic_write_json(projects, projects_path, ensure_ascii=False, separators=(',', ':'))
    size_mb = os.path.getsize(projects_path) / (1024 * 1024)
    logger.info("projects.json: %d 项目 (%.2fMB)", len(projects), size_mb)

# ---------- 部署 ----------
def deploy_site() -> None:
    logger.info("[5/5] 部署站点...")
    deploy_py = os.path.join(BASE, "deploy.py")
    if os.path.exists(deploy_py):
        result = subprocess.run(
            [sys.executable, deploy_py],
            capture_output=True, text=True, cwd=BASE, timeout=60,
        )
        if result.returncode == 0:
            logger.info("✅ deploy.py 完成")
            for line in result.stdout.strip().split('\n')[-5:]:
                logger.info("  %s", line)
        else:
            logger.warning("⚠️ deploy.py 失败: %s", result.stderr[-200:])
    else:
        logger.warning("⚠️ deploy.py 不存在，手动复制数据...")
        import shutil
        shutil.copy2(
            os.path.join(BASE, "projects.json"),
            os.path.join(BASE, "deploy", "projects.json"),
        )
        logger.info("✅ projects.json 已复制到 deploy/")

# ---------- Main ----------
def main() -> None:
    dry_run = is_dry_run()
    new_repos = discover_new_repos()

    # 雷达候选
    existing_names = set()
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, encoding="utf-8") as f:
                for r in json.load(f):
                    existing_names.add(r["name"].lower())
        except Exception:
            pass

    radar_repos = check_discovery_candidates(existing_names)
    if radar_repos:
        new_repos.extend(radar_repos)

    if not new_repos:
        logger.info("✅ 没有新项目")
        state = load_state()
        state["last_update"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    if dry_run:
        logger.info("🔍 干跑: 发现 %d 个新项目，不动手", len(new_repos))
        for r in new_repos[:15]:
            logger.info("  %s ⭐%s", r['name'], r['stars'])
        if len(new_repos) > 15:
            logger.info("  ... 还有 %d 个", len(new_repos)-15)
        return

    classify_repos(new_repos)
    translate_and_explain(new_repos)
    added = merge_and_rebuild(new_repos)
    if added > 0:
        deploy_site()
    logger.info("\\n✅ 全流程完成: +%d 新项目", added)

if __name__ == "__main__":
    main()
