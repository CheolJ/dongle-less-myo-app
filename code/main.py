"""Myo Monitor v4 application entry point.

BLE connection design reference: https://github.com/iomz/dl-myo
The application communicates through Bleak directly; dl-myo is not a runtime dependency.
"""
import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
