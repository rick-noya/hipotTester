import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Ensure the gui package is discoverable
import os
sys.path.append(os.path.dirname(__file__))

from gui.main_window import MainWindow

if __name__ == '__main__':
    # Set application attributes (optional, can improve appearance on some OS)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec()) 