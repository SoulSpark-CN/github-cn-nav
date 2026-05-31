#!/bin/bash
# 一键启动 GitHub 导航站
# 方式1: Python 内置服务器
PORT=${1:-8080}
echo "GitHub 导航站已启动: http://localhost:$PORT"
echo "按 Ctrl+C 停止"
python3 -m http.server $PORT --directory "$(dirname "$0")"
