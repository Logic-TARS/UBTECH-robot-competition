#!/bin/bash
# Task4 — 用系统 Qt 插件补全 cv2 offscreen 平台
export DISPLAY=:99
export QT_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/qt5/plugins
cd /workspace/GlobalHumanoidRobotChallenge2026_Baseline
echo "[INIT] Task4 Packing_Box..."
exec /isaac-sim/python.sh run_task4_wrapper.py
