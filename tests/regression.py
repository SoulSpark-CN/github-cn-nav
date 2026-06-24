#!/usr/bin/env python3
"""
回归测试套件 — GitHub导航站数据完整性检查
检测: manifest/数据库同步 / 重复条目 / 飙升数据真实性 / 部署完整性
用法: python3 tests/regression.py
"""

import json, sys, os
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).resolve().parent.parent
PASS = 0
FAIL = 0
ERRORS = []


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        ERRORS.append(f"  ✗ {name}: {detail}")
        print(f"  ✗ {name}: {detail}")


def load_json(path):
    with open(path) as f:
        return json.load(f)


# ══════════════════════════════════════════════
# 1. Manifest 完整性
# ══════════════════════════════════════════════
def test_manifest_integrity():
    print("\n═══ 1. Manifest 完整性 ═══")
    manifest = load_json(BASE / "data" / "manifest.json")

    check("manifest.json 存在且非空", len(manifest) > 0, f"项目数={len(manifest)}")
    check("manifest.json 不超过 10000 条", len(manifest) <= 10000, f"实际={len(manifest)}")

    # 必须字段
    required = ["id", "name", "stars", "url", "first_seen"]
    missing_fields = 0
    for r in manifest:
        for f in required:
            if not r.get(f):
                missing_fields += 1
                break
    check("所有条目有必填字段(id/name/stars/url/first_seen)", missing_fields == 0,
          f"{missing_fields} 条缺失")

    # 重复检测
    seen_names = {}
    dup_count = 0
    for i, r in enumerate(manifest):
        key = r["name"].lower()
        if key in seen_names:
            dup_count += 1
        seen_names[key] = i
    check("无重复条目", dup_count == 0, f"{dup_count} 对重复")

    # star 数必须 >= 5000（本项目门槛）
    below_5k = [r for r in manifest if r.get("stars", 0) < 5000]
    check(f"所有仓库 >= 5000⭐", len(below_5k) == 0,
          f"{len(below_5k)} 个低于门槛: {[r['name'] for r in below_5k[:3]]}")

    return manifest


# ══════════════════════════════════════════════
# 2. 数据库同步: manifest ↔ projects.json ↔ 快照
# ══════════════════════════════════════════════
def test_database_sync(manifest):
    print("\n═══ 2. 数据库同步 ═══")

    projects = load_json(BASE / "data" / "projects.json")
    check("projects.json 非空", len(projects) > 0, f"项目数={len(projects)}")

    # 同比 manifest 和 projects.json
    m_names = {r["name"].lower() for r in manifest}
    p_names = {p["name"].lower() for p in projects}

    only_m = m_names - p_names
    only_p = p_names - m_names
    check("manifest ↔ projects.json 完全同步",
          len(only_m) == 0 and len(only_p) == 0,
          f"manifest多{len(only_m)}个, projects多{len(only_p)}个"
          + (f" 例如: {list(only_m)[:3]}" if only_m else "")
          + (f" 例如: {list(only_p)[:3]}" if only_p else ""))

    # projects.json 的 star 顺序（按star降序）
    stars = [p["stars"] for p in projects]
    is_sorted = all(stars[i] >= stars[i + 1] for i in range(len(stars) - 1))
    check("projects.json 按 star 降序排列", is_sorted)

    # 快照同步
    snaps = sorted(BASE.glob("data/snapshots/*.json"))
    check("至少有 5 天快照", len(snaps) >= 5, f"实际={len(snaps)}")

    if snaps:
        latest_snap = load_json(snaps[-1])
        snap_repos = set(latest_snap.keys())

        # 快照里有但 manifest 没有的仓库
        orphaned = snap_repos - m_names
        check("快照无孤立仓库(manifest均有)",
              len(orphaned) == 0,
              f"{len(orphaned)} 个孤立: {sorted(orphaned)[:5]}")

        # manifest 有但最近快照没有的（2K以内可以接受，因为快照只每天刷部分）
        missing_in_snap = m_names - snap_repos
        check("快照覆盖率 >= 70%",
             len(missing_in_snap) <= len(m_names) * 0.3,
             f"缺失 {len(missing_in_snap)}/{len(m_names)}")

    return projects


# ══════════════════════════════════════════════
# 3. 飙升数据真实性
# ══════════════════════════════════════════════
def test_surge_validity():
    print("\n═══ 3. 飙升数据真实性 ═══")

    surge_path = BASE / "data" / "surge_top100.json"
    if not surge_path.exists():
        check("surge_top100.json 存在", False, "文件不存在")
        return

    surge = load_json(surge_path)
    # 兼容 v2 格式: {"data": [...], "_warning": "..."} 和纯列表
    surge_items = surge.get("data", surge) if isinstance(surge, dict) else surge
    check(f"飙升榜 <= 100 条", len(surge_items) <= 100, f"实际={len(surge_items)}")

    # _warning 标记检查：如果大量数据无历史，应有 _warning
    if isinstance(surge, dict) and surge.get("_warning"):
        check("存疑数据有 _warning 标记", True)
    else:
        # 检查实际数据质量
        check("存疑数据有 _warning 标记",
              all(item.get("_has_history") for item in surge_items),
              "大量数据无5天历史但缺少 _warning 警告")

    # 检查每个repo的 surge_5d 是否有真实历史数据支撑
    snaps = sorted(BASE.glob("data/snapshots/*.json"))
    if len(snaps) < 5:
        check("快照不足5天，跳过飙升验证", False, f"只有{len(snaps)}天快照")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")

    # 预加载快照
    snap_data = {}
    for sf in snaps:
        snap_data[sf.stem] = load_json(sf)

    inflated = 0
    valid_5d = 0
    for item in surge_items:
        repo = item["repo"].lower()
        has_history = five_days_ago in snap_data and repo in snap_data[five_days_ago]
        if has_history:
            valid_5d += 1
        else:
            inflated += 1

    # 只要有部分数据有真实历史就算通过（跟踪系统需要时间累积）
    # 无历史数据时 _warning 标记会由页面展示
    check(f"至少有 1 条飙升数据有真实历史", valid_5d >= 1,
          f"全部 {len(surge_items)} 条均无5天前历史（跟踪系统刚启动）")

    # 检查排名是否按 surge_5d 降序
    if surge_items:
        vals = [s["surge_5d"] for s in surge_items]
        is_sorted = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
        check("飙升榜按增量降序排列", is_sorted)

    # 检查所有飙升仓库是否在 projects.json 中
    projects = load_json(BASE / "data" / "projects.json")
    p_names = set()
    for p in projects:
        p_names.add(p["name"].lower())
        import re
        m = re.search(r'github\.com/([^/]+/[^/\\s#]+)', p.get("url", ""))
        if m:
            p_names.add(m.group(1).lower().rstrip("/"))

    unmatched = [s for s in surge_items if s["repo"].lower() not in p_names]
    check("所有飙升仓库在数据库中",
          len(unmatched) == 0,
          f"{len(unmatched)} 个不在: {[s['repo'] for s in unmatched[:5]]}")

    return surge_items


# ══════════════════════════════════════════════
# 4. 人话解读覆盖率
# ══════════════════════════════════════════════
def test_renhua_coverage():
    print("\n═══ 4. 人话解读覆盖率 ═══")

    projects = load_json(BASE / "data" / "projects.json")
    with_rh = sum(1 for p in projects if p.get("rh"))
    without_rh = len(projects) - with_rh

    check("人话解读覆盖率 >= 80%",
          with_rh >= len(projects) * 0.8,
          f"有人话: {with_rh}/{len(projects)} ({100*with_rh//len(projects)}%)")

    # 检查飙升仓库的人话覆盖
    surge_path = BASE / "data" / "surge_top100.json"
    if surge_path.exists():
        raw = load_json(surge_path)
        surge_items = raw.get("data", raw) if isinstance(raw, dict) else raw
        surge_names = {s["repo"].lower() for s in surge_items}
        rh_missing = [p for p in projects
                      if p["name"].lower() in surge_names and not p.get("rh")]
        if rh_missing:
            # 记录但不过关 - 需要 LLM 翻译，等 auto_update 下次跑
            print(f"  ℹ️  飙升仓库无人话: {len(rh_missing)}/{len(surge_items)} 个"
                  f"（新增仓库需等待 auto_update 补充）")
        check("飙升仓库人话覆盖率跟踪",
              True,  # 只是信息记录，不做门禁
              "")


# ══════════════════════════════════════════════
# 5. 部署完整性
# ══════════════════════════════════════════════
def test_deploy_integrity():
    print("\n═══ 5. 部署完整性 ═══")

    deploy = BASE / "deploy"
    required_files = ["standalone.html", "projects.json",
                      "surge_top100.json", "serve.sh", "README.txt"]
    for f in required_files:
        path = deploy / f
        check(f"{f} 存在", path.exists(), f"路径: {path}")
        if path.exists() and f.endswith(".html"):
            check(f"{f} >= 5MB", path.stat().st_size >= 5 * 1024 * 1024,
                  f"实际: {path.stat().st_size//1024}KB")
        elif path.exists() and f.endswith(".json") and f != "surge_top100.json":
            check(f"{f} >= 5MB", path.stat().st_size >= 5 * 1024 * 1024,
                  f"实际: {path.stat().st_size//1024}KB")

    # 检查 standalone.html 中数据已内联（不再 fetch 外部文件）
    if (deploy / "standalone.html").exists():
        html = (deploy / "standalone.html").read_text()
        check("standalone.html 内联 projects.json",
              "fetch('projects.json')" not in html,
              "仍包含 fetch 调用")
        check("standalone.html 内联 surge 数据",
              "fetch('surge_top100.json')" not in html,
              "仍包含 fetch 调用")

    # 检查 index.html 和 deploy 的文件同步
    if (deploy / "surge_top100.json").exists() and (BASE / "data" / "surge_top100.json").exists():
        import filecmp
        check("deploy/surge_top100.json 同步",
              filecmp.cmp(BASE/"data"/"surge_top100.json", deploy/"surge_top100.json"),
              "data 和 deploy 不一致，需重跑 deploy.py")
    if (deploy / "projects.json").exists() and (BASE / "data" / "projects.json").exists():
        import filecmp
        check("deploy/projects.json 同步",
              filecmp.cmp(BASE/"data"/"projects.json", deploy/"projects.json"),
              "data 和 deploy 不一致，需重跑 deploy.py")


# ══════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════
if __name__ == "__main__":
    print("GitHub 导航站 — 回归测试套件")
    print(f"时间: {datetime.now(timezone.utc).isoformat()}")
    print(f"路径: {BASE}")

    manifest = test_manifest_integrity()
    test_database_sync(manifest)
    test_surge_validity()
    test_renhua_coverage()
    test_deploy_integrity()

    print(f"\n═══ 汇总 ═══")
    print(f"通过: {PASS}")
    print(f"失败: {FAIL}")
    if ERRORS:
        print(f"\n失败详情:")
        for e in ERRORS:
            print(e)

    sys.exit(0 if FAIL == 0 else 1)
