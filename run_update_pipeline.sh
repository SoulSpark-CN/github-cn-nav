#!/bin/bash
# GitHub导航站 — 每日自动更新流水线
# 由 crontab 调度，零手动干预
# 流程: 计算飙升 → 部署 → 回归验证

set -euo pipefail

PROJECT_DIR="/home/soulspark/赚钱现金流项目/github中文导航站"
LOG_DIR="/home/soulspark/.hermes/logs/nav-update"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOGFILE="$LOG_DIR/$(date '+%Y-%m-%d').log"

mkdir -p "$LOG_DIR"

echo "==========================================" >> "$LOGFILE"
echo "[$TIMESTAMP] === GitHub导航站 每日更新 ===" >> "$LOGFILE"

# 从 ~/.hermes/.env 加载 GitHub token
ENV_FILE="/home/soulspark/.hermes/.env"
if [ -f "$ENV_FILE" ]; then
    # 提取 GITHUB_TOKEN 值（移除引号）
    GITHUB_TOKEN_VAL=$(grep '^GITHUB_TOKEN=' "$ENV_FILE" | head -1 | sed 's/^GITHUB_TOKEN=//' | sed 's/^"//;s/"$//' | sed "s/^'//;s/'$//")
    export GITHUB_TOKEN="$GITHUB_TOKEN_VAL"
    export GH_PAT="$GITHUB_TOKEN_VAL"
    echo "[CONFIG] GITHUB_TOKEN loaded from .env" >> "$LOGFILE"
else
    echo "[WARN] ~/.hermes/.env not found, running without token" >> "$LOGFILE"
fi

echo "[STEP 1/4] 计算近5日飙升..." >> "$LOGFILE"
cd "$PROJECT_DIR"
python3 src/compute_surge_v2.py --days 5 --top 50 --max-calls 900 2>&1 >> "$LOGFILE"
SURGE_EXIT=$?
echo "  → exit code: $SURGE_EXIT" >> "$LOGFILE"

echo "[STEP 2/4] 重建部署包..." >> "$LOGFILE"
python3 src/deploy.py 2>&1 >> "$LOGFILE"
DEPLOY_EXIT=$?
echo "  → exit code: $DEPLOY_EXIT" >> "$LOGFILE"

echo "[STEP 3/4] 回归验证..." >> "$LOGFILE"
python3 tests/regression.py 2>&1 >> "$LOGFILE"
TEST_EXIT=$?
echo "  → exit code: $TEST_EXIT" >> "$LOGFILE"

echo "[STEP 4/4] 结果:" >> "$LOGFILE"
if [ $TEST_EXIT -eq 0 ]; then
    echo "  ✅ 全部通过" >> "$LOGFILE"
else
    echo "  ⚠️ 回归测试失败，见日志: $LOGFILE" >> "$LOGFILE"
fi

# 清理日志（保留30天）
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true

echo "[$TIMESTAMP] === 完成 ===" >> "$LOGFILE"
echo "" >> "$LOGFILE"
