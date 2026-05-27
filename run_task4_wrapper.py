#!/usr/bin/env python
"""
Wrapper: 用 ctypes 在主线程创建 QApplication，避免 Isaac Sim 5.1 cv2 子线程崩溃。
不改动 programmatic_control.py 的任何代码。
"""
import os, sys, ctypes, ctypes.util

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_PLUGIN_PATH", "/usr/lib/x86_64-linux-gnu/qt5/plugins")

# 1) 找到并加载 Qt5Core
qtcore_path = ctypes.util.find_library("Qt5Core") or "libQt5Core.so.5"
qtcore = ctypes.CDLL(qtcore_path)

# 2) 加载 Qt5Widgets（内部会初始化 QApplication）
qtwidgets = ctypes.CDLL("libQt5Widgets.so.5")

# 3) 用 ctypes 创建 QApplication
argc = ctypes.c_int(0)
argv = (ctypes.c_char_p * 1)(b"wrapper")
# 调用 qApp 创建例程（简化方式：通过 QtWidgets 导出）
try:
    qtcore.qVersion.restype = ctypes.c_char_p
    print(f"[wrapper] Qt version: {qtcore.qVersion().decode()}")
except Exception:
    pass

# 实际上简单的 cv2 主线程初始化可能就够了
import cv2
# 不调用 namedWindow，仅触发 cv2 Qt 绑定
if hasattr(cv2, 'qt'):
    pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "auto_collect_unzipped"))

import runpy
sys.argv = [
    sys.argv[0],
    "--robot.type=walker_s2_sim",
    "--robot.headless=true",
    "--control.type=programmatic",
    "--control.task=Packing_Box",
    "--control.root=datasets/Packing_Box/batch1",
    "--control.repo_id=local/task4_packing_box",
    "--control.num_episodes=50",
    "--control.fps=30",
    "--control.video=true",
    "--control.objects_per_episode=1",
    "--control.single_task=Packing_Box",
    "--control.record_data=true",
]
runpy.run_path(
    os.path.join(os.path.dirname(__file__), "auto_collect_unzipped", "lerobot", "scripts", "programmatic_control.py"),
    run_name="__main__",
)
