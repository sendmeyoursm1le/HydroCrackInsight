import sys
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout

app = QApplication(sys.argv)

window = QWidget()
window.setWindowTitle("HydroCrack Insight")
window.resize(500, 300)

layout = QVBoxLayout()
label = QLabel("HydroCrack Insight запущен")
layout.addWidget(label)

window.setLayout(layout)
window.show()

sys.exit(app.exec())