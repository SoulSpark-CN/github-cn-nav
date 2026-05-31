#!/usr/bin/env python3
"""
通用工具模块：Token 获取、原子写入、日志配置等。
"""
import json, os, sys, tempfile, logging
from typing import Any, Dict, Optional
from pathlib import Path

# ---------- 路径常量 ----------
BASE_DIR = Path(__file__).resolve().parent.parent

MANIFEST_PATH = str(BASE_DIR / "data" / "manifest.json")
PROJECTS_PATH = str(BASE_DIR / "data" / "projects.json")
RENHUA_PATH = str(BASE_DIR / "data" / "人话解读.json")
STATE_PATH = str(BASE_DIR / "data" / ".update_state.json")
DISCOVERY_FILE = str(BASE_DIR / "data" / "discovery_candidates.json")
SURGE_OUTPUT_FILE = str(BASE_DIR / "data" / "surge_top100.json")


def get_project_root() -> Path:
    """返回项目根目录（src/ 的父目录）"""
    return Path(__file__).resolve().parent.parent

# ---------- 日志 ----------
def setup_logger(name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name or __name__)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    return logger

logger = setup_logger("utils")

# ---------- 环境变量读取 ----------
def get_env(key: str, default: Any = None) -> Optional[str]:
    value = os.environ.get(key)
    if value:
        return value.strip()

    # fallback: ~/.hermes/.env
    env_file = os.path.expanduser("~/.hermes/.env")
    if not value and os.path.exists(env_file):
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == key:
                            value = v.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning("读取 %s 时出错: %s", env_file, e)

    return value or default

def get_github_token() -> str:
    token = get_env("GITHUB_TOKEN") or get_env("GH_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN 未设置")
        sys.exit(1)
    return token

def get_llm_key() -> str:
    key = get_env("LLM_API_KEY") or get_env("DEEPSEEK_API_KEY") or get_env("DS_KEY")
    if not key:
        logger.error("LLM_API_KEY 未设置")
        sys.exit(1)
    return key

def get_llm_config() -> Dict[str, str]:
    return {
        "api": get_env("LLM_BASE_URL") or get_env("DS_API") or "https://api.deepseek.com/chat/completions",
        "model": get_env("LLM_MODEL") or "deepseek-chat",
    }

# ---------- 原子写入 JSON ----------
def atomic_write_json(data: Any, path: str, **json_kwargs) -> None:
    """原子写入 JSON 文件（先写临时文件，再 rename）"""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **json_kwargs)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise

# ---------- Git 代理配置 ----------
def is_dry_run() -> bool:
    return "--dry-run" in sys.argv
