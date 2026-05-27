# Python 启动前创建 QApplication 避免 cv2 Qt 崩溃
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DISPLAY"] = ":99"
try:
    from PyQt5.QtWidgets import QApplication
    _app = QApplication([])
except Exception:
    pass
