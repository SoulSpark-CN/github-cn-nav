#!/usr/bin/env python3
"""工具模块：Token、日志、原子写入"""
import json, os, sys, tempfile, logging
from typing import Any, Dict, Optional
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def setup_logger(name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name or __name__)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger

def get_env(key: str, default: Any = None) -> Optional[str]:
    v = os.environ.get(key)
    if v:
        return v.strip()
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, val = line.split("=", 1)
                    if k.strip() == key:
                        return val.strip().strip('"').strip("'")
        except Exception:
            pass
    return default or ""

def get_github_token() -> str:
    t = get_env("GITHUB_TOKEN") or get_env("GH_TOKEN")
    if not t:
        sys.exit("GITHUB_TOKEN 未设置")
    return t

def get_llm_key() -> str:
    k = get_env("LLM_API_KEY") or get_env("DEEPSEEK_API_KEY")
    if not k:
        sys.exit("DEEPSEEK_API_KEY 未设置")
    return k

def get_llm_config() -> Dict[str, str]:
    return {
        "api": get_env("LLM_BASE_URL") or "https://api.deepseek.com/chat/completions",
        "model": get_env("LLM_MODEL") or "deepseek-chat",
    }

def atomic_write_json(data: Any, path: str, **kw) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **kw)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise
