import sys
from PySide6.QtWidgets import QApplication
from src.gui.GSE_Generator import AchievementFetcherGUI
from src.core.cf_bypass import warm_up

def main():
    app = QApplication(sys.argv)
    warm_up()
    gui = AchievementFetcherGUI()
    gui.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()