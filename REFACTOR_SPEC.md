# 项目重构说明书

## 目标结构

```
项目根/
├── src/
│   ├── __init__.py
│   ├── auto_update.py
│   ├── compute_surge.py
│   ├── classify_module.py
│   ├── deploy.py
│   ├── phase3_enhanced.py
│   └── utils.py
├── data/
│   ├── manifest.json
│   ├── projects.json
│   ├── 人话解读.json
│   ├── surge_top100.json
│   ├── translate_batch_0_done.json
│   ├── translate_batch_1_done.json
│   ├── translate_batch_2_done.json
│   ├── translate_batch_3_done.json
│   ├── 分类统计.json
│   └── discovery_candidates.json
├── deploy/
│   ├── index.html
│   ├── standalone.html
│   ├── projects.json
│   ├── surge_top100.json
│   ├── serve.sh
│   ├── serve.bat
│   └── README.txt
├── .github/workflows/update.yml
├── .gitignore
├── pyproject.toml  (新增)
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── requirements.txt
```

## 变更清单

### 1. 目录移动
- .py 文件 → src/
- 数据 JSON → data/

### 2. 所有 Python 文件路径引用修改
旧模式（每个文件各自定义）:
```python
BASE = os.path.dirname(os.path.abspath(__file__))
```

新模式（统一从 src/ 出发，往上一级到项目根）:
```python
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
```

### 3. 数据文件路径加 data/ 前缀
所有 `os.path.join(BASE, "manifest.json")` → `BASE / "data" / "manifest.json"`

具体每个文件的路径常量修改清单:

**utils.py** (`src/utils.py`):
```python
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

MANIFEST_PATH = BASE_DIR / "data" / "manifest.json"
PROJECTS_PATH = BASE_DIR / "data" / "projects.json"
RENHUA_PATH = BASE_DIR / "data" / "人话解读.json"
STATE_PATH = BASE_DIR / "data" / ".update_state.json"
DISCOVERY_FILE = BASE_DIR / "data" / "discovery_candidates.json"
SURGE_OUTPUT_FILE = BASE_DIR / "data" / "surge_top100.json"
```

**auto_update.py** (`src/auto_update.py`):
```python
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
MANIFEST_PATH = BASE / "data" / "manifest.json"
RENHUA_PATH = BASE / "data" / "人话解读.json"
STATE_PATH = BASE / "data" / ".update_state.json"
Output paths: 翻译结果写到 data/translate_batch_*.json
```

**compute_surge.py** (`src/compute_surge.py`):
```python
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
PROJECTS_FILE = BASE / "data" / "projects.json"
OUTPUT_FILE = BASE / "data" / "surge_top100.json"
DISCOVERY_FILE = BASE / "data" / "discovery_candidates.json"
```

**deploy.py** (`src/deploy.py`):
```python
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
DEPLOY = BASE / "deploy"
JSON_SRC = BASE / "data" / "projects.json"
SURGE_SRC = BASE / "data" / "surge_top100.json"
```
deploy.py 要把 data/projects.json 复制到 deploy/projects.json，不是从根读了。

**classify_module.py** (`src/classify_module.py`):
- 所有 `os.path.join(BASE, "xxx.json")` → `BASE / "data" / "xxx.json"`

**phase3_enhanced.py** (`src/phase3_enhanced.py`):
- 同上，路径加 data/ 前缀

### 4. utilities.py 新增函数
在 `utils.py` 新增:
- `get_project_root()` -> 统一获取项目根目录
- `data_path(name)` -> 拼接 data/ 下路径 DSL

### 5. 新增 pyproject.toml
```toml
[project]
name = "github-chinese-nav"
version = "3.0.0"
description = "GitHub 5000+ Star 项目中文导航站"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "urllib3>=2.0",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

### 6. .gitignore 更新
追加:
```
# Build artifacts
src/__pycache__/

# Aider artifacts (already covered by .aider*)
.ruff_cache/
.aider.tags.cache.v4/

# Python
__pycache__/
*.pyc
```

### 7. 数据文件跟踪策略
- data/projects.json, data/manifest.json, data/人话解读.json 保持 git 跟踪（它们是项目核心数据）
- data/translate_batch_*.json 添加到 .gitignore（它们是中间产物）

### 8. deploy/index.html 前端性能优化（重要！）

当前问题: 渲染 6788 个项目时一次全部 append 到 DOM，导致首屏卡死。

优化方案:
1. **虚拟滚动** - 只渲染可视区域的批次（每批 30 个），滚动到末尾再加载下一批
2. **防抖搜索** - 搜索输入加 200ms debounce，避免每次按键都过滤 6788 条数据
3. **搜索索引** - 预计算搜索用的扁平字符串，避免重复拼接
4. **懒加载人话数据** - projects.json 加载完后再异步加载人话解读数据，不阻塞首屏
5. **批量 DOM 更新** - 用 DocumentFragment + requestAnimationFrame 批量插入

修改 deploy/index.html 的 script 部分:
- 保持现有 CSS 不动（样式已经很好了）
- 重写 JS 部分:
  - `BATCH_SIZE = 30` 保持不变
  - 增加 `debounce(fn, delay)` 函数
  - 增加 `renderBatch(startIndex)` 函数，使用 requestAnimationFrame
  - IntersectionObserver 在底部触发加载下一批
  - 搜索时重置列表，从头开始过滤
  - 分类切换时重置列表
- standalone.html 同样更新（通过 deploy.py 重新生成）

### 9. standalone.html 不直接改
standalone.html 由 deploy.py 生成，改 deploy.py 即可，然后重新运行 `python3 src/deploy.py` 生成新的 standalone.html

## 执行顺序

1. 创建 src/__init__.py（空文件）
2. 移动 .py 到 src/
3. 修改所有 Python 文件的路径引用
4. 修改所有 Python 文件的 import（from utils → from src.utils 等——但因为在 src/ 里了，直接 from utils 或 from .utils 即可）
5. 创建 pyproject.toml
6. 更新 .gitignore
7. 优化 deploy/index.html JS
8. 运行 python3 src/deploy.py 重新生成 standalone.html
9. 验证: python3 src/auto_update.py --dry-run 至少不报 import 错误
