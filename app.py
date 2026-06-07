# app.py
import sys
import logging
import warnings

from PyQt5.QtWidgets import QApplication

warnings.filterwarnings("ignore", category=DeprecationWarning)

# 配置日志（格式统一）
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s %(message)s')

from main_window import FloatingCaption

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FloatingCaption()
    sys.exit(app.exec_())