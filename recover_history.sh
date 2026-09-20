#!/usr/bin/env bash
set -e
export PYTHONIOENCODING=utf-8

cd "$(dirname "$0")"

echo "==================================================="
echo "  Antigravity IDE History Recovery"
echo "==================================================="

python3 antigravity_ide_history_recovery.py "$@"
