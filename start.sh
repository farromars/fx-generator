#!/usr/bin/env bash
# ============================================================
# fx-generator macOS / Linux 启动脚本
# 双击或终端 `./start.sh` 运行
# ============================================================

set -e

# 切到脚本所在目录
cd "$(dirname "$0")"

echo
echo "============================================================"
echo " fx-generator  launcher (mac/linux)"
echo "============================================================"

# 1. Python 检查
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] 没找到 python3，请先安装 Python 3.11+"
    exit 1
fi

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[info]  Python $PYVER  ($(command -v python3))"

# 2. HF 镜像（国内可解注释）
# export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
if [ -n "${HF_ENDPOINT:-}" ]; then
    echo "[info]  HF_ENDPOINT=$HF_ENDPOINT"
fi

# 3. Agnes key 提示
if [ -z "${AGNES_API_KEY:-}" ]; then
    echo "[warn]  AGNES_API_KEY 未设置，云端 Agnes 不可用"
    echo "        export AGNES_API_KEY=你的key  之后再启动"
else
    echo "[info]  AGNES_API_KEY 已设置"
fi

echo
echo "[info]  启动 UI（浏览器自动打开 http://127.0.0.1:7860）"
echo "[info]  Ctrl+C 停止"
echo "------------------------------------------------------------"
echo

python3 app.py
