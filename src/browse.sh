#!/bin/bash
# GitHub 5000+ Star 项目终端浏览器
# 用法: ./browse.sh [--stats|--top N|--search 关键词|--random]
cd "$(dirname "$0")"
MANIFEST="manifest.json"

show_help() {
    python3 -c "
import json
with open('$MANIFEST') as f:
    repos = json.load(f)
cats = {}
for r in repos:
    cat = '其他'
    desc = (r.get('desc','') or '').lower()
    name = r['name'].lower()
    text = f'{name} {desc}'
    if any(kw in text for kw in ['cli','command line','terminal','tool','utility','package manager','docker','curl','http']): cat='🔧API-工具-命令行'
    elif any(kw in text for kw in ['react','vue','angular','svelte','css','frontend','ui ']): cat='🖥️前端-UI框架'
    elif any(kw in text for kw in ['framework','server','backend','api','microservice']): cat='⚙️后端-框架-API'
    elif any(kw in text for kw in ['os','kernel','system programming','low-level','assembly']): cat='💻操作系统-底层-内核'
    elif any(kw in text for kw in ['editor','ide','vim','neovim','emacs','plugin','linter']): cat='🛠️开发工具-编辑器-IDE'
    elif any(kw in text for kw in ['tutorial','course','book','awesome','learn','guide','interview']): cat='📚学习资源-教程-书籍'
    elif any(kw in text for kw in ['llm','gpt','transformer','language model','chatgpt']): cat='🤖大语言模型-LLM'
    elif any(kw in text for kw in ['agent','copilot','ai assistant','openhands']): cat='⚡AI应用-Agent'
    elif any(kw in text for kw in ['android','ios','flutter','mobile']): cat='📱移动开发'
    elif any(kw in text for kw in ['database','db','sql','nosql','redis','mongodb']): cat='🗄️数据科学-数据库'
    elif any(kw in text for kw in ['machine learning','deep learning','neural','pytorch','tensorflow']): cat='🧠AI-机器学习'
    elif any(kw in text for kw in ['automation','ci/cd','deploy','devops','terraform']): cat='🔄自动化-DevOps'
    elif any(kw in text for kw in ['game','unity','godot','minecraft']): cat='🎮游戏-娱乐'
    elif any(kw in text for kw in ['security','vpn','proxy','hack']): cat='🔒安全-网络'
    elif any(kw in text for kw in ['blockchain','web3','crypto','bitcoin']): cat='⛓️区块链'
    elif any(kw in text for kw in ['image','video','audio','music','stream']): cat='🎬媒体-音视频'
    elif any(kw in text for kw in ['trading','finance','quant']): cat='💰量化交易-金融'
    elif any(kw in text for kw in ['programming language','compiler','language runtime']): cat='📜编程语言-编译器'
    else: cat='📌其他'
    cats[cat] = cats.get(cat, 0) + 1
for c in sorted(cats, key=lambda x: -cats[x]):
    print(f'  {c}: {cats[c]}')
"
}

if [ $# -eq 0 ]; then
    echo "GitHub 5000+ Star 项目终端浏览器"
    echo "用法: ./browse.sh [--stats|--top N|--search 词|--random]"
    echo ""
    show_help
    exit 0
fi

case "$1" in
    --help|-h) show_help ;;
    --stats)
        python3 -c "
import json
with open('$MANIFEST') as f:
    repos = json.load(f)
stars = [r['stars'] for r in repos]
langs = {}
for r in repos:
    l = r.get('lang','') or '其他'
    langs[l] = langs.get(l, 0) + 1
print(f'总项目: {len(repos)}')
print(f'总星数: {sum(stars):,}')
print(f'平均星数: {sum(stars)//len(stars):,}')
print(f'最高星: {max(stars):,}')
print(f'语言种类: {len(langs)}')
for l,c in sorted(langs.items(), key=lambda x:-x[1])[:10]:
    print(f'  {l:20s}: {c:5d}')
" 2>/dev/null ;;
    --top)
        n=${2:-20}
        echo "🏆 TOP $n 项目"
        python3 -c "
import json
with open('$MANIFEST') as f:
    repos = json.load(f)
repos.sort(key=lambda r: -r['stars'])
for i, r in enumerate(repos[:$n], 1):
    print(f'{i:3d}. ⭐{r[\"stars\"]:>7,}  {r[\"name\"]}')
    desc = (r.get('desc','') or '')[:80]
    if desc: print(f'      {desc}')
" ;;
    --search)
        shift
        keyword="$*"
        [ -z "$keyword" ] && echo "用法: browse.sh --search <关键词>" && exit 1
        echo "🔍 搜索: $keyword"
        python3 -c "
import json
with open('$MANIFEST') as f:
    repos = json.load(f)
kw = '$keyword'.lower()
hits = [(r['stars'], r['name'], r.get('desc','')[:100]) for r in repos 
        if kw in r['name'].lower() or kw in (r.get('desc','') or '').lower()]
hits.sort(key=lambda x: -x[0])
if not hits:
    print('  无结果')
else:
    for i, (s, n, d) in enumerate(hits[:30], 1):
        print(f'{i:3d}. ⭐{s:>7,}  {n}')
        if d: print(f'      {d[:80]}')
    if len(hits) > 30: print(f'  ...还有{len(hits)-30}个结果')
" ;;
    --random)
        python3 -c "
import json, random
with open('$MANIFEST') as f:
    repos = json.load(f)
samples = random.sample(repos, min(10, len(repos)))
print('🎲 随机项目推荐')
for r in samples:
    print(f'  ⭐{r[\"stars\"]:>7,}  {r[\"name\"]}')
    desc = (r.get('desc','') or '')[:80]
    if desc: print(f'      {desc}')
" ;;
    *) 
        echo "未知参数: $1"
        echo "用法: ./browse.sh [--stats|--top N|--search 词|--random]" ;;
esac