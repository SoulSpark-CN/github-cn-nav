#!/usr/bin/env python3
"""
GitHub 5000+ Star 项目 增量更新器 v2
改进: 翻译+人话合并为一次LLM调用(省钱50%)
用法: python3 auto_update.py [--dry-run]
"""
import json, os, sys, time, re, requests, subprocess
from datetime import datetime, timezone, timedelta

os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"
import urllib3
urllib3.disable_warnings()

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE, "manifest.json")
RENHUA_PATH = os.path.join(BASE, "人话解读.json")
STATE_PATH = os.path.join(BASE, ".update_state.json")

# Load tokens: env vars (CI) > .env file (local)
GH_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
# LLM: 支持任意OpenAI兼容API → 默认DeepSeek
LLM_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DS_KEY")
LLM_API = os.environ.get("LLM_BASE_URL") or os.environ.get("DS_API") or "https://api.deepseek.com/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL") or "deepseek-chat"

if not GH_TOKEN or not LLM_KEY:
    # Fallback: read from .env file
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        env_text = open(env_file).read()
        if not GH_TOKEN:
            m = re.search(r'GITHUB_TOKEN=(.+)', env_text) or re.search(r'GH_TOKEN=(.+)', env_text)
            GH_TOKEN = m.group(1).strip().strip('"').strip("'") if m else None
        if not LLM_KEY:
            m = re.search(r'DEEPSEEK_API_KEY=(.+)', env_text) or re.search(r'DS_KEY=(.+)', env_text)
            DS_KEY = m.group(1).strip().strip('"').strip("'") if m else None

if not GH_TOKEN:
    print("❌ GITHUB_TOKEN not set (env or ~/.hermes/.env)", flush=True)
    sys.exit(1)
if not LLM_KEY:
    print("❌ LLM_API_KEY not set. 设环境变量: LLM_API_KEY=sk-xxx (兼容 DEEPSEEK_API_KEY)", flush=True)
    sys.exit(1)

GH_HDR = {"Accept": "application/vnd.github.v3+json", "User-Agent": "hermes-updater/2.0", "Authorization": f"token {GH_TOKEN}"}
LLM_HDR = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}

# ============ State ============
def load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH))
    return {"last_update": None, "total_new": 0, "history": []}

def save_state(s):
    with open(STATE_PATH, "w") as f:
        json.dump(s, f, indent=2)

# ============ GitHub Discovery ============
def discover_new_repos():
    print("[1/4] 搜索GitHub新项目(5000+⭐)...", flush=True)
    existing = set()
    existing_ids = set()
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            for r in json.load(f):
                existing.add(r["name"].lower())
                existing_ids.add(r.get("id", 0))
    
    new_repos, seen = [], set()
    star_ranges = [(100000, None), (50000, 99999), (20000, 49999), (10000, 19999), (5000, 9999)]
    
    for min_s, max_s in star_ranges:
        q = f"stars:{min_s}..{max_s}" if max_s else f"stars:>={min_s}"
        for page in range(1, 4):
            url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=100&page={page}"
            try:
                resp = requests.get(url, headers=GH_HDR, timeout=30, verify=False)
                if resp.status_code == 403 and 'rate limit' in resp.text.lower():
                    print(f"  ⚠️ Rate limited, waiting 60s...", flush=True)
                    time.sleep(60)
                    resp = requests.get(url, headers=GH_HDR, timeout=30, verify=False)
                if resp.status_code != 200:
                    print(f"  GitHub {resp.status_code}, skip", flush=True)
                    break
                items = resp.json().get("items", [])
                if not items:
                    break
                for item in items:
                    name = item["full_name"].lower()
                    if name not in existing and name not in seen:
                        seen.add(name)
                        new_repos.append({
                            "id": item["id"], "name": item["full_name"],
                            "desc": item.get("description") or "",
                            "stars": item["stargazers_count"],
                            "url": item["html_url"],
                            "lang": item.get("language") or "-",
                            "topics": item.get("topics", []),
                            "created": item["created_at"],
                            "updated": item["updated_at"],
                            "first_seen": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        })
                print(f"  ✓ {q} p{page}: {len(items)} results", flush=True)
                time.sleep(2)
            except Exception as e:
                print(f"  ✗ {q}: {e}", flush=True)
                break
    
    print(f"  发现 {len(new_repos)} 个新项目", flush=True)
    return new_repos

# ============ Classification ============
def classify_repos(repos):
    print("[2/4] 分类...", flush=True)
    classify_path = os.path.join(BASE, "phase3_enhanced.py")
    with open(classify_path, encoding="utf-8") as f:
        code = f.read().split("def main")[0]
    loc = {"__file__": classify_path}
    exec(code, loc)
    classify_fn = loc["classify_repo"]
    
    cats = {}
    for r in repos:
        cat, _ = classify_fn(r["name"], r.get("desc", ""), r.get("lang", ""), r.get("topics", []))
        r["cat"] = cat
        cats[cat] = cats.get(cat, 0) + 1
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}", flush=True)
    return repos

# ============ TRANSLATE + RENHUA (MERGED - ONE API CALL) ============
def translate_and_explain(repos):
    """一次API调用完成: 中文描述 + 人话解读"""
    print("[3/4] 翻译+人话解读(合并调用)...", flush=True)
    
    # 加载现有人话
    existing_rh = {}
    if os.path.exists(RENHUA_PATH):
        with open(RENHUA_PATH, encoding="utf-8") as f:
            existing_rh = json.load(f)
    
    # 找需要处理的: 无中文描述 或 无人话解读
    to_process = []
    for r in repos:
        has_cn = any('\u4e00' <= c <= '\u9fff' for c in r.get("desc", ""))
        has_rh = False
        for k, v in existing_rh.items():
            if isinstance(v, dict) and k == r["name"]:
                has_rh = True; break
            if isinstance(v, str) and k == r["name"]:
                has_rh = True; break
        if not has_cn or not has_rh:
            to_process.append(r)
    
    if not to_process:
        print("  全部已处理", flush=True)
        return repos
    
    print(f"  需处理 {len(to_process)} 个项目", flush=True)
    
    desc_map = {}  # name → chinese desc
    rh_map = {}    # name → renhua object
    batch_size = 20
    
    for i in range(0, len(to_process), batch_size):
        batch = to_process[i:i+batch_size]
        lines = []
        for j, r in enumerate(batch):
            lines.append(f"[{j}] {r['name']} ({r['stars']}⭐): {r['desc'][:150]}")
        
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
                r = requests.post(LLM_API, headers=LLM_HDR,
                    json={"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 10000, "temperature": 0.3},
                    timeout=180, verify=False)
                if r.status_code == 200:
                    text = r.json()["choices"][0]["message"]["content"]
                    arr = json.loads(re.findall(r'\[.*\]', text, re.DOTALL)[0])
                    for item in arr:
                        idx = item["idx"]
                        name = batch[idx]["name"]
                        desc_map[name] = item.get("desc_zh", batch[idx]["desc"])
                        rh_map[name] = {
                            "one_liner": item.get("one_liner", ""),
                            "plain": item.get("plain", ""),
                            "analogy": item.get("analogy", ""),
                            "audience": item.get("audience", ""),
                        }
                    print(f"  batch {i//batch_size+1}: ✓ {len(arr)}", flush=True)
                    break
                elif r.status_code == 429:
                    wait = 30 + retry * 10
                    print(f"  [429] 等待{wait}s...", flush=True)
                    time.sleep(wait)
                else:
                    print(f"  [HTTP {r.status_code}] 等待10s...", flush=True)
                    time.sleep(10)
            except Exception as e:
                print(f"  [ERR:{e}] 等待15s...", flush=True)
                time.sleep(15)
        time.sleep(3)
    
    # Apply translations
    for r in repos:
        if r["name"] in desc_map:
            r["desc"] = desc_map[r["name"]]
    
    # Merge renhua
    for name, rh in rh_map.items():
        existing_rh[name] = rh
    with open(RENHUA_PATH, "w", encoding="utf-8") as f:
        json.dump(existing_rh, f, ensure_ascii=False, indent=2)
    
    print(f"  翻译: {len(desc_map)} 条, 人话: {len(rh_map)} 条 (总计 {len(existing_rh)})", flush=True)
    return repos

# ============ Merge & Rebuild ============
def merge_and_rebuild(new_repos):
    print("[4/4] 合并数据 + 重建...", flush=True)
    
    existing = []
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            existing = json.load(f)
    
    existing_names = {r["name"].lower() for r in existing}
    existing_ids = {r.get("id", 0) for r in existing}
    
    added = 0
    for r in new_repos:
        if r["name"].lower() not in existing_names and r.get("id", 0) not in existing_ids:
            existing.append({
                "id": r["id"], "name": r["name"], "desc": r["desc"],
                "stars": r["stars"], "url": r["url"], "lang": r["lang"],
                "topics": r.get("topics", []),
                "created": r.get("created", ""), "updated": r.get("updated", ""),
                "first_seen": r.get("first_seen", ""),
            })
            added += 1
    
    if added:
        existing.sort(key=lambda x: -x["stars"])
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"  manifest.json: +{added} → {len(existing)} 项目", flush=True)
    
    # Rebuild projects.json using gen_html.py logic
    rebuild_projects_json(existing)
    
    # Update state
    state = load_state()
    state["last_update"] = datetime.now(timezone.utc).isoformat()
    state["total_new"] = state.get("total_new", 0) + added
    state["history"].append({"time": state["last_update"], "new": added, "total": len(existing)})
    state["history"] = state["history"][-20:]
    save_state(state)
    
    print(f"✅ 完成: +{added} 新项目, 总计 {len(existing)} 项目", flush=True)
    return added

def rebuild_projects_json(repos):
    """Rebuild projects.json from source data"""
    print("  重建 projects.json...", flush=True)
    
    # Load translations
    desc_zh = {}
    for bf in ["translate_batch_0_done.json","translate_batch_1_done.json",
               "translate_batch_2_done.json","translate_batch_3_done.json"]:
        fp = os.path.join(BASE, bf)
        if os.path.exists(fp):
            with open(fp, encoding="utf-8") as f:
                for item in json.load(f):
                    if item.get("desc_zh"):
                        desc_zh[item["name"]] = item["desc_zh"]
    
    # Load renhua
    renhua = {}
    rh_path = os.path.join(BASE, "人话解读.json")
    if os.path.exists(rh_path):
        with open(rh_path, encoding="utf-8") as f:
            raw = json.load(f)
        for k, v in raw.items():
            if isinstance(v, dict):
                kstr = str(k)
                if kstr.isdigit():
                    # 数字key → 按位对应repos中的项目名
                    idx = int(kstr)
                    if 0 <= idx < len(repos):
                        renhua[repos[idx]["name"]] = v
                elif "/" in kstr:
                    # 项目名key → 直接用
                    renhua[kstr] = v
    
    # Load classifier
    with open(os.path.join(BASE, "phase3_enhanced.py"), encoding="utf-8") as f:
        code = f.read().split("def main")[0]
    loc = {"__file__": os.path.join(BASE, "phase3_enhanced.py")}
    exec(code, loc)
    classify = loc["classify_repo"]
    
    # Build
    projects = []
    for i, r in enumerate(repos):
        name = r["name"]
        cat, _ = classify(name, r.get("desc", ""), r.get("lang", ""), r.get("topics", []))
        desc = desc_zh.get(name) or r.get("desc", "")
        rh = renhua.get(name, "")
        projects.append({
            "id": i + 1, "cat": cat, "name": name,
            "desc": desc[:200], "stars": r["stars"],
            "lang": r.get("lang", "") or "-", "url": r["url"],
            "rh": rh if isinstance(rh, str) else rh,
            "first_seen": r.get("first_seen", "")[:10],
        })
    
    with open(os.path.join(BASE, "projects.json"), "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, separators=(',', ':'))
    print(f"  projects.json: {len(projects)} 项目 ({os.path.getsize(os.path.join(BASE,'projects.json'))//1024//1024}MB)", flush=True)

# ============ Deploy ============
def deploy_site():
    """Regenerate deploy/ from updated data"""
    print("[5/5] 部署站点...", flush=True)
    
    deploy_py = os.path.join(BASE, "deploy.py")
    if os.path.exists(deploy_py):
        result = subprocess.run([sys.executable, deploy_py], 
                               capture_output=True, text=True, cwd=BASE, timeout=60)
        if result.returncode == 0:
            print("  ✅ deploy.py 完成", flush=True)
            for line in result.stdout.strip().split('\n')[-5:]:
                print(f"  {line}", flush=True)
        else:
            print(f"  ⚠️ deploy.py 失败: {result.stderr[-200:]}", flush=True)
    else:
        print("  ⚠️ deploy.py 不存在，手动复制数据...", flush=True)
        import shutil
        shutil.copy2(os.path.join(BASE, "projects.json"), 
                    os.path.join(BASE, "deploy", "projects.json"))
        print("  ✅ projects.json 已复制到 deploy/", flush=True)

# ============ Main ============
def main():
    dry_run = "--dry-run" in sys.argv
    new_repos = discover_new_repos()
    
    if not new_repos:
        print("✅ 没有新项目", flush=True)
        state = load_state()
        state["last_update"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return
    
    if dry_run:
        print(f"\n🔍 干跑: 发现 {len(new_repos)} 个新项目，不动手")
        for r in new_repos[:15]:
            print(f"  {r['name']} ⭐{r['stars']}")
        if len(new_repos) > 15:
            print(f"  ... 还有 {len(new_repos)-15} 个")
        return
    
    classify_repos(new_repos)
    translate_and_explain(new_repos)
    added = merge_and_rebuild(new_repos)
    if added > 0:
        deploy_site()
    print(f"\\n✅ 全流程完成: +{added} 新项目", flush=True)

if __name__ == "__main__":
    main()
