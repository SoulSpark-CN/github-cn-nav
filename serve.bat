@echo off
REM 一键启动 GitHub 导航站 (Windows)
set PORT=8080
echo GitHub 导航站已启动: http://localhost:%PORT%
echo 按 Ctrl+C 停止
python -m http.server %PORT% --directory "%~dp0"
