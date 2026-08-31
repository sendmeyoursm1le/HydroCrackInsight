from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app.database.database_service import DatabaseService
from app.users import UserSession


class LoginDialog(QDialog):
    def __init__(self, database_service: DatabaseService) -> None:
        super().__init__()

        self.database_service = database_service
        self.user_session: UserSession | None = None

        self.setWindowTitle("Вход в HydroCrack Insight")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout()

        title = QLabel("HydroCrack Insight")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold;")

        subtitle = QLabel("Выбор пользователя")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #555555;")

        form_layout = QFormLayout()

        self.user_combo = QComboBox()
        self._fill_users()

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self.try_login)

        form_layout.addRow("Пользователь", self.user_combo)
        form_layout.addRow("Пароль", self.password_input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.try_login)
        button_box.rejected.connect(self.reject)

        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("Войти")

        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("Отмена")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(form_layout)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def try_login(self) -> None:
        username = str(self.user_combo.currentData())
        password = self.password_input.text()

        user_session = self.database_service.authenticate_user(username, password)
        if user_session is None:
            QMessageBox.warning(
                self,
                "Ошибка входа",
                "Проверьте пользователя и пароль.",
            )
            self.password_input.selectAll()
            self.password_input.setFocus()
            return

        self.user_session = user_session
        self.accept()

    def _fill_users(self) -> None:
        for account in self.database_service.get_active_user_accounts():
            self.user_combo.addItem(
                f"{account.display_name} - {account.role_title}",
                account.username,
            )
